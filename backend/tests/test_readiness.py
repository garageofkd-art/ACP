from app.config import Settings
from app.readiness import edge_confidence_pct, evaluate, profit_factor


def test_confidence_high_for_consistent_winners():
    pnls = [90, 100, 110, 95, 105] * 8  # 40 small, consistent wins
    assert edge_confidence_pct(pnls) >= 95


def test_confidence_near_coinflip_for_zero_mean():
    pnls = [100, -100] * 20  # mean ~0
    assert 40 <= edge_confidence_pct(pnls) <= 60


def test_profit_factor_basics():
    assert profit_factor([100, -50]) == 2.0
    assert profit_factor([100, 100]) == float("inf")
    assert profit_factor([]) == 0.0


def _fake_days(per_trade, n_days):
    return [
        {"date": f"2026-06-{d+1:02d}", "net_pnl": per_trade,
         "trades": [{"net_pnl": per_trade, "costs": 5.0}]}
        for d in range(n_days)
    ]


def test_not_ready_with_too_few_trades(monkeypatch):
    import app.journal as journal
    monkeypatch.setattr(journal, "load_days", lambda: _fake_days(100, 5))
    r = evaluate(Settings(capital=100_000))
    assert r["is_ready"] is False
    assert r["checks"]["enough_trades"] is False


def test_ready_when_proven(monkeypatch):
    import app.journal as journal
    # 40 days of consistent small wins -> high confidence, PF=inf, no drawdown.
    monkeypatch.setattr(journal, "load_days", lambda: _fake_days(100, 40))
    r = evaluate(Settings(capital=100_000))
    assert r["num_trades"] == 40
    assert r["edge_confidence_pct"] >= 95
    assert r["is_ready"] is True
