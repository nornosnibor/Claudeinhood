#!/usr/bin/env python3
"""Parameter sweep for the VWAP-reversion signal.

Pulls minute bars ONCE, then replays the strategy per trading day under many
parameter combos and ranks them by total return. This is in-sample exploration
to find tradeable settings + sanity-check whether any edge exists — NOT proof.
Anything promising must then survive out-of-sample + paper.

    python scripts/sweep.py SPY 2026-05-01 2026-06-28
"""
from __future__ import annotations

import itertools
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import pandas as pd

from claudeinhood.backtest.backtester import BacktestResult, run_backtest
from claudeinhood.config import load_config
from claudeinhood.strategy.vwap_reversion import VwapReversionParams


def fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
    cfg = load_config()
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(cfg.alpaca_api_key, cfg.alpaca_secret_key)
    req = StockBarsRequest(
        symbol_or_symbols=symbol, timeframe=TimeFrame.Minute,
        start=datetime.fromisoformat(start).replace(tzinfo=timezone.utc),
        end=datetime.fromisoformat(end).replace(tzinfo=timezone.utc),
        feed=DataFeed(cfg.alpaca_data_feed),
    )
    df = client.get_stock_bars(req).df
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")
    return df[["open", "high", "low", "close", "volume"]].tz_convert("America/New_York")


def evaluate(df: pd.DataFrame, params: VwapReversionParams) -> BacktestResult:
    agg = BacktestResult()
    for _, day_df in df.groupby(df.index.date):
        rth = day_df.between_time("09:30", "16:00")
        if len(rth) < 40:
            continue
        agg.trades.extend(run_backtest(rth, params).trades)
    return agg


def main() -> int:
    symbol, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    df = fetch(symbol, start, end)
    days = len(set(df.index.date))
    print(f"Loaded {len(df)} bars across {days} sessions of {symbol} "
          f"({start}..{end}, feed={load_config().alpaca_data_feed})\n")

    grid = dict(
        min_dev_z=[1.0, 1.5, 2.0],
        require_exhaustion=[True, False],
        trend_filter=[True, False],
        stop_atr_mult=[1.0, 1.5],
        target_vwap_fraction=[0.6, 0.8, 1.0],
    )
    keys = list(grid)
    rows = []
    for combo in itertools.product(*grid.values()):
        p = VwapReversionParams(**dict(zip(keys, combo)))
        res = evaluate(df, p)
        if res.n == 0:
            continue
        rows.append((res.total_return, res.n, res.win_rate, res.avg_return, combo))

    rows.sort(reverse=True)
    print(f"{'total%':>8} {'trades':>6} {'win%':>6} {'avg%':>7}  params")
    print("-" * 78)
    for total, n, wr, avg, combo in rows[:15]:
        cfg_str = ", ".join(f"{k}={v}" for k, v in zip(keys, combo))
        print(f"{total*100:8.2f} {n:6d} {wr*100:6.1f} {avg*100:7.3f}  {cfg_str}")
    if not rows:
        print("No configuration produced any trades.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
