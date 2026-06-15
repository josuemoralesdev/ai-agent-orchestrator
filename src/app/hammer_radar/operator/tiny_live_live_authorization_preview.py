"""R231 tiny-live live authorization preview.

This module consumes the R228/R229/R230 tiny-live path and previews the future
live authorization requirements only. It never writes live authorization,
enables live execution, arms lanes, creates order payloads, calls Binance, or
mutates env/config/lane state.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import (
    LEDGER_FILENAME as R228_LEDGER_FILENAME,
    RISK_CONTRACT_CONFIG_PATH,
    TINY_LIVE_10_OF_10_READY_PACKET_READY,
    TINY_LIVE_10_OF_10_READY_PACKET_RECORDED,
    load_tiny_live_10_of_10_ready_packet_records,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    LEDGER_FILENAME as R230_LEDGER_FILENAME,
    load_existing_tiny_live_risk_contract_config,
    load_tiny_live_risk_contract_config_write_gate_records,
    validate_tiny_live_risk_contract_config_entry,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_preview import (
    LEDGER_FILENAME as R229_LEDGER_FILENAME,
    TINY_LIVE_RISK_CONTRACT_PREVIEW_READY,
    TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED,
    TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER,
    load_tiny_live_risk_contract_preview_records,
)

TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY = "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY"
TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_REJECTED = "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_REJECTED"
TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDED = "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDED"
TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED = "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED"
TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_ERROR = "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_ERROR"

TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY_FOR_FUTURE_GATE = (
    "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY_FOR_FUTURE_GATE"
)
TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_RISK_CONTRACT = (
    "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_RISK_CONTRACT"
)
TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_EVIDENCE = (
    "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_EVIDENCE"
)
TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_FISHERMAN = (
    "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_FISHERMAN"
)
TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_CONFIG = (
    "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_CONFIG"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW"
LEDGER_FILENAME = "tiny_live_live_authorization_preview.ndjson"
CONFIRM_TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE LIVE AUTHORIZATION PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
LANE_CONTROLS_PATH = Path("configs/hammer_radar/lane_controls.json")

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "lane_controls_written": False,
    "fisherman_config_written": False,
    "scheduler_config_written": False,
    "live_config_written": False,
    "live_authorization_written": False,
    "registry_config_written": False,
    "scoring_config_written": False,
    "matrix_config_written": False,
    "ledger_rewritten": False,
    "destructive_write": False,
    "historical_ledger_rewritten": False,
    "normalized_rows_appended": False,
    "paper_outcome_ledger_rewritten": False,
    "paper_outcomes_appended": False,
    "strategy_performance_appended": False,
    "strategy_promotion_status_appended": False,
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
    "live_execution_enabled": False,
    "lane_armed": False,
    "signal_origin_promoted": False,
    "lane_promoted": False,
    "official_tiny_live_lane_changed": False,
    "alternate_lane_promoted": False,
    "betrayal_live_authorized": False,
    "betrayal_promoted": False,
    "live_authorization_preview_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R229_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R230_LEDGER_FILENAME}",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_live_authorization_preview(
    *,
    log_dir: str | Path | None = None,
    record_authorization_preview: bool = False,
    confirm_tiny_live_live_authorization_preview: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    confirmation_valid = (
        confirm_tiny_live_live_authorization_preview
        == CONFIRM_TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDING_PHRASE
    )
    try:
        latest_r228 = load_latest_tiny_live_10_of_10_ready_packet(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r229 = load_latest_tiny_live_risk_contract_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r230 = load_latest_tiny_live_risk_contract_config_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        config = load_tiny_live_risk_contract_config(risk_path, official_lane_key=official_lane_key)
        lane_state = build_lane_control_state(lane_path, official_lane_key=official_lane_key)
        prerequisites = validate_live_authorization_prerequisites(
            latest_r228=latest_r228,
            latest_r229=latest_r229,
            latest_r230=latest_r230,
            risk_contract_config=config,
            lane_control_state=lane_state,
            official_lane_key=official_lane_key,
        )
        requirement_preview = build_live_authorization_requirement_preview(
            prerequisites=prerequisites,
            latest_r228=latest_r228,
            latest_r229=latest_r229,
            latest_r230=latest_r230,
            risk_contract_config=config,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        matrix = build_live_authorization_gate_matrix(prerequisites)
        operator_packet = build_operator_live_authorization_review_packet(matrix)
        recommendations = build_live_authorization_preview_recommendations(matrix)
        overall = classify_tiny_live_live_authorization_preview_status(
            prerequisites=prerequisites,
            gate_matrix=matrix,
        )
        status = (
            TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY
            if overall == TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY_FOR_FUTURE_GATE
            and record_authorization_preview
            else TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED
        )
        if record_authorization_preview and not confirmation_valid:
            status = TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_REJECTED
        elif record_authorization_preview and confirmation_valid and status == TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY:
            status = TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "authorization_preview_recorded": False,
            "authorization_preview_record_id": None,
            "record_authorization_preview_requested": bool(record_authorization_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(official_lane_key),
            "input_summary": prerequisites["input_summary"],
            "risk_contract_summary": prerequisites["risk_contract_summary"],
            "live_authorization_requirement_preview": requirement_preview,
            "live_authorization_gate_matrix": matrix,
            "operator_live_authorization_review_packet": operator_packet,
            "recommended_next_operator_move": recommendations["recommended_next_operator_move"],
            "recommended_next_engineering_move": recommendations["recommended_next_engineering_move"],
            "live_authorization_preview_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if status == TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDED:
            record = append_tiny_live_live_authorization_preview_record(payload, log_dir=resolved_log_dir)
            payload["authorization_preview_recorded"] = True
            payload["authorization_preview_record_id"] = record["authorization_preview_record_id"]
            payload["ledger_path"] = str(tiny_live_live_authorization_preview_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "authorization_preview_recorded": False,
                "authorization_preview_record_id": None,
                "record_authorization_preview_requested": bool(record_authorization_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(official_lane_key),
                "input_summary": _empty_input_summary(),
                "risk_contract_summary": _empty_risk_contract_summary(official_lane_key),
                "live_authorization_requirement_preview": build_live_authorization_requirement_preview(
                    prerequisites=_empty_prerequisites(official_lane_key, ["authorization_preview_error"]),
                    latest_r228={},
                    latest_r229={},
                    latest_r230={},
                    risk_contract_config={},
                    official_lane_key=official_lane_key,
                    now=generated_at,
                ),
                "live_authorization_gate_matrix": _empty_gate_matrix(["authorization_preview_error"]),
                "operator_live_authorization_review_packet": build_operator_live_authorization_review_packet(
                    _empty_gate_matrix(["authorization_preview_error"])
                ),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R231 preview error before any future live authorization write gate.",
                "live_authorization_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_risk_contract_config_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_risk_contract_config_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        post_write = record.get("post_write_verification") if isinstance(record.get("post_write_verification"), Mapping) else {}
        if str(target.get("official_lane_key") or "") == official_lane_key or post_write.get("matching_contract_found") is True:
            return _sanitize({**record, "r230_config_gate_found": True})
    return {}


def load_latest_tiny_live_risk_contract_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_risk_contract_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        preview = record.get("risk_contract_preview") if isinstance(record.get("risk_contract_preview"), Mapping) else {}
        if str(target.get("official_lane_key") or preview.get("official_lane_key") or "") == official_lane_key:
            return _sanitize({**record, "r229_preview_found": True})
    return {}


def load_latest_tiny_live_10_of_10_ready_packet(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_10_of_10_ready_packet_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if str(target.get("official_lane_key") or "") == official_lane_key:
            return _sanitize({**record, "r228_packet_found": True})
    return {}


def load_tiny_live_risk_contract_config(
    config_path: str | Path | None = None,
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    existing = load_existing_tiny_live_risk_contract_config(config_path)
    contract = _find_contract(existing.get("payload"), official_lane_key)
    validation = validate_tiny_live_risk_contract_config_entry(contract or {})
    return {
        "config_found": existing.get("config_found") is True,
        "config_path": existing.get("config_path"),
        "shape": existing.get("shape"),
        "matching_risk_contract_found": contract is not None,
        "matching_risk_contract": contract or {},
        "matching_risk_contract_valid": bool(contract is not None and validation["valid"]),
        "validation": validation,
    }


def validate_live_authorization_prerequisites(
    *,
    latest_r228: Mapping[str, Any],
    latest_r229: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    risk_contract_config: Mapping[str, Any],
    lane_control_state: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    r228_ready = _r228_ready(latest_r228, official_lane_key=official_lane_key)
    r229_ready = _r229_ready(latest_r229, official_lane_key=official_lane_key)
    contract = (
        risk_contract_config.get("matching_risk_contract")
        if isinstance(risk_contract_config.get("matching_risk_contract"), Mapping)
        else {}
    )
    contract_valid = risk_contract_config.get("matching_risk_contract_valid") is True
    live_authorized = contract.get("live_authorized") is True
    live_execution_enabled = contract.get("live_execution_enabled") is True
    approval_status = str(contract.get("approval_status") or "")
    lane_armed = lane_control_state.get("lane_armed") is True
    kill_switch_disabled = lane_control_state.get("kill_switch_disabled") is True
    input_summary = {
        "r228_packet_found": bool(latest_r228),
        "r228_evidence_ready": r228_ready["evidence_ready"],
        "r228_fisherman_ready": r228_ready["fisherman_ready"],
        "r229_preview_found": bool(latest_r229),
        "r229_preview_ready": r229_ready,
        "r230_config_gate_found": bool(latest_r230),
        "risk_contract_config_found": risk_contract_config.get("config_found") is True,
        "matching_risk_contract_found": risk_contract_config.get("matching_risk_contract_found") is True,
        "matching_risk_contract_valid": contract_valid,
    }
    risk_summary = _risk_contract_summary(contract, official_lane_key=official_lane_key)
    blocked_by: list[str] = []
    if not input_summary["r228_packet_found"]:
        blocked_by.append("r228_packet_missing")
    elif not input_summary["r228_evidence_ready"]:
        blocked_by.append("r228_evidence_not_ready")
    if input_summary["r228_packet_found"] and not input_summary["r228_fisherman_ready"]:
        blocked_by.append("r228_fisherman_not_ready")
    if not input_summary["r229_preview_found"]:
        blocked_by.append("r229_preview_missing")
    elif not input_summary["r229_preview_ready"]:
        blocked_by.append("r229_preview_not_ready")
    if not (input_summary["r230_config_gate_found"] or input_summary["matching_risk_contract_found"]):
        blocked_by.append("r230_config_gate_or_config_entry_missing")
    if not input_summary["risk_contract_config_found"]:
        blocked_by.append("risk_contract_config_missing")
    if not input_summary["matching_risk_contract_found"]:
        blocked_by.append("matching_risk_contract_missing")
    if input_summary["matching_risk_contract_found"] and not contract_valid:
        blocked_by.append("matching_risk_contract_invalid")
    if official_lane_key != OFFICIAL_LANE_KEY:
        blocked_by.append("official_lane_mismatch")
    if approval_status != "CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED":
        blocked_by.append("risk_contract_approval_status_invalid")
    if contract.get("approved") is True:
        blocked_by.append("risk_contract_already_approved")
    if live_authorized:
        blocked_by.append("live_authorized_not_false")
    if live_execution_enabled:
        blocked_by.append("live_execution_enabled_not_false")
    if contract.get("order_payload_forbidden_until_live_gate") is not True:
        blocked_by.append("order_payload_not_forbidden")
    if contract.get("binance_call_forbidden_until_live_gate") is not True:
        blocked_by.append("binance_call_not_forbidden")
    if lane_armed:
        blocked_by.append("lane_armed")
    if kill_switch_disabled:
        blocked_by.append("kill_switch_disabled")
    return {
        "input_summary": input_summary,
        "risk_contract_summary": risk_summary,
        "lane_control_state": dict(lane_control_state),
        "blocked_by": blocked_by,
    }


def build_live_authorization_requirement_preview(
    *,
    prerequisites: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    latest_r229: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    risk_contract_config: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    contract = (
        risk_contract_config.get("matching_risk_contract")
        if isinstance(risk_contract_config.get("matching_risk_contract"), Mapping)
        else {}
    )
    return {
        "authorization_preview_id": f"r231_live_authorization_preview_{symbol}_{timeframe}_{direction}_{entry_mode}_{uuid4().hex}",
        "preview_only": True,
        "generated_at": generated_at.isoformat(),
        "official_lane_key": official_lane_key,
        "evidence_packet_reference": latest_r228.get("packet_record_id") or latest_r228.get("generated_at"),
        "risk_contract_preview_reference": latest_r229.get("risk_preview_record_id") or latest_r229.get("generated_at"),
        "risk_contract_config_gate_reference": latest_r230.get("gate_record_id") or latest_r230.get("generated_at"),
        "risk_contract_reference": contract.get("contract_id"),
        "future_authorization_required": True,
        "future_confirmation_required": True,
        "future_operator_final_approval_required": True,
        "future_live_execution_enable_required": True,
        "future_lane_arm_required": True,
        "future_order_preflight_required": True,
        "future_binance_connectivity_check_required": True,
        "future_order_payload_still_forbidden_now": True,
        "future_suggested_confirmation_phrase": "I CONFIRM TINY LIVE AUTHORIZATION ONLY; NO ORDER; NO BINANCE CALL.",
        "notes": [
            "R231 creates no live authorization object.",
            "A later R232-style write gate may be considered only after this preview is reviewed.",
            "Order payload creation, live execution enablement, lane arming, and Binance/network calls remain forbidden now.",
            f"Remaining blockers: {', '.join(prerequisites.get('blocked_by') or ['future_live_authorization_gate_required'])}.",
        ],
    }


def build_live_authorization_gate_matrix(prerequisites: Mapping[str, Any]) -> dict[str, Any]:
    input_summary = prerequisites.get("input_summary") if isinstance(prerequisites.get("input_summary"), Mapping) else {}
    risk_summary = (
        prerequisites.get("risk_contract_summary")
        if isinstance(prerequisites.get("risk_contract_summary"), Mapping)
        else {}
    )
    lane_state = prerequisites.get("lane_control_state") if isinstance(prerequisites.get("lane_control_state"), Mapping) else {}
    blocked_by = list(prerequisites.get("blocked_by") or [])
    preview_ready = not blocked_by
    if preview_ready:
        blocked_by = ["future_live_authorization_write_gate_required", "live_execution_disabled", "lane_not_armed", "order_payload_forbidden"]
    return {
        "evidence_ready": input_summary.get("r228_evidence_ready") is True,
        "fisherman_ready": input_summary.get("r228_fisherman_ready") is True,
        "risk_contract_config_ready": input_summary.get("matching_risk_contract_valid") is True
        and risk_summary.get("approval_status") == "CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED",
        "risk_contract_approved": False,
        "live_authorization_preview_ready": preview_ready,
        "live_authorization_written": False,
        "live_execution_ready": False,
        "lane_armed": lane_state.get("lane_armed") is True,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": blocked_by,
    }


def build_operator_live_authorization_review_packet(live_authorization_gate_matrix: Mapping[str, Any]) -> dict[str, Any]:
    preview_ready = live_authorization_gate_matrix.get("live_authorization_preview_ready") is True
    if preview_ready:
        action = "REVIEW_R231_LIVE_AUTHORIZATION_PREVIEW"
    elif live_authorization_gate_matrix.get("evidence_ready") and live_authorization_gate_matrix.get("fisherman_ready"):
        action = "FIX_BLOCKER"
    else:
        action = "WAIT"
    return {
        "operator_should_review_live_authorization_preview": preview_ready,
        "operator_should_authorize_live_now": False,
        "operator_should_enable_live": False,
        "operator_should_arm_lane": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not enable live",
            "do not disable kill switch",
            "do not arm lane from this phase",
        ],
    }


def build_live_authorization_preview_recommendations(live_authorization_gate_matrix: Mapping[str, Any]) -> dict[str, str]:
    if live_authorization_gate_matrix.get("live_authorization_preview_ready"):
        return {
            "recommended_next_operator_move": "REVIEW_R231_LIVE_AUTHORIZATION_PREVIEW",
            "recommended_next_engineering_move": "Create R232 guarded live authorization write gate; still no live execution, Binance/network calls, orders, or lane arming.",
        }
    if not live_authorization_gate_matrix.get("evidence_ready"):
        return {
            "recommended_next_operator_move": "WAIT",
            "recommended_next_engineering_move": "Restore R228 evidence readiness before any live authorization preview can proceed.",
        }
    if not live_authorization_gate_matrix.get("fisherman_ready"):
        return {
            "recommended_next_operator_move": "WAIT",
            "recommended_next_engineering_move": "Restore R228 fisherman readiness before any live authorization preview can proceed.",
        }
    return {
        "recommended_next_operator_move": "FIX_BLOCKER",
        "recommended_next_engineering_move": "Fix risk-contract/config blockers before any future live authorization write gate.",
    }


def classify_tiny_live_live_authorization_preview_status(
    *,
    prerequisites: Mapping[str, Any],
    gate_matrix: Mapping[str, Any],
) -> str:
    input_summary = prerequisites.get("input_summary") if isinstance(prerequisites.get("input_summary"), Mapping) else {}
    blocked_by = set(gate_matrix.get("blocked_by") or [])
    if gate_matrix.get("live_authorization_preview_ready"):
        return TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY_FOR_FUTURE_GATE
    if not input_summary.get("r228_packet_found") or "r228_evidence_not_ready" in blocked_by:
        return TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_EVIDENCE
    if "r228_fisherman_not_ready" in blocked_by:
        return TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_FISHERMAN
    if any(str(item).endswith("_missing") or "config" in str(item) for item in blocked_by):
        return TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_CONFIG
    if any("risk_contract" in str(item) for item in blocked_by):
        return TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_BLOCKED_BY_RISK_CONTRACT
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_live_authorization_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_live_authorization_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "authorization_preview_record_id": record.get("authorization_preview_record_id")
            or f"r231_live_authorization_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "authorization_preview_recorded": record.get("status") == TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDED
            or record.get("authorization_preview_recorded") is True,
            "record_authorization_preview_requested": record.get("record_authorization_preview_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "risk_contract_summary": dict(record.get("risk_contract_summary") or {}),
            "live_authorization_requirement_preview": dict(
                record.get("live_authorization_requirement_preview") or {}
            ),
            "live_authorization_gate_matrix": dict(record.get("live_authorization_gate_matrix") or {}),
            "operator_live_authorization_review_packet": dict(
                record.get("operator_live_authorization_review_packet") or {}
            ),
            "live_authorization_preview_overall_status": record.get("live_authorization_preview_overall_status"),
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


def load_tiny_live_live_authorization_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_live_authorization_preview_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_live_authorization_preview_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_preview_recorded": latest.get("authorization_preview_recorded") is True,
        "latest_overall_status": latest.get("live_authorization_preview_overall_status"),
    }


def tiny_live_live_authorization_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_live_authorization_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def build_lane_control_state(
    lane_controls_path: str | Path | None = None,
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    state = {
        "lane_controls_found": False,
        "lane_controls_path": str(path),
        "matching_lane_found": False,
        "matching_lane_mode": None,
        "lane_armed": False,
        "kill_switch_disabled": False,
    }
    if not path.exists():
        return state
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**state, "lane_controls_found": True, "read_error": True, "kill_switch_disabled": True}
    state["lane_controls_found"] = True
    state["kill_switch_disabled"] = payload.get("default_mode") not in (None, "disabled")
    lanes = payload.get("lanes") if isinstance(payload, Mapping) else []
    for lane in lanes if isinstance(lanes, list) else []:
        if isinstance(lane, Mapping) and _contract_matches_lane(lane, official_lane_key):
            mode = str(lane.get("mode") or "")
            state["matching_lane_found"] = True
            state["matching_lane_mode"] = mode
            state["lane_armed"] = mode == "tiny_live"
            break
    return state


def _r228_ready(latest_r228: Mapping[str, Any], *, official_lane_key: str) -> dict[str, bool]:
    target = latest_r228.get("target_scope") if isinstance(latest_r228.get("target_scope"), Mapping) else {}
    gates = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    capture = (
        latest_r228.get("capture_threshold_recheck")
        if isinstance(latest_r228.get("capture_threshold_recheck"), Mapping)
        else {}
    )
    fisherman = (
        latest_r228.get("fisherman_health_recheck")
        if isinstance(latest_r228.get("fisherman_health_recheck"), Mapping)
        else {}
    )
    status_ok = latest_r228.get("status") in {
        TINY_LIVE_10_OF_10_READY_PACKET_READY,
        TINY_LIVE_10_OF_10_READY_PACKET_RECORDED,
    }
    lane_ok = str(target.get("official_lane_key") or capture.get("official_lane_key") or "") == official_lane_key
    evidence_ready = gates.get("evidence_ready") is True or capture.get("evidence_threshold_ready") is True
    fisherman_ready = gates.get("fisherman_ready") is True or fisherman.get("fisherman_ready") is True
    return {
        "status_ok": bool(status_ok),
        "lane_ok": bool(lane_ok),
        "evidence_ready": bool(status_ok and lane_ok and evidence_ready),
        "fisherman_ready": bool(status_ok and lane_ok and fisherman_ready),
    }


def _r229_ready(latest_r229: Mapping[str, Any], *, official_lane_key: str) -> bool:
    target = latest_r229.get("target_scope") if isinstance(latest_r229.get("target_scope"), Mapping) else {}
    preview = latest_r229.get("risk_contract_preview") if isinstance(latest_r229.get("risk_contract_preview"), Mapping) else {}
    matrix = latest_r229.get("risk_gate_matrix") if isinstance(latest_r229.get("risk_gate_matrix"), Mapping) else {}
    return (
        bool(latest_r229)
        and str(target.get("official_lane_key") or preview.get("official_lane_key") or "") == official_lane_key
        and latest_r229.get("status") in {TINY_LIVE_RISK_CONTRACT_PREVIEW_READY, TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED}
        and latest_r229.get("risk_preview_overall_status") == TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER
        and matrix.get("risk_contract_preview_ready") is True
        and preview.get("approval_status") == "NOT_APPROVED_PREVIEW_ONLY"
        and preview.get("order_payload_forbidden_now") is True
        and preview.get("binance_call_forbidden_now") is True
    )


def _risk_contract_summary(contract: Mapping[str, Any], *, official_lane_key: str) -> dict[str, Any]:
    return {
        "official_lane_key": official_lane_key,
        "approval_status": contract.get("approval_status"),
        "approved": contract.get("approved") is True,
        "live_authorized": contract.get("live_authorized") is True,
        "live_execution_enabled": contract.get("live_execution_enabled") is True,
        "max_account_risk_usdt": _number_or_none(contract.get("max_account_risk_usdt")),
        "max_loss_usdt": _number_or_none(contract.get("max_loss_usdt")),
        "max_notional_usdt": _number_or_none(contract.get("max_notional_usdt")),
        "leverage": _number_or_none(contract.get("leverage")),
        "kill_switch_required": contract.get("kill_switch_required") is True,
        "operator_final_approval_required": contract.get("operator_final_approval_required") is True,
        "order_payload_forbidden_until_live_gate": contract.get("order_payload_forbidden_until_live_gate") is True,
        "binance_call_forbidden_until_live_gate": contract.get("binance_call_forbidden_until_live_gate") is True,
    }


def _target_scope(lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "live_authorization_preview_only": True,
        "live_authorized": False,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r228_packet_found": False,
        "r228_evidence_ready": False,
        "r228_fisherman_ready": False,
        "r229_preview_found": False,
        "r229_preview_ready": False,
        "r230_config_gate_found": False,
        "risk_contract_config_found": False,
        "matching_risk_contract_found": False,
        "matching_risk_contract_valid": False,
    }


def _empty_risk_contract_summary(official_lane_key: str) -> dict[str, Any]:
    return _risk_contract_summary({}, official_lane_key=official_lane_key)


def _empty_prerequisites(official_lane_key: str, blocked_by: list[str] | None = None) -> dict[str, Any]:
    return {
        "input_summary": _empty_input_summary(),
        "risk_contract_summary": _empty_risk_contract_summary(official_lane_key),
        "lane_control_state": {"lane_armed": False, "kill_switch_disabled": False},
        "blocked_by": list(blocked_by or []),
    }


def _empty_gate_matrix(blockers: list[str] | None = None) -> dict[str, Any]:
    return {
        "evidence_ready": False,
        "fisherman_ready": False,
        "risk_contract_config_ready": False,
        "risk_contract_approved": False,
        "live_authorization_preview_ready": False,
        "live_authorization_written": False,
        "live_execution_ready": False,
        "lane_armed": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": list(blockers or []),
    }


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set any lane tiny_live",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _find_contract(payload: Any, official_lane_key: str) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    contracts_dict = payload.get("contracts")
    if isinstance(contracts_dict, Mapping) and isinstance(contracts_dict.get(official_lane_key), Mapping):
        return _sanitize(dict(contracts_dict[official_lane_key]))
    contracts = payload.get("risk_contracts")
    if isinstance(contracts, list):
        for contract in contracts:
            if isinstance(contract, Mapping) and _contract_matches_lane(contract, official_lane_key):
                return _sanitize(dict(contract))
    return None


def _contract_matches_lane(contract: Mapping[str, Any], official_lane_key: str) -> bool:
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    return (
        contract.get("official_lane_key") == official_lane_key
        or (
            str(contract.get("symbol") or "") == symbol
            and str(contract.get("timeframe") or "") == timeframe
            and str(contract.get("direction") or "") == direction
            and str(contract.get("entry_mode") or "") == entry_mode
        )
    )


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key or "").split("|")
    return (
        parts[0] if len(parts) > 0 else "",
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
        parts[3] if len(parts) > 3 else "",
    )


def _number_or_none(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
