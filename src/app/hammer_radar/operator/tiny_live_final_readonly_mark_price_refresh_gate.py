"""R253 tiny-live final read-only mark-price refresh gate.

This phase performs only the final Binance public read-only refresh required
before a later submit-gate preview. It never signs, submits, calls private or
order endpoints, reads secrets, or mutates env/config/lane controls.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_binance_readonly_precision_mark_price_gate import (
    ALLOWED_ENDPOINTS,
    EXCHANGE_INFO_PATH,
    FORBIDDEN_ENDPOINTS,
    PREMIUM_INDEX_PATH,
    fetch_binance_public_exchange_info_for_symbol,
    fetch_binance_public_mark_price_for_symbol,
    load_tiny_live_binance_readonly_precision_mark_price_records,
    parse_mark_price_snapshot,
    parse_symbol_precision_from_exchange_info,
)
from src.app.hammer_radar.operator.tiny_live_executable_payload_write_gate import (
    load_tiny_live_executable_payload_write_gate_records,
    validate_executable_payload_artifact,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_runtime_source_write_gate import (
    load_tiny_live_signed_request_runtime_source_write_gate_records,
    validate_r251e_signed_request_artifact,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_write_gate import (
    load_tiny_live_signed_request_write_gate_records,
    validate_signed_request_artifact,
)
from src.app.hammer_radar.operator.tiny_live_stop_take_profit_source_gate import (
    load_tiny_live_stop_take_profit_source_gate_records,
    validate_short_stop_take_profit_levels,
)
from src.app.hammer_radar.operator.tiny_live_submit_readiness_preview import (
    load_tiny_live_submit_readiness_preview_records,
)

TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_READY = (
    "TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_READY"
)
TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_REJECTED = (
    "TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_REJECTED"
)
TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_FETCHED = (
    "TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_FETCHED"
)
TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_BLOCKED = (
    "TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_BLOCKED"
)
TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_ERROR = (
    "TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_ERROR"
)

TINY_LIVE_FINAL_READONLY_REFRESH_READY_FOR_CONFIRMATION = (
    "TINY_LIVE_FINAL_READONLY_REFRESH_READY_FOR_CONFIRMATION"
)
TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_REGENERATE_SIGNED_REQUEST_REQUIRED = (
    "TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_REGENERATE_SIGNED_REQUEST_REQUIRED"
)
TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_READY_FOR_SUBMIT_GATE_PREVIEW = (
    "TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_READY_FOR_SUBMIT_GATE_PREVIEW"
)
TINY_LIVE_FINAL_READONLY_REFRESH_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_FINAL_READONLY_REFRESH_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_ENDPOINT_SAFETY = (
    "TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_ENDPOINT_SAFETY"
)
TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_SIGNED_ARTIFACT = (
    "TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_SIGNED_ARTIFACT"
)
TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_MARKET_VALIDATION = (
    "TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_MARKET_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE"
LEDGER_FILENAME = "tiny_live_final_readonly_mark_price_refresh_gate.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE = (
    "I CONFIRM TINY LIVE FINAL READONLY MARK PRICE REFRESH ONLY; "
    "NO SUBMIT; NO ORDER; NO PRIVATE BINANCE CALL."
)

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_submit_readiness_preview.ndjson",
    "logs/hammer_radar_forward/tiny_live_signed_request_runtime_source_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson",
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
    "final_readonly_refresh_gate_only": True,
    "hmac_signature_created": False,
    "signed_request_written": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "submit_allowed": False,
    "submit_attempted": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "binance_exchange_info_endpoint_called": False,
    "binance_mark_price_endpoint_called": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "binance_account_endpoint_called": False,
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


def build_tiny_live_final_readonly_mark_price_refresh_gate(
    *,
    log_dir: str | Path | None = None,
    fetch_final_readonly_market: bool = False,
    confirm_tiny_live_final_readonly_refresh: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
    urlopen_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_final_readonly_refresh
        == CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE
    )
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    safety = dict(SAFETY)

    try:
        latest_r252 = load_latest_tiny_live_submit_readiness_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r251e = load_latest_tiny_live_signed_request_runtime_source_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r251 = load_latest_tiny_live_signed_request_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r249 = load_latest_tiny_live_executable_payload_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r248 = load_latest_tiny_live_stop_take_profit_source_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r242 = load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )

        r251_artifact = _signed_request_artifact(latest_r251)
        r249_artifact = _executable_payload_artifact(latest_r249)
        input_summary = _build_input_summary(
            latest_r252=latest_r252,
            latest_r251e=latest_r251e,
            latest_r251=latest_r251,
            latest_r249=latest_r249,
            latest_r248=latest_r248,
            r251_artifact=r251_artifact,
            r249_artifact=r249_artifact,
        )
        request_plan = build_allowed_public_readonly_request_plan(
            fetch_requested=fetch_final_readonly_market,
            confirmation_valid=confirmation_valid,
            symbol=symbol,
        )
        endpoint_safety = validate_final_readonly_endpoint_safety(request_plan)
        fresh_context = build_fresh_market_context_summary()
        final_readonly_market_fetched = False

        if fetch_final_readonly_market and confirmation_valid and endpoint_safety["valid"] is True:
            exchange_info = fetch_final_readonly_exchange_info(symbol=symbol, urlopen_func=urlopen_func)
            mark_payload = fetch_final_readonly_mark_price(symbol=symbol, urlopen_func=urlopen_func)
            precision = extract_btcusdt_precision_snapshot(exchange_info)
            mark = extract_final_mark_price_snapshot(mark_payload)
            fresh_context = build_fresh_market_context_summary(
                precision_snapshot=precision,
                mark_price_snapshot=mark,
            )
            final_readonly_market_fetched = True
            safety["binance_exchange_info_endpoint_called"] = True
            safety["binance_mark_price_endpoint_called"] = True
            safety["network_allowed"] = True

        signed_summary = _build_signed_artifact_context_summary(
            r251_artifact=r251_artifact,
            r249_artifact=r249_artifact,
            r248_record=latest_r248,
        )
        comparison = compare_fresh_context_to_signed_artifact(
            fresh_market_context_summary=fresh_context,
            signed_artifact_context_summary=signed_summary,
        )
        regeneration = build_signed_request_regeneration_decision(
            input_summary=input_summary,
            endpoint_safety_validation=endpoint_safety,
            fresh_market_context_summary=fresh_context,
            fresh_vs_signed_context_comparison=comparison,
            fetch_requested=fetch_final_readonly_market,
            confirmation_valid=confirmation_valid,
        )
        matrix = build_final_readonly_refresh_gate_matrix(
            input_summary=input_summary,
            endpoint_safety_validation=endpoint_safety,
            final_readonly_fetch_confirmed=fetch_final_readonly_market and confirmation_valid,
            fresh_market_context_summary=fresh_context,
            fresh_vs_signed_context_comparison=comparison,
            signed_request_regeneration_decision=regeneration,
        )
        operator_packet = build_operator_final_readonly_refresh_packet(matrix, regeneration)
        overall = classify_tiny_live_final_readonly_mark_price_refresh_gate_status(
            input_summary=input_summary,
            endpoint_safety_validation=endpoint_safety,
            final_readonly_refresh_gate_matrix=matrix,
            fetch_requested=fetch_final_readonly_market,
            confirmation_valid=confirmation_valid,
            final_readonly_market_fetched=final_readonly_market_fetched,
            signed_request_regeneration_decision=regeneration,
        )

        if fetch_final_readonly_market and not confirmation_valid:
            status = TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_REJECTED
        elif final_readonly_market_fetched:
            status = TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_FETCHED
        elif matrix["r252_submit_readiness_ready"] and matrix["signed_artifact_ready"] and endpoint_safety["valid"]:
            status = TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_READY
        else:
            status = TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_BLOCKED

        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "fetch_final_readonly_market_requested": bool(fetch_final_readonly_market),
                "confirmation_valid": bool(confirmation_valid),
                "final_readonly_market_fetched": bool(final_readonly_market_fetched),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "final_readonly_refresh_gate_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "private_binance_endpoint_called": False,
                    "network_allowed": bool(final_readonly_market_fetched),
                },
                "input_summary": input_summary,
                "allowed_public_readonly_request_plan": request_plan,
                "endpoint_safety_validation": endpoint_safety,
                "fresh_market_context_summary": fresh_context,
                "signed_artifact_context_summary": signed_summary,
                "fresh_vs_signed_context_comparison": comparison,
                "signed_request_regeneration_decision": regeneration,
                "final_readonly_refresh_gate_matrix": matrix,
                "operator_final_readonly_refresh_packet": operator_packet,
                "recommended_next_operator_move": _recommended_next_operator_move(operator_packet),
                "recommended_next_engineering_move": _recommended_next_engineering_move(regeneration, matrix),
                "final_readonly_refresh_overall_status": overall,
                "do_not_run_yet": _do_not_run_yet(),
                "safety": safety,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if final_readonly_market_fetched and endpoint_safety["valid"] is True:
            record = append_tiny_live_final_readonly_mark_price_refresh_gate_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_final_readonly_refresh=confirm_tiny_live_final_readonly_refresh,
            )
            payload["final_readonly_refresh_gate_record_id"] = record["final_readonly_refresh_gate_record_id"]
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        return _sanitize(
            {
                "status": TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "fetch_final_readonly_market_requested": bool(fetch_final_readonly_market),
                "confirmation_valid": bool(confirmation_valid),
                "final_readonly_market_fetched": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "final_readonly_refresh_gate_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "private_binance_endpoint_called": False,
                    "network_allowed": False,
                },
                "input_summary": _empty_input_summary(),
                "allowed_public_readonly_request_plan": build_allowed_public_readonly_request_plan(
                    fetch_requested=fetch_final_readonly_market,
                    confirmation_valid=confirmation_valid,
                    symbol=symbol,
                ),
                "endpoint_safety_validation": {
                    "valid": False,
                    "errors": ["final_readonly_refresh_gate_error"],
                    "warnings": [],
                    "exchange_info_endpoint_allowed": False,
                    "mark_price_endpoint_allowed": False,
                    "order_endpoint_called": False,
                    "account_endpoint_called": False,
                    "private_endpoint_called": False,
                    "signed_endpoint_called": False,
                },
                "fresh_market_context_summary": build_fresh_market_context_summary(),
                "signed_artifact_context_summary": _empty_signed_artifact_context_summary(),
                "fresh_vs_signed_context_comparison": _empty_comparison(),
                "signed_request_regeneration_decision": {
                    "must_regenerate_signed_request_before_submit": None,
                    "reason": "final_readonly_refresh_gate_error",
                    "blocking_reasons": ["final_readonly_refresh_gate_error"],
                    "submit_gate_preview_allowed_next": False,
                },
                "final_readonly_refresh_gate_matrix": {
                    **_empty_matrix(),
                    "blocked_by": ["final_readonly_refresh_gate_error"],
                },
                "operator_final_readonly_refresh_packet": {
                    "operator_should_review_fresh_market_context": False,
                    "operator_should_regenerate_signed_request": False,
                    "operator_should_continue_to_submit_gate_preview": False,
                    "operator_should_submit_now": False,
                    "operator_should_place_order": False,
                    "next_required_human_action": "FIX_BLOCKER",
                    "explicit_non_actions": _explicit_non_actions(),
                },
                "recommended_next_operator_move": "FIX_BLOCKER",
                "recommended_next_engineering_move": "Fix R253 final read-only refresh gate error before any submit preview.",
                "final_readonly_refresh_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": safety,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_submit_readiness_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_submit_readiness_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if (
            target.get("official_lane_key") == official_lane_key
            and record.get("submit_readiness_preview_recorded") is True
            and record.get("submit_readiness_overall_status")
            == "TINY_LIVE_SUBMIT_READINESS_RECORDED_FINAL_READONLY_REFRESH_REQUIRED"
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_signed_request_runtime_source_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_signed_request_runtime_source_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if (
            target.get("official_lane_key") == official_lane_key
            and record.get("signed_request_written") is True
            and record.get("post_write_verification", {}).get("matching_signed_request_valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_signed_request_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_signed_request_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        artifact = _signed_request_artifact(record)
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("signed_request_written") is True
            and validate_signed_request_artifact(artifact).get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_executable_payload_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_executable_payload_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        artifact = _executable_payload_artifact(record)
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("executable_payload_written") is True
            and validate_executable_payload_artifact(artifact).get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_stop_take_profit_source_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_stop_take_profit_source_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        if _record_matches_lane(record, official_lane_key) and _validate_r248_record(record).get("valid") is True:
            return _sanitize(record)
    return {}


def load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_binance_readonly_precision_mark_price_records(log_dir=log_dir, limit=50)
    for record in records:
        if _record_matches_lane(record, official_lane_key) and _validate_r242_record(record).get("valid") is True:
            return _sanitize(record)
    return {}


def build_allowed_public_readonly_request_plan(
    *,
    fetch_requested: bool = False,
    confirmation_valid: bool = False,
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    normalized_symbol = symbol.upper()
    return {
        "preview_only": not bool(fetch_requested and confirmation_valid),
        "allowed_endpoints": list(ALLOWED_ENDPOINTS),
        "forbidden_endpoints": [
            "POST /fapi/v1/order",
            "GET /fapi/v2/account",
            "private/signed endpoints",
        ],
        "network_allowed": bool(fetch_requested and confirmation_valid),
        "requires_confirmation": True,
        "planned_requests": [
            {"method": "GET", "path": EXCHANGE_INFO_PATH, "query": {}, "symbol": normalized_symbol},
            {
                "method": "GET",
                "path": PREMIUM_INDEX_PATH,
                "query": {"symbol": normalized_symbol},
                "symbol": normalized_symbol,
            },
        ],
        "method_allowlist": ["GET"],
        "uses_api_key": False,
        "uses_api_secret": False,
        "requires_signature": False,
        "source_allowlist": list(FORBIDDEN_ENDPOINTS),
    }


def fetch_final_readonly_exchange_info(
    symbol: str = "BTCUSDT", *, urlopen_func: Callable[..., Any] | None = None
) -> dict[str, Any]:
    return fetch_binance_public_exchange_info_for_symbol(symbol=symbol, urlopen_func=urlopen_func)


def fetch_final_readonly_mark_price(
    symbol: str = "BTCUSDT", *, urlopen_func: Callable[..., Any] | None = None
) -> dict[str, Any]:
    return fetch_binance_public_mark_price_for_symbol(symbol=symbol, urlopen_func=urlopen_func)


def extract_btcusdt_precision_snapshot(exchange_info: Mapping[str, Any]) -> dict[str, Any]:
    return parse_symbol_precision_from_exchange_info(exchange_info, symbol="BTCUSDT")


def extract_final_mark_price_snapshot(mark_price_payload: Mapping[str, Any]) -> dict[str, Any]:
    return parse_mark_price_snapshot(mark_price_payload, symbol="BTCUSDT")


def validate_final_readonly_endpoint_safety(plan: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    requests = plan.get("planned_requests") if isinstance(plan.get("planned_requests"), list) else []
    exchange_allowed = False
    mark_allowed = False
    order_called = False
    account_called = False
    private_called = False
    signed_called = False
    if plan.get("uses_api_key") is not False:
        errors.append("uses_api_key_not_false")
    if plan.get("uses_api_secret") is not False:
        errors.append("uses_api_secret_not_false")
    if plan.get("requires_signature") is not False:
        errors.append("requires_signature_not_false")
    if plan.get("method_allowlist") != ["GET"]:
        errors.append("method_allowlist_not_get_only")
    if len(requests) != 2:
        errors.append("planned_request_count_invalid")
    for request in requests:
        method = str(request.get("method") or "").upper()
        path = str(request.get("path") or "")
        query = request.get("query") if isinstance(request.get("query"), Mapping) else {}
        if method != "GET":
            errors.append("non_get_method_forbidden")
        lower_path = path.lower()
        if "order" in lower_path or "batchorders" in lower_path:
            order_called = True
            errors.append("order_endpoint_forbidden")
        if "account" in lower_path:
            account_called = True
            errors.append("account_endpoint_forbidden")
        if any(fragment in lower_path for fragment in ("leverage", "position", "margin", "transfer", "withdraw")):
            private_called = True
            errors.append("private_endpoint_forbidden")
        if any(key in query for key in ("timestamp", "signature", "recvWindow")):
            signed_called = True
            errors.append("signed_query_param_forbidden")
        if path == EXCHANGE_INFO_PATH and not query:
            exchange_allowed = True
        elif path == PREMIUM_INDEX_PATH and dict(query) == {"symbol": "BTCUSDT"}:
            mark_allowed = True
        else:
            errors.append("path_not_allowlisted")
    if not exchange_allowed:
        errors.append("exchange_info_endpoint_missing_or_invalid")
    if not mark_allowed:
        errors.append("mark_price_endpoint_missing_or_invalid")
    return {
        "valid": not errors,
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
        "exchange_info_endpoint_allowed": exchange_allowed,
        "mark_price_endpoint_allowed": mark_allowed,
        "order_endpoint_called": False if not order_called else True,
        "account_endpoint_called": False if not account_called else True,
        "private_endpoint_called": False if not private_called else True,
        "signed_endpoint_called": False if not signed_called else True,
    }


def build_fresh_market_context_summary(
    *,
    precision_snapshot: Mapping[str, Any] | None = None,
    mark_price_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    precision = precision_snapshot or {}
    mark = mark_price_snapshot or {}
    fetched = precision.get("found") is True and mark.get("found") is True
    return {
        "fetched": bool(fetched),
        "mark_price": _number(mark.get("mark_price")),
        "min_notional": _number(precision.get("min_notional")),
        "tick_size": _number(precision.get("tick_size")),
        "step_size": _number(precision.get("step_size")),
        "price_precision": _int_or_none(precision.get("price_precision")),
        "quantity_precision": _int_or_none(precision.get("quantity_precision")),
        "source": "binance_public_readonly_final_refresh",
    }


def compare_fresh_context_to_signed_artifact(
    *,
    fresh_market_context_summary: Mapping[str, Any],
    signed_artifact_context_summary: Mapping[str, Any],
) -> dict[str, Any]:
    if fresh_market_context_summary.get("fetched") is not True:
        return _empty_comparison()
    mark = _decimal(fresh_market_context_summary.get("mark_price"))
    reference = _decimal(signed_artifact_context_summary.get("reference_price"))
    quantity = _decimal(signed_artifact_context_summary.get("quantity"))
    stop = _decimal(signed_artifact_context_summary.get("stop_price"))
    take_profit = _decimal(signed_artifact_context_summary.get("take_profit_price"))
    min_notional = _decimal(fresh_market_context_summary.get("min_notional"))
    if None in (mark, reference, quantity, stop, take_profit):
        return _empty_comparison(can_compare=False)
    quantity_validation = validate_signed_quantity_against_fresh_precision(
        quantity=quantity,
        fresh_market_context_summary=fresh_market_context_summary,
    )
    direction_validation = validate_signed_stop_take_profit_against_fresh_mark(
        fresh_mark_price=mark,
        stop_price=stop,
        take_profit_price=take_profit,
        quantity=quantity,
    )
    notional = quantity * mark
    drift = mark - reference
    drift_pct = (drift / reference * Decimal("100")) if reference and reference > 0 else None
    min_ok = bool(min_notional is not None and notional >= min_notional)
    return _sanitize(
        {
            "can_compare": True,
            "reference_price": _float(reference),
            "fresh_mark_price": _float(mark),
            "absolute_mark_drift": _float(abs(drift)),
            "mark_drift_pct": _round_decimal(drift_pct, 4),
            "quantity_step_valid": quantity_validation["quantity_step_valid"],
            "notional_after_rounding_at_fresh_mark": _round_decimal(notional, 4),
            "min_notional_ok": min_ok,
            "short_stop_still_above_fresh_mark": direction_validation["short_stop_still_above_fresh_mark"],
            "short_take_profit_still_below_fresh_mark": direction_validation[
                "short_take_profit_still_below_fresh_mark"
            ],
            "estimated_loss_at_stop_from_fresh_mark": direction_validation[
                "estimated_loss_at_stop_from_fresh_mark"
            ],
            "estimated_reward_at_take_profit_from_fresh_mark": direction_validation[
                "estimated_reward_at_take_profit_from_fresh_mark"
            ],
        }
    )


def validate_signed_quantity_against_fresh_precision(
    *, quantity: Decimal | float | str, fresh_market_context_summary: Mapping[str, Any]
) -> dict[str, Any]:
    qty = _decimal(quantity)
    step = _decimal(fresh_market_context_summary.get("step_size"))
    if qty is None or qty <= 0 or step is None or step <= 0:
        return {"quantity_step_valid": False, "reason": "quantity_or_step_invalid"}
    return {"quantity_step_valid": (qty % step) == 0, "reason": "ok"}


def validate_signed_stop_take_profit_against_fresh_mark(
    *,
    fresh_mark_price: Decimal | float | str,
    stop_price: Decimal | float | str,
    take_profit_price: Decimal | float | str,
    quantity: Decimal | float | str,
) -> dict[str, Any]:
    mark = _decimal(fresh_mark_price)
    stop = _decimal(stop_price)
    take_profit = _decimal(take_profit_price)
    qty = _decimal(quantity)
    if None in (mark, stop, take_profit, qty):
        return {
            "short_stop_still_above_fresh_mark": False,
            "short_take_profit_still_below_fresh_mark": False,
            "estimated_loss_at_stop_from_fresh_mark": None,
            "estimated_reward_at_take_profit_from_fresh_mark": None,
        }
    return {
        "short_stop_still_above_fresh_mark": stop > mark,
        "short_take_profit_still_below_fresh_mark": take_profit < mark,
        "estimated_loss_at_stop_from_fresh_mark": _round_decimal(max(stop - mark, Decimal("0")) * qty, 4),
        "estimated_reward_at_take_profit_from_fresh_mark": _round_decimal(max(mark - take_profit, Decimal("0")) * qty, 4),
    }


def build_signed_request_regeneration_decision(
    *,
    input_summary: Mapping[str, Any],
    endpoint_safety_validation: Mapping[str, Any],
    fresh_market_context_summary: Mapping[str, Any],
    fresh_vs_signed_context_comparison: Mapping[str, Any],
    fetch_requested: bool,
    confirmation_valid: bool,
) -> dict[str, Any]:
    blocking: list[str] = []
    if fetch_requested and not confirmation_valid:
        return {
            "must_regenerate_signed_request_before_submit": None,
            "reason": "bad_confirmation",
            "blocking_reasons": ["bad_confirmation"],
            "submit_gate_preview_allowed_next": False,
        }
    if endpoint_safety_validation.get("valid") is not True:
        blocking.extend(str(item) for item in endpoint_safety_validation.get("errors") or ["endpoint_safety_invalid"])
    if not input_summary.get("r252_submit_readiness_valid"):
        blocking.append("r252_submit_readiness_not_ready")
    if not input_summary.get("r251_signed_request_valid") or not input_summary.get("r251e_runtime_signed_request_valid"):
        blocking.append("signed_artifact_not_ready")
    if not fetch_requested:
        return {
            "must_regenerate_signed_request_before_submit": None,
            "reason": "final_readonly_refresh_confirmation_required",
            "blocking_reasons": _dedupe(blocking),
            "submit_gate_preview_allowed_next": False,
        }
    if fresh_market_context_summary.get("fetched") is not True:
        blocking.append("fresh_market_context_not_fetched")
    if fresh_vs_signed_context_comparison.get("can_compare") is not True:
        blocking.append("fresh_context_not_comparable")
    for key in (
        "quantity_step_valid",
        "min_notional_ok",
        "short_stop_still_above_fresh_mark",
        "short_take_profit_still_below_fresh_mark",
    ):
        if fresh_vs_signed_context_comparison.get(key) is not True:
            blocking.append(key)
    loss = _number(fresh_vs_signed_context_comparison.get("estimated_loss_at_stop_from_fresh_mark"))
    if loss is not None and loss > 4.45:
        blocking.append("estimated_loss_at_stop_exceeds_signed_risk_tolerance")
    blocking = _dedupe(blocking)
    must_regenerate = bool(blocking)
    return {
        "must_regenerate_signed_request_before_submit": must_regenerate,
        "reason": "fresh_context_compatible_with_signed_artifact" if not must_regenerate else "fresh_context_requires_signed_request_regeneration",
        "blocking_reasons": blocking,
        "submit_gate_preview_allowed_next": not must_regenerate,
    }


def build_final_readonly_refresh_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    endpoint_safety_validation: Mapping[str, Any],
    final_readonly_fetch_confirmed: bool,
    fresh_market_context_summary: Mapping[str, Any],
    fresh_vs_signed_context_comparison: Mapping[str, Any],
    signed_request_regeneration_decision: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if not input_summary.get("r252_submit_readiness_valid"):
        blockers.append("r252_submit_readiness_not_ready")
    if not input_summary.get("r251_signed_request_valid") or not input_summary.get("r251e_runtime_signed_request_valid"):
        blockers.append("signed_artifact_not_ready")
    if endpoint_safety_validation.get("valid") is not True:
        blockers.append("endpoint_safety_invalid")
    if final_readonly_fetch_confirmed and fresh_market_context_summary.get("fetched") is not True:
        blockers.append("fresh_market_context_not_ready")
    if signed_request_regeneration_decision.get("must_regenerate_signed_request_before_submit") is True:
        blockers.append("signed_request_regeneration_required")
    blockers.extend(str(item) for item in signed_request_regeneration_decision.get("blocking_reasons") or [])
    return {
        "r252_submit_readiness_ready": input_summary.get("r252_submit_readiness_valid") is True,
        "signed_artifact_ready": (
            input_summary.get("r251e_runtime_signed_request_valid") is True
            and input_summary.get("r251_signed_request_valid") is True
        ),
        "endpoint_safety_valid": endpoint_safety_validation.get("valid") is True,
        "final_readonly_fetch_confirmed": bool(final_readonly_fetch_confirmed),
        "fresh_market_context_ready": fresh_market_context_summary.get("fetched") is True,
        "fresh_context_compatible_with_signed_artifact": None
        if fresh_vs_signed_context_comparison.get("can_compare") is not True
        else signed_request_regeneration_decision.get("must_regenerate_signed_request_before_submit") is False,
        "must_regenerate_signed_request": signed_request_regeneration_decision.get(
            "must_regenerate_signed_request_before_submit"
        ),
        "submit_allowed": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_final_readonly_refresh_packet(
    final_readonly_refresh_gate_matrix: Mapping[str, Any],
    signed_request_regeneration_decision: Mapping[str, Any],
) -> dict[str, Any]:
    if final_readonly_refresh_gate_matrix.get("fresh_market_context_ready") is not True:
        action = "CONFIRM_R253_FINAL_READONLY_REFRESH"
    elif signed_request_regeneration_decision.get("must_regenerate_signed_request_before_submit") is True:
        action = "REGENERATE_SIGNED_REQUEST"
    elif signed_request_regeneration_decision.get("submit_gate_preview_allowed_next") is True:
        action = "CONTINUE_TO_R254_SUBMIT_GATE_PREVIEW"
    elif final_readonly_refresh_gate_matrix.get("blocked_by"):
        action = "FIX_BLOCKER"
    else:
        action = "WAIT"
    return {
        "operator_should_review_fresh_market_context": final_readonly_refresh_gate_matrix.get(
            "fresh_market_context_ready"
        )
        is True,
        "operator_should_regenerate_signed_request": action == "REGENERATE_SIGNED_REQUEST",
        "operator_should_continue_to_submit_gate_preview": action == "CONTINUE_TO_R254_SUBMIT_GATE_PREVIEW",
        "operator_should_submit_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": _explicit_non_actions(),
    }


def classify_tiny_live_final_readonly_mark_price_refresh_gate_status(
    *,
    input_summary: Mapping[str, Any],
    endpoint_safety_validation: Mapping[str, Any],
    final_readonly_refresh_gate_matrix: Mapping[str, Any],
    fetch_requested: bool,
    confirmation_valid: bool,
    final_readonly_market_fetched: bool,
    signed_request_regeneration_decision: Mapping[str, Any],
) -> str:
    if fetch_requested and not confirmation_valid:
        return TINY_LIVE_FINAL_READONLY_REFRESH_REJECTED_BAD_CONFIRMATION
    if endpoint_safety_validation.get("valid") is not True:
        return TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_ENDPOINT_SAFETY
    if not input_summary.get("r251_signed_request_valid") or not input_summary.get("r251e_runtime_signed_request_valid"):
        return TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_SIGNED_ARTIFACT
    if final_readonly_market_fetched and signed_request_regeneration_decision.get("must_regenerate_signed_request_before_submit") is True:
        return TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_REGENERATE_SIGNED_REQUEST_REQUIRED
    if final_readonly_market_fetched and signed_request_regeneration_decision.get("submit_gate_preview_allowed_next") is True:
        return TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_READY_FOR_SUBMIT_GATE_PREVIEW
    if fetch_requested and confirmation_valid and final_readonly_refresh_gate_matrix.get("fresh_market_context_ready") is not True:
        return TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_MARKET_VALIDATION
    if input_summary.get("r252_submit_readiness_valid") and final_readonly_refresh_gate_matrix.get("signed_artifact_ready"):
        return TINY_LIVE_FINAL_READONLY_REFRESH_READY_FOR_CONFIRMATION
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_final_readonly_mark_price_refresh_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_final_readonly_refresh: str | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_final_readonly_refresh != CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE:
        raise ValueError("bad_tiny_live_final_readonly_refresh_confirmation")
    if record.get("endpoint_safety_validation", {}).get("valid") is not True:
        raise ValueError("endpoint_safety_validation_failed")
    if record.get("final_readonly_market_fetched") is not True:
        raise ValueError("final_readonly_market_not_fetched")
    path = tiny_live_final_readonly_mark_price_refresh_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "final_readonly_refresh_gate_record_id": record.get("final_readonly_refresh_gate_record_id")
            or f"r253_final_readonly_refresh_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_final_readonly_mark_price_refresh_gate_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_final_readonly_mark_price_refresh_gate_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_final_readonly_mark_price_refresh_gate_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_final_readonly_market_fetched": latest.get("final_readonly_market_fetched") is True,
        "latest_overall_status": latest.get("final_readonly_refresh_overall_status"),
        "latest_next_required_human_action": latest.get("operator_final_readonly_refresh_packet", {}).get(
            "next_required_human_action"
        ),
    }


def tiny_live_final_readonly_mark_price_refresh_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_final_readonly_mark_price_refresh_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r252: Mapping[str, Any],
    latest_r251e: Mapping[str, Any],
    latest_r251: Mapping[str, Any],
    latest_r249: Mapping[str, Any],
    latest_r248: Mapping[str, Any],
    r251_artifact: Mapping[str, Any],
    r249_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "r252_submit_readiness_found": bool(latest_r252),
        "r252_submit_readiness_valid": latest_r252.get("submit_readiness_overall_status")
        == "TINY_LIVE_SUBMIT_READINESS_RECORDED_FINAL_READONLY_REFRESH_REQUIRED",
        "r251e_runtime_signed_request_found": bool(latest_r251e),
        "r251e_runtime_signed_request_valid": validate_r251e_signed_request_artifact(r251_artifact).get("valid") is True
        and bool(latest_r251e),
        "r251_signed_request_found": bool(latest_r251),
        "r251_signed_request_valid": validate_signed_request_artifact(r251_artifact).get("valid") is True,
        "r249_executable_payload_found": bool(latest_r249),
        "r249_executable_payload_valid": validate_executable_payload_artifact(r249_artifact).get("valid") is True,
        "r248_stop_take_profit_source_found": bool(latest_r248),
        "r248_stop_take_profit_source_valid": _validate_r248_record(latest_r248).get("valid") is True,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r252_submit_readiness_found": False,
        "r252_submit_readiness_valid": False,
        "r251e_runtime_signed_request_found": False,
        "r251e_runtime_signed_request_valid": False,
        "r251_signed_request_found": False,
        "r251_signed_request_valid": False,
        "r249_executable_payload_found": False,
        "r249_executable_payload_valid": False,
        "r248_stop_take_profit_source_found": False,
        "r248_stop_take_profit_source_valid": False,
    }


def _build_signed_artifact_context_summary(
    *,
    r251_artifact: Mapping[str, Any],
    r249_artifact: Mapping[str, Any],
    r248_record: Mapping[str, Any],
) -> dict[str, Any]:
    signed = r251_artifact.get("signed_requests") if isinstance(r251_artifact.get("signed_requests"), Mapping) else {}
    main_query = _query_params(signed.get("main_order", {}))
    stop_query = _query_params(signed.get("stop_order", {}))
    tp_query = _query_params(signed.get("take_profit_order", {}))
    r248_source = _r248_source(r248_record)
    main = r249_artifact.get("main_order") if isinstance(r249_artifact.get("main_order"), Mapping) else {}
    stop = r249_artifact.get("stop_order") if isinstance(r249_artifact.get("stop_order"), Mapping) else {}
    take_profit = (
        r249_artifact.get("take_profit_order")
        if isinstance(r249_artifact.get("take_profit_order"), Mapping)
        else {}
    )
    return _sanitize(
        {
            "reference_price": _number(r249_artifact.get("reference_price") or r248_source.get("reference_price")),
            "quantity": _number(main_query.get("quantity") or main.get("quantity") or r248_source.get("quantity")),
            "stop_price": _number(stop_query.get("stopPrice") or stop.get("stopPrice") or r248_source.get("stop_price")),
            "take_profit_price": _number(
                tp_query.get("stopPrice") or take_profit.get("stopPrice") or r248_source.get("take_profit_price")
            ),
            "side": main_query.get("side") or main.get("side"),
            "signed_requests_count": len(signed),
        }
    )


def _empty_signed_artifact_context_summary() -> dict[str, Any]:
    return {
        "reference_price": None,
        "quantity": None,
        "stop_price": None,
        "take_profit_price": None,
        "side": None,
        "signed_requests_count": 0,
    }


def _empty_comparison(*, can_compare: bool = False) -> dict[str, Any]:
    return {
        "can_compare": can_compare,
        "reference_price": None,
        "fresh_mark_price": None,
        "absolute_mark_drift": None,
        "mark_drift_pct": None,
        "quantity_step_valid": None,
        "notional_after_rounding_at_fresh_mark": None,
        "min_notional_ok": None,
        "short_stop_still_above_fresh_mark": None,
        "short_take_profit_still_below_fresh_mark": None,
        "estimated_loss_at_stop_from_fresh_mark": None,
        "estimated_reward_at_take_profit_from_fresh_mark": None,
    }


def _empty_matrix() -> dict[str, Any]:
    return {
        "r252_submit_readiness_ready": False,
        "signed_artifact_ready": False,
        "endpoint_safety_valid": False,
        "final_readonly_fetch_confirmed": False,
        "fresh_market_context_ready": False,
        "fresh_context_compatible_with_signed_artifact": None,
        "must_regenerate_signed_request": None,
        "submit_allowed": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": [],
    }


def _validate_r248_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not record:
        return {"valid": False, "errors": ["r248_stop_take_profit_source_missing"], "warnings": []}
    source = _r248_source(record)
    selected = {
        "entry_reference_price": source.get("reference_price"),
        "rounded_stop_price": source.get("stop_price"),
        "rounded_take_profit_price": source.get("take_profit_price"),
        "source_valid": True,
        "blocked_by": [],
    }
    validation = validate_short_stop_take_profit_levels(selected)
    errors = list(validation.get("errors") or [])
    warnings = list(validation.get("warnings") or [])
    if _number(source.get("quantity")) is None:
        errors.append("r248_quantity_missing")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def _validate_r242_record(record: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not record:
        return {"valid": False, "errors": ["r242_readonly_reference_missing"], "warnings": []}
    result = record.get("binance_readonly_result") if isinstance(record.get("binance_readonly_result"), Mapping) else {}
    precision = result.get("precision_snapshot") if isinstance(result.get("precision_snapshot"), Mapping) else {}
    mark = result.get("mark_price_snapshot") if isinstance(result.get("mark_price_snapshot"), Mapping) else {}
    if record.get("readonly_fetch_performed") is not True:
        errors.append("r242_readonly_fetch_not_performed")
    if precision.get("found") is not True:
        errors.append("r242_precision_missing")
    if mark.get("found") is not True:
        errors.append("r242_mark_price_missing")
    if result.get("order_endpoint_called") is not False:
        errors.append("r242_order_endpoint_called")
    if result.get("account_endpoint_called") is not False:
        errors.append("r242_account_endpoint_called")
    if result.get("signed_request_created") is not False:
        errors.append("r242_signed_request_created")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": []}


def _signed_request_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("signed_request_artifact")
    return _sanitize(dict(artifact)) if isinstance(artifact, Mapping) else {}


def _executable_payload_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("executable_payload_artifact")
    return _sanitize(dict(artifact)) if isinstance(artifact, Mapping) else {}


def _r248_source(record: Mapping[str, Any]) -> dict[str, Any]:
    source = record.get("stop_take_profit_source") if isinstance(record.get("stop_take_profit_source"), Mapping) else {}
    selected = record.get("selected_stop_take_profit_source") if isinstance(record.get("selected_stop_take_profit_source"), Mapping) else {}
    risk = record.get("risk_reward_validation") if isinstance(record.get("risk_reward_validation"), Mapping) else {}
    return {
        "reference_price": source.get("reference_price") or selected.get("entry_reference_price"),
        "stop_price": source.get("stop_price") or source.get("final_stop_price") or selected.get("rounded_stop_price"),
        "take_profit_price": source.get("take_profit_price")
        or source.get("final_take_profit_price")
        or selected.get("rounded_take_profit_price"),
        "quantity": source.get("quantity") or risk.get("quantity_preview"),
    }


def _query_params(request: Mapping[str, Any]) -> dict[str, str]:
    query = str(request.get("query_string_without_signature") or "")
    parsed = parse_qs(query, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items() if values}


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    if target.get("official_lane_key") is not None:
        return str(target.get("official_lane_key")) == official_lane_key
    for key in ("signed_request_artifact", "executable_payload_artifact", "stop_take_profit_source"):
        value = record.get(key)
        if isinstance(value, Mapping) and value.get("official_lane_key") is not None:
            return str(value.get("official_lane_key")) == official_lane_key
    return True


def _recommended_next_operator_move(operator_packet: Mapping[str, Any]) -> str:
    return str(operator_packet.get("next_required_human_action") or "WAIT")


def _recommended_next_engineering_move(
    regeneration_decision: Mapping[str, Any],
    matrix: Mapping[str, Any],
) -> str:
    if matrix.get("fresh_market_context_ready") is not True:
        return "Run R253 final public read-only refresh only after exact confirmation; no submit or order."
    if regeneration_decision.get("must_regenerate_signed_request_before_submit") is True:
        return "Regenerate the signed request artifact from fresh market context before any R254 submit-gate preview."
    if regeneration_decision.get("submit_gate_preview_allowed_next") is True:
        return "Create R254 submit gate preview task that consumes R253 and keeps submit_allowed=false."
    return "Fix R253 blockers before any submit-gate preview."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "kill switch disable",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _explicit_non_actions() -> list[str]:
    return [
        "do not place order",
        "do not submit",
        "do not call Binance order endpoint from this phase",
    ]


def _lane_parts(official_lane_key: str) -> tuple[str, str, str, str]:
    parts = official_lane_key.split("|")
    if len(parts) != 4:
        return "BTCUSDT", "8m", "short", "ladder_close_50_618"
    return parts[0], parts[1], parts[2], parts[3]


def _number(value: Any) -> float | None:
    if value is None or value == "":
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
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: Decimal) -> float:
    return float(value.normalize())


def _round_decimal(value: Decimal | None, places: int) -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal(1).scaleb(-places)))


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _sanitize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Decimal):
        return _float(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
