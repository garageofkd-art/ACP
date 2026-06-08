"""Broker interface.

A broker turns an intended trade (symbol, side, qty, reference price) into a
realized `Fill`. Paper simulates it; live places a real Upstox order. The
trading session is identical regardless of which one is plugged in.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.core.events import Fill, Side


class Broker(ABC):
    mode: str = "base"

    @abstractmethod
    def execute(
        self,
        symbol: str,
        side: Side,
        qty: int,
        ref_price: float,
        ts: datetime,
        tag: str = "",
    ) -> Fill:
        """Execute a market order and return the resulting fill."""
