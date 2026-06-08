"""Live broker: places real intraday (MIS) market orders on Upstox and reports
the realized fill.

Inert until valid Upstox credentials are present — it's only constructed when
TRADING_MODE=live. Instrument keys are resolved lazily so importing/constructing
this class stays offline-safe.

Upstox API v2 endpoints used:
  POST /order/place          place an order
  GET  /order/details        order status + average fill price
"""
from __future__ import annotations

import time as _time
from datetime import datetime

from app.backtest.costs import CostConfig, charges
from app.core.events import Fill, Side
from app.execution.base import Broker

_POLL_TRIES = 10
_POLL_DELAY_S = 0.3
_FILLED_STATES = {"complete", "filled"}


class UpstoxBroker(Broker):
    mode = "live"

    def __init__(self, cost: CostConfig | None = None):
        self.cost = cost or CostConfig()
        self._keys: dict[str, str] | None = None  # resolved on first use

    def _key(self, symbol: str) -> str:
        if self._keys is None:
            from app.data.instruments import resolve_instrument_keys

            self._keys = resolve_instrument_keys()
        return self._keys[symbol]

    def execute(self, symbol, side: Side, qty, ref_price, ts: datetime, tag="") -> Fill:
        from app.data.upstox_client import client

        body = {
            "quantity": qty,
            "product": "I",            # I = intraday (MIS)
            "validity": "DAY",
            "price": 0,
            "instrument_token": self._key(symbol),
            "order_type": "MARKET",
            "transaction_type": side.value,  # BUY / SELL
            "disclosed_quantity": 0,
            "trigger_price": 0,
            "is_amo": False,
            "tag": tag[:20],
        }
        with client() as http:
            resp = http.post("/order/place", json=body)
            resp.raise_for_status()
            order_id = resp.json()["data"]["order_id"]
            fill_price, filled_qty = self._poll_fill(http, order_id, ref_price, qty)

        cost = charges(side, filled_qty, fill_price, self.cost)
        return Fill(symbol, ts, side, filled_qty, fill_price, cost, tag)

    def _poll_fill(self, http, order_id: str, ref_price: float, qty: int) -> tuple[float, int]:
        """Poll order status until filled. Falls back to the reference price if
        the average price isn't reported in time (rare for liquid market orders)."""
        for _ in range(_POLL_TRIES):
            resp = http.get("/order/details", params={"order_id": order_id})
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                status = str(data.get("status", "")).lower()
                avg = float(data.get("average_price") or 0)
                filled = int(data.get("filled_quantity") or 0)
                if status in _FILLED_STATES and avg > 0:
                    return avg, filled or qty
            _time.sleep(_POLL_DELAY_S)
        return ref_price, qty
