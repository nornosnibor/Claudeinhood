"""Flow-confirmation layer.

A FlowFilter reads "where the money's going" (options flow, dark-pool, whale
prints) for a symbol and lets the engine veto a fade that's fighting strong
same-direction flow. It does NOT generate entries — it only blocks bad ones.

The decision math (`flow_allows`) is pure and unit-tested. Concrete providers
(ProBors, Unusual Whales, Finnhub) implement `read()` behind this interface, so
the engine never depends on a specific vendor.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from ..strategy.base import Side


@dataclass(frozen=True)
class FlowReading:
    """Net directional flow for a symbol.

    net_sentiment: -1.0 (strongly bearish) .. +1.0 (strongly bullish)
    strength:       0.0 (noise) .. 1.0 (high conviction / large notional)
    """
    net_sentiment: float
    strength: float
    as_of: Optional[datetime] = None
    source: str = "unknown"
    notional: Optional[float] = None

    @property
    def effective(self) -> float:
        """Sentiment scaled by conviction, in [-1, 1]."""
        return max(-1.0, min(1.0, self.net_sentiment)) * max(0.0, min(1.0, self.strength))


def flow_allows(
    side: Side,
    reading: Optional[FlowReading],
    *,
    opposing_threshold: float = 0.4,
    max_age_seconds: Optional[float] = 600.0,
    now: Optional[datetime] = None,
) -> tuple[bool, str]:
    """Decide whether flow permits a fade in ``side``.

    We veto only when flow strongly OPPOSES our trade — i.e. the stretched move
    we want to fade has real conviction behind it, so it's probably not an
    overreaction. Missing or stale data never blocks (fail-open): the flow layer
    is a safety veto, not a gate that silences the strategy when data is absent.
    """
    if reading is None:
        return True, "no flow data (allow)"

    if max_age_seconds is not None and reading.as_of is not None:
        ref = now or datetime.now(reading.as_of.tzinfo)
        age = (ref - reading.as_of).total_seconds()
        if age > max_age_seconds:
            return True, f"flow stale {age:.0f}s (allow)"

    eff = reading.effective
    if side is Side.LONG and eff <= -opposing_threshold:
        return False, f"veto LONG: bearish flow {eff:+.2f}"
    if side is Side.SHORT and eff >= opposing_threshold:
        return False, f"veto SHORT: bullish flow {eff:+.2f}"
    return True, f"flow ok {eff:+.2f}"


class FlowFilter(Protocol):
    def read(self, symbol: str) -> Optional[FlowReading]: ...


class NullFlowFilter:
    """Default no-op filter: no flow data, never vetoes. Used until a real
    provider (ProBors) is configured."""

    def read(self, symbol: str) -> Optional[FlowReading]:
        return None
