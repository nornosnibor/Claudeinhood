#!/usr/bin/env python3
"""Directional diagnostic: at each stretched/thrust bar, does the edge point
toward FADE (mean-reversion) or MOMENTUM (continuation)?

Uses symmetric 1-ATR target/stop so the win rate is a clean read on direction:
 >50% means that side has an edge. This isn't a strategy, it's a compass.

    python scripts/direction_test.py SPY 2026-05-01 2026-06-28 [min_z] [hold]
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import numpy as np
import pandas as pd

from claudeinhood.config import load_config
from claudeinhood.data.indicators import compute_snapshot


def fetch(symbol, start, end):
    cfg = load_config()
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    c = StockHistoricalDataClient(cfg.alpaca_api_key, cfg.alpaca_secret_key)
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute,
                           start=datetime.fromisoformat(start).replace(tzinfo=timezone.utc),
                           end=datetime.fromisoformat(end).replace(tzinfo=timezone.utc),
                           feed=DataFeed(cfg.alpaca_data_feed))
    df = c.get_stock_bars(req).df
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")
    return df[["open", "high", "low", "close", "volume"]].tz_convert("America/New_York")


def simulate(df, entry_idx, direction, atr, hold):
    """direction +1 long / -1 short. Symmetric 1-ATR target & stop. Returns +1 win/-1 loss."""
    entry = float(df["close"].iloc[entry_idx])
    target = entry + direction * atr
    stop = entry - direction * atr
    n = len(df)
    for j in range(entry_idx + 1, min(entry_idx + 1 + hold, n)):
        hi, lo = float(df["high"].iloc[j]), float(df["low"].iloc[j])
        if direction == 1:
            if lo <= stop:
                return -1
            if hi >= target:
                return 1
        else:
            if hi >= stop:
                return -1
            if lo <= target:
                return 1
    last = float(df["close"].iloc[min(entry_idx + hold, n - 1)])
    return 1 if direction * (last - entry) > 0 else -1


def main():
    symbol, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    min_z = float(sys.argv[4]) if len(sys.argv) > 4 else 1.5
    hold = int(sys.argv[5]) if len(sys.argv) > 5 else 15
    df = fetch(symbol, start, end)

    fade, momo, require_thrust = [], [], True
    for _, day in df.groupby(df.index.date):
        rth = day.between_time("09:30", "16:00").reset_index(drop=True)
        if len(rth) < 60:
            continue
        for i in range(40, len(rth) - 1):
            snap = compute_snapshot(rth.iloc[: i + 1])
            if snap is None or abs(snap.vwap_dev_z) < min_z:
                continue
            if require_thrust and not snap.is_thrust:
                continue
            dev = snap.vwap_dev_frac
            fade_dir = -1 if dev > 0 else 1          # fade = back toward vwap
            fade.append(simulate(rth, i, fade_dir, snap.atr, hold))
            momo.append(simulate(rth, i, -fade_dir, snap.atr, hold))

    def stats(name, res):
        n = len(res)
        wr = (np.mean([r == 1 for r in res]) * 100) if n else 0
        exp = (np.mean([1 if r == 1 else -1 for r in res])) if n else 0
        print(f"  {name:12s} n={n:4d}  win={wr:5.1f}%  expectancy={exp:+.3f}R")

    print(f"\n{symbol} {start}..{end}  min|z|={min_z} hold={hold}bars feed={load_config().alpaca_data_feed}")
    print(f"Signals (stretched + thrust): {len(fade)}")
    stats("FADE", fade)
    stats("MOMENTUM", momo)


if __name__ == "__main__":
    main()
