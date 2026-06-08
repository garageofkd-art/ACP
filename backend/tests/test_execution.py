from datetime import datetime

from app.config import Settings
from app.execution import get_broker
from app.execution.live import UpstoxBroker
from app.execution.paper import PaperBroker
from app.core.events import Side


def test_factory_returns_paper_by_default():
    assert isinstance(get_broker(Settings(trading_mode="paper")), PaperBroker)


def test_live_is_blocked_until_ready():
    # Live requested but no track record yet -> readiness gate keeps us in paper.
    assert isinstance(get_broker(Settings(trading_mode="live")), PaperBroker)


def test_live_override_forces_live_broker():
    # Explicit override bypasses the gate (offline-safe: lazy key resolution).
    broker = get_broker(Settings(trading_mode="live", allow_live_override=True))
    assert isinstance(broker, UpstoxBroker)


def test_paper_fill_applies_slippage_and_cost():
    broker = PaperBroker()
    ts = datetime(2026, 6, 1, 9, 30)
    buy = broker.execute("TEST", Side.BUY, 100, 500.0, ts, "entry")
    assert buy.price > 500.0     # buy slips up
    assert buy.cost > 0
    sell = broker.execute("TEST", Side.SELL, 100, 500.0, ts, "exit")
    assert sell.price < 500.0    # sell slips down
