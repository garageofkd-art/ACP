"""Edge validation report — the first real read on whether ORB has an edge.

Runs on cached history (fetch it first with `scripts.fetch_history`) using the
EXACT live configuration (all ORB filters + the index-regime gate, costs, risk).
It evaluates the fixed config out-of-sample (train vs test split) so the verdict
isn't curve-fit — we're testing the strategy we'll actually run, not tuning one.

  python -m scripts.validate     (or: make validate)
"""
from __future__ import annotations

from app.backtest.engine import BacktestEngine
from app.backtest.metrics import per_symbol
from app.backtest.optimizer import split_by_date
from app.config import get_settings
from app.data.historical import load_cached
from app.data.instruments import INDEX_INSTRUMENT_KEY, INDEX_SYMBOL, resolve_instrument_keys
from app.strategies.orb import ORBStrategy
from app.strategies.regime import MarketRegime


def _load() -> dict:
    data = {}
    for sym, key in resolve_instrument_keys().items():
        df = load_cached(key)
        if not df.empty:
            data[sym] = df
    idx = load_cached(INDEX_INSTRUMENT_KEY)
    if not idx.empty:
        data[INDEX_SYMBOL] = idx
    return data


def _build():
    """A fresh strategy + regime built from the live .env config."""
    s = get_settings()
    regime = MarketRegime() if s.use_index_filter else None
    strat = ORBStrategy(
        opening_range_minutes=s.orb_opening_range_minutes,
        target_r=s.orb_target_r,
        min_range_pct=s.orb_min_range_pct,
        max_range_pct=s.orb_max_range_pct,
        volume_mult=s.orb_volume_mult,
        breakout_buffer_pct=s.orb_breakout_buffer_pct,
        regime=(regime.direction if regime else None),
    )
    return strat, regime


def _run(data: dict):
    strat, regime = _build()
    return BacktestEngine(strat, regime=regime).run(data)


def _verdict(test: dict | None) -> str:
    if not test or test["num_trades"] < 20:
        return "INSUFFICIENT DATA — too few out-of-sample trades to judge. Fetch more history."
    ok = test["net_pnl"] > 0 and test["profit_factor"] >= 1.3 and test["expectancy"] > 0
    if ok:
        return "PROMISING — positive out-of-sample edge after costs. Confirm with forward paper testing."
    return "NO EDGE YET — out-of-sample is weak. Tune/replace before risking capital."


def main() -> None:
    data = _load()
    stocks = [s for s in data if s != INDEX_SYMBOL]
    if not stocks:
        print("No cached history. Run `python -m scripts.fetch_history` first (needs an Upstox token).")
        return

    has_index = INDEX_SYMBOL in data
    print(f"Loaded {len(stocks)} symbols; index data: {'yes' if has_index else 'NO (regime filter inactive)'}\n")

    print("=== Full-period backtest (live config) ===")
    res = _run(data)
    print(res.summary())
    print(f"  expectancy ₹{res.stats['expectancy']:.1f}/trade | "
          f"profit factor {res.stats['profit_factor']:.2f} | sharpe {res.stats['sharpe']:.2f}")
    print("  Per-symbol (top 10 by net):")
    for sym, m in sorted(per_symbol(res.trades).items(), key=lambda x: -x[1]["net_pnl"])[:10]:
        print(f"    {sym:<11} trades={m['trades']:<3} win%={m['win_rate']:5.1f} net=₹{m['net_pnl']:.0f}")

    print("\n=== Out-of-sample check (train 60% / test 40%, same fixed config) ===")
    train, test = split_by_date(data, 0.6)
    res_tr, res_te = _run(train), _run(test)
    print(f"  Train: trades={res_tr.stats['num_trades']:<4} net=₹{res_tr.stats['net_pnl']:.0f} "
          f"PF={res_tr.stats['profit_factor']:.2f}")
    print(f"  Test : trades={res_te.stats['num_trades']:<4} net=₹{res_te.stats['net_pnl']:.0f} "
          f"PF={res_te.stats['profit_factor']:.2f} expectancy=₹{res_te.stats['expectancy']:.1f}")

    print("\n=== VERDICT ===")
    print(" ", _verdict(res_te.stats))


if __name__ == "__main__":
    main()
