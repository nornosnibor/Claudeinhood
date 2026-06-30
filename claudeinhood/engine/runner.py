"""Engine loop: data -> strategy -> risk -> order -> position management.

This is intentionally a deterministic rules engine. There is no LLM in the live
decision path — latency makes that unworkable for scalping. Claude's role is to
build, backtest, and tune this; the engine executes.

The loop is broker-agnostic. For paper validation, pass an AlpacaBroker; once
Robinhood is wired, pass a RobinhoodBroker — nothing else changes.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..broker.base import Broker, OrderSide
from ..config import AppConfig
from ..data.alpaca_data import AlpacaData
from ..flow.base import FlowFilter, NullFlowFilter, flow_allows
from ..options.selector import OptionsProvider
from ..risk.manager import RiskManager
from ..strategy.base import Side, Signal
from ..strategy.vwap_reversion import VwapReversionStrategy

log = logging.getLogger("claudeinhood.engine")


@dataclass
class OpenTrade:
    option_symbol: str
    side: Side
    qty: int
    entry_premium: float
    underlying_entry: float
    underlying_target: float
    underlying_stop: float


class Engine:
    def __init__(
        self,
        config: AppConfig,
        broker: Broker,
        data: AlpacaData,
        risk: RiskManager,
        options_provider: Optional[OptionsProvider] = None,
        flow_filter: Optional[FlowFilter] = None,
    ):
        self.cfg = config
        self.broker = broker
        self.data = data
        self.risk = risk
        self.strategy = VwapReversionStrategy(config.strategy)
        self.open_trade: Optional[OpenTrade] = None
        # Shadow mode: evaluate + log intended trades, place no orders.
        self.dry_run = config.dry_run
        # Flow-confirmation veto layer. Defaults to a no-op (never vetoes) until
        # a real provider (e.g. ProBors REST) is wired in.
        self.flow = flow_filter or NullFlowFilter()
        # Quotes + selects a 0/1-DTE contract. None -> option entries are skipped
        # (e.g. in dry-run/equity-only or tests without a live chain).
        self.options = options_provider

    # ---- one iteration of the loop -------------------------------------
    def step(self) -> None:
        if not self.broker.is_market_open():
            log.debug("market closed")
            return

        acct = self.broker.get_account()
        self.risk.roll_day(date.today(), acct.equity, acct.settled_cash)

        df_all = self.data.recent_minute_bars(self.cfg.primary_symbol)
        df = AlpacaData.current_session_only(df_all)
        if df.empty:
            return

        # Manage an open position first (exits take priority over entries).
        if self.open_trade is not None:
            self._manage_open(df)
            return

        ok, why = self.risk.can_trade()
        if not ok:
            log.info("not trading: %s", why)
            return

        signal = self.strategy.evaluate(df)
        if not signal.is_actionable:
            log.debug("flat: %s", signal.reason)
            return

        # Flow veto: don't fade a stretched move that strong same-direction flow
        # says is real (i.e. not an overreaction).
        reading = self.flow.read(self.cfg.primary_symbol)
        allowed, flow_why = flow_allows(signal.side, reading)
        if not allowed:
            log.info("signal %s vetoed by flow: %s", signal.side.value, flow_why)
            return

        log.info("signal %s conf=%.2f (%s) | %s", signal.side.value,
                 signal.confidence, signal.reason, flow_why)
        self._enter(signal, underlying_price=signal.entry_ref)

    # ---- entry ----------------------------------------------------------
    def _enter(self, signal: Signal, underlying_price: float) -> None:
        if self.dry_run:
            log.info("[DRY RUN] would enter %s @ %.2f target=%.2f stop=%.2f (%s)",
                     signal.side.value, signal.entry_ref, signal.target,
                     signal.stop, signal.reason)
            return
        if not self.cfg.trade_options:
            # Equity path (e.g. for non-SPY shares). Size by capital only.
            qty = self.risk.size_option_order(
                premium_per_contract=underlying_price / 100,  # placeholder
                underlying_entry=signal.entry_ref,
                underlying_stop=signal.stop,
                contract_multiplier=1,
                contract_delta=1.0,
            )
            if qty <= 0:
                log.info("equity size = 0, skipping")
                return
            side = OrderSide.BUY if signal.side is Side.LONG else OrderSide.SELL
            res = self.broker.submit_equity_order(
                symbol=self.cfg.primary_symbol, side=side, qty=qty)
            log.info("equity order: %s", res)
            return

        if self.options is None:
            log.info("no options provider configured; skipping option entry")
            return
        choice = self.options.select(
            self.cfg.primary_symbol, underlying_price, signal.side,
            date.today(), self.cfg.max_dte,
        )
        if choice is None:
            log.info("no suitable contract available")
            return

        premium = choice.est_premium
        if premium is None:
            log.warning("no premium quote for %s; skipping", choice.occ_symbol)
            return

        qty = self.risk.size_option_order(
            premium_per_contract=premium,
            underlying_entry=signal.entry_ref,
            underlying_stop=signal.stop,
            contract_delta=choice.est_delta or 0.5,
        )
        if qty <= 0:
            log.info("risk-sized qty = 0 (premium %.2f), skipping", premium)
            return

        res = self.broker.submit_option_order(
            option_symbol=choice.occ_symbol, side=OrderSide.BUY, qty=qty,
            limit_price=premium,
        )
        log.info("option BUY: %s", res)
        if res.filled_price:
            self.open_trade = OpenTrade(
                option_symbol=choice.occ_symbol, side=signal.side, qty=qty,
                entry_premium=res.filled_price, underlying_entry=signal.entry_ref,
                underlying_target=signal.target, underlying_stop=signal.stop,
            )

    # ---- exit management ------------------------------------------------
    def _manage_open(self, df) -> None:
        t = self.open_trade
        assert t is not None
        last_price = float(df["close"].iloc[-1])

        hit_target = (
            last_price >= t.underlying_target if t.side is Side.LONG
            else last_price <= t.underlying_target
        )
        hit_stop = (
            last_price <= t.underlying_stop if t.side is Side.LONG
            else last_price >= t.underlying_stop
        )
        if not (hit_target or hit_stop):
            return

        reason = "target" if hit_target else "stop"
        res = self.broker.submit_option_order(
            option_symbol=t.option_symbol, side=OrderSide.SELL, qty=t.qty)
        log.info("option SELL (%s): %s", reason, res)
        if res.filled_price is not None:
            pnl = (res.filled_price - t.entry_premium) * t.qty * 100
            self.risk.record_fill(pnl)
            log.info("closed %s pnl=%.2f day_pnl=%.2f", reason, pnl,
                     self.risk.state.realized_pnl_today)
        self.open_trade = None

    # ---- run forever ----------------------------------------------------
    def run(self) -> None:
        log.info("engine starting (paper=%s feed=%s symbol=%s)",
                 self.cfg.alpaca_paper, self.cfg.alpaca_data_feed,
                 self.cfg.primary_symbol)
        while True:
            try:
                self.step()
            except Exception:  # keep the loop alive; log and continue
                log.exception("step error")
            time.sleep(self.cfg.poll_seconds)
