"""The trading universe and symbol -> Upstox instrument_key resolution.

Upstox identifies instruments by a key like `NSE_EQ|INE002A01018` (ISIN-based),
not by trading symbol. Rather than hard-code ISINs (which drift), we resolve
symbols against Upstox's public instruments master and cache the result. The
ISINs below are only a convenience fallback and are verified against the master
on resolve.
"""
from __future__ import annotations

import gzip
import io
import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import CACHE_DIR

# Public instruments master (no auth needed).
UPSTOX_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
_MASTER_CACHE = CACHE_DIR / "instruments_master.json"


@dataclass(frozen=True, slots=True)
class Instrument:
    symbol: str          # NSE trading symbol, e.g. "RELIANCE"
    name: str            # display name
    isin_fallback: str   # used only if master lookup fails
    low_priority: bool = False  # skip when risk-sizing can't justify a position


# --- The basket -------------------------------------------------------------
# User picks: HDFCBANK (was "HDFC"), TCS, MRF. Plus liquid large-caps that
# size sanely on a 1L intraday book. MRF is flagged low_priority because one
# share (~1.4L) exceeds the whole capital, so it rarely yields a valid lot.
UNIVERSE: list[Instrument] = [
    Instrument("HDFCBANK", "HDFC Bank", "INE040A01034"),
    Instrument("TCS", "Tata Consultancy Services", "INE467B01029"),
    Instrument("RELIANCE", "Reliance Industries", "INE002A01018"),
    Instrument("ICICIBANK", "ICICI Bank", "INE090A01021"),
    Instrument("INFY", "Infosys", "INE009A01021"),
    Instrument("SBIN", "State Bank of India", "INE062A01020"),
    Instrument("AXISBANK", "Axis Bank", "INE238A01034"),
    Instrument("MRF", "MRF", "INE883A01011", low_priority=True),
]

UNIVERSE_BY_SYMBOL: dict[str, Instrument] = {i.symbol: i for i in UNIVERSE}


def _load_master(force_refresh: bool = False) -> list[dict]:
    """Download (and cache) the Upstox instruments master."""
    if _MASTER_CACHE.exists() and not force_refresh:
        return json.loads(_MASTER_CACHE.read_text())

    resp = httpx.get(UPSTOX_INSTRUMENTS_URL, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    raw = gzip.GzipFile(fileobj=io.BytesIO(resp.content)).read()
    data = json.loads(raw)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _MASTER_CACHE.write_text(json.dumps(data))
    return data


def resolve_instrument_keys(
    symbols: list[str] | None = None, force_refresh: bool = False
) -> dict[str, str]:
    """Map NSE equity trading symbols to Upstox instrument_keys.

    Returns {symbol: instrument_key}. Falls back to the ISIN-derived key if a
    symbol isn't found in the master (and warns via a missing entry otherwise).
    """
    symbols = symbols or [i.symbol for i in UNIVERSE]
    wanted = set(symbols)
    out: dict[str, str] = {}

    try:
        master = _load_master(force_refresh=force_refresh)
        for row in master:
            # NSE cash equities in the master: segment "NSE_EQ", instrument EQ.
            if row.get("segment") != "NSE_EQ" or row.get("instrument_type") != "EQ":
                continue
            sym = row.get("trading_symbol") or row.get("tradingsymbol")
            if sym in wanted:
                out[sym] = row["instrument_key"]
    except Exception:
        # Network/parse failure: fall back to ISIN-derived keys below.
        pass

    for sym in symbols:
        if sym not in out:
            inst = UNIVERSE_BY_SYMBOL.get(sym)
            if inst and inst.isin_fallback:
                out[sym] = f"NSE_EQ|{inst.isin_fallback}"
    return out
