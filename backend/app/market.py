"""Market quotes for the watchlist.

Provides last-traded / last-close prices so the dashboard market screen shows
data even when the live feed isn't running (after hours, before Start). Uses the
Upstox market-quote API, which returns the latest session's price + change, and
caches briefly to avoid hammering the endpoint.

Docs: https://upstox.com/developer/api-documentation/get-full-market-quote
"""
from __future__ import annotations

import time as _time

_CACHE: dict = {"ts": 0.0, "rows": []}
_TTL = 30.0  # seconds


def _parse(data: dict) -> list[dict]:
    """Turn an Upstox quotes payload into watchlist rows (movers first).

    Response keys look like 'NSE_EQ:RELIANCE'; each value has last_price and
    net_change (change vs previous close).
    """
    rows = []
    for resp_key, q in (data or {}).items():
        if not isinstance(q, dict):
            continue
        ltp = q.get("last_price")
        if ltp is None:
            continue
        net = q.get("net_change")
        if net is None:
            ohlc = q.get("ohlc") or {}
            net = ltp - (ohlc.get("close") or ltp)
        prev = ltp - net
        pct = (net / prev * 100) if prev else 0.0
        rows.append({
            "symbol": resp_key.split(":", 1)[-1],
            "ltp": round(ltp, 2),
            "change": round(net, 2),
            "change_pct": round(pct, 2),
            "close": round(prev, 2),
        })
    rows.sort(key=lambda r: r["change_pct"], reverse=True)
    return rows


def fetch_quotes(force: bool = False) -> list[dict]:
    """Last-close/last-traded quotes for the whole universe + index (cached)."""
    now = _time.time()
    if not force and _CACHE["rows"] and now - _CACHE["ts"] < _TTL:
        return _CACHE["rows"]

    from app.data.instruments import INDEX_INSTRUMENT_KEY, INDEX_SYMBOL, resolve_instrument_keys
    from app.data.upstox_client import client

    keys = resolve_instrument_keys()
    keys[INDEX_SYMBOL] = INDEX_INSTRUMENT_KEY
    with client() as http:
        resp = http.get("/market-quote/quotes", params={"instrument_key": ",".join(keys.values())})
        resp.raise_for_status()
        data = resp.json().get("data", {})

    rows = _parse(data)
    _CACHE.update(ts=now, rows=rows)
    return rows
