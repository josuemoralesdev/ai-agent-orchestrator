"""R245 tiny-live order payload refresh preview.

This module refreshes the non-executable order payload preview from the
official R244 44 USDT margin / 10x / 440 USDT risk contract and the latest
recorded R242 read-only precision/mark-price result. It never writes payload
artifacts, creates executable payloads, signs requests, calls Binance/network,
places orders, or mutates configs/env/lane controls.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import RISK_CONTRACT_CONFIG_PATH
from src.app.hammer_radar.operator.tiny_live_leverage_notional_adjustment_preview import (
    load_latest_tiny_live_10_of_10_ready_packet as _load_latest_tiny_live_10_of_10_ready_packet,
    load_latest_tiny_live_binance_readonly_precision_mark_price_gate as _load_latest_tiny_live_binance_readonly_precision_mark_price_gate,
    load_latest_tiny_live_lane_arm_write_gate as _load_latest_tiny_live_lane_arm_write_gate,
    load_latest_tiny_live_order_payload_write_gate as _load_latest_tiny_live_order_payload_write_gate,
    load_latest_tiny_live_order_preflight_write_gate as _load_latest_tiny_live_order_preflight_write_gate,
)
from src.app.hammer_radar.operator.tiny_live_leverage_notional_risk_contract_write_gate import (
    LEDGER_FILENAME as R244_LEDGER_FILENAME,
    TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITTEN_PAYLOAD_REFRESH_REQUIRED,
    TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_WRITTEN,
    load_tiny_live_leverage_notional_risk_contract_write_gate_records,
    validate_adjusted_risk_contract,
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    load_tiny_live_risk_contract_config as _load_tiny_live_risk_contract_config,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_write_gate import (
    validate_non_executable_order_payload_artifact,
)
from src.app.hammer_radar.operator.tiny_live_order_preflight_write_gate import validate_order_preflight_object
from src.app.hammer_radar.operator.tiny_live_lane_arm_write_gate import validate_lane_arm_object

TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_READY = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_READY"
TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_REJECTED = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_REJECTED"
TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDED = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDED"
TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED"
TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_ERROR = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_ERROR"

TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_READY_FOR_FUTURE_GATE = (
    "TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_READY_FOR_FUTURE_GATE"
)
TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_CLEARS_PRECISION_AND_MIN_NOTIONAL = (
    "TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_CLEARS_PRECISION_AND_MIN_NOTIONAL"
)
TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_RISK_CONTRACT = (
    "TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_RISK_CONTRACT"
)
TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_R242 = (
    "TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_R242"
)
TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_VALIDATION = (
    "TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW"
LEDGER_FILENAME = "tiny_live_order_payload_refresh_preview.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R245_TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW"
CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE ORDER PAYLOAD REFRESH PREVIEW RECORDING ONLY; "
    "NO PAYLOAD WRITE; NO ORDER; NO BINANCE CALL."
)
FUTURE_R246_CONFIRMATION_PHRASE_SUGGESTION = (
    "I CONFIRM TINY LIVE ORDER PAYLOAD REFRESH WRITE GATE ONLY; "
    "WRITE NON-EXECUTABLE PAYLOAD ARTIFACT ONLY; NO ORDER; NO BINANCE CALL."
)

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
    "binance_exchange_info_endpoint_called": False,
    "binance_mark_price_endpoint_called": False,
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "kill_switch_disabled": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
    "payload_refresh_preview_only": True,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R244_LEDGER_FILENAME}",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_order_payload_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_order_preflight_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_lane_arm_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_10_of_10_ready_packet.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_order_payload_refresh_preview(
    *,
    log_dir: str | Path | None = None,
    record_payload_refresh_preview: bool = False,
    confirm_tiny_live_order_payload_refresh_preview: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    confirmation_valid = (
        confirm_tiny_live_order_payload_refresh_preview
        == CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDING_PHRASE
    )
    symbol, _, direction, _ = _lane_parts(official_lane_key)
    try:
        latest_r244 = load_latest_tiny_live_leverage_notional_risk_contract_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        adjusted_contract = load_adjusted_tiny_live_risk_contract(
            risk_path,
            official_lane_key=official_lane_key,
        )
        latest_r242 = load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r240 = load_latest_tiny_live_order_payload_write_gate(
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
        latest_r228 = load_latest_tiny_live_10_of_10_ready_packet(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        input_summary = _build_input_summary(
            latest_r244=latest_r244,
            adjusted_contract=adjusted_contract,
            latest_r242=latest_r242,
            latest_r240=latest_r240,
            latest_r238=latest_r238,
            latest_r236=latest_r236,
            latest_r228=latest_r228,
        )
        contract_summary = _adjusted_risk_contract_summary(adjusted_contract.get("matching_risk_contract") or {})
        precision_summary = _precision_mark_price_summary(latest_r242)
        quantity_preview = compute_refreshed_quantity_preview(
            max_notional_usdt=contract_summary.get("max_notional_usdt"),
            mark_price=precision_summary.get("mark_price"),
            step_size=precision_summary.get("step_size"),
            min_notional=precision_summary.get("min_notional"),
        )
        refreshed_payload = build_refreshed_non_executable_payload_preview(
            adjusted_risk_contract_summary=contract_summary,
            refreshed_quantity_preview=quantity_preview,
            latest_r244=latest_r244,
            latest_r240=latest_r240,
            latest_r238=latest_r238,
            latest_r236=latest_r236,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        validation = validate_refreshed_payload_preview(
            refreshed_payload,
            input_summary=input_summary,
            refreshed_quantity_preview=quantity_preview,
        )
        matrix = build_payload_refresh_preview_gate_matrix(
            input_summary=input_summary,
            refreshed_quantity_preview=quantity_preview,
            payload_refresh_validation=validation,
        )
        operator_packet = build_operator_payload_refresh_preview_packet(matrix)
        overall = classify_tiny_live_order_payload_refresh_preview_status(
            input_summary=input_summary,
            payload_refresh_validation=validation,
            payload_refresh_preview_gate_matrix=matrix,
        )
        if record_payload_refresh_preview and not confirmation_valid:
            status = TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_REJECTED
            recorded = False
            overall = TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_VALIDATION
        elif validation.get("valid") is True and not matrix.get("blocked_by"):
            status = TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_READY
            recorded = False
        elif validation.get("valid") is True and matrix.get("payload_refresh_preview_ready") is True:
            status = TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_READY
            recorded = False
        else:
            status = TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED
            recorded = False

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "payload_refresh_preview_recorded": False,
            "record_payload_refresh_preview_requested": bool(record_payload_refresh_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "official_lane_key": official_lane_key,
                "symbol": symbol,
                "direction": direction,
                "payload_refresh_preview_only": True,
                "executable_payload_created": False,
                "signed_order_request_created": False,
                "order_placed": False,
                "binance_call_allowed": False,
                "network_allowed": False,
            },
            "input_summary": input_summary,
            "adjusted_risk_contract_summary": contract_summary,
            "precision_mark_price_summary": precision_summary,
            "refreshed_quantity_preview": quantity_preview,
            "refreshed_non_executable_payload_preview": refreshed_payload,
            "payload_refresh_validation": validation,
            "payload_refresh_preview_gate_matrix": matrix,
            "operator_payload_refresh_preview_packet": operator_packet,
            "recommended_next_operator_move": _recommended_next_operator_move(matrix),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
            "payload_refresh_preview_overall_status": overall,
            "future_r246_confirmation_phrase_suggestion": FUTURE_R246_CONFIRMATION_PHRASE_SUGGESTION,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_payload_refresh_preview and confirmation_valid and validation.get("valid") is True:
            record = append_tiny_live_order_payload_refresh_preview_record(payload, log_dir=resolved_log_dir)
            payload["status"] = TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDED
            payload["payload_refresh_preview_recorded"] = True
            payload["order_payload_refresh_preview_record_id"] = record["order_payload_refresh_preview_record_id"]
            payload["ledger_path"] = str(tiny_live_order_payload_refresh_preview_records_path(resolved_log_dir))
            recorded = True
        if recorded:
            payload["status"] = TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDED
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_payload_refresh_preview_gate_matrix(
            input_summary=_empty_input_summary(),
            refreshed_quantity_preview=_blocked_quantity_preview(["r245_preview_error"]),
            payload_refresh_validation={"valid": False, "errors": ["r245_preview_error"], "warnings": []},
        )
        return _sanitize(
            {
                "status": TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "payload_refresh_preview_recorded": False,
                "record_payload_refresh_preview_requested": bool(record_payload_refresh_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "direction": direction,
                    "payload_refresh_preview_only": True,
                    "executable_payload_created": False,
                    "signed_order_request_created": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": _empty_input_summary(),
                "adjusted_risk_contract_summary": _empty_adjusted_risk_contract_summary(),
                "precision_mark_price_summary": _empty_precision_mark_price_summary(),
                "refreshed_quantity_preview": _blocked_quantity_preview(["r245_preview_error"]),
                "refreshed_non_executable_payload_preview": {},
                "payload_refresh_validation": {"valid": False, "errors": ["r245_preview_error"], "warnings": []},
                "payload_refresh_preview_gate_matrix": matrix,
                "operator_payload_refresh_preview_packet": build_operator_payload_refresh_preview_packet(matrix),
                "recommended_next_operator_move": "FIX_BLOCKER",
                "recommended_next_engineering_move": "Fix R245 payload refresh preview error before any R246 write gate.",
                "payload_refresh_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "future_r246_confirmation_phrase_suggestion": FUTURE_R246_CONFIRMATION_PHRASE_SUGGESTION,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_leverage_notional_risk_contract_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_leverage_notional_risk_contract_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        post = record.get("post_write_verification") if isinstance(record.get("post_write_verification"), Mapping) else {}
        matrix = record.get("risk_contract_write_gate_matrix") if isinstance(record.get("risk_contract_write_gate_matrix"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_WRITTEN
            and record.get("risk_contract_written") is True
            and record.get("risk_contract_write_overall_status")
            == TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITTEN_PAYLOAD_REFRESH_REQUIRED
            and post.get("matching_adjusted_contract_valid") is True
            and matrix.get("risk_contract_written") is True
        ):
            return _sanitize({**record, "r244_adjusted_contract_found": True})
    return {}


def load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
        log_dir=log_dir,
        official_lane_key=official_lane_key,
    )


def load_latest_tiny_live_order_payload_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_tiny_live_order_payload_write_gate(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_order_preflight_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_tiny_live_order_preflight_write_gate(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_lane_arm_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_tiny_live_lane_arm_write_gate(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_10_of_10_ready_packet(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_tiny_live_10_of_10_ready_packet(log_dir=log_dir, official_lane_key=official_lane_key)


def load_adjusted_tiny_live_risk_contract(
    config_path: str | Path | None = None,
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    config = _load_tiny_live_risk_contract_config(config_path, official_lane_key=official_lane_key)
    contract = config.get("matching_risk_contract") if isinstance(config.get("matching_risk_contract"), Mapping) else {}
    validation = validate_adjusted_risk_contract(contract)
    return _sanitize(
        {
            **config,
            "matching_risk_contract": dict(contract),
            "adjusted_contract_validation": validation,
            "adjusted_contract_valid": validation.get("valid") is True,
        }
    )


def compute_refreshed_quantity_preview(
    *,
    max_notional_usdt: Any,
    mark_price: Any,
    step_size: Any,
    min_notional: Any,
) -> dict[str, Any]:
    blocked_by: list[str] = []
    mark = _decimal(mark_price)
    step = _decimal(step_size)
    minimum = _decimal(min_notional)
    notional = _decimal(max_notional_usdt)
    if mark is None or mark <= 0:
        blocked_by.append("mark_price_missing")
    if step is None or step <= 0:
        blocked_by.append("step_size_missing")
    if minimum is None or minimum < 0:
        blocked_by.append("min_notional_missing")
    if notional is None or notional <= 0:
        blocked_by.append("max_notional_invalid")
    if blocked_by:
        return _blocked_quantity_preview(_dedupe(blocked_by))
    quantity_raw = notional / mark
    quantity_rounded = (quantity_raw / step).to_integral_value(rounding=ROUND_FLOOR) * step
    notional_after_rounding = quantity_rounded * mark
    if quantity_rounded <= 0:
        blocked_by.append("quantity_rounds_to_zero")
    min_notional_ok = bool(notional_after_rounding >= minimum)
    if not min_notional_ok:
        blocked_by.append("min_notional_not_met_after_rounding")
    return {
        "can_compute": not blocked_by,
        "quantity_raw": _float(quantity_raw),
        "quantity_rounded": _float(quantity_rounded),
        "notional_after_rounding": _float(notional_after_rounding),
        "min_notional_ok": min_notional_ok,
        "clears_quantity_rounding": quantity_rounded > 0,
        "clears_min_notional": min_notional_ok,
        "blocked_by": _dedupe(blocked_by),
    }


def build_refreshed_non_executable_payload_preview(
    *,
    adjusted_risk_contract_summary: Mapping[str, Any],
    refreshed_quantity_preview: Mapping[str, Any],
    latest_r244: Mapping[str, Any] | None = None,
    latest_r240: Mapping[str, Any],
    latest_r238: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    old_payload = latest_r240.get("order_payload") if isinstance(latest_r240.get("order_payload"), Mapping) else {}
    preflight = latest_r238.get("order_preflight") if isinstance(latest_r238.get("order_preflight"), Mapping) else {}
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    return {
        "order_payload_refresh_preview_id": f"r245_order_payload_refresh_preview_{uuid4().hex}",
        "created_by_phase": CREATED_BY_PHASE,
        "created_at": generated_at.isoformat(),
        "preview_only": True,
        "artifact_written": False,
        "executable": False,
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "official_lane_key": official_lane_key,
        "exchange": "binance_futures",
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "side": "SELL",
        "position_side": old_payload.get("position_side") or "BOTH|SHORT|null",
        "order_type": "MARKET_PREVIEW_ONLY",
        "quantity_preview": refreshed_quantity_preview.get("quantity_rounded"),
        "quantity_source": "r242_readonly_precision_mark_price_and_r244_adjusted_contract",
        "notional_cap_usdt": adjusted_risk_contract_summary.get("max_notional_usdt"),
        "notional_after_rounding": refreshed_quantity_preview.get("notional_after_rounding"),
        "margin_budget_usdt": adjusted_risk_contract_summary.get("margin_budget_usdt"),
        "leverage": adjusted_risk_contract_summary.get("leverage"),
        "max_loss_usdt": adjusted_risk_contract_summary.get("max_loss_usdt"),
        "max_loss_requires_review": adjusted_risk_contract_summary.get("max_loss_requires_review") is True,
        "reduce_only": False,
        "stop_required": True,
        "take_profit_required": True,
        "stop_payload_preview": {
            "preview_only": True,
            "executable": False,
            "signed": False,
            "order_type": "STOP_MARKET_PREVIEW_ONLY",
            "side": "BUY",
            "reduce_only": True,
            "stop_price": None,
            "requires_future_price_precision": True,
            "requires_stop_level_source_later": True,
        },
        "take_profit_payload_preview": {
            "preview_only": True,
            "executable": False,
            "signed": False,
            "order_type": "TAKE_PROFIT_MARKET_PREVIEW_ONLY",
            "side": "BUY",
            "reduce_only": True,
            "take_profit_price": None,
            "requires_future_price_precision": True,
            "requires_take_profit_level_source_later": True,
        },
        "source_r244_risk_contract_record_id": (latest_r244 or {}).get("risk_contract_write_gate_record_id"),
        "source_r240_order_payload_id": old_payload.get("order_payload_id"),
        "source_order_preflight_id": preflight.get("order_preflight_id"),
        "source_lane_arm_id": lane_arm.get("lane_arm_id") or latest_r236.get("gate_record_id"),
        "missing_before_executable_payload": [
            "final_stop_price",
            "final_take_profit_price",
            "operator_executable_payload_confirmation",
            "signature_gate",
            "submit_gate",
        ],
    }


def validate_refreshed_payload_preview(
    refreshed_payload_preview: Mapping[str, Any],
    *,
    input_summary: Mapping[str, Any] | None = None,
    refreshed_quantity_preview: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    summary = input_summary or {}
    quantity = refreshed_quantity_preview or {}
    for key in (
        "r244_adjusted_contract_valid",
        "r242_readonly_valid",
        "r240_payload_valid",
        "r238_order_preflight_valid",
        "r236_lane_arm_valid",
        "r228_evidence_ready",
    ):
        if summary and summary.get(key) is not True:
            errors.append(f"{key}_missing_or_false")
    expected = {
        "preview_only": True,
        "artifact_written": False,
        "executable": False,
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "official_lane_key": OFFICIAL_LANE_KEY,
        "exchange": "binance_futures",
        "symbol": "BTCUSDT",
        "side": "SELL",
        "order_type": "MARKET_PREVIEW_ONLY",
        "quantity_source": "r242_readonly_precision_mark_price_and_r244_adjusted_contract",
        "notional_cap_usdt": 440,
        "margin_budget_usdt": 44,
        "leverage": 10,
        "max_loss_usdt": 4.44,
        "max_loss_requires_review": True,
        "reduce_only": False,
        "stop_required": True,
        "take_profit_required": True,
    }
    for key, value in expected.items():
        if refreshed_payload_preview.get(key) != value:
            errors.append(f"{key}_invalid")
    if quantity and quantity.get("can_compute") is not True:
        errors.append("refreshed_quantity_preview_blocked")
    if quantity and quantity.get("clears_min_notional") is not True:
        errors.append("refreshed_quantity_min_notional_not_clear")
    if refreshed_payload_preview.get("quantity_preview") in (None, 0, 0.0):
        errors.append("quantity_preview_missing_or_zero")
    stop = (
        refreshed_payload_preview.get("stop_payload_preview")
        if isinstance(refreshed_payload_preview.get("stop_payload_preview"), Mapping)
        else {}
    )
    tp = (
        refreshed_payload_preview.get("take_profit_payload_preview")
        if isinstance(refreshed_payload_preview.get("take_profit_payload_preview"), Mapping)
        else {}
    )
    if stop.get("stop_price") is not None or stop.get("requires_stop_level_source_later") is not True:
        errors.append("stop_payload_preview_invalid")
    if tp.get("take_profit_price") is not None or tp.get("requires_take_profit_level_source_later") is not True:
        errors.append("take_profit_payload_preview_invalid")
    required_missing = {
        "final_stop_price",
        "final_take_profit_price",
        "operator_executable_payload_confirmation",
        "signature_gate",
        "submit_gate",
    }
    if not required_missing.issubset(set(refreshed_payload_preview.get("missing_before_executable_payload") or [])):
        errors.append("missing_before_executable_payload_invalid")
    if not refreshed_payload_preview.get("source_r240_order_payload_id"):
        warnings.append("source_r240_order_payload_id_missing")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def build_payload_refresh_preview_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    refreshed_quantity_preview: Mapping[str, Any],
    payload_refresh_validation: Mapping[str, Any],
) -> dict[str, Any]:
    blocked_by: list[str] = []
    if not input_summary.get("r244_adjusted_contract_valid"):
        blocked_by.append("r244_adjusted_risk_contract_not_ready")
    if not input_summary.get("r242_readonly_valid"):
        blocked_by.append("r242_readonly_not_ready")
    if not input_summary.get("r240_payload_valid"):
        blocked_by.append("r240_payload_artifact_not_ready")
    if not input_summary.get("r238_order_preflight_valid"):
        blocked_by.append("r238_order_preflight_not_ready")
    if not input_summary.get("r236_lane_arm_valid"):
        blocked_by.append("r236_lane_arm_not_ready")
    if not input_summary.get("r228_evidence_ready"):
        blocked_by.append("r228_evidence_not_ready")
    if refreshed_quantity_preview.get("can_compute") is not True:
        blocked_by.extend(str(item) for item in refreshed_quantity_preview.get("blocked_by") or ["quantity_preview_blocked"])
    if payload_refresh_validation.get("valid") is not True:
        blocked_by.extend(str(item) for item in payload_refresh_validation.get("errors") or ["payload_refresh_invalid"])
    return {
        "adjusted_risk_contract_ready": bool(input_summary.get("r244_adjusted_contract_valid")),
        "r242_readonly_ready": bool(input_summary.get("r242_readonly_valid")),
        "refreshed_quantity_ready": refreshed_quantity_preview.get("can_compute") is True,
        "payload_refresh_preview_ready": payload_refresh_validation.get("valid") is True and not blocked_by,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blocked_by),
    }


def build_operator_payload_refresh_preview_packet(
    payload_refresh_preview_gate_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    ready = payload_refresh_preview_gate_matrix.get("payload_refresh_preview_ready") is True
    action = "REVIEW_R245_PAYLOAD_REFRESH_PREVIEW" if ready else "FIX_BLOCKER"
    if payload_refresh_preview_gate_matrix.get("r242_readonly_ready") is not True:
        action = "WAIT"
    return {
        "operator_should_review_payload_refresh_preview": bool(ready),
        "operator_should_create_executable_payload_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not create executable payload",
            "do not sign request",
            "do not call Binance from this phase",
        ],
    }


def classify_tiny_live_order_payload_refresh_preview_status(
    *,
    input_summary: Mapping[str, Any],
    payload_refresh_validation: Mapping[str, Any],
    payload_refresh_preview_gate_matrix: Mapping[str, Any],
) -> str:
    if not input_summary.get("r244_adjusted_contract_valid"):
        return TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_RISK_CONTRACT
    if not input_summary.get("r242_readonly_valid"):
        return TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_R242
    if payload_refresh_validation.get("valid") is not True:
        return TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_VALIDATION
    if payload_refresh_preview_gate_matrix.get("payload_refresh_preview_ready") is True:
        return TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_CLEARS_PRECISION_AND_MIN_NOTIONAL
    if payload_refresh_preview_gate_matrix.get("refreshed_quantity_ready") is True:
        return TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_READY_FOR_FUTURE_GATE
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_order_payload_refresh_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_order_payload_refresh_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "order_payload_refresh_preview_record_id": record.get("order_payload_refresh_preview_record_id")
            or f"r245_order_payload_refresh_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDED,
            "generated_at": record.get("generated_at"),
            "payload_refresh_preview_recorded": True,
            "record_payload_refresh_preview_requested": True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "adjusted_risk_contract_summary": dict(record.get("adjusted_risk_contract_summary") or {}),
            "precision_mark_price_summary": dict(record.get("precision_mark_price_summary") or {}),
            "refreshed_quantity_preview": dict(record.get("refreshed_quantity_preview") or {}),
            "refreshed_non_executable_payload_preview": dict(
                record.get("refreshed_non_executable_payload_preview") or {}
            ),
            "payload_refresh_validation": dict(record.get("payload_refresh_validation") or {}),
            "payload_refresh_preview_gate_matrix": dict(record.get("payload_refresh_preview_gate_matrix") or {}),
            "operator_payload_refresh_preview_packet": dict(record.get("operator_payload_refresh_preview_packet") or {}),
            "payload_refresh_preview_overall_status": record.get("payload_refresh_preview_overall_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "future_r246_confirmation_phrase_suggestion": record.get("future_r246_confirmation_phrase_suggestion"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_order_payload_refresh_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_order_payload_refresh_preview_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_order_payload_refresh_preview_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_payload_refresh_preview_recorded": latest.get("payload_refresh_preview_recorded") is True,
        "latest_overall_status": latest.get("payload_refresh_preview_overall_status"),
        "latest_quantity_preview": (latest.get("refreshed_quantity_preview") or {}).get("quantity_rounded")
        if isinstance(latest.get("refreshed_quantity_preview"), Mapping)
        else None,
    }


def tiny_live_order_payload_refresh_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_order_payload_refresh_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r244: Mapping[str, Any],
    adjusted_contract: Mapping[str, Any],
    latest_r242: Mapping[str, Any],
    latest_r240: Mapping[str, Any],
    latest_r238: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
) -> dict[str, Any]:
    readonly_result = latest_r242.get("binance_readonly_result") if isinstance(latest_r242.get("binance_readonly_result"), Mapping) else {}
    precision = readonly_result.get("precision_snapshot") if isinstance(readonly_result.get("precision_snapshot"), Mapping) else {}
    mark = readonly_result.get("mark_price_snapshot") if isinstance(readonly_result.get("mark_price_snapshot"), Mapping) else {}
    artifact = latest_r240.get("order_payload") if isinstance(latest_r240.get("order_payload"), Mapping) else {}
    preflight = latest_r238.get("order_preflight") if isinstance(latest_r238.get("order_preflight"), Mapping) else {}
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    r228_matrix = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    payload_validation = validate_non_executable_order_payload_artifact(artifact) if artifact else {"valid": False}
    preflight_validation = validate_order_preflight_object(preflight) if preflight else {"valid": False}
    lane_arm_validation = validate_lane_arm_object(lane_arm) if lane_arm else {"valid": False}
    return {
        "r244_adjusted_contract_found": bool(latest_r244) and bool(adjusted_contract.get("matching_risk_contract")),
        "r244_adjusted_contract_valid": adjusted_contract.get("adjusted_contract_valid") is True,
        "r242_readonly_found": bool(latest_r242),
        "r242_readonly_valid": (
            latest_r242.get("readonly_fetch_performed") is True
            and precision.get("found") is True
            and mark.get("found") is True
        ),
        "r240_payload_found": bool(latest_r240),
        "r240_payload_valid": payload_validation.get("valid") is True,
        "r238_order_preflight_found": bool(latest_r238),
        "r238_order_preflight_valid": preflight_validation.get("valid") is True,
        "r236_lane_arm_found": bool(latest_r236),
        "r236_lane_arm_valid": lane_arm_validation.get("valid") is True,
        "r228_evidence_ready": r228_matrix.get("evidence_ready") is True,
    }


def _adjusted_risk_contract_summary(contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "capital_mode": contract.get("capital_mode"),
        "margin_budget_usdt": _int_if_whole(contract.get("margin_budget_usdt")),
        "leverage": _int_if_whole(contract.get("leverage")),
        "max_notional_usdt": _int_if_whole(contract.get("max_notional_usdt")),
        "max_position_notional_usdt": _int_if_whole(contract.get("max_position_notional_usdt")),
        "max_loss_usdt": _number(contract.get("max_loss_usdt")),
        "max_loss_requires_review": contract.get("max_loss_requires_review") is True,
    }


def _precision_mark_price_summary(latest_r242: Mapping[str, Any]) -> dict[str, Any]:
    result = latest_r242.get("binance_readonly_result") if isinstance(latest_r242.get("binance_readonly_result"), Mapping) else {}
    precision = result.get("precision_snapshot") if isinstance(result.get("precision_snapshot"), Mapping) else {}
    mark = result.get("mark_price_snapshot") if isinstance(result.get("mark_price_snapshot"), Mapping) else {}
    return {
        "mark_price": _number(mark.get("mark_price")),
        "step_size": _number(precision.get("step_size")),
        "tick_size": _number(precision.get("tick_size")),
        "min_notional": _number(precision.get("min_notional")),
        "quantity_precision": precision.get("quantity_precision"),
        "price_precision": precision.get("price_precision"),
        "source": "r242_readonly",
    }


def _recommended_next_operator_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("payload_refresh_preview_ready") is True:
        return "REVIEW_R245_PAYLOAD_REFRESH_PREVIEW"
    if matrix.get("r242_readonly_ready") is not True:
        return "WAIT_FOR_R242_READONLY_RESULT"
    return "FIX_R245_BLOCKER"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("payload_refresh_preview_ready") is True:
        return "Create R246 Tiny-Live Order Payload Refresh Write Gate to write the refreshed non-executable artifact only; no executable payload, no signed request, no Binance call, no order."
    return "Fix R245 input or validation blockers before any R246 payload refresh write gate."


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


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r244_adjusted_contract_found": False,
        "r244_adjusted_contract_valid": False,
        "r242_readonly_found": False,
        "r242_readonly_valid": False,
        "r240_payload_found": False,
        "r240_payload_valid": False,
        "r238_order_preflight_found": False,
        "r238_order_preflight_valid": False,
        "r236_lane_arm_found": False,
        "r236_lane_arm_valid": False,
        "r228_evidence_ready": False,
    }


def _empty_adjusted_risk_contract_summary() -> dict[str, Any]:
    return {
        "capital_mode": None,
        "margin_budget_usdt": None,
        "leverage": None,
        "max_notional_usdt": None,
        "max_position_notional_usdt": None,
        "max_loss_usdt": None,
        "max_loss_requires_review": False,
    }


def _empty_precision_mark_price_summary() -> dict[str, Any]:
    return {
        "mark_price": None,
        "step_size": None,
        "tick_size": None,
        "min_notional": None,
        "quantity_precision": None,
        "price_precision": None,
        "source": "r242_readonly",
    }


def _blocked_quantity_preview(blocked_by: Sequence[str]) -> dict[str, Any]:
    return {
        "can_compute": False,
        "quantity_raw": None,
        "quantity_rounded": None,
        "notional_after_rounding": None,
        "min_notional_ok": None,
        "clears_quantity_rounding": False,
        "clears_min_notional": False,
        "blocked_by": _dedupe(blocked_by),
    }


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key).split("|")
    if len(parts) != 4:
        return ("BTCUSDT", "8m", "short", "ladder_close_50_618")
    return parts[0], parts[1], parts[2], parts[3]


def _decimal(value: Any) -> Decimal | None:
    try:
        if value is None:
            return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _number(value: Any) -> float | None:
    dec = _decimal(value)
    if dec is None:
        return None
    return _float(dec)


def _float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000000000001")).normalize())


def _int_if_whole(value: Any) -> int | float | None:
    number = _number(value)
    if number is None:
        return None
    if float(number).is_integer():
        return int(number)
    return number


def _dedupe(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Decimal):
        return _float(value)
    if isinstance(value, Path):
        return str(value)
    return value
