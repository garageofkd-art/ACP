"""Risk engine: position sizing and hard limits.

Sits between a strategy `Signal` and execution. It turns intent into a sized
order (or zero), and enforces the limits that protect the capital:
  - per-trade risk cap (size from stop distance)
  - max concurrent positions
  - max daily loss -> kill switch (no new entries that day)

The same instance is used in backtest, paper, and live so the guard rails are
identical everywhere.
"""
from __future__ import annotations

import math
from datetime import date

from app.config import Settings
from app.core.events import Signal


class RiskManager:
    def __init__(self, settings: Settings):
        self.s = settings
        self._daily_pnl: dict[date, float] = {}

    @staticmethod
    def per_share_risk(signal: Signal) -> float:
        if signal.stop is None:
            return 0.0
        return abs(signal.price - signal.stop)

    def size(self, signal: Signal, fill_price: float, available: float) -> int:
        """Shares to trade: bounded by per-trade risk AND available capital."""
        psr = self.per_share_risk(signal)
        if psr <= 0 or fill_price <= 0:
            return 0
        qty_by_risk = math.floor(self.s.risk_per_trade_inr / psr)
        qty_by_cash = math.floor(available / fill_price)
        return max(0, min(qty_by_risk, qty_by_cash))

    def daily_pnl(self, day: date) -> float:
        return self._daily_pnl.get(day, 0.0)

    def can_enter(self, day: date, open_positions: int) -> bool:
        if open_positions >= self.s.max_concurrent_positions:
            return False
        if self.daily_pnl(day) <= -self.s.max_daily_loss_inr:
            return False  # kill switch tripped for the day
        return True

    def record_close(self, day: date, net_pnl: float) -> None:
        self._daily_pnl[day] = self._daily_pnl.get(day, 0.0) + net_pnl
