"""VWAP overreaction / mean-reversion strategy.

Thesis: intraday, price periodically over-extends away from session VWAP on a
burst of emotional flow (a "thrust"). When that thrust stalls (a reversal bar)
without fresh information driving it, price tends to snap back toward VWAP. We
fade the stretch and target the reversion.

This is deliberately conservative: we require BOTH a statistically stretched
deviation AND evidence of exhaustion before entering, to avoid catching a knife
in a genuine trend day. Trend context (fast vs slow SMA) further filters trades.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..data.indicators import compute_snapshot
from .base import Side, Signal, Strategy


@dataclass(frozen=True)
class VwapReversionParams:
    # Minimum |z-score| of VWAP deviation to consider a move "stretched".
    min_dev_z: float = 2.0
    # Require the exhaustion (thrust + reversal bar) confirmation.
    require_exhaustion: bool = True
    # Don't fade in the direction the broader trend strongly favors:
    # skip shorts when fast SMA is well above slow SMA, and vice versa.
    trend_filter: bool = True
    trend_sma_gap_atr: float = 0.75
    # Reversion target as a fraction of the distance back to VWAP (1.0 = full).
    target_vwap_fraction: float = 0.8
    # Stop placed beyond the extreme by this many ATRs.
    stop_atr_mult: float = 1.0
    sma_fast_window: int = 9
    sma_slow_window: int = 21
    dev_z_window: int = 30


class VwapReversionStrategy(Strategy):
    name = "vwap_reversion"

    def __init__(self, params: VwapReversionParams | None = None):
        self.p = params or VwapReversionParams()

    def evaluate(self, df: pd.DataFrame) -> Signal:
        flat = Signal(Side.FLAT, 0.0, 0.0, 0.0, 0.0, "no setup")

        snap = compute_snapshot(
            df,
            sma_fast_window=self.p.sma_fast_window,
            sma_slow_window=self.p.sma_slow_window,
            dev_z_window=self.p.dev_z_window,
        )
        if snap is None:
            return Signal(Side.FLAT, 0.0, 0.0, 0.0, 0.0, "warming up")

        z = snap.vwap_dev_z
        if abs(z) < self.p.min_dev_z:
            return flat

        # Stretched BELOW vwap -> fade upward (LONG). Stretched ABOVE -> SHORT.
        side = Side.LONG if z < 0 else Side.SHORT

        if self.p.require_exhaustion and not (snap.is_thrust and snap.is_reversal_bar):
            return Signal(Side.FLAT, 0.0, 0.0, 0.0, 0.0,
                          f"stretched (z={z:.2f}) but no exhaustion confirm")

        if self.p.trend_filter:
            sma_gap = snap.sma_fast - snap.sma_slow
            strong_up = sma_gap > self.p.trend_sma_gap_atr * snap.atr
            strong_down = -sma_gap > self.p.trend_sma_gap_atr * snap.atr
            # Don't short into a strong uptrend or long into a strong downtrend.
            if side is Side.SHORT and strong_up:
                return Signal(Side.FLAT, 0.0, 0.0, 0.0, 0.0,
                              "skip short: strong uptrend")
            if side is Side.LONG and strong_down:
                return Signal(Side.FLAT, 0.0, 0.0, 0.0, 0.0,
                              "skip long: strong downtrend")

        entry = snap.price
        # Target is a fraction of the way back to VWAP.
        target = entry + self.p.target_vwap_fraction * (snap.vwap - entry)
        if side is Side.LONG:
            stop = entry - self.p.stop_atr_mult * snap.atr
        else:
            stop = entry + self.p.stop_atr_mult * snap.atr

        # Confidence scales with how stretched we are, capped at 1.
        confidence = min(1.0, (abs(z) - self.p.min_dev_z) / 2.0 + 0.5)

        return Signal(
            side=side,
            confidence=confidence,
            entry_ref=entry,
            target=target,
            stop=stop,
            reason=f"fade z={z:.2f} dev={snap.vwap_dev_frac*100:.2f}% -> vwap",
        )
