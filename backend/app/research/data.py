"""Load cached history for the AI backtester to run user strategies against.

Reuses the same parquet cache the validation scripts use, so once history has
been fetched the product works fully offline.
"""
from __future__ import annotations

import pandas as pd

from app.config import Settings, get_settings
from app.data.historical import load_cached
from app.data.instruments import active_symbols, resolve_instrument_keys


def load_universe(settings: Settings | None = None, interval: str = "day") -> dict[str, pd.DataFrame]:
    """Cached candles for the active universe, keyed by symbol (empties dropped)."""
    settings = settings or get_settings()
    data: dict[str, pd.DataFrame] = {}
    for sym, key in resolve_instrument_keys(active_symbols(settings)).items():
        df = load_cached(key, interval=interval)
        if not df.empty:
            data[sym] = df
    return data
