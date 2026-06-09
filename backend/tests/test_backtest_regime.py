"""Backtest engine: index feed drives the regime and is never traded."""
from datetime import datetime, timedelta

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.data.instruments import INDEX_SYMBOL
from app.strategies.orb import ORBStrategy
from app.strategies.regime import MarketRegime
from tests.test_backtest_orb import _make_long_target_day


def _index_day(open_px: float, close_px: float) -> pd.DataFrame:
    """Index bars for the same session, drifting from open_px to close_px."""
    rows = []
    start = datetime(2026, 6, 1, 9, 15)
    step = (close_px - open_px) / 60
    for i in range(60):
        px = open_px + step * i
        rows.append({"ts": start + timedelta(minutes=i), "open": px, "high": px,
                     "low": px, "close": px, "volume": 0})
    return pd.DataFrame(rows)


def _run(index_df):
    regime = MarketRegime()
    strat = ORBStrategy(regime=regime.direction)
    data = {"X": _make_long_target_day(), INDEX_SYMBOL: index_df}
    return BacktestEngine(strat, regime=regime, settings=Settings(capital=100_000)).run(data)


def test_long_blocked_when_index_down():
    res = _run(_index_day(100.0, 98.0))   # index down all day
    assert res.stats["num_trades"] == 0


def test_long_allowed_when_index_up():
    res = _run(_index_day(100.0, 102.0))  # index up
    assert res.stats["num_trades"] == 1


def test_index_symbol_is_never_traded():
    res = _run(_index_day(100.0, 102.0))
    assert all(t.symbol != INDEX_SYMBOL for t in res.trades)
