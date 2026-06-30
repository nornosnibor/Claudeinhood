import numpy as np
import pandas as pd

from claudeinhood.strategy.base import Side
from claudeinhood.strategy.vwap_reversion import (
    VwapReversionParams,
    VwapReversionStrategy,
)


def _bars(rows):
    """rows: list of (open, high, low, close, volume)."""
    idx = pd.date_range("2026-06-30 09:30", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)


def test_flat_when_warming_up():
    rows = [(100, 100.1, 99.9, 100, 1000)] * 5
    sig = VwapReversionStrategy().evaluate(_bars(rows))
    assert sig.side is Side.FLAT


def test_no_signal_when_price_at_vwap():
    rows = [(100, 100.1, 99.9, 100, 1000) for _ in range(60)]
    sig = VwapReversionStrategy().evaluate(_bars(rows))
    assert sig.side is Side.FLAT


def test_long_signal_on_stretched_oversold_with_exhaustion():
    # Flat tape to build VWAP ~100, then a sharp drop (thrust) that closes back
    # inside the prior bar (reversal) -> expect a LONG fade.
    rows = [(100, 100.05, 99.95, 100, 1000) for _ in range(58)]
    # big down thrust bar, high volume, large range:
    rows.append((100, 100.0, 99.0, 99.2, 5000))
    # reversal bar: closes back up inside prior bar's range, still high vol/range
    rows.append((99.2, 99.9, 99.1, 99.6, 6000))
    params = VwapReversionParams(min_dev_z=1.0, trend_filter=False)
    sig = VwapReversionStrategy(params).evaluate(_bars(rows))
    assert sig.side is Side.LONG
    assert sig.target > sig.entry_ref      # target back up toward vwap
    assert sig.stop < sig.entry_ref        # stop below entry


def test_exhaustion_required_blocks_entry():
    # Stretched but no thrust/reversal confirmation -> flat when required.
    rows = [(100, 100.05, 99.95, 100, 1000) for _ in range(59)]
    rows.append((100, 100.0, 99.95, 99.5, 1000))  # drift down, no thrust
    params = VwapReversionParams(min_dev_z=0.5, require_exhaustion=True,
                                 trend_filter=False)
    sig = VwapReversionStrategy(params).evaluate(_bars(rows))
    assert sig.side is Side.FLAT
