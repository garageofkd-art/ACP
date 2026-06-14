"""The /api/backtest endpoint: English idea -> spec -> backtest -> honest verdict."""
from datetime import datetime, timedelta

import pandas as pd
from fastapi.testclient import TestClient

import app.api.main as main
from app.api.main import app

client = TestClient(app)


def _daily(prices):
    start = datetime(2024, 1, 1)
    return pd.DataFrame([
        {"ts": start + timedelta(days=i), "open": p, "high": p, "low": p, "close": p, "volume": 100000}
        for i, p in enumerate(prices)
    ])


def test_backtester_page_served():
    r = client.get("/backtester")
    assert r.status_code == 200
    assert "Honest Backtester" in r.text


def test_empty_description_rejected():
    assert client.post("/api/backtest", json={"description": "  "}).status_code == 400


def test_unparseable_idea_returns_422():
    r = client.post("/api/backtest", json={"description": "make me rich somehow"})
    assert r.status_code == 422


def test_full_flow_returns_spec_verdict_and_explanation(monkeypatch):
    # Synthetic ramp-then-pullback so the breakout rule actually trades.
    prices = [100.0] * 12 + list(range(100, 140)) + [130, 120, 110]
    monkeypatch.setattr(main, "load_universe", lambda settings: {"X": _daily(prices), "Y": _daily(prices)})

    r = client.post("/api/backtest", json={
        "description": "Buy when the close breaks above the 20-day high, "
                       "exit when it falls below the 10-day low."})
    assert r.status_code == 200
    body = r.json()
    assert body["spec"]["entry"][0]["other_indicator"] == "ndayhigh"
    assert body["result"]["verdict"] in {"PROMISING", "NO EDGE", "INSUFFICIENT DATA"}
    assert isinstance(body["explanation"], str) and body["explanation"]
    assert body["symbols_tested"] == 2


def test_no_cached_data_returns_503(monkeypatch):
    monkeypatch.setattr(main, "load_universe", lambda settings: {})
    r = client.post("/api/backtest", json={
        "description": "Buy when close breaks above the 20-day high"})
    assert r.status_code == 503
