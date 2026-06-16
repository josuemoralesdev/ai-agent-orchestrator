"""R280 safe Binance Futures account/position read-only adapter.

This adapter signs only explicitly allowlisted private read-only Futures
endpoints. It never creates order/test-order/leverage/margin/cancel/transfer
requests and never returns API keys, secrets, signatures, or signed URLs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from src.app.hammer_radar.operator.binance_readonly import (
    CONNECTOR_STATUS_READY,
    ENV_API_KEY,
    ENV_API_SECRET,
    REQUIRED_CONNECTOR_MODE,
    build_binance_readonly_status,
)
from src.app.hammer_radar.operator.binance_account_read_env_contract import (
    ACCOUNT_READ_ENV_READY,
    adapt_env_for_selected_account_read_contract,
    build_binance_account_read_env_discovery,
)
from src.app.hammer_radar.operator.env_role_adapter import (
    resolve_account_read_env_pair,
    validate_account_read_runtime_safety,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.readonly_balance_error_sanitizer import sanitize_http_error

BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"
DEFAULT_RECV_WINDOW_MS = 5000
SYMBOL = "BTCUSDT"

FUTURES_BALANCE_PATH = "/fapi/v2/balance"
FUTURES_ACCOUNT_PATH = "/fapi/v2/account"
FUTURES_POSITION_RISK_PATH = "/fapi/v2/positionRisk"
ALLOWED_PRIVATE_READONLY_ENDPOINTS = {
    FUTURES_BALANCE_PATH,
    FUTURES_ACCOUNT_PATH,
    FUTURES_POSITION_RISK_PATH,
}
FORBIDDEN_PRIVATE_ENDPOINTS = {
    "/fapi/v1/order",
    "/fapi/v1/batchOrders",
    "/fapi/v1/leverage",
    "/fapi/v1/marginType",
    "/fapi/v1/allOpenOrders",
    "/sapi/v1/asset/transfer",
    "/sapi/v1/capital/withdraw/apply",
}

ACCOUNT_POSITION_NOT_REQUESTED = "NOT_REQUESTED"
ACCOUNT_POSITION_CONFIRMATION_REQUIRED = "BLOCKED_CONFIRMATION_REQUIRED"
ACCOUNT_POSITION_ENDPOINT_NOT_ALLOWLISTED = "BLOCKED_ENDPOINT_NOT_ALLOWLISTED"
ACCOUNT_POSITION_FETCH_FAILED = "BLOCKED_FETCH_FAILED"
ACCOUNT_POSITION_READY = "READY"
ACCOUNT_POSITION_CONFLICTING_POSITION = "BLOCKED_CONFLICTING_POSITION"
ACCOUNT_POSITION_WALLET_INSUFFICIENT = "BLOCKED_WALLET_INSUFFICIENT"

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "hmac_signature_created": False,
    "signed_request_created": False,
    "signed_readonly_request_created": False,
    "signed_trading_request_created": False,
    "signed_order_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "binance_account_endpoint_called": False,
    "binance_balance_endpoint_called": False,
    "binance_position_risk_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "cancel_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "private_readonly_endpoint_called": False,
    "private_binance_endpoint_called": False,
    "signed_binance_endpoint_called": False,
    "network_allowed": False,
    "api_key_used": False,
    "api_secret_used": False,
    "signature_created": False,
    "signature_shown": False,
    "signed_url_shown": False,
    "secrets_read": False,
    "secrets_shown": False,
    "secret_values_in_output": False,
    "paper_live_separation_intact": True,
    "final_command_available": False,
    "submit_allowed": False,
    "real_order_forbidden": True,
}


def build_signed_readonly_query(
    *,
    endpoint_path: str,
    params: Mapping[str, Any] | None = None,
    secret: str,
    timestamp_ms: int | None = None,
    recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
) -> dict[str, Any]:
    """Build a signed read-only query for an allowlisted endpoint.

    The returned diagnostics intentionally omit the query string and signature.
    Internal callers use the private ``_signed_query`` key only for transport and
    remove it before exposing any payload.
    """
    validation = validate_private_readonly_endpoint(endpoint_path)
    if not validation["endpoint_allowlisted"]:
        return {
            "requested_endpoint": endpoint_path,
            "endpoint_allowlisted": False,
            "signed_readonly_request_created": False,
            "signed_trading_request_created": False,
            "signed_order_request_created": False,
            "hmac_signature_created": False,
            "blocked_reason": ACCOUNT_POSITION_ENDPOINT_NOT_ALLOWLISTED,
        }
    query_params = {str(key): str(value) for key, value in (params or {}).items() if value is not None}
    query_params["timestamp"] = str(int(timestamp_ms if timestamp_ms is not None else time.time() * 1000))
    query_params["recvWindow"] = str(int(recv_window_ms))
    pre_signature = urllib.parse.urlencode([(key, query_params[key]) for key in sorted(query_params)])
    signature = hmac.new(str(secret).encode("utf-8"), pre_signature.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "requested_endpoint": endpoint_path,
        "endpoint_allowlisted": True,
        "signed_readonly_request_created": True,
        "signed_trading_request_created": False,
        "signed_order_request_created": False,
        "hmac_signature_created": True,
        "signed_query_param_keys": sorted(query_params),
        "signature_shown": False,
        "signed_url_shown": False,
        "_signed_query": f"{pre_signature}&signature={signature}",
    }


def validate_private_readonly_endpoint(endpoint_path: str) -> dict[str, Any]:
    path = str(endpoint_path or "").split("?", 1)[0]
    forbidden = path in FORBIDDEN_PRIVATE_ENDPOINTS or path.endswith("/order")
    allowlisted = path in ALLOWED_PRIVATE_READONLY_ENDPOINTS and not forbidden
    return {
        "requested_endpoint": path,
        "endpoint_allowlisted": allowlisted,
        "private_readonly_endpoint": allowlisted,
        "forbidden_endpoint": forbidden,
        "allowed_endpoint_class": "private_readonly" if allowlisted else "blocked",
    }


def fetch_futures_account_balance_readonly(
    *,
    env: Mapping[str, str] | None = None,
    recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
    urlopen_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    raw = _request_private_readonly_json(
        endpoint_path=FUTURES_BALANCE_PATH,
        params={},
        env=env,
        recv_window_ms=recv_window_ms,
        urlopen_func=urlopen_func,
    )
    balance = _extract_usdt_balance(raw.get("raw"))
    return _sanitize(
        {
            **_public_request_diagnostics(raw),
            "account_balance_checked": True,
            "asset": "USDT",
            "available_balance_usdt": balance["available_balance_usdt"],
            "wallet_balance_usdt": balance["wallet_balance_usdt"],
        }
    )


def fetch_futures_position_risk_readonly(
    *,
    symbol: str = SYMBOL,
    env: Mapping[str, str] | None = None,
    recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
    urlopen_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    normalized_symbol = str(symbol or SYMBOL).upper()
    raw = _request_private_readonly_json(
        endpoint_path=FUTURES_POSITION_RISK_PATH,
        params={"symbol": normalized_symbol},
        env=env,
        recv_window_ms=recv_window_ms,
        urlopen_func=urlopen_func,
    )
    position = _extract_symbol_position(raw.get("raw"), symbol=normalized_symbol)
    return _sanitize(
        {
            **_public_request_diagnostics(raw),
            "position_risk_checked": True,
            "symbol": normalized_symbol,
            **position,
        }
    )


def build_account_position_readiness(
    *,
    fetch_requested: bool = False,
    confirmation_valid: bool = False,
    env: Mapping[str, str] | None = None,
    symbol: str = SYMBOL,
    configured_margin_budget_usdt: float = 8.0,
    configured_notional_cap_usdt: float = 80.0,
    configured_leverage: float = 10.0,
    recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
    urlopen_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    safety = dict(SAFETY)
    if not fetch_requested:
        return _empty_readiness(
            status=ACCOUNT_POSITION_NOT_REQUESTED,
            fetch_requested=False,
            confirmation_valid=confirmation_valid,
            blockers=["readonly_account_position_not_requested"],
            safety=safety,
            configured_margin_budget_usdt=configured_margin_budget_usdt,
            configured_notional_cap_usdt=configured_notional_cap_usdt,
            configured_leverage=configured_leverage,
        )
    if not confirmation_valid:
        return _empty_readiness(
            status=ACCOUNT_POSITION_CONFIRMATION_REQUIRED,
            fetch_requested=True,
            confirmation_valid=False,
            blockers=["readonly_account_position_confirmation_required"],
            safety=safety,
            configured_margin_budget_usdt=configured_margin_budget_usdt,
            configured_notional_cap_usdt=configured_notional_cap_usdt,
            configured_leverage=configured_leverage,
        )

    preflight = _preflight(env=env)
    if preflight["safe_to_call"] is not True:
        return _empty_readiness(
            status=ACCOUNT_POSITION_FETCH_FAILED,
            fetch_requested=True,
            confirmation_valid=True,
            blockers=list(preflight["blockers"]),
            safety=safety,
            configured_margin_budget_usdt=configured_margin_budget_usdt,
            configured_notional_cap_usdt=configured_notional_cap_usdt,
            configured_leverage=configured_leverage,
            preflight=preflight,
        )

    try:
        balance = fetch_futures_account_balance_readonly(
            env=env,
            recv_window_ms=recv_window_ms,
            urlopen_func=urlopen_func,
        )
        position = fetch_futures_position_risk_readonly(
            symbol=symbol,
            env=env,
            recv_window_ms=recv_window_ms,
            urlopen_func=urlopen_func,
        )
    except Exception as exc:
        sanitized_error = sanitize_http_error(exc, endpoint_family="binance_account_position_readonly")
        failed = _empty_readiness(
            status=ACCOUNT_POSITION_FETCH_FAILED,
            fetch_requested=True,
            confirmation_valid=True,
            blockers=["readonly_account_position_fetch_failed"],
            safety=safety,
            configured_margin_budget_usdt=configured_margin_budget_usdt,
            configured_notional_cap_usdt=configured_notional_cap_usdt,
            configured_leverage=configured_leverage,
            preflight=preflight,
        )
        failed.update({"error": exc.__class__.__name__, **sanitized_error})
        return _sanitize(failed)

    _merge_safety_from_fetch(safety, balance, position)
    available = _number(balance.get("available_balance_usdt"))
    wallet = _number(balance.get("wallet_balance_usdt"))
    position_amt = _number(position.get("btcusdt_position_amt")) or 0.0
    position_notional = _number(position.get("btcusdt_position_notional")) or 0.0
    open_conflict = abs(position_amt) > 0 or abs(position_notional) > 0
    wallet_supports_margin = available is not None and available >= float(configured_margin_budget_usdt)
    wallet_supports_minimum = wallet_supports_margin
    leverage = _number(position.get("leverage"))
    margin_type = str(position.get("margin_type") or "").lower()
    current_margin_mode = margin_type.upper() if margin_type else None
    leverage_checked = leverage is not None
    margin_mode_checked = bool(margin_type)
    leverage_matches = None if leverage is None else leverage == float(configured_leverage)
    margin_matches = None if not margin_type else margin_type == "isolated"

    blockers: list[str] = []
    if not wallet_supports_minimum:
        blockers.append("wallet_supports_minimum_tiny_false")
    if not wallet_supports_margin:
        blockers.append("wallet_supports_configured_margin_budget_false")
    if open_conflict:
        blockers.append("btcusdt_open_position_conflict")
    if safety["binance_order_endpoint_called"] or safety["binance_test_order_endpoint_called"]:
        blockers.append("unsafe_order_endpoint_called")
    if safety["leverage_change_called"] or safety["margin_change_called"]:
        blockers.append("unsafe_account_mutation_endpoint_called")
    status = ACCOUNT_POSITION_READY
    if open_conflict:
        status = ACCOUNT_POSITION_CONFLICTING_POSITION
    elif not wallet_supports_margin or not wallet_supports_minimum:
        status = ACCOUNT_POSITION_WALLET_INSUFFICIENT
    elif blockers:
        status = ACCOUNT_POSITION_FETCH_FAILED

    return _sanitize(
        {
            "fetch_requested": True,
            "confirmation_valid": True,
            "account_position_readiness_status": status,
            "account_balance_checked": True,
            "position_risk_checked": True,
            "leverage_checked": leverage_checked,
            "margin_mode_checked": margin_mode_checked,
            "available_balance_usdt": available,
            "wallet_balance_usdt": wallet,
            "wallet_supports_minimum_tiny": wallet_supports_minimum,
            "wallet_supports_configured_margin_budget": wallet_supports_margin,
            "configured_margin_budget_usdt": float(configured_margin_budget_usdt),
            "configured_notional_cap_usdt": float(configured_notional_cap_usdt),
            "configured_leverage": float(configured_leverage),
            "open_position_conflict": open_conflict,
            "btcusdt_position_amt": position_amt,
            "btcusdt_position_side": position.get("btcusdt_position_side"),
            "btcusdt_position_notional": position_notional,
            "current_leverage": leverage,
            "current_margin_mode": current_margin_mode,
            "leverage": leverage,
            "margin_type": margin_type or None,
            "leverage_matches_expectation": leverage_matches,
            "margin_mode_matches_expectation": margin_matches,
            "readiness_blockers": blockers,
            "preflight": preflight,
            "endpoint_allowlist": sorted(ALLOWED_PRIVATE_READONLY_ENDPOINTS),
            "balance_request": _request_summary(balance),
            "position_request": _request_summary(position),
            "private_readonly_supported": True,
            "secrets_shown": False,
            "safety": safety,
        }
    )


def _request_private_readonly_json(
    *,
    endpoint_path: str,
    params: Mapping[str, Any] | None,
    env: Mapping[str, str] | None,
    recv_window_ms: int,
    urlopen_func: Callable[..., Any] | None,
) -> dict[str, Any]:
    validation = validate_private_readonly_endpoint(endpoint_path)
    if not validation["endpoint_allowlisted"]:
        raise RuntimeError("private_readonly_endpoint_not_allowlisted")
    adapted_env = adapt_env_for_selected_account_read_contract(env=env)
    api_key = str(adapted_env.get(ENV_API_KEY) or "").strip()
    api_secret = str(adapted_env.get(ENV_API_SECRET) or "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("missing_readonly_credentials")
    signed = build_signed_readonly_query(
        endpoint_path=endpoint_path,
        params=params,
        secret=api_secret,
        recv_window_ms=recv_window_ms,
    )
    signed_query = str(signed.pop("_signed_query"))
    url = f"{BINANCE_FUTURES_BASE_URL}{endpoint_path}?{signed_query}"
    request = urllib.request.Request(url, headers={"X-MBX-APIKEY": api_key}, method="GET")
    opener = urlopen_func or urllib.request.urlopen
    with opener(request, timeout=10.0) as response:
        raw_body = response.read()
    decoded = json.loads(raw_body.decode("utf-8"))
    return {
        **signed,
        **validation,
        "method": "GET",
        "private_readonly_endpoint_called": True,
        "signed_binance_endpoint_called": True,
        "api_key_used": True,
        "api_secret_used": True,
        "raw": decoded,
    }


def _preflight(*, env: Mapping[str, str] | None) -> dict[str, Any]:
    source = os.environ if env is None else env
    discovery = build_binance_account_read_env_discovery(env=source, include_systemd=False)
    selected = (
        discovery.get("selected_env_contract")
        if isinstance(discovery.get("selected_env_contract"), Mapping)
        else {}
    )
    adapted_env = adapt_env_for_selected_account_read_contract(env=source)
    connector = build_binance_readonly_status(env=adapted_env)
    env_role = resolve_account_read_env_pair(env=source)
    runtime = validate_account_read_runtime_safety(env=source)
    blockers: list[str] = []
    if discovery.get("status") != ACCOUNT_READ_ENV_READY:
        blockers.extend(str(item) for item in discovery.get("readiness_blockers") or [])
    if connector.get("connector_status") != CONNECTOR_STATUS_READY:
        blockers.append(f"connector_status_is_{connector.get('connector_status') or 'UNKNOWN'}")
    if connector.get("connector_mode") != REQUIRED_CONNECTOR_MODE:
        blockers.append("connector_mode_not_read_only")
    if not selected.get("api_key_present"):
        blockers.append("account_read_api_key_missing")
    if not selected.get("api_secret_present"):
        blockers.append("account_read_api_secret_missing")
    if selected.get("runtime_safety_ok") is not True and runtime.get("runtime_safety_ok") is not True:
        blockers.append("account_read_runtime_safety_not_ok")
    return {
        "safe_to_call": not blockers,
        "account_read_env_discovery_status": discovery.get("status"),
        "selected_env_contract": dict(selected),
        "connector_status": connector.get("connector_status"),
        "connector_mode": connector.get("connector_mode"),
        "api_key_present": bool(selected.get("api_key_present")),
        "api_secret_present": bool(selected.get("api_secret_present")),
        "selected_pair_source": selected.get("selected_env_source") or env_role.get("selected_pair_source"),
        "runtime_safety_ok": selected.get("runtime_safety_ok") is True or runtime.get("runtime_safety_ok") is True,
        "failed_runtime_flags": list(runtime.get("failed_flags") or []),
        "blockers": _dedupe(blockers),
        "warnings": _dedupe([*list(env_role.get("warnings") or []), *list(discovery.get("readiness_blockers") or [])]),
        "secrets_shown": False,
    }


def _extract_usdt_balance(raw: Any) -> dict[str, float | None]:
    rows = raw if isinstance(raw, list) else []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("asset") or "").upper() == "USDT":
            return {
                "available_balance_usdt": _number(row.get("availableBalance") or row.get("maxWithdrawAmount")),
                "wallet_balance_usdt": _number(row.get("balance") or row.get("walletBalance")),
            }
    return {"available_balance_usdt": None, "wallet_balance_usdt": None}


def _extract_symbol_position(raw: Any, *, symbol: str) -> dict[str, Any]:
    rows = raw if isinstance(raw, list) else []
    target = symbol.upper()
    for row in rows:
        if not isinstance(row, Mapping) or str(row.get("symbol") or "").upper() != target:
            continue
        amt = _number(row.get("positionAmt")) or 0.0
        side = str(row.get("positionSide") or "BOTH").upper()
        return {
            "btcusdt_position_amt": amt,
            "btcusdt_position_side": side,
            "btcusdt_position_notional": _number(row.get("notional")) or 0.0,
            "leverage": _number(row.get("leverage")),
            "margin_type": str(row.get("marginType") or "").lower() or None,
        }
    return {
        "btcusdt_position_amt": 0.0,
        "btcusdt_position_side": "BOTH",
        "btcusdt_position_notional": 0.0,
        "leverage": None,
        "margin_type": None,
    }


def _public_request_diagnostics(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in raw.items()
        if key not in {"raw", "_signed_query"}
    }


def _request_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "requested_endpoint": payload.get("requested_endpoint"),
        "endpoint_allowlisted": payload.get("endpoint_allowlisted") is True,
        "private_readonly_endpoint_called": payload.get("private_readonly_endpoint_called") is True,
        "signed_readonly_request_created": payload.get("signed_readonly_request_created") is True,
        "signed_trading_request_created": False,
        "signed_order_request_created": False,
        "hmac_signature_created": payload.get("hmac_signature_created") is True,
        "signature_shown": False,
        "signed_url_shown": False,
    }


def _empty_readiness(
    *,
    status: str,
    fetch_requested: bool,
    confirmation_valid: bool,
    blockers: list[str],
    safety: Mapping[str, Any],
    configured_margin_budget_usdt: float,
    configured_notional_cap_usdt: float,
    configured_leverage: float,
    preflight: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _sanitize(
        {
            "fetch_requested": bool(fetch_requested),
            "confirmation_valid": bool(confirmation_valid),
            "account_position_readiness_status": status,
            "account_balance_checked": False,
            "position_risk_checked": False,
            "leverage_checked": False,
            "margin_mode_checked": False,
            "available_balance_usdt": None,
            "wallet_balance_usdt": None,
            "wallet_supports_minimum_tiny": False if fetch_requested else None,
            "wallet_supports_configured_margin_budget": False if fetch_requested else None,
            "configured_margin_budget_usdt": float(configured_margin_budget_usdt),
            "configured_notional_cap_usdt": float(configured_notional_cap_usdt),
            "configured_leverage": float(configured_leverage),
            "open_position_conflict": None,
            "btcusdt_position_amt": None,
            "btcusdt_position_side": None,
            "btcusdt_position_notional": None,
            "current_leverage": None,
            "current_margin_mode": None,
            "leverage": None,
            "margin_type": None,
            "leverage_matches_expectation": None,
            "margin_mode_matches_expectation": None,
            "readiness_blockers": blockers,
            "preflight": dict(preflight or {}),
            "endpoint_allowlist": sorted(ALLOWED_PRIVATE_READONLY_ENDPOINTS),
            "private_readonly_supported": True,
            "secrets_shown": False,
            "safety": dict(safety),
        }
    )


def _merge_safety_from_fetch(safety: dict[str, Any], *payloads: Mapping[str, Any]) -> None:
    safety["network_allowed"] = True
    safety["private_readonly_endpoint_called"] = True
    safety["private_binance_endpoint_called"] = True
    safety["signed_binance_endpoint_called"] = True
    safety["api_key_used"] = True
    safety["api_secret_used"] = True
    safety["secrets_read"] = True
    safety["signed_request_created"] = True
    safety["signed_readonly_request_created"] = True
    safety["hmac_signature_created"] = True
    safety["signature_created"] = True
    for payload in payloads:
        endpoint = str(payload.get("requested_endpoint") or "")
        if endpoint == FUTURES_BALANCE_PATH:
            safety["binance_balance_endpoint_called"] = True
            safety["binance_account_endpoint_called"] = True
        if endpoint == FUTURES_ACCOUNT_PATH:
            safety["binance_account_endpoint_called"] = True
        if endpoint == FUTURES_POSITION_RISK_PATH:
            safety["binance_position_risk_endpoint_called"] = True


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key) not in {"_signed_query", "signature", "query", "signed_url"}
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
