"""anchor_first_bar lets a late start (after the 9:15 open) still trade."""
from datetime import datetime, timedelta

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.strategies.orb import ORBStrategy


def _late_start_day() -> pd.DataFrame:
    """Bars only from 10:00 onward (feed connected late). Range ~100-101 over the
    first 5 minutes, then a clean breakout up."""
    rows = []
    start = datetime(2026, 6, 10, 10, 0)
    for i in range(5):  # opening range 10:00-10:04
        rows.append({"ts": start + timedelta(minutes=i), "open": 100.5, "high": 101.0,
                     "low": 100.0, "close": 100.5, "volume": 12000})
    price = 101.2
    for i in range(5, 40):  # breakout + drift up to target
        price += 0.1
        rows.append({"ts": start + timedelta(minutes=i), "open": price - 0.05,
                     "high": price + 0.2, "low": price - 0.1, "close": price, "volume": 12000})
    return pd.DataFrame(rows)


def _strat(**kw):
    # Filters off so the test isolates the anchoring behaviour.
    base = dict(opening_range_minutes=5, min_range_pct=0.0, max_range_pct=0.0,
                volume_mult=0.0, breakout_buffer_pct=0.0)
    base.update(kw)
    return ORBStrategy(**base)


def test_late_start_trades_when_anchored():
    res = BacktestEngine(_strat(anchor_first_bar=True), settings=Settings(capital=100_000)).run(
        {"X": _late_start_day()})
    assert res.stats["num_trades"] == 1


def test_late_start_does_not_trade_without_anchor():
    # Default (fixed 9:15 open) -> the 10:00 bars are past the range, no trade.
    res = BacktestEngine(_strat(anchor_first_bar=False), settings=Settings(capital=100_000)).run(
        {"X": _late_start_day()})
    assert res.stats["num_trades"] == 0
