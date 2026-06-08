from datetime import date, datetime

from app.market_calendar import IST, is_market_open, is_trading_day


def test_weekend_is_not_trading_day():
    assert not is_trading_day(date(2026, 6, 6))   # Saturday
    assert not is_trading_day(date(2026, 6, 7))   # Sunday


def test_weekday_is_trading_day():
    assert is_trading_day(date(2026, 6, 8))       # Monday (not a holiday)


def test_known_holiday_is_closed():
    assert not is_trading_day(date(2026, 1, 26))  # Republic Day


def test_market_open_window():
    monday = date(2026, 6, 8)
    assert is_market_open(datetime(2026, 6, 8, 10, 0, tzinfo=IST))
    assert not is_market_open(datetime(2026, 6, 8, 8, 0, tzinfo=IST))   # pre-open
    assert not is_market_open(datetime(2026, 6, 8, 16, 0, tzinfo=IST))  # post-close
    assert is_trading_day(monday)


def test_journal_save_and_track_record(tmp_path, monkeypatch):
    import app.journal as journal

    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")

    # A profitable paper day and a losing one.
    from app.config import Settings
    from app.execution.paper import PaperBroker
    from app.strategies.orb import ORBStrategy
    from app.trading.session import TradingSession
    from tests.test_session import _bars_from_df, _feed, _stop_out_day
    from tests.test_backtest_orb import _make_long_target_day

    win = TradingSession(ORBStrategy(), broker=PaperBroker(), settings=Settings(capital=100_000))
    _feed(win, _bars_from_df(_make_long_target_day(), "TEST"))
    journal.save_session_day(win, day=date(2026, 6, 1))

    loss = TradingSession(ORBStrategy(), broker=PaperBroker(),
                          settings=Settings(capital=100_000, max_daily_loss_pct=0.5))
    _feed(loss, _bars_from_df(_stop_out_day(), "TEST"))
    journal.save_session_day(loss, day=date(2026, 6, 2))

    tr = journal.track_record()
    assert tr["days"] == 2
    assert tr["win_days"] == 1
    assert tr["total_trades"] == 2
    assert tr["best_day"] > 0 > tr["worst_day"]
