"""Runtime loop for the Hammer Radar v1 pipeline."""

from __future__ import annotations

from collections import deque
from datetime import datetime
import json
import time

from src.app.hammer_radar.execution import get_execution_adapter, get_execution_mode
from src.app.hammer_radar.hammer_detector import annotate_hammers
from src.app.hammer_radar.market_reader import MarketReader
from src.app.hammer_radar.operator.context import (
    compute_ema,
    compute_price_vs_ema_pct,
    compute_trend_direction,
    compute_trend_strength_score,
)
from src.app.hammer_radar.operator import (
    SignalRecord,
    append_outcome,
    append_signal,
    build_setup_summary,
    decide_trade_candidate,
    evaluate_open_positions,
    evaluate_signal_all_entry_modes,
    format_outcome_line,
    format_paper_close_line,
    format_paper_open_line,
    format_signal_operator_line,
    format_stats_summary,
    load_open_positions,
    load_evaluated_outcome_keys,
    load_outcomes,
    load_signals,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_candle_capture import capture_resampled_frames
from src.app.hammer_radar.operator.strategy_config import TIMEFRAME_CONFIGS, load_strategy_config
from src.app.hammer_radar.signal_engine import attach_bias, compute_bias_direction, extract_signal

TIMEFRAMES = TIMEFRAME_CONFIGS
RECENT_SIGNALS_LIMIT = 256
STATS_PRINT_INTERVAL_SECONDS = 300.0
TREND_LOOKBACK_CANDLES = 3


def run(sleep_seconds: float = 3.0) -> None:
    """Start the reader and continuously print new hammer signals."""
    log_dir = get_log_dir(use_env=True)
    print("Hammer Radar started")
    print(f"Hammer Radar archive_log_dir={log_dir}")
    reader = MarketReader()
    execution_adapter = get_execution_adapter(get_execution_mode(), log_dir=log_dir)
    print(f"Hammer Radar execution_mode={execution_adapter.mode} paper_only=true")
    strategy_config = load_strategy_config()
    historical_signals = load_signals(log_dir)
    seen_signal_keys = {
        (signal.timeframe, signal.timestamp, signal.direction)
        for signal in historical_signals
    }
    historical_outcomes = load_outcomes(log_dir)
    evaluated_outcome_keys = load_evaluated_outcome_keys(log_dir)
    open_positions = {position.position_id: position for position in load_open_positions(log_dir)}
    recent_signals = deque(historical_signals[-RECENT_SIGNALS_LIMIT:], maxlen=RECENT_SIGNALS_LIMIT)
    pending_signals = {
        signal.signal_id: signal
        for signal in recent_signals
        if signal.timeframe in {timeframe_label for _, timeframe_label in TIMEFRAMES}
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
                    resampled_frames: dict[str, object] = {
                        timeframe_label: reader.get_resampled(resample_rule)
                        for resample_rule, timeframe_label in TIMEFRAMES
                    }
                    capture_resampled_frames(resampled_frames, symbol="BTCUSDT", log_dir=log_dir)
                    for _resample_rule, timeframe_label in TIMEFRAMES:
                        resampled = resampled_frames[timeframe_label]
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

                        signal_record = _build_signal_record(
                            signal,
                            recent_signals=list(recent_signals),
                            signal_frame=resampled,
                            ema_4h_frame=resampled_frames.get("4H"),
                            trend_lookback_candles=TREND_LOOKBACK_CANDLES,
                        )
                        append_signal(signal_record, log_dir=log_dir)
                        recent_signals.append(signal_record)
                        historical_signals.append(signal_record)
                        if signal_record.timeframe in resampled_frames:
                            pending_signals[signal_record.signal_id] = signal_record

                        print(format_signal_operator_line(signal_record))
                        print(json.dumps(signal_record.to_dict(), indent=2, sort_keys=True))
                        if signal_record.tradable and strategy_config.paper_enabled:
                            order_result = execution_adapter.place_order(signal_record)
                            paper_position = order_result.position
                            if paper_position is not None:
                                open_positions[paper_position.position_id] = paper_position
                                print(format_paper_open_line(paper_position))
                        seen_signal_keys.add(signal_key)

                    newly_evaluated = _evaluate_pending_signals(
                        pending_signals=pending_signals,
                        resampled_frames=resampled_frames,
                        evaluated_outcome_keys=evaluated_outcome_keys,
                    )
                    for outcome in newly_evaluated:
                        append_outcome(outcome, log_dir=log_dir)
                        historical_outcomes.append(outcome)
                        print(format_outcome_line(outcome))

                    latest_candles_by_timeframe = _build_latest_candle_lookup(resampled_frames)
                    closed_positions = evaluate_open_positions(
                        list(open_positions.values()),
                        latest_candles_by_timeframe=latest_candles_by_timeframe,
                        log_dir=log_dir,
                    )
                    for position in closed_positions:
                        open_positions.pop(position.position_id, None)
                        print(format_paper_close_line(position))

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


def _build_signal_record(
    signal: dict,
    recent_signals: list[SignalRecord],
    signal_frame,
    ema_4h_frame,
    trend_lookback_candles: int,
) -> SignalRecord:
    same_direction_streak, opposite_direction_streak = _compute_streaks(signal, recent_signals)
    signal_close = _extract_signal_close(signal_frame, str(signal["timestamp"]))
    ema_4h_20 = _extract_relevant_ema_4h(ema_4h_frame, str(signal["timestamp"]))
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
        trend_direction=_safe_compute_trend_direction(signal_frame, trend_lookback_candles),
        trend_strength_score=compute_trend_strength_score(signal_frame, lookback=trend_lookback_candles),
        trend_lookback_candles=trend_lookback_candles,
        ema_4h_20=ema_4h_20,
        price_vs_ema_4h_pct=compute_price_vs_ema_pct(signal_close, ema_4h_20),
        signal_close=signal_close,
        rsi_length=_extract_nested_value(signal, "rsi", "length"),
        rsi_value=_extract_nested_value(signal, "rsi", "value"),
        rsi_state=_extract_nested_value(signal, "rsi", "state"),
        divergence_type=_extract_nested_value(signal, "divergence", "type"),
        divergence_confirmed=bool(_extract_nested_value(signal, "divergence", "confirmed")),
        divergence_price_pivot_1=_extract_nested_value(signal, "divergence", "price_pivot_1"),
        divergence_price_pivot_2=_extract_nested_value(signal, "divergence", "price_pivot_2"),
        divergence_rsi_pivot_1=_extract_nested_value(signal, "divergence", "rsi_pivot_1"),
        divergence_rsi_pivot_2=_extract_nested_value(signal, "divergence", "rsi_pivot_2"),
        extreme_trigger=bool(signal.get("extreme_trigger")),
        critical_trigger=bool(signal.get("critical_trigger")),
        micro_scalp_candidate=bool(signal.get("micro_scalp_candidate")),
        requires_human_approval=bool(signal.get("requires_human_approval")),
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


def _extract_nested_value(signal: dict, section: str, key: str):
    container = signal.get(section)
    if not isinstance(container, dict):
        return None
    return container.get(key)


def _evaluate_pending_signals(
    pending_signals: dict[str, SignalRecord],
    resampled_frames: dict[str, object],
    evaluated_outcome_keys: set[tuple[str, str]],
):
    next_candle_by_timeframe = {
        timeframe: _build_next_candle_lookup(frame)
        for timeframe, frame in resampled_frames.items()
    }
    signal_candle_by_timeframe = {
        timeframe: _build_signal_candle_lookup(frame)
        for timeframe, frame in resampled_frames.items()
    }

    newly_evaluated = []
    completed_signal_ids = []

    for signal_id, signal in pending_signals.items():
        next_candle_by_signal_time = next_candle_by_timeframe.get(signal.timeframe, {})
        next_candle = next_candle_by_signal_time.get(signal.timestamp)
        if next_candle is None:
            continue
        signal_candle = signal_candle_by_timeframe.get(signal.timeframe, {}).get(signal.timestamp)
        outcomes = evaluate_signal_all_entry_modes(
            signal,
            next_candle,
            signal_candle=signal_candle,
        )
        for outcome in outcomes:
            outcome_key = (outcome.signal_id, outcome.entry_mode)
            if outcome_key in evaluated_outcome_keys:
                continue
            evaluated_outcome_keys.add(outcome_key)
            newly_evaluated.append(outcome)
        completed_signal_ids.append(signal_id)

    for signal_id in completed_signal_ids:
        pending_signals.pop(signal_id, None)

    return newly_evaluated


def _build_next_candle_lookup(resampled_frame) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    if resampled_frame is None or getattr(resampled_frame, "empty", True):
        return lookup
    if len(resampled_frame.index) < 2:
        return lookup

    for index in range(len(resampled_frame.index) - 1):
        current_row = resampled_frame.iloc[index]
        next_row = resampled_frame.iloc[index + 1]
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


def _build_latest_candle_lookup(resampled_frames: dict[str, object]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for timeframe, frame in resampled_frames.items():
        if frame is None or getattr(frame, "empty", True):
            continue
        row = frame.iloc[-1]
        timestamp = _format_timestamp(row.get("close_time", row.get("open_time")))
        if timestamp is None:
            continue
        latest[timeframe] = {
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "timestamp": timestamp,
        }
    return latest


def _build_signal_candle_lookup(resampled_frame) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    if resampled_frame is None or getattr(resampled_frame, "empty", True):
        return lookup

    for index in range(len(resampled_frame.index)):
        row = resampled_frame.iloc[index]
        timestamp = _format_timestamp(row.get("close_time", row.get("open_time")))
        if timestamp is None:
            continue
        lookup[timestamp] = {
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "timestamp": timestamp,
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


def _safe_compute_trend_direction(signal_frame, lookback: int) -> str | None:
    if signal_frame is None or getattr(signal_frame, "empty", True):
        return None
    if len(signal_frame.index) < (max(lookback, 1) + 1):
        return None
    return compute_trend_direction(signal_frame, lookback=lookback)


def _extract_signal_close(signal_frame, signal_timestamp: str) -> float | None:
    signal_candle = _build_signal_candle_lookup(signal_frame).get(signal_timestamp)
    if signal_candle is None:
        return None
    return float(signal_candle["close"])


def _extract_relevant_ema_4h(ema_4h_frame, signal_timestamp: str) -> float | None:
    if ema_4h_frame is None or getattr(ema_4h_frame, "empty", True):
        return None
    if len(ema_4h_frame.index) < 20:
        return None
    ema_series = compute_ema(ema_4h_frame["close"], span=20)
    if getattr(ema_series, "empty", True):
        return None
    signal_time = datetime.fromisoformat(signal_timestamp)
    relevant_index = None
    for index in range(len(ema_4h_frame.index)):
        row = ema_4h_frame.iloc[index]
        row_timestamp = _format_timestamp(row.get("close_time", row.get("open_time")))
        if row_timestamp is None:
            continue
        row_time = datetime.fromisoformat(row_timestamp)
        if row_time <= signal_time:
            relevant_index = index
        else:
            break
    if relevant_index is None:
        return None
    return round(float(ema_series.iloc[relevant_index]), 4)

if __name__ == "__main__":
    run()
