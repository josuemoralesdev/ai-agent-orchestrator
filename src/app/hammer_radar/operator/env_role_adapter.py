"""R171 no-write Binance env role adapter.

This module resolves Binance credential roles from an injected/process env map.
It never writes env/config files, calls Binance, creates order payloads, or
returns raw secrets in summaries.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from typing import Any

from src.app.hammer_radar.operator.binance_live_status import (
    ENV_ALLOW_LIVE_ORDERS,
    ENV_BINANCE_LIVE_ENABLED,
    ENV_GLOBAL_KILL_SWITCH,
    ENV_LIVE_EXECUTION_ENABLED,
)
from src.app.hammer_radar.operator.binance_readonly import (
    ENV_API_KEY,
    ENV_API_SECRET,
    ENV_CONNECTOR_MODE,
    ENV_LIVE_TRADING_ENABLED,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

MARKET_KEY_VAR = "HAMMER_MARKET_BINANCE_API_KEY"
MARKET_SECRET_VAR = "HAMMER_MARKET_BINANCE_API_SECRET"
ACCOUNT_READ_KEY_VAR = "HAMMER_ACCOUNT_READ_BINANCE_API_KEY"
ACCOUNT_READ_SECRET_VAR = "HAMMER_ACCOUNT_READ_BINANCE_API_SECRET"
LIVE_KEY_VAR = "HAMMER_LIVE_BINANCE_API_KEY"
LIVE_SECRET_VAR = "HAMMER_LIVE_BINANCE_API_SECRET"

ROLE_MARKET_DATA = "market_data"
ROLE_ACCOUNT_READ = "account_read"
ROLE_FUTURE_LIVE = "future_live"
ROLES = (ROLE_MARKET_DATA, ROLE_ACCOUNT_READ, ROLE_FUTURE_LIVE)

SELECTED_ROLE_SPECIFIC = "role_specific"
SELECTED_LEGACY_FALLBACK = "legacy_fallback"
SELECTED_MISSING = "missing"

ACCOUNT_READ_LEGACY_FALLBACK_WARNING = (
    "account_read uses legacy fallback; role-specific HAMMER_ACCOUNT_READ_* variables are preferred."
)

ACCOUNT_READ_RUNTIME_REQUIRED = {
    ENV_CONNECTOR_MODE: "read_only",
    ENV_LIVE_TRADING_ENABLED: "false",
    ENV_LIVE_EXECUTION_ENABLED: "false",
    ENV_ALLOW_LIVE_ORDERS: "false",
    ENV_GLOBAL_KILL_SWITCH: "true",
}

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
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
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "full_api_key_shown": False,
    "full_api_secret_shown": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
}


def resolve_binance_env_role(role: str, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    if role not in ROLES:
        raise ValueError(f"unsupported env role: {role}")
    role_pair = _role_pair(role)
    legacy_pair = [ENV_API_KEY, ENV_API_SECRET] if role in {ROLE_MARKET_DATA, ROLE_ACCOUNT_READ} else []
    role_specific = _pair_summary(source, role_pair, SELECTED_ROLE_SPECIFIC)
    legacy = _pair_summary(source, legacy_pair, SELECTED_LEGACY_FALLBACK) if legacy_pair else _empty_pair_summary(SELECTED_LEGACY_FALLBACK)

    selected_source = SELECTED_MISSING
    selected = _empty_pair_summary(SELECTED_MISSING)
    legacy_fallback_used = False
    legacy_ambiguous = False
    if _pair_complete(role_specific):
        selected_source = SELECTED_ROLE_SPECIFIC
        selected = role_specific
    elif role != ROLE_FUTURE_LIVE and _pair_absent(role_specific) and _pair_complete(legacy):
        selected_source = SELECTED_LEGACY_FALLBACK
        selected = legacy
        legacy_fallback_used = True
        legacy_ambiguous = True

    partial_pair_detected = _pair_partial(role_specific) or (role != ROLE_FUTURE_LIVE and _pair_partial(legacy))
    warnings: list[str] = []
    if role == ROLE_ACCOUNT_READ and legacy_fallback_used:
        warnings.append(ACCOUNT_READ_LEGACY_FALLBACK_WARNING)
    if partial_pair_detected:
        warnings.append(f"{role} has a partial key/secret pair; complete pairs are required before use.")

    resolution = {
        "role": role,
        "selected_pair_source": selected_source,
        "api_key_variable": selected.get("api_key_variable"),
        "api_secret_variable": selected.get("api_secret_variable"),
        "api_key_present": bool(selected.get("api_key_present")),
        "api_secret_present": bool(selected.get("api_secret_present")),
        "api_key_length": int(selected.get("api_key_length") or 0),
        "api_secret_length": int(selected.get("api_secret_length") or 0),
        "api_key_hash_preview": selected.get("api_key_hash_preview"),
        "api_secret_hash_preview": selected.get("api_secret_hash_preview"),
        "role_specific_pair_present": _pair_complete(role_specific),
        "role_specific_pair_partial": _pair_partial(role_specific),
        "legacy_pair_present": _pair_complete(legacy),
        "legacy_pair_partial": _pair_partial(legacy),
        "partial_pair_detected": partial_pair_detected,
        "legacy_fallback_used": legacy_fallback_used,
        "legacy_ambiguous": legacy_ambiguous,
        "warnings": warnings,
        "full_api_key_shown": False,
        "full_api_secret_shown": False,
        "secrets_shown": False,
    }
    if role == ROLE_ACCOUNT_READ:
        runtime = build_runtime_safety_flags(env=source)
        resolution["account_read_runtime_required"] = dict(ACCOUNT_READ_RUNTIME_REQUIRED)
        resolution["account_read_runtime_safe"] = validate_account_read_runtime_safety(env=source)["runtime_safety_ok"]
        resolution["runtime_safety_ok"] = bool(resolution["account_read_runtime_safe"])
        resolution["runtime_safety_flags"] = runtime
    if role == ROLE_FUTURE_LIVE:
        legacy_present = bool(_env_value(source, ENV_API_KEY)) and bool(_env_value(source, ENV_API_SECRET))
        resolution["future_live_disabled"] = True
        resolution["legacy_fallback_allowed"] = False
        resolution["legacy_pair_present_ignored"] = legacy_present
    return resolution


def resolve_account_read_env_pair(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    return resolve_binance_env_role(ROLE_ACCOUNT_READ, env=env)


def resolve_market_data_env_pair(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    return resolve_binance_env_role(ROLE_MARKET_DATA, env=env)


def resolve_future_live_env_pair(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    return resolve_binance_env_role(ROLE_FUTURE_LIVE, env=env)


def build_env_role_resolution_summary(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    matrix = {role: resolve_binance_env_role(role, env=source) for role in ROLES}
    return {
        "role_resolution_matrix": matrix,
        "runtime_safety_flags": build_runtime_safety_flags(env=source),
        "legacy_fallback_risks": detect_legacy_fallback_risks(
            role_resolution_matrix=matrix,
            runtime_safety_flags=build_runtime_safety_flags(env=source),
        ),
        "safety": build_env_role_adapter_safety(),
    }


def validate_account_read_runtime_safety(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    flags = build_runtime_safety_flags(env=env)
    failed = [
        name
        for name, required in ACCOUNT_READ_RUNTIME_REQUIRED.items()
        if str(flags.get(name) or "n/a").lower() != required
    ]
    return {
        "runtime_safety_ok": not failed,
        "required_flags": dict(ACCOUNT_READ_RUNTIME_REQUIRED),
        "runtime_safety_flags": flags,
        "failed_flags": failed,
        "secrets_shown": False,
    }


def build_env_role_adapter_safety() -> dict[str, Any]:
    return dict(SAFETY)


def build_runtime_safety_flags(*, env: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    return {
        ENV_CONNECTOR_MODE: _env_value(source, ENV_CONNECTOR_MODE) or "n/a",
        ENV_LIVE_TRADING_ENABLED: _env_value(source, ENV_LIVE_TRADING_ENABLED) or "n/a",
        ENV_BINANCE_LIVE_ENABLED: _env_value(source, ENV_BINANCE_LIVE_ENABLED) or "n/a",
        ENV_LIVE_EXECUTION_ENABLED: _env_value(source, ENV_LIVE_EXECUTION_ENABLED) or "n/a",
        ENV_ALLOW_LIVE_ORDERS: _env_value(source, ENV_ALLOW_LIVE_ORDERS) or "n/a",
        ENV_GLOBAL_KILL_SWITCH: _env_value(source, ENV_GLOBAL_KILL_SWITCH) or "n/a",
    }


def detect_legacy_fallback_risks(
    *,
    role_resolution_matrix: Mapping[str, Any],
    runtime_safety_flags: Mapping[str, str] | None = None,
) -> list[str]:
    risks: list[str] = []
    market = role_resolution_matrix.get(ROLE_MARKET_DATA) or {}
    account = role_resolution_matrix.get(ROLE_ACCOUNT_READ) or {}
    future_live = role_resolution_matrix.get(ROLE_FUTURE_LIVE) or {}
    for role in (ROLE_MARKET_DATA, ROLE_ACCOUNT_READ):
        resolution = role_resolution_matrix.get(role) or {}
        if resolution.get("legacy_fallback_used"):
            if role == ROLE_ACCOUNT_READ:
                risks.append(ACCOUNT_READ_LEGACY_FALLBACK_WARNING)
            else:
                risks.append(f"{role} uses legacy BINANCE_API_KEY/BINANCE_API_SECRET fallback; role source remains ambiguous")
        if resolution.get("partial_pair_detected"):
            risks.append(f"{role} has a partial key/secret pair; do not migrate or wire until pair is complete")
    if market.get("legacy_fallback_used") and account.get("legacy_fallback_used"):
        risks.append("market_data and account_read both fall back to the same legacy pair; intended key role cannot be proven")
    if future_live.get("legacy_pair_present_ignored"):
        risks.append("future_live ignores legacy BINANCE_API_KEY/BINANCE_API_SECRET by design")
    if future_live.get("partial_pair_detected"):
        risks.append("future_live role-specific pair is partial; keep future live disabled")
    flags = runtime_safety_flags or {}
    if flags and _account_read_runtime_safe(flags) is not True:
        risks.append("account_read runtime flags are not in the required read-only/live-disabled/kill-switch-on state")
    return _dedupe(risks)


def account_read_env_for_legacy_connector(*, env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return env with selected account-read pair mapped to legacy connector names.

    The existing readonly connector expects BINANCE_API_KEY/BINANCE_API_SECRET.
    This adapter preserves that interface without mutating process env or files.
    """
    source = os.environ if env is None else env
    adapted = {str(key): str(value) for key, value in source.items()}
    resolution = resolve_account_read_env_pair(env=source)
    if resolution.get("api_key_present") and resolution.get("api_key_variable"):
        adapted[ENV_API_KEY] = _env_value(source, str(resolution["api_key_variable"]))
    if resolution.get("api_secret_present") and resolution.get("api_secret_variable"):
        adapted[ENV_API_SECRET] = _env_value(source, str(resolution["api_secret_variable"]))
    return adapted


