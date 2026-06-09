"""Generate SYNTHETIC market data into the cache so the full backtest/validate
pipeline can be exercised offline (no Upstox token needed).

  python -m scripts.demo_data   # writes ~40 days of fake 1-min bars + index

⚠️ This is random synthetic data — any resulting verdict is meaningless. It
exists only to demonstrate/verify the plumbing (fetch -> cache -> validate),
not to evaluate the strategy. Cache files are git-ignored.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from app.config import CACHE_DIR
from app.data.instruments import INDEX_INSTRUMENT_KEY, UNIVERSE_BY_SYMBOL

MASTER = CACHE_DIR / "instruments_master.json"
BASE_PRICES = {
    "HDFCBANK": 1680, "TCS": 3900, "RELIANCE": 2850, "ICICIBANK": 1150,
    "INFY": 1500, "SBIN": 820, "AXISBANK": 1100, "MRF": 140000,
}
SEED = 7
BARS_PER_DAY = 375  # 09:15–15:30


def _gen_day(rng, base, day, n=BARS_PER_DAY) -> pd.DataFrame:
    start = datetime(day.year, day.month, day.day, 9, 15)
    drift = rng.normal(0, 0.003)
    steps = rng.normal(drift / n, 0.0009, n)
    closes = base * np.cumprod(1 + steps)
    opens = np.empty(n)
    opens[0], opens[1:] = base, closes[:-1]
    highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, 0.0004, n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, 0.0004, n)))
    vols = rng.integers(4000, 20000, n)
    ts = [start + timedelta(minutes=i) for i in range(n)]
    return pd.DataFrame({"ts": ts, "open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": vols, "oi": 0})


def _trading_days(num: int) -> list[date]:
    days, d = [], date.today() - timedelta(days=1)
    while len(days) < num:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def _write(key: str, df: pd.DataFrame, frm: str, to: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = key.replace("|", "_")
    df.to_parquet(CACHE_DIR / f"{safe}__1minute__{frm}__{to}.parquet", index=False)


def main() -> None:
    rng = np.random.default_rng(SEED)
    days = _trading_days(40)
    frm, to = days[0].isoformat(), days[-1].isoformat()

    master = []
    for sym, base in BASE_PRICES.items():
        key = f"NSE_EQ|{UNIVERSE_BY_SYMBOL[sym].isin_fallback}"
        df = pd.concat([_gen_day(rng, base, d) for d in days], ignore_index=True)
        _write(key, df, frm, to)
        master.append({"segment": "NSE_EQ", "instrument_type": "EQ",
                       "trading_symbol": sym, "instrument_key": key})

    idx = pd.concat([_gen_day(rng, 24000, d) for d in days], ignore_index=True)
    _write(INDEX_INSTRUMENT_KEY, idx, frm, to)
    MASTER.write_text(json.dumps(master))
    print(f"Wrote SYNTHETIC cache: {len(BASE_PRICES)} symbols + index, {len(days)} days ({frm}..{to}).")


if __name__ == "__main__":
    main()
