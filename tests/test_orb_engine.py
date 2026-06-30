"""End-to-end ORB paper engine wiring: a volume-confirmed opening-range break
opens an option position; a premium move past target closes it and journals the
outcome. In-memory fakes, no network."""
from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from claudeinhood.broker.base import Account, OrderResult, OrderSide
from claudeinhood.config import AppConfig
from claudeinhood.engine.orb_engine import ORBPaperEngine
from claudeinhood.journal import Journal
from claudeinhood.options.selector import OptionChoice
from claudeinhood.risk.manager import RiskConfig, RiskManager, RiskState
from claudeinhood.strategy.base import Side

ET = ZoneInfo("America/New_York")


def _session_with_break():
    """OR 9:30-9:45 around 540; then a volume-confirmed break above OR high."""
    rows, idx = [], []
    base = datetime(2026, 7, 1, 9, 30, tzinfo=ET)
    # 3 OR bars (9:30,9:35,9:40): tight range 539.8-540.2, modest volume
    for k, (o, h, l, c) in enumerate([(540, 540.2, 539.8, 540.0),
                                      (540, 540.2, 539.9, 540.1),
                                      (540.1, 540.2, 539.9, 540.0)]):
        rows.append((o, h, l, c, 1000)); idx.append(base + pd.Timedelta(minutes=5 * k))
    # 9:45 inside; 9:50 breakout close above 540.2 with big volume
    rows.append((540.0, 540.2, 539.9, 540.15, 1000)); idx.append(base + pd.Timedelta(minutes=15))
    rows.append((540.2, 540.8, 540.2, 540.7, 5000)); idx.append(base + pd.Timedelta(minutes=20))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                        index=pd.DatetimeIndex(idx))


class FakeBroker:
    def __init__(self):
        self.orders = []
    def is_market_open(self): return True
    def get_account(self):
        return Account(equity=500.0, cash=500.0, settled_cash=500.0, day=date.today())
    def get_position(self, s): return None
    def submit_option_order(self, *, option_symbol, side, qty, limit_price=None):
        self.orders.append((option_symbol, side, qty))
        price = limit_price if limit_price is not None else 1.50  # exit fill (mid)
        return OrderResult(id="x", symbol=option_symbol, side=side, qty=qty,
                           filled_price=price, status="filled")
    def submit_equity_order(self, **k): raise NotImplementedError


class FakeData:
    def __init__(self, df): self._df = df
    def recent_bars(self, symbol, bar_minutes=5, lookback_minutes=420): return self._df


class FakeOptions:
    def __init__(self): self.mid = 1.00
    def select(self, underlying, price, side, today, max_dte):
        right = "C" if side is Side.LONG else "P"
        return OptionChoice(occ_symbol=f"SPY260701{right}00540000", expiry=today,
                            strike=540.0, right=right, est_premium=1.00, est_delta=0.5)
    def latest_mid(self, occ): return self.mid


def _cfg():
    c = AppConfig(); c.primary_symbol = "SPY"; c.dry_run = False
    c.orb_minutes = 15; c.orb_volume_mult = 1.2
    c.target_premium_pct = 0.20; c.stop_premium_pct = 0.22
    c.max_trades_per_session = 1
    return c


def _risk():
    return RiskManager(RiskConfig(max_daily_loss_pct=0.25, max_risk_per_trade_pct=0.10,
                                  max_position_pct=0.50),
                       RiskState(start_of_day_equity=500.0, equity=500.0,
                                 day=date.today(), settled_cash=500.0))


def _engine(broker, data, options, journal, when):
    return ORBPaperEngine(_cfg(), broker, data, options, _risk(), journal,
                          now_fn=lambda: when)


def test_orb_break_opens_and_target_closes():
    j = Journal(Path(tempfile.mkdtemp()) / "orb.jsonl")
    broker, data, opts = FakeBroker(), FakeData(_session_with_break()), FakeOptions()
    # 10:30 ET -> inside entry window
    eng = _engine(broker, data, opts, j, datetime(2026, 7, 1, 10, 30, tzinfo=ET))

    eng.step()  # should enter on the break
    assert eng.open_trade is not None
    assert broker.orders[0][1] is OrderSide.BUY
    assert j.summarize()["predictions"] == 1

    opts.mid = 1.25  # +25% -> target
    eng.step()       # should exit
    assert eng.open_trade is None
    s = j.summarize()
    assert s["resolved"] == 1 and s["realized_win_rate"] == 100.0


def test_no_entry_before_window():
    j = Journal(Path(tempfile.mkdtemp()) / "orb.jsonl")
    broker = FakeBroker()
    eng = _engine(broker, FakeData(_session_with_break()), FakeOptions(), j,
                  datetime(2026, 7, 1, 9, 40, tzinfo=ET))  # before OR completes
    eng.step()
    assert eng.open_trade is None and not broker.orders


def test_stop_closes_with_loss():
    j = Journal(Path(tempfile.mkdtemp()) / "orb.jsonl")
    broker, opts = FakeBroker(), FakeOptions()
    eng = _engine(broker, FakeData(_session_with_break()), opts, j,
                  datetime(2026, 7, 1, 10, 30, tzinfo=ET))
    eng.step()
    opts.mid = 0.70  # -30% -> stop
    eng.step()
    assert eng.open_trade is None
    assert j.summarize()["realized_win_rate"] == 0.0
