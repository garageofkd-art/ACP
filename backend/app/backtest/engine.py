"""Event-driven backtest engine.

Replays cached candles for the whole universe in chronological order through a
strategy, sizing entries with the risk engine and applying the cost/slippage
model on every fill. Position exits (stop / target / mandatory square-off) are
managed by the engine so strategies stay focused on entries.

The same flow will drive paper/live later — only the data source and execution
handler change.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd

from app.backtest.costs import CostConfig, apply_slippage, charges
from app.config import Settings, get_settings
from app.core.events import Bar, Side, SignalType
from app.core.portfolio import Portfolio, Position, Trade
from app.risk.manager import RiskManager
from app.strategies.base import Strategy


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: pd.DataFrame  # columns: ts, equity
    stats: dict

    def summary(self) -> str:
        s = self.stats
        return (
            f"Trades: {s['num_trades']} | Win%: {s['win_rate']:.1f} | "
            f"Net P&L: ₹{s['net_pnl']:.0f} | Costs: ₹{s['total_costs']:.0f} | "
            f"Max DD: ₹{s['max_drawdown']:.0f} | Return: {s['return_pct']:.2f}%"
        )


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        settings: Settings | None = None,
        cost: CostConfig | None = None,
        square_off: time | None = None,
    ):
        self.strategy = strategy
        self.s = settings or get_settings()
        self.cost = cost or CostConfig()
        self.square_off = square_off or self.s.square_off

    def run(self, data: dict[str, pd.DataFrame]) -> BacktestResult:
        pf = Portfolio(self.s.capital)
        risk = RiskManager(self.s)
        self.strategy.reset()

        bars = self._merge(data)
        last_price: dict[str, float] = {}
        equity_rows: list[tuple] = []

        for row in bars.itertuples(index=False):
            bar = Bar(row.symbol, row.ts, row.open, row.high, row.low, row.close, int(row.volume))
            last_price[bar.symbol] = bar.close
            t = bar.ts.time()
            day = bar.ts.date()

            # 1) Manage an open position on this symbol (exits take priority).
            if bar.symbol in pf.positions:
                self._manage(pf, risk, bar, t)

            # 2) Always advance strategy state; act on entries only if flat.
            signals = self.strategy.on_bar(bar)
            if bar.symbol not in pf.positions:
                for sig in signals:
                    if sig.type is not SignalType.ENTRY:
                        continue
                    if not risk.can_enter(day, len(pf.positions)):
                        continue
                    fill = apply_slippage(sig.price, sig.side, self.cost)
                    qty = risk.size(sig, fill, pf.available)
                    if qty <= 0:
                        continue
                    entry_cost = charges(sig.side, qty, fill, self.cost)
                    pf.open(
                        Position(bar.symbol, sig.side, qty, bar.ts, fill,
                                 sig.stop, sig.target, entry_cost)
                    )

            equity_rows.append((bar.ts, pf.equity(last_price)))

        # Square off anything still open at the final observed price.
        self._flush(pf, risk, last_price, bars)

        eq = pd.DataFrame(equity_rows, columns=["ts", "equity"]).drop_duplicates("ts", keep="last")
        return BacktestResult(pf.trades, eq, self._stats(pf.trades, eq))

    # --- internals ----------------------------------------------------------
    @staticmethod
    def _merge(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        frames = []
        for sym, df in data.items():
            d = df.copy()
            d["symbol"] = sym
            frames.append(d)
        merged = pd.concat(frames, ignore_index=True)
        return merged.sort_values("ts", kind="stable").reset_index(drop=True)

    def _manage(self, pf: Portfolio, risk: RiskManager, bar: Bar, t: time) -> None:
        pos = pf.positions[bar.symbol]
        exit_price: float | None = None
        reason = ""
        if pos.side == Side.BUY:
            if bar.low <= pos.stop:
                exit_price, reason = pos.stop, "stop"
            elif bar.high >= pos.target:
                exit_price, reason = pos.target, "target"
        else:  # short
            if bar.high >= pos.stop:
                exit_price, reason = pos.stop, "stop"
            elif bar.low <= pos.target:
                exit_price, reason = pos.target, "target"

        if exit_price is None and t >= self.square_off:
            exit_price, reason = bar.close, "square_off"

        if exit_price is not None:
            self._close(pf, risk, bar.symbol, bar.ts, exit_price, reason)

    def _close(self, pf, risk, symbol, ts, price, reason) -> None:
        pos = pf.positions[symbol]
        exit_side = Side.SELL if pos.side == Side.BUY else Side.BUY
        fill = apply_slippage(price, exit_side, self.cost)
        exit_cost = charges(exit_side, pos.qty, fill, self.cost)
        trade = pf.close(symbol, ts, fill, exit_cost, reason)
        risk.record_close(ts.date(), trade.net_pnl)

    def _flush(self, pf, risk, last_price, bars) -> None:
        if not pf.positions:
            return
        last_ts = bars["ts"].iloc[-1]
        for sym in list(pf.positions):
            self._close(pf, risk, sym, last_ts, last_price[sym], "end_of_data")

    @staticmethod
    def _stats(trades: list[Trade], eq: pd.DataFrame) -> dict:
        n = len(trades)
        net = sum(t.net_pnl for t in trades)
        gross = sum(t.gross_pnl for t in trades)
        costs = sum(t.costs for t in trades)
        wins = [t for t in trades if t.net_pnl > 0]
        start = eq["equity"].iloc[0] if not eq.empty else 0.0
        if eq.empty:
            max_dd = 0.0
        else:
            roll_max = eq["equity"].cummax()
            max_dd = float((eq["equity"] - roll_max).min())
        return {
            "num_trades": n,
            "win_rate": (100.0 * len(wins) / n) if n else 0.0,
            "gross_pnl": gross,
            "net_pnl": net,
            "total_costs": costs,
            "max_drawdown": max_dd,
            "return_pct": (100.0 * net / start) if start else 0.0,
        }
