#!/usr/bin/env python3
"""Does a trend/chop regime filter rescue the 5-min momentum edge?

Same momentum trigger (RSI extreme on the VWAP-aligned side, traded WITH the
move), but only when the Kaufman Efficiency Ratio over the last N bars is high
enough (trending). Sweeps the ER threshold and shows per-month stability so we
can see whether "sit out the chop" actually removes the losing months.

    python scripts/momentum_regime.py SPY 2026-03-01 2026-06-28 [rsi_low] [rsi_high] [hold] [er_window]
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
from claudeinhood.data.indicators import atr, efficiency_ratio, rsi, session_vwap


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


def mom_win(df, i, d, av, hold):
    entry = float(df["close"].iloc[i]); target, stop = entry + d * av, entry - d * av
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


def collect(df, rsi_low, rsi_high, hold, er_window):
    """Return [(result, month, er)] for every momentum signal (unfiltered)."""
    out = []
    for day_date, day in df.groupby(df.index.date):
        rth = day.between_time("09:30", "16:00").reset_index(drop=True)
        if len(rth) < 20:
            continue
        vwap = session_vwap(rth); r = rsi(rth["close"], 14); a = atr(rth, 14)
        er = efficiency_ratio(rth["close"], er_window)
        month = f"{day_date.year}-{day_date.month:02d}"
        for i in range(max(14, er_window), len(rth) - 1):
            price = float(rth["close"].iloc[i]); av = float(a.iloc[i])
            if av <= 0:
                continue
            if r.iloc[i] <= rsi_low and price < vwap.iloc[i]:
                d = -1
            elif r.iloc[i] >= rsi_high and price > vwap.iloc[i]:
                d = 1
            else:
                continue
            out.append((mom_win(rth, i, d, av, hold), month, float(er.iloc[i])))
    return out


def wr(res):
    n = len(res)
    return (np.mean([x == 1 for x in res]) * 100 if n else 0.0), n


def main():
    symbol, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    rsi_low = float(sys.argv[4]) if len(sys.argv) > 4 else 25
    rsi_high = float(sys.argv[5]) if len(sys.argv) > 5 else 75
    hold = int(sys.argv[6]) if len(sys.argv) > 6 else 6
    er_window = int(sys.argv[7]) if len(sys.argv) > 7 else 10
    df = fetch_5m(symbol, start, end)
    data = collect(df, rsi_low, rsi_high, hold, er_window)

    print(f"\n{symbol} 5-min momentum + regime filter  {start}..{end}  feed={load_config().alpaca_data_feed}")
    print(f"RSI {rsi_low}/{rsi_high}  hold={hold}  ER window={er_window}\n")
    print(f"  {'ER>=':>5} {'win%':>6} {'n':>5} {'kept%':>6}")
    total = len(data)
    for thr in [0.0, 0.3, 0.4, 0.5, 0.6, 0.7]:
        res = [r for r, _, e in data if e >= thr]
        w, n = wr(res)
        print(f"  {thr:>5.2f} {w:6.1f} {n:>5} {100*n/total:6.0f}")

    # per-month at a promising threshold
    thr = 0.5
    print(f"\nPer-month with ER>={thr}:")
    for m in sorted(set(mm for _, mm, _ in data)):
        res = [r for r, mm, e in data if mm == m and e >= thr]
        w, n = wr(res)
        print(f"  {m}: win={w:5.1f}%  n={n}")


if __name__ == "__main__":
    main()
