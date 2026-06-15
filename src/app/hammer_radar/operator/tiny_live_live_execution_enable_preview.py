"""R233 tiny-live live execution enable preview.

This module consumes the R228/R230/R231/R232 tiny-live lane artifacts and
previews future live-execution enablement requirements only. It never enables
live execution, arms lanes, creates order payloads, calls Binance/network, or
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
from src.app.hammer_radar.operator.tiny_live_live_authorization_preview import (
    LEDGER_FILENAME as R231_LEDGER_FILENAME,
    LANE_CONTROLS_PATH,
    TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY,
    TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY_FOR_FUTURE_GATE,
    TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDED,
    build_lane_control_state,
    load_tiny_live_live_authorization_preview_records,
    load_tiny_live_risk_contract_config as _load_r231_risk_contract_config,
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    LEDGER_FILENAME as R232_LEDGER_FILENAME,
    TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_WRITTEN,
    validate_live_authorization_object,
    load_tiny_live_live_authorization_write_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    LEDGER_FILENAME as R230_LEDGER_FILENAME,
    TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_WRITTEN,
    load_tiny_live_risk_contract_config_write_gate_records,
)

TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY = "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY"
TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_REJECTED = "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_REJECTED"
TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDED = "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDED"
TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED = "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED"
TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_ERROR = "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_ERROR"

TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY_FOR_FUTURE_GATE = (
    "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY_FOR_FUTURE_GATE"
)
TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_AUTHORIZATION = (
    "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_AUTHORIZATION"
)
TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_RISK_CONTRACT = (
    "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_RISK_CONTRACT"
)
TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_EVIDENCE = (
    "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_EVIDENCE"
)
TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_FISHERMAN = (
    "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_FISHERMAN"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW"
LEDGER_FILENAME = "tiny_live_live_execution_enable_preview.ndjson"
CONFIRM_TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE LIVE EXECUTION ENABLE PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "live_execution_enable_preview_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R232_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R231_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R230_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_live_execution_enable_preview(
    *,
    log_dir: str | Path | None = None,
    record_execution_enable_preview: bool = False,
    confirm_tiny_live_live_execution_enable_preview: str | None = None,
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
        confirm_tiny_live_live_execution_enable_preview
        == CONFIRM_TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDING_PHRASE
    )
    try:
        latest_r232 = load_latest_tiny_live_live_authorization_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r231 = load_latest_tiny_live_live_authorization_preview(
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
            latest_r231=latest_r231,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_contract_config=risk_config,
            lane_control_state=lane_state,
            official_lane_key=official_lane_key,
        )
        requirement_preview = build_live_execution_enable_requirement_preview(
            prerequisites=prerequisites,
            latest_r232=latest_r232,
            latest_r231=latest_r231,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_contract_config=risk_config,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        matrix = build_live_execution_enable_gate_matrix(prerequisites)
        operator_packet = build_operator_live_execution_enable_review_packet(matrix)
        recommendations = build_live_execution_enable_preview_recommendations(matrix)
        overall = classify_tiny_live_live_execution_enable_preview_status(
            prerequisites=prerequisites,
            gate_matrix=matrix,
        )
        status = (
            TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY
            if overall == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY_FOR_FUTURE_GATE
            and record_execution_enable_preview
            else TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED
        )
        if record_execution_enable_preview and not confirmation_valid:
            status = TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_REJECTED
        elif (
            record_execution_enable_preview
            and confirmation_valid
            and status == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY
        ):
            status = TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "execution_enable_preview_recorded": False,
            "execution_enable_preview_record_id": None,
            "record_execution_enable_preview_requested": bool(record_execution_enable_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(official_lane_key, prerequisites["input_summary"].get("live_authorized") is True),
            "input_summary": prerequisites["input_summary"],
            "authorization_summary": prerequisites["authorization_summary"],
            "risk_contract_summary": prerequisites["risk_contract_summary"],
            "live_execution_enable_requirement_preview": requirement_preview,
            "live_execution_enable_gate_matrix": matrix,
            "operator_live_execution_enable_review_packet": operator_packet,
            "recommended_next_operator_move": recommendations["recommended_next_operator_move"],
            "recommended_next_engineering_move": recommendations["recommended_next_engineering_move"],
            "live_execution_enable_preview_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if status == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDED:
            record = append_tiny_live_live_execution_enable_preview_record(payload, log_dir=resolved_log_dir)
            payload["execution_enable_preview_recorded"] = True
            payload["execution_enable_preview_record_id"] = record["execution_enable_preview_record_id"]
            payload["ledger_path"] = str(tiny_live_live_execution_enable_preview_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = _empty_gate_matrix(["execution_enable_preview_error"])
        return _sanitize(
            {
                "status": TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "execution_enable_preview_recorded": False,
                "execution_enable_preview_record_id": None,
                "record_execution_enable_preview_requested": bool(record_execution_enable_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(official_lane_key, False),
                "input_summary": _empty_input_summary(),
                "authorization_summary": _empty_authorization_summary(),
                "risk_contract_summary": _empty_risk_contract_summary(official_lane_key),
                "live_execution_enable_requirement_preview": build_live_execution_enable_requirement_preview(
                    prerequisites=_empty_prerequisites(official_lane_key, ["execution_enable_preview_error"]),
                    latest_r232={},
                    latest_r231={},
                    latest_r230={},
                    latest_r228={},
                    risk_contract_config={},
                    official_lane_key=official_lane_key,
                    now=generated_at,
                ),
                "live_execution_enable_gate_matrix": matrix,
                "operator_live_execution_enable_review_packet": build_operator_live_execution_enable_review_packet(matrix),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R233 preview error before any live execution enable write gate.",
                "live_execution_enable_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


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
            and record.get("status") == TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_WRITTEN
            and record.get("authorization_written") is True
        ):
            return _sanitize({**record, "r232_authorization_found": True})
    return {}


def load_latest_tiny_live_live_authorization_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_live_authorization_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        matrix = record.get("live_authorization_gate_matrix") if isinstance(record.get("live_authorization_gate_matrix"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or "") == official_lane_key
            and record.get("status") in {TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY, TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDED}
            and record.get("live_authorization_preview_overall_status")
            == TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY_FOR_FUTURE_GATE
            and matrix.get("live_authorization_preview_ready") is True
        ):
            return _sanitize({**record, "r231_preview_found": True})
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
            record.get("status") == TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_WRITTEN
            and record.get("config_written") is True
            and (str(target.get("official_lane_key") or "") == official_lane_key or post_write.get("matching_contract_found") is True)
        ):
            return _sanitize({**record, "r230_config_gate_found": True})
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
    return _load_r231_risk_contract_config(config_path, official_lane_key=official_lane_key)


def validate_live_execution_enable_prerequisites(
    *,
    latest_r232: Mapping[str, Any],
    latest_r231: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_contract_config: Mapping[str, Any],
    lane_control_state: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    auth = latest_r232.get("authorization") if isinstance(latest_r232.get("authorization"), Mapping) else {}
    auth_validation = validate_live_authorization_object(auth) if auth else {"valid": False, "errors": ["authorization_missing"], "warnings": []}
    r228_ready = _r228_ready(latest_r228, official_lane_key=official_lane_key)
    contract = risk_contract_config.get("matching_risk_contract") if isinstance(risk_contract_config.get("matching_risk_contract"), Mapping) else {}
    contract_valid = risk_contract_config.get("matching_risk_contract_valid") is True
    lane_armed = lane_control_state.get("lane_armed") is True or auth.get("lane_armed") is True
    live_execution_enabled = contract.get("live_execution_enabled") is True or auth.get("live_execution_enabled") is True
    input_summary = {
        "r228_packet_found": bool(latest_r228),
        "r228_evidence_ready": r228_ready["evidence_ready"],
        "r228_fisherman_ready": r228_ready["fisherman_ready"],
        "r230_risk_contract_config_found": bool(latest_r230) or risk_contract_config.get("matching_risk_contract_found") is True,
        "risk_contract_config_found": risk_contract_config.get("config_found") is True,
        "risk_contract_valid": contract_valid,
        "r232_authorization_found": bool(latest_r232),
        "r232_authorization_valid": auth_validation.get("valid") is True,
        "live_authorized": auth.get("live_authorized") is True,
        "live_execution_enabled": live_execution_enabled,
        "lane_armed": lane_armed,
    }
    blocked_by: list[str] = []
    if official_lane_key != OFFICIAL_LANE_KEY:
        blocked_by.append("official_lane_mismatch")
    if not input_summary["r228_packet_found"]:
        blocked_by.append("r228_packet_missing")
    elif not input_summary["r228_evidence_ready"]:
        blocked_by.append("r228_evidence_not_ready")
    if input_summary["r228_packet_found"] and not input_summary["r228_fisherman_ready"]:
        blocked_by.append("r228_fisherman_not_ready")
    if not input_summary["r230_risk_contract_config_found"]:
        blocked_by.append("r230_risk_contract_config_missing")
    if not input_summary["risk_contract_config_found"]:
        blocked_by.append("risk_contract_config_missing")
    if not contract_valid:
        blocked_by.append("risk_contract_invalid")
    if contract.get("live_authorized") is True:
        blocked_by.append("risk_contract_live_authorized_not_false")
    if not input_summary["r232_authorization_found"]:
        blocked_by.append("r232_authorization_missing")
    if input_summary["r232_authorization_found"] and not input_summary["r232_authorization_valid"]:
        blocked_by.extend(str(error) for error in auth_validation.get("errors") or ["r232_authorization_invalid"])
    if auth.get("live_authorized") is not True:
        blocked_by.append("live_authorized_not_true_in_authorization_artifact")
    if live_execution_enabled:
        blocked_by.append("live_execution_enabled_not_false")
    if lane_armed:
        blocked_by.append("lane_armed_not_false")
    if auth.get("order_payload_allowed") is not False:
        blocked_by.append("order_payload_allowed_not_false")
    if auth.get("binance_call_allowed") is not False:
        blocked_by.append("binance_call_allowed_not_false")
    if contract.get("order_payload_forbidden_until_live_gate") is not True:
        blocked_by.append("order_payload_not_forbidden_by_risk_contract")
    if contract.get("binance_call_forbidden_until_live_gate") is not True:
        blocked_by.append("binance_call_not_forbidden_by_risk_contract")
    if lane_control_state.get("kill_switch_disabled") is True:
        blocked_by.append("kill_switch_disabled")
    return {
        "input_summary": input_summary,
        "authorization_summary": _authorization_summary(auth),
        "risk_contract_summary": _risk_contract_summary(contract, official_lane_key=official_lane_key),
        "lane_control_state": dict(lane_control_state),
        "authorization_validation": auth_validation,
        "blocked_by": _dedupe(blocked_by),
    }


def build_live_execution_enable_requirement_preview(
    *,
    prerequisites: Mapping[str, Any],
    latest_r232: Mapping[str, Any],
    latest_r231: Mapping[str, Any],
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
    return {
        "execution_enable_preview_id": f"r233_live_execution_enable_preview_{symbol}_{timeframe}_{direction}_{entry_mode}_{uuid4().hex}",
        "preview_only": True,
        "generated_at": generated_at.isoformat(),
        "official_lane_key": official_lane_key,
        "evidence_packet_reference": latest_r228.get("packet_record_id") or latest_r228.get("generated_at"),
        "risk_contract_config_gate_reference": latest_r230.get("gate_record_id") or latest_r230.get("generated_at"),
        "risk_contract_reference": contract.get("contract_id"),
        "authorization_preview_reference": latest_r231.get("authorization_preview_record_id") or latest_r231.get("generated_at"),
        "authorization_reference": auth.get("authorization_id") or latest_r232.get("gate_record_id"),
        "future_execution_enable_required": True,
        "future_confirmation_required": True,
        "future_operator_final_approval_required": True,
        "future_lane_arm_required": True,
        "future_order_preflight_required": True,
        "future_binance_connectivity_check_required": True,
        "future_order_payload_still_forbidden_now": True,
        "future_suggested_confirmation_phrase": "I CONFIRM TINY LIVE EXECUTION ENABLE ONLY; NO ORDER; NO BINANCE CALL.",
        "notes": [
            "R233 creates no live execution enable flag and no executable payload.",
            "R232 authorization is necessary but is not live execution authority.",
            "A later R234-style write gate may be considered only after this preview is reviewed.",
            "Lane arming, order payload creation, and Binance/network calls remain forbidden now.",
            f"Remaining gates: {', '.join(prerequisites.get('blocked_by') or ['future_live_execution_enable_write_gate_required', 'future_lane_arm_required', 'future_order_preflight_required'])}.",
        ],
    }


def build_live_execution_enable_gate_matrix(prerequisites: Mapping[str, Any]) -> dict[str, Any]:
    input_summary = prerequisites.get("input_summary") if isinstance(prerequisites.get("input_summary"), Mapping) else {}
    blocked_by = list(prerequisites.get("blocked_by") or [])
    preview_ready = not blocked_by
    if preview_ready:
        blocked_by = [
            "future_live_execution_enable_write_gate_required",
            "future_lane_arm_required",
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
        "live_execution_enable_preview_ready": preview_ready,
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blocked_by),
    }


def build_operator_live_execution_enable_review_packet(live_execution_enable_gate_matrix: Mapping[str, Any]) -> dict[str, Any]:
    preview_ready = live_execution_enable_gate_matrix.get("live_execution_enable_preview_ready") is True
    if preview_ready:
        action = "REVIEW_R233_LIVE_EXECUTION_ENABLE_PREVIEW"
    elif live_execution_enable_gate_matrix.get("evidence_ready") and live_execution_enable_gate_matrix.get("risk_contract_config_ready"):
        action = "FIX_BLOCKER"
    else:
        action = "WAIT"
    return {
        "operator_should_review_live_execution_enable_preview": preview_ready,
        "operator_should_enable_live_now": False,
        "operator_should_arm_lane": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not enable live execution from this phase",
            "do not disable kill switch",
            "do not arm lane from this phase",
        ],
    }


def build_live_execution_enable_preview_recommendations(live_execution_enable_gate_matrix: Mapping[str, Any]) -> dict[str, str]:
    if live_execution_enable_gate_matrix.get("live_execution_enable_preview_ready"):
        return {
            "recommended_next_operator_move": "REVIEW_R233_LIVE_EXECUTION_ENABLE_PREVIEW",
            "recommended_next_engineering_move": "Create R234 guarded live execution enable write gate; still no Binance/network calls, orders, lane arming, or order payloads.",
        }
    if not live_execution_enable_gate_matrix.get("live_authorization_written"):
        return {
            "recommended_next_operator_move": "WAIT",
            "recommended_next_engineering_move": "Restore or write the R232 authorization artifact before any live execution enable preview can proceed.",
        }
    if not live_execution_enable_gate_matrix.get("risk_contract_config_ready"):
        return {
            "recommended_next_operator_move": "FIX_BLOCKER",
            "recommended_next_engineering_move": "Fix risk-contract config blockers before any live execution enable write gate.",
        }
    return {
        "recommended_next_operator_move": "FIX_BLOCKER",
        "recommended_next_engineering_move": "Fix R233 evidence, fisherman, authorization, or lane-control blockers before R234.",
    }


def classify_tiny_live_live_execution_enable_preview_status(
    *,
    prerequisites: Mapping[str, Any],
    gate_matrix: Mapping[str, Any],
) -> str:
    input_summary = prerequisites.get("input_summary") if isinstance(prerequisites.get("input_summary"), Mapping) else {}
    blocked_by = set(gate_matrix.get("blocked_by") or [])
    if gate_matrix.get("live_execution_enable_preview_ready"):
        return TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY_FOR_FUTURE_GATE
    if not input_summary.get("r232_authorization_found") or any("authorization" in str(item) for item in blocked_by):
        return TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_AUTHORIZATION
    if not input_summary.get("r228_packet_found") or "r228_evidence_not_ready" in blocked_by:
        return TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_EVIDENCE
    if "r228_fisherman_not_ready" in blocked_by:
        return TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_FISHERMAN
    if any("risk_contract" in str(item) or "r230" in str(item) for item in blocked_by):
        return TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_RISK_CONTRACT
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_live_execution_enable_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_live_execution_enable_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "execution_enable_preview_record_id": record.get("execution_enable_preview_record_id")
            or f"r233_live_execution_enable_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "execution_enable_preview_recorded": record.get("status")
            == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDED
            or record.get("execution_enable_preview_recorded") is True,
            "record_execution_enable_preview_requested": record.get("record_execution_enable_preview_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "authorization_summary": dict(record.get("authorization_summary") or {}),
            "risk_contract_summary": dict(record.get("risk_contract_summary") or {}),
            "live_execution_enable_requirement_preview": dict(
                record.get("live_execution_enable_requirement_preview") or {}
            ),
            "live_execution_enable_gate_matrix": dict(record.get("live_execution_enable_gate_matrix") or {}),
            "operator_live_execution_enable_review_packet": dict(
                record.get("operator_live_execution_enable_review_packet") or {}
            ),
            "live_execution_enable_preview_overall_status": record.get(
                "live_execution_enable_preview_overall_status"
            ),
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


def load_tiny_live_live_execution_enable_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_live_execution_enable_preview_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_tiny_live_live_execution_enable_preview_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_preview_recorded": latest.get("execution_enable_preview_recorded") is True,
        "latest_overall_status": latest.get("live_execution_enable_preview_overall_status"),
    }


def tiny_live_live_execution_enable_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_live_execution_enable_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _r228_ready(latest_r228: Mapping[str, Any], *, official_lane_key: str) -> dict[str, bool]:
    target = latest_r228.get("target_scope") if isinstance(latest_r228.get("target_scope"), Mapping) else {}
    gates = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    capture = latest_r228.get("capture_threshold_recheck") if isinstance(latest_r228.get("capture_threshold_recheck"), Mapping) else {}
    fisherman = latest_r228.get("fisherman_health_recheck") if isinstance(latest_r228.get("fisherman_health_recheck"), Mapping) else {}
    status_ok = latest_r228.get("status") in {TINY_LIVE_10_OF_10_READY_PACKET_READY, TINY_LIVE_10_OF_10_READY_PACKET_RECORDED}
    lane_ok = str(target.get("official_lane_key") or capture.get("official_lane_key") or "") == official_lane_key
    evidence_ready = gates.get("evidence_ready") is True or capture.get("evidence_threshold_ready") is True
    fisherman_ready = gates.get("fisherman_ready") is True or fisherman.get("fisherman_ready") is True
    return {
        "status_ok": bool(status_ok),
        "lane_ok": bool(lane_ok),
        "evidence_ready": bool(status_ok and lane_ok and evidence_ready),
        "fisherman_ready": bool(status_ok and lane_ok and fisherman_ready),
    }


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
    }


def _target_scope(lane_key: str, live_authorized: bool) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "live_execution_enable_preview_only": True,
        "live_authorized": bool(live_authorized),
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_payload_allowed": False,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r228_packet_found": False,
        "r228_evidence_ready": False,
        "r228_fisherman_ready": False,
        "r230_risk_contract_config_found": False,
        "risk_contract_config_found": False,
        "risk_contract_valid": False,
        "r232_authorization_found": False,
        "r232_authorization_valid": False,
        "live_authorized": False,
        "live_execution_enabled": False,
        "lane_armed": False,
    }


def _empty_authorization_summary() -> dict[str, Any]:
    return _authorization_summary({})


def _empty_risk_contract_summary(official_lane_key: str) -> dict[str, Any]:
    return _risk_contract_summary({}, official_lane_key=official_lane_key)


def _empty_prerequisites(official_lane_key: str, blocked_by: list[str] | None = None) -> dict[str, Any]:
    return {
        "input_summary": _empty_input_summary(),
        "authorization_summary": _empty_authorization_summary(),
        "risk_contract_summary": _empty_risk_contract_summary(official_lane_key),
        "lane_control_state": {"lane_armed": False, "kill_switch_disabled": False},
        "authorization_validation": {"valid": False, "errors": list(blocked_by or []), "warnings": []},
        "blocked_by": list(blocked_by or []),
    }


def _empty_gate_matrix(blockers: list[str] | None = None) -> dict[str, Any]:
    return {
        "evidence_ready": False,
        "fisherman_ready": False,
        "risk_contract_config_ready": False,
        "live_authorization_written": False,
        "live_authorized": False,
        "live_execution_enable_preview_ready": False,
        "live_execution_enabled": False,
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
