"""Validate the positional trend strategy on DAILY data with delivery costs.

  python -m scripts.validate_positional   (or: make validate-positional)

Holds overnight (intraday=False), uses the delivery cost model, and allows a
wider concurrent-position book (trend-following needs diversification). Same
honest yardstick: full-period + out-of-sample + verdict.

Fetch daily data first:  python -m scripts.fetch_history --interval day --days 1095
"""
from __future__ import annotations

from app.backtest.costs import DELIVERY_COSTS
from app.backtest.engine import BacktestEngine
from app.backtest.metrics import per_symbol
from app.backtest.optimizer import split_by_date
from app.config import get_settings
from app.data.historical import load_cached
from app.data.instruments import resolve_instrument_keys
from app.strategies.trend import TrendBreakoutStrategy

MAX_POSITIONS = 10  # trend-following wants a diversified book, not 3 names


def _load() -> dict:
    data = {}
    for sym, key in resolve_instrument_keys().items():
        df = load_cached(key, interval="day")
        if not df.empty:
            data[sym] = df
    return data


def _run(data: dict, settings):
    engine = BacktestEngine(TrendBreakoutStrategy(), settings=settings,
                            cost=DELIVERY_COSTS, intraday=False)
    return engine.run(data)


def _verdict(test: dict | None) -> str:
    if not test or test["num_trades"] < 20:
        return "INSUFFICIENT DATA — fetch more daily history / more trades to judge."
    ok = test["net_pnl"] > 0 and test["profit_factor"] >= 1.3 and test["expectancy"] > 0
    return ("PROMISING — positive out-of-sample edge after delivery costs. Confirm with forward testing."
            if ok else "NO EDGE YET — out-of-sample is weak.")


def main() -> None:
    data = _load()
    if not data:
        print("No daily data cached. Run: python -m scripts.fetch_history --interval day --days 1095")
        return

    s = get_settings().model_copy(update={"max_concurrent_positions": MAX_POSITIONS})
    print("Strategy: TrendBreakout (positional · daily bars · delivery costs · "
          f"max {MAX_POSITIONS} positions)")
    print(f"Loaded {len(data)} symbols\n")

    print("=== Full-period backtest ===")
    res = _run(data, s)
    print(res.summary())
    print(f"  expectancy ₹{res.stats['expectancy']:.1f}/trade | "
          f"profit factor {res.stats['profit_factor']:.2f} | sharpe {res.stats['sharpe']:.2f}")
    print("  Per-symbol (top 10 by net):")
    for sym, m in sorted(per_symbol(res.trades).items(), key=lambda x: -x[1]["net_pnl"])[:10]:
        print(f"    {sym:<11} trades={m['trades']:<3} win%={m['win_rate']:5.1f} net=₹{m['net_pnl']:.0f}")

    print("\n=== Out-of-sample check (train 60% / test 40%) ===")
    train, test = split_by_date(data, 0.6)
    res_tr, res_te = _run(train, s), _run(test, s)
    print(f"  Train: trades={res_tr.stats['num_trades']:<4} net=₹{res_tr.stats['net_pnl']:.0f} "
          f"PF={res_tr.stats['profit_factor']:.2f}")
    print(f"  Test : trades={res_te.stats['num_trades']:<4} net=₹{res_te.stats['net_pnl']:.0f} "
          f"PF={res_te.stats['profit_factor']:.2f} expectancy=₹{res_te.stats['expectancy']:.1f}")

    print("\n=== VERDICT ===")
    print(" ", _verdict(res_te.stats))


if __name__ == "__main__":
    main()
