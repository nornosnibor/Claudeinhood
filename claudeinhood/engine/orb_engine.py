"""ORB paper engine for SPY — forward-test harness.

Flow per loop:
  flat  -> if inside the entry window and ORB fires, buy a 0/1-DTE option, log a
           PREDICTION to the journal.
  in    -> monitor the option premium; exit at +target / -stop / force-flat,
           log the OUTCOME to the journal.

Deterministic, broker-agnostic, journaled. No LLM in the loop. Built for Alpaca
paper today; swap the broker for Robinhood later without touching this file.
"""
from __future__ import annotations

import logging
import time as _time
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from ..broker.base import Broker, OrderSide
from ..config import AppConfig
from ..data.alpaca_data import AlpacaData
from ..exits import premium_exit
from ..journal import Journal, Outcome, Prediction
from ..options.selector import OptionsProvider
from ..risk.manager import RiskManager
from ..session_rules import SessionRules, can_enter, must_flat, size_multiplier
from ..strategy.base import Side
from ..strategy.orb import ORBParams, ORBStrategy

log = logging.getLogger("claudeinhood.orb")
ET = ZoneInfo("America/New_York")


@dataclass
class ORBTrade:
    prediction_id: str
    option_symbol: str
    side: Side
    qty: int
    entry_premium: float


class ORBPaperEngine:
    def __init__(self, cfg: AppConfig, broker: Broker, data: AlpacaData,
                 options: OptionsProvider, risk: RiskManager, journal: Journal,
                 rules: Optional[SessionRules] = None, now_fn=None):
        self.cfg = cfg
        self.broker = broker
        self.data = data
        self.options = options
        self.risk = risk
        self.journal = journal
        self.rules = rules or SessionRules(or_minutes=cfg.orb_minutes)
        self.strategy = ORBStrategy(ORBParams(
            or_minutes=cfg.orb_minutes, volume_mult=cfg.orb_volume_mult,
            no_entry_after=self.rules.entry_end))
        self._now = now_fn or (lambda: datetime.now(ET))
        self.open_trade: Optional[ORBTrade] = None
        self._session: Optional[date] = None
        self._trades_today = 0

    def _roll_session(self, today: date, equity: float, settled: float):
        if today != self._session:
            self._session = today
            self._trades_today = 0
        self.risk.roll_day(today, equity, settled)

    def step(self) -> None:
        if not self.broker.is_market_open():
            return
        now = self._now()
        acct = self.broker.get_account()
        self._roll_session(now.date(), acct.equity, acct.settled_cash)

        # 600-min lookback always reaches the 9:30 open, even on a late start.
        df_all = self.data.recent_bars(self.cfg.primary_symbol, self.cfg.bar_minutes,
                                       lookback_minutes=600)
        df = AlpacaData.current_session_only(df_all)
        if df.empty:
            return

        if self.open_trade is not None:
            self._manage(now)
            return

        if self._trades_today >= self.cfg.max_trades_per_session:
            return
        ok, why = self.risk.can_trade()
        if not ok:
            log.info("risk halt: %s", why)
            return
        ok, why = can_enter(now, self.rules)
        if not ok:
            log.debug("no entry: %s", why)
            return

        sig = self.strategy.evaluate(df)
        if not sig.is_actionable:
            return
        self._enter(now, sig)

    # ---- entry ----
    def _enter(self, now: datetime, sig) -> None:
        price = sig.entry_ref
        if self.cfg.dry_run:
            log.info("[DRY] ORB %s @ %.2f (%s)", sig.side.value, price, sig.reason)
            self._trades_today += 1
            return

        choice = self.options.select(self.cfg.primary_symbol, price, sig.side,
                                     now.date(), self.cfg.max_dte)
        if choice is None or choice.est_premium is None:
            log.info("no quotable contract; skip")
            return

        mult = size_multiplier(now.date(), self.rules)
        qty = int(self.risk.size_option_order(
            premium_per_contract=choice.est_premium,
            underlying_entry=sig.entry_ref, underlying_stop=sig.stop,
            contract_delta=choice.est_delta or 0.5) * mult)
        if qty <= 0:
            log.info("size 0 (premium %.2f, fomc_mult %.2f); skip", choice.est_premium, mult)
            return

        res = self.broker.submit_option_order(
            option_symbol=choice.occ_symbol, side=OrderSide.BUY, qty=qty,
            limit_price=choice.est_premium)
        if res.filled_price is None:
            log.warning("entry not filled: %s", res.status)
            return

        pid = uuid.uuid4().hex[:12]
        self.journal.predict(Prediction(
            id=pid, strategy="orb", symbol=self.cfg.primary_symbol, side=sig.side.value,
            underlying_entry=sig.entry_ref, target=sig.target, stop=sig.stop,
            thesis=sig.reason, predicted="target", option_symbol=choice.occ_symbol,
            entry_premium=res.filled_price, target_premium_pct=self.cfg.target_premium_pct,
            regime="fomc_week" if mult < 1 else "normal", confidence=sig.confidence))
        self.open_trade = ORBTrade(pid, choice.occ_symbol, sig.side, qty, res.filled_price)
        self._trades_today += 1
        log.info("ENTER %s %s x%d @ %.2f (pred %s)", sig.side.value,
                 choice.occ_symbol, qty, res.filled_price, pid)

    # ---- manage / exit ----
    def _manage(self, now: datetime) -> None:
        t = self.open_trade
        assert t is not None
        force = must_flat(now, self.rules)
        mid = self.options.latest_mid(t.option_symbol) if hasattr(self.options, "latest_mid") else None

        reason = None
        pnl = 0.0
        if mid is not None:
            reason, pnl = premium_exit(t.entry_premium, mid,
                                       target_pct=self.cfg.target_premium_pct,
                                       stop_pct=self.cfg.stop_premium_pct)
        if force and reason is None:
            reason = "time"
            if mid is not None:
                pnl = (mid - t.entry_premium) / t.entry_premium
        if reason is None:
            return

        res = self.broker.submit_option_order(
            option_symbol=t.option_symbol, side=OrderSide.SELL, qty=t.qty)
        exit_premium = res.filled_price if res.filled_price is not None else (mid or t.entry_premium)
        pnl = (exit_premium - t.entry_premium) / t.entry_premium
        self.risk.record_fill((exit_premium - t.entry_premium) * t.qty * 100)
        self.journal.resolve(Outcome(
            id=t.prediction_id, result=reason, exit_premium=exit_premium,
            pnl_pct=pnl, lesson=""))
        log.info("EXIT %s %s pnl=%.1f%% (pred %s)", reason, t.option_symbol,
                 pnl * 100, t.prediction_id)
        self.open_trade = None

    def run(self) -> None:
        log.info("ORB paper engine up (symbol=%s bar=%dm OR=%dm target=%.0f%% stop=%.0f%% dry=%s)",
                 self.cfg.primary_symbol, self.cfg.bar_minutes, self.cfg.orb_minutes,
                 self.cfg.target_premium_pct * 100, self.cfg.stop_premium_pct * 100,
                 self.cfg.dry_run)
        from datetime import time as _t
        while True:
            try:
                self.step()
            except Exception:
                log.exception("step error")
            now = self._now()
            # Clean shutdown after the close (only once flat) so scheduled runs
            # don't linger overnight.
            if now.time() >= _t(16, 5) and self.open_trade is None:
                log.info("after close and flat — shutting down for the day")
                return
            _time.sleep(self.cfg.poll_seconds)
