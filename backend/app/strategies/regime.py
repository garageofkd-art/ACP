"""Market-regime tracker.

Follows the index (Nifty 50) intraday vs its day-open to give a coarse market
direction: +1 (up), -1 (down), 0 (flat/unknown). ORB uses it to avoid
counter-trend trades — only longs when the market's up, shorts when it's down.

Resets automatically each day (open = first price seen that day).
"""
from __future__ import annotations

from datetime import date


class MarketRegime:
    def __init__(self, deadband_pct: float = 0.0):
        self.band = deadband_pct
        self._day: date | None = None
        self.open_price: float | None = None
        self.last: float | None = None

    def update(self, price: float, day: date) -> None:
        if day != self._day:  # new session -> reset the day's open
            self._day = day
            self.open_price = price
        self.last = price

    def direction(self) -> int:
        if self.open_price is None or self.last is None:
            return 0
        if self.last > self.open_price * (1 + self.band):
            return 1
        if self.last < self.open_price * (1 - self.band):
            return -1
        return 0
