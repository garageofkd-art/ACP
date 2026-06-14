"""Run a user-defined StrategySpec through the rigorous backtest -> honest verdict.

This is the product's core operation: take a strategy spec, backtest it on the
chosen timeframe with realistic costs and an out-of-sample split, and return a
plain, honest result (PROMISING / NO EDGE / INSUFFICIENT DATA) — institutional
rigor, not hype.
"""
from __future__ import annotations

import pandas as pd

from app.backtest.costs import DELIVERY_COSTS, CostConfig
from app.backtest.engine import BacktestEngine
from app.backtest.optimizer import split_by_date
from app.config import Settings, get_settings
from app.strategies.spec import SpecStrategy, StrategySpec


def _verdict(test: dict | None) -> str:
    if not test or test["num_trades"] < 20:
        return "INSUFFICIENT DATA"
    if test["net_pnl"] > 0 and test["profit_factor"] >= 1.3 and test["expectancy"] > 0:
        return "PROMISING"
    return "NO EDGE"


def run_spec(spec: StrategySpec, data: dict[str, pd.DataFrame], settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    positional = spec.timeframe == "day"
    cost = DELIVERY_COSTS if positional else CostConfig()

    def _run(d: dict) -> dict:
        engine = BacktestEngine(SpecStrategy(spec), settings=settings, cost=cost, intraday=not positional)
        return engine.run(d).stats

    full = _run(data)
    train_data, test_data = split_by_date(data, 0.6)
    train = _run(train_data) if train_data else None
    test = _run(test_data) if test_data else None

    return {
        "name": spec.name,
        "timeframe": spec.timeframe,
        "full": full,
        "train": train,
        "test": test,
        "verdict": _verdict(test),
    }
