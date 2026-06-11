#!/usr/bin/env bash
# One-command launcher for QuantifyWealth.
#   ./start.sh
# Sets up the venv on first run, then runs the API + dashboard on :8000 under a
# supervisor that auto-restarts the server if it ever crashes. Press Ctrl-C to quit.
set -e
cd "$(dirname "$0")/backend"

if [ ! -d .venv ]; then
  echo "First run: creating virtual environment and installing dependencies…"
  (python3.12 -m venv .venv 2>/dev/null) || python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi

if [ ! -f ../.env ]; then
  echo "⚠️  No .env found at repo root. Copy .env.example to .env and add your Upstox keys."
fi

# Clean Ctrl-C: stop supervising and exit.
trap 'echo ""; echo "Stopping QuantifyWealth."; exit 0' INT TERM

echo "Starting QuantifyWealth → http://localhost:8000/   (Ctrl-C to quit)"
while true; do
  ./.venv/bin/uvicorn app.api.main:app --host 0.0.0.0 --port 8000 || true
  echo "⚠️  Server exited unexpectedly — restarting in 5s… (Ctrl-C to quit)"
  sleep 5
done
