from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.env_role_adapter_preview import (
    ACCOUNT_READ_KEY_VAR,
    CONFIRM_ENV_ROLE_ADAPTER_PREVIEW_RECORDING_PHRASE,
    ENV_ROLE_ADAPTER_PREVIEW_RECORDED,
    ENV_ROLE_ADAPTER_PREVIEW_REJECTED,
    LEDGER_FILENAME,
    LIVE_KEY_VAR,
    MARKET_KEY_VAR,
    build_env_role_adapter_preview,
    build_role_resolution_matrix,
    load_env_role_adapter_preview_records,
)

NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
SAFE_FLAGS = {
    "BINANCE_CONNECTOR_MODE": "read_only",
    "BINANCE_LIVE_TRADING_ENABLED": "false",
    "HAMMER_BINANCE_LIVE_ENABLED": "false",
    "HAMMER_LIVE_EXECUTION_ENABLED": "false",
    "HAMMER_ALLOW_LIVE_ORDERS": "false",
    "HAMMER_GLOBAL_KILL_SWITCH": "true",
}
LEGACY_PAIR = {
    "BINANCE_API_KEY": "legacy-key-full-value",
    "BINANCE_API_SECRET": "legacy-secret-full-value",
}


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = build_env_role_adapter_preview(log_dir=log_dir, env={**SAFE_FLAGS, **LEGACY_PAIR}, now=NOW)

    assert payload["preview_recorded"] is False
    assert payload["preview_id"] is None
    assert payload["record_preview_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = build_env_role_adapter_preview(
        log_dir=log_dir,
        env={**SAFE_FLAGS, **LEGACY_PAIR},
        record_preview=True,
        confirm_env_role_adapter_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == ENV_ROLE_ADAPTER_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["preview_recorded"] is False
    assert payload["recommended_next_operator_move"] == "KEEP_ENV_UNCHANGED"
    assert load_env_role_adapter_preview_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    env_path = _write_env(tmp_path / ".env")
    before_files = {
        config_path: config_path.read_text(encoding="utf-8"),
        env_path: env_path.read_text(encoding="utf-8"),
    }

    payload = build_env_role_adapter_preview(
        log_dir=log_dir,
        env={**SAFE_FLAGS, **LEGACY_PAIR},
        record_preview=True,
        confirm_env_role_adapter_preview=CONFIRM_ENV_ROLE_ADAPTER_PREVIEW_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_env_role_adapter_preview_records(log_dir=log_dir, limit=0)

    assert payload["status"] == ENV_ROLE_ADAPTER_PREVIEW_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["preview_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "ENV_ROLE_ADAPTER_PREVIEW"
    assert {path: path.read_text(encoding="utf-8") for path in before_files} == before_files


def test_market_role_prefers_hammer_market_pair_if_present() -> None:
    matrix = build_role_resolution_matrix(
        env={
            **SAFE_FLAGS,
            **LEGACY_PAIR,
            "HAMMER_MARKET_BINANCE_API_KEY": "market-key-full-value",
            "HAMMER_MARKET_BINANCE_API_SECRET": "market-secret-full-value",
        }
    )

    market = matrix["market_data"]
    assert market["selected_pair_source"] == "role_specific"
    assert market["api_key_variable"] == MARKET_KEY_VAR
    assert market["legacy_fallback_used"] is False


def test_account_read_role_prefers_hammer_account_read_pair_if_present() -> None:
    matrix = build_role_resolution_matrix(
        env={
            **SAFE_FLAGS,
            **LEGACY_PAIR,
            "HAMMER_ACCOUNT_READ_BINANCE_API_KEY": "account-key-full-value",
            "HAMMER_ACCOUNT_READ_BINANCE_API_SECRET": "account-secret-full-value",
        }
    )

    account = matrix["account_read"]
    assert account["selected_pair_source"] == "role_specific"
    assert account["api_key_variable"] == ACCOUNT_READ_KEY_VAR
    assert account["legacy_fallback_used"] is False
    assert account["account_read_runtime_safe"] is True


def test_future_live_role_prefers_hammer_live_pair_if_present() -> None:
    matrix = build_role_resolution_matrix(
        env={
            **SAFE_FLAGS,
            **LEGACY_PAIR,
            "HAMMER_LIVE_BINANCE_API_KEY": "live-key-full-value",
            "HAMMER_LIVE_BINANCE_API_SECRET": "live-secret-full-value",
        }
    )

    future_live = matrix["future_live"]
    assert future_live["selected_pair_source"] == "role_specific"
    assert future_live["api_key_variable"] == LIVE_KEY_VAR
    assert future_live["legacy_fallback_used"] is False
    assert future_live["future_live_disabled"] is True


def test_future_live_does_not_fallback_to_legacy_binance_pair() -> None:
    matrix = build_role_resolution_matrix(env={**SAFE_FLAGS, **LEGACY_PAIR})

    future_live = matrix["future_live"]
    assert future_live["selected_pair_source"] == "missing"
    assert future_live["api_key_present"] is False
    assert future_live["api_secret_present"] is False
    assert future_live["legacy_fallback_used"] is False
    assert future_live["legacy_pair_present_ignored"] is True


def test_account_read_legacy_fallback_is_marked_ambiguous() -> None:
    matrix = build_role_resolution_matrix(env={**SAFE_FLAGS, **LEGACY_PAIR})

    account = matrix["account_read"]
    assert account["selected_pair_source"] == "legacy_fallback"
    assert account["legacy_fallback_used"] is True
    assert account["legacy_ambiguous"] is True


def test_market_legacy_fallback_is_marked_ambiguous() -> None:
    matrix = build_role_resolution_matrix(env={**SAFE_FLAGS, **LEGACY_PAIR})

    market = matrix["market_data"]
    assert market["selected_pair_source"] == "legacy_fallback"
    assert market["legacy_fallback_used"] is True
    assert market["legacy_ambiguous"] is True


def test_no_secrets_shown_only_hash_previews_and_lengths() -> None:
    payload = build_env_role_adapter_preview(
        env={
            **SAFE_FLAGS,
            **LEGACY_PAIR,
            "HAMMER_MARKET_BINANCE_API_KEY": "market-key-full-value",
            "HAMMER_MARKET_BINANCE_API_SECRET": "market-secret-full-value",
            "HAMMER_ACCOUNT_READ_BINANCE_API_KEY": "account-key-full-value",
            "HAMMER_ACCOUNT_READ_BINANCE_API_SECRET": "account-secret-full-value",
            "HAMMER_LIVE_BINANCE_API_KEY": "live-key-full-value",
            "HAMMER_LIVE_BINANCE_API_SECRET": "live-secret-full-value",
        },
        now=NOW,
    )
    rendered = json.dumps(payload, sort_keys=True)

    for secret in (
        "legacy-key-full-value",
        "legacy-secret-full-value",
        "market-key-full-value",
        "market-secret-full-value",
        "account-key-full-value",
        "account-secret-full-value",
        "live-key-full-value",
        "live-secret-full-value",
    ):
        assert secret not in rendered
    market = payload["role_resolution_matrix"]["market_data"]
    assert market["api_key_length"] == len("market-key-full-value")
    assert market["api_secret_length"] == len("market-secret-full-value")
    assert market["api_key_hash_preview"]
    assert market["api_secret_hash_preview"]
    assert payload["safety"]["secrets_shown"] is False


def test_runtime_safety_flags_reported() -> None:
    payload = build_env_role_adapter_preview(env={**SAFE_FLAGS, **LEGACY_PAIR}, now=NOW)

    assert payload["runtime_safety_flags"]["BINANCE_CONNECTOR_MODE"] == "read_only"
    assert payload["runtime_safety_flags"]["BINANCE_LIVE_TRADING_ENABLED"] == "false"
    assert payload["runtime_safety_flags"]["HAMMER_BINANCE_LIVE_ENABLED"] == "false"
    assert payload["runtime_safety_flags"]["HAMMER_LIVE_EXECUTION_ENABLED"] == "false"
    assert payload["runtime_safety_flags"]["HAMMER_ALLOW_LIVE_ORDERS"] == "false"
    assert payload["runtime_safety_flags"]["HAMMER_GLOBAL_KILL_SWITCH"] == "true"


def test_no_env_config_mutation() -> None:
    before_env = dict(os.environ)

    payload = build_env_role_adapter_preview(env={**SAFE_FLAGS, **LEGACY_PAIR}, now=NOW)

    assert before_env == dict(os.environ)
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False


def test_no_binance_calls() -> None:
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_env_role_adapter_preview(env={**SAFE_FLAGS, **LEGACY_PAIR}, now=NOW)

    urlopen.assert_not_called()
    assert payload["safety"]["signed_readonly_request_created"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["binance_test_order_endpoint_called"] is False


def test_no_order_live_transfer_withdraw_actions() -> None:
    payload = build_env_role_adapter_preview(env={**SAFE_FLAGS, **LEGACY_PAIR}, now=NOW)

    assert payload["safety"]["order_placed"] is False
    assert payload["safety"]["real_order_placed"] is False
    assert payload["safety"]["execution_attempted"] is False
    assert payload["safety"]["order_payload_created"] is False
    assert payload["safety"]["executable_payload_created"] is False
    assert payload["safety"]["signed_order_request_created"] is False
    assert payload["safety"]["signed_trading_request_created"] is False
    assert payload["safety"]["transfer_endpoint_called"] is False
    assert payload["safety"]["withdraw_endpoint_called"] is False
    assert payload["safety"]["global_live_flags_changed"] is False
    assert payload["safety"]["paper_live_separation_intact"] is True
    assert "live-connector-submit" in payload["do_not_run_yet"]
    assert "any order endpoint" in payload["do_not_run_yet"]
    assert "transfer" in payload["do_not_run_yet"]
    assert "withdraw" in payload["do_not_run_yet"]


def test_cli_exists() -> None:
    result = subprocess.run(
        [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "env-role-adapter-preview" in result.stdout


def _write_env(path: Path) -> Path:
    path.write_text("BINANCE_API_KEY=legacy-key\nBINANCE_API_SECRET=legacy-secret\n", encoding="utf-8")
    return path


def _write_config(path: Path) -> Path:
    path.write_text(json.dumps({"lanes": []}), encoding="utf-8")
    return path
