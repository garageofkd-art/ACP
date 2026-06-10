"""Upstox live market-data feed (WebSocket v3).

Wraps the Upstox SDK's market-data streamer (which handles the protobuf wire
format) and normalizes each update into a `Tick`. Inert until credentials are
present — the SDK is imported lazily so this module loads offline.

TRADING_MODE governs paper vs real *orders*; this feed always needs a valid
Upstox token because the live price stream is authenticated.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from app.core.events import Tick
from app.market_calendar import IST


class UpstoxLiveFeed:
    def __init__(
        self,
        instrument_keys: list[str],
        key_to_symbol: dict[str, str],
        on_tick: Callable[[Tick], None],
    ):
        self.instrument_keys = instrument_keys
        self.key_to_symbol = key_to_symbol
        self.on_tick = on_tick
        self._streamer = None

    def connect(self) -> None:
        """Blocking: open the stream and dispatch ticks to `on_tick`."""
        import upstox_client

        from app.config import get_settings

        cfg = upstox_client.Configuration()
        cfg.access_token = get_settings().upstox_access_token
        api_client = upstox_client.ApiClient(cfg)

        self._streamer = upstox_client.MarketDataStreamerV3(
            api_client, self.instrument_keys, "ltpc"
        )
        self._streamer.on("message", self._on_message)
        self._streamer.connect()

    def disconnect(self) -> None:
        if self._streamer is not None:
            try:
                self._streamer.disconnect()
            except Exception:
                pass

    def _on_message(self, message: dict) -> None:
        for key, payload in (message.get("feeds") or {}).items():
            symbol = self.key_to_symbol.get(key)
            if symbol is None:
                continue
            ltpc = payload.get("ltpc") or {}
            ltp = ltpc.get("ltp")
            if ltp is None:
                continue
            ltt = ltpc.get("ltt")  # epoch ms
            # Normalize to IST wall-clock (naive) so session_start/square-off are
            # correct regardless of the host machine's timezone.
            if ltt:
                ts = datetime.fromtimestamp(int(ltt) / 1000, IST).replace(tzinfo=None)
            else:
                ts = datetime.now(IST).replace(tzinfo=None)
            self.on_tick(Tick(symbol, ts, float(ltp), int(ltpc.get("ltq") or 0)))
