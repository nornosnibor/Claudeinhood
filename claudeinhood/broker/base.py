"""Broker adapter interface.

The strategy/engine never talk to a broker SDK directly — they go through this
interface. That's what lets us validate on Alpaca paper today and swap in
Robinhood (via robin_stocks or an MCP bridge) tomorrow without touching the
strategy code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional, Protocol


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Account:
    equity: float
    cash: float
    settled_cash: float
    day: date


@dataclass
class Position:
    symbol: str
    qty: int
    avg_price: float
    market_value: float
    unrealized_pnl: float


@dataclass
class OrderResult:
    id: str
    symbol: str
    side: OrderSide
    qty: int
    filled_price: Optional[float]
    status: str


class Broker(Protocol):
    """Minimal surface the engine needs from any broker."""

    def is_market_open(self) -> bool: ...

    def get_account(self) -> Account: ...

    def get_position(self, symbol: str) -> Optional[Position]: ...

    def submit_option_order(
        self, *, option_symbol: str, side: OrderSide, qty: int,
        limit_price: Optional[float] = None,
    ) -> OrderResult: ...

    def submit_equity_order(
        self, *, symbol: str, side: OrderSide, qty: int,
        limit_price: Optional[float] = None,
    ) -> OrderResult: ...
