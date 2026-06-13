"""Opening-gap fade.

If a stock opens far from the previous day's close (a gap), fade it back toward
that close — gap up -> short, gap down -> long. Target = previous close, stop = a
further extension. One trade per symbol per day, entered in the first few minutes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.core.events import Bar, Side, Signal, SignalType
from app.strategies.base import Strategy


@dataclass(slots=True)
class _GapState:
    day: date
    prev_close: float | None = None
    today_open: float | None = None
    last_close: float = 0.0
    traded: bool = False


class GapStrategy(Strategy):
    name = "Gap"

    def __init__(
        self,
        gap_pct: float = 0.01,        # min open-vs-prev-close gap to fade
        stop_pct: float = 0.005,      # further extension that stops us out
        entry_window_minutes: int = 15,
        session_start: time = time(9, 15),
    ):
        self.gap_pct = gap_pct
        self.stop_pct = stop_pct
        self.entry_window = entry_window_minutes
        self.session_start = session_start
        self._state: dict[str, _GapState] = {}

    def reset(self) -> None:
        self._state = {}

    def _window_end(self) -> time:
        base = datetime(2000, 1, 1, self.session_start.hour, self.session_start.minute)
        return (base + timedelta(minutes=self.entry_window)).time()

    def on_bar(self, bar: Bar) -> list[Signal]:
        d = bar.ts.date()
        st = self._state.get(bar.symbol)
        if st is None or st.day != d:
            prev_close = st.last_close if (st and st.last_close > 0) else None
            st = _GapState(day=d, prev_close=prev_close, today_open=bar.open)
            self._state[bar.symbol] = st
        st.last_close = bar.close  # carries into tomorrow as prev_close

        t = bar.ts.time()
        if (st.prev_close is None or st.prev_close <= 0 or st.traded
                or t < self.session_start or t >= self._window_end()):
            return []

        gap = (st.today_open - st.prev_close) / st.prev_close
        if gap > self.gap_pct:
            stop = bar.close * (1 + self.stop_pct)
            if stop > bar.close and st.prev_close < bar.close:
                st.traded = True
                return [Signal(bar.symbol, bar.ts, SignalType.ENTRY, Side.SELL,
                               price=bar.close, stop=stop, target=st.prev_close, reason="Gap fade short")]
        elif gap < -self.gap_pct:
            stop = bar.close * (1 - self.stop_pct)
            if stop < bar.close and st.prev_close > bar.close:
                st.traded = True
                return [Signal(bar.symbol, bar.ts, SignalType.ENTRY, Side.BUY,
                               price=bar.close, stop=stop, target=st.prev_close, reason="Gap fade long")]
        return []
