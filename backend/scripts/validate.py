"""Edge validation report.

Runs on cached history (fetch it first with `scripts.fetch_history`, which needs
an Upstox token) and answers the only question that matters before going live:
does ORB show a real, out-of-sample edge after costs?

  python -m scripts.validate

Prints: baseline backtest, parameter grid, walk-forward (train vs test), and a
blunt go/no-go read.
"""
from __future__ import annotations

from app.backtest.engine import BacktestEngine
from app.backtest.metrics import per_symbol
from app.backtest.optimizer import optimize, walk_forward
from app.data.historical import load_cached
from app.data.instruments import resolve_instrument_keys
from app.strategies.orb import ORBStrategy


def _load() -> dict:
    data = {}
    for sym, key in resolve_instrument_keys().items():
        df = load_cached(key)
        if not df.empty:
            data[sym] = df
    return data


def _verdict(test: dict | None) -> str:
    if not test or test["num_trades"] < 20:
        return "INSUFFICIENT DATA — fetch more history / more trades before judging."
    ok = test["net_pnl"] > 0 and test["profit_factor"] >= 1.2 and test["expectancy"] > 0
    if ok:
        return "PROMISING — positive out-of-sample edge. Still validate with forward paper testing."
    return "NO EDGE YET — out-of-sample is weak. Tune/replace the strategy before risking capital."


def main() -> None:
    data = _load()
    if not data:
        print("No cached history. Run `python -m scripts.fetch_history` first (needs Upstox token).")
        return

    print(f"Universe with data: {', '.join(sorted(data))}\n")

    print("=== Baseline backtest (default params) ===")
    res = BacktestEngine(ORBStrategy()).run(data)
    print(res.summary())
    print(f"  expectancy ₹{res.stats['expectancy']:.1f}/trade | "
          f"profit factor {res.stats['profit_factor']:.2f} | sharpe {res.stats['sharpe']:.2f}")
    print("  Per-symbol:")
    for sym, m in sorted(per_symbol(res.trades).items(), key=lambda x: -x[1]["net_pnl"]):
        print(f"    {sym:<10} trades={m['trades']:<3} win%={m['win_rate']:5.1f} net=₹{m['net_pnl']:.0f}")

    print("\n=== Parameter grid (top 5 by net P&L) ===")
    table = optimize(data, objective="net_pnl")
    cols = ["opening_range_minutes", "target_r", "num_trades", "win_rate",
            "net_pnl", "profit_factor", "sharpe", "max_drawdown"]
    print(table[cols].head(5).to_string(index=False))

    print("\n=== Walk-forward (optimize on first 60% of days, test on last 40%) ===")
    wf = walk_forward(data, train_frac=0.6)
    print(f"  Best params: {wf['best_params']}")
    print(f"  Train: {wf['train_stats']}")
    print(f"  Test : {wf['test_stats']}")

    print("\n=== VERDICT ===")
    print(" ", _verdict(wf["test_stats"]))


if __name__ == "__main__":
    main()
