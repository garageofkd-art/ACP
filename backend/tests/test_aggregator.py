from datetime import datetime

from app.core.events import Bar, Tick
from app.data.aggregator import BarAggregator


def test_emits_bar_on_minute_rollover():
    bars: list[Bar] = []
    agg = BarAggregator(bars.append, interval_seconds=60)

    base = datetime(2026, 6, 1, 9, 15, 0)
    # Three ticks in the 09:15 minute.
    agg.on_tick(Tick("TEST", base.replace(second=1), 100.0, 10))
    agg.on_tick(Tick("TEST", base.replace(second=20), 101.0, 5))
    agg.on_tick(Tick("TEST", base.replace(second=50), 99.5, 5))
    assert bars == []  # bar not closed yet

    # Tick in the next minute closes the 09:15 bar.
    agg.on_tick(Tick("TEST", datetime(2026, 6, 1, 9, 16, 2), 100.2, 3))
    assert len(bars) == 1
    bar = bars[0]
    assert bar.ts == base
    assert bar.open == 100.0
    assert bar.high == 101.0
    assert bar.low == 99.5
    assert bar.close == 99.5
    assert bar.volume == 20


def test_flush_finalizes_in_progress_bar():
    bars: list[Bar] = []
    agg = BarAggregator(bars.append)
    agg.on_tick(Tick("TEST", datetime(2026, 6, 1, 9, 15, 1), 100.0, 7))
    agg.flush()
    assert len(bars) == 1
    assert bars[0].close == 100.0


def test_multiple_symbols_tracked_independently():
    bars: list[Bar] = []
    agg = BarAggregator(bars.append)
    agg.on_tick(Tick("A", datetime(2026, 6, 1, 9, 15, 1), 10.0, 1))
    agg.on_tick(Tick("B", datetime(2026, 6, 1, 9, 15, 1), 20.0, 1))
    agg.flush()
    assert {b.symbol for b in bars} == {"A", "B"}
