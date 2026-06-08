"""Tick -> bar aggregation.

The live feed delivers ticks (last-traded price); strategies consume bars. This
rolls ticks up into fixed-interval (default 1-minute) OHLCV bars and emits a
completed bar the moment a tick crosses into the next interval. `flush()`
finalizes the in-progress bar (e.g. at square-off).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from app.core.events import Bar, Tick


def _floor(ts: datetime, seconds: int) -> datetime:
    epoch = int(ts.timestamp())
    floored = epoch - (epoch % seconds)
    return datetime.fromtimestamp(floored, tz=ts.tzinfo)


@dataclass(slots=True)
class _Building:
    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class BarAggregator:
    def __init__(self, on_bar: Callable[[Bar], None], interval_seconds: int = 60):
        self.on_bar = on_bar
        self.interval = interval_seconds
        self._cur: dict[str, _Building] = {}

    def on_tick(self, tick: Tick) -> None:
        bucket = _floor(tick.ts, self.interval)
        b = self._cur.get(tick.symbol)
        if b is None:
            self._cur[tick.symbol] = _Building(bucket, tick.ltp, tick.ltp, tick.ltp, tick.ltp, tick.volume)
            return
        if bucket > b.start:
            self._emit(tick.symbol, b)
            self._cur[tick.symbol] = _Building(bucket, tick.ltp, tick.ltp, tick.ltp, tick.ltp, tick.volume)
            return
        # Same bucket: update OHLCV.
        b.high = max(b.high, tick.ltp)
        b.low = min(b.low, tick.ltp)
        b.close = tick.ltp
        b.volume += tick.volume

    def flush(self) -> None:
        for sym, b in list(self._cur.items()):
            self._emit(sym, b)
        self._cur.clear()

    def _emit(self, symbol: str, b: _Building) -> None:
        self.on_bar(Bar(symbol, b.start, b.open, b.high, b.low, b.close, int(b.volume)))
