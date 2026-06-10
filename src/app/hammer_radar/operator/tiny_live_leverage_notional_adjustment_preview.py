"""R243 tiny-live leverage / notional risk-contract adjustment preview.

This module is preview-only except for its own append-only R243 ledger after
the exact R243 confirmation phrase. It never calls Binance/network endpoints,
creates executable payloads, signs requests, places orders, mutates configs/env,
or changes the official tiny-live lane.
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
from src.app.hammer_radar.operator.tiny_live_binance_readonly_precision_mark_price_gate import (
    LEDGER_FILENAME as R242_LEDGER_FILENAME,
    load_tiny_live_binance_readonly_precision_mark_price_records,
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    load_tiny_live_risk_contract_config as _load_tiny_live_risk_contract_config,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_write_gate import (
    validate_non_executable_order_payload_artifact,
)
from src.app.hammer_radar.operator.tiny_live_order_preflight_write_gate import validate_order_preflight_object
from src.app.hammer_radar.operator.tiny_live_precision_and_mark_price_preview import (
    load_latest_tiny_live_10_of_10_ready_packet as _load_latest_tiny_live_10_of_10_ready_packet,
    load_latest_tiny_live_lane_arm_write_gate as _load_latest_tiny_live_lane_arm_write_gate,
    load_latest_tiny_live_order_payload_write_gate as _load_latest_tiny_live_order_payload_write_gate,
    load_latest_tiny_live_order_preflight_write_gate as _load_latest_tiny_live_order_preflight_write_gate,
    load_latest_tiny_live_risk_contract_config_write_gate as _load_latest_tiny_live_risk_contract_config_write_gate,
)
from src.app.hammer_radar.operator.tiny_live_lane_arm_write_gate import validate_lane_arm_object
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    validate_tiny_live_risk_contract_config_entry,
)

TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_READY = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_READY"
)
TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_REJECTED = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_REJECTED"
)
TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDED = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDED"
)
TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED"
)
TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_ERROR = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_ERROR"
)

TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_READY_FOR_FUTURE_GATE = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_READY_FOR_FUTURE_GATE"
)
TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_CLEARS_BINANCE_MINIMUMS = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_CLEARS_BINANCE_MINIMUMS"
)
TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_STILL_BLOCKED = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_STILL_BLOCKED"
)
TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED_BY_R242 = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED_BY_R242"
)
TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED_BY_RISK_CONTRACT = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED_BY_RISK_CONTRACT"
)
TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED_BY_VALIDATION = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED_BY_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW"
LEDGER_FILENAME = "tiny_live_leverage_notional_adjustment_preview.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE LEVERAGE NOTIONAL ADJUSTMENT PREVIEW RECORDING ONLY; "
    "NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)
FUTURE_R244_CONFIRMATION_PHRASE_SUGGESTION = (
    "I CONFIRM TINY LIVE LEVERAGE NOTIONAL RISK CONTRACT WRITE GATE ONLY; "
    "WRITE RISK CONFIG ONLY; NO ORDER; NO BINANCE CALL."
)

CURRENT_MARGIN_BUDGET_USDT = 44
CURRENT_LEVERAGE = 1
CURRENT_MAX_NOTIONAL_USDT = 44
CURRENT_MAX_LOSS_USDT = 4.44
ADJUSTED_MARGIN_BUDGET_USDT = 44
ADJUSTED_LEVERAGE = 10
ADJUSTED_MAX_NOTIONAL_USDT = 440

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
    "leverage_notional_adjustment_preview_only": True,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R242_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/tiny_live_order_payload_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_order_preflight_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_lane_arm_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_risk_contract_config_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_10_of_10_ready_packet.ndjson",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_leverage_notional_adjustment_preview(
    *,
    log_dir: str | Path | None = None,
    record_adjustment_preview: bool = False,
    confirm_tiny_live_leverage_notional_adjustment_preview: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    confirmation_valid = (
        confirm_tiny_live_leverage_notional_adjustment_preview
        == CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDING_PHRASE
    )
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    try:
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
        latest_r230 = load_latest_tiny_live_risk_contract_config_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r228 = load_latest_tiny_live_10_of_10_ready_packet(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        risk_config = load_tiny_live_risk_contract_config(risk_path, official_lane_key=official_lane_key)
        input_summary = _build_input_summary(
            latest_r242=latest_r242,
            latest_r240=latest_r240,
            latest_r238=latest_r238,
            latest_r236=latest_r236,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_config=risk_config,
        )
        precision_summary = _binance_precision_mark_price_summary(latest_r242)
        current_summary = build_current_risk_model_summary(
            risk_config=risk_config,
            precision_mark_price_summary=precision_summary,
        )
        adjusted_model = build_adjusted_leverage_notional_model_preview(
            current_risk_model_summary=current_summary,
            official_lane_key=official_lane_key,
        )
        adjusted_quantity = compute_adjusted_quantity_preview(
            max_notional_usdt=ADJUSTED_MAX_NOTIONAL_USDT,
            precision_mark_price_summary=precision_summary,
        )
        validation = validate_adjusted_leverage_notional_model_preview(
            input_summary=input_summary,
            current_risk_model_summary=current_summary,
            adjusted_model_preview=adjusted_model,
            adjusted_quantity_preview=adjusted_quantity,
        )
        matrix = build_adjustment_gate_matrix(
            input_summary=input_summary,
            current_risk_model_summary=current_summary,
            adjusted_model_preview=adjusted_model,
            adjusted_quantity_preview=adjusted_quantity,
            validation=validation,
        )
        operator_packet = build_operator_adjustment_review_packet(matrix)
        overall = classify_tiny_live_leverage_notional_adjustment_preview_status(
            input_summary=input_summary,
            adjustment_validation=validation,
            adjustment_gate_matrix=matrix,
        )

        if record_adjustment_preview and not confirmation_valid:
            status = TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_REJECTED
        elif record_adjustment_preview and confirmation_valid and validation.get("valid") is True:
            status = TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDED
        elif overall in {
            TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_READY_FOR_FUTURE_GATE,
            TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_CLEARS_BINANCE_MINIMUMS,
        }:
            status = TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_READY
        else:
            status = TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "adjustment_preview_recorded": False,
            "adjustment_preview_record_id": None,
            "record_adjustment_preview_requested": bool(record_adjustment_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "official_lane_key": official_lane_key,
                "symbol": symbol,
                "timeframe": timeframe,
                "direction": direction,
                "entry_mode": entry_mode,
                "leverage_notional_adjustment_preview_only": True,
                "config_written": False,
                "order_placed": False,
                "binance_call_allowed": False,
                "network_allowed": False,
            },
            "input_summary": input_summary,
            "current_risk_model_summary": current_summary,
            "adjusted_leverage_notional_model_preview": adjusted_model,
            "binance_precision_mark_price_summary": precision_summary,
            "adjusted_quantity_preview": adjusted_quantity,
            "adjustment_validation": validation,
            "adjustment_gate_matrix": matrix,
            "operator_adjustment_review_packet": operator_packet,
            "recommended_next_operator_move": _recommended_next_operator_move(matrix),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
            "adjustment_preview_overall_status": overall,
            "future_r244_confirmation_phrase_suggestion": FUTURE_R244_CONFIRMATION_PHRASE_SUGGESTION,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_adjustment_preview and confirmation_valid and validation.get("valid") is True:
            record = append_tiny_live_leverage_notional_adjustment_preview_record(
                payload,
                log_dir=resolved_log_dir,
            )
            payload["adjustment_preview_recorded"] = True
            payload["adjustment_preview_record_id"] = record["adjustment_preview_record_id"]
            payload["ledger_path"] = str(tiny_live_leverage_notional_adjustment_preview_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "adjustment_preview_recorded": False,
                "adjustment_preview_record_id": None,
                "record_adjustment_preview_requested": bool(record_adjustment_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "leverage_notional_adjustment_preview_only": True,
                    "config_written": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": _empty_input_summary(),
                "current_risk_model_summary": _empty_current_risk_model_summary(),
                "adjusted_leverage_notional_model_preview": build_adjusted_leverage_notional_model_preview(
                    current_risk_model_summary=_empty_current_risk_model_summary(),
                    official_lane_key=official_lane_key,
                ),
                "binance_precision_mark_price_summary": _empty_precision_mark_price_summary(),
                "adjusted_quantity_preview": _blocked_quantity_preview(["r243_preview_error"]),
                "adjustment_validation": {"valid": False, "errors": ["r243_preview_error"], "warnings": []},
                "adjustment_gate_matrix": build_adjustment_gate_matrix(
                    input_summary=_empty_input_summary(),
                    current_risk_model_summary=_empty_current_risk_model_summary(),
                    adjusted_model_preview={},
                    adjusted_quantity_preview=_blocked_quantity_preview(["r243_preview_error"]),
                    validation={"valid": False, "errors": ["r243_preview_error"], "warnings": []},
                ),
                "operator_adjustment_review_packet": build_operator_adjustment_review_packet(
                    {"blocked_by": ["r243_preview_error"]}
                ),
                "recommended_next_operator_move": "FIX_BLOCKER",
                "recommended_next_engineering_move": "Fix R243 preview error before any R244 write gate.",
                "adjustment_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "future_r244_confirmation_phrase_suggestion": FUTURE_R244_CONFIRMATION_PHRASE_SUGGESTION,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_binance_readonly_precision_mark_price_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        result = record.get("binance_readonly_result") if isinstance(record.get("binance_readonly_result"), Mapping) else {}
        precision = result.get("precision_snapshot") if isinstance(result.get("precision_snapshot"), Mapping) else {}
        mark = result.get("mark_price_snapshot") if isinstance(result.get("mark_price_snapshot"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == "TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_FETCHED"
            and record.get("readonly_fetch_performed") is True
            and precision.get("found") is True
            and mark.get("found") is True
        ):
            return _sanitize({**record, "r242_readonly_found": True})
    return {}


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


def load_latest_tiny_live_risk_contract_config_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_tiny_live_risk_contract_config_write_gate(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_10_of_10_ready_packet(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_tiny_live_10_of_10_ready_packet(log_dir=log_dir, official_lane_key=official_lane_key)


def load_tiny_live_risk_contract_config(
    config_path: str | Path | None = None,
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return _load_tiny_live_risk_contract_config(config_path, official_lane_key=official_lane_key)


def build_current_risk_model_summary(
    *,
    risk_config: Mapping[str, Any],
    precision_mark_price_summary: Mapping[str, Any],
) -> dict[str, Any]:
    contract = risk_config.get("matching_risk_contract") if isinstance(risk_config.get("matching_risk_contract"), Mapping) else {}
    leverage = _number(contract.get("leverage"))
    max_notional = _number(contract.get("max_notional_usdt"))
    max_loss = _number(contract.get("max_loss_usdt"))
    quantity = compute_adjusted_quantity_preview(
        max_notional_usdt=max_notional,
        precision_mark_price_summary=precision_mark_price_summary,
    )
    blocked_by = list(quantity.get("blocked_by") or [])
    return {
        "leverage": _int_if_whole(leverage),
        "max_notional_usdt": _int_if_whole(max_notional),
        "max_loss_usdt": max_loss,
        "margin_budget_usdt": None,
        "quantity_raw_at_current_notional": quantity.get("quantity_raw"),
        "quantity_rounded_at_current_notional": quantity.get("quantity_rounded"),
        "notional_after_rounding_at_current_notional": quantity.get("notional_after_rounding"),
        "min_notional_ok_at_current_notional": quantity.get("min_notional_ok"),
        "quantity_rounds_to_zero": "quantity_rounds_to_zero" in blocked_by,
        "blocked_by": _dedupe(blocked_by),
    }


def build_adjusted_leverage_notional_model_preview(
    *,
    current_risk_model_summary: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    return {
        "model_id": "r243_adjusted_risk_model_BTCUSDT_8m_short_ladder_close_50_618",
        "preview_only": True,
        "config_written": False,
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "current_model": {
            "leverage": current_risk_model_summary.get("leverage"),
            "max_notional_usdt": current_risk_model_summary.get("max_notional_usdt"),
            "margin_budget_usdt": current_risk_model_summary.get("margin_budget_usdt"),
            "quantity_rounds_to_zero": current_risk_model_summary.get("quantity_rounds_to_zero") is True,
        },
        "adjusted_model": {
            "margin_budget_usdt": ADJUSTED_MARGIN_BUDGET_USDT,
            "leverage": ADJUSTED_LEVERAGE,
            "max_notional_usdt": ADJUSTED_MAX_NOTIONAL_USDT,
            "max_position_notional_usdt": ADJUSTED_MAX_NOTIONAL_USDT,
            "max_account_risk_usdt_existing": CURRENT_MARGIN_BUDGET_USDT,
            "max_account_risk_usdt_reviewed_conservatively": True,
            "max_loss_usdt_existing": CURRENT_MAX_LOSS_USDT,
            "max_loss_requires_review": True,
            "risk_contract_write_required_later": True,
        },
        "rationale": [
            "44 USDT at 1x is below practical BTCUSDT quantity step size at current BTC price.",
            "44 USDT margin at 10x produces approximately 440 USDT notional.",
            "Adjusted notional should clear BTCUSDT step size and min-notional requirements.",
        ],
        "risk_implications": [
            "10x exposure amplifies liquidation and adverse-move risk.",
            "Margin budget differs from total notional exposure.",
            "Stop loss, liquidation buffer, and risk caps must be reconsidered before any executable payload.",
        ],
    }


def compute_adjusted_quantity_preview(
    *,
    max_notional_usdt: Any,
    precision_mark_price_summary: Mapping[str, Any],
) -> dict[str, Any]:
    blocked_by: list[str] = []
    mark_price = _decimal(precision_mark_price_summary.get("mark_price"))
    step = _decimal(precision_mark_price_summary.get("step_size"))
    min_notional = _decimal(precision_mark_price_summary.get("min_notional"))
    notional = _decimal(max_notional_usdt)
    if mark_price is None or mark_price <= 0:
        blocked_by.append("mark_price_missing")
    if step is None or step <= 0:
        blocked_by.append("step_size_missing")
    if min_notional is None or min_notional < 0:
        blocked_by.append("min_notional_missing")
    if notional is None or notional <= 0:
        blocked_by.append("max_notional_invalid")
    if blocked_by:
        return _blocked_quantity_preview(_dedupe(blocked_by))
    quantity_raw = notional / mark_price
    quantity_rounded = (quantity_raw / step).to_integral_value(rounding=ROUND_FLOOR) * step
    notional_after_rounding = quantity_rounded * mark_price
    if quantity_rounded <= 0:
        blocked_by.append("quantity_rounds_to_zero")
    min_notional_ok = bool(notional_after_rounding >= min_notional)
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


def validate_adjusted_leverage_notional_model_preview(
    *,
    input_summary: Mapping[str, Any],
    current_risk_model_summary: Mapping[str, Any],
    adjusted_model_preview: Mapping[str, Any],
    adjusted_quantity_preview: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not input_summary.get("r242_readonly_valid"):
        errors.append("r242_readonly_result_missing_or_invalid")
    if not input_summary.get("r240_payload_valid"):
        errors.append("r240_payload_artifact_invalid_or_missing")
    if not input_summary.get("r238_order_preflight_valid"):
        errors.append("r238_order_preflight_invalid_or_missing")
    if not input_summary.get("r236_lane_arm_valid"):
        errors.append("r236_lane_arm_invalid_or_missing")
    if not input_summary.get("r230_risk_contract_config_found"):
        errors.append("r230_risk_contract_config_write_record_missing")
    if not input_summary.get("risk_contract_valid"):
        errors.append("risk_contract_invalid_or_missing")
    if not input_summary.get("r228_evidence_ready"):
        errors.append("r228_evidence_not_ready")
    if current_risk_model_summary.get("leverage") != CURRENT_LEVERAGE:
        errors.append("current_leverage_not_r230_expected_1x")
    if current_risk_model_summary.get("max_notional_usdt") != CURRENT_MAX_NOTIONAL_USDT:
        errors.append("current_max_notional_not_r230_expected_44")
    if current_risk_model_summary.get("max_loss_usdt") != CURRENT_MAX_LOSS_USDT:
        errors.append("current_max_loss_not_r230_expected_4_44")
    if "quantity_rounds_to_zero" not in (current_risk_model_summary.get("blocked_by") or []):
        warnings.append("current_model_does_not_show_quantity_rounds_to_zero")
    if "min_notional_not_met_after_rounding" not in (current_risk_model_summary.get("blocked_by") or []):
        warnings.append("current_model_does_not_show_min_notional_blocker")
    adjusted = adjusted_model_preview.get("adjusted_model") if isinstance(adjusted_model_preview.get("adjusted_model"), Mapping) else {}
    if adjusted.get("margin_budget_usdt") != ADJUSTED_MARGIN_BUDGET_USDT:
        errors.append("adjusted_margin_budget_not_44")
    if adjusted.get("leverage") != ADJUSTED_LEVERAGE:
        errors.append("adjusted_leverage_not_10")
    if adjusted.get("max_notional_usdt") != ADJUSTED_MAX_NOTIONAL_USDT:
        errors.append("adjusted_max_notional_not_440")
    if adjusted.get("max_position_notional_usdt") != ADJUSTED_MAX_NOTIONAL_USDT:
        errors.append("adjusted_max_position_notional_not_440")
    if adjusted.get("max_loss_requires_review") is not True:
        errors.append("max_loss_requires_review_not_true")
    if adjusted.get("risk_contract_write_required_later") is not True:
        errors.append("risk_contract_write_required_later_not_true")
    if adjusted_quantity_preview.get("can_compute") is not True:
        errors.append("adjusted_quantity_preview_blocked")
    if adjusted_quantity_preview.get("clears_quantity_rounding") is not True:
        errors.append("adjusted_quantity_does_not_clear_rounding")
    if adjusted_quantity_preview.get("clears_min_notional") is not True:
        errors.append("adjusted_quantity_does_not_clear_min_notional")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def build_adjustment_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    current_risk_model_summary: Mapping[str, Any],
    adjusted_model_preview: Mapping[str, Any],
    adjusted_quantity_preview: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    blocked_by: list[str] = []
    if not input_summary.get("r242_readonly_valid"):
        blocked_by.append("r242_readonly_not_ready")
    if not input_summary.get("r240_payload_valid"):
        blocked_by.append("r240_payload_artifact_not_ready")
    if not input_summary.get("r238_order_preflight_valid"):
        blocked_by.append("r238_order_preflight_not_ready")
    if not input_summary.get("r236_lane_arm_valid"):
        blocked_by.append("r236_lane_arm_not_ready")
    if not input_summary.get("risk_contract_valid"):
        blocked_by.append("risk_contract_not_ready")
    if not input_summary.get("r228_evidence_ready"):
        blocked_by.append("r228_evidence_not_ready")
    if adjusted_quantity_preview.get("can_compute") is not True:
        blocked_by.extend(str(item) for item in adjusted_quantity_preview.get("blocked_by") or ["adjusted_quantity_blocked"])
    if validation.get("valid") is not True:
        blocked_by.extend(str(item) for item in validation.get("errors") or ["validation_failed"])
    adjusted = adjusted_model_preview.get("adjusted_model") if isinstance(adjusted_model_preview.get("adjusted_model"), Mapping) else {}
    return {
        "r242_readonly_ready": bool(input_summary.get("r242_readonly_valid")),
        "current_model_blocked": bool(current_risk_model_summary.get("blocked_by")),
        "adjusted_model_preview_ready": bool(adjusted) and adjusted.get("max_loss_requires_review") is True,
        "adjusted_quantity_preview_ready": adjusted_quantity_preview.get("can_compute") is True,
        "clears_binance_minimums": (
            adjusted_quantity_preview.get("clears_quantity_rounding") is True
            and adjusted_quantity_preview.get("clears_min_notional") is True
        ),
        "risk_contract_write_required_later": True,
        "config_written": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blocked_by),
    }


def build_operator_adjustment_review_packet(adjustment_gate_matrix: Mapping[str, Any]) -> dict[str, Any]:
    if adjustment_gate_matrix.get("clears_binance_minimums") is True and not adjustment_gate_matrix.get("blocked_by"):
        action = "REVIEW_R243_ADJUSTMENT_PREVIEW"
    elif adjustment_gate_matrix.get("r242_readonly_ready") is not True:
        action = "WAIT"
    else:
        action = "FIX_BLOCKER"
    return {
        "operator_should_review_adjusted_model": action == "REVIEW_R243_ADJUSTMENT_PREVIEW",
        "operator_should_write_risk_contract_now": False,
        "operator_should_create_executable_payload_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not write risk config from this phase",
            "do not create executable payload",
            "do not call Binance from this phase",
        ],
    }


def classify_tiny_live_leverage_notional_adjustment_preview_status(
    *,
    input_summary: Mapping[str, Any],
    adjustment_validation: Mapping[str, Any],
    adjustment_gate_matrix: Mapping[str, Any],
) -> str:
    if not input_summary.get("r242_readonly_valid"):
        return TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED_BY_R242
    if not input_summary.get("risk_contract_valid"):
        return TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED_BY_RISK_CONTRACT
    if adjustment_validation.get("valid") is not True:
        return TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED_BY_VALIDATION
    if adjustment_gate_matrix.get("clears_binance_minimums") is True:
        return TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_CLEARS_BINANCE_MINIMUMS
    if adjustment_gate_matrix.get("adjusted_quantity_preview_ready") is True:
        return TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_READY_FOR_FUTURE_GATE
    return TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_STILL_BLOCKED


def append_tiny_live_leverage_notional_adjustment_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_leverage_notional_adjustment_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "adjustment_preview_record_id": record.get("adjustment_preview_record_id")
            or f"r243_leverage_notional_adjustment_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDED,
            "generated_at": record.get("generated_at"),
            "adjustment_preview_recorded": True,
            "record_adjustment_preview_requested": True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "current_risk_model_summary": dict(record.get("current_risk_model_summary") or {}),
            "adjusted_leverage_notional_model_preview": dict(
                record.get("adjusted_leverage_notional_model_preview") or {}
            ),
            "binance_precision_mark_price_summary": dict(record.get("binance_precision_mark_price_summary") or {}),
            "adjusted_quantity_preview": dict(record.get("adjusted_quantity_preview") or {}),
            "adjustment_validation": dict(record.get("adjustment_validation") or {}),
            "adjustment_gate_matrix": dict(record.get("adjustment_gate_matrix") or {}),
            "operator_adjustment_review_packet": dict(record.get("operator_adjustment_review_packet") or {}),
            "adjustment_preview_overall_status": record.get("adjustment_preview_overall_status"),
            "future_r244_confirmation_phrase_suggestion": record.get("future_r244_confirmation_phrase_suggestion"),
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


def load_tiny_live_leverage_notional_adjustment_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_leverage_notional_adjustment_preview_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_leverage_notional_adjustment_preview_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_adjustment_preview_recorded": latest.get("adjustment_preview_recorded") is True,
        "latest_overall_status": latest.get("adjustment_preview_overall_status"),
    }


def tiny_live_leverage_notional_adjustment_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_leverage_notional_adjustment_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r242: Mapping[str, Any],
    latest_r240: Mapping[str, Any],
    latest_r238: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_config: Mapping[str, Any],
) -> dict[str, Any]:
    readonly_result = latest_r242.get("binance_readonly_result") if isinstance(latest_r242.get("binance_readonly_result"), Mapping) else {}
    precision = readonly_result.get("precision_snapshot") if isinstance(readonly_result.get("precision_snapshot"), Mapping) else {}
    mark = readonly_result.get("mark_price_snapshot") if isinstance(readonly_result.get("mark_price_snapshot"), Mapping) else {}
    artifact = latest_r240.get("order_payload") if isinstance(latest_r240.get("order_payload"), Mapping) else {}
    order_preflight = latest_r238.get("order_preflight") if isinstance(latest_r238.get("order_preflight"), Mapping) else {}
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    risk_contract = (
        risk_config.get("matching_risk_contract") if isinstance(risk_config.get("matching_risk_contract"), Mapping) else {}
    )
    r228_matrix = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    payload_validation = validate_non_executable_order_payload_artifact(artifact) if artifact else {"valid": False}
    preflight_validation = validate_order_preflight_object(order_preflight) if order_preflight else {"valid": False}
    lane_arm_validation = validate_lane_arm_object(lane_arm) if lane_arm else {"valid": False}
    risk_validation = validate_tiny_live_risk_contract_config_entry(risk_contract) if risk_contract else {"valid": False}
    return {
        "r242_readonly_found": bool(latest_r242),
        "r242_readonly_valid": (
            latest_r242.get("readonly_fetch_performed") is True
            and precision.get("found") is True
            and mark.get("found") is True
        ),
        "precision_snapshot_found": precision.get("found") is True,
        "mark_price_found": mark.get("found") is True,
        "r240_payload_found": bool(latest_r240),
        "r240_payload_valid": payload_validation.get("valid") is True,
        "r238_order_preflight_found": bool(latest_r238),
        "r238_order_preflight_valid": preflight_validation.get("valid") is True,
        "r236_lane_arm_found": bool(latest_r236),
        "r236_lane_arm_valid": lane_arm_validation.get("valid") is True,
        "r230_risk_contract_config_found": bool(latest_r230),
        "risk_contract_valid": risk_validation.get("valid") is True,
        "r228_evidence_ready": r228_matrix.get("evidence_ready") is True,
    }


def _binance_precision_mark_price_summary(latest_r242: Mapping[str, Any]) -> dict[str, Any]:
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
    if matrix.get("clears_binance_minimums") is True and not matrix.get("blocked_by"):
        return "REVIEW_R243_ADJUSTMENT_PREVIEW"
    if matrix.get("r242_readonly_ready") is not True:
        return "WAIT_FOR_R242_READONLY_RESULT"
    return "FIX_R243_BLOCKER"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("clears_binance_minimums") is True and not matrix.get("blocked_by"):
        return "Create R244 guarded risk-contract write gate for the reviewed 44 USDT margin / 10x / 440 USDT notional model; no Binance calls, no executable payload, no order."
    return "Fix R243 input or validation blockers before any R244 risk-contract write gate."


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
        "r242_readonly_found": False,
        "r242_readonly_valid": False,
        "precision_snapshot_found": False,
        "mark_price_found": False,
        "r240_payload_found": False,
        "r240_payload_valid": False,
        "r238_order_preflight_found": False,
        "r238_order_preflight_valid": False,
        "r236_lane_arm_found": False,
        "r236_lane_arm_valid": False,
        "r230_risk_contract_config_found": False,
        "risk_contract_valid": False,
        "r228_evidence_ready": False,
    }


def _empty_current_risk_model_summary() -> dict[str, Any]:
    return {
        "leverage": None,
        "max_notional_usdt": None,
        "max_loss_usdt": None,
        "margin_budget_usdt": None,
        "quantity_raw_at_current_notional": None,
        "quantity_rounded_at_current_notional": None,
        "notional_after_rounding_at_current_notional": None,
        "min_notional_ok_at_current_notional": None,
        "quantity_rounds_to_zero": False,
        "blocked_by": [],
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
            seen.add(text)
            result.append(text)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _float(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
