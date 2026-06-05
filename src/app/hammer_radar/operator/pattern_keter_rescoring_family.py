"""R204 pattern-family Keter rescoring.

This module composes R202 pattern outcome mapping and R200 detector-family
feedback into a paper-only Keter rescore packet. It reads local ledgers only and
never calls Binance/network, creates payloads, mutates env/config, promotes
origins/lanes, or authorizes live execution.
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
from src.app.hammer_radar.operator.crow_outcome_keter_feedback import (
    load_crow_outcome_keter_feedback_records,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.keter_rescoring_after_three_black_crows import (
    load_keter_rescore_after_three_black_crows_records,
)
from src.app.hammer_radar.operator.keter_signal_origin_scoring import (
    load_keter_signal_origin_scoring_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.pattern_detector_family_expansion import (
    DEFAULT_PATTERNS,
    DEFAULT_SYMBOL,
    DETECTOR_PATTERNS,
    REGISTRY_ONLY_PATTERNS,
)
from src.app.hammer_radar.operator.pattern_family_feedback_sync import (
    load_pattern_family_feedback_sync_records,
)
from src.app.hammer_radar.operator.pattern_outcome_mapping_family import (
    REGISTRY_ONLY_BLOCK_REASON,
    load_pattern_outcome_mapping_family_records,
)

PATTERN_KETER_RESCORING_FAMILY_READY = "PATTERN_KETER_RESCORING_FAMILY_READY"
PATTERN_KETER_RESCORING_FAMILY_REJECTED = "PATTERN_KETER_RESCORING_FAMILY_REJECTED"
PATTERN_KETER_RESCORING_FAMILY_RECORDED = "PATTERN_KETER_RESCORING_FAMILY_RECORDED"
PATTERN_KETER_RESCORING_FAMILY_BLOCKED = "PATTERN_KETER_RESCORING_FAMILY_BLOCKED"
PATTERN_KETER_RESCORING_FAMILY_ERROR = "PATTERN_KETER_RESCORING_FAMILY_ERROR"

PATTERN_READY_FOR_PAPER_MATRIX_REVIEW = "PATTERN_READY_FOR_PAPER_MATRIX_REVIEW"
PATTERN_NEEDS_MORE_OUTCOME_EVIDENCE = "PATTERN_NEEDS_MORE_OUTCOME_EVIDENCE"
PATTERN_MIXED_BIAS_REVIEW_REQUIRED = "PATTERN_MIXED_BIAS_REVIEW_REQUIRED"
PATTERN_REGISTRY_ONLY_BLOCKED = "PATTERN_REGISTRY_ONLY_BLOCKED"
PATTERN_NOT_LIVE_AUTHORIZED = "PATTERN_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "PATTERN_KETER_RESCORING_FAMILY"
LEDGER_FILENAME = "pattern_keter_rescoring_family.ndjson"
CONFIRM_PATTERN_KETER_RESCORING_FAMILY_RECORDING_PHRASE = (
    "I CONFIRM PATTERN KETER RESCORING FAMILY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

REFERENCE_HAMMER_ORIGIN = "hammer_wick_reversal"
REFERENCE_CROWS_ORIGIN = "three_black_crows"

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
    "logs/hammer_radar_forward/pattern_outcome_mapping_family.ndjson",
    "logs/hammer_radar_forward/pattern_family_feedback_sync.ndjson",
    "logs/hammer_radar_forward/keter_signal_origin_scoring.ndjson",
    "logs/hammer_radar_forward/keter_rescore_after_three_black_crows.ndjson",
    "logs/hammer_radar_forward/crow_outcome_keter_feedback.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_pattern_keter_rescoring_family(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    record_rescore: bool = False,
    confirm_pattern_keter_family: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    confirmation_valid = confirm_pattern_keter_family == CONFIRM_PATTERN_KETER_RESCORING_FAMILY_RECORDING_PHRASE
    try:
        outcome_mapping = load_latest_pattern_outcome_mapping_family(log_dir=resolved_log_dir)
        feedback = load_latest_pattern_family_feedback_sync(log_dir=resolved_log_dir)
        input_summary = _build_input_summary(outcome_mapping=outcome_mapping, feedback=feedback)
        scorecards = build_pattern_origin_scorecard(outcome_mapping=outcome_mapping, feedback=feedback)
        rankings = build_pattern_keter_rankings(scorecards)
        reference = compare_pattern_origins_to_references(
            rankings=rankings,
            log_dir=resolved_log_dir,
        )
        lane_recommendations = build_pattern_lane_matrix_recommendations(scorecards)
        anchor_recommendations = build_pattern_anchor_confluence_recommendations(scorecards)
        rescore_status = classify_pattern_keter_rescoring_status(
            scorecards=scorecards,
            pattern_outcome_mapping_found=bool(outcome_mapping),
            pattern_family_feedback_found=bool(feedback),
        )
        status = _status_for_rescore(
            record_rescore=record_rescore,
            confirmation_valid=confirmation_valid,
            rescore_status=rescore_status,
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "rescore_recorded": False,
            "rescore_id": None,
            "record_rescore_requested": bool(record_rescore),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "symbol": normalized_symbol,
                "signal_origins": list(DEFAULT_PATTERNS),
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": input_summary,
            "pattern_origin_scorecards": scorecards,
            "pattern_keter_rankings": rankings,
            "reference_comparison": reference,
            "lane_matrix_recommendations": lane_recommendations,
            "anchor_confluence_recommendations": anchor_recommendations,
            "rescore_status": rescore_status,
            "recommended_next_operator_move": _recommended_next_operator_move(rescore_status, lane_recommendations),
            "recommended_next_engineering_move": _recommended_next_engineering_move(rescore_status, rankings),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "r202_outcome_mapping_source": outcome_mapping.get("mapping_source") if outcome_mapping else "missing",
            "r200_feedback_source": feedback.get("feedback_source") if feedback else "missing",
        }
        if record_rescore and confirmation_valid and rescore_status != UNKNOWN_NEEDS_MANUAL_REVIEW:
            record = append_pattern_keter_rescoring_family_record(payload, log_dir=resolved_log_dir)
            payload["status"] = PATTERN_KETER_RESCORING_FAMILY_RECORDED
            payload["rescore_recorded"] = True
            payload["rescore_id"] = record["rescore_id"]
            payload["ledger_path"] = str(pattern_keter_rescoring_family_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": PATTERN_KETER_RESCORING_FAMILY_ERROR,
                "generated_at": generated_at.isoformat(),
                "rescore_recorded": False,
                "rescore_id": None,
                "record_rescore_requested": bool(record_rescore),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "symbol": normalized_symbol,
                    "signal_origins": list(DEFAULT_PATTERNS),
                    "paper_only": True,
                    "live_authorized": False,
                },
                "input_summary": _empty_input_summary(),
                "pattern_origin_scorecards": _empty_scorecards(),
                "pattern_keter_rankings": [],
                "reference_comparison": compare_pattern_origins_to_references(rankings=[], log_dir=resolved_log_dir),
                "lane_matrix_recommendations": build_pattern_lane_matrix_recommendations(_empty_scorecards()),
                "anchor_confluence_recommendations": build_pattern_anchor_confluence_recommendations(_empty_scorecards()),
                "rescore_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R204 pattern Keter rescoring error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_pattern_outcome_mapping_family(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_pattern_outcome_mapping_family_records(log_dir=log_dir, limit=100)
    for record in records:
        if isinstance(record.get("origin_outcome_summary"), Mapping):
            latest = dict(record)
            latest["mapping_source"] = "pattern_outcome_mapping_family_ledger"
            return latest
    return {}


def load_latest_pattern_family_feedback_sync(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_pattern_family_feedback_sync_records(log_dir=log_dir, limit=100)
    for record in records:
        if isinstance(record.get("pattern_family_detection_summary"), Mapping):
            latest = dict(record)
            latest["feedback_source"] = "pattern_family_feedback_sync_ledger"
            return latest
    return {}


def build_pattern_keter_dimensions(
    *,
    signal_origin: str,
    outcome_summary: Mapping[str, Any],
    detector_summary: Mapping[str, Any],
    outcome_rankings: Sequence[Mapping[str, Any]] | None = None,
    anchor_recommendations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, int]:
    if signal_origin in REGISTRY_ONLY_PATTERNS:
        return {
            "detector_availability_score": 0,
            "detection_volume_score": 0,
            "outcome_sample_score": 0,
            "directional_bias_score": 0,
            "favorable_move_score": 0,
            "adverse_risk_penalty": 100,
            "failure_rate_penalty": 100,
            "mixed_bias_penalty": 100,
            "timeframe_coverage_score": 0,
            "anchor_overlay_readiness_score": 0,
            "live_safety_penalty": 0,
        }
    strict = _to_int(detector_summary.get("strict_detections_found"))
    loose = _to_int(detector_summary.get("loose_detections_found"))
    mapped_count = _to_int(outcome_summary.get("mapped_count"))
    best_stats = _best_window_stats(outcome_summary)
    supports = outcome_summary.get("supports_directional_bias")
    timeframes = detector_summary.get("timeframes_with_detections") or []
    warnings = _risk_warnings_for_origin(signal_origin, outcome_summary, outcome_rankings or [])
    favorable_rate = _to_float(best_stats.get("favorable_close_rate_pct"), 0.0)
    success_rate = _to_float(best_stats.get("simple_success_rate_pct"), 0.0)
    failure_rate = _to_float(best_stats.get("simple_failure_rate_pct"), 0.0)
    favorable_move = _to_float(best_stats.get("avg_favorable_move_pct"), 0.0)
    adverse_move = _to_float(best_stats.get("avg_adverse_move_pct"), 0.0)
    dimensions = {
        "detector_availability_score": 92 if bool(detector_summary.get("detector_available")) else 20,
        "detection_volume_score": _volume_score(strict + loose),
        "outcome_sample_score": _sample_score(mapped_count),
        "directional_bias_score": 88 if supports is True else 35 if supports is False else 10,
        "favorable_move_score": int(max(0, min(100, (favorable_rate * 0.45) + (success_rate * 0.35) + min(20.0, favorable_move * 20.0)))),
        "adverse_risk_penalty": _adverse_risk_penalty(favorable_move=favorable_move, adverse_move=adverse_move, warnings=warnings),
        "failure_rate_penalty": _failure_rate_penalty(failure_rate=failure_rate, success_rate=success_rate, warnings=warnings),
        "mixed_bias_penalty": 42 if supports is False else 0,
        "timeframe_coverage_score": min(100, len([item for item in timeframes if str(item)]) * 8),
        "anchor_overlay_readiness_score": _anchor_score(signal_origin, anchor_recommendations or []),
        "live_safety_penalty": 100 if bool(outcome_summary.get("live_authorized")) or bool(detector_summary.get("live_authorized")) else 0,
    }
    return {key: int(max(0, min(100, value))) for key, value in dimensions.items()}


def score_pattern_origin(
    *,
    signal_origin: str,
    outcome_summary: Mapping[str, Any],
    detector_summary: Mapping[str, Any],
    outcome_rankings: Sequence[Mapping[str, Any]] | None = None,
    anchor_recommendations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if signal_origin in REGISTRY_ONLY_PATTERNS:
        return {
            "signal_origin": signal_origin,
            "keter_score": 0,
            "score_band": "registry-only blocked",
            "readiness": PATTERN_REGISTRY_ONLY_BLOCKED,
            "blocked_reason": REGISTRY_ONLY_BLOCK_REASON,
            "dimension_scores": build_pattern_keter_dimensions(
                signal_origin=signal_origin,
                outcome_summary=outcome_summary,
                detector_summary=detector_summary,
                outcome_rankings=outcome_rankings,
                anchor_recommendations=anchor_recommendations,
            ),
            "mapped_count": 0,
            "supports_directional_bias": False,
            "risk_warnings": [REGISTRY_ONLY_BLOCK_REASON],
            "paper_only": True,
            "live_authorized": False,
            "signal_origin_promoted": False,
            "lane_promoted": False,
        }
    dimensions = build_pattern_keter_dimensions(
        signal_origin=signal_origin,
        outcome_summary=outcome_summary,
        detector_summary=detector_summary,
        outcome_rankings=outcome_rankings,
        anchor_recommendations=anchor_recommendations,
    )
    weighted = (
        dimensions["detector_availability_score"] * 0.15
        + dimensions["detection_volume_score"] * 0.09
        + dimensions["outcome_sample_score"] * 0.15
        + dimensions["directional_bias_score"] * 0.18
        + dimensions["favorable_move_score"] * 0.15
        + dimensions["timeframe_coverage_score"] * 0.08
        + dimensions["anchor_overlay_readiness_score"] * 0.08
        - dimensions["adverse_risk_penalty"] * 0.08
        - dimensions["failure_rate_penalty"] * 0.08
        - dimensions["mixed_bias_penalty"] * 0.10
        - dimensions["live_safety_penalty"] * 0.50
    )
    score = int(round(max(0.0, min(100.0, weighted))))
    readiness = _readiness_for_pattern(outcome_summary=outcome_summary, dimension_scores=dimensions, score=score)
    if readiness == PATTERN_NEEDS_MORE_OUTCOME_EVIDENCE:
        score = min(score, 69)
    elif readiness == PATTERN_MIXED_BIAS_REVIEW_REQUIRED:
        score = min(score, 64)
    warnings = _risk_warnings_for_origin(signal_origin, outcome_summary, outcome_rankings or [])
    return {
        "signal_origin": signal_origin,
        "keter_score": score,
        "score_band": _score_band(score),
        "readiness": readiness,
        "dimension_scores": dimensions,
        "mapped_count": _to_int(outcome_summary.get("mapped_count")),
        "supports_directional_bias": bool(outcome_summary.get("supports_directional_bias")),
        "best_window": str(outcome_summary.get("best_window") or "unknown"),
        "risk_warnings": warnings,
        "paper_only": True,
        "live_authorized": False,
        "signal_origin_promoted": False,
        "lane_promoted": False,
    }


def build_pattern_origin_scorecard(
    *,
    outcome_mapping: Mapping[str, Any],
    feedback: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    outcome_summary = outcome_mapping.get("origin_outcome_summary") if isinstance(outcome_mapping.get("origin_outcome_summary"), Mapping) else {}
    detector_summary = feedback.get("pattern_family_detection_summary") if isinstance(feedback.get("pattern_family_detection_summary"), Mapping) else {}
    rankings = outcome_mapping.get("pattern_outcome_rankings") if isinstance(outcome_mapping.get("pattern_outcome_rankings"), list) else []
    anchors = feedback.get("anchor_overlay_recommendations") if isinstance(feedback.get("anchor_overlay_recommendations"), list) else []
    return {
        origin: score_pattern_origin(
            signal_origin=origin,
            outcome_summary=dict((outcome_summary or {}).get(origin) or {}),
            detector_summary=dict((detector_summary or {}).get(origin) or {}),
            outcome_rankings=rankings,
            anchor_recommendations=anchors,
        )
        for origin in DEFAULT_PATTERNS
    }


def compare_pattern_origins_to_references(
    *,
    rankings: Sequence[Mapping[str, Any]],
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    references = _load_reference_scores(log_dir=log_dir)
    top = rankings[0] if rankings else {}
    top_origin = top.get("signal_origin")
    top_score = _to_int(top.get("keter_score")) if top else None
    hammer_score = references.get("hammer_wick_reversal_keter_score")
    crows_score = references.get("three_black_crows_projected_score")
    pattern_beats_crows = None if crows_score is None or top_score is None else top_score > int(crows_score)
    pattern_beats_hammer = None if hammer_score is None or top_score is None else top_score > int(hammer_score)
    why = (
        "Reference scores were unavailable in local ledgers; comparison remains manual-review only."
        if hammer_score is None and crows_score is None
        else "Top pattern origin is compared against local paper-only Keter reference records; no promotion or live authority is created."
    )
    return {
        "hammer_wick_reversal_keter_score": hammer_score,
        "three_black_crows_projected_score": crows_score,
        "top_pattern_origin": top_origin,
        "top_pattern_score": top_score,
        "pattern_beats_crows": pattern_beats_crows,
        "pattern_beats_hammer": pattern_beats_hammer,
        "reference_sources": references.get("reference_sources", {}),
        "why": why,
    }


def build_pattern_keter_rankings(scorecards: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for origin in DETECTOR_PATTERNS:
        card = dict(scorecards.get(origin) or {})
        why = _ranking_why(origin, card)
        rows.append(
            {
                "rank": 0,
                "signal_origin": origin,
                "keter_score": _to_int(card.get("keter_score")),
                "readiness": card.get("readiness") or UNKNOWN_NEEDS_MANUAL_REVIEW,
                "why": why,
                "paper_only": True,
                "live_authorized": False,
            }
        )
    rows.sort(key=lambda row: (-int(row["keter_score"]), str(row["signal_origin"])))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def build_pattern_lane_matrix_recommendations(scorecards: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    recommendations = []
    for origin in DEFAULT_PATTERNS:
        card = dict(scorecards.get(origin) or {})
        readiness = str(card.get("readiness") or UNKNOWN_NEEDS_MANUAL_REVIEW)
        score = _to_int(card.get("keter_score"))
        if readiness == PATTERN_REGISTRY_ONLY_BLOCKED:
            action, priority, why = "KEEP_BLOCKED", "LOW", "Retest origin remains registry-only until retest structure exists."
        elif readiness == PATTERN_READY_FOR_PAPER_MATRIX_REVIEW and score >= 70:
            action, priority, why = "INCLUDE_IN_PAPER_MATRIX", "HIGH", "Keter score and directional evidence support paper lane-matrix review."
        elif readiness == PATTERN_READY_FOR_PAPER_MATRIX_REVIEW:
            action, priority, why = "INCLUDE_IN_PAPER_MATRIX", "MEDIUM", "Paper evidence is review-ready but should remain audit-only."
        else:
            action, priority, why = "COLLECT_MORE_SAMPLES", "MEDIUM", "Outcome evidence is mixed or sample/risk limited."
        recommendations.append({"signal_origin": origin, "recommended_action": action, "priority": priority, "why": why})
    return recommendations


def build_pattern_anchor_confluence_recommendations(scorecards: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    recommendations = []
    for origin in DEFAULT_PATTERNS:
        card = dict(scorecards.get(origin) or {})
        readiness = str(card.get("readiness") or UNKNOWN_NEEDS_MANUAL_REVIEW)
        score = _to_int(card.get("keter_score"))
        anchor_score = _to_int((card.get("dimension_scores") or {}).get("anchor_overlay_readiness_score"))
        if readiness == PATTERN_REGISTRY_ONLY_BLOCKED:
            action, priority, why = "KEEP_BLOCKED", "LOW", "Retest origin has no detector/outcome basis for anchor confluence."
        elif readiness == PATTERN_READY_FOR_PAPER_MATRIX_REVIEW and anchor_score >= 70:
            action = "INCLUDE_IN_R203_CONFLUENCE"
            priority = "HIGH" if score >= 70 else "MEDIUM"
            why = "Pattern evidence and R200 anchor overlay both support paper confluence review."
        else:
            action, priority, why = "WAIT_FOR_OUTCOME_DEPTH", "MEDIUM", "Keep collecting outcome depth before anchor confluence review."
        recommendations.append({"signal_origin": origin, "recommended_action": action, "priority": priority, "why": why})
    return recommendations


def classify_pattern_keter_rescoring_status(
    *,
    scorecards: Mapping[str, Mapping[str, Any]],
    pattern_outcome_mapping_found: bool,
    pattern_family_feedback_found: bool,
) -> str:
    if not pattern_outcome_mapping_found or not pattern_family_feedback_found:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if any((scorecards.get(origin) or {}).get("readiness") == PATTERN_READY_FOR_PAPER_MATRIX_REVIEW for origin in DETECTOR_PATTERNS):
        return PATTERN_READY_FOR_PAPER_MATRIX_REVIEW
    if any((scorecards.get(origin) or {}).get("readiness") == PATTERN_MIXED_BIAS_REVIEW_REQUIRED for origin in DETECTOR_PATTERNS):
        return PATTERN_MIXED_BIAS_REVIEW_REQUIRED
    return PATTERN_NEEDS_MORE_OUTCOME_EVIDENCE


def append_pattern_keter_rescoring_family_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = pattern_keter_rescoring_family_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "rescore_id": str(record.get("rescore_id") or f"r204_pattern_keter_rescoring_family_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": PATTERN_KETER_RESCORING_FAMILY_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_rescore_requested": bool(record.get("record_rescore_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "pattern_origin_scorecards": dict(record.get("pattern_origin_scorecards") or {}),
            "pattern_keter_rankings": list(record.get("pattern_keter_rankings") or []),
            "reference_comparison": dict(record.get("reference_comparison") or {}),
            "lane_matrix_recommendations": list(record.get("lane_matrix_recommendations") or []),
            "anchor_confluence_recommendations": list(record.get("anchor_confluence_recommendations") or []),
            "rescore_status": record.get("rescore_status"),
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


def load_pattern_keter_rescoring_family_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = pattern_keter_rescoring_family_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_pattern_keter_rescoring_family_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    rankings = latest.get("pattern_keter_rankings") if isinstance(latest, Mapping) else []
    top = rankings[0] if rankings and isinstance(rankings[0], Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_rescore_id": latest.get("rescore_id") if isinstance(latest, Mapping) else None,
        "last_top_pattern_origin": top.get("signal_origin"),
        "last_top_pattern_score": top.get("keter_score"),
        "safety": dict(SAFETY),
    }


def pattern_keter_rescoring_family_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_pattern_keter_rescoring_family_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(*, outcome_mapping: Mapping[str, Any], feedback: Mapping[str, Any]) -> dict[str, Any]:
    aggregate = outcome_mapping.get("aggregate_summary") if isinstance(outcome_mapping.get("aggregate_summary"), Mapping) else {}
    return {
        "pattern_outcome_mapping_found": bool(outcome_mapping),
        "pattern_family_feedback_found": bool(feedback),
        "total_mapped_count": _to_int(aggregate.get("total_mapped_count")),
        "origins_with_positive_bias": list(aggregate.get("origins_with_positive_bias") or []),
        "origins_with_mixed_bias": list(aggregate.get("origins_with_mixed_bias") or []),
        "registry_only_blocked": list(aggregate.get("registry_only_blocked") or REGISTRY_ONLY_PATTERNS),
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "pattern_outcome_mapping_found": False,
        "pattern_family_feedback_found": False,
        "total_mapped_count": 0,
        "origins_with_positive_bias": [],
        "origins_with_mixed_bias": [],
        "registry_only_blocked": list(REGISTRY_ONLY_PATTERNS),
    }


def _empty_scorecards() -> dict[str, dict[str, Any]]:
    return {origin: score_pattern_origin(signal_origin=origin, outcome_summary={}, detector_summary={}) for origin in DEFAULT_PATTERNS}


def _status_for_rescore(*, record_rescore: bool, confirmation_valid: bool, rescore_status: str) -> str:
    if record_rescore and not confirmation_valid:
        return PATTERN_KETER_RESCORING_FAMILY_REJECTED
    if rescore_status == UNKNOWN_NEEDS_MANUAL_REVIEW:
        return PATTERN_KETER_RESCORING_FAMILY_BLOCKED
    if record_rescore and confirmation_valid:
        return PATTERN_KETER_RESCORING_FAMILY_RECORDED
    return PATTERN_KETER_RESCORING_FAMILY_READY


def _best_window_stats(outcome_summary: Mapping[str, Any]) -> dict[str, Any]:
    best_window = str(outcome_summary.get("best_window") or "unknown")
    stats_by_window = outcome_summary.get("window_stats") if isinstance(outcome_summary.get("window_stats"), Mapping) else {}
    stats = stats_by_window.get(best_window) if isinstance(stats_by_window.get(best_window), Mapping) else {}
    return dict(stats)


def _risk_warnings_for_origin(
    signal_origin: str,
    outcome_summary: Mapping[str, Any],
    rankings: Sequence[Mapping[str, Any]],
) -> list[str]:
    warnings = []
    best_stats = _best_window_stats(outcome_summary)
    if _to_float(best_stats.get("simple_failure_rate_pct"), 0.0) > _to_float(best_stats.get("simple_success_rate_pct"), 0.0):
        warnings.append("failure_rate_exceeds_success_rate")
    if _to_float(best_stats.get("avg_adverse_move_pct"), 0.0) > _to_float(best_stats.get("avg_favorable_move_pct"), 0.0):
        warnings.append("average_adverse_exceeds_average_favorable")
    if outcome_summary.get("supports_directional_bias") is False:
        warnings.append("mixed_directional_bias_review_required")
    for row in rankings:
        if str(row.get("signal_origin") or "") == signal_origin:
            warnings.extend(str(item) for item in row.get("risk_warnings") or [])
    return list(dict.fromkeys(warnings))


def _volume_score(count: int) -> int:
    if count >= 1000:
        return 100
    if count >= 250:
        return 88
    if count >= 100:
        return 76
    if count >= 30:
        return 60
    if count > 0:
        return 36
    return 0


def _sample_score(count: int) -> int:
    if count >= 1000:
        return 100
    if count >= 250:
        return 90
    if count >= 100:
        return 78
    if count >= 30:
        return 62
    if count > 0:
        return 36
    return 0


def _adverse_risk_penalty(*, favorable_move: float, adverse_move: float, warnings: Sequence[str]) -> int:
    penalty = 0
    if adverse_move > favorable_move:
        penalty += 45
    if "average_adverse_exceeds_average_favorable" in warnings:
        penalty += 25
    return min(100, penalty)


def _failure_rate_penalty(*, failure_rate: float, success_rate: float, warnings: Sequence[str]) -> int:
    penalty = 0
    if failure_rate > success_rate:
        penalty += 45
    if failure_rate >= 80.0:
        penalty += 35
    elif failure_rate >= 60.0:
        penalty += 20
    if "failure_rate_exceeds_success_rate" in warnings:
        penalty += 15
    return min(100, penalty)


def _anchor_score(signal_origin: str, anchor_recommendations: Sequence[Mapping[str, Any]]) -> int:
    for row in anchor_recommendations:
        if str(row.get("signal_origin") or "") != signal_origin:
            continue
        priority = str(row.get("priority") or "").upper()
        if priority == "HIGH":
            return 88
        if priority == "MEDIUM":
            return 68
        if priority == "LOW":
            return 42
    return 0


def _readiness_for_pattern(*, outcome_summary: Mapping[str, Any], dimension_scores: Mapping[str, int], score: int) -> str:
    if _to_int(outcome_summary.get("mapped_count")) <= 0:
        return PATTERN_NEEDS_MORE_OUTCOME_EVIDENCE
    if dimension_scores.get("live_safety_penalty", 0) > 0:
        return PATTERN_NOT_LIVE_AUTHORIZED
    if outcome_summary.get("supports_directional_bias") is False or dimension_scores.get("mixed_bias_penalty", 0) > 0:
        return PATTERN_MIXED_BIAS_REVIEW_REQUIRED
    if _to_int(outcome_summary.get("mapped_count")) < 30 or score < 50:
        return PATTERN_NEEDS_MORE_OUTCOME_EVIDENCE
    return PATTERN_READY_FOR_PAPER_MATRIX_REVIEW


def _score_band(score: int) -> str:
    if score <= 24:
        return "blocked or insufficient evidence"
    if score <= 49:
        return "needs more paper evidence"
    if score <= 69:
        return "paper review candidate with limits"
    if score <= 84:
        return "strong paper matrix candidate"
    return "top paper matrix candidate"


def _ranking_why(origin: str, card: Mapping[str, Any]) -> str:
    readiness = str(card.get("readiness") or UNKNOWN_NEEDS_MANUAL_REVIEW)
    if readiness == PATTERN_READY_FOR_PAPER_MATRIX_REVIEW:
        return f"{origin} has detector evidence, mapped outcome depth, and favorable directional behavior for paper matrix review."
    if readiness == PATTERN_MIXED_BIAS_REVIEW_REQUIRED:
        return f"{origin} has mapped outcomes but mixed directional bias or risk warnings keep it review-only."
    return f"{origin} needs more paper-only outcome evidence before lane/anchor matrix use."


def _load_reference_scores(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    sources: dict[str, str] = {}
    hammer_score = None
    crows_score = None
    for record in load_keter_signal_origin_scoring_records(log_dir=log_dir, limit=100):
        rows = record.get("keter_origin_rankings") if isinstance(record.get("keter_origin_rankings"), list) else []
        for row in rows:
            if isinstance(row, Mapping) and row.get("signal_origin") == REFERENCE_HAMMER_ORIGIN:
                hammer_score = _to_int(row.get("keter_score"))
                sources["hammer_wick_reversal_keter_score"] = "keter_signal_origin_scoring_ledger"
                break
        if hammer_score is not None:
            break
    for record in load_crow_outcome_keter_feedback_records(log_dir=log_dir, limit=100):
        projection = record.get("updated_crow_keter_projection") if isinstance(record.get("updated_crow_keter_projection"), Mapping) else {}
        if projection.get("projected_keter_score_after_outcome") is not None:
            crows_score = _to_int(projection.get("projected_keter_score_after_outcome"))
            sources["three_black_crows_projected_score"] = "crow_outcome_keter_feedback_ledger"
            comparison = record.get("comparison_to_hammer") if isinstance(record.get("comparison_to_hammer"), Mapping) else {}
            if hammer_score is None and comparison.get("hammer_keter_score") is not None:
                hammer_score = _to_int(comparison.get("hammer_keter_score"))
                sources["hammer_wick_reversal_keter_score"] = "crow_outcome_keter_feedback_ledger"
            break
    if crows_score is None:
        for record in load_keter_rescore_after_three_black_crows_records(log_dir=log_dir, limit=100):
            comparison = record.get("comparison_to_hammer") if isinstance(record.get("comparison_to_hammer"), Mapping) else {}
            if comparison.get("three_black_crows_keter_score") is not None:
                crows_score = _to_int(comparison.get("three_black_crows_keter_score"))
                sources["three_black_crows_projected_score"] = "keter_rescore_after_three_black_crows_ledger"
            if hammer_score is None and comparison.get("hammer_keter_score") is not None:
                hammer_score = _to_int(comparison.get("hammer_keter_score"))
                sources["hammer_wick_reversal_keter_score"] = "keter_rescore_after_three_black_crows_ledger"
            if crows_score is not None:
                break
    return {
        "hammer_wick_reversal_keter_score": hammer_score,
        "three_black_crows_projected_score": crows_score,
        "reference_sources": sources,
    }


def _recommended_next_operator_move(rescore_status: str, lane_recommendations: Sequence[Mapping[str, Any]]) -> str:
    if any(row.get("recommended_action") == "INCLUDE_IN_PAPER_MATRIX" for row in lane_recommendations):
        return "RUN_R205_PATTERN_LANE_MATRIX_REVIEW"
    if rescore_status == PATTERN_READY_FOR_PAPER_MATRIX_REVIEW:
        return "RUN_R203_ANCHOR_SIGNAL_CONFLUENCE_MATRIX"
    return "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"


def _recommended_next_engineering_move(rescore_status: str, rankings: Sequence[Mapping[str, Any]]) -> str:
    if rescore_status == PATTERN_READY_FOR_PAPER_MATRIX_REVIEW and rankings:
        return "Build R205 pattern-origin lane matrix review from R204 scorecards; keep it paper-only with no config writes."
    if rescore_status == PATTERN_MIXED_BIAS_REVIEW_REQUIRED:
        return "Deepen outcome samples and isolate high-risk timeframe/mode rows before matrix review."
    return "Rerun R200 and R202 records after more pattern-family paper evidence is collected."


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


def _to_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
