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

import logging
from datetime import datetime, time

from app.backtest.costs import CostConfig, apply_slippage
from app.config import Settings, get_settings
from app.core.events import Bar, Side, Signal, SignalType
from app.core.portfolio import Portfolio, Position
from app.data.instruments import INDEX_SYMBOL
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
        regime=None,
        capital: float | None = None,
    ):
        self.s = settings or get_settings()
        self.cost = cost or CostConfig()
        self.strategy = strategy
        self.regime = regime
        self.broker = broker or get_broker(self.s, self.cost)
        self.square_off = square_off or self.s.square_off
        cap = capital if capital is not None else self.s.capital
        self.pf = Portfolio(cap)
        self.risk = RiskManager(self.s, capital=cap)
        self.halted = False
        self.halt_reason: str | None = None
        self._last_price: dict[str, float] = {}
        self.log = logging.getLogger("quantifywealth.session")

    # --- main entry point ---------------------------------------------------
    def on_bar(self, bar: Bar) -> None:
        # The index feed only updates the regime; it is never traded.
        if self.regime is not None and bar.symbol == INDEX_SYMBOL:
            self.regime.update(bar.close, bar.ts.date())
            return

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
            self.log.info(
                "ENTRY %s %s x%d @ %.2f stop %.2f target %.2f (%s)",
                sig.side.value, bar.symbol, fill.quantity, fill.price,
                sig.stop, sig.target, sig.reason,
            )

    # --- position management ------------------------------------------------
    def _manage(self, bar: Bar, t: time) -> None:
        pos = self.pf.positions[bar.symbol]

        # Halted (kill switch OR daily target) flattens everything.
        if self.halted:
            self._close(bar.symbol, bar.close, bar.ts, self.halt_reason or "halted")
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
        self.log.info(
            "EXIT  %s x%d @ %.2f (%s) net ₹%.2f | day P&L ₹%.2f",
            symbol, pos.qty, fill.price, reason, trade.net_pnl,
            self.risk.daily_pnl(ts.date()),
        )
        if not self.halted and self.risk.kill_switch_tripped(ts.date()):
            self.halted, self.halt_reason = True, "kill_switch"
            self.log.warning(
                "KILL SWITCH tripped — daily loss ₹%.2f breached cap. Flattening, no new entries today.",
                self.risk.daily_pnl(ts.date()),
            )
        elif not self.halted and self.risk.profit_target_hit(ts.date()):
            self.halted, self.halt_reason = True, "profit_target"
            self.log.info(
                "DAILY TARGET HIT — banked ₹%.2f. Flattening and done for the day. 🎯",
                self.risk.daily_pnl(ts.date()),
            )

    def flatten_all(self, reason: str = "square_off", ts: datetime | None = None) -> None:
        """Force-close every open position at the last seen price. Called by the
        scheduler at square-off so we never carry an intraday position past close,
        even if the tick stream went quiet near the bell."""
        ts = ts or datetime.now()
        for symbol in list(self.pf.positions):
            ref = self._last_price.get(symbol, self.pf.positions[symbol].entry_price)
            self._close(symbol, ref, ts, reason)

    def close_position(self, symbol: str) -> dict:
        """Manually close one open position at the current price (user override)."""
        if symbol not in self.pf.positions:
            raise ValueError(f"No open position in {symbol}.")
        ref = self._last_price.get(symbol, self.pf.positions[symbol].entry_price)
        self._close(symbol, ref, datetime.now(), "manual_close")
        trade = self.pf.trades[-1]
        self.log.info("MANUAL CLOSE %s at %.2f — net ₹%.2f", symbol, ref, trade.net_pnl)
        return {"symbol": symbol, "exit_price": round(ref, 2), "net_pnl": round(trade.net_pnl, 2)}

    def place_test_trade(self, symbol: str | None = None) -> dict:
        """Manual smoke-test: a complete paper round-trip (buy + immediate sell)
        at the live price, to prove the execution -> portfolio -> journal path.
        Paper mode only; never fires a real order. Not a strategy signal — and the
        P&L is essentially just the real trading cost, since it exits flat."""
        if self.broker.mode != "paper":
            raise ValueError("Test trade is paper-only and disabled in live mode.")

        # Prefer a live price; fall back to last-known, then a nominal price so the
        # smoke test works even after market hours (it's just exercising machinery).
        symbol = symbol or (next(iter(self._last_price)) if self._last_price else "RELIANCE")
        price = self._last_price.get(symbol) or 2850.0
        if symbol in self.pf.positions:
            raise ValueError(f"Already holding {symbol}.")

        now = datetime.now()
        stop, target = round(price * 0.995, 2), round(price * 1.01, 2)
        sig = Signal(symbol, now, SignalType.ENTRY, Side.BUY, price, stop, target, "manual_test")
        qty = max(1, self.risk.size(sig, price, self.pf.available))
        fill = self.broker.execute(symbol, Side.BUY, qty, price, now, "manual_test")
        self.pf.open(Position(symbol, Side.BUY, fill.quantity, now, fill.price, stop, target, fill.cost))
        # Immediately close it at the live price -> one completed round-trip trade.
        self._close(symbol, price, now, "manual_test")
        trade = self.pf.trades[-1]
        self.log.info("MANUAL TEST round-trip: %s x%d @ %.2f, net ₹%.2f (paper)",
                      symbol, trade.qty, trade.entry_price, trade.net_pnl)
        return {
            "symbol": symbol, "qty": trade.qty,
            "entry_price": round(trade.entry_price, 2),
            "exit_price": round(trade.exit_price, 2),
            "net_pnl": round(trade.net_pnl, 2),
            "costs": round(trade.costs, 2),
        }

    # --- state for the API / UI --------------------------------------------
    def snapshot(self) -> dict:
        equity = self.pf.equity(self._last_price)
        return {
            "mode": self.broker.mode,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "daily_pnl": round(self.risk.latest_day_pnl(), 2),
            "daily_profit_target": self.s.daily_profit_target_inr,
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
