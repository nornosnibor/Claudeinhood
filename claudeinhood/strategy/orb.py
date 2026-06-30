"""Opening Range Breakout — structural, not predictive.

Signal: define the opening range (first `or_minutes` of the session); when a bar
CLOSES beyond the range with volume confirmation, trade the break in that
direction. One filter (volume), nothing else. The exit rules (10-30% target /
22% stop, never to expiry) are premium-based and enforced by the engine, not
here — this class only decides entry + reference levels.

Operates on a tz-aware (ET) datetime-indexed session DataFrame.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd

from .base import Side, Signal, Strategy


@dataclass(frozen=True)
class ORBParams:
    or_minutes: int = 15
    # Breakout bar volume must exceed this multiple of the average bar volume
    # from the open up to the breakout (the one filter).
    volume_mult: float = 1.2
    session_open: time = time(9, 30)
    # No new entries after this (engine also enforces the hard window).
    no_entry_after: time = time(13, 30)


class ORBStrategy(Strategy):
    name = "orb"

    def __init__(self, params: ORBParams | None = None):
        self.p = params or ORBParams()

    def _opening_range(self, df: pd.DataFrame):
        from datetime import datetime, timedelta
        start = self.p.session_open
        end_dt = (datetime.combine(datetime.today(), start) +
                  timedelta(minutes=self.p.or_minutes)).time()
        or_bars = df[(df.index.time >= start) & (df.index.time < end_dt)]
        if or_bars.empty:
            return None
        return float(or_bars["high"].max()), float(or_bars["low"].min()), end_dt

    def evaluate(self, df: pd.DataFrame) -> Signal:
        flat = Signal(Side.FLAT, 0.0, 0.0, 0.0, 0.0, "no setup")
        if len(df) < 2 or df.index.tz is None:
            return flat

        rng = self._opening_range(df)
        if rng is None:
            return Signal(Side.FLAT, 0.0, 0.0, 0.0, 0.0, "no opening range yet")
        or_high, or_low, or_end = rng
        or_range = or_high - or_low
        if or_range <= 0:
            return flat

        last = df.iloc[-1]
        last_t = df.index[-1].time()
        # Only act after the OR is complete and inside the entry window.
        if last_t < or_end or last_t >= self.p.no_entry_after:
            return flat

        prev = df.iloc[-2]
        # Average bar volume from open up to (not including) the breakout bar.
        prior = df[df.index < df.index[-1]]
        avg_vol = float(prior["volume"].mean()) if len(prior) else 0.0
        vol_ok = avg_vol > 0 and last["volume"] >= self.p.volume_mult * avg_vol

        broke_up = prev["close"] <= or_high and last["close"] > or_high
        broke_dn = prev["close"] >= or_low and last["close"] < or_low

        if broke_up and vol_ok:
            side, level = Side.LONG, or_high
        elif broke_dn and vol_ok:
            side, level = Side.SHORT, or_low
        else:
            if (broke_up or broke_dn) and not vol_ok:
                return Signal(Side.FLAT, 0.0, 0.0, 0.0, 0.0, "break w/o volume")
            return flat

        entry = float(last["close"])
        # Reference levels for risk sizing; actual exit is premium-based.
        if side is Side.LONG:
            target, stop = entry + or_range, level   # measured move; void if back below level
        else:
            target, stop = entry - or_range, level
        return Signal(side, 0.6, entry, target, stop,
                      f"ORB {side.value} break of {level:.2f} (range {or_range:.2f}, vol ok)")
