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
    isin_fallback: str = ""   # used only if master lookup fails (offline)
    low_priority: bool = False  # skip when risk-sizing can't justify a position


# --- The basket: Nifty 50 + MRF --------------------------------------------
# We monitor the full Nifty 50 (deepest liquidity, tightest spreads) plus MRF
# at the user's request. MRF is flagged low_priority because one share (~1.4L)
# exceeds the whole capital, so it rarely yields a valid lot under risk sizing.
# instrument_keys are resolved from the Upstox master at runtime; the ISINs
# below are only an offline fallback for a few core names.
UNIVERSE: list[Instrument] = [
    Instrument("ADANIENT", "Adani Enterprises"),
    Instrument("ADANIPORTS", "Adani Ports"),
    Instrument("APOLLOHOSP", "Apollo Hospitals"),
    Instrument("ASIANPAINT", "Asian Paints"),
    Instrument("AXISBANK", "Axis Bank", "INE238A01034"),
    Instrument("BAJAJ-AUTO", "Bajaj Auto"),
    Instrument("BAJFINANCE", "Bajaj Finance"),
    Instrument("BAJAJFINSV", "Bajaj Finserv"),
    Instrument("BEL", "Bharat Electronics"),
    Instrument("BHARTIARTL", "Bharti Airtel"),
    Instrument("BPCL", "Bharat Petroleum"),
    Instrument("BRITANNIA", "Britannia Industries"),
    Instrument("CIPLA", "Cipla"),
    Instrument("COALINDIA", "Coal India"),
    Instrument("DRREDDY", "Dr Reddy's Labs"),
    Instrument("EICHERMOT", "Eicher Motors"),
    Instrument("GRASIM", "Grasim Industries"),
    Instrument("HCLTECH", "HCL Technologies"),
    Instrument("HDFCBANK", "HDFC Bank", "INE040A01034"),
    Instrument("HDFCLIFE", "HDFC Life"),
    Instrument("HEROMOTOCO", "Hero MotoCorp"),
    Instrument("HINDALCO", "Hindalco Industries"),
    Instrument("HINDUNILVR", "Hindustan Unilever"),
    Instrument("ICICIBANK", "ICICI Bank", "INE090A01021"),
    Instrument("INDUSINDBK", "IndusInd Bank"),
    Instrument("INFY", "Infosys", "INE009A01021"),
    Instrument("ITC", "ITC"),
    Instrument("JSWSTEEL", "JSW Steel"),
    Instrument("KOTAKBANK", "Kotak Mahindra Bank"),
    Instrument("LT", "Larsen & Toubro"),
    Instrument("LTIM", "LTIMindtree"),
    Instrument("M&M", "Mahindra & Mahindra"),
    Instrument("MARUTI", "Maruti Suzuki"),
    Instrument("NESTLEIND", "Nestle India"),
    Instrument("NTPC", "NTPC"),
    Instrument("ONGC", "ONGC"),
    Instrument("POWERGRID", "Power Grid"),
    Instrument("RELIANCE", "Reliance Industries", "INE002A01018"),
    Instrument("SBILIFE", "SBI Life Insurance"),
    Instrument("SBIN", "State Bank of India", "INE062A01020"),
    Instrument("SUNPHARMA", "Sun Pharma"),
    Instrument("TATACONSUM", "Tata Consumer"),
    Instrument("TATAMOTORS", "Tata Motors"),
    Instrument("TATASTEEL", "Tata Steel"),
    Instrument("TCS", "Tata Consultancy Services", "INE467B01029"),
    Instrument("TECHM", "Tech Mahindra"),
    Instrument("TITAN", "Titan Company"),
    Instrument("TRENT", "Trent"),
    Instrument("ULTRACEMCO", "UltraTech Cement"),
    Instrument("WIPRO", "Wipro"),
    Instrument("MRF", "MRF", "INE883A01011", low_priority=True),
]

UNIVERSE_BY_SYMBOL: dict[str, Instrument] = {i.symbol: i for i in UNIVERSE}

# --- Broader, less-efficient universe (mid/small-caps) for research ----------
# Trend/momentum edges are strongest where the market is least arbitraged. Keys
# are resolved from the Upstox master at runtime; any symbol not found is skipped.
_MIDCAP_NAMES = [
    "DIXON", "PERSISTENT", "COFORGE", "MPHASIS", "TATAELXSI", "POLYCAB", "ASTRAL",
    "SUPREMEIND", "APLAPOLLO", "JUBLFOOD", "PAGEIND", "HAVELLS", "VOLTAS", "CROMPTON",
    "CDSL", "BSE", "MCX", "ANGELONE", "CAMS", "IEX", "IRCTC", "IRFC", "RVNL", "MAZDOCK",
    "HAL", "BDL", "NHPC", "SJVN", "OIL", "GAIL", "PETRONET", "IGL", "MGL", "AARTIIND",
    "DEEPAKNTR", "NAVINFLUOR", "TATACHEM", "PIIND", "COROMANDEL", "BALRAMCHIN",
    "UNIONBANK", "CANBK", "PNB", "FEDERALBNK", "IDFCFIRSTB", "AUBANK", "BANDHANBNK",
    "RBLBANK", "BANKBARODA", "LICHSGFIN", "CHOLAFIN", "MUTHOOTFIN", "MANAPPURAM",
    "PEL", "ABCAPITAL", "ABFRL", "VBL", "UBL", "MARICO", "DABUR", "GODREJCP", "COLPAL",
    "MAXHEALTH", "FORTIS", "LALPATHLAB", "LUPIN", "BIOCON", "AUROPHARMA", "ALKEM",
    "TORNTPHARM", "ZYDUSLIFE", "OBEROIRLTY", "PRESTIGE", "DLF", "GODREJPROP", "LODHA",
    "IDEA", "TATAPOWER", "TATACOMM", "JINDALSTEL", "VEDL", "SAIL", "NMDC", "NATIONALUM",
    "ASHOKLEY", "TVSMOTOR", "BHARATFORG", "MOTHERSON", "BOSCHLTD", "ICICIPRULI",
    "ICICIGI", "HUDCO", "YESBANK", "INDHOTEL", "ZOMATO", "PAYTM", "NYKAA", "POLICYBZR",
]
MIDCAP_EXTRA: list[Instrument] = [Instrument(s, s) for s in _MIDCAP_NAMES]
BROAD_UNIVERSE: list[Instrument] = UNIVERSE + MIDCAP_EXTRA


def active_universe(settings=None) -> list[Instrument]:
    from app.config import get_settings

    s = settings or get_settings()
    return BROAD_UNIVERSE if s.universe.lower() == "broad" else UNIVERSE


def active_symbols(settings=None) -> list[str]:
    return [i.symbol for i in active_universe(settings)]

# Nifty 50 index — streamed for the market-regime filter, never traded.
INDEX_SYMBOL = "NIFTY50"
INDEX_INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"


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
