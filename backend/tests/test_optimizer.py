from datetime import time

from app.backtest.metrics import compute_metrics, per_symbol
from app.backtest.optimizer import ORBGrid, optimize
from app.config import Settings
from tests.test_backtest_orb import _make_long_target_day


def test_optimizer_runs_full_grid_sorted():
    data = {"TEST": _make_long_target_day()}
    grid = ORBGrid(opening_range_minutes=[10, 15], target_r=[1.5, 2.0], latest_entry=[time(14, 30)])
    settings = Settings(capital=100_000)
    table = optimize(data, grid=grid, settings=settings, objective="net_pnl")

    assert len(table) == 4  # 2 x 2 x 1 combinations
    assert "net_pnl" in table.columns
    # Sorted best-first.
    assert list(table["net_pnl"]) == sorted(table["net_pnl"], reverse=True)


def test_metrics_keys_and_per_symbol():
    from app.backtest.engine import BacktestEngine
    from app.strategies.orb import ORBStrategy

    result = BacktestEngine(ORBStrategy(), settings=Settings(capital=100_000)).run(
        {"TEST": _make_long_target_day()}
    )
    for key in ("expectancy", "profit_factor", "sharpe", "max_consecutive_losses", "max_drawdown_pct"):
        assert key in result.stats

    breakdown = per_symbol(result.trades)
    assert breakdown["TEST"]["trades"] == 1
    assert breakdown["TEST"]["net_pnl"] > 0


def test_compute_metrics_empty():
    import pandas as pd

    m = compute_metrics([], pd.DataFrame(columns=["ts", "equity"]), 100_000)
    assert m["num_trades"] == 0
    assert m["profit_factor"] == 0.0
