"""Trade candidate gating for Hammer Radar operator signals."""

from __future__ import annotations

from datetime import datetime

from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.strategy_config import TIMEFRAME_MINUTES, load_strategy_config


def decide_trade_candidate(signal: SignalRecord, recent_signals: list[SignalRecord]) -> tuple[bool, str | None]:
    strategy_config = load_strategy_config()
    if signal.timeframe not in strategy_config.enabled_timeframes:
        return False, "timeframe_not_enabled"
    if signal.hammer_strength < strategy_config.minimum_hammer_strength:
        return False, "strength_below_minimum"
    if strategy_config.require_bias_alignment and not signal.bias_aligned:
        return False, "bias_not_aligned"
    if _has_recent_same_direction_signal(
        signal,
        recent_signals,
        max_recent_same_direction_gap=strategy_config.max_recent_same_direction_gap,
    ):
        return False, "same_direction_recent"
    return True, None


def _has_recent_same_direction_signal(
    signal: SignalRecord,
    recent_signals: list[SignalRecord],
    *,
    max_recent_same_direction_gap: int,
) -> bool:
    timeframe_minutes = TIMEFRAME_MINUTES.get(signal.timeframe)
    if timeframe_minutes is None:
        return False
    if max_recent_same_direction_gap <= 0:
        return False

    signal_time = _parse_timestamp(signal.timestamp)
    if signal_time is None:
        return False

    for recent_signal in reversed(recent_signals):
        if recent_signal.timeframe != signal.timeframe:
            continue
        if recent_signal.direction != signal.direction:
            continue
        recent_time = _parse_timestamp(recent_signal.timestamp)
        if recent_time is None or recent_time >= signal_time:
            continue

        candle_gap = (signal_time - recent_time).total_seconds() / (timeframe_minutes * 60.0)
        if candle_gap <= float(max_recent_same_direction_gap):
            return True
        if candle_gap > float(max_recent_same_direction_gap):
            return False
    return False


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
