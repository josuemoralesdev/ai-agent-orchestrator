"""R202 paper-only pattern-family outcome mapping.

This module maps detector-backed R197 pattern-family origins to future local
OHLC windows. It is audit-only: no Binance/network calls, no config writes, no
payload creation, no origin/lane promotion, and no live authorization.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.local_candle_feed_adapter import (
    MAX_LATEST_CANDLES,
    load_local_candle_feed,
    normalize_local_candle_feed,
    resolve_local_candle_feed_path,
)
from src.app.hammer_radar.operator.pattern_detector_family_expansion import (
    DEFAULT_PATTERNS,
    DEFAULT_SYMBOL,
    DETECTOR_PATTERNS,
    REGISTRY_ONLY_PATTERNS,
    detect_bearish_engulfing_sequences,
    detect_bullish_engulfing_sequences,
    detect_exhaustion_wick_sequences,
    detect_three_white_soldiers_sequences,
    load_pattern_family_expansion_records,
)

PATTERN_OUTCOME_MAPPING_FAMILY_READY = "PATTERN_OUTCOME_MAPPING_FAMILY_READY"
PATTERN_OUTCOME_MAPPING_FAMILY_REJECTED = "PATTERN_OUTCOME_MAPPING_FAMILY_REJECTED"
PATTERN_OUTCOME_MAPPING_FAMILY_RECORDED = "PATTERN_OUTCOME_MAPPING_FAMILY_RECORDED"
PATTERN_OUTCOME_MAPPING_FAMILY_BLOCKED = "PATTERN_OUTCOME_MAPPING_FAMILY_BLOCKED"
PATTERN_OUTCOME_MAPPING_FAMILY_ERROR = "PATTERN_OUTCOME_MAPPING_FAMILY_ERROR"

PATTERN_OUTCOME_MAPPING_AVAILABLE = "PATTERN_OUTCOME_MAPPING_AVAILABLE"
PATTERN_OUTCOME_MAPPING_PARTIAL = "PATTERN_OUTCOME_MAPPING_PARTIAL"
PATTERN_OUTCOME_MAPPING_NO_DETECTIONS = "PATTERN_OUTCOME_MAPPING_NO_DETECTIONS"
PATTERN_OUTCOME_MAPPING_NO_LOCAL_CANDLES = "PATTERN_OUTCOME_MAPPING_NO_LOCAL_CANDLES"
PATTERN_OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW = "PATTERN_OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW"
PATTERN_OUTCOME_NOT_LIVE_AUTHORIZED = "PATTERN_OUTCOME_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "PATTERN_OUTCOME_MAPPING_FAMILY"
LEDGER_FILENAME = "pattern_outcome_mapping_family.ndjson"
CONFIRM_PATTERN_OUTCOME_MAPPING_FAMILY_RECORDING_PHRASE = (
    "I CONFIRM PATTERN OUTCOME MAPPING FAMILY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_TIMEFRAMES = ("4m", "8m", "13m", "22m", "44m", "55m", "88m", "222m", "444m", "666m", "888m", "4H", "13H", "13D")
DEFAULT_WINDOWS = (1, 3, 5, 10, 21, 34, 55)
DEFAULT_SUCCESS_THRESHOLD_PCT = 0.10
DEFAULT_ADVERSE_THRESHOLD_PCT = 0.10
ENTRY_MODE = "ladder_close_50_618"
REGISTRY_ONLY_BLOCK_REASON = "registry_only_until_retest_structure"

ORIGIN_DIRECTIONS = {
    "three_white_soldiers": "long",
    "bullish_engulfing": "long",
    "bearish_engulfing": "short",
}

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
    "pattern_family_live_authorized": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/pattern_detector_family_expansion.ndjson",
    "logs/hammer_radar_forward/candle_archive/{symbol}_{timeframe}.ndjson",
    "operator.pattern_detector_family_expansion detector functions",
    "operator.local_candle_feed_adapter.load_local_candle_feed",
    "operator.local_candle_feed_adapter.normalize_local_candle_feed",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_pattern_outcome_mapping_family(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    success_threshold_pct: float = DEFAULT_SUCCESS_THRESHOLD_PCT,
    adverse_threshold_pct: float = DEFAULT_ADVERSE_THRESHOLD_PCT,
    record_mapping: bool = False,
    confirm_pattern_outcome_family: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    success_threshold = _bounded_float(success_threshold_pct, DEFAULT_SUCCESS_THRESHOLD_PCT)
    adverse_threshold = _bounded_float(adverse_threshold_pct, DEFAULT_ADVERSE_THRESHOLD_PCT)
    confirmation_valid = confirm_pattern_outcome_family == CONFIRM_PATTERN_OUTCOME_MAPPING_FAMILY_RECORDING_PHRASE
    try:
        expansion = load_latest_pattern_family_expansion(log_dir=resolved_log_dir)
        timeframes = _timeframes_from_expansion(expansion)
        candles_by_timeframe = load_local_candles_for_pattern_outcomes(
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            timeframes=timeframes,
        )
        detections_by_origin = extract_pattern_family_detections(
            pattern_expansion=expansion,
            candles_by_timeframe=candles_by_timeframe,
            symbol=normalized_symbol,
        )
        mapped_outcomes = _map_all_detections(
            detections_by_origin=detections_by_origin,
            candles_by_timeframe=candles_by_timeframe,
            success_threshold_pct=success_threshold,
            adverse_threshold_pct=adverse_threshold,
        )
        outcome_mapping_status = _overall_outcome_mapping_status(
            detections_by_origin=detections_by_origin,
            candles_by_timeframe=candles_by_timeframe,
            mapped_outcomes=mapped_outcomes,
        )
        origin_summary = build_pattern_origin_outcome_summary(mapped_outcomes, detections_by_origin=detections_by_origin)
        timeframe_summary = build_pattern_timeframe_outcome_summary(mapped_outcomes, timeframes=timeframes)
        aggregate_summary = build_pattern_family_aggregate_summary(origin_summary)
        rankings = build_pattern_outcome_rankings(mapped_outcomes)
        recommendations = build_pattern_outcome_keter_recommendations(origin_summary, rankings)
        status = classify_pattern_outcome_mapping_status(
            record_mapping=record_mapping,
            confirmation_valid=confirmation_valid,
            outcome_mapping_status=outcome_mapping_status,
            pattern_expansion_found=bool(expansion),
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "mapping_recorded": False,
            "mapping_id": None,
            "record_mapping_requested": bool(record_mapping),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "symbol": normalized_symbol,
                "signal_origins": list(DEFAULT_PATTERNS),
                "timeframes": list(timeframes),
                "outcome_windows": list(DEFAULT_WINDOWS),
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "pattern_expansion_found": bool(expansion),
                "detections_loaded_by_origin": {origin: len(rows) for origin, rows in detections_by_origin.items()},
                "candles_loaded_by_timeframe": {timeframe: len(candles_by_timeframe.get(timeframe) or []) for timeframe in timeframes},
                "registry_only_origins": list(REGISTRY_ONLY_PATTERNS),
            },
            "origin_outcome_summary": origin_summary,
            "timeframe_outcome_summary": timeframe_summary,
            "aggregate_summary": aggregate_summary,
            "pattern_outcome_rankings": rankings,
            "keter_recommendations": recommendations,
            "recommended_next_operator_move": _recommended_next_operator_move(aggregate_summary, rankings),
            "recommended_next_engineering_move": _recommended_next_engineering_move(aggregate_summary, rankings),
            "do_not_run_yet": _do_not_run_yet(),
            "outcome_mapping_status": outcome_mapping_status,
            "mapped_outcome_count": len(mapped_outcomes),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_mapping and confirmation_valid and status != PATTERN_OUTCOME_MAPPING_FAMILY_BLOCKED:
            record = append_pattern_outcome_mapping_family_record(payload, log_dir=resolved_log_dir)
            payload["status"] = PATTERN_OUTCOME_MAPPING_FAMILY_RECORDED
            payload["mapping_recorded"] = True
            payload["mapping_id"] = record["mapping_id"]
            payload["ledger_path"] = str(pattern_outcome_mapping_family_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": PATTERN_OUTCOME_MAPPING_FAMILY_ERROR,
                "generated_at": generated_at.isoformat(),
                "mapping_recorded": False,
                "mapping_id": None,
                "record_mapping_requested": bool(record_mapping),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "symbol": normalized_symbol,
                    "signal_origins": list(DEFAULT_PATTERNS),
                    "timeframes": list(DEFAULT_TIMEFRAMES),
                    "outcome_windows": list(DEFAULT_WINDOWS),
                    "paper_only": True,
                    "live_authorized": False,
                },
                "input_summary": {
                    "pattern_expansion_found": False,
                    "detections_loaded_by_origin": {origin: 0 for origin in DETECTOR_PATTERNS},
                    "candles_loaded_by_timeframe": {},
                    "registry_only_origins": list(REGISTRY_ONLY_PATTERNS),
                },
                "origin_outcome_summary": _empty_origin_summary(),
                "timeframe_outcome_summary": {},
                "aggregate_summary": build_pattern_family_aggregate_summary(_empty_origin_summary()),
                "pattern_outcome_rankings": [],
                "keter_recommendations": build_pattern_outcome_keter_recommendations(_empty_origin_summary(), []),
                "recommended_next_operator_move": "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R202 pattern outcome mapping error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "outcome_mapping_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_pattern_family_expansion(*, log_dir: str | Path | None = None) -> dict[str, Any] | None:
    records = load_pattern_family_expansion_records(log_dir=log_dir, limit=1)
    return dict(records[0]) if records else None


def extract_pattern_family_detections(
    *,
    pattern_expansion: Mapping[str, Any] | None,
    candles_by_timeframe: Mapping[str, Sequence[Mapping[str, Any]]],
    symbol: str = DEFAULT_SYMBOL,
) -> dict[str, list[dict[str, Any]]]:
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    detector_functions = {
        "three_white_soldiers": detect_three_white_soldiers_sequences,
        "bearish_engulfing": detect_bearish_engulfing_sequences,
        "bullish_engulfing": detect_bullish_engulfing_sequences,
        "exhaustion_wick": detect_exhaustion_wick_sequences,
    }
    timeframes = _timeframes_from_expansion(pattern_expansion)
    output = {origin: [] for origin in DETECTOR_PATTERNS}
    for timeframe in timeframes:
        candles = list(candles_by_timeframe.get(timeframe) or [])
        if not candles:
            continue
        for origin, detector in detector_functions.items():
            strict = detector(candles, symbol=normalized_symbol, timeframe=timeframe, mode="strict")
            loose = detector(candles, symbol=normalized_symbol, timeframe=timeframe, mode="loose_preview")
            output[origin].extend([*strict, *loose])
    return output


def load_local_candles_for_pattern_outcomes(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframes: Sequence[str] | str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    output: dict[str, list[dict[str, Any]]] = {}
    for timeframe in _normalize_timeframes(timeframes):
        source_path = resolve_local_candle_feed_path(log_dir=resolved_log_dir, symbol=normalized_symbol, timeframe=timeframe)
        raw_records = load_local_candle_feed(source_path, latest_candles=MAX_LATEST_CANDLES)
        candles = normalize_local_candle_feed(
            raw_records,
            symbol=normalized_symbol,
            timeframe=timeframe,
            source=source_path.name,
            latest_candles=MAX_LATEST_CANDLES,
        )
        candles.sort(key=lambda row: str(row.get("open_time") or row.get("timestamp") or ""))
        output[timeframe] = candles
    return output


def map_pattern_detection_to_future_candles(
    detection: Mapping[str, Any],
    candles: Sequence[Mapping[str, Any]],
    *,
    windows: Sequence[int] = DEFAULT_WINDOWS,
) -> dict[str, Any]:
    detected_at = str(detection.get("detected_at") or "")
    rows = [dict(row) for row in candles]
    rows.sort(key=lambda row: str(row.get("open_time") or row.get("timestamp") or ""))
    detection_index = next((index for index, row in enumerate(rows) if _candle_time(row) == detected_at), None)
    if detection_index is None:
        return {
            "entry_reference_price": None,
            "entry_reference_source": None,
            "future_candles": [],
            "outcome_mapping_status": PATTERN_OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW,
        }
    detection_close = _to_float(rows[detection_index].get("close"))
    next_open = _to_float(rows[detection_index + 1].get("open")) if detection_index + 1 < len(rows) else None
    entry = detection_close if detection_close is not None else next_open
    entry_source = "detection_close" if detection_close is not None else "next_candle_open"
    max_window = max((int(window) for window in windows), default=0)
    future_candles = rows[detection_index + 1 : detection_index + 1 + max_window]
    status = PATTERN_OUTCOME_MAPPING_AVAILABLE if len(future_candles) >= max_window else PATTERN_OUTCOME_MAPPING_PARTIAL
    if not future_candles:
        status = PATTERN_OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW
    return {
        "entry_reference_price": entry,
        "entry_reference_source": entry_source,
        "future_candles": future_candles,
        "future_candles_available": len(future_candles),
        "outcome_mapping_status": status,
    }


def compute_pattern_outcome_window(
    *,
    entry_reference_price: float,
    future_candles: Sequence[Mapping[str, Any]],
    direction: str,
    windows: Sequence[int] = DEFAULT_WINDOWS,
    success_threshold_pct: float = DEFAULT_SUCCESS_THRESHOLD_PCT,
    adverse_threshold_pct: float = DEFAULT_ADVERSE_THRESHOLD_PCT,
) -> dict[str, dict[str, Any]]:
    if entry_reference_price <= 0:
        return {}
    normalized_direction = _normalize_direction(direction)
    output: dict[str, dict[str, Any]] = {}
    for raw_window in windows:
        window = int(raw_window)
        if window <= 0 or len(future_candles) < window:
            continue
        rows = [dict(row) for row in future_candles[:window]]
        lows = [_to_float(row.get("low")) for row in rows]
        highs = [_to_float(row.get("high")) for row in rows]
        future_close = _to_float(rows[-1].get("close"))
        if future_close is None or any(value is None for value in lows + highs):
            continue
        min_low = min(float(value) for value in lows if value is not None)
        max_high = max(float(value) for value in highs if value is not None)
        close_return = ((future_close - entry_reference_price) / entry_reference_price) * 100
        upside = ((max_high - entry_reference_price) / entry_reference_price) * 100
        downside = ((entry_reference_price - min_low) / entry_reference_price) * 100
        if normalized_direction == "short":
            favorable_move = max(0.0, downside)
            adverse_move = max(0.0, upside)
            favorable_close = close_return < 0
            adverse_close = close_return > 0
        else:
            favorable_move = max(0.0, upside)
            adverse_move = max(0.0, downside)
            favorable_close = close_return > 0
            adverse_close = close_return < 0
        output[str(window)] = {
            "future_close_time": _candle_time(rows[-1]),
            "close_return_pct": _round(close_return),
            "mfe_favorable_pct": _round(favorable_move),
            "mae_adverse_pct": _round(adverse_move),
            "favorable_close": favorable_close,
            "adverse_close": adverse_close,
            "simple_success": favorable_move >= success_threshold_pct,
            "simple_failure": adverse_move >= adverse_threshold_pct,
        }
    return output


def build_pattern_origin_outcome_summary(
    mapped_outcomes: Sequence[Mapping[str, Any]],
    *,
    detections_by_origin: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for origin in DETECTOR_PATTERNS:
        rows = [row for row in mapped_outcomes if row.get("signal_origin") == origin]
        summary = _summary_for_rows(rows)
        source_count = len((detections_by_origin or {}).get(origin) or [])
        summary["unmapped_detection_count"] = max(0, source_count - int(summary["mapped_count"]))
        output[origin] = summary
    for origin in REGISTRY_ONLY_PATTERNS:
        output[origin] = {
            "mapped_count": 0,
            "blocked_reason": REGISTRY_ONLY_BLOCK_REASON,
            "paper_only": True,
            "live_ready": False,
            "live_authorized": False,
        }
    return output


def build_pattern_timeframe_outcome_summary(
    mapped_outcomes: Sequence[Mapping[str, Any]],
    *,
    timeframes: Sequence[str] | None = None,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for timeframe in _normalize_timeframes(timeframes):
        rows = [row for row in mapped_outcomes if str(row.get("timeframe") or "") == timeframe]
        summary = _summary_for_rows(rows)
        summary["origins_mapped"] = sorted({str(row.get("signal_origin")) for row in rows if row.get("signal_origin")})
        output[timeframe] = summary
    return output


def build_pattern_family_aggregate_summary(origin_outcome_summary: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    detector_rows = {origin: dict(origin_outcome_summary.get(origin) or {}) for origin in DETECTOR_PATTERNS}
    positive = [origin for origin, row in detector_rows.items() if row.get("supports_directional_bias") is True]
    mixed = [
        origin
        for origin, row in detector_rows.items()
        if int(row.get("mapped_count") or 0) > 0 and row.get("supports_directional_bias") is False
    ]
    sample_limited = [origin for origin, row in detector_rows.items() if bool(row.get("needs_more_samples"))]
    return {
        "total_mapped_count": sum(int(row.get("mapped_count") or 0) for row in detector_rows.values()),
        "origins_with_positive_bias": positive,
        "origins_with_mixed_bias": mixed,
        "origins_needing_more_samples": sample_limited,
        "registry_only_blocked": list(REGISTRY_ONLY_PATTERNS),
    }


def build_pattern_outcome_rankings(mapped_outcomes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for row in mapped_outcomes:
        origin = str(row.get("signal_origin") or "")
        timeframe = str(row.get("timeframe") or "")
        direction = _normalize_direction(row.get("direction"))
        mode = str(row.get("mode") or "combined")
        groups.setdefault((origin, timeframe, mode, direction), []).append(row)
        groups.setdefault((origin, timeframe, "combined", direction), []).append(row)
    rankings: list[dict[str, Any]] = []
    for (origin, timeframe, mode, direction), rows in groups.items():
        summary = _summary_for_rows(rows)
        mapped_count = int(summary["mapped_count"])
        if mapped_count <= 0:
            continue
        best_window = str(summary["best_window"])
        stats = dict((summary.get("window_stats") or {}).get(best_window) or {})
        confidence = _confidence_for_count(mapped_count)
        warnings = _risk_warnings(mapped_count=mapped_count, stats=stats)
        score = _score(stats=stats, mapped_count=mapped_count)
        rankings.append(
            {
                "rank": 0,
                "signal_origin": origin,
                "timeframe": timeframe,
                "mode": mode,
                "direction_bias": direction,
                "mapped_count": mapped_count,
                "best_window": best_window,
                "favorable_close_rate_pct": stats.get("favorable_close_rate_pct", 0.0),
                "simple_success_rate_pct": stats.get("simple_success_rate_pct", 0.0),
                "simple_failure_rate_pct": stats.get("simple_failure_rate_pct", 0.0),
                "avg_favorable_move_pct": stats.get("avg_favorable_move_pct", 0.0),
                "avg_adverse_move_pct": stats.get("avg_adverse_move_pct", 0.0),
                "score": score,
                "confidence": confidence,
                "risk_warnings": warnings,
                "paper_only": True,
                "live_authorized": False,
            }
        )
    rankings.sort(key=lambda row: (float(row["score"]), int(row["mapped_count"]), float(row["favorable_close_rate_pct"])), reverse=True)
    for index, row in enumerate(rankings, start=1):
        row["rank"] = index
    return rankings


def build_pattern_outcome_keter_recommendations(
    origin_outcome_summary: Mapping[str, Mapping[str, Any]],
    rankings: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    ranked_origins = {str(row.get("signal_origin")) for row in rankings[:10]}
    output: list[dict[str, Any]] = []
    for origin in DEFAULT_PATTERNS:
        summary = dict(origin_outcome_summary.get(origin) or {})
        if origin in REGISTRY_ONLY_PATTERNS:
            action = "KEEP_REGISTRY_ONLY"
            priority = "LOW"
            why = "Retest origins remain blocked until local retest-structure detectors exist."
        elif summary.get("supports_directional_bias") is True and not summary.get("needs_more_samples"):
            action = "RUN_KETER_FEEDBACK"
            priority = "HIGH" if origin in ranked_origins else "MEDIUM"
            why = "Mapped paper outcomes support the origin direction with enough samples for Keter review."
        elif int(summary.get("mapped_count") or 0) > 0:
            action = "COLLECT_MORE_SAMPLES"
            priority = "MEDIUM"
            why = "Mapped outcomes exist, but sample count or directional evidence is not strong enough yet."
        else:
            action = "COLLECT_MORE_SAMPLES"
            priority = "LOW"
            why = "No future-window outcomes were mapped from local candles."
        output.append({"signal_origin": origin, "recommended_action": action, "priority": priority, "why": why})
    return output


def classify_pattern_outcome_mapping_status(
    *,
    record_mapping: bool,
    confirmation_valid: bool,
    outcome_mapping_status: str,
    pattern_expansion_found: bool = True,
) -> str:
    if record_mapping and not confirmation_valid:
        return PATTERN_OUTCOME_MAPPING_FAMILY_REJECTED
    if not pattern_expansion_found or outcome_mapping_status in {
        PATTERN_OUTCOME_MAPPING_NO_DETECTIONS,
        PATTERN_OUTCOME_MAPPING_NO_LOCAL_CANDLES,
        PATTERN_OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW,
    }:
        return PATTERN_OUTCOME_MAPPING_FAMILY_BLOCKED
    if record_mapping and confirmation_valid:
        return PATTERN_OUTCOME_MAPPING_FAMILY_RECORDED
    return PATTERN_OUTCOME_MAPPING_FAMILY_READY


def append_pattern_outcome_mapping_family_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = pattern_outcome_mapping_family_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "mapping_id": str(record.get("mapping_id") or f"r202_pattern_outcome_mapping_family_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_mapping_requested": bool(record.get("record_mapping_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "origin_outcome_summary": dict(record.get("origin_outcome_summary") or {}),
            "timeframe_outcome_summary": dict(record.get("timeframe_outcome_summary") or {}),
            "aggregate_summary": dict(record.get("aggregate_summary") or {}),
            "pattern_outcome_rankings": list(record.get("pattern_outcome_rankings") or []),
            "keter_recommendations": list(record.get("keter_recommendations") or []),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "outcome_mapping_status": record.get("outcome_mapping_status"),
            "mapped_outcome_count": int(record.get("mapped_outcome_count") or 0),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_pattern_outcome_mapping_family_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return _load_ndjson(pattern_outcome_mapping_family_records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def summarize_pattern_outcome_mapping_family_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_mapping_id": latest.get("mapping_id") if isinstance(latest, Mapping) else None,
        "last_total_mapped_count": (latest.get("aggregate_summary") or {}).get("total_mapped_count") if isinstance(latest, Mapping) else 0,
        "safety": dict(SAFETY),
    }


def pattern_outcome_mapping_family_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_pattern_outcome_mapping_family_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _map_all_detections(
    *,
    detections_by_origin: Mapping[str, Sequence[Mapping[str, Any]]],
    candles_by_timeframe: Mapping[str, Sequence[Mapping[str, Any]]],
    success_threshold_pct: float,
    adverse_threshold_pct: float,
) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for origin, detections in detections_by_origin.items():
        for detection in detections:
            timeframe = str(detection.get("timeframe") or "")
            candles = candles_by_timeframe.get(timeframe) or []
            future = map_pattern_detection_to_future_candles(detection, candles, windows=DEFAULT_WINDOWS)
            entry = future.get("entry_reference_price")
            direction = _direction_for_detection(detection)
            if entry is None or not future.get("future_candles"):
                continue
            windows = compute_pattern_outcome_window(
                entry_reference_price=float(entry),
                future_candles=future["future_candles"],
                direction=direction,
                windows=DEFAULT_WINDOWS,
                success_threshold_pct=success_threshold_pct,
                adverse_threshold_pct=adverse_threshold_pct,
            )
            if not windows:
                continue
            mapped.append(
                {
                    "candidate_id": detection.get("candidate_id"),
                    "signal_origin": origin,
                    "timeframe": timeframe,
                    "symbol": detection.get("symbol"),
                    "direction": direction,
                    "mode": detection.get("mode"),
                    "confidence": detection.get("confidence"),
                    "detected_at": detection.get("detected_at"),
                    "entry_reference_price": entry,
                    "entry_reference_source": future.get("entry_reference_source"),
                    "windows": windows,
                    "outcome_mapping_status": future.get("outcome_mapping_status"),
                    "paper_only": True,
                    "live_authorized": False,
                }
            )
    return mapped


def _summary_for_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    strict_count = sum(1 for row in rows if str(row.get("mode") or "") == "strict")
    loose_count = sum(1 for row in rows if str(row.get("mode") or "") == "loose_preview")
    window_stats = {str(window): _window_stats(rows, str(window)) for window in DEFAULT_WINDOWS}
    scored = {window: stats for window, stats in window_stats.items() if int(stats.get("mapped_count") or 0) > 0}
    best_window = max(
        scored,
        key=lambda key: (
            float(scored[key]["simple_success_rate_pct"]),
            float(scored[key]["favorable_close_rate_pct"]),
            -float(scored[key]["simple_failure_rate_pct"]),
        ),
        default="unknown",
    )
    best_stats = dict(scored.get(str(best_window)) or {})
    mapped_count = len(rows)
    supports = None
    if mapped_count > 0 and best_stats:
        supports = (
            float(best_stats.get("favorable_close_rate_pct") or 0.0) >= 50.0
            and float(best_stats.get("simple_success_rate_pct") or 0.0) >= float(best_stats.get("simple_failure_rate_pct") or 0.0)
        )
    return {
        "mapped_count": mapped_count,
        "strict_mapped_count": strict_count,
        "loose_mapped_count": loose_count,
        "best_window": str(best_window),
        "supports_directional_bias": supports,
        "paper_tracking_recommended": mapped_count > 0,
        "needs_more_samples": mapped_count < 30,
        "window_stats": window_stats,
        "live_ready": False,
        "paper_only": True,
        "live_authorized": False,
    }


def _window_stats(mapped_outcomes: Sequence[Mapping[str, Any]], window: str) -> dict[str, Any]:
    rows = [
        dict((outcome.get("windows") or {}).get(window) or {})
        for outcome in mapped_outcomes
        if isinstance((outcome.get("windows") or {}).get(window), Mapping)
    ]
    if not rows:
        return {
            "mapped_count": 0,
            "favorable_close_rate_pct": 0.0,
            "simple_success_rate_pct": 0.0,
            "simple_failure_rate_pct": 0.0,
            "avg_close_return_pct": 0.0,
            "avg_favorable_move_pct": 0.0,
            "avg_adverse_move_pct": 0.0,
        }
    return {
        "mapped_count": len(rows),
        "favorable_close_rate_pct": _rate(rows, "favorable_close"),
        "simple_success_rate_pct": _rate(rows, "simple_success"),
        "simple_failure_rate_pct": _rate(rows, "simple_failure"),
        "avg_close_return_pct": _avg(rows, "close_return_pct"),
        "avg_favorable_move_pct": _avg(rows, "mfe_favorable_pct"),
        "avg_adverse_move_pct": _avg(rows, "mae_adverse_pct"),
    }


def _overall_outcome_mapping_status(
    *,
    detections_by_origin: Mapping[str, Sequence[Mapping[str, Any]]],
    candles_by_timeframe: Mapping[str, Sequence[Mapping[str, Any]]],
    mapped_outcomes: Sequence[Mapping[str, Any]],
) -> str:
    if not any(detections_by_origin.values()):
        return PATTERN_OUTCOME_MAPPING_NO_DETECTIONS
    if not any(candles_by_timeframe.values()):
        return PATTERN_OUTCOME_MAPPING_NO_LOCAL_CANDLES
    if not mapped_outcomes:
        return PATTERN_OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW
    if any(str(row.get("outcome_mapping_status") or "") != PATTERN_OUTCOME_MAPPING_AVAILABLE for row in mapped_outcomes):
        return PATTERN_OUTCOME_MAPPING_PARTIAL
    return PATTERN_OUTCOME_MAPPING_AVAILABLE


def _empty_origin_summary() -> dict[str, Any]:
    output = {}
    for origin in DETECTOR_PATTERNS:
        output[origin] = _summary_for_rows([])
    for origin in REGISTRY_ONLY_PATTERNS:
        output[origin] = {
            "mapped_count": 0,
            "blocked_reason": REGISTRY_ONLY_BLOCK_REASON,
            "paper_only": True,
            "live_ready": False,
            "live_authorized": False,
        }
    return output


def _direction_for_detection(detection: Mapping[str, Any]) -> str:
    origin = str(detection.get("signal_origin") or "")
    direction = str(detection.get("direction") or "").strip().lower()
    if direction in {"long", "short"}:
        return direction
    if origin in ORIGIN_DIRECTIONS:
        return ORIGIN_DIRECTIONS[origin]
    metrics = detection.get("metrics") if isinstance(detection.get("metrics"), Mapping) else {}
    lower = _to_float(metrics.get("lower_wick_ratio"))
    upper = _to_float(metrics.get("upper_wick_ratio"))
    if lower is not None or upper is not None:
        return "long" if float(lower or 0.0) >= float(upper or 0.0) else "short"
    return "long"


def _timeframes_from_expansion(pattern_expansion: Mapping[str, Any] | None) -> list[str]:
    if isinstance(pattern_expansion, Mapping):
        scope = pattern_expansion.get("target_scope") if isinstance(pattern_expansion.get("target_scope"), Mapping) else {}
        value = scope.get("timeframes")
        if value:
            return _normalize_timeframes(value)
    return list(DEFAULT_TIMEFRAMES)


def _recommended_next_operator_move(aggregate: Mapping[str, Any], rankings: Sequence[Mapping[str, Any]]) -> str:
    if rankings and aggregate.get("origins_with_positive_bias"):
        return "RUN_R204_PATTERN_KETER_RESCORING_FAMILY"
    if aggregate.get("total_mapped_count"):
        return "RUN_R203_ANCHOR_SIGNAL_CONFLUENCE_MATRIX"
    return "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"


def _recommended_next_engineering_move(aggregate: Mapping[str, Any], rankings: Sequence[Mapping[str, Any]]) -> str:
    if rankings and aggregate.get("origins_with_positive_bias"):
        return "Build R204 paper-only Keter rescoring from R202 rankings without config writes, Binance calls, or promotion."
    if aggregate.get("total_mapped_count"):
        return "Build R203 anchor x signal-origin confluence matrix from R201/R202 summaries without live authorization."
    return "Keep collecting local pattern detections and future candles, then rerun R202 preview."


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


def _risk_warnings(*, mapped_count: int, stats: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    if mapped_count < 30:
        warnings.append("sample_size_below_30")
    if float(stats.get("simple_failure_rate_pct") or 0.0) > float(stats.get("simple_success_rate_pct") or 0.0):
        warnings.append("failure_rate_exceeds_success_rate")
    if float(stats.get("favorable_close_rate_pct") or 0.0) < 50.0:
        warnings.append("favorable_close_rate_below_50")
    return warnings


def _score(*, stats: Mapping[str, Any], mapped_count: int) -> float:
    sample_factor = min(1.0, mapped_count / 50.0)
    raw = (
        float(stats.get("simple_success_rate_pct") or 0.0)
        + float(stats.get("favorable_close_rate_pct") or 0.0)
        - float(stats.get("simple_failure_rate_pct") or 0.0)
        + float(stats.get("avg_favorable_move_pct") or 0.0)
        - float(stats.get("avg_adverse_move_pct") or 0.0)
    )
    return _round(raw * sample_factor)


def _confidence_for_count(mapped_count: int) -> str:
    if mapped_count >= 100:
        return "HIGH"
    if mapped_count >= 30:
        return "MEDIUM"
    return "LOW"


def _normalize_timeframes(value: Sequence[str] | str | None) -> list[str]:
    if value is None:
        return list(DEFAULT_TIMEFRAMES)
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    else:
        parts = [str(part).strip() for part in value]
    return [part for part in parts if part]


def _normalize_direction(value: Any) -> str:
    direction = str(value or "").strip().lower()
    return direction if direction in {"long", "short"} else "long"


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


def _candle_time(candle: Mapping[str, Any]) -> str:
    return str(candle.get("open_time") or candle.get("timestamp") or "")


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
