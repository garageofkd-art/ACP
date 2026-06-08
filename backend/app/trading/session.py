"""Live/paper trading session.

Drives the same strategy + risk + accounting as the backtest, but routes fills
through a `Broker` (paper sim or live Upstox). Fed one bar at a time by the
live data feed (or any bar source), it:

  - manages open positions (stop / target / mandatory square-off),
  - sizes and places new entries via the risk engine,
  - enforces the daily-loss kill switch: once tripped, it flattens everything
    and refuses new entries for the rest of the day.

The kill switch is the hard floor that protects the ₹1L — it cannot be bypassed
by a strategy.
"""
from __future__ import annotations

from datetime import datetime, time

from app.backtest.costs import CostConfig, apply_slippage
from app.config import Settings, get_settings
from app.core.events import Bar, Side, SignalType
from app.core.portfolio import Portfolio, Position
from app.execution.base import Broker
from app.execution import get_broker
from app.risk.manager import RiskManager
from app.strategies.base import Strategy


class TradingSession:
    def __init__(
        self,
        strategy: Strategy,
        broker: Broker | None = None,
        settings: Settings | None = None,
        cost: CostConfig | None = None,
        square_off: time | None = None,
    ):
        self.s = settings or get_settings()
        self.cost = cost or CostConfig()
        self.strategy = strategy
        self.broker = broker or get_broker(self.s, self.cost)
        self.square_off = square_off or self.s.square_off
        self.pf = Portfolio(self.s.capital)
        self.risk = RiskManager(self.s)
        self.halted = False
        self._last_price: dict[str, float] = {}

    # --- main entry point ---------------------------------------------------
    def on_bar(self, bar: Bar) -> None:
        self._last_price[bar.symbol] = bar.close
        t = bar.ts.time()
        day = bar.ts.date()

        if bar.symbol in self.pf.positions:
            self._manage(bar, t)

        signals = self.strategy.on_bar(bar)
        if self.halted or bar.symbol in self.pf.positions:
            return
        for sig in signals:
            if sig.type is not SignalType.ENTRY:
                continue
            if not self.risk.can_enter(day, len(self.pf.positions)):
                continue
            expected_fill = apply_slippage(sig.price, sig.side, self.cost)
            qty = self.risk.size(sig, expected_fill, self.pf.available)
            if qty <= 0:
                continue
            fill = self.broker.execute(bar.symbol, sig.side, qty, sig.price, bar.ts, sig.reason)
            if fill.quantity <= 0:
                continue
            self.pf.open(
                Position(bar.symbol, sig.side, fill.quantity, bar.ts, fill.price,
                         sig.stop, sig.target, fill.cost)
            )

    # --- position management ------------------------------------------------
    def _manage(self, bar: Bar, t: time) -> None:
        pos = self.pf.positions[bar.symbol]

        # Kill switch flattens everything, no questions asked.
        if self.halted:
            self._close(bar.symbol, bar.close, bar.ts, "kill_switch")
            return

        exit_price: float | None = None
        reason = ""
        if pos.side == Side.BUY:
            if bar.low <= pos.stop:
                exit_price, reason = pos.stop, "stop"
            elif bar.high >= pos.target:
                exit_price, reason = pos.target, "target"
        else:
            if bar.high >= pos.stop:
                exit_price, reason = pos.stop, "stop"
            elif bar.low <= pos.target:
                exit_price, reason = pos.target, "target"

        if exit_price is None and t >= self.square_off:
            exit_price, reason = bar.close, "square_off"

        if exit_price is not None:
            self._close(bar.symbol, exit_price, bar.ts, reason)

    def _close(self, symbol: str, ref_price: float, ts: datetime, reason: str) -> None:
        pos = self.pf.positions[symbol]
        exit_side = Side.SELL if pos.side == Side.BUY else Side.BUY
        fill = self.broker.execute(symbol, exit_side, pos.qty, ref_price, ts, reason)
        trade = self.pf.close(symbol, ts, fill.price, fill.cost, reason)
        self.risk.record_close(ts.date(), trade.net_pnl)
        if self.risk.kill_switch_tripped(ts.date()):
            self.halted = True

    def flatten_all(self, reason: str = "square_off", ts: datetime | None = None) -> None:
        """Force-close every open position at the last seen price. Called by the
        scheduler at square-off so we never carry an intraday position past close,
        even if the tick stream went quiet near the bell."""
        ts = ts or datetime.now()
        for symbol in list(self.pf.positions):
            ref = self._last_price.get(symbol, self.pf.positions[symbol].entry_price)
            self._close(symbol, ref, ts, reason)

    # --- state for the API / UI --------------------------------------------
    def snapshot(self) -> dict:
        equity = self.pf.equity(self._last_price)
        return {
            "mode": self.broker.mode,
            "halted": self.halted,
            "equity": round(equity, 2),
            "realized_pnl": round(self.pf.realized_pnl, 2),
            "available": round(self.pf.available, 2),
            "num_trades": len(self.pf.trades),
            "open_positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side.value,
                    "qty": p.qty,
                    "entry_price": round(p.entry_price, 2),
                    "stop": round(p.stop, 2),
                    "target": round(p.target, 2),
                    "unrealized": round(p.unrealized(self._last_price.get(s, p.entry_price)), 2),
                }
                for s, p in self.pf.positions.items()
            ],
        }
