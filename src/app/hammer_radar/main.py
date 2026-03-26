"""Runtime loop for the Hammer Radar v1 pipeline."""

from __future__ import annotations

from collections import deque
from datetime import datetime
import json
import time

from src.app.hammer_radar.hammer_detector import annotate_hammers
from src.app.hammer_radar.market_reader import MarketReader
from src.app.hammer_radar.operator import (
    SignalRecord,
    append_outcome,
    append_signal,
    build_setup_summary,
    decide_trade_candidate,
    evaluate_signal_on_next_candle,
    format_outcome_line,
    format_signal_operator_line,
    format_stats_summary,
    load_evaluated_signal_ids,
    load_outcomes,
    load_signals,
)
from src.app.hammer_radar.signal_engine import attach_bias, compute_bias_direction, extract_signal

TIMEFRAMES = (
    ("13min", "13m"),
    ("55min", "55m"),
)
RECENT_SIGNALS_LIMIT = 256
STATS_PRINT_INTERVAL_SECONDS = 300.0


def run(sleep_seconds: float = 3.0) -> None:
    """Start the reader and continuously print new hammer signals."""
    print("Hammer Radar started")
    reader = MarketReader()
    historical_signals = load_signals()
    seen_signal_keys = {
        (signal.timeframe, signal.timestamp, signal.direction)
        for signal in historical_signals
    }
    historical_outcomes = load_outcomes()
    evaluated_signal_ids = load_evaluated_signal_ids()
    recent_signals = deque(historical_signals[-RECENT_SIGNALS_LIMIT:], maxlen=RECENT_SIGNALS_LIMIT)
    pending_signals = {
        signal.signal_id: signal
        for signal in recent_signals
        if signal.timeframe == "13m" and signal.signal_id not in evaluated_signal_ids
    }
    last_stats_printed_at = 0.0
    last_stats_block: str | None = None

    try:
        reader.start()
        print("Reader started")
        print("Waiting for signals...")

        while True:
            try:
                dataframe_1m = reader.get_dataframe()
                if dataframe_1m.empty:
                    print("Waiting for market data...")
                else:
                    bias_direction = compute_bias_direction(reader.get_resampled("4h"))
                    resampled_frames: dict[str, object] = {}
                    for resample_rule, timeframe_label in TIMEFRAMES:
                        resampled = reader.get_resampled(resample_rule)
                        resampled_frames[timeframe_label] = resampled
                        annotated = annotate_hammers(resampled)
                        signal = extract_signal(annotated, "BTCUSDT", timeframe=timeframe_label)

                        if not signal:
                            continue
                        signal = attach_bias(signal, bias_direction=bias_direction, bias_timeframe="4H")

                        signal_key = (
                            signal.get("timeframe"),
                            signal.get("timestamp"),
                            signal.get("direction"),
                        )
                        if signal_key in seen_signal_keys:
                            continue

                        signal_record = _build_signal_record(signal, list(recent_signals))
                        append_signal(signal_record)
                        recent_signals.append(signal_record)
                        historical_signals.append(signal_record)
                        if signal_record.timeframe == "13m" and signal_record.signal_id not in evaluated_signal_ids:
                            pending_signals[signal_record.signal_id] = signal_record

                        print(format_signal_operator_line(signal_record))
                        print(json.dumps(signal_record.to_dict(), indent=2, sort_keys=True))
                        seen_signal_keys.add(signal_key)

                    newly_evaluated = _evaluate_pending_signals(
                        pending_signals=pending_signals,
                        resampled_13m=resampled_frames.get("13m"),
                        evaluated_signal_ids=evaluated_signal_ids,
                    )
                    for outcome in newly_evaluated:
                        append_outcome(outcome)
                        historical_outcomes.append(outcome)
                        print(format_outcome_line(outcome))

                    stats_block = _build_stats_block(historical_signals, historical_outcomes)
                    should_check_stats = bool(newly_evaluated) or (
                        (time.monotonic() - last_stats_printed_at) >= STATS_PRINT_INTERVAL_SECONDS
                    )
                    if should_check_stats and stats_block != last_stats_block:
                        print(stats_block)
                        last_stats_block = stats_block
                        last_stats_printed_at = time.monotonic()
            except Exception as error:
                print(f"Hammer Radar loop error: {error}")

            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("Stopping Hammer Radar...")
    finally:
        reader.stop()
        print("Hammer Radar stopped")


