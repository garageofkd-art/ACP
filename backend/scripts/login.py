"""One-command Upstox daily login (headless-friendly).

Upstox access tokens expire each day. This makes the daily refresh a single
command: it prints the authorization URL, you approve in any browser, then paste
the redirect URL (or just the `code`) back here. The token is saved to `.env`.

  python -m scripts.login

This is the *safe* approach — it never stores your Upstox password or 2FA secret.
A fully-unattended auto-login is possible but requires storing those credentials
and scripting the login form (fragile + a security/ToS risk); ask before enabling.
"""
from __future__ import annotations

import webbrowser
from urllib.parse import parse_qs, urlparse

from app.data.upstox_client import exchange_code_for_token, login_url, persist_token


def main() -> None:
    url = login_url()
    print("1) Open this URL and approve access:\n")
    print("   " + url + "\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    raw = input("2) Paste the redirect URL (or just the code) here: ").strip()
    code = raw
    if "code=" in raw:
        code = parse_qs(urlparse(raw).query).get("code", [raw])[0]

    payload = exchange_code_for_token(code)
    token = payload.get("access_token")
    if not token:
        print("Token exchange failed:", payload)
        return
    persist_token(token)
    print("\n✓ Token saved to .env. The agent is ready to trade today.")


if __name__ == "__main__":
    main()
