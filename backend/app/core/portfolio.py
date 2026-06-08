"""Position and portfolio accounting, shared by backtest/paper/live.

Accounting is no-leverage by default: a new position can deploy at most the
currently-available capital (starting capital + realized P&L - deployed
notional). Intraday MIS leverage can be layered on later as a toggle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.events import Side


@dataclass(slots=True)
class Position:
    symbol: str
    side: Side
    qty: int
    entry_ts: datetime
    entry_price: float
    stop: float
    target: float
    entry_cost: float = 0.0

    @property
    def notional(self) -> float:
        return self.qty * self.entry_price

    def unrealized(self, price: float) -> float:
        direction = 1 if self.side == Side.BUY else -1
        return (price - self.entry_price) * self.qty * direction


@dataclass(slots=True)
class Trade:
    symbol: str
    side: Side  # the entry side
    qty: int
    entry_ts: datetime
    entry_price: float
    exit_ts: datetime
    exit_price: float
    gross_pnl: float
    costs: float
    net_pnl: float
    reason: str


@dataclass(slots=True)
class Portfolio:
    starting_capital: float
    realized_pnl: float = 0.0
    deployed: float = 0.0
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)

    @property
    def available(self) -> float:
        return self.starting_capital + self.realized_pnl - self.deployed

    def open(self, pos: Position) -> None:
        self.positions[pos.symbol] = pos
        self.deployed += pos.notional

    def close(
        self,
        symbol: str,
        exit_ts: datetime,
        exit_price: float,
        exit_cost: float,
        reason: str,
    ) -> Trade:
        pos = self.positions.pop(symbol)
        direction = 1 if pos.side == Side.BUY else -1
        gross = (exit_price - pos.entry_price) * pos.qty * direction
        total_cost = pos.entry_cost + exit_cost
        net = gross - total_cost
        self.realized_pnl += net
        self.deployed -= pos.notional
        trade = Trade(
            symbol=symbol,
            side=pos.side,
            qty=pos.qty,
            entry_ts=pos.entry_ts,
            entry_price=pos.entry_price,
            exit_ts=exit_ts,
            exit_price=exit_price,
            gross_pnl=gross,
            costs=total_cost,
            net_pnl=net,
            reason=reason,
        )
        self.trades.append(trade)
        return trade

    def equity(self, prices: dict[str, float]) -> float:
        unreal = sum(
            p.unrealized(prices.get(s, p.entry_price)) for s, p in self.positions.items()
        )
        return self.starting_capital + self.realized_pnl + unreal
