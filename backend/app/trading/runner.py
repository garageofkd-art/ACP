"""Live runner: wires the Upstox feed -> bar aggregator -> trading session.

Holds a single `TradingSession` and pumps live ticks through the aggregator
into it. Built for unattended operation:
  - a single bad bar/order is logged and isolated, never kills the feed thread;
  - the feed auto-reconnects with exponential backoff on transient drops;
  - status (running, last tick, last error, reauth-needed) is exposed for the UI.

Instrument keys are resolved only when the runner actually starts, so
constructing it stays offline-safe.
"""
from __future__ import annotations

import logging
import time as _time
from datetime import datetime

from app.core.events import Bar, Tick
from app.data.aggregator import BarAggregator
from app.trading.session import TradingSession

_MAX_BACKOFF_S = 60


class LiveRunner:
    def __init__(self, session: TradingSession):
        self.session = session
        self.agg = BarAggregator(self._safe_on_bar)
        self._feed = None
        self.running = False
        self.needs_reauth = False
        self.last_error: str | None = None
        self.last_tick_ts: datetime | None = None
        self.log = logging.getLogger("quantifywealth.runner")

    def start(self) -> None:
        """Blocking — resolves instruments, connects the feed, and keeps it up
        with backoff reconnection until `stop()` is called."""
        from app.data.instruments import resolve_instrument_keys
        from app.data.live_feed import UpstoxLiveFeed

        keys = resolve_instrument_keys()
        key_to_symbol = {k: s for s, k in keys.items()}
        feed_keys = list(keys.values())
        # Also stream the index (data only) when the regime filter is in use.
        if getattr(self.session, "regime", None) is not None:
            from app.data.instruments import INDEX_INSTRUMENT_KEY, INDEX_SYMBOL

            key_to_symbol[INDEX_INSTRUMENT_KEY] = INDEX_SYMBOL
            feed_keys.append(INDEX_INSTRUMENT_KEY)
        self.running = True
        self.needs_reauth = False
        backoff = 2

        while self.running:
            try:
                self._feed = UpstoxLiveFeed(feed_keys, key_to_symbol, self._on_tick)
                self.log.info("Connecting Upstox live feed for %d instruments…", len(keys))
                self._feed.connect()  # blocks until disconnect/error
                backoff = 2
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.log.error("Feed error: %s", self.last_error)
                if "401" in str(exc) or "unauthor" in str(exc).lower():
                    self.needs_reauth = True
                    self.log.error("Upstox token looks invalid/expired — re-authentication required.")
                    break
            if not self.running:
                break
            self.log.info("Reconnecting in %ds…", backoff)
            _time.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)

    def stop(self) -> None:
        self.running = False
        if self._feed is not None:
            self._feed.disconnect()
        self.agg.flush()
        self.log.info("Runner stopped.")

    def _on_tick(self, tick: Tick) -> None:
        self.last_tick_ts = tick.ts
        self.agg.on_tick(tick)

    def _safe_on_bar(self, bar: Bar) -> None:
        try:
            self.session.on_bar(bar)
        except Exception:  # noqa: BLE001
            self.log.exception("on_bar failed for %s — skipping this bar", bar.symbol)

    def snapshot(self) -> dict:
        snap = self.session.snapshot()
        snap["running"] = self.running
        snap["authenticated"] = bool(self.session.s.upstox_access_token)
        snap["needs_reauth"] = self.needs_reauth
        snap["last_error"] = self.last_error
        snap["last_tick"] = self.last_tick_ts.isoformat() if self.last_tick_ts else None
        return snap
