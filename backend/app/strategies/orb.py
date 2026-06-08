"""Opening Range Breakout (ORB).

For each symbol each day:
  1. Build the opening range (high/low) over the first N minutes after the open.
  2. After the range is set, a close above the range high -> long; below the
     range low -> short. Stop is the opposite side of the range; target is a
     multiple (R) of the risk.
  3. At most one trade per symbol per day.

Entries late in the session are suppressed (`latest_entry`) so positions have
room to work before the mandatory square-off.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.core.events import Bar, Side, Signal, SignalType
from app.strategies.base import Strategy


@dataclass(slots=True)
class _SymbolState:
    day: date
    or_high: float = float("-inf")
    or_low: float = float("inf")
    traded: bool = False


class ORBStrategy(Strategy):
    name = "ORB"

    def __init__(
        self,
        opening_range_minutes: int = 15,
        target_r: float = 2.0,
        session_start: time = time(9, 15),
        latest_entry: time = time(14, 30),
    ):
        self.n = opening_range_minutes
        self.target_r = target_r
        self.session_start = session_start
        self.latest_entry = latest_entry
        self._state: dict[str, _SymbolState] = {}

    def reset(self) -> None:
        self._state = {}

    def _end_of_range(self) -> time:
        base = datetime(2000, 1, 1, self.session_start.hour, self.session_start.minute)
        return (base + timedelta(minutes=self.n)).time()

    def on_bar(self, bar: Bar) -> list[Signal]:
        d = bar.ts.date()
        st = self._state.get(bar.symbol)
        if st is None or st.day != d:
            st = _SymbolState(day=d)
            self._state[bar.symbol] = st

        t = bar.ts.time()
        if t < self.session_start:
            return []

        # Phase 1: accumulate the opening range.
        if t < self._end_of_range():
            st.or_high = max(st.or_high, bar.high)
            st.or_low = min(st.or_low, bar.low)
            return []

        # Phase 2: look for a breakout.
        if st.traded or st.or_high == float("-inf") or t >= self.latest_entry:
            return []

        if bar.close > st.or_high:
            stop = st.or_low
            risk = bar.close - stop
            if risk > 0:
                st.traded = True
                return [
                    Signal(
                        bar.symbol, bar.ts, SignalType.ENTRY, Side.BUY,
                        price=bar.close, stop=stop,
                        target=bar.close + self.target_r * risk,
                        reason="ORB long breakout",
                    )
                ]
        elif bar.close < st.or_low:
            stop = st.or_high
            risk = stop - bar.close
            if risk > 0:
                st.traded = True
                return [
                    Signal(
                        bar.symbol, bar.ts, SignalType.ENTRY, Side.SELL,
                        price=bar.close, stop=stop,
                        target=bar.close - self.target_r * risk,
                        reason="ORB short breakout",
                    )
                ]
        return []
