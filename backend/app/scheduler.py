"""Market-hours orchestration.

Runs the agent autonomously every trading day:
  - 09:14 IST  start the live feed + session (if it's a trading day and we have a token)
  - 15:15 IST  force-flatten all positions (mandatory square-off)
  - 15:31 IST  stop the feed and persist the day to the journal

Weekends/holidays are skipped via the market calendar. Times are IST.
"""
from __future__ import annotations

import threading
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.market_calendar import IST, is_trading_day, now_ist
from app.trading.runner import LiveRunner


class MarketScheduler:
    def __init__(self, runner: LiveRunner, on_day_end: Callable | None = None):
        self.runner = runner
        self.on_day_end = on_day_end
        self.sched = BackgroundScheduler(timezone=IST)

    def start(self) -> None:
        weekdays = {"day_of_week": "mon-fri"}
        self.sched.add_job(self._start_day, CronTrigger(hour=9, minute=14, **weekdays))
        self.sched.add_job(self._square_off, CronTrigger(hour=15, minute=15, **weekdays))
        self.sched.add_job(self._end_day, CronTrigger(hour=15, minute=31, **weekdays))
        self.sched.start()

    def shutdown(self) -> None:
        if self.sched.running:
            self.sched.shutdown(wait=False)

    # --- jobs ---------------------------------------------------------------
    def _start_day(self) -> None:
        if not is_trading_day(now_ist().date()):
            return
        if not get_settings().upstox_access_token:
            return  # can't stream without auth; daily login required
        if not self.runner.running:
            threading.Thread(target=self.runner.start, daemon=True).start()

    def _square_off(self) -> None:
        if is_trading_day(now_ist().date()):
            self.runner.session.flatten_all("square_off")

    def _end_day(self) -> None:
        if not is_trading_day(now_ist().date()):
            return
        self.runner.stop()
        if self.on_day_end is not None:
            self.on_day_end(self.runner.session)
