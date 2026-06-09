from datetime import date

from app.config import Settings


def _settings(**kw):
    base = dict(capital=100_000, enable_monthly_compounding=True,
                capital_reinvest_pct=50.0, capital_growth_target=200_000.0)
    base.update(kw)
    return Settings(**base)


def _seed_month(journal, month: str, net: float):
    journal.save_session_day  # noqa  (ensure attr exists)
    import json
    (journal.JOURNAL_DIR).mkdir(parents=True, exist_ok=True)
    rec = {"date": f"{month}-15", "mode": "paper", "num_trades": 1,
           "net_pnl": net, "halted": False,
           "trades": [{"net_pnl": net, "costs": 50.0}]}
    (journal.JOURNAL_DIR / f"{month}-15.json").write_text(json.dumps(rec))


def test_profitable_month_reinvests_half_and_banks_half(tmp_path, monkeypatch):
    import app.capital as capital
    import app.journal as journal
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(capital, "STATE_FILE", tmp_path / "capital_state.json")

    _seed_month(journal, "2026-05", 40_000)
    res = capital.process_month(_settings(), month="2026-05")
    assert res["last_reinvested"] == 20_000   # 50% reinvested
    assert res["last_withdrawn"] == 20_000     # 50% banked
    assert res["current_capital"] == 120_000
    assert capital.get_current_capital(_settings()) == 120_000


def test_losing_month_leaves_base_unchanged(tmp_path, monkeypatch):
    import app.capital as capital
    import app.journal as journal
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(capital, "STATE_FILE", tmp_path / "capital_state.json")

    _seed_month(journal, "2026-05", -15_000)
    res = capital.process_month(_settings(), month="2026-05")
    assert res["current_capital"] == 100_000   # no shrink, no growth
    assert res["last_withdrawn"] == 0


def test_reinvest_capped_at_target(tmp_path, monkeypatch):
    import app.capital as capital
    import app.journal as journal
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(capital, "STATE_FILE", tmp_path / "capital_state.json")

    # Already near the target: only the remaining room is reinvested, rest banked.
    capital._save({"current_capital": 190_000, "total_withdrawn": 0.0})
    _seed_month(journal, "2026-05", 40_000)
    res = capital.process_month(_settings(), month="2026-05")
    assert res["current_capital"] == 200_000           # capped
    assert res["last_reinvested"] == 10_000            # only the room
    assert res["last_withdrawn"] == 30_000             # the rest banked


def test_idempotent_per_month(tmp_path, monkeypatch):
    import app.capital as capital
    import app.journal as journal
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(capital, "STATE_FILE", tmp_path / "capital_state.json")

    _seed_month(journal, "2026-05", 40_000)
    capital.process_month(_settings(), month="2026-05")
    again = capital.process_month(_settings(), month="2026-05")
    assert again["skipped"] is True
    assert again["current_capital"] == 120_000         # not doubled-up
