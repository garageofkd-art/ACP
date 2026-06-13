"""Positional trend-following (Donchian breakout).

On daily bars:
  • Entry: close breaks above the prior `entry_lookback`-day high AND is above a
    long-term moving average (`trend_ma`) — i.e. a new high in an uptrend.
  • Exit: close falls below the prior `exit_lookback`-day low (a trailing exit) —
    emitted as an EXIT signal, so winners can run for as long as the trend holds.
  • Long-only, one position per symbol at a time.

Designed for the positional engine (intraday=False): the engine holds overnight
and this strategy owns the exit. Trend-following is one of the few approaches
with a documented long-run edge — *if* it survives costs, which is what we test.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from app.core.events import Bar, Side, Signal, SignalType
from app.strategies.base import Strategy


@dataclass(slots=True)
class _TrendState:
    entry_highs: deque   # prior highs (entry_lookback)
    exit_lows: deque     # prior lows (exit_lookback)
    ma_closes: deque     # closes for the trend MA
    holding: bool = False


class TrendBreakoutStrategy(Strategy):
    name = "TrendBreakout"

    def __init__(self, entry_lookback: int = 20, exit_lookback: int = 10, trend_ma: int = 100):
        self.entry_lookback = entry_lookback
        self.exit_lookback = exit_lookback
        self.trend_ma = trend_ma
        self._state: dict[str, _TrendState] = {}

    def reset(self) -> None:
        self._state = {}

    def on_bar(self, bar: Bar) -> list[Signal]:
        st = self._state.get(bar.symbol)
        if st is None:
            st = _TrendState(
                entry_highs=deque(maxlen=self.entry_lookback),
                exit_lows=deque(maxlen=self.exit_lookback),
                ma_closes=deque(maxlen=self.trend_ma),
            )
            self._state[bar.symbol] = st

        signals: list[Signal] = []
        # Evaluate against the PRIOR windows (excluding today), then append today.
        ready = (len(st.entry_highs) == self.entry_lookback
                 and len(st.exit_lows) == self.exit_lookback
                 and len(st.ma_closes) == self.trend_ma)

        if ready:
            prior_high = max(st.entry_highs)
            prior_low = min(st.exit_lows)
            ma = sum(st.ma_closes) / len(st.ma_closes)

            if not st.holding:
                if bar.close > prior_high and bar.close > ma:
                    st.holding = True
                    signals.append(Signal(bar.symbol, bar.ts, SignalType.ENTRY, Side.BUY,
                                          price=bar.close, stop=prior_low, target=None,
                                          reason="Trend breakout"))
            elif bar.close < prior_low:
                st.holding = False
                signals.append(Signal(bar.symbol, bar.ts, SignalType.EXIT, Side.SELL,
                                      price=bar.close, reason="Trend exit"))

        st.entry_highs.append(bar.high)
        st.exit_lows.append(bar.low)
        st.ma_closes.append(bar.close)
        return signals
