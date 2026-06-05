"""R200 pattern-family feedback sync.

This module syncs recorded R197 pattern-family detector evidence into
registry/Keter/lane-matrix review recommendations. It is audit-only: no
Binance/network calls, no payload creation, no config writes, no signal-origin
or lane promotion, and no live authorization.
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
from src.app.hammer_radar.operator.pattern_detector_family_expansion import (
    DEFAULT_PATTERNS,
    DEFAULT_SYMBOL,
    DETECTOR_PATTERNS,
    LEDGER_FILENAME as PATTERN_FAMILY_EXPANSION_LEDGER_FILENAME,
    REGISTRY_ONLY_PATTERNS,
    load_pattern_family_expansion_records,
)
from src.app.hammer_radar.operator.wma_ma_anchor_layer_preview import (
    LEDGER_FILENAME as WMA_MA_ANCHOR_LAYER_PREVIEW_LEDGER_FILENAME,
    load_wma_ma_anchor_preview_records,
)

PATTERN_FAMILY_FEEDBACK_SYNC_READY = "PATTERN_FAMILY_FEEDBACK_SYNC_READY"
PATTERN_FAMILY_FEEDBACK_SYNC_REJECTED = "PATTERN_FAMILY_FEEDBACK_SYNC_REJECTED"
PATTERN_FAMILY_FEEDBACK_SYNC_RECORDED = "PATTERN_FAMILY_FEEDBACK_SYNC_RECORDED"
PATTERN_FAMILY_FEEDBACK_SYNC_BLOCKED = "PATTERN_FAMILY_FEEDBACK_SYNC_BLOCKED"
PATTERN_FAMILY_FEEDBACK_SYNC_ERROR = "PATTERN_FAMILY_FEEDBACK_SYNC_ERROR"

PATTERN_DETECTOR_EVIDENCE_AVAILABLE_REVIEW_REQUIRED = "PATTERN_DETECTOR_EVIDENCE_AVAILABLE_REVIEW_REQUIRED"
PATTERN_DETECTIONS_FOUND = "PATTERN_DETECTIONS_FOUND"
PATTERN_DETECTIONS_MISSING = "PATTERN_DETECTIONS_MISSING"
PATTERN_REGISTRY_ONLY_GAPS_REMAIN = "PATTERN_REGISTRY_ONLY_GAPS_REMAIN"
READY_FOR_PATTERN_OUTCOME_MAPPING = "READY_FOR_PATTERN_OUTCOME_MAPPING"
READY_FOR_KETER_AND_MATRIX_REVIEW = "READY_FOR_KETER_AND_MATRIX_REVIEW"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "PATTERN_FAMILY_FEEDBACK_SYNC"
LEDGER_FILENAME = "pattern_family_feedback_sync.ndjson"
CONFIRM_PATTERN_FAMILY_FEEDBACK_SYNC_RECORDING_PHRASE = (
    "I CONFIRM PATTERN FAMILY FEEDBACK SYNC RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DETECTOR_AVAILABLE_AFTER_REVIEW = "DETECTOR_AVAILABLE_AFTER_REVIEW"
REGISTRY_ONLY_UNTIL_RETEST_STRUCTURE = "REGISTRY_ONLY_UNTIL_RETEST_STRUCTURE"
TARGET_SIGNAL_ORIGINS = tuple(DEFAULT_PATTERNS)

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
    "anchor_live_authorized": False,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{PATTERN_FAMILY_EXPANSION_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/pattern_family_paper_tags.ndjson",
    "logs/hammer_radar_forward/signal_origin_registry.ndjson",
    "logs/hammer_radar_forward/keter_signal_origin_scoring.ndjson",
    "logs/hammer_radar_forward/signal_origin_lane_matrix.ndjson",
    f"logs/hammer_radar_forward/{WMA_MA_ANCHOR_LAYER_PREVIEW_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_pattern_family_feedback_sync(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    record_feedback: bool = False,
    confirm_pattern_family_feedback_sync: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    confirmation_valid = confirm_pattern_family_feedback_sync == CONFIRM_PATTERN_FAMILY_FEEDBACK_SYNC_RECORDING_PHRASE
    try:
        latest_expansion = load_latest_pattern_family_expansion(log_dir=resolved_log_dir)
        latest_anchor = _load_latest_anchor_preview(log_dir=resolved_log_dir)
        detection_summary = summarize_pattern_family_detections(latest_expansion)
        registry_feedback = build_pattern_family_registry_feedback(detection_summary)
        keter_feedback = build_pattern_family_keter_feedback(detection_summary)
        lane_matrix_feedback = build_pattern_family_lane_matrix_feedback(detection_summary)
        outcome_mapping = build_pattern_family_outcome_mapping_recommendations(detection_summary)
        anchor_overlay = build_pattern_family_anchor_overlay_recommendations(
            detection_summary,
            latest_anchor_preview=latest_anchor,
        )
        remaining_gaps = _remaining_gaps(detection_summary)
        feedback_status = classify_pattern_family_feedback_status(detection_summary)
        blockers = _blockers_for_feedback(feedback_status)
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
            "target_scope": {
                "symbol": normalized_symbol,
                "signal_origins": list(TARGET_SIGNAL_ORIGINS),
                "paper_only": True,
                "live_authorized": False,
            },
            "pattern_family_detection_summary": detection_summary,
            "registry_feedback": registry_feedback,
            "keter_feedback": keter_feedback,
            "lane_matrix_feedback": lane_matrix_feedback,
            "outcome_mapping_recommendations": outcome_mapping,
            "anchor_overlay_recommendations": anchor_overlay,
            "remaining_gaps": remaining_gaps,
            "feedback_status": feedback_status,
            "feedback_statuses": _feedback_statuses(detection_summary, feedback_status),
            "blockers": blockers,
            "recommended_next_operator_move": _recommended_next_operator_move(feedback_status),
            "recommended_next_engineering_move": _recommended_next_engineering_move(feedback_status),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "r197_expansion_source": latest_expansion.get("expansion_source"),
            "r199_anchor_source": latest_anchor.get("anchor_source"),
        }
        if record_feedback and confirmation_valid and not blockers:
            record = append_pattern_family_feedback_sync_record(payload, log_dir=resolved_log_dir)
            payload["status"] = PATTERN_FAMILY_FEEDBACK_SYNC_RECORDED
            payload["feedback_recorded"] = True
            payload["feedback_id"] = record["feedback_id"]
            payload["ledger_path"] = str(pattern_family_feedback_sync_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": PATTERN_FAMILY_FEEDBACK_SYNC_ERROR,
                "generated_at": generated_at.isoformat(),
                "feedback_recorded": False,
                "feedback_id": None,
                "record_feedback_requested": bool(record_feedback),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "symbol": normalized_symbol,
                    "signal_origins": list(TARGET_SIGNAL_ORIGINS),
                    "paper_only": True,
                    "live_authorized": False,
                },
                "pattern_family_detection_summary": summarize_pattern_family_detections({}),
                "registry_feedback": build_pattern_family_registry_feedback({}),
                "keter_feedback": build_pattern_family_keter_feedback({}),
                "lane_matrix_feedback": build_pattern_family_lane_matrix_feedback({}),
                "outcome_mapping_recommendations": [],
                "anchor_overlay_recommendations": [],
                "remaining_gaps": list(_retest_gap_messages()),
                "feedback_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "feedback_statuses": [UNKNOWN_NEEDS_MANUAL_REVIEW],
                "blockers": [UNKNOWN_NEEDS_MANUAL_REVIEW],
                "recommended_next_operator_move": "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R200 feedback sync error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_pattern_family_expansion(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_pattern_family_expansion_records(log_dir=log_dir, limit=100)
    for record in records:
        if isinstance(record.get("detector_results"), Mapping):
            latest = dict(record)
            latest["expansion_source"] = "pattern_detector_family_expansion_ledger"
            return latest
    return {"expansion_source": "missing"}


def summarize_pattern_family_detections(latest_expansion: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    detector_results = latest_expansion.get("detector_results") if isinstance(latest_expansion.get("detector_results"), Mapping) else {}
    summary: dict[str, dict[str, Any]] = {}
    for origin in TARGET_SIGNAL_ORIGINS:
        row = detector_results.get(origin) if isinstance(detector_results.get(origin), Mapping) else {}
        if origin in REGISTRY_ONLY_PATTERNS:
            summary[origin] = {
                "strict_detections_found": 0,
                "loose_detections_found": 0,
                "timeframes_with_detections": [],
                "detector_available": False,
                "registry_only": True,
                "paper_only": True,
                "live_authorized": False,
            }
            continue
        strict = _to_int(row.get("strict_detections_found"))
        loose = _to_int(row.get("loose_detections_found"))
        timeframes = sorted({str(item) for item in row.get("timeframes_with_detections") or [] if str(item)})
        summary[origin] = {
            "strict_detections_found": strict,
            "loose_detections_found": loose,
            "timeframes_with_detections": timeframes,
            "detector_available": strict > 0 or loose > 0,
            "paper_only": True,
            "live_authorized": False,
        }
    return summary


def build_pattern_family_registry_feedback(detection_summary: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    recommendations = {}
    for origin in TARGET_SIGNAL_ORIGINS:
        if origin in REGISTRY_ONLY_PATTERNS:
            recommendations[origin] = REGISTRY_ONLY_UNTIL_RETEST_STRUCTURE
        elif bool((detection_summary.get(origin) or {}).get("detector_available")):
            recommendations[origin] = DETECTOR_AVAILABLE_AFTER_REVIEW
        else:
            recommendations[origin] = "KEEP_REGISTRY_ONLY_UNTIL_DETECTOR_EVIDENCE"
    return {
        "write_registry_now": False,
        "signal_origin_promoted": False,
        "recommended_future_availability": recommendations,
        "requires_review": True,
    }


def build_pattern_family_keter_feedback(detection_summary: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    ready = _ready_detector_origins(detection_summary)
    blocked = _blocked_origins(detection_summary)
    return {
        "rerun_keter_scoring_recommended": bool(ready),
        "write_scoring_now": False,
        "pattern_origins_ready_for_scoring": ready,
        "pattern_origins_blocked": blocked,
    }


def build_pattern_family_lane_matrix_feedback(detection_summary: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    ready = _ready_detector_origins(detection_summary)
    blocked = _blocked_origins(detection_summary)
    return {
        "rerun_lane_matrix_recommended": bool(ready),
        "write_matrix_now": False,
        "origins_ready_for_matrix": ready,
        "origins_blocked_from_matrix": blocked,
    }


def build_pattern_family_outcome_mapping_recommendations(
    detection_summary: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    recommendations = []
    for origin in _ready_detector_origins(detection_summary):
        row = detection_summary.get(origin) or {}
        strict = _to_int(row.get("strict_detections_found"))
        loose = _to_int(row.get("loose_detections_found"))
        total = strict + loose
        priority = "HIGH" if strict >= 50 or total >= 150 else "MEDIUM" if total >= 25 else "LOW"
        recommendations.append(
            {
                "signal_origin": origin,
                "priority": priority,
                "why": f"{origin} has {strict} strict and {loose} loose paper-only detections ready for outcome mapping review.",
                "future_phase": "R202",
            }
        )
    return recommendations


def build_pattern_family_anchor_overlay_recommendations(
    detection_summary: Mapping[str, Mapping[str, Any]],
    *,
    latest_anchor_preview: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    anchor_summary = latest_anchor_preview or {}
    anchor_events = (
        anchor_summary.get("anchor_event_summary")
        if isinstance(anchor_summary.get("anchor_event_summary"), Mapping)
        else {}
    )
    events_by_timeframe = (
        anchor_events.get("events_by_timeframe")
        if isinstance(anchor_events.get("events_by_timeframe"), Mapping)
        else {}
    )
    recommendations = []
    for origin in _ready_detector_origins(detection_summary):
        row = detection_summary.get(origin) or {}
        timeframes = [str(item) for item in row.get("timeframes_with_detections") or []]
        overlap_events = sum(_to_int(events_by_timeframe.get(timeframe)) for timeframe in timeframes)
        priority = "HIGH" if overlap_events >= 10_000 else "MEDIUM" if overlap_events > 0 else "LOW"
        why = (
            f"{origin} detections overlap R199 WMA/MA anchor event timeframes with {overlap_events} anchor events."
            if overlap_events
            else f"{origin} has detector evidence; run R201 to deepen WMA/MA confluence before scoring."
        )
        recommendations.append(
            {
                "signal_origin": origin,
                "anchor_layer": "WMA/MA",
                "priority": priority,
                "why": why,
            }
        )
    return recommendations


def classify_pattern_family_feedback_status(detection_summary: Mapping[str, Mapping[str, Any]]) -> str:
    if not detection_summary:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    ready = _ready_detector_origins(detection_summary)
    if not ready:
        return PATTERN_DETECTIONS_MISSING
    if any(origin in REGISTRY_ONLY_PATTERNS and bool((detection_summary.get(origin) or {}).get("registry_only")) for origin in TARGET_SIGNAL_ORIGINS):
        return READY_FOR_KETER_AND_MATRIX_REVIEW
    return READY_FOR_PATTERN_OUTCOME_MAPPING


def append_pattern_family_feedback_sync_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = pattern_family_feedback_sync_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "feedback_id": str(record.get("feedback_id") or f"r200_pattern_family_feedback_sync_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": PATTERN_FAMILY_FEEDBACK_SYNC_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_feedback_requested": bool(record.get("record_feedback_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "pattern_family_detection_summary": dict(record.get("pattern_family_detection_summary") or {}),
            "registry_feedback": dict(record.get("registry_feedback") or {}),
            "keter_feedback": dict(record.get("keter_feedback") or {}),
            "lane_matrix_feedback": dict(record.get("lane_matrix_feedback") or {}),
            "outcome_mapping_recommendations": list(record.get("outcome_mapping_recommendations") or []),
            "anchor_overlay_recommendations": list(record.get("anchor_overlay_recommendations") or []),
            "remaining_gaps": list(record.get("remaining_gaps") or []),
            "feedback_status": record.get("feedback_status"),
            "feedback_statuses": list(record.get("feedback_statuses") or []),
            "blockers": list(record.get("blockers") or []),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
            "r197_expansion_source": record.get("r197_expansion_source"),
            "r199_anchor_source": record.get("r199_anchor_source"),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_pattern_family_feedback_sync_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return _load_ndjson(pattern_family_feedback_sync_records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def summarize_pattern_family_feedback_sync_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    feedback_counts = Counter(str(record.get("feedback_status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    latest_summary = latest.get("pattern_family_detection_summary") if isinstance(latest, Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "feedback_status_counts": dict(sorted(feedback_counts.items())),
        "last_feedback_id": latest.get("feedback_id") if isinstance(latest, Mapping) else None,
        "last_ready_origins": _ready_detector_origins(latest_summary) if isinstance(latest_summary, Mapping) else [],
        "safety": dict(SAFETY),
    }


def pattern_family_feedback_sync_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_pattern_family_feedback_sync_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _load_latest_anchor_preview(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_wma_ma_anchor_preview_records(log_dir=log_dir, limit=100)
    if records:
        latest = dict(records[0])
        latest["anchor_source"] = "wma_ma_anchor_layer_preview_ledger"
        return latest
    return {"anchor_source": "missing"}


def _ready_detector_origins(detection_summary: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return [
        origin
        for origin in DETECTOR_PATTERNS
        if bool((detection_summary.get(origin) or {}).get("detector_available"))
        and bool((detection_summary.get(origin) or {}).get("paper_only"))
        and not bool((detection_summary.get(origin) or {}).get("live_authorized"))
    ]


def _blocked_origins(detection_summary: Mapping[str, Mapping[str, Any]]) -> list[str]:
    blocked = []
    for origin in TARGET_SIGNAL_ORIGINS:
        row = detection_summary.get(origin) or {}
        if origin in REGISTRY_ONLY_PATTERNS or not bool(row.get("detector_available")):
            blocked.append(origin)
    return blocked


def _remaining_gaps(detection_summary: Mapping[str, Mapping[str, Any]]) -> list[str]:
    gaps = list(_retest_gap_messages())
    for origin in DETECTOR_PATTERNS:
        if not bool((detection_summary.get(origin) or {}).get("detector_available")):
            gaps.append(f"{origin} requires recorded detector evidence")
    return gaps


def _retest_gap_messages() -> tuple[str, str]:
    return (
        "breakdown_retest requires swing/retest structure",
        "breakout_retest requires swing/retest structure",
    )


def _feedback_statuses(detection_summary: Mapping[str, Mapping[str, Any]], feedback_status: str) -> list[str]:
    statuses = [feedback_status]
    ready = _ready_detector_origins(detection_summary)
    if ready:
        statuses.extend(
            [
                PATTERN_DETECTOR_EVIDENCE_AVAILABLE_REVIEW_REQUIRED,
                PATTERN_DETECTIONS_FOUND,
                READY_FOR_PATTERN_OUTCOME_MAPPING,
            ]
        )
    else:
        statuses.append(PATTERN_DETECTIONS_MISSING)
    if any(origin in REGISTRY_ONLY_PATTERNS for origin in _blocked_origins(detection_summary)):
        statuses.append(PATTERN_REGISTRY_ONLY_GAPS_REMAIN)
    if ready:
        statuses.append(READY_FOR_KETER_AND_MATRIX_REVIEW)
    return list(dict.fromkeys(statuses))


def _blockers_for_feedback(feedback_status: str) -> list[str]:
    if feedback_status in {PATTERN_DETECTIONS_MISSING, UNKNOWN_NEEDS_MANUAL_REVIEW}:
        return [feedback_status]
    return []


def _status_for_sync(*, record_feedback: bool, confirmation_valid: bool, feedback_status: str) -> str:
    if record_feedback and not confirmation_valid:
        return PATTERN_FAMILY_FEEDBACK_SYNC_REJECTED
    if feedback_status in {PATTERN_DETECTIONS_MISSING, UNKNOWN_NEEDS_MANUAL_REVIEW}:
        return PATTERN_FAMILY_FEEDBACK_SYNC_BLOCKED
    if record_feedback and confirmation_valid:
        return PATTERN_FAMILY_FEEDBACK_SYNC_RECORDED
    return PATTERN_FAMILY_FEEDBACK_SYNC_READY


def _recommended_next_operator_move(feedback_status: str) -> str:
    if feedback_status == READY_FOR_KETER_AND_MATRIX_REVIEW:
        return "RUN_R202_PATTERN_OUTCOME_MAPPING_FAMILY"
    if feedback_status == READY_FOR_PATTERN_OUTCOME_MAPPING:
        return "RUN_R201_ANCHOR_OUTCOME_DEEPENING"
    return "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"


def _recommended_next_engineering_move(feedback_status: str) -> str:
    if feedback_status in {READY_FOR_KETER_AND_MATRIX_REVIEW, READY_FOR_PATTERN_OUTCOME_MAPPING}:
        return "Build R202 pattern-family outcome mapping from R197 detector evidence; keep it paper-only with no config writes."
    if feedback_status == PATTERN_DETECTIONS_MISSING:
        return "Rerun and record R197 pattern detector family expansion after local candle archives have detector evidence."
    return "Review R200 feedback sync inputs manually before recording."


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


def _to_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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
