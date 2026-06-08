"""Optional notifications (Telegram and/or email).

Used to ping you when the go-live readiness gate clears (a one-time "🟢 READY"
alert) and for an end-of-day paper-testing summary. Everything no-ops silently
if no channel is configured, so the agent runs fine without it.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

import httpx

from app.config import DATA_DIR, Settings, get_settings

log = logging.getLogger("quantifywealth.notify")

# Latch so the READY alert fires once (re-arms if readiness drops then clears).
READY_FLAG = DATA_DIR / ".ready_notified"


def configured(settings: Settings | None = None) -> bool:
    return (settings or get_settings()).notifications_configured


def send(message: str, subject: str = "QuantifyWealth", settings: Settings | None = None) -> bool:
    """Send via every configured channel. Returns True if at least one sent."""
    s = settings or get_settings()
    sent = False

    if s.telegram_configured:
        try:
            httpx.post(
                f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage",
                json={"chat_id": s.telegram_chat_id, "text": message},
                timeout=10,
            ).raise_for_status()
            sent = True
        except Exception:  # noqa: BLE001
            log.exception("Telegram notification failed")

    if s.email_configured:
        try:
            msg = MIMEText(message)
            msg["Subject"] = subject
            msg["From"] = s.smtp_user
            msg["To"] = s.notify_email_to
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(s.smtp_user, s.smtp_password)
                server.send_message(msg)
            sent = True
        except Exception:  # noqa: BLE001
            log.exception("Email notification failed")

    if not s.notifications_configured:
        log.info("No notification channel configured; skipping: %s", subject)
    return sent


def notify_if_ready(settings: Settings | None = None) -> bool:
    """Fire a one-time alert when the readiness gate first clears."""
    from app.readiness import evaluate

    report = evaluate(settings)
    if report["is_ready"]:
        if READY_FLAG.exists():
            return False  # already notified
        send(
            "🟢 QuantifyWealth: GO-LIVE READY.\n"
            f"Edge confidence {report['edge_confidence_pct']}% over {report['num_trades']} trades, "
            f"profit factor {report['profit_factor']}.\n"
            "All readiness checks passed. Set TRADING_MODE=live when you're ready to flip.",
            subject="QuantifyWealth: READY to go live",
            settings=settings,
        )
        READY_FLAG.parent.mkdir(parents=True, exist_ok=True)
        READY_FLAG.write_text("1")
        return True
    # Re-arm if readiness regressed.
    if READY_FLAG.exists():
        READY_FLAG.unlink()
    return False


def send_daily_summary(session, settings: Settings | None = None) -> bool:
    """End-of-day paper/live summary ping."""
    s = settings or get_settings()
    if not s.notify_daily_summary:
        return False
    snap = session.snapshot()
    halt = {"profit_target": "🎯 hit daily target",
            "kill_switch": "⛔ hit loss limit"}.get(snap.get("halt_reason"), "ran full session")
    from app.journal import track_record

    tr = track_record()
    msg = (
        f"QuantifyWealth daily summary ({snap['mode']}):\n"
        f"Trades: {snap['num_trades']} | Day P&L: ₹{snap['daily_pnl']:.0f} ({halt})\n"
        f"Track record: {tr['days']} days, net ₹{tr['net_pnl']:.0f}, "
        f"win-days {tr['win_days']}/{tr['days']}."
    )
    return send(msg, subject="QuantifyWealth: daily summary", settings=settings)
