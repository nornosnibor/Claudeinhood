#!/usr/bin/env python3
"""Robustness check for the 5-min momentum finding: when SPY hits an RSI extreme
on the VWAP-aligned side, does trading WITH the move hold an edge across
thresholds, hold times, and sub-periods? Symmetric 1-ATR barriers -> win% > 50
means directional edge.

    python scripts/momentum_robust.py SPY 2026-03-01 2026-06-28
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
from claudeinhood.data.indicators import atr, rsi, session_vwap


def fetch_5m(symbol, start, end):
    cfg = load_config()
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    c = StockHistoricalDataClient(cfg.alpaca_api_key, cfg.alpaca_secret_key)
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                           start=datetime.fromisoformat(start).replace(tzinfo=timezone.utc),
                           end=datetime.fromisoformat(end).replace(tzinfo=timezone.utc),
                           feed=DataFeed(cfg.alpaca_data_feed))
    df = c.get_stock_bars(req).df
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")
    return df[["open", "high", "low", "close", "volume"]].tz_convert("America/New_York")


def momentum_win(df, i, d, atrv, hold):
    """d = momentum direction (with the move). Symmetric 1-ATR. Returns +1/-1, month."""
    entry = float(df["close"].iloc[i])
    target, stop = entry + d * atrv, entry - d * atrv
    n = len(df)
    for j in range(i + 1, min(i + 1 + hold, n)):
        hi, lo = float(df["high"].iloc[j]), float(df["low"].iloc[j])
        if d == 1:
            if lo <= stop: return -1
            if hi >= target: return 1
        else:
            if hi >= stop: return -1
            if lo <= target: return 1
    last = float(df["close"].iloc[min(i + hold, n - 1)])
    return 1 if d * (last - entry) > 0 else -1


def collect(df, rsi_low, rsi_high, hold):
    """Return list of (result, month) for momentum trades."""
    out = []
    for day_date, day in df.groupby(df.index.date):
        rth = day.between_time("09:30", "16:00").reset_index(drop=True)
        if len(rth) < 20:
            continue
        vwap = session_vwap(rth); r = rsi(rth["close"], 14); a = atr(rth, 14)
        month = f"{day_date.year}-{day_date.month:02d}"
        for i in range(14, len(rth) - 1):
            price = float(rth["close"].iloc[i]); av = float(a.iloc[i])
            if av <= 0:
                continue
            if r.iloc[i] <= rsi_low and price < vwap.iloc[i]:
                d = -1  # oversold + below vwap -> momentum is DOWN
            elif r.iloc[i] >= rsi_high and price > vwap.iloc[i]:
                d = 1   # overbought + above vwap -> momentum is UP
            else:
                continue
            out.append((momentum_win(rth, i, d, av, hold), month))
    return out


def wr(results):
    n = len(results)
    return (np.mean([x == 1 for x in results]) * 100 if n else 0.0), n


def main():
    symbol, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    df = fetch_5m(symbol, start, end)
    feed = load_config().alpaca_data_feed
    print(f"\n{symbol} 5-min momentum robustness  {start}..{end}  feed={feed}\n")

    print("Grid (momentum win% across thresholds x hold):")
    print(f"  {'rsi':>9} {'hold':>5} {'win%':>6} {'n':>5}")
    for lo, hi in [(20, 80), (25, 75), (30, 70)]:
        for hold in [3, 6, 9]:
            res = [r for r, _ in collect(df, lo, hi, hold)]
            w, n = wr(res)
            print(f"  {lo:>3}/{hi:<3} {hold:>5} {w:6.1f} {n:>5}")

    print("\nPer-month stability (rsi 25/75, hold 6):")
    base = collect(df, 25, 75, 6)
    months = sorted(set(m for _, m in base))
    for m in months:
        res = [r for r, mm in base if mm == m]
        w, n = wr(res)
        print(f"  {m}: win={w:5.1f}%  n={n}")


if __name__ == "__main__":
    main()
