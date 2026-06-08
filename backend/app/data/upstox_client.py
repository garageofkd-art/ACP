"""Thin Upstox API v2 client: OAuth helpers + an authenticated HTTP client.

Order placement and the live WebSocket feed will build on this in later
milestones. Everything here is inert until a valid access token is present in
`.env` (UPSTOX_ACCESS_TOKEN) or set via the OAuth flow.

Docs: https://upstox.com/developer/api-documentation/
"""
from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.config import get_settings

API_BASE = "https://api.upstox.com/v2"
AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


def login_url(state: str = "quantifywealth") -> str:
    """Build the URL the user visits to authorize the app (step 1 of OAuth)."""
    s = get_settings()
    params = {
        "client_id": s.upstox_api_key,
        "redirect_uri": s.upstox_redirect_uri,
        "response_type": "code",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code_for_token(auth_code: str) -> dict:
    """Exchange the redirect `code` for an access token (step 2 of OAuth).

    Returns the raw token payload; the caller is responsible for persisting
    `access_token` into `.env` (UPSTOX_ACCESS_TOKEN).
    """
    s = get_settings()
    resp = httpx.post(
        TOKEN_URL,
        headers={"accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        data={
            "code": auth_code,
            "client_id": s.upstox_api_key,
            "client_secret": s.upstox_api_secret,
            "redirect_uri": s.upstox_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def persist_token(token: str) -> None:
    """Write/replace UPSTOX_ACCESS_TOKEN in the repo-root .env and refresh
    cached settings so the new token takes effect immediately."""
    from app.config import REPO_ROOT, get_settings

    path = REPO_ROOT / ".env"
    lines = path.read_text().splitlines() if path.exists() else []
    line = f"UPSTOX_ACCESS_TOKEN={token}"
    for i, existing in enumerate(lines):
        if existing.startswith("UPSTOX_ACCESS_TOKEN="):
            lines[i] = line
            break
    else:
        lines.append(line)
    path.write_text("\n".join(lines) + "\n")
    get_settings.cache_clear()


def client() -> httpx.Client:
    """An authenticated httpx client for Upstox REST calls."""
    s = get_settings()
    if not s.upstox_access_token:
        raise RuntimeError(
            "No Upstox access token. Run the OAuth flow or set UPSTOX_ACCESS_TOKEN in .env."
        )
    return httpx.Client(
        base_url=API_BASE,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {s.upstox_access_token}",
        },
        timeout=30,
    )
