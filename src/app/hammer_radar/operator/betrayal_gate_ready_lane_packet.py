"""R234 betrayal gate-ready lane packet.

Paper-only gate preparation for betrayal lanes. This module reads existing
local ledgers, builds an explicit requirement packet, and optionally appends
that packet to its own audit ledger after an exact confirmation phrase.
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
from src.app.hammer_radar.operator.capture_priority_rebalance import (
    build_capture_priority_rebalance,
    load_capture_priority_rebalance_records,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import (
    DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    DEFAULT_THRESHOLD_REQUIRED_COUNT,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.lane_outcome_enrichment import normalize_lane_key

BETRAYAL_GATE_READY_LANE_PACKET_READY = "BETRAYAL_GATE_READY_LANE_PACKET_READY"
BETRAYAL_GATE_READY_LANE_PACKET_REJECTED = "BETRAYAL_GATE_READY_LANE_PACKET_REJECTED"
BETRAYAL_GATE_READY_LANE_PACKET_RECORDED = "BETRAYAL_GATE_READY_LANE_PACKET_RECORDED"
BETRAYAL_GATE_READY_LANE_PACKET_BLOCKED = "BETRAYAL_GATE_READY_LANE_PACKET_BLOCKED"
BETRAYAL_GATE_READY_LANE_PACKET_ERROR = "BETRAYAL_GATE_READY_LANE_PACKET_ERROR"

BETRAYAL_SHADOW_GATE_PREPARED = "BETRAYAL_SHADOW_GATE_PREPARED"
BETRAYAL_ACTIVE_SHADOW_NEEDS_ENTRY_MODE = "BETRAYAL_ACTIVE_SHADOW_NEEDS_ENTRY_MODE"
BETRAYAL_ACTIVE_SHADOW_NEEDS_CONTRACT_ADOPTION = "BETRAYAL_ACTIVE_SHADOW_NEEDS_CONTRACT_ADOPTION"
BETRAYAL_WAITING_FOR_TRUE_INVERSE_OUTCOMES = "BETRAYAL_WAITING_FOR_TRUE_INVERSE_OUTCOMES"
BETRAYAL_WAITING_FOR_GLOBAL_10_OF_10 = "BETRAYAL_WAITING_FOR_GLOBAL_10_OF_10"
BETRAYAL_NOT_ENOUGH_DATA = "BETRAYAL_NOT_ENOUGH_DATA"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

GATE_READY_SHADOW = "GATE_READY_SHADOW"
NEEDS_ENTRY_MODE = "NEEDS_ENTRY_MODE"
NEEDS_LANE_KEY = "NEEDS_LANE_KEY"
NEEDS_TRUE_INVERSE_OUTCOMES = "NEEDS_TRUE_INVERSE_OUTCOMES"
NEEDS_CONTRACT_ADOPTION = "NEEDS_CONTRACT_ADOPTION"
RESEARCH_ONLY = "RESEARCH_ONLY"

EVENT_TYPE = "BETRAYAL_GATE_READY_LANE_PACKET"
LEDGER_FILENAME = "betrayal_gate_ready_lane_packet.ndjson"
CONFIRM_BETRAYAL_GATE_READY_LANE_PACKET_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL GATE READY LANE PACKET RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "normalized_rows_appended": False,
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
    "betrayal_gate_prepared_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/capture_priority_rebalance.ndjson",
    "logs/hammer_radar_forward/betrayal_upstream_emitter_entry_mode_contract.ndjson",
    "logs/hammer_radar_forward/betrayal_entry_mode_source_propagation.ndjson",
    "logs/hammer_radar_forward/betrayal_direction_completion.ndjson",
    "logs/hammer_radar_forward/betrayal_renormalize_with_entry_mode.ndjson",
    "logs/hammer_radar_forward/betrayal_entry_mode_evidence_wiring.ndjson",
    "logs/hammer_radar_forward/betrayal_source_identity_evidence_collector.ndjson",
    "logs/hammer_radar_forward/betrayal_source_identity_normalizer.ndjson",
    "logs/hammer_radar_forward/betrayal_source_emitter_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_resolutions.ndjson",
    "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_signals.ndjson",
    "logs/hammer_radar_forward/weekend_paper_fisherman_supervisor.ndjson",
    "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_gate_ready_lane_packet(
    *,
    log_dir: str | Path | None = None,
    record_packet: bool = False,
    confirm_betrayal_gate_ready_lane_packet: str | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_betrayal_gate_ready_lane_packet == CONFIRM_BETRAYAL_GATE_READY_LANE_PACKET_RECORDING_PHRASE
    try:
        capture_priority = load_latest_capture_priority_rebalance(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        upstream_contract = load_latest_betrayal_upstream_contract(log_dir=resolved_log_dir)
        source_propagation = load_latest_betrayal_entry_mode_source_propagation(log_dir=resolved_log_dir)
        direction_completion = load_latest_betrayal_direction_completion(log_dir=resolved_log_dir)
        shadow_outcomes = load_latest_betrayal_shadow_outcomes(log_dir=resolved_log_dir)
        fisherman = load_latest_weekend_fisherman_supervisor(log_dir=resolved_log_dir)
        tiny_live_sync = load_latest_tiny_live_capture_count_sync(log_dir=resolved_log_dir)

        official_status = _build_official_tiny_live_status(
            capture_priority=capture_priority,
            tiny_live_sync=tiny_live_sync,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        registry = build_betrayal_candidate_lane_registry(
            capture_priority_rebalance=capture_priority,
            betrayal_upstream_contract=upstream_contract,
            betrayal_source_propagation=source_propagation,
            betrayal_direction_completion=direction_completion,
            betrayal_shadow_outcomes=shadow_outcomes,
            weekend_fisherman_supervisor=fisherman,
        )
        checklist = build_betrayal_activation_gate_checklist(registry)
        auto_open = build_betrayal_auto_open_readiness_packet(
            registry,
            official_tiny_live_status=official_status,
            activation_gate_checklist=checklist,
            upstream_contract=upstream_contract,
        )
        remaining_work = build_betrayal_remaining_work_plan(
            registry,
            official_tiny_live_status=official_status,
            upstream_contract=upstream_contract,
        )
        focus_plan = build_betrayal_focus_alignment_plan(official_status)
        recommendations = build_betrayal_gate_ready_recommendations(
            registry,
            official_tiny_live_status=official_status,
            upstream_contract=upstream_contract,
        )
        gate_packet_status = classify_betrayal_gate_ready_packet_status(
            registry,
            official_tiny_live_status=official_status,
            upstream_contract=upstream_contract,
        )
        status = BETRAYAL_GATE_READY_LANE_PACKET_READY if registry else BETRAYAL_GATE_READY_LANE_PACKET_BLOCKED
        if record_packet and not confirmation_valid:
            status = BETRAYAL_GATE_READY_LANE_PACKET_REJECTED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "packet_recorded": False,
            "packet_id": None,
            "record_packet_requested": bool(record_packet),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "paper_only": True,
                "live_authorized": False,
                "betrayal_shadow_active": bool(registry),
                "betrayal_gate_prepared": bool(registry),
                "official_tiny_live_lane": official_tiny_live_lane,
                "official_tiny_live_lane_changed": False,
            },
            "input_summary": {
                "capture_priority_rebalance_found": bool(capture_priority.get("rebalance_id")),
                "betrayal_upstream_contract_found": bool(upstream_contract.get("contract_id")),
                "betrayal_source_propagation_found": bool(source_propagation.get("propagation_id")),
                "betrayal_direction_completion_found": bool(direction_completion.get("completion_id")),
                "betrayal_shadow_outcomes_found": bool(shadow_outcomes),
                "weekend_fisherman_supervisor_found": bool(fisherman),
                "tiny_live_capture_sync_found": bool(tiny_live_sync),
            },
            "official_tiny_live_status": official_status,
            "betrayal_candidate_lane_registry": registry,
            "betrayal_activation_gate_checklist": checklist,
            "betrayal_auto_open_readiness_packet": auto_open,
            "betrayal_remaining_work_plan": remaining_work,
            "focus_alignment_plan": focus_plan,
            "betrayal_gate_ready_recommendations": recommendations,
            "gate_packet_status": gate_packet_status,
            "recommended_next_operator_move": _recommended_next_operator_move(official_status),
            "recommended_next_engineering_move": remaining_work.get("minimal_next_engineering_step"),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_packet and confirmation_valid:
            record = append_betrayal_gate_ready_lane_packet_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_GATE_READY_LANE_PACKET_RECORDED
            payload["packet_recorded"] = True
            payload["packet_id"] = record["packet_id"]
            payload["ledger_path"] = str(betrayal_gate_ready_lane_packet_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_GATE_READY_LANE_PACKET_ERROR,
                "generated_at": generated_at.isoformat(),
                "packet_recorded": False,
                "packet_id": None,
                "record_packet_requested": bool(record_packet),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {
                    "paper_only": True,
                    "live_authorized": False,
                    "betrayal_shadow_active": False,
                    "betrayal_gate_prepared": False,
                    "official_tiny_live_lane": official_tiny_live_lane,
                    "official_tiny_live_lane_changed": False,
                },
                "input_summary": {},
                "official_tiny_live_status": _empty_official_status(official_tiny_live_lane, threshold_required_count),
                "betrayal_candidate_lane_registry": [],
                "betrayal_activation_gate_checklist": build_betrayal_activation_gate_checklist([]),
                "betrayal_auto_open_readiness_packet": {
                    "can_auto_open_today": False,
                    "can_wait_at_gate": False,
                    "auto_open_when": _auto_open_when(),
                    "blocked_by": ["betrayal_gate_ready_packet_error"],
                },
                "betrayal_remaining_work_plan": build_betrayal_remaining_work_plan([], official_tiny_live_status={}),
                "focus_alignment_plan": build_betrayal_focus_alignment_plan({}),
                "betrayal_gate_ready_recommendations": [],
                "gate_packet_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R234 packet build error before using betrayal gate context.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_capture_priority_rebalance(
    *,
    log_dir: str | Path | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
) -> dict[str, Any]:
    records = load_capture_priority_rebalance_records(log_dir=log_dir, limit=1)
    if records:
        return _sanitize(records[0])
    return _sanitize(
        build_capture_priority_rebalance(
            log_dir=log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
    )


def load_latest_betrayal_upstream_contract(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_upstream_emitter_entry_mode_contract.ndjson")


def load_latest_betrayal_entry_mode_source_propagation(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_entry_mode_source_propagation.ndjson")


def load_latest_betrayal_direction_completion(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_direction_completion.ndjson")


def load_latest_betrayal_shadow_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    resolved = get_log_dir(log_dir, use_env=True)
    rows = []
    for filename in (
        "betrayal_shadow_outcomes.ndjson",
        "betrayal_shadow_resolutions.ndjson",
        "betrayal_true_paper_outcomes.ndjson",
        "betrayal_paper_signals.ndjson",
    ):
        rows.extend(_read_records(resolved / filename, limit=500))
    return _sanitize(_dedupe_rows(rows))


def load_latest_weekend_fisherman_supervisor(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "weekend_paper_fisherman_supervisor.ndjson")


def load_latest_tiny_live_capture_count_sync(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "capture_count_sync_8m_short.ndjson")


def build_betrayal_candidate_lane_registry(
    *,
    capture_priority_rebalance: Mapping[str, Any],
    betrayal_upstream_contract: Mapping[str, Any],
    betrayal_source_propagation: Mapping[str, Any],
    betrayal_direction_completion: Mapping[str, Any],
    betrayal_shadow_outcomes: Sequence[Mapping[str, Any]],
    weekend_fisherman_supervisor: Mapping[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    shadow_context = dict(capture_priority_rebalance.get("betrayal_shadow_context") or {})
    for row in shadow_context.get("candidate_lanes") or []:
        candidates.append(_registry_row_from_candidate(row, source_hint=row.get("source") or "capture_priority_rebalance"))

    for row in betrayal_source_propagation.get("entry_mode_propagated_rows_preview") or []:
        candidates.append(_registry_row_from_candidate(row, source_hint="betrayal_entry_mode_source_propagation"))

    for row in betrayal_direction_completion.get("direction_completed_rows_preview") or []:
        candidates.append(_registry_row_from_candidate(row, source_hint="betrayal_direction_completion"))

    for row in betrayal_shadow_outcomes:
        candidates.append(_registry_row_from_candidate(row, source_hint=row.get("source") or "betrayal_shadow_outcomes"))

    summary = dict(weekend_fisherman_supervisor.get("betrayal_watch_summary") or {})
    if summary:
        if summary.get("latest_222m_capture_lane") or summary.get("primary_betrayal_candidate"):
            candidates.append(
                _registry_row_from_candidate(
                    {
                        "lane_key": summary.get("latest_222m_capture_lane"),
                        "candidate": summary.get("primary_betrayal_candidate") or "222m aggregate",
                        "win_rate_pct": summary.get("primary_betrayal_naive_inverse_win_rate_pct"),
                        "source": "weekend_supervisor",
                    },
                    source_hint="weekend_supervisor",
                )
            )
        if summary.get("watchlist_betrayal_candidate"):
            candidates.append(
                _registry_row_from_candidate(
                    {
                        "candidate": summary.get("watchlist_betrayal_candidate"),
                        "symbol": "BTCUSDT",
                        "timeframe": "88m",
                        "direction": "inverse",
                        "entry_mode": "entry_unknown",
                        "win_rate_pct": summary.get("watchlist_betrayal_naive_inverse_win_rate_pct"),
                        "source": "weekend_supervisor",
                    },
                    source_hint="weekend_supervisor",
                )
            )

    contract_ready = _contract_surfaces_ready(betrayal_upstream_contract)
    rows = []
    for candidate in _merge_candidates(candidates):
        row = dict(candidate)
        row["gate_preparation_status"] = classify_betrayal_gate_preparation_status(row, contract_ready=contract_ready)
        row["requirements"] = build_betrayal_lane_requirements(row, contract_ready=contract_ready)
        row["why"] = _candidate_why(row)
        rows.append(_public_registry_row(row))
    rows.sort(key=lambda row: (str(row.get("gate_preparation_status") or ""), str(row.get("lane_key") or "")))
    return _sanitize(rows)


def classify_betrayal_gate_preparation_status(row: Mapping[str, Any], *, contract_ready: bool = False) -> str:
    if str(row.get("shadow_status") or "") == "RESEARCH_ONLY":
        return RESEARCH_ONLY
    if _missing_entry_mode(row):
        return NEEDS_ENTRY_MODE
    if not row.get("lane_key") or str(row.get("lane_key")).endswith("|entry_unknown"):
        return NEEDS_LANE_KEY
    if int(row.get("known_outcome_count") or 0) <= 0 and int(row.get("paper_signal_count") or 0) <= 0:
        return NEEDS_TRUE_INVERSE_OUTCOMES
    if not contract_ready:
        return NEEDS_CONTRACT_ADOPTION
    return GATE_READY_SHADOW


def build_betrayal_lane_requirements(row: Mapping[str, Any], *, contract_ready: bool = False) -> list[str]:
    requirements = [
        "global live/tiny-live gates open through future approved workflow",
        "operator approval exists for betrayal family",
        "risk contract exists for candidate lane",
        "kill switch policy satisfied",
        "paper/live separation verified",
    ]
    if _missing_entry_mode(row):
        requirements.append("entry_mode registry-valid for candidate lane")
    if not row.get("lane_key") or str(row.get("lane_key")).endswith("|entry_unknown"):
        requirements.append("lane_key exists")
    if not row.get("source") or row.get("source") == "unknown":
        requirements.append("source identity exists")
    if str(row.get("direction") or "unknown") == "unknown":
        requirements.append("direction/inverse direction complete")
    if int(row.get("known_outcome_count") or 0) <= 0 and int(row.get("paper_signal_count") or 0) <= 0:
        requirements.append("true inverse/paper outcomes meet threshold")
    if not contract_ready:
        requirements.append("future source emitter contract adopted for candidate source")
    return _dedupe(requirements)


def build_betrayal_activation_gate_checklist(registry: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "global_requirements": [
            "official protected tiny-live path reaches 10/10 or future approved lane threshold reaches 10/10",
            "risk contract exists",
            "operator approval exists",
            "live execution enabled by explicit future workflow",
            "kill switch policy satisfied",
            "paper/live separation verified",
        ],
        "betrayal_specific_requirements": [
            "entry_mode registry-valid for candidate lane",
            "lane_key exists",
            "source identity exists",
            "direction/inverse direction complete",
            "true inverse/paper outcomes meet threshold",
            "future source emitter contract adopted for candidate source",
        ],
        "all_requirements_known": bool(registry),
        "live_ready_today": False,
    }


def build_betrayal_auto_open_readiness_packet(
    registry: Sequence[Mapping[str, Any]],
    *,
    official_tiny_live_status: Mapping[str, Any],
    activation_gate_checklist: Mapping[str, Any],
    upstream_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blocked_by = []
    if not official_tiny_live_status.get("threshold_met"):
        blocked_by.append("official_8m_short_not_10_of_10")
    if not registry:
        blocked_by.append("betrayal_candidate_registry_empty")
    statuses = {str(row.get("gate_preparation_status") or "") for row in registry}
    for status, blocker in (
        (NEEDS_ENTRY_MODE, "entry_mode_missing"),
        (NEEDS_LANE_KEY, "lane_key_missing"),
        (NEEDS_TRUE_INVERSE_OUTCOMES, "true_inverse_or_paper_outcomes_missing"),
        (NEEDS_CONTRACT_ADOPTION, "r230_contract_not_adopted_by_all_surfaces"),
    ):
        if status in statuses:
            blocked_by.append(blocker)
    blocked_by.extend(
        [
            "risk_contract_not_written_by_this_phase",
            "operator_approval_missing",
            "live_execution_not_enabled",
            "betrayal_live_authorization_missing",
        ]
    )
    return {
        "can_auto_open_today": False,
        "can_wait_at_gate": bool(registry and activation_gate_checklist.get("all_requirements_known")),
        "auto_open_when": _auto_open_when(),
        "blocked_by": _dedupe(blocked_by),
    }


def build_betrayal_remaining_work_plan(
    registry: Sequence[Mapping[str, Any]],
    *,
    official_tiny_live_status: Mapping[str, Any] | None = None,
    upstream_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    statuses = {str(row.get("gate_preparation_status") or "") for row in registry}
    must_do = ["keep betrayal paper/shadow only until explicit future live gate"]
    if NEEDS_ENTRY_MODE in statuses:
        must_do.append("adopt R230 entry_mode contract in remaining betrayal source emitters")
    if NEEDS_LANE_KEY in statuses:
        must_do.append("derive lane_key only from registry-valid entry_mode plus complete direction")
    if NEEDS_TRUE_INVERSE_OUTCOMES in statuses:
        must_do.append("collect true inverse or paper outcomes without rewriting historical ledgers")
    if NEEDS_CONTRACT_ADOPTION in statuses:
        must_do.append("finish future contract adoption for betrayal surfaces")
    if not (official_tiny_live_status or {}).get("threshold_met"):
        must_do.append("wait for official 8m short 10/10 before R228")
    return {
        "must_do_before_live_gate": _dedupe(must_do),
        "can_wait_until_after_10_of_10": [
            "risk contract drafting for any betrayal lane",
            "operator lane switch review for betrayal family",
            "future live authorization request",
        ],
        "not_needed_now": [
            "config writes",
            "lane mode changes",
            "risk contract writes",
            "Binance calls",
            "historical ledger rewrite",
        ],
        "minimal_next_engineering_step": "Run R235 lightweight status check after more official 8m short captures or adopt R230 in remaining betrayal emitters if working on betrayal plumbing.",
    }


def build_betrayal_focus_alignment_plan(official_tiny_live_status: Mapping[str, Any]) -> dict[str, str]:
    threshold_met = bool(official_tiny_live_status.get("threshold_met"))
    return {
        "primary_focus": "WAIT_FOR_OFFICIAL_8M_SHORT_10_OF_10",
        "secondary_watch": "8M_LONG_NEAR_THRESHOLD",
        "betrayal_watch": "ACTIVE_GATE_PREPARED_SHADOW",
        "next_if_10_of_10": "R228_TINY_LIVE_10_OF_10_READY_PACKET",
        "next_if_still_8_of_10": "KEEP_FISHERMAN_RUNNING_OR_LIGHTWEIGHT_STATUS_CHECK",
        "current_threshold_action": "RUN_R228_IF_10_OF_10" if threshold_met else "WAIT_FOR_10_OF_10",
    }


def build_betrayal_gate_ready_recommendations(
    registry: Sequence[Mapping[str, Any]],
    *,
    official_tiny_live_status: Mapping[str, Any],
    upstream_contract: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "KEEP_BETRAYAL_AT_GATE",
            "future_phase": "R235",
            "why": "Betrayal context is active shadow preparation only and must not be closed or promoted.",
        },
        {
            "priority": "HIGH",
            "recommended_action": "RUN_R228_IF_10_OF_10" if official_tiny_live_status.get("threshold_met") else "WAIT_FOR_10_OF_10",
            "future_phase": "R228",
            "why": "The official protected 8m short lane remains the only tiny-live readiness path.",
        },
    ]
    statuses = {str(row.get("gate_preparation_status") or "") for row in registry}
    if NEEDS_CONTRACT_ADOPTION in statuses or not _contract_surfaces_ready(upstream_contract or {}):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "ADOPT_CONTRACT_FOR_BETRAYAL_SURFACES",
                "future_phase": "R235",
                "why": "R230 exists but not every future betrayal emitter surface is contract-ready.",
            }
        )
    if NEEDS_ENTRY_MODE in statuses:
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "COLLECT_ENTRY_MODE_WITH_CONTRACT",
                "future_phase": "R235",
                "why": "Unknown-entry shadow rows can wait at the gate but cannot become live gate prepared.",
            }
        )
    return recommendations


def classify_betrayal_gate_ready_packet_status(
    registry: Sequence[Mapping[str, Any]],
    *,
    official_tiny_live_status: Mapping[str, Any],
    upstream_contract: Mapping[str, Any] | None = None,
) -> str:
    if not registry:
        return BETRAYAL_NOT_ENOUGH_DATA
    statuses = {str(row.get("gate_preparation_status") or "") for row in registry}
    if NEEDS_ENTRY_MODE in statuses or NEEDS_LANE_KEY in statuses:
        return BETRAYAL_ACTIVE_SHADOW_NEEDS_ENTRY_MODE
    if NEEDS_CONTRACT_ADOPTION in statuses:
        return BETRAYAL_ACTIVE_SHADOW_NEEDS_CONTRACT_ADOPTION
    if NEEDS_TRUE_INVERSE_OUTCOMES in statuses:
        return BETRAYAL_WAITING_FOR_TRUE_INVERSE_OUTCOMES
    if not official_tiny_live_status.get("threshold_met"):
        return BETRAYAL_WAITING_FOR_GLOBAL_10_OF_10
    if GATE_READY_SHADOW in statuses:
        return BETRAYAL_SHADOW_GATE_PREPARED
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_betrayal_gate_ready_lane_packet_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_gate_ready_lane_packet_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "packet_id": str(record.get("packet_id") or f"r234_betrayal_gate_ready_lane_packet_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_GATE_READY_LANE_PACKET_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_packet_requested": bool(record.get("record_packet_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "official_tiny_live_status": dict(record.get("official_tiny_live_status") or {}),
            "betrayal_candidate_lane_registry": list(record.get("betrayal_candidate_lane_registry") or []),
            "betrayal_activation_gate_checklist": dict(record.get("betrayal_activation_gate_checklist") or {}),
            "betrayal_auto_open_readiness_packet": dict(record.get("betrayal_auto_open_readiness_packet") or {}),
            "betrayal_remaining_work_plan": dict(record.get("betrayal_remaining_work_plan") or {}),
            "focus_alignment_plan": dict(record.get("focus_alignment_plan") or {}),
            "betrayal_gate_ready_recommendations": list(record.get("betrayal_gate_ready_recommendations") or []),
            "gate_packet_status": record.get("gate_packet_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_betrayal_gate_ready_lane_packet_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_gate_ready_lane_packet_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_records(path, limit=0)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def summarize_betrayal_gate_ready_lane_packet_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "gate_packet_status_counts": dict(
            sorted(Counter(str(record.get("gate_packet_status") or "UNKNOWN") for record in records).items())
        ),
        "latest_packet_id": latest.get("packet_id") if isinstance(latest, Mapping) else None,
        "latest_gate_packet_status": latest.get("gate_packet_status") if isinstance(latest, Mapping) else None,
        "safety": dict(SAFETY),
    }


def betrayal_gate_ready_lane_packet_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_gate_ready_lane_packet_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _build_official_tiny_live_status(
    *,
    capture_priority: Mapping[str, Any],
    tiny_live_sync: Mapping[str, Any],
    official_tiny_live_lane: str,
    threshold_required_count: int,
) -> dict[str, Any]:
    summary = dict(capture_priority.get("official_protected_path_summary") or {})
    capture = dict(tiny_live_sync.get("capture_count") or {})
    fresh = int(summary.get("fresh_capture_count") or capture.get("fresh_capture_count") or 0)
    required = int(summary.get("required_fresh_capture_count") or capture.get("required_fresh_capture_count") or threshold_required_count)
    threshold_met = bool(summary.get("threshold_met") or capture.get("threshold_met") or fresh >= required)
    return {
        "lane_key": official_tiny_live_lane,
        "fresh_capture_count": fresh,
        "required_fresh_capture_count": required,
        "threshold_met": threshold_met,
        "threshold_distance_remaining": max(0, required - fresh),
        "recommended_action": "RUN_R228_IF_10_OF_10" if threshold_met else "WAIT_FOR_10_OF_10",
    }


def _empty_official_status(lane_key: str, required: int) -> dict[str, Any]:
    return {
        "lane_key": lane_key,
        "fresh_capture_count": 0,
        "required_fresh_capture_count": required,
        "threshold_met": False,
        "threshold_distance_remaining": required,
        "recommended_action": "WAIT_FOR_10_OF_10",
    }


def _registry_row_from_candidate(row: Mapping[str, Any], *, source_hint: Any) -> dict[str, Any]:
    lane = _lane_from_candidate(row)
    known_outcomes = int(row.get("known_outcome_count") or row.get("samples") or row.get("outcome_count") or 0)
    paper_signals = int(row.get("paper_signal_count") or (1 if row.get("original_signal_id") or row.get("signal_id") else 0))
    shadow_status = _shadow_status(row)
    return {
        "lane_key": lane["lane_key"],
        "candidate": str(row.get("candidate") or row.get("betrayal_tier") or "BETRAYAL_WATCH"),
        "symbol": lane["symbol"],
        "timeframe": lane["timeframe"],
        "direction": lane["direction"],
        "entry_mode": lane["entry_mode"],
        "source": str(row.get("source") or source_hint or "unknown"),
        "win_rate_pct": row.get("win_rate_pct"),
        "known_outcome_count": known_outcomes or None,
        "paper_signal_count": paper_signals or None,
        "shadow_status": shadow_status,
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _public_registry_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_key": row.get("lane_key"),
        "candidate": row.get("candidate"),
        "symbol": row.get("symbol"),
        "timeframe": row.get("timeframe"),
        "direction": row.get("direction"),
        "entry_mode": row.get("entry_mode"),
        "source": row.get("source"),
        "win_rate_pct": row.get("win_rate_pct"),
        "known_outcome_count": row.get("known_outcome_count"),
        "paper_signal_count": row.get("paper_signal_count"),
        "shadow_status": row.get("shadow_status"),
        "gate_preparation_status": row.get("gate_preparation_status"),
        "live_authorized": False,
        "promotion_allowed": False,
        "why": row.get("why"),
    }


def _lane_from_candidate(row: Mapping[str, Any]) -> dict[str, str]:
    lane_key = _string_or_none(row.get("lane_key") or row.get("lane_key_preview"))
    parts = lane_key.split("|") if lane_key else []
    if len(parts) >= 4 and _looks_like_symbol(parts[0]):
        return {
            "lane_key": "|".join(parts[:4]),
            "symbol": parts[0],
            "timeframe": parts[1],
            "direction": _normal_direction(parts[2]) or "unknown",
            "entry_mode": parts[3] or "entry_unknown",
        }
    symbol = _string_or_none(row.get("symbol")) or "BTCUSDT"
    timeframe = _string_or_none(row.get("timeframe")) or _timeframe_from_candidate(row.get("candidate"))
    direction = (
        _normal_direction(row.get("direction"))
        or _normal_direction(row.get("emitted_direction"))
        or _normal_direction(row.get("inverse_direction"))
        or _normal_direction(row.get("shadow_direction"))
        or "unknown"
    )
    entry_mode = _string_or_none(row.get("entry_mode")) or "entry_unknown"
    return {
        "lane_key": normalize_lane_key(symbol, timeframe, direction, entry_mode),
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
    }


def _merge_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = str(candidate.get("lane_key") or "")
        if not key:
            continue
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(candidate)
            continue
        existing["known_outcome_count"] = max(int(existing.get("known_outcome_count") or 0), int(candidate.get("known_outcome_count") or 0)) or None
        existing["paper_signal_count"] = max(int(existing.get("paper_signal_count") or 0), int(candidate.get("paper_signal_count") or 0)) or None
        if existing.get("win_rate_pct") is None and candidate.get("win_rate_pct") is not None:
            existing["win_rate_pct"] = candidate.get("win_rate_pct")
        if existing.get("entry_mode") == "entry_unknown" and candidate.get("entry_mode") not in (None, "entry_unknown"):
            existing["entry_mode"] = candidate.get("entry_mode")
        if existing.get("direction") == "unknown" and candidate.get("direction") not in (None, "unknown"):
            existing["direction"] = candidate.get("direction")
        existing["source"] = "|".join(_dedupe(_source_tokens(existing.get("source")) + _source_tokens(candidate.get("source"))))
    return list(merged.values())


def _candidate_why(row: Mapping[str, Any]) -> str:
    status = str(row.get("gate_preparation_status") or "")
    if status == GATE_READY_SHADOW:
        return "Betrayal lane is active paper/shadow context with explicit blockers; live remains blocked by future gates."
    if status == NEEDS_ENTRY_MODE:
        return "Betrayal lane can wait at the gate, but entry_mode must be explicit and registry-valid before live-gate preparation."
    if status == NEEDS_LANE_KEY:
        return "Betrayal lane can wait at the gate, but lane_key must be complete before live-gate preparation."
    if status == NEEDS_TRUE_INVERSE_OUTCOMES:
        return "Betrayal lane has identity but still needs true inverse or paper outcome evidence before any live-gate review."
    if status == NEEDS_CONTRACT_ADOPTION:
        return "Betrayal lane has paper identity but remaining source emitters must adopt the R230 contract."
    return "Betrayal row remains research-only context and creates no live eligibility."


def _shadow_status(row: Mapping[str, Any]) -> str:
    if row.get("shadow_only") is False:
        return "RESEARCH_ONLY"
    status = str(row.get("shadow_status") or "")
    if status and status not in {"SHADOW_NO_DATA", "UNKNOWN"}:
        return "ACTIVE_SHADOW"
    if row.get("original_signal_id") or row.get("signal_id") or row.get("shadow_direction") or row.get("candidate"):
        return "ACTIVE_SHADOW"
    return "RESEARCH_ONLY"


def _contract_surfaces_ready(contract: Mapping[str, Any]) -> bool:
    report = dict(contract.get("future_emitter_contract_readiness_report") or {})
    inspected = int(report.get("surfaces_inspected") or 0)
    ready = int(report.get("surfaces_future_contract_ready") or 0)
    return bool(inspected and ready >= inspected)


def _missing_entry_mode(row: Mapping[str, Any]) -> bool:
    return not row.get("entry_mode") or str(row.get("entry_mode")).lower() in {"unknown", "entry_unknown", "none", "null"}


def _recommended_next_operator_move(official_status: Mapping[str, Any]) -> str:
    return "RUN_R228_TINY_LIVE_10_OF_10_READY_PACKET" if official_status.get("threshold_met") else "WAIT_FOR_10_OF_10"


def _auto_open_when() -> list[str]:
    return [
        "global live gates open",
        "candidate betrayal lane requirements pass",
        "operator lane switch allows betrayal family",
        "risk contract exists",
        "no safety blocker active",
    ]


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
        "betrayal live promotion",
    ]


def _timeframe_from_candidate(candidate: Any) -> str:
    text = str(candidate or "").strip().split(" ")[0].lower()
    return text if text and text != "none" else "unknown"


def _normal_direction(value: Any) -> str | None:
    text = str(value or "").lower()
    return text if text in {"long", "short", "inverse"} else None


def _looks_like_symbol(value: Any) -> bool:
    text = str(value or "")
    return text.isupper() and text.endswith("USDT")


def _source_tokens(value: Any) -> list[str]:
    return [token for token in str(value or "").split("|") if token]


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "unknown"}:
        return None
    return text


def _latest_record(path: Path) -> dict[str, Any]:
    records = _read_records(path, limit=1)
    return records[0] if records else {}


def _read_records(path: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if limit > 0:
        return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(_sanitize(payload))
    return records


def _dedupe_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (
            str(row.get("shadow_outcome_id") or ""),
            str(row.get("original_signal_id") or row.get("signal_id") or ""),
            str(row.get("symbol") or ""),
            str(row.get("timeframe") or ""),
            str(row.get("shadow_direction") or row.get("direction") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(row))
    return deduped


def _dedupe(values: Sequence[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        text = str(value or "")
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_sanitize(inner) for inner in value]
    if isinstance(value, tuple):
        return [_sanitize(inner) for inner in value]
    if isinstance(value, Path):
        return str(value)
    return value
