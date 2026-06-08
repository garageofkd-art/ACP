# QuantifyWealth — Architecture

## Principle: one strategy, three modes

The same strategy code runs unchanged in **backtest**, **paper**, and **live**. Modes differ only in the *data source* (historical replay vs live feed) and the *execution handler* (simulated fill vs real Upstox order). This keeps live behaviour faithful to what we backtested.

```
                 ┌───────────────────────────────────────────┐
                 │                Strategy core                │
                 │   (ORB rules — emits Signals on events)     │
                 └───────────────▲──────────────┬──────────────┘
                                 │ MarketEvent   │ Signal
        ┌────────────────────────┴───┐   ┌──────▼───────────────┐
        │        Data layer          │   │     Risk engine      │
        │ ┌────────────┐ ┌─────────┐ │   │ size / limits / kill │
        │ │ historical │ │  live   │ │   └──────┬───────────────┘
        │ │  (replay)  │ │ (WS)    │ │          │ approved Order
        │ └────────────┘ └─────────┘ │   ┌──────▼───────────────┐
        └────────────────────────────┘   │   Execution handler  │
                                          │ ┌────────┐ ┌───────┐ │
                                          │ │ paper  │ │ live  │ │
                                          │ │  sim   │ │Upstox │ │
                                          │ └────────┘ └───────┘ │
                                          └──────┬───────────────┘
                                                 │ Fill / state
                                   ┌─────────────▼──────────────┐
                                   │  Portfolio / P&L / journal  │
                                   └─────────────┬──────────────┘
                                                 │
                              FastAPI REST + WebSocket → React dashboard
```

## Components

### Data layer
- **Historical:** Upstox historical candle API → local cache (parquet/SQLite) for fast, repeatable backtests.
- **Live:** Upstox market-data WebSocket (LTP/quotes) normalized into the same `MarketEvent` shape as historical bars.

### Strategy core
- Pluggable interface: `on_event(event) -> list[Signal]`. ORB is the first implementation.
- Stateless w.r.t. broker; emits intent (`BUY`/`SELL`/`EXIT` + stop/target), never talks to the broker directly.

### Risk engine (hard gate)
- Sits between Signal and Execution. Owns: position sizing from stop distance, per-trade risk cap, max daily loss kill-switch, max concurrent positions, and forced square-off near close. Can veto or shrink any order.

### Execution handler
- **Paper:** simulates fills with a cost+slippage model (brokerage, STT, exchange txn, GST, stamp duty, SEBI fees, slippage).
- **Live:** places/cancels/modifies real Upstox MIS orders; reconciles fills and positions from the broker as source of truth.
- Selected by `TRADING_MODE` (`backtest` | `paper` | `live`).

### Portfolio & journal
- Tracks positions, realized/unrealized P&L, equity curve. Every signal, order, and fill is logged for audit and post-trade analysis.

### Orchestration
- Scheduler aligned to NSE hours: warm up before 09:15, compute opening range, run the session, square off by 15:15, generate end-of-day report.

### API + UI
- **Backend:** FastAPI (REST for config/history, WebSocket for live ticks/positions/P&L).
- **Frontend:** React + Tailwind + TradingView lightweight-charts — live dashboard, trade log, equity curve, strategy controls, and the paper↔live switch.

## Tech stack

- **Backend:** Python 3.11+, Upstox SDK, FastAPI, APScheduler, pandas, pydantic; SQLite/parquet for storage.
- **Frontend:** React + Vite + TypeScript + Tailwind + lightweight-charts.
- **Secrets:** `.env` (git-ignored): Upstox API key/secret, redirect URI, tokens.

## Cost model (NSE intraday equity, MIS)

Backtests and paper trading apply realistic costs so results aren't fantasy:
brokerage (per Upstox plan), STT, exchange transaction charges, GST, SEBI turnover fee,
stamp duty, plus a configurable slippage assumption. All centralized in one module so
the same numbers feed backtest and paper.
