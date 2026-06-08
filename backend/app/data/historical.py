"""Historical candle fetching with a local parquet cache.

Used to build the dataset that the backtest engine replays. Upstox returns
candles as [timestamp, open, high, low, close, volume, oi]; we normalize to a
tidy DataFrame and cache per (instrument, interval, date-range) so repeated
backtests are fast and offline.

Endpoints (Upstox API v2):
  historical: GET /historical-candle/{instrument_key}/{interval}/{to}/{from}
  intraday:   GET /historical-candle/intraday/{instrument_key}/{interval}
Valid intervals: 1minute, 30minute, day, week, month.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import quote

import pandas as pd

from app.config import CACHE_DIR
from app.data.upstox_client import client

_COLUMNS = ["ts", "open", "high", "low", "close", "volume", "oi"]


def _cache_path(instrument_key: str, interval: str, frm: str, to: str) -> "Path":  # type: ignore[name-defined]
    from pathlib import Path

    safe_key = instrument_key.replace("|", "_")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{safe_key}__{interval}__{frm}__{to}.parquet"


def _to_frame(candles: list[list]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=_COLUMNS)
    df = pd.DataFrame(candles, columns=_COLUMNS)
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.sort_values("ts").reset_index(drop=True)
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    df["volume"] = df["volume"].astype("int64")
    return df


def fetch_historical(
    instrument_key: str,
    frm: date,
    to: date,
    interval: str = "1minute",
    use_cache: bool = True,
) -> pd.DataFrame:
    """Fetch candles for [frm, to] inclusive. Cached to parquet."""
    frm_s, to_s = frm.isoformat(), to.isoformat()
    path = _cache_path(instrument_key, interval, frm_s, to_s)
    if use_cache and path.exists():
        return pd.read_parquet(path)

    enc_key = quote(instrument_key, safe="")
    with client() as http:
        resp = http.get(f"/historical-candle/{enc_key}/{interval}/{to_s}/{frm_s}")
        resp.raise_for_status()
        candles = resp.json().get("data", {}).get("candles", [])

    df = _to_frame(candles)
    if use_cache:
        df.to_parquet(path, index=False)
    return df


def fetch_intraday(instrument_key: str, interval: str = "1minute") -> pd.DataFrame:
    """Fetch *today's* candles so far (not cached — it's still forming)."""
    enc_key = quote(instrument_key, safe="")
    with client() as http:
        resp = http.get(f"/historical-candle/intraday/{enc_key}/{interval}")
        resp.raise_for_status()
        candles = resp.json().get("data", {}).get("candles", [])
    return _to_frame(candles)
