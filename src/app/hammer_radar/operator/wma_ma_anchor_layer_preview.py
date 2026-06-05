"""R199 WMA / MA anchor layer preview.

This module is a local, paper-only research surface. It reads local candle
archives, computes SMA/WMA anchors, maps anchor interactions to future windows,
and summarizes candidate anchors. It never calls Binance/network, mutates
env/config, creates payloads, promotes lanes/origins, or authorizes live.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_harvester_expansion import DEFAULT_EXPANDED_TIMEFRAMES
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.local_candle_feed_adapter import (
    DEFAULT_LATEST_CANDLES,
    MAX_LATEST_CANDLES,
    load_local_candle_feed,
    normalize_local_candle_feed,
    resolve_local_candle_feed_path,
    validate_normalized_candle_feed,
)
from src.app.hammer_radar.operator.pattern_detector_family_expansion import (
    LEDGER_FILENAME as PATTERN_FAMILY_LEDGER_FILENAME,
)
from src.app.hammer_radar.operator.three_black_crows_local_feed_detection import (
    LEDGER_FILENAME as THREE_BLACK_CROWS_LEDGER_FILENAME,
)

WMA_MA_ANCHOR_LAYER_PREVIEW_READY = "WMA_MA_ANCHOR_LAYER_PREVIEW_READY"
WMA_MA_ANCHOR_LAYER_PREVIEW_REJECTED = "WMA_MA_ANCHOR_LAYER_PREVIEW_REJECTED"
WMA_MA_ANCHOR_LAYER_PREVIEW_RECORDED = "WMA_MA_ANCHOR_LAYER_PREVIEW_RECORDED"
WMA_MA_ANCHOR_LAYER_PREVIEW_BLOCKED = "WMA_MA_ANCHOR_LAYER_PREVIEW_BLOCKED"
WMA_MA_ANCHOR_LAYER_PREVIEW_ERROR = "WMA_MA_ANCHOR_LAYER_PREVIEW_ERROR"

ANCHOR_EVENTS_FOUND = "ANCHOR_EVENTS_FOUND"
ANCHOR_EVENTS_NOT_FOUND = "ANCHOR_EVENTS_NOT_FOUND"
INSUFFICIENT_CANDLES_FOR_ANCHOR = "INSUFFICIENT_CANDLES_FOR_ANCHOR"
LOCAL_CANDLE_FEED_MISSING = "LOCAL_CANDLE_FEED_MISSING"
ANCHOR_OUTCOME_MAPPING_AVAILABLE = "ANCHOR_OUTCOME_MAPPING_AVAILABLE"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

SMA200 = "SMA200"
WMA200 = "WMA200"
CUSTOM_WMA = "custom_wma"
ANCHOR_TYPES = (SMA200, WMA200, CUSTOM_WMA)
DEFAULT_ANCHOR_PERIODS = (13, 21, 34, 55, 89, 144, 200, 233, 377, 610, 888)
DEFAULT_TIMEFRAMES = (*DEFAULT_EXPANDED_TIMEFRAMES,)
PRIORITY_TIMEFRAMES = ("13D", "4H", "666m", "13H", "888m", "8m", "4m")
DEFAULT_OUTCOME_WINDOWS = (1, 3, 5, 10, 21)
DEFAULT_NEAR_TOUCH_THRESHOLD_PCT = 0.15
DEFAULT_SUCCESS_THRESHOLD_PCT = 0.10
DEFAULT_ADVERSE_THRESHOLD_PCT = 0.10
DEFAULT_SYMBOL = "BTCUSDT"
EVENT_TYPE = "WMA_MA_ANCHOR_LAYER_PREVIEW"
LEDGER_FILENAME = "wma_ma_anchor_layer_preview.ndjson"
CONFIRM_WMA_MA_ANCHOR_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM WMA MA ANCHOR LAYER PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "registry_config_written": False,
    "scoring_config_written": False,
    "matrix_config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
    "live_authorization_created": False,
    "signal_origin_promoted": False,
    "lane_promoted": False,
    "anchor_live_authorized": False,
    "anchor_position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "operator.local_candle_feed_adapter.resolve_local_candle_feed_path",
    "operator.local_candle_feed_adapter.load_local_candle_feed",
    "operator.local_candle_feed_adapter.normalize_local_candle_feed",
    "logs/hammer_radar_forward/candle_archive/{symbol}_{timeframe}.ndjson",
    f"logs/hammer_radar_forward/{PATTERN_FAMILY_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{THREE_BLACK_CROWS_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_wma_ma_anchor_layer_preview(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframes: Sequence[str] | str | None = None,
    periods: Sequence[int] | str | None = None,
    near_touch_threshold_pct: float = DEFAULT_NEAR_TOUCH_THRESHOLD_PCT,
    success_threshold_pct: float = DEFAULT_SUCCESS_THRESHOLD_PCT,
    adverse_threshold_pct: float = DEFAULT_ADVERSE_THRESHOLD_PCT,
    record_preview: bool = False,
    confirm_wma_ma_anchor_preview: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    normalized_periods = _normalize_periods(periods)
    discovered = discover_anchor_candle_sources(
        log_dir=resolved_log_dir,
        symbol=normalized_symbol,
        requested_timeframes=timeframes,
        periods=normalized_periods,
    )
    normalized_timeframes = list(discovered["timeframes"])
    near_touch_threshold = _bounded_float(near_touch_threshold_pct, DEFAULT_NEAR_TOUCH_THRESHOLD_PCT)
    success_threshold = _bounded_float(success_threshold_pct, DEFAULT_SUCCESS_THRESHOLD_PCT)
    adverse_threshold = _bounded_float(adverse_threshold_pct, DEFAULT_ADVERSE_THRESHOLD_PCT)
    confirmation_valid = confirm_wma_ma_anchor_preview == CONFIRM_WMA_MA_ANCHOR_PREVIEW_RECORDING_PHRASE
    try:
        all_events: list[dict[str, Any]] = []
        source_rows: list[dict[str, Any]] = []
        for timeframe in normalized_timeframes:
            candles = load_anchor_candles(log_dir=resolved_log_dir, symbol=normalized_symbol, timeframe=timeframe)
            source_path = resolve_local_candle_feed_path(log_dir=resolved_log_dir, symbol=normalized_symbol, timeframe=timeframe)
            validation = validate_normalized_candle_feed(
                source_path=source_path,
                normalized_candles=candles,
                symbol=normalized_symbol,
                timeframe=timeframe,
                latest_candles=MAX_LATEST_CANDLES,
            )
            enough = [period for period in normalized_periods if len(candles) >= period]
            source_rows.append(
                {
                    "symbol": normalized_symbol,
                    "timeframe": timeframe,
                    "source_path": f"logs/hammer_radar_forward/candle_archive/{normalized_symbol}_{timeframe}.ndjson",
                    "source_found": bool(validation.get("source_found")),
                    "records_loaded": len(candles),
                    "enough_for_periods": enough,
                    "anchor_status": _source_anchor_status(source_found=bool(validation.get("source_found")), candles=len(candles), periods=normalized_periods),
                }
            )
            anchor_series = compute_anchor_series(candles, periods=normalized_periods)
            all_events.extend(
                build_anchor_event_candidates(
                    candles,
                    anchor_series,
                    symbol=normalized_symbol,
                    timeframe=timeframe,
                    near_touch_threshold_pct=near_touch_threshold,
                )
            )
        mapped_events = map_anchor_event_outcomes(
            all_events,
            candles_by_timeframe={
                row["timeframe"]: load_anchor_candles(log_dir=resolved_log_dir, symbol=normalized_symbol, timeframe=row["timeframe"])
                for row in source_rows
                if row["source_found"]
            },
            windows=DEFAULT_OUTCOME_WINDOWS,
            success_threshold_pct=success_threshold,
            adverse_threshold_pct=adverse_threshold,
        )
        event_summary = _build_anchor_event_summary(all_events)
        outcome_summary = build_anchor_outcome_summary(mapped_events)
        overlay = build_anchor_signal_origin_overlay(
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            timeframes=normalized_timeframes,
            anchor_events=all_events,
        )
        ranking = build_anchor_candidate_ranking(mapped_events)
        next_actions = build_anchor_layer_next_actions(outcome_summary=outcome_summary, overlay=overlay, ranking=ranking)
        anchor_status = _overall_anchor_status(source_rows, all_events, mapped_events)
        status = _status_for_preview(record_preview=record_preview, confirmation_valid=confirmation_valid, anchor_status=anchor_status)
        payload = {
            "status": status,
            "anchor_status": anchor_status,
            "generated_at": generated_at.isoformat(),
            "preview_recorded": False,
            "preview_id": None,
            "record_preview_requested": bool(record_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "symbol": normalized_symbol,
                "timeframes": normalized_timeframes,
                "anchor_types": list(ANCHOR_TYPES),
                "anchor_periods": normalized_periods,
            },
            "thresholds": {
                "near_touch_threshold_pct": near_touch_threshold,
                "outcome_windows": list(DEFAULT_OUTCOME_WINDOWS),
                "success_threshold_pct": success_threshold,
                "adverse_threshold_pct": adverse_threshold,
            },
            "candle_source_summary": build_candle_source_summary(source_rows, requested_timeframes=normalized_timeframes),
            "anchor_event_summary": event_summary,
            "anchor_outcome_summary": outcome_summary,
            "anchor_signal_origin_overlay": overlay,
            "anchor_candidate_ranking": ranking,
            "anchor_layer_next_actions": next_actions,
            "recommended_next_operator_move": _recommended_next_operator_move(ranking, outcome_summary),
            "recommended_next_engineering_move": _recommended_next_engineering_move(ranking, outcome_summary),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_preview and confirmation_valid and status != WMA_MA_ANCHOR_LAYER_PREVIEW_BLOCKED:
            record = append_wma_ma_anchor_preview_record(payload, log_dir=resolved_log_dir)
            payload["status"] = WMA_MA_ANCHOR_LAYER_PREVIEW_RECORDED
            payload["preview_recorded"] = True
            payload["preview_id"] = record["preview_id"]
            payload["ledger_path"] = str(wma_ma_anchor_preview_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": WMA_MA_ANCHOR_LAYER_PREVIEW_ERROR,
                "anchor_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "generated_at": generated_at.isoformat(),
                "preview_recorded": False,
                "preview_id": None,
                "record_preview_requested": bool(record_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "symbol": normalized_symbol,
                    "timeframes": normalized_timeframes,
                    "anchor_types": list(ANCHOR_TYPES),
                    "anchor_periods": normalized_periods,
                },
                "candle_source_summary": build_candle_source_summary([], requested_timeframes=normalized_timeframes),
                "anchor_event_summary": _build_anchor_event_summary([]),
                "anchor_outcome_summary": build_anchor_outcome_summary([]),
                "anchor_signal_origin_overlay": {"overlap_records_found": 0, "top_overlaps": [], "notes": ["R199 preview errored before overlay mapping."]},
                "anchor_candidate_ranking": [],
                "anchor_layer_next_actions": build_anchor_layer_next_actions(),
                "recommended_next_operator_move": "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R199 anchor preview error and rerun without network.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def discover_anchor_candle_sources(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    requested_timeframes: Sequence[str] | str | None = None,
    periods: Sequence[int] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    explicit = _normalize_timeframes(requested_timeframes)
    discovered = []
    archive_dir = resolved_log_dir / "candle_archive"
    if archive_dir.exists():
        prefix = f"{normalized_symbol}_"
        for path in archive_dir.glob(f"{prefix}*.ndjson"):
            timeframe = path.stem[len(prefix) :]
            if timeframe and timeframe not in discovered:
                discovered.append(timeframe)
    timeframes = _ordered_timeframes([*explicit, *discovered])
    source_rows = []
    max_period = max(periods or DEFAULT_ANCHOR_PERIODS)
    for timeframe in timeframes:
        path = resolve_local_candle_feed_path(log_dir=resolved_log_dir, symbol=normalized_symbol, timeframe=timeframe)
        count = _count_lines(path)
        source_rows.append(
            {
                "symbol": normalized_symbol,
                "timeframe": timeframe,
                "path": f"logs/hammer_radar_forward/candle_archive/{normalized_symbol}_{timeframe}.ndjson",
                "source_found": path.exists(),
                "available_records": count,
                "enough_for_max_period": count >= max_period,
            }
        )
    return {"symbol": normalized_symbol, "timeframes": timeframes, "sources": source_rows}


def load_anchor_candles(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = "8m",
    latest_candles: int = MAX_LATEST_CANDLES,
) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    source_path = resolve_local_candle_feed_path(log_dir=resolved_log_dir, symbol=normalized_symbol, timeframe=timeframe)
    raw = load_local_candle_feed(source_path, latest_candles=_bounded_int(latest_candles, 1, MAX_LATEST_CANDLES, DEFAULT_LATEST_CANDLES))
    candles = normalize_local_candle_feed(
        raw,
        symbol=normalized_symbol,
        timeframe=str(timeframe),
        source=source_path.name,
        latest_candles=latest_candles,
    )
    return _sorted_candles(candles)


def compute_sma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    window = [float(value) for value in values[-period:]]
    return _round(sum(window) / period)


def compute_wma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    window = [float(value) for value in values[-period:]]
    weights = list(range(1, period + 1))
    denominator = sum(weights)
    return _round(sum(value * weight for value, weight in zip(window, weights)) / denominator)


def compute_anchor_series(candles: Sequence[Mapping[str, Any]], *, periods: Sequence[int] | None = None) -> dict[str, list[dict[str, Any]]]:
    normalized_periods = _normalize_periods(periods)
    closes = [_to_float(candle.get("close")) for candle in candles]
    close_values = [float(value) for value in closes if value is not None]
    series: dict[str, list[dict[str, Any]]] = {}
    for anchor_type, period in _anchor_specs(normalized_periods):
        key = _anchor_key(anchor_type, period)
        rows = []
        for index in range(len(close_values)):
            values = close_values[: index + 1]
            anchor = compute_sma(values, period) if anchor_type == SMA200 else compute_wma(values, period)
            rows.append({"index": index, "anchor": anchor, "anchor_type": anchor_type, "period": period})
        series[key] = rows
    return series


def build_anchor_event_candidates(
    candles: Sequence[Mapping[str, Any]],
    anchor_series: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = "8m",
    near_touch_threshold_pct: float = DEFAULT_NEAR_TOUCH_THRESHOLD_PCT,
) -> list[dict[str, Any]]:
    rows = _sorted_candles(candles)
    events: list[dict[str, Any]] = []
    for key, series in anchor_series.items():
        previous_candle = None
        previous_anchor = None
        for index, candle in enumerate(rows):
            anchor_row = series[index] if index < len(series) else {}
            anchor = _to_float(anchor_row.get("anchor"))
            if anchor is None:
                previous_candle = candle
                previous_anchor = None
                continue
            interaction = classify_anchor_interaction(
                candle,
                anchor=anchor,
                previous_candle=previous_candle,
                previous_anchor=previous_anchor,
                near_touch_threshold_pct=near_touch_threshold_pct,
            )
            interaction_types = [
                name
                for name in ("touch", "near_touch", "cross_up", "cross_down", "rejection_up", "rejection_down", "reclaim", "loss")
                if interaction.get(name) is True
            ]
            for interaction_type in interaction_types:
                events.append(
                    {
                        "event_id": f"r199_anchor_event_{uuid4().hex}",
                        "symbol": str(symbol or DEFAULT_SYMBOL).upper(),
                        "timeframe": timeframe,
                        "anchor_type": anchor_row.get("anchor_type"),
                        "period": int(anchor_row.get("period") or 0),
                        "anchor_key": key,
                        "candle_index": index,
                        "event_time": _candle_time(candle),
                        "interaction": interaction_type,
                        "direction_bias": _direction_bias(interaction_type),
                        "anchor": anchor,
                        "close": _to_float(candle.get("close")),
                        "close_distance_pct": interaction["close_distance_pct"],
                        "high_distance_pct": interaction["high_distance_pct"],
                        "low_distance_pct": interaction["low_distance_pct"],
                        "paper_only": True,
                        "live_authorized": False,
                    }
                )
            previous_candle = candle
            previous_anchor = anchor
    return events


def classify_anchor_interaction(
    candle: Mapping[str, Any],
    *,
    anchor: float,
    previous_candle: Mapping[str, Any] | None = None,
    previous_anchor: float | None = None,
    near_touch_threshold_pct: float = DEFAULT_NEAR_TOUCH_THRESHOLD_PCT,
) -> dict[str, Any]:
    close = float(candle["close"])
    high = float(candle["high"])
    low = float(candle["low"])
    close_distance = _pct(close, anchor)
    high_distance = _pct(high, anchor)
    low_distance = _pct(low, anchor)
    touched = low <= anchor <= high
    near_touch = abs(close_distance) <= near_touch_threshold_pct
    above = close > anchor
    below = close < anchor
    prev_close = _to_float((previous_candle or {}).get("close"))
    cross_up = previous_anchor is not None and prev_close is not None and prev_close < previous_anchor and close > anchor
    cross_down = previous_anchor is not None and prev_close is not None and prev_close > previous_anchor and close < anchor
    rejection_down = high >= anchor and close < anchor
    rejection_up = low <= anchor and close > anchor
    return {
        "close_distance_pct": close_distance,
        "high_distance_pct": high_distance,
        "low_distance_pct": low_distance,
        "touched_anchor": touched,
        "touch": touched,
        "near_touch": near_touch,
        "above_anchor": above,
        "below_anchor": below,
        "cross_up": cross_up,
        "cross_down": cross_down,
        "rejection_down": rejection_down,
        "rejection_up": rejection_up,
        "reclaim": cross_up,
        "loss": cross_down,
    }


def map_anchor_event_outcomes(
    anchor_events: Sequence[Mapping[str, Any]],
    *,
    candles_by_timeframe: Mapping[str, Sequence[Mapping[str, Any]]],
    windows: Sequence[int] = DEFAULT_OUTCOME_WINDOWS,
    success_threshold_pct: float = DEFAULT_SUCCESS_THRESHOLD_PCT,
    adverse_threshold_pct: float = DEFAULT_ADVERSE_THRESHOLD_PCT,
) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for event in anchor_events:
        bias = str(event.get("direction_bias") or "neutral")
        if bias == "neutral":
            continue
        timeframe = str(event.get("timeframe") or "")
        candles = list(candles_by_timeframe.get(timeframe) or [])
        index = int(event.get("candle_index") or 0)
        entry = _to_float(event.get("close"))
        if entry is None or index >= len(candles) - 1:
            continue
        future = candles[index + 1 :]
        window_map = _compute_directional_outcome_windows(
            entry_reference_price=entry,
            future_candles=future,
            direction_bias=bias,
            windows=windows,
            success_threshold_pct=success_threshold_pct,
            adverse_threshold_pct=adverse_threshold_pct,
        )
        if not window_map:
            continue
        mapped.append(
            {
                **dict(event),
                "outcome_mapping_status": ANCHOR_OUTCOME_MAPPING_AVAILABLE,
                "windows": window_map,
                "paper_only": True,
                "live_authorized": False,
                "anchor_position_permission_created": False,
            }
        )
    return _sanitize(mapped)


def build_anchor_outcome_summary(mapped_events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stats_by_combo: dict[tuple[str, str, int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for event in mapped_events:
        key = (
            str(event.get("timeframe") or ""),
            str(event.get("anchor_type") or ""),
            int(event.get("period") or 0),
            str(event.get("interaction") or ""),
        )
        stats_by_combo[key].append(event)
    window_stats: dict[str, dict[str, Any]] = {}
    for window in DEFAULT_OUTCOME_WINDOWS:
        rows = [_window for event in mapped_events if isinstance((_window := (event.get("windows") or {}).get(str(window))), Mapping)]
        window_stats[str(window)] = _window_stats(rows)
    best_combo = None
    best_score = -1.0
    for combo, events in stats_by_combo.items():
        stats = _candidate_stats(events)
        if stats["score"] > best_score:
            best_combo = combo
            best_score = stats["score"]
    return {
        "mapped_events": len(mapped_events),
        "best_anchor_timeframe": best_combo[0] if best_combo else None,
        "best_anchor_type": best_combo[1] if best_combo else None,
        "best_anchor_period": best_combo[2] if best_combo else None,
        "best_interaction": best_combo[3] if best_combo else None,
        "window_stats": window_stats,
        "paper_only": True,
        "live_authorized": False,
    }


def build_anchor_signal_origin_overlay(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframes: Sequence[str] | None = None,
    anchor_events: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    normalized_timeframes = set(timeframes or DEFAULT_TIMEFRAMES)
    records = []
    records.extend(_load_ndjson(resolved_log_dir / PATTERN_FAMILY_LEDGER_FILENAME, limit=20))
    records.extend(_load_ndjson(resolved_log_dir / THREE_BLACK_CROWS_LEDGER_FILENAME, limit=20))
    event_counts = Counter(str(event.get("timeframe") or "") for event in anchor_events or [])
    overlaps = []
    for record in records:
        target = record.get("target_scope") or record.get("target_context") or {}
        record_symbol = str(target.get("symbol") or normalized_symbol).upper()
        record_timeframes = target.get("timeframes") or [target.get("timeframe")]
        for timeframe in [str(tf) for tf in record_timeframes if tf]:
            if record_symbol == normalized_symbol and timeframe in normalized_timeframes:
                origins = _record_signal_origins(record)
                overlaps.append(
                    {
                        "source_event_type": record.get("event_type"),
                        "record_status": record.get("status"),
                        "symbol": record_symbol,
                        "timeframe": timeframe,
                        "anchor_events_on_timeframe": event_counts.get(timeframe, 0),
                        "signal_origins": origins,
                        "preview_only": True,
                        "live_authorized": False,
                        "signal_origin_promoted": False,
                    }
                )
    overlaps.sort(key=lambda row: (int(row["anchor_events_on_timeframe"]), str(row["timeframe"])), reverse=True)
    notes = [
        "Overlay is preview-only and does not promote signal origins or lanes.",
        "R199 uses recorded detector summaries where available; detailed candle-level confluence should be deepened in R201.",
    ]
    return {"overlap_records_found": len(overlaps), "top_overlaps": overlaps[:20], "notes": notes}


def build_anchor_candidate_ranking(mapped_events: Sequence[Mapping[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, int, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for event in mapped_events:
        grouped[
            (
                str(event.get("symbol") or DEFAULT_SYMBOL),
                str(event.get("timeframe") or ""),
                str(event.get("anchor_type") or ""),
                int(event.get("period") or 0),
                str(event.get("interaction") or ""),
                str(event.get("direction_bias") or "neutral"),
            )
        ].append(event)
    candidates = []
    for (symbol, timeframe, anchor_type, period, interaction, direction_bias), rows in grouped.items():
        stats = _candidate_stats(rows)
        candidates.append(
            {
                "rank": 0,
                "symbol": symbol,
                "timeframe": timeframe,
                "anchor_type": anchor_type,
                "period": period,
                "interaction": interaction,
                "direction_bias": direction_bias,
                "mapped_events": len(rows),
                "success_rate_pct": stats["success_rate_pct"],
                "failure_rate_pct": stats["failure_rate_pct"],
                "avg_favorable_move_pct": stats["avg_favorable_move_pct"],
                "avg_adverse_move_pct": stats["avg_adverse_move_pct"],
                "score": stats["score"],
                "confidence": _confidence(len(rows), stats["success_rate_pct"], stats["failure_rate_pct"]),
                "why": _candidate_why(timeframe, anchor_type, period, interaction, direction_bias, stats),
                "paper_only": True,
                "live_authorized": False,
            }
        )
    candidates.sort(key=lambda row: (float(row["score"]), int(row["mapped_events"])), reverse=True)
    for rank, row in enumerate(candidates[:limit], start=1):
        row["rank"] = rank
    return _sanitize(candidates[:limit])


def build_anchor_layer_next_actions(
    *,
    outcome_summary: Mapping[str, Any] | None = None,
    overlay: Mapping[str, Any] | None = None,
    ranking: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, str]]:
    mapped = int((outcome_summary or {}).get("mapped_events") or 0)
    overlaps = int((overlay or {}).get("overlap_records_found") or 0)
    ranked = list(ranking or [])
    actions = [
        {
            "priority": "HIGH",
            "action": "Deepen anchor outcome studies across WMA200, MA200, and custom WMA periods with candle-level signal-origin confluence.",
            "future_phase": "R201",
            "why": "R199 is preview-only; candidate anchors need larger mapped samples and confluence attribution before scoring.",
        },
        {
            "priority": "MEDIUM" if overlaps else "HIGH",
            "action": "Sync R197 pattern-family evidence into registry/Keter/lane-matrix review surfaces without config writes.",
            "future_phase": "R200",
            "why": "Anchor context is more useful after detector-family evidence is available to overlay.",
        },
    ]
    if mapped == 0:
        actions.insert(
            0,
            {
                "priority": "HIGH",
                "action": "Keep full-spectrum paper harvester and local candle archive capture running until anchor periods have enough candles.",
                "future_phase": "R198",
                "why": "No mapped anchor outcomes means the layer is not ready for scoring research.",
            },
        )
    elif ranked:
        actions.append(
            {
                "priority": "LOW",
                "action": "Review top paper-only anchor candidates manually before any future scoring proposal.",
                "future_phase": "R201",
                "why": "Top candidates are research evidence only and do not create entry permission.",
            }
        )
    return actions


def append_wma_ma_anchor_preview_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = wma_ma_anchor_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "preview_id": str(record.get("preview_id") or f"r199_wma_ma_anchor_preview_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "anchor_status": record.get("anchor_status"),
            "generated_at": record.get("generated_at"),
            "record_preview_requested": bool(record.get("record_preview_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "thresholds": dict(record.get("thresholds") or {}),
            "candle_source_summary": dict(record.get("candle_source_summary") or {}),
            "anchor_event_summary": dict(record.get("anchor_event_summary") or {}),
            "anchor_outcome_summary": dict(record.get("anchor_outcome_summary") or {}),
            "anchor_signal_origin_overlay": dict(record.get("anchor_signal_origin_overlay") or {}),
            "anchor_candidate_ranking": list(record.get("anchor_candidate_ranking") or []),
            "anchor_layer_next_actions": list(record.get("anchor_layer_next_actions") or []),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_wma_ma_anchor_preview_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return _load_ndjson(wma_ma_anchor_preview_records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def summarize_wma_ma_anchor_preview_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "anchor_status_counts": dict(sorted(Counter(str(record.get("anchor_status") or "UNKNOWN") for record in records).items())),
        "last_preview_id": latest.get("preview_id") if isinstance(latest, Mapping) else None,
        "last_best_anchor": dict(latest.get("anchor_outcome_summary") or {}) if isinstance(latest, Mapping) else {},
        "safety": dict(SAFETY),
    }


def wma_ma_anchor_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_wma_ma_anchor_layer_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def build_candle_source_summary(source_rows: Sequence[Mapping[str, Any]], *, requested_timeframes: Sequence[str]) -> dict[str, Any]:
    found = [str(row.get("timeframe")) for row in source_rows if row.get("source_found")]
    missing = [timeframe for timeframe in requested_timeframes if timeframe not in found]
    max_period = max(DEFAULT_ANCHOR_PERIODS)
    enough = [
        str(row.get("timeframe"))
        for row in source_rows
        if row.get("source_found") and int(row.get("records_loaded") or 0) >= max_period
    ]
    partial = [
        str(row.get("timeframe"))
        for row in source_rows
        if row.get("source_found") and row.get("enough_for_periods") and int(row.get("records_loaded") or 0) < max_period
    ]
    not_enough = [
        str(row.get("timeframe"))
        for row in source_rows
        if row.get("source_found") and not row.get("enough_for_periods")
    ]
    return {
        "sources_found": found,
        "sources_missing": missing,
        "timeframes_with_enough_candles": enough,
        "timeframes_with_partial_anchor_periods": partial,
        "timeframes_without_enough_candles": [*partial, *not_enough],
        "sources": list(source_rows),
    }


def _build_anchor_event_summary(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "total_anchor_events": len(events),
        "events_by_timeframe": dict(sorted(Counter(str(event.get("timeframe") or "") for event in events).items())),
        "events_by_anchor": dict(sorted(Counter(str(event.get("anchor_key") or "") for event in events).items())),
        "events_by_interaction": dict(sorted(Counter(str(event.get("interaction") or "") for event in events).items())),
    }


def _compute_directional_outcome_windows(
    *,
    entry_reference_price: float,
    future_candles: Sequence[Mapping[str, Any]],
    direction_bias: str,
    windows: Sequence[int],
    success_threshold_pct: float,
    adverse_threshold_pct: float,
) -> dict[str, Any]:
    output = {}
    for window in windows:
        if len(future_candles) < window:
            continue
        sliced = future_candles[:window]
        close = float(sliced[-1]["close"])
        high = max(float(candle["high"]) for candle in sliced)
        low = min(float(candle["low"]) for candle in sliced)
        close_return = _pct(close, entry_reference_price)
        if direction_bias == "long":
            favorable = close_return >= success_threshold_pct
            adverse = close_return <= -adverse_threshold_pct
            mfe = _pct(high, entry_reference_price)
            mae = abs(min(0.0, _pct(low, entry_reference_price)))
            simple_success = mfe >= success_threshold_pct
            simple_failure = mae >= adverse_threshold_pct
        else:
            favorable = close_return <= -success_threshold_pct
            adverse = close_return >= adverse_threshold_pct
            mfe = abs(min(0.0, _pct(low, entry_reference_price)))
            mae = max(0.0, _pct(high, entry_reference_price))
            simple_success = mfe >= success_threshold_pct
            simple_failure = mae >= adverse_threshold_pct
        output[str(window)] = {
            "future_close_time": _candle_time(sliced[-1]),
            "close_return_pct": close_return,
            "mfe_favorable_pct": _round(mfe),
            "mae_adverse_pct": _round(mae),
            "favorable_close": favorable,
            "adverse_close": adverse,
            "simple_success": simple_success,
            "simple_failure": simple_failure,
        }
    return output


def _window_stats(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "mapped_count": len(rows),
        "simple_success_rate_pct": _rate(rows, "simple_success"),
        "simple_failure_rate_pct": _rate(rows, "simple_failure"),
        "favorable_close_rate_pct": _rate(rows, "favorable_close"),
        "avg_close_return_pct": _avg(rows, "close_return_pct"),
        "avg_favorable_move_pct": _avg(rows, "mfe_favorable_pct"),
        "avg_adverse_move_pct": _avg(rows, "mae_adverse_pct"),
    }


def _candidate_stats(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    windows = [
        dict((event.get("windows") or {}).get("3") or next(iter((event.get("windows") or {}).values()), {}))
        for event in events
        if event.get("windows")
    ]
    mapped = len(windows)
    success = _rate(windows, "simple_success")
    failure = _rate(windows, "simple_failure")
    favorable = _avg(windows, "mfe_favorable_pct")
    adverse = _avg(windows, "mae_adverse_pct")
    score = _round((success - failure) + favorable - adverse + min(mapped, 50) * 0.2)
    return {
        "mapped_events": mapped,
        "success_rate_pct": success,
        "failure_rate_pct": failure,
        "avg_favorable_move_pct": favorable,
        "avg_adverse_move_pct": adverse,
        "score": score,
    }


def _record_signal_origins(record: Mapping[str, Any]) -> list[str]:
    origins = []
    for row in record.get("pattern_family_registry") or []:
        if isinstance(row, Mapping) and row.get("signal_origin"):
            origins.append(str(row["signal_origin"]))
    for row in record.get("detections") or []:
        if isinstance(row, Mapping) and row.get("signal_origin"):
            origins.append(str(row["signal_origin"]))
    if not origins and record.get("target_context", {}).get("signal_origin"):
        origins.append(str(record["target_context"]["signal_origin"]))
    return sorted(set(origins))


def _source_anchor_status(*, source_found: bool, candles: int, periods: Sequence[int]) -> str:
    if not source_found:
        return LOCAL_CANDLE_FEED_MISSING
    if candles < min(periods or DEFAULT_ANCHOR_PERIODS):
        return INSUFFICIENT_CANDLES_FOR_ANCHOR
    return ANCHOR_EVENTS_FOUND


def _overall_anchor_status(source_rows: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]], mapped: Sequence[Mapping[str, Any]]) -> str:
    if mapped:
        return ANCHOR_OUTCOME_MAPPING_AVAILABLE
    if events:
        return ANCHOR_EVENTS_FOUND
    if source_rows and all(row.get("anchor_status") == LOCAL_CANDLE_FEED_MISSING for row in source_rows):
        return LOCAL_CANDLE_FEED_MISSING
    if source_rows and all(row.get("anchor_status") == INSUFFICIENT_CANDLES_FOR_ANCHOR for row in source_rows):
        return INSUFFICIENT_CANDLES_FOR_ANCHOR
    return ANCHOR_EVENTS_NOT_FOUND


def _status_for_preview(*, record_preview: bool, confirmation_valid: bool, anchor_status: str) -> str:
    if record_preview and not confirmation_valid:
        return WMA_MA_ANCHOR_LAYER_PREVIEW_REJECTED
    if anchor_status in {LOCAL_CANDLE_FEED_MISSING, INSUFFICIENT_CANDLES_FOR_ANCHOR, ANCHOR_EVENTS_NOT_FOUND}:
        return WMA_MA_ANCHOR_LAYER_PREVIEW_BLOCKED
    if record_preview and confirmation_valid:
        return WMA_MA_ANCHOR_LAYER_PREVIEW_RECORDED
    return WMA_MA_ANCHOR_LAYER_PREVIEW_READY


def _anchor_specs(periods: Sequence[int]) -> list[tuple[str, int]]:
    specs = [(SMA200, 200), (WMA200, 200)]
    specs.extend((CUSTOM_WMA, period) for period in periods)
    deduped = []
    for spec in specs:
        if spec not in deduped:
            deduped.append(spec)
    return deduped


def _anchor_key(anchor_type: str, period: int) -> str:
    if anchor_type == CUSTOM_WMA:
        return f"{anchor_type}_{period}"
    return anchor_type


def _direction_bias(interaction: str) -> str:
    if interaction in {"rejection_down", "loss", "cross_down"}:
        return "short"
    if interaction in {"rejection_up", "reclaim", "cross_up"}:
        return "long"
    return "neutral"


def _confidence(mapped: int, success: float, failure: float) -> str:
    if mapped >= 30 and success >= failure + 10:
        return "HIGH"
    if mapped >= 10 and success >= failure:
        return "MEDIUM"
    return "LOW"


def _candidate_why(timeframe: str, anchor_type: str, period: int, interaction: str, direction: str, stats: Mapping[str, Any]) -> str:
    return (
        f"{timeframe} {anchor_type} period {period} {interaction} mapped as {direction} bias with "
        f"{stats['mapped_events']} paper windows; success {stats['success_rate_pct']}% vs failure {stats['failure_rate_pct']}%."
    )


def _recommended_next_operator_move(ranking: Sequence[Mapping[str, Any]], outcome_summary: Mapping[str, Any]) -> str:
    if ranking:
        return "RUN_R201_ANCHOR_OUTCOME_DEEPENING"
    if int(outcome_summary.get("mapped_events") or 0) > 0:
        return "RUN_R200_PATTERN_FAMILY_FEEDBACK_SYNC"
    return "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"


def _recommended_next_engineering_move(ranking: Sequence[Mapping[str, Any]], outcome_summary: Mapping[str, Any]) -> str:
    if ranking:
        return "Build R201 anchor outcome deepening with candle-level anchor + signal-origin confluence; keep it paper-only with no config writes."
    if int(outcome_summary.get("mapped_events") or 0) > 0:
        return "Run R200 feedback sync before considering anchor scoring integration."
    return "Keep R199 as an audit-only preview and collect more local candles across priority timeframes."


def _normalize_timeframes(timeframes: Sequence[str] | str | None) -> list[str]:
    if timeframes is None:
        raw = list(DEFAULT_TIMEFRAMES)
    elif isinstance(timeframes, str):
        raw = [part.strip() for part in timeframes.split(",")]
    else:
        raw = [str(part).strip() for part in timeframes]
    return _ordered_timeframes([timeframe for timeframe in raw if timeframe])


def _normalize_periods(periods: Sequence[int] | str | None) -> list[int]:
    if periods is None:
        raw: Sequence[Any] = DEFAULT_ANCHOR_PERIODS
    elif isinstance(periods, str):
        raw = [part.strip() for part in periods.split(",")]
    else:
        raw = periods
    parsed = []
    for period in raw:
        try:
            value = int(period)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in parsed:
            parsed.append(value)
    return parsed or list(DEFAULT_ANCHOR_PERIODS)


def _ordered_timeframes(timeframes: Sequence[str]) -> list[str]:
    order = {timeframe: index for index, timeframe in enumerate(DEFAULT_TIMEFRAMES)}
    priority = {timeframe: index for index, timeframe in enumerate(PRIORITY_TIMEFRAMES)}
    deduped = []
    for timeframe in timeframes:
        if timeframe and timeframe not in deduped:
            deduped.append(timeframe)
    return sorted(deduped, key=lambda tf: (priority.get(tf, 99), order.get(tf, 999), tf))


def _sorted_candles(candles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(candle) for candle in candles if all(_to_float(candle.get(key)) is not None for key in ("open", "high", "low", "close"))]
    rows.sort(key=lambda row: _candle_time(row))
    return rows


def _candle_time(candle: Mapping[str, Any]) -> str:
    return str(candle.get("open_time") or candle.get("timestamp") or candle.get("close_time") or "")


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _load_ndjson(path: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    resolved = Path(path)
    if not resolved.exists():
        return []
    if limit <= 0:
        rows = []
        with resolved.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(_sanitize(json.loads(line)))
        return rows
    return [_sanitize(row) for row in read_recent_ndjson_records(resolved, limit=limit, max_bytes=32_000_000)]


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set any lane tiny_live",
        "write risk contract config",
        "transfer",
        "withdraw",
    ]


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed < 0:
        return default
    return _round(parsed)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: float, reference: float) -> float:
    if reference == 0:
        return 0.0
    return _round(((float(value) - float(reference)) / float(reference)) * 100)


def _rate(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return _round((sum(1 for row in rows if bool(row.get(key))) / len(rows)) * 100)


def _avg(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    values = [_to_float(row.get(key)) for row in rows]
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return 0.0
    return _round(sum(numeric) / len(numeric))


def _round(value: float) -> float:
    return round(float(value), 6)


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
