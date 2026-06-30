"""Lightweight event-driven backtester for the underlying signal.

It replays historical 1-minute bars through the strategy and simulates the
reversion trade on the UNDERLYING (not options) to measure the raw edge of the
signal: win rate, average move captured, expectancy. Option P&L depends on
premium/greeks and is validated separately on Alpaca paper — but if the
underlying signal has no edge, the options version won't either.

Exits: target (back toward VWAP) or stop (ATR-based), whichever comes first,
plus a time stop after ``max_hold_bars`` bars.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from ..strategy.base import Side
from ..strategy.vwap_reversion import VwapReversionParams, VwapReversionStrategy


@dataclass
class Trade:
    entry_idx: int
    side: Side
    entry: float
    exit: float
    bars_held: int
    outcome: str  # "target" | "stop" | "time"

    @property
    def ret(self) -> float:
        if self.side is Side.LONG:
            return (self.exit - self.entry) / self.entry
        return (self.entry - self.exit) / self.entry


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.ret > 0)
        return wins / len(self.trades)

    @property
    def avg_return(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.ret for t in self.trades) / len(self.trades)

    @property
    def total_return(self) -> float:
        return sum(t.ret for t in self.trades)

    def summary(self) -> str:
        return (
            f"trades={self.n} win_rate={self.win_rate*100:.1f}% "
            f"avg_ret={self.avg_return*100:.3f}% total={self.total_return*100:.2f}%"
        )


def run_backtest(
    session_df: pd.DataFrame,
    params: Optional[VwapReversionParams] = None,
    *,
    warmup: int = 30,
    max_hold_bars: int = 20,
) -> BacktestResult:
    """Replay a single session's bars. Pass one trading day at a time so VWAP is
    session-scoped (use AlpacaData.current_session_only or group by date).
    """
    strat = VwapReversionStrategy(params)
    result = BacktestResult()
    i = warmup
    n = len(session_df)

    while i < n:
        window = session_df.iloc[: i + 1]
        sig = strat.evaluate(window)
        if not sig.is_actionable:
            i += 1
            continue

        entry = sig.entry_ref
        exit_price = entry
        outcome = "time"
        held = 0
        for j in range(i + 1, min(i + 1 + max_hold_bars, n)):
            bar = session_df.iloc[j]
            held = j - i
            if sig.side is Side.LONG:
                if bar["low"] <= sig.stop:
                    exit_price, outcome = sig.stop, "stop"; break
                if bar["high"] >= sig.target:
                    exit_price, outcome = sig.target, "target"; break
            else:
                if bar["high"] >= sig.stop:
                    exit_price, outcome = sig.stop, "stop"; break
                if bar["low"] <= sig.target:
                    exit_price, outcome = sig.target, "target"; break
            exit_price = float(bar["close"])

        result.trades.append(Trade(i, sig.side, entry, exit_price, held, outcome))
        # Skip past the trade we just simulated to avoid overlapping entries.
        i += max(held, 1)

    return result
