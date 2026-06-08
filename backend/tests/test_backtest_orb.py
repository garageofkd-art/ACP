"""End-to-end backtest on synthetic data with a known ORB outcome."""
from datetime import datetime, timedelta

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.strategies.orb import ORBStrategy


def _bar(ts, o, h, low, c, v=10000):
    return {"ts": ts, "open": o, "high": h, "low": low, "close": c, "volume": v}


def _make_long_target_day() -> pd.DataFrame:
    """09:15-09:29 range 100-101, then a clean breakout up that hits target."""
    rows = []
    start = datetime(2026, 6, 1, 9, 15)
    # Opening range: 15 one-min bars oscillating in [100, 101].
    for i in range(15):
        ts = start + timedelta(minutes=i)
        rows.append(_bar(ts, 100.5, 101.0, 100.0, 100.5))
    # Breakout bar at 09:30: close above range high (101).
    rows.append(_bar(start + timedelta(minutes=15), 100.8, 101.3, 100.7, 101.2))
    # Drift up to hit target (entry ~101.2, stop 100, risk ~1.2, target ~103.6).
    price = 101.2
    for i in range(16, 60):
        ts = start + timedelta(minutes=i)
        price += 0.1
        rows.append(_bar(ts, price - 0.05, price + 0.2, price - 0.1, price))
    return pd.DataFrame(rows)


def test_orb_long_hits_target_and_profits():
    settings = Settings(capital=100_000, risk_per_trade_pct=1.0)
    engine = BacktestEngine(ORBStrategy(opening_range_minutes=15, target_r=2.0), settings=settings)
    result = engine.run({"TEST": _make_long_target_day()})

    assert result.stats["num_trades"] == 1
    trade = result.trades[0]
    assert trade.reason == "target"
    assert trade.net_pnl > 0
    # Net is gross minus costs, so it must be strictly smaller than gross.
    assert trade.net_pnl < trade.gross_pnl
    assert result.stats["return_pct"] > 0


def test_no_trade_when_range_never_breaks():
    settings = Settings(capital=100_000)
    rows = []
    start = datetime(2026, 6, 1, 9, 15)
    for i in range(60):  # flat, range-bound all day -> no breakout
        ts = start + timedelta(minutes=i)
        rows.append(_bar(ts, 100.5, 101.0, 100.0, 100.5))
    engine = BacktestEngine(ORBStrategy(), settings=settings)
    result = engine.run({"TEST": pd.DataFrame(rows)})
    assert result.stats["num_trades"] == 0
