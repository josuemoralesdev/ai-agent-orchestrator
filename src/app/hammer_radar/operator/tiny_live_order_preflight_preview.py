"""R237 tiny-live order preflight preview.

This module consumes the modern R228-R236 tiny-live artifact chain and previews
future order-preflight requirements only. It never creates order payloads,
signed requests, Binance/network calls, config writes, live orders, or kill
switch changes.
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
from src.app.hammer_radar.operator.tiny_live_lane_arm_preview import (
    LEDGER_FILENAME as R235_LEDGER_FILENAME,
    load_lane_controls_readonly as _load_lane_controls_readonly,
    load_tiny_live_lane_arm_preview_records,
)
from src.app.hammer_radar.operator.tiny_live_lane_arm_write_gate import (
    LEDGER_FILENAME as R236_LEDGER_FILENAME,
    load_tiny_live_lane_arm_write_gate_records,
    validate_lane_arm_object,
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_preview import LANE_CONTROLS_PATH
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    LEDGER_FILENAME as R232_LEDGER_FILENAME,
    load_latest_tiny_live_10_of_10_ready_packet,
    load_latest_tiny_live_risk_contract_config_write_gate,
    load_tiny_live_live_authorization_write_gate_records,
    load_tiny_live_risk_contract_config,
    validate_live_authorization_object,
)
from src.app.hammer_radar.operator.tiny_live_live_execution_enable_write_gate import (
    LEDGER_FILENAME as R234_LEDGER_FILENAME,
    load_tiny_live_live_execution_enable_write_gate_records,
    validate_live_execution_enable_object,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    LEDGER_FILENAME as R230_LEDGER_FILENAME,
    load_tiny_live_risk_contract_config_write_gate_records,
    validate_tiny_live_risk_contract_config_entry,
)

TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY = "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY"
TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_REJECTED = "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_REJECTED"
TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDED = "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDED"
TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED = "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED"
TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_ERROR = "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_ERROR"

TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY_FOR_FUTURE_GATE = (
    "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY_FOR_FUTURE_GATE"
)
TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_LANE_ARM = (
    "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_LANE_ARM"
)
TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE = (
    "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE"
)
TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_AUTHORIZATION = (
    "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_AUTHORIZATION"
)
TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_RISK_CONTRACT = (
    "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_RISK_CONTRACT"
)
TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EVIDENCE = (
    "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EVIDENCE"
)
TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_FISHERMAN = (
    "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_FISHERMAN"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW"
LEDGER_FILENAME = "tiny_live_order_preflight_preview.ndjson"
CONFIRM_TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE ORDER PREFLIGHT PREVIEW RECORDING ONLY; "
    "NO CONFIG WRITE; NO ORDER PAYLOAD; NO BINANCE CALL."
)
FUTURE_ORDER_PREFLIGHT_CONFIRMATION_PHRASE = (
    "I CONFIRM TINY LIVE ORDER PREFLIGHT ONLY; NO ORDER PAYLOAD; NO BINANCE CALL."
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
    "lane_arm_written": False,
    "order_preflight_written": False,
    "live_execution_enabled": False,
    "lane_armed": False,
    "order_payload_allowed": False,
    "order_payload_created": False,
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
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "binance_account_endpoint_called": False,
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
    "order_preflight_preview_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R236_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R235_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R234_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R232_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R230_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_order_preflight_preview(
    *,
    log_dir: str | Path | None = None,
    record_order_preflight_preview: bool = False,
    confirm_tiny_live_order_preflight_preview: str | None = None,
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
        confirm_tiny_live_order_preflight_preview
        == CONFIRM_TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDING_PHRASE
    )
    try:
        latest_r236 = load_latest_tiny_live_lane_arm_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r235 = load_latest_tiny_live_lane_arm_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r234 = load_latest_tiny_live_live_execution_enable_write_gate(
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
        lane_controls = load_lane_controls_readonly(lane_path, official_lane_key=official_lane_key)
        prerequisites = validate_order_preflight_prerequisites(
            latest_r236=latest_r236,
            latest_r235=latest_r235,
            latest_r234=latest_r234,
            latest_r232=latest_r232,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_contract_config=risk_config,
            lane_controls_readonly_summary=lane_controls,
            official_lane_key=official_lane_key,
        )
        requirement_preview = build_order_preflight_requirement_preview(
            prerequisites=prerequisites,
            latest_r236=latest_r236,
            latest_r235=latest_r235,
            latest_r234=latest_r234,
            latest_r232=latest_r232,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_contract_config=risk_config,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        matrix = build_order_preflight_gate_matrix(prerequisites)
        operator_packet = build_operator_order_preflight_review_packet(matrix)
        recommendations = build_order_preflight_preview_recommendations(matrix)
        overall = classify_tiny_live_order_preflight_preview_status(
            prerequisites=prerequisites,
            gate_matrix=matrix,
        )
        status = (
            TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY
            if overall == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY_FOR_FUTURE_GATE
            else TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED
        )
        if record_order_preflight_preview and not confirmation_valid:
            status = TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_REJECTED
        elif record_order_preflight_preview and confirmation_valid and status == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY:
            status = TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "order_preflight_preview_recorded": False,
            "order_preflight_preview_record_id": None,
            "record_order_preflight_preview_requested": bool(record_order_preflight_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(
                official_lane_key,
                live_authorized=prerequisites["input_summary"].get("live_authorized") is True,
                live_execution_enabled=prerequisites["input_summary"].get("live_execution_enabled") is True,
                lane_armed=prerequisites["input_summary"].get("lane_armed") is True,
            ),
            "input_summary": prerequisites["input_summary"],
            "risk_contract_summary": _risk_contract_summary(risk_config),
            "lane_arm_summary": prerequisites["lane_arm_summary"],
            "lane_controls_readonly_summary": lane_controls,
            "order_preflight_requirement_preview": requirement_preview,
            "order_preflight_gate_matrix": matrix,
            "operator_order_preflight_review_packet": operator_packet,
            "recommended_next_operator_move": recommendations["recommended_next_operator_move"],
            "recommended_next_engineering_move": recommendations["recommended_next_engineering_move"],
            "order_preflight_preview_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if status == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDED:
            record = append_tiny_live_order_preflight_preview_record(payload, log_dir=resolved_log_dir)
            payload["order_preflight_preview_recorded"] = True
            payload["order_preflight_preview_record_id"] = record["order_preflight_preview_record_id"]
            payload["ledger_path"] = str(tiny_live_order_preflight_preview_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = _empty_gate_matrix(["order_preflight_preview_error"])
        return _sanitize(
            {
                "status": TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "order_preflight_preview_recorded": False,
                "order_preflight_preview_record_id": None,
                "record_order_preflight_preview_requested": bool(record_order_preflight_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(
                    official_lane_key,
                    live_authorized=False,
                    live_execution_enabled=False,
                    lane_armed=False,
                ),
                "input_summary": _empty_input_summary(),
                "risk_contract_summary": _risk_contract_summary({}),
                "lane_arm_summary": _lane_arm_summary({}),
                "lane_controls_readonly_summary": _empty_lane_controls_readonly_summary(lane_path),
                "order_preflight_requirement_preview": build_order_preflight_requirement_preview(
                    prerequisites=_empty_prerequisites(["order_preflight_preview_error"]),
                    latest_r236={},
                    latest_r235={},
                    latest_r234={},
                    latest_r232={},
                    latest_r230={},
                    latest_r228={},
                    risk_contract_config={},
                    official_lane_key=official_lane_key,
                    now=generated_at,
                ),
                "order_preflight_gate_matrix": matrix,
                "operator_order_preflight_review_packet": build_operator_order_preflight_review_packet(matrix),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R237 order-preflight preview error before any write gate.",
                "order_preflight_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_lane_arm_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_lane_arm_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        artifact = record.get("lane_arm") if isinstance(record.get("lane_arm"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or artifact.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == "TINY_LIVE_LANE_ARM_WRITE_GATE_WRITTEN"
            and record.get("lane_arm_written") is True
        ):
            return _sanitize({**record, "r236_lane_arm_found": True})
    return {}


def load_latest_tiny_live_lane_arm_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_lane_arm_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        matrix = record.get("lane_arm_gate_matrix") if isinstance(record.get("lane_arm_gate_matrix"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or "") == official_lane_key
            and record.get("status") in {"TINY_LIVE_LANE_ARM_PREVIEW_READY", "TINY_LIVE_LANE_ARM_PREVIEW_RECORDED"}
            and record.get("lane_arm_preview_overall_status") == "TINY_LIVE_LANE_ARM_PREVIEW_READY_FOR_FUTURE_GATE"
            and matrix.get("lane_arm_preview_ready") is True
        ):
            return _sanitize({**record, "r235_preview_found": True})
    return {}


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


def load_lane_controls_readonly(
    lane_controls_path: str | Path | None = None,
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    summary = _load_lane_controls_readonly(lane_controls_path, official_lane_key=official_lane_key)
    return {
        **summary,
        "official_lane_already_armed_in_config": summary.get("official_lane_already_armed") is True,
    }


def validate_order_preflight_prerequisites(
    *,
    latest_r236: Mapping[str, Any],
    latest_r235: Mapping[str, Any],
    latest_r234: Mapping[str, Any],
    latest_r232: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_contract_config: Mapping[str, Any],
    lane_controls_readonly_summary: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    execution_enable = latest_r234.get("execution_enable") if isinstance(latest_r234.get("execution_enable"), Mapping) else {}
    auth = latest_r232.get("authorization") if isinstance(latest_r232.get("authorization"), Mapping) else {}
    risk_contract = (
        risk_contract_config.get("matching_risk_contract")
        if isinstance(risk_contract_config.get("matching_risk_contract"), Mapping)
        else {}
    )
    r228_matrix = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    lane_arm_validation = validate_lane_arm_object(lane_arm) if lane_arm else {"valid": False, "errors": ["lane_arm_missing"]}
    execution_validation = (
        validate_live_execution_enable_object(execution_enable)
        if execution_enable
        else {"valid": False, "errors": ["execution_enable_missing"]}
    )
    auth_validation = validate_live_authorization_object(auth) if auth else {"valid": False, "errors": ["authorization_missing"]}
    risk_validation = (
        validate_tiny_live_risk_contract_config_entry(risk_contract)
        if risk_contract
        else {"valid": False, "errors": ["risk_contract_missing"]}
    )
    input_summary = {
        "r228_packet_found": bool(latest_r228),
        "r228_evidence_ready": r228_matrix.get("evidence_ready") is True,
        "r228_fisherman_ready": r228_matrix.get("fisherman_ready") is True,
        "r230_risk_contract_config_found": bool(latest_r230) and bool(risk_contract),
        "risk_contract_valid": risk_validation.get("valid") is True,
        "r232_authorization_found": bool(latest_r232),
        "r232_authorization_valid": auth_validation.get("valid") is True,
        "r234_execution_enable_found": bool(latest_r234),
        "r234_execution_enable_valid": execution_validation.get("valid") is True,
        "r236_lane_arm_found": bool(latest_r236),
        "r236_lane_arm_valid": lane_arm_validation.get("valid") is True,
        "live_authorized": auth.get("live_authorized") is True
        and execution_enable.get("live_authorized") is True
        and lane_arm.get("live_authorized") is True,
        "live_execution_enabled": execution_enable.get("live_execution_enabled") is True
        and lane_arm.get("live_execution_enabled") is True,
        "lane_armed": lane_arm.get("lane_armed") is True,
        "order_payload_created": False,
    }
    blocked_by: list[str] = []
    if official_lane_key != OFFICIAL_LANE_KEY:
        blocked_by.append("official_lane_mismatch")
    if not input_summary["r228_packet_found"] or not input_summary["r228_evidence_ready"]:
        blocked_by.append("r228_evidence_not_ready")
    if not input_summary["r228_fisherman_ready"]:
        blocked_by.append("r228_fisherman_not_ready")
    if not input_summary["r230_risk_contract_config_found"] or not input_summary["risk_contract_valid"]:
        blocked_by.append("risk_contract_config_not_ready")
    if not input_summary["r232_authorization_found"] or not input_summary["r232_authorization_valid"]:
        blocked_by.append("authorization_not_ready")
    if not input_summary["r234_execution_enable_found"] or not input_summary["r234_execution_enable_valid"]:
        blocked_by.append("execution_enable_not_ready")
    if not input_summary["r236_lane_arm_found"] or not input_summary["r236_lane_arm_valid"]:
        blocked_by.append("lane_arm_not_ready")
    if not input_summary["live_authorized"]:
        blocked_by.append("live_authorized_not_true")
    if not input_summary["live_execution_enabled"]:
        blocked_by.append("live_execution_enabled_not_true")
    if not input_summary["lane_armed"]:
        blocked_by.append("lane_armed_not_true")
    if lane_controls_readonly_summary.get("lane_controls_found") is not True:
        blocked_by.append("lane_controls_missing")
    if lane_controls_readonly_summary.get("official_lane_already_armed_in_config") is True:
        blocked_by.append("lane_controls_config_already_armed")
    if lane_controls_readonly_summary.get("kill_switch_disabled") is True:
        blocked_by.append("kill_switch_disabled_in_lane_controls")
    for artifact_name, artifact in (
        ("authorization", auth),
        ("execution_enable", execution_enable),
        ("lane_arm", lane_arm),
    ):
        if artifact.get("order_payload_allowed") is not False:
            blocked_by.append(f"{artifact_name}_order_payload_allowed_not_false")
        if artifact.get("order_payload_created") is True:
            blocked_by.append(f"{artifact_name}_order_payload_created_not_false")
        if artifact.get("binance_call_allowed") is not False:
            blocked_by.append(f"{artifact_name}_binance_call_allowed_not_false")
        if artifact.get("kill_switch_disabled") is True:
            blocked_by.append(f"{artifact_name}_kill_switch_disabled")
    return {
        "input_summary": input_summary,
        "risk_contract_validation": risk_validation,
        "authorization_validation": auth_validation,
        "execution_enable_validation": execution_validation,
        "lane_arm_validation": lane_arm_validation,
        "lane_arm_summary": _lane_arm_summary(lane_arm),
        "blocked_by": _dedupe(blocked_by),
    }


def build_order_preflight_requirement_preview(
    *,
    prerequisites: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    latest_r235: Mapping[str, Any],
    latest_r234: Mapping[str, Any],
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
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    execution_enable = latest_r234.get("execution_enable") if isinstance(latest_r234.get("execution_enable"), Mapping) else {}
    auth = latest_r232.get("authorization") if isinstance(latest_r232.get("authorization"), Mapping) else {}
    return {
        "order_preflight_preview_id": f"r237_order_preflight_preview_{symbol}_{timeframe}_{direction}_{entry_mode}_{uuid4().hex}",
        "preview_only": True,
        "generated_at": generated_at.isoformat(),
        "official_lane_key": official_lane_key,
        "evidence_packet_reference": latest_r228.get("packet_record_id") or latest_r228.get("generated_at"),
        "risk_contract_config_gate_reference": latest_r230.get("gate_record_id") or latest_r230.get("generated_at"),
        "risk_contract_reference": contract.get("contract_id"),
        "authorization_reference": auth.get("authorization_id") or latest_r232.get("gate_record_id"),
        "execution_enable_reference": execution_enable.get("execution_enable_id") or latest_r234.get("gate_record_id"),
        "lane_arm_preview_reference": latest_r235.get("lane_arm_preview_record_id"),
        "lane_arm_reference": lane_arm.get("lane_arm_id") or latest_r236.get("gate_record_id"),
        "future_order_preflight_required": True,
        "future_confirmation_required": True,
        "future_operator_final_approval_required": True,
        "future_binance_connectivity_check_required": True,
        "future_order_payload_creation_required_later": True,
        "future_order_payload_still_forbidden_now": True,
        "future_suggested_confirmation_phrase": FUTURE_ORDER_PREFLIGHT_CONFIRMATION_PHRASE,
        "notes": [
            "R237 records an order-preflight preview only; it does not create an order payload.",
            "The R236 lane-arm artifact is non-executable and keeps order payloads forbidden.",
            "Any future order-preflight write gate must require a fresh exact operator confirmation.",
            "Binance/network calls, signed requests, kill-switch disable, and order placement remain forbidden now.",
            f"Remaining gates: {', '.join(prerequisites.get('blocked_by') or ['future_order_preflight_write_gate_required', 'future_operator_final_approval_required', 'future_binance_connectivity_check_required', 'order_payload_forbidden'])}.",
        ],
    }


def build_order_preflight_gate_matrix(prerequisites: Mapping[str, Any]) -> dict[str, Any]:
    input_summary = prerequisites.get("input_summary") if isinstance(prerequisites.get("input_summary"), Mapping) else {}
    blocked_by = list(prerequisites.get("blocked_by") or [])
    preview_ready = not blocked_by
    if preview_ready:
        blocked_by = [
            "future_order_preflight_write_gate_required",
            "future_operator_final_approval_required",
            "future_binance_connectivity_check_required",
            "order_payload_forbidden",
            "kill_switch_still_active",
        ]
    return {
        "evidence_ready": input_summary.get("r228_evidence_ready") is True,
        "fisherman_ready": input_summary.get("r228_fisherman_ready") is True,
        "risk_contract_config_ready": input_summary.get("risk_contract_valid") is True,
        "live_authorization_written": input_summary.get("r232_authorization_found") is True,
        "live_authorized": input_summary.get("live_authorized") is True,
        "live_execution_enable_written": input_summary.get("r234_execution_enable_found") is True,
        "live_execution_enabled": input_summary.get("live_execution_enabled") is True,
        "lane_arm_written": input_summary.get("r236_lane_arm_found") is True,
        "lane_armed": input_summary.get("lane_armed") is True,
        "order_preflight_preview_ready": preview_ready,
        "order_payload_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blocked_by),
    }


def build_operator_order_preflight_review_packet(order_preflight_gate_matrix: Mapping[str, Any]) -> dict[str, Any]:
    preview_ready = order_preflight_gate_matrix.get("order_preflight_preview_ready") is True
    if preview_ready:
        action = "REVIEW_R237_ORDER_PREFLIGHT_PREVIEW"
    elif any(str(item).endswith("_missing") or "not_ready" in str(item) for item in order_preflight_gate_matrix.get("blocked_by") or []):
        action = "WAIT"
    else:
        action = "FIX_BLOCKER"
    return {
        "operator_should_review_order_preflight_preview": preview_ready,
        "operator_should_create_order_payload_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not create order payload from this phase",
            "do not disable kill switch",
            "do not call Binance from this phase",
        ],
    }


def build_order_preflight_preview_recommendations(order_preflight_gate_matrix: Mapping[str, Any]) -> dict[str, str]:
    if order_preflight_gate_matrix.get("order_preflight_preview_ready"):
        return {
            "recommended_next_operator_move": "REVIEW_R237_ORDER_PREFLIGHT_PREVIEW",
            "recommended_next_engineering_move": "Create R238 guarded tiny-live order-preflight write gate; still no Binance/network calls, orders, executable payloads, signed requests, or kill-switch disable.",
        }
    if not order_preflight_gate_matrix.get("lane_arm_written"):
        return {
            "recommended_next_operator_move": "WAIT",
            "recommended_next_engineering_move": "Restore or write the R236 lane-arm artifact before any order-preflight preview can proceed.",
        }
    return {
        "recommended_next_operator_move": "FIX_BLOCKER",
        "recommended_next_engineering_move": "Fix R237 evidence, fisherman, risk-contract, authorization, execution-enable, lane-arm, or read-only lane-control blockers before R238.",
    }


def classify_tiny_live_order_preflight_preview_status(
    *,
    prerequisites: Mapping[str, Any],
    gate_matrix: Mapping[str, Any],
) -> str:
    input_summary = prerequisites.get("input_summary") if isinstance(prerequisites.get("input_summary"), Mapping) else {}
    blocked_by = set(gate_matrix.get("blocked_by") or [])
    if gate_matrix.get("order_preflight_preview_ready"):
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY_FOR_FUTURE_GATE
    if not input_summary.get("r236_lane_arm_found"):
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_LANE_ARM
    if not input_summary.get("r234_execution_enable_found"):
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE
    if not input_summary.get("r232_authorization_found"):
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_AUTHORIZATION
    if "live_authorized_not_true" in blocked_by:
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_AUTHORIZATION
    if any("execution_enable" in str(item) for item in blocked_by):
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE
    if any("authorization" in str(item) for item in blocked_by):
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_AUTHORIZATION
    if "live_execution_enabled_not_true" in blocked_by:
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE
    if any("lane_arm" in str(item) or "lane_armed" in str(item) for item in blocked_by):
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_LANE_ARM
    if not input_summary.get("r228_packet_found") or "r228_evidence_not_ready" in blocked_by:
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EVIDENCE
    if "r228_fisherman_not_ready" in blocked_by:
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_FISHERMAN
    if any("risk_contract" in str(item) or "r230" in str(item) for item in blocked_by):
        return TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_RISK_CONTRACT
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_order_preflight_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_order_preflight_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "order_preflight_preview_record_id": record.get("order_preflight_preview_record_id")
            or f"r237_order_preflight_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "order_preflight_preview_recorded": record.get("status") == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDED
            or record.get("order_preflight_preview_recorded") is True,
            "record_order_preflight_preview_requested": record.get("record_order_preflight_preview_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "risk_contract_summary": dict(record.get("risk_contract_summary") or {}),
            "lane_arm_summary": dict(record.get("lane_arm_summary") or {}),
            "lane_controls_readonly_summary": dict(record.get("lane_controls_readonly_summary") or {}),
            "order_preflight_requirement_preview": dict(record.get("order_preflight_requirement_preview") or {}),
            "order_preflight_gate_matrix": dict(record.get("order_preflight_gate_matrix") or {}),
            "operator_order_preflight_review_packet": dict(record.get("operator_order_preflight_review_packet") or {}),
            "order_preflight_preview_overall_status": record.get("order_preflight_preview_overall_status"),
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


def load_tiny_live_order_preflight_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_order_preflight_preview_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_tiny_live_order_preflight_preview_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_preview_recorded": latest.get("order_preflight_preview_recorded") is True,
        "latest_overall_status": latest.get("order_preflight_preview_overall_status"),
    }


def tiny_live_order_preflight_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_order_preflight_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _risk_contract_summary(risk_contract_config: Mapping[str, Any]) -> dict[str, Any]:
    contract = risk_contract_config.get("matching_risk_contract") if isinstance(risk_contract_config.get("matching_risk_contract"), Mapping) else {}
    return {
        "official_lane_key": contract.get("official_lane_key") or OFFICIAL_LANE_KEY,
        "max_account_risk_usdt": contract.get("max_account_risk_usdt"),
        "max_loss_usdt": contract.get("max_loss_usdt"),
        "max_notional_usdt": contract.get("max_notional_usdt"),
        "leverage": contract.get("leverage"),
    }


def _lane_arm_summary(lane_arm: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_arm_id": lane_arm.get("lane_arm_id"),
        "lane_arm_status": lane_arm.get("lane_arm_status"),
        "live_authorized": lane_arm.get("live_authorized") is True,
        "live_execution_enabled": lane_arm.get("live_execution_enabled") is True,
        "lane_armed": lane_arm.get("lane_armed") is True,
        "order_payload_allowed": lane_arm.get("order_payload_allowed") is True,
        "order_payload_created": lane_arm.get("order_payload_created") is True,
        "binance_call_allowed": lane_arm.get("binance_call_allowed") is True,
        "kill_switch_disabled": lane_arm.get("kill_switch_disabled") is True,
    }


def _target_scope(
    lane_key: str,
    *,
    live_authorized: bool,
    live_execution_enabled: bool,
    lane_armed: bool,
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "order_preflight_preview_only": True,
        "live_authorized": bool(live_authorized),
        "live_execution_enabled": bool(live_execution_enabled),
        "lane_armed": bool(lane_armed),
        "order_payload_allowed": False,
        "order_payload_created": False,
        "kill_switch_disabled": False,
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
        "r236_lane_arm_found": False,
        "r236_lane_arm_valid": False,
        "live_authorized": False,
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_payload_created": False,
    }


def _empty_lane_controls_readonly_summary(path: str | Path) -> dict[str, Any]:
    return {
        "lane_controls_found": False,
        "official_lane_already_armed_in_config": False,
        "official_lane_mode": None,
        "matching_lane_found": False,
        "kill_switch_disabled": False,
        "read_only": True,
        "would_mutate": False,
        "lane_controls_path": str(path),
    }


def _empty_prerequisites(blocked_by: list[str] | None = None) -> dict[str, Any]:
    return {
        "input_summary": _empty_input_summary(),
        "risk_contract_validation": {"valid": False, "errors": list(blocked_by or []), "warnings": []},
        "authorization_validation": {"valid": False, "errors": list(blocked_by or []), "warnings": []},
        "execution_enable_validation": {"valid": False, "errors": list(blocked_by or []), "warnings": []},
        "lane_arm_validation": {"valid": False, "errors": list(blocked_by or []), "warnings": []},
        "lane_arm_summary": _lane_arm_summary({}),
        "blocked_by": list(blocked_by or []),
    }


def _empty_gate_matrix(blocked_by: list[str] | None = None) -> dict[str, Any]:
    return {
        "evidence_ready": False,
        "fisherman_ready": False,
        "risk_contract_config_ready": False,
        "live_authorization_written": False,
        "live_authorized": False,
        "live_execution_enable_written": False,
        "live_execution_enabled": False,
        "lane_arm_written": False,
        "lane_armed": False,
        "order_preflight_preview_ready": False,
        "order_payload_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": list(blocked_by or []),
    }


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "order payload creation",
        "kill switch disable",
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
