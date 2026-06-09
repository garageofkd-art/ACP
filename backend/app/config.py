"""Application settings, loaded from the repo-root `.env`.

Defaults are safe: TRADING_MODE is `paper` unless explicitly set to `live`.
"""
from __future__ import annotations

from datetime import time
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> repo root is two parents up from `app`.
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "backend" / "data"
CACHE_DIR = DATA_DIR / "cache"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Upstox credentials ---
    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    upstox_redirect_uri: str = "http://localhost:8000/auth/callback"
    upstox_access_token: str = ""

    # --- Trading mode: backtest | paper | live ---
    trading_mode: str = "paper"

    # Auto-run the market-hours scheduler when the API starts.
    auto_schedule: bool = True

    # Assumed monthly infrastructure cost (VM etc.) for break-even tracking.
    monthly_infra_cost_inr: float = 500.0

    # --- Go-live readiness gate (hard lock on real-money trading) ---
    # Live trading is blocked until ALL of these pass (see app/readiness.py).
    target_confidence_pct: float = 95.0       # statistical confidence the edge is real
    min_trades_for_live: int = 30             # sample size before the stats mean anything
    min_profit_factor: float = 1.3            # gross profit / gross loss
    max_drawdown_pct_for_live: float = 15.0   # cap on peak-to-trough, % of capital
    allow_live_override: bool = False         # emergency bypass of the lock (use with care)

    # --- Optional unattended TOTP auto-login (security-sensitive) ---
    upstox_mobile: str = ""
    upstox_pin: str = ""
    upstox_totp_secret: str = ""

    @property
    def auto_login_enabled(self) -> bool:
        return bool(self.upstox_mobile and self.upstox_pin and self.upstox_totp_secret)

    # --- Notifications (optional) ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notify_email_to: str = ""
    notify_daily_summary: bool = True

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.notify_email_to)

    @property
    def notifications_configured(self) -> bool:
        return self.telegram_configured or self.email_configured

    # --- Capital & risk (INR) ---
    capital: float = 100_000
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 2.0
    max_concurrent_positions: int = 3
    square_off_time: str = "15:15"

    # Daily profit target (flat INR). On hitting it, flatten and stop for the
    # day — "make the money and walk away". 0 disables it.
    daily_profit_target_inr: float = 2000.0

    # --- ORB strategy parameters (tunable without code changes) ---
    orb_opening_range_minutes: int = 15
    orb_target_r: float = 2.0
    orb_min_range_pct: float = 0.0015   # skip days with too-narrow opening range
    orb_max_range_pct: float = 0.05     # skip gap/news-distorted wide ranges (0 = off)
    orb_volume_mult: float = 1.0        # breakout volume vs avg OR-bar volume (0 = off)
    orb_breakout_buffer_pct: float = 0.0005  # require a decisive break past the range
    use_index_filter: bool = True       # only long when Nifty up / short when down

    @property
    def is_live(self) -> bool:
        return self.trading_mode.lower() == "live"

    @property
    def risk_per_trade_inr(self) -> float:
        return self.capital * self.risk_per_trade_pct / 100.0

    @property
    def max_daily_loss_inr(self) -> float:
        return self.capital * self.max_daily_loss_pct / 100.0

    @property
    def square_off(self) -> time:
        hh, mm = self.square_off_time.split(":")
        return time(int(hh), int(mm))


@lru_cache
def get_settings() -> Settings:
    return Settings()
