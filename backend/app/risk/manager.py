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
    def __init__(self, settings: Settings, capital: float | None = None):
        self.s = settings
        # Sizing/loss caps scale with the (possibly compounded) capital base.
        self.capital = capital if capital is not None else settings.capital
        self._daily_pnl: dict[date, float] = {}

    @property
    def risk_per_trade_inr(self) -> float:
        return self.capital * self.s.risk_per_trade_pct / 100.0

    @property
    def max_daily_loss_inr(self) -> float:
        return self.capital * self.s.max_daily_loss_pct / 100.0

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
        qty_by_risk = math.floor(self.risk_per_trade_inr / psr)
        qty_by_cash = math.floor(available / fill_price)
        return max(0, min(qty_by_risk, qty_by_cash))

    def daily_pnl(self, day: date) -> float:
        return self._daily_pnl.get(day, 0.0)

    def kill_switch_tripped(self, day: date) -> bool:
        """Daily loss limit breached -> flatten and stop trading for the day."""
        return self.daily_pnl(day) <= -self.max_daily_loss_inr

    def profit_target_hit(self, day: date) -> bool:
        """Daily profit target reached -> bank it and stop for the day."""
        target = self.s.daily_profit_target_inr
        return target > 0 and self.daily_pnl(day) >= target

    def latest_day_pnl(self) -> float:
        """P&L of the most recent day seen (for live status display)."""
        if not self._daily_pnl:
            return 0.0
        return self._daily_pnl[max(self._daily_pnl)]

    def can_enter(self, day: date, open_positions: int) -> bool:
        if open_positions >= self.s.max_concurrent_positions:
            return False
        if self.kill_switch_tripped(day) or self.profit_target_hit(day):
            return False
        return True

    def record_close(self, day: date, net_pnl: float) -> None:
        self._daily_pnl[day] = self._daily_pnl.get(day, 0.0) + net_pnl
