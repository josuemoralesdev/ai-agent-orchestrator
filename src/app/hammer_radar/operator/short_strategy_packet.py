"""R156 short strategy packet for the BTCUSDT 8m short paper lane.

This module is diagnostic/audit only. It composes existing local evidence into
a short-side strategy review packet and never creates execution authority,
order payloads, signed requests, Binance calls, env mutations, or lane config
changes.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.expanded_paper_watch import (
    build_expanded_paper_distribution,
    build_expanded_paper_safe_watch_command,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_betrayal_short_review import (
    build_betrayal_inverse_matrix,
    load_recent_betrayal_shadow_outcomes,
)
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE, load_lane_controls, normalize_lane_key
from src.app.hammer_radar.operator.paper_execution import load_paper_executions
from src.app.hammer_radar.operator.paper_opportunity_expansion import TARGET_ENTRY_MODE, TARGET_SYMBOL
from src.app.hammer_radar.operator.promotion_candidate_audit import (
    build_lane_family_opportunity_summary,
    build_lane_family_performance_summary,
    load_recent_expanded_paper_watch_records,
    load_recent_outcome_records,
)

SHORT_STRATEGY_PACKET_READY = "SHORT_STRATEGY_PACKET_READY"
SHORT_STRATEGY_PACKET_REJECTED = "SHORT_STRATEGY_PACKET_REJECTED"
SHORT_STRATEGY_PACKET_RECORDED = "SHORT_STRATEGY_PACKET_RECORDED"
SHORT_STRATEGY_PACKET_BLOCKED = "SHORT_STRATEGY_PACKET_BLOCKED"
SHORT_STRATEGY_PACKET_ERROR = "SHORT_STRATEGY_PACKET_ERROR"

PAPER_ONLY_NOT_READY = "PAPER_ONLY_NOT_READY"
PAPER_ONLY_COLLECT_MORE_EVIDENCE = "PAPER_ONLY_COLLECT_MORE_EVIDENCE"
SHORT_STRATEGY_REVIEW_READY = "SHORT_STRATEGY_REVIEW_READY"
STRONG_SHORT_PAPER_CANDIDATE_REQUIRES_OPERATOR_REVIEW = "STRONG_SHORT_PAPER_CANDIDATE_REQUIRES_OPERATOR_REVIEW"
DO_NOT_PROMOTE = "DO_NOT_PROMOTE"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "SHORT_STRATEGY_PACKET"
LEDGER_FILENAME = "short_strategy_packets.ndjson"
DEFAULT_TARGET_LANE_KEY = "BTCUSDT|8m|short|ladder_close_50_618"
CONFIRM_SHORT_STRATEGY_PACKET_RECORDING_PHRASE = (
    "I CONFIRM SHORT STRATEGY PACKET RECORDING ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_OUTCOMES = 10000
MAX_LATEST_OUTCOMES = 100000
DEFAULT_LATEST_SIGNALS = 3000
MAX_LATEST_SIGNALS = 50000
DEFAULT_LATEST_BETRAYAL = 5000
MAX_LATEST_BETRAYAL = 50000
DEFAULT_LATEST_WATCH_RECORDS = 500
MAX_LATEST_WATCH_RECORDS = 10000

MIN_PAPER_OUTCOMES = 30
MIN_FRESH_CANDIDATES = 10
PREFERRED_WIN_RATE_PCT = 52.0

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
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "logs/hammer_radar_forward/expanded_paper_watch.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "operator.promotion_candidate_audit build_lane_family_performance_summary",
    "operator.promotion_candidate_audit build_lane_family_opportunity_summary",
    "operator.expanded_paper_watch.build_expanded_paper_distribution",
    "operator.full_spectrum_betrayal_short_review.build_betrayal_inverse_matrix",
    "operator.lane_control.load_lane_controls",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_short_strategy_packet(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_outcomes: int = DEFAULT_LATEST_OUTCOMES,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_betrayal: int = DEFAULT_LATEST_BETRAYAL,
    latest_watch_records: int = DEFAULT_LATEST_WATCH_RECORDS,
    record_packet: bool = False,
    confirm_short_strategy_packet: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_short_strategy_packet == CONFIRM_SHORT_STRATEGY_PACKET_RECORDING_PHRASE
    try:
        target = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)
        evidence = load_short_family_recent_evidence(
            log_dir=resolved_log_dir,
            target_family=target,
            latest_outcomes=latest_outcomes,
            latest_signals=latest_signals,
            latest_betrayal=latest_betrayal,
            latest_watch_records=latest_watch_records,
            now=generated_at,
        )
        interpretation = build_short_golden_pocket_interpretation(target)
        stop_tp_review = build_short_stop_tp_review(target_family=target, evidence_summary=evidence)
        thresholds = build_short_evidence_thresholds()
        readiness = classify_short_strategy_readiness(target_family=target, evidence_summary=evidence)
        blockers = _blockers_to_tiny_live(target_family=target, evidence_summary=evidence, readiness=readiness)
        status = (
            SHORT_STRATEGY_PACKET_READY
            if target.get("direction") == "short" and target.get("current_mode") == "paper"
            else SHORT_STRATEGY_PACKET_BLOCKED
        )
        if record_packet and not confirmation_valid:
            status = SHORT_STRATEGY_PACKET_REJECTED
        elif record_packet and confirmation_valid:
            status = SHORT_STRATEGY_PACKET_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "packet_recorded": False,
            "packet_id": None,
            "record_packet_requested": bool(record_packet),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": target,
            "short_strategy_interpretation": interpretation,
            "stop_tp_review": stop_tp_review,
            "evidence_summary": evidence,
            "thresholds_for_future_review": thresholds,
            "readiness": readiness,
            "why": _why(readiness, target_family=target, evidence_summary=evidence),
            "blockers_to_tiny_live": blockers,
            "paper_tracking_plan": build_short_paper_tracking_plan(target_family=target),
            "recommended_next_operator_move": build_short_strategy_next_action(readiness, record_packet=record_packet, confirmation_valid=confirmation_valid),
            "recommended_next_engineering_move": _recommended_next_engineering_move(readiness),
            "do_not_run_yet": [
                "live-connector-submit",
                "any order endpoint",
                "global live flag arming",
                "kill switch disable",
                "set short lane tiny_live",
                "set new lane tiny_live",
            ],
            "safe_commands": _safe_commands(target["lane_key"]),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_packet and confirmation_valid:
            record = append_short_strategy_packet_record(payload, log_dir=resolved_log_dir)
            payload["packet_recorded"] = True
            payload["packet_id"] = record["packet_id"]
            payload["ledger_path"] = str(short_strategy_packet_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": SHORT_STRATEGY_PACKET_ERROR,
                "generated_at": generated_at.isoformat(),
                "packet_recorded": False,
                "packet_id": None,
                "record_packet_requested": bool(record_packet),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": _target_from_key(lane_key, mode="unknown"),
                "short_strategy_interpretation": build_short_golden_pocket_interpretation(_target_from_key(lane_key, mode="unknown")),
                "stop_tp_review": {},
                "evidence_summary": _empty_evidence_summary(),
                "thresholds_for_future_review": build_short_evidence_thresholds(),
                "readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "why": "R156 packet builder hit an error before evidence could be interpreted.",
                "blockers_to_tiny_live": ["packet build error must be fixed before any future review"],
                "paper_tracking_plan": build_short_paper_tracking_plan(target_family=_target_from_key(lane_key, mode="unknown")),
                "recommended_next_operator_move": "WAIT_FOR_MORE_SHORT_EVIDENCE",
                "recommended_next_engineering_move": "Fix the R156 short strategy packet error before any review.",
                "do_not_run_yet": [
                    "live-connector-submit",
                    "any order endpoint",
                    "global live flag arming",
                    "kill switch disable",
                    "set short lane tiny_live",
                    "set new lane tiny_live",
                ],
                "safe_commands": _safe_commands(lane_key),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_short_strategy_target_family(
    *,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    controls = load_lane_controls(Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH)
    normalized_key = _normalize_lane_key_text(lane_key)
    lane = (controls.get("lane_map") or {}).get(normalized_key)
    if lane:
        return _compact_target(lane)
    return _target_from_key(normalized_key, mode="disabled")


def load_short_family_recent_evidence(
    *,
    log_dir: str | Path | None = None,
    target_family: Mapping[str, Any] | None = None,
    latest_outcomes: int = DEFAULT_LATEST_OUTCOMES,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_betrayal: int = DEFAULT_LATEST_BETRAYAL,
    latest_watch_records: int = DEFAULT_LATEST_WATCH_RECORDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    target = dict(target_family or build_short_strategy_target_family())
    outcomes = load_recent_outcome_records(log_dir=resolved_log_dir, limit=_bounded_int(latest_outcomes, 1, MAX_LATEST_OUTCOMES, DEFAULT_LATEST_OUTCOMES))
    paper_executions = load_paper_executions(limit=0, log_dir=resolved_log_dir)
    watch_records = load_recent_expanded_paper_watch_records(log_dir=resolved_log_dir, limit=_bounded_int(latest_watch_records, 1, MAX_LATEST_WATCH_RECORDS, DEFAULT_LATEST_WATCH_RECORDS))
    betrayal_records = load_recent_betrayal_shadow_outcomes(log_dir=resolved_log_dir, limit=_bounded_int(latest_betrayal, 1, MAX_LATEST_BETRAYAL, DEFAULT_LATEST_BETRAYAL))
    distribution = build_expanded_paper_distribution(
        log_dir=resolved_log_dir,
        paper_lanes=[target],
        latest_signals=_bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS),
        latest_scans=_bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS),
        now=now or datetime.now(UTC),
    )
    performance = build_lane_family_performance_summary(target, outcome_records=outcomes, paper_execution_records=paper_executions)
    opportunity = build_lane_family_opportunity_summary(target, current_distribution=distribution, watch_records=watch_records)
    inverse_key = f"{target.get('timeframe')}|{target.get('direction')}"
    betrayal_inverse = build_betrayal_inverse_matrix(betrayal_records=betrayal_records, lanes=[target]).get(inverse_key, {})
    return {
        "signal_count": int(performance.get("signal_count") or 0),
        "paper_outcome_count": int(performance.get("paper_outcome_count") or 0),
        "fresh_candidate_count": int(opportunity.get("fresh_candidate_count") or 0),
        "stale_candidate_count": int(opportunity.get("stale_candidate_count") or 0),
        "win_rate_pct": performance.get("win_rate_pct"),
        "avg_pnl_pct": performance.get("avg_pnl_pct"),
        "total_pnl_pct": performance.get("total_pnl_pct"),
        "stop_count": int(performance.get("stop_count") or 0),
        "win_count": int(performance.get("win_count") or 0),
        "loss_count": int(performance.get("loss_count") or 0),
        "paper_execution_count": int(performance.get("paper_execution_count") or 0),
        "fill_rate_pct": performance.get("fill_rate_pct"),
        "freshness_hit_rate_pct": opportunity.get("freshness_hit_rate_pct"),
        "betrayal_inverse_summary": dict(betrayal_inverse),
        "sample_quality": _sample_quality(performance, opportunity),
        "performance": performance,
        "opportunity": opportunity,
    }


def build_short_golden_pocket_interpretation(target_family: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "golden_pocket_role": "resistance/retrace zone",
        "short_entry_concept": "Treat a short setup as a retrace into golden-pocket resistance, then require paper evidence of rejection before considering the lane for any future review.",
        "invalidation_concept": "Invalidation belongs above the relevant swing high or resistance zone, not below the entry as in long support logic.",
        "take_profit_concept": "Take-profit logic must be below entry toward downside continuation, prior liquidity, or measured support targets.",
        "notes": [
            "Short golden pocket is resistance/retrace, not support.",
            "Stop and take-profit assumptions must be short-specific before any future operator review.",
            "This packet does not promote the lane and does not alter lane config.",
        ],
    }


def build_short_stop_tp_review(
    *,
    target_family: Mapping[str, Any] | None = None,
    evidence_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    target = dict(target_family or {})
    evidence = dict(evidence_summary or {})
    outcome_count = int(evidence.get("paper_outcome_count") or 0)
    stop_count = int(evidence.get("stop_count") or 0)
    return {
        "target_lane_key": target.get("lane_key"),
        "stop_logic_review": "Stop should be above the short invalidation high/resistance zone and must not be copied from long support invalidation.",
        "take_profit_logic_review": "TP should be below entry toward downside continuation or prior liquidity and must be validated through paper outcomes.",
        "stop_dominance_ratio": round(stop_count / outcome_count, 4) if outcome_count else None,
        "short_specific_policy_required_before_live": True,
    }


def build_short_evidence_thresholds() -> dict[str, Any]:
    return {
        "min_paper_outcomes": MIN_PAPER_OUTCOMES,
        "min_fresh_candidates": MIN_FRESH_CANDIDATES,
        "preferred_win_rate_pct": int(PREFERRED_WIN_RATE_PCT),
        "avg_pnl_must_be_positive": True,
        "stop_dominance_must_be_controlled": True,
        "requires_operator_approval": True,
    }


def build_short_paper_tracking_plan(*, target_family: Mapping[str, Any] | None = None) -> dict[str, Any]:
    lane_key = str((target_family or {}).get("lane_key") or DEFAULT_TARGET_LANE_KEY)
    return {
        "continue_mode": "paper",
        "watch_commands": [
            build_expanded_paper_safe_watch_command(record=False),
            build_expanded_paper_safe_watch_command(record=True),
        ],
        "audit_commands": [
            _full_spectrum_review_command(),
            _promotion_candidate_audit_command(),
            _preview_command(lane_key),
        ],
        "what_to_collect": [
            "fresh BTCUSDT 8m short paper candidates",
            "closed paper outcomes for BTCUSDT 8m short ladder_close_50_618",
            "stop-hit frequency and invalidation quality",
            "average and total paper PnL for the short family",
            "betrayal inverse sample quality for 8m short where available",
        ],
    }


def classify_short_strategy_readiness(
    *,
    target_family: Mapping[str, Any] | None = None,
    evidence_summary: Mapping[str, Any] | None = None,
) -> str:
    target = dict(target_family or {})
    evidence = dict(evidence_summary or {})
    if target.get("direction") != "short":
        return DO_NOT_PROMOTE
    if target.get("current_mode") != "paper":
        return DO_NOT_PROMOTE
    outcomes = int(evidence.get("paper_outcome_count") or 0)
    fresh = int(evidence.get("fresh_candidate_count") or 0)
    stops = int(evidence.get("stop_count") or 0)
    win_rate = _number_or_none(evidence.get("win_rate_pct"))
    avg_pnl = _number_or_none(evidence.get("avg_pnl_pct"))
    if outcomes <= 0 and fresh <= 0:
        return PAPER_ONLY_NOT_READY
    if outcomes and stops / outcomes > 0.6:
        return DO_NOT_PROMOTE
    if outcomes >= MIN_PAPER_OUTCOMES and avg_pnl is not None and avg_pnl <= 0.0:
        return DO_NOT_PROMOTE
    if outcomes < MIN_PAPER_OUTCOMES or fresh < MIN_FRESH_CANDIDATES:
        return PAPER_ONLY_COLLECT_MORE_EVIDENCE
    if win_rate is None or avg_pnl is None:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if win_rate >= PREFERRED_WIN_RATE_PCT and avg_pnl > 0.0:
        return STRONG_SHORT_PAPER_CANDIDATE_REQUIRES_OPERATOR_REVIEW
    if avg_pnl > 0.0:
        return SHORT_STRATEGY_REVIEW_READY
    return PAPER_ONLY_COLLECT_MORE_EVIDENCE


def build_short_strategy_next_action(readiness: str, *, record_packet: bool = False, confirmation_valid: bool = False) -> str:
    if record_packet and not confirmation_valid:
        return "RECORD_SHORT_STRATEGY_PACKET"
    if readiness == STRONG_SHORT_PAPER_CANDIDATE_REQUIRES_OPERATOR_REVIEW:
        return "RECORD_SHORT_STRATEGY_PACKET"
    if readiness in {PAPER_ONLY_NOT_READY, PAPER_ONLY_COLLECT_MORE_EVIDENCE}:
        return "RUN_R157_SHORT_PAPER_EVIDENCE_CAPTURE_LOOP"
    if readiness == SHORT_STRATEGY_REVIEW_READY:
        return "RECORD_SHORT_STRATEGY_PACKET"
    return "WAIT_FOR_MORE_SHORT_EVIDENCE"


def append_short_strategy_packet_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = short_strategy_packet_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "packet_id": record.get("packet_id") or f"short_strategy_packet_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "record_packet_requested": bool(record.get("record_packet_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "short_strategy_interpretation": dict(record.get("short_strategy_interpretation") or {}),
            "stop_tp_review": dict(record.get("stop_tp_review") or {}),
            "evidence_summary": dict(record.get("evidence_summary") or {}),
            "thresholds_for_future_review": dict(record.get("thresholds_for_future_review") or {}),
            "readiness": record.get("readiness"),
            "why": record.get("why"),
            "blockers_to_tiny_live": list(record.get("blockers_to_tiny_live") or []),
            "paper_tracking_plan": dict(record.get("paper_tracking_plan") or {}),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safe_commands": list(record.get("safe_commands") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_short_strategy_packet_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = short_strategy_packet_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=limit if limit > 0 else 100000, max_bytes=32_000_000)
    if limit <= 0:
        records = list(reversed(records))
    return [_sanitize(record) for record in records]


def summarize_short_strategy_packets(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_packet_id": latest.get("packet_id"),
        "last_target_lane": (latest.get("target_family") or {}).get("lane_key") if isinstance(latest.get("target_family"), Mapping) else None,
        "last_readiness": latest.get("readiness"),
        "safety": dict(SAFETY),
    }


def short_strategy_packet_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_short_strategy_packet_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _blockers_to_tiny_live(*, target_family: Mapping[str, Any], evidence_summary: Mapping[str, Any], readiness: str) -> list[str]:
    blockers: list[str] = []
    if target_family.get("current_mode") != "paper":
        blockers.append("target lane is not in paper mode")
    if target_family.get("direction") != "short":
        blockers.append("target lane is not a short lane")
    if int(evidence_summary.get("paper_outcome_count") or 0) < MIN_PAPER_OUTCOMES:
        blockers.append("paper outcome sample below 30")
    if int(evidence_summary.get("fresh_candidate_count") or 0) < MIN_FRESH_CANDIDATES:
        blockers.append("fresh short candidate sample below 10")
    avg_pnl = _number_or_none(evidence_summary.get("avg_pnl_pct"))
    if avg_pnl is None:
        blockers.append("avg_pnl_pct unavailable")
    elif avg_pnl <= 0.0:
        blockers.append("avg_pnl_pct is not positive")
    win_rate = _number_or_none(evidence_summary.get("win_rate_pct"))
    if win_rate is None or win_rate < PREFERRED_WIN_RATE_PCT:
        blockers.append("win rate below preferred 52 pct or unavailable")
    outcomes = int(evidence_summary.get("paper_outcome_count") or 0)
    stops = int(evidence_summary.get("stop_count") or 0)
    if outcomes and stops / outcomes > 0.5:
        blockers.append("stop dominance must be controlled")
    blockers.extend(
        [
            "short lane has no tiny_live authorization",
            "future operator approval is required",
            "global/protective/live gates remain separate and not cleared by this packet",
        ]
    )
    if readiness == DO_NOT_PROMOTE:
        blockers.append("readiness is DO_NOT_PROMOTE")
    return _dedupe(blockers)


def _why(readiness: str, *, target_family: Mapping[str, Any], evidence_summary: Mapping[str, Any]) -> str:
    if target_family.get("current_mode") != "paper":
        return "The target family is not paper-only; R156 cannot package it for short paper tracking."
    if readiness == PAPER_ONLY_NOT_READY:
        return "No usable paper outcome or fresh candidate evidence exists for the short family yet."
    if readiness == PAPER_ONLY_COLLECT_MORE_EVIDENCE:
        return "Short-side evidence exists, but paper outcome or fresh candidate thresholds are still below R156 minimums."
    if readiness == DO_NOT_PROMOTE:
        return "Short paper evidence is negative, stop-dominated, or not a valid short paper target."
    if readiness == STRONG_SHORT_PAPER_CANDIDATE_REQUIRES_OPERATOR_REVIEW:
        return "Paper thresholds are met, but any short tiny-live discussion still requires explicit future operator approval."
    if readiness == SHORT_STRATEGY_REVIEW_READY:
        return "Paper evidence is constructive enough for strategy review, but not an authorization to promote."
    return "Missing evidence fields require manual review."


def _recommended_next_engineering_move(readiness: str) -> str:
    if readiness in {PAPER_ONLY_NOT_READY, PAPER_ONLY_COLLECT_MORE_EVIDENCE}:
        return "Build R157 bounded short paper evidence capture loop for BTCUSDT 8m short; keep the lane paper-only."
    if readiness in {SHORT_STRATEGY_REVIEW_READY, STRONG_SHORT_PAPER_CANDIDATE_REQUIRES_OPERATOR_REVIEW}:
        return "Prepare a future operator review package; do not mutate lane mode or live flags."
    if readiness == DO_NOT_PROMOTE:
        return "Keep the short lane paper-only and review stop/TP assumptions before collecting more evidence."
    return "Manually inspect missing evidence fields before any further packet work."


def _safe_commands(lane_key: str) -> list[str]:
    return [
        _record_command(lane_key),
        _full_spectrum_review_command(),
        _promotion_candidate_audit_command(),
        build_expanded_paper_safe_watch_command(record=True),
        _preview_command(lane_key),
    ]


def _preview_command(lane_key: str) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-strategy-packet "
        f"--lane-key {lane_key} --latest-outcomes 10000 --latest-signals 3000 "
        "--latest-betrayal 5000 --latest-watch-records 500"
    )


def _record_command(lane_key: str) -> str:
    return (
        f"{_preview_command(lane_key)} --record-packet --confirm-short-strategy-packet "
        f'"{CONFIRM_SHORT_STRATEGY_PACKET_RECORDING_PHRASE}"'
    )


def _full_spectrum_review_command() -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward full-spectrum-betrayal-short-review "
        "--latest-outcomes 10000 --latest-signals 3000 --latest-betrayal 5000 --latest-watch-records 500 "
        "--include-paper-lanes --include-tiny-live-incumbents --include-betrayal-inverse"
    )


def _promotion_candidate_audit_command() -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward promotion-candidate-audit "
        "--latest-outcomes 5000 --latest-signals 2000 --latest-watch-records 200 "
        "--include-paper-lanes --include-tiny-live-incumbents"
    )


def _sample_quality(performance: Mapping[str, Any], opportunity: Mapping[str, Any]) -> str:
    outcomes = int(performance.get("paper_outcome_count") or 0)
    fresh = int(opportunity.get("fresh_candidate_count") or 0)
    if outcomes <= 0 and fresh <= 0:
        return "NO_SHORT_EVIDENCE"
    if outcomes < MIN_PAPER_OUTCOMES or fresh < MIN_FRESH_CANDIDATES:
        return "LOW_SAMPLE"
    if outcomes < MIN_PAPER_OUTCOMES * 3:
        return "DEVELOPING"
    return "USABLE_SAMPLE"


def _empty_evidence_summary() -> dict[str, Any]:
    return {
        "signal_count": 0,
        "paper_outcome_count": 0,
        "fresh_candidate_count": 0,
        "stale_candidate_count": 0,
        "win_rate_pct": None,
        "avg_pnl_pct": None,
        "total_pnl_pct": None,
        "stop_count": 0,
        "betrayal_inverse_summary": {},
        "sample_quality": "NO_SHORT_EVIDENCE",
    }


def _compact_target(lane: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_key": str(lane.get("lane_key") or normalize_lane_key(lane.get("symbol"), lane.get("timeframe"), lane.get("direction"), lane.get("entry_mode"))),
        "symbol": str(lane.get("symbol") or "").strip().upper(),
        "timeframe": str(lane.get("timeframe") or "").strip().lower(),
        "direction": str(lane.get("direction") or "").strip().lower(),
        "entry_mode": str(lane.get("entry_mode") or TARGET_ENTRY_MODE).strip().lower(),
        "current_mode": str(lane.get("mode") or "disabled").strip().lower(),
    }


def _target_from_key(lane_key: str, *, mode: str) -> dict[str, Any]:
    parts = _normalize_lane_key_text(lane_key).split("|")
    while len(parts) < 4:
        parts.append("")
    return {
        "lane_key": "|".join(parts[:4]),
        "symbol": parts[0] or TARGET_SYMBOL,
        "timeframe": parts[1],
        "direction": parts[2],
        "entry_mode": parts[3] or TARGET_ENTRY_MODE,
        "current_mode": mode,
    }


def _normalize_lane_key_text(lane_key: str) -> str:
    parts = str(lane_key or DEFAULT_TARGET_LANE_KEY).split("|")
    while len(parts) < 4:
        parts.append("")
    return normalize_lane_key(parts[0], parts[1], parts[2], parts[3])


def _bounded_int(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _number_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
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
    return value
