"""Breakout buffer: only decisive breaks trigger, not marginal pokes."""
from datetime import datetime, timedelta

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.strategies.orb import ORBStrategy


def _bar(ts, o, h, l, c, v=12000):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _day(breakout_close: float) -> pd.DataFrame:
    """Opening range 100-101, then a breakout bar closing at `breakout_close`."""
    rows = []
    start = datetime(2026, 6, 1, 9, 15)
    for i in range(15):
        rows.append(_bar(start + timedelta(minutes=i), 100.5, 101.0, 100.0, 100.5))
    for i in range(15, 45):
        rows.append(_bar(start + timedelta(minutes=i), 101.0, breakout_close + 0.1, 100.9, breakout_close))
    return pd.DataFrame(rows)


def test_marginal_poke_does_not_trigger():
    # 101.03 is above 101 but inside the 0.05% buffer (101.0505) -> no trade.
    strat = ORBStrategy(breakout_buffer_pct=0.0005)
    res = BacktestEngine(strat, settings=Settings(capital=100_000)).run({"X": _day(101.03)})
    assert res.stats["num_trades"] == 0


def test_decisive_break_triggers():
    # 101.30 clears the buffer comfortably -> trades.
    strat = ORBStrategy(breakout_buffer_pct=0.0005)
    res = BacktestEngine(strat, settings=Settings(capital=100_000)).run({"X": _day(101.30)})
    assert res.stats["num_trades"] == 1


def test_zero_buffer_lets_any_break_through():
    strat = ORBStrategy(breakout_buffer_pct=0.0)
    res = BacktestEngine(strat, settings=Settings(capital=100_000)).run({"X": _day(101.03)})
    assert res.stats["num_trades"] == 1
