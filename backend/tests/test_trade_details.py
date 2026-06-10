"""The trades endpoint exposes the full per-trade breakdown for the detail view."""
from datetime import datetime

from fastapi.testclient import TestClient

from app.api.main import STATE, app
from app.core.events import Side
from app.core.portfolio import Trade

client = TestClient(app)


def test_trades_endpoint_includes_full_breakdown():
    trade = Trade(
        symbol="RELIANCE", side=Side.BUY, qty=35,
        entry_ts=datetime(2026, 6, 10, 9, 32), entry_price=2850.0,
        exit_ts=datetime(2026, 6, 10, 11, 5), exit_price=2890.0,
        gross_pnl=1400.0, costs=80.0, net_pnl=1320.0, reason="ORB long breakout",
    )
    STATE.session.pf.trades.append(trade)
    try:
        rows = client.get("/api/trades").json()
        row = next(r for r in rows if r["symbol"] == "RELIANCE")
        for key in ("entry_ts", "entry_price", "exit_ts", "exit_price",
                    "gross_pnl", "costs", "net_pnl", "reason", "side", "qty"):
            assert key in row
        assert row["gross_pnl"] == 1400.0
        assert row["costs"] == 80.0
        assert row["net_pnl"] == 1320.0
        assert row["reason"] == "ORB long breakout"
    finally:
        STATE.session.pf.trades.remove(trade)
