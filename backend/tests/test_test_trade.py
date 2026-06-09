"""Manual paper test-trade smoke check."""
import pytest

from app.config import Settings
from app.execution.paper import PaperBroker
from app.strategies.orb import ORBStrategy
from app.trading.session import TradingSession


def _session():
    return TradingSession(ORBStrategy(), broker=PaperBroker(), settings=Settings(capital=100_000))


def test_place_test_trade_records_completed_roundtrip():
    s = _session()
    s._last_price = {"RELIANCE": 2850.0}
    res = s.place_test_trade()
    assert res["symbol"] == "RELIANCE"
    assert res["qty"] >= 1
    # Round-trip closes immediately -> a completed trade, no lingering position.
    assert "RELIANCE" not in s.pf.positions
    assert len(s.pf.trades) == 1
    # Flat exit -> P&L is just the (negative) trading cost.
    assert res["net_pnl"] < 0
    assert res["costs"] > 0


def test_test_trade_works_after_hours_with_fallback_price():
    s = _session()  # no _last_price at all
    res = s.place_test_trade()
    assert res["symbol"] == "RELIANCE"
    assert len(s.pf.trades) == 1


def test_test_trade_blocked_when_already_holding_real_position():
    from datetime import datetime
    from app.core.events import Side
    from app.core.portfolio import Position

    s = _session()
    s._last_price = {"RELIANCE": 2850.0}
    s.pf.open(Position("RELIANCE", Side.BUY, 10, datetime.now(), 2850.0, 2835.0, 2880.0, 50.0))
    with pytest.raises(ValueError):
        s.place_test_trade("RELIANCE")
