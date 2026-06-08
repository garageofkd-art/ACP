"""Paper TradingSession: profit parity with backtest + kill-switch behaviour."""
from datetime import datetime, timedelta

import pandas as pd

from app.config import Settings
from app.core.events import Bar
from app.execution.paper import PaperBroker
from app.strategies.orb import ORBStrategy
from app.trading.session import TradingSession
from tests.test_backtest_orb import _bar, _make_long_target_day


def _bars_from_df(df: pd.DataFrame, symbol: str) -> list[Bar]:
    return [
        Bar(symbol, r.ts, r.open, r.high, r.low, r.close, int(r.volume))
        for r in df.itertuples(index=False)
    ]


def _feed(session: TradingSession, bars: list[Bar]) -> None:
    for b in sorted(bars, key=lambda x: x.ts):
        session.on_bar(b)


def test_session_profits_like_backtest():
    session = TradingSession(
        ORBStrategy(), broker=PaperBroker(), settings=Settings(capital=100_000)
    )
    _feed(session, _bars_from_df(_make_long_target_day(), "TEST"))

    assert session.snapshot()["num_trades"] == 1
    trade = session.pf.trades[0]
    assert trade.reason == "target"
    assert trade.net_pnl > 0
    assert not session.halted


def _stop_out_day(symbol_start_close: float = 101.2) -> pd.DataFrame:
    """Range 100-101, breakout up, then collapse through the stop (100)."""
    rows = []
    start = datetime(2026, 6, 1, 9, 15)
    for i in range(15):  # opening range
        rows.append(_bar(start + timedelta(minutes=i), 100.5, 101.0, 100.0, 100.5))
    rows.append(_bar(start + timedelta(minutes=15), 100.8, 101.3, 100.7, symbol_start_close))
    # Next bar slams down below the stop.
    rows.append(_bar(start + timedelta(minutes=16), 100.5, 100.6, 99.0, 99.2))
    for i in range(17, 40):
        rows.append(_bar(start + timedelta(minutes=i), 99.0, 99.2, 98.8, 99.0))
    return pd.DataFrame(rows)


def test_kill_switch_halts_after_daily_loss():
    # Tiny daily-loss cap so a single stop-out trips the kill switch.
    settings = Settings(capital=100_000, risk_per_trade_pct=1.0, max_daily_loss_pct=0.5)
    session = TradingSession(ORBStrategy(), broker=PaperBroker(), settings=settings)
    _feed(session, _bars_from_df(_stop_out_day(), "TEST"))

    assert session.pf.trades[0].reason == "stop"
    assert session.pf.trades[0].net_pnl < 0
    assert session.halted is True
    # Once halted, no further entries are allowed.
    assert not session.risk.can_enter(datetime(2026, 6, 1).date(), 0)
