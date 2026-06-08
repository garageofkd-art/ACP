from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "paper"        # safe default
    assert body["authenticated"] is False  # no token in test env


def test_universe_lists_user_picks():
    symbols = {row["symbol"] for row in client.get("/api/universe").json()}
    assert {"HDFCBANK", "TCS", "MRF"} <= symbols


def test_snapshot_is_flat_idle_session():
    snap = client.get("/api/snapshot").json()
    assert snap["mode"] == "paper"
    assert snap["num_trades"] == 0
    assert snap["open_positions"] == []
    assert snap["running"] is False


def test_start_requires_token():
    r = client.post("/api/session/start")
    assert r.status_code == 400  # no Upstox token configured


def test_auth_login_returns_url():
    r = client.get("/api/auth/login")
    assert r.status_code == 200
    assert "url" in r.json()
