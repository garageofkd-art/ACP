#!/usr/bin/env bash
# One-command launcher for QuantifyWealth.
#   ./start.sh
# Sets up the venv on first run, then starts the API + dashboard on :8000.
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

echo "Starting QuantifyWealth → http://localhost:8000/"
exec ./.venv/bin/uvicorn app.api.main:app --host 0.0.0.0 --port 8000
