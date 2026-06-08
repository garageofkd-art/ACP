"""Core domain objects shared across backtest, paper, and live modes.

The whole system speaks in `Bar`/`Tick` -> `Signal` -> `Order` -> `Fill`,
so the same strategy and risk code runs unchanged regardless of where the
data and execution come from.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class SignalType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


@dataclass(frozen=True, slots=True)
class Bar:
    """A single OHLCV candle for one instrument."""

    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True, slots=True)
class Tick:
    """A live last-traded-price update."""

    symbol: str
    ts: datetime
    ltp: float
    volume: int = 0


@dataclass(frozen=True, slots=True)
class Signal:
    """Strategy intent. It never sizes or talks to the broker itself —
    the risk engine turns this into a concrete, sized order (or vetoes it)."""

    symbol: str
    ts: datetime
    type: SignalType
    side: Side
    price: float  # reference price (e.g. breakout level)
    stop: float | None = None  # stop-loss price (entries should set this)
    target: float | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Order:
    symbol: str
    ts: datetime
    side: Side
    quantity: int
    price: float  # 0 => market order
    stop: float | None = None
    target: float | None = None
    tag: str = ""


@dataclass(frozen=True, slots=True)
class Fill:
    symbol: str
    ts: datetime
    side: Side
    quantity: int
    price: float
    cost: float = 0.0  # total charges applied to this fill
    order_tag: str = ""
