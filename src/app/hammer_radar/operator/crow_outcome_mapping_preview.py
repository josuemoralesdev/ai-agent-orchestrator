"""R193 Three Black Crows paper outcome mapping preview.

This module maps local R189 Three Black Crows detections to future local OHLC
candles. It is audit-only and paper-only: no Binance/network calls, payload
creation, config writes, lane/origin promotion, or live authorization.
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
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, normalize_lane_key
from src.app.hammer_radar.operator.local_candle_feed_adapter import (
    MAX_LATEST_CANDLES,
    load_local_candle_feed,
    normalize_local_candle_feed,
    resolve_local_candle_feed_path,
)
from src.app.hammer_radar.operator.three_black_crows_detector import (
    DEFAULT_DIRECTION,
    DEFAULT_SYMBOL,
    DEFAULT_TIMEFRAME,
    SIGNAL_ORIGIN,
)
from src.app.hammer_radar.operator.three_black_crows_local_feed_detection import (
    LEDGER_FILENAME as THREE_BLACK_CROWS_DETECTION_LEDGER_FILENAME,
    PAPER_TAG_LEDGER_FILENAME,
    three_black_crows_local_detection_records_path,
    three_black_crows_paper_tag_records_path,
)

CROW_OUTCOME_MAPPING_PREVIEW_READY = "CROW_OUTCOME_MAPPING_PREVIEW_READY"
CROW_OUTCOME_MAPPING_PREVIEW_REJECTED = "CROW_OUTCOME_MAPPING_PREVIEW_REJECTED"
CROW_OUTCOME_MAPPING_PREVIEW_RECORDED = "CROW_OUTCOME_MAPPING_PREVIEW_RECORDED"
CROW_OUTCOME_MAPPING_PREVIEW_BLOCKED = "CROW_OUTCOME_MAPPING_PREVIEW_BLOCKED"
CROW_OUTCOME_MAPPING_PREVIEW_ERROR = "CROW_OUTCOME_MAPPING_PREVIEW_ERROR"

OUTCOME_MAPPING_AVAILABLE = "OUTCOME_MAPPING_AVAILABLE"
OUTCOME_MAPPING_PARTIAL_FUTURE_CANDLES_MISSING = "OUTCOME_MAPPING_PARTIAL_FUTURE_CANDLES_MISSING"
OUTCOME_MAPPING_NO_DETECTIONS = "OUTCOME_MAPPING_NO_DETECTIONS"
OUTCOME_MAPPING_NO_LOCAL_CANDLES = "OUTCOME_MAPPING_NO_LOCAL_CANDLES"
OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW = "OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "CROW_OUTCOME_MAPPING_PREVIEW"
LEDGER_FILENAME = "crow_outcome_mapping_preview.ndjson"
DEFAULT_ENTRY_MODE = "ladder_close_50_618"
DEFAULT_TARGET_LANE_KEY = "BTCUSDT|8m|short|ladder_close_50_618"
DEFAULT_WINDOWS = (1, 3, 5, 10)
DEFAULT_SUCCESS_THRESHOLD_PCT = 0.10
DEFAULT_ADVERSE_THRESHOLD_PCT = 0.10
CONFIRM_CROW_OUTCOME_MAPPING_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM CROW OUTCOME MAPPING PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{THREE_BLACK_CROWS_DETECTION_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{PAPER_TAG_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/candle_archive/BTCUSDT_8m.ndjson",
    "operator.local_candle_feed_adapter.load_local_candle_feed",
    "operator.local_candle_feed_adapter.normalize_local_candle_feed",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_crow_outcome_mapping_preview(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    success_threshold_pct: float = DEFAULT_SUCCESS_THRESHOLD_PCT,
    adverse_threshold_pct: float = DEFAULT_ADVERSE_THRESHOLD_PCT,
    record_mapping: bool = False,
    confirm_crow_outcome_mapping: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    normalized_timeframe = str(timeframe or DEFAULT_TIMEFRAME).strip()
    normalized_lane = _normalize_lane_key(lane_key, normalized_symbol, normalized_timeframe)
    success_threshold = _bounded_float(success_threshold_pct, DEFAULT_SUCCESS_THRESHOLD_PCT)
    adverse_threshold = _bounded_float(adverse_threshold_pct, DEFAULT_ADVERSE_THRESHOLD_PCT)
    confirmation_valid = confirm_crow_outcome_mapping == CONFIRM_CROW_OUTCOME_MAPPING_PREVIEW_RECORDING_PHRASE
    try:
        detection_records = load_three_black_crows_detections(log_dir=resolved_log_dir, limit=0)
        paper_tags_all = load_three_black_crows_paper_tags(log_dir=resolved_log_dir, limit=0)
        detections = _latest_matching_detections(
            detection_records,
            signal_origin=SIGNAL_ORIGIN,
            lane_key=normalized_lane,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
        )
        detection_ids = {str(row.get("detection_id") or "") for row in detections if row.get("detection_id")}
        paper_tags = [
            dict(row)
            for row in paper_tags_all
            if _row_targets(
                row,
                signal_origin=SIGNAL_ORIGIN,
                lane_key=normalized_lane,
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
            )
            and (not detection_ids or str(row.get("detection_id") or "") in detection_ids)
        ]
        candles = load_local_8m_candles_for_outcome_mapping(
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
        )
        mapped_outcomes: list[dict[str, Any]] = []
        skipped = 0
        for detection in detections:
            future = map_detection_to_future_candles(detection, candles, windows=DEFAULT_WINDOWS)
            if not future.get("entry_reference_price") or not future.get("future_candles"):
                skipped += 1
                continue
            mapped_outcomes.append(
                {
                    "detection_id": detection.get("detection_id"),
                    "detected_at": detection.get("detected_at"),
                    "mode": detection.get("mode"),
                    "confidence": detection.get("confidence"),
                    "entry_reference_price": future["entry_reference_price"],
                    "entry_reference_source": future["entry_reference_source"],
                    "windows": compute_short_outcome_window(
                        entry_reference_price=float(future["entry_reference_price"]),
                        future_candles=future["future_candles"],
                        windows=DEFAULT_WINDOWS,
                        success_threshold_pct=success_threshold,
                        adverse_threshold_pct=adverse_threshold,
                    ),
                    "outcome_mapping_status": future["outcome_mapping_status"],
                    "paper_only": True,
                    "live_authorized": False,
                }
            )
        aggregate = build_crow_outcome_summary(mapped_outcomes)
        outcome_mapping_status = classify_crow_outcome_mapping_status(
            detections=detections,
            candles=candles,
            mapped_outcomes=mapped_outcomes,
        )
        interpretation = _interpretation(aggregate, outcome_mapping_status)
        status = _status_for_preview(
            record_mapping=record_mapping,
            confirmation_valid=confirmation_valid,
            outcome_mapping_status=outcome_mapping_status,
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "mapping_recorded": False,
            "mapping_id": None,
            "record_mapping_requested": bool(record_mapping),
            "confirmation_valid": bool(confirmation_valid),
            "target_context": _target_context(normalized_symbol, normalized_timeframe, normalized_lane),
            "input_summary": {
                "detections_loaded": len(detections),
                "paper_tags_loaded": len(paper_tags),
                "candles_loaded": len(candles),
                "valid_detections_mapped": len(mapped_outcomes),
                "detections_skipped": skipped,
            },
            "outcome_windows": {
                "windows_candles": list(DEFAULT_WINDOWS),
                "entry_reference": "detection_close_or_next_open",
                "success_threshold_pct": success_threshold,
                "adverse_threshold_pct": adverse_threshold,
            },
            "mapped_outcomes": mapped_outcomes,
            "aggregate_summary": aggregate,
            "outcome_mapping_status": outcome_mapping_status,
            "interpretation": interpretation,
            "recommended_next_operator_move": _recommended_next_operator_move(outcome_mapping_status, interpretation),
            "recommended_next_engineering_move": _recommended_next_engineering_move(outcome_mapping_status, interpretation),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_mapping and confirmation_valid and status != CROW_OUTCOME_MAPPING_PREVIEW_BLOCKED:
            record = append_crow_outcome_mapping_preview_record(payload, log_dir=resolved_log_dir)
            payload["status"] = CROW_OUTCOME_MAPPING_PREVIEW_RECORDED
            payload["mapping_recorded"] = True
            payload["mapping_id"] = record["mapping_id"]
            payload["ledger_path"] = str(crow_outcome_mapping_preview_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": CROW_OUTCOME_MAPPING_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "mapping_recorded": False,
                "mapping_id": None,
                "record_mapping_requested": bool(record_mapping),
                "confirmation_valid": bool(confirmation_valid),
                "target_context": _target_context(normalized_symbol, normalized_timeframe, normalized_lane),
                "input_summary": {
                    "detections_loaded": 0,
                    "paper_tags_loaded": 0,
                    "candles_loaded": 0,
                    "valid_detections_mapped": 0,
                    "detections_skipped": 0,
                },
                "outcome_windows": {
                    "windows_candles": list(DEFAULT_WINDOWS),
                    "entry_reference": "detection_close_or_next_open",
                    "success_threshold_pct": success_threshold,
                    "adverse_threshold_pct": adverse_threshold,
                },
                "mapped_outcomes": [],
                "aggregate_summary": build_crow_outcome_summary([]),
                "outcome_mapping_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "interpretation": _interpretation({}, UNKNOWN_NEEDS_MANUAL_REVIEW),
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R193 outcome mapping error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_three_black_crows_detections(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = three_black_crows_local_detection_records_path(get_log_dir(log_dir, use_env=True))
    return _load_ndjson(path, limit=limit)


def load_three_black_crows_paper_tags(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = three_black_crows_paper_tag_records_path(get_log_dir(log_dir, use_env=True))
    return _load_ndjson(path, limit=limit)


def load_local_8m_candles_for_outcome_mapping(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> list[dict[str, Any]]:
    source_path = resolve_local_candle_feed_path(log_dir=log_dir, symbol=symbol, timeframe=timeframe)
    records = load_local_candle_feed(source_path, latest_candles=MAX_LATEST_CANDLES)
    candles = normalize_local_candle_feed(
        records,
        symbol=str(symbol or DEFAULT_SYMBOL).upper(),
        timeframe=str(timeframe or DEFAULT_TIMEFRAME),
        source=source_path.name,
        latest_candles=MAX_LATEST_CANDLES,
    )
    candles.sort(key=lambda row: str(row.get("open_time") or row.get("timestamp") or ""))
    return candles


def map_detection_to_future_candles(
    detection: Mapping[str, Any],
    candles: Sequence[Mapping[str, Any]],
    *,
    windows: Sequence[int] = DEFAULT_WINDOWS,
) -> dict[str, Any]:
    detected_at = str(detection.get("detected_at") or "")
    rows = [dict(row) for row in candles]
    rows.sort(key=lambda row: str(row.get("open_time") or row.get("timestamp") or ""))
    detection_index = next(
        (index for index, row in enumerate(rows) if _candle_time(row) == detected_at),
        None,
    )
    if detection_index is None:
        return {
            "entry_reference_price": None,
            "entry_reference_source": None,
            "future_candles": [],
            "outcome_mapping_status": OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW,
        }
    detection_close = _to_float(rows[detection_index].get("close"))
    next_open = _to_float(rows[detection_index + 1].get("open")) if detection_index + 1 < len(rows) else None
    entry = detection_close if detection_close is not None else next_open
    entry_source = "detection_close" if detection_close is not None else "next_candle_open"
    max_window = max((int(window) for window in windows), default=0)
    future_candles = rows[detection_index + 1 : detection_index + 1 + max_window]
    status = OUTCOME_MAPPING_AVAILABLE if len(future_candles) >= max_window else OUTCOME_MAPPING_PARTIAL_FUTURE_CANDLES_MISSING
    if not future_candles:
        status = OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW
    return {
        "entry_reference_price": entry,
        "entry_reference_source": entry_source,
        "future_candles": future_candles,
        "future_candles_available": len(future_candles),
        "outcome_mapping_status": status,
    }


def compute_short_outcome_window(
    *,
    entry_reference_price: float,
    future_candles: Sequence[Mapping[str, Any]],
    windows: Sequence[int] = DEFAULT_WINDOWS,
    success_threshold_pct: float = DEFAULT_SUCCESS_THRESHOLD_PCT,
    adverse_threshold_pct: float = DEFAULT_ADVERSE_THRESHOLD_PCT,
) -> dict[str, dict[str, Any]]:
    if entry_reference_price <= 0:
        return {}
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
        mfe_downside = ((entry_reference_price - min_low) / entry_reference_price) * 100
        mae_upside = ((max_high - entry_reference_price) / entry_reference_price) * 100
        output[str(window)] = {
            "future_close_time": _candle_time(rows[-1]),
            "close_return_pct": _round(close_return),
            "mfe_downside_pct": _round(max(0.0, mfe_downside)),
            "mae_upside_pct": _round(max(0.0, mae_upside)),
            "favorable_close": close_return < 0,
            "adverse_close": close_return > 0,
            "simple_success": mfe_downside >= success_threshold_pct,
            "simple_failure": mae_upside >= adverse_threshold_pct,
        }
    return output


def build_crow_outcome_summary(mapped_outcomes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    strict_count = sum(1 for row in mapped_outcomes if str(row.get("mode") or "") == "strict")
    loose_count = sum(1 for row in mapped_outcomes if str(row.get("mode") or "") == "loose_preview")
    window_stats = {str(window): _window_stats(mapped_outcomes, str(window)) for window in DEFAULT_WINDOWS}
    scored = {
        window: stats
        for window, stats in window_stats.items()
        if int(stats.get("mapped_count") or 0) > 0
    }
    best_window = max(scored, key=lambda key: (float(scored[key]["simple_success_rate_pct"]), float(scored[key]["favorable_close_rate_pct"])), default="unknown")
    worst_window = min(scored, key=lambda key: (float(scored[key]["simple_success_rate_pct"]), -float(scored[key]["simple_failure_rate_pct"])), default="unknown")
    return {
        "mapped_count": len(mapped_outcomes),
        "strict_mapped_count": strict_count,
        "loose_mapped_count": loose_count,
        "window_stats": window_stats,
        "best_window": best_window,
        "worst_window": worst_window,
    }


def classify_crow_outcome_mapping_status(
    *,
    detections: Sequence[Mapping[str, Any]],
    candles: Sequence[Mapping[str, Any]],
    mapped_outcomes: Sequence[Mapping[str, Any]],
) -> str:
    if not detections:
        return OUTCOME_MAPPING_NO_DETECTIONS
    if not candles:
        return OUTCOME_MAPPING_NO_LOCAL_CANDLES
    if not mapped_outcomes:
        return OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW
    if any(str(row.get("outcome_mapping_status") or "") != OUTCOME_MAPPING_AVAILABLE for row in mapped_outcomes):
        return OUTCOME_MAPPING_PARTIAL_FUTURE_CANDLES_MISSING
    return OUTCOME_MAPPING_AVAILABLE


def append_crow_outcome_mapping_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = crow_outcome_mapping_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "mapping_id": str(record.get("mapping_id") or f"r193_crow_outcome_mapping_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_mapping_requested": bool(record.get("record_mapping_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_context": dict(record.get("target_context") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "outcome_windows": dict(record.get("outcome_windows") or {}),
            "mapped_outcomes": list(record.get("mapped_outcomes") or []),
            "aggregate_summary": dict(record.get("aggregate_summary") or {}),
            "outcome_mapping_status": record.get("outcome_mapping_status"),
            "interpretation": dict(record.get("interpretation") or {}),
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


def load_crow_outcome_mapping_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = crow_outcome_mapping_preview_records_path(get_log_dir(log_dir, use_env=True))
    return _load_ndjson(path, limit=limit)


def summarize_crow_outcome_mapping_previews(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    mapping_status_counts = Counter(str(record.get("outcome_mapping_status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "outcome_mapping_status_counts": dict(sorted(mapping_status_counts.items())),
        "last_mapping_id": latest.get("mapping_id") if isinstance(latest, Mapping) else None,
        "last_mapped_count": (latest.get("aggregate_summary") or {}).get("mapped_count") if isinstance(latest, Mapping) else 0,
        "safety": dict(SAFETY),
    }


def crow_outcome_mapping_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_crow_outcome_mapping_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _latest_matching_detections(
    records: Sequence[Mapping[str, Any]],
    *,
    signal_origin: str,
    lane_key: str,
    symbol: str,
    timeframe: str,
) -> list[dict[str, Any]]:
    matching_records = [
        record
        for record in records
        if isinstance(record, Mapping)
        and _record_targets(record, signal_origin=signal_origin, lane_key=lane_key, symbol=symbol, timeframe=timeframe)
    ]
    if not matching_records:
        return []
    matching_records.sort(key=lambda row: str(row.get("recorded_at_utc") or row.get("generated_at") or ""), reverse=True)
    latest = matching_records[0]
    return [
        dict(row)
        for row in latest.get("detections") or []
        if isinstance(row, Mapping)
        and _row_targets(row, signal_origin=signal_origin, lane_key=lane_key, symbol=symbol, timeframe=timeframe)
    ]


def _record_targets(
    record: Mapping[str, Any],
    *,
    signal_origin: str,
    lane_key: str,
    symbol: str,
    timeframe: str,
) -> bool:
    target = record.get("target_context") if isinstance(record.get("target_context"), Mapping) else {}
    if _row_targets(target, signal_origin=signal_origin, lane_key=lane_key, symbol=symbol, timeframe=timeframe):
        return True
    return any(
        isinstance(row, Mapping) and _row_targets(row, signal_origin=signal_origin, lane_key=lane_key, symbol=symbol, timeframe=timeframe)
        for row in record.get("detections") or []
    )


def _row_targets(
    row: Mapping[str, Any],
    *,
    signal_origin: str,
    lane_key: str,
    symbol: str,
    timeframe: str,
) -> bool:
    origin = str(row.get("signal_origin") or signal_origin).strip()
    lane = str(row.get("lane_key") or row.get("primary_lane") or "").strip()
    return (
        origin == signal_origin
        and (not lane or lane == lane_key)
        and str(row.get("symbol") or symbol).upper() == symbol
        and str(row.get("timeframe") or timeframe) == timeframe
    )


def _window_stats(mapped_outcomes: Sequence[Mapping[str, Any]], window: str) -> dict[str, Any]:
    rows = [
        dict((outcome.get("windows") or {}).get(window) or {})
        for outcome in mapped_outcomes
        if isinstance((outcome.get("windows") or {}).get(window), Mapping)
    ]
    count = len(rows)
    if not rows:
        return {
            "mapped_count": 0,
            "favorable_close_rate_pct": 0.0,
            "simple_success_rate_pct": 0.0,
            "simple_failure_rate_pct": 0.0,
            "avg_close_return_pct": 0.0,
            "avg_mfe_downside_pct": 0.0,
            "avg_mae_upside_pct": 0.0,
        }
    return {
        "mapped_count": count,
        "favorable_close_rate_pct": _rate(rows, "favorable_close"),
        "simple_success_rate_pct": _rate(rows, "simple_success"),
        "simple_failure_rate_pct": _rate(rows, "simple_failure"),
        "avg_close_return_pct": _avg(rows, "close_return_pct"),
        "avg_mfe_downside_pct": _avg(rows, "mfe_downside_pct"),
        "avg_mae_upside_pct": _avg(rows, "mae_upside_pct"),
    }


def _interpretation(aggregate: Mapping[str, Any], outcome_mapping_status: str) -> dict[str, Any]:
    stats = (aggregate.get("window_stats") or {}).get("3") or {}
    mapped_count = int(aggregate.get("mapped_count") or 0)
    favorable = float(stats.get("favorable_close_rate_pct") or 0.0)
    success = float(stats.get("simple_success_rate_pct") or 0.0)
    failure = float(stats.get("simple_failure_rate_pct") or 0.0)
    supports = None
    if mapped_count > 0:
        supports = favorable >= 50.0 and success >= failure
    needs_more = mapped_count < 30 or outcome_mapping_status != OUTCOME_MAPPING_AVAILABLE
    if outcome_mapping_status in {OUTCOME_MAPPING_NO_DETECTIONS, OUTCOME_MAPPING_NO_LOCAL_CANDLES, OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW}:
        why = "Outcome mapping is blocked because required local detections or future candles are missing."
    elif supports:
        why = "Mapped paper windows show favorable short closes and downside MFE at least matching adverse MAE pressure; still needs more paper samples before scoring feedback."
    else:
        why = "Mapped paper windows do not yet show enough favorable short follow-through to support promotion review."
    return {
        "supports_short_bias": supports,
        "needs_more_samples": needs_more,
        "paper_tracking_recommended": mapped_count > 0,
        "live_ready": False,
        "why": why,
    }


def _status_for_preview(*, record_mapping: bool, confirmation_valid: bool, outcome_mapping_status: str) -> str:
    if record_mapping and not confirmation_valid:
        return CROW_OUTCOME_MAPPING_PREVIEW_REJECTED
    if outcome_mapping_status in {OUTCOME_MAPPING_NO_DETECTIONS, OUTCOME_MAPPING_NO_LOCAL_CANDLES, OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW}:
        return CROW_OUTCOME_MAPPING_PREVIEW_BLOCKED
    if record_mapping and confirmation_valid:
        return CROW_OUTCOME_MAPPING_PREVIEW_RECORDED
    return CROW_OUTCOME_MAPPING_PREVIEW_READY


def _recommended_next_operator_move(outcome_mapping_status: str, interpretation: Mapping[str, Any]) -> str:
    if outcome_mapping_status == OUTCOME_MAPPING_AVAILABLE and interpretation.get("supports_short_bias") is True:
        return "RUN_R194_CROW_OUTCOME_KETER_FEEDBACK"
    if outcome_mapping_status in {OUTCOME_MAPPING_NO_DETECTIONS, OUTCOME_MAPPING_INSUFFICIENT_FUTURE_WINDOW}:
        return "KEEP_8M_SHORT_WATCHER_RUNNING"
    if outcome_mapping_status == OUTCOME_MAPPING_NO_LOCAL_CANDLES:
        return "KEEP_MULTI_LANE_HARVESTER_RUNNING"
    return "COLLECT_MORE_CROW_DETECTIONS"


def _recommended_next_engineering_move(outcome_mapping_status: str, interpretation: Mapping[str, Any]) -> str:
    if outcome_mapping_status == OUTCOME_MAPPING_AVAILABLE and interpretation.get("supports_short_bias") is True:
        return "Build R194 paper-only Keter feedback from R193 outcomes without config writes, Binance calls, or promotion."
    if outcome_mapping_status == OUTCOME_MAPPING_PARTIAL_FUTURE_CANDLES_MISSING:
        return "Keep collecting local BTCUSDT 8m candles, then rerun R193 before Keter feedback."
    return "Keep R193 as an audit-only mapping surface and collect more local crow detections/future candles."


def _target_context(symbol: str, timeframe: str, lane_key: str) -> dict[str, Any]:
    return {
        "primary_lane": lane_key,
        "symbol": str(symbol or DEFAULT_SYMBOL).upper(),
        "timeframe": str(timeframe or DEFAULT_TIMEFRAME),
        "direction": DEFAULT_DIRECTION,
        "signal_origin": SIGNAL_ORIGIN,
    }


def _normalize_lane_key(lane_key: str, symbol: str, timeframe: str) -> str:
    value = str(lane_key or "").strip()
    if value:
        return value
    return normalize_lane_key(symbol, timeframe, DEFAULT_DIRECTION, DEFAULT_ENTRY_MODE)


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
