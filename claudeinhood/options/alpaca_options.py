"""Alpaca options provider: fetch the 0/1-DTE chain, pick a contract, quote it.

Implements OptionsProvider. Given a directional signal it returns an OptionChoice
with `est_premium` (quote mid) and `est_delta` filled, so the risk manager can
size a real order.

`alpaca-py` is imported lazily. API surface varies across alpaca-py versions, so
field access is defensive. Validate against your installed version on paper.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from ..strategy.base import Side
from .selector import OptionChoice, parse_occ, pick_strike

log = logging.getLogger("claudeinhood.options.alpaca")


class AlpacaOptions:
    def __init__(self, api_key: str, secret_key: str, feed: str = "indicative"):
        from alpaca.data.historical.option import OptionHistoricalDataClient

        self._client = OptionHistoricalDataClient(api_key, secret_key)
        self.feed = feed

    def _chain(self, underlying: str, today: date, max_dte: int,
               spot: float, right: str):
        """Return chain snapshots filtered to near-dated, near-the-money strikes
        for one side. Keyed by OCC symbol."""
        from alpaca.data.requests import OptionChainRequest

        kwargs = dict(
            underlying_symbol=underlying,
            expiration_date_gte=today,
            expiration_date_lte=today + timedelta(days=max_dte),
            strike_price_gte=spot * 0.97,
            strike_price_lte=spot * 1.03,
        )
        # `type` filter (call/put) when supported by the installed version.
        try:
            from alpaca.trading.enums import ContractType
            kwargs["type"] = ContractType.CALL if right == "C" else ContractType.PUT
        except Exception:
            pass
        return self._client.get_option_chain(OptionChainRequest(**kwargs))

    @staticmethod
    def _mid(snapshot) -> Optional[float]:
        q = getattr(snapshot, "latest_quote", None)
        if q is None:
            return None
        bid = float(getattr(q, "bid_price", 0) or 0)
        ask = float(getattr(q, "ask_price", 0) or 0)
        if bid <= 0 and ask <= 0:
            return None
        if bid <= 0:
            return ask
        if ask <= 0:
            return bid
        return round((bid + ask) / 2, 2)

    @staticmethod
    def _delta(snapshot) -> Optional[float]:
        g = getattr(snapshot, "greeks", None)
        d = getattr(g, "delta", None) if g else None
        return float(d) if d is not None else None

    def select(
        self, underlying: str, underlying_price: float, side: Side,
        today: date, max_dte: int,
    ) -> Optional[OptionChoice]:
        target_strike, right = pick_strike(underlying_price, side)
        try:
            chain = self._chain(underlying, today, max_dte, underlying_price, right)
        except Exception:
            log.exception("option chain fetch failed for %s", underlying)
            return None
        if not chain:
            log.info("empty option chain for %s", underlying)
            return None

        # Among the filtered contracts, pick the soonest expiry and the strike
        # closest to our target, that has a usable quote.
        best = None  # (expiry, |strike-target|, occ, strike, premium, delta)
        for occ, snap in chain.items():
            try:
                _, expiry, r, strike = parse_occ(occ)
            except Exception:
                continue
            if r != right:
                continue
            premium = self._mid(snap)
            if premium is None:
                continue
            key = (expiry, abs(strike - target_strike))
            if best is None or key < best[0]:
                best = (key, occ, expiry, strike, premium, self._delta(snap))

        if best is None:
            log.info("no quotable %s contract near %.2f", right, target_strike)
            return None

        _, occ, expiry, strike, premium, delta = best
        return OptionChoice(
            occ_symbol=occ, expiry=expiry, strike=strike, right=right,
            est_premium=premium, est_delta=delta,
        )
