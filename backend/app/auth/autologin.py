"""Unattended daily Upstox login via TOTP (OPTIONAL, security-sensitive).

⚠️ READ THIS. Upstox has no documented programmatic username/password login —
the only sanctioned auth is the browser OAuth redirect. So a truly hands-off
login automates that real login page with a headless browser, and that means:

  • You must store your Upstox MOBILE, PIN, and TOTP SECRET in `.env`
    (git-ignored, but still sensitive — anyone with that file can log into your
    broker account). Only enable this on a host you fully control.
  • You must switch Upstox 2FA from SMS OTP to an Authenticator-app TOTP, and
    paste that TOTP secret into `.env` (UPSTOX_TOTP_SECRET).
  • The login-page selectors below can change when Upstox updates their UI; if
    auto-login breaks, fall back to `python -m scripts.login` and update selectors.

This is genuinely fragile and a real security trade-off. The recommended default
remains the ~30-second manual login. Enable this only if you accept the above.

Setup:  pip install -r requirements-autologin.txt && playwright install chromium
"""
from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlparse

from app.config import Settings, get_settings
from app.data.upstox_client import exchange_code_for_token, login_url, persist_token

log = logging.getLogger("quantifywealth.autologin")

# Upstox login UI selectors — VERIFY/UPDATE against the live page if it changes.
SEL_MOBILE = "input#mobileNum, input[name='mobileNumber']"
SEL_GET_OTP = "button#getOtp"
SEL_OTP = "input#otpNum, input[name='otp']"
SEL_OTP_CONTINUE = "button#continueBtn"
SEL_PIN = "input#pinCode, input[name='pin']"
SEL_PIN_CONTINUE = "button#pinContinueBtn"


def totp_now(secret: str) -> str:
    import pyotp

    return pyotp.TOTP(secret).now()


def auto_login(settings: Settings | None = None) -> bool:
    """Refresh today's Upstox token without human interaction. Returns success."""
    s = settings or get_settings()
    if not s.auto_login_enabled:
        log.info("Auto-login not configured (need mobile + pin + TOTP secret); skipping.")
        return False
    try:
        code = _browser_login(s)
    except Exception:  # noqa: BLE001
        log.exception("Auto-login failed during browser flow")
        return False
    if not code:
        log.error("Auto-login did not capture an authorization code.")
        return False

    payload = exchange_code_for_token(code)
    token = payload.get("access_token")
    if not token:
        log.error("Auto-login token exchange failed: %s", payload)
        return False
    persist_token(token)
    log.info("Auto-login succeeded; token refreshed.")
    return True


def _browser_login(s: Settings) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Playwright not installed. Run: pip install -r requirements-autologin.txt "
            "&& playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(login_url(), wait_until="domcontentloaded")
            page.fill(SEL_MOBILE, s.upstox_mobile)
            page.click(SEL_GET_OTP)
            page.fill(SEL_OTP, totp_now(s.upstox_totp_secret))
            page.click(SEL_OTP_CONTINUE)
            page.fill(SEL_PIN, s.upstox_pin)
            page.click(SEL_PIN_CONTINUE)
            page.wait_for_url(f"{s.upstox_redirect_uri}*", timeout=30_000)
            return parse_qs(urlparse(page.url).query).get("code", [None])[0]
        finally:
            browser.close()
