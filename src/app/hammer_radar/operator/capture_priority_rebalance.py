"""R233 paper-only capture priority rebalance audit.

This module composes existing local R231/R232/fisherman/betrayal evidence into
watchlist recommendations only. It never calls Binance/network, creates order
payloads, mutates configs/env/lane modes, promotes lanes, or authorizes live.
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
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import (
    DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    DEFAULT_THRESHOLD_REQUIRED_COUNT,
    build_full_spectrum_lane_scoreboard,
    load_full_spectrum_lane_scoreboard_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.lane_outcome_enrichment import (
    build_lane_outcome_enrichment,
    load_lane_outcome_enrichment_records,
    load_tiny_live_capture_count_sync as _load_tiny_live_capture_count_sync,
    normalize_lane_key,
)

CAPTURE_PRIORITY_REBALANCE_READY = "CAPTURE_PRIORITY_REBALANCE_READY"
CAPTURE_PRIORITY_REBALANCE_REJECTED = "CAPTURE_PRIORITY_REBALANCE_REJECTED"
CAPTURE_PRIORITY_REBALANCE_RECORDED = "CAPTURE_PRIORITY_REBALANCE_RECORDED"
CAPTURE_PRIORITY_REBALANCE_BLOCKED = "CAPTURE_PRIORITY_REBALANCE_BLOCKED"
CAPTURE_PRIORITY_REBALANCE_ERROR = "CAPTURE_PRIORITY_REBALANCE_ERROR"

OFFICIAL_PATH_STILL_PRIMARY = "OFFICIAL_PATH_STILL_PRIMARY"
NEAR_THRESHOLD_ALTERNATES_FOUND = "NEAR_THRESHOLD_ALTERNATES_FOUND"
BETRAYAL_SHADOW_CONTEXT_PRESERVED = "BETRAYAL_SHADOW_CONTEXT_PRESERVED"
WAITING_FOR_10_OF_10 = "WAITING_FOR_10_OF_10"
CAPTURE_PRIORITY_DATA_GAPS_REMAIN = "CAPTURE_PRIORITY_DATA_GAPS_REMAIN"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

OFFICIAL_PROTECTED_TINY_LIVE_PATH = "OFFICIAL_PROTECTED_TINY_LIVE_PATH"
NEAR_THRESHOLD_ALTERNATE = "NEAR_THRESHOLD_ALTERNATE"
OUTCOME_STRONG_CAPTURE_BLOCKED = "OUTCOME_STRONG_CAPTURE_BLOCKED"
BETRAYAL_SHADOW_PRIORITY = "BETRAYAL_SHADOW_PRIORITY"
TINY_SAMPLE_TRAP = "TINY_SAMPLE_TRAP"
BLOCKED_OR_UNKNOWN = "BLOCKED_OR_UNKNOWN"

EVENT_TYPE = "CAPTURE_PRIORITY_REBALANCE"
LEDGER_FILENAME = "capture_priority_rebalance.ndjson"
CONFIRM_CAPTURE_PRIORITY_REBALANCE_RECORDING_PHRASE = (
    "I CONFIRM CAPTURE PRIORITY REBALANCE RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "fisherman_config_written": False,
    "scheduler_config_written": False,
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
    "betrayal_live_authorized": False,
    "betrayal_promoted": False,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/lane_outcome_enrichment.ndjson",
    "logs/hammer_radar_forward/full_spectrum_lane_scoreboard.ndjson",
    "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson",
    "logs/hammer_radar_forward/weekend_paper_fisherman_supervisor.ndjson",
    "logs/hammer_radar_forward/fisherman_watchdog_ledger_reconciliation.ndjson",
    "logs/hammer_radar_forward/betrayal_upstream_emitter_entry_mode_contract.ndjson",
    "logs/hammer_radar_forward/betrayal_entry_mode_source_propagation.ndjson",
    "logs/hammer_radar_forward/betrayal_direction_completion.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_resolutions.ndjson",
    "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_signals.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_capture_priority_rebalance(
    *,
    log_dir: str | Path | None = None,
    record_rebalance: bool = False,
    confirm_capture_priority_rebalance: str | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_capture_priority_rebalance == CONFIRM_CAPTURE_PRIORITY_REBALANCE_RECORDING_PHRASE
    try:
        enrichment = load_latest_lane_outcome_enrichment(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        scoreboard = load_latest_full_spectrum_lane_scoreboard(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        tiny_live_sync = load_latest_tiny_live_capture_count_sync(log_dir=resolved_log_dir)
        fisherman = load_latest_fisherman_supervisor(log_dir=resolved_log_dir)
        betrayal_context = load_latest_betrayal_context(log_dir=resolved_log_dir)

        enriched_rows = list(enrichment.get("enriched_lane_rows") or [])
        official_summary = build_official_protected_path_summary(
            enriched_rows=enriched_rows,
            scoreboard=scoreboard,
            tiny_live_sync=tiny_live_sync,
            fisherman_supervisor=fisherman,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        priority_rows = rank_capture_priority_rows(
            build_capture_priority_rows(
                enriched_rows=enriched_rows,
                betrayal_context=betrayal_context,
                official_tiny_live_lane=official_tiny_live_lane,
            )
        )
        rebalance_plan = build_capture_priority_rebalance_plan(priority_rows)
        shadow_context = build_betrayal_shadow_priority_context(betrayal_context)
        gap_report = build_capture_priority_gap_report(
            priority_rows=priority_rows,
            official_summary=official_summary,
            betrayal_shadow_context=shadow_context,
        )
        recommendations = build_capture_priority_recommendations(
            official_summary=official_summary,
            rebalance_plan=rebalance_plan,
            betrayal_shadow_context=shadow_context,
        )
        rebalance_status = classify_capture_priority_rebalance_status(
            priority_rows=priority_rows,
            official_summary=official_summary,
            betrayal_shadow_context=shadow_context,
            gap_report=gap_report,
        )
        status = CAPTURE_PRIORITY_REBALANCE_READY if priority_rows else CAPTURE_PRIORITY_REBALANCE_BLOCKED
        if record_rebalance and not confirmation_valid:
            status = CAPTURE_PRIORITY_REBALANCE_REJECTED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "rebalance_recorded": False,
            "rebalance_id": None,
            "record_rebalance_requested": bool(record_rebalance),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "paper_only": True,
                "live_authorized": False,
                "official_tiny_live_lane": official_tiny_live_lane,
                "official_tiny_live_lane_changed": False,
                "betrayal_shadow_preserved": True,
            },
            "input_summary": {
                "lane_outcome_enrichment_found": bool(enrichment.get("enrichment_found")),
                "full_spectrum_lane_scoreboard_found": bool(scoreboard.get("scoreboard_found")),
                "tiny_live_capture_sync_found": bool(tiny_live_sync),
                "fisherman_supervisor_found": bool(fisherman),
                "betrayal_context_found": bool(shadow_context.get("candidate_lanes")),
            },
            "official_protected_path_summary": official_summary,
            "capture_priority_rows": priority_rows,
            "rebalance_plan": rebalance_plan,
            "betrayal_shadow_context": shadow_context,
            "capture_priority_gap_report": gap_report,
            "capture_priority_recommendations": recommendations,
            "rebalance_status": rebalance_status,
            "recommended_next_operator_move": _recommended_next_operator_move(official_summary, rebalance_plan, shadow_context),
            "recommended_next_engineering_move": _recommended_next_engineering_move(official_summary, rebalance_plan, shadow_context),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_rebalance and confirmation_valid:
            record = append_capture_priority_rebalance_record(payload, log_dir=resolved_log_dir)
            payload["status"] = CAPTURE_PRIORITY_REBALANCE_RECORDED
            payload["rebalance_recorded"] = True
            payload["rebalance_id"] = record["rebalance_id"]
            payload["ledger_path"] = str(capture_priority_rebalance_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": CAPTURE_PRIORITY_REBALANCE_ERROR,
                "generated_at": generated_at.isoformat(),
                "rebalance_recorded": False,
                "rebalance_id": None,
                "record_rebalance_requested": bool(record_rebalance),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "paper_only": True,
                    "live_authorized": False,
                    "official_tiny_live_lane": official_tiny_live_lane,
                    "official_tiny_live_lane_changed": False,
                    "betrayal_shadow_preserved": True,
                },
                "input_summary": {
                    "lane_outcome_enrichment_found": False,
                    "full_spectrum_lane_scoreboard_found": False,
                    "tiny_live_capture_sync_found": False,
                    "fisherman_supervisor_found": False,
                    "betrayal_context_found": False,
                },
                "official_protected_path_summary": _empty_official_summary(
                    official_tiny_live_lane,
                    threshold_required_count=threshold_required_count,
                ),
                "capture_priority_rows": [],
                "rebalance_plan": build_capture_priority_rebalance_plan([]),
                "betrayal_shadow_context": build_betrayal_shadow_priority_context({}),
                "capture_priority_gap_report": {
                    "official_lane_blockers": ["capture_priority_rebalance_error"],
                    "alternate_lane_blockers": [],
                    "betrayal_shadow_blockers": ["capture_priority_rebalance_error"],
                    "tiny_sample_trap_count": 0,
                    "lanes_missing_entry_mode": 0,
                    "lanes_missing_unique_captures": 0,
                    "hard_live_blockers": _hard_live_blockers(),
                },
                "capture_priority_recommendations": [],
                "rebalance_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R233 capture priority rebalance error before using priority rows.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_lane_outcome_enrichment(
    *,
    log_dir: str | Path | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
) -> dict[str, Any]:
    records = load_lane_outcome_enrichment_records(log_dir=log_dir, limit=1)
    if records:
        latest = dict(records[0])
        latest["enrichment_found"] = True
        return _sanitize(latest)
    built = build_lane_outcome_enrichment(
        log_dir=log_dir,
        official_tiny_live_lane=official_tiny_live_lane,
        threshold_required_count=threshold_required_count,
    )
    built["enrichment_found"] = False
    return _sanitize(built)


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


def load_latest_tiny_live_capture_count_sync(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _sanitize(_load_tiny_live_capture_count_sync(log_dir=log_dir))


def load_latest_fisherman_supervisor(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved = get_log_dir(log_dir, use_env=True)
    return _sanitize(_latest_record(resolved / "weekend_paper_fisherman_supervisor.ndjson"))


def load_latest_betrayal_context(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved = get_log_dir(log_dir, use_env=True)
    sources = {
        "weekend_supervisor": _latest_record(resolved / "weekend_paper_fisherman_supervisor.ndjson"),
        "upstream_contract": _latest_record(resolved / "betrayal_upstream_emitter_entry_mode_contract.ndjson"),
        "source_propagation": _latest_record(resolved / "betrayal_entry_mode_source_propagation.ndjson"),
        "direction_completion": _latest_record(resolved / "betrayal_direction_completion.ndjson"),
        "renormalization": _latest_record(resolved / "betrayal_renormalize_with_entry_mode.ndjson"),
        "entry_mode_evidence": _latest_record(resolved / "betrayal_entry_mode_evidence_wiring.ndjson"),
        "shadow_outcomes": _read_records(resolved / "betrayal_shadow_outcomes.ndjson", limit=50),
        "shadow_resolutions": _read_records(resolved / "betrayal_shadow_resolutions.ndjson", limit=50),
        "true_paper_outcomes": _read_records(resolved / "betrayal_true_paper_outcomes.ndjson", limit=50),
        "paper_signals": _read_records(resolved / "betrayal_paper_signals.ndjson", limit=50),
    }
    return _sanitize({"sources": sources, "candidate_lanes": _extract_betrayal_candidate_lanes(sources)})


def classify_priority_group(row: Mapping[str, Any], *, official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE) -> str:
    if row.get("priority_group") == BETRAYAL_SHADOW_PRIORITY:
        return BETRAYAL_SHADOW_PRIORITY
    if row.get("lane_key") == official_tiny_live_lane:
        return OFFICIAL_PROTECTED_TINY_LIVE_PATH
    known = int(row.get("known_outcome_count") or 0)
    unique = int(row.get("unique_capture_count") or 0)
    entry_mode = str(row.get("entry_mode") or "entry_unknown")
    win_rate = row.get("win_rate_pct")
    if win_rate == 100.0 and known < 30:
        return TINY_SAMPLE_TRAP
    if entry_mode != "entry_unknown" and unique >= 5 and 0 < int(row.get("threshold_distance_remaining") or 0):
        return NEAR_THRESHOLD_ALTERNATE
    if _outcome_strong(row) and unique < int(row.get("threshold_required_count") or DEFAULT_THRESHOLD_REQUIRED_COUNT):
        return OUTCOME_STRONG_CAPTURE_BLOCKED
    if entry_mode == "entry_unknown" or unique <= 0 or known <= 0:
        return BLOCKED_OR_UNKNOWN
    return BLOCKED_OR_UNKNOWN


def build_official_protected_path_summary(
    *,
    enriched_rows: Sequence[Mapping[str, Any]],
    scoreboard: Mapping[str, Any],
    tiny_live_sync: Mapping[str, Any],
    fisherman_supervisor: Mapping[str, Any],
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
) -> dict[str, Any]:
    row = next((dict(candidate) for candidate in enriched_rows if candidate.get("lane_key") == official_tiny_live_lane), {})
    status = dict(scoreboard.get("official_tiny_live_lane_status") or {})
    capture = dict(tiny_live_sync.get("capture_count") or {})
    watcher = dict(tiny_live_sync.get("watcher_status") or {})
    fisherman_health = dict(fisherman_supervisor.get("fisherman_health") or {})
    fresh = int(status.get("fresh_capture_count") or capture.get("fresh_capture_count") or row.get("unique_capture_count") or 0)
    required = int(status.get("required_fresh_capture_count") or capture.get("required_fresh_capture_count") or threshold_required_count)
    watcher_likely = bool(status.get("watcher_likely_running") or watcher.get("watcher_likely_running"))
    watcher_stale = bool(status.get("watcher_stale") or watcher.get("watcher_stale"))
    fisherman_status = str(status.get("fisherman_status") or fisherman_health.get("fisherman_status") or "")
    if not fisherman_status:
        fisherman_status = "FISHERMAN_RUNNING_RECENT" if watcher_likely and not watcher_stale else "FISHERMAN_NEEDS_REVIEW"
    return _sanitize(
        {
            "lane_key": official_tiny_live_lane,
            "fresh_capture_count": fresh,
            "required_fresh_capture_count": required,
            "threshold_met": bool(status.get("threshold_met") or capture.get("threshold_met") or fresh >= required),
            "threshold_distance_remaining": max(0, required - fresh),
            "combined_watch_score": row.get("combined_watch_score"),
            "win_rate_pct": row.get("win_rate_pct"),
            "known_outcome_count": int(row.get("known_outcome_count") or 0),
            "fisherman_status": fisherman_status,
            "watcher_likely_running": watcher_likely,
            "watcher_stale": watcher_stale,
            "recommended_action": "KEEP_AS_OFFICIAL_AND_WAIT_FOR_10_OF_10",
        }
    )


def build_near_threshold_alternates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row.get("priority_group") == NEAR_THRESHOLD_ALTERNATE]


def build_outcome_strong_capture_blocked_lanes(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row.get("priority_group") == OUTCOME_STRONG_CAPTURE_BLOCKED]


def build_betrayal_shadow_priority_context(betrayal_context: Mapping[str, Any]) -> dict[str, Any]:
    candidate_lanes = list(betrayal_context.get("candidate_lanes") or [])
    blockers = [
        "betrayal_shadow_context_only",
        "betrayal_not_live_authorized",
        "betrayal_not_promoted",
        "tiny_live_capture_threshold_separate",
    ]
    status = "CONTEXT_ONLY" if candidate_lanes else "MISSING"
    next_phase = "R234_BETRAYAL_SHADOW_PRIORITY_REFRESH" if candidate_lanes else "NONE"
    return _sanitize(
        {
            "preserved": True,
            "status": status,
            "candidate_lanes": candidate_lanes,
            "blockers": blockers if candidate_lanes else ["betrayal_context_missing_or_empty"],
            "recommended_next_betrayal_phase": next_phase,
            "why": (
                "Betrayal/inverse evidence is preserved as active shadow priority context only; it is not live eligibility."
                if candidate_lanes
                else "No current betrayal/inverse candidate lanes were found in the inspected local ledgers."
            ),
        }
    )


def build_tiny_sample_traps(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row.get("priority_group") == TINY_SAMPLE_TRAP]


def build_blocked_or_unknown_lanes(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row.get("priority_group") == BLOCKED_OR_UNKNOWN]


def calculate_capture_priority_score(row: Mapping[str, Any]) -> float:
    group = str(row.get("priority_group") or "")
    group_bonus = {
        OFFICIAL_PROTECTED_TINY_LIVE_PATH: 1000.0,
        NEAR_THRESHOLD_ALTERNATE: 700.0,
        OUTCOME_STRONG_CAPTURE_BLOCKED: 500.0,
        BETRAYAL_SHADOW_PRIORITY: 400.0,
        TINY_SAMPLE_TRAP: 100.0,
        BLOCKED_OR_UNKNOWN: 0.0,
    }.get(group, 0.0)
    combined = float(row.get("combined_watch_score") or 0.0)
    unique = min(10, int(row.get("unique_capture_count") or 0)) * 3.0
    known = min(300, int(row.get("known_outcome_count") or 0)) / 30.0
    win = 0.0 if row.get("win_rate_pct") is None else min(100.0, float(row.get("win_rate_pct") or 0.0)) / 10.0
    return round(group_bonus + combined + unique + known + win, 2)


def build_capture_priority_rows(
    *,
    enriched_rows: Sequence[Mapping[str, Any]],
    betrayal_context: Mapping[str, Any],
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in enriched_rows:
        row = _priority_row_from_enriched(source, official_tiny_live_lane=official_tiny_live_lane)
        row["priority_group"] = classify_priority_group(row, official_tiny_live_lane=official_tiny_live_lane)
        row["recommended_paper_action"] = _recommended_paper_action(row["priority_group"])
        row["why"] = _why(row)
        row["capture_priority_score"] = calculate_capture_priority_score(row)
        rows.append(row)
    for candidate in betrayal_context.get("candidate_lanes") or []:
        row = _priority_row_from_betrayal(candidate)
        row["capture_priority_score"] = calculate_capture_priority_score(row)
        rows.append(row)
    return _dedupe_priority_rows(rows)


def rank_capture_priority_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    group_order = {
        OFFICIAL_PROTECTED_TINY_LIVE_PATH: 0,
        NEAR_THRESHOLD_ALTERNATE: 1,
        OUTCOME_STRONG_CAPTURE_BLOCKED: 2,
        BETRAYAL_SHADOW_PRIORITY: 3,
        TINY_SAMPLE_TRAP: 4,
        BLOCKED_OR_UNKNOWN: 5,
    }
    ranked = [dict(row) for row in rows]
    ranked.sort(
        key=lambda row: (
            group_order.get(str(row.get("priority_group") or ""), 99),
            -float(row.get("capture_priority_score") or 0.0),
            -float(row.get("combined_watch_score") or 0.0),
            str(row.get("lane_key") or ""),
        )
    )
    for index, row in enumerate(ranked, start=1):
        row["priority_rank"] = index
    return _sanitize(ranked)


def build_capture_priority_rebalance_plan(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    near = build_near_threshold_alternates(rows)
    strong = build_outcome_strong_capture_blocked_lanes(rows)
    betrayal = [dict(row) for row in rows if row.get("priority_group") == BETRAYAL_SHADOW_PRIORITY]
    traps = build_tiny_sample_traps(rows)
    blocked = build_blocked_or_unknown_lanes(rows)
    return _sanitize(
        {
            "official_lane_unchanged": True,
            "paper_priority_order": [row.get("lane_key") for row in rows[:40]],
            "near_threshold_alternates": [row.get("lane_key") for row in near],
            "outcome_strong_capture_blocked": [row.get("lane_key") for row in strong],
            "betrayal_shadow_priority": [row.get("lane_key") for row in betrayal],
            "tiny_sample_traps": [row.get("lane_key") for row in traps],
            "blocked_or_unknown": [row.get("lane_key") for row in blocked],
            "runtime_config_change_required": False,
            "live_readiness_implied": False,
        }
    )


def build_capture_priority_gap_report(
    *,
    priority_rows: Sequence[Mapping[str, Any]],
    official_summary: Mapping[str, Any],
    betrayal_shadow_context: Mapping[str, Any],
) -> dict[str, Any]:
    alternate_blockers = []
    if build_near_threshold_alternates(priority_rows):
        alternate_blockers.append("alternate_lanes_capture_blocked_under_10_of_10")
    if build_outcome_strong_capture_blocked_lanes(priority_rows):
        alternate_blockers.append("outcome_strong_lanes_are_paper_watch_only")
    return _sanitize(
        {
            "official_lane_blockers": _official_blockers(official_summary),
            "alternate_lane_blockers": alternate_blockers,
            "betrayal_shadow_blockers": list(betrayal_shadow_context.get("blockers") or []),
            "tiny_sample_trap_count": len(build_tiny_sample_traps(priority_rows)),
            "lanes_missing_entry_mode": sum(1 for row in priority_rows if row.get("entry_mode") == "entry_unknown"),
            "lanes_missing_unique_captures": sum(1 for row in priority_rows if int(row.get("unique_capture_count") or 0) <= 0),
            "hard_live_blockers": _hard_live_blockers(),
        }
    )


def build_capture_priority_recommendations(
    *,
    official_summary: Mapping[str, Any],
    rebalance_plan: Mapping[str, Any],
    betrayal_shadow_context: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "KEEP_FISHERMAN_RUNNING",
            "future_phase": "R233",
            "why": "The official protected path remains the top paper priority until BTCUSDT 8m short reaches 10/10.",
        },
        {
            "priority": "HIGH",
            "recommended_action": "WAIT_FOR_10_OF_10",
            "future_phase": "R228",
            "why": f"Official lane is {official_summary.get('fresh_capture_count')}/{official_summary.get('required_fresh_capture_count')}; R233 does not authorize live.",
        },
    ]
    if official_summary.get("threshold_met"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RUN_R228_IF_10_OF_10",
                "future_phase": "R228",
                "why": "Only the protected official path may move to the checklist packet, and still without live execution.",
            }
        )
    if "BTCUSDT|8m|long|ladder_close_50_618" in set(rebalance_plan.get("near_threshold_alternates") or []):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "WATCH_8M_LONG",
                "future_phase": "R233",
                "why": "8m long has meaningful paper outcome evidence and is near threshold, but remains capture-blocked and non-promoted.",
            }
        )
    if betrayal_shadow_context.get("candidate_lanes"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "PRESERVE_BETRAYAL_SHADOW",
                "future_phase": "R234",
                "why": "Betrayal/inverse evidence remains active shadow context and must not be forgotten by future phases.",
            }
        )
        recommendations.append(
            {
                "priority": "LOW",
                "recommended_action": "RUN_R234_BETRAYAL_SHADOW_PRIORITY_REFRESH",
                "future_phase": "R234",
                "why": "R234 can refresh 222m/88m betrayal/inverse priority without writing configs or changing live readiness.",
            }
        )
    return recommendations


def classify_capture_priority_rebalance_status(
    *,
    priority_rows: Sequence[Mapping[str, Any]],
    official_summary: Mapping[str, Any],
    betrayal_shadow_context: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> str:
    if not priority_rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if betrayal_shadow_context.get("candidate_lanes"):
        return BETRAYAL_SHADOW_CONTEXT_PRESERVED
    if build_near_threshold_alternates(priority_rows):
        return NEAR_THRESHOLD_ALTERNATES_FOUND
    if official_summary.get("threshold_met") is False:
        return WAITING_FOR_10_OF_10
    if int(gap_report.get("lanes_missing_entry_mode") or 0) > 0:
        return CAPTURE_PRIORITY_DATA_GAPS_REMAIN
    if priority_rows[0].get("priority_group") == OFFICIAL_PROTECTED_TINY_LIVE_PATH:
        return OFFICIAL_PATH_STILL_PRIMARY
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_capture_priority_rebalance_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = capture_priority_rebalance_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "rebalance_id": str(record.get("rebalance_id") or f"r233_capture_priority_rebalance_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "official_protected_path_summary": dict(record.get("official_protected_path_summary") or {}),
            "capture_priority_rows": list(record.get("capture_priority_rows") or []),
            "rebalance_plan": dict(record.get("rebalance_plan") or {}),
            "betrayal_shadow_context": dict(record.get("betrayal_shadow_context") or {}),
            "capture_priority_gap_report": dict(record.get("capture_priority_gap_report") or {}),
            "capture_priority_recommendations": list(record.get("capture_priority_recommendations") or []),
            "rebalance_status": record.get("rebalance_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_capture_priority_rebalance_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return _read_records(capture_priority_rebalance_records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def summarize_capture_priority_rebalance_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "latest_rebalance_id": latest.get("rebalance_id") if latest else None,
        "latest_rebalance_status": latest.get("rebalance_status") if latest else None,
        "safety": dict(SAFETY),
    }


def capture_priority_rebalance_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_capture_priority_rebalance_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _priority_row_from_enriched(row: Mapping[str, Any], *, official_tiny_live_lane: str) -> dict[str, Any]:
    lane = _lane_from_key(row.get("lane_key"))
    return {
        "priority_rank": None,
        "priority_group": None,
        "lane_key": lane["lane_key"],
        "symbol": lane["symbol"],
        "timeframe": lane["timeframe"],
        "direction": lane["direction"],
        "entry_mode": lane["entry_mode"],
        "unique_capture_count": int(row.get("unique_capture_count") or 0),
        "threshold_distance_remaining": int(row.get("threshold_distance_remaining") or 0),
        "threshold_required_count": int(row.get("threshold_required_count") or DEFAULT_THRESHOLD_REQUIRED_COUNT),
        "known_outcome_count": int(row.get("known_outcome_count") or 0),
        "win_rate_pct": row.get("win_rate_pct"),
        "combined_watch_score": row.get("combined_watch_score"),
        "capture_priority_score": None,
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
        "recommended_paper_action": "KEEP_OFFICIAL" if lane["lane_key"] == official_tiny_live_lane else "IGNORE_FOR_NOW",
        "why": "",
    }


def _priority_row_from_betrayal(candidate: Mapping[str, Any]) -> dict[str, Any]:
    lane = _lane_from_key(candidate.get("lane_key") or candidate.get("lane_key_preview") or "")
    if not lane["lane_key"]:
        lane = {
            "symbol": str(candidate.get("symbol") or "BTCUSDT").upper(),
            "timeframe": str(candidate.get("timeframe") or "unknown").lower(),
            "direction": str(candidate.get("emitted_direction") or candidate.get("inverse_direction") or candidate.get("shadow_direction") or "inverse"),
            "entry_mode": str(candidate.get("entry_mode") or "entry_unknown"),
        }
        lane["lane_key"] = normalize_lane_key(lane["symbol"], lane["timeframe"], lane["direction"], lane["entry_mode"])
    return {
        "priority_rank": None,
        "priority_group": BETRAYAL_SHADOW_PRIORITY,
        "lane_key": lane["lane_key"],
        "symbol": lane["symbol"],
        "timeframe": lane["timeframe"],
        "direction": lane["direction"] or "inverse",
        "entry_mode": lane["entry_mode"],
        "unique_capture_count": int(candidate.get("unique_capture_count") or 0),
        "threshold_distance_remaining": None,
        "threshold_required_count": DEFAULT_THRESHOLD_REQUIRED_COUNT,
        "known_outcome_count": int(candidate.get("known_outcome_count") or candidate.get("samples") or 0),
        "win_rate_pct": candidate.get("win_rate_pct"),
        "combined_watch_score": candidate.get("combined_watch_score"),
        "capture_priority_score": None,
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
        "recommended_paper_action": "KEEP_SHADOW_CONTEXT",
        "why": str(candidate.get("why") or "Betrayal/inverse evidence is shadow context only and does not imply live eligibility."),
    }


def _extract_betrayal_candidate_lanes(sources: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    supervisor = dict(sources.get("weekend_supervisor") or {})
    summary = dict(supervisor.get("betrayal_watch_summary") or {})
    for timeframe_key, label_key, win_key in (
        ("latest_222m_capture_lane", "primary_betrayal_candidate", "primary_betrayal_naive_inverse_win_rate_pct"),
        ("watchlist_betrayal_lane", "watchlist_betrayal_candidate", "watchlist_betrayal_naive_inverse_win_rate_pct"),
    ):
        lane_key = summary.get(timeframe_key)
        candidate = summary.get(label_key)
        if lane_key or candidate:
            lane = _lane_from_key(lane_key or f"BTCUSDT|{str(candidate).split(' ')[0]}|inverse|entry_unknown")
            candidates.append(
                {
                    **lane,
                    "candidate": candidate,
                    "win_rate_pct": summary.get(win_key),
                    "source": "weekend_supervisor",
                    "why": "Supervisor preserved betrayal/inverse watch summary as paper-only context.",
                }
            )
    for source_name, row_key in (
        ("source_propagation", "entry_mode_propagated_rows_preview"),
        ("direction_completion", "direction_completed_rows_preview"),
        ("renormalization", "renormalized_source_rows_preview"),
    ):
        source = dict(sources.get(source_name) or {})
        for row in source.get(row_key) or []:
            if isinstance(row, Mapping) and _is_betrayal_candidate(row):
                candidates.append({**dict(row), "source": source_name})
    for record in sources.get("shadow_outcomes") or []:
        if isinstance(record, Mapping):
            lane_key = normalize_lane_key(
                record.get("symbol"),
                record.get("timeframe"),
                record.get("shadow_direction") or "inverse",
                record.get("entry_mode") or "entry_unknown",
            )
            candidates.append(
                {
                    "lane_key": lane_key,
                    "symbol": record.get("symbol"),
                    "timeframe": record.get("timeframe"),
                    "shadow_direction": record.get("shadow_direction"),
                    "entry_mode": record.get("entry_mode") or "entry_unknown",
                    "candidate": record.get("betrayal_tier"),
                    "source": "betrayal_shadow_outcomes",
                    "why": "Active shadow outcome row keeps betrayal context visible.",
                }
            )
    return _dedupe_betrayal_candidates(candidates)


def _dedupe_betrayal_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for candidate in candidates:
        key = str(candidate.get("lane_key") or candidate.get("lane_key_preview") or candidate.get("betrayal_event_identity_hash") or candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(candidate))
    return deduped[:20]


def _dedupe_priority_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row.get("priority_group") or ""), str(row.get("lane_key") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(row))
    return deduped


def _recommended_paper_action(group: str) -> str:
    return {
        OFFICIAL_PROTECTED_TINY_LIVE_PATH: "KEEP_OFFICIAL",
        NEAR_THRESHOLD_ALTERNATE: "WATCH_CLOSELY",
        OUTCOME_STRONG_CAPTURE_BLOCKED: "WATCH_CLOSELY",
        BETRAYAL_SHADOW_PRIORITY: "KEEP_SHADOW_CONTEXT",
        TINY_SAMPLE_TRAP: "RESEARCH_ONLY",
        BLOCKED_OR_UNKNOWN: "IGNORE_FOR_NOW",
    }.get(group, "IGNORE_FOR_NOW")


def _why(row: Mapping[str, Any]) -> str:
    group = str(row.get("priority_group") or "")
    if group == OFFICIAL_PROTECTED_TINY_LIVE_PATH:
        return "Official protected tiny-live path stays first; wait for 10/10 and do not change lane mode."
    if group == NEAR_THRESHOLD_ALTERNATE:
        return "Known entry mode and at least 5 unique captures make this a paper-only near-threshold watch, not a promotion."
    if group == OUTCOME_STRONG_CAPTURE_BLOCKED:
        return "Outcome evidence is strong, but unique captures remain below 10 and live eligibility is not implied."
    if group == TINY_SAMPLE_TRAP:
        return "Perfect win rate with fewer than 30 known outcomes is research-only tiny-sample evidence."
    return "Missing entry mode, unique captures, known outcomes, or fresh evidence keeps this low priority."


def _outcome_strong(row: Mapping[str, Any]) -> bool:
    quality = str(row.get("win_rate_quality_bucket") or "")
    score = float(row.get("outcome_quality_score") or row.get("combined_watch_score") or 0.0)
    known = int(row.get("known_outcome_count") or 0)
    return known >= 30 and (quality in {"STRONG", "VERY_STRONG"} or score >= 45.0)


def _official_blockers(summary: Mapping[str, Any]) -> list[str]:
    blockers = []
    if not summary.get("threshold_met"):
        blockers.append("official_lane_waiting_for_10_of_10")
    if summary.get("watcher_stale"):
        blockers.append("official_lane_watcher_stale")
    blockers.extend(["live_authorization_absent_by_design", "risk_contract_changes_forbidden_by_r233"])
    return blockers


def _hard_live_blockers() -> list[str]:
    return [
        "R233 is paper-only audit and cannot authorize live.",
        "Priority rank is not tiny-live readiness.",
        "Outcome score is not live eligibility.",
        "Betrayal/inverse context is not live eligibility.",
        "Official protected path must independently reach 10/10.",
        "No config, lane, fisherman, scheduler, or risk-contract writes are allowed.",
    ]


def _recommended_next_operator_move(
    official_summary: Mapping[str, Any],
    rebalance_plan: Mapping[str, Any],
    betrayal_shadow_context: Mapping[str, Any],
) -> str:
    if official_summary.get("threshold_met"):
        return "RUN_R228_TINY_LIVE_10_OF_10_READY_PACKET"
    if "BTCUSDT|8m|long|ladder_close_50_618" in set(rebalance_plan.get("near_threshold_alternates") or []):
        return "WATCH_8M_LONG"
    if betrayal_shadow_context.get("candidate_lanes"):
        return "PRESERVE_BETRAYAL_SHADOW"
    return "KEEP_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(
    official_summary: Mapping[str, Any],
    rebalance_plan: Mapping[str, Any],
    betrayal_shadow_context: Mapping[str, Any],
) -> str:
    if official_summary.get("threshold_met"):
        return "Run R228 checklist-only ready packet; still no live execution or config writes."
    if betrayal_shadow_context.get("candidate_lanes"):
        return "Run R234 betrayal shadow priority refresh while continuing to wait for official 10/10."
    if rebalance_plan.get("near_threshold_alternates"):
        return "Keep R233 priority as paper-only guidance and continue capture monitoring."
    return "Keep fisherman running and refresh R232/R231 before changing any engineering scope."


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


def _is_betrayal_candidate(row: Mapping[str, Any]) -> bool:
    text = " ".join(str(row.get(key) or "") for key in ("candidate", "source_family", "schema_version", "betrayal_event_identity"))
    return "betrayal" in text.lower() or "aggregate" in text.lower()


def _empty_official_summary(lane_key: str, *, threshold_required_count: int) -> dict[str, Any]:
    return {
        "lane_key": lane_key,
        "fresh_capture_count": 0,
        "required_fresh_capture_count": int(threshold_required_count),
        "threshold_met": False,
        "threshold_distance_remaining": int(threshold_required_count),
        "combined_watch_score": None,
        "win_rate_pct": None,
        "known_outcome_count": 0,
        "fisherman_status": "FISHERMAN_NEEDS_REVIEW",
        "watcher_likely_running": False,
        "watcher_stale": False,
        "recommended_action": "KEEP_AS_OFFICIAL_AND_WAIT_FOR_10_OF_10",
    }


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
        "entry_mode": str(entry_mode).strip().lower() or "entry_unknown",
    }


def _latest_record(path: Path) -> dict[str, Any]:
    records = _read_records(path, limit=1)
    return records[0] if records else {}


def _read_records(path: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    if limit == 0:
        if not path.exists():
            return []
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        records.reverse()
        return [_sanitize(record) for record in records]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit)]


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
