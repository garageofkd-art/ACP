"""Monthly capital compounding.

At each month-end, take the month's realized profit and:
  • reinvest `capital_reinvest_pct` of it into the capital base (bigger base ->
    bigger position sizes -> compounding), up to `capital_growth_target`;
  • bank the rest (tracked as total_withdrawn).

The base only ever GROWS on profitable months — a losing month leaves it
unchanged (we never compound a bigger base onto a loss). State persists in
data/capital_state.json. Sizing reads the current base at session start.

⚠️ In paper mode this simulates the growth curve; real withdrawals only mean
something live. And like all compounding, it should only run once the edge is
proven — growing the base on a losing strategy just scales the damage.
"""
from __future__ import annotations

import json
from datetime import date

from app import journal
from app.config import DATA_DIR, Settings, get_settings

STATE_FILE = DATA_DIR / "capital_state.json"


def _load() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def _save(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_current_capital(settings: Settings | None = None) -> float:
    s = settings or get_settings()
    return float(_load().get("current_capital", s.capital))


def get_total_withdrawn(settings: Settings | None = None) -> float:
    return float(_load().get("total_withdrawn", 0.0))


def _prev_month(today: date | None = None) -> str:
    today = today or date.today()
    y, m = today.year, today.month
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _month_profit(month: str) -> float:
    return round(sum(d["net_pnl"] for d in journal.load_days() if d["date"].startswith(month)), 2)


def process_month(settings: Settings | None = None, month: str | None = None) -> dict:
    """Apply the compounding step for `month` (default: the previous month).
    Idempotent — re-running for an already-processed month is a no-op."""
    s = settings or get_settings()
    month = month or _prev_month()
    st = _load()
    base = float(st.get("current_capital", s.capital))
    withdrawn_total = float(st.get("total_withdrawn", 0.0))

    if not s.enable_monthly_compounding or st.get("last_month") == month:
        return {"current_capital": base, "total_withdrawn": withdrawn_total,
                "last_month": st.get("last_month"), "skipped": True}

    profit = _month_profit(month)
    reinvested = withdrawn = 0.0
    if profit > 0:
        if base < s.capital_growth_target:
            room = s.capital_growth_target - base
            reinvested = min(profit * s.capital_reinvest_pct / 100.0, room)
            base += reinvested
        withdrawn = profit - reinvested  # the rest (incl. overflow above target) is banked
        withdrawn_total += withdrawn

    st = {
        "current_capital": round(base, 2),
        "total_withdrawn": round(withdrawn_total, 2),
        "last_month": month,
        "last_profit": profit,
        "last_reinvested": round(reinvested, 2),
        "last_withdrawn": round(withdrawn, 2),
    }
    _save(st)
    return st
