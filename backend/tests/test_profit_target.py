"""Daily profit target: bank the money and stop for the day."""
from app.config import Settings
from app.execution.paper import PaperBroker
from app.strategies.orb import ORBStrategy
from app.trading.session import TradingSession
from tests.test_backtest_orb import _make_long_target_day
from tests.test_session import _bars_from_df, _feed


def test_target_hit_halts_for_the_day():
    # The synthetic day nets ~₹1,888; a ₹1,000 target trips on that win.
    settings = Settings(capital=100_000, daily_profit_target_inr=1_000)
    session = TradingSession(ORBStrategy(), broker=PaperBroker(), settings=settings)
    _feed(session, _bars_from_df(_make_long_target_day(), "TEST"))

    assert session.halted is True
    assert session.halt_reason == "profit_target"
    snap = session.snapshot()
    assert snap["daily_pnl"] >= 1_000
    # No new entries allowed once the target is banked.
    day = session.pf.trades[0].exit_ts.date()
    assert session.risk.can_enter(day, 0) is False


def test_target_not_hit_when_below_threshold():
    # Same ~₹1,888 day, but a ₹5,000 target is not reached -> keep trading.
    settings = Settings(capital=100_000, daily_profit_target_inr=5_000)
    session = TradingSession(ORBStrategy(), broker=PaperBroker(), settings=settings)
    _feed(session, _bars_from_df(_make_long_target_day(), "TEST"))
    assert session.halted is False
    assert session.halt_reason is None


def test_target_disabled_when_zero():
    settings = Settings(capital=100_000, daily_profit_target_inr=0)
    session = TradingSession(ORBStrategy(), broker=PaperBroker(), settings=settings)
    _feed(session, _bars_from_df(_make_long_target_day(), "TEST"))
    assert session.halted is False
