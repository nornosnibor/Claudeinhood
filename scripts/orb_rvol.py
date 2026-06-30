#!/usr/bin/env python3
"""Is ORB's edge concentrated on CATALYST days? Stratify opening-range breakouts
by relative volume and overnight gap, pooled across liquid names, and see if the
high-RVOL / big-gap buckets follow through better than the ~50% average.

If they do, the strategy is: ORB only on catalyst days (the 'one filter'), with
ProBors selecting which names have a catalyst.

    python scripts/orb_rvol.py 2024-09-01 2026-06-28
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import numpy as np
import pandas as pd

from claudeinhood.config import load_config

SYMBOLS = ["TSLA", "NVDA", "AMD", "PLTR", "COIN", "AAPL", "META", "AMZN", "GOOGL", "MSFT"]


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


def collect_symbol(sym, start, end, or_min=15, vol_mult=1.2, end_time=time(13, 30)):
    df = fetch_5m(sym, start, end)
    or_end = (datetime.combine(datetime.today(), time(9, 30)) + timedelta(minutes=or_min)).time()
    rows = []
    prev_close = None
    or_vol_hist = []
    for day_date, day in df.groupby(df.index.date):
        d = day.between_time("09:30", "16:00")
        if len(d) < 20:
            prev_close = None
            continue
        orb = d[d.index.time < or_end]
        rest = d[(d.index.time >= or_end) & (d.index.time < end_time)].reset_index(drop=True)
        if orb.empty or len(rest) < 3:
            prev_close = float(d["close"].iloc[-1]); continue
        or_high, or_low = float(orb["high"].max()), float(orb["low"].min())
        or_range = or_high - or_low
        or_vol = float(orb["volume"].sum())
        today_open = float(d["open"].iloc[0])
        gap = abs(today_open / prev_close - 1) if prev_close else 0.0
        rvol = (or_vol / np.median(or_vol_hist)) if len(or_vol_hist) >= 10 else np.nan
        # update history AFTER computing rvol (no lookahead)
        or_vol_hist.append(or_vol)
        if len(or_vol_hist) > 20:
            or_vol_hist.pop(0)
        prev_close = float(d["close"].iloc[-1])
        if or_range <= 0 or np.isnan(rvol):
            continue
        avg_or_vol_bar = float(orb["volume"].mean())

        entry_i = side = None
        for i in range(len(rest)):
            c = float(rest["close"].iloc[i]); v = float(rest["volume"].iloc[i])
            if v < vol_mult * avg_or_vol_bar:
                continue
            if c > or_high:
                entry_i, side, level = i, 1, or_high; break
            if c < or_low:
                entry_i, side, level = i, -1, or_low; break
        if entry_i is None:
            continue
        entry = float(rest["close"].iloc[entry_i])

        def walk(target, stop):
            for j in range(entry_i + 1, len(rest)):
                hi, lo = float(rest["high"].iloc[j]), float(rest["low"].iloc[j])
                if side == 1:
                    if lo <= stop: return -1
                    if hi >= target: return 1
                else:
                    if hi >= stop: return -1
                    if lo <= target: return 1
            last = float(rest["close"].iloc[-1])
            return 1 if side * (last - entry) > 0 else -1

        ft = walk(entry + side * 0.5 * or_range, entry - side * 0.5 * or_range)
        mm = walk(entry + side * or_range, level)
        risk = abs(entry - level) or 0.5 * or_range
        R = (or_range / risk) if mm == 1 else -1.0
        rows.append((rvol, gap, ft, R))
    return rows


def bucketize(rows, key_idx, edges, labels):
    print(f"\n  {'bucket':>12} {'n':>5} {'FT win%':>8} {'avgR':>7}")
    for lo, hi, lab in zip(edges[:-1], edges[1:], labels):
        sub = [r for r in rows if lo <= r[key_idx] < hi]
        n = len(sub)
        if not n:
            print(f"  {lab:>12} {n:>5}"); continue
        ft = np.mean([1 if r[2] == 1 else 0 for r in sub]) * 100
        avgR = np.mean([r[3] for r in sub])
        print(f"  {lab:>12} {n:>5} {ft:8.1f} {avgR:+7.2f}")


def main():
    start, end = sys.argv[1], sys.argv[2]
    all_rows = []
    for s in SYMBOLS:
        try:
            r = collect_symbol(s, start, end)
            all_rows += r
            print(f"[{s}] {len(r)} breakouts")
        except Exception as e:
            print(f"[{s}] error: {e}")
    print(f"\nPooled breakouts: {len(all_rows)}  ({len(SYMBOLS)} names, {start}..{end})")

    print("\nBy RELATIVE VOLUME (OR vol vs 20-day median):")
    bucketize(all_rows, 0, [0, 1.0, 1.5, 2.5, 1e9], ["<1.0x", "1.0-1.5x", "1.5-2.5x", ">2.5x"])
    print("\nBy OVERNIGHT GAP (abs %):")
    bucketize(all_rows, 1, [0, 0.01, 0.02, 0.04, 1e9], ["<1%", "1-2%", "2-4%", ">4%"])


if __name__ == "__main__":
    main()
