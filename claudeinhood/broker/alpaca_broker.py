"""Alpaca broker adapter — used for paper trading and as the data source.

Requires `alpaca-py`. Credentials come from the environment:
  ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER (default "true").

This file imports alpaca-py lazily so the rest of the package (indicators,
strategy, risk, tests) works without the SDK installed.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from .base import Account, Broker, OrderResult, OrderSide, Position


class AlpacaBroker(Broker):
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        from alpaca.trading.client import TradingClient

        self._client = TradingClient(api_key, secret_key, paper=paper)
        self.paper = paper

    def is_market_open(self) -> bool:
        return bool(self._client.get_clock().is_open)

    def get_account(self) -> Account:
        a = self._client.get_account()
        cash = float(a.cash)
        # Alpaca exposes non-marginable buying power as a settled-cash proxy.
        settled = float(getattr(a, "cash_withdrawable", None) or cash)
        return Account(
            equity=float(a.equity),
            cash=cash,
            settled_cash=settled,
            day=date.today(),
        )

    def get_position(self, symbol: str) -> Optional[Position]:
        try:
            p = self._client.get_open_position(symbol)
        except Exception:
            return None
        return Position(
            symbol=p.symbol,
            qty=int(float(p.qty)),
            avg_price=float(p.avg_entry_price),
            market_value=float(p.market_value),
            unrealized_pnl=float(p.unrealized_pl),
        )

    def submit_option_order(
        self, *, option_symbol: str, side: OrderSide, qty: int,
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        from alpaca.trading.enums import OrderSide as AlSide
        from alpaca.trading.enums import TimeInForce
        from alpaca.trading.requests import (
            LimitOrderRequest,
            MarketOrderRequest,
        )

        al_side = AlSide.BUY if side is OrderSide.BUY else AlSide.SELL
        if limit_price is not None:
            req = LimitOrderRequest(
                symbol=option_symbol, qty=qty, side=al_side,
                time_in_force=TimeInForce.DAY, limit_price=round(limit_price, 2),
            )
        else:
            req = MarketOrderRequest(
                symbol=option_symbol, qty=qty, side=al_side,
                time_in_force=TimeInForce.DAY,
            )
        o = self._client.submit_order(req)
        return OrderResult(
            id=str(o.id), symbol=option_symbol, side=side, qty=qty,
            filled_price=float(o.filled_avg_price) if o.filled_avg_price else None,
            status=str(o.status),
        )

    def submit_equity_order(
        self, *, symbol: str, side: OrderSide, qty: int,
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        from alpaca.trading.enums import OrderSide as AlSide
        from alpaca.trading.enums import TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        al_side = AlSide.BUY if side is OrderSide.BUY else AlSide.SELL
        if limit_price is not None:
            req = LimitOrderRequest(
                symbol=symbol, qty=qty, side=al_side,
                time_in_force=TimeInForce.DAY, limit_price=round(limit_price, 2),
            )
        else:
            req = MarketOrderRequest(
                symbol=symbol, qty=qty, side=al_side,
                time_in_force=TimeInForce.DAY,
            )
        o = self._client.submit_order(req)
        return OrderResult(
            id=str(o.id), symbol=symbol, side=side, qty=qty,
            filled_price=float(o.filled_avg_price) if o.filled_avg_price else None,
            status=str(o.status),
        )
