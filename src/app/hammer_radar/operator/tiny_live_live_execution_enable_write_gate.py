"""R234 tiny-live live execution enable write gate.

This module can append a bounded local execution-enable ledger record only
when the exact R234 confirmation phrase is supplied. It never arms lanes,
creates order payloads, calls Binance/network, disables the kill switch, or
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
from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import RISK_CONTRACT_CONFIG_PATH
from src.app.hammer_radar.operator.tiny_live_live_authorization_preview import LANE_CONTROLS_PATH, build_lane_control_state
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import validate_live_authorization_object
from src.app.hammer_radar.operator.tiny_live_live_execution_enable_preview import (
    LEDGER_FILENAME as R233_LEDGER_FILENAME,
    TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY,
    TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY_FOR_FUTURE_GATE,
    TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDED,
    load_tiny_live_live_execution_enable_preview_records,
    load_latest_tiny_live_live_authorization_write_gate,
    load_latest_tiny_live_risk_contract_config_write_gate,
    load_latest_tiny_live_10_of_10_ready_packet,
    load_tiny_live_risk_contract_config,
    validate_live_execution_enable_prerequisites,
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import LEDGER_FILENAME as R232_LEDGER_FILENAME
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import LEDGER_FILENAME as R230_LEDGER_FILENAME
from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import LEDGER_FILENAME as R228_LEDGER_FILENAME

TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_READY = "TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_READY"
TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_REJECTED = "TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_REJECTED"
TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_WRITTEN = "TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_WRITTEN"
TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_BLOCKED = "TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_BLOCKED"
TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_ERROR = "TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_ERROR"

TINY_LIVE_EXECUTION_ENABLE_WRITE_READY_FOR_CONFIRMATION = "TINY_LIVE_EXECUTION_ENABLE_WRITE_READY_FOR_CONFIRMATION"
TINY_LIVE_EXECUTION_ENABLE_WRITTEN_LANE_ARM_REQUIRED_LATER = (
    "TINY_LIVE_EXECUTION_ENABLE_WRITTEN_LANE_ARM_REQUIRED_LATER"
)
TINY_LIVE_EXECUTION_ENABLE_WRITE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_EXECUTION_ENABLE_WRITE_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_R233_PREVIEW = (
    "TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_R233_PREVIEW"
)
TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_AUTHORIZATION = (
    "TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_AUTHORIZATION"
)
TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_RISK_CONTRACT = (
    "TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_RISK_CONTRACT"
)
TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_VALIDATION = (
    "TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE"
LEDGER_FILENAME = "tiny_live_live_execution_enable_write_gate.ndjson"
CONFIRM_TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_PHRASE = (
    "I CONFIRM TINY LIVE EXECUTION ENABLE WRITE ONLY; NO LANE ARM; NO ORDER; NO BINANCE CALL."
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
EXECUTION_ENABLE_VERSION = "tiny_live_execution_enable_v1"
CREATED_BY_PHASE = "R234_TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE"

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
    "live_execution_enable_written": False,
    "live_execution_enabled": False,
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
    "lane_armed": False,
    "signal_origin_promoted": False,
    "lane_promoted": False,
    "official_tiny_live_lane_changed": False,
    "alternate_lane_promoted": False,
    "betrayal_live_authorized": False,
    "betrayal_promoted": False,
    "execution_enable_write_gate_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R233_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R232_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R230_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_live_execution_enable_write_gate(
    *,
    log_dir: str | Path | None = None,
    write_execution_enable: bool = False,
    confirm_tiny_live_live_execution_enable_write: str | None = None,
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
        confirm_tiny_live_live_execution_enable_write == CONFIRM_TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_PHRASE
    )
    try:
        latest_r233 = load_latest_tiny_live_live_execution_enable_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r232 = load_latest_tiny_live_live_authorization_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r230 = load_latest_tiny_live_risk_contract_config_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r228 = load_latest_tiny_live_10_of_10_ready_packet(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        risk_config = load_tiny_live_risk_contract_config(risk_path, official_lane_key=official_lane_key)
        lane_state = build_lane_control_state(lane_path, official_lane_key=official_lane_key)
        prerequisites = validate_live_execution_enable_prerequisites(
            latest_r232=latest_r232,
            latest_r231={},
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_contract_config=risk_config,
            lane_control_state=lane_state,
            official_lane_key=official_lane_key,
        )
        input_summary = _build_input_summary(latest_r233=latest_r233, prerequisites=prerequisites)
        proposed = build_live_execution_enable_object(
            latest_r233=latest_r233,
            latest_r232=latest_r232,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_contract_config=risk_config,
            input_summary=input_summary,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        validation = validate_live_execution_enable_object(proposed)
        r233_ready = _r233_preview_ready(latest_r233, official_lane_key=official_lane_key)
        auth_ready = input_summary["r232_authorization_valid"] and input_summary["live_authorized"]
        risk_ready = input_summary["risk_contract_valid"] and input_summary["risk_contract_config_ready"]
        blocked_by = _blocked_by(
            r233_ready=r233_ready,
            auth_ready=auth_ready,
            risk_ready=risk_ready,
            validation=validation,
            prerequisites=prerequisites,
        )
        preview = build_live_execution_enable_write_preview(
            proposed_execution_enable=proposed,
            execution_enable_valid=validation["valid"],
            r233_preview_ready=r233_ready,
            blocked_by=blocked_by,
            official_lane_key=official_lane_key,
        )
        can_write = write_execution_enable and confirmation_valid and not blocked_by

        if write_execution_enable and not confirmation_valid:
            written = False
            status = TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_REJECTED
            overall = TINY_LIVE_EXECUTION_ENABLE_WRITE_REJECTED_BAD_CONFIRMATION
        elif can_write:
            write_live_execution_enable_if_confirmed(
                execution_enable=proposed,
                confirm_tiny_live_live_execution_enable_write=confirm_tiny_live_live_execution_enable_write,
                log_dir=resolved_log_dir,
            )
            written = True
            status = TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_WRITTEN
            overall = TINY_LIVE_EXECUTION_ENABLE_WRITTEN_LANE_ARM_REQUIRED_LATER
        elif not r233_ready:
            written = False
            status = TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_BLOCKED
            overall = TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_R233_PREVIEW
        elif not auth_ready:
            written = False
            status = TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_BLOCKED
            overall = TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_AUTHORIZATION
        elif not risk_ready:
            written = False
            status = TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_BLOCKED
            overall = TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_RISK_CONTRACT
        elif not validation["valid"]:
            written = False
            status = TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_BLOCKED
            overall = TINY_LIVE_EXECUTION_ENABLE_WRITE_BLOCKED_BY_VALIDATION
        else:
            written = False
            status = TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_READY
            overall = TINY_LIVE_EXECUTION_ENABLE_WRITE_READY_FOR_CONFIRMATION

        post_write = build_post_write_execution_enable_verification(
            execution_enable=proposed,
            execution_enable_written=written,
            log_dir=resolved_log_dir,
        )
        matrix = build_live_execution_enable_write_gate_matrix(
            r233_preview_ready=r233_ready,
            risk_contract_config_ready=risk_ready,
            authorization_valid=auth_ready,
            execution_enable_valid=validation["valid"],
            execution_enable_write_confirmed=write_execution_enable and confirmation_valid,
            live_execution_enable_written=written,
            live_authorized=input_summary["live_authorized"],
            live_execution_enabled=written,
            blocked_by=blocked_by,
        )
        operator_packet = build_operator_execution_enable_write_review_packet(matrix, write_requested=write_execution_enable)
        safety = dict(SAFETY)
        if written:
            safety["live_execution_enable_written"] = True
            safety["live_execution_enabled"] = True
            safety["global_live_flags_changed"] = True
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "execution_enable_written": written,
            "write_execution_enable_requested": bool(write_execution_enable),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(official_lane_key, live_authorized=input_summary["live_authorized"]),
            "input_summary": input_summary,
            "execution_enable_write_preview": preview,
            "execution_enable_validation": validation,
            "post_write_verification": post_write,
            "live_execution_enable_write_gate_matrix": matrix,
            "operator_execution_enable_write_review_packet": operator_packet,
            "recommended_next_operator_move": _recommended_next_operator_move(matrix, write_requested=write_execution_enable),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
            "execution_enable_write_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_live_execution_enable_write_gate_matrix(
            r233_preview_ready=False,
            risk_contract_config_ready=False,
            authorization_valid=False,
            execution_enable_valid=False,
            execution_enable_write_confirmed=False,
            live_execution_enable_written=False,
            live_authorized=False,
            live_execution_enabled=False,
            blocked_by=["execution_enable_write_gate_error"],
        )
        return _sanitize(
            {
                "status": TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "execution_enable_written": False,
                "write_execution_enable_requested": bool(write_execution_enable),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(official_lane_key, live_authorized=False),
                "input_summary": _empty_input_summary(),
                "execution_enable_write_preview": _empty_execution_enable_write_preview(official_lane_key),
                "execution_enable_validation": {"valid": False, "errors": ["execution_enable_write_gate_error"], "warnings": []},
                "post_write_verification": _empty_post_write_verification(),
                "live_execution_enable_write_gate_matrix": matrix,
                "operator_execution_enable_write_review_packet": build_operator_execution_enable_write_review_packet(
                    matrix,
                    write_requested=write_execution_enable,
                ),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R234 execution-enable write-gate error before any lane-arm preview.",
                "execution_enable_write_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_live_execution_enable_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_live_execution_enable_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        matrix = record.get("live_execution_enable_gate_matrix") if isinstance(record.get("live_execution_enable_gate_matrix"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or "") == official_lane_key
            and record.get("status") in {
                TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY,
                TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDED,
            }
            and record.get("live_execution_enable_preview_overall_status")
            == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY_FOR_FUTURE_GATE
            and matrix.get("live_execution_enable_preview_ready") is True
            and matrix.get("live_execution_enabled") is False
            and matrix.get("lane_armed") is False
        ):
            return _sanitize({**record, "r233_preview_found": True})
    return {}


def build_live_execution_enable_object(
    *,
    latest_r233: Mapping[str, Any],
    latest_r232: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_contract_config: Mapping[str, Any],
    input_summary: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    contract = risk_contract_config.get("matching_risk_contract") if isinstance(risk_contract_config.get("matching_risk_contract"), Mapping) else {}
    auth = latest_r232.get("authorization") if isinstance(latest_r232.get("authorization"), Mapping) else {}
    requirement_preview = (
        latest_r233.get("live_execution_enable_requirement_preview")
        if isinstance(latest_r233.get("live_execution_enable_requirement_preview"), Mapping)
        else {}
    )
    return {
        "execution_enable_id": "r234_execution_enable_BTCUSDT_8m_short_ladder_close_50_618",
        "execution_enable_version": EXECUTION_ENABLE_VERSION,
        "created_by_phase": CREATED_BY_PHASE,
        "created_at": generated_at.isoformat(),
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "source_execution_enable_preview_id": latest_r233.get("execution_enable_preview_record_id")
        or requirement_preview.get("execution_enable_preview_id"),
        "source_authorization_id": auth.get("authorization_id") or latest_r232.get("gate_record_id"),
        "source_risk_contract_id": contract.get("contract_id") or latest_r230.get("gate_record_id"),
        "risk_contract_config_ready": input_summary.get("risk_contract_valid") is True,
        "evidence_ready": input_summary.get("r228_evidence_ready") is True,
        "fisherman_ready": input_summary.get("fisherman_ready") is True,
        "live_authorized": input_summary.get("live_authorized") is True,
        "execution_enable_scope": "tiny_live_single_lane",
        "execution_enable_status": "LIVE_EXECUTION_ENABLED_NOT_ARMED_NOT_EXECUTABLE",
        "live_execution_enabled": True,
        "lane_armed": False,
        "order_payload_allowed": False,
        "binance_call_allowed": False,
        "kill_switch_required": True,
        "operator_final_approval_required": True,
        "lane_arm_required_later": True,
        "order_preflight_required_later": True,
        "binance_connectivity_check_required_later": True,
        "notes": [
            "R234 writes live execution enable artifact only; it does not arm the lane.",
            "Lane arming, order payload creation, and Binance/network calls remain forbidden.",
            "A later phase must separately gate lane arming.",
        ],
    }


def validate_live_execution_enable_object(execution_enable: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    expected = {
        "official_lane_key": OFFICIAL_LANE_KEY,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "risk_contract_config_ready": True,
        "evidence_ready": True,
        "fisherman_ready": True,
        "live_authorized": True,
        "live_execution_enabled": True,
        "lane_armed": False,
        "order_payload_allowed": False,
        "binance_call_allowed": False,
        "kill_switch_required": True,
        "operator_final_approval_required": True,
        "lane_arm_required_later": True,
        "order_preflight_required_later": True,
        "binance_connectivity_check_required_later": True,
    }
    for key, value in expected.items():
        if execution_enable.get(key) is not value and execution_enable.get(key) != value:
            errors.append(f"{key}_invalid")
    if execution_enable.get("execution_enable_status") != "LIVE_EXECUTION_ENABLED_NOT_ARMED_NOT_EXECUTABLE":
        errors.append("execution_enable_status_invalid")
    if not execution_enable.get("source_execution_enable_preview_id"):
        errors.append("source_execution_enable_preview_id_missing")
    if execution_enable.get("source_authorization_id") != "r232_authorization_BTCUSDT_8m_short_ladder_close_50_618":
        errors.append("source_authorization_id_invalid")
    if execution_enable.get("source_risk_contract_id") != "r230_contract_BTCUSDT_8m_short_ladder_close_50_618":
        errors.append("source_risk_contract_id_invalid")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def build_live_execution_enable_write_preview(
    *,
    proposed_execution_enable: Mapping[str, Any],
    execution_enable_valid: bool,
    r233_preview_ready: bool,
    blocked_by: Sequence[str] | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return {
        "would_write": bool(execution_enable_valid and r233_preview_ready and not blocked_by),
        "write_requires_confirmation": True,
        "target_execution_enable_key": official_lane_key,
        "bounded_mutation_only": True,
        "execution_enable_artifact": "ledger_only",
        "proposed_execution_enable": _sanitize(dict(proposed_execution_enable)),
    }


def write_live_execution_enable_if_confirmed(
    *,
    execution_enable: Mapping[str, Any],
    confirm_tiny_live_live_execution_enable_write: str | None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_live_execution_enable_write != CONFIRM_TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_PHRASE:
        return {"written": False, "reason": "bad_confirmation"}
    validation = validate_live_execution_enable_object(execution_enable)
    if not validation["valid"]:
        return {"written": False, "reason": "validation_failed", "validation": validation}
    record = append_tiny_live_live_execution_enable_write_gate_record(
        {
            "status": TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_WRITTEN,
            "generated_at": execution_enable.get("created_at"),
            "execution_enable_written": True,
            "write_execution_enable_requested": True,
            "confirmation_valid": True,
            "target_scope": _target_scope(str(execution_enable.get("official_lane_key") or OFFICIAL_LANE_KEY), live_authorized=True),
            "execution_enable": dict(execution_enable),
            "execution_enable_validation": validation,
            "safety": {**SAFETY, "live_execution_enable_written": True, "live_execution_enabled": True, "global_live_flags_changed": True},
        },
        log_dir=log_dir,
    )
    return {"written": True, "record": record}


def build_post_write_execution_enable_verification(
    *,
    execution_enable: Mapping[str, Any],
    execution_enable_written: bool,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_tiny_live_live_execution_enable_write_gate_records(log_dir=log_dir, limit=50) if execution_enable_written else []
    matching = _matching_execution_enable_record(records, execution_enable)
    artifact = matching.get("execution_enable") if isinstance(matching.get("execution_enable"), Mapping) else {}
    validation = validate_live_execution_enable_object(artifact)
    return {
        "execution_enable_written": bool(execution_enable_written),
        "matching_execution_enable_found": bool(matching),
        "matching_execution_enable_valid": bool(matching and validation["valid"]),
        "live_authorized": bool(matching and artifact.get("live_authorized") is True),
        "live_execution_enabled": bool(matching and artifact.get("live_execution_enabled") is True),
        "lane_armed": False,
        "order_payload_created": False,
        "order_payload_allowed": False,
        "binance_call_allowed": False,
    }


def build_live_execution_enable_write_gate_matrix(
    *,
    r233_preview_ready: bool,
    risk_contract_config_ready: bool,
    authorization_valid: bool,
    execution_enable_valid: bool,
    execution_enable_write_confirmed: bool,
    live_execution_enable_written: bool,
    live_authorized: bool,
    live_execution_enabled: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if not r233_preview_ready:
        blockers.append("r233_preview_not_ready")
    if not risk_contract_config_ready:
        blockers.append("risk_contract_config_not_ready")
    if not authorization_valid:
        blockers.append("authorization_invalid")
    if not execution_enable_valid:
        blockers.append("execution_enable_invalid")
    if not execution_enable_write_confirmed:
        blockers.append("exact_execution_enable_write_confirmation_required")
    if live_execution_enable_written:
        blockers = ["lane_not_armed", "order_payload_forbidden", "order_preflight_required_later"]
    return {
        "r233_preview_ready": bool(r233_preview_ready),
        "risk_contract_config_ready": bool(risk_contract_config_ready),
        "authorization_valid": bool(authorization_valid),
        "execution_enable_valid": bool(execution_enable_valid),
        "execution_enable_write_confirmed": bool(execution_enable_write_confirmed),
        "live_execution_enable_written": bool(live_execution_enable_written),
        "live_authorized": bool(live_authorized),
        "live_execution_enabled": bool(live_execution_enabled),
        "lane_armed": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_execution_enable_write_review_packet(
    live_execution_enable_write_gate_matrix: Mapping[str, Any],
    *,
    write_requested: bool = False,
) -> dict[str, Any]:
    written = live_execution_enable_write_gate_matrix.get("live_execution_enable_written") is True
    ready = (
        live_execution_enable_write_gate_matrix.get("r233_preview_ready") is True
        and live_execution_enable_write_gate_matrix.get("risk_contract_config_ready") is True
        and live_execution_enable_write_gate_matrix.get("authorization_valid") is True
        and live_execution_enable_write_gate_matrix.get("execution_enable_valid") is True
        and not written
    )
    if written:
        action = "REVIEW_R234_RESULT"
    elif ready:
        action = "CONFIRM_R234_EXECUTION_ENABLE_WRITE"
    else:
        action = "WAIT"
    return {
        "operator_should_review_execution_enable_write": bool(ready or written or write_requested),
        "operator_confirmation_required": True,
        "operator_should_arm_lane": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not disable kill switch",
            "do not arm lane from this phase",
            "do not call Binance from this phase",
        ],
    }


def classify_tiny_live_live_execution_enable_write_status(payload: Mapping[str, Any]) -> str:
    return str(payload.get("execution_enable_write_overall_status") or UNKNOWN_NEEDS_MANUAL_REVIEW)


def append_tiny_live_live_execution_enable_write_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_live_execution_enable_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "gate_record_id": record.get("gate_record_id") or f"r234_execution_enable_write_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "execution_enable_written": record.get("execution_enable_written") is True,
            "write_execution_enable_requested": record.get("write_execution_enable_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "execution_enable": dict(record.get("execution_enable") or {}),
            "execution_enable_validation": dict(record.get("execution_enable_validation") or {}),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_live_execution_enable_write_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_live_execution_enable_write_gate_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_tiny_live_live_execution_enable_write_gate_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_execution_enable_written": latest.get("execution_enable_written") is True,
        "latest_execution_enable_id": (latest.get("execution_enable") or {}).get("execution_enable_id")
        if isinstance(latest.get("execution_enable"), Mapping)
        else None,
    }


def tiny_live_live_execution_enable_write_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_live_execution_enable_write_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(*, latest_r233: Mapping[str, Any], prerequisites: Mapping[str, Any]) -> dict[str, Any]:
    base = prerequisites.get("input_summary") if isinstance(prerequisites.get("input_summary"), Mapping) else {}
    return {
        "r233_preview_found": bool(latest_r233),
        "r233_preview_ready": _r233_preview_ready(latest_r233),
        "r232_authorization_found": base.get("r232_authorization_found") is True,
        "r232_authorization_valid": base.get("r232_authorization_valid") is True,
        "r230_risk_contract_config_found": base.get("r230_risk_contract_config_found") is True,
        "risk_contract_valid": base.get("risk_contract_valid") is True,
        "risk_contract_config_ready": base.get("r230_risk_contract_config_found") is True and base.get("risk_contract_valid") is True,
        "r228_evidence_ready": base.get("r228_evidence_ready") is True,
        "fisherman_ready": base.get("r228_fisherman_ready") is True,
        "live_authorized": base.get("live_authorized") is True,
    }


def _r233_preview_ready(
    latest_r233: Mapping[str, Any],
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> bool:
    target = latest_r233.get("target_scope") if isinstance(latest_r233.get("target_scope"), Mapping) else {}
    matrix = latest_r233.get("live_execution_enable_gate_matrix") if isinstance(latest_r233.get("live_execution_enable_gate_matrix"), Mapping) else {}
    return (
        bool(latest_r233)
        and str(target.get("official_lane_key") or "") == official_lane_key
        and latest_r233.get("status") in {
            TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY,
            TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDED,
        }
        and latest_r233.get("live_execution_enable_preview_overall_status")
        == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY_FOR_FUTURE_GATE
        and matrix.get("live_execution_enable_preview_ready") is True
        and matrix.get("live_execution_enabled") is False
        and matrix.get("lane_armed") is False
        and matrix.get("order_ready") is False
        and matrix.get("live_ready_today") is False
    )


def _blocked_by(
    *,
    r233_ready: bool,
    auth_ready: bool,
    risk_ready: bool,
    validation: Mapping[str, Any],
    prerequisites: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not r233_ready:
        blockers.append("r233_preview_not_ready")
    if not auth_ready:
        blockers.append("authorization_not_ready")
    if not risk_ready:
        blockers.append("risk_contract_config_not_ready")
    if validation.get("valid") is not True:
        blockers.extend(str(error) for error in validation.get("errors") or ["execution_enable_invalid"])
    for blocker in prerequisites.get("blocked_by") or []:
        blockers.append(str(blocker))
    return _dedupe(blockers)


def _matching_execution_enable_record(
    records: Sequence[Mapping[str, Any]],
    execution_enable: Mapping[str, Any],
) -> dict[str, Any]:
    expected_id = execution_enable.get("execution_enable_id")
    for record in records:
        artifact = record.get("execution_enable") if isinstance(record.get("execution_enable"), Mapping) else {}
        if artifact.get("execution_enable_id") == expected_id and record.get("execution_enable_written") is True:
            return _sanitize(dict(record))
    return {}


def _target_scope(lane_key: str, *, live_authorized: bool) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "execution_enable_write_gate_only": True,
        "live_authorized": bool(live_authorized),
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_payload_allowed": False,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r233_preview_found": False,
        "r233_preview_ready": False,
        "r232_authorization_found": False,
        "r232_authorization_valid": False,
        "r230_risk_contract_config_found": False,
        "risk_contract_valid": False,
        "risk_contract_config_ready": False,
        "r228_evidence_ready": False,
        "fisherman_ready": False,
        "live_authorized": False,
    }


def _empty_execution_enable_write_preview(official_lane_key: str) -> dict[str, Any]:
    return {
        "would_write": False,
        "write_requires_confirmation": True,
        "target_execution_enable_key": official_lane_key,
        "bounded_mutation_only": True,
        "execution_enable_artifact": "ledger_only",
        "proposed_execution_enable": {},
    }


def _empty_post_write_verification() -> dict[str, Any]:
    return {
        "execution_enable_written": False,
        "matching_execution_enable_found": False,
        "matching_execution_enable_valid": False,
        "live_authorized": False,
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_payload_created": False,
        "order_payload_allowed": False,
        "binance_call_allowed": False,
    }


def _recommended_next_operator_move(matrix: Mapping[str, Any], *, write_requested: bool) -> str:
    if matrix.get("live_execution_enable_written"):
        return "REVIEW_R234_EXECUTION_ENABLE_WRITE_RESULT"
    if (
        matrix.get("r233_preview_ready")
        and matrix.get("risk_contract_config_ready")
        and matrix.get("authorization_valid")
        and matrix.get("execution_enable_valid")
        and not write_requested
    ):
        return "CONFIRM_R234_EXECUTION_ENABLE_WRITE"
    return "WAIT"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("live_execution_enable_written"):
        return "Create R235 Tiny-Live Lane Arm Preview; no Binance/network calls, orders, order payloads, or kill-switch disable."
    if (
        matrix.get("r233_preview_ready")
        and matrix.get("risk_contract_config_ready")
        and matrix.get("authorization_valid")
        and matrix.get("execution_enable_valid")
    ):
        return "Await exact R234 confirmation phrase before writing only the execution-enable ledger artifact."
    return "Fix R234 blockers before any execution-enable write."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming outside this bounded artifact",
        "kill switch disable",
        "set any lane tiny_live",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key or "").split("|")
    return (
        parts[0] if len(parts) > 0 else "",
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
        parts[3] if len(parts) > 3 else "",
    )


def _dedupe(items: Sequence[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
