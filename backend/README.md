# QuantifyWealth — Backend

Python engine: data, backtest, strategies, execution, risk, and the API.

## Planned module layout

```
app/
  config.py          # settings from .env (pydantic-settings)
  data/              # Upstox historical + live WS feeds, local cache
  core/              # events, portfolio, P&L journal
  strategies/        # base interface + ORB
  backtest/          # event-driven engine + cost/slippage model
  risk/              # sizing, limits, kill-switch, square-off
  execution/         # paper sim + live Upstox order handler
  api/               # FastAPI REST + WebSocket
  scheduler.py       # NSE market-hours orchestration
tests/
```

## Setup (once built)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # then fill in Upstox credentials
uvicorn app.api.main:app --reload
```

Defaults to `TRADING_MODE=paper`. Switching to `live` requires explicitly setting it in `.env`.
