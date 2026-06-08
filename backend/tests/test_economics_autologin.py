from datetime import date

from app.config import Settings


# --- economics --------------------------------------------------------------
def test_monthly_cost_report(tmp_path, monkeypatch):
    import app.economics as economics
    import app.journal as journal

    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")

    from app.execution.paper import PaperBroker
    from app.strategies.orb import ORBStrategy
    from app.trading.session import TradingSession
    from tests.test_backtest_orb import _make_long_target_day
    from tests.test_session import _bars_from_df, _feed

    sess = TradingSession(ORBStrategy(), broker=PaperBroker(), settings=Settings(capital=100_000))
    _feed(sess, _bars_from_df(_make_long_target_day(), "TEST"))
    journal.save_session_day(sess, day=date(2026, 6, 1))

    rep = economics.monthly_cost_report("2026-06")
    assert rep["num_trades"] == 1
    assert rep["trading_costs"] > 0
    assert rep["infra_cost"] == 500.0
    # gross = net + trading costs, and break-even = trading costs + infra.
    assert round(rep["gross_pnl"], 2) == round(rep["net_pnl"] + rep["trading_costs"], 2)
    assert rep["breakeven_gross"] == round(rep["trading_costs"] + rep["infra_cost"], 2)


def test_cost_report_empty_month():
    import app.economics as economics

    rep = economics.monthly_cost_report("1999-01")
    assert rep["num_trades"] == 0
    assert rep["breakeven_gross"] == rep["infra_cost"]


# --- auto-login gating + TOTP ----------------------------------------------
def test_auto_login_disabled_without_full_creds():
    assert Settings().auto_login_enabled is False
    assert Settings(upstox_mobile="9999999999").auto_login_enabled is False
    full = Settings(upstox_mobile="9999999999", upstox_pin="123456", upstox_totp_secret="JBSWY3DPEHPK3PXP")
    assert full.auto_login_enabled is True


def test_auto_login_noops_when_disabled():
    from app.auth.autologin import auto_login

    assert auto_login(Settings()) is False  # not configured -> no browser, returns False


def test_totp_now_is_six_digits():
    from app.auth.autologin import totp_now

    code = totp_now("JBSWY3DPEHPK3PXP")
    assert len(code) == 6 and code.isdigit()
