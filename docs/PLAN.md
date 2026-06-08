# QuantifyWealth — Build Plan

**Internal deadline:** live by **2026-06-25**. Hard stop: **2026-06-28**.
NSE trading hours: 09:15–15:30 IST, Mon–Fri (markets closed weekends).

## Decisions (locked)

| Topic | Decision |
|---|---|
| System type | Classical quant/algo (no LLM in trade loop) + UI for personal use |
| Horizon | Intraday |
| Capital | ₹1,00,000 |
| Instruments | Liquid large-cap NSE cash equities, MIS (intraday) |
| First strategy | Opening Range Breakout (ORB) |
| Broker | Upstox (API v2) |
| UI | React + Tailwind |
| Go-live | Real money by Jun 25; paper↔live behind a manual switch |

## Milestones

| Dates | Milestone | Status |
|---|---|---|
| Jun 8–10 | Repo scaffold, Upstox OAuth, historical candle fetch, data layer | ✅ |
| Jun 11–12 | Event-driven backtest engine + cost/slippage model | ✅ |
| Jun 15–17 | ORB strategy + parameter optimizer/scanner; validate on history | ✅ (code; real-data run pending token) |
| Jun 18–19 | Live WebSocket feed, paper execution, risk engine + kill switch | ✅ |
| Jun 22–24 | Dashboard (served from API) + autonomy (scheduler/journal) + hardening | ✅ |
| Ongoing | Forward paper testing on live market | ⏳ starts once Upstox token added |
| Later | Go live (flip TRADING_MODE=live), monitored | ☐ after paper validation |

Build is feature-complete. Only external dependency: the Upstox Developer App /
daily token. See `docs/RUNBOOK.md`.

## Risk rules (defaults — tunable)

- **Per-trade risk:** ~1% of capital (₹1,000) — position size derived from stop distance.
- **Max daily loss:** ~2% (₹2,000) → auto kill-switch, no new entries for the day. Symmetric with the daily profit target.
- **Max concurrent positions:** 3.
- **Mandatory square-off:** all positions closed by 15:15 IST.
- **No averaging down.** One stop per position, hard.

## Open items / inputs needed

- [ ] Upstox Developer App credentials (API Key, Secret, Redirect URI) — stored in git-ignored `.env`.
- [ ] Final basket of equities to trade (default: top liquid Nifty names).
- [ ] Confirm minimum paper-validation window before flipping to live.

## Definition of "validated enough to go live"

Forward paper results on live data should broadly match backtest expectations:
positive expectancy after costs, drawdown within tolerance, no execution/reconciliation bugs.
