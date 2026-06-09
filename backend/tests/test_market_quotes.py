from app.api.main import app
from app.market import _parse
from fastapi.testclient import TestClient

client = TestClient(app)


def test_parse_computes_change_and_sorts_movers():
    data = {
        "NSE_EQ:RELIANCE": {"last_price": 2890.0, "net_change": 40.0},
        "NSE_EQ:INFY": {"last_price": 1480.0, "net_change": -20.0},
        "NSE_INDEX:Nifty 50": {"last_price": 24200.0, "net_change": 120.0},
    }
    rows = _parse(data)
    by = {r["symbol"]: r for r in rows}
    assert by["RELIANCE"]["change"] == 40.0
    assert round(by["RELIANCE"]["change_pct"], 2) == 1.40   # 40 / 2850
    assert by["INFY"]["change_pct"] < 0
    # Sorted by % move, biggest gainer first, loser last.
    assert rows[0]["symbol"] in {"RELIANCE", "Nifty 50"}
    assert rows[-1]["symbol"] == "INFY"


def test_parse_falls_back_to_ohlc_close():
    data = {"NSE_EQ:TCS": {"last_price": 3950.0, "ohlc": {"close": 3900.0}}}
    rows = _parse(data)
    assert rows[0]["change"] == 50.0


def test_market_endpoint_without_token():
    # No token in test env and session idle -> graceful 'connect' note, no crash.
    body = client.get("/api/market").json()
    assert body["source"] == "none"
    assert body["rows"] == []
