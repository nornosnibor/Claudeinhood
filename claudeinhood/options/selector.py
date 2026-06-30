"""Map a directional signal to a concrete SPY 0/1-DTE option contract.

Given a Side (LONG -> CALL, SHORT -> PUT), the current underlying price, and the
available expirations, pick a contract by target delta / moneyness. For a $500
account we favor near-the-money to slightly-OTM contracts: enough delta to move
on a reversion, cheap enough to size at least one contract.

The chain fetch is via Alpaca's options data (lazily imported). The selection
math (`pick_strike`, `nearest_expiry`) is pure and unit-tested.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from ..strategy.base import Side


@dataclass(frozen=True)
class OptionChoice:
    occ_symbol: str   # e.g. SPY260630C00540000
    expiry: date
    strike: float
    right: str        # "C" or "P"
    est_premium: Optional[float] = None
    est_delta: Optional[float] = None


def occ_symbol(underlying: str, expiry: date, right: str, strike: float) -> str:
    """Build an OCC-format option symbol."""
    yymmdd = expiry.strftime("%y%m%d")
    strike_int = int(round(strike * 1000))
    return f"{underlying}{yymmdd}{right}{strike_int:08d}"


def nearest_expiry(today: date, expiries: Sequence[date], max_dte: int = 1) -> Optional[date]:
    """Pick the soonest expiry within ``max_dte`` days (0DTE preferred)."""
    candidates = sorted(e for e in expiries if 0 <= (e - today).days <= max_dte)
    return candidates[0] if candidates else None


def pick_strike(
    underlying_price: float,
    side: Side,
    *,
    otm_offset_pct: float = 0.0015,
    strike_increment: float = 1.0,
) -> tuple[float, str]:
    """Choose a strike and right for the given side.

    Slightly OTM by ``otm_offset_pct`` to keep premium low while retaining delta.
    LONG -> CALL above spot; SHORT -> PUT below spot. Rounds to the listed
    strike increment ($1 for SPY).
    """
    if side is Side.LONG:
        raw = underlying_price * (1 + otm_offset_pct)
        strike = round(raw / strike_increment) * strike_increment
        return strike, "C"
    elif side is Side.SHORT:
        raw = underlying_price * (1 - otm_offset_pct)
        strike = round(raw / strike_increment) * strike_increment
        return strike, "P"
    raise ValueError("pick_strike requires a directional side")


def select_contract(
    underlying: str,
    underlying_price: float,
    side: Side,
    today: date,
    available_expiries: Sequence[date],
    *,
    max_dte: int = 1,
) -> Optional[OptionChoice]:
    expiry = nearest_expiry(today, available_expiries, max_dte=max_dte)
    if expiry is None:
        return None
    strike, right = pick_strike(underlying_price, side)
    return OptionChoice(
        occ_symbol=occ_symbol(underlying, expiry, right, strike),
        expiry=expiry,
        strike=strike,
        right=right,
    )
