"""Manual close button: close one open position on demand."""
from datetime import datetime

import pytest

from app.config import Settings
from app.core.events import Side
from app.core.portfolio import Position
from app.execution.paper import PaperBroker
from app.strategies.orb import ORBStrategy
from app.trading.session import TradingSession


def _session_with_position():
    s = TradingSession(ORBStrategy(), broker=PaperBroker(), settings=Settings(capital=100_000))
    s.pf.open(Position("RELIANCE", Side.BUY, 30, datetime.now(), 2850.0, 2835.0, 2880.0, 50.0))
    s._last_price["RELIANCE"] = 2870.0  # current price above entry -> a profit
    return s


def test_close_position_books_the_trade():
    s = _session_with_position()
    res = s.close_position("RELIANCE")
    assert res["symbol"] == "RELIANCE"
    assert "RELIANCE" not in s.pf.positions          # position closed
    assert len(s.pf.trades) == 1
    assert s.pf.trades[0].reason == "manual_close"
    assert res["net_pnl"] > 0                          # exited in profit


def test_close_unknown_position_raises():
    s = _session_with_position()
    with pytest.raises(ValueError):
        s.close_position("INFY")
