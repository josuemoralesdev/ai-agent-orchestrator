"""R235 tiny-live lane arm preview.

This module consumes the R228/R230/R232/R233/R234 tiny-live artifacts and
previews future lane-arm requirements only. It never arms lanes, creates order
payloads, calls Binance/network, disables the kill switch, or mutates
env/config/lane state.
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
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_preview import (
    LANE_CONTROLS_PATH,
    build_lane_control_state,
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    LEDGER_FILENAME as R232_LEDGER_FILENAME,
    load_tiny_live_live_authorization_write_gate_records,
    validate_live_authorization_object,
)
from src.app.hammer_radar.operator.tiny_live_live_execution_enable_preview import (
    LEDGER_FILENAME as R233_LEDGER_FILENAME,
    load_latest_tiny_live_10_of_10_ready_packet,
    load_latest_tiny_live_risk_contract_config_write_gate,
    load_tiny_live_risk_contract_config,
    validate_live_execution_enable_prerequisites,
)
from src.app.hammer_radar.operator.tiny_live_live_execution_enable_write_gate import (
    LEDGER_FILENAME as R234_LEDGER_FILENAME,
    load_tiny_live_live_execution_enable_write_gate_records,
    validate_live_execution_enable_object,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    LEDGER_FILENAME as R230_LEDGER_FILENAME,
    load_tiny_live_risk_contract_config_write_gate_records,
)

TINY_LIVE_LANE_ARM_PREVIEW_READY = "TINY_LIVE_LANE_ARM_PREVIEW_READY"
TINY_LIVE_LANE_ARM_PREVIEW_REJECTED = "TINY_LIVE_LANE_ARM_PREVIEW_REJECTED"
TINY_LIVE_LANE_ARM_PREVIEW_RECORDED = "TINY_LIVE_LANE_ARM_PREVIEW_RECORDED"
TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED = "TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED"
TINY_LIVE_LANE_ARM_PREVIEW_ERROR = "TINY_LIVE_LANE_ARM_PREVIEW_ERROR"

TINY_LIVE_LANE_ARM_PREVIEW_READY_FOR_FUTURE_GATE = "TINY_LIVE_LANE_ARM_PREVIEW_READY_FOR_FUTURE_GATE"
TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE = (
    "TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE"
)
TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_AUTHORIZATION = "TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_AUTHORIZATION"
TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_RISK_CONTRACT = "TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_RISK_CONTRACT"
TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_EVIDENCE = "TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_EVIDENCE"
TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_FISHERMAN = "TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_FISHERMAN"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_LANE_ARM_PREVIEW"
LEDGER_FILENAME = "tiny_live_lane_arm_preview.ndjson"
CONFIRM_TINY_LIVE_LANE_ARM_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE LANE ARM PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE

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
    "lane_arm_written": False,
    "lane_armed": False,
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
    "signal_origin_promoted": False,
    "lane_promoted": False,
    "official_tiny_live_lane_changed": False,
    "alternate_lane_promoted": False,
    "betrayal_live_authorized": False,
    "betrayal_promoted": False,
    "lane_arm_preview_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R234_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R233_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R232_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R230_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_lane_arm_preview(
    *,
    log_dir: str | Path | None = None,
    record_lane_arm_preview: bool = False,
    confirm_tiny_live_lane_arm_preview: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    confirmation_valid = confirm_tiny_live_lane_arm_preview == CONFIRM_TINY_LIVE_LANE_ARM_PREVIEW_RECORDING_PHRASE
    try:
        latest_r234 = load_latest_tiny_live_live_execution_enable_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r233 = load_latest_tiny_live_live_execution_enable_preview_record(
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
        lane_summary = load_lane_controls_readonly(lane_path, official_lane_key=official_lane_key)
        prerequisites = validate_lane_arm_prerequisites(
            latest_r234=latest_r234,
            latest_r233=latest_r233,
            latest_r232=latest_r232,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_contract_config=risk_config,
            lane_controls_readonly_summary=lane_summary,
            official_lane_key=official_lane_key,
        )
        requirement_preview = build_lane_arm_requirement_preview(
            prerequisites=prerequisites,
            latest_r234=latest_r234,
            latest_r233=latest_r233,
            latest_r232=latest_r232,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_contract_config=risk_config,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        matrix = build_lane_arm_gate_matrix(prerequisites)
        operator_packet = build_operator_lane_arm_review_packet(matrix)
        recommendations = build_lane_arm_preview_recommendations(matrix)
        overall = classify_tiny_live_lane_arm_preview_status(prerequisites=prerequisites, gate_matrix=matrix)
        status = (
            TINY_LIVE_LANE_ARM_PREVIEW_READY
            if overall == TINY_LIVE_LANE_ARM_PREVIEW_READY_FOR_FUTURE_GATE
            else TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED
        )
        if record_lane_arm_preview and not confirmation_valid:
            status = TINY_LIVE_LANE_ARM_PREVIEW_REJECTED
        elif record_lane_arm_preview and confirmation_valid and status == TINY_LIVE_LANE_ARM_PREVIEW_READY:
            status = TINY_LIVE_LANE_ARM_PREVIEW_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "lane_arm_preview_recorded": False,
            "lane_arm_preview_record_id": None,
            "record_lane_arm_preview_requested": bool(record_lane_arm_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(
                official_lane_key,
                live_authorized=prerequisites["input_summary"].get("live_authorized") is True,
                live_execution_enabled=prerequisites["input_summary"].get("live_execution_enabled") is True,
            ),
            "input_summary": prerequisites["input_summary"],
            "authorization_summary": prerequisites["authorization_summary"],
            "execution_enable_summary": prerequisites["execution_enable_summary"],
            "lane_controls_readonly_summary": lane_summary,
            "lane_arm_requirement_preview": requirement_preview,
            "lane_arm_gate_matrix": matrix,
            "operator_lane_arm_review_packet": operator_packet,
            "recommended_next_operator_move": recommendations["recommended_next_operator_move"],
            "recommended_next_engineering_move": recommendations["recommended_next_engineering_move"],
            "lane_arm_preview_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if status == TINY_LIVE_LANE_ARM_PREVIEW_RECORDED:
            record = append_tiny_live_lane_arm_preview_record(payload, log_dir=resolved_log_dir)
            payload["lane_arm_preview_recorded"] = True
            payload["lane_arm_preview_record_id"] = record["lane_arm_preview_record_id"]
            payload["ledger_path"] = str(tiny_live_lane_arm_preview_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = _empty_gate_matrix(["lane_arm_preview_error"])
        return _sanitize(
            {
                "status": TINY_LIVE_LANE_ARM_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "lane_arm_preview_recorded": False,
                "lane_arm_preview_record_id": None,
                "record_lane_arm_preview_requested": bool(record_lane_arm_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(official_lane_key, live_authorized=False, live_execution_enabled=False),
                "input_summary": _empty_input_summary(),
                "authorization_summary": _authorization_summary({}),
                "execution_enable_summary": _execution_enable_summary({}),
                "lane_controls_readonly_summary": _empty_lane_controls_readonly_summary(lane_path),
                "lane_arm_requirement_preview": build_lane_arm_requirement_preview(
                    prerequisites=_empty_prerequisites(official_lane_key, ["lane_arm_preview_error"]),
                    latest_r234={},
                    latest_r233={},
                    latest_r232={},
                    latest_r230={},
                    latest_r228={},
                    risk_contract_config={},
                    official_lane_key=official_lane_key,
                    now=generated_at,
                ),
                "lane_arm_gate_matrix": matrix,
                "operator_lane_arm_review_packet": build_operator_lane_arm_review_packet(matrix),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R235 lane-arm preview error before any lane-arm write gate.",
                "lane_arm_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_live_execution_enable_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_live_execution_enable_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        artifact = record.get("execution_enable") if isinstance(record.get("execution_enable"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or artifact.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == "TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_WRITTEN"
            and record.get("execution_enable_written") is True
        ):
            return _sanitize({**record, "r234_execution_enable_found": True})
    return {}


def load_latest_tiny_live_live_execution_enable_preview_record(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    path = Path(get_log_dir(log_dir, use_env=True)) / R233_LEDGER_FILENAME
    if not path.exists():
        return {}
    records = read_recent_ndjson_records(path, limit=50, max_bytes=16_777_216)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        matrix = record.get("live_execution_enable_gate_matrix") if isinstance(record.get("live_execution_enable_gate_matrix"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or "") == official_lane_key
            and record.get("status") in {
                "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY",
                "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDED",
            }
            and matrix.get("live_execution_enable_preview_ready") is True
        ):
            return _sanitize({**record, "r233_preview_found": True})
    return {}


def load_latest_tiny_live_live_authorization_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_live_authorization_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        auth = record.get("authorization") if isinstance(record.get("authorization"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or auth.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_WRITTEN"
            and record.get("authorization_written") is True
        ):
            return _sanitize({**record, "r232_authorization_found": True})
    return {}


def load_latest_tiny_live_risk_contract_config_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_risk_contract_config_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        post_write = record.get("post_write_verification") if isinstance(record.get("post_write_verification"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_WRITTEN"
            and record.get("config_written") is True
            and post_write.get("matching_contract_valid") is True
        ):
            return _sanitize({**record, "r230_config_gate_found": True})
    return {}


def load_lane_controls_readonly(
    lane_controls_path: str | Path | None = None,
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    state = build_lane_control_state(path, official_lane_key=official_lane_key)
    return {
        "lane_controls_found": state.get("lane_controls_found") is True,
        "official_lane_already_armed": state.get("lane_armed") is True,
        "official_lane_mode": state.get("matching_lane_mode"),
        "matching_lane_found": state.get("matching_lane_found") is True,
        "kill_switch_disabled": state.get("kill_switch_disabled") is True,
        "read_only": True,
        "would_mutate": False,
        "lane_controls_path": str(path),
    }


def validate_lane_arm_prerequisites(
    *,
    latest_r234: Mapping[str, Any],
    latest_r233: Mapping[str, Any],
    latest_r232: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_contract_config: Mapping[str, Any],
    lane_controls_readonly_summary: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    lane_state = {
        "lane_armed": lane_controls_readonly_summary.get("official_lane_already_armed") is True,
        "kill_switch_disabled": lane_controls_readonly_summary.get("kill_switch_disabled") is True,
    }
    base = validate_live_execution_enable_prerequisites(
        latest_r232=latest_r232,
        latest_r231={},
        latest_r230=latest_r230,
        latest_r228=latest_r228,
        risk_contract_config=risk_contract_config,
        lane_control_state=lane_state,
        official_lane_key=official_lane_key,
    )
    auth = latest_r232.get("authorization") if isinstance(latest_r232.get("authorization"), Mapping) else {}
    execution_enable = (
        latest_r234.get("execution_enable") if isinstance(latest_r234.get("execution_enable"), Mapping) else {}
    )
    auth_validation = validate_live_authorization_object(auth) if auth else {"valid": False, "errors": ["authorization_missing"], "warnings": []}
    execution_validation = (
        validate_live_execution_enable_object(execution_enable)
        if execution_enable
        else {"valid": False, "errors": ["execution_enable_missing"], "warnings": []}
    )
    input_summary = {
        "r228_packet_found": bool(latest_r228),
        "r228_evidence_ready": base["input_summary"].get("r228_evidence_ready") is True,
        "r228_fisherman_ready": base["input_summary"].get("r228_fisherman_ready") is True,
        "r230_risk_contract_config_found": base["input_summary"].get("r230_risk_contract_config_found") is True,
        "risk_contract_valid": base["input_summary"].get("risk_contract_valid") is True,
        "r232_authorization_found": bool(latest_r232),
        "r232_authorization_valid": auth_validation.get("valid") is True,
        "r234_execution_enable_found": bool(latest_r234),
        "r234_execution_enable_valid": execution_validation.get("valid") is True,
        "live_authorized": auth.get("live_authorized") is True and execution_enable.get("live_authorized") is True,
        "live_execution_enabled": execution_enable.get("live_execution_enabled") is True,
        "lane_armed": False,
    }
    blocked_by = list(base.get("blocked_by") or [])
    blocked_by = [item for item in blocked_by if item != "live_execution_enabled_not_false"]
    if not latest_r233:
        blocked_by.append("r233_execution_enable_preview_missing")
    if not input_summary["r234_execution_enable_found"]:
        blocked_by.append("r234_execution_enable_missing")
    if input_summary["r234_execution_enable_found"] and not input_summary["r234_execution_enable_valid"]:
        blocked_by.extend(str(error) for error in execution_validation.get("errors") or ["r234_execution_enable_invalid"])
    if execution_enable.get("live_execution_enabled") is not True:
        blocked_by.append("live_execution_enabled_not_true_in_execution_enable_artifact")
    if auth.get("live_authorized") is not True:
        blocked_by.append("live_authorized_not_true_in_authorization_artifact")
    if execution_enable.get("live_authorized") is not True:
        blocked_by.append("live_authorized_not_true_in_execution_enable_artifact")
    if auth.get("order_payload_allowed") is not False or execution_enable.get("order_payload_allowed") is not False:
        blocked_by.append("order_payload_allowed_not_false")
    if execution_enable.get("lane_armed") is not False or auth.get("lane_armed") is not False:
        blocked_by.append("lane_armed_not_false")
    if lane_controls_readonly_summary.get("official_lane_already_armed") is True:
        blocked_by.append("official_lane_already_armed_in_lane_controls")
    if lane_controls_readonly_summary.get("lane_controls_found") is not True:
        blocked_by.append("lane_controls_missing")
    if official_lane_key != OFFICIAL_LANE_KEY:
        blocked_by.append("official_lane_mismatch")
    return {
        "input_summary": input_summary,
        "authorization_summary": _authorization_summary(auth),
        "execution_enable_summary": _execution_enable_summary(execution_enable),
        "lane_controls_readonly_summary": dict(lane_controls_readonly_summary),
        "authorization_validation": auth_validation,
        "execution_enable_validation": execution_validation,
        "blocked_by": _dedupe(blocked_by),
    }


def build_lane_arm_requirement_preview(
    *,
    prerequisites: Mapping[str, Any],
    latest_r234: Mapping[str, Any],
    latest_r233: Mapping[str, Any],
    latest_r232: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_contract_config: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    contract = risk_contract_config.get("matching_risk_contract") if isinstance(risk_contract_config.get("matching_risk_contract"), Mapping) else {}
    auth = latest_r232.get("authorization") if isinstance(latest_r232.get("authorization"), Mapping) else {}
    execution_enable = (
        latest_r234.get("execution_enable") if isinstance(latest_r234.get("execution_enable"), Mapping) else {}
    )
    return {
        "lane_arm_preview_id": f"r235_lane_arm_preview_{symbol}_{timeframe}_{direction}_{entry_mode}_{uuid4().hex}",
        "preview_only": True,
        "generated_at": generated_at.isoformat(),
        "official_lane_key": official_lane_key,
        "evidence_packet_reference": latest_r228.get("packet_record_id") or latest_r228.get("generated_at"),
        "risk_contract_config_gate_reference": latest_r230.get("gate_record_id") or latest_r230.get("generated_at"),
        "risk_contract_reference": contract.get("contract_id"),
        "authorization_preview_reference": latest_r233.get("authorization_preview_reference"),
        "authorization_reference": auth.get("authorization_id") or latest_r232.get("gate_record_id"),
        "execution_enable_preview_reference": latest_r233.get("execution_enable_preview_record_id"),
        "execution_enable_reference": execution_enable.get("execution_enable_id") or latest_r234.get("gate_record_id"),
        "future_lane_arm_required": True,
        "future_confirmation_required": True,
        "future_operator_final_approval_required": True,
        "future_order_preflight_required": True,
        "future_binance_connectivity_check_required": True,
        "future_order_payload_still_forbidden_now": True,
        "future_suggested_confirmation_phrase": "I CONFIRM TINY LIVE LANE ARM ONLY; NO ORDER; NO BINANCE CALL.",
        "notes": [
            "R235 records a preview only; it does not arm the official lane.",
            "R234 live execution enable is a bounded artifact and is not order authority.",
            "A future R236 write gate must separately require exact operator confirmation.",
            "Order payload creation and Binance/network calls remain forbidden now.",
            f"Remaining gates: {', '.join(prerequisites.get('blocked_by') or ['future_lane_arm_write_gate_required', 'future_order_preflight_required', 'future_binance_connectivity_check_required'])}.",
        ],
    }


def build_lane_arm_gate_matrix(prerequisites: Mapping[str, Any]) -> dict[str, Any]:
    input_summary = prerequisites.get("input_summary") if isinstance(prerequisites.get("input_summary"), Mapping) else {}
    blocked_by = list(prerequisites.get("blocked_by") or [])
    preview_ready = not blocked_by
    if preview_ready:
        blocked_by = [
            "future_lane_arm_write_gate_required",
            "future_operator_final_approval_required",
            "future_order_preflight_required",
            "future_binance_connectivity_check_required",
            "order_payload_forbidden",
        ]
    return {
        "evidence_ready": input_summary.get("r228_evidence_ready") is True,
        "fisherman_ready": input_summary.get("r228_fisherman_ready") is True,
        "risk_contract_config_ready": input_summary.get("risk_contract_valid") is True,
        "live_authorization_written": input_summary.get("r232_authorization_found") is True,
        "live_authorized": input_summary.get("live_authorized") is True,
        "live_execution_enable_written": input_summary.get("r234_execution_enable_found") is True,
        "live_execution_enabled": input_summary.get("live_execution_enabled") is True,
        "lane_arm_preview_ready": preview_ready,
        "lane_armed": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blocked_by),
    }


def build_operator_lane_arm_review_packet(lane_arm_gate_matrix: Mapping[str, Any]) -> dict[str, Any]:
    preview_ready = lane_arm_gate_matrix.get("lane_arm_preview_ready") is True
    if preview_ready:
        action = "REVIEW_R235_LANE_ARM_PREVIEW"
    elif any(str(item).endswith("_missing") for item in lane_arm_gate_matrix.get("blocked_by") or []):
        action = "WAIT"
    else:
        action = "FIX_BLOCKER"
    return {
        "operator_should_review_lane_arm_preview": preview_ready,
        "operator_should_arm_lane_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not arm lane from this phase",
            "do not disable kill switch",
            "do not call Binance from this phase",
        ],
    }


def build_lane_arm_preview_recommendations(lane_arm_gate_matrix: Mapping[str, Any]) -> dict[str, str]:
    if lane_arm_gate_matrix.get("lane_arm_preview_ready"):
        return {
            "recommended_next_operator_move": "REVIEW_R235_LANE_ARM_PREVIEW",
            "recommended_next_engineering_move": "Create R236 guarded tiny-live lane-arm write gate; still no Binance/network calls, orders, order payloads, or kill-switch disable.",
        }
    if not lane_arm_gate_matrix.get("live_execution_enable_written"):
        return {
            "recommended_next_operator_move": "WAIT",
            "recommended_next_engineering_move": "Restore or write the R234 execution-enable artifact before any lane-arm preview can proceed.",
        }
    return {
        "recommended_next_operator_move": "FIX_BLOCKER",
        "recommended_next_engineering_move": "Fix R235 evidence, fisherman, risk-contract, authorization, execution-enable, or lane-control blockers before R236.",
    }


def classify_tiny_live_lane_arm_preview_status(
    *,
    prerequisites: Mapping[str, Any],
    gate_matrix: Mapping[str, Any],
) -> str:
    input_summary = prerequisites.get("input_summary") if isinstance(prerequisites.get("input_summary"), Mapping) else {}
    blocked_by = set(gate_matrix.get("blocked_by") or [])
    if gate_matrix.get("lane_arm_preview_ready"):
        return TINY_LIVE_LANE_ARM_PREVIEW_READY_FOR_FUTURE_GATE
    if not input_summary.get("r234_execution_enable_found"):
        return TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE
    if not input_summary.get("r232_authorization_found") or any("authorization" in str(item) for item in blocked_by):
        return TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_AUTHORIZATION
    if any("execution_enable" in str(item) for item in blocked_by):
        return TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE
    if not input_summary.get("r228_packet_found") or "r228_evidence_not_ready" in blocked_by:
        return TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_EVIDENCE
    if "r228_fisherman_not_ready" in blocked_by:
        return TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_FISHERMAN
    if any("risk_contract" in str(item) or "r230" in str(item) for item in blocked_by):
        return TINY_LIVE_LANE_ARM_PREVIEW_BLOCKED_BY_RISK_CONTRACT
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_lane_arm_preview_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = tiny_live_lane_arm_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "lane_arm_preview_record_id": record.get("lane_arm_preview_record_id")
            or f"r235_lane_arm_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "lane_arm_preview_recorded": record.get("status") == TINY_LIVE_LANE_ARM_PREVIEW_RECORDED
            or record.get("lane_arm_preview_recorded") is True,
            "record_lane_arm_preview_requested": record.get("record_lane_arm_preview_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "authorization_summary": dict(record.get("authorization_summary") or {}),
            "execution_enable_summary": dict(record.get("execution_enable_summary") or {}),
            "lane_controls_readonly_summary": dict(record.get("lane_controls_readonly_summary") or {}),
            "lane_arm_requirement_preview": dict(record.get("lane_arm_requirement_preview") or {}),
            "lane_arm_gate_matrix": dict(record.get("lane_arm_gate_matrix") or {}),
            "operator_lane_arm_review_packet": dict(record.get("operator_lane_arm_review_packet") or {}),
            "lane_arm_preview_overall_status": record.get("lane_arm_preview_overall_status"),
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


def load_tiny_live_lane_arm_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_lane_arm_preview_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_tiny_live_lane_arm_preview_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_preview_recorded": latest.get("lane_arm_preview_recorded") is True,
        "latest_overall_status": latest.get("lane_arm_preview_overall_status"),
    }


def tiny_live_lane_arm_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_lane_arm_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _authorization_summary(auth: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "authorization_id": auth.get("authorization_id"),
        "authorization_status": auth.get("authorization_status"),
        "live_authorized": auth.get("live_authorized") is True,
        "live_execution_enabled": auth.get("live_execution_enabled") is True,
        "lane_armed": auth.get("lane_armed") is True,
        "order_payload_allowed": auth.get("order_payload_allowed") is True,
        "binance_call_allowed": auth.get("binance_call_allowed") is True,
    }


def _execution_enable_summary(execution_enable: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "execution_enable_id": execution_enable.get("execution_enable_id"),
        "execution_enable_status": execution_enable.get("execution_enable_status"),
        "live_authorized": execution_enable.get("live_authorized") is True,
        "live_execution_enabled": execution_enable.get("live_execution_enabled") is True,
        "lane_armed": execution_enable.get("lane_armed") is True,
        "order_payload_allowed": execution_enable.get("order_payload_allowed") is True,
        "binance_call_allowed": execution_enable.get("binance_call_allowed") is True,
    }


def _target_scope(lane_key: str, *, live_authorized: bool, live_execution_enabled: bool) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "lane_arm_preview_only": True,
        "live_authorized": bool(live_authorized),
        "live_execution_enabled": bool(live_execution_enabled),
        "lane_armed": False,
        "order_payload_allowed": False,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r228_packet_found": False,
        "r228_evidence_ready": False,
        "r228_fisherman_ready": False,
        "r230_risk_contract_config_found": False,
        "risk_contract_valid": False,
        "r232_authorization_found": False,
        "r232_authorization_valid": False,
        "r234_execution_enable_found": False,
        "r234_execution_enable_valid": False,
        "live_authorized": False,
        "live_execution_enabled": False,
        "lane_armed": False,
    }


def _empty_lane_controls_readonly_summary(path: str | Path) -> dict[str, Any]:
    return {
        "lane_controls_found": False,
        "official_lane_already_armed": False,
        "official_lane_mode": None,
        "matching_lane_found": False,
        "kill_switch_disabled": False,
        "read_only": True,
        "would_mutate": False,
        "lane_controls_path": str(path),
    }


def _empty_prerequisites(official_lane_key: str, blocked_by: list[str] | None = None) -> dict[str, Any]:
    return {
        "input_summary": _empty_input_summary(),
        "authorization_summary": _authorization_summary({}),
        "execution_enable_summary": _execution_enable_summary({}),
        "lane_controls_readonly_summary": _empty_lane_controls_readonly_summary(LANE_CONTROLS_PATH),
        "authorization_validation": {"valid": False, "errors": list(blocked_by or []), "warnings": []},
        "execution_enable_validation": {"valid": False, "errors": list(blocked_by or []), "warnings": []},
        "blocked_by": list(blocked_by or []),
    }


def _empty_gate_matrix(blockers: list[str] | None = None) -> dict[str, Any]:
    return {
        "evidence_ready": False,
        "fisherman_ready": False,
        "risk_contract_config_ready": False,
        "live_authorization_written": False,
        "live_authorized": False,
        "live_execution_enable_written": False,
        "live_execution_enabled": False,
        "lane_arm_preview_ready": False,
        "lane_armed": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": list(blockers or []),
    }


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming outside bounded artifacts",
        "kill switch disable",
        "set any lane tiny_live",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = lane_key.split("|")
    if len(parts) != 4:
        return lane_key, "", "", ""
    return parts[0], parts[1], parts[2], parts[3]


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
