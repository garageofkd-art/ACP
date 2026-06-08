# QuantifyWealth

A personal, classical-quant intraday trading platform for the Indian stock market (NSE), built on the Upstox API.

> ⚠️ **Risk notice.** This software places (or can place) real orders with real capital. Markets are risky; intraday leverage amplifies both gains and losses. Nothing here is investment advice. Trade only capital you can afford to lose, and only after validating a strategy in paper mode.

## What it is

- **Strategy:** Opening Range Breakout (ORB) on a basket of liquid large-cap NSE equities, intraday (MIS).
- **Capital:** ₹1,00,000 (configurable).
- **Approach:** classical/quant rules (no LLM in the trade loop) — backtested, optimized, then run live.
- **Broker:** Upstox (OAuth, historical candles, live WebSocket feed, order placement).
- **UI:** React + Tailwind dashboard for live P&L, positions, trade log, equity curve, and the paper↔live switch.

## Safety model

The same strategy code runs in **backtest**, **paper**, and **live** so behaviour is consistent. Live trading sits behind:

1. A hard **risk engine** (per-trade risk, max daily loss → auto kill-switch, mandatory square-off before close).
2. A manual **`TRADING_MODE`** flag (`paper` by default; `live` requires explicit opt-in).

## Repo layout

```
backend/      Python engine: data, backtest, strategies, execution, risk, API
frontend/     React + Tailwind dashboard
docs/         Architecture, plan, and runbooks
```

See [`docs/PLAN.md`](docs/PLAN.md) for the build timeline and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the system design.
