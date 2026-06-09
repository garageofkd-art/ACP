"""Manual paper test-trade smoke check."""
import pytest

from app.config import Settings
from app.execution.paper import PaperBroker
from app.strategies.orb import ORBStrategy
from app.trading.session import TradingSession


def _session():
    return TradingSession(ORBStrategy(), broker=PaperBroker(), settings=Settings(capital=100_000))


def test_place_test_trade_opens_position():
    s = _session()
    s._last_price = {"RELIANCE": 2850.0}
    res = s.place_test_trade()
    assert res["symbol"] == "RELIANCE"
    assert res["qty"] >= 1
    assert "RELIANCE" in s.pf.positions


def test_test_trade_needs_live_price():
    s = _session()
    with pytest.raises(ValueError):
        s.place_test_trade()  # no _last_price yet


def test_test_trade_blocked_when_already_holding():
    s = _session()
    s._last_price = {"RELIANCE": 2850.0}
    s.place_test_trade()
    with pytest.raises(ValueError):
        s.place_test_trade("RELIANCE")
