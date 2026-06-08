"""Execution layer: pick paper vs live based on TRADING_MODE."""
from __future__ import annotations

from app.backtest.costs import CostConfig
from app.config import Settings, get_settings
from app.execution.base import Broker
from app.execution.paper import PaperBroker


def get_broker(settings: Settings | None = None, cost: CostConfig | None = None) -> Broker:
    """Return the broker for the configured mode. `live` requires Upstox creds;
    anything else (paper/backtest) uses the simulator."""
    s = settings or get_settings()
    if s.is_live:
        from app.execution.live import UpstoxBroker  # imported lazily (needs creds)

        return UpstoxBroker(cost)
    return PaperBroker(cost)
