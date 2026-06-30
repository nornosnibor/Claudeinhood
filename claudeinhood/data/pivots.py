"""Classic floor-trader pivot levels from a prior session's High/Low/Close.

    P  = (H + L + C) / 3
    R1 = 2P - L      S1 = 2P - H
    R2 = P + (H - L) S2 = P - (H - L)
    R3 = H + 2(P-L)  S3 = L - 2(P-H)

Pure math, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pivots:
    p: float
    r1: float
    r2: float
    r3: float
    s1: float
    s2: float
    s3: float

    def levels(self) -> dict[str, float]:
        return {"P": self.p, "R1": self.r1, "R2": self.r2, "R3": self.r3,
                "S1": self.s1, "S2": self.s2, "S3": self.s3}


def compute_pivots(high: float, low: float, close: float) -> Pivots:
    p = (high + low + close) / 3.0
    return Pivots(
        p=p,
        r1=2 * p - low,
        s1=2 * p - high,
        r2=p + (high - low),
        s2=p - (high - low),
        r3=high + 2 * (p - low),
        s3=low - 2 * (p - high),
    )
