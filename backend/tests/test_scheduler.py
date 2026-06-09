from app.api.main import STATE
from app.scheduler import MarketScheduler


def test_scheduler_registers_daily_jobs():
    sched = MarketScheduler(STATE.runner)
    sched.start()
    try:
        # token refresh, start-day, square-off, end-day, monthly compounding.
        assert len(sched.sched.get_jobs()) == 5
    finally:
        sched.shutdown()


def test_start_day_noop_without_token():
    # No token in the test env -> _start_day must not launch the runner.
    sched = MarketScheduler(STATE.runner)
    sched._start_day()
    assert STATE.runner.running is False
