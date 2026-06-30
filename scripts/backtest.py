#!/usr/bin/env python3
"""Backtest the VWAP-reversion signal on historical Alpaca minute bars.

Usage:
    python scripts/backtest.py SPY 2026-06-01 2026-06-27

Pulls 1-min bars, splits by trading day (VWAP resets daily), runs the backtester
per session, and prints aggregate stats. Use this to sanity-check the edge and
tune params before paper, and paper before live.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import pandas as pd

from claudeinhood.backtest.backtester import BacktestResult, run_backtest
from claudeinhood.config import load_config


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    symbol, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    cfg = load_config()

    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(cfg.alpaca_api_key, cfg.alpaca_secret_key)
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=datetime.fromisoformat(start).replace(tzinfo=timezone.utc),
        end=datetime.fromisoformat(end).replace(tzinfo=timezone.utc),
        feed=DataFeed(cfg.alpaca_data_feed),
    )
    df = client.get_stock_bars(req).df
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")
    df = df[["open", "high", "low", "close", "volume"]]

    local = df.tz_convert("America/New_York")
    agg = BacktestResult()
    for day, day_df in local.groupby(local.index.date):
        # Regular trading hours only.
        rth = day_df.between_time("09:30", "16:00")
        if len(rth) < 40:
            continue
        res = run_backtest(rth, cfg.strategy)
        agg.trades.extend(res.trades)
        if res.n:
            print(f"{day}: {res.summary()}")

    print("\n=== AGGREGATE ===")
    print(agg.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
