"""Live runner: wires the Upstox feed -> bar aggregator -> trading session.

Holds a single `TradingSession` and pumps live ticks through the aggregator
into it. Instrument keys are resolved only when the runner actually starts, so
constructing it stays offline-safe.
"""
from __future__ import annotations

from app.core.events import Tick
from app.data.aggregator import BarAggregator
from app.strategies.base import Strategy
from app.trading.session import TradingSession


class LiveRunner:
    def __init__(self, session: TradingSession):
        self.session = session
        self.agg = BarAggregator(self.session.on_bar)
        self._feed = None
        self.running = False

    def start(self) -> None:
        """Blocking — resolves instruments, connects the feed, streams ticks."""
        from app.data.instruments import resolve_instrument_keys
        from app.data.live_feed import UpstoxLiveFeed

        keys = resolve_instrument_keys()
        key_to_symbol = {k: s for s, k in keys.items()}
        self._feed = UpstoxLiveFeed(list(keys.values()), key_to_symbol, self._on_tick)
        self.running = True
        self._feed.connect()

    def stop(self) -> None:
        self.running = False
        if self._feed is not None:
            self._feed.disconnect()
        self.agg.flush()

    def _on_tick(self, tick: Tick) -> None:
        self.agg.on_tick(tick)

    def snapshot(self) -> dict:
        snap = self.session.snapshot()
        snap["running"] = self.running
        return snap
