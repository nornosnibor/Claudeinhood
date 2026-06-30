"""Risk manager — the safety layer that sits between a signal and an order.

Responsibilities:
  * Enforce a hard daily loss cap (trading halts for the day once breached).
  * Size positions so a single losing trade can't blow past the per-trade budget.
  * Track settled vs. unsettled cash so a cash account doesn't trip a
    good-faith settlement violation (option proceeds settle T+1).

All pure logic — the engine feeds it fills and equity; it answers yes/no + size.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class RiskConfig:
    # Hard daily loss cap as a fraction of starting-of-day equity. Trading
    # halts for the rest of the day once realized loss exceeds this.
    max_daily_loss_pct: float = 0.25
    # Max fraction of equity to risk (to the stop) on any single trade.
    max_risk_per_trade_pct: float = 0.10
    # Never deploy more than this fraction of equity into one position's premium.
    max_position_pct: float = 0.50
    # Optional ceiling on number of trades per day (0 = unlimited).
    max_trades_per_day: int = 0


@dataclass
class RiskState:
    start_of_day_equity: float
    equity: float
    day: date
    realized_pnl_today: float = 0.0
    trades_today: int = 0
    settled_cash: float = 0.0
    unsettled_cash: float = 0.0


@dataclass
class RiskManager:
    config: RiskConfig
    state: RiskState
    halt_reason: str | None = field(default=None)

    def roll_day(self, today: date, equity: float, settled_cash: float) -> None:
        """Reset daily counters at the start of a new session."""
        if today != self.state.day:
            self.state.day = today
            self.state.start_of_day_equity = equity
            self.state.realized_pnl_today = 0.0
            self.state.trades_today = 0
            self.halt_reason = None
        self.state.equity = equity
        self.state.settled_cash = settled_cash

    @property
    def daily_loss_limit(self) -> float:
        return self.config.max_daily_loss_pct * self.state.start_of_day_equity

    def can_trade(self) -> tuple[bool, str]:
        if self.halt_reason:
            return False, self.halt_reason
        loss = -self.state.realized_pnl_today
        if loss >= self.daily_loss_limit:
            self.halt_reason = (
                f"daily loss limit hit: -{loss:.2f} >= -{self.daily_loss_limit:.2f}"
            )
            return False, self.halt_reason
        if (
            self.config.max_trades_per_day
            and self.state.trades_today >= self.config.max_trades_per_day
        ):
            return False, "max trades per day reached"
        return True, "ok"

    def record_fill(self, realized_pnl_delta: float) -> None:
        """Call on every closing fill to update daily P&L and trade count."""
        self.state.realized_pnl_today += realized_pnl_delta
        self.state.equity += realized_pnl_delta
        self.state.trades_today += 1

    def size_option_order(
        self,
        *,
        premium_per_contract: float,
        underlying_entry: float,
        underlying_stop: float,
        contract_delta: float = 0.5,
        contract_multiplier: int = 100,
    ) -> int:
        """Return how many option contracts to buy, or 0 if no safe size exists.

        Premium is per share; cost per contract = premium * multiplier.
        Estimated risk per contract uses the underlying stop distance scaled by
        delta (a first-order estimate of option loss if the stop is hit).
        """
        cost_per_contract = premium_per_contract * contract_multiplier
        if cost_per_contract <= 0:
            return 0

        equity = self.state.equity
        # Budget 1: per-trade risk to the stop.
        risk_budget = self.config.max_risk_per_trade_pct * equity
        stop_dist = abs(underlying_entry - underlying_stop)
        est_risk_per_contract = max(
            stop_dist * abs(contract_delta) * contract_multiplier,
            0.01 * cost_per_contract,  # floor: assume at least 1% premium at risk
        )
        by_risk = int(risk_budget // est_risk_per_contract)

        # Budget 2: max capital deployed into premium.
        capital_budget = min(
            self.config.max_position_pct * equity,
            self.state.settled_cash,  # cash account: only spend settled cash
        )
        by_capital = int(capital_budget // cost_per_contract)

        return max(0, min(by_risk, by_capital))
