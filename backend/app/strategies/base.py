"""Strategy interface.

A strategy is fed one `Bar` at a time (in chronological order) and emits zero
or more `Signal`s of intent. It never sizes positions or talks to the broker —
that's the risk engine and execution layer. This keeps the exact same strategy
code running in backtest, paper, and live.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.events import Bar, Signal


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def on_bar(self, bar: Bar) -> list[Signal]:
        """Process one bar; return any signals it triggers."""

    def reset(self) -> None:
        """Clear internal state (called at the start of a backtest/session)."""
