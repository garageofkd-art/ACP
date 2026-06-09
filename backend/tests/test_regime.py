from datetime import date

from app.backtest.engine import BacktestEngine
from app.config import Settings
from app.strategies.orb import ORBStrategy
from app.strategies.regime import MarketRegime
from tests.test_backtest_orb import _make_long_target_day


def test_regime_direction():
    r = MarketRegime()
    d = date(2026, 6, 1)
    r.update(100.0, d)
    assert r.direction() == 0          # open == last
    r.update(101.0, d)
    assert r.direction() == 1          # up since open
    r.update(99.0, d)
    assert r.direction() == -1         # down since open


def test_regime_resets_each_day():
    r = MarketRegime()
    r.update(100.0, date(2026, 6, 1))
    r.update(110.0, date(2026, 6, 1))
    assert r.direction() == 1
    r.update(110.0, date(2026, 6, 2))  # new day -> this is the new open
    assert r.direction() == 0


def test_long_blocked_when_index_down():
    data = {"X": _make_long_target_day()}
    strat = ORBStrategy(regime=lambda: -1)  # index down -> block longs
    res = BacktestEngine(strat, settings=Settings(capital=100_000)).run(data)
    assert res.stats["num_trades"] == 0


def test_long_allowed_when_index_up():
    data = {"X": _make_long_target_day()}
    strat = ORBStrategy(regime=lambda: 1)   # index up -> allow longs
    res = BacktestEngine(strat, settings=Settings(capital=100_000)).run(data)
    assert res.stats["num_trades"] == 1


def test_no_regime_means_no_filter():
    data = {"X": _make_long_target_day()}
    res = BacktestEngine(ORBStrategy(), settings=Settings(capital=100_000)).run(data)
    assert res.stats["num_trades"] == 1
