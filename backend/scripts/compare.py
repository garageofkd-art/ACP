"""Strategy bake-off — run every candidate over the cached history and rank them.

  python -m scripts.compare    (or: make compare)

Each strategy is run full-period AND out-of-sample (60/40 split) on the same
cached data, then ranked by out-of-sample net P&L. Honest health warning: testing
many strategies and picking the best invites *lucky flukes* (data snooping) — any
winner here still has to survive forward paper testing.
"""
from __future__ import annotations

from app.backtest.engine import BacktestEngine
from app.backtest.optimizer import split_by_date
from app.config import get_settings
from app.data.historical import load_cached
from app.data.instruments import INDEX_INSTRUMENT_KEY, INDEX_SYMBOL, resolve_instrument_keys
from app.strategies.gap import GapStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
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


def _orb(s, reg):
    return ORBStrategy(opening_range_minutes=s.orb_opening_range_minutes, target_r=s.orb_target_r,
                       min_range_pct=s.orb_min_range_pct, max_range_pct=s.orb_max_range_pct,
                       volume_mult=s.orb_volume_mult, breakout_buffer_pct=s.orb_breakout_buffer_pct,
                       regime=reg)


# (name, factory(settings, regime_fn), uses_index)
CANDIDATES = [
    ("ORB", _orb, True),
    ("MeanReversion", lambda s, reg: MeanReversionStrategy(
        entry_pct=s.mr_entry_pct, stop_pct=s.mr_stop_pct, warmup_minutes=s.mr_warmup_minutes), False),
    ("Gap-fade", lambda s, reg: GapStrategy(), False),
]


def _verdict(test: dict) -> str:
    if test["num_trades"] < 20:
        return "INSUFFICIENT"
    if test["net_pnl"] > 0 and test["profit_factor"] >= 1.3 and test["expectancy"] > 0:
        return "PROMISING"
    return "NO EDGE"


def _pf(x) -> str:
    return "inf" if x == float("inf") else f"{x:.2f}"


def _evaluate(factory, uses_idx, data, settings):
    def build():
        reg = MarketRegime() if uses_idx else None
        return factory(settings, reg.direction if reg else None), reg

    s1, r1 = build()
    full = BacktestEngine(s1, regime=r1).run(data).stats
    train, test_data = split_by_date(data, 0.6)
    s3, r3 = build()
    test = BacktestEngine(s3, regime=r3).run(test_data).stats if test_data else None
    return full, test


def main() -> None:
    data = _load()
    stocks = [s for s in data if s != INDEX_SYMBOL]
    if not stocks:
        print("No cached history. Run `python -m scripts.fetch_history` first.")
        return
    s = get_settings()
    print(f"Bake-off over {len(stocks)} symbols\n")

    rows = []
    for name, factory, uses_idx in CANDIDATES:
        full, test = _evaluate(factory, uses_idx, data, s)
        rows.append((name, full, test))
    rows.sort(key=lambda r: (r[2]["net_pnl"] if r[2] else -1e18), reverse=True)

    hdr = f"{'Strategy':<14}{'Trades':>7}{'Net P&L':>10}{'PF':>6}{'Exp':>7}   {'OOS Net':>9}{'OOS PF':>7}  Verdict"
    print(hdr)
    print("-" * len(hdr))
    for name, full, test in rows:
        t = test or {"net_pnl": 0, "profit_factor": 0, "num_trades": 0, "expectancy": 0}
        print(f"{name:<14}{full['num_trades']:>7}{full['net_pnl']:>10.0f}{_pf(full['profit_factor']):>6}"
              f"{full['expectancy']:>7.0f}   {t['net_pnl']:>9.0f}{_pf(t['profit_factor']):>7}  {_verdict(t)}")

    print("\nRanked by out-of-sample net P&L. A 'PROMISING' here is necessary but NOT "
          "sufficient — it still needs forward paper testing, because testing many "
          "strategies can surface a fluke.")


if __name__ == "__main__":
    main()
