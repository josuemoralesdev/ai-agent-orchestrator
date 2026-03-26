"""Trade candidate gating for Hammer Radar operator signals."""

from __future__ import annotations

from datetime import datetime

from src.app.hammer_radar.operator.models import SignalRecord

TIMEFRAME_MINUTES = {
    "13m": 13,
    "55m": 55,
}


def decide_trade_candidate(signal: SignalRecord, recent_signals: list[SignalRecord]) -> tuple[bool, str | None]:
    if signal.timeframe != "13m":
        return False, "timeframe_not_enabled"
    if signal.hammer_strength < 85.0:
        return False, "strength_below_85"
    if not signal.bias_aligned:
        return False, "bias_not_aligned"
    if _has_recent_same_direction_signal(signal, recent_signals):
        return False, "same_direction_recent"
    return True, None


def _has_recent_same_direction_signal(signal: SignalRecord, recent_signals: list[SignalRecord]) -> bool:
    timeframe_minutes = TIMEFRAME_MINUTES.get(signal.timeframe)
    if timeframe_minutes is None:
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
        if candle_gap <= 2.0:
            return True
        if candle_gap > 2.0:
            return False
    return False


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
