"""R240 tiny-live order payload write gate.

This module writes only a local, non-executable order payload artifact after
the exact R240 confirmation phrase. It never creates executable payloads,
signs requests, calls Binance/network endpoints, places orders, mutates
configs/env, or disables the kill switch.
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
    validate_lane_arm_object,
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_preview import LANE_CONTROLS_PATH
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    LEDGER_FILENAME as R232_LEDGER_FILENAME,
    load_latest_tiny_live_10_of_10_ready_packet,
    load_latest_tiny_live_risk_contract_config_write_gate,
    load_tiny_live_risk_contract_config,
    validate_live_authorization_object,
)
from src.app.hammer_radar.operator.tiny_live_live_execution_enable_write_gate import (
    LEDGER_FILENAME as R234_LEDGER_FILENAME,
    validate_live_execution_enable_object,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_preview import (
    LEDGER_FILENAME as R239_LEDGER_FILENAME,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY_FOR_FUTURE_GATE,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDED,
    load_tiny_live_order_payload_preview_records,
    validate_order_payload_preview,
)
from src.app.hammer_radar.operator.tiny_live_order_preflight_preview import (
    load_lane_controls_readonly,
    load_latest_tiny_live_lane_arm_write_gate,
    load_latest_tiny_live_live_authorization_write_gate,
    load_latest_tiny_live_live_execution_enable_write_gate,
)
from src.app.hammer_radar.operator.tiny_live_order_preflight_write_gate import (
    LEDGER_FILENAME as R238_LEDGER_FILENAME,
    load_latest_tiny_live_order_preflight_preview,
    load_tiny_live_order_preflight_write_gate_records,
    validate_order_preflight_object,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    LEDGER_FILENAME as R230_LEDGER_FILENAME,
    validate_tiny_live_risk_contract_config_entry,
)

TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_READY = "TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_READY"
TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_REJECTED = "TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_REJECTED"
TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_WRITTEN = "TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_WRITTEN"
TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_BLOCKED = "TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_BLOCKED"
TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_ERROR = "TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_ERROR"

TINY_LIVE_ORDER_PAYLOAD_WRITE_READY_FOR_CONFIRMATION = "TINY_LIVE_ORDER_PAYLOAD_WRITE_READY_FOR_CONFIRMATION"
TINY_LIVE_ORDER_PAYLOAD_WRITTEN_PRECISION_AND_CONNECTIVITY_REQUIRED_LATER = (
    "TINY_LIVE_ORDER_PAYLOAD_WRITTEN_PRECISION_AND_CONNECTIVITY_REQUIRED_LATER"
)
TINY_LIVE_ORDER_PAYLOAD_WRITE_REJECTED_BAD_CONFIRMATION = "TINY_LIVE_ORDER_PAYLOAD_WRITE_REJECTED_BAD_CONFIRMATION"
TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_R239_PREVIEW = "TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_R239_PREVIEW"
TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_PREFLIGHT = "TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_PREFLIGHT"
TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_LANE_ARM = "TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_LANE_ARM"
TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_RISK_CONTRACT = "TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_RISK_CONTRACT"
TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_VALIDATION = "TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_VALIDATION"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE"
LEDGER_FILENAME = "tiny_live_order_payload_write_gate.ndjson"
CONFIRM_TINY_LIVE_ORDER_PAYLOAD_WRITE_PHRASE = (
    "I CONFIRM TINY LIVE ORDER PAYLOAD WRITE GATE ONLY; "
    "NON-EXECUTABLE PAYLOAD ARTIFACT ONLY; NO ORDER; NO BINANCE CALL."
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
ORDER_PAYLOAD_VERSION = "tiny_live_non_executable_order_payload_v1"
CREATED_BY_PHASE = "R240_TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE"

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "order_payload_written": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "submit_allowed": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "binance_account_endpoint_called": False,
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "kill_switch_disabled": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
    "order_payload_write_gate_only": True,
    "non_executable_artifact_only": True,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R239_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R238_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R236_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R234_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R232_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R230_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_order_payload_write_gate(
    *,
    log_dir: str | Path | None = None,
    write_order_payload: bool = False,
    confirm_tiny_live_order_payload_write: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    confirmation_valid = confirm_tiny_live_order_payload_write == CONFIRM_TINY_LIVE_ORDER_PAYLOAD_WRITE_PHRASE
    try:
        latest_r239 = load_latest_tiny_live_order_payload_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r238 = load_latest_tiny_live_order_preflight_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r236 = load_latest_tiny_live_lane_arm_write_gate(
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
        input_summary = _build_input_summary(
            latest_r239=latest_r239,
            latest_r238=latest_r238,
            latest_r236=latest_r236,
            latest_r234=latest_r234,
            latest_r232=latest_r232,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_config=risk_config,
        )
        proposed = build_non_executable_order_payload_artifact(
            latest_r239=latest_r239,
            latest_r238=latest_r238,
            latest_r236=latest_r236,
            risk_config=risk_config,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        validation = validate_non_executable_order_payload_artifact(proposed)
        blocked_by = _blocked_by(input_summary=input_summary, validation=validation, official_lane_key=official_lane_key)
        preview = build_order_payload_write_preview(
            proposed_order_payload=proposed,
            order_payload_valid=validation["valid"],
            blocked_by=blocked_by,
            official_lane_key=official_lane_key,
        )
        can_write = write_order_payload and confirmation_valid and not blocked_by

        if write_order_payload and not confirmation_valid:
            written = False
            status = TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_REJECTED
            overall = TINY_LIVE_ORDER_PAYLOAD_WRITE_REJECTED_BAD_CONFIRMATION
        elif can_write:
            write_order_payload_if_confirmed(
                order_payload=proposed,
                confirm_tiny_live_order_payload_write=confirm_tiny_live_order_payload_write,
                log_dir=resolved_log_dir,
            )
            written = True
            status = TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_WRITTEN
            overall = TINY_LIVE_ORDER_PAYLOAD_WRITTEN_PRECISION_AND_CONNECTIVITY_REQUIRED_LATER
        else:
            written = False
            status, overall = _ready_or_blocked_status(input_summary=input_summary, validation=validation)

        post_write = build_post_write_order_payload_verification(
            order_payload=proposed,
            order_payload_written=written,
            log_dir=resolved_log_dir,
        )
        matrix = build_order_payload_write_gate_matrix(
            r239_payload_preview_ready=input_summary["r239_payload_preview_ready"],
            order_preflight_valid=input_summary["r238_order_preflight_valid"],
            lane_arm_valid=input_summary["r236_lane_arm_valid"],
            order_payload_valid=validation["valid"],
            order_payload_write_confirmed=write_order_payload and confirmation_valid,
            order_payload_written=written,
            order_payload_created=written,
            blocked_by=blocked_by,
        )
        operator_packet = build_operator_order_payload_write_review_packet(
            matrix,
            write_requested=write_order_payload,
        )
        safety = dict(SAFETY)
        if written:
            safety["order_payload_written"] = True
            safety["order_payload_created"] = True
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "order_payload_written": written,
            "write_order_payload_requested": bool(write_order_payload),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(official_lane_key),
            "input_summary": input_summary,
            "lane_controls_readonly_summary": lane_controls,
            "order_payload_write_preview": preview,
            "order_payload_validation": validation,
            "post_write_verification": post_write,
            "order_payload_write_gate_matrix": matrix,
            "operator_order_payload_write_review_packet": operator_packet,
            "recommended_next_operator_move": _recommended_next_operator_move(matrix, write_requested=write_order_payload),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
            "order_payload_write_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_order_payload_write_gate_matrix(
            r239_payload_preview_ready=False,
            order_preflight_valid=False,
            lane_arm_valid=False,
            order_payload_valid=False,
            order_payload_write_confirmed=False,
            order_payload_written=False,
            order_payload_created=False,
            blocked_by=["order_payload_write_gate_error"],
        )
        return _sanitize(
            {
                "status": TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "order_payload_written": False,
                "write_order_payload_requested": bool(write_order_payload),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(official_lane_key),
                "input_summary": _empty_input_summary(),
                "order_payload_write_preview": _empty_order_payload_write_preview(official_lane_key),
                "order_payload_validation": {
                    "valid": False,
                    "errors": ["order_payload_write_gate_error"],
                    "warnings": [],
                },
                "post_write_verification": _empty_post_write_verification(),
                "order_payload_write_gate_matrix": matrix,
                "operator_order_payload_write_review_packet": build_operator_order_payload_write_review_packet(
                    matrix,
                    write_requested=write_order_payload,
                ),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R240 order-payload write-gate error before precision/connectivity preview.",
                "order_payload_write_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_order_payload_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_order_payload_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        preview = (
            record.get("non_executable_order_payload_preview")
            if isinstance(record.get("non_executable_order_payload_preview"), Mapping)
            else {}
        )
        matrix = record.get("order_payload_preview_gate_matrix") if isinstance(record.get("order_payload_preview_gate_matrix"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or preview.get("official_lane_key") or "") == official_lane_key
            and record.get("status") in {TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY, TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDED}
            and record.get("order_payload_preview_overall_status")
            == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY_FOR_FUTURE_GATE
            and matrix.get("order_payload_preview_ready") is True
            and record.get("order_payload_preview_recorded") is True
            and validate_order_payload_preview(preview).get("valid") is True
        ):
            return _sanitize({**record, "r239_payload_preview_found": True})
    return {}


def load_latest_tiny_live_order_preflight_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_order_preflight_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        artifact = record.get("order_preflight") if isinstance(record.get("order_preflight"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or artifact.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == "TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_WRITTEN"
            and record.get("order_preflight_written") is True
            and validate_order_preflight_object(artifact).get("valid") is True
        ):
            return _sanitize({**record, "r238_order_preflight_found": True})
    return {}


def build_non_executable_order_payload_artifact(
    *,
    latest_r239: Mapping[str, Any],
    latest_r238: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    risk_config: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    preview = (
        latest_r239.get("non_executable_order_payload_preview")
        if isinstance(latest_r239.get("non_executable_order_payload_preview"), Mapping)
        else {}
    )
    order_preflight = latest_r238.get("order_preflight") if isinstance(latest_r238.get("order_preflight"), Mapping) else {}
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    contract = risk_config.get("matching_risk_contract") if isinstance(risk_config.get("matching_risk_contract"), Mapping) else {}
    notional = min(_float_or_default(preview.get("notional_cap_usdt") or contract.get("max_notional_usdt"), 44.0), 44.0)
    max_loss = min(_float_or_default(preview.get("max_loss_usdt") or contract.get("max_loss_usdt"), 4.44), 4.44)
    leverage = int(preview.get("leverage") or contract.get("leverage") or 1)
    return {
        "order_payload_id": "r240_order_payload_BTCUSDT_8m_short_ladder_close_50_618",
        "order_payload_version": ORDER_PAYLOAD_VERSION,
        "created_by_phase": CREATED_BY_PHASE,
        "created_at": generated_at.isoformat(),
        "official_lane_key": official_lane_key,
        "exchange": "binance_futures",
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "side": "SELL",
        "position_side": "BOTH|SHORT|null",
        "order_type": "MARKET_PREVIEW_ONLY",
        "time_in_force": None,
        "quantity": None,
        "quantity_source": "requires_precision_and_mark_price_later",
        "notional_cap_usdt": int(notional) if notional.is_integer() else notional,
        "max_loss_usdt": max_loss,
        "leverage": leverage,
        "reduce_only": False,
        "stop_required": True,
        "take_profit_required": True,
        "stop_payload": {
            "preview_only": True,
            "executable": False,
            "signed": False,
            "order_type": "STOP_MARKET_PREVIEW_ONLY",
            "side": "BUY",
            "reduce_only": True,
            "stop_price": None,
            "requires_future_price_precision": True,
        },
        "take_profit_payload": {
            "preview_only": True,
            "executable": False,
            "signed": False,
            "order_type": "TAKE_PROFIT_MARKET_PREVIEW_ONLY",
            "side": "BUY",
            "reduce_only": True,
            "take_profit_price": None,
            "requires_future_price_precision": True,
        },
        "source_order_payload_preview_id": latest_r239.get("order_payload_preview_record_id")
        or preview.get("order_payload_preview_id"),
        "source_order_preflight_id": order_preflight.get("order_preflight_id"),
        "source_lane_arm_id": lane_arm.get("lane_arm_id") or latest_r236.get("gate_record_id"),
        "source_risk_contract_id": "r230_contract_BTCUSDT_8m_short_ladder_close_50_618",
        "preview_only": False,
        "artifact_only": True,
        "executable": False,
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "order_payload_created": True,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "order_placed": False,
        "requires_future_precision_check": True,
        "requires_future_mark_price_snapshot": True,
        "requires_future_quantity_rounding": True,
        "requires_future_min_notional_check": True,
        "requires_future_final_operator_confirmation": True,
        "missing_before_executable_payload": [
            "symbol_precision_check",
            "mark_price_or_candidate_price_snapshot",
            "quantity_rounding",
            "min_notional_check",
            "final_operator_executable_payload_confirmation",
            "signature_gate",
            "submit_gate",
        ],
        "notes": [
            "R240 writes a non-executable order payload artifact only.",
            "This artifact is not signed, not submittable, and cannot be sent to Binance.",
            "A later phase must perform precision and connectivity checks before any executable payload.",
        ],
    }


def validate_non_executable_order_payload_artifact(order_payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    expected = {
        "order_payload_id": "r240_order_payload_BTCUSDT_8m_short_ladder_close_50_618",
        "order_payload_version": ORDER_PAYLOAD_VERSION,
        "created_by_phase": CREATED_BY_PHASE,
        "official_lane_key": OFFICIAL_LANE_KEY,
        "exchange": "binance_futures",
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "side": "SELL",
        "position_side": "BOTH|SHORT|null",
        "order_type": "MARKET_PREVIEW_ONLY",
        "time_in_force": None,
        "quantity": None,
        "quantity_source": "requires_precision_and_mark_price_later",
        "notional_cap_usdt": 44,
        "max_loss_usdt": 4.44,
        "leverage": 1,
        "reduce_only": False,
        "stop_required": True,
        "take_profit_required": True,
        "source_order_preflight_id": "r238_order_preflight_BTCUSDT_8m_short_ladder_close_50_618",
        "source_lane_arm_id": "r236_lane_arm_BTCUSDT_8m_short_ladder_close_50_618",
        "source_risk_contract_id": "r230_contract_BTCUSDT_8m_short_ladder_close_50_618",
        "preview_only": False,
        "artifact_only": True,
        "executable": False,
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "order_payload_created": True,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "order_placed": False,
        "requires_future_precision_check": True,
        "requires_future_mark_price_snapshot": True,
        "requires_future_quantity_rounding": True,
        "requires_future_min_notional_check": True,
        "requires_future_final_operator_confirmation": True,
    }
    for key, value in expected.items():
        if order_payload.get(key) is not value and order_payload.get(key) != value:
            errors.append(f"{key}_invalid")
    if not order_payload.get("source_order_payload_preview_id"):
        errors.append("source_order_payload_preview_id_missing")
    stop = order_payload.get("stop_payload") if isinstance(order_payload.get("stop_payload"), Mapping) else {}
    tp = order_payload.get("take_profit_payload") if isinstance(order_payload.get("take_profit_payload"), Mapping) else {}
    for name, payload in (("stop_payload", stop), ("take_profit_payload", tp)):
        for key, value in {
            "preview_only": True,
            "executable": False,
            "signed": False,
            "side": "BUY",
            "reduce_only": True,
            "requires_future_price_precision": True,
        }.items():
            if payload.get(key) is not value and payload.get(key) != value:
                errors.append(f"{name}_{key}_invalid")
    if stop.get("order_type") != "STOP_MARKET_PREVIEW_ONLY" or stop.get("stop_price") is not None:
        errors.append("stop_payload_invalid")
    if tp.get("order_type") != "TAKE_PROFIT_MARKET_PREVIEW_ONLY" or tp.get("take_profit_price") is not None:
        errors.append("take_profit_payload_invalid")
    required_missing = {
        "symbol_precision_check",
        "mark_price_or_candidate_price_snapshot",
        "quantity_rounding",
        "min_notional_check",
        "final_operator_executable_payload_confirmation",
        "signature_gate",
        "submit_gate",
    }
    if not required_missing.issubset(set(order_payload.get("missing_before_executable_payload") or [])):
        errors.append("missing_before_executable_payload_invalid")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def build_order_payload_write_preview(
    *,
    proposed_order_payload: Mapping[str, Any],
    order_payload_valid: bool,
    blocked_by: Sequence[str] | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return {
        "would_write": bool(order_payload_valid and not blocked_by),
        "write_requires_confirmation": True,
        "target_order_payload_key": official_lane_key,
        "bounded_mutation_only": True,
        "order_payload_artifact": "ledger_only_non_executable",
        "proposed_order_payload": _sanitize(dict(proposed_order_payload)),
    }


def write_order_payload_if_confirmed(
    *,
    order_payload: Mapping[str, Any],
    confirm_tiny_live_order_payload_write: str | None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_order_payload_write != CONFIRM_TINY_LIVE_ORDER_PAYLOAD_WRITE_PHRASE:
        return {"written": False, "reason": "bad_confirmation"}
    validation = validate_non_executable_order_payload_artifact(order_payload)
    if not validation["valid"]:
        return {"written": False, "reason": "validation_failed", "validation": validation}
    record = append_tiny_live_order_payload_write_gate_record(
        {
            "status": TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_WRITTEN,
            "generated_at": order_payload.get("created_at"),
            "order_payload_written": True,
            "write_order_payload_requested": True,
            "confirmation_valid": True,
            "target_scope": _target_scope(str(order_payload.get("official_lane_key") or OFFICIAL_LANE_KEY)),
            "order_payload": dict(order_payload),
            "order_payload_validation": validation,
            "safety": {**SAFETY, "order_payload_written": True, "order_payload_created": True},
        },
        log_dir=log_dir,
    )
    return {"written": True, "record": record}


def build_post_write_order_payload_verification(
    *,
    order_payload: Mapping[str, Any],
    order_payload_written: bool,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_tiny_live_order_payload_write_gate_records(log_dir=log_dir, limit=50) if order_payload_written else []
    matching = _matching_order_payload_record(records, order_payload)
    artifact = matching.get("order_payload") if isinstance(matching.get("order_payload"), Mapping) else {}
    validation = validate_non_executable_order_payload_artifact(artifact)
    return {
        "order_payload_written": bool(order_payload_written),
        "matching_order_payload_found": bool(matching),
        "matching_order_payload_valid": bool(matching and validation["valid"]),
        "order_payload_created": bool(matching and artifact.get("order_payload_created") is True),
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "submit_allowed": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "kill_switch_disabled": False,
    }


def build_order_payload_write_gate_matrix(
    *,
    r239_payload_preview_ready: bool,
    order_preflight_valid: bool,
    lane_arm_valid: bool,
    order_payload_valid: bool,
    order_payload_write_confirmed: bool,
    order_payload_written: bool,
    order_payload_created: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if not r239_payload_preview_ready:
        blockers.append("r239_payload_preview_not_ready")
    if not order_preflight_valid:
        blockers.append("order_preflight_invalid")
    if not lane_arm_valid:
        blockers.append("lane_arm_invalid")
    if not order_payload_valid:
        blockers.append("order_payload_invalid")
    if not order_payload_write_confirmed:
        blockers.append("exact_order_payload_write_confirmation_required")
    if order_payload_written:
        blockers = [
            "precision_and_mark_price_preview_required_later",
            "executable_payload_forbidden",
            "signed_request_forbidden",
            "submit_gate_required_later",
            "kill_switch_still_active",
        ]
    return {
        "r239_payload_preview_ready": bool(r239_payload_preview_ready),
        "order_preflight_valid": bool(order_preflight_valid),
        "lane_arm_valid": bool(lane_arm_valid),
        "order_payload_valid": bool(order_payload_valid),
        "order_payload_write_confirmed": bool(order_payload_write_confirmed),
        "order_payload_written": bool(order_payload_written),
        "order_payload_created": bool(order_payload_created),
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_order_payload_write_review_packet(
    order_payload_write_gate_matrix: Mapping[str, Any],
    *,
    write_requested: bool = False,
) -> dict[str, Any]:
    written = order_payload_write_gate_matrix.get("order_payload_written") is True
    ready = (
        order_payload_write_gate_matrix.get("r239_payload_preview_ready") is True
        and order_payload_write_gate_matrix.get("order_preflight_valid") is True
        and order_payload_write_gate_matrix.get("lane_arm_valid") is True
        and order_payload_write_gate_matrix.get("order_payload_valid") is True
        and not written
    )
    if written:
        action = "REVIEW_R240_RESULT"
    elif ready:
        action = "CONFIRM_R240_ORDER_PAYLOAD_WRITE"
    else:
        action = "WAIT"
    return {
        "operator_should_review_order_payload_write": bool(ready or written or write_requested),
        "operator_confirmation_required": True,
        "operator_should_sign_request": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not sign request",
            "do not create executable payload",
            "do not call Binance from this phase",
        ],
    }


def classify_tiny_live_order_payload_write_status(payload: Mapping[str, Any]) -> str:
    return str(payload.get("order_payload_write_overall_status") or UNKNOWN_NEEDS_MANUAL_REVIEW)


def append_tiny_live_order_payload_write_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_order_payload_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "gate_record_id": record.get("gate_record_id") or f"r240_order_payload_write_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "order_payload_written": record.get("order_payload_written") is True,
            "write_order_payload_requested": record.get("write_order_payload_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "order_payload": dict(record.get("order_payload") or {}),
            "order_payload_validation": dict(record.get("order_payload_validation") or {}),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_order_payload_write_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_order_payload_write_gate_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_tiny_live_order_payload_write_gate_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_order_payload_written": latest.get("order_payload_written") is True,
        "latest_order_payload_id": (latest.get("order_payload") or {}).get("order_payload_id")
        if isinstance(latest.get("order_payload"), Mapping)
        else None,
    }


def tiny_live_order_payload_write_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_order_payload_write_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r239: Mapping[str, Any],
    latest_r238: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    latest_r234: Mapping[str, Any],
    latest_r232: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_config: Mapping[str, Any],
) -> dict[str, Any]:
    preview = (
        latest_r239.get("non_executable_order_payload_preview")
        if isinstance(latest_r239.get("non_executable_order_payload_preview"), Mapping)
        else {}
    )
    order_preflight = latest_r238.get("order_preflight") if isinstance(latest_r238.get("order_preflight"), Mapping) else {}
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    execution_enable = latest_r234.get("execution_enable") if isinstance(latest_r234.get("execution_enable"), Mapping) else {}
    auth = latest_r232.get("authorization") if isinstance(latest_r232.get("authorization"), Mapping) else {}
    risk_contract = (
        risk_config.get("matching_risk_contract") if isinstance(risk_config.get("matching_risk_contract"), Mapping) else {}
    )
    r228_matrix = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    preview_validation = validate_order_payload_preview(preview) if preview else {"valid": False}
    order_preflight_validation = validate_order_preflight_object(order_preflight) if order_preflight else {"valid": False}
    lane_arm_validation = validate_lane_arm_object(lane_arm) if lane_arm else {"valid": False}
    execution_validation = validate_live_execution_enable_object(execution_enable) if execution_enable else {"valid": False}
    auth_validation = validate_live_authorization_object(auth) if auth else {"valid": False}
    risk_validation = (
        validate_tiny_live_risk_contract_config_entry(risk_contract)
        if risk_contract
        else {"valid": False}
    )
    return {
        "r239_payload_preview_found": bool(latest_r239),
        "r239_payload_preview_ready": _r239_preview_ready(latest_r239) and preview_validation.get("valid") is True,
        "r238_order_preflight_found": bool(latest_r238),
        "r238_order_preflight_valid": order_preflight_validation.get("valid") is True,
        "r236_lane_arm_found": bool(latest_r236),
        "r236_lane_arm_valid": lane_arm_validation.get("valid") is True,
        "r234_execution_enable_found": bool(latest_r234),
        "r234_execution_enable_valid": execution_validation.get("valid") is True,
        "r232_authorization_found": bool(latest_r232),
        "r232_authorization_valid": auth_validation.get("valid") is True,
        "r230_risk_contract_config_found": bool(latest_r230) and bool(risk_contract),
        "risk_contract_valid": risk_validation.get("valid") is True,
        "r228_evidence_ready": r228_matrix.get("evidence_ready") is True,
        "fisherman_ready": r228_matrix.get("fisherman_ready") is True,
        "live_authorized": auth.get("live_authorized") is True
        and execution_enable.get("live_authorized") is True
        and lane_arm.get("live_authorized") is True
        and order_preflight.get("live_authorized") is True,
        "live_execution_enabled": execution_enable.get("live_execution_enabled") is True
        and lane_arm.get("live_execution_enabled") is True
        and order_preflight.get("live_execution_enabled") is True,
        "lane_armed": lane_arm.get("lane_armed") is True and order_preflight.get("lane_armed") is True,
        "order_payload_created": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "kill_switch_disabled": False,
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
    if not input_summary.get("r239_payload_preview_ready"):
        blockers.append("r239_payload_preview_not_ready")
    if not input_summary.get("r238_order_preflight_valid"):
        blockers.append("order_preflight_not_ready")
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
    for key in (
        "order_payload_created",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "binance_call_allowed",
        "network_allowed",
        "kill_switch_disabled",
    ):
        if input_summary.get(key) is not False:
            blockers.append(f"{key}_not_false")
    if not validation.get("valid"):
        blockers.extend(str(error) for error in validation.get("errors") or ["order_payload_invalid"])
    return _dedupe(blockers)


def _ready_or_blocked_status(
    *,
    input_summary: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> tuple[str, str]:
    if not input_summary.get("r239_payload_preview_ready"):
        return TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_BLOCKED, TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_R239_PREVIEW
    if not input_summary.get("r238_order_preflight_valid"):
        return TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_BLOCKED, TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_PREFLIGHT
    if not input_summary.get("r236_lane_arm_valid") or not input_summary.get("lane_armed"):
        return TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_BLOCKED, TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_LANE_ARM
    if not input_summary.get("risk_contract_valid"):
        return TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_BLOCKED, TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_RISK_CONTRACT
    if not validation.get("valid"):
        return TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_BLOCKED, TINY_LIVE_ORDER_PAYLOAD_WRITE_BLOCKED_BY_VALIDATION
    return TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_READY, TINY_LIVE_ORDER_PAYLOAD_WRITE_READY_FOR_CONFIRMATION


def _recommended_next_operator_move(matrix: Mapping[str, Any], *, write_requested: bool) -> str:
    if matrix.get("order_payload_written"):
        return "REVIEW_R240_RESULT"
    if (
        matrix.get("r239_payload_preview_ready")
        and matrix.get("order_preflight_valid")
        and matrix.get("lane_arm_valid")
        and matrix.get("order_payload_valid")
    ):
        return "CONFIRM_R240_ORDER_PAYLOAD_WRITE"
    return "WAIT" if not write_requested else "REVIEW_BLOCKED_R240_ORDER_PAYLOAD_WRITE"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("order_payload_written"):
        return "Create R241 tiny-live precision and mark-price preview; prefer cached exchange info and keep no Binance/network/order/signed request behavior."
    if matrix.get("order_payload_valid"):
        return "Await exact R240 confirmation before appending the non-executable order payload artifact."
    return "Fix R240 prerequisites before any order-payload artifact write."


def _r239_preview_ready(latest_r239: Mapping[str, Any]) -> bool:
    matrix = latest_r239.get("order_payload_preview_gate_matrix") if isinstance(latest_r239.get("order_payload_preview_gate_matrix"), Mapping) else {}
    return (
        bool(latest_r239)
        and latest_r239.get("status") in {TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY, TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDED}
        and latest_r239.get("order_payload_preview_overall_status")
        == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY_FOR_FUTURE_GATE
        and matrix.get("order_payload_preview_ready") is True
        and matrix.get("order_payload_created") is False
    )


def _matching_order_payload_record(records: Sequence[Mapping[str, Any]], order_payload: Mapping[str, Any]) -> dict[str, Any]:
    expected_id = order_payload.get("order_payload_id")
    for record in records:
        artifact = record.get("order_payload") if isinstance(record.get("order_payload"), Mapping) else {}
        if artifact.get("order_payload_id") == expected_id and record.get("order_payload_written") is True:
            return _sanitize(record)
    return {}


def _target_scope(lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "order_payload_write_gate_only": True,
        "non_executable_artifact_only": True,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r239_payload_preview_found": False,
        "r239_payload_preview_ready": False,
        "r238_order_preflight_found": False,
        "r238_order_preflight_valid": False,
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
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "kill_switch_disabled": False,
    }


def _empty_order_payload_write_preview(official_lane_key: str) -> dict[str, Any]:
    return {
        "would_write": False,
        "write_requires_confirmation": True,
        "target_order_payload_key": official_lane_key,
        "bounded_mutation_only": True,
        "order_payload_artifact": "ledger_only_non_executable",
        "proposed_order_payload": {},
    }


def _empty_post_write_verification() -> dict[str, Any]:
    return {
        "order_payload_written": False,
        "matching_order_payload_found": False,
        "matching_order_payload_valid": False,
        "order_payload_created": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "submit_allowed": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "kill_switch_disabled": False,
    }


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "executable order payload creation",
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


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
