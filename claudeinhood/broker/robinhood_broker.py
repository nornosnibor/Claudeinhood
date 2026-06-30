"""Robinhood broker adapter — STUB.

Wire this up when you connect Robinhood (tomorrow). Two viable backends:

  1. `robin_stocks` (https://github.com/jmfernandes/robin_stocks) — a mature
     unofficial Python library. Login with username/password + MFA. It supports
     options orders: ``robin_stocks.robinhood.order_buy_option_limit(...)``.

  2. A Robinhood MCP server, if you have one. In that case this adapter becomes
     a thin shim that calls the MCP tools.

The method signatures below already match the Broker interface, so once the
backend calls are filled in, the engine and strategy work unchanged. Until then
every method raises so we can't accidentally route a live order to an
unimplemented path.

IMPORTANT: there is no official Robinhood API. robin_stocks is reverse-engineered
and can break when Robinhood changes their site. Always keep Alpaca paper as the
validation environment.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from .base import Account, Broker, OrderResult, OrderSide, Position

_NOT_WIRED = (
    "RobinhoodBroker is a stub. Wire up robin_stocks or the Robinhood MCP "
    "before trading live. See claudeinhood/broker/robinhood_broker.py."
)


class RobinhoodBroker(Broker):
    def __init__(self, username: str | None = None, password: str | None = None,
                 mfa_code: str | None = None):
        # TODO: import robin_stocks and login here, e.g.:
        #   import robin_stocks.robinhood as rh
        #   rh.login(username, password, mfa_code=mfa_code)
        #   self._rh = rh
        self._creds = (username, password, mfa_code)

    def is_market_open(self) -> bool:
        raise NotImplementedError(_NOT_WIRED)

    def get_account(self) -> Account:
        # TODO: rh.profiles.load_account_profile() / load_phoenix_account()
        raise NotImplementedError(_NOT_WIRED)

    def get_position(self, symbol: str) -> Optional[Position]:
        # TODO: rh.options.get_open_option_positions()
        raise NotImplementedError(_NOT_WIRED)

    def submit_option_order(
        self, *, option_symbol: str, side: OrderSide, qty: int,
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        # TODO: rh.orders.order_buy_option_limit / order_sell_option_limit
        raise NotImplementedError(_NOT_WIRED)

    def submit_equity_order(
        self, *, symbol: str, side: OrderSide, qty: int,
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        # TODO: rh.orders.order_buy_limit / order_sell_limit
        raise NotImplementedError(_NOT_WIRED)
