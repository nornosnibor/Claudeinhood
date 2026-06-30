#!/usr/bin/env python3
"""Does a regime-switch rule beat a static one across MANY regimes?

Regime (per day, from prior days only): Kaufman Efficiency Ratio on the last N
daily closes. High ER = trending, low ER = ranging.

At a 5-min RSI extreme (VWAP-aligned) inside the window, pick direction by regime:
  trend regime -> momentum (ride);  range regime -> fade (revert).
Compared against always-momentum and always-fade baselines. Symmetric 1-ATR
barriers, so win% > 50 = edge. Reports per-quarter to expose instability.

    python scripts/regime_switch.py SPY 2024-09-01 2026-06-28 [er_thr] [er_days]
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


def quarter(day_date):
    return f"{day_date.year}Q{(day_date.month-1)//3+1}"


def main():
    symbol, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    er_thr = float(sys.argv[4]) if len(sys.argv) > 4 else 0.35
    er_days = int(sys.argv[5]) if len(sys.argv) > 5 else 10
    rsi_low, rsi_high, hold = 25, 75, 6
    df = fetch_5m(symbol, start, end)

    # Daily regime from daily closes (prior-day info only).
    daily_close = df["close"].groupby(df.index.date).last()
    er_daily = efficiency_ratio(daily_close, er_days)
    regime = {}  # date -> 'trend'/'range'
    dates = list(daily_close.index)
    for k in range(1, len(dates)):
        e = er_daily.iloc[k - 1]
        if np.isnan(e):
            continue
        regime[dates[k]] = "trend" if e >= er_thr else "range"

    sw, mo, fa = [], [], []  # (result, quarter) for switch/momentum/fade
    for day_date, day in df.groupby(df.index.date):
        rth = day.between_time("09:30", "13:30").reset_index(drop=True)
        if len(rth) < 20 or day_date not in regime:
            continue
        reg = regime[day_date]; q = quarter(day_date)
        vwap = session_vwap(rth); r = rsi(rth["close"], 14); a = atr(rth, 14)
        for i in range(14, len(rth) - 1):
            price = float(rth["close"].iloc[i]); av = float(a.iloc[i])
            if av <= 0:
                continue
            if r.iloc[i] <= rsi_low and price < vwap.iloc[i]:
                momentum_dir = -1
            elif r.iloc[i] >= rsi_high and price > vwap.iloc[i]:
                momentum_dir = 1
            else:
                continue
            fade_dir = -momentum_dir
            mo.append((compass(rth, i, momentum_dir, av, hold), q))
            fa.append((compass(rth, i, fade_dir, av, hold), q))
            switch_dir = momentum_dir if reg == "trend" else fade_dir
            sw.append((compass(rth, i, switch_dir, av, hold), q))

    def wr(res):
        n = len(res); return (np.mean([x == 1 for x, _ in res]) * 100 if n else 0.0), n

    feed = load_config().alpaca_data_feed
    print(f"\n{symbol} regime-switch test  {start}..{end}  ER>= {er_thr} over {er_days}d  feed={feed}")
    for name, res in [("SWITCH", sw), ("always MOMENTUM", mo), ("always FADE", fa)]:
        w, n = wr(res); print(f"  {name:16s} win={w:5.1f}%  n={n}")
    print("\nSWITCH per quarter:")
    for q in sorted(set(qq for _, qq in sw)):
        w, n = wr([(x, qq) for x, qq in sw if qq == q])
        print(f"  {q}: win={w:5.1f}%  n={n}")


if __name__ == "__main__":
    main()
