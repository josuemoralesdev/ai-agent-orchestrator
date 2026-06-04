"""R192 lane matrix after Three Black Crows rescoring.

This module composes R191 crow rescoring, R184 lane/origin matrix, and R181
multi-lane ranking evidence. It is audit-only: no network/Binance calls,
payload creation, config writes, lane/origin promotion, or live authorization.
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
from src.app.hammer_radar.operator.keter_rescoring_after_three_black_crows import (
    CROWS_READY_FOR_PAPER_TRACKING_REVIEW,
    build_keter_rescoring_after_three_black_crows,
    load_keter_rescore_after_three_black_crows_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.multi_lane_evidence_ranking import (
    build_multi_lane_evidence_ranking,
    load_multi_lane_evidence_ranking_records,
)
from src.app.hammer_radar.operator.signal_origin_lane_matrix import (
    PAIR_READY_FOR_PAPER_TRACKING,
    build_signal_origin_lane_matrix,
    load_signal_origin_lane_matrix_records,
    score_lane_origin_pair,
)
from src.app.hammer_radar.operator.signal_origin_registry import DETECTOR_AVAILABLE
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY
from src.app.hammer_radar.operator.three_black_crows_detector import SIGNAL_ORIGIN as CROW_ORIGIN

LANE_MATRIX_AFTER_CROW_RESCORING_READY = "LANE_MATRIX_AFTER_CROW_RESCORING_READY"
LANE_MATRIX_AFTER_CROW_RESCORING_REJECTED = "LANE_MATRIX_AFTER_CROW_RESCORING_REJECTED"
LANE_MATRIX_AFTER_CROW_RESCORING_RECORDED = "LANE_MATRIX_AFTER_CROW_RESCORING_RECORDED"
LANE_MATRIX_AFTER_CROW_RESCORING_BLOCKED = "LANE_MATRIX_AFTER_CROW_RESCORING_BLOCKED"
LANE_MATRIX_AFTER_CROW_RESCORING_ERROR = "LANE_MATRIX_AFTER_CROW_RESCORING_ERROR"

HAMMER_REMAINS_CURRENT_BEST_PAIR = "HAMMER_REMAINS_CURRENT_BEST_PAIR"
CROWS_BECOME_PAPER_TRACKING_PAIR = "CROWS_BECOME_PAPER_TRACKING_PAIR"
CROWS_NEED_PAPER_OUTCOME_MAPPING = "CROWS_NEED_PAPER_OUTCOME_MAPPING"
CROWS_NEED_MORE_EVIDENCE = "CROWS_NEED_MORE_EVIDENCE"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

PAIR_NEEDS_PAPER_OUTCOME_MAPPING = "PAIR_NEEDS_PAPER_OUTCOME_MAPPING"
PAIR_READY_FOR_PAPER_TRACKING_AFTER_OUTCOME_MAPPING = "PAIR_READY_FOR_PAPER_TRACKING"

EVENT_TYPE = "LANE_MATRIX_AFTER_CROW_RESCORING"
LEDGER_FILENAME = "lane_matrix_after_crow_rescoring.ndjson"
HAMMER_ORIGIN = "hammer_wick_reversal"
CONFIRM_LANE_MATRIX_AFTER_CROW_RESCORING_RECORDING_PHRASE = (
    "I CONFIRM LANE MATRIX AFTER CROW RESCORING RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "logs/hammer_radar_forward/keter_rescore_after_three_black_crows.ndjson",
    "logs/hammer_radar_forward/signal_origin_lane_matrix.ndjson",
    "logs/hammer_radar_forward/multi_lane_evidence_rankings.ndjson",
    "logs/hammer_radar_forward/three_black_crows_local_detections.ndjson",
    "logs/hammer_radar_forward/three_black_crows_paper_tags.ndjson",
    "operator.keter_rescoring_after_three_black_crows.build_keter_rescoring_after_three_black_crows",
    "operator.signal_origin_lane_matrix.build_signal_origin_lane_matrix",
    "operator.multi_lane_evidence_ranking.build_multi_lane_evidence_ranking",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_lane_matrix_after_crow_rescoring(
    *,
    log_dir: str | Path | None = None,
    record_matrix: bool = False,
    confirm_lane_matrix_after_crow_rescore: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_lane_matrix_after_crow_rescore == CONFIRM_LANE_MATRIX_AFTER_CROW_RESCORING_RECORDING_PHRASE
    )
    try:
        crow_rescore = load_latest_crow_rescore(log_dir=resolved_log_dir, now=generated_at)
        lane_matrix = load_latest_signal_origin_lane_matrix(log_dir=resolved_log_dir, now=generated_at)
        lane_ranking = _load_latest_multi_lane_ranking(log_dir=resolved_log_dir, now=generated_at)
        pair_comparison = build_post_crow_pair_scores(
            crow_rescore=crow_rescore,
            lane_matrix=lane_matrix,
            lane_ranking=lane_ranking,
        )
        current_best_pair = compare_hammer_vs_three_black_crows_pair(pair_comparison)
        post_crow_matrix_status = classify_post_crow_matrix_status(
            pair_comparison=pair_comparison,
            current_best_pair=current_best_pair,
        )
        recommendations = build_post_crow_matrix_recommendations(
            pair_comparison=pair_comparison,
            current_best_pair=current_best_pair,
            post_crow_matrix_status=post_crow_matrix_status,
        )
        blocked = not pair_comparison.get(HAMMER_ORIGIN) or not pair_comparison.get(CROW_ORIGIN)
        status = LANE_MATRIX_AFTER_CROW_RESCORING_READY
        if blocked:
            status = LANE_MATRIX_AFTER_CROW_RESCORING_BLOCKED
        if record_matrix and not confirmation_valid:
            status = LANE_MATRIX_AFTER_CROW_RESCORING_REJECTED
        elif record_matrix and confirmation_valid and not blocked:
            status = LANE_MATRIX_AFTER_CROW_RESCORING_RECORDED
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "matrix_recorded": False,
            "matrix_id": None,
            "record_matrix_requested": bool(record_matrix),
            "confirmation_valid": bool(confirmation_valid),
            "target_context": _target_context(DEFAULT_TARGET_LANE_KEY),
            "pair_comparison": pair_comparison,
            "current_best_pair": current_best_pair,
            "post_crow_matrix_status": post_crow_matrix_status,
            "candle_pattern_family_reuse_plan": build_candle_pattern_family_reuse_plan(),
            "recommendations": recommendations,
            "recommended_next_operator_move": _recommended_next_operator_move(
                post_crow_matrix_status=post_crow_matrix_status,
                recommendations=recommendations,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(
                post_crow_matrix_status=post_crow_matrix_status,
                recommendations=recommendations,
            ),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "r191_rescore_source": crow_rescore.get("rescore_source"),
            "r184_matrix_source": lane_matrix.get("matrix_source"),
            "r181_ranking_source": lane_ranking.get("ranking_source"),
        }
        if record_matrix and confirmation_valid and not blocked:
            record = append_lane_matrix_after_crow_rescoring_record(payload, log_dir=resolved_log_dir)
            payload["matrix_recorded"] = True
            payload["matrix_id"] = record["matrix_id"]
            payload["ledger_path"] = str(lane_matrix_after_crow_rescoring_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": LANE_MATRIX_AFTER_CROW_RESCORING_ERROR,
                "generated_at": generated_at.isoformat(),
                "matrix_recorded": False,
                "matrix_id": None,
                "record_matrix_requested": bool(record_matrix),
                "confirmation_valid": bool(confirmation_valid),
                "target_context": _target_context(DEFAULT_TARGET_LANE_KEY),
                "pair_comparison": {},
                "current_best_pair": None,
                "post_crow_matrix_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "candle_pattern_family_reuse_plan": build_candle_pattern_family_reuse_plan(),
                "recommendations": build_post_crow_matrix_recommendations(
                    pair_comparison={},
                    current_best_pair=None,
                    post_crow_matrix_status=UNKNOWN_NEEDS_MANUAL_REVIEW,
                ),
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R192 matrix build error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_crow_rescore(*, log_dir: str | Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    records = load_keter_rescore_after_three_black_crows_records(log_dir=log_dir, limit=100)
    if records:
        latest = dict(records[0])
        latest["rescore_source"] = "keter_rescore_after_three_black_crows_ledger"
        return latest
    preview = build_keter_rescoring_after_three_black_crows(log_dir=log_dir, record_rescore=False, now=now)
    preview["rescore_source"] = "keter_rescore_after_three_black_crows_preview"
    return preview


def load_latest_signal_origin_lane_matrix(
    *,
    log_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    records = load_signal_origin_lane_matrix_records(log_dir=log_dir, limit=100)
    if records:
        latest = dict(records[0])
        latest["matrix_source"] = "signal_origin_lane_matrix_ledger"
        return latest
    preview = build_signal_origin_lane_matrix(log_dir=log_dir, record_matrix=False, now=now)
    preview["matrix_source"] = "signal_origin_lane_matrix_preview"
    return preview


def build_post_crow_pair_scores(
    *,
    crow_rescore: Mapping[str, Any],
    lane_matrix: Mapping[str, Any],
    lane_ranking: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    lane = _target_lane(lane_ranking=lane_ranking, lane_matrix=lane_matrix)
    hammer = _hammer_pair_from_matrix(lane_matrix)
    rescore = crow_rescore.get("three_black_crows_rescore") if isinstance(crow_rescore.get("three_black_crows_rescore"), Mapping) else {}
    feedback = crow_rescore.get("input_feedback") if isinstance(crow_rescore.get("input_feedback"), Mapping) else {}
    hammer_origin_score = _bounded_int(
        hammer.get("origin_keter_score")
        or (crow_rescore.get("comparison_to_hammer") or {}).get("hammer_keter_score")
        if isinstance(crow_rescore.get("comparison_to_hammer"), Mapping)
        else None,
        0,
        100,
        82,
    )
    crow_origin_score = _bounded_int(rescore.get("new_keter_score"), 0, 100, 0)
    hammer_pair = score_lane_origin_pair(
        lane=lane,
        origin={
            "signal_origin": HAMMER_ORIGIN,
            "availability": DETECTOR_AVAILABLE,
            "keter_score": hammer_origin_score,
        },
        tagged_record_count_for_lane=_bounded_int(hammer.get("tagged_record_count_for_lane"), 0, 1_000_000, 0),
    )
    crow_pair = score_lane_origin_pair(
        lane=lane,
        origin={
            "signal_origin": CROW_ORIGIN,
            "availability": DETECTOR_AVAILABLE,
            "keter_score": crow_origin_score,
        },
        tagged_record_count_for_lane=_bounded_int(feedback.get("paper_tags_found"), 0, 1_000_000, 0),
    )
    crow_pair["pair_readiness"] = _crow_pair_readiness(crow_rescore=crow_rescore, crow_pair=crow_pair)
    crow_pair["strict_detections_found"] = _bounded_int(feedback.get("strict_detections_found"), 0, 1_000_000, 0)
    crow_pair["loose_detections_found"] = _bounded_int(feedback.get("loose_detections_found"), 0, 1_000_000, 0)
    crow_pair["paper_tags_found"] = _bounded_int(feedback.get("paper_tags_found"), 0, 1_000_000, 0)
    crow_pair["detection_records_found"] = _bounded_int(feedback.get("detection_records_found"), 0, 1_000_000, 0)
    crow_pair["needs_paper_outcome_mapping"] = True
    crow_pair["paper_only"] = True
    crow_pair["live_authorized"] = False
    crow_pair["signal_origin_promoted"] = False
    crow_pair["lane_promoted"] = False
    if "paper outcome mapping required before promotion review" not in crow_pair["blockers"]:
        crow_pair["blockers"] = [*list(crow_pair.get("blockers") or []), "paper outcome mapping required before promotion review"]
    return {
        HAMMER_ORIGIN: _public_pair(hammer_pair),
        CROW_ORIGIN: _public_pair(crow_pair),
    }


def compare_hammer_vs_three_black_crows_pair(pair_comparison: Mapping[str, Any]) -> dict[str, Any]:
    hammer = pair_comparison.get(HAMMER_ORIGIN) if isinstance(pair_comparison.get(HAMMER_ORIGIN), Mapping) else {}
    crows = pair_comparison.get(CROW_ORIGIN) if isinstance(pair_comparison.get(CROW_ORIGIN), Mapping) else {}
    hammer_score = _bounded_int(hammer.get("pair_score"), 0, 100, 0)
    crow_score = _bounded_int(crows.get("pair_score"), 0, 100, 0)
    if crow_score > hammer_score and crows:
        return {
            "lane_key": crows.get("lane_key") or DEFAULT_TARGET_LANE_KEY,
            "signal_origin": CROW_ORIGIN,
            "pair_score": crow_score,
            "why": "Three Black Crows pair score overtook hammer, but it remains paper-only and needs outcome mapping before any promotion review.",
            "paper_only": True,
            "live_authorized": False,
        }
    return {
        "lane_key": hammer.get("lane_key") or DEFAULT_TARGET_LANE_KEY,
        "signal_origin": HAMMER_ORIGIN,
        "pair_score": hammer_score,
        "why": "hammer_wick_reversal remains current best because its pair score is higher than the rescored Three Black Crows pair.",
        "paper_only": True,
        "live_authorized": False,
    }


def build_candle_pattern_family_reuse_plan() -> list[dict[str, Any]]:
    return [
        {
            "next_origin": "three_white_soldiers",
            "reuse_from_three_black_crows": True,
            "direction": "long",
            "priority": "MEDIUM",
            "why": "bullish mirror of the 3-candle detector family",
        },
        {
            "next_origin": "bearish_engulfing",
            "reuse_from_three_black_crows": "partial",
            "direction": "short",
            "priority": "MEDIUM",
            "why": "bearish candle-pattern detector can reuse local feed, lane tagging, and paper-only ledger architecture",
        },
        {
            "next_origin": "bullish_engulfing",
            "reuse_from_three_black_crows": "partial",
            "direction": "long",
            "priority": "MEDIUM",
            "why": "bullish engulfing should share the candle-pattern feed adapter and paper-tag path",
        },
        {
            "next_origin": "exhaustion_wick",
            "reuse_from_three_black_crows": "partial",
            "direction": "long|short",
            "priority": "LOW",
            "why": "wick exhaustion can reuse local feed plumbing but needs distinct wick-location rules",
        },
        {
            "next_origin": "breakdown_retest",
            "reuse_from_three_black_crows": "partial",
            "direction": "short",
            "priority": "LOW",
            "why": "retest family can reuse tagging and outcome mapping after pattern detectors are stable",
        },
        {
            "next_origin": "breakout_retest",
            "reuse_from_three_black_crows": "partial",
            "direction": "long",
            "priority": "LOW",
            "why": "long retest family can reuse tagging and outcome mapping after pattern detectors are stable",
        },
    ]


def build_post_crow_matrix_recommendations(
    *,
    pair_comparison: Mapping[str, Any],
    current_best_pair: Mapping[str, Any] | None,
    post_crow_matrix_status: str,
) -> dict[str, Any]:
    _ = pair_comparison
    best_origin = str((current_best_pair or {}).get("signal_origin") or "")
    return {
        "keep_hammer_as_current_best_pair": best_origin != CROW_ORIGIN,
        "paper_track_three_black_crows": post_crow_matrix_status
        in {HAMMER_REMAINS_CURRENT_BEST_PAIR, CROWS_BECOME_PAPER_TRACKING_PAIR, CROWS_NEED_PAPER_OUTCOME_MAPPING},
        "map_crow_detections_to_paper_outcomes": True,
        "build_three_white_soldiers_detector_later": True,
        "build_engulfing_detectors_later": True,
        "no_live_authorization": True,
    }


def classify_post_crow_matrix_status(
    *,
    pair_comparison: Mapping[str, Any],
    current_best_pair: Mapping[str, Any] | None,
) -> str:
    hammer = pair_comparison.get(HAMMER_ORIGIN) if isinstance(pair_comparison.get(HAMMER_ORIGIN), Mapping) else {}
    crows = pair_comparison.get(CROW_ORIGIN) if isinstance(pair_comparison.get(CROW_ORIGIN), Mapping) else {}
    if not hammer or not crows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if _bounded_int(crows.get("paper_tags_found"), 0, 1_000_000, 0) <= 0:
        return CROWS_NEED_MORE_EVIDENCE
    if str((current_best_pair or {}).get("signal_origin") or "") == CROW_ORIGIN:
        return CROWS_BECOME_PAPER_TRACKING_PAIR
    if bool(crows.get("needs_paper_outcome_mapping")):
        return HAMMER_REMAINS_CURRENT_BEST_PAIR
    return CROWS_NEED_PAPER_OUTCOME_MAPPING


def append_lane_matrix_after_crow_rescoring_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = lane_matrix_after_crow_rescoring_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "matrix_id": str(record.get("matrix_id") or f"r192_lane_matrix_after_crow_rescoring_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": LANE_MATRIX_AFTER_CROW_RESCORING_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_matrix_requested": bool(record.get("record_matrix_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_context": dict(record.get("target_context") or {}),
            "pair_comparison": dict(record.get("pair_comparison") or {}),
            "current_best_pair": record.get("current_best_pair"),
            "post_crow_matrix_status": record.get("post_crow_matrix_status"),
            "candle_pattern_family_reuse_plan": list(record.get("candle_pattern_family_reuse_plan") or []),
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


def load_lane_matrix_after_crow_rescoring_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = lane_matrix_after_crow_rescoring_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_lane_matrix_after_crow_rescoring_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    best = latest.get("current_best_pair") if isinstance(latest.get("current_best_pair"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_matrix_id": latest.get("matrix_id") if isinstance(latest, Mapping) else None,
        "last_best_lane": best.get("lane_key"),
        "last_best_origin": best.get("signal_origin"),
        "last_post_crow_matrix_status": latest.get("post_crow_matrix_status") if isinstance(latest, Mapping) else None,
        "safety": dict(SAFETY),
    }


def lane_matrix_after_crow_rescoring_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_lane_matrix_after_crow_rescoring_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _load_latest_multi_lane_ranking(*, log_dir: Path, now: datetime) -> dict[str, Any]:
    records = load_multi_lane_evidence_ranking_records(log_dir=log_dir, limit=100)
    if records:
        latest = dict(records[0])
        latest["ranking_source"] = "multi_lane_evidence_ranking_ledger"
        return latest
    preview = build_multi_lane_evidence_ranking(log_dir=log_dir, record_ranking=False, now=now)
    preview["ranking_source"] = "multi_lane_evidence_ranking_preview"
    return preview


def _target_lane(*, lane_ranking: Mapping[str, Any], lane_matrix: Mapping[str, Any]) -> dict[str, Any]:
    for lane in lane_ranking.get("ranked_lanes") or []:
        if isinstance(lane, Mapping) and lane.get("lane_key") == DEFAULT_TARGET_LANE_KEY:
            return dict(lane)
    for pair in lane_matrix.get("lane_origin_matrix") or []:
        if isinstance(pair, Mapping) and pair.get("lane_key") == DEFAULT_TARGET_LANE_KEY:
            return {
                "lane_key": DEFAULT_TARGET_LANE_KEY,
                "mode": "paper",
                "fresh_capture_count": _bounded_int(pair.get("fresh_capture_count"), 0, 1_000_000, 0),
                "fresh_threshold_required": _bounded_int(pair.get("required_fresh_capture_count"), 1, 1_000_000, 10),
                "fresh_threshold_met": bool(pair.get("threshold_met")),
                "score": _bounded_int(pair.get("lane_score"), 0, 100, 0),
                "reference_only": False,
            }
    return {
        "lane_key": DEFAULT_TARGET_LANE_KEY,
        "mode": "paper",
        "fresh_capture_count": 0,
        "fresh_threshold_required": 10,
        "fresh_threshold_met": False,
        "score": 0,
        "reference_only": False,
    }


def _hammer_pair_from_matrix(lane_matrix: Mapping[str, Any]) -> dict[str, Any]:
    for pair in lane_matrix.get("lane_origin_matrix") or []:
        if (
            isinstance(pair, Mapping)
            and pair.get("lane_key") == DEFAULT_TARGET_LANE_KEY
            and pair.get("signal_origin") == HAMMER_ORIGIN
        ):
            return dict(pair)
    current_best = lane_matrix.get("current_best_pair") if isinstance(lane_matrix.get("current_best_pair"), Mapping) else {}
    if current_best.get("lane_key") == DEFAULT_TARGET_LANE_KEY and current_best.get("signal_origin") == HAMMER_ORIGIN:
        return dict(current_best)
    return {}


def _crow_pair_readiness(*, crow_rescore: Mapping[str, Any], crow_pair: Mapping[str, Any]) -> str:
    rescore = crow_rescore.get("three_black_crows_rescore") if isinstance(crow_rescore.get("three_black_crows_rescore"), Mapping) else {}
    if rescore.get("readiness") == CROWS_READY_FOR_PAPER_TRACKING_REVIEW and _bounded_int(crow_pair.get("pair_score"), 0, 100, 0) >= 50:
        return PAIR_NEEDS_PAPER_OUTCOME_MAPPING
    if _bounded_int(crow_pair.get("pair_score"), 0, 100, 0) >= 50:
        return PAIR_READY_FOR_PAPER_TRACKING_AFTER_OUTCOME_MAPPING
    return str(crow_pair.get("pair_readiness") or PAIR_READY_FOR_PAPER_TRACKING)


def _public_pair(pair: Mapping[str, Any]) -> dict[str, Any]:
    keep = {
        "lane_key",
        "signal_origin",
        "lane_score",
        "origin_keter_score",
        "pair_score",
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


def _target_context(lane_key: str) -> dict[str, str]:
    parts = lane_key.split("|")
    symbol = parts[0] if len(parts) > 0 else "BTCUSDT"
    timeframe = parts[1] if len(parts) > 1 else "8m"
    direction = parts[2] if len(parts) > 2 else "short"
    return {
        "primary_lane": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
    }


def _recommended_next_operator_move(*, post_crow_matrix_status: str, recommendations: Mapping[str, Any]) -> str:
    if recommendations.get("map_crow_detections_to_paper_outcomes"):
        return "RUN_R193_CROW_OUTCOME_MAPPING_PREVIEW"
    if post_crow_matrix_status == CROWS_NEED_MORE_EVIDENCE:
        return "KEEP_8M_SHORT_WATCHER_RUNNING"
    return "KEEP_MULTI_LANE_HARVESTER_RUNNING"


def _recommended_next_engineering_move(*, post_crow_matrix_status: str, recommendations: Mapping[str, Any]) -> str:
    _ = recommendations
    if post_crow_matrix_status in {HAMMER_REMAINS_CURRENT_BEST_PAIR, CROWS_BECOME_PAPER_TRACKING_PAIR}:
        return "Build R193 crow outcome mapping preview to connect Three Black Crows detections to future paper outcome windows; keep all live/config gates closed."
    if post_crow_matrix_status == CROWS_NEED_MORE_EVIDENCE:
        return "Keep collecting local crow detector/tag evidence, then rerun R191 and R192 preview only."
    return "Review R181/R184/R191 inputs manually before any further detector-family expansion."


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
        parsed = default
    return max(minimum, min(maximum, parsed))


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
