"""R186 Three Black Crows feed integration and paper tagging.

This module wires the R185 detector to local candle/OHLC ledgers only. Signal
logs can provide candidate context, but they are never converted into fake OHLC
or valid Three Black Crows detections.
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
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY
from src.app.hammer_radar.operator.three_black_crows_detector import (
    DEFAULT_DIRECTION,
    DEFAULT_LATEST_CANDLES,
    DEFAULT_SYMBOL,
    DEFAULT_TIMEFRAME,
    DETECTIONS_FOUND,
    INSUFFICIENT_CANDLES,
    MAX_LATEST_CANDLES,
    MISSING_OHLC_FEED,
    NO_DETECTIONS_FOUND,
    SIGNAL_ORIGIN,
    UNKNOWN_NEEDS_MANUAL_REVIEW,
    classify_three_black_crows_detector_status,
    detect_three_black_crows_sequences,
    normalize_candle_records,
)

THREE_BLACK_CROWS_FEED_INTEGRATION_READY = "THREE_BLACK_CROWS_FEED_INTEGRATION_READY"
THREE_BLACK_CROWS_FEED_INTEGRATION_REJECTED = "THREE_BLACK_CROWS_FEED_INTEGRATION_REJECTED"
THREE_BLACK_CROWS_FEED_INTEGRATION_RECORDED = "THREE_BLACK_CROWS_FEED_INTEGRATION_RECORDED"
THREE_BLACK_CROWS_FEED_INTEGRATION_BLOCKED = "THREE_BLACK_CROWS_FEED_INTEGRATION_BLOCKED"
THREE_BLACK_CROWS_FEED_INTEGRATION_ERROR = "THREE_BLACK_CROWS_FEED_INTEGRATION_ERROR"

LOCAL_OHLC_FEED_FOUND = "LOCAL_OHLC_FEED_FOUND"
LOCAL_OHLC_FEED_MISSING = "LOCAL_OHLC_FEED_MISSING"
SYNTHETIC_SIGNAL_FEED_AVAILABLE = "SYNTHETIC_SIGNAL_FEED_AVAILABLE"
INSUFFICIENT_CANDLE_DATA = "INSUFFICIENT_CANDLE_DATA"
DETECTIONS_TAGGED = "DETECTIONS_TAGGED"
NO_DETECTIONS_FOUND_STATUS = "NO_DETECTIONS_FOUND"
UNKNOWN_FEED_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "THREE_BLACK_CROWS_FEED_INTEGRATION"
TAG_EVENT_TYPE = "THREE_BLACK_CROWS_PAPER_TAG"
LEDGER_FILENAME = "three_black_crows_feed_integration.ndjson"
PAPER_TAG_LEDGER_FILENAME = "three_black_crows_paper_tags.ndjson"
CONFIRM_THREE_BLACK_CROWS_FEED_INTEGRATION_RECORDING_PHRASE = (
    "I CONFIRM THREE BLACK CROWS FEED INTEGRATION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

SYNTHETIC_CONTEXT_FILENAMES = (
    "signals.ndjson",
    "multi_symbol_paper_scans.ndjson",
    "multi_lane_paper_harvester.ndjson",
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
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
    "logs/hammer_radar_forward/candles.ndjson",
    "logs/hammer_radar_forward/ohlc.ndjson",
    "logs/hammer_radar_forward/klines.ndjson",
    "logs/hammer_radar_forward/*candles*.ndjson",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "logs/hammer_radar_forward/multi_lane_paper_harvester.ndjson",
    "operator.three_black_crows_detector.detect_three_black_crows_sequences",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{PAPER_TAG_LEDGER_FILENAME}",
]


def build_three_black_crows_feed_integration(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    mode: str = "strict",
    latest_candles: int = DEFAULT_LATEST_CANDLES,
    record_integration: bool = False,
    confirm_three_black_crows_feed_integration: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    normalized_timeframe = str(timeframe or DEFAULT_TIMEFRAME).strip()
    normalized_mode = _normalize_mode(mode)
    confirmation_valid = (
        confirm_three_black_crows_feed_integration == CONFIRM_THREE_BLACK_CROWS_FEED_INTEGRATION_RECORDING_PHRASE
    )
    try:
        discovery = discover_local_candle_feeds(
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
        )
        raw_records = load_local_candle_records(
            discovery["source_files_used"],
            latest_candles=latest_candles,
        )
        candles = [
            candle
            for candle in (
                normalize_local_candle_record(record, symbol=normalized_symbol, timeframe=normalized_timeframe)
                for record in raw_records
            )
            if candle is not None
        ]
        synthetic_context = build_synthetic_candle_candidates_from_signal_logs_if_safe(
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            latest_records=latest_candles,
        )
        detector_result = run_three_black_crows_detector_on_feed(
            candles,
            ohlc_feed_found=bool(discovery["local_ohlc_feed_found"]),
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            mode=normalized_mode,
        )
        paper_tags = tag_three_black_crows_paper_candidates(
            detector_result["detections"],
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
        )
        feed_status = _feed_status(
            local_ohlc_feed_found=bool(discovery["local_ohlc_feed_found"]),
            candles_count=len(candles),
            detections_count=detector_result["detections_found"],
            synthetic_context_count=len(synthetic_context),
        )
        blockers = _blockers(
            feed_status=feed_status,
            detector_status=str(detector_result["detector_status"]),
            synthetic_context_count=len(synthetic_context),
        )
        status = _integration_status(feed_status)
        if record_integration and not confirmation_valid:
            status = THREE_BLACK_CROWS_FEED_INTEGRATION_REJECTED
        elif record_integration and confirmation_valid:
            status = THREE_BLACK_CROWS_FEED_INTEGRATION_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "integration_recorded": False,
            "integration_id": None,
            "record_integration_requested": bool(record_integration),
            "confirmation_valid": bool(confirmation_valid),
            "target_context": _target_context(normalized_symbol, normalized_timeframe),
            "feed_discovery": {
                "local_ohlc_feed_found": bool(discovery["local_ohlc_feed_found"]),
                "source_files_checked": list(discovery["source_files_checked"]),
                "source_files_used": list(discovery["source_files_used"]),
                "records_loaded": len(raw_records),
                "normalized_candles": len(candles),
                "synthetic_signal_context_records": len(synthetic_context),
            },
            "detector_result": {
                "detector_status": detector_result["detector_status"],
                "detections_found": detector_result["detections_found"],
                "latest_detection_at": detector_result["latest_detection_at"],
                "mode": normalized_mode,
                "paper_only": True,
                "live_authorized": False,
            },
            "paper_tags": build_three_black_crows_paper_tag_summary(paper_tags),
            "feed_status": feed_status,
            "blockers": blockers,
            "synthetic_signal_context": synthetic_context,
            "recommended_next_operator_move": _recommended_next_operator_move(feed_status),
            "recommended_next_engineering_move": _recommended_next_engineering_move(feed_status),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_integration and confirmation_valid:
            record = append_three_black_crows_feed_integration_record(payload, log_dir=resolved_log_dir)
            payload["integration_recorded"] = True
            payload["integration_id"] = record["integration_id"]
            payload["ledger_path"] = str(three_black_crows_feed_integration_records_path(resolved_log_dir))
            if paper_tags:
                appended_tags = append_three_black_crows_paper_tag_records(paper_tags, log_dir=resolved_log_dir)
                payload["paper_tags"]["paper_tag_ledger_path"] = str(three_black_crows_paper_tags_records_path(resolved_log_dir))
                payload["paper_tags"]["tags_recorded"] = len(appended_tags)
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": THREE_BLACK_CROWS_FEED_INTEGRATION_ERROR,
                "generated_at": generated_at.isoformat(),
                "integration_recorded": False,
                "integration_id": None,
                "record_integration_requested": bool(record_integration),
                "confirmation_valid": bool(confirmation_valid),
                "target_context": _target_context(normalized_symbol, normalized_timeframe),
                "feed_discovery": {
                    "local_ohlc_feed_found": False,
                    "source_files_checked": [],
                    "source_files_used": [],
                    "records_loaded": 0,
                },
                "detector_result": {
                    "detector_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                    "detections_found": 0,
                    "latest_detection_at": None,
                    "mode": normalized_mode,
                    "paper_only": True,
                    "live_authorized": False,
                },
                "paper_tags": build_three_black_crows_paper_tag_summary([]),
                "feed_status": UNKNOWN_FEED_NEEDS_MANUAL_REVIEW,
                "blockers": [UNKNOWN_FEED_NEEDS_MANUAL_REVIEW],
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R186 feed integration error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def discover_local_candle_feeds(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    candidates = _candidate_source_files(resolved_log_dir, symbol, timeframe)
    used = [path for path in candidates if path.exists()]
    return {
        "local_ohlc_feed_found": bool(used),
        "source_files_checked": [str(path) for path in candidates],
        "source_files_used": [str(path) for path in used],
    }


def load_local_candle_records(paths: Sequence[str | Path], *, latest_candles: int = DEFAULT_LATEST_CANDLES) -> list[Any]:
    limit = _bounded_int(latest_candles, 3, MAX_LATEST_CANDLES, DEFAULT_LATEST_CANDLES)
    records: list[Any] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.exists():
            records.extend(read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000))
    return records[-limit:]


def normalize_local_candle_record(
    record: Mapping[str, Any] | Sequence[Any],
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> dict[str, Any] | None:
    normalized = normalize_candle_records([record], symbol=symbol, timeframe=timeframe)
    return normalized[0] if normalized else None


def build_synthetic_candle_candidates_from_signal_logs_if_safe(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    latest_records: int = DEFAULT_LATEST_CANDLES,
) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    limit = _bounded_int(latest_records, 1, MAX_LATEST_CANDLES, DEFAULT_LATEST_CANDLES)
    contexts: list[dict[str, Any]] = []
    for filename in SYNTHETIC_CONTEXT_FILENAMES:
        path = resolved_log_dir / filename
        if not path.exists():
            continue
        for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000):
            context = _synthetic_context_from_record(record, source=filename, symbol=symbol, timeframe=timeframe)
            if context is not None:
                contexts.append(context)
    return contexts[-limit:]


def run_three_black_crows_detector_on_feed(
    candles: Sequence[Mapping[str, Any]],
    *,
    ohlc_feed_found: bool,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    mode: str = "strict",
) -> dict[str, Any]:
    normalized_mode = _normalize_mode(mode)
    detections = (
        detect_three_black_crows_sequences(candles, symbol=symbol, timeframe=timeframe, mode=normalized_mode)
        if ohlc_feed_found and len(candles) >= 3
        else []
    )
    detector_status = classify_three_black_crows_detector_status(
        ohlc_feed_found=ohlc_feed_found,
        records_checked=len(candles),
        detections=detections,
    )
    latest_detection_at = max((str(row.get("detected_at") or "") for row in detections), default=None)
    return {
        "detector_status": detector_status,
        "detections_found": len(detections),
        "latest_detection_at": latest_detection_at,
        "detections": list(detections),
        "mode": normalized_mode,
        "paper_only": True,
        "live_authorized": False,
    }


def tag_three_black_crows_paper_candidates(
    detections: Sequence[Mapping[str, Any]],
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> list[dict[str, Any]]:
    lane_key = normalize_lane_key(symbol, timeframe, DEFAULT_DIRECTION, "ladder_close_50_618")
    tags: list[dict[str, Any]] = []
    for detection in detections:
        tags.append(
            {
                "tag_id": f"r186_three_black_crows_tag_{uuid4().hex}",
                "signal_origin": SIGNAL_ORIGIN,
                "lane_key": lane_key,
                "symbol": str(symbol or DEFAULT_SYMBOL).upper(),
                "timeframe": str(timeframe or DEFAULT_TIMEFRAME),
                "direction": DEFAULT_DIRECTION,
                "detected_at": detection.get("detected_at"),
                "mode": detection.get("mode"),
                "confidence": detection.get("confidence"),
                "paper_only": True,
                "live_authorized": False,
                "signal_origin_promoted": False,
                "lane_promoted": False,
            }
        )
    return tags


def build_three_black_crows_paper_tag_summary(tags: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "tags_created": len(tags),
        "tags": [
            {
                "signal_origin": tag.get("signal_origin"),
                "lane_key": tag.get("lane_key"),
                "paper_only": bool(tag.get("paper_only")),
                "live_authorized": bool(tag.get("live_authorized")),
            }
            for tag in tags
        ],
    }


def append_three_black_crows_feed_integration_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = three_black_crows_feed_integration_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "integration_id": str(record.get("integration_id") or f"r186_three_black_crows_feed_integration_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_integration_requested": bool(record.get("record_integration_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_context": dict(record.get("target_context") or {}),
            "feed_discovery": dict(record.get("feed_discovery") or {}),
            "detector_result": dict(record.get("detector_result") or {}),
            "paper_tags": dict(record.get("paper_tags") or {}),
            "feed_status": record.get("feed_status"),
            "blockers": list(record.get("blockers") or []),
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
    path = three_black_crows_paper_tags_records_path(get_log_dir(log_dir, use_env=True))
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


def load_three_black_crows_feed_integration_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = three_black_crows_feed_integration_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_three_black_crows_feed_integrations(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    feed_status_counts = Counter(str(record.get("feed_status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "feed_status_counts": dict(sorted(feed_status_counts.items())),
        "last_integration_id": latest.get("integration_id"),
        "last_feed_status": latest.get("feed_status"),
        "last_tags_created": (latest.get("paper_tags") or {}).get("tags_created") if isinstance(latest, Mapping) else 0,
        "safety": dict(SAFETY),
    }


def three_black_crows_feed_integration_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def three_black_crows_paper_tags_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / PAPER_TAG_LEDGER_FILENAME


def format_three_black_crows_feed_integration_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _candidate_source_files(log_dir: Path, symbol: str, timeframe: str) -> list[Path]:
    lower_symbol = str(symbol or DEFAULT_SYMBOL).lower()
    upper_symbol = str(symbol or DEFAULT_SYMBOL).upper()
    direct = [
        log_dir / "candles.ndjson",
        log_dir / "ohlc.ndjson",
        log_dir / "klines.ndjson",
        log_dir / f"{lower_symbol}_{timeframe}_candles.ndjson",
        log_dir / f"{upper_symbol}_{timeframe}_candles.ndjson",
        log_dir / f"candles_{lower_symbol}_{timeframe}.ndjson",
        log_dir / f"candles_{upper_symbol}_{timeframe}.ndjson",
    ]
    wildcard = sorted(path for path in log_dir.glob("*candles*.ndjson") if path not in set(direct))
    return [*direct, *wildcard]


def _synthetic_context_from_record(
    record: Mapping[str, Any],
    *,
    source: str,
    symbol: str,
    timeframe: str,
) -> dict[str, Any] | None:
    raw_symbol = str(_first_present(record, "symbol", "asset") or symbol).strip().upper()
    raw_timeframe = str(_first_present(record, "timeframe", "interval") or timeframe).strip()
    if raw_symbol != str(symbol).upper() or raw_timeframe != str(timeframe):
        return None
    direction = str(_first_present(record, "direction", "side") or "").strip().lower()
    lane_key = str(_first_present(record, "lane_key", "after_bridge_lane_key") or "")
    if not lane_key and direction:
        lane_key = normalize_lane_key(raw_symbol, raw_timeframe, direction, "ladder_close_50_618")
    return {
        "source": source,
        "candidate_id": str(_first_present(record, "candidate_id", "signal_id", "harvest_id", "scan_id") or ""),
        "symbol": raw_symbol,
        "timeframe": raw_timeframe,
        "direction": direction,
        "lane_key": lane_key,
        "timestamp": str(_first_present(record, "generated_at", "timestamp", "detected_at", "recorded_at_utc") or ""),
        "not_valid_for_three_black_crows_detection": True,
        "reason": "signal log context lacks verified open/high/low/close candle sequence",
    }


def _feed_status(
    *,
    local_ohlc_feed_found: bool,
    candles_count: int,
    detections_count: int,
    synthetic_context_count: int,
) -> str:
    if local_ohlc_feed_found and candles_count < 3:
        return INSUFFICIENT_CANDLE_DATA
    if local_ohlc_feed_found and detections_count > 0:
        return DETECTIONS_TAGGED
    if local_ohlc_feed_found:
        return NO_DETECTIONS_FOUND_STATUS
    if synthetic_context_count > 0:
        return SYNTHETIC_SIGNAL_FEED_AVAILABLE
    return LOCAL_OHLC_FEED_MISSING


def _integration_status(feed_status: str) -> str:
    if feed_status in {LOCAL_OHLC_FEED_MISSING, SYNTHETIC_SIGNAL_FEED_AVAILABLE, INSUFFICIENT_CANDLE_DATA}:
        return THREE_BLACK_CROWS_FEED_INTEGRATION_BLOCKED
    if feed_status == UNKNOWN_FEED_NEEDS_MANUAL_REVIEW:
        return THREE_BLACK_CROWS_FEED_INTEGRATION_BLOCKED
    return THREE_BLACK_CROWS_FEED_INTEGRATION_READY


def _blockers(*, feed_status: str, detector_status: str, synthetic_context_count: int) -> list[str]:
    blockers: list[str] = []
    if feed_status == LOCAL_OHLC_FEED_MISSING:
        blockers.append("missing_local_ohlc_feed")
    if feed_status == SYNTHETIC_SIGNAL_FEED_AVAILABLE:
        blockers.append("synthetic_signal_context_not_valid_for_three_black_crows_detection")
    if feed_status == INSUFFICIENT_CANDLE_DATA or detector_status == INSUFFICIENT_CANDLES:
        blockers.append("insufficient_candle_data")
    if feed_status == NO_DETECTIONS_FOUND_STATUS:
        blockers.append("no_three_black_crows_detection")
    if synthetic_context_count and feed_status != SYNTHETIC_SIGNAL_FEED_AVAILABLE:
        blockers.append("synthetic_signal_context_excluded_from_detection")
    return blockers


def _recommended_next_operator_move(feed_status: str) -> str:
    if feed_status == DETECTIONS_TAGGED:
        return "RUN_R184_AFTER_CROW_TAGS"
    if feed_status in {LOCAL_OHLC_FEED_MISSING, SYNTHETIC_SIGNAL_FEED_AVAILABLE, INSUFFICIENT_CANDLE_DATA}:
        return "RUN_R187_LOCAL_CANDLE_FEED_CAPTURE_PREVIEW"
    return "KEEP_MULTI_LANE_HARVESTER_RUNNING"


def _recommended_next_engineering_move(feed_status: str) -> str:
    if feed_status == DETECTIONS_TAGGED:
        return "Review paper-only Three Black Crows tags in R184/R183 context without promotion."
    if feed_status == SYNTHETIC_SIGNAL_FEED_AVAILABLE:
        return "Build R187 local candle feed capture preview; signal context cannot satisfy OHLC detection."
    if feed_status == LOCAL_OHLC_FEED_MISSING:
        return "Find or create a local OHLC candle feed adapter without Binance calls."
    if feed_status == INSUFFICIENT_CANDLE_DATA:
        return "Collect at least three consecutive local OHLC candles for the target symbol/timeframe."
    return "Keep local OHLC feed running and rerun R186 after fresh candles arrive."


def _target_context(symbol: str, timeframe: str) -> dict[str, Any]:
    return {
        "primary_lane": DEFAULT_TARGET_LANE_KEY,
        "symbol": str(symbol or DEFAULT_SYMBOL).upper(),
        "timeframe": str(timeframe or DEFAULT_TIMEFRAME),
        "direction": DEFAULT_DIRECTION,
        "signal_origin": SIGNAL_ORIGIN,
    }


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


def _normalize_mode(mode: str) -> str:
    return "loose_preview" if str(mode or "").strip() == "loose_preview" else "strict"


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _first_present(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


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
