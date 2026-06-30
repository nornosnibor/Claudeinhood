#!/usr/bin/env python3
"""ORB structural backtest: after a 15-min opening-range break with volume, does
SPY follow through? Measures the UNDERLYING (option premium proven on paper).

Two reads per breakout:
  * FOLLOW-THROUGH (compass): symmetric 0.5*OR-range target/stop -> win% > 50
    means the break continues more than it fails.
  * MEASURED MOVE: target = +1.0*OR-range, stop = back to the broken level ->
    realistic R and expectancy.

    python scripts/orb_backtest.py SPY 2024-09-01 2026-06-28 [or_min] [vol_mult] [end_time]
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


def quarter(d):
    return f"{d.year}Q{(d.month-1)//3+1}"


def main():
    symbol, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    or_min = int(sys.argv[4]) if len(sys.argv) > 4 else 15
    vol_mult = float(sys.argv[5]) if len(sys.argv) > 5 else 1.2
    end_time = sys.argv[6] if len(sys.argv) > 6 else "13:30"
    eh, em = map(int, end_time.split(":"))
    df = fetch_5m(symbol, start, end)
    or_end = (datetime.combine(datetime.today(), time(9, 30)) + timedelta(minutes=or_min)).time()

    compass, measured = [], []   # (result, quarter[, R])
    n_sessions = n_break = 0
    for day_date, day in df.groupby(df.index.date):
        d = day.between_time("09:30", "16:00")
        if len(d) < 20:
            continue
        n_sessions += 1
        orb = d[d.index.time < or_end]
        rest = d[(d.index.time >= or_end) & (d.index.time < time(eh, em))].reset_index(drop=True)
        if orb.empty or len(rest) < 3:
            continue
        or_high, or_low = float(orb["high"].max()), float(orb["low"].min())
        or_range = or_high - or_low
        if or_range <= 0:
            continue
        avg_or_vol = float(orb["volume"].mean())
        q = quarter(day_date)

        # first volume-confirmed close beyond the range
        entry_i = side = None
        for i in range(len(rest)):
            c = float(rest["close"].iloc[i]); v = float(rest["volume"].iloc[i])
            if v < vol_mult * avg_or_vol:
                continue
            if c > or_high:
                entry_i, side, level = i, 1, or_high; break
            if c < or_low:
                entry_i, side, level = i, -1, or_low; break
        if entry_i is None:
            continue
        n_break += 1
        entry = float(rest["close"].iloc[entry_i])

        def walk(target, stop):
            for j in range(entry_i + 1, len(rest)):
                hi, lo = float(rest["high"].iloc[j]), float(rest["low"].iloc[j])
                if side == 1:
                    if lo <= stop: return -1, stop
                    if hi >= target: return 1, target
                else:
                    if hi >= stop: return -1, stop
                    if lo <= target: return 1, target
            last = float(rest["close"].iloc[-1])
            return (1 if side * (last - entry) > 0 else -1), last

        # follow-through compass: symmetric 0.5*range
        d2 = 0.5 * or_range
        r_c, _ = walk(entry + side * d2, entry - side * d2)
        compass.append((r_c, q))
        # measured move: +1.0*range target, stop back at broken level
        r_m, _ = walk(entry + side * or_range, level)
        risk = abs(entry - level) or (0.5 * or_range)
        R = (or_range / risk) if r_m == 1 else -1.0
        measured.append((r_m, q, R))

    def wr(res):
        n = len(res); return (np.mean([x[0] == 1 for x in res]) * 100 if n else 0.0), n

    feed = load_config().alpaca_data_feed
    print(f"\n{symbol} ORB  {start}..{end}  OR={or_min}min  vol>={vol_mult}x  window->{end_time}  feed={feed}")
    print(f"sessions={n_sessions}  breakouts={n_break}  ({100*n_break/max(n_sessions,1):.0f}% of days)")
    wc, nc = wr(compass)
    wm, nm = wr(measured)
    exp_R = np.mean([R for _, _, R in measured]) if measured else 0.0
    print(f"\n  FOLLOW-THROUGH (compass 0.5R)  win={wc:5.1f}%  n={nc}")
    print(f"  MEASURED MOVE (+1R/stop@level) win={wm:5.1f}%  n={nm}  avg={exp_R:+.2f}R/trade")
    print("\nFollow-through per quarter:")
    for q in sorted(set(x[1] for x in compass)):
        w, n = wr([x for x in compass if x[1] == q])
        print(f"  {q}: win={w:5.1f}%  n={n}")


if __name__ == "__main__":
    main()
