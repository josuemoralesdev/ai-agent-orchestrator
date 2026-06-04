"""R190 signal-origin feedback sync after Three Black Crows evidence.

This module reads local R189 detector/tag ledgers and writes only an
append-only feedback sync record after exact confirmation. It never calls
Binance or any network, creates payloads, mutates env/config, changes lane
modes, promotes origins/lanes, or authorizes live execution.
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
from src.app.hammer_radar.operator.signal_origin_registry import REGISTRY_ONLY
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

SIGNAL_ORIGIN_FEEDBACK_SYNC_READY = "SIGNAL_ORIGIN_FEEDBACK_SYNC_READY"
SIGNAL_ORIGIN_FEEDBACK_SYNC_REJECTED = "SIGNAL_ORIGIN_FEEDBACK_SYNC_REJECTED"
SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDED = "SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDED"
SIGNAL_ORIGIN_FEEDBACK_SYNC_BLOCKED = "SIGNAL_ORIGIN_FEEDBACK_SYNC_BLOCKED"
SIGNAL_ORIGIN_FEEDBACK_SYNC_ERROR = "SIGNAL_ORIGIN_FEEDBACK_SYNC_ERROR"

DETECTOR_EVIDENCE_AVAILABLE_REVIEW_REQUIRED = "DETECTOR_EVIDENCE_AVAILABLE_REVIEW_REQUIRED"
NO_DETECTION_RECORDS_FOUND = "NO_DETECTION_RECORDS_FOUND"
PAPER_TAGS_FOUND = "PAPER_TAGS_FOUND"
PAPER_TAGS_MISSING = "PAPER_TAGS_MISSING"
READY_TO_RERUN_KETER_AND_MATRIX = "READY_TO_RERUN_KETER_AND_MATRIX"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "SIGNAL_ORIGIN_FEEDBACK_SYNC"
LEDGER_FILENAME = "signal_origin_feedback_sync.ndjson"
DETECTOR_AVAILABLE_AFTER_REVIEW = "DETECTOR_AVAILABLE_AFTER_REVIEW"
DEFAULT_ENTRY_MODE = "ladder_close_50_618"
DEFAULT_TARGET_LANE_KEY = "BTCUSDT|8m|short|ladder_close_50_618"
CONFIRM_SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDING_PHRASE = (
    "I CONFIRM SIGNAL ORIGIN FEEDBACK SYNC RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "logs/hammer_radar_forward/signal_origin_registry.ndjson",
    "logs/hammer_radar_forward/keter_signal_origin_scoring.ndjson",
    "logs/hammer_radar_forward/signal_origin_lane_matrix.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_signal_origin_feedback_sync_after_three_black_crows(
    *,
    log_dir: str | Path | None = None,
    signal_origin: str = SIGNAL_ORIGIN,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    record_feedback: bool = False,
    confirm_signal_origin_feedback_sync: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_origin = _normalize_signal_origin(signal_origin)
    normalized_lane = _normalize_lane_key(lane_key)
    confirmation_valid = confirm_signal_origin_feedback_sync == CONFIRM_SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDING_PHRASE
    try:
        detection_records = load_three_black_crows_detection_records(log_dir=resolved_log_dir, limit=0)
        paper_tags = load_three_black_crows_paper_tags(log_dir=resolved_log_dir, limit=0)
        summary = build_three_black_crows_feedback_summary(
            detection_records=detection_records,
            paper_tags=paper_tags,
            signal_origin=normalized_origin,
            lane_key=normalized_lane,
        )
        feedback_status = classify_signal_origin_feedback_status(summary)
        blockers = _blockers_for_feedback(summary=summary, feedback_status=feedback_status)
        registry_feedback = build_registry_feedback_recommendation(summary)
        keter_feedback = build_keter_feedback_recommendation(summary)
        lane_matrix_feedback = build_lane_matrix_feedback_recommendation(summary, lane_key=normalized_lane)
        status = _status_for_sync(
            record_feedback=record_feedback,
            confirmation_valid=confirmation_valid,
            feedback_status=feedback_status,
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "feedback_recorded": False,
            "feedback_id": None,
            "record_feedback_requested": bool(record_feedback),
            "confirmation_valid": bool(confirmation_valid),
            "target_context": _target_context(normalized_origin, normalized_lane),
            "three_black_crows_feedback_summary": summary,
            "registry_feedback": registry_feedback,
            "keter_feedback": keter_feedback,
            "lane_matrix_feedback": lane_matrix_feedback,
            "feedback_status": feedback_status,
            "feedback_statuses": _feedback_statuses(summary, feedback_status),
            "blockers": blockers,
            "recommended_next_operator_move": _recommended_next_operator_move(summary),
            "recommended_next_engineering_move": _recommended_next_engineering_move(summary, feedback_status),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_feedback and confirmation_valid and not blockers:
            record = append_signal_origin_feedback_sync_record(payload, log_dir=resolved_log_dir)
            payload["status"] = SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDED
            payload["feedback_recorded"] = True
            payload["feedback_id"] = record["feedback_id"]
            payload["ledger_path"] = str(signal_origin_feedback_sync_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": SIGNAL_ORIGIN_FEEDBACK_SYNC_ERROR,
                "generated_at": generated_at.isoformat(),
                "feedback_recorded": False,
                "feedback_id": None,
                "record_feedback_requested": bool(record_feedback),
                "confirmation_valid": bool(confirmation_valid),
                "target_context": _target_context(normalized_origin, normalized_lane),
                "three_black_crows_feedback_summary": _empty_feedback_summary(normalized_origin, normalized_lane),
                "registry_feedback": build_registry_feedback_recommendation({}),
                "keter_feedback": build_keter_feedback_recommendation({}),
                "lane_matrix_feedback": build_lane_matrix_feedback_recommendation({}, lane_key=normalized_lane),
                "feedback_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "feedback_statuses": [UNKNOWN_NEEDS_MANUAL_REVIEW],
                "blockers": [UNKNOWN_NEEDS_MANUAL_REVIEW],
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R190 feedback sync error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_three_black_crows_detection_records(
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


def build_three_black_crows_feedback_summary(
    *,
    detection_records: Sequence[Mapping[str, Any]],
    paper_tags: Sequence[Mapping[str, Any]],
    signal_origin: str = SIGNAL_ORIGIN,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
) -> dict[str, Any]:
    normalized_origin = _normalize_signal_origin(signal_origin)
    normalized_lane = _normalize_lane_key(lane_key)
    matching_records = [
        record for record in detection_records if isinstance(record, Mapping) and _record_targets(record, normalized_origin, normalized_lane)
    ]
    latest_record = _latest_source_detection_record(matching_records)
    detections = _matching_detection_entries([latest_record] if latest_record else [], normalized_origin, normalized_lane)
    detection_ids = {str(row.get("detection_id") or "") for row in detections if row.get("detection_id")}
    tags = _matching_paper_tags(paper_tags, normalized_origin, normalized_lane, detection_ids=detection_ids)
    strict_count = sum(1 for row in detections if str(row.get("mode") or "") == "strict")
    loose_count = sum(1 for row in detections if str(row.get("mode") or "") == "loose_preview")
    latest_detection_at = max((str(row.get("detected_at") or "") for row in detections), default=None)
    latest_tag_at = max((str(row.get("detected_at") or row.get("recorded_at_utc") or "") for row in tags), default=None)
    return {
        "detection_records_found": len(detections),
        "source_detection_records_found": len(matching_records),
        "source_detection_record_id": latest_record.get("detection_id") if latest_record else None,
        "paper_tags_found": len(tags),
        "strict_detections_found": strict_count,
        "loose_detections_found": loose_count,
        "latest_detection_at": latest_detection_at,
        "latest_tag_at": latest_tag_at,
        "local_detector_available": bool(detections),
        "paper_only": True,
        "live_authorized": False,
        "signal_origin_promoted": False,
        "lane_promoted": False,
    }


def build_registry_feedback_recommendation(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "previous_availability": REGISTRY_ONLY,
        "recommended_future_availability": DETECTOR_AVAILABLE_AFTER_REVIEW,
        "new_evidence": "local detector evidence exists" if summary.get("local_detector_available") else "no local detector evidence found",
        "write_registry_now": False,
        "requires_review": True,
        "signal_origin_promoted": False,
    }


def build_keter_feedback_recommendation(summary: Mapping[str, Any]) -> dict[str, Any]:
    has_evidence = bool(summary.get("local_detector_available"))
    return {
        "rerun_keter_scoring_recommended": has_evidence,
        "expected_effect": (
            "three_black_crows should move from detector priority only toward paper-tracking candidate after review"
            if has_evidence
            else "three_black_crows should stay detector-priority only until local evidence exists"
        ),
        "write_scoring_now": False,
    }


def build_lane_matrix_feedback_recommendation(
    summary: Mapping[str, Any],
    *,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
) -> dict[str, Any]:
    normalized_lane = _normalize_lane_key(lane_key)
    has_evidence = bool(summary.get("local_detector_available"))
    return {
        "rerun_lane_matrix_recommended": has_evidence,
        "target_pair": f"{normalized_lane} + {SIGNAL_ORIGIN}",
        "expected_effect": (
            "pair may become paper-tracking candidate after Keter review, still not live"
            if has_evidence
            else "pair remains detector-priority only until local detector evidence exists"
        ),
        "write_matrix_now": False,
    }


def classify_signal_origin_feedback_status(summary: Mapping[str, Any]) -> str:
    if not summary:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if int(summary.get("detection_records_found") or 0) <= 0:
        return NO_DETECTION_RECORDS_FOUND
    if int(summary.get("paper_tags_found") or 0) <= 0:
        return PAPER_TAGS_MISSING
    return READY_TO_RERUN_KETER_AND_MATRIX


def append_signal_origin_feedback_sync_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = signal_origin_feedback_sync_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "feedback_id": str(record.get("feedback_id") or f"r190_signal_origin_feedback_sync_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_feedback_requested": bool(record.get("record_feedback_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_context": dict(record.get("target_context") or {}),
            "three_black_crows_feedback_summary": dict(record.get("three_black_crows_feedback_summary") or {}),
            "registry_feedback": dict(record.get("registry_feedback") or {}),
            "keter_feedback": dict(record.get("keter_feedback") or {}),
            "lane_matrix_feedback": dict(record.get("lane_matrix_feedback") or {}),
            "feedback_status": record.get("feedback_status"),
            "feedback_statuses": list(record.get("feedback_statuses") or []),
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


def load_signal_origin_feedback_sync_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return _load_ndjson(signal_origin_feedback_sync_records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def summarize_signal_origin_feedback_sync_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    feedback_counts = Counter(str(record.get("feedback_status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    latest_summary = latest.get("three_black_crows_feedback_summary") if isinstance(latest, Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "feedback_status_counts": dict(sorted(feedback_counts.items())),
        "last_feedback_id": latest.get("feedback_id") if isinstance(latest, Mapping) else None,
        "last_detection_records_found": (latest_summary or {}).get("detection_records_found")
        if isinstance(latest_summary, Mapping)
        else 0,
        "last_paper_tags_found": (latest_summary or {}).get("paper_tags_found") if isinstance(latest_summary, Mapping) else 0,
        "safety": dict(SAFETY),
    }


def signal_origin_feedback_sync_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_signal_origin_feedback_sync_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _target_context(signal_origin: str, lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction = _lane_parts(lane_key)
    return {
        "signal_origin": signal_origin,
        "primary_lane": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
    }


def _empty_feedback_summary(signal_origin: str, lane_key: str) -> dict[str, Any]:
    _ = (signal_origin, lane_key)
    return {
        "detection_records_found": 0,
        "paper_tags_found": 0,
        "strict_detections_found": 0,
        "loose_detections_found": 0,
        "latest_detection_at": None,
        "latest_tag_at": None,
        "local_detector_available": False,
        "paper_only": True,
        "live_authorized": False,
        "signal_origin_promoted": False,
        "lane_promoted": False,
    }


def _matching_detection_entries(
    records: Sequence[Mapping[str, Any]],
    signal_origin: str,
    lane_key: str,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for record in records:
        for detection in record.get("detections") or []:
            if not isinstance(detection, Mapping):
                continue
            if _row_targets(detection, signal_origin, lane_key):
                matches.append(dict(detection))
    return matches


def _matching_paper_tags(
    records: Sequence[Mapping[str, Any]],
    signal_origin: str,
    lane_key: str,
    *,
    detection_ids: set[str],
) -> list[dict[str, Any]]:
    rows = [dict(record) for record in records if _row_targets(record, signal_origin, lane_key)]
    if not detection_ids:
        return rows
    return [row for row in rows if str(row.get("detection_id") or "") in detection_ids]


def _latest_source_detection_record(records: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    return dict(
        max(
            records,
            key=lambda record: str(record.get("recorded_at_utc") or record.get("generated_at") or ""),
        )
    )


def _record_targets(record: Mapping[str, Any], signal_origin: str, lane_key: str) -> bool:
    target = record.get("target_context") if isinstance(record.get("target_context"), Mapping) else {}
    if _row_targets(target, signal_origin, lane_key):
        return True
    return any(_row_targets(row, signal_origin, lane_key) for row in record.get("detections") or [] if isinstance(row, Mapping))


def _row_targets(row: Mapping[str, Any], signal_origin: str, lane_key: str) -> bool:
    return str(row.get("signal_origin") or "") == signal_origin and _normalize_lane_key(str(row.get("lane_key") or row.get("primary_lane") or lane_key)) == lane_key


def _feedback_statuses(summary: Mapping[str, Any], feedback_status: str) -> list[str]:
    statuses = [feedback_status]
    if int(summary.get("detection_records_found") or 0) > 0:
        statuses.append(DETECTOR_EVIDENCE_AVAILABLE_REVIEW_REQUIRED)
    if int(summary.get("paper_tags_found") or 0) > 0:
        statuses.append(PAPER_TAGS_FOUND)
    elif int(summary.get("detection_records_found") or 0) > 0:
        statuses.append(PAPER_TAGS_MISSING)
    return list(dict.fromkeys(statuses))


def _blockers_for_feedback(*, summary: Mapping[str, Any], feedback_status: str) -> list[str]:
    if feedback_status == NO_DETECTION_RECORDS_FOUND:
        return [NO_DETECTION_RECORDS_FOUND]
    if feedback_status == PAPER_TAGS_MISSING:
        return [PAPER_TAGS_MISSING]
    if feedback_status == UNKNOWN_NEEDS_MANUAL_REVIEW:
        return [UNKNOWN_NEEDS_MANUAL_REVIEW]
    if not bool(summary.get("paper_only")) or bool(summary.get("live_authorized")):
        return [UNKNOWN_NEEDS_MANUAL_REVIEW]
    return []


def _status_for_sync(*, record_feedback: bool, confirmation_valid: bool, feedback_status: str) -> str:
    if record_feedback and not confirmation_valid:
        return SIGNAL_ORIGIN_FEEDBACK_SYNC_REJECTED
    if feedback_status in {NO_DETECTION_RECORDS_FOUND, PAPER_TAGS_MISSING, UNKNOWN_NEEDS_MANUAL_REVIEW}:
        return SIGNAL_ORIGIN_FEEDBACK_SYNC_BLOCKED
    if record_feedback and confirmation_valid:
        return SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDED
    return SIGNAL_ORIGIN_FEEDBACK_SYNC_READY


def _recommended_next_operator_move(summary: Mapping[str, Any]) -> str:
    if int(summary.get("detection_records_found") or 0) > 0 and int(summary.get("paper_tags_found") or 0) > 0:
        return "RUN_R191_KETER_RESCORING_AFTER_THREE_BLACK_CROWS"
    if int(summary.get("detection_records_found") or 0) > 0:
        return "KEEP_MULTI_LANE_HARVESTER_RUNNING"
    return "KEEP_8M_SHORT_WATCHER_RUNNING"


def _recommended_next_engineering_move(summary: Mapping[str, Any], feedback_status: str) -> str:
    if feedback_status == READY_TO_RERUN_KETER_AND_MATRIX:
        return (
            "Build R191 Keter rescoring after Three Black Crows evidence; keep it paper-only, no config writes, "
            "no Binance/network calls, and no live promotion."
        )
    if feedback_status == PAPER_TAGS_MISSING:
        return "Restore or rerun R189 paper-tag recording before syncing feedback into Keter/matrix review."
    if feedback_status == NO_DETECTION_RECORDS_FOUND:
        return "Run R189 local detection recording after fresh BTCUSDT 8m local candles exist."
    if not summary:
        return "Review R190 inputs manually before recording any feedback."
    return "Review R190 feedback sync inputs manually."


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


def _load_ndjson(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if limit <= 0:
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def _normalize_signal_origin(value: object) -> str:
    normalized = str(value or SIGNAL_ORIGIN).strip().lower()
    return normalized or SIGNAL_ORIGIN


def _normalize_lane_key(value: object) -> str:
    text = str(value or DEFAULT_TARGET_LANE_KEY).strip()
    parts = text.split("|")
    if len(parts) == 4:
        return normalize_lane_key(parts[0], parts[1], parts[2], parts[3])
    return DEFAULT_TARGET_LANE_KEY


def _lane_parts(lane_key: str) -> tuple[str, str, str]:
    parts = lane_key.split("|")
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    return DEFAULT_SYMBOL, DEFAULT_TIMEFRAME, DEFAULT_DIRECTION


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
