from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.account_read_env_migration_packet import (
    ACCOUNT_READ_ENV_MIGRATION_PACKET_RECORDED,
    ACCOUNT_READ_ENV_MIGRATION_PACKET_REJECTED,
    CONFIRM_ACCOUNT_READ_ENV_MIGRATION_PACKET_RECORDING_PHRASE,
    LEDGER_FILENAME,
    build_account_read_env_migration_packet,
    build_account_read_source_inventory,
    load_account_read_env_migration_packet_records,
)

NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
SOURCE_KEY = "k" * 64
SOURCE_SECRET = "s" * 64


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    source = _write_source_env(tmp_path / "binance-live.env")

    payload = build_account_read_env_migration_packet(
        log_dir=log_dir,
        account_capable_source_file=source,
        now=NOW,
    )

    assert payload["packet_recorded"] is False
    assert payload["packet_id"] is None
    assert payload["record_packet_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    source = _write_source_env(tmp_path / "binance-live.env")

    payload = build_account_read_env_migration_packet(
        log_dir=log_dir,
        account_capable_source_file=source,
        record_packet=True,
        confirm_account_read_env_migration="wrong",
        now=NOW,
    )

    assert payload["status"] == ACCOUNT_READ_ENV_MIGRATION_PACKET_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["packet_recorded"] is False
    assert load_account_read_env_migration_packet_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    source = _write_source_env(tmp_path / "binance-live.env")
    config_path = _write_config(tmp_path / "lane_controls.json")
    before_files = {
        source: source.read_text(encoding="utf-8"),
        config_path: config_path.read_text(encoding="utf-8"),
    }

    payload = build_account_read_env_migration_packet(
        log_dir=log_dir,
        account_capable_source_file=source,
        record_packet=True,
        confirm_account_read_env_migration=CONFIRM_ACCOUNT_READ_ENV_MIGRATION_PACKET_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_account_read_env_migration_packet_records(log_dir=log_dir, limit=0)

    assert payload["status"] == ACCOUNT_READ_ENV_MIGRATION_PACKET_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["packet_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "ACCOUNT_READ_ENV_MIGRATION_PACKET"
    assert {path: path.read_text(encoding="utf-8") for path in before_files} == before_files


def test_account_capable_source_inventory_uses_hash_and_length_only(tmp_path: Path) -> None:
    source = _write_source_env(tmp_path / "binance-live.env")

    inventory = build_account_read_source_inventory(account_capable_source_file=source)
    rendered = json.dumps(inventory, sort_keys=True)

    assert inventory["account_capable_source_file"] == str(source)
    assert inventory["source_file_present"] is True
    assert inventory["source_key_length"] == 64
    assert inventory["source_secret_length"] == 64
    assert inventory["source_key_hash_preview"]
    assert inventory["source_secret_hash_preview"]
    assert inventory["secrets_shown"] is False
    assert SOURCE_KEY not in rendered
    assert SOURCE_SECRET not in rendered


def test_secrets_are_not_shown(tmp_path: Path) -> None:
    source = _write_source_env(tmp_path / "binance-live.env")

    payload = build_account_read_env_migration_packet(account_capable_source_file=source, now=NOW)
    rendered = json.dumps(payload, sort_keys=True)

    assert SOURCE_KEY not in rendered
    assert SOURCE_SECRET not in rendered
    assert payload["account_read_source_inventory"]["secrets_shown"] is False
    assert payload["safety"]["secrets_shown"] is False
    assert payload["safety"]["full_api_key_shown"] is False
    assert payload["safety"]["full_api_secret_shown"] is False


def test_manual_commands_include_account_read_vars_and_forced_flags(tmp_path: Path) -> None:
    source = _write_source_env(tmp_path / "binance-live.env")

    payload = build_account_read_env_migration_packet(account_capable_source_file=source, now=NOW)
    commands = "\n".join(payload["manual_source_commands"])

    assert "HAMMER_ACCOUNT_READ_BINANCE_API_KEY" in commands
    assert "HAMMER_ACCOUNT_READ_BINANCE_API_SECRET" in commands
    assert 'export HAMMER_ACCOUNT_READ_BINANCE_API_KEY="$BINANCE_API_KEY"' in commands
    assert 'export HAMMER_ACCOUNT_READ_BINANCE_API_SECRET="$BINANCE_API_SECRET"' in commands
    assert "export BINANCE_CONNECTOR_MODE=read_only" in commands
    assert "export BINANCE_LIVE_TRADING_ENABLED=false" in commands
    assert "export HAMMER_BINANCE_LIVE_ENABLED=false" in commands
    assert "export HAMMER_LIVE_EXECUTION_ENABLED=false" in commands
    assert "export HAMMER_ALLOW_LIVE_ORDERS=false" in commands
    assert "export HAMMER_GLOBAL_KILL_SWITCH=true" in commands


def test_post_migration_verification_commands_included(tmp_path: Path) -> None:
    source = _write_source_env(tmp_path / "binance-live.env")

    payload = build_account_read_env_migration_packet(account_capable_source_file=source, now=NOW)
    commands = "\n".join(payload["post_migration_verification_commands"])

    assert "env-role-adapter-preview" in commands
    assert "funding-readonly-precheck" in commands
    assert "readonly-balance-check" in commands
    assert "readonly-balance-check --allow-readonly-network-check" in commands


def test_no_env_config_mutation_no_binance_calls(tmp_path: Path) -> None:
    source = _write_source_env(tmp_path / "binance-live.env")
    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_files = {
        source: source.read_text(encoding="utf-8"),
        config_path: config_path.read_text(encoding="utf-8"),
    }

    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_account_read_env_migration_packet(account_capable_source_file=source, now=NOW)

    urlopen.assert_not_called()
    assert before_env == dict(os.environ)
    assert {path: path.read_text(encoding="utf-8") for path in before_files} == before_files
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["signed_readonly_request_created"] is False


def test_no_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    source = _write_source_env(tmp_path / "binance-live.env")

    payload = build_account_read_env_migration_packet(account_capable_source_file=source, now=NOW)
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

    assert "account-read-env-migration-packet" in result.stdout


def _write_source_env(path: Path) -> Path:
    path.write_text(
        f"BINANCE_API_KEY={SOURCE_KEY}\nBINANCE_API_SECRET={SOURCE_SECRET}\n",
        encoding="utf-8",
    )
    return path


def _write_config(path: Path) -> Path:
    path.write_text(json.dumps({"lanes": []}), encoding="utf-8")
    return path
