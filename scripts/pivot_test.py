#!/usr/bin/env python3
"""Do pivot levels + a morning time window have an intraday edge on SPY?

When price interacts with a floor-trader pivot (P/R1-3/S1-3) inside the trading
window, we classify the approach and test both plays with symmetric 1-ATR
barriers (win% > 50 = edge):
  * BOUNCE : fade off the level (support touched from above -> long; resistance
             touched from below -> short)
  * BREAK  : continue through the level (opposite of bounce)

Window default 09:30-13:30 ET. Pivots come from the prior session's RTH H/L/C.

    python scripts/pivot_test.py SPY 2026-03-01 2026-06-28 [touch_atr] [hold] [start] [end]
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
from claudeinhood.data.indicators import atr
from claudeinhood.data.pivots import compute_pivots


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


def compass(df, i, d, av, hold):
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


def main():
    symbol, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    touch_atr = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
    hold = int(sys.argv[5]) if len(sys.argv) > 5 else 6
    win_start = sys.argv[6] if len(sys.argv) > 6 else "09:30"
    win_end = sys.argv[7] if len(sys.argv) > 7 else "13:30"
    df = fetch_5m(symbol, start, end)

    sessions = sorted(set(df.index.date))
    prev_hlc = None
    bounce, brk = [], []  # (result, month)
    n_sessions = 0
    for day_date in sessions:
        day = df[df.index.date == day_date]
        rth_full = day.between_time("09:30", "16:00")
        if len(rth_full) < 20:
            prev_hlc = None
            continue
        if prev_hlc is not None:
            piv = compute_pivots(*prev_hlc)
            levels = list(piv.levels().values())
            win = day.between_time(win_start, win_end).reset_index(drop=True)
            # ATR computed on the full session for stable scale, aligned to window
            a_full = atr(rth_full, 14)
            a = a_full.reindex(rth_full.index)
            # map window bars to atr by position in rth_full
            rth_reset = rth_full.reset_index()
            ts_to_atr = dict(zip(range(len(rth_full)), a.values))
            month = f"{day_date.year}-{day_date.month:02d}"
            n_sessions += 1
            for i in range(3, len(win) - 1):
                price = float(win["close"].iloc[i])
                # find atr for this bar (match by timestamp position)
                # recompute simple atr proxy from window if needed
                av = float(np.nanmean([abs(win["high"].iloc[k] - win["low"].iloc[k])
                                       for k in range(max(0, i - 14), i + 1)]))
                if av <= 0:
                    continue
                # nearest level within touch band
                near = min(levels, key=lambda L: abs(price - L))
                if abs(price - near) > touch_atr * av:
                    continue
                came_from_above = float(win["close"].iloc[i - 3]) > near
                bounce_dir = 1 if came_from_above else -1  # support bounce up / resistance reject down
                bounce.append((compass(win, i, bounce_dir, av, hold), month))
                brk.append((compass(win, i, -bounce_dir, av, hold), month))
        prev_hlc = (float(rth_full["high"].max()), float(rth_full["low"].min()),
                    float(rth_full["close"].iloc[-1]))

    def wr(res):
        n = len(res); return (np.mean([r == 1 for r, _ in res]) * 100 if n else 0.0), n

    feed = load_config().alpaca_data_feed
    print(f"\n{symbol} 5-min PIVOT interaction  {start}..{end}  window {win_start}-{win_end}  feed={feed}")
    print(f"touch={touch_atr}ATR  hold={hold}  sessions={n_sessions}")
    wb, nb = wr(bounce); wk, nk = wr(brk)
    print(f"\n  BOUNCE off level   win={wb:5.1f}%  n={nb}")
    print(f"  BREAK through level win={wk:5.1f}%  n={nk}")
    print("\nPer-month (BOUNCE):")
    for m in sorted(set(mm for _, mm in bounce)):
        w, n = wr([(r, mm) for r, mm in bounce if mm == m])
        print(f"  {m}: win={w:5.1f}%  n={n}")
    print("Per-month (BREAK):")
    for m in sorted(set(mm for _, mm in brk)):
        w, n = wr([(r, mm) for r, mm in brk if mm == m])
        print(f"  {m}: win={w:5.1f}%  n={n}")


if __name__ == "__main__":
    main()
