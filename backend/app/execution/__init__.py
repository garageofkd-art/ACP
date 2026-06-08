"""Execution layer: pick paper vs live based on TRADING_MODE.

Real-money trading is HARD-LOCKED behind the go-live readiness gate: even with
TRADING_MODE=live, orders stay simulated (paper) until app/readiness says the
edge is statistically proven. The only bypass is the explicit allow_live_override
flag. This is the code that guarantees we don't go live before we're ready.
"""
from __future__ import annotations

import logging

from app.backtest.costs import CostConfig
from app.config import Settings, get_settings
from app.execution.base import Broker
from app.execution.paper import PaperBroker

log = logging.getLogger("quantifywealth.execution")


def get_broker(settings: Settings | None = None, cost: CostConfig | None = None) -> Broker:
    """Return the broker for the configured mode. Live is gated by readiness."""
    s = settings or get_settings()
    if not s.is_live:
        return PaperBroker(cost)

    from app.readiness import evaluate

    report = evaluate(s)
    if report["is_ready"] or s.allow_live_override:
        from app.execution.live import UpstoxBroker  # imported lazily (needs creds)

        why = "override active" if (s.allow_live_override and not report["is_ready"]) else "readiness met"
        log.warning("LIVE trading ENABLED (%s) — placing REAL orders.", why)
        return UpstoxBroker(cost)

    failed = [k for k, ok in report["checks"].items() if not ok]
    log.warning(
        "LIVE requested but BLOCKED by readiness gate (failing: %s). "
        "Staying in PAPER. Confidence %.1f%% / target %.1f%%, trades %d.",
        ", ".join(failed), report["edge_confidence_pct"],
        report["targets"]["confidence_pct"], report["num_trades"],
    )
    return PaperBroker(cost)
