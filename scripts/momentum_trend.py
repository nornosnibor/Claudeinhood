#!/usr/bin/env python3
"""Does aligning 5-min momentum with the higher-timeframe (daily) trend rescue
the edge — specifically, does it fix the losing months?

Regime = sign of prior-day close vs its N-day SMA (computed only from data
available before the session, so no lookahead). Take a momentum continuation
only when its direction matches the daily trend; otherwise sit out.

    python scripts/momentum_trend.py SPY 2026-03-01 2026-06-28 [rsi_low] [rsi_high] [hold] [daily_sma]
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


def _client():
    cfg = load_config()
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(cfg.alpaca_api_key, cfg.alpaca_secret_key), cfg


def fetch(symbol, start, end, tf):
    client, cfg = _client()
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf,
                           start=datetime.fromisoformat(start).replace(tzinfo=timezone.utc),
                           end=datetime.fromisoformat(end).replace(tzinfo=timezone.utc),
                           feed=DataFeed(cfg.alpaca_data_feed))
    df = client.get_stock_bars(req).df
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")
    return df[["open", "high", "low", "close", "volume"]]


def daily_bias(symbol, start, end, sma_n):
    """Map session date -> +1/-1 daily-trend bias using only prior-day info."""
    from alpaca.data.timeframe import TimeFrame
    # pull extra history before `start` so the SMA is warm on day one
    pad_start = (datetime.fromisoformat(start) - pd.Timedelta(days=2 * sma_n + 10)).date().isoformat()
    d = fetch(symbol, pad_start, end, TimeFrame.Day)
    d = d.tz_convert("America/New_York")
    sma = d["close"].rolling(sma_n).mean()
    bias = {}
    dates = list(d.index)
    for k in range(1, len(dates)):
        prev = dates[k - 1]
        if pd.isna(sma.iloc[k - 1]):
            continue
        bias[dates[k].date()] = 1 if d["close"].iloc[k - 1] > sma.iloc[k - 1] else -1
    return bias


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


def main():
    symbol, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    rsi_low = float(sys.argv[4]) if len(sys.argv) > 4 else 25
    rsi_high = float(sys.argv[5]) if len(sys.argv) > 5 else 75
    hold = int(sys.argv[6]) if len(sys.argv) > 6 else 6
    sma_n = int(sys.argv[7]) if len(sys.argv) > 7 else 10
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    bias = daily_bias(symbol, start, end, sma_n)
    df = fetch(symbol, start, end, TimeFrame(5, TimeFrameUnit.Minute)).tz_convert("America/New_York")

    rows = []  # (result, month, aligned_bool)
    for day_date, day in df.groupby(df.index.date):
        rth = day.between_time("09:30", "16:00").reset_index(drop=True)
        if len(rth) < 20 or day_date not in bias:
            continue
        b = bias[day_date]
        vwap = session_vwap(rth); r = rsi(rth["close"], 14); a = atr(rth, 14)
        month = f"{day_date.year}-{day_date.month:02d}"
        for i in range(14, len(rth) - 1):
            price = float(rth["close"].iloc[i]); av = float(a.iloc[i])
            if av <= 0:
                continue
            if r.iloc[i] <= rsi_low and price < vwap.iloc[i]:
                d = -1
            elif r.iloc[i] >= rsi_high and price > vwap.iloc[i]:
                d = 1
            else:
                continue
            rows.append((mom_win(rth, i, d, av, hold), month, d == b))

    def wr(res):
        n = len(res); return (np.mean([x == 1 for x in res]) * 100 if n else 0.0), n

    print(f"\n{symbol} 5-min momentum + DAILY-trend alignment  {start}..{end}  feed={load_config().alpaca_data_feed}")
    print(f"RSI {rsi_low}/{rsi_high}  hold={hold}  daily SMA={sma_n}\n")
    w_all, n_all = wr([r for r, _, _ in rows])
    w_al, n_al = wr([r for r, _, al in rows if al])
    w_ct, n_ct = wr([r for r, _, al in rows if not al])
    print(f"  all signals           win={w_all:5.1f}%  n={n_all}")
    print(f"  ALIGNED w/ daily trend win={w_al:5.1f}%  n={n_al}")
    print(f"  counter-trend         win={w_ct:5.1f}%  n={n_ct}")
    print("\nPer-month, ALIGNED only:")
    for m in sorted(set(mm for _, mm, _ in rows)):
        w, n = wr([r for r, mm, al in rows if mm == m and al])
        print(f"  {m}: win={w:5.1f}%  n={n}")


if __name__ == "__main__":
    main()
