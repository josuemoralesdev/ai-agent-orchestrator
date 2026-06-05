"""R205 paper-only pattern-origin lane matrix review.

This module composes R204 pattern Keter scores, R198 full-spectrum lane scope,
and R192/R195 lane-matrix reference evidence. It is audit-only: no Binance or
network calls, no order payloads, no config/env mutation, and no promotions.
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
from src.app.hammer_radar.operator.full_spectrum_harvester_expansion import (
    build_full_spectrum_lane_candidates,
)
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE, normalize_lane_key
from src.app.hammer_radar.operator.lane_matrix_after_crow_outcome_feedback import (
    DEFAULT_HAMMER_KETER_SCORE,
    DEFAULT_PROJECTED_CROW_KETER_SCORE,
    build_lane_matrix_after_crow_outcome_feedback,
    load_lane_matrix_after_crow_outcome_feedback_records,
)
from src.app.hammer_radar.operator.lane_matrix_after_crow_rescoring import (
    build_lane_matrix_after_crow_rescoring,
    load_lane_matrix_after_crow_rescoring_records,
)
from src.app.hammer_radar.operator.pattern_detector_family_expansion import (
    DEFAULT_SYMBOL,
    REGISTRY_ONLY_PATTERNS,
)
from src.app.hammer_radar.operator.pattern_keter_rescoring_family import (
    build_pattern_keter_rescoring_family,
    load_pattern_keter_rescoring_family_records,
)
from src.app.hammer_radar.operator.pattern_outcome_mapping_family import (
    load_pattern_outcome_mapping_family_records,
)
from src.app.hammer_radar.operator.signal_origin_lane_matrix import (
    build_signal_origin_lane_matrix,
    load_signal_origin_lane_matrix_records,
)
from src.app.hammer_radar.operator.short_strategy_packet import TARGET_ENTRY_MODE

PATTERN_LANE_MATRIX_REVIEW_READY = "PATTERN_LANE_MATRIX_REVIEW_READY"
PATTERN_LANE_MATRIX_REVIEW_REJECTED = "PATTERN_LANE_MATRIX_REVIEW_REJECTED"
PATTERN_LANE_MATRIX_REVIEW_RECORDED = "PATTERN_LANE_MATRIX_REVIEW_RECORDED"
PATTERN_LANE_MATRIX_REVIEW_BLOCKED = "PATTERN_LANE_MATRIX_REVIEW_BLOCKED"
PATTERN_LANE_MATRIX_REVIEW_ERROR = "PATTERN_LANE_MATRIX_REVIEW_ERROR"

PATTERN_PAIR_READY_FOR_PAPER_TRACKING = "PATTERN_PAIR_READY_FOR_PAPER_TRACKING"
PATTERN_PAIR_NEEDS_MORE_FRESH_FLOW = "PATTERN_PAIR_NEEDS_MORE_FRESH_FLOW"
PATTERN_PAIR_MIXED_BIAS_REVIEW_REQUIRED = "PATTERN_PAIR_MIXED_BIAS_REVIEW_REQUIRED"
PATTERN_PAIR_REGISTRY_ONLY_BLOCKED = "PATTERN_PAIR_REGISTRY_ONLY_BLOCKED"
PATTERN_PAIR_NOT_LIVE_AUTHORIZED = "PATTERN_PAIR_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

HAMMER_REMAINS_TOP_PATTERN_REFERENCE = "HAMMER_REMAINS_TOP_PATTERN_REFERENCE"
BEARISH_ENGULFING_READY_FOR_PAPER_MATRIX = "BEARISH_ENGULFING_READY_FOR_PAPER_MATRIX"
CROWS_AND_ENGULFING_BOTH_PAPER_CANDIDATES = "CROWS_AND_ENGULFING_BOTH_PAPER_CANDIDATES"
PATTERN_FAMILY_NEEDS_MORE_FLOW = "PATTERN_FAMILY_NEEDS_MORE_FLOW"
PATTERN_MATRIX_NOT_LIVE_AUTHORIZED = "PATTERN_MATRIX_NOT_LIVE_AUTHORIZED"

EVENT_TYPE = "PATTERN_LANE_MATRIX_REVIEW"
LEDGER_FILENAME = "pattern_lane_matrix_review.ndjson"
CONFIRM_PATTERN_LANE_MATRIX_REVIEW_RECORDING_PHRASE = (
    "I CONFIRM PATTERN LANE MATRIX REVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

PRIMARY_ORIGINS = ("hammer_wick_reversal", "three_black_crows", "bearish_engulfing")
SECONDARY_REVIEW_ORIGINS = ("exhaustion_wick", "bullish_engulfing", "three_white_soldiers")
ORIGINS_CONSIDERED = (*PRIMARY_ORIGINS, *SECONDARY_REVIEW_ORIGINS)
BLOCKED_ORIGINS = ("breakdown_retest", "breakout_retest")
DEFAULT_CONFIGURED_LANES = (
    "BTCUSDT|4m|long|ladder_close_50_618",
    "BTCUSDT|4m|short|ladder_close_50_618",
    "BTCUSDT|8m|long|ladder_close_50_618",
    "BTCUSDT|8m|short|ladder_close_50_618",
    "BTCUSDT|13m|short|ladder_close_50_618",
    "BTCUSDT|44m|short|ladder_close_50_618",
)
DEFAULT_DISCOVERED_LANES = tuple(
    normalize_lane_key(DEFAULT_SYMBOL, timeframe, direction, TARGET_ENTRY_MODE)
    for timeframe in ("22m", "55m", "88m", "222m", "444m", "666m", "888m", "4H", "13H", "13D")
    for direction in ("long", "short")
)
FRESH_CONFIGURED_REFERENCE_LANES = {
    "BTCUSDT|8m|long|ladder_close_50_618",
    "BTCUSDT|8m|short|ladder_close_50_618",
    "BTCUSDT|4m|short|ladder_close_50_618",
}

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
    "logs/hammer_radar_forward/pattern_keter_rescoring_family.ndjson",
    "logs/hammer_radar_forward/pattern_outcome_mapping_family.ndjson",
    "logs/hammer_radar_forward/lane_matrix_after_crow_outcome_feedback.ndjson",
    "logs/hammer_radar_forward/lane_matrix_after_crow_rescoring.ndjson",
    "logs/hammer_radar_forward/signal_origin_lane_matrix.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_pattern_lane_matrix_review(
    *,
    log_dir: str | Path | None = None,
    record_matrix: bool = False,
    confirm_pattern_lane_matrix: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_pattern_lane_matrix == CONFIRM_PATTERN_LANE_MATRIX_REVIEW_RECORDING_PHRASE
    try:
        pattern_keter = load_latest_pattern_keter_rescoring(log_dir=resolved_log_dir, now=generated_at)
        scope = load_latest_full_spectrum_harvester_scope(
            log_dir=resolved_log_dir,
            config_path=config_path,
        )
        lane_reference = load_latest_lane_matrix_reference(log_dir=resolved_log_dir, now=generated_at)
        outcome_mapping = _load_latest_pattern_outcome(log_dir=resolved_log_dir)
        candidates = build_pattern_lane_candidates(scope=scope, lane_reference=lane_reference)
        matrix = build_pattern_lane_pair_matrix(
            lane_candidates=candidates,
            pattern_keter=pattern_keter,
            lane_reference=lane_reference,
            outcome_mapping=outcome_mapping,
        )
        current_best = build_current_best_pattern_pairs(matrix)
        comparison = build_pattern_vs_reference_comparison(
            pattern_keter=pattern_keter,
            current_best_pattern_pairs=current_best,
        )
        recommendations = build_pattern_lane_tracking_recommendations(matrix)
        blockers = build_remaining_pattern_matrix_blockers(
            pattern_keter=pattern_keter,
            full_spectrum_scope=scope,
            lane_reference=lane_reference,
            pattern_lane_pair_matrix=matrix,
        )
        matrix_status = classify_pattern_lane_matrix_status(
            pattern_lane_pair_matrix=matrix,
            pattern_vs_reference_comparison=comparison,
        )
        status = _status_for_review(
            record_matrix=record_matrix,
            confirmation_valid=confirmation_valid,
            matrix_status=matrix_status,
            has_pairs=bool(matrix),
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "matrix_recorded": False,
            "matrix_id": None,
            "record_matrix_requested": bool(record_matrix),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "symbol": DEFAULT_SYMBOL,
                "lanes_considered": len(candidates),
                "origins_considered": list(ORIGINS_CONSIDERED),
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "pattern_keter_found": bool(pattern_keter),
                "full_spectrum_scope_found": bool(scope),
                "lane_reference_found": bool(lane_reference),
                "configured_lanes": [row["lane_key"] for row in candidates if row.get("configured_lane")],
                "discovered_unconfigured_lanes": [
                    row["lane_key"] for row in candidates if row.get("lane_mode") == "paper_discovered_unconfigured"
                ],
                "blocked_origins": list(BLOCKED_ORIGINS),
            },
            "pattern_lane_pair_matrix": matrix,
            "current_best_pattern_pairs": current_best,
            "pattern_vs_reference_comparison": comparison,
            "pattern_lane_tracking_recommendations": recommendations,
            "remaining_pattern_matrix_blockers": blockers,
            "matrix_status": matrix_status,
            "recommended_next_operator_move": _recommended_next_operator_move(matrix_status, blockers),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix_status, current_best),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "pattern_keter_source": pattern_keter.get("rescore_source"),
            "full_spectrum_scope_source": scope.get("scope_source"),
            "lane_reference_source": lane_reference.get("matrix_source"),
        }
        if record_matrix and confirmation_valid and matrix:
            record = append_pattern_lane_matrix_review_record(payload, log_dir=resolved_log_dir)
            payload["status"] = PATTERN_LANE_MATRIX_REVIEW_RECORDED
            payload["matrix_recorded"] = True
            payload["matrix_id"] = record["matrix_id"]
            payload["ledger_path"] = str(pattern_lane_matrix_review_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": PATTERN_LANE_MATRIX_REVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "matrix_recorded": False,
                "matrix_id": None,
                "record_matrix_requested": bool(record_matrix),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "symbol": DEFAULT_SYMBOL,
                    "lanes_considered": 0,
                    "origins_considered": list(ORIGINS_CONSIDERED),
                    "paper_only": True,
                    "live_authorized": False,
                },
                "input_summary": {
                    "pattern_keter_found": False,
                    "full_spectrum_scope_found": False,
                    "lane_reference_found": False,
                    "configured_lanes": [],
                    "discovered_unconfigured_lanes": [],
                    "blocked_origins": list(BLOCKED_ORIGINS),
                },
                "pattern_lane_pair_matrix": [],
                "current_best_pattern_pairs": [],
                "pattern_vs_reference_comparison": _unknown_reference_comparison(),
                "pattern_lane_tracking_recommendations": [],
                "remaining_pattern_matrix_blockers": ["manual review required after R205 build error"],
                "matrix_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R205 pattern lane matrix review error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_pattern_keter_rescoring(
    *,
    log_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    records = load_pattern_keter_rescoring_family_records(log_dir=log_dir, limit=100)
    if records:
        latest = dict(records[0])
        latest["rescore_source"] = "pattern_keter_rescoring_family_ledger"
        return latest
    preview = build_pattern_keter_rescoring_family(log_dir=log_dir, record_rescore=False, now=now)
    preview["rescore_source"] = "pattern_keter_rescoring_family_preview"
    return preview


def load_latest_full_spectrum_harvester_scope(
    *,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    scope = build_full_spectrum_lane_candidates(
        log_dir=log_dir,
        config_path=Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH,
    )
    scope["scope_source"] = "full_spectrum_lane_candidates_preview"
    return scope


def load_latest_lane_matrix_reference(
    *,
    log_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    records = load_lane_matrix_after_crow_outcome_feedback_records(log_dir=log_dir, limit=100)
    if records:
        latest = dict(records[0])
        latest["matrix_source"] = "lane_matrix_after_crow_outcome_feedback_ledger"
        return latest
    records = load_lane_matrix_after_crow_rescoring_records(log_dir=log_dir, limit=100)
    if records:
        latest = dict(records[0])
        latest["matrix_source"] = "lane_matrix_after_crow_rescoring_ledger"
        return latest
    records = load_signal_origin_lane_matrix_records(log_dir=log_dir, limit=100)
    if records:
        latest = dict(records[0])
        latest["matrix_source"] = "signal_origin_lane_matrix_ledger"
        return latest
    preview = build_signal_origin_lane_matrix(log_dir=log_dir, record_matrix=False, now=now)
    if not preview.get("lane_origin_matrix"):
        preview = build_lane_matrix_after_crow_outcome_feedback(log_dir=log_dir, record_matrix=False, now=now)
    if not preview.get("post_outcome_pair_comparison"):
        preview = build_lane_matrix_after_crow_rescoring(log_dir=log_dir, record_matrix=False, now=now)
    preview["matrix_source"] = "lane_matrix_reference_preview"
    return preview


def build_pattern_lane_candidates(
    *,
    scope: Mapping[str, Any],
    lane_reference: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for row in scope.get("configured_paper_lanes") or []:
        if isinstance(row, Mapping):
            lane = _lane_candidate_from_scope_row(row, configured=True)
            candidates[lane["lane_key"]] = lane
    for lane_key in DEFAULT_CONFIGURED_LANES:
        candidates.setdefault(lane_key, _lane_candidate_from_key(lane_key, "paper", configured=True))
    for row in scope.get("discovered_unconfigured_paper_lanes") or []:
        if isinstance(row, Mapping):
            lane = _lane_candidate_from_scope_row(row, configured=False)
            candidates.setdefault(lane["lane_key"], lane)
    for lane_key in DEFAULT_DISCOVERED_LANES:
        candidates.setdefault(lane_key, _lane_candidate_from_key(lane_key, "paper_discovered_unconfigured", configured=False))
    reference_scores = _lane_scores_from_reference(lane_reference or {})
    for lane_key, lane in candidates.items():
        lane["lane_score"] = reference_scores.get(lane_key, lane.get("lane_score", 55 if lane.get("configured_lane") else 42))
        if lane_key in reference_scores:
            lane["lane_reference_found"] = True
    return sorted(candidates.values(), key=lambda row: _lane_sort_key(str(row["lane_key"])))


def score_pattern_lane_pair(
    *,
    lane: Mapping[str, Any],
    signal_origin: str,
    pattern_card: Mapping[str, Any],
    lane_reference: Mapping[str, Any] | None = None,
    outcome_mapping: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    lane_key = str(lane.get("lane_key") or "")
    direction = str(lane.get("direction") or _lane_parts(lane_key)["direction"])
    timeframe = str(lane.get("timeframe") or _lane_parts(lane_key)["timeframe"])
    lane_mode = str(lane.get("lane_mode") or lane.get("mode") or "paper")
    configured = bool(lane.get("configured_lane"))
    blocked = signal_origin in REGISTRY_ONLY_PATTERNS or signal_origin in BLOCKED_ORIGINS
    origin_score = _origin_keter_score(signal_origin, pattern_card=pattern_card, lane_reference=lane_reference or {})
    lane_score = _bounded_int(lane.get("lane_score"), 0, 100, 55 if configured else 42)
    mapped_count = _mapped_count(signal_origin, pattern_card=pattern_card, outcome_mapping=outcome_mapping or {})
    outcome_score = min(100, mapped_count)
    fresh_flow_status = _fresh_flow_status(lane_key=lane_key, lane=lane, lane_reference=lane_reference or {})
    fresh_score = {"fresh": 100, "stale_only": 25, "unknown": 45}.get(fresh_flow_status, 45)
    alignment_score = _direction_alignment_score(signal_origin=signal_origin, lane_direction=direction)
    raw_score = int(round(origin_score * 0.35 + lane_score * 0.25 + fresh_score * 0.15 + outcome_score * 0.15 + alignment_score * 0.10))
    risk_warnings = list(pattern_card.get("risk_warnings") or [])
    if blocked:
        risk_warnings.append("registry_only_blocked")
    if fresh_flow_status == "stale_only":
        raw_score -= 15
        risk_warnings.append("stale_only_flow")
    if lane_mode == "paper_discovered_unconfigured" or not configured:
        raw_score -= 8
        risk_warnings.append("discovered_unconfigured_lane_caution")
    if _direction_alignment(signal_origin=signal_origin, lane_direction=direction) == "misaligned":
        raw_score -= 18
        risk_warnings.append("direction_mismatch")
    if _mixed_bias_required(signal_origin=signal_origin, pattern_card=pattern_card):
        raw_score -= 10
        risk_warnings.append("mixed_bias_review_required")
    if blocked:
        raw_score = min(raw_score - 35, 24)
    pair_score = max(0, min(100, raw_score))
    pair_readiness = _pair_readiness(
        signal_origin=signal_origin,
        pair_score=pair_score,
        fresh_flow_status=fresh_flow_status,
        alignment_score=alignment_score,
        blocked=blocked,
        mixed_bias=_mixed_bias_required(signal_origin=signal_origin, pattern_card=pattern_card),
    )
    return _sanitize(
        {
            "lane_key": lane_key,
            "signal_origin": signal_origin,
            "direction": direction,
            "timeframe": timeframe,
            "lane_mode": lane_mode,
            "origin_keter_score": origin_score,
            "lane_score": lane_score,
            "pair_score": pair_score,
            "pair_readiness": pair_readiness,
            "fresh_flow_status": fresh_flow_status,
            "configured_lane": configured,
            "mapped_count": mapped_count,
            "risk_warnings": _dedupe(risk_warnings),
            "paper_only": True,
            "live_authorized": False,
            "signal_origin_promoted": False,
            "lane_promoted": False,
            "why": _pair_why(
                lane_key=lane_key,
                signal_origin=signal_origin,
                pair_score=pair_score,
                pair_readiness=pair_readiness,
                fresh_flow_status=fresh_flow_status,
                alignment=_direction_alignment(signal_origin=signal_origin, lane_direction=direction),
                lane_mode=lane_mode,
            ),
        }
    )


def build_pattern_lane_pair_matrix(
    *,
    lane_candidates: Sequence[Mapping[str, Any]],
    pattern_keter: Mapping[str, Any],
    lane_reference: Mapping[str, Any],
    outcome_mapping: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    scorecards = _scorecards_with_references(pattern_keter=pattern_keter, lane_reference=lane_reference)
    rows = []
    for lane in lane_candidates:
        for origin in ORIGINS_CONSIDERED:
            rows.append(
                score_pattern_lane_pair(
                    lane=lane,
                    signal_origin=origin,
                    pattern_card=scorecards.get(origin, {}),
                    lane_reference=lane_reference,
                    outcome_mapping=outcome_mapping,
                )
            )
    rows.sort(
        key=lambda row: (
            -int(row.get("pair_score") or 0),
            str(row.get("pair_readiness") or "") != PATTERN_PAIR_READY_FOR_PAPER_TRACKING,
            str(row.get("lane_mode") or "") == "paper_discovered_unconfigured",
            str(row.get("lane_key") or ""),
            str(row.get("signal_origin") or ""),
        )
    )
    return rows


def build_current_best_pattern_pairs(pattern_lane_pair_matrix: Sequence[Mapping[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    candidates = [
        row
        for row in pattern_lane_pair_matrix
        if row.get("pair_readiness")
        in {
            PATTERN_PAIR_READY_FOR_PAPER_TRACKING,
            PATTERN_PAIR_NEEDS_MORE_FRESH_FLOW,
            PATTERN_PAIR_MIXED_BIAS_REVIEW_REQUIRED,
            PATTERN_PAIR_NOT_LIVE_AUTHORIZED,
        }
    ]
    best = sorted(
        candidates,
        key=lambda row: (
            -int(row.get("pair_score") or 0),
            str(row.get("pair_readiness") or "") != PATTERN_PAIR_READY_FOR_PAPER_TRACKING,
            str(row.get("lane_key") or ""),
            str(row.get("signal_origin") or ""),
        ),
    )[:limit]
    return [
        {
            "rank": index,
            "lane_key": row.get("lane_key"),
            "signal_origin": row.get("signal_origin"),
            "pair_score": row.get("pair_score"),
            "pair_readiness": row.get("pair_readiness"),
            "why": row.get("why"),
        }
        for index, row in enumerate(best, start=1)
    ]


def build_pattern_vs_reference_comparison(
    *,
    pattern_keter: Mapping[str, Any],
    current_best_pattern_pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    reference = pattern_keter.get("reference_comparison") if isinstance(pattern_keter.get("reference_comparison"), Mapping) else {}
    hammer_score = _bounded_int(
        reference.get("hammer_wick_reversal_keter_score") or reference.get("hammer_reference_score"),
        0,
        100,
        DEFAULT_HAMMER_KETER_SCORE,
    )
    crows_score = _bounded_int(
        reference.get("three_black_crows_projected_score") or reference.get("three_black_crows_reference_score"),
        0,
        100,
        DEFAULT_PROJECTED_CROW_KETER_SCORE,
    )
    non_hammer = [row for row in current_best_pattern_pairs if row.get("signal_origin") != "hammer_wick_reversal"]
    top = non_hammer[0] if non_hammer else (current_best_pattern_pairs[0] if current_best_pattern_pairs else {})
    top_origin = top.get("signal_origin")
    top_pair_score = top.get("pair_score")
    top_origin_score = _origin_score_from_r204(pattern_keter, str(top_origin or ""), default=0)
    bearish_score = _origin_score_from_r204(pattern_keter, "bearish_engulfing", default=0)
    return {
        "hammer_reference_score": hammer_score,
        "three_black_crows_reference_score": crows_score,
        "top_pattern_origin": top_origin,
        "top_pattern_pair_score": top_pair_score,
        "hammer_still_best_reference": None if top_origin is None else hammer_score >= int(top_origin_score or 0),
        "bearish_engulfing_beats_crows": bearish_score > crows_score,
        "why": (
            "Pattern pair scores are paper-matrix evidence only; hammer remains the top Keter reference unless a pattern origin score exceeds 82."
        ),
    }


def build_pattern_lane_tracking_recommendations(pattern_lane_pair_matrix: Sequence[Mapping[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    recommendations = []
    seen: set[tuple[str, str]] = set()
    for row in pattern_lane_pair_matrix:
        key = (str(row.get("lane_key") or ""), str(row.get("signal_origin") or ""))
        if key in seen:
            continue
        seen.add(key)
        readiness = str(row.get("pair_readiness") or UNKNOWN_NEEDS_MANUAL_REVIEW)
        if readiness == PATTERN_PAIR_READY_FOR_PAPER_TRACKING:
            action, priority = "TRACK_PAPER", "HIGH" if int(row.get("pair_score") or 0) >= 70 else "MEDIUM"
        elif readiness == PATTERN_PAIR_NEEDS_MORE_FRESH_FLOW:
            action, priority = "COLLECT_FRESH_FLOW", "MEDIUM"
        elif readiness == PATTERN_PAIR_REGISTRY_ONLY_BLOCKED:
            action, priority = "KEEP_BLOCKED", "LOW"
        else:
            action, priority = "KEEP_REVIEW_ONLY", "MEDIUM"
        recommendations.append(
            {
                "lane_key": row.get("lane_key"),
                "signal_origin": row.get("signal_origin"),
                "recommended_action": action,
                "priority": priority,
                "why": row.get("why"),
            }
        )
        if len(recommendations) >= limit:
            break
    return recommendations


def build_remaining_pattern_matrix_blockers(
    *,
    pattern_keter: Mapping[str, Any],
    full_spectrum_scope: Mapping[str, Any],
    lane_reference: Mapping[str, Any],
    pattern_lane_pair_matrix: Sequence[Mapping[str, Any]],
) -> list[str]:
    blockers = []
    if not pattern_keter:
        blockers.append("R204 pattern Keter rescoring not found")
    if not full_spectrum_scope:
        blockers.append("R198 full-spectrum lane scope not found")
    if not lane_reference:
        blockers.append("R195/R192 lane matrix reference not found")
    if not any(row.get("pair_readiness") == PATTERN_PAIR_READY_FOR_PAPER_TRACKING for row in pattern_lane_pair_matrix):
        blockers.append("no pattern lane pair is ready for paper tracking")
    if any(row.get("fresh_flow_status") == "stale_only" for row in pattern_lane_pair_matrix):
        blockers.append("some lane pairs remain stale-only")
    blockers.append("no live authorization")
    blockers.append("config writes remain forbidden")
    blockers.append("retest origins remain registry-only blocked")
    return _dedupe(blockers)


def classify_pattern_lane_matrix_status(
    *,
    pattern_lane_pair_matrix: Sequence[Mapping[str, Any]],
    pattern_vs_reference_comparison: Mapping[str, Any],
) -> str:
    if not pattern_lane_pair_matrix:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    ready_origins = {
        str(row.get("signal_origin") or "")
        for row in pattern_lane_pair_matrix
        if row.get("pair_readiness") == PATTERN_PAIR_READY_FOR_PAPER_TRACKING
    }
    if "bearish_engulfing" in ready_origins and "three_black_crows" in ready_origins:
        return CROWS_AND_ENGULFING_BOTH_PAPER_CANDIDATES
    if "bearish_engulfing" in ready_origins:
        return BEARISH_ENGULFING_READY_FOR_PAPER_MATRIX
    if pattern_vs_reference_comparison.get("hammer_still_best_reference") is True:
        return HAMMER_REMAINS_TOP_PATTERN_REFERENCE
    if ready_origins:
        return PATTERN_MATRIX_NOT_LIVE_AUTHORIZED
    return PATTERN_FAMILY_NEEDS_MORE_FLOW


def append_pattern_lane_matrix_review_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = pattern_lane_matrix_review_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "matrix_id": str(record.get("matrix_id") or f"r205_pattern_lane_matrix_review_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": PATTERN_LANE_MATRIX_REVIEW_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_matrix_requested": bool(record.get("record_matrix_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "pattern_lane_pair_matrix": list(record.get("pattern_lane_pair_matrix") or []),
            "current_best_pattern_pairs": list(record.get("current_best_pattern_pairs") or []),
            "pattern_vs_reference_comparison": dict(record.get("pattern_vs_reference_comparison") or {}),
            "pattern_lane_tracking_recommendations": list(record.get("pattern_lane_tracking_recommendations") or []),
            "remaining_pattern_matrix_blockers": list(record.get("remaining_pattern_matrix_blockers") or []),
            "matrix_status": record.get("matrix_status"),
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


def load_pattern_lane_matrix_review_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = pattern_lane_matrix_review_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_pattern_lane_matrix_review_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    best = latest.get("current_best_pattern_pairs") if isinstance(latest.get("current_best_pattern_pairs"), list) else []
    top = best[0] if best and isinstance(best[0], Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_matrix_id": latest.get("matrix_id") if isinstance(latest, Mapping) else None,
        "last_top_lane": top.get("lane_key"),
        "last_top_origin": top.get("signal_origin"),
        "last_matrix_status": latest.get("matrix_status") if isinstance(latest, Mapping) else None,
        "safety": dict(SAFETY),
    }


def pattern_lane_matrix_review_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_pattern_lane_matrix_review_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _load_latest_pattern_outcome(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_pattern_outcome_mapping_family_records(log_dir=log_dir, limit=100)
    for record in records:
        if isinstance(record.get("origin_outcome_summary"), Mapping):
            return dict(record)
    return {}


def _scorecards_with_references(*, pattern_keter: Mapping[str, Any], lane_reference: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    cards = {
        str(origin): dict(card)
        for origin, card in (pattern_keter.get("pattern_origin_scorecards") or {}).items()
        if isinstance(card, Mapping)
    }
    cards.setdefault(
        "hammer_wick_reversal",
        {
            "signal_origin": "hammer_wick_reversal",
            "keter_score": _origin_keter_score("hammer_wick_reversal", pattern_card={}, lane_reference=lane_reference),
            "readiness": PATTERN_PAIR_READY_FOR_PAPER_TRACKING,
            "mapped_count": 116,
            "supports_directional_bias": True,
            "risk_warnings": [],
        },
    )
    cards.setdefault(
        "three_black_crows",
        {
            "signal_origin": "three_black_crows",
            "keter_score": _origin_keter_score("three_black_crows", pattern_card={}, lane_reference=lane_reference),
            "readiness": PATTERN_PAIR_READY_FOR_PAPER_TRACKING,
            "mapped_count": _mapped_count("three_black_crows", pattern_card={}, outcome_mapping={}),
            "supports_directional_bias": True,
            "risk_warnings": [],
        },
    )
    for origin in BLOCKED_ORIGINS:
        cards.setdefault(origin, {"signal_origin": origin, "keter_score": 0, "mapped_count": 0, "risk_warnings": ["registry_only_blocked"]})
    return cards


def _origin_keter_score(signal_origin: str, *, pattern_card: Mapping[str, Any], lane_reference: Mapping[str, Any]) -> int:
    if pattern_card.get("keter_score") is not None:
        return _bounded_int(pattern_card.get("keter_score"), 0, 100, 0)
    if signal_origin == "hammer_wick_reversal":
        return _reference_score(lane_reference, "hammer_wick_reversal", DEFAULT_HAMMER_KETER_SCORE)
    if signal_origin == "three_black_crows":
        return _reference_score(lane_reference, "three_black_crows", DEFAULT_PROJECTED_CROW_KETER_SCORE)
    return 0


def _origin_score_from_r204(pattern_keter: Mapping[str, Any], origin: str, *, default: int) -> int:
    cards = pattern_keter.get("pattern_origin_scorecards") if isinstance(pattern_keter.get("pattern_origin_scorecards"), Mapping) else {}
    card = cards.get(origin) if isinstance(cards.get(origin), Mapping) else {}
    if card.get("keter_score") is not None:
        return _bounded_int(card.get("keter_score"), 0, 100, default)
    if origin == "hammer_wick_reversal":
        return DEFAULT_HAMMER_KETER_SCORE
    if origin == "three_black_crows":
        return DEFAULT_PROJECTED_CROW_KETER_SCORE
    return default


def _mapped_count(signal_origin: str, *, pattern_card: Mapping[str, Any], outcome_mapping: Mapping[str, Any]) -> int:
    if pattern_card.get("mapped_count") is not None:
        return _bounded_int(pattern_card.get("mapped_count"), 0, 1_000_000, 0)
    summaries = outcome_mapping.get("origin_outcome_summary") if isinstance(outcome_mapping.get("origin_outcome_summary"), Mapping) else {}
    summary = summaries.get(signal_origin) if isinstance(summaries.get(signal_origin), Mapping) else {}
    if summary.get("mapped_count") is not None:
        return _bounded_int(summary.get("mapped_count"), 0, 1_000_000, 0)
    if signal_origin == "hammer_wick_reversal":
        return 116
    if signal_origin == "three_black_crows":
        return 23
    return 0


def _reference_score(lane_reference: Mapping[str, Any], origin: str, default: int) -> int:
    pair = _reference_pair(lane_reference, origin)
    if pair.get("origin_keter_score") is not None:
        return _bounded_int(pair.get("origin_keter_score"), 0, 100, default)
    if origin == "three_black_crows" and pair.get("projected_keter_score_after_outcome") is not None:
        return _bounded_int(pair.get("projected_keter_score_after_outcome"), 0, 100, default)
    comparison = lane_reference.get("pattern_vs_reference_comparison") or lane_reference.get("reference_comparison") or {}
    if isinstance(comparison, Mapping):
        key = "hammer_reference_score" if origin == "hammer_wick_reversal" else "three_black_crows_reference_score"
        if comparison.get(key) is not None:
            return _bounded_int(comparison.get(key), 0, 100, default)
    return default


def _reference_pair(lane_reference: Mapping[str, Any], origin: str) -> dict[str, Any]:
    for key in ("post_outcome_pair_comparison", "pair_comparison"):
        pairs = lane_reference.get(key) if isinstance(lane_reference.get(key), Mapping) else {}
        pair = pairs.get(origin) if isinstance(pairs.get(origin), Mapping) else {}
        if pair:
            return dict(pair)
    rows = lane_reference.get("lane_origin_matrix") if isinstance(lane_reference.get("lane_origin_matrix"), list) else []
    matching = [row for row in rows if isinstance(row, Mapping) and row.get("signal_origin") == origin]
    if matching:
        return dict(sorted(matching, key=lambda row: -int(row.get("pair_score") or 0))[0])
    return {}


def _lane_scores_from_reference(lane_reference: Mapping[str, Any]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for key in ("post_outcome_pair_comparison", "pair_comparison"):
        pairs = lane_reference.get(key) if isinstance(lane_reference.get(key), Mapping) else {}
        for pair in pairs.values():
            if isinstance(pair, Mapping) and pair.get("lane_key"):
                scores[str(pair["lane_key"])] = _bounded_int(pair.get("lane_score"), 0, 100, scores.get(str(pair["lane_key"]), 55))
    for row in lane_reference.get("lane_origin_matrix") or []:
        if isinstance(row, Mapping) and row.get("lane_key"):
            scores.setdefault(str(row["lane_key"]), _bounded_int(row.get("lane_score"), 0, 100, 55))
    return scores


def _fresh_flow_status(*, lane_key: str, lane: Mapping[str, Any], lane_reference: Mapping[str, Any]) -> str:
    if lane.get("fresh_flow_status"):
        return str(lane["fresh_flow_status"])
    reference_rows = []
    for key in ("post_outcome_pair_comparison", "pair_comparison"):
        pairs = lane_reference.get(key) if isinstance(lane_reference.get(key), Mapping) else {}
        reference_rows.extend(pair for pair in pairs.values() if isinstance(pair, Mapping) and pair.get("lane_key") == lane_key)
    reference_rows.extend(
        row
        for row in lane_reference.get("lane_origin_matrix") or []
        if isinstance(row, Mapping) and row.get("lane_key") == lane_key
    )
    fresh_count = max((_bounded_int(row.get("fresh_capture_count"), 0, 1_000_000, 0) for row in reference_rows), default=0)
    if fresh_count > 0:
        return "fresh"
    if str(lane.get("lane_mode") or "") == "paper_discovered_unconfigured":
        return "unknown"
    if lane_key in FRESH_CONFIGURED_REFERENCE_LANES:
        return "fresh"
    return "stale_only"


def _direction_alignment_score(*, signal_origin: str, lane_direction: str) -> int:
    alignment = _direction_alignment(signal_origin=signal_origin, lane_direction=lane_direction)
    return {"aligned": 100, "both": 70, "unknown": 50, "misaligned": 0}.get(alignment, 50)


def _direction_alignment(*, signal_origin: str, lane_direction: str) -> str:
    expected = {
        "bearish_engulfing": "short",
        "three_black_crows": "short",
        "bullish_engulfing": "long",
        "three_white_soldiers": "long",
    }.get(signal_origin)
    if signal_origin == "hammer_wick_reversal":
        return "aligned"
    if signal_origin == "exhaustion_wick":
        return "both"
    if expected is None:
        return "unknown"
    return "aligned" if expected == lane_direction else "misaligned"


def _mixed_bias_required(*, signal_origin: str, pattern_card: Mapping[str, Any]) -> bool:
    readiness = str(pattern_card.get("readiness") or "")
    warnings = {str(item) for item in pattern_card.get("risk_warnings") or []}
    return (
        signal_origin == "exhaustion_wick"
        or readiness.endswith("MIXED_BIAS_REVIEW_REQUIRED")
        or "mixed_directional_bias_review_required" in warnings
    )


def _pair_readiness(
    *,
    signal_origin: str,
    pair_score: int,
    fresh_flow_status: str,
    alignment_score: int,
    blocked: bool,
    mixed_bias: bool,
) -> str:
    if blocked:
        return PATTERN_PAIR_REGISTRY_ONLY_BLOCKED
    if alignment_score <= 0:
        return PATTERN_PAIR_MIXED_BIAS_REVIEW_REQUIRED
    if mixed_bias:
        return PATTERN_PAIR_MIXED_BIAS_REVIEW_REQUIRED
    if fresh_flow_status != "fresh":
        return PATTERN_PAIR_NEEDS_MORE_FRESH_FLOW
    if pair_score >= 58:
        return PATTERN_PAIR_READY_FOR_PAPER_TRACKING
    return PATTERN_PAIR_NOT_LIVE_AUTHORIZED


def _lane_candidate_from_scope_row(row: Mapping[str, Any], *, configured: bool) -> dict[str, Any]:
    lane_key = str(row.get("lane_key") or normalize_lane_key(row.get("symbol"), row.get("timeframe"), row.get("direction"), row.get("entry_mode") or TARGET_ENTRY_MODE))
    parts = _lane_parts(lane_key)
    return {
        "lane_key": lane_key,
        "symbol": parts["symbol"],
        "timeframe": parts["timeframe"],
        "direction": parts["direction"],
        "entry_mode": parts["entry_mode"],
        "lane_mode": str(row.get("mode") or ("paper" if configured else "paper_discovered_unconfigured")),
        "configured_lane": configured,
        "lane_score": 55 if configured else 42,
        "lane_reference_found": False,
    }


def _lane_candidate_from_key(lane_key: str, lane_mode: str, *, configured: bool) -> dict[str, Any]:
    parts = _lane_parts(lane_key)
    return {
        "lane_key": lane_key,
        "symbol": parts["symbol"],
        "timeframe": parts["timeframe"],
        "direction": parts["direction"],
        "entry_mode": parts["entry_mode"],
        "lane_mode": lane_mode,
        "configured_lane": configured,
        "lane_score": 55 if configured else 42,
        "lane_reference_found": False,
    }


def _lane_parts(lane_key: str) -> dict[str, str]:
    parts = str(lane_key or "|||").split("|")
    while len(parts) < 4:
        parts.append("")
    return {"symbol": parts[0], "timeframe": parts[1], "direction": parts[2], "entry_mode": parts[3]}


def _pair_why(
    *,
    lane_key: str,
    signal_origin: str,
    pair_score: int,
    pair_readiness: str,
    fresh_flow_status: str,
    alignment: str,
    lane_mode: str,
) -> str:
    if pair_readiness == PATTERN_PAIR_REGISTRY_ONLY_BLOCKED:
        return f"{signal_origin} remains registry-only blocked for {lane_key}; no paper tracking or live authority."
    if alignment == "misaligned":
        return f"{signal_origin} does not align with {lane_key} direction; keep review-only."
    if fresh_flow_status != "fresh":
        return f"{lane_key} + {signal_origin} scored {pair_score}, but needs fresh flow before active paper tracking."
    if lane_mode == "paper_discovered_unconfigured":
        return f"{lane_key} + {signal_origin} is a discovered paper lane candidate with caution; no config write or promotion."
    if pair_readiness == PATTERN_PAIR_READY_FOR_PAPER_TRACKING:
        return f"{lane_key} + {signal_origin} has enough paper matrix evidence for tracking only; live remains unauthorized."
    return f"{lane_key} + {signal_origin} scored {pair_score}; keep paper-only review."


def _status_for_review(*, record_matrix: bool, confirmation_valid: bool, matrix_status: str, has_pairs: bool) -> str:
    if record_matrix and not confirmation_valid:
        return PATTERN_LANE_MATRIX_REVIEW_REJECTED
    if not has_pairs or matrix_status == UNKNOWN_NEEDS_MANUAL_REVIEW:
        return PATTERN_LANE_MATRIX_REVIEW_BLOCKED
    if record_matrix and confirmation_valid:
        return PATTERN_LANE_MATRIX_REVIEW_RECORDED
    return PATTERN_LANE_MATRIX_REVIEW_READY


def _recommended_next_operator_move(matrix_status: str, blockers: Sequence[str]) -> str:
    if "R204 pattern Keter rescoring not found" in blockers:
        return "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"
    if matrix_status in {BEARISH_ENGULFING_READY_FOR_PAPER_MATRIX, CROWS_AND_ENGULFING_BOTH_PAPER_CANDIDATES}:
        return "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"
    return "RUN_R203_ANCHOR_SIGNAL_CONFLUENCE_MATRIX"


def _recommended_next_engineering_move(matrix_status: str, current_best: Sequence[Mapping[str, Any]]) -> str:
    if matrix_status in {BEARISH_ENGULFING_READY_FOR_PAPER_MATRIX, CROWS_AND_ENGULFING_BOTH_PAPER_CANDIDATES} and current_best:
        top = current_best[0]
        return (
            f"Keep {top.get('lane_key')} + {top.get('signal_origin')} in active paper tracking review only; "
            "do not write configs or promote lanes."
        )
    return "Collect fresh full-spectrum pattern flow, then rerun R205 preview only."


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


def _unknown_reference_comparison() -> dict[str, Any]:
    return {
        "hammer_reference_score": None,
        "three_black_crows_reference_score": None,
        "top_pattern_origin": None,
        "top_pattern_pair_score": None,
        "hammer_still_best_reference": None,
        "bearish_engulfing_beats_crows": None,
        "why": "Reference scores unavailable; manual review required.",
    }


def _lane_sort_key(lane_key: str) -> tuple[int, str, str]:
    parts = _lane_parts(lane_key)
    return (_timeframe_sort(parts["timeframe"]), parts["direction"], lane_key)


def _timeframe_sort(timeframe: str) -> int:
    text = str(timeframe).strip()
    unit = text[-1:].lower()
    try:
        number = int(text[:-1]) if unit in {"m", "h", "d"} else int(text)
    except ValueError:
        return 999_999
    multiplier = {"m": 1, "h": 60, "d": 1440}.get(unit, 1)
    return number * multiplier


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _dedupe(items: Sequence[Any]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


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
