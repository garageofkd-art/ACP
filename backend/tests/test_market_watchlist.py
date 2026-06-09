"""Live market watchlist: runner tracks tick-rate prices + day-open per symbol."""
from datetime import datetime

from app.config import Settings
from app.core.events import Tick
from app.execution.paper import PaperBroker
from app.strategies.orb import ORBStrategy
from app.trading.runner import LiveRunner
from app.trading.session import TradingSession


def _runner():
    session = TradingSession(ORBStrategy(), broker=PaperBroker(), settings=Settings(capital=100_000))
    return LiveRunner(session)


def test_market_tracks_price_and_change():
    r = _runner()
    day = datetime(2026, 6, 1, 9, 15)
    r._on_tick(Tick("RELIANCE", day, 2850.0))
    r._on_tick(Tick("RELIANCE", day.replace(minute=30), 2880.0))  # +30 from open

    market = {m["symbol"]: m for m in r.snapshot()["market"]}
    assert market["RELIANCE"]["ltp"] == 2880.0
    assert market["RELIANCE"]["change"] == 30.0
    assert round(market["RELIANCE"]["change_pct"], 2) == 1.05


def test_market_sorted_by_movers():
    r = _runner()
    day = datetime(2026, 6, 1, 9, 15)
    r._on_tick(Tick("A", day, 100.0))
    r._on_tick(Tick("A", day.replace(minute=20), 102.0))   # +2%
    r._on_tick(Tick("B", day, 100.0))
    r._on_tick(Tick("B", day.replace(minute=20), 99.0))    # -1%

    syms = [m["symbol"] for m in r.snapshot()["market"]]
    assert syms.index("A") < syms.index("B")  # bigger gainer first


def test_day_open_resets_next_day():
    r = _runner()
    r._on_tick(Tick("X", datetime(2026, 6, 1, 9, 15), 100.0))
    r._on_tick(Tick("X", datetime(2026, 6, 2, 9, 15), 110.0))  # new day -> new open
    market = {m["symbol"]: m for m in r.snapshot()["market"]}
    assert market["X"]["change"] == 0.0  # open == ltp on the new day
