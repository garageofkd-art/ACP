"""Grid-search optimizer for ORB parameters.

Runs the backtest across a grid of (opening-range minutes, target-R, latest
entry) and ranks the combinations by a chosen objective. This is how we tune
the strategy on real history instead of guessing — and a guard against
overfitting once we look at the spread of results, not just the top row.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from itertools import product

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.config import Settings, get_settings
from app.strategies.orb import ORBStrategy


@dataclass
class ORBGrid:
    opening_range_minutes: list[int] = field(default_factory=lambda: [5, 15, 30])
    target_r: list[float] = field(default_factory=lambda: [1.5, 2.0, 3.0])
    latest_entry: list[time] = field(default_factory=lambda: [time(14, 30)])


def optimize(
    data: dict[str, pd.DataFrame],
    grid: ORBGrid | None = None,
    settings: Settings | None = None,
    objective: str = "net_pnl",
) -> pd.DataFrame:
    """Return one row per parameter combo, sorted best-first by `objective`."""
    grid = grid or ORBGrid()
    settings = settings or get_settings()
    rows: list[dict] = []

    for orm, tr, le in product(grid.opening_range_minutes, grid.target_r, grid.latest_entry):
        strat = ORBStrategy(opening_range_minutes=orm, target_r=tr, latest_entry=le)
        result = BacktestEngine(strat, settings=settings).run(data)
        row = {"opening_range_minutes": orm, "target_r": tr, "latest_entry": le.strftime("%H:%M")}
        row.update(result.stats)
        rows.append(row)

    df = pd.DataFrame(rows)
    if objective in df.columns:
        df = df.sort_values(objective, ascending=False).reset_index(drop=True)
    return df


def split_by_date(
    data: dict[str, pd.DataFrame], train_frac: float = 0.6
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Chronological split: earliest `train_frac` of trading days -> train,
    the rest -> test. The basis for honest (out-of-sample) walk-forward."""
    dates = sorted({ts.date() for df in data.values() for ts in df["ts"]})
    if not dates:
        return data, {}
    k = max(1, int(len(dates) * train_frac))
    train_dates = set(dates[:k])

    train: dict[str, pd.DataFrame] = {}
    test: dict[str, pd.DataFrame] = {}
    for sym, df in data.items():
        in_train = df["ts"].map(lambda x: x.date() in train_dates)
        tr, te = df[in_train], df[~in_train]
        if not tr.empty:
            train[sym] = tr.reset_index(drop=True)
        if not te.empty:
            test[sym] = te.reset_index(drop=True)
    return train, test


def walk_forward(
    data: dict[str, pd.DataFrame],
    grid: ORBGrid | None = None,
    settings: Settings | None = None,
    train_frac: float = 0.6,
    objective: str = "net_pnl",
) -> dict:
    """Optimize on the train window, then evaluate the winning params on the
    untouched test window. If test results collapse vs train, that's overfit —
    the single most important guard before trusting a backtest."""
    settings = settings or get_settings()
    train, test = split_by_date(data, train_frac)
    table = optimize(train, grid, settings, objective)
    best = table.iloc[0].to_dict()

    strat = ORBStrategy(
        opening_range_minutes=int(best["opening_range_minutes"]),
        target_r=float(best["target_r"]),
    )
    test_result = BacktestEngine(strat, settings=settings).run(test) if test else None
    return {
        "best_params": {
            "opening_range_minutes": int(best["opening_range_minutes"]),
            "target_r": float(best["target_r"]),
        },
        "train_stats": {k: best[k] for k in ("num_trades", "net_pnl", "win_rate", "profit_factor")},
        "test_stats": test_result.stats if test_result else None,
    }
