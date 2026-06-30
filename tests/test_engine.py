"""End-to-end wiring test: bars -> signal -> flow veto -> options -> risk -> order.

Uses in-memory fakes for broker/data/options so no network or SDK is needed.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from claudeinhood.broker.base import Account, OrderResult, OrderSide, Position
from claudeinhood.config import AppConfig
from claudeinhood.engine.runner import Engine
from claudeinhood.flow.base import FlowReading
from claudeinhood.options.selector import OptionChoice
from claudeinhood.risk.manager import RiskConfig, RiskManager, RiskState
from claudeinhood.strategy.base import Side
from claudeinhood.strategy.vwap_reversion import VwapReversionParams


def _overreaction_df():
    rows = [(100, 100.05, 99.95, 100, 1000) for _ in range(58)]
    rows.append((100, 100.0, 99.0, 99.2, 5000))      # down thrust
    rows.append((99.2, 99.9, 99.1, 99.6, 6000))      # reversal bar
    idx = pd.date_range("2026-06-30 13:30", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)


class FakeBroker:
    def __init__(self):
        self.orders = []

    def is_market_open(self):
        return True

    def get_account(self):
        return Account(equity=500.0, cash=500.0, settled_cash=500.0, day=date.today())

    def get_position(self, symbol):
        return None

    def submit_option_order(self, *, option_symbol, side, qty, limit_price=None):
        self.orders.append((option_symbol, side, qty))
        return OrderResult(id="1", symbol=option_symbol, side=side, qty=qty,
                           filled_price=limit_price or 0.5, status="filled")

    def submit_equity_order(self, *, symbol, side, qty, limit_price=None):
        self.orders.append((symbol, side, qty))
        return OrderResult(id="1", symbol=symbol, side=side, qty=qty,
                           filled_price=limit_price or 100.0, status="filled")


class FakeData:
    def __init__(self, df):
        self._df = df

    def recent_minute_bars(self, symbol, lookback_minutes=240):
        return self._df


class FakeOptions:
    def select(self, underlying, underlying_price, side, today, max_dte):
        right = "C" if side is Side.LONG else "P"
        return OptionChoice(occ_symbol=f"{underlying}260630{right}00100000",
                            expiry=date(2026, 6, 30), strike=100.0, right=right,
                            est_premium=0.5, est_delta=0.5)


class StaticFlow:
    def __init__(self, reading):
        self._r = reading

    def read(self, symbol):
        return self._r


def _config():
    cfg = AppConfig()
    cfg.primary_symbol = "SPY"
    cfg.trade_options = True
    cfg.dry_run = False
    cfg.strategy = VwapReversionParams(min_dev_z=1.0, trend_filter=False)
    return cfg


def _risk():
    return RiskManager(
        RiskConfig(max_daily_loss_pct=0.25, max_risk_per_trade_pct=0.10,
                   max_position_pct=0.50),
        RiskState(start_of_day_equity=500.0, equity=500.0, day=date.today(),
                  settled_cash=500.0),
    )


def test_full_entry_path_opens_trade():
    broker = FakeBroker()
    engine = Engine(_config(), broker, FakeData(_overreaction_df()), _risk(),
                    options_provider=FakeOptions())
    engine.step()
    assert broker.orders, "expected an option order to be submitted"
    sym, side, qty = broker.orders[0]
    assert side is OrderSide.BUY and qty > 0
    assert engine.open_trade is not None
    assert engine.open_trade.side is Side.LONG


def test_flow_veto_blocks_entry():
    broker = FakeBroker()
    bearish = FlowReading(net_sentiment=-0.9, strength=0.9)  # opposes the LONG fade
    engine = Engine(_config(), broker, FakeData(_overreaction_df()), _risk(),
                    options_provider=FakeOptions(), flow_filter=StaticFlow(bearish))
    engine.step()
    assert not broker.orders, "flow veto should have blocked the order"
    assert engine.open_trade is None


def test_dry_run_places_no_orders():
    cfg = _config()
    cfg.dry_run = True
    broker = FakeBroker()
    engine = Engine(cfg, broker, FakeData(_overreaction_df()), _risk(),
                    options_provider=FakeOptions())
    engine.step()
    assert not broker.orders
    assert engine.open_trade is None
