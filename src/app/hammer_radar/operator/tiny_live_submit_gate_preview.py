"""R254 tiny-live submit gate preview.

This module validates the latest R253B regenerated local artifacts for a
future submit gate. It never calls Binance/network endpoints, signs requests,
reads secrets, submits, places orders, or mutates env/config/lane controls.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_executable_payload_write_gate import (
    load_tiny_live_executable_payload_write_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_final_readonly_mark_price_refresh_gate import (
    load_tiny_live_final_readonly_mark_price_refresh_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_fresh_context_signed_request_regeneration_gate import (
    CREATED_BY_PHASE as R253B_CREATED_BY_PHASE,
    load_tiny_live_fresh_context_signed_request_regeneration_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_write_gate import (
    load_tiny_live_signed_request_write_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_stop_take_profit_source_gate import (
    load_tiny_live_stop_take_profit_source_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_submit_readiness_preview import (
    load_tiny_live_submit_readiness_preview_records,
)

TINY_LIVE_SUBMIT_GATE_PREVIEW_READY = "TINY_LIVE_SUBMIT_GATE_PREVIEW_READY"
TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED = "TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED"
TINY_LIVE_SUBMIT_GATE_PREVIEW_REJECTED = "TINY_LIVE_SUBMIT_GATE_PREVIEW_REJECTED"
TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED = "TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED"
TINY_LIVE_SUBMIT_GATE_PREVIEW_ERROR = "TINY_LIVE_SUBMIT_GATE_PREVIEW_ERROR"

TINY_LIVE_SUBMIT_GATE_PREVIEW_READY_FOR_RECORDING = (
    "TINY_LIVE_SUBMIT_GATE_PREVIEW_READY_FOR_RECORDING"
)
TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED_R255_SUBMIT_GATE_REQUIRED = (
    "TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED_R255_SUBMIT_GATE_REQUIRED"
)
TINY_LIVE_SUBMIT_GATE_PREVIEW_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_SUBMIT_GATE_PREVIEW_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED_BY_MISSING_R253B_REGENERATION = (
    "TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED_BY_MISSING_R253B_REGENERATION"
)
TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED_BY_INVALID_SIGNED_REQUEST = (
    "TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED_BY_INVALID_SIGNED_REQUEST"
)
TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED_BY_SUBMIT_CONTROL = (
    "TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED_BY_SUBMIT_CONTROL"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_SUBMIT_GATE_PREVIEW"
LEDGER_FILENAME = "tiny_live_submit_gate_preview.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R254_TINY_LIVE_SUBMIT_GATE_PREVIEW"
CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE = (
    "I CONFIRM TINY LIVE SUBMIT GATE PREVIEW RECORDING ONLY; "
    "NO SUBMIT; NO ORDER; NO BINANCE CALL."
)

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_final_readonly_mark_price_refresh_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_submit_readiness_preview.ndjson",
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
    "submit_gate_preview_only": True,
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
    "secrets_read": False,
    "secrets_shown": False,
    "secrets_persisted": False,
    "secret_values_in_output": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
}


def build_tiny_live_submit_gate_preview(
    *,
    log_dir: str | Path | None = None,
    record_submit_gate_preview: bool = False,
    confirm_tiny_live_submit_gate_preview: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_submit_gate_preview
        == CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE
    )
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    try:
        latest_r253b = load_latest_tiny_live_fresh_context_signed_request_regeneration_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_signed = load_latest_tiny_live_signed_request_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_payload = load_latest_tiny_live_executable_payload_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_stop_tp = load_latest_tiny_live_stop_take_profit_source_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r253 = load_latest_tiny_live_final_readonly_mark_price_refresh_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r252 = load_latest_tiny_live_submit_readiness_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )

        signed_artifact = _signed_request_artifact(latest_signed)
        executable_artifact = _executable_payload_artifact(latest_payload)
        stop_tp_artifact = _stop_take_profit_artifact(latest_stop_tp)

        signed_validation = validate_latest_fresh_signed_request_for_submit_gate_preview(
            latest_r253b=latest_r253b,
            signed_request_artifact=signed_artifact,
        )
        triplet_preview = build_submit_gate_order_triplet_preview(
            signed_request_artifact=signed_artifact,
            executable_payload_artifact=executable_artifact,
        )
        triplet_validation = validate_submit_order_triplet_shape(
            submit_order_triplet_preview=triplet_preview,
            stop_take_profit_source=stop_tp_artifact,
        )
        triplet_preview["valid"] = triplet_validation.get("valid") is True
        controls_validation = validate_submit_controls_remain_disabled(
            latest_r253b=latest_r253b,
            signed_request_artifact=signed_artifact,
            executable_payload_artifact=executable_artifact,
        )
        input_summary = _build_input_summary(
            latest_r253b=latest_r253b,
            signed_validation=signed_validation,
            latest_signed=latest_signed,
            latest_payload=latest_payload,
            triplet_validation=triplet_validation,
            latest_stop_tp=latest_stop_tp,
            latest_r253=latest_r253,
            latest_r252=latest_r252,
        )
        signed_summary = _build_fresh_signed_request_summary(
            signed_artifact=signed_artifact,
            signed_validation=signed_validation,
        )
        submit_control_summary = _build_submit_control_summary(signed_artifact)
        future_phrase = build_future_submit_confirmation_phrase()
        r255_requirements = build_r255_submit_gate_requirements()
        blocked_by = _blocked_by(
            input_summary=input_summary,
            signed_validation=signed_validation,
            triplet_validation=triplet_validation,
            controls_validation=controls_validation,
        )

        if record_submit_gate_preview and not confirmation_valid:
            status = TINY_LIVE_SUBMIT_GATE_PREVIEW_REJECTED
            overall = TINY_LIVE_SUBMIT_GATE_PREVIEW_REJECTED_BAD_CONFIRMATION
        elif blocked_by:
            status = TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED
            overall = classify_tiny_live_submit_gate_preview_status(
                input_summary=input_summary,
                signed_request_validation=signed_validation,
                submit_controls_validation=controls_validation,
                record_requested=record_submit_gate_preview,
                confirmation_valid=confirmation_valid,
                recorded=False,
            )
        elif record_submit_gate_preview and confirmation_valid:
            status = TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED
            overall = TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED_R255_SUBMIT_GATE_REQUIRED
        else:
            status = TINY_LIVE_SUBMIT_GATE_PREVIEW_READY
            overall = TINY_LIVE_SUBMIT_GATE_PREVIEW_READY_FOR_RECORDING

        recorded = status == TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED
        matrix = build_submit_gate_preview_matrix(
            input_summary=input_summary,
            signed_request_validation=signed_validation,
            triplet_validation=triplet_validation,
            controls_validation=controls_validation,
            record_confirmed=record_submit_gate_preview and confirmation_valid,
            recorded=recorded,
            blocked_by=blocked_by,
        )
        operator_packet = build_operator_submit_gate_preview_packet(matrix)
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "record_submit_gate_preview_requested": bool(record_submit_gate_preview),
                "confirmation_valid": bool(confirmation_valid),
                "submit_gate_preview_recorded": bool(recorded),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "submit_gate_preview_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "fresh_signed_request_summary": signed_summary,
                "submit_order_triplet_preview": triplet_preview,
                "submit_control_summary": submit_control_summary,
                "future_submit_confirmation_phrase": future_phrase,
                "r255_submit_gate_requirements": r255_requirements,
                "submit_gate_preview_matrix": matrix,
                "operator_submit_gate_preview_packet": operator_packet,
                "recommended_next_operator_move": _recommended_next_operator_move(matrix),
                "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
                "submit_gate_preview_overall_status": overall,
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if recorded:
            payload = append_tiny_live_submit_gate_preview_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_submit_gate_preview=confirm_tiny_live_submit_gate_preview,
            )
        return payload
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        return _sanitize(
            {
                "status": TINY_LIVE_SUBMIT_GATE_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "record_submit_gate_preview_requested": bool(record_submit_gate_preview),
                "confirmation_valid": bool(confirmation_valid),
                "submit_gate_preview_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "submit_gate_preview_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "error": type(exc).__name__,
                "submit_gate_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "safety": dict(SAFETY),
            }
        )


def load_latest_tiny_live_fresh_context_signed_request_regeneration_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_fresh_context_signed_request_regeneration_gate_records(
        log_dir=log_dir,
        limit=50,
    ):
        if _record_matches_lane(record, official_lane_key) and record.get("fresh_context_regeneration_written") is True:
            return _sanitize(record)
    return {}


def load_latest_tiny_live_signed_request_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_signed_request_write_gate_records(log_dir=log_dir, limit=50):
        artifact = _signed_request_artifact(record)
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("signed_request_written") is True
            and artifact.get("created_by_phase") == R253B_CREATED_BY_PHASE
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_executable_payload_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_executable_payload_write_gate_records(log_dir=log_dir, limit=50):
        artifact = _executable_payload_artifact(record)
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("executable_payload_written") is True
            and artifact.get("created_by_phase") == R253B_CREATED_BY_PHASE
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_stop_take_profit_source_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_stop_take_profit_source_gate_records(log_dir=log_dir, limit=50):
        source = _stop_take_profit_artifact(record)
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("stop_take_profit_source_preview_recorded") is True
            and source.get("created_by_phase") == R253B_CREATED_BY_PHASE
        ):
            return _sanitize(record)
    return {}


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


def validate_latest_fresh_signed_request_for_submit_gate_preview(
    *,
    latest_r253b: Mapping[str, Any],
    signed_request_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not latest_r253b:
        errors.append("r253b_fresh_regeneration_missing")
    elif latest_r253b.get("fresh_context_regeneration_written") is not True:
        errors.append("r253b_fresh_regeneration_not_written")
    if not signed_request_artifact:
        errors.append("r253b_signed_request_missing")
        return {"valid": False, "errors": _dedupe(errors), "warnings": warnings}
    if signed_request_artifact.get("created_by_phase") != R253B_CREATED_BY_PHASE:
        errors.append("signed_request_not_created_by_r253b")
    signed_requests = signed_request_artifact.get("signed_requests")
    signed_requests = signed_requests if isinstance(signed_requests, Mapping) else {}
    if len(signed_requests) != 3 or set(signed_requests) != {"main_order", "stop_order", "take_profit_order"}:
        errors.append("signed_requests_count_not_three")
    for order_key in ("main_order", "stop_order", "take_profit_order"):
        request = signed_requests.get(order_key) if isinstance(signed_requests.get(order_key), Mapping) else {}
        signature = str(request.get("signature") or "")
        if not signature:
            errors.append(f"{order_key}_signature_missing")
        elif not re.fullmatch(r"[0-9a-f]{64}", signature):
            errors.append(f"{order_key}_signature_not_64_hex")
        if request.get("method") != "POST" or request.get("endpoint") != "/fapi/v1/order":
            errors.append(f"{order_key}_endpoint_invalid")
        if request.get("submit_allowed") is not False:
            errors.append(f"{order_key}_submit_allowed_not_false")
        if request.get("network_allowed") is not False:
            errors.append(f"{order_key}_network_allowed_not_false")
        if "signature=" in str(request.get("query_string_without_signature") or ""):
            errors.append(f"{order_key}_query_contains_signature")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def validate_submit_order_triplet_shape(
    *,
    submit_order_triplet_preview: Mapping[str, Any],
    stop_take_profit_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    main = submit_order_triplet_preview.get("main_order")
    main = main if isinstance(main, Mapping) else {}
    stop = submit_order_triplet_preview.get("stop_order")
    stop = stop if isinstance(stop, Mapping) else {}
    tp = submit_order_triplet_preview.get("take_profit_order")
    tp = tp if isinstance(tp, Mapping) else {}
    if main.get("method") != "POST" or main.get("endpoint") != "/fapi/v1/order":
        errors.append("main_order_endpoint_invalid")
    if main.get("side") != "SELL" or main.get("type") != "MARKET":
        errors.append("main_order_shape_invalid")
    main_qty = _number(main.get("quantity"))
    stop_qty = _number(stop.get("quantity"))
    tp_qty = _number(tp.get("quantity"))
    if main_qty is None or main_qty <= 0:
        errors.append("main_order_quantity_invalid")
    if stop.get("side") != "BUY" or stop.get("type") != "STOP_MARKET":
        errors.append("stop_order_shape_invalid")
    if stop.get("reduceOnly") is not True or stop.get("workingType") != "MARK_PRICE":
        errors.append("stop_order_reduce_only_or_working_type_invalid")
    if stop_qty != main_qty:
        errors.append("stop_order_quantity_invalid")
    if _number(stop.get("stopPrice")) != _number((stop_take_profit_source or {}).get("stop_price")):
        errors.append("stop_order_stop_price_not_latest_r253b")
    if tp.get("side") != "BUY" or tp.get("type") != "TAKE_PROFIT_MARKET":
        errors.append("take_profit_order_shape_invalid")
    if tp.get("reduceOnly") is not True or tp.get("workingType") != "MARK_PRICE":
        errors.append("take_profit_order_reduce_only_or_working_type_invalid")
    if tp_qty != main_qty:
        errors.append("take_profit_order_quantity_invalid")
    if _number(tp.get("stopPrice")) != _number((stop_take_profit_source or {}).get("take_profit_price")):
        errors.append("take_profit_order_stop_price_not_latest_r253b")
    for key, order in (("main_order", main), ("stop_order", stop), ("take_profit_order", tp)):
        if order.get("submit_in_this_phase") is not False:
            errors.append(f"{key}_submit_in_this_phase_not_false")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": []}


def validate_submit_controls_remain_disabled(
    *,
    latest_r253b: Mapping[str, Any],
    signed_request_artifact: Mapping[str, Any],
    executable_payload_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    controls = signed_request_artifact.get("controls")
    controls = controls if isinstance(controls, Mapping) else {}
    signed_safety = signed_request_artifact.get("safety")
    signed_safety = signed_safety if isinstance(signed_safety, Mapping) else {}
    payload_safety = executable_payload_artifact.get("safety")
    payload_safety = payload_safety if isinstance(payload_safety, Mapping) else {}
    r253b_scope = latest_r253b.get("target_scope")
    r253b_scope = r253b_scope if isinstance(r253b_scope, Mapping) else {}
    for key in ("submit_allowed", "network_allowed"):
        if controls.get(key) is not False:
            errors.append(f"controls_{key}_not_false")
    if controls.get("binance_call_allowed") is not False:
        errors.append("controls_binance_call_allowed_not_false")
    for source_name, source in (
        ("signed_safety", signed_safety),
        ("payload_safety", payload_safety),
        ("r253b_target_scope", r253b_scope),
    ):
        for key in ("submit_allowed", "order_placed", "binance_order_endpoint_called", "network_allowed"):
            if source.get(key) is not False:
                errors.append(f"{source_name}_{key}_not_false")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": []}


def build_submit_gate_order_triplet_preview(
    *,
    signed_request_artifact: Mapping[str, Any],
    executable_payload_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    signed_requests = signed_request_artifact.get("signed_requests")
    signed_requests = signed_requests if isinstance(signed_requests, Mapping) else {}
    executable_orders = {
        "main_order": executable_payload_artifact.get("main_order") if isinstance(executable_payload_artifact.get("main_order"), Mapping) else {},
        "stop_order": executable_payload_artifact.get("stop_order") if isinstance(executable_payload_artifact.get("stop_order"), Mapping) else {},
        "take_profit_order": executable_payload_artifact.get("take_profit_order") if isinstance(executable_payload_artifact.get("take_profit_order"), Mapping) else {},
    }
    triplet: dict[str, Any] = {}
    reference_price = _number(
        executable_payload_artifact.get("reference_price")
        or executable_payload_artifact.get("entry_reference_price")
    )
    for key in ("main_order", "stop_order", "take_profit_order"):
        signed = signed_requests.get(key) if isinstance(signed_requests.get(key), Mapping) else {}
        parsed = _parse_query_string(str(signed.get("query_string_without_signature") or ""))
        fallback = executable_orders[key]
        triplet[key] = _sanitize(
            {
                "method": signed.get("method") or "POST",
                "endpoint": signed.get("endpoint") or "/fapi/v1/order",
                "side": parsed.get("side") or fallback.get("side"),
                "type": parsed.get("type") or fallback.get("type"),
                "quantity": _number(parsed.get("quantity") or fallback.get("quantity")),
                "submit_in_this_phase": False,
            }
        )
        if key != "main_order":
            triplet[key]["stopPrice"] = _number(parsed.get("stopPrice") or fallback.get("stopPrice"))
            triplet[key]["reduceOnly"] = _bool(parsed.get("reduceOnly"), fallback.get("reduceOnly"))
            triplet[key]["workingType"] = parsed.get("workingType") or fallback.get("workingType")
    triplet["entry_reference_price"] = reference_price
    triplet["valid"] = False
    return triplet


def build_future_submit_confirmation_phrase() -> str:
    return (
        "I CONFIRM TINY LIVE BTCUSDT 8M SHORT SUBMIT ONLY; PLACE EXACTLY THREE "
        "BINANCE FUTURES ORDERS FROM LATEST R253B SIGNED REQUEST; MAIN SELL "
        "MARKET 0.007 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY "
        "TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS."
    )


def build_r255_submit_gate_requirements() -> dict[str, list[str]]:
    return {
        "must_verify_before_submit": [
            "fresh R253B signed request is latest",
            "signed request age within allowed window",
            "timestamp freshness or regeneration",
            "runtime credential source ready",
            "kill switch state allows tiny live",
            "order endpoint allowlist exactly /fapi/v1/order",
            "exactly three orders intended",
            "main order then stop then take-profit sequence",
            "idempotency/dedupe no prior live order for same signal",
            "post-submit reconciliation plan exists",
            "max loss and notional within tiny-live contract",
            "operator exact R255 confirmation",
        ],
        "must_remain_false_until_r255": [
            "submit_allowed",
            "order_placed",
            "binance_order_endpoint_called",
            "network_allowed",
        ],
    }


def build_submit_gate_preview_matrix(
    *,
    input_summary: Mapping[str, Any],
    signed_request_validation: Mapping[str, Any],
    triplet_validation: Mapping[str, Any],
    controls_validation: Mapping[str, Any],
    record_confirmed: bool,
    recorded: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "fresh_regeneration_ready": input_summary.get("r253b_fresh_regeneration_valid") is True,
        "fresh_signed_request_valid": signed_request_validation.get("valid") is True,
        "submit_order_triplet_valid": triplet_validation.get("valid") is True,
        "submit_controls_disabled": controls_validation.get("valid") is True,
        "future_submit_phrase_ready": True,
        "record_confirmed": bool(record_confirmed),
        "recorded": bool(recorded),
        "submit_allowed": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blocked_by or []),
    }


def build_operator_submit_gate_preview_packet(
    submit_gate_preview_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    if submit_gate_preview_matrix.get("recorded") is True:
        action = "CONTINUE_TO_R255_ACTUAL_SUBMIT_GATE"
    elif submit_gate_preview_matrix.get("blocked_by"):
        action = "FIX_BLOCKER"
    elif (
        submit_gate_preview_matrix.get("fresh_regeneration_ready") is True
        and submit_gate_preview_matrix.get("fresh_signed_request_valid") is True
        and submit_gate_preview_matrix.get("submit_order_triplet_valid") is True
    ):
        action = "REVIEW_R254_SUBMIT_GATE_PREVIEW"
    else:
        action = "WAIT"
    return {
        "operator_should_review_submit_gate_preview": action in {
            "REVIEW_R254_SUBMIT_GATE_PREVIEW",
            "CONTINUE_TO_R255_ACTUAL_SUBMIT_GATE",
        },
        "operator_should_continue_to_r255_actual_submit_gate": action == "CONTINUE_TO_R255_ACTUAL_SUBMIT_GATE",
        "operator_should_submit_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not submit",
            "do not call Binance order endpoint from this phase",
        ],
    }


def classify_tiny_live_submit_gate_preview_status(
    *,
    input_summary: Mapping[str, Any],
    signed_request_validation: Mapping[str, Any],
    submit_controls_validation: Mapping[str, Any],
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_SUBMIT_GATE_PREVIEW_REJECTED_BAD_CONFIRMATION
    if recorded:
        return TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED_R255_SUBMIT_GATE_REQUIRED
    if not input_summary.get("r253b_fresh_regeneration_found"):
        return TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED_BY_MISSING_R253B_REGENERATION
    if signed_request_validation.get("valid") is not True:
        return TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED_BY_INVALID_SIGNED_REQUEST
    if submit_controls_validation.get("valid") is not True:
        return TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED_BY_SUBMIT_CONTROL
    if input_summary.get("r253b_fresh_regeneration_valid") is True:
        return TINY_LIVE_SUBMIT_GATE_PREVIEW_READY_FOR_RECORDING
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_submit_gate_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_submit_gate_preview: str | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_submit_gate_preview != CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE:
        raise ValueError("bad_tiny_live_submit_gate_preview_confirmation")
    path = tiny_live_submit_gate_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "submit_gate_preview_record_id": record.get("submit_gate_preview_record_id")
            or f"r254_submit_gate_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "submit_gate_preview_recorded": True,
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_submit_gate_preview_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_submit_gate_preview_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_submit_gate_preview_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_recorded": latest.get("submit_gate_preview_recorded") is True,
        "latest_overall_status": latest.get("submit_gate_preview_overall_status"),
        "latest_next_required_human_action": latest.get("operator_submit_gate_preview_packet", {}).get("next_required_human_action"),
    }


def tiny_live_submit_gate_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_submit_gate_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r253b: Mapping[str, Any],
    signed_validation: Mapping[str, Any],
    latest_signed: Mapping[str, Any],
    latest_payload: Mapping[str, Any],
    triplet_validation: Mapping[str, Any],
    latest_stop_tp: Mapping[str, Any],
    latest_r253: Mapping[str, Any],
    latest_r252: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "r253b_fresh_regeneration_found": bool(latest_r253b),
        "r253b_fresh_regeneration_valid": _r253b_regeneration_valid(latest_r253b),
        "r253b_signed_request_found": bool(latest_signed),
        "r253b_signed_request_valid": signed_validation.get("valid") is True,
        "r253b_payload_found": bool(latest_payload),
        "r253b_payload_valid": triplet_validation.get("valid") is True,
        "r253b_stop_take_profit_found": bool(latest_stop_tp),
        "r253b_stop_take_profit_valid": bool(latest_stop_tp),
        "r253_final_readonly_found": bool(latest_r253),
        "r252_submit_readiness_found": bool(latest_r252),
    }


def _build_fresh_signed_request_summary(
    *,
    signed_artifact: Mapping[str, Any],
    signed_validation: Mapping[str, Any],
) -> dict[str, Any]:
    signed_requests = signed_artifact.get("signed_requests")
    signed_requests = signed_requests if isinstance(signed_requests, Mapping) else {}
    safety = signed_artifact.get("safety") if isinstance(signed_artifact.get("safety"), Mapping) else {}
    controls = signed_artifact.get("controls") if isinstance(signed_artifact.get("controls"), Mapping) else {}
    return {
        "created_by_phase": signed_artifact.get("created_by_phase"),
        "signed_requests_count": len(signed_requests),
        "main_order_signature_present": bool((signed_requests.get("main_order") or {}).get("signature")),
        "stop_order_signature_present": bool((signed_requests.get("stop_order") or {}).get("signature")),
        "take_profit_order_signature_present": bool((signed_requests.get("take_profit_order") or {}).get("signature")),
        "all_signatures_64_hex": signed_validation.get("valid") is True
        and all(
            re.fullmatch(r"[0-9a-f]{64}", str((signed_requests.get(key) or {}).get("signature") or ""))
            for key in ("main_order", "stop_order", "take_profit_order")
        ),
        "submit_allowed": controls.get("submit_allowed", False) is True,
        "order_placed": safety.get("order_placed", False) is True,
        "network_allowed": controls.get("network_allowed", False) is True,
        "binance_order_endpoint_called": safety.get("binance_order_endpoint_called", False) is True,
    }


def _build_submit_control_summary(signed_artifact: Mapping[str, Any]) -> dict[str, Any]:
    controls = signed_artifact.get("controls") if isinstance(signed_artifact.get("controls"), Mapping) else {}
    safety = signed_artifact.get("safety") if isinstance(signed_artifact.get("safety"), Mapping) else {}
    return {
        "submit_allowed": controls.get("submit_allowed", False) is True,
        "network_allowed": controls.get("network_allowed", False) is True,
        "order_placed": safety.get("order_placed", False) is True,
        "requires_operator_final_submit_confirmation": True,
        "requires_r255_submit_gate": True,
        "requires_idempotency_guard": True,
        "requires_order_endpoint_allowlist": True,
        "requires_post_submit_reconciliation": True,
        "requires_kill_switch_check": True,
    }


def _blocked_by(
    *,
    input_summary: Mapping[str, Any],
    signed_validation: Mapping[str, Any],
    triplet_validation: Mapping[str, Any],
    controls_validation: Mapping[str, Any],
) -> list[str]:
    blocked: list[str] = []
    if input_summary.get("r253b_fresh_regeneration_found") is not True:
        blocked.append("r253b_fresh_regeneration_missing")
    if input_summary.get("r253b_fresh_regeneration_valid") is not True:
        blocked.append("r253b_fresh_regeneration_invalid")
    if signed_validation.get("valid") is not True:
        blocked.extend(str(item) for item in signed_validation.get("errors") or ["r253b_signed_request_invalid"])
    if triplet_validation.get("valid") is not True:
        blocked.extend(str(item) for item in triplet_validation.get("errors") or ["submit_order_triplet_invalid"])
    if controls_validation.get("valid") is not True:
        blocked.extend(str(item) for item in controls_validation.get("errors") or ["submit_controls_not_disabled"])
    for key in ("r253b_payload_found", "r253b_stop_take_profit_found", "r253_final_readonly_found", "r252_submit_readiness_found"):
        if input_summary.get(key) is not True:
            blocked.append(key.replace("_found", "_missing"))
    return _dedupe(blocked)


def _r253b_regeneration_valid(record: Mapping[str, Any]) -> bool:
    if not record or record.get("fresh_context_regeneration_written") is not True:
        return False
    summary = record.get("fresh_signed_request_artifact_summary")
    summary = summary if isinstance(summary, Mapping) else {}
    return (
        summary.get("signed_requests_count") == 3
        and summary.get("main_order_signature_present") is True
        and summary.get("stop_order_signature_present") is True
        and summary.get("take_profit_order_signature_present") is True
        and summary.get("submit_allowed") is False
        and summary.get("order_placed") is False
        and summary.get("network_allowed") is False
        and summary.get("binance_order_endpoint_called") is False
    )


def _recommended_next_operator_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("recorded") is True:
        return "CONTINUE_TO_R255_ACTUAL_SUBMIT_GATE"
    if matrix.get("blocked_by"):
        return "FIX_BLOCKER"
    return "REVIEW_R254_SUBMIT_GATE_PREVIEW"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("recorded") is True:
        return "Create R255 actual submit gate with idempotency, stale timestamp, kill-switch, endpoint allowlist, and post-submit reconciliation enforcement."
    if matrix.get("blocked_by"):
        return "Fix R254 input blockers before recording the final submit gate preview."
    return "Record R254 preview only with the exact confirmation phrase; do not submit in R254."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "kill switch disable",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _signed_request_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("signed_request_artifact")
    return _sanitize(artifact if isinstance(artifact, Mapping) else {})


def _executable_payload_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("executable_payload_artifact")
    return _sanitize(artifact if isinstance(artifact, Mapping) else {})


def _stop_take_profit_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("stop_take_profit_source_preview")
    return _sanitize(artifact if isinstance(artifact, Mapping) else {})


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    return target.get("official_lane_key") == official_lane_key


def _lane_parts(official_lane_key: str) -> tuple[str, str, str, str]:
    parts = official_lane_key.split("|")
    if len(parts) != 4:
        return official_lane_key, "", "", ""
    return parts[0], parts[1], parts[2], parts[3]


def _parse_query_string(query: str) -> dict[str, str]:
    return {str(key): str(value) for key, value in parse_qsl(query, keep_blank_values=True)}


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any, fallback: Any = None) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    if isinstance(fallback, bool):
        return fallback
    return None


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_sanitize(item) for item in value]
    return value
