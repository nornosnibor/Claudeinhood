"""Strategy interface and shared signal types."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Side(str, Enum):
    LONG = "long"    # expect price up -> buy shares / buy CALL
    SHORT = "short"  # expect price down -> short shares / buy PUT
    FLAT = "flat"    # no trade


@dataclass(frozen=True)
class Signal:
    side: Side
    # 0..1 confidence the strategy assigns; used for sizing/filtering.
    confidence: float
    # Reference levels for the order/exit logic, in underlying price terms.
    entry_ref: float
    target: float
    stop: float
    reason: str

    @property
    def is_actionable(self) -> bool:
        return self.side is not Side.FLAT


class Strategy:
    """Base class. Implementations consume a bars DataFrame and emit a Signal."""

    name: str = "base"

    def evaluate(self, df: pd.DataFrame) -> Signal:  # pragma: no cover - interface
        raise NotImplementedError
