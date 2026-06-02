from __future__ import annotations

import json
import os
import urllib.request
from unittest.mock import patch

from src.app.hammer_radar.operator.env_role_adapter import (
    ACCOUNT_READ_LEGACY_FALLBACK_WARNING,
    ROLE_ACCOUNT_READ,
    ROLE_FUTURE_LIVE,
    ROLE_MARKET_DATA,
    build_env_role_adapter_safety,
    build_env_role_resolution_summary,
    resolve_account_read_env_pair,
    resolve_binance_env_role,
    resolve_future_live_env_pair,
    resolve_market_data_env_pair,
    validate_account_read_runtime_safety,
)

SAFE_FLAGS = {
    "BINANCE_CONNECTOR_MODE": "read_only",
    "BINANCE_LIVE_TRADING_ENABLED": "false",
    "HAMMER_LIVE_EXECUTION_ENABLED": "false",
    "HAMMER_ALLOW_LIVE_ORDERS": "false",
    "HAMMER_GLOBAL_KILL_SWITCH": "true",
}
LEGACY_PAIR = {
    "BINANCE_API_KEY": "legacy-key-full-value",
    "BINANCE_API_SECRET": "legacy-secret-full-value",
}
ACCOUNT_READ_PAIR = {
    "HAMMER_ACCOUNT_READ_BINANCE_API_KEY": "account-key-full-value",
    "HAMMER_ACCOUNT_READ_BINANCE_API_SECRET": "account-secret-full-value",
}
MARKET_PAIR = {
    "HAMMER_MARKET_BINANCE_API_KEY": "market-key-full-value",
    "HAMMER_MARKET_BINANCE_API_SECRET": "market-secret-full-value",
}
LIVE_PAIR = {
    "HAMMER_LIVE_BINANCE_API_KEY": "live-key-full-value",
    "HAMMER_LIVE_BINANCE_API_SECRET": "live-secret-full-value",
}


def test_account_read_prefers_role_specific_pair_when_present() -> None:
    resolution = resolve_account_read_env_pair(env={**SAFE_FLAGS, **LEGACY_PAIR, **ACCOUNT_READ_PAIR})

    assert resolution["role"] == ROLE_ACCOUNT_READ
    assert resolution["selected_pair_source"] == "role_specific"
    assert resolution["legacy_fallback_used"] is False
    assert resolution["role_specific_pair_present"] is True
    assert resolution["runtime_safety_ok"] is True


def test_account_read_falls_back_to_legacy_only_when_role_specific_absent() -> None:
    resolution = resolve_account_read_env_pair(env={**SAFE_FLAGS, **LEGACY_PAIR})

    assert resolution["selected_pair_source"] == "legacy_fallback"
    assert resolution["legacy_fallback_used"] is True
    assert resolution["legacy_ambiguous"] is True
    assert ACCOUNT_READ_LEGACY_FALLBACK_WARNING in resolution["warnings"]


def test_account_read_partial_role_pair_does_not_fallback_to_legacy() -> None:
    resolution = resolve_account_read_env_pair(
        env={**SAFE_FLAGS, **LEGACY_PAIR, "HAMMER_ACCOUNT_READ_BINANCE_API_KEY": "partial-account-key"}
    )

    assert resolution["selected_pair_source"] == "missing"
    assert resolution["partial_pair_detected"] is True
    assert resolution["legacy_fallback_used"] is False


def test_account_read_runtime_safety_requires_read_only_live_false_and_kill_switch_true() -> None:
    assert validate_account_read_runtime_safety(env=SAFE_FLAGS)["runtime_safety_ok"] is True

    unsafe = validate_account_read_runtime_safety(env={**SAFE_FLAGS, "HAMMER_ALLOW_LIVE_ORDERS": "true"})

    assert unsafe["runtime_safety_ok"] is False
    assert "HAMMER_ALLOW_LIVE_ORDERS" in unsafe["failed_flags"]


def test_market_data_prefers_hammer_market_pair() -> None:
    resolution = resolve_market_data_env_pair(env={**SAFE_FLAGS, **LEGACY_PAIR, **MARKET_PAIR})

    assert resolution["role"] == ROLE_MARKET_DATA
    assert resolution["selected_pair_source"] == "role_specific"
    assert resolution["legacy_fallback_used"] is False


def test_future_live_prefers_hammer_live_pair_but_never_legacy_fallback() -> None:
    with_live = resolve_future_live_env_pair(env={**SAFE_FLAGS, **LEGACY_PAIR, **LIVE_PAIR})
    legacy_only = resolve_future_live_env_pair(env={**SAFE_FLAGS, **LEGACY_PAIR})

    assert with_live["role"] == ROLE_FUTURE_LIVE
    assert with_live["selected_pair_source"] == "role_specific"
    assert with_live["future_live_disabled"] is True
    assert legacy_only["selected_pair_source"] == "missing"
    assert legacy_only["legacy_fallback_used"] is False
    assert legacy_only["legacy_pair_present_ignored"] is True
    assert legacy_only["future_live_disabled"] is True


def test_resolve_binance_env_role_rejects_unknown_role() -> None:
    try:
        resolve_binance_env_role("unknown", env={})
    except ValueError as exc:
        assert "unsupported env role" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unknown role should raise")


def test_summary_contains_matrix_risks_and_no_raw_secrets() -> None:
    payload = build_env_role_resolution_summary(env={**SAFE_FLAGS, **LEGACY_PAIR, **ACCOUNT_READ_PAIR, **MARKET_PAIR, **LIVE_PAIR})
    rendered = json.dumps(payload, sort_keys=True)

    for secret in (
        "legacy-key-full-value",
        "legacy-secret-full-value",
        "account-key-full-value",
        "account-secret-full-value",
        "market-key-full-value",
        "market-secret-full-value",
        "live-key-full-value",
        "live-secret-full-value",
    ):
        assert secret not in rendered
    assert payload["role_resolution_matrix"]["account_read"]["api_key_hash_preview"]
    assert payload["safety"]["secrets_shown"] is False


def test_no_env_mutation_no_network_no_order_or_transfer_actions() -> None:
    before_env = dict(os.environ)
    with patch.object(urllib.request, "urlopen") as urlopen:
        safety = build_env_role_adapter_safety()
        payload = build_env_role_resolution_summary(env={**SAFE_FLAGS, **LEGACY_PAIR})

    urlopen.assert_not_called()
    assert before_env == dict(os.environ)
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert safety["order_placed"] is False
    assert safety["real_order_placed"] is False
    assert safety["execution_attempted"] is False
    assert safety["order_payload_created"] is False
    assert safety["executable_payload_created"] is False
    assert safety["signed_order_request_created"] is False
    assert safety["signed_trading_request_created"] is False
    assert safety["binance_order_endpoint_called"] is False
    assert safety["binance_test_order_endpoint_called"] is False
    assert safety["transfer_endpoint_called"] is False
    assert safety["withdraw_endpoint_called"] is False
    assert safety["paper_live_separation_intact"] is True
