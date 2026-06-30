"""Premium-based exit decision — Ronny's rule: take 10-30%, stop at -22%,
never hold to expiry. Pure and unit-tested.
"""
from __future__ import annotations

from typing import Optional


def premium_exit(
    entry_premium: float,
    current_premium: float,
    *,
    target_pct: float,
    stop_pct: float,
) -> tuple[Optional[str], float]:
    """Return (reason, pnl_pct).

    reason is "target" if the option is up >= target_pct, "stop" if down
    <= -stop_pct, else None (hold). pnl_pct is the current option P&L fraction.
    target_pct/stop_pct are positive fractions (e.g. 0.20 and 0.22).
    """
    if entry_premium <= 0:
        return None, 0.0
    pnl = (current_premium - entry_premium) / entry_premium
    if pnl >= target_pct:
        return "target", pnl
    if pnl <= -stop_pct:
        return "stop", pnl
    return None, pnl
