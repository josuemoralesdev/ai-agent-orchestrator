from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.account_read_env_migration_verify import (
    ACCOUNT_READ_ENV_MIGRATION_VERIFY_BLOCKED,
    ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDED,
    ACCOUNT_READ_ENV_MIGRATION_VERIFY_REJECTED,
    CONFIRM_ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDING_PHRASE,
    LEDGER_FILENAME,
    build_account_read_env_migration_verify,
    load_account_read_env_migration_verify_records,
)

NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
SAFE_FLAGS = {
    "BINANCE_CONNECTOR_MODE": "read_only",
    "BINANCE_LIVE_TRADING_ENABLED": "false",
    "HAMMER_LIVE_EXECUTION_ENABLED": "false",
    "HAMMER_ALLOW_LIVE_ORDERS": "false",
    "HAMMER_GLOBAL_KILL_SWITCH": "true",
}
ACCOUNT_READ_PAIR = {
    "HAMMER_ACCOUNT_READ_BINANCE_API_KEY": "account-key-full-value",
    "HAMMER_ACCOUNT_READ_BINANCE_API_SECRET": "account-secret-full-value",
}
LEGACY_PAIR = {
    "BINANCE_API_KEY": "legacy-key-full-value",
    "BINANCE_API_SECRET": "legacy-secret-full-value",
}


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = build_account_read_env_migration_verify(log_dir=log_dir, env={**SAFE_FLAGS, **ACCOUNT_READ_PAIR}, now=NOW)

    assert payload["verify_recorded"] is False
    assert payload["verify_id"] is None
    assert payload["record_verify_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = build_account_read_env_migration_verify(
        log_dir=log_dir,
        record_verify=True,
        confirm_account_read_env_migration_verify="wrong",
        env={**SAFE_FLAGS, **ACCOUNT_READ_PAIR},
        now=NOW,
    )

    assert payload["status"] == ACCOUNT_READ_ENV_MIGRATION_VERIFY_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["verify_recorded"] is False
    assert load_account_read_env_migration_verify_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    before_config = config_path.read_text(encoding="utf-8")
    before_env = dict(os.environ)

    payload = build_account_read_env_migration_verify(
        log_dir=log_dir,
        record_verify=True,
        confirm_account_read_env_migration_verify=CONFIRM_ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDING_PHRASE,
        env={**SAFE_FLAGS, **ACCOUNT_READ_PAIR},
        now=NOW,
    )
    records = load_account_read_env_migration_verify_records(log_dir=log_dir, limit=0)

    assert payload["status"] == ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDED
    assert payload["verify_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "ACCOUNT_READ_ENV_MIGRATION_VERIFY"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_role_specific_account_read_passes(tmp_path: Path) -> None:
    payload = build_account_read_env_migration_verify(log_dir=tmp_path / "logs", env={**SAFE_FLAGS, **LEGACY_PAIR, **ACCOUNT_READ_PAIR}, now=NOW)

    role = payload["account_read_role_verification"]
    assert role["selected_pair_source"] == "role_specific"
    assert role["role_specific_pair_present"] is True
    assert role["legacy_fallback_used"] is False
    assert role["passed"] is True
    assert payload["recommended_next_operator_move"] == "RUN_READONLY_BALANCE_CHECK_WITH_ROLE_SPECIFIC_ACCOUNT_READ"


def test_legacy_fallback_account_read_blocks_and_warns(tmp_path: Path) -> None:
    payload = build_account_read_env_migration_verify(log_dir=tmp_path / "logs", env={**SAFE_FLAGS, **LEGACY_PAIR}, now=NOW)

    role = payload["account_read_role_verification"]
    assert payload["status"] == ACCOUNT_READ_ENV_MIGRATION_VERIFY_BLOCKED
    assert role["selected_pair_source"] == "legacy_fallback"
    assert role["legacy_fallback_used"] is True
    assert role["passed"] is False
    assert payload["recommended_next_operator_move"] == "FIX_ACCOUNT_READ_ENV_ROLE"


def test_missing_account_read_role_blocks(tmp_path: Path) -> None:
    payload = build_account_read_env_migration_verify(log_dir=tmp_path / "logs", env=SAFE_FLAGS, now=NOW)

    assert payload["status"] == ACCOUNT_READ_ENV_MIGRATION_VERIFY_BLOCKED
    assert payload["account_read_role_verification"]["selected_pair_source"] == "missing"
    assert payload["account_read_role_verification"]["passed"] is False
    assert "account_read role-specific key/secret pair is missing" in payload["blockers"]


def test_future_live_does_not_fallback_to_legacy(tmp_path: Path) -> None:
    payload = build_account_read_env_migration_verify(log_dir=tmp_path / "logs", env={**SAFE_FLAGS, **LEGACY_PAIR, **ACCOUNT_READ_PAIR}, now=NOW)

    future_live = payload["future_live_isolation"]
    assert future_live["future_live_disabled"] is True
    assert future_live["legacy_fallback_used_for_future_live"] is False
    assert future_live["selected_pair_source"] == "missing"
    assert future_live["passed"] is True


def test_runtime_safety_flags_required(tmp_path: Path) -> None:
    env = {**SAFE_FLAGS, **ACCOUNT_READ_PAIR, "HAMMER_ALLOW_LIVE_ORDERS": "true"}

    payload = build_account_read_env_migration_verify(log_dir=tmp_path / "logs", env=env, now=NOW)

    assert payload["status"] == ACCOUNT_READ_ENV_MIGRATION_VERIFY_BLOCKED
    assert payload["runtime_safety_verification"]["passed"] is False
    assert "HAMMER_ALLOW_LIVE_ORDERS" in payload["runtime_safety_verification"]["failed_flags"]


def test_no_secrets_shown(tmp_path: Path) -> None:
    payload = build_account_read_env_migration_verify(log_dir=tmp_path / "logs", env={**SAFE_FLAGS, **LEGACY_PAIR, **ACCOUNT_READ_PAIR}, now=NOW)
    rendered = json.dumps(payload, sort_keys=True)

    assert "account-key-full-value" not in rendered
    assert "account-secret-full-value" not in rendered
    assert "legacy-key-full-value" not in rendered
    assert "legacy-secret-full-value" not in rendered
    assert payload["account_read_role_verification"]["api_key_hash_preview"]
    assert payload["account_read_role_verification"]["api_secret_hash_preview"]
    assert payload["account_read_role_verification"]["secrets_shown"] is False
    assert payload["safety"]["secrets_shown"] is False
    assert payload["safety"]["full_api_key_shown"] is False
    assert payload["safety"]["full_api_secret_shown"] is False


def test_no_env_config_mutation_no_binance_calls(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_account_read_env_migration_verify(
            log_dir=tmp_path / "logs",
            env={**SAFE_FLAGS, **ACCOUNT_READ_PAIR},
            now=NOW,
        )

    urlopen.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert payload["no_write_verification"]["env_written"] is False
    assert payload["no_write_verification"]["env_mutated"] is False
    assert payload["no_write_verification"]["config_written"] is False
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False


def test_no_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    with (
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_account_read_env_migration_verify(
            log_dir=tmp_path / "logs",
            env={**SAFE_FLAGS, **ACCOUNT_READ_PAIR},
            now=NOW,
        )

    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    safety = payload["safety"]
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
    assert safety["global_live_flags_changed"] is False
    assert safety["paper_live_separation_intact"] is True


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "account-read-env-migration-verify",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": ".", **SAFE_FLAGS, **ACCOUNT_READ_PAIR},
        text=True,
        capture_output=True,
        check=True,
    )
    help_result = subprocess.run(
        [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["account_read_role_verification"]["selected_pair_source"] == "role_specific"
    assert "account-read-env-migration-verify" in help_result.stdout


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"lanes": []}), encoding="utf-8")
    return path
