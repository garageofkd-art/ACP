"""Fetch and cache historical 1-minute candles for the trading universe.

Usage (from backend/, with Upstox token set in ../.env):
    python -m scripts.fetch_history --days 60

Without a token it will exit cleanly — instrument resolution still works
offline so you can verify the universe before wiring credentials.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

from app.data.historical import fetch_historical
from app.data.instruments import UNIVERSE, resolve_instrument_keys


def main() -> None:
    ap = argparse.ArgumentParser(description="Cache historical candles for the universe.")
    ap.add_argument("--days", type=int, default=60, help="Calendar days of history to fetch.")
    ap.add_argument("--interval", default="1minute", help="1minute | 30minute | day")
    args = ap.parse_args()

    to = date.today()
    frm = to - timedelta(days=args.days)

    keys = resolve_instrument_keys()
    print(f"Resolved {len(keys)} instruments:")
    for inst in UNIVERSE:
        print(f"  {inst.symbol:<10} -> {keys.get(inst.symbol, '??? UNRESOLVED')}")

    print(f"\nFetching {args.interval} candles {frm} -> {to} ...")
    for sym, key in keys.items():
        try:
            df = fetch_historical(key, frm, to, interval=args.interval)
            print(f"  {sym:<10} {len(df):>6} candles cached")
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym:<10} SKIPPED ({type(exc).__name__}: {exc})")


if __name__ == "__main__":
    main()
