"""Strategy factory — pick the strategy from config (STRATEGY=orb|mean_reversion).

Keeps the live session and the validator in lock-step: both build the exact
same strategy from the same settings.
"""
from __future__ import annotations

from typing import Callable

from app.config import Settings
from app.strategies.base import Strategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.orb import ORBStrategy

_MR_NAMES = {"mr", "mean_reversion", "meanreversion"}


def build_strategy(settings: Settings, regime_fn: Callable[[], int] | None = None) -> Strategy:
    if settings.strategy.lower() in _MR_NAMES:
        return MeanReversionStrategy(
            entry_pct=settings.mr_entry_pct,
            stop_pct=settings.mr_stop_pct,
            warmup_minutes=settings.mr_warmup_minutes,
        )
    return ORBStrategy(
        opening_range_minutes=settings.orb_opening_range_minutes,
        target_r=settings.orb_target_r,
        min_range_pct=settings.orb_min_range_pct,
        max_range_pct=settings.orb_max_range_pct,
        volume_mult=settings.orb_volume_mult,
        breakout_buffer_pct=settings.orb_breakout_buffer_pct,
        anchor_first_bar=settings.orb_anchor_first_bar,
        regime=regime_fn,
    )


def uses_index(settings: Settings) -> bool:
    """The index/regime feed is only used by ORB; mean-reversion ignores it."""
    return settings.use_index_filter and settings.strategy.lower() not in _MR_NAMES
