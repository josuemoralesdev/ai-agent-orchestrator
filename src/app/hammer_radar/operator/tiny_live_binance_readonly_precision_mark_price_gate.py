"""R242 tiny-live Binance read-only precision / mark-price gate.

This module may call only Binance Futures public read-only market-data
endpoints after the exact R242 confirmation phrase. It never uses secrets,
signs requests, creates executable payloads, calls private/order endpoints,
places orders, mutates configs/env, or disables the kill switch.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
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
from src.app.hammer_radar.operator.tiny_live_live_authorization_preview import LANE_CONTROLS_PATH
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    load_tiny_live_risk_contract_config,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_write_gate import (
    validate_non_executable_order_payload_artifact,
)
from src.app.hammer_radar.operator.tiny_live_precision_and_mark_price_preview import (
    LEDGER_FILENAME as R241_LEDGER_FILENAME,
    load_latest_tiny_live_10_of_10_ready_packet as _load_latest_tiny_live_10_of_10_ready_packet,
    load_latest_tiny_live_lane_arm_write_gate as _load_latest_tiny_live_lane_arm_write_gate,
    load_latest_tiny_live_order_payload_write_gate as _load_latest_tiny_live_order_payload_write_gate,
    load_latest_tiny_live_order_preflight_write_gate as _load_latest_tiny_live_order_preflight_write_gate,
    load_latest_tiny_live_risk_contract_config_write_gate as _load_latest_tiny_live_risk_contract_config_write_gate,
    load_tiny_live_precision_and_mark_price_preview_records,
)
from src.app.hammer_radar.operator.tiny_live_order_preflight_preview import load_lane_controls_readonly
from src.app.hammer_radar.operator.tiny_live_order_preflight_write_gate import validate_order_preflight_object
from src.app.hammer_radar.operator.tiny_live_lane_arm_write_gate import validate_lane_arm_object
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    validate_tiny_live_risk_contract_config_entry,
)

TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_READY = (
    "TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_READY"
)
TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_REJECTED = (
    "TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_REJECTED"
)
TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_FETCHED = (
    "TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_FETCHED"
)
TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_BLOCKED = (
    "TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_BLOCKED"
)
TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_ERROR = (
    "TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_ERROR"
)

TINY_LIVE_BINANCE_READONLY_READY_FOR_CONFIRMATION = "TINY_LIVE_BINANCE_READONLY_READY_FOR_CONFIRMATION"
TINY_LIVE_BINANCE_READONLY_FETCHED_QUANTITY_PREVIEW_READY = (
    "TINY_LIVE_BINANCE_READONLY_FETCHED_QUANTITY_PREVIEW_READY"
)
TINY_LIVE_BINANCE_READONLY_FETCHED_QUANTITY_PREVIEW_BLOCKED = (
    "TINY_LIVE_BINANCE_READONLY_FETCHED_QUANTITY_PREVIEW_BLOCKED"
)
TINY_LIVE_BINANCE_READONLY_REJECTED_BAD_CONFIRMATION = "TINY_LIVE_BINANCE_READONLY_REJECTED_BAD_CONFIRMATION"
TINY_LIVE_BINANCE_READONLY_BLOCKED_BY_R241_PREVIEW = "TINY_LIVE_BINANCE_READONLY_BLOCKED_BY_R241_PREVIEW"
TINY_LIVE_BINANCE_READONLY_BLOCKED_BY_PAYLOAD = "TINY_LIVE_BINANCE_READONLY_BLOCKED_BY_PAYLOAD"
TINY_LIVE_BINANCE_READONLY_BLOCKED_BY_VALIDATION = "TINY_LIVE_BINANCE_READONLY_BLOCKED_BY_VALIDATION"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE"
LEDGER_FILENAME = "tiny_live_binance_readonly_precision_mark_price_gate.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CONFIRM_TINY_LIVE_BINANCE_READONLY_FETCH_PHRASE = (
    "I CONFIRM BINANCE READONLY PRECISION MARK PRICE CHECK ONLY; "
    "NO ORDER; NO SIGNATURE; NO PRIVATE ENDPOINT."
)

BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"
EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"
PREMIUM_INDEX_PATH = "/fapi/v1/premiumIndex"
ALLOWED_ENDPOINTS = [
    "GET /fapi/v1/exchangeInfo",
    "GET /fapi/v1/premiumIndex?symbol=BTCUSDT",
]
FORBIDDEN_ENDPOINTS = [
    "POST *",
    "PUT *",
    "DELETE *",
    "/fapi/v1/order",
    "/fapi/v1/batchOrders",
    "/fapi/v1/leverage",
    "/fapi/v2/account",
    "/fapi/v3/account",
    "any endpoint requiring timestamp/signature",
    "any endpoint requiring API key/secret",
]

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
    "private_endpoint_called": False,
    "api_key_used": False,
    "api_secret_used": False,
    "signature_created": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "kill_switch_disabled": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
    "binance_readonly_gate_only": True,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R241_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/tiny_live_order_payload_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_order_preflight_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_lane_arm_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_risk_contract_config_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_10_of_10_ready_packet.ndjson",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_binance_readonly_precision_mark_price_gate(
    *,
    log_dir: str | Path | None = None,
    fetch_binance_readonly: bool = False,
    confirm_tiny_live_binance_readonly_fetch: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    now: datetime | None = None,
    urlopen_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    confirmation_valid = confirm_tiny_live_binance_readonly_fetch == CONFIRM_TINY_LIVE_BINANCE_READONLY_FETCH_PHRASE
    symbol, _, direction, _ = _lane_parts(official_lane_key)
    safety = dict(SAFETY)

    try:
        latest_r241 = load_latest_tiny_live_precision_and_mark_price_preview(
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
        lane_controls = load_lane_controls_readonly(lane_path, official_lane_key=official_lane_key)
        input_summary = _build_input_summary(
            latest_r241=latest_r241,
            latest_r240=latest_r240,
            latest_r238=latest_r238,
            latest_r236=latest_r236,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_config=risk_config,
        )
        request_plan = build_readonly_request_plan(
            symbol=symbol,
            fetch_requested=fetch_binance_readonly,
            confirmation_valid=confirmation_valid,
        )
        plan_validation = validate_readonly_request_plan(request_plan)
        binance_result = _empty_binance_readonly_result(symbol)
        fetch_performed = False
        if fetch_binance_readonly and confirmation_valid and plan_validation.get("valid") is True:
            exchange_info = fetch_binance_public_exchange_info_for_symbol(symbol, urlopen_func=urlopen_func)
            mark_price = fetch_binance_public_mark_price_for_symbol(symbol, urlopen_func=urlopen_func)
            precision_snapshot = parse_symbol_precision_from_exchange_info(exchange_info, symbol=symbol)
            mark_price_snapshot = parse_mark_price_snapshot(mark_price, symbol=symbol)
            fetch_performed = True
            safety["binance_exchange_info_endpoint_called"] = True
            safety["binance_mark_price_endpoint_called"] = True
            safety["network_allowed"] = True
            binance_result = {
                "fetched": True,
                "exchange_info_endpoint_called": True,
                "mark_price_endpoint_called": True,
                "order_endpoint_called": False,
                "account_endpoint_called": False,
                "signed_request_created": False,
                "network_allowed": True,
                "precision_snapshot": precision_snapshot,
                "mark_price_snapshot": mark_price_snapshot,
            }
        quantity_preview = build_quantity_preview_from_readonly_data(
            notional_cap_usdt=44,
            precision_snapshot=binance_result["precision_snapshot"],
            mark_price_snapshot=binance_result["mark_price_snapshot"],
        )
        result_validation = validate_readonly_precision_mark_price_result(
            input_summary=input_summary,
            readonly_request_plan_validation=plan_validation,
            binance_readonly_result=binance_result,
            quantity_preview=quantity_preview,
            fetch_requested=fetch_binance_readonly,
            confirmation_valid=confirmation_valid,
        )
        matrix = build_binance_readonly_gate_matrix(
            input_summary=input_summary,
            readonly_request_plan_validation=plan_validation,
            readonly_fetch_confirmed=fetch_binance_readonly and confirmation_valid,
            readonly_fetch_performed=fetch_performed,
            binance_readonly_result=binance_result,
            quantity_preview=quantity_preview,
            validation=result_validation,
        )
        operator_packet = build_operator_binance_readonly_review_packet(matrix, fetch_requested=fetch_binance_readonly)
        overall = classify_tiny_live_binance_readonly_precision_mark_price_status(
            input_summary=input_summary,
            validation=result_validation,
            gate_matrix=matrix,
            fetch_requested=fetch_binance_readonly,
            confirmation_valid=confirmation_valid,
            fetch_performed=fetch_performed,
        )
        if fetch_binance_readonly and not confirmation_valid:
            status = TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_REJECTED
        elif fetch_performed:
            status = TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_FETCHED
        elif overall == TINY_LIVE_BINANCE_READONLY_READY_FOR_CONFIRMATION:
            status = TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_READY
        else:
            status = TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_BLOCKED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "readonly_fetch_requested": bool(fetch_binance_readonly),
            "readonly_fetch_performed": bool(fetch_performed),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "official_lane_key": official_lane_key,
                "symbol": symbol,
                "direction": direction,
                "binance_readonly_gate_only": True,
                "public_endpoints_only": True,
                "order_endpoint_allowed": False,
                "private_endpoint_allowed": False,
                "signed_request_allowed": False,
                "order_placed": False,
            },
            "input_summary": input_summary,
            "lane_controls_readonly_summary": lane_controls,
            "readonly_request_plan": request_plan,
            "readonly_request_plan_validation": plan_validation,
            "binance_readonly_result": binance_result,
            "quantity_preview": quantity_preview,
            "readonly_precision_mark_price_validation": result_validation,
            "binance_readonly_gate_matrix": matrix,
            "operator_binance_readonly_review_packet": operator_packet,
            "recommended_next_operator_move": _recommended_next_operator_move(operator_packet),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
            "binance_readonly_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if fetch_performed:
            record = append_tiny_live_binance_readonly_precision_mark_price_record(payload, log_dir=resolved_log_dir)
            payload["binance_readonly_record_id"] = record["binance_readonly_record_id"]
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        error_result = _empty_binance_readonly_result(symbol or "BTCUSDT")
        return _sanitize(
            {
                "status": TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "readonly_fetch_requested": bool(fetch_binance_readonly),
                "readonly_fetch_performed": False,
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {"official_lane_key": official_lane_key, "symbol": symbol or "BTCUSDT"},
                "input_summary": _empty_input_summary(),
                "readonly_request_plan": build_readonly_request_plan(
                    symbol=symbol or "BTCUSDT",
                    fetch_requested=fetch_binance_readonly,
                    confirmation_valid=confirmation_valid,
                ),
                "readonly_request_plan_validation": {
                    "valid": False,
                    "errors": ["binance_readonly_gate_error"],
                    "warnings": [],
                },
                "binance_readonly_result": error_result,
                "quantity_preview": _blocked_quantity_preview(["binance_readonly_gate_error"]),
                "binance_readonly_gate_matrix": build_binance_readonly_gate_matrix(
                    input_summary=_empty_input_summary(),
                    readonly_request_plan_validation={"valid": False, "errors": ["binance_readonly_gate_error"]},
                    readonly_fetch_confirmed=False,
                    readonly_fetch_performed=False,
                    binance_readonly_result=error_result,
                    quantity_preview=_blocked_quantity_preview(["binance_readonly_gate_error"]),
                    validation={"valid": False, "errors": ["binance_readonly_gate_error"]},
                ),
                "operator_binance_readonly_review_packet": build_operator_binance_readonly_review_packet(
                    {"blocked_by": ["binance_readonly_gate_error"]},
                    fetch_requested=fetch_binance_readonly,
                ),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R242 read-only gate error before any later phase.",
                "binance_readonly_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": safety,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_precision_and_mark_price_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_precision_and_mark_price_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_RECORDED"
            and record.get("precision_mark_price_preview_recorded") is True
        ):
            return _sanitize({**record, "r241_preview_found": True})
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


def build_readonly_request_plan(
    *,
    symbol: str = "BTCUSDT",
    fetch_requested: bool = False,
    confirmation_valid: bool = False,
) -> dict[str, Any]:
    normalized_symbol = symbol.upper()
    return {
        "would_call_network": bool(fetch_requested and confirmation_valid),
        "would_call_readonly_endpoints": True,
        "requires_confirmation": True,
        "allowed_endpoints": list(ALLOWED_ENDPOINTS),
        "forbidden_endpoints": list(FORBIDDEN_ENDPOINTS),
        "uses_api_key": False,
        "uses_api_secret": False,
        "requires_signature": False,
        "method_allowlist": ["GET"],
        "symbol": normalized_symbol,
        "planned_requests": [
            {"method": "GET", "path": EXCHANGE_INFO_PATH, "query": {}, "symbol": normalized_symbol},
            {"method": "GET", "path": PREMIUM_INDEX_PATH, "query": {"symbol": normalized_symbol}, "symbol": normalized_symbol},
        ],
    }


def validate_readonly_request_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if plan.get("symbol") != "BTCUSDT":
        errors.append("symbol_not_btcusdt")
    if plan.get("uses_api_key") is not False:
        errors.append("uses_api_key_not_false")
    if plan.get("uses_api_secret") is not False:
        errors.append("uses_api_secret_not_false")
    if plan.get("requires_signature") is not False:
        errors.append("requires_signature_not_false")
    if plan.get("method_allowlist") != ["GET"]:
        errors.append("method_allowlist_not_get_only")
    for request in plan.get("planned_requests") or []:
        validation = _validate_public_request(request)
        errors.extend(validation["errors"])
        warnings.extend(validation["warnings"])
    if len(plan.get("planned_requests") or []) != 2:
        errors.append("planned_request_count_invalid")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def fetch_binance_public_exchange_info_for_symbol(
    symbol: str = "BTCUSDT",
    *,
    urlopen_func: Callable[..., Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    normalized_symbol = symbol.upper()
    _raise_unless_allowed_public_request(
        {"method": "GET", "path": EXCHANGE_INFO_PATH, "query": {}, "symbol": normalized_symbol}
    )
    payload = _public_get(EXCHANGE_INFO_PATH, query={}, urlopen_func=urlopen_func, timeout=timeout)
    return {"symbol": normalized_symbol, "raw": payload}


def fetch_binance_public_mark_price_for_symbol(
    symbol: str = "BTCUSDT",
    *,
    urlopen_func: Callable[..., Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    normalized_symbol = symbol.upper()
    query = {"symbol": normalized_symbol}
    _raise_unless_allowed_public_request(
        {"method": "GET", "path": PREMIUM_INDEX_PATH, "query": query, "symbol": normalized_symbol}
    )
    payload = _public_get(PREMIUM_INDEX_PATH, query=query, urlopen_func=urlopen_func, timeout=timeout)
    return {"symbol": normalized_symbol, "raw": payload}


def parse_symbol_precision_from_exchange_info(exchange_info: Mapping[str, Any], *, symbol: str = "BTCUSDT") -> dict[str, Any]:
    normalized_symbol = symbol.upper()
    raw = exchange_info.get("raw") if isinstance(exchange_info.get("raw"), Mapping) else exchange_info
    symbols = raw.get("symbols") if isinstance(raw, Mapping) else []
    match = next((item for item in symbols if isinstance(item, Mapping) and item.get("symbol") == normalized_symbol), None)
    if not match:
        return _empty_precision_snapshot(normalized_symbol)
    filters = match.get("filters") if isinstance(match.get("filters"), list) else []
    lot = _filter(filters, "LOT_SIZE")
    price_filter = _filter(filters, "PRICE_FILTER")
    min_filter = _filter(filters, "MIN_NOTIONAL") or _filter(filters, "NOTIONAL")
    step_size = _number(lot.get("stepSize"))
    min_qty = _number(lot.get("minQty")) or step_size
    tick_size = _number(price_filter.get("tickSize"))
    min_notional = _number(min_filter.get("notional") or min_filter.get("minNotional"))
    return {
        "found": min_qty is not None and step_size is not None and tick_size is not None and min_notional is not None,
        "symbol": normalized_symbol,
        "quantity_precision": _int_or_none(match.get("quantityPrecision")) or _precision_from_step(step_size),
        "min_qty": min_qty,
        "step_size": step_size,
        "price_precision": _int_or_none(match.get("pricePrecision")) or _precision_from_step(tick_size),
        "tick_size": tick_size,
        "min_notional": min_notional,
        "source": "binance_public_exchangeInfo",
    }


def parse_mark_price_snapshot(mark_price_payload: Mapping[str, Any], *, symbol: str = "BTCUSDT") -> dict[str, Any]:
    normalized_symbol = symbol.upper()
    raw = mark_price_payload.get("raw") if isinstance(mark_price_payload.get("raw"), Mapping) else mark_price_payload
    if not isinstance(raw, Mapping) or raw.get("symbol") != normalized_symbol:
        return _empty_mark_price_snapshot(normalized_symbol)
    mark_price = _number(raw.get("markPrice"))
    timestamp = raw.get("time") or raw.get("timestamp")
    return {
        "found": mark_price is not None and mark_price > 0,
        "symbol": normalized_symbol,
        "mark_price": mark_price,
        "timestamp": timestamp,
        "source": "binance_public_premiumIndex",
    }


def build_quantity_preview_from_readonly_data(
    *,
    notional_cap_usdt: Any,
    precision_snapshot: Mapping[str, Any],
    mark_price_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    blocked_by: list[str] = []
    if precision_snapshot.get("found") is not True:
        blocked_by.append("precision_snapshot_missing")
    if mark_price_snapshot.get("found") is not True:
        blocked_by.append("mark_price_missing")
    notional = _decimal(notional_cap_usdt)
    mark_price = _decimal(mark_price_snapshot.get("mark_price"))
    step = _decimal(precision_snapshot.get("step_size"))
    min_qty = _decimal(precision_snapshot.get("min_qty"))
    min_notional = _decimal(precision_snapshot.get("min_notional"))
    if notional is None or notional <= 0:
        blocked_by.append("notional_cap_invalid")
    if mark_price is None or mark_price <= 0:
        blocked_by.append("mark_price_invalid")
    if step is None or step <= 0:
        blocked_by.append("step_size_invalid")
    if min_qty is None or min_qty <= 0:
        blocked_by.append("min_qty_invalid")
    if min_notional is None or min_notional < 0:
        blocked_by.append("min_notional_unknown")
    if blocked_by:
        return _blocked_quantity_preview(_dedupe(blocked_by))
    quantity_raw = notional / mark_price
    quantity_rounded = (quantity_raw / step).to_integral_value(rounding=ROUND_FLOOR) * step
    notional_after_rounding = quantity_rounded * mark_price
    min_notional_quantity = (min_notional / mark_price / step).to_integral_value(rounding=ROUND_FLOOR) * step
    if min_notional_quantity * mark_price < min_notional:
        min_notional_quantity += step
    minimum_valid_quantity = max(min_qty, min_notional_quantity)
    minimum_valid_notional = minimum_valid_quantity * mark_price
    if quantity_rounded <= 0:
        blocked_by.append("quantity_rounds_to_zero")
    min_qty_ok = bool(quantity_rounded >= min_qty)
    if not min_qty_ok:
        blocked_by.append("min_qty_not_met_after_rounding")
    min_notional_ok = bool(notional_after_rounding >= min_notional)
    if not min_notional_ok:
        blocked_by.append("min_notional_not_met_after_rounding")
    return {
        "can_compute": not blocked_by,
        "quantity_raw": _float(quantity_raw),
        "quantity_rounded": _float(quantity_rounded),
        "notional_after_rounding": _float(notional_after_rounding),
        "min_qty": _float(min_qty),
        "step_size": _float(step),
        "min_notional": _float(min_notional),
        "min_qty_ok": min_qty_ok,
        "min_notional_ok": min_notional_ok,
        "minimum_valid_quantity": _float(minimum_valid_quantity),
        "minimum_valid_notional_after_rounding": _float(minimum_valid_notional),
        "configured_cap_possible": bool(notional >= minimum_valid_notional),
        "blocked_by": _dedupe(blocked_by),
    }


def build_exchange_minimum_tiny_live_decision_packet(
    *,
    configured_cap_usdt: Any = 44,
    precision_snapshot: Mapping[str, Any],
    mark_price_snapshot: Mapping[str, Any],
    operator_reported_wallet_usdt: Any = 126,
) -> dict[str, Any]:
    quantity_preview = build_quantity_preview_from_readonly_data(
        notional_cap_usdt=configured_cap_usdt,
        precision_snapshot=precision_snapshot,
        mark_price_snapshot=mark_price_snapshot,
    )
    configured_cap = _number(configured_cap_usdt)
    minimum_valid_notional = _number(quantity_preview.get("minimum_valid_notional_after_rounding"))
    wallet_amount = _number(operator_reported_wallet_usdt)
    cap_possible = (
        configured_cap is not None
        and minimum_valid_notional is not None
        and configured_cap >= minimum_valid_notional
        and quantity_preview.get("blocked_by") == []
    )
    recommended_cap = None if cap_possible else minimum_valid_notional
    wallet_enough = None
    if wallet_amount is not None and minimum_valid_notional is not None:
        wallet_enough = wallet_amount >= minimum_valid_notional
    return _sanitize(
        {
            "status": "EXCHANGE_MINIMUM_TINY_LIVE_DECISION_PACKET_READY",
            "symbol": str(precision_snapshot.get("symbol") or mark_price_snapshot.get("symbol") or "BTCUSDT"),
            "configured_proper_tiny_cap_usdt": configured_cap,
            "configured_cap_possible": bool(cap_possible),
            "configured_cap_blocked_by": list(quantity_preview.get("blocked_by") or []),
            "block_reason": None if cap_possible else "proper_tiny_live_below_exchange_minimum",
            "min_quantity": precision_snapshot.get("min_qty"),
            "step_size": precision_snapshot.get("step_size"),
            "min_notional": precision_snapshot.get("min_notional"),
            "mark_price": mark_price_snapshot.get("mark_price"),
            "minimum_valid_quantity_after_rounding": quantity_preview.get("minimum_valid_quantity"),
            "minimum_valid_notional_after_rounding": minimum_valid_notional,
            "candidate_quantity_at_configured_cap": quantity_preview.get("quantity_rounded"),
            "candidate_notional_at_configured_cap": quantity_preview.get("notional_after_rounding"),
            "wallet_funded_amount_usdt": wallet_amount,
            "wallet_funded_amount_source": "operator_reported_phase_context_no_account_check"
            if wallet_amount is not None
            else "unknown_not_checked",
            "account_balance_checked": False,
            "wallet_supports_exchange_minimum_tiny": wallet_enough,
            "recommended_operator_decision": "ACCEPT_EXCHANGE_MINIMUM_TINY_LIVE_CAP"
            if recommended_cap is not None
            else "KEEP_44_USDT_PROPER_TINY_CAP",
            "recommended_cap_usdt": recommended_cap,
            "recommended_cap_applied": False,
            "recommended_cap_warning": (
                "Recommended exchange-minimum cap is not applied automatically; operator approval and a later safe write phase are required."
                if recommended_cap is not None
                else "No cap increase recommended by this packet."
            ),
            "safe_next_command": (
                "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
                "--log-dir logs/hammer_radar_forward tiny-live-binance-readonly-precision-mark-price-gate "
                "--fetch-binance-readonly --confirm-tiny-live-binance-readonly-fetch "
                "\"I CONFIRM BINANCE READONLY PRECISION MARK PRICE CHECK ONLY; NO ORDER; NO SIGNATURE; NO PRIVATE ENDPOINT.\""
            ),
            "go_no_go": "NO-GO",
            "final_command_available": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "secrets_shown": False,
        }
    )


def validate_readonly_precision_mark_price_result(
    *,
    input_summary: Mapping[str, Any],
    readonly_request_plan_validation: Mapping[str, Any],
    binance_readonly_result: Mapping[str, Any],
    quantity_preview: Mapping[str, Any],
    fetch_requested: bool,
    confirmation_valid: bool,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not input_summary.get("r241_preview_ready"):
        errors.append("r241_preview_not_ready")
    if not input_summary.get("r240_payload_valid"):
        errors.append("r240_payload_artifact_invalid_or_missing")
    if not input_summary.get("r238_order_preflight_valid"):
        errors.append("r238_order_preflight_invalid_or_missing")
    if not input_summary.get("risk_contract_valid"):
        errors.append("risk_contract_invalid_or_missing")
    if readonly_request_plan_validation.get("valid") is not True:
        errors.extend(str(item) for item in readonly_request_plan_validation.get("errors") or ["readonly_plan_invalid"])
    if fetch_requested and not confirmation_valid:
        errors.append("confirmation_invalid")
    if binance_readonly_result.get("order_endpoint_called") is not False:
        errors.append("order_endpoint_called")
    if binance_readonly_result.get("account_endpoint_called") is not False:
        errors.append("account_endpoint_called")
    if binance_readonly_result.get("signed_request_created") is not False:
        errors.append("signed_request_created")
    if fetch_requested and confirmation_valid:
        if binance_readonly_result.get("fetched") is not True:
            errors.append("readonly_fetch_not_performed")
        if binance_readonly_result.get("precision_snapshot", {}).get("found") is not True:
            errors.append("precision_snapshot_missing")
        if binance_readonly_result.get("mark_price_snapshot", {}).get("found") is not True:
            errors.append("mark_price_missing")
        if quantity_preview.get("can_compute") is not True:
            warnings.append("quantity_preview_blocked")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def build_binance_readonly_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    readonly_request_plan_validation: Mapping[str, Any],
    readonly_fetch_confirmed: bool,
    readonly_fetch_performed: bool,
    binance_readonly_result: Mapping[str, Any],
    quantity_preview: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if not input_summary.get("r241_preview_ready"):
        blockers.append("r241_preview_not_ready")
    if not input_summary.get("r240_payload_valid"):
        blockers.append("payload_artifact_not_ready")
    if readonly_request_plan_validation.get("valid") is not True:
        blockers.extend(str(item) for item in readonly_request_plan_validation.get("errors") or ["readonly_plan_invalid"])
    if readonly_fetch_performed:
        if binance_readonly_result.get("precision_snapshot", {}).get("found") is not True:
            blockers.append("precision_snapshot_missing")
        if binance_readonly_result.get("mark_price_snapshot", {}).get("found") is not True:
            blockers.append("mark_price_missing")
        if quantity_preview.get("can_compute") is not True:
            blockers.extend(str(item) for item in quantity_preview.get("blocked_by") or ["quantity_preview_blocked"])
    if validation.get("valid") is not True:
        blockers.extend(str(item) for item in validation.get("errors") or ["validation_failed"])
    return {
        "r241_preview_ready": bool(input_summary.get("r241_preview_ready")),
        "payload_artifact_ready": bool(input_summary.get("r240_payload_valid")),
        "readonly_plan_valid": readonly_request_plan_validation.get("valid") is True,
        "readonly_fetch_confirmed": bool(readonly_fetch_confirmed),
        "readonly_fetch_performed": bool(readonly_fetch_performed),
        "precision_snapshot_found": binance_readonly_result.get("precision_snapshot", {}).get("found") is True,
        "mark_price_found": binance_readonly_result.get("mark_price_snapshot", {}).get("found") is True,
        "quantity_preview_ready": quantity_preview.get("can_compute") is True,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_binance_readonly_review_packet(
    binance_readonly_gate_matrix: Mapping[str, Any],
    *,
    fetch_requested: bool = False,
) -> dict[str, Any]:
    if binance_readonly_gate_matrix.get("readonly_fetch_performed") is True:
        next_action = "REVIEW_R242_RESULT"
    elif binance_readonly_gate_matrix.get("r241_preview_ready") is True and binance_readonly_gate_matrix.get("payload_artifact_ready") is True:
        next_action = "CONFIRM_R242_BINANCE_READONLY_FETCH"
    else:
        next_action = "WAIT"
    return {
        "operator_should_review_readonly_plan": not fetch_requested,
        "operator_confirmation_required": True,
        "operator_should_create_executable_payload_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": next_action,
        "explicit_non_actions": [
            "do not place order",
            "do not call order endpoint",
            "do not sign request",
            "do not create executable payload",
        ],
    }


def classify_tiny_live_binance_readonly_precision_mark_price_status(
    *,
    input_summary: Mapping[str, Any],
    validation: Mapping[str, Any],
    gate_matrix: Mapping[str, Any],
    fetch_requested: bool,
    confirmation_valid: bool,
    fetch_performed: bool,
) -> str:
    if fetch_requested and not confirmation_valid:
        return TINY_LIVE_BINANCE_READONLY_REJECTED_BAD_CONFIRMATION
    if not input_summary.get("r241_preview_ready"):
        return TINY_LIVE_BINANCE_READONLY_BLOCKED_BY_R241_PREVIEW
    if not input_summary.get("r240_payload_valid"):
        return TINY_LIVE_BINANCE_READONLY_BLOCKED_BY_PAYLOAD
    if validation.get("valid") is not True and not (fetch_requested and confirmation_valid):
        return TINY_LIVE_BINANCE_READONLY_BLOCKED_BY_VALIDATION
    if fetch_performed and gate_matrix.get("quantity_preview_ready") is True:
        return TINY_LIVE_BINANCE_READONLY_FETCHED_QUANTITY_PREVIEW_READY
    if fetch_performed:
        return TINY_LIVE_BINANCE_READONLY_FETCHED_QUANTITY_PREVIEW_BLOCKED
    return TINY_LIVE_BINANCE_READONLY_READY_FOR_CONFIRMATION


def append_tiny_live_binance_readonly_precision_mark_price_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_binance_readonly_precision_mark_price_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "binance_readonly_record_id": record.get("binance_readonly_record_id")
            or f"r242_binance_readonly_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_FETCHED,
            "generated_at": record.get("generated_at"),
            "readonly_fetch_requested": record.get("readonly_fetch_requested") is True,
            "readonly_fetch_performed": record.get("readonly_fetch_performed") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "readonly_request_plan": dict(record.get("readonly_request_plan") or {}),
            "readonly_request_plan_validation": dict(record.get("readonly_request_plan_validation") or {}),
            "binance_readonly_result": dict(record.get("binance_readonly_result") or {}),
            "quantity_preview": dict(record.get("quantity_preview") or {}),
            "binance_readonly_gate_matrix": dict(record.get("binance_readonly_gate_matrix") or {}),
            "operator_binance_readonly_review_packet": dict(
                record.get("operator_binance_readonly_review_packet") or {}
            ),
            "binance_readonly_overall_status": record.get("binance_readonly_overall_status"),
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


def load_tiny_live_binance_readonly_precision_mark_price_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_binance_readonly_precision_mark_price_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_binance_readonly_precision_mark_price_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_fetch_performed": latest.get("readonly_fetch_performed") is True,
        "latest_overall_status": latest.get("binance_readonly_overall_status"),
    }


def tiny_live_binance_readonly_precision_mark_price_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_binance_readonly_precision_mark_price_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r241: Mapping[str, Any],
    latest_r240: Mapping[str, Any],
    latest_r238: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_config: Mapping[str, Any],
) -> dict[str, Any]:
    artifact = latest_r240.get("order_payload") if isinstance(latest_r240.get("order_payload"), Mapping) else {}
    order_preflight = latest_r238.get("order_preflight") if isinstance(latest_r238.get("order_preflight"), Mapping) else {}
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    risk_contract = (
        risk_config.get("matching_risk_contract") if isinstance(risk_config.get("matching_risk_contract"), Mapping) else {}
    )
    r228_matrix = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    r241_overall = str(latest_r241.get("precision_mark_price_preview_overall_status") or "")
    return {
        "r241_preview_found": bool(latest_r241),
        "r241_preview_ready": bool(latest_r241)
        and r241_overall
        in {
            "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_NEEDS_BINANCE_READONLY_CHECK",
            "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY_FOR_FUTURE_GATE",
        },
        "r240_payload_found": bool(latest_r240),
        "r240_payload_valid": validate_non_executable_order_payload_artifact(artifact).get("valid") is True
        if artifact
        else False,
        "r238_order_preflight_found": bool(latest_r238),
        "r238_order_preflight_valid": validate_order_preflight_object(order_preflight).get("valid") is True
        if order_preflight
        else False,
        "r236_lane_arm_found": bool(latest_r236),
        "r236_lane_arm_valid": validate_lane_arm_object(lane_arm).get("valid") is True if lane_arm else False,
        "r230_risk_contract_config_found": bool(latest_r230) and bool(risk_contract),
        "risk_contract_valid": validate_tiny_live_risk_contract_config_entry(risk_contract).get("valid") is True
        if risk_contract
        else False,
        "evidence_ready": r228_matrix.get("evidence_ready") is True,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r241_preview_found": False,
        "r241_preview_ready": False,
        "r240_payload_found": False,
        "r240_payload_valid": False,
        "r238_order_preflight_found": False,
        "r238_order_preflight_valid": False,
        "r236_lane_arm_found": False,
        "r236_lane_arm_valid": False,
        "r230_risk_contract_config_found": False,
        "risk_contract_valid": False,
        "evidence_ready": False,
    }


def _public_get(
    path: str,
    *,
    query: Mapping[str, str],
    urlopen_func: Callable[..., Any] | None,
    timeout: float,
) -> Any:
    encoded = urllib.parse.urlencode(query)
    url = f"{BINANCE_FUTURES_BASE_URL}{path}" + (f"?{encoded}" if encoded else "")
    opener = urlopen_func or urllib.request.urlopen
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "hammer-radar-r242-readonly"})
    with opener(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body.decode("utf-8"))


def _validate_public_request(request: Mapping[str, Any]) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    method = str(request.get("method") or "").upper()
    path = str(request.get("path") or "")
    query = request.get("query") if isinstance(request.get("query"), Mapping) else {}
    if method != "GET":
        errors.append("non_get_method_forbidden")
    forbidden_fragments = ("order", "batchOrders", "leverage", "account", "position", "margin", "transfer", "withdraw")
    if any(fragment.lower() in path.lower() for fragment in forbidden_fragments):
        errors.append("forbidden_endpoint_path")
    if path == EXCHANGE_INFO_PATH and query:
        errors.append("exchange_info_query_not_allowed")
    elif path == PREMIUM_INDEX_PATH and dict(query) != {"symbol": "BTCUSDT"}:
        errors.append("premium_index_query_invalid")
    elif path not in {EXCHANGE_INFO_PATH, PREMIUM_INDEX_PATH}:
        errors.append("path_not_allowlisted")
    if any(key in query for key in ("timestamp", "signature", "recvWindow")):
        errors.append("signed_query_param_forbidden")
    return {"errors": errors, "warnings": warnings}


def _raise_unless_allowed_public_request(request: Mapping[str, Any]) -> None:
    validation = _validate_public_request(request)
    if validation["errors"]:
        raise ValueError(",".join(validation["errors"]))


def _empty_binance_readonly_result(symbol: str) -> dict[str, Any]:
    return {
        "fetched": False,
        "exchange_info_endpoint_called": False,
        "mark_price_endpoint_called": False,
        "order_endpoint_called": False,
        "account_endpoint_called": False,
        "signed_request_created": False,
        "network_allowed": False,
        "precision_snapshot": _empty_precision_snapshot(symbol),
        "mark_price_snapshot": _empty_mark_price_snapshot(symbol),
    }


def _empty_precision_snapshot(symbol: str) -> dict[str, Any]:
    return {
        "found": False,
        "symbol": symbol,
        "quantity_precision": None,
        "min_qty": None,
        "step_size": None,
        "price_precision": None,
        "tick_size": None,
        "min_notional": None,
        "source": None,
    }


def _empty_mark_price_snapshot(symbol: str) -> dict[str, Any]:
    return {"found": False, "symbol": symbol, "mark_price": None, "timestamp": None, "source": None}


def _blocked_quantity_preview(blocked_by: Sequence[str]) -> dict[str, Any]:
    return {
        "can_compute": False,
        "quantity_raw": None,
        "quantity_rounded": None,
        "notional_after_rounding": None,
        "min_qty": None,
        "step_size": None,
        "min_notional": None,
        "min_qty_ok": None,
        "min_notional_ok": None,
        "minimum_valid_quantity": None,
        "minimum_valid_notional_after_rounding": None,
        "configured_cap_possible": False,
        "blocked_by": _dedupe(list(blocked_by)),
    }


def _recommended_next_operator_move(operator_packet: Mapping[str, Any]) -> str:
    return str(operator_packet.get("next_required_human_action") or "WAIT")


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("readonly_fetch_performed") is not True:
        return "Run R242 only after exact operator confirmation for public Binance read-only precision and mark price."
    if matrix.get("quantity_preview_ready") is True:
        return "Create R243 executable payload preview or R243 quantity-application preview; no signing, submit, private endpoint, or order."
    return "Review R242 precision/mark-price blockers before any executable payload preview."


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


def _filter(filters: Sequence[Any], filter_type: str) -> Mapping[str, Any]:
    for item in filters:
        if isinstance(item, Mapping) and item.get("filterType") == filter_type:
            return item
    return {}


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: Decimal) -> float:
    return float(value.normalize())


def _precision_from_step(step: float | None) -> int | None:
    decimal = _decimal(step)
    if decimal is None:
        return None
    return max(0, -decimal.normalize().as_tuple().exponent)


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
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
