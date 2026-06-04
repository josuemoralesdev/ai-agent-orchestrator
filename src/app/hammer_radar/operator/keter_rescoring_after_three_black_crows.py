"""R191 Keter rescoring after Three Black Crows detector evidence.

This module composes R190 feedback, R189 detector/tag evidence, and R183 Keter
scoring into a paper-only rescore packet. It never calls Binance/network,
creates payloads, mutates env/config, promotes origins/lanes, or authorizes
live execution.
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
from src.app.hammer_radar.operator.keter_signal_origin_scoring import (
    build_keter_signal_origin_scoring,
    load_keter_signal_origin_scoring_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, normalize_lane_key
from src.app.hammer_radar.operator.signal_origin_feedback_sync import (
    DETECTOR_AVAILABLE_AFTER_REVIEW,
    READY_TO_RERUN_KETER_AND_MATRIX,
    load_signal_origin_feedback_sync_records,
)
from src.app.hammer_radar.operator.signal_origin_registry import (
    DETECTOR_AVAILABLE,
    REGISTRY_ONLY,
)
from src.app.hammer_radar.operator.three_black_crows_detector import (
    DEFAULT_DIRECTION,
    DEFAULT_SYMBOL,
    DEFAULT_TIMEFRAME,
    SIGNAL_ORIGIN,
)
from src.app.hammer_radar.operator.three_black_crows_local_feed_detection import (
    load_three_black_crows_local_detection_records,
)
from src.app.hammer_radar.operator.signal_origin_feedback_sync import (
    load_three_black_crows_paper_tags as load_three_black_crows_feedback_paper_tags,
)

KETER_RESCORING_AFTER_CROWS_READY = "KETER_RESCORING_AFTER_CROWS_READY"
KETER_RESCORING_AFTER_CROWS_REJECTED = "KETER_RESCORING_AFTER_CROWS_REJECTED"
KETER_RESCORING_AFTER_CROWS_RECORDED = "KETER_RESCORING_AFTER_CROWS_RECORDED"
KETER_RESCORING_AFTER_CROWS_BLOCKED = "KETER_RESCORING_AFTER_CROWS_BLOCKED"
KETER_RESCORING_AFTER_CROWS_ERROR = "KETER_RESCORING_AFTER_CROWS_ERROR"

CROWS_READY_FOR_PAPER_TRACKING_REVIEW = "CROWS_READY_FOR_PAPER_TRACKING_REVIEW"
CROWS_NEED_MORE_PAPER_OUTCOMES = "CROWS_NEED_MORE_PAPER_OUTCOMES"
CROWS_NEED_MORE_DETECTION_HISTORY = "CROWS_NEED_MORE_DETECTION_HISTORY"
CROWS_DETECTOR_EVIDENCE_MISSING = "CROWS_DETECTOR_EVIDENCE_MISSING"
CROWS_NOT_LIVE_AUTHORIZED = "CROWS_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "KETER_RESCORING_AFTER_THREE_BLACK_CROWS"
LEDGER_FILENAME = "keter_rescore_after_three_black_crows.ndjson"
DEFAULT_TARGET_LANE_KEY = "BTCUSDT|8m|short|ladder_close_50_618"
REFERENCE_ORIGIN = "hammer_wick_reversal"
CONFIRM_KETER_RESCORING_AFTER_CROWS_RECORDING_PHRASE = (
    "I CONFIRM KETER RESCORING AFTER THREE BLACK CROWS RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "logs/hammer_radar_forward/signal_origin_feedback_sync.ndjson",
    "logs/hammer_radar_forward/three_black_crows_local_detections.ndjson",
    "logs/hammer_radar_forward/three_black_crows_paper_tags.ndjson",
    "logs/hammer_radar_forward/keter_signal_origin_scoring.ndjson",
    "operator.keter_signal_origin_scoring.build_keter_signal_origin_scoring",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_keter_rescoring_after_three_black_crows(
    *,
    log_dir: str | Path | None = None,
    record_rescore: bool = False,
    confirm_keter_rescore_after_crows: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_keter_rescore_after_crows == CONFIRM_KETER_RESCORING_AFTER_CROWS_RECORDING_PHRASE
    try:
        feedback = load_latest_three_black_crows_feedback(log_dir=resolved_log_dir)
        evidence = load_three_black_crows_detection_evidence(log_dir=resolved_log_dir)
        base_scoring = _load_latest_or_preview_keter_scoring(log_dir=resolved_log_dir, now=generated_at)
        input_feedback = _build_input_feedback(feedback=feedback, evidence=evidence)
        previous = _origin_row(base_scoring, SIGNAL_ORIGIN)
        hammer = _origin_row(base_scoring, REFERENCE_ORIGIN)
        rescore = rescore_three_black_crows_origin(
            input_feedback=input_feedback,
            previous_keter_score=int(previous.get("keter_score") or 0),
            now=generated_at,
        )
        comparison = compare_three_black_crows_to_hammer(
            hammer_origin=hammer,
            three_black_crows_rescore=rescore,
        )
        recommendations = build_keter_rescore_recommendations(
            input_feedback=input_feedback,
            rescore=rescore,
        )
        blockers = _blockers(input_feedback)
        status = _status_for_rescore(
            record_rescore=record_rescore,
            confirmation_valid=confirmation_valid,
            blockers=blockers,
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "rescore_recorded": False,
            "rescore_id": None,
            "record_rescore_requested": bool(record_rescore),
            "confirmation_valid": bool(confirmation_valid),
            "target_context": _target_context(DEFAULT_TARGET_LANE_KEY),
            "input_feedback": input_feedback,
            "three_black_crows_rescore": rescore,
            "comparison_to_hammer": comparison,
            "recommendations": recommendations,
            "recommended_next_operator_move": _recommended_next_operator_move(recommendations, rescore),
            "recommended_next_engineering_move": _recommended_next_engineering_move(recommendations, rescore),
            "do_not_run_yet": _do_not_run_yet(),
            "blockers": blockers,
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "feedback_source": feedback.get("feedback_source"),
            "keter_scoring_source": base_scoring.get("scoring_source"),
        }
        if record_rescore and confirmation_valid and not blockers:
            record = append_keter_rescore_after_three_black_crows_record(payload, log_dir=resolved_log_dir)
            payload["status"] = KETER_RESCORING_AFTER_CROWS_RECORDED
            payload["rescore_recorded"] = True
            payload["rescore_id"] = record["rescore_id"]
            payload["ledger_path"] = str(keter_rescore_after_three_black_crows_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": KETER_RESCORING_AFTER_CROWS_ERROR,
                "generated_at": generated_at.isoformat(),
                "rescore_recorded": False,
                "rescore_id": None,
                "record_rescore_requested": bool(record_rescore),
                "confirmation_valid": bool(confirmation_valid),
                "target_context": _target_context(DEFAULT_TARGET_LANE_KEY),
                "input_feedback": _empty_input_feedback(),
                "three_black_crows_rescore": _empty_rescore(),
                "comparison_to_hammer": compare_three_black_crows_to_hammer(
                    hammer_origin={},
                    three_black_crows_rescore=_empty_rescore(),
                ),
                "recommendations": build_keter_rescore_recommendations(input_feedback={}, rescore=_empty_rescore()),
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R191 Keter rescoring error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "blockers": [UNKNOWN_NEEDS_MANUAL_REVIEW],
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_three_black_crows_feedback(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_signal_origin_feedback_sync_records(log_dir=log_dir, limit=100)
    for record in records:
        target = record.get("target_context") if isinstance(record.get("target_context"), Mapping) else {}
        summary = record.get("three_black_crows_feedback_summary")
        if target.get("signal_origin") == SIGNAL_ORIGIN and isinstance(summary, Mapping):
            latest = dict(record)
            latest["feedback_source"] = "signal_origin_feedback_sync_ledger"
            return latest
    return {"feedback_source": "missing"}


def load_three_black_crows_detection_evidence(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    detections = load_three_black_crows_local_detection_records(log_dir=log_dir, limit=0)
    tags = load_three_black_crows_feedback_paper_tags(log_dir=log_dir, limit=0)
    matching_detections = []
    detection_ids: set[str] = set()
    for record in detections:
        for row in record.get("detections") or []:
            if isinstance(row, Mapping) and _row_targets(row):
                matching_detections.append(dict(row))
                if row.get("detection_id"):
                    detection_ids.add(str(row["detection_id"]))
    matching_tags = [
        dict(row)
        for row in tags
        if isinstance(row, Mapping)
        and _row_targets(row)
        and (not detection_ids or str(row.get("detection_id") or "") in detection_ids)
    ]
    strict = sum(1 for row in matching_detections if str(row.get("mode") or "") == "strict")
    loose = sum(1 for row in matching_detections if str(row.get("mode") or "") == "loose_preview")
    return {
        "detection_records_found": len(matching_detections),
        "paper_tags_found": len(matching_tags),
        "strict_detections_found": strict,
        "loose_detections_found": loose,
        "latest_detection_at": max((str(row.get("detected_at") or "") for row in matching_detections), default=None),
        "latest_tag_at": max((str(row.get("detected_at") or row.get("recorded_at_utc") or "") for row in matching_tags), default=None),
        "local_detector_available": bool(matching_detections),
    }


def build_three_black_crows_rescore_dimensions(
    *,
    input_feedback: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, int]:
    detector_available = bool(input_feedback.get("local_detector_available"))
    detections = int(input_feedback.get("detection_records_found") or 0)
    paper_tags = int(input_feedback.get("paper_tags_found") or 0)
    strict = int(input_feedback.get("strict_detections_found") or 0)
    latest_detection_at = str(input_feedback.get("latest_detection_at") or "")
    dimensions = {
        "detector_availability_score": 82 if detector_available else 12,
        "tagged_data_score": min(82, paper_tags * 4),
        "lane_coverage_score": 36 if detections > 0 else 0,
        "freshness_score": _freshness_score(latest_detection_at=latest_detection_at, now=now),
        "historical_outcome_score": 0,
        "reversal_context_score": 90 if strict > 0 else 76 if detections > 0 else 35,
        "conflict_penalty": _conflict_penalty(input_feedback),
    }
    return {key: int(max(0, min(100, value))) for key, value in dimensions.items()}


def rescore_three_black_crows_origin(
    *,
    input_feedback: Mapping[str, Any],
    previous_keter_score: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    dimensions = build_three_black_crows_rescore_dimensions(input_feedback=input_feedback, now=now)
    weighted = (
        dimensions["detector_availability_score"] * 0.24
        + dimensions["tagged_data_score"] * 0.18
        + dimensions["lane_coverage_score"] * 0.14
        + dimensions["freshness_score"] * 0.12
        + dimensions["historical_outcome_score"] * 0.14
        + dimensions["reversal_context_score"] * 0.18
        - dimensions["conflict_penalty"] * 0.30
    )
    score = int(round(max(0.0, min(100.0, weighted))))
    readiness = classify_three_black_crows_rescore_readiness(input_feedback=input_feedback, dimension_scores=dimensions)
    if readiness in {CROWS_DETECTOR_EVIDENCE_MISSING, CROWS_NEED_MORE_DETECTION_HISTORY}:
        score = min(score, 49)
    return {
        "previous_keter_score": int(previous_keter_score or 0),
        "new_keter_score": score,
        "score_band": _score_band(score),
        "readiness": readiness,
        "dimension_scores": dimensions,
        "paper_only": True,
        "live_authorized": False,
        "signal_origin_promoted": False,
    }


def compare_three_black_crows_to_hammer(
    *,
    hammer_origin: Mapping[str, Any],
    three_black_crows_rescore: Mapping[str, Any],
) -> dict[str, Any]:
    hammer_score = int(hammer_origin.get("keter_score") or 0)
    crows_score = int(three_black_crows_rescore.get("new_keter_score") or 0)
    hammer_best = hammer_score >= crows_score
    why = (
        "hammer_wick_reversal remains ahead because it has incumbent detector/tagged Keter evidence."
        if hammer_best
        else "three_black_crows has detector evidence after review, but remains paper-only and requires outcome mapping before promotion."
    )
    return {
        "hammer_keter_score": hammer_score,
        "three_black_crows_keter_score": crows_score,
        "hammer_still_best_origin": bool(hammer_best),
        "why": why,
    }


def build_keter_rescore_recommendations(
    *,
    input_feedback: Mapping[str, Any],
    rescore: Mapping[str, Any],
) -> dict[str, Any]:
    readiness = str(rescore.get("readiness") or UNKNOWN_NEEDS_MANUAL_REVIEW)
    detections = int(input_feedback.get("detection_records_found") or 0)
    return {
        "rerun_lane_matrix": readiness != CROWS_DETECTOR_EVIDENCE_MISSING,
        "paper_track_three_black_crows": readiness == CROWS_READY_FOR_PAPER_TRACKING_REVIEW,
        "need_paper_outcome_mapping": True,
        "need_more_detections": detections < 10,
        "no_live_authorization": True,
    }


def classify_three_black_crows_rescore_readiness(
    *,
    input_feedback: Mapping[str, Any],
    dimension_scores: Mapping[str, Any] | None = None,
) -> str:
    _ = dimension_scores
    if not bool(input_feedback.get("local_detector_available")) or int(input_feedback.get("detection_records_found") or 0) <= 0:
        return CROWS_DETECTOR_EVIDENCE_MISSING
    if int(input_feedback.get("detection_records_found") or 0) < 10:
        return CROWS_NEED_MORE_DETECTION_HISTORY
    if int(input_feedback.get("paper_tags_found") or 0) < 10:
        return CROWS_NEED_MORE_PAPER_OUTCOMES
    if bool(input_feedback.get("live_authorized")):
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    return CROWS_READY_FOR_PAPER_TRACKING_REVIEW


def append_keter_rescore_after_three_black_crows_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = keter_rescore_after_three_black_crows_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "rescore_id": str(record.get("rescore_id") or f"r191_keter_rescore_after_crows_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": KETER_RESCORING_AFTER_CROWS_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_rescore_requested": bool(record.get("record_rescore_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_context": dict(record.get("target_context") or {}),
            "input_feedback": dict(record.get("input_feedback") or {}),
            "three_black_crows_rescore": dict(record.get("three_black_crows_rescore") or {}),
            "comparison_to_hammer": dict(record.get("comparison_to_hammer") or {}),
            "recommendations": dict(record.get("recommendations") or {}),
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


def load_keter_rescore_after_three_black_crows_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = keter_rescore_after_three_black_crows_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_keter_rescore_after_three_black_crows_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    rescore = latest.get("three_black_crows_rescore") if isinstance(latest, Mapping) else {}
    comparison = latest.get("comparison_to_hammer") if isinstance(latest, Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_rescore_id": latest.get("rescore_id") if isinstance(latest, Mapping) else None,
        "last_three_black_crows_score": (rescore or {}).get("new_keter_score") if isinstance(rescore, Mapping) else None,
        "last_hammer_still_best_origin": (comparison or {}).get("hammer_still_best_origin")
        if isinstance(comparison, Mapping)
        else None,
        "safety": dict(SAFETY),
    }


def keter_rescore_after_three_black_crows_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_keter_rescore_after_three_black_crows_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _load_latest_or_preview_keter_scoring(*, log_dir: Path, now: datetime) -> dict[str, Any]:
    records = load_keter_signal_origin_scoring_records(log_dir=log_dir, limit=100)
    if records:
        latest = dict(records[0])
        latest["scoring_source"] = "keter_signal_origin_scoring_ledger"
        return latest
    preview = build_keter_signal_origin_scoring(log_dir=log_dir, record_scoring=False, now=now)
    preview["scoring_source"] = "keter_signal_origin_scoring_preview"
    return preview


def _build_input_feedback(*, feedback: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    summary = feedback.get("three_black_crows_feedback_summary") if isinstance(feedback.get("three_black_crows_feedback_summary"), Mapping) else {}
    registry_feedback = feedback.get("registry_feedback") if isinstance(feedback.get("registry_feedback"), Mapping) else {}
    return {
        "feedback_found": bool(summary),
        "detection_records_found": int(summary.get("detection_records_found") or evidence.get("detection_records_found") or 0),
        "paper_tags_found": int(summary.get("paper_tags_found") or evidence.get("paper_tags_found") or 0),
        "strict_detections_found": int(summary.get("strict_detections_found") or evidence.get("strict_detections_found") or 0),
        "loose_detections_found": int(summary.get("loose_detections_found") or evidence.get("loose_detections_found") or 0),
        "latest_detection_at": summary.get("latest_detection_at") or evidence.get("latest_detection_at"),
        "local_detector_available": bool(summary.get("local_detector_available") or evidence.get("local_detector_available")),
        "previous_availability": registry_feedback.get("previous_availability") or REGISTRY_ONLY,
        "recommended_future_availability": registry_feedback.get("recommended_future_availability") or DETECTOR_AVAILABLE_AFTER_REVIEW,
        "feedback_status": feedback.get("feedback_status"),
        "paper_only": True,
        "live_authorized": False,
        "signal_origin_promoted": False,
        "lane_promoted": False,
    }


def _origin_row(scoring: Mapping[str, Any], origin: str) -> dict[str, Any]:
    for row in scoring.get("keter_origin_rankings") or []:
        if isinstance(row, Mapping) and row.get("signal_origin") == origin:
            return dict(row)
    availability = DETECTOR_AVAILABLE if origin == REFERENCE_ORIGIN else REGISTRY_ONLY
    return {"signal_origin": origin, "availability": availability, "keter_score": 0}


def _blockers(input_feedback: Mapping[str, Any]) -> list[str]:
    if not bool(input_feedback.get("feedback_found")):
        return ["R190_FEEDBACK_SYNC_MISSING"]
    if str(input_feedback.get("feedback_status") or "") != READY_TO_RERUN_KETER_AND_MATRIX:
        return [str(input_feedback.get("feedback_status") or UNKNOWN_NEEDS_MANUAL_REVIEW)]
    if not bool(input_feedback.get("local_detector_available")):
        return [CROWS_DETECTOR_EVIDENCE_MISSING]
    return []


def _status_for_rescore(*, record_rescore: bool, confirmation_valid: bool, blockers: Sequence[str]) -> str:
    if record_rescore and not confirmation_valid:
        return KETER_RESCORING_AFTER_CROWS_REJECTED
    if blockers:
        return KETER_RESCORING_AFTER_CROWS_BLOCKED
    if record_rescore and confirmation_valid:
        return KETER_RESCORING_AFTER_CROWS_RECORDED
    return KETER_RESCORING_AFTER_CROWS_READY


def _target_context(lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction = _lane_parts(lane_key)
    return {
        "signal_origin": SIGNAL_ORIGIN,
        "primary_lane": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
    }


def _lane_parts(lane_key: str) -> tuple[str, str, str]:
    parts = str(lane_key).split("|")
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    return DEFAULT_SYMBOL, DEFAULT_TIMEFRAME, DEFAULT_DIRECTION


def _row_targets(row: Mapping[str, Any]) -> bool:
    return (
        str(row.get("signal_origin") or "") == SIGNAL_ORIGIN
        and _normalize_lane_key(row.get("lane_key") or row.get("primary_lane") or DEFAULT_TARGET_LANE_KEY) == DEFAULT_TARGET_LANE_KEY
    )


def _normalize_lane_key(value: object) -> str:
    parts = str(value or DEFAULT_TARGET_LANE_KEY).strip().split("|")
    if len(parts) == 4:
        return normalize_lane_key(parts[0], parts[1], parts[2], parts[3])
    return DEFAULT_TARGET_LANE_KEY


def _freshness_score(*, latest_detection_at: str, now: datetime | None) -> int:
    if not latest_detection_at:
        return 0
    generated_at = now or datetime.now(UTC)
    try:
        detected_at = datetime.fromisoformat(latest_detection_at.replace("Z", "+00:00"))
        age_hours = max(0.0, (generated_at - detected_at).total_seconds() / 3600.0)
    except ValueError:
        return 45
    if age_hours <= 24:
        return 92
    if age_hours <= 72:
        return 76
    if age_hours <= 168:
        return 58
    return 35


def _conflict_penalty(input_feedback: Mapping[str, Any]) -> int:
    penalty = 35
    if int(input_feedback.get("paper_tags_found") or 0) <= 0:
        penalty += 20
    if int(input_feedback.get("detection_records_found") or 0) < 10:
        penalty += 15
    if not bool(input_feedback.get("local_detector_available")):
        penalty += 55
    if bool(input_feedback.get("live_authorized")):
        penalty += 25
    return min(100, penalty)


def _score_band(score: int) -> str:
    if score <= 24:
        return "registry / unknown / not actionable"
    if score <= 49:
        return "needs detector or more data"
    if score <= 69:
        return "paper tracking candidate"
    if score <= 84:
        return "strong paper origin candidate"
    return "high-priority origin for next matrix work"


def _recommended_next_operator_move(recommendations: Mapping[str, Any], rescore: Mapping[str, Any]) -> str:
    if recommendations.get("rerun_lane_matrix"):
        return "RUN_R192_LANE_MATRIX_AFTER_CROW_RESCORING"
    if rescore.get("readiness") == CROWS_NEED_MORE_DETECTION_HISTORY:
        return "KEEP_8M_SHORT_WATCHER_RUNNING"
    return "KEEP_MULTI_LANE_HARVESTER_RUNNING"


def _recommended_next_engineering_move(recommendations: Mapping[str, Any], rescore: Mapping[str, Any]) -> str:
    if recommendations.get("rerun_lane_matrix"):
        return "Build R192 lane matrix after crow rescoring; compare 8m short hammer vs Three Black Crows without config writes or live execution."
    if rescore.get("readiness") == CROWS_DETECTOR_EVIDENCE_MISSING:
        return "Restore R190 feedback sync evidence before rescoring Keter."
    return "Keep collecting local paper evidence and map paper outcomes before any promotion review."


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


def _empty_input_feedback() -> dict[str, Any]:
    return {
        "feedback_found": False,
        "detection_records_found": 0,
        "paper_tags_found": 0,
        "strict_detections_found": 0,
        "loose_detections_found": 0,
        "latest_detection_at": None,
        "local_detector_available": False,
        "previous_availability": REGISTRY_ONLY,
        "recommended_future_availability": DETECTOR_AVAILABLE_AFTER_REVIEW,
    }


def _empty_rescore() -> dict[str, Any]:
    return {
        "previous_keter_score": 0,
        "new_keter_score": 0,
        "score_band": _score_band(0),
        "readiness": CROWS_DETECTOR_EVIDENCE_MISSING,
        "dimension_scores": {
            "detector_availability_score": 0,
            "tagged_data_score": 0,
            "lane_coverage_score": 0,
            "freshness_score": 0,
            "historical_outcome_score": 0,
            "reversal_context_score": 0,
            "conflict_penalty": 100,
        },
        "paper_only": True,
        "live_authorized": False,
        "signal_origin_promoted": False,
    }


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
