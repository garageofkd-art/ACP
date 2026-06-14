"""Spec-driven strategies: a user's idea compiles into a real backtestable strategy."""
from datetime import datetime, timedelta

import pandas as pd

from app.backtest.costs import DELIVERY_COSTS
from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.core.events import Side
from app.research.runner import run_spec
from app.strategies.spec import Condition, SpecStrategy, StrategySpec


def _daily(prices):
    start = datetime(2026, 1, 1)
    return pd.DataFrame([
        {"ts": start + timedelta(days=i), "open": p, "high": p, "low": p, "close": p, "volume": 100000}
        for i, p in enumerate(prices)
    ])


def _engine(spec):
    return BacktestEngine(SpecStrategy(spec), settings=Settings(capital=100_000),
                          cost=DELIVERY_COSTS, intraday=False)


def test_breakout_spec_enters_and_trail_exits_in_profit():
    # "Buy when close breaks the prior 5-day high; exit below the prior 3-day low."
    spec = StrategySpec(
        name="5-day breakout",
        entry=[Condition(indicator="close", op=">", other_indicator="ndayhigh", other_lookback=5)],
        exit=[Condition(indicator="close", op="<", other_indicator="ndaylow", other_lookback=3)],
    )
    prices = [100.0] * 10 + [102, 104, 106, 108, 110, 112, 114, 116, 118, 120] + [116, 110, 104]
    res = _engine(spec).run({"X": _daily(prices)})
    assert res.stats["num_trades"] == 1
    t = res.trades[0]
    assert t.side == Side.BUY
    assert t.net_pnl > 0


def test_rsi_meanreversion_spec_buys_oversold():
    # "Buy when RSI(5) < 35; exit when RSI(5) > 55."
    spec = StrategySpec(
        name="RSI dip buy",
        entry=[Condition(indicator="rsi", lookback=5, op="<", value=35)],
        exit=[Condition(indicator="rsi", lookback=5, op=">", value=55)],
    )
    prices = [100, 100, 100, 100, 100, 98, 96, 94, 92, 90, 95, 100, 104, 106]  # dip then recover
    res = _engine(spec).run({"X": _daily(prices)})
    assert res.stats["num_trades"] >= 1
    assert res.trades[0].side == Side.BUY


def test_run_spec_returns_verdict():
    spec = StrategySpec(
        name="5-day breakout",
        entry=[Condition(indicator="close", op=">", other_indicator="ndayhigh", other_lookback=5)],
        exit=[Condition(indicator="close", op="<", other_indicator="ndaylow", other_lookback=3)],
    )
    prices = [100.0] * 10 + [102, 104, 106, 108, 110, 112, 114, 116, 118, 120] + [116, 110, 104]
    result = run_spec(spec, {"X": _daily(prices)}, settings=Settings(capital=100_000))
    assert result["name"] == "5-day breakout"
    assert "full" in result and "verdict" in result
    assert result["verdict"] in {"PROMISING", "NO EDGE", "INSUFFICIENT DATA"}
