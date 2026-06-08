"""Performance metrics for a set of trades + equity curve.

This is where we decide whether ORB has an *edge*: expectancy, profit factor,
Sharpe, drawdown, and a per-symbol breakdown. Shared by the engine and the
optimizer so every report speaks the same numbers.
"""
from __future__ import annotations

import math
from collections import defaultdict

import pandas as pd

from app.core.portfolio import Trade

TRADING_DAYS = 252


def compute_metrics(trades: list[Trade], equity: pd.DataFrame, starting_capital: float) -> dict:
    n = len(trades)
    net = sum(t.net_pnl for t in trades)
    gross = sum(t.gross_pnl for t in trades)
    costs = sum(t.costs for t in trades)

    wins = [t.net_pnl for t in trades if t.net_pnl > 0]
    losses = [t.net_pnl for t in trades if t.net_pnl <= 0]
    win_sum, loss_sum = sum(wins), sum(losses)

    if loss_sum < 0:
        profit_factor = win_sum / abs(loss_sum)
    else:
        profit_factor = float("inf") if win_sum > 0 else 0.0

    # Drawdown from the equity curve.
    if equity.empty:
        max_dd = max_dd_pct = 0.0
    else:
        roll_max = equity["equity"].cummax()
        dd = equity["equity"] - roll_max
        max_dd = float(dd.min())
        max_dd_pct = float((dd / roll_max).min() * 100) if (roll_max > 0).all() else 0.0

    # Sharpe from per-day P&L (annualized).
    daily: dict = defaultdict(float)
    for t in trades:
        daily[t.exit_ts.date()] += t.net_pnl
    rets = [v / starting_capital for v in daily.values()]
    if len(rets) > 1:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        std = math.sqrt(var)
        sharpe = (mean / std * math.sqrt(TRADING_DAYS)) if std > 0 else 0.0
    else:
        sharpe = 0.0

    # Worst losing streak.
    max_consec_losses = streak = 0
    for t in trades:
        if t.net_pnl <= 0:
            streak += 1
            max_consec_losses = max(max_consec_losses, streak)
        else:
            streak = 0

    return {
        "num_trades": n,
        "win_rate": (100.0 * len(wins) / n) if n else 0.0,
        "gross_pnl": gross,
        "net_pnl": net,
        "total_costs": costs,
        "avg_win": (win_sum / len(wins)) if wins else 0.0,
        "avg_loss": (loss_sum / len(losses)) if losses else 0.0,
        "expectancy": (net / n) if n else 0.0,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "sharpe": sharpe,
        "max_consecutive_losses": max_consec_losses,
        "return_pct": (100.0 * net / starting_capital) if starting_capital else 0.0,
    }


def per_symbol(trades: list[Trade]) -> dict[str, dict]:
    agg: dict = defaultdict(lambda: {"trades": 0, "net_pnl": 0.0, "wins": 0})
    for t in trades:
        a = agg[t.symbol]
        a["trades"] += 1
        a["net_pnl"] += t.net_pnl
        if t.net_pnl > 0:
            a["wins"] += 1
    return {
        sym: {
            "trades": a["trades"],
            "net_pnl": a["net_pnl"],
            "win_rate": (100.0 * a["wins"] / a["trades"]) if a["trades"] else 0.0,
        }
        for sym, a in agg.items()
    }
