"""Positional trend-following: enter on breakout, trail-exit with a profit."""
from datetime import datetime, timedelta

import pandas as pd

from app.backtest.costs import DELIVERY_COSTS
from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.core.events import Side
from app.strategies.trend import TrendBreakoutStrategy


def _daily(prices: list[float]) -> pd.DataFrame:
    start = datetime(2026, 1, 1)
    return pd.DataFrame([
        {"ts": start + timedelta(days=i), "open": p, "high": p, "low": p, "close": p, "volume": 100000}
        for i, p in enumerate(prices)
    ])


def _engine(strat):
    # Positional mode: engine holds overnight, strategy owns the exit.
    return BacktestEngine(strat, settings=Settings(capital=100_000),
                          cost=DELIVERY_COSTS, intraday=False)


def test_trend_breakout_rides_uptrend_then_exits_in_profit():
    # 12 flat days (warm up windows), a clean uptrend, then a pullback.
    prices = [100.0] * 12 + [102, 104, 106, 108, 110, 112, 114, 116, 118, 120] + [116, 110, 104]
    strat = TrendBreakoutStrategy(entry_lookback=5, exit_lookback=3, trend_ma=10)
    res = _engine(strat).run({"X": _daily(prices)})

    assert res.stats["num_trades"] == 1
    t = res.trades[0]
    assert t.side == Side.BUY
    assert t.reason == "Trend exit"          # closed by the strategy's trailing exit
    assert t.net_pnl > 0                       # rode the trend up


def test_no_breakout_no_trade():
    prices = [100.0] * 40                      # dead flat -> never breaks out
    strat = TrendBreakoutStrategy(entry_lookback=5, exit_lookback=3, trend_ma=10)
    res = _engine(strat).run({"X": _daily(prices)})
    assert res.stats["num_trades"] == 0


def test_position_held_overnight_not_squared_off():
    # In positional mode there is no intraday square-off; the only exit is the
    # strategy's trailing exit (or end-of-data).
    prices = [100.0] * 12 + [102, 104, 106, 108, 110]   # enters, never pulls back
    strat = TrendBreakoutStrategy(entry_lookback=5, exit_lookback=3, trend_ma=10)
    res = _engine(strat).run({"X": _daily(prices)})
    # Closed only at end_of_data, never "square_off".
    assert all(t.reason != "square_off" for t in res.trades)
