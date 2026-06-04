"""R194 Three Black Crows outcome feedback into Keter scoring.

This module reads recorded R193 outcome mapping evidence and builds a
paper-only Keter feedback projection. It never calls Binance/network, creates
payloads, mutates env/config, promotes origins/lanes, or authorizes live
execution.
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
from src.app.hammer_radar.operator.crow_outcome_mapping_preview import (
    LEDGER_FILENAME as CROW_OUTCOME_MAPPING_LEDGER_FILENAME,
    OUTCOME_MAPPING_AVAILABLE,
    load_crow_outcome_mapping_preview_records,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.keter_rescoring_after_three_black_crows import (
    CROWS_READY_FOR_PAPER_TRACKING_REVIEW,
    LEDGER_FILENAME as KETER_RESCORING_AFTER_CROWS_LEDGER_FILENAME,
    REFERENCE_ORIGIN,
    load_keter_rescore_after_three_black_crows_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY
from src.app.hammer_radar.operator.three_black_crows_detector import (
    DEFAULT_DIRECTION,
    DEFAULT_SYMBOL,
    DEFAULT_TIMEFRAME,
    SIGNAL_ORIGIN,
)

CROW_OUTCOME_KETER_FEEDBACK_READY = "CROW_OUTCOME_KETER_FEEDBACK_READY"
CROW_OUTCOME_KETER_FEEDBACK_REJECTED = "CROW_OUTCOME_KETER_FEEDBACK_REJECTED"
CROW_OUTCOME_KETER_FEEDBACK_RECORDED = "CROW_OUTCOME_KETER_FEEDBACK_RECORDED"
CROW_OUTCOME_KETER_FEEDBACK_BLOCKED = "CROW_OUTCOME_KETER_FEEDBACK_BLOCKED"
CROW_OUTCOME_KETER_FEEDBACK_ERROR = "CROW_OUTCOME_KETER_FEEDBACK_ERROR"

CROW_OUTCOME_SUPPORTS_PAPER_TRACKING = "CROW_OUTCOME_SUPPORTS_PAPER_TRACKING"
CROW_OUTCOME_NEEDS_MORE_SAMPLES = "CROW_OUTCOME_NEEDS_MORE_SAMPLES"
CROW_OUTCOME_WEAK_OR_MIXED = "CROW_OUTCOME_WEAK_OR_MIXED"
CROW_OUTCOME_MAPPING_MISSING = "CROW_OUTCOME_MAPPING_MISSING"
CROW_OUTCOME_NOT_LIVE_AUTHORIZED = "CROW_OUTCOME_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "CROW_OUTCOME_KETER_FEEDBACK"
LEDGER_FILENAME = "crow_outcome_keter_feedback.ndjson"
CONFIRM_CROW_OUTCOME_KETER_FEEDBACK_RECORDING_PHRASE = (
    "I CONFIRM CROW OUTCOME KETER FEEDBACK RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_PREVIOUS_CROW_KETER_SCORE = 56
DEFAULT_HAMMER_KETER_SCORE = 82

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
    f"logs/hammer_radar_forward/{CROW_OUTCOME_MAPPING_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{KETER_RESCORING_AFTER_CROWS_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_crow_outcome_keter_feedback(
    *,
    log_dir: str | Path | None = None,
    record_feedback: bool = False,
    confirm_crow_outcome_keter_feedback: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_crow_outcome_keter_feedback == CONFIRM_CROW_OUTCOME_KETER_FEEDBACK_RECORDING_PHRASE
    try:
        outcome_mapping = load_latest_crow_outcome_mapping(log_dir=resolved_log_dir)
        input_mapping = _build_input_outcome_mapping(outcome_mapping)
        quality = build_crow_outcome_quality_dimensions(input_mapping=input_mapping, outcome_mapping=outcome_mapping)
        feedback_score = compute_crow_outcome_feedback_score(input_mapping=input_mapping, quality_dimensions=quality)
        previous_context = _load_latest_crow_keter_context(log_dir=resolved_log_dir)
        projection = build_updated_crow_keter_projection(
            previous_keter_score=int(previous_context.get("previous_crow_keter_score") or DEFAULT_PREVIOUS_CROW_KETER_SCORE),
            outcome_feedback_score=feedback_score,
        )
        comparison = compare_crow_outcome_to_hammer_reference(
            projected_crow_keter_score=int(projection["projected_keter_score_after_outcome"]),
            hammer_keter_score=int(previous_context.get("hammer_keter_score") or DEFAULT_HAMMER_KETER_SCORE),
        )
        feedback_status = classify_crow_outcome_keter_feedback_status(
            input_mapping=input_mapping,
            quality_dimensions=quality,
            feedback_score=feedback_score,
        )
        recommendations = build_crow_outcome_next_actions(
            input_mapping=input_mapping,
            feedback_status=feedback_status,
        )
        status = _status_for_feedback(
            record_feedback=record_feedback,
            confirmation_valid=confirmation_valid,
            mapping_found=bool(input_mapping["mapping_found"]),
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "feedback_recorded": False,
            "feedback_id": None,
            "record_feedback_requested": bool(record_feedback),
            "confirmation_valid": bool(confirmation_valid),
            "target_context": _target_context(),
            "input_outcome_mapping": input_mapping,
            "outcome_quality_dimensions": quality,
            "crow_outcome_feedback_score": feedback_score,
            "updated_crow_keter_projection": projection,
            "comparison_to_hammer": comparison,
            "feedback_status": feedback_status,
            "recommendations": recommendations,
            "recommended_next_operator_move": _recommended_next_operator_move(feedback_status, recommendations),
            "recommended_next_engineering_move": _recommended_next_engineering_move(feedback_status, recommendations),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "outcome_mapping_source": outcome_mapping.get("mapping_source"),
            "keter_rescore_source": previous_context.get("keter_rescore_source"),
        }
        if record_feedback and confirmation_valid and input_mapping["mapping_found"]:
            record = append_crow_outcome_keter_feedback_record(payload, log_dir=resolved_log_dir)
            payload["status"] = CROW_OUTCOME_KETER_FEEDBACK_RECORDED
            payload["feedback_recorded"] = True
            payload["feedback_id"] = record["feedback_id"]
            payload["ledger_path"] = str(crow_outcome_keter_feedback_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": CROW_OUTCOME_KETER_FEEDBACK_ERROR,
                "generated_at": generated_at.isoformat(),
                "feedback_recorded": False,
                "feedback_id": None,
                "record_feedback_requested": bool(record_feedback),
                "confirmation_valid": bool(confirmation_valid),
                "target_context": _target_context(),
                "input_outcome_mapping": _empty_input_mapping(),
                "outcome_quality_dimensions": _empty_quality_dimensions(),
                "crow_outcome_feedback_score": _empty_feedback_score(),
                "updated_crow_keter_projection": build_updated_crow_keter_projection(
                    previous_keter_score=DEFAULT_PREVIOUS_CROW_KETER_SCORE,
                    outcome_feedback_score=_empty_feedback_score(),
                ),
                "comparison_to_hammer": compare_crow_outcome_to_hammer_reference(
                    projected_crow_keter_score=DEFAULT_PREVIOUS_CROW_KETER_SCORE,
                    hammer_keter_score=DEFAULT_HAMMER_KETER_SCORE,
                ),
                "feedback_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommendations": build_crow_outcome_next_actions(
                    input_mapping=_empty_input_mapping(),
                    feedback_status=UNKNOWN_NEEDS_MANUAL_REVIEW,
                ),
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R194 crow outcome Keter feedback error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_crow_outcome_mapping(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_crow_outcome_mapping_preview_records(log_dir=log_dir, limit=100)
    for record in records:
        target = record.get("target_context") if isinstance(record.get("target_context"), Mapping) else {}
        if target.get("signal_origin") == SIGNAL_ORIGIN and target.get("primary_lane") == DEFAULT_TARGET_LANE_KEY:
            latest = dict(record)
            latest["mapping_source"] = "crow_outcome_mapping_preview_ledger"
            return latest
    return {"mapping_source": "missing"}


def build_crow_outcome_quality_dimensions(
    *,
    input_mapping: Mapping[str, Any],
    outcome_mapping: Mapping[str, Any],
) -> dict[str, Any]:
    aggregate = outcome_mapping.get("aggregate_summary") if isinstance(outcome_mapping.get("aggregate_summary"), Mapping) else {}
    best_window = str(input_mapping.get("best_window") or aggregate.get("best_window") or "unknown")
    stats = (aggregate.get("window_stats") or {}).get(best_window) if isinstance(aggregate.get("window_stats"), Mapping) else {}
    stats = stats if isinstance(stats, Mapping) else {}
    mapped_count = int(input_mapping.get("mapped_count") or stats.get("mapped_count") or 0)
    failure_rate = _to_float(stats.get("simple_failure_rate_pct"), 0.0)
    favorable = _to_float(stats.get("favorable_close_rate_pct"), 0.0)
    success = _to_float(stats.get("simple_success_rate_pct"), 0.0)
    avg_close = _to_float(stats.get("avg_close_return_pct"), 0.0)
    mfe = _to_float(stats.get("avg_mfe_downside_pct"), 0.0)
    mae = _to_float(stats.get("avg_mae_upside_pct"), 0.0)
    risk_warning = _risk_warning(failure_rate=failure_rate, mfe=mfe, mae=mae)
    return {
        "best_window": best_window,
        "favorable_close_rate_pct": _round(favorable),
        "simple_success_rate_pct": _round(success),
        "simple_failure_rate_pct": _round(failure_rate),
        "avg_close_return_pct": _round(avg_close),
        "avg_mfe_downside_pct": _round(mfe),
        "avg_mae_upside_pct": _round(mae),
        "risk_warning": risk_warning,
        "sample_confidence": _sample_confidence(mapped_count=mapped_count),
    }


def compute_crow_outcome_feedback_score(
    *,
    input_mapping: Mapping[str, Any],
    quality_dimensions: Mapping[str, Any],
) -> dict[str, Any]:
    if not input_mapping.get("mapping_found"):
        return _empty_feedback_score()
    favorable = _to_float(quality_dimensions.get("favorable_close_rate_pct"), 0.0)
    success = _to_float(quality_dimensions.get("simple_success_rate_pct"), 0.0)
    failure = _to_float(quality_dimensions.get("simple_failure_rate_pct"), 0.0)
    avg_close = _to_float(quality_dimensions.get("avg_close_return_pct"), 0.0)
    mfe = _to_float(quality_dimensions.get("avg_mfe_downside_pct"), 0.0)
    mae = _to_float(quality_dimensions.get("avg_mae_upside_pct"), 0.0)
    score = 35
    reasons: list[str] = []
    if favorable > 65:
        score += 25
        reasons.append("favorable close rate is above 65%")
    elif favorable >= 50:
        score += 10
        reasons.append("favorable close rate is mixed but above 50%")
    if success > 70:
        score += 25
        reasons.append("simple success rate is above 70%")
    elif success >= 50:
        score += 8
        reasons.append("simple success rate is mixed but above 50%")
    if avg_close < 0:
        score += 15
        reasons.append("average close return is negative for a short setup")
    if mfe > mae:
        score += 15
        reasons.append("average downside MFE exceeds average upside MAE")
    if bool(input_mapping.get("supports_short_bias")):
        score += 10
        reasons.append("R193 interpretation supports short bias")
    if failure >= 85:
        score -= 10
        reasons.append("high simple failure rate keeps risk warning active")
    elif failure >= 70:
        score -= 6
        reasons.append("elevated simple failure rate limits confidence")
    confidence = str(quality_dimensions.get("sample_confidence") or "LOW")
    outcome_score = int(max(0, min(100, round(score))))
    return {
        "outcome_score": outcome_score,
        "score_band": _score_band(outcome_score),
        "confidence": confidence,
        "why": "; ".join(reasons) if reasons else "Outcome mapping is weak, missing, or needs manual review.",
    }


def build_updated_crow_keter_projection(
    *,
    previous_keter_score: int,
    outcome_feedback_score: Mapping[str, Any],
) -> dict[str, Any]:
    previous = int(max(0, min(100, previous_keter_score)))
    outcome_score = int(max(0, min(100, outcome_feedback_score.get("outcome_score") or 0)))
    confidence = str(outcome_feedback_score.get("confidence") or "LOW")
    delta = int(round((outcome_score - 50) * 0.35))
    projected = int(max(0, min(100, previous + delta)))
    if confidence == "LOW":
        projected = min(projected, 69)
    elif confidence == "MEDIUM":
        projected = min(projected, 79)
    return {
        "previous_keter_score": previous,
        "projected_keter_score_after_outcome": projected,
        "projected_readiness": _projected_readiness(projected, confidence),
        "write_scoring_now": False,
        "signal_origin_promoted": False,
        "live_authorized": False,
        "paper_only": True,
    }


def compare_crow_outcome_to_hammer_reference(
    *,
    projected_crow_keter_score: int,
    hammer_keter_score: int,
) -> dict[str, Any]:
    hammer = int(max(0, min(100, hammer_keter_score)))
    crow = int(max(0, min(100, projected_crow_keter_score)))
    hammer_best = hammer >= crow
    why = (
        "hammer_wick_reversal remains ahead after outcome feedback because its Keter score is still higher."
        if hammer_best
        else "three_black_crows projects above hammer on paper evidence only; no promotion or live authorization is created."
    )
    return {
        "hammer_keter_score": hammer,
        "projected_crow_keter_score": crow,
        "hammer_still_best_origin": bool(hammer_best),
        "why": why,
    }


def classify_crow_outcome_keter_feedback_status(
    *,
    input_mapping: Mapping[str, Any],
    quality_dimensions: Mapping[str, Any],
    feedback_score: Mapping[str, Any],
) -> str:
    if not input_mapping.get("mapping_found"):
        return CROW_OUTCOME_MAPPING_MISSING
    if bool(input_mapping.get("live_ready")):
        return CROW_OUTCOME_NOT_LIVE_AUTHORIZED
    if not bool(input_mapping.get("supports_short_bias")):
        return CROW_OUTCOME_WEAK_OR_MIXED
    if int(input_mapping.get("mapped_count") or 0) < 30 or bool(input_mapping.get("needs_more_samples")):
        return CROW_OUTCOME_NEEDS_MORE_SAMPLES
    if int(feedback_score.get("outcome_score") or 0) >= 65 and quality_dimensions.get("sample_confidence") != "LOW":
        return CROW_OUTCOME_SUPPORTS_PAPER_TRACKING
    return CROW_OUTCOME_WEAK_OR_MIXED


def build_crow_outcome_next_actions(
    *,
    input_mapping: Mapping[str, Any],
    feedback_status: str,
) -> dict[str, Any]:
    mapping_found = bool(input_mapping.get("mapping_found"))
    needs_more = bool(input_mapping.get("needs_more_samples")) or int(input_mapping.get("mapped_count") or 0) < 30
    return {
        "rerun_lane_matrix_after_outcome_feedback": mapping_found
        and feedback_status in {CROW_OUTCOME_SUPPORTS_PAPER_TRACKING, CROW_OUTCOME_NEEDS_MORE_SAMPLES},
        "continue_crow_paper_tracking": mapping_found and feedback_status != CROW_OUTCOME_WEAK_OR_MIXED,
        "collect_more_crow_detections": not mapping_found or needs_more,
        "map_crow_to_paper_executions_later": mapping_found,
        "no_live_authorization": True,
    }


def append_crow_outcome_keter_feedback_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = crow_outcome_keter_feedback_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "feedback_id": str(record.get("feedback_id") or f"r194_crow_outcome_keter_feedback_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": CROW_OUTCOME_KETER_FEEDBACK_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_feedback_requested": bool(record.get("record_feedback_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_context": dict(record.get("target_context") or {}),
            "input_outcome_mapping": dict(record.get("input_outcome_mapping") or {}),
            "outcome_quality_dimensions": dict(record.get("outcome_quality_dimensions") or {}),
            "crow_outcome_feedback_score": dict(record.get("crow_outcome_feedback_score") or {}),
            "updated_crow_keter_projection": dict(record.get("updated_crow_keter_projection") or {}),
            "comparison_to_hammer": dict(record.get("comparison_to_hammer") or {}),
            "feedback_status": record.get("feedback_status"),
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


def load_crow_outcome_keter_feedback_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = crow_outcome_keter_feedback_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_crow_outcome_keter_feedback_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    feedback_counts = Counter(str(record.get("feedback_status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    score = latest.get("crow_outcome_feedback_score") if isinstance(latest, Mapping) else {}
    projection = latest.get("updated_crow_keter_projection") if isinstance(latest, Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "feedback_status_counts": dict(sorted(feedback_counts.items())),
        "last_feedback_id": latest.get("feedback_id") if isinstance(latest, Mapping) else None,
        "last_outcome_score": (score or {}).get("outcome_score") if isinstance(score, Mapping) else None,
        "last_projected_crow_keter_score": (projection or {}).get("projected_keter_score_after_outcome")
        if isinstance(projection, Mapping)
        else None,
        "safety": dict(SAFETY),
    }


def crow_outcome_keter_feedback_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_crow_outcome_keter_feedback_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_outcome_mapping(outcome_mapping: Mapping[str, Any]) -> dict[str, Any]:
    aggregate = outcome_mapping.get("aggregate_summary") if isinstance(outcome_mapping.get("aggregate_summary"), Mapping) else {}
    interpretation = outcome_mapping.get("interpretation") if isinstance(outcome_mapping.get("interpretation"), Mapping) else {}
    best_window = str(aggregate.get("best_window") or "unknown")
    return {
        "mapping_found": bool(aggregate),
        "mapped_count": int(aggregate.get("mapped_count") or 0),
        "best_window": best_window,
        "supports_short_bias": bool(interpretation.get("supports_short_bias")),
        "paper_tracking_recommended": bool(interpretation.get("paper_tracking_recommended")),
        "needs_more_samples": bool(interpretation.get("needs_more_samples")),
        "live_ready": False,
    }


def _load_latest_crow_keter_context(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_keter_rescore_after_three_black_crows_records(log_dir=log_dir, limit=100)
    for record in records:
        target = record.get("target_context") if isinstance(record.get("target_context"), Mapping) else {}
        if target.get("signal_origin") != SIGNAL_ORIGIN:
            continue
        rescore = record.get("three_black_crows_rescore") if isinstance(record.get("three_black_crows_rescore"), Mapping) else {}
        comparison = record.get("comparison_to_hammer") if isinstance(record.get("comparison_to_hammer"), Mapping) else {}
        return {
            "previous_crow_keter_score": int(rescore.get("new_keter_score") or DEFAULT_PREVIOUS_CROW_KETER_SCORE),
            "hammer_keter_score": int(comparison.get("hammer_keter_score") or DEFAULT_HAMMER_KETER_SCORE),
            "keter_rescore_source": "keter_rescore_after_three_black_crows_ledger",
        }
    return {
        "previous_crow_keter_score": DEFAULT_PREVIOUS_CROW_KETER_SCORE,
        "hammer_keter_score": DEFAULT_HAMMER_KETER_SCORE,
        "keter_rescore_source": "default_previous_context",
    }


def _status_for_feedback(*, record_feedback: bool, confirmation_valid: bool, mapping_found: bool) -> str:
    if record_feedback and not confirmation_valid:
        return CROW_OUTCOME_KETER_FEEDBACK_REJECTED
    if not mapping_found:
        return CROW_OUTCOME_KETER_FEEDBACK_BLOCKED
    if record_feedback and confirmation_valid:
        return CROW_OUTCOME_KETER_FEEDBACK_RECORDED
    return CROW_OUTCOME_KETER_FEEDBACK_READY


def _target_context() -> dict[str, Any]:
    return {
        "signal_origin": SIGNAL_ORIGIN,
        "primary_lane": DEFAULT_TARGET_LANE_KEY,
        "symbol": DEFAULT_SYMBOL,
        "timeframe": DEFAULT_TIMEFRAME,
        "direction": DEFAULT_DIRECTION,
    }


def _risk_warning(*, failure_rate: float, mfe: float, mae: float) -> str:
    if failure_rate >= 85:
        return "HIGH_SIMPLE_FAILURE_RATE_REVIEW_REQUIRED"
    if failure_rate >= 70:
        return "ELEVATED_SIMPLE_FAILURE_RATE"
    if mae > mfe:
        return "ADVERSE_MAE_EXCEEDS_DOWNSIDE_MFE"
    return "NONE"


def _sample_confidence(*, mapped_count: int) -> str:
    if mapped_count < 30:
        return "LOW"
    if mapped_count < 75:
        return "MEDIUM"
    return "HIGH"


def _score_band(score: int) -> str:
    if score <= 39:
        return "weak or missing outcome evidence"
    if score <= 64:
        return "mixed paper outcome evidence"
    if score <= 79:
        return "supportive paper outcome evidence"
    return "strong paper outcome evidence"


def _projected_readiness(projected_score: int, confidence: str) -> str:
    if confidence == "LOW":
        return CROW_OUTCOME_NEEDS_MORE_SAMPLES
    if projected_score >= 70:
        return CROWS_READY_FOR_PAPER_TRACKING_REVIEW
    return CROW_OUTCOME_WEAK_OR_MIXED


def _recommended_next_operator_move(feedback_status: str, recommendations: Mapping[str, Any]) -> str:
    if recommendations.get("rerun_lane_matrix_after_outcome_feedback"):
        return "RUN_R195_LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK"
    if feedback_status == CROW_OUTCOME_MAPPING_MISSING:
        return "KEEP_8M_SHORT_WATCHER_RUNNING"
    return "KEEP_MULTI_LANE_HARVESTER_RUNNING"


def _recommended_next_engineering_move(feedback_status: str, recommendations: Mapping[str, Any]) -> str:
    if recommendations.get("rerun_lane_matrix_after_outcome_feedback"):
        return "Build R195 lane matrix after crow outcome feedback; compare hammer vs crows without config writes, Binance calls, or promotion."
    if feedback_status == CROW_OUTCOME_MAPPING_MISSING:
        return "Record R193 crow outcome mapping before feeding outcome behavior into Keter."
    return "Keep collecting crow detections and paper outcomes before any scoring-config or promotion review."


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


def _empty_input_mapping() -> dict[str, Any]:
    return {
        "mapping_found": False,
        "mapped_count": 0,
        "best_window": "unknown",
        "supports_short_bias": False,
        "paper_tracking_recommended": False,
        "needs_more_samples": True,
        "live_ready": False,
    }


def _empty_quality_dimensions() -> dict[str, Any]:
    return {
        "best_window": "unknown",
        "favorable_close_rate_pct": 0.0,
        "simple_success_rate_pct": 0.0,
        "simple_failure_rate_pct": 0.0,
        "avg_close_return_pct": 0.0,
        "avg_mfe_downside_pct": 0.0,
        "avg_mae_upside_pct": 0.0,
        "risk_warning": "MAPPING_MISSING",
        "sample_confidence": "LOW",
    }


def _empty_feedback_score() -> dict[str, Any]:
    return {
        "outcome_score": 0,
        "score_band": _score_band(0),
        "confidence": "LOW",
        "why": "R193 outcome mapping is missing.",
    }


def _to_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
