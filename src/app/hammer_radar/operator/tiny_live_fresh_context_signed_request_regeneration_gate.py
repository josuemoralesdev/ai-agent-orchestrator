"""R253B tiny-live fresh-context signed request regeneration gate.

This gate rebuilds local stop/TP, executable payload, and signed request
artifacts from the latest R253 public-readonly market context. It never calls
Binance/network endpoints, submits, places orders, mutates configs/env/lane
controls, or persists secret values.
"""

from __future__ import annotations

import hmac
import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_executable_payload_write_gate import (
    append_tiny_live_executable_payload_write_gate_record,
    load_tiny_live_executable_payload_write_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_final_readonly_mark_price_refresh_gate import (
    load_tiny_live_final_readonly_mark_price_refresh_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_runtime_credential_source_drill import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
    resolve_runtime_credential_source_path,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_runtime_source_write_gate import (
    load_tiny_live_signed_request_runtime_source_write_gate_records,
    validate_runtime_credential_source_ready,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_write_gate import (
    append_tiny_live_signed_request_write_gate_record,
    load_tiny_live_signed_request_write_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_stop_take_profit_source_gate import (
    append_tiny_live_stop_take_profit_source_gate_record,
    load_adjusted_tiny_live_risk_contract,
    load_tiny_live_stop_take_profit_source_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_submit_readiness_preview import (
    load_tiny_live_submit_readiness_preview_records,
)

TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_READY = (
    "TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_READY"
)
TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_REJECTED = (
    "TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_REJECTED"
)
TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_WRITTEN = (
    "TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_WRITTEN"
)
TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_BLOCKED = (
    "TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_BLOCKED"
)
TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_ERROR = (
    "TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_ERROR"
)

TINY_LIVE_FRESH_CONTEXT_REGENERATION_READY_FOR_CONFIRMATION = (
    "TINY_LIVE_FRESH_CONTEXT_REGENERATION_READY_FOR_CONFIRMATION"
)
TINY_LIVE_FRESH_CONTEXT_REGENERATION_WRITTEN_R254_PREVIEW_REQUIRED = (
    "TINY_LIVE_FRESH_CONTEXT_REGENERATION_WRITTEN_R254_PREVIEW_REQUIRED"
)
TINY_LIVE_FRESH_CONTEXT_REGENERATION_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_FRESH_CONTEXT_REGENERATION_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_R253 = (
    "TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_R253"
)
TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_RISK_VALIDATION = (
    "TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_RISK_VALIDATION"
)
TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_CREDENTIAL_SOURCE = (
    "TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_CREDENTIAL_SOURCE"
)
TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_SECRET_VALIDATION = (
    "TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_SECRET_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE"
LEDGER_FILENAME = "tiny_live_fresh_context_signed_request_regeneration_gate.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE"
CONFIRM_TINY_LIVE_FRESH_CONTEXT_REGENERATION_PHRASE = (
    "I CONFIRM TINY LIVE FRESH CONTEXT SIGNED REQUEST REGENERATION ONLY; "
    "NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL."
)

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_final_readonly_mark_price_refresh_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_submit_readiness_preview.ndjson",
    "logs/hammer_radar_forward/tiny_live_signed_request_runtime_source_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "external_env_file_written": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "fresh_context_signed_request_regeneration_only": True,
    "hmac_signature_created": False,
    "signed_request_written": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "submit_allowed": False,
    "submit_attempted": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "binance_account_endpoint_called": False,
    "binance_exchange_info_endpoint_called": False,
    "binance_mark_price_endpoint_called": False,
    "private_binance_endpoint_called": False,
    "signed_binance_endpoint_called": False,
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "kill_switch_disabled": False,
    "secrets_shown": False,
    "secrets_persisted": False,
    "secret_values_in_output": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
}


def build_tiny_live_fresh_context_signed_request_regeneration_gate(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    regenerate_fresh_context_signed_request: bool = False,
    confirm_tiny_live_fresh_context_regeneration: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_fresh_context_regeneration
        == CONFIRM_TINY_LIVE_FRESH_CONTEXT_REGENERATION_PHRASE
    )
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    try:
        latest_r253 = load_latest_tiny_live_final_readonly_mark_price_refresh_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r252 = load_latest_tiny_live_submit_readiness_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r251e = load_latest_tiny_live_signed_request_runtime_source_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r248 = load_latest_tiny_live_stop_take_profit_source_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r249 = load_latest_tiny_live_executable_payload_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        risk_contract = load_adjusted_tiny_live_risk_contract(
            risk_contract_config_path=risk_contract_config_path,
            official_lane_key=official_lane_key,
        )
        r253_validation = validate_r253_regeneration_required(latest_r253)
        fresh_context = extract_fresh_reference_context_for_regeneration(latest_r253)
        stop_source = build_fresh_stop_take_profit_source(
            fresh_reference_context=fresh_context,
            risk_contract=risk_contract,
            latest_r253=latest_r253,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        stop_validation = validate_fresh_stop_take_profit_source(stop_source)
        executable_payload = build_fresh_executable_payload(
            fresh_stop_take_profit_source=stop_source,
            risk_contract=risk_contract,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        payload_validation = validate_fresh_executable_payload(executable_payload)
        credential_context = validate_runtime_credential_source_ready()
        input_summary = _build_input_summary(
            latest_r253=latest_r253,
            r253_validation=r253_validation,
            latest_r252=latest_r252,
            latest_r251e=latest_r251e,
        )

        signed_artifact: dict[str, Any] = {}
        signed_validation = _empty_signed_validation()
        secret_validation = _empty_secret_validation()
        written = False
        credentials = {"api_key": "", "api_secret": "", "source_type": "none"}

        prewrite_blockers = _prewrite_blockers(
            r253_validation=r253_validation,
            fresh_context=fresh_context,
            stop_validation=stop_validation,
            payload_validation=payload_validation,
        )
        if regenerate_fresh_context_signed_request and not confirmation_valid:
            status = TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_REJECTED
            overall = TINY_LIVE_FRESH_CONTEXT_REGENERATION_REJECTED_BAD_CONFIRMATION
        elif prewrite_blockers:
            status = TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_BLOCKED
            overall = classify_tiny_live_fresh_context_signed_request_regeneration_gate_status(
                r253_validation=r253_validation,
                stop_validation=stop_validation,
                payload_validation=payload_validation,
                credential_context=credential_context,
                secret_validation=secret_validation,
                write_requested=regenerate_fresh_context_signed_request,
                confirmation_valid=confirmation_valid,
                written=False,
            )
        elif regenerate_fresh_context_signed_request and confirmation_valid:
            credentials = resolve_runtime_signing_credentials_for_fresh_regeneration(
                confirm_tiny_live_fresh_context_regeneration=confirm_tiny_live_fresh_context_regeneration
            )
            if not credentials.get("api_key") or not credentials.get("api_secret"):
                status = TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_BLOCKED
                overall = TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_CREDENTIAL_SOURCE
            else:
                signed_artifact = _build_fresh_signed_request_artifact(
                    executable_payload,
                    api_secret=str(credentials["api_secret"]),
                    official_lane_key=official_lane_key,
                    now=generated_at,
                )
                signed_validation = validate_fresh_signed_request_artifact(
                    signed_artifact,
                    raw_api_key=str(credentials["api_key"]),
                    raw_api_secret=str(credentials["api_secret"]),
                )
                secret_validation = validate_no_secret_values_in_fresh_regeneration_artifacts(
                    artifacts=[stop_source, executable_payload, signed_artifact],
                    raw_api_key=str(credentials["api_key"]),
                    raw_api_secret=str(credentials["api_secret"]),
                )
                if signed_validation["valid"] is not True or secret_validation["valid"] is not True:
                    status = TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_BLOCKED
                    overall = TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_SECRET_VALIDATION
                else:
                    _append_child_regeneration_records(
                        log_dir=resolved_log_dir,
                        generated_at=generated_at,
                        official_lane_key=official_lane_key,
                        stop_source=stop_source,
                        stop_validation=stop_validation,
                        executable_payload=executable_payload,
                        payload_validation=payload_validation,
                        signed_artifact=signed_artifact,
                        signed_validation=signed_validation,
                    )
                    written = True
                    status = TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_WRITTEN
                    overall = TINY_LIVE_FRESH_CONTEXT_REGENERATION_WRITTEN_R254_PREVIEW_REQUIRED
        else:
            status = TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_READY
            overall = TINY_LIVE_FRESH_CONTEXT_REGENERATION_READY_FOR_CONFIRMATION

        matrix = build_fresh_regeneration_gate_matrix(
            r253_validation=r253_validation,
            fresh_reference_context=fresh_context,
            stop_validation=stop_validation,
            payload_validation=payload_validation,
            credential_context=credential_context,
            write_confirmed=regenerate_fresh_context_signed_request and confirmation_valid,
            signed_request_written=written,
            secret_validation=secret_validation,
        )
        payload = _base_payload(
            status=status,
            generated_at=generated_at,
            regenerate_requested=regenerate_fresh_context_signed_request,
            confirmation_valid=confirmation_valid,
            written=written,
            official_lane_key=official_lane_key,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            input_summary=input_summary,
            fresh_context=fresh_context,
            stop_source=stop_source,
            stop_validation=stop_validation,
            executable_payload=executable_payload,
            payload_validation=payload_validation,
            signed_artifact=signed_artifact,
            signed_validation=signed_validation,
            secret_validation=secret_validation,
            matrix=matrix,
            overall=overall,
        )
        if written:
            payload = append_tiny_live_fresh_context_signed_request_regeneration_gate_record(
                payload,
                log_dir=resolved_log_dir,
            )
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_fresh_regeneration_gate_matrix(
            r253_validation={"valid": False, "errors": ["r253b_error"], "regeneration_required": False},
            fresh_reference_context={},
            stop_validation={"valid": False, "errors": ["r253b_error"], "warnings": []},
            payload_validation={"valid": False, "errors": ["r253b_error"], "warnings": []},
            credential_context={"credential_source_ready": False},
            write_confirmed=False,
            signed_request_written=False,
            secret_validation=_empty_secret_validation(),
        )
        return _sanitize(
            _base_payload(
                status=TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_ERROR,
                generated_at=generated_at,
                regenerate_requested=regenerate_fresh_context_signed_request,
                confirmation_valid=confirmation_valid,
                written=False,
                official_lane_key=official_lane_key,
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                input_summary=_empty_input_summary(),
                fresh_context={},
                stop_source={},
                stop_validation={"valid": False, "errors": ["r253b_error"], "warnings": []},
                executable_payload={},
                payload_validation={"valid": False, "errors": ["r253b_error"], "warnings": []},
                signed_artifact={},
                signed_validation=_empty_signed_validation(),
                secret_validation=_empty_secret_validation(),
                matrix=matrix,
                overall=UNKNOWN_NEEDS_MANUAL_REVIEW,
                error=exc.__class__.__name__,
            )
        )


def load_latest_tiny_live_final_readonly_mark_price_refresh_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_final_readonly_mark_price_refresh_gate_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_submit_readiness_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_submit_readiness_preview_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_signed_request_runtime_source_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_signed_request_runtime_source_write_gate_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_stop_take_profit_source_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_stop_take_profit_source_gate_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_executable_payload_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_executable_payload_write_gate_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def validate_r253_regeneration_required(record: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    decision = record.get("signed_request_regeneration_decision")
    decision = decision if isinstance(decision, Mapping) else {}
    matrix = record.get("final_readonly_refresh_gate_matrix")
    matrix = matrix if isinstance(matrix, Mapping) else {}
    comparison = record.get("fresh_vs_signed_context_comparison")
    comparison = comparison if isinstance(comparison, Mapping) else {}
    safety = record.get("safety")
    safety = safety if isinstance(safety, Mapping) else {}
    if not record:
        errors.append("r253_final_readonly_missing")
    if decision.get("must_regenerate_signed_request_before_submit") is not True:
        errors.append("r253_regeneration_not_required")
    if matrix.get("fresh_context_compatible_with_signed_artifact") is not False:
        errors.append("r253_fresh_context_not_marked_incompatible")
    if decision.get("submit_gate_preview_allowed_next") is not False:
        errors.append("r253_submit_gate_preview_not_blocked")
    if safety.get("submit_allowed") is not False:
        errors.append("r253_submit_allowed_not_false")
    if safety.get("order_placed") is not False:
        errors.append("r253_order_placed_not_false")
    if comparison.get("fresh_mark_price") in (None, ""):
        errors.append("r253_fresh_mark_price_missing")
    return {
        "valid": not errors,
        "regeneration_required": "r253_regeneration_not_required" not in errors and bool(record),
        "fresh_market_context_ready": matrix.get("fresh_market_context_ready") is True,
        "old_signed_artifact_stale": matrix.get("fresh_context_compatible_with_signed_artifact") is False,
        "errors": _dedupe(errors),
        "warnings": [],
    }


def extract_fresh_reference_context_for_regeneration(record: Mapping[str, Any]) -> dict[str, Any]:
    fresh = record.get("fresh_market_context_summary")
    fresh = fresh if isinstance(fresh, Mapping) else {}
    mark = _number(fresh.get("mark_price"))
    return _sanitize(
        {
            "reference_price": mark,
            "fresh_mark_price_source_phase": "R253",
            "tick_size": _number(fresh.get("tick_size")),
            "step_size": _number(fresh.get("step_size")),
            "min_notional": _number(fresh.get("min_notional")),
            "price_precision": fresh.get("price_precision"),
            "quantity_precision": fresh.get("quantity_precision"),
            "source_r253_record_id": record.get("final_readonly_refresh_gate_record_id"),
        }
    )


def build_fresh_stop_take_profit_source(
    *,
    fresh_reference_context: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    latest_r253: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    reference = _number(fresh_reference_context.get("reference_price"))
    quantity_plan = compute_fresh_contract_fit_quantity(
        reference_price=reference,
        max_notional_usdt=risk_contract.get("max_notional_usdt")
        or risk_contract.get("max_position_notional_usdt"),
        step_size=fresh_reference_context.get("step_size"),
        min_notional=fresh_reference_context.get("min_notional"),
        default_quantity=risk_contract.get("target_quantity") or 0.007,
    )
    quantity = _number(quantity_plan.get("quantity")) or 0.0
    max_loss = _number(risk_contract.get("max_loss_usdt")) or 4.44
    rr = _number(risk_contract.get("risk_reward_ratio")) or 2.0
    tick = _number(fresh_reference_context.get("tick_size")) or 0.1
    risk_distance = max_loss / quantity if quantity else 0.0
    raw_stop = (reference + risk_distance) if reference is not None else None
    raw_tp = (reference - (risk_distance * rr)) if reference is not None else None
    stop = _round_price(raw_stop, tick)
    tp = _round_price(raw_tp, tick)
    loss = max((stop - reference) * quantity, 0) if None not in (reference, stop) else None
    reward = max((reference - tp) * quantity, 0) if None not in (reference, tp) else None
    ratio = reward / loss if loss and reward is not None else None
    return _sanitize(
        {
            "stop_take_profit_source_id": f"r253b_stop_take_profit_source_{symbol}_{timeframe}_{direction}_{entry_mode}_{uuid4().hex}",
            "artifact_only": True,
            "created_by_phase": CREATED_BY_PHASE,
            "created_at": generated_at.isoformat(),
            "source_mode": "R253_FRESH_MARK_PRICE_REGENERATION",
            "reference_price_source": "R253_FINAL_READONLY_MARK_PRICE_REFRESH_GATE",
            "source_r253_final_readonly_record_id": latest_r253.get("final_readonly_refresh_gate_record_id"),
            "official_lane_key": official_lane_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": entry_mode,
            "quantity": quantity,
            "quantity_sizing_plan": quantity_plan,
            "reference_price": reference,
            "entry_reference_price": reference,
            "price_risk_distance": risk_distance,
            "raw_stop_price": raw_stop,
            "raw_take_profit_price": raw_tp,
            "rounded_stop_price": stop,
            "rounded_take_profit_price": tp,
            "stop_price": stop,
            "take_profit_price": tp,
            "final_stop_price": stop,
            "final_take_profit_price": tp,
            "stop_side": "BUY",
            "take_profit_side": "BUY",
            "reduce_only": True,
            "tick_size": tick,
            "step_size": fresh_reference_context.get("step_size"),
            "min_notional": fresh_reference_context.get("min_notional"),
            "price_precision": fresh_reference_context.get("price_precision"),
            "quantity_precision": fresh_reference_context.get("quantity_precision"),
            "max_loss_usdt": max_loss,
            "estimated_loss_at_stop_usdt": loss,
            "estimated_reward_at_take_profit_usdt": reward,
            "risk_reward_ratio": ratio,
            "notional_after_rounding": reference * quantity if reference is not None else None,
            "risk_contract": {
                "margin_budget_usdt": risk_contract.get("margin_budget_usdt"),
                "tiny_live_margin_usdt": risk_contract.get("tiny_live_margin_usdt"),
                "leverage": risk_contract.get("leverage"),
                "max_notional_usdt": risk_contract.get("max_notional_usdt"),
                "max_position_notional_usdt": risk_contract.get("max_position_notional_usdt"),
                "max_loss_usdt": risk_contract.get("max_loss_usdt"),
                "risk_reward_ratio": risk_contract.get("risk_reward_ratio"),
            },
            "stop_payload_source": {
                "side": "BUY",
                "order_type": "STOP_MARKET",
                "stop_price": stop,
                "reduce_only": True,
                "signed": False,
                "executable": False,
            },
            "take_profit_payload_source": {
                "side": "BUY",
                "order_type": "TAKE_PROFIT_MARKET",
                "take_profit_price": tp,
                "reduce_only": True,
                "signed": False,
                "executable": False,
            },
            "network_allowed": False,
            "submit_allowed": False,
            "order_placed": False,
        }
    )


def validate_fresh_stop_take_profit_source(source: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    reference = _number(source.get("reference_price"))
    stop = _number(source.get("stop_price"))
    tp = _number(source.get("take_profit_price"))
    quantity = _number(source.get("quantity"))
    step = _number(source.get("step_size")) or 0.001
    min_notional = _number(source.get("min_notional")) or 50.0
    notional = _number(source.get("notional_after_rounding"))
    max_loss = _number(source.get("max_loss_usdt"))
    loss = _number(source.get("estimated_loss_at_stop_usdt"))
    ratio = _number(source.get("risk_reward_ratio"))
    if reference is None or reference <= 0:
        errors.append("reference_price_invalid")
    if stop is None or reference is None or stop <= reference:
        errors.append("short_stop_price_must_be_above_fresh_mark")
    if tp is None or reference is None or tp >= reference:
        errors.append("short_take_profit_price_must_be_below_fresh_mark")
    if quantity is None or quantity <= 0:
        errors.append("quantity_invalid")
    elif not _multiple_of_step(quantity, step):
        errors.append("quantity_step_invalid")
    if notional is None or notional < min_notional:
        errors.append("min_notional_invalid")
    max_notional = _number((source.get("risk_contract") or {}).get("max_notional_usdt")) if isinstance(source.get("risk_contract"), Mapping) else None
    if max_notional is not None and notional is not None and notional > max_notional:
        errors.append("notional_after_rounding_exceeds_contract_max_notional")
    tolerance = max(0.01, (_number(source.get("tick_size")) or 0.1) * (quantity or 0))
    if loss is None or max_loss is None or loss > max_loss + tolerance:
        errors.append("estimated_loss_at_stop_usdt_exceeds_tolerance")
    if ratio is None or abs(ratio - 2.0) > 0.05:
        errors.append("risk_reward_ratio_invalid")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def build_fresh_executable_payload(
    *,
    fresh_stop_take_profit_source: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    quantity = _number(fresh_stop_take_profit_source.get("quantity"))
    return _sanitize(
        {
            "executable_payload_id": f"r253b_executable_payload_{symbol}_{timeframe}_{direction}_{entry_mode}_{uuid4().hex}",
            "artifact_only": True,
            "created_by_phase": CREATED_BY_PHASE,
            "created_at": generated_at.isoformat(),
            "official_lane_key": official_lane_key,
            "exchange": "binance_futures",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": entry_mode,
            "reference_price": fresh_stop_take_profit_source.get("reference_price"),
            "main_order": {
                "symbol": symbol,
                "side": "SELL",
                "type": "MARKET",
                "quantity": quantity,
                "reduceOnly": False,
                "positionSide": "BOTH|SHORT|null",
            },
            "stop_order": {
                "symbol": symbol,
                "side": "BUY",
                "type": "STOP_MARKET",
                "stopPrice": fresh_stop_take_profit_source.get("stop_price"),
                "quantity": quantity,
                "reduceOnly": True,
                "workingType": "MARK_PRICE",
            },
            "take_profit_order": {
                "symbol": symbol,
                "side": "BUY",
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": fresh_stop_take_profit_source.get("take_profit_price"),
                "quantity": quantity,
                "reduceOnly": True,
                "workingType": "MARK_PRICE",
            },
            "risk": {
                "margin_budget_usdt": risk_contract.get("margin_budget_usdt"),
                "tiny_live_margin_usdt": risk_contract.get("tiny_live_margin_usdt"),
                "leverage": risk_contract.get("leverage"),
                "max_notional_usdt": risk_contract.get("max_notional_usdt"),
                "max_position_notional_usdt": risk_contract.get("max_position_notional_usdt"),
                "notional_after_rounding": fresh_stop_take_profit_source.get("notional_after_rounding"),
                "max_loss_usdt": fresh_stop_take_profit_source.get("max_loss_usdt"),
                "estimated_loss_at_stop_usdt": fresh_stop_take_profit_source.get("estimated_loss_at_stop_usdt"),
                "estimated_reward_at_take_profit_usdt": fresh_stop_take_profit_source.get("estimated_reward_at_take_profit_usdt"),
                "risk_reward_ratio": fresh_stop_take_profit_source.get("risk_reward_ratio"),
                "max_loss_requires_review": risk_contract.get("max_loss_requires_review") is True,
                "tick_size": fresh_stop_take_profit_source.get("tick_size"),
            },
            "source_refs": {
                "r253b_stop_take_profit_source_id": fresh_stop_take_profit_source.get("stop_take_profit_source_id"),
                "r253_final_readonly_record_id": fresh_stop_take_profit_source.get("source_r253_final_readonly_record_id"),
            },
            "controls": {
                "signed": False,
                "submit_allowed": False,
                "binance_call_allowed": False,
                "network_allowed": False,
                "requires_signature_gate": False,
                "requires_submit_gate": True,
                "requires_operator_final_submit_confirmation": True,
                "kill_switch_required": True,
            },
            "safety": {
                "executable_payload_created": True,
                "signed_order_request_created": False,
                "signed_trading_request_created": False,
                "submit_allowed": False,
                "order_placed": False,
                "binance_order_endpoint_called": False,
                "network_allowed": False,
            },
        }
    )


def validate_fresh_executable_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    main = payload.get("main_order") if isinstance(payload.get("main_order"), Mapping) else {}
    stop = payload.get("stop_order") if isinstance(payload.get("stop_order"), Mapping) else {}
    tp = payload.get("take_profit_order") if isinstance(payload.get("take_profit_order"), Mapping) else {}
    controls = payload.get("controls") if isinstance(payload.get("controls"), Mapping) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    reference = _number(payload.get("reference_price"))
    quantity = _number(main.get("quantity"))
    if main.get("side") != "SELL" or main.get("type") != "MARKET":
        errors.append("main_order_shape_invalid")
    if quantity is None or quantity <= 0:
        errors.append("quantity_invalid")
    if stop.get("side") != "BUY" or stop.get("type") != "STOP_MARKET" or stop.get("reduceOnly") is not True:
        errors.append("stop_order_shape_invalid")
    if tp.get("side") != "BUY" or tp.get("type") != "TAKE_PROFIT_MARKET" or tp.get("reduceOnly") is not True:
        errors.append("take_profit_order_shape_invalid")
    if _number(stop.get("quantity")) != quantity or _number(tp.get("quantity")) != quantity:
        errors.append("protective_quantity_mismatch")
    if reference is None or _number(stop.get("stopPrice")) is None or _number(stop.get("stopPrice")) <= reference:
        errors.append("short_stop_price_must_be_above_reference_price")
    if reference is None or _number(tp.get("stopPrice")) is None or _number(tp.get("stopPrice")) >= reference:
        errors.append("short_take_profit_price_must_be_below_reference_price")
    for key in ("signed", "submit_allowed", "binance_call_allowed", "network_allowed"):
        if controls.get(key) is not False:
            errors.append(f"controls_{key}_invalid")
    for key in ("signed_order_request_created", "signed_trading_request_created", "submit_allowed", "order_placed", "binance_order_endpoint_called", "network_allowed"):
        if safety.get(key) is not False:
            errors.append(f"safety_{key}_invalid")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": []}


def compute_fresh_contract_fit_quantity(
    *,
    reference_price: Any,
    max_notional_usdt: Any,
    step_size: Any,
    min_notional: Any,
    default_quantity: Any = 0.007,
) -> dict[str, Any]:
    reference = _decimal(reference_price)
    max_notional = _decimal(max_notional_usdt)
    step = _decimal(step_size) or Decimal("0.001")
    min_notional_dec = _decimal(min_notional) or Decimal("5")
    default_qty = _decimal(default_quantity) or Decimal("0.007")
    blockers: list[str] = []
    if reference is None or reference <= 0:
        blockers.append("reference_price_invalid")
    if max_notional is None or max_notional <= 0:
        blockers.append("max_notional_invalid")
    if step <= 0:
        blockers.append("step_size_invalid")
    if blockers:
        return {
            "quantity": None,
            "default_quantity": _float(default_qty),
            "max_notional_usdt": _float(max_notional),
            "candidate_notional_usdt": None,
            "fits_max_notional": False,
            "fits_binance_step_size": False,
            "fits_binance_min_notional": False,
            "blocked_by": blockers,
        }
    max_qty_by_notional = (max_notional / reference).quantize(step, rounding=ROUND_FLOOR)
    default_stepped = (default_qty / step).to_integral_value(rounding=ROUND_FLOOR) * step
    quantity = min(default_stepped, max_qty_by_notional)
    notional = reference * quantity
    return {
        "quantity": _float(quantity),
        "default_quantity": _float(default_qty),
        "max_quantity_by_notional": _float(max_qty_by_notional),
        "quantity_reduced_to_fit_contract": bool(quantity < default_stepped),
        "max_notional_usdt": _float(max_notional),
        "candidate_notional_usdt": _float(notional.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
        "fits_max_notional": bool(notional <= max_notional),
        "fits_binance_step_size": bool(quantity > 0 and (quantity % step) == 0),
        "fits_binance_min_notional": bool(notional >= min_notional_dec),
        "blocked_by": [] if quantity > 0 and notional <= max_notional and notional >= min_notional_dec else [
            reason
            for reason, blocked in (
                ("quantity_zero_after_contract_fit", quantity <= 0),
                ("notional_exceeds_max_notional", notional > max_notional),
                ("notional_below_min_notional", notional < min_notional_dec),
            )
            if blocked
        ],
    }


def resolve_runtime_signing_credentials_for_fresh_regeneration(
    *,
    confirm_tiny_live_fresh_context_regeneration: str | None,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    if confirm_tiny_live_fresh_context_regeneration != CONFIRM_TINY_LIVE_FRESH_CONTEXT_REGENERATION_PHRASE:
        return {"api_key": "", "api_secret": "", "source_type": "none"}
    source_env = env if env is not None else os.environ
    context = validate_runtime_credential_source_ready(env=source_env)
    if context.get("source_type") == "process_env":
        return {
            "api_key": source_env.get(BINANCE_API_KEY_ENV, ""),
            "api_secret": source_env.get(BINANCE_API_SECRET_ENV, ""),
            "source_type": "process_env",
        }
    if context.get("source_type") == "external_env_file":
        values = _read_external_env_file_values(resolve_runtime_credential_source_path(source_env))
        return {
            "api_key": values.get(BINANCE_API_KEY_ENV, ""),
            "api_secret": values.get(BINANCE_API_SECRET_ENV, ""),
            "source_type": "external_env_file",
        }
    return {"api_key": "", "api_secret": "", "source_type": "none"}


def write_fresh_signed_request_artifact(
    *,
    executable_payload: Mapping[str, Any],
    api_secret: str,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    return _build_fresh_signed_request_artifact(
        executable_payload,
        api_secret=api_secret,
        official_lane_key=official_lane_key,
        now=now,
    )


def validate_fresh_signed_request_artifact(
    artifact: Mapping[str, Any],
    *,
    raw_api_key: str | None = None,
    raw_api_secret: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    signed_requests = artifact.get("signed_requests") if isinstance(artifact.get("signed_requests"), Mapping) else {}
    if set(signed_requests) != {"main_order", "stop_order", "take_profit_order"}:
        errors.append("signed_requests_keys_invalid")
    text = json.dumps(artifact, sort_keys=True, separators=(",", ":"), default=str)
    if raw_api_key and raw_api_key in text:
        errors.append("raw_api_key_persisted")
    if raw_api_secret and raw_api_secret in text:
        errors.append("raw_api_secret_persisted")
    for key in ("main_order", "stop_order", "take_profit_order"):
        request = signed_requests.get(key) if isinstance(signed_requests.get(key), Mapping) else {}
        if request.get("method") != "POST" or request.get("endpoint") != "/fapi/v1/order":
            errors.append(f"{key}_endpoint_invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", str(request.get("signature") or "")):
            errors.append(f"{key}_signature_invalid")
        if request.get("submit_allowed") is not False or request.get("network_allowed") is not False:
            errors.append(f"{key}_controls_invalid")
        query = str(request.get("query_string_without_signature") or "")
        if "signature=" in query:
            errors.append(f"{key}_query_contains_signature")
        if raw_api_key and raw_api_key in query:
            errors.append(f"{key}_query_contains_api_key")
        if raw_api_secret and raw_api_secret in query:
            errors.append(f"{key}_query_contains_api_secret")
    controls = artifact.get("controls") if isinstance(artifact.get("controls"), Mapping) else {}
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), Mapping) else {}
    for key in ("submit_allowed", "binance_call_allowed", "network_allowed"):
        if controls.get(key) is not False:
            errors.append(f"controls_{key}_invalid")
    for key in ("submit_allowed", "order_placed", "binance_order_endpoint_called", "network_allowed", "secrets_shown", "secrets_persisted"):
        if safety.get(key) is not False:
            errors.append(f"safety_{key}_invalid")
    for key in ("hmac_signature_created", "signed_order_request_created", "signed_trading_request_created"):
        if safety.get(key) is not True:
            errors.append(f"safety_{key}_invalid")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": []}


def validate_no_secret_values_in_fresh_regeneration_artifacts(
    *,
    artifacts: Sequence[Mapping[str, Any]],
    raw_api_key: str | None = None,
    raw_api_secret: str | None = None,
) -> dict[str, Any]:
    text = json.dumps(list(artifacts), sort_keys=True, separators=(",", ":"), default=str)
    raw_api_key_found = bool(raw_api_key and raw_api_key in text)
    raw_api_secret_found = bool(raw_api_secret and raw_api_secret in text)
    errors: list[str] = []
    if raw_api_key_found:
        errors.append("raw_api_key_found_in_artifacts")
    if raw_api_secret_found:
        errors.append("raw_api_secret_found_in_artifacts")
    return {
        "valid": not errors,
        "raw_api_key_found_in_artifacts": raw_api_key_found,
        "raw_api_secret_found_in_artifacts": raw_api_secret_found,
        "secret_values_in_output": bool(errors),
        "errors": errors,
        "warnings": [],
    }


def build_fresh_regeneration_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "fresh_context_regeneration_written": payload.get("fresh_context_regeneration_written") is True,
        "fresh_regeneration_overall_status": payload.get("fresh_regeneration_overall_status"),
    }


def build_fresh_regeneration_gate_matrix(
    *,
    r253_validation: Mapping[str, Any],
    fresh_reference_context: Mapping[str, Any],
    stop_validation: Mapping[str, Any],
    payload_validation: Mapping[str, Any],
    credential_context: Mapping[str, Any],
    write_confirmed: bool,
    signed_request_written: bool,
    secret_validation: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if r253_validation.get("valid") is not True:
        blockers.extend(str(item) for item in r253_validation.get("errors") or ["r253_not_ready"])
    if _number(fresh_reference_context.get("reference_price")) is None:
        blockers.append("fresh_reference_context_missing")
    if stop_validation.get("valid") is not True:
        blockers.extend(str(item) for item in stop_validation.get("errors") or ["fresh_stop_take_profit_invalid"])
    if payload_validation.get("valid") is not True:
        blockers.extend(str(item) for item in payload_validation.get("errors") or ["fresh_payload_invalid"])
    if credential_context.get("credential_source_ready") is not True:
        blockers.append("runtime_credential_source_not_ready")
    if not write_confirmed:
        blockers.append("exact_fresh_context_regeneration_confirmation_required")
    if signed_request_written and secret_validation.get("valid") is True:
        blockers = ["r254_submit_gate_preview_required", "submit_still_forbidden"]
    elif write_confirmed and secret_validation.get("valid") is not True:
        blockers.extend(str(item) for item in secret_validation.get("errors") or ["secret_validation_not_passed"])
    return {
        "r253_regeneration_required": r253_validation.get("regeneration_required") is True,
        "fresh_reference_context_ready": _number(fresh_reference_context.get("reference_price")) is not None,
        "fresh_stop_take_profit_valid": stop_validation.get("valid") is True,
        "fresh_payload_valid": payload_validation.get("valid") is True,
        "runtime_credential_source_ready": credential_context.get("credential_source_ready") is True,
        "write_confirmed": bool(write_confirmed),
        "fresh_signed_request_written": bool(signed_request_written),
        "secret_validation_passed": secret_validation.get("valid") is True,
        "submit_allowed": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_fresh_regeneration_packet(matrix: Mapping[str, Any]) -> dict[str, Any]:
    written = matrix.get("fresh_signed_request_written") is True
    ready = (
        matrix.get("r253_regeneration_required") is True
        and matrix.get("fresh_reference_context_ready") is True
        and matrix.get("fresh_stop_take_profit_valid") is True
        and matrix.get("fresh_payload_valid") is True
        and matrix.get("runtime_credential_source_ready") is True
    )
    if written:
        action = "CONTINUE_TO_R254_SUBMIT_GATE_PREVIEW"
    elif ready:
        action = "CONFIRM_R253B_REGENERATION"
    elif matrix.get("blocked_by"):
        action = "FIX_BLOCKER"
    else:
        action = "WAIT"
    return {
        "operator_should_review_fresh_regenerated_artifacts": bool(ready or written),
        "operator_should_continue_to_r254_submit_gate_preview": bool(written),
        "operator_should_submit_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not submit",
            "do not call Binance order endpoint from this phase",
        ],
    }


def classify_tiny_live_fresh_context_signed_request_regeneration_gate_status(
    *,
    r253_validation: Mapping[str, Any],
    stop_validation: Mapping[str, Any],
    payload_validation: Mapping[str, Any],
    credential_context: Mapping[str, Any],
    secret_validation: Mapping[str, Any],
    write_requested: bool,
    confirmation_valid: bool,
    written: bool,
) -> str:
    if write_requested and not confirmation_valid:
        return TINY_LIVE_FRESH_CONTEXT_REGENERATION_REJECTED_BAD_CONFIRMATION
    if written:
        return TINY_LIVE_FRESH_CONTEXT_REGENERATION_WRITTEN_R254_PREVIEW_REQUIRED
    if r253_validation.get("valid") is not True:
        return TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_R253
    if stop_validation.get("valid") is not True or payload_validation.get("valid") is not True:
        return TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_RISK_VALIDATION
    if write_requested and credential_context.get("credential_source_ready") is not True:
        return TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_CREDENTIAL_SOURCE
    if write_requested and secret_validation.get("valid") is not True:
        return TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_SECRET_VALIDATION
    return TINY_LIVE_FRESH_CONTEXT_REGENERATION_READY_FOR_CONFIRMATION


def append_tiny_live_fresh_context_signed_request_regeneration_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_fresh_context_signed_request_regeneration_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "fresh_regeneration_gate_record_id": record.get("fresh_regeneration_gate_record_id")
            or f"r253b_fresh_regeneration_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "safety": dict(record.get("safety") or _safety(record.get("fresh_context_regeneration_written") is True)),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_fresh_context_signed_request_regeneration_gate_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_fresh_context_signed_request_regeneration_gate_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_fresh_context_signed_request_regeneration_gate_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_written": latest.get("fresh_context_regeneration_written") is True,
        "latest_overall_status": latest.get("fresh_regeneration_overall_status"),
    }


def tiny_live_fresh_context_signed_request_regeneration_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_fresh_context_signed_request_regeneration_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _append_child_regeneration_records(
    *,
    log_dir: str | Path,
    generated_at: datetime,
    official_lane_key: str,
    stop_source: Mapping[str, Any],
    stop_validation: Mapping[str, Any],
    executable_payload: Mapping[str, Any],
    payload_validation: Mapping[str, Any],
    signed_artifact: Mapping[str, Any],
    signed_validation: Mapping[str, Any],
) -> None:
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    target = _target_scope(official_lane_key)
    append_tiny_live_stop_take_profit_source_gate_record(
        {
            "status": "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_WRITTEN",
            "generated_at": generated_at.isoformat(),
            "stop_take_profit_source_preview_recorded": True,
            "record_stop_take_profit_source_preview_requested": True,
            "confirmation_valid": True,
            "target_scope": {**target, "created_by_phase": CREATED_BY_PHASE},
            "selected_stop_take_profit_source": {
                "source_name": "r253b_fresh_context_regeneration",
                "source_record_id": stop_source.get("source_r253_final_readonly_record_id"),
                "entry_reference_price": stop_source.get("reference_price"),
                "raw_stop_price": stop_source.get("raw_stop_price"),
                "raw_take_profit_price": stop_source.get("raw_take_profit_price"),
                "rounded_stop_price": stop_source.get("stop_price"),
                "rounded_take_profit_price": stop_source.get("take_profit_price"),
                "source_valid": stop_validation.get("valid") is True,
                "blocked_by": stop_validation.get("errors") or [],
            },
            "stop_take_profit_source_preview": dict(stop_source),
            "stop_take_profit_source": dict(stop_source),
            "stop_take_profit_validation": dict(stop_validation),
            "safety": _safety(False),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        },
        log_dir=log_dir,
    )
    append_tiny_live_executable_payload_write_gate_record(
        {
            "status": "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_WRITTEN",
            "generated_at": generated_at.isoformat(),
            "executable_payload_written": True,
            "write_executable_payload_requested": True,
            "confirmation_valid": True,
            "target_scope": {**target, "created_by_phase": CREATED_BY_PHASE},
            "executable_payload_artifact": dict(executable_payload),
            "payload_artifact_validation": dict(payload_validation),
            "safety": {**_safety(False), "executable_payload_created": True, "executable_payload_written": True},
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        },
        log_dir=log_dir,
    )
    append_tiny_live_signed_request_write_gate_record(
        {
            "status": "TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_WRITTEN",
            "generated_at": generated_at.isoformat(),
            "signed_request_written": True,
            "write_signed_request_requested": True,
            "confirmation_valid": True,
            "target_scope": {
                **target,
                "symbol": symbol,
                "timeframe": timeframe,
                "direction": direction,
                "entry_mode": entry_mode,
                "created_by_phase": CREATED_BY_PHASE,
            },
            "signed_request_artifact": dict(signed_artifact),
            "signed_request_validation": dict(signed_validation),
            "post_write_verification": {
                "signed_request_written": True,
                "matching_signed_request_found": True,
                "matching_signed_request_valid": True,
                "submit_allowed": False,
                "order_placed": False,
                "binance_call_allowed": False,
                "network_allowed": False,
                "secrets_shown": False,
                "secrets_persisted": False,
            },
            "safety": _safety(True),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        },
        log_dir=log_dir,
    )


def _base_payload(
    *,
    status: str,
    generated_at: datetime,
    regenerate_requested: bool,
    confirmation_valid: bool,
    written: bool,
    official_lane_key: str,
    symbol: str,
    timeframe: str,
    direction: str,
    input_summary: Mapping[str, Any],
    fresh_context: Mapping[str, Any],
    stop_source: Mapping[str, Any],
    stop_validation: Mapping[str, Any],
    executable_payload: Mapping[str, Any],
    payload_validation: Mapping[str, Any],
    signed_artifact: Mapping[str, Any],
    signed_validation: Mapping[str, Any],
    secret_validation: Mapping[str, Any],
    matrix: Mapping[str, Any],
    overall: str,
    error: str | None = None,
) -> dict[str, Any]:
    stop_summary = _stop_summary(stop_source, stop_validation, written)
    payload_summary = _payload_summary(executable_payload, payload_validation, written)
    signed_summary = _signed_summary(signed_artifact, written)
    operator_packet = build_operator_fresh_regeneration_packet(matrix)
    safety = _safety(written)
    payload = {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "regenerate_fresh_context_signed_request_requested": bool(regenerate_requested),
        "confirmation_valid": bool(confirmation_valid),
        "fresh_context_regeneration_written": bool(written),
        "target_scope": {
            "official_lane_key": official_lane_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "fresh_context_signed_request_regeneration_only": True,
            "submit_allowed": False,
            "order_placed": False,
            "binance_order_endpoint_called": False,
            "network_allowed": False,
        },
        "input_summary": dict(input_summary),
        "fresh_reference_context": _fresh_context_summary(fresh_context),
        "fresh_stop_take_profit_source": stop_summary,
        "fresh_executable_payload_summary": payload_summary,
        "fresh_signed_request_artifact_summary": signed_summary,
        "secret_validation": dict(secret_validation),
        "fresh_regeneration_gate_matrix": dict(matrix),
        "operator_fresh_regeneration_packet": operator_packet,
        "recommended_next_operator_move": _recommended_next_operator_move(operator_packet),
        "recommended_next_engineering_move": _recommended_next_engineering_move(written, matrix),
        "fresh_regeneration_overall_status": overall,
        "do_not_run_yet": _do_not_run_yet(),
        "safety": safety,
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }
    if error:
        payload["error"] = error
    return _sanitize(payload)


def _build_fresh_signed_request_artifact(
    executable_payload: Mapping[str, Any],
    *,
    api_secret: str,
    official_lane_key: str,
    now: datetime | None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    timestamp = str(int(generated_at.timestamp() * 1000))
    main = executable_payload.get("main_order") if isinstance(executable_payload.get("main_order"), Mapping) else {}
    stop = executable_payload.get("stop_order") if isinstance(executable_payload.get("stop_order"), Mapping) else {}
    tp = executable_payload.get("take_profit_order") if isinstance(executable_payload.get("take_profit_order"), Mapping) else {}
    unsigned = {
        "main_order": {
            "symbol": symbol,
            "side": main.get("side"),
            "type": main.get("type"),
            "quantity": _format_decimal(main.get("quantity")),
            "timestamp": timestamp,
        },
        "stop_order": {
            "symbol": symbol,
            "side": stop.get("side"),
            "type": stop.get("type"),
            "quantity": _format_decimal(stop.get("quantity")),
            "stopPrice": _format_decimal(stop.get("stopPrice")),
            "reduceOnly": "true",
            "workingType": stop.get("workingType") or "MARK_PRICE",
            "timestamp": timestamp,
        },
        "take_profit_order": {
            "symbol": symbol,
            "side": tp.get("side"),
            "type": tp.get("type"),
            "quantity": _format_decimal(tp.get("quantity")),
            "stopPrice": _format_decimal(tp.get("stopPrice")),
            "reduceOnly": "true",
            "workingType": tp.get("workingType") or "MARK_PRICE",
            "timestamp": timestamp,
        },
    }
    signed_requests: dict[str, Any] = {}
    for key, params in unsigned.items():
        query = urlencode([(str(k), str(v)) for k, v in params.items() if v not in (None, "")], doseq=False, safe="")
        signed_requests[key] = {
            "method": "POST",
            "endpoint": "/fapi/v1/order",
            "query_string_without_signature": query,
            "signature": hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), sha256).hexdigest(),
            "signed": True,
            "submit_allowed": False,
            "network_allowed": False,
        }
    return _sanitize(
        {
            "signed_request_artifact_id": f"r253b_signed_request_{symbol}_{timeframe}_{direction}_{entry_mode}_{uuid4().hex}",
            "artifact_only": True,
            "created_by_phase": CREATED_BY_PHASE,
            "created_at": generated_at.isoformat(),
            "official_lane_key": official_lane_key,
            "exchange": "binance_futures",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": entry_mode,
            "source_executable_payload_id": executable_payload.get("executable_payload_id"),
            "credential_context": {
                "api_key_present": True,
                "api_secret_present": True,
                "api_key_hint": "<PRESENT_REDACTED>",
                "api_secret_persisted": False,
                "secrets_printed": False,
                "secrets_persisted": False,
            },
            "signed_requests": signed_requests,
            "controls": {
                "signed_request_written": True,
                "submit_allowed": False,
                "binance_call_allowed": False,
                "network_allowed": False,
                "requires_submit_gate": True,
                "requires_operator_final_submit_confirmation": True,
                "kill_switch_required": True,
            },
            "safety": {
                "hmac_signature_created": True,
                "signed_order_request_created": True,
                "signed_trading_request_created": True,
                "submit_allowed": False,
                "order_placed": False,
                "binance_order_endpoint_called": False,
                "network_allowed": False,
                "secrets_shown": False,
                "secrets_persisted": False,
            },
        }
    )


def _build_input_summary(
    *,
    latest_r253: Mapping[str, Any],
    r253_validation: Mapping[str, Any],
    latest_r252: Mapping[str, Any],
    latest_r251e: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "r253_final_readonly_found": bool(latest_r253),
        "r253_regeneration_required": r253_validation.get("regeneration_required") is True,
        "r253_fresh_market_context_ready": r253_validation.get("fresh_market_context_ready") is True,
        "r252_submit_readiness_found": bool(latest_r252),
        "r251e_runtime_signed_request_found": bool(latest_r251e),
        "old_signed_artifact_stale": r253_validation.get("old_signed_artifact_stale") is True,
    }


def _prewrite_blockers(
    *,
    r253_validation: Mapping[str, Any],
    fresh_context: Mapping[str, Any],
    stop_validation: Mapping[str, Any],
    payload_validation: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if r253_validation.get("valid") is not True:
        blockers.extend(str(item) for item in r253_validation.get("errors") or [])
    if _number(fresh_context.get("reference_price")) is None:
        blockers.append("fresh_reference_context_missing")
    if stop_validation.get("valid") is not True:
        blockers.extend(str(item) for item in stop_validation.get("errors") or [])
    if payload_validation.get("valid") is not True:
        blockers.extend(str(item) for item in payload_validation.get("errors") or [])
    return _dedupe(blockers)


def _stop_summary(source: Mapping[str, Any], validation: Mapping[str, Any], written: bool) -> dict[str, Any]:
    return {
        "source_written": bool(written),
        "symbol": source.get("symbol") or "BTCUSDT",
        "direction": source.get("direction") or "short",
        "quantity": _number(source.get("quantity")),
        "quantity_sizing_plan": source.get("quantity_sizing_plan") if isinstance(source.get("quantity_sizing_plan"), Mapping) else {},
        "reference_price": source.get("reference_price"),
        "stop_price": source.get("stop_price"),
        "take_profit_price": source.get("take_profit_price"),
        "estimated_loss_at_stop_usdt": source.get("estimated_loss_at_stop_usdt"),
        "estimated_reward_at_take_profit_usdt": source.get("estimated_reward_at_take_profit_usdt"),
        "risk_reward_ratio": source.get("risk_reward_ratio"),
        "max_loss_usdt": source.get("max_loss_usdt"),
        "valid": validation.get("valid") is True,
    }


def _payload_summary(payload: Mapping[str, Any], validation: Mapping[str, Any], written: bool) -> dict[str, Any]:
    main = payload.get("main_order") if isinstance(payload.get("main_order"), Mapping) else {}
    stop = payload.get("stop_order") if isinstance(payload.get("stop_order"), Mapping) else {}
    tp = payload.get("take_profit_order") if isinstance(payload.get("take_profit_order"), Mapping) else {}
    return {
        "payload_written": bool(written),
        "main_order_side": main.get("side") or "SELL",
        "main_order_type": main.get("type") or "MARKET",
        "quantity": _number(main.get("quantity")),
        "stop_order_side": stop.get("side") or "BUY",
        "stop_order_type": stop.get("type") or "STOP_MARKET",
        "take_profit_order_side": tp.get("side") or "BUY",
        "take_profit_order_type": tp.get("type") or "TAKE_PROFIT_MARKET",
        "reduce_only": stop.get("reduceOnly") is True and tp.get("reduceOnly") is True,
        "submit_allowed": False,
        "network_allowed": False,
        "order_placed": False,
        "valid": validation.get("valid") is True,
    }


def _signed_summary(artifact: Mapping[str, Any], written: bool) -> dict[str, Any]:
    signed = artifact.get("signed_requests") if isinstance(artifact.get("signed_requests"), Mapping) else {}
    return {
        "signed_request_written": bool(written),
        "signed_requests_count": len(signed),
        "main_order_signature_present": bool((signed.get("main_order") or {}).get("signature")) if isinstance(signed.get("main_order"), Mapping) else False,
        "stop_order_signature_present": bool((signed.get("stop_order") or {}).get("signature")) if isinstance(signed.get("stop_order"), Mapping) else False,
        "take_profit_order_signature_present": bool((signed.get("take_profit_order") or {}).get("signature")) if isinstance(signed.get("take_profit_order"), Mapping) else False,
        "submit_allowed": False,
        "order_placed": False,
        "binance_order_endpoint_called": False,
        "network_allowed": False,
    }


def _fresh_context_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reference_price": context.get("reference_price"),
        "fresh_mark_price_source_phase": "R253",
        "tick_size": context.get("tick_size"),
        "step_size": context.get("step_size"),
        "min_notional": context.get("min_notional"),
        "price_precision": context.get("price_precision"),
        "quantity_precision": context.get("quantity_precision"),
    }


def _safety(written: bool) -> dict[str, Any]:
    return {
        **SAFETY,
        "hmac_signature_created": bool(written),
        "signed_request_written": bool(written),
        "signed_order_request_created": bool(written),
        "signed_trading_request_created": bool(written),
    }


def _target_scope(official_lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    return {
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "fresh_context_signed_request_regeneration_only": True,
        "submit_allowed": False,
        "order_placed": False,
        "binance_order_endpoint_called": False,
        "network_allowed": False,
    }


def _read_external_env_file_values(path: str | Path) -> dict[str, str]:
    values: dict[str, str] = {}
    file_path = Path(path)
    if not file_path.exists():
        return values
    for line in file_path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, value = clean.split("=", 1)
        if key in {BINANCE_API_KEY_ENV, BINANCE_API_SECRET_ENV}:
            values[key] = value.strip().strip('"').strip("'")
    return values


def _recommended_next_operator_move(packet: Mapping[str, Any]) -> str:
    return str(packet.get("next_required_human_action") or "WAIT")


def _recommended_next_engineering_move(written: bool, matrix: Mapping[str, Any]) -> str:
    if written:
        return "Implement R254 submit-gate preview consuming the R253B regenerated signed request; keep submit disabled."
    if matrix.get("runtime_credential_source_ready") is not True:
        return "Fix runtime credential source readiness before R253B regeneration."
    if matrix.get("r253_regeneration_required") is not True:
        return "Review latest R253 final readonly artifact before regenerating signed requests."
    return "Run R253B with exact confirmation if the operator approves local regeneration only."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "kill switch disable",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r253_final_readonly_found": False,
        "r253_regeneration_required": False,
        "r253_fresh_market_context_ready": False,
        "r252_submit_readiness_found": False,
        "r251e_runtime_signed_request_found": False,
        "old_signed_artifact_stale": False,
    }


def _empty_signed_validation() -> dict[str, Any]:
    return {"valid": False, "errors": ["signed_request_not_created"], "warnings": []}


def _empty_secret_validation() -> dict[str, Any]:
    return {
        "valid": False,
        "raw_api_key_found_in_artifacts": False,
        "raw_api_secret_found_in_artifacts": False,
        "secret_values_in_output": False,
        "errors": [],
        "warnings": [],
    }


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    if record.get("official_lane_key") == official_lane_key or target.get("official_lane_key") == official_lane_key:
        return True
    for key in (
        "stop_take_profit_source",
        "stop_take_profit_source_preview",
        "executable_payload_artifact",
        "signed_request_artifact",
    ):
        value = record.get(key)
        if isinstance(value, Mapping) and value.get("official_lane_key") == official_lane_key:
            return True
    return False


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = lane_key.split("|")
    if len(parts) != 4:
        return ("BTCUSDT", "8m", "short", "ladder_close_50_618")
    return (parts[0], parts[1], parts[2], parts[3])


def _round_price(price: Any, tick_size: Any) -> float | None:
    price_dec = _decimal(price)
    tick_dec = _decimal(tick_size)
    if price_dec is None or tick_dec is None or tick_dec <= 0:
        return None
    rounded = (price_dec / tick_dec).to_integral_value(rounding=ROUND_HALF_UP) * tick_dec
    return _float(rounded)


def _multiple_of_step(value: float, step: float) -> bool:
    value_dec = _decimal(value)
    step_dec = _decimal(step)
    if value_dec is None or step_dec is None or step_dec <= 0:
        return False
    return value_dec.remainder_near(step_dec) == 0


def _format_decimal(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    return format(number.normalize(), "f")


def _number(value: Any) -> float | None:
    dec = _decimal(value)
    return _float(dec) if dec is not None else None


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _dedupe(items: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = str(item)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Decimal):
        return _float(value)
    return value
