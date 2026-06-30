"""Pure indicator math. No I/O, no external services — fully unit-testable.

All functions operate on plain sequences / pandas objects so they can be reused
by both the live engine and the backtester.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


def typical_price(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """HLC3 — the standard price proxy used for VWAP."""
    return (high + low + close) / 3.0


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """Cumulative session VWAP.

    Expects columns: high, low, close, volume. The caller is responsible for
    passing only bars from the current trading session (VWAP resets each day).
    Returns a Series aligned to df.index.
    """
    tp = typical_price(df["high"], df["low"], df["close"])
    pv = tp * df["volume"]
    cum_vol = df["volume"].cumsum()
    # Avoid div-by-zero on a leading zero-volume bar.
    cum_vol = cum_vol.replace(0, np.nan)
    return (pv.cumsum() / cum_vol).bfill()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range — used to size stops and normalize deviation."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=window, min_periods=1).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI. <30 oversold, >70 overbought by convention."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(50.0)


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    """How many standard deviations the latest value sits from its rolling mean."""
    mean = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std(ddof=0)
    std = std.replace(0, np.nan)
    return (series - mean) / std


@dataclass(frozen=True)
class IndicatorSnapshot:
    """The full indicator state at the most recent bar."""

    price: float
    vwap: float
    sma_fast: float
    sma_slow: float
    atr: float
    # Deviation of price from VWAP, expressed both as a fraction and a z-score.
    vwap_dev_frac: float
    vwap_dev_z: float
    # True when the latest bar is a large-range, high-volume "thrust" bar.
    is_thrust: bool
    # True when the latest bar stalled/reversed relative to the prior bar.
    is_reversal_bar: bool


def compute_snapshot(
    df: pd.DataFrame,
    *,
    sma_fast_window: int = 9,
    sma_slow_window: int = 21,
    atr_window: int = 14,
    dev_z_window: int = 30,
    thrust_atr_mult: float = 1.5,
    volume_spike_mult: float = 1.5,
) -> IndicatorSnapshot | None:
    """Compute the indicator snapshot for the last bar in ``df``.

    Returns None if there aren't enough bars to compute the slowest indicator.
    """
    needed = max(sma_slow_window, dev_z_window, atr_window) + 1
    if len(df) < needed:
        return None

    vwap = session_vwap(df)
    a = atr(df, atr_window)
    dev_frac = (df["close"] - vwap) / vwap
    dev_z = rolling_zscore(dev_frac, dev_z_window)
    sf = sma(df["close"], sma_fast_window)
    ss = sma(df["close"], sma_slow_window)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    last_range = last["high"] - last["low"]
    avg_vol = df["volume"].rolling(20, min_periods=5).mean().iloc[-1]

    is_thrust = (
        last_range >= thrust_atr_mult * a.iloc[-1]
        and last["volume"] >= volume_spike_mult * avg_vol
    )
    # A reversal bar closes back inside the prior bar's range after stretching.
    is_reversal_bar = (
        last["close"] < prev["high"] and last["close"] > prev["low"]
    )

    return IndicatorSnapshot(
        price=float(last["close"]),
        vwap=float(vwap.iloc[-1]),
        sma_fast=float(sf.iloc[-1]),
        sma_slow=float(ss.iloc[-1]),
        atr=float(a.iloc[-1]),
        vwap_dev_frac=float(dev_frac.iloc[-1]),
        vwap_dev_z=float(dev_z.iloc[-1]) if not np.isnan(dev_z.iloc[-1]) else 0.0,
        is_thrust=bool(is_thrust),
        is_reversal_bar=bool(is_reversal_bar),
    )
