"""Daily trading journal: persist each session's results so the paper-testing
track record accumulates across days.

This is how we judge "is it making money?" before going live: a growing record
of daily P&L, win-day rate, and the worst drawdown of the cumulative curve.
"""
from __future__ import annotations

import json
from datetime import date

from app.config import DATA_DIR

JOURNAL_DIR = DATA_DIR / "journal"


def _trade_rows(session) -> list[dict]:
    return [
        {
            "symbol": t.symbol,
            "side": t.side.value,
            "qty": t.qty,
            "entry_ts": t.entry_ts.isoformat(),
            "entry_price": round(t.entry_price, 2),
            "exit_ts": t.exit_ts.isoformat(),
            "exit_price": round(t.exit_price, 2),
            "net_pnl": round(t.net_pnl, 2),
            "costs": round(t.costs, 2),
            "reason": t.reason,
        }
        for t in session.pf.trades
    ]


def save_session_day(session, day: date | None = None) -> dict:
    """Write one day's record to the journal and return it."""
    day = day or date.today()
    trades = _trade_rows(session)
    record = {
        "date": day.isoformat(),
        "mode": session.broker.mode,
        "num_trades": len(trades),
        "net_pnl": round(sum(t["net_pnl"] for t in trades), 2),
        "halted": session.halted,
        "trades": trades,
    }
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    (JOURNAL_DIR / f"{day.isoformat()}.json").write_text(json.dumps(record, indent=2))
    return record


def load_days() -> list[dict]:
    if not JOURNAL_DIR.exists():
        return []
    days = [json.loads(p.read_text()) for p in sorted(JOURNAL_DIR.glob("*.json"))]
    return days


def track_record() -> dict:
    """Aggregate stats across all journaled days — the go/no-go scoreboard."""
    days = load_days()
    n = len(days)
    if n == 0:
        return {"days": 0, "net_pnl": 0.0, "win_days": 0, "win_day_rate": 0.0,
                "avg_daily_pnl": 0.0, "best_day": 0.0, "worst_day": 0.0,
                "max_drawdown": 0.0, "total_trades": 0}

    pnls = [d["net_pnl"] for d in days]
    total = sum(pnls)
    win_days = sum(1 for p in pnls if p > 0)

    # Max drawdown of the cumulative daily-P&L curve.
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    return {
        "days": n,
        "net_pnl": round(total, 2),
        "win_days": win_days,
        "win_day_rate": round(100.0 * win_days / n, 1),
        "avg_daily_pnl": round(total / n, 2),
        "best_day": round(max(pnls), 2),
        "worst_day": round(min(pnls), 2),
        "max_drawdown": round(max_dd, 2),
        "total_trades": sum(d["num_trades"] for d in days),
    }