def _role_pair(role: str) -> list[str]:
    if role == ROLE_MARKET_DATA:
        return [MARKET_KEY_VAR, MARKET_SECRET_VAR]
    if role == ROLE_ACCOUNT_READ:
        return [ACCOUNT_READ_KEY_VAR, ACCOUNT_READ_SECRET_VAR]
    if role == ROLE_FUTURE_LIVE:
        return [LIVE_KEY_VAR, LIVE_SECRET_VAR]
    raise ValueError(f"unsupported env role: {role}")


def _pair_summary(source: Mapping[str, str], pair: list[str], source_name: str) -> dict[str, Any]:
    if len(pair) != 2:
        return _empty_pair_summary(source_name)
    key_name, secret_name = pair
    api_key = _env_value(source, key_name)
    api_secret = _env_value(source, secret_name)
    return {
        "pair_source": source_name,
        "api_key_variable": key_name,
        "api_secret_variable": secret_name,
        "api_key_present": bool(api_key),
        "api_secret_present": bool(api_secret),
        "api_key_length": len(api_key) if api_key else 0,
        "api_secret_length": len(api_secret) if api_secret else 0,
        "api_key_hash_preview": _hash_preview(api_key),
        "api_secret_hash_preview": _hash_preview(api_secret),
        "secrets_shown": False,
    }


def _empty_pair_summary(source_name: str) -> dict[str, Any]:
    return {
        "pair_source": source_name,
        "api_key_variable": None,
        "api_secret_variable": None,
        "api_key_present": False,
        "api_secret_present": False,
        "api_key_length": 0,
        "api_secret_length": 0,
        "api_key_hash_preview": None,
        "api_secret_hash_preview": None,
        "secrets_shown": False,
    }


def _pair_complete(pair: Mapping[str, Any]) -> bool:
    return bool(pair.get("api_key_present")) and bool(pair.get("api_secret_present"))


def _pair_absent(pair: Mapping[str, Any]) -> bool:
    return not pair.get("api_key_present") and not pair.get("api_secret_present")


def _pair_partial(pair: Mapping[str, Any]) -> bool:
    return bool(pair.get("api_key_present")) != bool(pair.get("api_secret_present"))


def _account_read_runtime_safe(flags: Mapping[str, str]) -> bool:
    return all(str(flags.get(name) or "n/a").lower() == required for name, required in ACCOUNT_READ_RUNTIME_REQUIRED.items())


def _env_value(source: Mapping[str, str], key: str) -> str:
    return str(source.get(key) or "").strip()


def _hash_preview(value: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))
