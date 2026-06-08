"""R235 betrayal signal-origin integration contract.

Paper-only integration contract that maps existing betrayal shadow/context rows
into the same signal-origin preview schema used by normal paper flow surfaces.
It never mutates configs, rewrites source ledgers, promotes betrayal, or
authorizes live execution.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_gate_ready_lane_packet import (
    build_betrayal_gate_ready_lane_packet,
    load_betrayal_gate_ready_lane_packet_records,
)
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
from src.app.hammer_radar.operator.strategy_evidence_registry import get_entry_mode_manifest

BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_READY = "BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_READY"
BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_REJECTED = "BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_REJECTED"
BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_RECORDED = "BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_RECORDED"
BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_BLOCKED = "BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_BLOCKED"
BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_ERROR = "BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_ERROR"

BETRAYAL_SIGNAL_ORIGIN_CONTRACT_READY = "BETRAYAL_SIGNAL_ORIGIN_CONTRACT_READY"
BETRAYAL_SAME_FLOW_PARTIALLY_READY = "BETRAYAL_SAME_FLOW_PARTIALLY_READY"
BETRAYAL_SAME_FLOW_NEEDS_ENTRY_MODE = "BETRAYAL_SAME_FLOW_NEEDS_ENTRY_MODE"
BETRAYAL_SAME_FLOW_NEEDS_OUTCOME_TRACKING = "BETRAYAL_SAME_FLOW_NEEDS_OUTCOME_TRACKING"
BETRAYAL_PROMOTION_PATH_KNOWN_BUT_BLOCKED = "BETRAYAL_PROMOTION_PATH_KNOWN_BUT_BLOCKED"
BETRAYAL_NOT_ENOUGH_DATA = "BETRAYAL_NOT_ENOUGH_DATA"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT"
LEDGER_FILENAME = "betrayal_signal_origin_integration_contract.ndjson"
CONTRACT_NAME = "betrayal_signal_origin_contract_v1"
SCHEMA_VERSION = "betrayal_signal_origin_preview_v1"
CONFIRM_BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL SIGNAL ORIGIN INTEGRATION CONTRACT RECORDING ONLY; "
    "NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

REQUIRED_FIELDS_FOR_PAPER_SIGNAL = [
    "schema_version",
    "signal_origin_family",
    "signal_origin_type",
    "signal_origin_variant",
    "symbol",
    "timeframe",
    "direction",
    "entry_mode",
    "lane_key",
    "signal_id",
    "source_signal_id",
    "source_identity",
    "paper_only",
]
REQUIRED_FIELDS_FOR_PAPER_OUTCOME = [
    *REQUIRED_FIELDS_FOR_PAPER_SIGNAL,
    "paper_outcome_tracking_identity",
    "outcome_window_spec",
]
REQUIRED_FIELDS_FOR_RANKING = [
    *REQUIRED_FIELDS_FOR_PAPER_OUTCOME,
    "paper_outcomes_exist_or_trackable",
    "lane_key",
]
REQUIRED_FIELDS_FOR_PROMOTION_GATE = [
    *REQUIRED_FIELDS_FOR_RANKING,
    "promotion_blockers",
    "live_authorized",
    "promotion_allowed",
]

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
    "betrayal_same_flow_contract_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/betrayal_gate_ready_lane_packet.ndjson",
    "logs/hammer_radar_forward/capture_priority_rebalance.ndjson",
    "logs/hammer_radar_forward/betrayal_upstream_emitter_entry_mode_contract.ndjson",
    "logs/hammer_radar_forward/betrayal_entry_mode_source_propagation.ndjson",
    "logs/hammer_radar_forward/betrayal_direction_completion.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_resolutions.ndjson",
    "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_signals.ndjson",
    "logs/hammer_radar_forward/paper_outcomes.ndjson",
    "logs/hammer_radar_forward/strategy_performance.ndjson",
    "logs/hammer_radar_forward/strategy_promotion_status.ndjson",
    "logs/hammer_radar_forward/full_spectrum_lane_scoreboard.ndjson",
    "logs/hammer_radar_forward/lane_outcome_enrichment.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_signal_origin_integration_contract(
    *,
    log_dir: str | Path | None = None,
    record_contract: bool = False,
    confirm_betrayal_signal_origin_integration_contract: str | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_signal_origin_integration_contract
        == CONFIRM_BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_RECORDING_PHRASE
    )
    try:
        gate_packet = load_latest_betrayal_gate_ready_lane_packet(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        capture_priority = load_latest_capture_priority_rebalance(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        upstream_contract = load_latest_betrayal_upstream_contract(log_dir=resolved_log_dir)
        source_propagation = load_latest_betrayal_entry_mode_source_propagation(log_dir=resolved_log_dir)
        direction_completion = load_latest_betrayal_direction_completion(log_dir=resolved_log_dir)
        schema_context = load_existing_signal_origin_schema_context(log_dir=resolved_log_dir)
        contract = build_betrayal_signal_origin_contract(schema_context=schema_context)
        rows = build_betrayal_same_flow_readiness_rows(
            betrayal_gate_ready_packet=gate_packet,
            capture_priority_rebalance=capture_priority,
            betrayal_upstream_contract=upstream_contract,
            betrayal_source_propagation=source_propagation,
            betrayal_direction_completion=direction_completion,
            schema_context=schema_context,
        )
        summary = _same_flow_summary(rows)
        gap_report = build_betrayal_integration_gap_report(rows)
        requirements = build_betrayal_promotion_path_requirements(rows)
        recommendations = build_betrayal_integration_recommendations(
            rows=rows,
            gap_report=gap_report,
            gate_packet=gate_packet,
            capture_priority=capture_priority,
        )
        integration_status = classify_betrayal_signal_origin_integration_status(
            rows=rows,
            gap_report=gap_report,
            requirements=requirements,
        )
        status = BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_READY if rows else BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_BLOCKED
        if record_contract and not confirmation_valid:
            status = BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_REJECTED
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "contract_recorded": False,
            "contract_id": None,
            "record_contract_requested": bool(record_contract),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "paper_only": True,
                "live_authorized": False,
                "betrayal_signal_origin_family": "betrayal",
                "same_flow_target": True,
                "official_tiny_live_lane": official_tiny_live_lane,
                "official_tiny_live_lane_changed": False,
            },
            "input_summary": {
                "betrayal_gate_ready_packet_found": bool(gate_packet.get("betrayal_candidate_lane_registry")),
                "capture_priority_rebalance_found": bool(capture_priority.get("rebalance_id")),
                "betrayal_upstream_contract_found": bool(upstream_contract.get("contract_id")),
                "betrayal_source_propagation_found": bool(source_propagation.get("propagation_id")),
                "betrayal_direction_completion_found": bool(direction_completion.get("completion_id")),
                "normal_signal_schema_context_found": bool(schema_context.get("context_found")),
            },
            "betrayal_signal_origin_contract": contract,
            "same_flow_readiness_rows": rows,
            "same_flow_summary": summary,
            "betrayal_integration_gap_report": gap_report,
            "betrayal_promotion_path_requirements": requirements,
            "betrayal_integration_recommendations": recommendations,
            "integration_status": integration_status,
            "recommended_next_operator_move": _recommended_next_operator_move(gate_packet, capture_priority),
            "recommended_next_engineering_move": _recommended_next_engineering_move(integration_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_contract and confirmation_valid:
            record = append_betrayal_signal_origin_integration_contract_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_RECORDED
            payload["contract_recorded"] = True
            payload["contract_id"] = record["contract_id"]
            payload["ledger_path"] = str(betrayal_signal_origin_integration_contract_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_ERROR,
                "generated_at": generated_at.isoformat(),
                "contract_recorded": False,
                "contract_id": None,
                "record_contract_requested": bool(record_contract),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {
                    "paper_only": True,
                    "live_authorized": False,
                    "betrayal_signal_origin_family": "betrayal",
                    "same_flow_target": True,
                    "official_tiny_live_lane": official_tiny_live_lane,
                    "official_tiny_live_lane_changed": False,
                },
                "input_summary": {},
                "betrayal_signal_origin_contract": build_betrayal_signal_origin_contract(schema_context={}),
                "same_flow_readiness_rows": [],
                "same_flow_summary": _same_flow_summary([]),
                "betrayal_integration_gap_report": build_betrayal_integration_gap_report([]),
                "betrayal_promotion_path_requirements": build_betrayal_promotion_path_requirements([]),
                "betrayal_integration_recommendations": [],
                "integration_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R235 contract build error before adopting betrayal same-flow preview.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_gate_ready_lane_packet(
    *,
    log_dir: str | Path | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
) -> dict[str, Any]:
    records = load_betrayal_gate_ready_lane_packet_records(log_dir=log_dir, limit=1)
    if records:
        return _sanitize(records[0])
    return _sanitize(
        build_betrayal_gate_ready_lane_packet(
            log_dir=log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
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


def load_existing_signal_origin_schema_context(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved = get_log_dir(log_dir, use_env=True)
    files = {
        "paper_outcomes": "paper_outcomes.ndjson",
        "strategy_performance": "strategy_performance.ndjson",
        "strategy_promotion_status": "strategy_promotion_status.ndjson",
        "full_spectrum_lane_scoreboard": "full_spectrum_lane_scoreboard.ndjson",
        "lane_outcome_enrichment": "lane_outcome_enrichment.ndjson",
        "strategy_evidence_registry": "strategy_evidence_registry.ndjson",
    }
    latest = {name: _latest_record(resolved / filename) for name, filename in files.items()}
    entry_modes = [
        row["entry_mode"]
        for row in get_entry_mode_manifest()
        if isinstance(row, Mapping) and not row.get("blocked_placeholder")
    ]
    return _sanitize(
        {
            "context_found": any(bool(row) for row in latest.values()),
            "latest_records_found": {name: bool(row) for name, row in latest.items()},
            "registry_valid_entry_modes": entry_modes,
            "normal_flow_join_fields": [
                "symbol",
                "timeframe",
                "direction",
                "entry_mode",
                "lane_key",
                "signal_id",
                "source_signal_id",
                "paper_outcome_tracking_identity",
            ],
            "promotion_surfaces": ["strategy_performance", "strategy_promotion_status", "strategy_promotion_events"],
        }
    )


def build_betrayal_signal_origin_contract(*, schema_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "contract_name": CONTRACT_NAME,
        "signal_origin_family": "betrayal",
        "allowed_signal_origin_types": ["inverse", "aggregate", "shadow"],
        "allowed_signal_origin_variants": ["betrayal_inverse", "betrayal_aggregate", "betrayal_shadow"],
        "registry_valid_entry_modes": list((schema_context or {}).get("registry_valid_entry_modes") or []),
        "required_fields_for_paper_signal": list(REQUIRED_FIELDS_FOR_PAPER_SIGNAL),
        "required_fields_for_paper_outcome": list(REQUIRED_FIELDS_FOR_PAPER_OUTCOME),
        "required_fields_for_ranking": list(REQUIRED_FIELDS_FOR_RANKING),
        "required_fields_for_promotion_gate": list(REQUIRED_FIELDS_FOR_PROMOTION_GATE),
        "live_ready_today": False,
    }


def normalize_betrayal_candidate_to_signal_origin_preview(
    candidate: Mapping[str, Any],
    *,
    schema_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    lane = _lane_parts(candidate)
    signal_origin_type = _signal_origin_type(candidate, lane)
    variant = f"betrayal_{signal_origin_type}"
    source_signal_id = _first_string(
        candidate,
        "source_signal_id",
        "original_signal_id",
        "signal_id",
        "emitted_signal_id",
    )
    emitted_signal_id = _first_string(candidate, "emitted_signal_id")
    signal_id = emitted_signal_id or _first_string(candidate, "signal_id") or source_signal_id
    source_identity = _first_string(candidate, "source_identity", "source", "source_type")
    event_identity = _first_string(candidate, "betrayal_event_identity", "event_identity")
    if not event_identity and source_signal_id:
        event_identity = f"betrayal|{source_signal_id}|{lane['lane_key'] or 'lane_missing'}"
    event_hash = _first_string(candidate, "betrayal_event_identity_hash", "event_identity_hash")
    if not event_hash and event_identity:
        event_hash = hashlib.sha256(event_identity.encode("utf-8")).hexdigest()[:24]
    outcome_windows = candidate.get("outcome_windows") or candidate.get("outcome_window_spec") or [1, 3, 5, 10, 21, 34, 55]
    preview = {
        "schema_version": SCHEMA_VERSION,
        "candidate": str(candidate.get("candidate") or candidate.get("betrayal_tier") or "BETRAYAL_WATCH"),
        "signal_origin_family": "betrayal",
        "signal_origin_type": signal_origin_type,
        "signal_origin_variant": variant,
        "symbol": lane["symbol"],
        "timeframe": lane["timeframe"],
        "direction": lane["direction"],
        "entry_mode": lane["entry_mode"],
        "lane_key": lane["lane_key"],
        "signal_id": signal_id,
        "source_signal_id": source_signal_id,
        "source_identity": source_identity,
        "source_signal_timestamp": _first_string(candidate, "source_signal_timestamp", "timestamp", "created_at"),
        "emitted_signal_id": emitted_signal_id,
        "betrayal_event_identity": event_identity,
        "betrayal_event_identity_hash": event_hash,
        "paper_outcome_tracking_identity": _first_string(
            candidate,
            "paper_outcome_tracking_identity",
            "outcome_tracking_identity",
        )
        or event_hash,
        "outcome_window_spec": list(outcome_windows) if isinstance(outcome_windows, Sequence) and not isinstance(outcome_windows, str) else outcome_windows,
        "known_outcome_count": int(candidate.get("known_outcome_count") or candidate.get("samples") or candidate.get("outcome_count") or 0),
        "paper_signal_count": int(candidate.get("paper_signal_count") or (1 if signal_id else 0)),
        "paper_only": bool(candidate.get("paper_only", True)),
        "live_ready_today": False,
        "live_authorized": False,
        "promotion_allowed": False,
    }
    return classify_betrayal_same_flow_readiness(preview, schema_context=schema_context or {})


def build_betrayal_same_flow_readiness_rows(
    *,
    betrayal_gate_ready_packet: Mapping[str, Any],
    capture_priority_rebalance: Mapping[str, Any],
    betrayal_upstream_contract: Mapping[str, Any],
    betrayal_source_propagation: Mapping[str, Any],
    betrayal_direction_completion: Mapping[str, Any],
    schema_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    candidates = []
    candidates.extend(betrayal_gate_ready_packet.get("betrayal_candidate_lane_registry") or [])
    candidates.extend((capture_priority_rebalance.get("betrayal_shadow_context") or {}).get("candidate_lanes") or [])
    candidates.extend(betrayal_source_propagation.get("entry_mode_propagated_rows_preview") or [])
    candidates.extend(betrayal_direction_completion.get("direction_completed_rows_preview") or [])
    candidates.extend(_shadow_rows_from_log_context(betrayal_gate_ready_packet, capture_priority_rebalance))
    rows = [
        normalize_betrayal_candidate_to_signal_origin_preview(candidate, schema_context=schema_context or {})
        for candidate in _merge_candidate_details(candidates)
    ]
    rows.sort(key=lambda row: (not row["paper_signal_ready"], str(row.get("lane_key") or ""), str(row.get("candidate") or "")))
    return _sanitize(rows)


def classify_betrayal_same_flow_readiness(
    row: Mapping[str, Any],
    *,
    schema_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    valid_modes = set((schema_context or {}).get("registry_valid_entry_modes") or [])
    blockers = []
    if row.get("signal_origin_family") != "betrayal":
        blockers.append("contract_adoption_partial")
    if not row.get("symbol"):
        blockers.append("missing_symbol")
    if not row.get("timeframe"):
        blockers.append("missing_timeframe")
    if not row.get("direction") or row.get("direction") == "unknown":
        blockers.append("missing_direction")
    entry_mode = str(row.get("entry_mode") or "")
    if not entry_mode or entry_mode in {"entry_unknown", "unknown", "None"} or (valid_modes and entry_mode not in valid_modes):
        blockers.append("missing_entry_mode")
    if not row.get("lane_key") or str(row.get("lane_key")).endswith("|entry_unknown"):
        blockers.append("missing_lane_key")
    if not row.get("signal_id") or not row.get("source_signal_id"):
        blockers.append("missing_signal_id")
    if not row.get("source_identity") or row.get("source_identity") == "unknown":
        blockers.append("missing_source_identity")
    if row.get("paper_only") is not True:
        blockers.append("contract_adoption_partial")
    paper_signal_ready = not any(
        blocker
        in {
            "contract_adoption_partial",
            "missing_symbol",
            "missing_timeframe",
            "missing_direction",
            "missing_entry_mode",
            "missing_lane_key",
            "missing_signal_id",
            "missing_source_identity",
        }
        for blocker in blockers
    )
    if not row.get("paper_outcome_tracking_identity") or not row.get("outcome_window_spec"):
        blockers.append("missing_outcome_identity")
    if int(row.get("known_outcome_count") or 0) <= 0:
        blockers.append("true_inverse_outcomes_missing")
    paper_outcome_ready = paper_signal_ready and "missing_outcome_identity" not in blockers
    ranking_ready = paper_outcome_ready and not row.get("lane_key") is None
    if not ranking_ready:
        blockers.append("promotion_gate_not_ready")
    blockers.extend(["risk_contract_missing", "operator_approval_missing", "global_live_gate_closed"])
    promotion_gate_ready = (
        ranking_ready
        and bool(blockers)
        and row.get("live_authorized") is False
        and row.get("promotion_allowed") is False
    )
    risk_contract_ready_later = promotion_gate_ready
    result = dict(row)
    result.update(
        {
            "paper_signal_ready": bool(paper_signal_ready),
            "paper_outcome_ready": bool(paper_outcome_ready),
            "ranking_ready": bool(ranking_ready),
            "promotion_gate_ready": bool(promotion_gate_ready),
            "risk_contract_ready_later": bool(risk_contract_ready_later),
            "live_ready_today": False,
            "live_authorized": False,
            "promotion_allowed": False,
            "blockers": _dedupe(blockers),
            "why": _row_why(paper_signal_ready, paper_outcome_ready, ranking_ready, blockers),
        }
    )
    return _sanitize(result)


def build_betrayal_integration_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "missing_entry_mode_rows": _count_blocker(rows, "missing_entry_mode"),
        "missing_lane_key_rows": _count_blocker(rows, "missing_lane_key"),
        "missing_source_identity_rows": _count_blocker(rows, "missing_source_identity"),
        "missing_direction_rows": _count_blocker(rows, "missing_direction"),
        "missing_signal_id_rows": _count_blocker(rows, "missing_signal_id"),
        "missing_outcome_identity_rows": _count_blocker(rows, "missing_outcome_identity"),
        "true_inverse_outcomes_missing_rows": _count_blocker(rows, "true_inverse_outcomes_missing"),
        "contract_adoption_partial": any("contract_adoption_partial" in (row.get("blockers") or []) for row in rows)
        or any(not row.get("paper_signal_ready") for row in rows),
        "hard_live_blockers": ["risk_contract_missing", "operator_approval_missing", "global_live_gate_closed"],
    }


def build_betrayal_promotion_path_requirements(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "can_enter_same_flow": any(row.get("paper_signal_ready") for row in rows),
        "promotion_path_known": True,
        "promotion_path_blocked": True,
        "requirements": [
            "registry-valid entry_mode",
            "lane_key",
            "paper signal identity",
            "paper outcome tracking",
            "ranking/performance evidence",
            "promotion gate",
            "risk contract later",
            "operator approval later",
            "global live gate later",
        ],
        "live_ready_today": False,
    }


def build_betrayal_integration_recommendations(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
    gate_packet: Mapping[str, Any],
    capture_priority: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "ADOPT_SIGNAL_ORIGIN_CONTRACT",
            "future_phase": "R235",
            "why": "Betrayal now has a paper-only signal-origin contract but source emitters must adopt it for future rows.",
        },
        {
            "priority": "HIGH",
            "recommended_action": "RUN_R228_IF_10_OF_10"
            if _threshold_met(gate_packet, capture_priority)
            else "WAIT_FOR_10_OF_10",
            "future_phase": "R228",
            "why": "The official protected BTCUSDT 8m short lane remains the only tiny-live readiness path.",
        },
    ]
    if gap_report.get("missing_outcome_identity_rows") or gap_report.get("true_inverse_outcomes_missing_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "WIRE_BETRAYAL_OUTCOME_TRACKING",
                "future_phase": "R236",
                "why": "Betrayal rows need paper outcome tracking identity before ranking can become meaningful.",
            }
        )
    if gap_report.get("missing_entry_mode_rows") or gap_report.get("missing_lane_key_rows"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "ADOPT_R230_ENTRY_MODE_CONTRACT",
                "future_phase": "R236",
                "why": "Rows with entry_unknown cannot enter paper signal flow.",
            }
        )
    return recommendations


def classify_betrayal_signal_origin_integration_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
    requirements: Mapping[str, Any],
) -> str:
    if not rows:
        return BETRAYAL_NOT_ENOUGH_DATA
    if gap_report.get("missing_entry_mode_rows") or gap_report.get("missing_lane_key_rows"):
        return BETRAYAL_SAME_FLOW_NEEDS_ENTRY_MODE
    if gap_report.get("missing_outcome_identity_rows") or gap_report.get("true_inverse_outcomes_missing_rows"):
        return BETRAYAL_SAME_FLOW_NEEDS_OUTCOME_TRACKING
    if requirements.get("promotion_path_blocked"):
        return BETRAYAL_PROMOTION_PATH_KNOWN_BUT_BLOCKED
    if all(row.get("paper_signal_ready") for row in rows):
        return BETRAYAL_SIGNAL_ORIGIN_CONTRACT_READY
    if any(row.get("paper_signal_ready") for row in rows):
        return BETRAYAL_SAME_FLOW_PARTIALLY_READY
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_betrayal_signal_origin_integration_contract_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_signal_origin_integration_contract_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "contract_id": str(record.get("contract_id") or f"r235_betrayal_signal_origin_integration_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_contract_requested": bool(record.get("record_contract_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "betrayal_signal_origin_contract": dict(record.get("betrayal_signal_origin_contract") or {}),
            "same_flow_readiness_rows": list(record.get("same_flow_readiness_rows") or []),
            "same_flow_summary": dict(record.get("same_flow_summary") or {}),
            "betrayal_integration_gap_report": dict(record.get("betrayal_integration_gap_report") or {}),
            "betrayal_promotion_path_requirements": dict(record.get("betrayal_promotion_path_requirements") or {}),
            "betrayal_integration_recommendations": list(record.get("betrayal_integration_recommendations") or []),
            "integration_status": record.get("integration_status"),
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


def load_betrayal_signal_origin_integration_contract_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_signal_origin_integration_contract_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_records(path, limit=0)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def summarize_betrayal_signal_origin_integration_contract_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "integration_status_counts": dict(
            sorted(Counter(str(record.get("integration_status") or "UNKNOWN") for record in records).items())
        ),
        "latest_contract_id": latest.get("contract_id") if latest else None,
        "latest_integration_status": latest.get("integration_status") if latest else None,
        "safety": dict(SAFETY),
    }


def betrayal_signal_origin_integration_contract_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_signal_origin_integration_contract_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _same_flow_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "rows_reviewed": len(rows),
        "paper_signal_ready_rows": sum(1 for row in rows if row.get("paper_signal_ready")),
        "paper_outcome_ready_rows": sum(1 for row in rows if row.get("paper_outcome_ready")),
        "ranking_ready_rows": sum(1 for row in rows if row.get("ranking_ready")),
        "promotion_gate_ready_rows": sum(1 for row in rows if row.get("promotion_gate_ready")),
        "risk_contract_ready_later_rows": sum(1 for row in rows if row.get("risk_contract_ready_later")),
        "live_ready_today_rows": 0,
        "blocked_rows": sum(1 for row in rows if row.get("blockers")),
    }


def _merge_candidate_details(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        lane = _lane_parts(candidate)
        key = "|".join(
            [
                str(lane.get("lane_key") or ""),
                str(candidate.get("candidate") or candidate.get("betrayal_tier") or ""),
                str(candidate.get("source_signal_id") or candidate.get("original_signal_id") or candidate.get("signal_id") or ""),
            ]
        )
        existing = merged.setdefault(key, {})
        for field, value in candidate.items():
            if value not in (None, "", [], {}) and existing.get(field) in (None, "", [], {}, "unknown", "entry_unknown"):
                existing[field] = value
    return list(merged.values())


def _shadow_rows_from_log_context(*contexts: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for context in contexts:
        for key in ("betrayal_shadow_outcomes", "betrayal_shadow_resolutions", "betrayal_true_paper_outcomes", "betrayal_paper_signals"):
            value = context.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                rows.extend(row for row in value if isinstance(row, Mapping))
    return rows


def _lane_parts(row: Mapping[str, Any]) -> dict[str, str | None]:
    lane_key = _string_or_none(row.get("lane_key") or row.get("lane_key_preview"))
    parts = lane_key.split("|") if lane_key else []
    if len(parts) >= 4:
        symbol = parts[0].upper()
        timeframe = parts[1]
        direction = _normal_direction(parts[2])
        entry_mode = parts[3]
        normalized = normalize_lane_key(symbol, timeframe, direction or "unknown", entry_mode)
        return {"lane_key": normalized, "symbol": symbol, "timeframe": timeframe, "direction": direction, "entry_mode": entry_mode}
    symbol = (_string_or_none(row.get("symbol")) or "BTCUSDT").upper()
    timeframe = _string_or_none(row.get("timeframe")) or _timeframe_from_candidate(row.get("candidate"))
    direction = _normal_direction(
        row.get("direction")
        or row.get("emitted_direction")
        or row.get("inverse_direction")
        or row.get("shadow_direction")
    )
    entry_mode = _string_or_none(row.get("entry_mode")) or "entry_unknown"
    built_lane = None
    if symbol and timeframe and direction and entry_mode:
        built_lane = normalize_lane_key(symbol, timeframe, direction, entry_mode)
    return {"lane_key": built_lane, "symbol": symbol, "timeframe": timeframe, "direction": direction, "entry_mode": entry_mode}


def _signal_origin_type(row: Mapping[str, Any], lane: Mapping[str, Any]) -> str:
    text = " ".join(str(row.get(key) or "") for key in ("candidate", "betrayal_tier", "source", "signal_origin_variant")).lower()
    direction = str(lane.get("direction") or "").lower()
    if "shadow" in text:
        return "shadow"
    if "aggregate" in text or "222m" in text or "88m" in text:
        return "aggregate"
    if direction == "inverse" or "inverse" in text:
        return "inverse"
    return "shadow"


def _normal_direction(value: Any) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"long", "short", "inverse"}:
        return lowered
    return None


def _first_string(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _string_or_none(row.get(key))
        if value and value not in {"unknown", "entry_unknown", "None"}:
            return value
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _timeframe_from_candidate(value: Any) -> str | None:
    text = _string_or_none(value) or ""
    for token in text.replace("|", " ").split():
        if token.endswith("m") or token.endswith("H") or token.endswith("D"):
            return token
    return None


def _count_blocker(rows: Sequence[Mapping[str, Any]], blocker: str) -> int:
    return sum(1 for row in rows if blocker in (row.get("blockers") or []))


def _row_why(paper_signal_ready: bool, paper_outcome_ready: bool, ranking_ready: bool, blockers: Sequence[str]) -> str:
    if ranking_ready:
        return "Betrayal row has enough schema to enter paper/ranking flow, but promotion and live stay blocked."
    if paper_outcome_ready:
        return "Betrayal row has paper signal and outcome tracking identity, but ranking still needs outcome evidence."
    if paper_signal_ready:
        return "Betrayal row can enter paper signal flow but needs paper outcome tracking/evidence."
    return "Betrayal row remains preview-only until blockers clear: " + ", ".join(_dedupe(blockers)[:4])


def _threshold_met(gate_packet: Mapping[str, Any], capture_priority: Mapping[str, Any]) -> bool:
    return bool(
        (gate_packet.get("official_tiny_live_status") or {}).get("threshold_met")
        or (capture_priority.get("official_protected_path_summary") or {}).get("threshold_met")
    )


def _recommended_next_operator_move(gate_packet: Mapping[str, Any], capture_priority: Mapping[str, Any]) -> str:
    if _threshold_met(gate_packet, capture_priority):
        return "RUN_R228_TINY_LIVE_10_OF_10_READY_PACKET"
    move = gate_packet.get("recommended_next_operator_move") or capture_priority.get("recommended_next_operator_move")
    if move in {"RUN_R228_TINY_LIVE_10_OF_10_READY_PACKET", "WAIT_FOR_10_OF_10"}:
        return str(move)
    return "KEEP_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(status: str, gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("missing_outcome_identity_rows") or gap_report.get("true_inverse_outcomes_missing_rows"):
        return "Build R236 betrayal paper outcome tracking bridge without config writes or live execution."
    if status == BETRAYAL_SAME_FLOW_NEEDS_ENTRY_MODE:
        return "Adopt R230 entry_mode and lane_key contract in future betrayal emitter rows."
    return "Keep R235 as contract-only and wait for paper outcomes before any promotion review."


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
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping):
                records.append(_sanitize(parsed))
    return records


def _dedupe(values: Sequence[Any]) -> list[Any]:
    seen = set()
    out = []
    for value in values:
        key = json.dumps(_sanitize(value), sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, set):
        return sorted(_sanitize(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    return value
