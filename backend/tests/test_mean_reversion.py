"""Mean-reversion: fade a stretch from VWAP back toward it."""
from datetime import datetime, timedelta

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.core.events import Side
from app.strategies.factory import build_strategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.orb import ORBStrategy


def _bar(ts, px, v=10000):
    return {"ts": ts, "open": px, "high": px, "low": px, "close": px, "volume": v}


def _stretch_then_revert(direction: int) -> pd.DataFrame:
    """15 warm-up bars at 100 (VWAP≈100), a ~1% stretch, then revert to 100."""
    rows = []
    start = datetime(2026, 6, 1, 9, 15)
    for i in range(15):                       # 09:15–09:29 warm-up, VWAP ≈ 100
        rows.append(_bar(start + timedelta(minutes=i), 100.0))
    stretch = 101.0 if direction > 0 else 99.0
    rows.append(_bar(start + timedelta(minutes=15), stretch))   # 09:30 entry bar
    for i in range(16, 45):                   # revert to 100 (back to VWAP)
        rows.append(_bar(start + timedelta(minutes=i), 100.0))
    return pd.DataFrame(rows)


def test_fades_stretch_above_vwap_short():
    data = {"X": _stretch_then_revert(+1)}
    res = BacktestEngine(MeanReversionStrategy(), settings=Settings(capital=100_000)).run(data)
    assert res.stats["num_trades"] == 1
    t = res.trades[0]
    assert t.side == Side.SELL                # faded the stretch above VWAP (short)
    assert t.net_pnl > 0                      # reverted to VWAP -> profit


def test_fades_stretch_below_vwap_long():
    data = {"X": _stretch_then_revert(-1)}
    res = BacktestEngine(MeanReversionStrategy(), settings=Settings(capital=100_000)).run(data)
    assert res.trades[0].side == Side.BUY     # faded the stretch below VWAP (long)
    assert res.trades[0].net_pnl > 0


def test_no_trade_when_not_stretched():
    rows = [{"ts": datetime(2026, 6, 1, 9, 15) + __import__("datetime").timedelta(minutes=i),
             "open": 100, "high": 100, "low": 100, "close": 100, "volume": 10000} for i in range(40)]
    res = BacktestEngine(MeanReversionStrategy(), settings=Settings(capital=100_000)).run({"X": pd.DataFrame(rows)})
    assert res.stats["num_trades"] == 0


def test_factory_selects_strategy():
    assert isinstance(build_strategy(Settings(strategy="mean_reversion")), MeanReversionStrategy)
    assert isinstance(build_strategy(Settings(strategy="orb")), ORBStrategy)
