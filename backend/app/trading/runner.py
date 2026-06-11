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

_MAX_BACKOFF_S = 120
STALE_RECONNECT_S = 90  # reconnect if no ticks for this long during market hours


class LiveRunner:
    def __init__(self, session: TradingSession):
        self.session = session
        self.agg = BarAggregator(self._safe_on_bar)
        self._feed = None
        self.running = False
        self.needs_reauth = False
        self.last_error: str | None = None
        self.last_tick_ts: datetime | None = None
        self.prices: dict[str, float] = {}      # latest LTP per symbol (tick-rate)
        self.day_open: dict[str, float] = {}     # first price seen today, per symbol
        self._price_day = None
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
        attempt = 0

        while self.running:
            try:
                if self._feed is not None:
                    self._feed.disconnect()  # never leave a connection dangling
                self._feed = UpstoxLiveFeed(feed_keys, key_to_symbol, self._on_tick)
                self.log.info("Connecting Upstox live feed for %d instruments…", len(feed_keys))
                self._feed.connect()  # streams in a background thread, returns immediately
                self.last_error = None
                attempt = 0
                # Connected: hold open while the SDK streams, but watch for a
                # silently-dropped connection (ticks stop) and reconnect if stale.
                # We do NOT recreate in a tight loop — that floods Upstox (429).
                self._hold_until_stale()
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
                if "401" in str(exc) or "unauthor" in str(exc).lower():
                    self.needs_reauth = True
                    self.log.error("Upstox token invalid/expired — re-authentication required.")
                    break
                attempt += 1
                rate_limited = "429" in str(exc) or "too many" in str(exc).lower()
                wait = 60 if rate_limited else min(15 * attempt, _MAX_BACKOFF_S)
                self.log.error("Feed error: %s — reconnecting in %ds (attempt %d).",
                               self.last_error, wait, attempt)
                self._sleep_responsive(wait)

        if self._feed is not None:
            try:
                self._feed.disconnect()
            except Exception:  # noqa: BLE001
                pass

    def _hold_until_stale(self) -> None:
        """Hold the connection open. If no tick arrives for STALE_RECONNECT_S
        while the market is open, return so the outer loop reconnects once
        (graceful recovery from a silently-dropped feed — not a 429 storm)."""
        from app.market_calendar import is_market_open

        last_seen = self.last_tick_ts
        stale_since = _time.monotonic()
        while self.running:
            _time.sleep(2)
            if self.last_tick_ts != last_seen:
                last_seen = self.last_tick_ts
                stale_since = _time.monotonic()
            elif is_market_open() and (_time.monotonic() - stale_since) > STALE_RECONNECT_S:
                self.log.warning("No ticks for %ds during market hours — reconnecting feed.",
                                 STALE_RECONNECT_S)
                return

    def _sleep_responsive(self, seconds: int) -> None:
        """Sleep, but wake immediately if stop() is called."""
        for _ in range(int(seconds)):
            if not self.running:
                return
            _time.sleep(1)

    def stop(self) -> None:
        self.running = False
        if self._feed is not None:
            self._feed.disconnect()
        self.agg.flush()
        self.log.info("Runner stopped.")

    def _on_tick(self, tick: Tick) -> None:
        # Track live prices (tick-rate) for the market watchlist.
        if tick.ts.date() != self._price_day:
            self._price_day = tick.ts.date()
            self.day_open = {}
        self.day_open.setdefault(tick.symbol, tick.ltp)
        self.prices[tick.symbol] = tick.ltp
        self.last_tick_ts = tick.ts
        self.agg.on_tick(tick)

    def market_rows(self) -> list[dict]:
        rows = []
        for sym, ltp in self.prices.items():
            op = self.day_open.get(sym, ltp)
            chg = ltp - op
            rows.append({
                "symbol": sym,
                "ltp": round(ltp, 2),
                "change": round(chg, 2),
                "change_pct": round((chg / op * 100) if op else 0.0, 2),
            })
        # Biggest movers first.
        return sorted(rows, key=lambda r: r["change_pct"], reverse=True)

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
        snap["market"] = self.market_rows()
        return snap
