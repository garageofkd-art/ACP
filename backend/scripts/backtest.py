"""Run the ORB backtest + optimizer on cached history for the universe.

Usage (from backend/):
    python -m scripts.backtest            # single run with default params
    python -m scripts.backtest --optimize # grid search

Loads whatever is in the parquet cache, so it works offline once
`scripts.fetch_history` has been run (which needs an Upstox token).
"""
from __future__ import annotations

import argparse

from app.backtest.engine import BacktestEngine
from app.backtest.metrics import per_symbol
from app.backtest.optimizer import optimize
from app.data.historical import load_cached
from app.data.instruments import resolve_instrument_keys
from app.strategies.orb import ORBStrategy


def _load_universe() -> dict:
    data = {}
    for sym, key in resolve_instrument_keys().items():
        df = load_cached(key)
        if not df.empty:
            data[sym] = df
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--optimize", action="store_true", help="Run a parameter grid search.")
    args = ap.parse_args()

    data = _load_universe()
    if not data:
        print("No cached history found. Run `python -m scripts.fetch_history` first "
              "(requires an Upstox token in .env).")
        return
    print(f"Loaded cached history for: {', '.join(sorted(data))}\n")

    if args.optimize:
        table = optimize(data, objective="net_pnl")
        cols = ["opening_range_minutes", "target_r", "latest_entry",
                "num_trades", "win_rate", "net_pnl", "profit_factor", "sharpe", "max_drawdown"]
        print(table[cols].to_string(index=False))
        return

    result = BacktestEngine(ORBStrategy()).run(data)
    print(result.summary())
    print("\nPer-symbol:")
    for sym, m in sorted(per_symbol(result.trades).items(), key=lambda x: -x[1]["net_pnl"]):
        print(f"  {sym:<10} trades={m['trades']:<3} win%={m['win_rate']:5.1f} net=₹{m['net_pnl']:.0f}")


if __name__ == "__main__":
    main()
