"""Cost & break-even tracking.

Turns the journal into a plain-English monthly scoreboard: how much the agent
spent on trading friction + infrastructure, and how much gross P&L it needs just
to break even. Profit only starts above that line.
"""
from __future__ import annotations

from datetime import date

from app import journal
from app.config import get_settings


def monthly_cost_report(month: str | None = None) -> dict:
    """Cost/break-even summary for a calendar month (YYYY-MM, default current)."""
    settings = get_settings()
    month = month or date.today().strftime("%Y-%m")

    days = [d for d in journal.load_days() if d["date"].startswith(month)]
    trades = [t for d in days for t in d.get("trades", [])]

    trading_costs = round(sum(t.get("costs", 0.0) for t in trades), 2)
    net_pnl = round(sum(d["net_pnl"] for d in days), 2)   # already net of trading costs
    gross_pnl = round(net_pnl + trading_costs, 2)
    infra = settings.monthly_infra_cost_inr

    return {
        "month": month,
        "num_trades": len(trades),
        "trading_costs": trading_costs,
        "infra_cost": infra,
        "total_costs": round(trading_costs + infra, 2),
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "profit_after_infra": round(net_pnl - infra, 2),
        # Gross P&L the strategy must produce to fully cover costs this month.
        "breakeven_gross": round(trading_costs + infra, 2),
        "covering_costs": (net_pnl - infra) >= 0,
        "avg_cost_per_trade": round(trading_costs / len(trades), 2) if trades else 0.0,
    }
