"""R195 lane matrix after Three Black Crows outcome feedback.

This module composes R194 outcome feedback, R192 lane matrix evidence, and
local funding/capture sync records into one audit-only post-outcome matrix. It
never calls Binance/network, creates payloads, mutates env/config, promotes
origins/lanes, changes lane modes, or authorizes live execution.
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
from src.app.hammer_radar.operator.capture_count_sync_8m_short import (
    LEDGER_FILENAME as CAPTURE_COUNT_SYNC_LEDGER_FILENAME,
    load_capture_count_sync_records,
)
from src.app.hammer_radar.operator.crow_outcome_keter_feedback import (
    CROW_OUTCOME_NEEDS_MORE_SAMPLES,
    LEDGER_FILENAME as CROW_OUTCOME_KETER_FEEDBACK_LEDGER_FILENAME,
    build_crow_outcome_keter_feedback,
    load_crow_outcome_keter_feedback_records,
)
from src.app.hammer_radar.operator.crow_outcome_mapping_preview import (
    LEDGER_FILENAME as CROW_OUTCOME_MAPPING_LEDGER_FILENAME,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.funding_gate_role_specific_sync import (
    LEDGER_FILENAME as FUNDING_GATE_SYNC_LEDGER_FILENAME,
    load_funding_gate_role_specific_sync_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.lane_matrix_after_crow_rescoring import (
    HAMMER_ORIGIN,
    LEDGER_FILENAME as LANE_MATRIX_AFTER_CROW_RESCORING_LEDGER_FILENAME,
    PAIR_NEEDS_PAPER_OUTCOME_MAPPING,
    build_lane_matrix_after_crow_rescoring,
    load_lane_matrix_after_crow_rescoring_records,
)
from src.app.hammer_radar.operator.signal_origin_lane_matrix import (
    PAIR_READY_FOR_PAPER_TRACKING,
    score_lane_origin_pair,
)
from src.app.hammer_radar.operator.signal_origin_registry import DETECTOR_AVAILABLE
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY
from src.app.hammer_radar.operator.three_black_crows_detector import (
    DEFAULT_DIRECTION,
    DEFAULT_SYMBOL,
    DEFAULT_TIMEFRAME,
    SIGNAL_ORIGIN as CROW_ORIGIN,
)

LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_READY = "LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_READY"
LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_REJECTED = "LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_REJECTED"
LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_RECORDED = "LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_RECORDED"
LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_BLOCKED = "LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_BLOCKED"
LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_ERROR = "LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_ERROR"

HAMMER_REMAINS_CURRENT_BEST_PAIR_AFTER_OUTCOME = "HAMMER_REMAINS_CURRENT_BEST_PAIR_AFTER_OUTCOME"
CROWS_CLOSE_GAP_BUT_NEED_MORE_SAMPLES = "CROWS_CLOSE_GAP_BUT_NEED_MORE_SAMPLES"
CROWS_OVERTAKE_HAMMER_FOR_PAPER_TRACKING = "CROWS_OVERTAKE_HAMMER_FOR_PAPER_TRACKING"
CROWS_NEED_MORE_OUTCOME_EVIDENCE = "CROWS_NEED_MORE_OUTCOME_EVIDENCE"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

NOT_CLOSE_FUNDING_AND_EVIDENCE_BLOCKED = "NOT_CLOSE_FUNDING_AND_EVIDENCE_BLOCKED"
STRUCTURALLY_CLOSE_BUT_OPERATIONALLY_BLOCKED = "STRUCTURALLY_CLOSE_BUT_OPERATIONALLY_BLOCKED"
CLOSE_AFTER_FUNDING_AND_10_CAPTURES = "CLOSE_AFTER_FUNDING_AND_10_CAPTURES"
READY_FOR_REVIEW_PACKET_AFTER_BLOCKERS_CLEAR = "READY_FOR_REVIEW_PACKET_AFTER_BLOCKERS_CLEAR"

EVENT_TYPE = "LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK"
LEDGER_FILENAME = "lane_matrix_after_crow_outcome_feedback.ndjson"
CONFIRM_LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_RECORDING_PHRASE = (
    "I CONFIRM LANE MATRIX AFTER CROW OUTCOME FEEDBACK RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_HAMMER_KETER_SCORE = 82
DEFAULT_PREVIOUS_HAMMER_PAIR_SCORE = 72
DEFAULT_PREVIOUS_CROW_PAIR_SCORE = 51
DEFAULT_PROJECTED_CROW_KETER_SCORE = 69
DEFAULT_OUTCOME_SCORE = 100
DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT = 10

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
    f"logs/hammer_radar_forward/{CROW_OUTCOME_KETER_FEEDBACK_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LANE_MATRIX_AFTER_CROW_RESCORING_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{CROW_OUTCOME_MAPPING_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{CAPTURE_COUNT_SYNC_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{FUNDING_GATE_SYNC_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_lane_matrix_after_crow_outcome_feedback(
    *,
    log_dir: str | Path | None = None,
    record_matrix: bool = False,
    confirm_lane_matrix_after_crow_outcome: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_lane_matrix_after_crow_outcome == CONFIRM_LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_RECORDING_PHRASE
    )
    try:
        r194_feedback = load_latest_crow_outcome_keter_feedback(log_dir=resolved_log_dir, now=generated_at)
        r192_matrix = load_latest_lane_matrix_after_crow_rescoring(log_dir=resolved_log_dir, now=generated_at)
        pair_comparison = build_post_outcome_pair_comparison(
            crow_outcome_keter_feedback=r194_feedback,
            lane_matrix_after_crow_rescoring=r192_matrix,
        )
        current_best = build_post_outcome_current_best_pair(pair_comparison=pair_comparison)
        matrix_status = classify_lane_matrix_after_outcome_status(
            pair_comparison=pair_comparison,
            current_best_pair=current_best,
        )
        tiny_live_distance = build_tiny_live_distance_after_outcome_feedback(
            log_dir=resolved_log_dir,
            pair_comparison=pair_comparison,
        )
        blockers = build_remaining_tiny_live_blockers(tiny_live_distance=tiny_live_distance, pair_comparison=pair_comparison)
        blocked = matrix_status == UNKNOWN_NEEDS_MANUAL_REVIEW
        status = LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_READY
        if blocked:
            status = LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_BLOCKED
        if record_matrix and not confirmation_valid:
            status = LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_REJECTED
        elif record_matrix and confirmation_valid and not blocked:
            status = LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_RECORDED
        recommendations = _recommendations(pair_comparison=pair_comparison, current_best_pair=current_best)
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "matrix_recorded": False,
            "matrix_id": None,
            "record_matrix_requested": bool(record_matrix),
            "confirmation_valid": bool(confirmation_valid),
            "target_context": _target_context(),
            "post_outcome_pair_comparison": pair_comparison,
            "current_best_pair": current_best,
            "post_outcome_matrix_status": matrix_status,
            "tiny_live_distance_after_outcome_feedback": tiny_live_distance,
            "remaining_tiny_live_blockers": blockers,
            "recommendations": recommendations,
            "recommended_next_operator_move": _recommended_next_operator_move(tiny_live_distance, recommendations),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix_status, tiny_live_distance),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "r194_feedback_source": r194_feedback.get("feedback_source"),
            "r192_matrix_source": r192_matrix.get("matrix_source"),
        }
        if record_matrix and confirmation_valid and not blocked:
            record = append_lane_matrix_after_crow_outcome_feedback_record(payload, log_dir=resolved_log_dir)
            payload["matrix_recorded"] = True
            payload["matrix_id"] = record["matrix_id"]
            payload["ledger_path"] = str(lane_matrix_after_crow_outcome_feedback_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_ERROR,
                "generated_at": generated_at.isoformat(),
                "matrix_recorded": False,
                "matrix_id": None,
                "record_matrix_requested": bool(record_matrix),
                "confirmation_valid": bool(confirmation_valid),
                "target_context": _target_context(),
                "post_outcome_pair_comparison": {},
                "current_best_pair": None,
                "post_outcome_matrix_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "tiny_live_distance_after_outcome_feedback": _unknown_tiny_live_distance(),
                "remaining_tiny_live_blockers": ["manual review required after R195 build error"],
                "recommendations": _recommendations(pair_comparison={}, current_best_pair=None),
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R195 lane matrix after crow outcome feedback error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_crow_outcome_keter_feedback(
    *,
    log_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    records = load_crow_outcome_keter_feedback_records(log_dir=log_dir, limit=100)
    for record in records:
        target = record.get("target_context") if isinstance(record.get("target_context"), Mapping) else {}
        if target.get("signal_origin") == CROW_ORIGIN and target.get("primary_lane") == DEFAULT_TARGET_LANE_KEY:
            latest = dict(record)
            latest["feedback_source"] = "crow_outcome_keter_feedback_ledger"
            return latest
    preview = build_crow_outcome_keter_feedback(log_dir=log_dir, record_feedback=False, now=now)
    preview["feedback_source"] = "crow_outcome_keter_feedback_preview"
    return preview


def load_latest_lane_matrix_after_crow_rescoring(
    *,
    log_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    records = load_lane_matrix_after_crow_rescoring_records(log_dir=log_dir, limit=100)
    if records:
        latest = dict(records[0])
        latest["matrix_source"] = "lane_matrix_after_crow_rescoring_ledger"
        return latest
    preview = build_lane_matrix_after_crow_rescoring(log_dir=log_dir, record_matrix=False, now=now)
    preview["matrix_source"] = "lane_matrix_after_crow_rescoring_preview"
    return preview


def build_post_outcome_pair_comparison(
    *,
    crow_outcome_keter_feedback: Mapping[str, Any],
    lane_matrix_after_crow_rescoring: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    previous_pairs = lane_matrix_after_crow_rescoring.get("pair_comparison")
    if not isinstance(previous_pairs, Mapping):
        previous_pairs = {}
    previous_hammer = previous_pairs.get(HAMMER_ORIGIN) if isinstance(previous_pairs.get(HAMMER_ORIGIN), Mapping) else {}
    previous_crows = previous_pairs.get(CROW_ORIGIN) if isinstance(previous_pairs.get(CROW_ORIGIN), Mapping) else {}
    feedback_score = (
        crow_outcome_keter_feedback.get("crow_outcome_feedback_score")
        if isinstance(crow_outcome_keter_feedback.get("crow_outcome_feedback_score"), Mapping)
        else {}
    )
    projection = (
        crow_outcome_keter_feedback.get("updated_crow_keter_projection")
        if isinstance(crow_outcome_keter_feedback.get("updated_crow_keter_projection"), Mapping)
        else {}
    )
    input_mapping = (
        crow_outcome_keter_feedback.get("input_outcome_mapping")
        if isinstance(crow_outcome_keter_feedback.get("input_outcome_mapping"), Mapping)
        else {}
    )
    comparison_to_hammer = (
        crow_outcome_keter_feedback.get("comparison_to_hammer")
        if isinstance(crow_outcome_keter_feedback.get("comparison_to_hammer"), Mapping)
        else {}
    )
    lane = {
        "lane_key": DEFAULT_TARGET_LANE_KEY,
        "mode": "paper",
        "fresh_capture_count": _int(
            previous_crows.get("fresh_capture_count") or previous_hammer.get("fresh_capture_count"),
            0,
            1_000_000,
            0,
        ),
        "fresh_threshold_required": _int(
            previous_crows.get("required_fresh_capture_count") or previous_hammer.get("required_fresh_capture_count"),
            1,
            1_000_000,
            DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT,
        ),
        "fresh_threshold_met": bool(previous_crows.get("threshold_met") or previous_hammer.get("threshold_met")),
        "score": _int(previous_crows.get("lane_score") or previous_hammer.get("lane_score"), 0, 100, 63),
        "reference_only": False,
    }
    hammer_keter_score = _int(
        previous_hammer.get("origin_keter_score") or comparison_to_hammer.get("hammer_keter_score"),
        0,
        100,
        DEFAULT_HAMMER_KETER_SCORE,
    )
    projected_crow_keter = _int(
        projection.get("projected_keter_score_after_outcome"),
        0,
        100,
        DEFAULT_PROJECTED_CROW_KETER_SCORE,
    )
    hammer_pair = dict(previous_hammer)
    hammer_pair.update(
        {
            "previous_pair_score": _int(previous_hammer.get("pair_score"), 0, 100, DEFAULT_PREVIOUS_HAMMER_PAIR_SCORE),
            "keter_score": hammer_keter_score,
            "current_pair_score": _int(previous_hammer.get("pair_score"), 0, 100, DEFAULT_PREVIOUS_HAMMER_PAIR_SCORE),
            "pair_readiness": str(previous_hammer.get("pair_readiness") or PAIR_READY_FOR_PAPER_TRACKING),
            "paper_only": True,
            "live_authorized": False,
            "signal_origin_promoted": False,
            "lane_promoted": False,
        }
    )
    crow_scored_pair = score_lane_origin_pair(
        lane=lane,
        origin={
            "signal_origin": CROW_ORIGIN,
            "availability": DETECTOR_AVAILABLE,
            "keter_score": projected_crow_keter,
        },
        tagged_record_count_for_lane=_int(previous_crows.get("paper_tags_found") or previous_crows.get("tagged_record_count_for_lane"), 0, 1_000_000, 23),
    )
    crow_readiness = (
        CROW_OUTCOME_NEEDS_MORE_SAMPLES
        if bool(input_mapping.get("needs_more_samples")) or _int(input_mapping.get("mapped_count"), 0, 1_000_000, 0) < 30
        else PAIR_READY_FOR_PAPER_TRACKING
    )
    crow_blockers = _dedupe(
        [
            *list(previous_crows.get("blockers") or []),
            "paper outcome sample size below promotion threshold"
            if crow_readiness == CROW_OUTCOME_NEEDS_MORE_SAMPLES
            else "",
        ]
    )
    crow_pair = dict(previous_crows)
    crow_pair.update(
        {
            "previous_pair_score": _int(previous_crows.get("pair_score"), 0, 100, DEFAULT_PREVIOUS_CROW_PAIR_SCORE),
            "origin_keter_score": projected_crow_keter,
            "projected_keter_score_after_outcome": projected_crow_keter,
            "outcome_score": _int(feedback_score.get("outcome_score"), 0, 100, DEFAULT_OUTCOME_SCORE),
            "best_window": str(input_mapping.get("best_window") or "unknown"),
            "mapped_count": _int(input_mapping.get("mapped_count"), 0, 1_000_000, 0),
            "needs_more_samples": bool(input_mapping.get("needs_more_samples", True)),
            "pair_score": _int(crow_scored_pair.get("pair_score"), 0, 100, DEFAULT_PREVIOUS_CROW_PAIR_SCORE),
            "current_pair_score": _int(crow_scored_pair.get("pair_score"), 0, 100, DEFAULT_PREVIOUS_CROW_PAIR_SCORE),
            "pair_readiness": crow_readiness,
            "paper_only": True,
            "live_authorized": False,
            "signal_origin_promoted": False,
            "lane_promoted": False,
            "score_inputs": dict(crow_scored_pair.get("score_inputs") or {}),
            "why": crow_scored_pair.get("why"),
            "blockers": crow_blockers,
        }
    )
    return {
        HAMMER_ORIGIN: _public_pair(hammer_pair),
        CROW_ORIGIN: _public_pair(crow_pair),
    }


def build_post_outcome_current_best_pair(*, pair_comparison: Mapping[str, Any]) -> dict[str, Any]:
    hammer = pair_comparison.get(HAMMER_ORIGIN) if isinstance(pair_comparison.get(HAMMER_ORIGIN), Mapping) else {}
    crows = pair_comparison.get(CROW_ORIGIN) if isinstance(pair_comparison.get(CROW_ORIGIN), Mapping) else {}
    hammer_score = _int(hammer.get("current_pair_score") or hammer.get("pair_score"), 0, 100, 0)
    crow_score = _int(crows.get("current_pair_score") or crows.get("pair_score"), 0, 100, 0)
    if crows and crow_score > hammer_score:
        return {
            "lane_key": DEFAULT_TARGET_LANE_KEY,
            "signal_origin": CROW_ORIGIN,
            "pair_score": crow_score,
            "why": "three_black_crows overtakes hammer on paper-only post-outcome scoring; it remains a paper-tracking candidate with no live authorization.",
            "paper_only": True,
            "live_authorized": False,
        }
    return {
        "lane_key": DEFAULT_TARGET_LANE_KEY,
        "signal_origin": HAMMER_ORIGIN,
        "pair_score": hammer_score,
        "why": "hammer_wick_reversal remains current best because its post-outcome pair score is still above Three Black Crows.",
        "paper_only": True,
        "live_authorized": False,
    }


def build_tiny_live_distance_after_outcome_feedback(
    *,
    log_dir: str | Path | None = None,
    pair_comparison: Mapping[str, Any],
) -> dict[str, Any]:
    capture = _latest_capture_context(log_dir=log_dir, pair_comparison=pair_comparison)
    funding = _latest_funding_context(log_dir=log_dir)
    fresh_count = _int(capture.get("fresh_capture_count"), 0, 1_000_000, 0)
    required = _int(capture.get("required_fresh_capture_count"), 1, 1_000_000, DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT)
    funding_ready = funding.get("funding_ready") is True
    evidence_ready = fresh_count >= required
    risk_contract_applied = False
    lane_mode = "paper"
    operator_approval = False
    live_flags_armed = False
    if not funding_ready and not evidence_ready:
        distance = NOT_CLOSE_FUNDING_AND_EVIDENCE_BLOCKED
    elif not all([funding_ready, evidence_ready, risk_contract_applied, lane_mode == "tiny_live", operator_approval, live_flags_armed]):
        distance = STRUCTURALLY_CLOSE_BUT_OPERATIONALLY_BLOCKED if funding_ready and evidence_ready else CLOSE_AFTER_FUNDING_AND_10_CAPTURES
    else:
        distance = READY_FOR_REVIEW_PACKET_AFTER_BLOCKERS_CLEAR
    return {
        "distance": distance,
        "funding_status": funding.get("funding_status") or "UNKNOWN",
        "available_balance_usdt": funding.get("available_balance_usdt"),
        "fresh_capture_count": fresh_count,
        "required_fresh_capture_count": required,
        "risk_contract_applied": risk_contract_applied,
        "lane_mode": lane_mode,
        "operator_approval": operator_approval,
        "live_flags_armed": live_flags_armed,
    }


def build_remaining_tiny_live_blockers(
    *,
    tiny_live_distance: Mapping[str, Any],
    pair_comparison: Mapping[str, Any],
) -> list[str]:
    _ = pair_comparison
    blockers: list[str] = []
    if tiny_live_distance.get("funding_status") not in {"ACCOUNT_FUNDED_READY_FOR_REVIEW", "FUNDING_SYNC_READY_FOR_REVIEW"}:
        blockers.append("funding")
    if _int(tiny_live_distance.get("fresh_capture_count"), 0, 1_000_000, 0) < _int(
        tiny_live_distance.get("required_fresh_capture_count"), 1, 1_000_000, DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT
    ):
        blockers.append("fresh captures 10/10")
    if tiny_live_distance.get("risk_contract_applied") is not True:
        blockers.append("risk contract")
    if tiny_live_distance.get("lane_mode") != "tiny_live":
        blockers.append("lane mode")
    if tiny_live_distance.get("operator_approval") is not True:
        blockers.append("operator approval")
    if tiny_live_distance.get("live_flags_armed") is not True:
        blockers.append("live flags")
    return blockers


def classify_lane_matrix_after_outcome_status(
    *,
    pair_comparison: Mapping[str, Any],
    current_best_pair: Mapping[str, Any] | None,
) -> str:
    hammer = pair_comparison.get(HAMMER_ORIGIN) if isinstance(pair_comparison.get(HAMMER_ORIGIN), Mapping) else {}
    crows = pair_comparison.get(CROW_ORIGIN) if isinstance(pair_comparison.get(CROW_ORIGIN), Mapping) else {}
    if not hammer or not crows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    previous_crow = _int(crows.get("previous_pair_score"), 0, 100, 0)
    current_crow = _int(crows.get("current_pair_score"), 0, 100, 0)
    best_origin = str((current_best_pair or {}).get("signal_origin") or "")
    if best_origin == CROW_ORIGIN:
        return CROWS_OVERTAKE_HAMMER_FOR_PAPER_TRACKING
    if bool(crows.get("needs_more_samples")) or _int(crows.get("mapped_count"), 0, 1_000_000, 0) < 30:
        if current_crow > previous_crow:
            return CROWS_CLOSE_GAP_BUT_NEED_MORE_SAMPLES
        return CROWS_NEED_MORE_OUTCOME_EVIDENCE
    return HAMMER_REMAINS_CURRENT_BEST_PAIR_AFTER_OUTCOME


def append_lane_matrix_after_crow_outcome_feedback_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = lane_matrix_after_crow_outcome_feedback_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "matrix_id": str(record.get("matrix_id") or f"r195_lane_matrix_after_crow_outcome_feedback_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_matrix_requested": bool(record.get("record_matrix_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_context": dict(record.get("target_context") or {}),
            "post_outcome_pair_comparison": dict(record.get("post_outcome_pair_comparison") or {}),
            "current_best_pair": record.get("current_best_pair"),
            "post_outcome_matrix_status": record.get("post_outcome_matrix_status"),
            "tiny_live_distance_after_outcome_feedback": dict(
                record.get("tiny_live_distance_after_outcome_feedback") or {}
            ),
            "remaining_tiny_live_blockers": list(record.get("remaining_tiny_live_blockers") or []),
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


def load_lane_matrix_after_crow_outcome_feedback_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = lane_matrix_after_crow_outcome_feedback_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_lane_matrix_after_crow_outcome_feedback_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    matrix_counts = Counter(str(record.get("post_outcome_matrix_status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    best = latest.get("current_best_pair") if isinstance(latest.get("current_best_pair"), Mapping) else {}
    distance = (
        latest.get("tiny_live_distance_after_outcome_feedback")
        if isinstance(latest.get("tiny_live_distance_after_outcome_feedback"), Mapping)
        else {}
    )
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "post_outcome_matrix_status_counts": dict(sorted(matrix_counts.items())),
        "last_matrix_id": latest.get("matrix_id") if isinstance(latest, Mapping) else None,
        "last_best_origin": best.get("signal_origin"),
        "last_tiny_live_distance": distance.get("distance"),
        "safety": dict(SAFETY),
    }


def lane_matrix_after_crow_outcome_feedback_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_lane_matrix_after_crow_outcome_feedback_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _latest_capture_context(*, log_dir: str | Path | None, pair_comparison: Mapping[str, Any]) -> dict[str, Any]:
    records = load_capture_count_sync_records(log_dir=log_dir, limit=1)
    if records:
        capture_count = records[0].get("capture_count") if isinstance(records[0].get("capture_count"), Mapping) else {}
        return {
            "fresh_capture_count": _int(capture_count.get("fresh_capture_count"), 0, 1_000_000, 0),
            "required_fresh_capture_count": _int(
                capture_count.get("required_fresh_capture_count"),
                1,
                1_000_000,
                DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT,
            ),
            "threshold_met": bool(capture_count.get("threshold_met")),
        }
    hammer = pair_comparison.get(HAMMER_ORIGIN) if isinstance(pair_comparison.get(HAMMER_ORIGIN), Mapping) else {}
    crows = pair_comparison.get(CROW_ORIGIN) if isinstance(pair_comparison.get(CROW_ORIGIN), Mapping) else {}
    return {
        "fresh_capture_count": _int(crows.get("fresh_capture_count") or hammer.get("fresh_capture_count"), 0, 1_000_000, 0),
        "required_fresh_capture_count": _int(
            crows.get("required_fresh_capture_count") or hammer.get("required_fresh_capture_count"),
            1,
            1_000_000,
            DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT,
        ),
        "threshold_met": bool(crows.get("threshold_met") or hammer.get("threshold_met")),
    }


def _latest_funding_context(*, log_dir: str | Path | None) -> dict[str, Any]:
    records = load_funding_gate_role_specific_sync_records(log_dir=log_dir, limit=1)
    if not records:
        return {"funding_status": "UNKNOWN", "available_balance_usdt": None, "funding_ready": False}
    latest = records[0]
    gate = latest.get("funding_gate") if isinstance(latest.get("funding_gate"), Mapping) else {}
    balance = latest.get("latest_balance_state") if isinstance(latest.get("latest_balance_state"), Mapping) else {}
    status = str(gate.get("funding_sync_status") or balance.get("balance_readiness") or "UNKNOWN")
    if status == "FUNDING_SYNC_ACCOUNT_NOT_FUNDED":
        status = "ACCOUNT_NOT_FUNDED"
    elif status == "FUNDING_SYNC_READY_FOR_REVIEW":
        status = "ACCOUNT_FUNDED_READY_FOR_REVIEW"
    elif status == "FUNDING_SYNC_BELOW_MINIMUM":
        status = "ACCOUNT_FUNDED_BELOW_MINIMUM"
    return {
        "funding_status": status,
        "available_balance_usdt": _float_or_none(balance.get("available_balance_usdt")),
        "funding_ready": bool(gate.get("funding_ready")),
    }


def _recommendations(
    *,
    pair_comparison: Mapping[str, Any],
    current_best_pair: Mapping[str, Any] | None,
) -> dict[str, Any]:
    crows = pair_comparison.get(CROW_ORIGIN) if isinstance(pair_comparison.get(CROW_ORIGIN), Mapping) else {}
    return {
        "keep_hammer_as_current_best_pair": str((current_best_pair or {}).get("signal_origin") or "") != CROW_ORIGIN,
        "continue_crow_paper_tracking": True,
        "collect_more_crow_samples": bool(crows.get("needs_more_samples", True)),
        "funding_required_before_live": True,
        "fresh_capture_threshold_required": True,
        "risk_contract_required": True,
        "no_live_authorization": True,
    }


def _recommended_next_operator_move(tiny_live_distance: Mapping[str, Any], recommendations: Mapping[str, Any]) -> str:
    if tiny_live_distance.get("funding_status") in {"UNKNOWN", "ACCOUNT_NOT_FUNDED", "FUNDING_SYNC_ACCOUNT_NOT_FUNDED"}:
        return "FUND_ACCOUNT_LATER"
    if recommendations.get("collect_more_crow_samples"):
        return "KEEP_8M_SHORT_WATCHER_RUNNING"
    if _int(tiny_live_distance.get("fresh_capture_count"), 0, 1_000_000, 0) < _int(
        tiny_live_distance.get("required_fresh_capture_count"), 1, 1_000_000, DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT
    ):
        return "KEEP_MULTI_LANE_HARVESTER_RUNNING"
    return "RUN_R196_TINY_LIVE_READINESS_ROADMAP"


def _recommended_next_engineering_move(matrix_status: str, tiny_live_distance: Mapping[str, Any]) -> str:
    _ = tiny_live_distance
    if matrix_status == CROWS_CLOSE_GAP_BUT_NEED_MORE_SAMPLES:
        return "Build R196 tiny-live readiness roadmap from current blockers; keep crows paper-tracking only and collect more outcome samples."
    if matrix_status == CROWS_OVERTAKE_HAMMER_FOR_PAPER_TRACKING:
        return "Open a paper-only promotion review packet later; do not promote crows, lanes, configs, or live flags from R195."
    return "Run R196 tiny-live readiness roadmap only after reviewing funding, fresh captures, risk contract, lane mode, approval, and live flags."


def _public_pair(pair: Mapping[str, Any]) -> dict[str, Any]:
    keep = {
        "lane_key",
        "signal_origin",
        "lane_score",
        "origin_keter_score",
        "previous_pair_score",
        "keter_score",
        "projected_keter_score_after_outcome",
        "outcome_score",
        "best_window",
        "mapped_count",
        "needs_more_samples",
        "pair_score",
        "current_pair_score",
        "pair_readiness",
        "fresh_capture_count",
        "required_fresh_capture_count",
        "threshold_met",
        "tagged_record_count_for_lane",
        "strict_detections_found",
        "loose_detections_found",
        "paper_tags_found",
        "detection_records_found",
        "needs_paper_outcome_mapping",
        "paper_only",
        "live_authorized",
        "lane_promoted",
        "signal_origin_promoted",
        "score_inputs",
        "why",
        "blockers",
    }
    result = {key: pair.get(key) for key in keep if key in pair}
    result["paper_only"] = True
    result["live_authorized"] = False
    result["lane_promoted"] = False
    result["signal_origin_promoted"] = False
    return result


def _target_context() -> dict[str, Any]:
    return {
        "primary_lane": DEFAULT_TARGET_LANE_KEY,
        "symbol": DEFAULT_SYMBOL,
        "timeframe": DEFAULT_TIMEFRAME,
        "direction": DEFAULT_DIRECTION,
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


def _unknown_tiny_live_distance() -> dict[str, Any]:
    return {
        "distance": UNKNOWN_NEEDS_MANUAL_REVIEW,
        "funding_status": "UNKNOWN",
        "available_balance_usdt": None,
        "fresh_capture_count": 0,
        "required_fresh_capture_count": DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT,
        "risk_contract_applied": False,
        "lane_mode": "paper",
        "operator_approval": False,
        "live_flags_armed": False,
    }


def _int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
