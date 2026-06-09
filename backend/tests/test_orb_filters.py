"""ORB filter behaviour: range-width and volume confirmation."""
from datetime import datetime, timedelta

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.strategies.orb import ORBStrategy


def _bar(ts, o, h, l, c, v=10000):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _day(or_lo, or_hi, breakout_close, breakout_vol, or_vol=10000):
    rows = []
    start = datetime(2026, 6, 1, 9, 15)
    for i in range(15):
        rows.append(_bar(start + timedelta(minutes=i), or_lo, or_hi, or_lo, (or_lo + or_hi) / 2, or_vol))
    rows.append(_bar(start + timedelta(minutes=15), or_hi, breakout_close + 0.1, or_hi, breakout_close, breakout_vol))
    price = breakout_close
    for i in range(16, 50):
        price += 0.1
        # Trailing bars carry the same volume so a low-volume scenario persists.
        rows.append(_bar(start + timedelta(minutes=i), price - 0.05, price + 0.2, price - 0.1, price, breakout_vol))
    return pd.DataFrame(rows)


def test_narrow_range_day_is_skipped():
    # OR width 0.05 on ~100 price = 0.05% < default 0.15% min -> no trade.
    data = {"X": _day(100.00, 100.05, 100.10, 10000)}
    res = BacktestEngine(ORBStrategy(), settings=Settings(capital=100_000)).run(data)
    assert res.stats["num_trades"] == 0


def test_low_volume_breakout_is_skipped():
    # Healthy range but breakout volume below the average -> volume filter blocks.
    data = {"X": _day(100.0, 101.0, 101.2, breakout_vol=2000, or_vol=10000)}
    res = BacktestEngine(ORBStrategy(volume_mult=1.0), settings=Settings(capital=100_000)).run(data)
    assert res.stats["num_trades"] == 0


def test_healthy_breakout_still_trades():
    data = {"X": _day(100.0, 101.0, 101.2, breakout_vol=15000, or_vol=10000)}
    res = BacktestEngine(ORBStrategy(), settings=Settings(capital=100_000)).run(data)
    assert res.stats["num_trades"] == 1


def test_filters_can_be_disabled():
    # volume_mult=0 and min_range_pct=0 -> low-vol narrow-ish breakout trades.
    data = {"X": _day(100.0, 101.0, 101.2, breakout_vol=1000)}
    strat = ORBStrategy(min_range_pct=0.0, max_range_pct=0.0, volume_mult=0.0)
    res = BacktestEngine(strat, settings=Settings(capital=100_000)).run(data)
    assert res.stats["num_trades"] == 1
