"""Gap-fade: fade an opening gap back toward the previous close."""
from datetime import datetime, timedelta

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.core.events import Side
from app.strategies.gap import GapStrategy


def _bar(ts, px, v=10000):
    return {"ts": ts, "open": px, "high": px, "low": px, "close": px, "volume": v}


def _two_days_with_gap_up() -> pd.DataFrame:
    rows = []
    d1 = datetime(2026, 6, 1, 9, 15)
    for i in range(30):                       # day 1 flat at 100 -> prev_close 100
        rows.append(_bar(d1 + timedelta(minutes=i), 100.0))
    d2 = datetime(2026, 6, 2, 9, 15)
    rows.append(_bar(d2, 102.0))              # gap up 2% at the open -> fade short
    for i in range(1, 20):                    # fills back to 100 (prev close)
        rows.append(_bar(d2 + timedelta(minutes=i), 100.0))
    return pd.DataFrame(rows)


def test_gap_up_is_faded_short_and_profits():
    res = BacktestEngine(GapStrategy(), settings=Settings(capital=100_000)).run(
        {"X": _two_days_with_gap_up()})
    assert res.stats["num_trades"] == 1
    t = res.trades[0]
    assert t.side == Side.SELL                # faded the gap up
    assert t.net_pnl > 0                      # filled back to prev close


def test_no_gap_no_trade():
    rows = []
    d1 = datetime(2026, 6, 1, 9, 15)
    for day in (d1, datetime(2026, 6, 2, 9, 15)):
        for i in range(20):
            rows.append(_bar(day + timedelta(minutes=i), 100.0))   # no gap
    res = BacktestEngine(GapStrategy(), settings=Settings(capital=100_000)).run({"X": pd.DataFrame(rows)})
    assert res.stats["num_trades"] == 0
