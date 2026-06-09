# QuantifyWealth — Runbook

How to connect Upstox and start paper testing. Everything defaults to **paper
mode** — no real orders until you explicitly set `TRADING_MODE=live`.

## 1. One-time: create the Upstox Developer App (needs a laptop)

1. Go to the Upstox developer console → **Apps** → create a new app.
2. Set the **Redirect URI** to exactly: `http://localhost:8000/auth/callback`
3. Copy the **API Key** and **API Secret**.

## 2. One-time: configure the project

```bash
cp .env.example .env
# edit .env and fill in:
#   UPSTOX_API_KEY=...
#   UPSTOX_API_SECRET=...
#   UPSTOX_REDIRECT_URI=http://localhost:8000/auth/callback
#   TRADING_MODE=paper        # keep this until validated
```

## 3. Install + run

**Easiest — one command from the repo root:**
```bash
./start.sh
```
(First run sets up the venv and installs everything; subsequent runs just start.)

Or manually:
```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000/** (or the host's IP from your phone on the same
network). That's the dashboard.

## 4. Daily: connect Upstox (≈30 seconds)

Upstox access tokens **expire every day**, so each trading morning:

1. Open the dashboard → click **Connect Upstox**.
2. Log in / approve. You'll be redirected back and the token is saved to `.env`.
3. Click **Start** (or let the scheduler auto-start at 09:14 IST).

The scheduler then runs the session, force-squares-off at 15:15, and writes the
day to the journal at 15:31 — automatically, every trading day.

## 5. Watching paper results

- **Dashboard** (`/`): live equity, P&L, open positions, kill-switch state, and
  the growing **paper track record**.
- **Logs**: `logs/quantifywealth.log` — every entry/exit/kill-switch event.
- **Journal**: `backend/data/journal/<date>.json` — one file per day.

## 6. Going live (only after the track record looks good)

1. Stop the server.
2. In `.env` set `TRADING_MODE=live`.
3. Restart. The badge turns **LIVE** (red) and orders become real MIS orders.

Risk caps (`RISK_PER_TRADE_PCT`, `MAX_DAILY_LOSS_PCT`) and the kill switch apply
identically in paper and live.

## Reducing daily friction (optional)

### Telegram alerts (READY ping + daily summary)
1. In Telegram, message **@BotFather** → `/newbot` → copy the **bot token**.
2. Message **@userinfobot** → copy your numeric **chat id**.
3. Add to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID=...
   ```
4. Restart, open the dashboard, click **Test alert** — you should get a Telegram message.

You'll then get a one-time "🟢 READY" ping when the gate clears, plus an
end-of-day summary.

### Hands-off auto-login (removes the daily Upstox login)
⚠️ Security-sensitive — only on a host you fully control. See the warnings in
`backend/app/auth/autologin.py`.
1. In Upstox security settings, switch 2FA to an **Authenticator-app TOTP** and
   save the **TOTP secret**.
2. Add to `.env`: `UPSTOX_MOBILE`, `UPSTOX_PIN`, `UPSTOX_TOTP_SECRET`.
3. Install the extra: `pip install -r requirements-autologin.txt && playwright install chromium`.

With this set and the server left running, the scheduler **auto-refreshes the
token at 09:05** and **auto-starts the session at 09:14** every trading day —
fully hands-off, no morning login.

## Notes / gotchas
- **Always-on host:** for hands-off running during 09:15–15:30 IST, run this on
  a machine that stays on (e.g. a small cloud VM), not a phone/closed laptop.
- **Holidays:** verify `NSE_HOLIDAYS` in `app/market_calendar.py` against the
  official NSE circular each year.
- **Cost rates:** confirm `CostConfig` in `app/backtest/costs.py` against
  Upstox's current charges schedule.
