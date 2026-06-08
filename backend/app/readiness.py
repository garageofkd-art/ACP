"""Go-live readiness — the hard gate that decides when (if ever) we trade real money.

The headline number is **edge confidence**: the statistical probability that the
strategy's average per-trade P&L is genuinely positive and not luck. It's a
one-sided t-test on realized trade P&L, expressed as a percentage. "95% success"
means this confidence reaches 95% — NOT a 95% win rate (which would be a red flag).

`evaluate()` also enforces guardrails (sample size, profit factor, drawdown).
Real-money trading stays locked until every check passes — see app/execution.
"""
from __future__ import annotations

import math

from app import journal
from app.config import Settings, get_settings


def _all_trade_pnls() -> list[float]:
    return [t["net_pnl"] for d in journal.load_days() for t in d.get("trades", [])]


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def edge_confidence_pct(pnls: list[float]) -> float:
    """One-sided confidence (%) that mean per-trade P&L > 0.

    Uses a normal approximation to the t-statistic; with small samples this is
    slightly optimistic, which is why we also require a minimum trade count.
    """
    n = len(pnls)
    if n < 2:
        return 0.0
    mean = sum(pnls) / n
    var = sum((p - mean) ** 2 for p in pnls) / (n - 1)
    std = math.sqrt(var)
    if std == 0:
        return 100.0 if mean > 0 else 0.0
    t = mean / (std / math.sqrt(n))
    return round(100 * _normal_cdf(t), 1)


def profit_factor(pnls: list[float]) -> float:
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = sum(p for p in pnls if p < 0)
    if gross_loss < 0:
        return gross_win / abs(gross_loss)
    return float("inf") if gross_win > 0 else 0.0


def evaluate(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    pnls = _all_trade_pnls()
    n = len(pnls)
    net = round(sum(pnls), 2)
    pf = profit_factor(pnls)
    confidence = edge_confidence_pct(pnls)

    max_dd = journal.track_record()["max_drawdown"]
    dd_limit = -(s.max_drawdown_pct_for_live / 100.0) * s.capital

    checks = {
        "enough_trades": n >= s.min_trades_for_live,
        "net_positive": net > 0,
        "profit_factor": pf >= s.min_profit_factor,
        "edge_confidence": confidence >= s.target_confidence_pct,
        "drawdown_within_limit": max_dd >= dd_limit,
    }
    return {
        "is_ready": all(checks.values()),
        "checks": checks,
        "num_trades": n,
        "net_pnl": net,
        "profit_factor": round(pf, 2) if pf != float("inf") else None,
        "edge_confidence_pct": confidence,
        "max_drawdown": max_dd,
        "drawdown_limit": round(dd_limit, 2),
        "targets": {
            "confidence_pct": s.target_confidence_pct,
            "min_trades": s.min_trades_for_live,
            "min_profit_factor": s.min_profit_factor,
            "max_drawdown_pct": s.max_drawdown_pct_for_live,
        },
        "override_active": s.allow_live_override,
    }
