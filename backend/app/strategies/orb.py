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
from typing import Callable

from app.core.events import Bar, Side, Signal, SignalType
from app.strategies.base import Strategy


@dataclass(slots=True)
class _SymbolState:
    day: date
    or_high: float = float("-inf")
    or_low: float = float("inf")
    vol_sum: float = 0.0
    bar_count: int = 0
    traded: bool = False
    or_start: time | None = None  # used when anchoring the range to the first bar


class ORBStrategy(Strategy):
    name = "ORB"

    def __init__(
        self,
        opening_range_minutes: int = 15,
        target_r: float = 2.0,
        session_start: time = time(9, 15),
        latest_entry: time = time(14, 30),
        min_range_pct: float = 0.0015,
        max_range_pct: float = 0.05,
        volume_mult: float = 1.0,
        breakout_buffer_pct: float = 0.0005,
        regime: Callable[[], int] | None = None,
        anchor_first_bar: bool = False,
    ):
        self.n = opening_range_minutes
        self.target_r = target_r
        self.session_start = session_start
        self.latest_entry = latest_entry
        self.breakout_buffer_pct = breakout_buffer_pct
        # When True, anchor the opening range to the first bar seen each day
        # instead of the fixed market open — lets a late start still trade.
        self.anchor_first_bar = anchor_first_bar
        # Optional market-regime gate: returns +1/-1/0. Longs need >=0, shorts <=0.
        self.regime = regime
        # Filters: skip days whose opening range is too narrow (choppy/dead) or
        # too wide (gap/news distorted), and require volume confirmation on the
        # breakout bar (vs the average bar volume during the opening range).
        self.min_range_pct = min_range_pct
        self.max_range_pct = max_range_pct
        self.volume_mult = volume_mult
        self._state: dict[str, _SymbolState] = {}

    def reset(self) -> None:
        self._state = {}

    def _add_minutes(self, start: time, minutes: int) -> time:
        base = datetime(2000, 1, 1, start.hour, start.minute, start.second)
        return (base + timedelta(minutes=minutes)).time()

    def on_bar(self, bar: Bar) -> list[Signal]:
        d = bar.ts.date()
        st = self._state.get(bar.symbol)
        if st is None or st.day != d:
            st = _SymbolState(day=d)
            self._state[bar.symbol] = st

        t = bar.ts.time()

        # Where does the opening range start? Fixed market open, or the first bar
        # of the day for this symbol (anchor mode, for late starts).
        if self.anchor_first_bar:
            if st.or_start is None:
                st.or_start = t
            range_start = st.or_start
        else:
            if t < self.session_start:
                return []
            range_start = self.session_start
        end_of_range = self._add_minutes(range_start, self.n)

        # Phase 1: accumulate the opening range.
        if t < end_of_range:
            st.or_high = max(st.or_high, bar.high)
            st.or_low = min(st.or_low, bar.low)
            st.vol_sum += bar.volume
            st.bar_count += 1
            return []

        # Phase 2: look for a breakout.
        if st.traded or st.or_high == float("-inf") or t >= self.latest_entry:
            return []

        # Range-width filters: skip dead/choppy or gap-distorted days.
        range_pct = (st.or_high - st.or_low) / bar.close if bar.close else 0.0
        if range_pct < self.min_range_pct:
            return []
        if self.max_range_pct and range_pct > self.max_range_pct:
            return []

        # Volume confirmation: breakout bar must trade at least volume_mult x the
        # average opening-range bar volume (otherwise wait for a stronger bar).
        avg_vol = (st.vol_sum / st.bar_count) if st.bar_count else 0.0
        volume_ok = not (self.volume_mult and avg_vol) or bar.volume >= self.volume_mult * avg_vol

        # Market-regime gate: don't fight the broader market.
        direction = self.regime() if self.regime else 0

        # Require a decisive break beyond the range (buffer), not a marginal poke.
        long_level = st.or_high * (1 + self.breakout_buffer_pct)
        short_level = st.or_low * (1 - self.breakout_buffer_pct)

        if bar.close > long_level:
            if not volume_ok or direction < 0:
                return []
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
        elif bar.close < short_level:
            if not volume_ok or direction > 0:
                return []
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
