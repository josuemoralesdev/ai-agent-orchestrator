"""R155 full-spectrum betrayal and short strategy review.

This module is diagnostic/audit only. It composes local paper outcome,
expanded paper watch, lane-control, and betrayal/inverse evidence to recommend
the next review door without changing lane config or creating execution
authority.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_shadow_outcomes import RESOLVED_STATUSES, SHADOW_LOSS, SHADOW_WIN
from src.app.hammer_radar.operator.expanded_paper_watch import (
    build_expanded_paper_distribution,
    build_expanded_paper_safe_watch_command,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE, load_lane_controls, normalize_lane_key
from src.app.hammer_radar.operator.paper_execution import load_paper_executions
from src.app.hammer_radar.operator.paper_opportunity_expansion import TARGET_ENTRY_MODE, TARGET_SYMBOL
from src.app.hammer_radar.operator.promotion_candidate_audit import (
    build_lane_family_key,
    build_lane_family_opportunity_summary,
    build_lane_family_performance_summary,
    load_recent_expanded_paper_watch_records,
)

FULL_SPECTRUM_BETRAYAL_REVIEW_READY = "FULL_SPECTRUM_BETRAYAL_REVIEW_READY"
FULL_SPECTRUM_BETRAYAL_REVIEW_REJECTED = "FULL_SPECTRUM_BETRAYAL_REVIEW_REJECTED"
FULL_SPECTRUM_BETRAYAL_REVIEW_RECORDED = "FULL_SPECTRUM_BETRAYAL_REVIEW_RECORDED"
FULL_SPECTRUM_BETRAYAL_REVIEW_BLOCKED = "FULL_SPECTRUM_BETRAYAL_REVIEW_BLOCKED"
FULL_SPECTRUM_BETRAYAL_REVIEW_ERROR = "FULL_SPECTRUM_BETRAYAL_REVIEW_ERROR"

NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"
PAPER_ONLY_CONTINUE_COLLECTING = "PAPER_ONLY_CONTINUE_COLLECTING"
SHORT_STRATEGY_REVIEW_REQUIRED = "SHORT_STRATEGY_REVIEW_REQUIRED"
WATCHLIST_FOR_FUTURE_TINY_LIVE = "WATCHLIST_FOR_FUTURE_TINY_LIVE"
STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW = "STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW"
INCUMBENT_TINY_LIVE_SHOULD_BE_REVIEWED = "INCUMBENT_TINY_LIVE_SHOULD_BE_REVIEWED"
DO_NOT_PROMOTE = "DO_NOT_PROMOTE"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "FULL_SPECTRUM_BETRAYAL_SHORT_REVIEW"
LEDGER_FILENAME = "full_spectrum_betrayal_short_reviews.ndjson"
CONFIRM_FULL_SPECTRUM_REVIEW_RECORDING_PHRASE = (
    "I CONFIRM FULL SPECTRUM BETRAYAL REVIEW RECORDING ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
)

FULL_SPECTRUM_TIMEFRAMES = ("4m", "8m", "13m", "22m", "44m", "55m", "88m", "222m", "4h", "444m", "666m", "888m")
DIRECTIONS = ("long", "short")
PRIMARY_ENTRY_MODE = TARGET_ENTRY_MODE
ENTRY_MODES = (
    PRIMARY_ENTRY_MODE,
    "fib_618",
    "fib_650",
    "market_close",
    "ladder_22_44_22",
    "ladder_382_50_618",
)
TINY_LIVE_INCUMBENTS = {
    "BTCUSDT|13m|long|ladder_close_50_618",
    "BTCUSDT|44m|long|ladder_close_50_618",
}

DEFAULT_LATEST_OUTCOMES = 10000
MAX_LATEST_OUTCOMES = 100000
DEFAULT_LATEST_SIGNALS = 3000
MAX_LATEST_SIGNALS = 50000
DEFAULT_LATEST_BETRAYAL = 5000
MAX_LATEST_BETRAYAL = 50000
DEFAULT_LATEST_WATCH_RECORDS = 500
MAX_LATEST_WATCH_RECORDS = 10000

MIN_USABLE_OUTCOMES = 30
MIN_FRESH_CANDIDATES = 10
MIN_BETRAYAL_USABLE_SAMPLE = 30

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "network_allowed": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/outcomes.ndjson",
    "logs/hammer_radar_forward/paper_executions.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "logs/hammer_radar_forward/expanded_paper_watch.ndjson",
    "operator.promotion_candidate_audit build_lane_family_performance_summary",
    "operator.expanded_paper_watch.build_expanded_paper_distribution",
    "operator.lane_control.load_lane_controls",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_full_spectrum_betrayal_short_review(
    *,
    log_dir: str | Path | None = None,
    latest_outcomes: int = DEFAULT_LATEST_OUTCOMES,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_betrayal: int = DEFAULT_LATEST_BETRAYAL,
    latest_watch_records: int = DEFAULT_LATEST_WATCH_RECORDS,
    include_paper_lanes: bool = False,
    include_tiny_live_incumbents: bool = False,
    include_betrayal_inverse: bool = False,
    record_review: bool = False,
    confirm_full_spectrum_review: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_full_spectrum_review == CONFIRM_FULL_SPECTRUM_REVIEW_RECORDING_PHRASE
    try:
        scope = build_full_spectrum_lane_family_scope(
            include_paper_lanes=include_paper_lanes,
            include_tiny_live_incumbents=include_tiny_live_incumbents,
            config_path=config_path,
        )
        outcomes = load_recent_strategy_outcomes(log_dir=resolved_log_dir, limit=latest_outcomes)
        paper_executions = load_paper_executions(limit=0, log_dir=resolved_log_dir)
        betrayal_records = load_recent_betrayal_shadow_outcomes(log_dir=resolved_log_dir, limit=latest_betrayal)
        watch_records = load_recent_expanded_paper_watch_records(log_dir=resolved_log_dir, limit=latest_watch_records)
        distribution = build_expanded_paper_distribution(
            log_dir=resolved_log_dir,
            paper_lanes=scope["lanes"],
            latest_signals=latest_signals,
            latest_scans=latest_signals,
            now=generated_at,
        )

        direction_timeframe_matrix = build_direction_timeframe_matrix(
            scope["lanes"],
            outcome_records=outcomes,
            paper_execution_records=paper_executions,
            current_distribution=distribution,
            watch_records=watch_records,
        )
        entry_mode_matrix = build_entry_mode_matrix(outcome_records=outcomes, signal_distribution=distribution)
        betrayal_inverse_matrix = (
            build_betrayal_inverse_matrix(betrayal_records=betrayal_records, lanes=scope["lanes"])
            if include_betrayal_inverse
            else {}
        )

        lane_families = {}
        for lane in scope["lanes"]:
            lane_key = lane["lane_key"]
            performance = build_lane_family_performance_summary(
                lane,
                outcome_records=outcomes,
                paper_execution_records=paper_executions,
            )
            opportunity = build_lane_family_opportunity_summary(
                lane,
                current_distribution=distribution,
                watch_records=watch_records,
            )
            betrayal = betrayal_inverse_matrix.get(f"{lane['timeframe']}|{lane['direction']}", {})
            score = score_full_spectrum_candidate_family(
                lane=lane,
                performance=performance,
                opportunity=opportunity,
                betrayal_inverse=betrayal,
            )
            readiness = classify_full_spectrum_readiness(
                lane=lane,
                performance=performance,
                opportunity=opportunity,
                betrayal_inverse=betrayal,
                score=score,
            )
            lane_families[lane_key] = {
                "lane_family": lane_key,
                "mode": lane["mode"],
                "direction": lane["direction"],
                "timeframe": lane["timeframe"],
                "entry_mode": lane["entry_mode"],
                "performance": performance,
                "opportunity": opportunity,
                "betrayal_inverse": betrayal,
                "score": score,
                "readiness": readiness,
                "why": _why(readiness, lane=lane, performance=performance, opportunity=opportunity, betrayal=betrayal),
                "risks": _risks(lane=lane, performance=performance, opportunity=opportunity, betrayal=betrayal, readiness=readiness),
                "recommended_next_action": _recommended_lane_action(lane=lane, readiness=readiness),
            }

        candidate_rankings = _ranked_candidates(lane_families)
        short_strategy_review = build_short_strategy_review(candidate_rankings=candidate_rankings, lane_families=lane_families)
        incumbent_review = _incumbent_tiny_live_review(lane_families)
        next_door = build_next_tiny_live_candidate_door_recommendation(
            candidate_rankings=candidate_rankings,
            short_strategy_review=short_strategy_review,
            incumbent_tiny_live_review=incumbent_review,
        )
        status = FULL_SPECTRUM_BETRAYAL_REVIEW_READY if scope["lanes"] else FULL_SPECTRUM_BETRAYAL_REVIEW_BLOCKED
        if record_review and not confirmation_valid:
            status = FULL_SPECTRUM_BETRAYAL_REVIEW_REJECTED
        elif record_review and confirmation_valid:
            status = FULL_SPECTRUM_BETRAYAL_REVIEW_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "audit_recorded": False,
            "audit_id": None,
            "record_audit_requested": bool(record_review),
            "confirmation_valid": bool(confirmation_valid),
            "scope": scope["scope"],
            "direction_timeframe_matrix": direction_timeframe_matrix,
            "entry_mode_matrix": entry_mode_matrix,
            "betrayal_inverse_matrix": betrayal_inverse_matrix,
            "short_strategy_review": short_strategy_review,
            "candidate_rankings": candidate_rankings,
            "incumbent_tiny_live_review": incumbent_review,
            "next_tiny_live_candidate_door": next_door,
            "recommended_next_operator_move": _recommended_next_operator_move(next_door, candidate_rankings, incumbent_review),
            "recommended_next_engineering_move": _recommended_next_engineering_move(next_door),
            "safe_commands": _safe_commands(),
            "do_not_run_yet": [
                "live-connector-submit",
                "any order endpoint",
                "global live flag arming",
                "kill switch disable",
                "set short lane tiny_live",
                "set new lane tiny_live",
            ],
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_review and confirmation_valid:
            record = append_full_spectrum_betrayal_review_record(payload, log_dir=resolved_log_dir)
            payload["audit_recorded"] = True
            payload["audit_id"] = record["audit_id"]
            payload["ledger_path"] = str(full_spectrum_betrayal_review_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": FULL_SPECTRUM_BETRAYAL_REVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "audit_recorded": False,
                "audit_id": None,
                "record_audit_requested": bool(record_review),
                "confirmation_valid": bool(confirmation_valid),
                "scope": {"symbol": TARGET_SYMBOL, "timeframes": list(FULL_SPECTRUM_TIMEFRAMES), "directions": list(DIRECTIONS), "entry_modes": list(ENTRY_MODES)},
                "direction_timeframe_matrix": {},
                "entry_mode_matrix": {},
                "betrayal_inverse_matrix": {},
                "short_strategy_review": _empty_short_strategy_review(),
                "candidate_rankings": [],
                "incumbent_tiny_live_review": {},
                "next_tiny_live_candidate_door": {
                    "recommended_family": None,
                    "recommendation_type": "PAPER_CONTINUE",
                    "operator_summary": "R155 review failed before candidate door selection.",
                    "requires_future_operator_approval": True,
                    "config_change_allowed_now": False,
                },
                "recommended_next_operator_move": "KEEP_COLLECTING_EVIDENCE",
                "recommended_next_engineering_move": "Fix the R155 audit error before considering any strategy packet.",
                "safe_commands": _safe_commands(),
                "do_not_run_yet": [
                    "live-connector-submit",
                    "any order endpoint",
                    "global live flag arming",
                    "kill switch disable",
                    "set short lane tiny_live",
                    "set new lane tiny_live",
                ],
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_full_spectrum_lane_family_scope(
    *,
    include_paper_lanes: bool = False,
    include_tiny_live_incumbents: bool = False,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    controls = load_lane_controls(Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH)
    configured = {str(lane.get("lane_key") or build_lane_family_key(lane)): _compact_lane(lane) for lane in controls.get("lanes") or []}
    lanes = []
    for timeframe in FULL_SPECTRUM_TIMEFRAMES:
        for direction in DIRECTIONS:
            lane_key = normalize_lane_key(TARGET_SYMBOL, timeframe, direction, PRIMARY_ENTRY_MODE)
            lane = configured.get(lane_key) or _synthetic_lane(timeframe, direction)
            if lane["mode"] == "paper" and not include_paper_lanes:
                continue
            if lane["mode"] == "tiny_live" and not include_tiny_live_incumbents:
                continue
            if lane["mode"] == "disabled" and not include_paper_lanes:
                continue
            lanes.append(lane)
    return {
        "lanes": sorted(lanes, key=lambda lane: _lane_sort_key(lane["lane_key"])),
        "scope": {
            "symbol": TARGET_SYMBOL,
            "timeframes": list(FULL_SPECTRUM_TIMEFRAMES),
            "directions": list(DIRECTIONS),
            "entry_modes": list(ENTRY_MODES),
            "primary_entry_mode": PRIMARY_ENTRY_MODE,
            "configured_lane_count": len(configured),
            "synthetic_review_only_lanes": sum(1 for lane in lanes if lane["mode"] == "disabled"),
        },
    }


def load_recent_strategy_outcomes(*, log_dir: str | Path | None = None, limit: int = DEFAULT_LATEST_OUTCOMES) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    bounded = _bounded_int(limit, 1, MAX_LATEST_OUTCOMES, DEFAULT_LATEST_OUTCOMES)
    path = resolved_log_dir / "outcomes.ndjson"
    if not path.exists():
        return []
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=bounded, max_bytes=64_000_000)]


def load_recent_betrayal_shadow_outcomes(
    *,
    log_dir: str | Path | None = None,
    limit: int = DEFAULT_LATEST_BETRAYAL,
) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    bounded = _bounded_int(limit, 1, MAX_LATEST_BETRAYAL, DEFAULT_LATEST_BETRAYAL)
    path = resolved_log_dir / "betrayal_shadow_outcomes.ndjson"
    if not path.exists():
        return []
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=bounded, max_bytes=64_000_000)]


def build_direction_timeframe_matrix(
    lanes: list[Mapping[str, Any]],
    *,
    outcome_records: list[Mapping[str, Any]] | None = None,
    paper_execution_records: list[Mapping[str, Any]] | None = None,
    current_distribution: Mapping[str, Any] | None = None,
    watch_records: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    matrix = {}
    for lane in lanes:
        key = f"{lane['timeframe']}|{lane['direction']}"
        performance = build_lane_family_performance_summary(lane, outcome_records=outcome_records, paper_execution_records=paper_execution_records)
        opportunity = build_lane_family_opportunity_summary(lane, current_distribution=current_distribution, watch_records=watch_records)
        matrix[key] = {
            "lane_family": lane["lane_key"],
            "mode": lane["mode"],
            "timeframe": lane["timeframe"],
            "direction": lane["direction"],
            "entry_mode": lane["entry_mode"],
            "paper_outcome_count": performance["paper_outcome_count"],
            "win_rate_pct": performance["win_rate_pct"],
            "avg_pnl_pct": performance["avg_pnl_pct"],
            "stop_count": performance["stop_count"],
            "fresh_candidate_count": opportunity["fresh_candidate_count"],
            "sample_count_quality": performance["sample_count_quality"],
        }
    return dict(sorted(matrix.items(), key=lambda item: _timeframe_direction_sort_key(item[0])))


def build_entry_mode_matrix(
    *,
    outcome_records: list[Mapping[str, Any]] | None = None,
    signal_distribution: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    outcomes_by_mode: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in outcome_records or []:
        entry_mode = _entry_mode(record)
        outcomes_by_mode[entry_mode].append(record)
    signal_by_mode = Counter()
    for lane_key, candidates in (signal_distribution or {}).get("paper_lane_candidates", {}).items():
        parts = str(lane_key).split("|")
        entry_mode = parts[3] if len(parts) >= 4 else PRIMARY_ENTRY_MODE
        signal_by_mode[entry_mode] += len(candidates or [])
    matrix = {}
    for entry_mode in ENTRY_MODES:
        rows = outcomes_by_mode.get(entry_mode, [])
        filled = [row for row in rows if _number_or_none(row.get("pnl_pct")) is not None]
        pnl_values = [float(row.get("pnl_pct")) for row in filled]
        wins = sum(1 for value in pnl_values if value > 0.0)
        matrix[entry_mode] = {
            "paper_outcome_count": len(filled),
            "win_rate_pct": round((wins / len(filled)) * 100.0, 2) if filled else None,
            "avg_pnl_pct": round(sum(pnl_values) / len(filled), 4) if filled else None,
            "fresh_candidate_examples_seen": int(signal_by_mode.get(entry_mode) or 0),
            "ranking_focus": entry_mode == PRIMARY_ENTRY_MODE,
        }
    return matrix


def build_betrayal_inverse_matrix(
    *,
    betrayal_records: list[Mapping[str, Any]] | None = None,
    lanes: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in betrayal_records or []:
        timeframe = _normalize_timeframe(record.get("timeframe"))
        inverse_direction = _normalize_direction(record.get("shadow_direction"))
        original_direction = _normalize_direction(record.get("original_direction"))
        direction = inverse_direction or _invert_direction(original_direction)
        if timeframe and direction:
            groups[f"{timeframe}|{direction}"].append(record)
    keys = {f"{lane['timeframe']}|{lane['direction']}" for lane in lanes or []}
    keys.update(groups)
    matrix = {}
    for key in sorted(keys, key=_timeframe_direction_sort_key):
        records = groups.get(key, [])
        resolved = [record for record in records if record.get("shadow_status") in RESOLVED_STATUSES]
        inverse_wins = [record for record in resolved if record.get("shadow_status") == SHADOW_WIN]
        inverse_losses = [record for record in resolved if record.get("shadow_status") == SHADOW_LOSS]
        inverse_pnl = [_number_or_none(record.get("shadow_pnl_pct")) for record in resolved]
        inverse_pnl_values = [float(value) for value in inverse_pnl if value is not None]
        original_summaries = [record.get("original_outcome_summary") for record in records if isinstance(record.get("original_outcome_summary"), Mapping)]
        original_wins = sum(int(summary.get("wins") or 0) for summary in original_summaries)
        original_losses = sum(int(summary.get("losses") or 0) for summary in original_summaries)
        original_sample = original_wins + original_losses
        inverse_sample = len(resolved)
        inverse_win_rate = round((len(inverse_wins) / inverse_sample) * 100.0, 2) if inverse_sample else None
        original_win_rate = round((original_wins / original_sample) * 100.0, 2) if original_sample else None
        matrix[key] = {
            "sample_count": inverse_sample,
            "total_shadow_records": len(records),
            "original_win_rate_pct": original_win_rate,
            "inverse_win_rate_pct": inverse_win_rate,
            "inverse_avg_pnl_pct": round(sum(inverse_pnl_values) / len(inverse_pnl_values), 4) if inverse_pnl_values else None,
            "inverse_advantage_pct": round(inverse_win_rate - original_win_rate, 2) if inverse_win_rate is not None and original_win_rate is not None else None,
            "inverse_wins": len(inverse_wins),
            "inverse_losses": len(inverse_losses),
            "confidence": _betrayal_confidence(inverse_sample),
        }
    return matrix


def build_short_strategy_review(
    *,
    candidate_rankings: list[Mapping[str, Any]],
    lane_families: Mapping[str, Any],
) -> dict[str, Any]:
    shorts = [row for row in candidate_rankings if row.get("direction") == "short"]
    best = shorts[0] if shorts else None
    return {
        "shorts_seen": bool(shorts) or any(row.get("direction") == "short" for row in lane_families.values()),
        "best_short_family": best.get("lane_family") if best else None,
        "short_golden_pocket_interpretation": "resistance/retrace zone",
        "requires_future_short_strategy_review": True,
        "shorts_remain_paper_only": True,
        "notes": [
            "For short candidates, the golden pocket acts as resistance/retrace zone, not support.",
            "R155 does not set any short lane to tiny_live.",
            "Future short tiny-live requires a separate short strategy packet and explicit operator approval.",
        ],
    }


def score_full_spectrum_candidate_family(
    *,
    lane: Mapping[str, Any],
    performance: Mapping[str, Any],
    opportunity: Mapping[str, Any],
    betrayal_inverse: Mapping[str, Any] | None = None,
) -> int:
    score = 0
    outcomes = int(performance.get("paper_outcome_count") or 0)
    fresh = int(opportunity.get("fresh_candidate_count") or 0)
    win_rate = _number_or_none(performance.get("win_rate_pct"))
    avg_pnl = _number_or_none(performance.get("avg_pnl_pct"))
    total_pnl = _number_or_none(performance.get("total_pnl_pct"))
    stops = int(performance.get("stop_count") or 0)
    inverse_sample = int((betrayal_inverse or {}).get("sample_count") or 0)
    inverse_advantage = _number_or_none((betrayal_inverse or {}).get("inverse_advantage_pct"))
    inverse_avg = _number_or_none((betrayal_inverse or {}).get("inverse_avg_pnl_pct"))

    score += min(24, int((outcomes / MIN_USABLE_OUTCOMES) * 24)) if outcomes else 0
    score += min(18, int((fresh / MIN_FRESH_CANDIDATES) * 18)) if fresh else 0
    if win_rate is not None:
        score += 18 if win_rate >= 55.0 else max(0, int((win_rate / 55.0) * 14))
    if avg_pnl is not None and avg_pnl > 0.0:
        score += 12
    if total_pnl is not None and total_pnl > 0.0:
        score += 8
    if inverse_sample >= MIN_BETRAYAL_USABLE_SAMPLE and inverse_advantage is not None and inverse_advantage > 0:
        score += min(15, int(inverse_advantage / 2))
        if inverse_avg is not None and inverse_avg > 0.0:
            score += 5
    elif inverse_sample > 0 and inverse_advantage is not None and inverse_advantage > 0:
        score += min(5, int(inverse_advantage / 5))
    if outcomes and stops / outcomes > 0.5:
        score -= 25
    if lane.get("mode") == "disabled":
        score = min(score, 45)
    if outcomes < 5:
        score = min(score, 59)
    return max(0, min(100, score))


def classify_full_spectrum_readiness(
    *,
    lane: Mapping[str, Any],
    performance: Mapping[str, Any],
    opportunity: Mapping[str, Any],
    betrayal_inverse: Mapping[str, Any] | None = None,
    score: int,
) -> str:
    outcomes = int(performance.get("paper_outcome_count") or 0)
    fresh = int(opportunity.get("fresh_candidate_count") or 0)
    stops = int(performance.get("stop_count") or 0)
    avg_pnl = _number_or_none(performance.get("avg_pnl_pct"))
    win_rate = _number_or_none(performance.get("win_rate_pct"))
    inverse_sample = int((betrayal_inverse or {}).get("sample_count") or 0)
    inverse_advantage = _number_or_none((betrayal_inverse or {}).get("inverse_advantage_pct"))
    if lane.get("mode") == "tiny_live" and (outcomes >= MIN_USABLE_OUTCOMES and (avg_pnl is None or avg_pnl <= 0.0 or (win_rate or 0) < 45.0)):
        return INCUMBENT_TINY_LIVE_SHOULD_BE_REVIEWED
    if outcomes <= 0 and fresh <= 0 and inverse_sample <= 0:
        return NOT_ENOUGH_EVIDENCE
    if outcomes and stops / outcomes > 0.6:
        return DO_NOT_PROMOTE
    if outcomes >= MIN_USABLE_OUTCOMES and avg_pnl is not None and avg_pnl <= 0.0:
        return DO_NOT_PROMOTE
    if lane.get("direction") == "short" and score >= 60:
        return SHORT_STRATEGY_REVIEW_REQUIRED
    if inverse_sample < MIN_BETRAYAL_USABLE_SAMPLE and inverse_advantage is not None and inverse_advantage > 0 and outcomes < MIN_USABLE_OUTCOMES:
        return NOT_ENOUGH_EVIDENCE
    if outcomes < MIN_USABLE_OUTCOMES or fresh < MIN_FRESH_CANDIDATES:
        return NOT_ENOUGH_EVIDENCE
    if win_rate is None or avg_pnl is None:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if score >= 75 and win_rate >= 55.0 and avg_pnl > 0.0:
        return STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW
    if score >= 60:
        return WATCHLIST_FOR_FUTURE_TINY_LIVE
    return PAPER_ONLY_CONTINUE_COLLECTING


def build_next_tiny_live_candidate_door_recommendation(
    *,
    candidate_rankings: list[Mapping[str, Any]],
    short_strategy_review: Mapping[str, Any],
    incumbent_tiny_live_review: Mapping[str, Any],
) -> dict[str, Any]:
    best = candidate_rankings[0] if candidate_rankings else None
    review_incumbent = bool(incumbent_tiny_live_review.get("incumbent_review_recommended"))
    if review_incumbent and (not best or int(best.get("score") or 0) < 60):
        return {
            "recommended_family": (incumbent_tiny_live_review.get("incumbent_lane_keys") or [None])[0],
            "recommendation_type": "INCUMBENT_REVIEW",
            "operator_summary": "Existing tiny_live incumbents deserve review before opening a new tiny-live door.",
            "requires_future_operator_approval": True,
            "config_change_allowed_now": False,
        }
    if not best:
        return {
            "recommended_family": None,
            "recommendation_type": "PAPER_CONTINUE",
            "operator_summary": "No full-spectrum family has enough evidence for a promotion packet.",
            "requires_future_operator_approval": True,
            "config_change_allowed_now": False,
        }
    if best.get("direction") == "short":
        return {
            "recommended_family": best.get("lane_family"),
            "recommendation_type": "SHORT_STRATEGY_REVIEW",
            "operator_summary": "The best current door is short-side evidence, but short tiny-live requires a separate strategy review.",
            "requires_future_operator_approval": True,
            "config_change_allowed_now": False,
        }
    if best.get("readiness") == STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW:
        return {
            "recommended_family": best.get("lane_family"),
            "recommendation_type": "PROMOTION_PACKET_REVIEW",
            "operator_summary": "The top long paper lane can be packaged for future promotion review only.",
            "requires_future_operator_approval": True,
            "config_change_allowed_now": False,
        }
    return {
        "recommended_family": best.get("lane_family"),
        "recommendation_type": "PAPER_CONTINUE",
        "operator_summary": "Continue collecting paper evidence before any tiny-live packet.",
        "requires_future_operator_approval": True,
        "config_change_allowed_now": False,
    }


def append_full_spectrum_betrayal_review_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = full_spectrum_betrayal_review_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "audit_id": record.get("audit_id") or f"full_spectrum_betrayal_review_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "record_audit_requested": bool(record.get("record_audit_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "scope": dict(record.get("scope") or {}),
            "direction_timeframe_matrix": dict(record.get("direction_timeframe_matrix") or {}),
            "entry_mode_matrix": dict(record.get("entry_mode_matrix") or {}),
            "betrayal_inverse_matrix": dict(record.get("betrayal_inverse_matrix") or {}),
            "short_strategy_review": dict(record.get("short_strategy_review") or {}),
            "candidate_rankings": list(record.get("candidate_rankings") or []),
            "incumbent_tiny_live_review": dict(record.get("incumbent_tiny_live_review") or {}),
            "next_tiny_live_candidate_door": dict(record.get("next_tiny_live_candidate_door") or {}),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safe_commands": list(record.get("safe_commands") or []),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_full_spectrum_betrayal_review_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = full_spectrum_betrayal_review_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=limit if limit > 0 else 100000, max_bytes=64_000_000)
    if limit <= 0:
        records = list(reversed(records))
    return [_sanitize(record) for record in records]


def summarize_full_spectrum_betrayal_reviews(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    door = latest.get("next_tiny_live_candidate_door") if isinstance(latest.get("next_tiny_live_candidate_door"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_audit_id": latest.get("audit_id"),
        "last_recommended_family": door.get("recommended_family"),
        "last_recommendation_type": door.get("recommendation_type"),
        "safety": dict(SAFETY),
    }


def full_spectrum_betrayal_review_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_full_spectrum_betrayal_review_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _ranked_candidates(lane_families: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for lane_key, payload in lane_families.items():
        if payload.get("mode") not in {"paper", "tiny_live"}:
            continue
        rows.append(
            {
                "lane_family": lane_key,
                "mode": payload.get("mode"),
                "direction": payload.get("direction"),
                "timeframe": payload.get("timeframe"),
                "entry_mode": payload.get("entry_mode"),
                "score": payload.get("score"),
                "readiness": payload.get("readiness"),
                "why": payload.get("why"),
                "risks": list(payload.get("risks") or []),
                "recommended_next_action": payload.get("recommended_next_action"),
            }
        )
    return sorted(rows, key=lambda row: (-int(row.get("score") or 0), _lane_sort_key(str(row.get("lane_family") or ""))))


def _incumbent_tiny_live_review(lane_families: Mapping[str, Any]) -> dict[str, Any]:
    incumbents = {key: value for key, value in lane_families.items() if value.get("mode") == "tiny_live"}
    review = any(value.get("readiness") in {INCUMBENT_TINY_LIVE_SHOULD_BE_REVIEWED, DO_NOT_PROMOTE} for value in incumbents.values())
    return {
        "incumbents_seen": bool(incumbents),
        "incumbent_lane_keys": sorted(incumbents),
        "review_only": True,
        "mode_changes_recommended": False,
        "incumbent_review_recommended": review,
        "lanes": incumbents,
    }


def _recommended_next_operator_move(
    next_door: Mapping[str, Any],
    candidate_rankings: list[Mapping[str, Any]],
    incumbent_review: Mapping[str, Any],
) -> str:
    rec_type = next_door.get("recommendation_type")
    if rec_type == "SHORT_STRATEGY_REVIEW":
        return "RUN_R156_SHORT_STRATEGY_PACKET"
    if rec_type == "PROMOTION_PACKET_REVIEW":
        return "RUN_R156_TOP_LANE_PROMOTION_PACKET"
    if rec_type == "INCUMBENT_REVIEW" or incumbent_review.get("incumbent_review_recommended"):
        return "REVIEW_INCUMBENT_TINY_LIVE_LANES"
    if candidate_rankings:
        return "RUN_EXPANDED_PAPER_WATCH"
    return "KEEP_COLLECTING_EVIDENCE"


def _recommended_next_engineering_move(next_door: Mapping[str, Any]) -> str:
    rec_type = next_door.get("recommendation_type")
    if rec_type == "SHORT_STRATEGY_REVIEW":
        return "Build R156 short strategy packet with resistance/retrace golden-pocket interpretation and paper-only thresholds."
    if rec_type == "PROMOTION_PACKET_REVIEW":
        return "Build R156 top-lane promotion packet review without lane mode changes."
    if rec_type == "INCUMBENT_REVIEW":
        return "Review incumbent tiny_live lanes against expanded paper evidence before opening a new door."
    return "Keep collecting expanded paper and betrayal inverse evidence; do not change lane modes."


def _safe_commands() -> list[str]:
    review_record = (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward full-spectrum-betrayal-short-review "
        "--latest-outcomes 10000 --latest-signals 3000 --latest-betrayal 5000 --latest-watch-records 500 "
        "--include-paper-lanes --include-tiny-live-incumbents --include-betrayal-inverse "
        "--record-review --confirm-full-spectrum-review "
        f'"{CONFIRM_FULL_SPECTRUM_REVIEW_RECORDING_PHRASE}"'
    )
    return [
        build_expanded_paper_safe_watch_command(record=False),
        build_expanded_paper_safe_watch_command(record=True),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward promotion-candidate-audit "
            "--latest-outcomes 5000 --latest-signals 2000 --latest-watch-records 200 "
            "--include-paper-lanes --include-tiny-live-incumbents"
        ),
        review_record,
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward candidate-source-freshness-audit "
            "--latest-signals 1000 --latest-scans 2000"
        ),
    ]


def _compact_lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_key": str(lane.get("lane_key") or build_lane_family_key(lane)),
        "symbol": str(lane.get("symbol") or TARGET_SYMBOL).strip().upper(),
        "timeframe": _normalize_timeframe(lane.get("timeframe")),
        "direction": _normalize_direction(lane.get("direction")),
        "entry_mode": str(lane.get("entry_mode") or PRIMARY_ENTRY_MODE).strip().lower(),
        "mode": str(lane.get("mode") or "disabled").strip().lower(),
        "max_daily_trades": int(lane.get("max_daily_trades") or 0),
        "max_daily_loss_pct": float(lane.get("max_daily_loss_pct") or 0.0),
        "freshness_seconds": int(lane.get("freshness_seconds") or 0),
        "cooldown_after_loss_minutes": int(lane.get("cooldown_after_loss_minutes") or 0),
        "require_protective_orders": bool(lane.get("require_protective_orders")),
    }


def _synthetic_lane(timeframe: str, direction: str) -> dict[str, Any]:
    return {
        "lane_key": normalize_lane_key(TARGET_SYMBOL, timeframe, direction, PRIMARY_ENTRY_MODE),
        "symbol": TARGET_SYMBOL,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": PRIMARY_ENTRY_MODE,
        "mode": "disabled",
        "max_daily_trades": 0,
        "max_daily_loss_pct": 0.0,
        "freshness_seconds": 0,
        "cooldown_after_loss_minutes": 0,
        "require_protective_orders": True,
    }


def _why(readiness: str, *, lane: Mapping[str, Any], performance: Mapping[str, Any], opportunity: Mapping[str, Any], betrayal: Mapping[str, Any]) -> str:
    if readiness == SHORT_STRATEGY_REVIEW_REQUIRED:
        return "Short-side evidence is notable, but short tiny-live requires a separate strategy review and approval."
    if readiness == INCUMBENT_TINY_LIVE_SHOULD_BE_REVIEWED:
        return "Incumbent tiny_live lane has enough unfavorable evidence to deserve review; no mode change is made here."
    if readiness == STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW:
        return "Paper outcomes, PnL, freshness, and score justify a future review packet only."
    if readiness == DO_NOT_PROMOTE:
        return "Performance is negative or stop dominated."
    if readiness == NOT_ENOUGH_EVIDENCE:
        return "Sample quality is not sufficient for a tiny-live candidate packet."
    return "Continue collecting full-spectrum paper and betrayal evidence."


def _risks(*, lane: Mapping[str, Any], performance: Mapping[str, Any], opportunity: Mapping[str, Any], betrayal: Mapping[str, Any], readiness: str) -> list[str]:
    risks = []
    if int(performance.get("paper_outcome_count") or 0) < MIN_USABLE_OUTCOMES:
        risks.append("paper outcome sample below usable threshold")
    if int(opportunity.get("fresh_candidate_count") or 0) < MIN_FRESH_CANDIDATES:
        risks.append("fresh candidate sample below preferred threshold")
    if lane.get("direction") == "short":
        risks.append("short tiny-live requires future short strategy review")
    if int(betrayal.get("sample_count") or 0) and int(betrayal.get("sample_count") or 0) < MIN_BETRAYAL_USABLE_SAMPLE:
        risks.append("betrayal inverse sample too low to dominate ranking")
    if readiness == DO_NOT_PROMOTE:
        risks.append("do not promote based on current evidence")
    return risks


def _recommended_lane_action(*, lane: Mapping[str, Any], readiness: str) -> str:
    if lane.get("direction") == "short" and readiness in {SHORT_STRATEGY_REVIEW_REQUIRED, WATCHLIST_FOR_FUTURE_TINY_LIVE, STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW}:
        return "RUN_R156_SHORT_STRATEGY_PACKET"
    if readiness == STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW:
        return "RUN_R156_TOP_LANE_PROMOTION_PACKET"
    if readiness == INCUMBENT_TINY_LIVE_SHOULD_BE_REVIEWED:
        return "REVIEW_INCUMBENT_TINY_LIVE_LANE"
    return "KEEP_COLLECTING_EVIDENCE"


def _empty_short_strategy_review() -> dict[str, Any]:
    return {
        "shorts_seen": False,
        "best_short_family": None,
        "short_golden_pocket_interpretation": "resistance/retrace zone",
        "requires_future_short_strategy_review": True,
        "shorts_remain_paper_only": True,
        "notes": ["For short candidates, the golden pocket acts as resistance/retrace zone, not support."],
    }


def _entry_mode(record: Mapping[str, Any]) -> str:
    ticket = record.get("ticket") if isinstance(record.get("ticket"), Mapping) else {}
    return str(_first_present(record, "entry_mode", "mode") or _first_present(ticket, "entry_mode") or PRIMARY_ENTRY_MODE).strip().lower()


def _normalize_direction(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"buy", "bull", "bullish"}:
        return "long"
    if text in {"sell", "bear", "bearish"}:
        return "short"
    return text


def _invert_direction(value: str) -> str | None:
    if value == "long":
        return "short"
    if value == "short":
        return "long"
    return None


def _normalize_timeframe(value: object) -> str:
    text = str(value or "").strip().lower()
    return "4h" if text == "4H" else text


def _betrayal_confidence(sample_count: int) -> str:
    if sample_count <= 0:
        return "UNKNOWN"
    if sample_count < 10:
        return "LOW"
    if sample_count < MIN_BETRAYAL_USABLE_SAMPLE:
        return "MEDIUM"
    return "HIGH"


def _bounded_int(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _number_or_none(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _lane_sort_key(value: str) -> tuple[int, str, str, str]:
    symbol, timeframe, direction, entry_mode = (str(value).split("|") + ["", "", "", ""])[:4]
    return (*_timeframe_sort_key(timeframe), direction, entry_mode or symbol)


def _timeframe_direction_sort_key(value: str) -> tuple[int, str, str]:
    timeframe, _, direction = str(value).partition("|")
    return (*_timeframe_sort_key(timeframe), direction)


def _timeframe_sort_key(value: str) -> tuple[int, str]:
    text = _normalize_timeframe(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    unit = "".join(ch for ch in text if ch.isalpha())
    multiplier = {"m": 1, "h": 60, "d": 1440}.get(unit or "m", 1)
    return (int(digits or 0) * multiplier, text)


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized = {str(key): _sanitize(item) for key, item in value.items()}
        for key, expected in SAFETY.items():
            if key in sanitized:
                sanitized[key] = expected
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
