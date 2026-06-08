"""Paper broker: simulates fills using the same cost + slippage model as the
backtest, so paper results are directly comparable to backtest expectations."""
from __future__ import annotations

from datetime import datetime

from app.backtest.costs import CostConfig, apply_slippage, charges
from app.core.events import Fill, Side
from app.execution.base import Broker


class PaperBroker(Broker):
    mode = "paper"

    def __init__(self, cost: CostConfig | None = None):
        self.cost = cost or CostConfig()

    def execute(self, symbol, side: Side, qty, ref_price, ts: datetime, tag="") -> Fill:
        fill_price = apply_slippage(ref_price, side, self.cost)
        cost = charges(side, qty, fill_price, self.cost)
        return Fill(symbol, ts, side, qty, fill_price, cost, tag)
