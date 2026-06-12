"""Intraday VWAP mean-reversion — the opposite hypothesis to ORB.

For each symbol each day:
  1. Track the session VWAP (volume-weighted average price), reset daily.
  2. After a warm-up, when price stretches more than `entry_pct` ABOVE VWAP,
     fade it (SELL, expecting reversion down); more than `entry_pct` BELOW VWAP,
     fade it (BUY, expecting reversion up).
  3. Target = back to VWAP. Stop = a further `stop_pct` extension (continuation).
  4. At most one trade per symbol per day.

No index/regime gate — mean-reversion is counter-trend by nature.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.core.events import Bar, Side, Signal, SignalType
from app.strategies.base import Strategy


@dataclass(slots=True)
class _MRState:
    day: date
    cum_pv: float = 0.0   # cumulative typical-price * volume
    cum_vol: float = 0.0
    traded: bool = False


class MeanReversionStrategy(Strategy):
    name = "MeanReversion"

    def __init__(
        self,
        entry_pct: float = 0.006,   # stretch from VWAP to trigger a fade
        stop_pct: float = 0.004,    # further extension that stops us out
        warmup_minutes: int = 15,   # let VWAP settle before trading
        session_start: time = time(9, 15),
        latest_entry: time = time(14, 30),
    ):
        self.entry_pct = entry_pct
        self.stop_pct = stop_pct
        self.warmup = warmup_minutes
        self.session_start = session_start
        self.latest_entry = latest_entry
        self._state: dict[str, _MRState] = {}

    def reset(self) -> None:
        self._state = {}

    def _warmup_end(self) -> time:
        base = datetime(2000, 1, 1, self.session_start.hour, self.session_start.minute)
        return (base + timedelta(minutes=self.warmup)).time()

    def on_bar(self, bar: Bar) -> list[Signal]:
        d = bar.ts.date()
        st = self._state.get(bar.symbol)
        if st is None or st.day != d:
            st = _MRState(day=d)
            self._state[bar.symbol] = st

        t = bar.ts.time()
        if t < self.session_start:
            return []

        # Update session VWAP with this bar's typical price.
        typical = (bar.high + bar.low + bar.close) / 3
        st.cum_pv += typical * bar.volume
        st.cum_vol += bar.volume
        if st.cum_vol <= 0:
            return []
        vwap = st.cum_pv / st.cum_vol

        if t < self._warmup_end() or t >= self.latest_entry or st.traded or vwap <= 0:
            return []

        dev = (bar.close - vwap) / vwap
        if dev > self.entry_pct:
            # Stretched above VWAP -> fade short, target back to VWAP.
            stop = bar.close * (1 + self.stop_pct)
            if stop > bar.close and vwap < bar.close:
                st.traded = True
                return [Signal(bar.symbol, bar.ts, SignalType.ENTRY, Side.SELL,
                               price=bar.close, stop=stop, target=vwap, reason="MR fade short")]
        elif dev < -self.entry_pct:
            stop = bar.close * (1 - self.stop_pct)
            if stop < bar.close and vwap > bar.close:
                st.traded = True
                return [Signal(bar.symbol, bar.ts, SignalType.ENTRY, Side.BUY,
                               price=bar.close, stop=stop, target=vwap, reason="MR fade long")]
        return []
