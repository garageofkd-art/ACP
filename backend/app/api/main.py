"""FastAPI server: REST + WebSocket for the dashboard, plus Upstox OAuth.

Holds one paper/live TradingSession (per TRADING_MODE) and a LiveRunner that
streams the Upstox feed into it. Starting the feed needs a valid token; until
then everything still loads and the snapshot reflects a flat, idle session.
"""
from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.data.instruments import UNIVERSE
from app.journal import save_session_day, track_record
from app.data.upstox_client import exchange_code_for_token, login_url, persist_token
from app.strategies.orb import ORBStrategy
from app.trading.runner import LiveRunner
from app.trading.session import TradingSession

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the autonomous market-hours scheduler unless disabled (tests)."""
    if get_settings().auto_schedule:
        try:
            from app.scheduler import MarketScheduler

            STATE.scheduler = MarketScheduler(STATE.runner, on_day_end=save_session_day)
            STATE.scheduler.start()
        except Exception:  # never let scheduler issues block the API
            STATE.scheduler = None
    yield
    scheduler = getattr(STATE, "scheduler", None)
    if scheduler is not None:
        scheduler.shutdown()


app = FastAPI(title="QuantifyWealth", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dashboard runs locally; tighten for any deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


class _State:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        settings = get_settings()
        self.session = TradingSession(ORBStrategy(), settings=settings)
        self.runner = LiveRunner(self.session)
        self.thread: threading.Thread | None = None


STATE = _State()


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "mode": s.trading_mode,
        "authenticated": bool(s.upstox_access_token),
        "running": STATE.runner.running,
    }


@app.get("/api/config")
def config() -> dict:
    s = get_settings()
    return {
        "mode": s.trading_mode,
        "capital": s.capital,
        "risk_per_trade_inr": s.risk_per_trade_inr,
        "max_daily_loss_inr": s.max_daily_loss_inr,
        "max_concurrent_positions": s.max_concurrent_positions,
        "square_off_time": s.square_off_time,
    }


@app.get("/api/universe")
def universe() -> list[dict]:
    return [
        {"symbol": i.symbol, "name": i.name, "low_priority": i.low_priority}
        for i in UNIVERSE
    ]


@app.get("/api/snapshot")
def snapshot() -> dict:
    return STATE.runner.snapshot()


@app.get("/api/track-record")
def get_track_record() -> dict:
    """Accumulated paper/live track record across all journaled days —
    the go/no-go scoreboard for moving to (or staying) live."""
    return track_record()


@app.get("/api/trades")
def trades() -> list[dict]:
    return [
        {
            "symbol": t.symbol,
            "side": t.side.value,
            "qty": t.qty,
            "entry_ts": t.entry_ts.isoformat(),
            "entry_price": round(t.entry_price, 2),
            "exit_ts": t.exit_ts.isoformat(),
            "exit_price": round(t.exit_price, 2),
            "net_pnl": round(t.net_pnl, 2),
            "reason": t.reason,
        }
        for t in STATE.session.pf.trades
    ]


# --- session control --------------------------------------------------------
@app.post("/api/session/start")
def start_session() -> dict:
    s = get_settings()
    if not s.upstox_access_token:
        raise HTTPException(400, "No Upstox token. Authenticate via /api/auth/login first.")
    if STATE.runner.running:
        return {"running": True, "mode": s.trading_mode}
    STATE.thread = threading.Thread(target=STATE.runner.start, daemon=True)
    STATE.thread.start()
    return {"running": True, "mode": s.trading_mode}


@app.post("/api/session/stop")
def stop_session() -> dict:
    STATE.runner.stop()
    return {"running": False}


# --- Upstox OAuth -----------------------------------------------------------
@app.get("/api/auth/login")
def auth_login() -> dict:
    return {"url": login_url()}


@app.get("/auth/callback", response_class=HTMLResponse)
def auth_callback(code: str | None = None, error: str | None = None) -> str:
    if error or not code:
        return f"<h3>Authorization failed: {error or 'no code returned'}</h3>"
    payload = exchange_code_for_token(code)
    token = payload.get("access_token")
    if not token:
        return f"<h3>Token exchange failed: {payload}</h3>"
    persist_token(token)
    STATE.reset()  # rebuild session with the new token in effect
    return "<h3>Upstox connected. You can close this tab and return to QuantifyWealth.</h3>"


# --- live snapshot stream ---------------------------------------------------
@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(STATE.runner.snapshot())
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
