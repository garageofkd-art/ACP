"""NSE market hours and trading-day calendar (IST).

The holiday list is best-effort and MUST be verified against the official NSE
trading-holiday circular each year — it's the one thing here that silently
drifts. Weekends are always closed.
"""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# NSE equity trading holidays — VERIFY against the NSE circular before relying
# on these. Easy to override at runtime via `set_holidays`.
NSE_HOLIDAYS: set[date] = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 2, 15),   # Mahashivratri (approx — verify)
    date(2026, 3, 6),    # Holi (approx — verify)
    date(2026, 3, 21),   # Eid (approx — verify)
    date(2026, 4, 3),    # Good Friday (approx — verify)
    date(2026, 4, 14),   # Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 8, 15),   # Independence Day
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 11, 9),   # Diwali (approx — verify)
}


def set_holidays(holidays: set[date]) -> None:
    global NSE_HOLIDAYS
    NSE_HOLIDAYS = set(holidays)


def now_ist() -> datetime:
    return datetime.now(IST)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NSE_HOLIDAYS


def is_market_open(dt: datetime | None = None) -> bool:
    dt = dt or now_ist()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return is_trading_day(dt.date()) and MARKET_OPEN <= dt.timetz().replace(tzinfo=None) <= MARKET_CLOSE
