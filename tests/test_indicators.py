import numpy as np
import pandas as pd

from claudeinhood.data.indicators import (
    atr,
    compute_snapshot,
    rolling_zscore,
    session_vwap,
    sma,
)


def _bars(closes, vols=None, spread=0.1):
    n = len(closes)
    vols = vols if vols is not None else [1000] * n
    idx = pd.date_range("2026-06-30 09:30", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + spread for c in closes],
            "low": [c - spread for c in closes],
            "close": closes,
            "volume": vols,
        },
        index=idx,
    )


def test_session_vwap_constant_price():
    df = _bars([100.0] * 10)
    vw = session_vwap(df)
    assert np.allclose(vw.values, 100.0)


def test_session_vwap_volume_weighting():
    # Price 100 with tiny volume, then 200 with huge volume -> vwap near 200.
    df = _bars([100.0, 200.0], vols=[1, 1_000_000], spread=0.0)
    vw = session_vwap(df)
    assert vw.iloc[-1] > 199.0


def test_sma_basic():
    df = _bars(list(range(1, 11)))
    s = sma(df["close"], 3)
    assert s.iloc[-1] == (8 + 9 + 10) / 3


def test_atr_positive():
    df = _bars([100, 101, 99, 102, 98, 103])
    a = atr(df, 3)
    assert (a.dropna() > 0).all()


def test_rolling_zscore_extreme():
    vals = pd.Series([0.0] * 20 + [5.0])
    z = rolling_zscore(vals, 20)
    # The last value is far above the rolling mean of zeros.
    assert z.iloc[-1] > 3


def test_compute_snapshot_warmup_returns_none():
    df = _bars([100.0] * 5)
    assert compute_snapshot(df) is None


def test_compute_snapshot_fields():
    closes = [100 + np.sin(i / 3) for i in range(60)]
    df = _bars(closes)
    snap = compute_snapshot(df)
    assert snap is not None
    assert snap.vwap > 0
    assert isinstance(snap.is_thrust, bool)
