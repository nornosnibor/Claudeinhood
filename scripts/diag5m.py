#!/usr/bin/env python3
"""5-minute reversion diagnostic: does fading an RSI extreme (with VWAP as the
magnet) actually predict direction on SPY?

Trigger (per the refined thesis):
  oversold  : RSI <= low  AND price below VWAP  -> fade LONG  (revert up to VWAP)
  overbought: RSI >= high AND price above VWAP  -> fade SHORT (revert down to VWAP)

Two reads per signal:
  * COMPASS  : symmetric 1-ATR target/stop -> win% is a clean directional edge test
  * REVERT   : realistic target=VWAP, stop=k*ATR -> expectancy in R

    python scripts/diag5m.py SPY 2026-03-01 2026-06-28 [rsi_low] [rsi_high] [hold]
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


def walk(df, i, direction, target, stop, hold):
    n = len(df)
    for j in range(i + 1, min(i + 1 + hold, n)):
        hi, lo = float(df["high"].iloc[j]), float(df["low"].iloc[j])
        if direction == 1:
            if lo <= stop:
                return -1, (stop / float(df["close"].iloc[i]) - 1)
            if hi >= target:
                return 1, (target / float(df["close"].iloc[i]) - 1)
        else:
            if hi >= stop:
                return -1, (1 - stop / float(df["close"].iloc[i]))
            if lo <= target:
                return 1, (1 - target / float(df["close"].iloc[i]))
    last = float(df["close"].iloc[min(i + hold, n - 1)])
    entry = float(df["close"].iloc[i])
    r = (last - entry) / entry * direction
    return (1 if r > 0 else -1), r


def main():
    symbol, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    rsi_low = float(sys.argv[4]) if len(sys.argv) > 4 else 25
    rsi_high = float(sys.argv[5]) if len(sys.argv) > 5 else 75
    hold = int(sys.argv[6]) if len(sys.argv) > 6 else 6
    stop_atr = 1.5
    df = fetch_5m(symbol, start, end)

    comp_fade, comp_momo, revert_r = [], [], []
    sessions = 0
    for _, day in df.groupby(df.index.date):
        rth = day.between_time("09:30", "16:00").reset_index(drop=True)
        if len(rth) < 20:
            continue
        sessions += 1
        vwap = session_vwap(rth)
        r = rsi(rth["close"], 14)
        a = atr(rth, 14)
        for i in range(14, len(rth) - 1):
            price = float(rth["close"].iloc[i])
            if r.iloc[i] <= rsi_low and price < vwap.iloc[i]:
                d = 1
            elif r.iloc[i] >= rsi_high and price > vwap.iloc[i]:
                d = -1
            else:
                continue
            av = float(a.iloc[i])
            if av <= 0:
                continue
            # compass (symmetric)
            comp_fade.append(walk(rth, i, d, price + d * av, price - d * av, hold)[0])
            comp_momo.append(walk(rth, i, -d, price - d * av, price + d * av, hold)[0])
            # realistic reversion: target = vwap, stop = k*ATR against
            tgt = float(vwap.iloc[i])
            stp = price - d * stop_atr * av
            revert_r.append(walk(rth, i, d, tgt, stp, hold)[1])

    def stats(name, res, as_r=False):
        n = len(res)
        if not n:
            print(f"  {name:16s} n=0"); return
        if as_r:
            wins = np.mean([x > 0 for x in res]) * 100
            print(f"  {name:16s} n={n:4d}  win={wins:5.1f}%  avg={np.mean(res)*100:+.3f}%  sum={np.sum(res)*100:+.2f}%")
        else:
            wr = np.mean([x == 1 for x in res]) * 100
            print(f"  {name:16s} n={n:4d}  win={wr:5.1f}%")

    print(f"\n{symbol} 5-min  {start}..{end}  {sessions} sessions  RSI<= {rsi_low}/>= {rsi_high}  hold={hold}bars(={hold*5}min)  feed={load_config().alpaca_data_feed}")
    print(f"Signals: {len(comp_fade)}")
    stats("COMPASS fade", comp_fade)
    stats("COMPASS momentum", comp_momo)
    stats("REVERT->vwap", revert_r, as_r=True)


if __name__ == "__main__":
    main()