def _build_signal_record(signal: dict, recent_signals: list[SignalRecord]) -> SignalRecord:
    same_direction_streak, opposite_direction_streak = _compute_streaks(signal, recent_signals)
    signal_record = SignalRecord(
        signal_id=_build_signal_id(signal),
        symbol=str(signal["symbol"]),
        timeframe=str(signal["timeframe"]),
        direction=str(signal["direction"]),
        timestamp=str(signal["timestamp"]),
        hammer_strength=float(signal["hammer_strength"]),
        hammer_high=float(signal["hammer_high"]),
        hammer_low=float(signal["hammer_low"]),
        fib_50=float(signal["fib_50"]),
        fib_618=float(signal["fib_618"]),
        fib_650=float(signal["fib_650"]),
        fib_786=float(signal["fib_786"]),
        invalidation=float(signal["invalidation"]),
        bias_timeframe=str(signal.get("bias_timeframe", "")),
        bias_direction=str(signal.get("bias_direction", "neutral")),
        bias_aligned=bool(signal.get("bias_aligned")),
        same_direction_streak=same_direction_streak,
        opposite_direction_streak=opposite_direction_streak,
        tradable=False,
        reject_reason=None,
    )
    tradable, reject_reason = decide_trade_candidate(signal_record, recent_signals)
    signal_record.tradable = tradable
    signal_record.reject_reason = reject_reason
    return signal_record


def _compute_streaks(signal: dict, recent_signals: list[SignalRecord]) -> tuple[int, int]:
    same_direction_streak = 0
    opposite_direction_streak = 0
    timeframe = signal["timeframe"]
    direction = signal["direction"]

    for recent_signal in reversed(recent_signals):
        if recent_signal.timeframe != timeframe:
            continue
        if recent_signal.direction == direction:
            same_direction_streak += 1
            if opposite_direction_streak > 0:
                break
        else:
            opposite_direction_streak += 1
            if same_direction_streak > 0:
                break

    return same_direction_streak, opposite_direction_streak


def _build_signal_id(signal: dict) -> str:
    return f"{signal['symbol']}|{signal['timeframe']}|{signal['direction']}|{signal['timestamp']}"


def _evaluate_pending_signals(pending_signals: dict[str, SignalRecord], resampled_13m, evaluated_signal_ids: set[str]):
    if resampled_13m is None or getattr(resampled_13m, "empty", True):
        return []

    next_candle_by_signal_time = _build_next_candle_lookup(resampled_13m)
    newly_evaluated = []
    completed_signal_ids = []

    for signal_id, signal in pending_signals.items():
        if signal_id in evaluated_signal_ids:
            completed_signal_ids.append(signal_id)
            continue
        next_candle = next_candle_by_signal_time.get(signal.timestamp)
        if next_candle is None:
            continue
        outcome = evaluate_signal_on_next_candle(signal, next_candle)
        if outcome is None:
            completed_signal_ids.append(signal_id)
            continue
        evaluated_signal_ids.add(signal_id)
        newly_evaluated.append(outcome)
        completed_signal_ids.append(signal_id)

    for signal_id in completed_signal_ids:
        pending_signals.pop(signal_id, None)

    return newly_evaluated


def _build_next_candle_lookup(resampled_13m) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    if len(resampled_13m.index) < 2:
        return lookup

    for index in range(len(resampled_13m.index) - 1):
        current_row = resampled_13m.iloc[index]
        next_row = resampled_13m.iloc[index + 1]
        current_timestamp = _format_timestamp(current_row.get("close_time", current_row.get("open_time")))
        next_timestamp = _format_timestamp(next_row.get("close_time", next_row.get("open_time")))
        if current_timestamp is None or next_timestamp is None:
            continue
        lookup[current_timestamp] = {
            "open": float(next_row["open"]),
            "high": float(next_row["high"]),
            "low": float(next_row["low"]),
            "close": float(next_row["close"]),
            "timestamp": next_timestamp,
        }
    return lookup


def _format_timestamp(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        return datetime.fromisoformat(str(value)).isoformat()
    except ValueError:
        return str(value)


def _build_stats_block(signals: list[SignalRecord], outcomes: list) -> str:
    all_summary = build_setup_summary(signals, outcomes, tradable_only=False)
    tradable_summary = build_setup_summary(signals, outcomes, tradable_only=True)
    return "\n".join(
        [
            format_stats_summary(all_summary, top_n=5, label="all_evaluated_signals"),
            format_stats_summary(tradable_summary, top_n=5, label="tradable_only_signals"),
        ]
    )

if __name__ == "__main__":
    run()
