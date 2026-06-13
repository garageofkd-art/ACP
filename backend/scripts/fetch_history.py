"""Fetch and cache historical candles for the universe + the Nifty index.

Usage (from backend/, with Upstox token set in ../.env):
    python -m scripts.fetch_history --days 180

Fetches in ~28-day chunks (Upstox limits the per-request range for intraday
intervals); each chunk is cached separately and stitched back together by
`load_cached`. The index is fetched too so the regime filter can be validated.

Without a token it exits cleanly after printing the resolved universe.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

from app.data.historical import fetch_historical
from app.data.instruments import INDEX_INSTRUMENT_KEY, INDEX_SYMBOL, resolve_instrument_keys

CHUNK_DAYS = 28


def _fetch_all(key: str, days: int, interval: str) -> int:
    """Fetch `days` of history for one instrument in chunks; return candle count."""
    # Daily/weekly/monthly candles allow long ranges per request — no chunking.
    if interval in ("day", "week", "month"):
        try:
            return len(fetch_historical(key, date.today() - timedelta(days=days), date.today(),
                                        interval=interval))
        except Exception as exc:  # noqa: BLE001
            print(f"      skipped ({type(exc).__name__})")
            return 0

    total = 0
    chunk_end = date.today()
    remaining = days
    while remaining > 0:
        span = min(CHUNK_DAYS, remaining)
        frm = chunk_end - timedelta(days=span)
        try:
            df = fetch_historical(key, frm, chunk_end, interval=interval)
            total += len(df)
        except Exception as exc:  # noqa: BLE001
            print(f"      chunk {frm}->{chunk_end} skipped ({type(exc).__name__})")
        chunk_end = frm - timedelta(days=1)
        remaining -= span
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description="Cache historical candles for the universe + index.")
    ap.add_argument("--days", type=int, default=180, help="Calendar days of history.")
    ap.add_argument("--interval", default="1minute", help="1minute | 30minute | day")
    args = ap.parse_args()

    keys = resolve_instrument_keys()
    keys[INDEX_SYMBOL] = INDEX_INSTRUMENT_KEY  # index for the regime filter
    print(f"Fetching {args.days}d of {args.interval} candles for {len(keys)} instruments…\n")

    for sym, key in keys.items():
        try:
            n = _fetch_all(key, args.days, args.interval)
            print(f"  {sym:<11} {n:>7} candles cached")
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym:<11} SKIPPED ({type(exc).__name__}: {exc})")


if __name__ == "__main__":
    main()
