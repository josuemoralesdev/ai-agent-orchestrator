"""R238 tiny-live order preflight write gate.

This module appends a bounded local order-preflight artifact only when the
exact R238 confirmation phrase is supplied. It never creates order payloads,
signed requests, Binance/network calls, live orders, config writes, env writes,
or kill-switch changes.
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
from src.app.hammer_radar.operator.tiny_live_order_preflight_preview import (
    LEDGER_FILENAME as R237_LEDGER_FILENAME,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY_FOR_FUTURE_GATE,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDED,
    load_lane_controls_readonly,
    load_latest_tiny_live_lane_arm_write_gate,
    load_latest_tiny_live_live_authorization_write_gate,
    load_latest_tiny_live_live_execution_enable_write_gate,
    load_tiny_live_order_preflight_preview_records,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    LEDGER_FILENAME as R230_LEDGER_FILENAME,
    load_tiny_live_risk_contract_config_write_gate_records,
    validate_tiny_live_risk_contract_config_entry,
)

TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_READY = "TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_READY"
TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_REJECTED = "TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_REJECTED"
TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_WRITTEN = "TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_WRITTEN"
TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_BLOCKED = "TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_BLOCKED"
TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_ERROR = "TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_ERROR"

TINY_LIVE_ORDER_PREFLIGHT_WRITE_READY_FOR_CONFIRMATION = "TINY_LIVE_ORDER_PREFLIGHT_WRITE_READY_FOR_CONFIRMATION"
TINY_LIVE_ORDER_PREFLIGHT_WRITTEN_PAYLOAD_PREVIEW_REQUIRED_LATER = (
    "TINY_LIVE_ORDER_PREFLIGHT_WRITTEN_PAYLOAD_PREVIEW_REQUIRED_LATER"
)
TINY_LIVE_ORDER_PREFLIGHT_WRITE_REJECTED_BAD_CONFIRMATION = "TINY_LIVE_ORDER_PREFLIGHT_WRITE_REJECTED_BAD_CONFIRMATION"
TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_R237_PREVIEW = "TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_R237_PREVIEW"
TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_LANE_ARM = "TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_LANE_ARM"
TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_EXECUTION_ENABLE = (
    "TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_EXECUTION_ENABLE"
)
TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_AUTHORIZATION = (
    "TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_AUTHORIZATION"
)
TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_RISK_CONTRACT = (
    "TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_RISK_CONTRACT"
)
TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_VALIDATION = "TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_VALIDATION"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE"
LEDGER_FILENAME = "tiny_live_order_preflight_write_gate.ndjson"
CONFIRM_TINY_LIVE_ORDER_PREFLIGHT_WRITE_PHRASE = (
    "I CONFIRM TINY LIVE ORDER PREFLIGHT WRITE ONLY; "
    "NO ORDER PAYLOAD; NO ORDER; NO BINANCE CALL."
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
ORDER_PREFLIGHT_VERSION = "tiny_live_order_preflight_v1"
CREATED_BY_PHASE = "R238_TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE"

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
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
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
    "order_preflight_write_gate_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R237_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R236_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R234_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R232_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R230_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_order_preflight_write_gate(
    *,
    log_dir: str | Path | None = None,
    write_order_preflight: bool = False,
    confirm_tiny_live_order_preflight_write: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    confirmation_valid = confirm_tiny_live_order_preflight_write == CONFIRM_TINY_LIVE_ORDER_PREFLIGHT_WRITE_PHRASE
    try:
        latest_r237 = load_latest_tiny_live_order_preflight_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r236 = load_latest_tiny_live_lane_arm_write_gate(log_dir=resolved_log_dir, official_lane_key=official_lane_key)
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
        input_summary = _build_input_summary(
            latest_r237=latest_r237,
            latest_r236=latest_r236,
            latest_r234=latest_r234,
            latest_r232=latest_r232,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_config=risk_config,
            official_lane_key=official_lane_key,
        )
        proposed = build_order_preflight_object(
            latest_r237=latest_r237,
            latest_r236=latest_r236,
            latest_r234=latest_r234,
            latest_r232=latest_r232,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            input_summary=input_summary,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        validation = validate_order_preflight_object(proposed)
        blocked_by = _blocked_by(input_summary=input_summary, validation=validation, official_lane_key=official_lane_key)
        preview = build_order_preflight_write_preview(
            proposed_order_preflight=proposed,
            order_preflight_valid=validation["valid"],
            blocked_by=blocked_by,
            official_lane_key=official_lane_key,
        )
        can_write = write_order_preflight and confirmation_valid and not blocked_by

        if write_order_preflight and not confirmation_valid:
            written = False
            status = TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_REJECTED
            overall = TINY_LIVE_ORDER_PREFLIGHT_WRITE_REJECTED_BAD_CONFIRMATION
        elif can_write:
            write_order_preflight_if_confirmed(
                order_preflight=proposed,
                confirm_tiny_live_order_preflight_write=confirm_tiny_live_order_preflight_write,
                log_dir=resolved_log_dir,
            )
            written = True
            status = TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_WRITTEN
            overall = TINY_LIVE_ORDER_PREFLIGHT_WRITTEN_PAYLOAD_PREVIEW_REQUIRED_LATER
        else:
            written = False
            status, overall = _ready_or_blocked_status(input_summary=input_summary, validation=validation)

        post_write = build_post_write_order_preflight_verification(
            order_preflight=proposed,
            order_preflight_written=written,
            log_dir=resolved_log_dir,
        )
        matrix = build_order_preflight_write_gate_matrix(
            r237_preview_ready=input_summary["r237_preview_ready"],
            risk_contract_config_ready=input_summary["risk_contract_valid"],
            authorization_valid=input_summary["r232_authorization_valid"],
            execution_enable_valid=input_summary["r234_execution_enable_valid"],
            lane_arm_valid=input_summary["r236_lane_arm_valid"],
            order_preflight_valid=validation["valid"],
            order_preflight_write_confirmed=write_order_preflight and confirmation_valid,
            order_preflight_written=written,
            live_authorized=input_summary["live_authorized"],
            live_execution_enabled=input_summary["live_execution_enabled"],
            lane_armed=input_summary["lane_armed"],
            blocked_by=blocked_by,
        )
        operator_packet = build_operator_order_preflight_write_review_packet(
            matrix,
            write_requested=write_order_preflight,
        )
        safety = dict(SAFETY)
        if written:
            safety["order_preflight_written"] = True
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "order_preflight_written": written,
            "write_order_preflight_requested": bool(write_order_preflight),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(
                official_lane_key,
                live_authorized=input_summary["live_authorized"],
                live_execution_enabled=input_summary["live_execution_enabled"],
                lane_armed=input_summary["lane_armed"],
            ),
            "input_summary": input_summary,
            "lane_controls_readonly_summary": lane_controls,
            "order_preflight_write_preview": preview,
            "order_preflight_validation": validation,
            "post_write_verification": post_write,
            "order_preflight_write_gate_matrix": matrix,
            "operator_order_preflight_write_review_packet": operator_packet,
            "recommended_next_operator_move": _recommended_next_operator_move(matrix, write_requested=write_order_preflight),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
            "order_preflight_write_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_order_preflight_write_gate_matrix(
            r237_preview_ready=False,
            risk_contract_config_ready=False,
            authorization_valid=False,
            execution_enable_valid=False,
            lane_arm_valid=False,
            order_preflight_valid=False,
            order_preflight_write_confirmed=False,
            order_preflight_written=False,
            live_authorized=False,
            live_execution_enabled=False,
            lane_armed=False,
            blocked_by=["order_preflight_write_gate_error"],
        )
        return _sanitize(
            {
                "status": TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "order_preflight_written": False,
                "write_order_preflight_requested": bool(write_order_preflight),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(
                    official_lane_key,
                    live_authorized=False,
                    live_execution_enabled=False,
                    lane_armed=False,
                ),
                "input_summary": _empty_input_summary(),
                "order_preflight_write_preview": _empty_order_preflight_write_preview(official_lane_key),
                "order_preflight_validation": {"valid": False, "errors": ["order_preflight_write_gate_error"], "warnings": []},
                "post_write_verification": _empty_post_write_verification(),
                "order_preflight_write_gate_matrix": matrix,
                "operator_order_preflight_write_review_packet": build_operator_order_preflight_write_review_packet(
                    matrix,
                    write_requested=write_order_preflight,
                ),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R238 order-preflight write-gate error before order-payload preview.",
                "order_preflight_write_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_order_preflight_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_order_preflight_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        matrix = record.get("order_preflight_gate_matrix") if isinstance(record.get("order_preflight_gate_matrix"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or "") == official_lane_key
            and record.get("status") in {TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY, TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDED}
            and record.get("order_preflight_preview_overall_status")
            == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY_FOR_FUTURE_GATE
            and matrix.get("order_preflight_preview_ready") is True
            and record.get("order_preflight_preview_recorded") is True
        ):
            return _sanitize({**record, "r237_preview_found": True})
    return {}


def build_order_preflight_object(
    *,
    latest_r237: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    latest_r234: Mapping[str, Any],
    latest_r232: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    input_summary: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    preview = (
        latest_r237.get("order_preflight_requirement_preview")
        if isinstance(latest_r237.get("order_preflight_requirement_preview"), Mapping)
        else {}
    )
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    execution_enable = latest_r234.get("execution_enable") if isinstance(latest_r234.get("execution_enable"), Mapping) else {}
    auth = latest_r232.get("authorization") if isinstance(latest_r232.get("authorization"), Mapping) else {}
    return {
        "order_preflight_id": "r238_order_preflight_BTCUSDT_8m_short_ladder_close_50_618",
        "order_preflight_version": ORDER_PREFLIGHT_VERSION,
        "created_by_phase": CREATED_BY_PHASE,
        "created_at": generated_at.isoformat(),
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "source_order_preflight_preview_id": latest_r237.get("order_preflight_preview_record_id")
        or preview.get("order_preflight_preview_id"),
        "source_lane_arm_id": lane_arm.get("lane_arm_id") or latest_r236.get("gate_record_id"),
        "source_execution_enable_id": execution_enable.get("execution_enable_id") or latest_r234.get("gate_record_id"),
        "source_authorization_id": auth.get("authorization_id") or latest_r232.get("gate_record_id"),
        "source_risk_contract_id": "r230_contract_BTCUSDT_8m_short_ladder_close_50_618",
        "risk_contract_config_ready": input_summary.get("risk_contract_valid") is True,
        "evidence_ready": input_summary.get("r228_evidence_ready") is True,
        "fisherman_ready": input_summary.get("fisherman_ready") is True,
        "live_authorized": input_summary.get("live_authorized") is True,
        "live_execution_enabled": input_summary.get("live_execution_enabled") is True,
        "lane_armed": input_summary.get("lane_armed") is True,
        "order_preflight_scope": "tiny_live_single_lane",
        "order_preflight_status": "PREFLIGHT_WRITTEN_NO_PAYLOAD_NO_ORDER",
        "order_preflight_written": True,
        "order_payload_allowed": False,
        "order_payload_created": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "kill_switch_required": True,
        "kill_switch_disabled": False,
        "operator_final_approval_required": True,
        "order_payload_preview_required_later": True,
        "binance_connectivity_check_required_later": True,
        "notes": [
            "R238 writes order-preflight artifact only; it does not create an order payload.",
            "Order payload creation, signed requests, order placement, and Binance/network calls remain forbidden.",
            "A later phase must separately preview order payload creation.",
        ],
    }


def validate_order_preflight_object(order_preflight: Mapping[str, Any]) -> dict[str, Any]:
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
        "lane_armed": True,
        "order_preflight_written": True,
        "order_payload_allowed": False,
        "order_payload_created": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "kill_switch_required": True,
        "kill_switch_disabled": False,
        "operator_final_approval_required": True,
        "order_payload_preview_required_later": True,
        "binance_connectivity_check_required_later": True,
    }
    for key, value in expected.items():
        if order_preflight.get(key) is not value and order_preflight.get(key) != value:
            errors.append(f"{key}_invalid")
    if order_preflight.get("order_preflight_id") != "r238_order_preflight_BTCUSDT_8m_short_ladder_close_50_618":
        errors.append("order_preflight_id_invalid")
    if order_preflight.get("order_preflight_version") != ORDER_PREFLIGHT_VERSION:
        errors.append("order_preflight_version_invalid")
    if order_preflight.get("created_by_phase") != CREATED_BY_PHASE:
        errors.append("created_by_phase_invalid")
    if order_preflight.get("order_preflight_status") != "PREFLIGHT_WRITTEN_NO_PAYLOAD_NO_ORDER":
        errors.append("order_preflight_status_invalid")
    if not order_preflight.get("source_order_preflight_preview_id"):
        errors.append("source_order_preflight_preview_id_missing")
    if order_preflight.get("source_lane_arm_id") != "r236_lane_arm_BTCUSDT_8m_short_ladder_close_50_618":
        errors.append("source_lane_arm_id_invalid")
    if order_preflight.get("source_execution_enable_id") != "r234_execution_enable_BTCUSDT_8m_short_ladder_close_50_618":
        errors.append("source_execution_enable_id_invalid")
    if order_preflight.get("source_authorization_id") != "r232_authorization_BTCUSDT_8m_short_ladder_close_50_618":
        errors.append("source_authorization_id_invalid")
    if order_preflight.get("source_risk_contract_id") != "r230_contract_BTCUSDT_8m_short_ladder_close_50_618":
        errors.append("source_risk_contract_id_invalid")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def build_order_preflight_write_preview(
    *,
    proposed_order_preflight: Mapping[str, Any],
    order_preflight_valid: bool,
    blocked_by: Sequence[str] | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return {
        "would_write": bool(order_preflight_valid and not blocked_by),
        "write_requires_confirmation": True,
        "target_order_preflight_key": official_lane_key,
        "bounded_mutation_only": True,
        "order_preflight_artifact": "ledger_only",
        "proposed_order_preflight": _sanitize(dict(proposed_order_preflight)),
    }


def write_order_preflight_if_confirmed(
    *,
    order_preflight: Mapping[str, Any],
    confirm_tiny_live_order_preflight_write: str | None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_order_preflight_write != CONFIRM_TINY_LIVE_ORDER_PREFLIGHT_WRITE_PHRASE:
        return {"written": False, "reason": "bad_confirmation"}
    validation = validate_order_preflight_object(order_preflight)
    if not validation["valid"]:
        return {"written": False, "reason": "validation_failed", "validation": validation}
    record = append_tiny_live_order_preflight_write_gate_record(
        {
            "status": TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_WRITTEN,
            "generated_at": order_preflight.get("created_at"),
            "order_preflight_written": True,
            "write_order_preflight_requested": True,
            "confirmation_valid": True,
            "target_scope": _target_scope(
                str(order_preflight.get("official_lane_key") or OFFICIAL_LANE_KEY),
                live_authorized=True,
                live_execution_enabled=True,
                lane_armed=True,
            ),
            "order_preflight": dict(order_preflight),
            "order_preflight_validation": validation,
            "safety": {**SAFETY, "order_preflight_written": True},
        },
        log_dir=log_dir,
    )
    return {"written": True, "record": record}


def build_post_write_order_preflight_verification(
    *,
    order_preflight: Mapping[str, Any],
    order_preflight_written: bool,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_tiny_live_order_preflight_write_gate_records(log_dir=log_dir, limit=50) if order_preflight_written else []
    matching = _matching_order_preflight_record(records, order_preflight)
    artifact = matching.get("order_preflight") if isinstance(matching.get("order_preflight"), Mapping) else {}
    validation = validate_order_preflight_object(artifact)
    return {
        "order_preflight_written": bool(order_preflight_written),
        "matching_order_preflight_found": bool(matching),
        "matching_order_preflight_valid": bool(matching and validation["valid"]),
        "live_authorized": bool(matching and artifact.get("live_authorized") is True),
        "live_execution_enabled": bool(matching and artifact.get("live_execution_enabled") is True),
        "lane_armed": bool(matching and artifact.get("lane_armed") is True),
        "order_payload_allowed": False,
        "order_payload_created": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "kill_switch_disabled": False,
    }


def build_order_preflight_write_gate_matrix(
    *,
    r237_preview_ready: bool,
    risk_contract_config_ready: bool,
    authorization_valid: bool,
    execution_enable_valid: bool,
    lane_arm_valid: bool,
    order_preflight_valid: bool,
    order_preflight_write_confirmed: bool,
    order_preflight_written: bool,
    live_authorized: bool,
    live_execution_enabled: bool,
    lane_armed: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if not r237_preview_ready:
        blockers.append("r237_preview_not_ready")
    if not risk_contract_config_ready:
        blockers.append("risk_contract_config_not_ready")
    if not authorization_valid:
        blockers.append("authorization_invalid")
    if not execution_enable_valid:
        blockers.append("execution_enable_invalid")
    if not lane_arm_valid:
        blockers.append("lane_arm_invalid")
    if not order_preflight_valid:
        blockers.append("order_preflight_invalid")
    if not order_preflight_write_confirmed:
        blockers.append("exact_order_preflight_write_confirmation_required")
    if order_preflight_written:
        blockers = ["order_payload_preview_required_later", "order_payload_forbidden", "kill_switch_still_active"]
    return {
        "r237_preview_ready": bool(r237_preview_ready),
        "risk_contract_config_ready": bool(risk_contract_config_ready),
        "authorization_valid": bool(authorization_valid),
        "execution_enable_valid": bool(execution_enable_valid),
        "lane_arm_valid": bool(lane_arm_valid),
        "order_preflight_valid": bool(order_preflight_valid),
        "order_preflight_write_confirmed": bool(order_preflight_write_confirmed),
        "order_preflight_written": bool(order_preflight_written),
        "live_authorized": bool(live_authorized),
        "live_execution_enabled": bool(live_execution_enabled),
        "lane_armed": bool(lane_armed),
        "order_payload_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_order_preflight_write_review_packet(
    order_preflight_write_gate_matrix: Mapping[str, Any],
    *,
    write_requested: bool = False,
) -> dict[str, Any]:
    written = order_preflight_write_gate_matrix.get("order_preflight_written") is True
    ready = (
        order_preflight_write_gate_matrix.get("r237_preview_ready") is True
        and order_preflight_write_gate_matrix.get("risk_contract_config_ready") is True
        and order_preflight_write_gate_matrix.get("authorization_valid") is True
        and order_preflight_write_gate_matrix.get("execution_enable_valid") is True
        and order_preflight_write_gate_matrix.get("lane_arm_valid") is True
        and order_preflight_write_gate_matrix.get("order_preflight_valid") is True
        and not written
    )
    if written:
        action = "REVIEW_R238_RESULT"
    elif ready:
        action = "CONFIRM_R238_ORDER_PREFLIGHT_WRITE"
    else:
        action = "WAIT"
    return {
        "operator_should_review_order_preflight_write": bool(ready or written or write_requested),
        "operator_confirmation_required": True,
        "operator_should_create_order_payload": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not create order payload",
            "do not disable kill switch",
            "do not call Binance from this phase",
        ],
    }


def classify_tiny_live_order_preflight_write_status(payload: Mapping[str, Any]) -> str:
    return str(payload.get("order_preflight_write_overall_status") or UNKNOWN_NEEDS_MANUAL_REVIEW)


def append_tiny_live_order_preflight_write_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_order_preflight_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "gate_record_id": record.get("gate_record_id") or f"r238_order_preflight_write_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "order_preflight_written": record.get("order_preflight_written") is True,
            "write_order_preflight_requested": record.get("write_order_preflight_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "order_preflight": dict(record.get("order_preflight") or {}),
            "order_preflight_validation": dict(record.get("order_preflight_validation") or {}),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_order_preflight_write_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_order_preflight_write_gate_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_tiny_live_order_preflight_write_gate_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_order_preflight_written": latest.get("order_preflight_written") is True,
        "latest_order_preflight_id": (latest.get("order_preflight") or {}).get("order_preflight_id")
        if isinstance(latest.get("order_preflight"), Mapping)
        else None,
    }


def tiny_live_order_preflight_write_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_order_preflight_write_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r237: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    latest_r234: Mapping[str, Any],
    latest_r232: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_config: Mapping[str, Any],
    official_lane_key: str,
) -> dict[str, Any]:
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    execution_enable = latest_r234.get("execution_enable") if isinstance(latest_r234.get("execution_enable"), Mapping) else {}
    auth = latest_r232.get("authorization") if isinstance(latest_r232.get("authorization"), Mapping) else {}
    risk_contract = (
        risk_config.get("matching_risk_contract") if isinstance(risk_config.get("matching_risk_contract"), Mapping) else {}
    )
    preview_matrix = latest_r237.get("order_preflight_gate_matrix") if isinstance(latest_r237.get("order_preflight_gate_matrix"), Mapping) else {}
    r228_matrix = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    lane_arm_validation = validate_lane_arm_object(lane_arm) if lane_arm else {"valid": False}
    execution_validation = validate_live_execution_enable_object(execution_enable) if execution_enable else {"valid": False}
    auth_validation = validate_live_authorization_object(auth) if auth else {"valid": False}
    risk_validation = (
        validate_tiny_live_risk_contract_config_entry(risk_contract)
        if risk_contract
        else {"valid": False}
    )
    return {
        "r237_preview_found": bool(latest_r237),
        "r237_preview_ready": _r237_preview_ready(latest_r237, official_lane_key=official_lane_key),
        "r236_lane_arm_found": bool(latest_r236),
        "r236_lane_arm_valid": lane_arm_validation.get("valid") is True,
        "r234_execution_enable_found": bool(latest_r234),
        "r234_execution_enable_valid": execution_validation.get("valid") is True,
        "r232_authorization_found": bool(latest_r232),
        "r232_authorization_valid": auth_validation.get("valid") is True,
        "r230_risk_contract_config_found": bool(latest_r230) and bool(risk_contract),
        "risk_contract_valid": risk_validation.get("valid") is True,
        "r228_evidence_ready": r228_matrix.get("evidence_ready") is True or preview_matrix.get("evidence_ready") is True,
        "fisherman_ready": r228_matrix.get("fisherman_ready") is True or preview_matrix.get("fisherman_ready") is True,
        "live_authorized": auth.get("live_authorized") is True
        and execution_enable.get("live_authorized") is True
        and lane_arm.get("live_authorized") is True,
        "live_execution_enabled": execution_enable.get("live_execution_enabled") is True
        and lane_arm.get("live_execution_enabled") is True,
        "lane_armed": lane_arm.get("lane_armed") is True,
        "order_payload_created": False,
    }


def _blocked_by(
    *,
    input_summary: Mapping[str, Any],
    validation: Mapping[str, Any],
    official_lane_key: str,
) -> list[str]:
    blockers: list[str] = []
    if official_lane_key != OFFICIAL_LANE_KEY:
        blockers.append("official_lane_mismatch")
    if not input_summary.get("r237_preview_ready"):
        blockers.append("r237_preview_not_ready")
    if not input_summary.get("r236_lane_arm_valid") or not input_summary.get("lane_armed"):
        blockers.append("lane_arm_not_ready")
    if not input_summary.get("r234_execution_enable_valid") or not input_summary.get("live_execution_enabled"):
        blockers.append("execution_enable_not_ready")
    if not input_summary.get("r232_authorization_valid") or not input_summary.get("live_authorized"):
        blockers.append("authorization_not_ready")
    if not input_summary.get("risk_contract_valid"):
        blockers.append("risk_contract_config_not_ready")
    if not input_summary.get("r228_evidence_ready"):
        blockers.append("r228_evidence_not_ready")
    if not input_summary.get("fisherman_ready"):
        blockers.append("fisherman_not_ready")
    if not validation.get("valid"):
        blockers.extend(str(error) for error in validation.get("errors") or ["order_preflight_invalid"])
    return _dedupe(blockers)


def _ready_or_blocked_status(
    *,
    input_summary: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> tuple[str, str]:
    if not input_summary.get("r237_preview_ready"):
        return TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_BLOCKED, TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_R237_PREVIEW
    if not input_summary.get("r236_lane_arm_valid") or not input_summary.get("lane_armed"):
        return TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_BLOCKED, TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_LANE_ARM
    if not input_summary.get("r234_execution_enable_valid") or not input_summary.get("live_execution_enabled"):
        return TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_BLOCKED, TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_EXECUTION_ENABLE
    if not input_summary.get("r232_authorization_valid") or not input_summary.get("live_authorized"):
        return TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_BLOCKED, TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_AUTHORIZATION
    if not input_summary.get("risk_contract_valid"):
        return TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_BLOCKED, TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_RISK_CONTRACT
    if not validation.get("valid"):
        return TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_BLOCKED, TINY_LIVE_ORDER_PREFLIGHT_WRITE_BLOCKED_BY_VALIDATION
    return TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_READY, TINY_LIVE_ORDER_PREFLIGHT_WRITE_READY_FOR_CONFIRMATION


def _recommended_next_operator_move(matrix: Mapping[str, Any], *, write_requested: bool) -> str:
    if matrix.get("order_preflight_written"):
        return "REVIEW_R238_RESULT"
    if (
        matrix.get("r237_preview_ready")
        and matrix.get("risk_contract_config_ready")
        and matrix.get("authorization_valid")
        and matrix.get("execution_enable_valid")
        and matrix.get("lane_arm_valid")
        and matrix.get("order_preflight_valid")
    ):
        return "CONFIRM_R238_ORDER_PREFLIGHT_WRITE"
    return "WAIT" if not write_requested else "REVIEW_BLOCKED_R238_ORDER_PREFLIGHT_WRITE"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("order_preflight_written"):
        return "Create R239 tiny-live order-payload preview; still no Binance/network calls, orders, executable payloads, signed requests, or kill-switch disable."
    if matrix.get("order_preflight_valid"):
        return "Await exact R238 confirmation before appending the order-preflight artifact."
    return "Fix R238 prerequisites before any order-preflight artifact write."


def _r237_preview_ready(latest_r237: Mapping[str, Any], *, official_lane_key: str) -> bool:
    target = latest_r237.get("target_scope") if isinstance(latest_r237.get("target_scope"), Mapping) else {}
    matrix = latest_r237.get("order_preflight_gate_matrix") if isinstance(latest_r237.get("order_preflight_gate_matrix"), Mapping) else {}
    return (
        bool(latest_r237)
        and str(target.get("official_lane_key") or "") == official_lane_key
        and latest_r237.get("status") in {TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY, TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDED}
        and latest_r237.get("order_preflight_preview_overall_status")
        == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY_FOR_FUTURE_GATE
        and matrix.get("order_preflight_preview_ready") is True
        and matrix.get("order_payload_created") is False
    )


def _matching_order_preflight_record(records: Sequence[Mapping[str, Any]], order_preflight: Mapping[str, Any]) -> dict[str, Any]:
    expected_id = order_preflight.get("order_preflight_id")
    for record in records:
        artifact = record.get("order_preflight") if isinstance(record.get("order_preflight"), Mapping) else {}
        if artifact.get("order_preflight_id") == expected_id and record.get("order_preflight_written") is True:
            return _sanitize(record)
    return {}


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
        "order_preflight_write_gate_only": True,
        "live_authorized": bool(live_authorized),
        "live_execution_enabled": bool(live_execution_enabled),
        "lane_armed": bool(lane_armed),
        "order_payload_allowed": False,
        "order_payload_created": False,
        "kill_switch_disabled": False,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r237_preview_found": False,
        "r237_preview_ready": False,
        "r236_lane_arm_found": False,
        "r236_lane_arm_valid": False,
        "r234_execution_enable_found": False,
        "r234_execution_enable_valid": False,
        "r232_authorization_found": False,
        "r232_authorization_valid": False,
        "r230_risk_contract_config_found": False,
        "risk_contract_valid": False,
        "r228_evidence_ready": False,
        "fisherman_ready": False,
        "live_authorized": False,
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_payload_created": False,
    }


def _empty_order_preflight_write_preview(official_lane_key: str) -> dict[str, Any]:
    return {
        "would_write": False,
        "write_requires_confirmation": True,
        "target_order_preflight_key": official_lane_key,
        "bounded_mutation_only": True,
        "order_preflight_artifact": "ledger_only",
        "proposed_order_preflight": {},
    }


def _empty_post_write_verification() -> dict[str, Any]:
    return {
        "order_preflight_written": False,
        "matching_order_preflight_found": False,
        "matching_order_preflight_valid": False,
        "live_authorized": False,
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_payload_allowed": False,
        "order_payload_created": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "kill_switch_disabled": False,
    }


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "order payload creation",
        "signed order request",
        "signed trading request",
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
