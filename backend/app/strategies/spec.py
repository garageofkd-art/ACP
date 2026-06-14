"""Spec-driven strategy — the core of the AI backtester product.

A user's idea is expressed as a `StrategySpec` (entry conditions, exit conditions,
optional stop). `SpecStrategy` compiles it into a runnable strategy over a small,
honest set of indicators. The LLM layer (next) only has to translate English into
this spec — keeping the system bounded, explainable, and not a black box.

Supported indicators: close, sma(n), ndayhigh(n), ndaylow(n), rsi(n).
Supported ops: > < >= <=  (LHS indicator vs a constant or another indicator).
Entry = ALL conditions true. Exit = ANY condition true (or the stop).
"""
from __future__ import annotations

from collections import deque
from typing import Optional

from pydantic import BaseModel

from app.core.events import Bar, Side, Signal, SignalType
from app.strategies.base import Strategy

INDICATORS = {"close", "sma", "ndayhigh", "ndaylow", "rsi"}
OPS = {">", "<", ">=", "<="}


class Condition(BaseModel):
    indicator: str               # close | sma | ndayhigh | ndaylow | rsi
    lookback: int = 0            # window for sma/ndayhigh/ndaylow/rsi
    op: str                      # > < >= <=
    value: Optional[float] = None        # compare to a constant, OR
    other_indicator: Optional[str] = None  # compare to another indicator
    other_lookback: int = 0


class StrategySpec(BaseModel):
    name: str = "Custom strategy"
    entry: list[Condition]
    exit: list[Condition] = []
    stop_pct: Optional[float] = None     # exit if price falls this far below entry
    timeframe: str = "day"               # day | 1minute


def _rsi(closes: list[float], n: int) -> Optional[float]:
    if len(closes) < n + 1:
        return None
    window = closes[-(n + 1):]
    gains = losses = 0.0
    for i in range(1, len(window)):
        d = window[i] - window[i - 1]
        gains += d if d > 0 else 0.0
        losses += -d if d < 0 else 0.0
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)


class _SymState:
    __slots__ = ("closes", "highs", "lows", "holding", "entry_price")

    def __init__(self, maxlen: int):
        self.closes: deque = deque(maxlen=maxlen)
        self.highs: deque = deque(maxlen=maxlen)
        self.lows: deque = deque(maxlen=maxlen)
        self.holding = False
        self.entry_price = 0.0


class SpecStrategy(Strategy):
    name = "Spec"

    def __init__(self, spec: StrategySpec):
        self.spec = spec
        lbs = [1]
        for c in spec.entry + spec.exit:
            lbs += [c.lookback, c.other_lookback]
        self._maxlen = max(lbs) + 2
        self._state: dict[str, _SymState] = {}

    def reset(self) -> None:
        self._state = {}

    def _indicator(self, name: str, lookback: int, st: _SymState) -> Optional[float]:
        closes = list(st.closes)
        if name == "close":
            return closes[-1] if closes else None
        if name == "sma":
            return sum(closes[-lookback:]) / lookback if len(closes) >= lookback else None
        if name == "rsi":
            return _rsi(closes, lookback)
        if name == "ndayhigh":   # prior N-day high (excludes today)
            hs = list(st.highs)
            return max(hs[-(lookback + 1):-1]) if len(hs) >= lookback + 1 else None
        if name == "ndaylow":
            ls = list(st.lows)
            return min(ls[-(lookback + 1):-1]) if len(ls) >= lookback + 1 else None
        return None

    def _eval(self, c: Condition, st: _SymState) -> bool:
        lhs = self._indicator(c.indicator, c.lookback, st)
        rhs = c.value if c.value is not None else self._indicator(c.other_indicator, c.other_lookback, st)
        if lhs is None or rhs is None:
            return False
        if c.op == ">":
            return lhs > rhs
        if c.op == "<":
            return lhs < rhs
        if c.op == ">=":
            return lhs >= rhs
        if c.op == "<=":
            return lhs <= rhs
        return False

    def on_bar(self, bar: Bar) -> list[Signal]:
        st = self._state.get(bar.symbol)
        if st is None:
            st = _SymState(self._maxlen)
            self._state[bar.symbol] = st
        st.closes.append(bar.close)
        st.highs.append(bar.high)
        st.lows.append(bar.low)

        if len(st.closes) < self._maxlen:
            return []

        if not st.holding:
            if self.spec.entry and all(self._eval(c, st) for c in self.spec.entry):
                st.holding = True
                st.entry_price = bar.close
                stop = bar.close * (1 - (self.spec.stop_pct or 0.10))
                return [Signal(bar.symbol, bar.ts, SignalType.ENTRY, Side.BUY,
                               price=bar.close, stop=stop, target=None, reason=self.spec.name)]
        else:
            hit_exit = bool(self.spec.exit) and any(self._eval(c, st) for c in self.spec.exit)
            if self.spec.stop_pct and bar.close <= st.entry_price * (1 - self.spec.stop_pct):
                hit_exit = True
            if hit_exit:
                st.holding = False
                return [Signal(bar.symbol, bar.ts, SignalType.EXIT, Side.SELL,
                               price=bar.close, reason="exit")]
        return []
