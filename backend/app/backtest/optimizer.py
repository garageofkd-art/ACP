"""Grid-search optimizer for ORB parameters.

Runs the backtest across a grid of (opening-range minutes, target-R, latest
entry) and ranks the combinations by a chosen objective. This is how we tune
the strategy on real history instead of guessing — and a guard against
overfitting once we look at the spread of results, not just the top row.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
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
