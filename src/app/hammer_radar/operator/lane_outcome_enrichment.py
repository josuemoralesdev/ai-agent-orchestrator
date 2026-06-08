"""R232 lane outcome enrichment audit.

This module reads local paper ledgers only. It can append an R232 audit record
after exact confirmation, but it never mutates env/config/lane/risk state,
calls Binance/network, creates payloads, promotes lanes, or authorizes live.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import (
    DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    DEFAULT_THRESHOLD_REQUIRED_COUNT,
    build_full_spectrum_lane_scoreboard,
    build_lane_outcome_counts,
    load_full_spectrum_lane_scoreboard_records,
    load_paper_outcome_records,
    load_tiny_live_capture_count_sync as _load_tiny_live_capture_count_sync,
    normalize_lane_key as _normalize_lane_key,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

LANE_OUTCOME_ENRICHMENT_READY = "LANE_OUTCOME_ENRICHMENT_READY"
LANE_OUTCOME_ENRICHMENT_REJECTED = "LANE_OUTCOME_ENRICHMENT_REJECTED"
LANE_OUTCOME_ENRICHMENT_RECORDED = "LANE_OUTCOME_ENRICHMENT_RECORDED"
LANE_OUTCOME_ENRICHMENT_BLOCKED = "LANE_OUTCOME_ENRICHMENT_BLOCKED"
LANE_OUTCOME_ENRICHMENT_ERROR = "LANE_OUTCOME_ENRICHMENT_ERROR"

OFFICIAL_TINY_LIVE_OUTCOME_EDGE_CONFIRMED = "OFFICIAL_TINY_LIVE_OUTCOME_EDGE_CONFIRMED"
OFFICIAL_TINY_LIVE_EDGE_NEEDS_MORE_CAPTURES = "OFFICIAL_TINY_LIVE_EDGE_NEEDS_MORE_CAPTURES"
ALTERNATE_OUTCOME_EDGE_FOUND_BUT_CAPTURE_BLOCKED = "ALTERNATE_OUTCOME_EDGE_FOUND_BUT_CAPTURE_BLOCKED"
OUTCOME_DATA_GAPS_REMAIN = "OUTCOME_DATA_GAPS_REMAIN"
TINY_LIVE_THRESHOLD_MET = "TINY_LIVE_THRESHOLD_MET"
TINY_LIVE_THRESHOLD_NOT_MET = "TINY_LIVE_THRESHOLD_NOT_MET"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "LANE_OUTCOME_ENRICHMENT"
LEDGER_FILENAME = "lane_outcome_enrichment.ndjson"
CONFIRM_LANE_OUTCOME_ENRICHMENT_RECORDING_PHRASE = (
    "I CONFIRM LANE OUTCOME ENRICHMENT RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

FRESH_OUTCOME_AFTER_SECONDS = 72 * 60 * 60
LOW_COVERAGE_PCT = 50.0

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
    "ledger_rewritten": False,
    "destructive_write": False,
    "historical_ledger_rewritten": False,
    "paper_outcome_ledger_rewritten": False,
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
    "official_tiny_live_lane_changed": False,
    "alternate_lane_promoted": False,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/full_spectrum_lane_scoreboard.ndjson",
    "logs/hammer_radar_forward/paper_outcomes.ndjson",
    "logs/hammer_radar_forward/outcomes.ndjson",
    "logs/hammer_radar_forward/paper_executions.ndjson",
    "logs/hammer_radar_forward/simulated_executions.ndjson",
    "logs/hammer_radar_forward/strategy_performance.ndjson",
    "logs/hammer_radar_forward/strategy_promotion_status.ndjson",
    "logs/hammer_radar_forward/strategy_promotion_events.ndjson",
    "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_lane_outcome_enrichment(
    *,
    log_dir: str | Path | None = None,
    record_enrichment: bool = False,
    confirm_lane_outcome_enrichment: str | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_lane_outcome_enrichment == CONFIRM_LANE_OUTCOME_ENRICHMENT_RECORDING_PHRASE
    try:
        scoreboard = load_latest_full_spectrum_lane_scoreboard(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        scoreboard_rows = list(scoreboard.get("lane_scoreboard_rows") or [])
        outcome_records = load_lane_outcome_records(log_dir=resolved_log_dir, limit=0)
        strategy_performance = load_strategy_performance_records(log_dir=resolved_log_dir, limit=0)
        strategy_promotion = load_strategy_promotion_records(log_dir=resolved_log_dir, limit=0)
        tiny_live_sync = load_tiny_live_capture_count_sync(log_dir=resolved_log_dir)
        outcome_index = build_outcome_index_by_lane(outcome_records)
        enriched = rank_enriched_lane_rows(
            [
                enrich_lane_scoreboard_row(
                    row,
                    outcome_index=outcome_index,
                    official_tiny_live_lane=official_tiny_live_lane,
                    threshold_required_count=threshold_required_count,
                    now=generated_at,
                )
                for row in scoreboard_rows
            ]
        )
        official_status = _official_tiny_live_lane_status(
            scoreboard=scoreboard,
            tiny_live_sync=tiny_live_sync,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        comparison = build_official_vs_alternate_comparison(enriched, official_tiny_live_lane=official_tiny_live_lane)
        gap_report = build_lane_outcome_gap_report(enriched, official_tiny_live_lane=official_tiny_live_lane)
        recommendations = build_lane_outcome_recommendations(
            official_tiny_live_lane_status=official_status,
            comparison=comparison,
            gap_report=gap_report,
        )
        enrichment_status = classify_lane_outcome_enrichment_status(
            official_tiny_live_lane_status=official_status,
            comparison=comparison,
            gap_report=gap_report,
        )
        status = LANE_OUTCOME_ENRICHMENT_READY if enriched else LANE_OUTCOME_ENRICHMENT_BLOCKED
        if record_enrichment and not confirmation_valid:
            status = LANE_OUTCOME_ENRICHMENT_REJECTED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "enrichment_recorded": False,
            "enrichment_id": None,
            "record_enrichment_requested": bool(record_enrichment),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "paper_only": True,
                "live_authorized": False,
                "official_tiny_live_lane": official_tiny_live_lane,
            },
            "input_summary": {
                "scoreboard_found": bool(scoreboard.get("scoreboard_found")),
                "paper_outcome_records_found": bool(outcome_records),
                "strategy_performance_records_found": bool(strategy_performance),
                "strategy_promotion_status_records_found": bool(strategy_promotion),
                "tiny_live_capture_sync_found": bool(tiny_live_sync),
            },
            "official_tiny_live_lane_status": official_status,
            "enriched_lane_rows": enriched,
            "official_vs_alternate_comparison": comparison,
            "lane_outcome_gap_report": gap_report,
            "lane_outcome_recommendations": recommendations,
            "enrichment_status": enrichment_status,
            "recommended_next_operator_move": _recommended_next_operator_move(
                official_tiny_live_lane_status=official_status,
                comparison=comparison,
                gap_report=gap_report,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(comparison=comparison, gap_report=gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_enrichment and confirmation_valid:
            record = append_lane_outcome_enrichment_record(payload, log_dir=resolved_log_dir)
            payload["status"] = LANE_OUTCOME_ENRICHMENT_RECORDED
            payload["enrichment_recorded"] = True
            payload["enrichment_id"] = record["enrichment_id"]
            payload["ledger_path"] = str(lane_outcome_enrichment_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": LANE_OUTCOME_ENRICHMENT_ERROR,
                "generated_at": generated_at.isoformat(),
                "enrichment_recorded": False,
                "enrichment_id": None,
                "record_enrichment_requested": bool(record_enrichment),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "paper_only": True,
                    "live_authorized": False,
                    "official_tiny_live_lane": official_tiny_live_lane,
                },
                "input_summary": {
                    "scoreboard_found": False,
                    "paper_outcome_records_found": False,
                    "strategy_performance_records_found": False,
                    "strategy_promotion_status_records_found": False,
                    "tiny_live_capture_sync_found": False,
                },
                "official_tiny_live_lane_status": _empty_official_status(
                    official_tiny_live_lane,
                    threshold_required_count=threshold_required_count,
                ),
                "enriched_lane_rows": [],
                "official_vs_alternate_comparison": _empty_comparison(official_tiny_live_lane),
                "lane_outcome_gap_report": _empty_gap_report(),
                "lane_outcome_recommendations": [],
                "enrichment_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R232 enrichment error before using lane outcome rankings.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_full_spectrum_lane_scoreboard(
    *,
    log_dir: str | Path | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
) -> dict[str, Any]:
    records = load_full_spectrum_lane_scoreboard_records(log_dir=log_dir, limit=1)
    if records:
        latest = dict(records[0])
        latest["scoreboard_found"] = True
        return _sanitize(latest)
    built = build_full_spectrum_lane_scoreboard(
        log_dir=log_dir,
        official_tiny_live_lane=official_tiny_live_lane,
        threshold_required_count=threshold_required_count,
    )
    built["scoreboard_found"] = False
    return _sanitize(built)


def load_lane_outcome_records(*, log_dir: str | Path | None = None, limit: int = 0) -> list[dict[str, Any]]:
    resolved = get_log_dir(log_dir, use_env=True)
    records = list(load_paper_outcome_records(log_dir=resolved, limit=limit))
    for filename in ("paper_executions.ndjson", "simulated_executions.ndjson"):
        for record in _read_ndjson_records(resolved / filename, limit=limit):
            row = _execution_or_outcome_row(record)
            if row.get("lane_key"):
                records.append(row)
    return _sanitize(records)


def load_strategy_performance_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return _read_ndjson_records(get_log_dir(log_dir, use_env=True) / "strategy_performance.ndjson", limit=limit)


def load_strategy_promotion_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    resolved = get_log_dir(log_dir, use_env=True)
    return [
        *_read_ndjson_records(resolved / "strategy_promotion_status.ndjson", limit=limit),
        *_read_ndjson_records(resolved / "strategy_promotion_events.ndjson", limit=limit),
    ]


def load_tiny_live_capture_count_sync(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _sanitize(_load_tiny_live_capture_count_sync(log_dir=log_dir))


def normalize_lane_key(
    symbol_or_lane_key: object,
    timeframe: object | None = None,
    direction: object | None = None,
    entry_mode: object | None = None,
) -> str:
    if timeframe is None and direction is None:
        parts = str(symbol_or_lane_key or "").split("|")
        if len(parts) >= 3:
            return _normalize_lane_key(parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else entry_mode)
    return _normalize_lane_key(symbol_or_lane_key, timeframe, direction, entry_mode)


def build_outcome_index_by_lane(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return build_lane_outcome_counts(records)


def enrich_lane_scoreboard_row(
    row: Mapping[str, Any],
    *,
    outcome_index: Mapping[str, Mapping[str, Any]],
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
    now: datetime | None = None,
) -> dict[str, Any]:
    lane_key = normalize_lane_key(row.get("lane_key") or "")
    outcomes = dict(outcome_index.get(lane_key) or {})
    paper_count = int(outcomes.get("paper_outcome_count") if outcomes else row.get("paper_outcome_count") or 0)
    known = int(outcomes.get("known_outcome_count") if outcomes else row.get("known_outcome_count") or 0)
    wins = int(outcomes.get("win_count") if outcomes else row.get("win_count") or 0)
    losses = int(outcomes.get("loss_count") if outcomes else row.get("loss_count") or 0)
    unknown = int(outcomes.get("outcome_unknown_count") if outcomes else row.get("outcome_unknown_count") or 0)
    unique_captures = int(row.get("unique_capture_count") or 0)
    required = int(row.get("threshold_required_count") or threshold_required_count)
    win_rate = round((wins / known) * 100, 2) if known else None
    loss_rate = round((losses / known) * 100, 2) if known else None
    coverage = calculate_outcome_coverage_pct(known_outcome_count=known, paper_outcome_count=paper_count)
    freshness = _freshness_status(outcomes.get("latest_outcome_at") or row.get("latest_outcome_at"), now=now)
    sample_bucket = classify_sample_size_bucket(known)
    win_bucket = classify_win_rate_quality_bucket(win_rate_pct=win_rate, known_outcome_count=known)
    blockers = _blockers(
        row=row,
        known=known,
        paper_count=paper_count,
        coverage=coverage,
        unique_captures=unique_captures,
        required=required,
    )
    outcome_quality = calculate_outcome_quality_score(
        win_rate_pct=win_rate,
        known_outcome_count=known,
        paper_outcome_count=paper_count,
        unknown_outcome_count=unknown,
        outcome_coverage_pct=coverage,
        outcome_freshness_status=freshness,
        blockers=blockers,
    )
    capture_readiness = calculate_capture_readiness_score(
        unique_capture_count=unique_captures,
        threshold_required_count=required,
    )
    combined = calculate_combined_watch_score(
        outcome_quality_score=outcome_quality,
        capture_readiness_score=capture_readiness,
    )
    lane = _lane_from_key(lane_key)
    return _sanitize(
        {
            "rank": None,
            "rank_from_scoreboard": row.get("rank"),
            "lane_key": lane_key,
            "symbol": lane["symbol"],
            "timeframe": lane["timeframe"],
            "direction": lane["direction"],
            "entry_mode": lane["entry_mode"],
            "official_candidate": lane_key == official_tiny_live_lane,
            "signal_flow_count": int(row.get("signal_flow_count") or 0),
            "capture_event_count": int(row.get("capture_event_count") or 0),
            "unique_capture_count": unique_captures,
            "threshold_required_count": required,
            "threshold_distance_remaining": max(0, required - unique_captures),
            "capture_readiness_score": capture_readiness,
            "paper_outcome_count": paper_count,
            "known_outcome_count": known,
            "win_count": wins,
            "loss_count": losses,
            "unknown_outcome_count": unknown,
            "win_rate_pct": win_rate,
            "loss_rate_pct": loss_rate,
            "outcome_coverage_pct": coverage,
            "sample_size_bucket": sample_bucket,
            "win_rate_quality_bucket": win_bucket,
            "outcome_freshness_status": freshness,
            "outcome_quality_score": outcome_quality,
            "combined_watch_score": combined,
            "tiny_live_candidate_status": _tiny_live_candidate_status(
                lane_key=lane_key,
                official_tiny_live_lane=official_tiny_live_lane,
                entry_mode=lane["entry_mode"],
                unique_captures=unique_captures,
                required=required,
                known=known,
            ),
            "enrichment_notes": _enrichment_notes(
                row=row,
                sample_bucket=sample_bucket,
                win_bucket=win_bucket,
                freshness=freshness,
            ),
            "blockers": blockers,
            "live_authorized": False,
            "promotion_allowed": False,
        }
    )


def classify_sample_size_bucket(known_outcome_count: int) -> str:
    count = int(known_outcome_count or 0)
    if count <= 0:
        return "NONE"
    if count <= 29:
        return "TINY"
    if count <= 99:
        return "SMALL"
    if count <= 299:
        return "MEDIUM"
    return "LARGE"


def classify_win_rate_quality_bucket(*, win_rate_pct: float | None, known_outcome_count: int = 0) -> str:
    if int(known_outcome_count or 0) <= 0 or win_rate_pct is None:
        return "UNKNOWN"
    rate = float(win_rate_pct)
    if rate < 55.0:
        return "WEAK"
    if rate < 65.0:
        return "MODERATE"
    if rate < 75.0:
        return "STRONG"
    return "VERY_STRONG"


def calculate_outcome_coverage_pct(*, known_outcome_count: int, paper_outcome_count: int) -> float | None:
    paper_count = int(paper_outcome_count or 0)
    if paper_count <= 0:
        return None
    return round((int(known_outcome_count or 0) / paper_count) * 100, 2)


def calculate_outcome_quality_score(
    *,
    win_rate_pct: float | None,
    known_outcome_count: int,
    paper_outcome_count: int,
    unknown_outcome_count: int,
    outcome_coverage_pct: float | None,
    outcome_freshness_status: str,
    blockers: Sequence[str] | None = None,
) -> float:
    if int(known_outcome_count or 0) <= 0 or win_rate_pct is None:
        return 0.0
    sample_bonus = {"NONE": 0.0, "TINY": 5.0, "SMALL": 10.0, "MEDIUM": 15.0, "LARGE": 20.0}[
        classify_sample_size_bucket(int(known_outcome_count or 0))
    ]
    win_component = max(0.0, min(float(win_rate_pct), 100.0)) * 0.6
    coverage_bonus = 0.0 if outcome_coverage_pct is None else max(0.0, min(float(outcome_coverage_pct), 100.0)) * 0.1
    freshness_bonus = {"fresh": 5.0, "stale": 1.0, "unknown": 0.0}.get(str(outcome_freshness_status), 0.0)
    paper_count = max(1, int(paper_outcome_count or 0))
    unknown_penalty = min(10.0, (int(unknown_outcome_count or 0) / paper_count) * 10.0)
    blocker_penalty = min(15.0, len(list(blockers or [])) * 5.0)
    score = win_component + sample_bonus + coverage_bonus + freshness_bonus - unknown_penalty - blocker_penalty
    return round(max(0.0, min(score, 100.0)), 2)


def calculate_capture_readiness_score(*, unique_capture_count: int, threshold_required_count: int) -> float:
    required = int(threshold_required_count or 0)
    if required <= 0:
        return 0.0
    return round(min(1.0, max(0.0, int(unique_capture_count or 0) / required)), 4)


def calculate_combined_watch_score(*, outcome_quality_score: float, capture_readiness_score: float) -> float:
    return round((float(outcome_quality_score or 0.0) * 0.7) + (float(capture_readiness_score or 0.0) * 100.0 * 0.3), 2)


def rank_enriched_lane_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ranked = [dict(row) for row in rows]
    ranked.sort(
        key=lambda row: (
            -float(row.get("combined_watch_score") or 0.0),
            -float(row.get("outcome_quality_score") or 0.0),
            -float(row.get("capture_readiness_score") or 0.0),
            int(row.get("rank_from_scoreboard") or 999999),
            str(row.get("lane_key") or ""),
        )
    )
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return _sanitize(ranked)


def build_official_vs_alternate_comparison(
    rows: Sequence[Mapping[str, Any]],
    *,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
) -> dict[str, Any]:
    official = next((dict(row) for row in rows if row.get("lane_key") == official_tiny_live_lane), None)
    alternates = [dict(row) for row in rows if row.get("lane_key") != official_tiny_live_lane]
    top_alternates = alternates[:10]
    official_quality = float(official.get("outcome_quality_score") or 0.0) if official else 0.0
    better = [row for row in top_alternates if float(row.get("outcome_quality_score") or 0.0) > official_quality]
    capture_blocked = any(int(row.get("threshold_distance_remaining") or 0) > 0 for row in better)
    confirmed = bool(official) and not better and int(official.get("known_outcome_count") or 0) > 0
    return _sanitize(
        {
            "official_lane": _comparison_row(official) if official else None,
            "top_outcome_alternates": [_comparison_row(row) for row in top_alternates],
            "official_lane_outcome_edge_confirmed": confirmed,
            "alternate_outcome_edge_found": bool(better),
            "alternate_capture_blocked": bool(capture_blocked),
            "why": _comparison_why(official=official, better=better, capture_blocked=capture_blocked),
        }
    )


def build_lane_outcome_gap_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
) -> dict[str, Any]:
    no_known = [row for row in rows if int(row.get("known_outcome_count") or 0) == 0]
    low_coverage = [
        row
        for row in rows
        if row.get("outcome_coverage_pct") is not None and float(row.get("outcome_coverage_pct") or 0.0) < LOW_COVERAGE_PCT
    ]
    strong_blocked = [
        _gap_row(row)
        for row in rows
        if row.get("win_rate_quality_bucket") in {"STRONG", "VERY_STRONG"}
        and int(row.get("threshold_distance_remaining") or 0) > 0
    ][:20]
    near_threshold = [
        _gap_row(row)
        for row in rows
        if 0 < int(row.get("threshold_distance_remaining") or 0) <= 3
    ][:20]
    official = next((row for row in rows if row.get("lane_key") == official_tiny_live_lane), {})
    return {
        "lanes_with_no_known_outcomes": len(no_known),
        "lanes_with_low_outcome_coverage": len(low_coverage),
        "lanes_with_strong_outcomes_but_capture_blocked": strong_blocked,
        "lanes_near_capture_threshold": near_threshold,
        "official_lane_blockers": list(official.get("blockers") or []),
        "hard_live_blockers": [
            "R232 is audit-only and cannot authorize live.",
            "Win rate alone is not tiny-live readiness.",
            "Unique capture threshold remains mandatory.",
            "Funding must wait.",
            "Risk contract changes must wait.",
            "No lane promotion is allowed by this enrichment.",
        ],
    }


def build_lane_outcome_recommendations(
    *,
    official_tiny_live_lane_status: Mapping[str, Any],
    comparison: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "KEEP_8M_SHORT_AS_OFFICIAL",
            "future_phase": "R228",
            "why": "R232 enriches paper outcome trust only and keeps the official tiny-live lane unchanged.",
        },
        {
            "priority": "HIGH",
            "recommended_action": "KEEP_FISHERMAN_RUNNING",
            "future_phase": "R232",
            "why": "Official lane capture threshold is still the deciding tiny-live blocker until it reaches 10 of 10.",
        },
    ]
    if official_tiny_live_lane_status.get("threshold_met"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RUN_R228_IF_10_OF_10",
                "future_phase": "R228",
                "why": "Official lane reached the unique capture threshold; R232 still does not authorize live.",
            }
        )
    if comparison.get("alternate_outcome_edge_found"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "WATCH_ALTERNATE_LANE",
                "future_phase": "R233",
                "why": "At least one alternate has stronger outcome quality, but capture threshold and promotion blockers remain.",
            }
        )
    if int(gap_report.get("lanes_with_strong_outcomes_but_capture_blocked") and len(gap_report.get("lanes_with_strong_outcomes_but_capture_blocked") or [])):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "RUN_R233_CAPTURE_PRIORITY_REBALANCE",
                "future_phase": "R233",
                "why": "Outcome quality can inform paper-only fishing priority without changing lane controls.",
            }
        )
    return recommendations


def classify_lane_outcome_enrichment_status(
    *,
    official_tiny_live_lane_status: Mapping[str, Any],
    comparison: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> str:
    if official_tiny_live_lane_status.get("threshold_met"):
        return TINY_LIVE_THRESHOLD_MET
    if comparison.get("alternate_outcome_edge_found") and comparison.get("alternate_capture_blocked"):
        return ALTERNATE_OUTCOME_EDGE_FOUND_BUT_CAPTURE_BLOCKED
    if comparison.get("official_lane_outcome_edge_confirmed"):
        return OFFICIAL_TINY_LIVE_EDGE_NEEDS_MORE_CAPTURES
    if int(gap_report.get("lanes_with_no_known_outcomes") or 0) > 0 or int(gap_report.get("lanes_with_low_outcome_coverage") or 0) > 0:
        return OUTCOME_DATA_GAPS_REMAIN
    if official_tiny_live_lane_status.get("threshold_met") is False:
        return TINY_LIVE_THRESHOLD_NOT_MET
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_lane_outcome_enrichment_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = lane_outcome_enrichment_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "enrichment_id": str(record.get("enrichment_id") or f"r232_lane_outcome_enrichment_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "official_tiny_live_lane_status": dict(record.get("official_tiny_live_lane_status") or {}),
            "enriched_lane_rows": list(record.get("enriched_lane_rows") or []),
            "official_vs_alternate_comparison": dict(record.get("official_vs_alternate_comparison") or {}),
            "lane_outcome_gap_report": dict(record.get("lane_outcome_gap_report") or {}),
            "lane_outcome_recommendations": list(record.get("lane_outcome_recommendations") or []),
            "enrichment_status": record.get("enrichment_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_lane_outcome_enrichment_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return _read_ndjson_records(lane_outcome_enrichment_records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def summarize_lane_outcome_enrichment_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "latest_enrichment_id": latest.get("enrichment_id") if latest else None,
        "latest_enrichment_status": latest.get("enrichment_status") if latest else None,
        "safety": dict(SAFETY),
    }


def lane_outcome_enrichment_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_lane_outcome_enrichment_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _execution_or_outcome_row(record: Mapping[str, Any]) -> dict[str, Any]:
    signal_id = str(_first_present(record, "signal_id", "candidate_id", "id") or "")
    lane = _lane_from_record_or_signal(record, signal_id)
    outcome = _first_present(record, "outcome", "result", "close_reason", "status")
    return {
        **lane,
        "signal_id": signal_id or None,
        "outcome": _normalize_outcome(outcome),
        "outcome_at": _first_present(record, "evaluated_at", "closed_at", "created_at", "timestamp", "generated_at", "recorded_at_utc"),
    }


def _normalize_outcome(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"win", "won", "take_profit", "tp", "profit"}:
        return "win"
    if text in {"loss", "lose", "lost", "stop", "stopped", "stop_loss", "sl"}:
        return "loss"
    return text or "unknown"


def _official_tiny_live_lane_status(
    *,
    scoreboard: Mapping[str, Any],
    tiny_live_sync: Mapping[str, Any],
    official_tiny_live_lane: str,
    threshold_required_count: int,
) -> dict[str, Any]:
    status = dict(scoreboard.get("official_tiny_live_lane_status") or {})
    if not status:
        capture = dict(tiny_live_sync.get("capture_count") or {})
        count = int(capture.get("fresh_capture_count") or 0)
        required = int(capture.get("required_fresh_capture_count") or threshold_required_count)
        status = {
            "lane_key": official_tiny_live_lane,
            "fresh_capture_count": count,
            "required_fresh_capture_count": required,
            "threshold_met": bool(capture.get("threshold_met")) or count >= required,
            "threshold_distance_remaining": max(0, required - count),
        }
    status["lane_key"] = official_tiny_live_lane
    status["funding_should_wait"] = True
    status["risk_contract_should_wait"] = True
    return _sanitize(status)


def _empty_official_status(lane_key: str, *, threshold_required_count: int) -> dict[str, Any]:
    return {
        "lane_key": lane_key,
        "fresh_capture_count": 0,
        "required_fresh_capture_count": int(threshold_required_count),
        "threshold_met": False,
        "threshold_distance_remaining": int(threshold_required_count),
        "funding_should_wait": True,
        "risk_contract_should_wait": True,
    }


def _empty_comparison(official_tiny_live_lane: str) -> dict[str, Any]:
    return {
        "official_lane": {"lane_key": official_tiny_live_lane},
        "top_outcome_alternates": [],
        "official_lane_outcome_edge_confirmed": False,
        "alternate_outcome_edge_found": False,
        "alternate_capture_blocked": False,
        "why": "No enriched rows were available.",
    }


def _empty_gap_report() -> dict[str, Any]:
    return {
        "lanes_with_no_known_outcomes": 0,
        "lanes_with_low_outcome_coverage": 0,
        "lanes_with_strong_outcomes_but_capture_blocked": [],
        "lanes_near_capture_threshold": [],
        "official_lane_blockers": [],
        "hard_live_blockers": [],
    }


def _blockers(
    *,
    row: Mapping[str, Any],
    known: int,
    paper_count: int,
    coverage: float | None,
    unique_captures: int,
    required: int,
) -> list[str]:
    blockers: list[str] = []
    if int(known or 0) <= 0:
        blockers.append("known_outcomes_missing")
    if int(paper_count or 0) > 0 and coverage is not None and coverage < LOW_COVERAGE_PCT:
        blockers.append("outcome_coverage_low")
    if int(unique_captures or 0) <= 0:
        blockers.append("unique_captures_missing")
    if int(unique_captures or 0) < int(required or 0):
        blockers.append("tiny_live_unique_capture_threshold_not_met")
    if str(row.get("entry_mode") or "") == "entry_unknown":
        blockers.append("entry_mode_missing")
    blockers.extend(["live_authorization_absent_by_design", "lane_promotion_forbidden_by_r232"])
    return blockers


def _tiny_live_candidate_status(
    *,
    lane_key: str,
    official_tiny_live_lane: str,
    entry_mode: str,
    unique_captures: int,
    required: int,
    known: int,
) -> str:
    if lane_key == official_tiny_live_lane:
        return "OFFICIAL_CANDIDATE"
    if entry_mode == "entry_unknown":
        return "ENTRY_MODE_MISSING"
    if int(unique_captures or 0) < int(required or 0):
        return "CAPTURE_BLOCKED"
    if int(known or 0) <= 0:
        return "OUTCOME_DATA_MISSING"
    return "WATCHLIST_ONLY_NOT_PROMOTED"


def _enrichment_notes(
    *,
    row: Mapping[str, Any],
    sample_bucket: str,
    win_bucket: str,
    freshness: str,
) -> list[str]:
    notes = [
        f"sample_size_bucket={sample_bucket}",
        f"win_rate_quality_bucket={win_bucket}",
        f"outcome_freshness_status={freshness}",
        "combined_watch_score is watchlist-only",
        "live_authorized=false",
        "promotion_allowed=false",
    ]
    notes.extend(str(note) for note in row.get("score_notes") or [])
    return notes


def _freshness_status(value: object, *, now: datetime | None = None) -> str:
    if not value:
        return "unknown"
    parsed = _parse_dt(value)
    if parsed is None:
        return "unknown"
    generated_at = now or datetime.now(UTC)
    return "fresh" if (generated_at - parsed).total_seconds() <= FRESH_OUTCOME_AFTER_SECONDS else "stale"


def _comparison_row(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    keys = (
        "rank",
        "rank_from_scoreboard",
        "lane_key",
        "official_candidate",
        "unique_capture_count",
        "threshold_distance_remaining",
        "known_outcome_count",
        "win_rate_pct",
        "sample_size_bucket",
        "win_rate_quality_bucket",
        "outcome_quality_score",
        "capture_readiness_score",
        "combined_watch_score",
        "tiny_live_candidate_status",
        "blockers",
        "live_authorized",
        "promotion_allowed",
    )
    return {key: row.get(key) for key in keys}


def _comparison_why(
    *,
    official: Mapping[str, Any] | None,
    better: Sequence[Mapping[str, Any]],
    capture_blocked: bool,
) -> str:
    if not official:
        return "Official lane was not present in the enriched scoreboard rows."
    if not better:
        return "No top alternate has a higher outcome quality score than the official lane."
    if capture_blocked:
        return "One or more alternates have stronger outcome quality but remain blocked by unique capture threshold."
    return "An alternate has stronger outcome quality; R232 still forbids promotion and live authorization."


def _gap_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_key": row.get("lane_key"),
        "rank": row.get("rank"),
        "rank_from_scoreboard": row.get("rank_from_scoreboard"),
        "unique_capture_count": row.get("unique_capture_count"),
        "threshold_distance_remaining": row.get("threshold_distance_remaining"),
        "known_outcome_count": row.get("known_outcome_count"),
        "win_rate_pct": row.get("win_rate_pct"),
        "outcome_quality_score": row.get("outcome_quality_score"),
        "combined_watch_score": row.get("combined_watch_score"),
    }


def _recommended_next_operator_move(
    *,
    official_tiny_live_lane_status: Mapping[str, Any],
    comparison: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> str:
    if official_tiny_live_lane_status.get("threshold_met"):
        return "RUN_R228_TINY_LIVE_10_OF_10_READY_PACKET"
    if comparison.get("alternate_outcome_edge_found") or gap_report.get("lanes_with_strong_outcomes_but_capture_blocked"):
        return "RUN_R233_CAPTURE_PRIORITY_REBALANCE"
    return "KEEP_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(*, comparison: Mapping[str, Any], gap_report: Mapping[str, Any]) -> str:
    if comparison.get("alternate_outcome_edge_found"):
        return "Build R233 paper-only capture priority rebalance from R232 enriched watch scores; no config writes."
    if int(gap_report.get("lanes_with_no_known_outcomes") or 0) > 0:
        return "Keep outcome ledgers and full-spectrum capture ledgers separated; fill gaps through paper-only capture/outcome flow."
    return "Maintain R232 as an audit record and continue official lane capture threshold monitoring."


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


def _lane_from_record_or_signal(record: Mapping[str, Any], signal_id: str | None = None) -> dict[str, Any]:
    symbol = _first_present(record, "symbol", "base_symbol")
    timeframe = _first_present(record, "timeframe", "tf", "interval")
    direction = _normalize_direction(_first_present(record, "direction", "bias_direction", "side"))
    entry_mode = _first_present(record, "entry_mode", "mode")
    if not entry_mode and isinstance(record.get("ticket"), Mapping):
        entry_mode = _first_present(record["ticket"], "entry_mode", "mode")
    if symbol and timeframe and direction:
        return _lane_from_key(normalize_lane_key(symbol, timeframe, direction, entry_mode))
    if signal_id:
        parts = str(signal_id or "").split("|")
        if len(parts) >= 3:
            return _lane_from_key(normalize_lane_key(parts[0], parts[1], parts[2], parts[3] if len(parts) > 4 else "entry_unknown"))
    return _lane_from_key("")


def _lane_from_key(lane_key: object) -> dict[str, Any]:
    parts = str(lane_key or "").split("|")
    symbol = parts[0] if len(parts) > 0 else ""
    timeframe = parts[1] if len(parts) > 1 else ""
    direction = parts[2] if len(parts) > 2 else ""
    entry_mode = parts[3] if len(parts) > 3 and parts[3] else "entry_unknown"
    normalized = normalize_lane_key(symbol, timeframe, direction, entry_mode) if symbol and timeframe and direction else ""
    return {
        "lane_key": normalized,
        "symbol": str(symbol).strip().upper(),
        "timeframe": str(timeframe).strip().lower(),
        "direction": str(direction).strip().lower(),
        "entry_mode": str(entry_mode).strip().lower(),
    }


def _normalize_direction(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"buy", "bull", "bullish"}:
        return "long"
    if text in {"sell", "bear", "bearish"}:
        return "short"
    return text


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _parse_dt(value: object) -> datetime | None:
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _read_ndjson_records(path: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if int(limit) <= 0:
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    records.append(record)
        return _sanitize(list(reversed(records)))
    return _sanitize(read_recent_ndjson_records(path, limit=max(0, int(limit)), max_bytes=32_000_000))


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
