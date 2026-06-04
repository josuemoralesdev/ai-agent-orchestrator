"""R189 Three Black Crows detection on the R188 local candle feed.

This module is paper-only local detector/tagging wiring. It reads local OHLC
archive records through the R188 adapter helpers and appends only R189 ledgers
after explicit confirmation. It never calls Binance or any network, creates
payloads, mutates env/config, changes lane modes, promotes origins/lanes, or
authorizes live execution.
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
    DETECTOR_READY_LOCAL_OHLC_AVAILABLE,
    LOCAL_OHLC_INVALID,
    LOCAL_OHLC_MISSING,
    load_local_candle_feed,
    normalize_local_candle_feed,
    resolve_local_candle_feed_path,
    validate_normalized_candle_feed,
)
from src.app.hammer_radar.operator.three_black_crows_detector import (
    DEFAULT_DIRECTION,
    DEFAULT_LATEST_CANDLES,
    DEFAULT_SYMBOL,
    DEFAULT_TIMEFRAME,
    MAX_LATEST_CANDLES,
    SIGNAL_ORIGIN,
    detect_three_black_crows_sequences,
)

THREE_BLACK_CROWS_LOCAL_DETECTION_READY = "THREE_BLACK_CROWS_LOCAL_DETECTION_READY"
THREE_BLACK_CROWS_LOCAL_DETECTION_REJECTED = "THREE_BLACK_CROWS_LOCAL_DETECTION_REJECTED"
THREE_BLACK_CROWS_LOCAL_DETECTION_RECORDED = "THREE_BLACK_CROWS_LOCAL_DETECTION_RECORDED"
THREE_BLACK_CROWS_LOCAL_DETECTION_BLOCKED = "THREE_BLACK_CROWS_LOCAL_DETECTION_BLOCKED"
THREE_BLACK_CROWS_LOCAL_DETECTION_ERROR = "THREE_BLACK_CROWS_LOCAL_DETECTION_ERROR"

STRICT_DETECTIONS_FOUND = "STRICT_DETECTIONS_FOUND"
LOOSE_DETECTIONS_FOUND = "LOOSE_DETECTIONS_FOUND"
STRICT_AND_LOOSE_DETECTIONS_FOUND = "STRICT_AND_LOOSE_DETECTIONS_FOUND"
NO_DETECTIONS_FOUND = "NO_DETECTIONS_FOUND"
LOCAL_FEED_MISSING = "LOCAL_FEED_MISSING"
LOCAL_FEED_INVALID = "LOCAL_FEED_INVALID"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "THREE_BLACK_CROWS_LOCAL_DETECTION"
TAG_EVENT_TYPE = "THREE_BLACK_CROWS_PAPER_TAG"
LEDGER_FILENAME = "three_black_crows_local_detections.ndjson"
PAPER_TAG_LEDGER_FILENAME = "three_black_crows_paper_tags.ndjson"
CONFIRM_THREE_BLACK_CROWS_LOCAL_DETECTION_RECORDING_PHRASE = (
    "I CONFIRM THREE BLACK CROWS LOCAL DETECTION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "candle_feed_written": False,
    "fake_ohlc_created": False,
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
    "logs/hammer_radar_forward/candle_archive/BTCUSDT_8m.ndjson",
    "operator.local_candle_feed_adapter.resolve_local_candle_feed_path",
    "operator.local_candle_feed_adapter.load_local_candle_feed",
    "operator.local_candle_feed_adapter.normalize_local_candle_feed",
    "operator.local_candle_feed_adapter.validate_normalized_candle_feed",
    "operator.three_black_crows_detector.detect_three_black_crows_sequences",
    "logs/hammer_radar_forward/signal_origin_registry.ndjson",
    "logs/hammer_radar_forward/keter_signal_origin_scoring.ndjson",
    "logs/hammer_radar_forward/signal_origin_lane_matrix.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{PAPER_TAG_LEDGER_FILENAME}",
]


def build_three_black_crows_local_feed_detection(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    latest_candles: int = DEFAULT_LATEST_CANDLES,
    mode: str = "both",
    record_detection: bool = False,
    confirm_three_black_crows_local_detection: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    normalized_timeframe = str(timeframe or DEFAULT_TIMEFRAME).strip()
    normalized_mode = _normalize_mode(mode)
    confirmation_valid = (
        confirm_three_black_crows_local_detection == CONFIRM_THREE_BLACK_CROWS_LOCAL_DETECTION_RECORDING_PHRASE
    )
    try:
        source_path = resolve_local_candle_feed_path(
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
        )
        raw_records = load_local_candle_feed(source_path, latest_candles=latest_candles)
        candles = normalize_local_candle_feed(
            raw_records,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            source=source_path.name,
            latest_candles=latest_candles,
        )
        validation = validate_normalized_candle_feed(
            source_path=source_path,
            normalized_candles=candles,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            latest_candles=latest_candles,
        )
        feed_ready = bool(validation.get("source_found")) and bool(validation.get("all_normalized_records_valid")) and bool(candles)
        detector_result = run_three_black_crows_detection_on_local_feed(
            candles,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            mode=normalized_mode,
            feed_ready=feed_ready,
            feed_missing=not bool(validation.get("source_found")),
        )
        detections = build_three_black_crows_detection_records(
            strict_detections=detector_result["strict_detections"],
            loose_detections=detector_result["loose_detections"],
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            mode=normalized_mode,
        )
        status = _status_for_detection(
            record_detection=record_detection,
            confirmation_valid=confirmation_valid,
            feed_ready=feed_ready,
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "detection_recorded": False,
            "detection_id": None,
            "record_detection_requested": bool(record_detection),
            "confirmation_valid": bool(confirmation_valid),
            "target_context": _target_context(normalized_symbol, normalized_timeframe),
            "local_feed": {
                "source_path": _display_archive_path(normalized_symbol, normalized_timeframe),
                "records_loaded": len(raw_records),
                "valid_records": int(validation.get("valid_records") or 0),
                "latest_candle_time": _latest_candle_time(candles),
                "feed_ready": bool(feed_ready),
                "adapter_readiness": _adapter_readiness(validation=validation, feed_ready=feed_ready),
            },
            "detector_result": {
                "strict_detections_found": int(detector_result["strict_detections_found"]),
                "loose_detections_found": int(detector_result["loose_detections_found"]),
                "latest_detection_at": detector_result["latest_detection_at"],
                "detection_status": detector_result["detection_status"],
                "paper_only": True,
                "live_authorized": False,
            },
            "detections": detections,
            "paper_tags": {
                "tags_created": 0,
                "tag_ledger_path": _display_tag_ledger_path(),
                "paper_only": True,
                "live_authorized": False,
            },
            "lane_detection_summary": build_three_black_crows_lane_detection_summary(
                strict_detections_found=int(detector_result["strict_detections_found"]),
                loose_detections_found=int(detector_result["loose_detections_found"]),
                latest_detection_at=detector_result["latest_detection_at"],
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
            ),
            "origin_feedback": build_three_black_crows_origin_feedback(),
            "recommended_next_operator_move": _recommended_next_operator_move(detector_result["detection_status"]),
            "recommended_next_engineering_move": _recommended_next_engineering_move(detector_result["detection_status"]),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_detection and confirmation_valid and feed_ready:
            paper_tags = build_three_black_crows_paper_tags(detections)
            appended_tags = append_three_black_crows_paper_tag_records(paper_tags, log_dir=resolved_log_dir)
            payload["status"] = THREE_BLACK_CROWS_LOCAL_DETECTION_RECORDED
            payload["paper_tags"]["tags_created"] = len(appended_tags)
            payload["paper_tags"]["tags_recorded"] = len(appended_tags)
            record = append_three_black_crows_local_detection_record(payload, log_dir=resolved_log_dir)
            payload["detection_recorded"] = True
            payload["detection_id"] = record["detection_id"]
            payload["ledger_path"] = str(three_black_crows_local_detection_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": THREE_BLACK_CROWS_LOCAL_DETECTION_ERROR,
                "generated_at": generated_at.isoformat(),
                "detection_recorded": False,
                "detection_id": None,
                "record_detection_requested": bool(record_detection),
                "confirmation_valid": bool(confirmation_valid),
                "target_context": _target_context(normalized_symbol, normalized_timeframe),
                "local_feed": {
                    "source_path": _display_archive_path(normalized_symbol, normalized_timeframe),
                    "records_loaded": 0,
                    "valid_records": 0,
                    "latest_candle_time": None,
                    "feed_ready": False,
                    "adapter_readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                },
                "detector_result": _empty_detector_result(UNKNOWN_NEEDS_MANUAL_REVIEW),
                "detections": [],
                "paper_tags": {
                    "tags_created": 0,
                    "tag_ledger_path": _display_tag_ledger_path(),
                    "paper_only": True,
                    "live_authorized": False,
                },
                "lane_detection_summary": build_three_black_crows_lane_detection_summary(),
                "origin_feedback": build_three_black_crows_origin_feedback(),
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R189 local-feed detection error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def run_three_black_crows_detection_on_local_feed(
    candles: Sequence[Mapping[str, Any]],
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    mode: str = "both",
    feed_ready: bool = True,
    feed_missing: bool = False,
) -> dict[str, Any]:
    normalized_mode = _normalize_mode(mode)
    if feed_missing:
        return {**_empty_detector_result(LOCAL_FEED_MISSING), "strict_detections": [], "loose_detections": []}
    if not feed_ready or len(candles) < 3:
        return {**_empty_detector_result(LOCAL_FEED_INVALID), "strict_detections": [], "loose_detections": []}
    strict = (
        detect_three_black_crows_sequences(candles, symbol=symbol, timeframe=timeframe, mode="strict")
        if normalized_mode in {"strict", "both"}
        else []
    )
    loose = (
        detect_three_black_crows_sequences(candles, symbol=symbol, timeframe=timeframe, mode="loose_preview")
        if normalized_mode in {"loose_preview", "both"}
        else []
    )
    latest_detection_at = max((str(row.get("detected_at") or "") for row in [*strict, *loose]), default=None)
    return {
        "strict_detections_found": len(strict),
        "loose_detections_found": len(loose),
        "latest_detection_at": latest_detection_at,
        "detection_status": _detection_status(strict, loose),
        "paper_only": True,
        "live_authorized": False,
        "strict_detections": list(strict),
        "loose_detections": list(loose),
    }


def build_three_black_crows_detection_records(
    *,
    strict_detections: Sequence[Mapping[str, Any]] | None = None,
    loose_detections: Sequence[Mapping[str, Any]] | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    mode: str = "both",
) -> list[dict[str, Any]]:
    lane_key = normalize_lane_key(symbol, timeframe, DEFAULT_DIRECTION, "ladder_close_50_618")
    rows: list[dict[str, Any]] = []
    if _normalize_mode(mode) in {"strict", "both"}:
        rows.extend(_detection_record(row, lane_key=lane_key, symbol=symbol, timeframe=timeframe) for row in strict_detections or [])
    if _normalize_mode(mode) in {"loose_preview", "both"}:
        rows.extend(_detection_record(row, lane_key=lane_key, symbol=symbol, timeframe=timeframe) for row in loose_detections or [])
    return rows


def build_three_black_crows_paper_tags(detections: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    tags: list[dict[str, Any]] = []
    for detection in detections:
        tags.append(
            {
                "tag_id": f"r189_three_black_crows_tag_{uuid4().hex}",
                "detection_id": detection.get("detection_id"),
                "signal_origin": SIGNAL_ORIGIN,
                "lane_key": detection.get("lane_key"),
                "symbol": detection.get("symbol"),
                "timeframe": detection.get("timeframe"),
                "direction": detection.get("direction"),
                "mode": detection.get("mode"),
                "detected_at": detection.get("detected_at"),
                "confidence": detection.get("confidence"),
                "paper_only": True,
                "live_authorized": False,
                "signal_origin_promoted": False,
                "lane_promoted": False,
            }
        )
    return tags


def build_three_black_crows_lane_detection_summary(
    *,
    strict_detections_found: int = 0,
    loose_detections_found: int = 0,
    latest_detection_at: str | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> dict[str, Any]:
    lane_key = normalize_lane_key(symbol, timeframe, DEFAULT_DIRECTION, "ladder_close_50_618")
    return {
        lane_key: {
            "strict_detections_found": int(strict_detections_found),
            "loose_detections_found": int(loose_detections_found),
            "latest_detection_at": latest_detection_at,
            "ready_for_paper_tracking": bool(strict_detections_found or loose_detections_found),
            "ready_for_live": False,
        }
    }


def build_three_black_crows_origin_feedback() -> dict[str, Any]:
    return {
        "signal_origin": SIGNAL_ORIGIN,
        "previous_availability": "REGISTRY_ONLY",
        "new_local_detector_available": True,
        "recommended_future_registry_status": "DETECTOR_AVAILABLE_AFTER_REVIEW",
        "still_paper_only": True,
        "requires_R190_feedback_sync": True,
    }


def append_three_black_crows_local_detection_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = three_black_crows_local_detection_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "detection_id": str(record.get("detection_id") or f"r189_three_black_crows_local_detection_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_detection_requested": bool(record.get("record_detection_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_context": dict(record.get("target_context") or {}),
            "local_feed": dict(record.get("local_feed") or {}),
            "detector_result": dict(record.get("detector_result") or {}),
            "detections": list(record.get("detections") or []),
            "paper_tags": dict(record.get("paper_tags") or {}),
            "lane_detection_summary": dict(record.get("lane_detection_summary") or {}),
            "origin_feedback": dict(record.get("origin_feedback") or {}),
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


def append_three_black_crows_paper_tag_records(
    tags: Sequence[Mapping[str, Any]],
    *,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = three_black_crows_paper_tag_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    appended: list[dict[str, Any]] = []
    with path.open("a", encoding="utf-8") as handle:
        for tag in tags:
            payload = _sanitize(
                {
                    "event_type": TAG_EVENT_TYPE,
                    "recorded_at_utc": datetime.now(UTC).isoformat(),
                    **dict(tag),
                    "safety": dict(SAFETY),
                }
            )
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            appended.append(payload)
    return appended


def load_three_black_crows_local_detection_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = three_black_crows_local_detection_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_three_black_crows_local_detections(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    detection_status_counts = Counter(
        str((record.get("detector_result") or {}).get("detection_status") or "UNKNOWN") for record in records
    )
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "detection_status_counts": dict(sorted(detection_status_counts.items())),
        "last_detection_id": latest.get("detection_id") if isinstance(latest, Mapping) else None,
        "last_detection_status": (latest.get("detector_result") or {}).get("detection_status")
        if isinstance(latest, Mapping)
        else None,
        "last_tags_created": (latest.get("paper_tags") or {}).get("tags_created") if isinstance(latest, Mapping) else 0,
        "safety": dict(SAFETY),
    }


def three_black_crows_local_detection_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def three_black_crows_paper_tag_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / PAPER_TAG_LEDGER_FILENAME


def format_three_black_crows_local_feed_detection_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _detection_record(
    detection: Mapping[str, Any],
    *,
    lane_key: str,
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    return {
        "detection_id": f"r189_three_black_crows_detection_{uuid4().hex}",
        "signal_origin": SIGNAL_ORIGIN,
        "lane_key": lane_key,
        "symbol": str(symbol or DEFAULT_SYMBOL).upper(),
        "timeframe": str(timeframe or DEFAULT_TIMEFRAME),
        "direction": DEFAULT_DIRECTION,
        "mode": detection.get("mode"),
        "detected_at": detection.get("detected_at"),
        "candle_times": list(detection.get("candle_times") or []),
        "confidence": detection.get("confidence"),
        "paper_only": True,
        "live_authorized": False,
        "why": detection.get("why"),
    }


def _status_for_detection(*, record_detection: bool, confirmation_valid: bool, feed_ready: bool) -> str:
    if record_detection and not confirmation_valid:
        return THREE_BLACK_CROWS_LOCAL_DETECTION_REJECTED
    if not feed_ready:
        return THREE_BLACK_CROWS_LOCAL_DETECTION_BLOCKED
    if record_detection and confirmation_valid:
        return THREE_BLACK_CROWS_LOCAL_DETECTION_RECORDED
    return THREE_BLACK_CROWS_LOCAL_DETECTION_READY


def _detection_status(strict: Sequence[Mapping[str, Any]], loose: Sequence[Mapping[str, Any]]) -> str:
    if strict and loose:
        return STRICT_AND_LOOSE_DETECTIONS_FOUND
    if strict:
        return STRICT_DETECTIONS_FOUND
    if loose:
        return LOOSE_DETECTIONS_FOUND
    return NO_DETECTIONS_FOUND


def _adapter_readiness(*, validation: Mapping[str, Any], feed_ready: bool) -> str:
    if feed_ready:
        return DETECTOR_READY_LOCAL_OHLC_AVAILABLE
    if not bool(validation.get("source_found")):
        return LOCAL_OHLC_MISSING
    if not bool(validation.get("all_normalized_records_valid")):
        return LOCAL_OHLC_INVALID
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def _target_context(symbol: str, timeframe: str) -> dict[str, Any]:
    return {
        "primary_lane": normalize_lane_key(symbol, timeframe, DEFAULT_DIRECTION, "ladder_close_50_618"),
        "symbol": str(symbol or DEFAULT_SYMBOL).upper(),
        "timeframe": str(timeframe or DEFAULT_TIMEFRAME),
        "direction": DEFAULT_DIRECTION,
        "signal_origin": SIGNAL_ORIGIN,
    }


def _latest_candle_time(candles: Sequence[Mapping[str, Any]]) -> str | None:
    if not candles:
        return None
    return max(str(row.get("open_time") or row.get("timestamp") or "") for row in candles) or None


def _display_archive_path(symbol: str, timeframe: str) -> str:
    return f"logs/hammer_radar_forward/candle_archive/{str(symbol or DEFAULT_SYMBOL).upper()}_{timeframe}.ndjson"


def _display_tag_ledger_path() -> str:
    return f"logs/hammer_radar_forward/{PAPER_TAG_LEDGER_FILENAME}"


def _recommended_next_operator_move(detection_status: str) -> str:
    if detection_status in {STRICT_DETECTIONS_FOUND, LOOSE_DETECTIONS_FOUND, STRICT_AND_LOOSE_DETECTIONS_FOUND}:
        return "RUN_R190_SIGNAL_ORIGIN_FEEDBACK_SYNC"
    return "KEEP_8M_SHORT_WATCHER_RUNNING"


def _recommended_next_engineering_move(detection_status: str) -> str:
    if detection_status in {STRICT_DETECTIONS_FOUND, LOOSE_DETECTIONS_FOUND, STRICT_AND_LOOSE_DETECTIONS_FOUND}:
        return "Build R190 feedback sync to review detector evidence into registry/Keter/lane matrix without promotion."
    if detection_status == NO_DETECTIONS_FOUND:
        return "Keep local-feed detection available and rerun after fresh BTCUSDT 8m candles arrive."
    return "Review the R188 local candle feed before any signal-origin feedback sync."


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


def _empty_detector_result(detection_status: str) -> dict[str, Any]:
    return {
        "strict_detections_found": 0,
        "loose_detections_found": 0,
        "latest_detection_at": None,
        "detection_status": detection_status,
        "paper_only": True,
        "live_authorized": False,
    }


def _normalize_mode(mode: str) -> str:
    value = str(mode or "both").strip()
    if value in {"strict", "loose_preview", "both"}:
        return value
    return "both"


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
