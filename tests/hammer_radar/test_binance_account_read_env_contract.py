from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.binance_account_read_env_contract import (
    ACCOUNT_READ_ENV_ALIAS_PRESENT_BUT_NOT_MARKED_READ_ONLY,
    ACCOUNT_READ_ENV_MISSING,
    ACCOUNT_READ_ENV_PARTIAL,
    ACCOUNT_READ_ENV_READY,
    build_binance_account_read_env_discovery,
    format_binance_account_read_env_discovery_json,
    load_allowed_readonly_env_file,
    parse_env_file_names_only,
)
from src.app.hammer_radar.operator import binance_account_read_env_contract as env_contract
from src.app.hammer_radar.operator.binance_account_position_readonly import build_account_position_readiness
from tests.hammer_radar.test_binance_account_position_readonly import _PrivateFakeUrlOpen


SAFE_FLAGS = {
    "BINANCE_CONNECTOR_MODE": "read_only",
    "BINANCE_LIVE_TRADING_ENABLED": "false",
    "HAMMER_BINANCE_LIVE_ENABLED": "false",
    "HAMMER_LIVE_EXECUTION_ENABLED": "false",
    "HAMMER_ALLOW_LIVE_ORDERS": "false",
    "HAMMER_GLOBAL_KILL_SWITCH": "true",
}


def test_canonical_env_present_is_ready_without_values() -> None:
    env = {
        "HAMMER_BINANCE_ACCOUNT_READ_ENABLED": "true",
        "HAMMER_BINANCE_ACCOUNT_READ_MODE": "read_only",
        "HAMMER_BINANCE_ACCOUNT_READ_API_KEY": "canonical-key-value",
        "HAMMER_BINANCE_ACCOUNT_READ_API_SECRET": "canonical-secret-value",
    }

    payload = build_binance_account_read_env_discovery(env=env, include_systemd=False)
    rendered = json.dumps(payload)

    assert payload["status"] == ACCOUNT_READ_ENV_READY
    assert payload["selected_env_contract"]["selected_env_source"] == "canonical"
    assert payload["selected_env_contract"]["selected_api_key_env_name"] == "HAMMER_BINANCE_ACCOUNT_READ_API_KEY"
    assert payload["selected_env_contract"]["selected_env_values_redacted"] is True
    assert "canonical-key-value" not in rendered
    assert "canonical-secret-value" not in rendered
    assert payload["safety"]["secret_values_in_output"] is False
    assert payload["safety"]["env_mutated"] is False


def test_legacy_alias_env_with_readonly_marker_is_ready() -> None:
    env = {
        **SAFE_FLAGS,
        "BINANCE_API_KEY": "legacy-key-value",
        "BINANCE_API_SECRET": "legacy-secret-value",
    }

    payload = build_binance_account_read_env_discovery(env=env, include_systemd=False)

    assert payload["status"] == ACCOUNT_READ_ENV_READY
    assert payload["selected_env_contract"]["selected_env_source"] == "alias"
    assert payload["selected_env_contract"]["selected_env_source_detail"] == "legacy_readonly_alias"
    assert payload["selected_env_contract"]["selected_api_key_env_name"] == "BINANCE_API_KEY"
    assert payload["selected_env_contract"]["selected_api_secret_env_name"] == "BINANCE_API_SECRET"


def test_generic_alias_without_readonly_marker_is_blocked() -> None:
    payload = build_binance_account_read_env_discovery(
        env={
            "BINANCE_FUTURES_API_KEY": "trading-looking-key",
            "BINANCE_FUTURES_API_SECRET": "trading-looking-secret",
        },
        include_systemd=False,
    )

    assert payload["status"] == ACCOUNT_READ_ENV_ALIAS_PRESENT_BUT_NOT_MARKED_READ_ONLY
    assert "account_read_env_alias_present_but_not_marked_read_only" in payload["readiness_blockers"]
    assert payload["selected_env_contract"]["runtime_safety_ok"] is False


def test_missing_secret_is_partial_and_redacted() -> None:
    payload = build_binance_account_read_env_discovery(
        env={"BINANCE_API_KEY": "partial-key"},
        include_systemd=False,
    )

    rendered = format_binance_account_read_env_discovery_json(payload)
    assert payload["status"] == ACCOUNT_READ_ENV_PARTIAL
    assert "partial-key" not in rendered
    assert payload["discovered_alias_candidates"][-1]["api_key_present"] is True
    assert payload["discovered_alias_candidates"][-1]["api_secret_present"] is False


def test_missing_all_env_is_missing() -> None:
    payload = build_binance_account_read_env_discovery(env={}, include_systemd=False)

    assert payload["status"] == ACCOUNT_READ_ENV_MISSING
    assert "account_read_env_missing" in payload["readiness_blockers"]


def test_adapter_uses_selected_alias_contract_for_private_readonly_calls() -> None:
    fake = _PrivateFakeUrlOpen(available_balance="20", wallet_balance="22", position_amt="0", notional="0")

    payload = build_account_position_readiness(
        fetch_requested=True,
        confirmation_valid=True,
        env={
            **SAFE_FLAGS,
            "BINANCE_API_KEY": "legacy-key-value",
            "BINANCE_API_SECRET": "legacy-secret-value",
        },
        urlopen_func=fake,
    )

    rendered = json.dumps(payload)
    assert [request.get_method() for request in fake.calls] == ["GET", "GET"]
    assert payload["preflight"]["account_read_env_discovery_status"] == ACCOUNT_READ_ENV_READY
    assert payload["preflight"]["selected_env_contract"]["selected_api_key_env_name"] == "BINANCE_API_KEY"
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["binance_test_order_endpoint_called"] is False
    assert payload["safety"]["leverage_change_called"] is False
    assert payload["safety"]["margin_change_called"] is False
    assert "legacy-key-value" not in rendered
    assert "legacy-secret-value" not in rendered


def test_endpoint_discovery_does_not_hit_binance_network() -> None:
    with patch.object(urllib.request, "urlopen") as urlopen:
        response = TestClient(app).get("/tiny-live/binance-account-read-env-discovery")

    urlopen.assert_not_called()
    payload = response.json()
    assert response.status_code == 200
    assert payload["event_type"] == "BINANCE_ACCOUNT_READ_ENV_DISCOVERY"
    assert payload["safety"]["network_allowed"] is False
    assert payload["safety"]["secrets_shown"] is False


def test_cli_discovery_hides_secret_values_and_does_not_require_network(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path),
            "tiny-live-binance-account-read-env-discovery",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={
            **os.environ,
            "PYTHONPATH": ".",
            **SAFE_FLAGS,
            "BINANCE_API_KEY": "cli-secret-key-value",
            "BINANCE_API_SECRET": "cli-secret-value",
        },
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == ACCOUNT_READ_ENV_READY
    assert payload["safety"]["network_allowed"] is False
    assert "cli-secret-key-value" not in result.stdout
    assert "cli-secret-value" not in result.stdout


def test_runtime_env_loader_rejects_non_allowlisted_path(tmp_path: Path, monkeypatch) -> None:
    safe_dir = tmp_path / "hammer-radar"
    monkeypatch.setattr(env_contract, "HAMMER_RADAR_CONFIG_DIR", safe_dir)
    monkeypatch.setattr(env_contract, "KNOWN_SAFE_READONLY_ENV_FILE", safe_dir / "binance-readonly.env")
    outside = tmp_path / "other.env"
    outside.write_text("BINANCE_CONNECTOR_MODE=read_only\nBINANCE_LIVE_TRADING_ENABLED=false\n", encoding="utf-8")

    payload = load_allowed_readonly_env_file(outside)

    assert payload["loaded_env_file_status"] == "ENV_FILE_PATH_OUTSIDE_ALLOWLIST_DIR"
    assert payload["loaded_env_names"] == []
    assert payload["env_file_values_printed"] is False
    assert payload["env_written"] is False
    assert payload["env_mutated"] is False


def test_runtime_env_loader_rejects_traversal_path(tmp_path: Path, monkeypatch) -> None:
    safe_dir = tmp_path / "hammer-radar"
    safe_dir.mkdir()
    monkeypatch.setattr(env_contract, "HAMMER_RADAR_CONFIG_DIR", safe_dir)
    monkeypatch.setattr(env_contract, "KNOWN_SAFE_READONLY_ENV_FILE", safe_dir / "binance-readonly.env")
    traversal = safe_dir / ".." / "outside.env"
    traversal.write_text("BINANCE_CONNECTOR_MODE=read_only\nBINANCE_LIVE_TRADING_ENABLED=false\n", encoding="utf-8")

    payload = load_allowed_readonly_env_file(traversal)

    assert payload["loaded_env_file_status"] == "ENV_FILE_PATH_OUTSIDE_ALLOWLIST_DIR"
    assert payload["loaded_env_names"] == []


def test_runtime_env_loader_loads_only_allowlisted_keys_and_redacts(tmp_path: Path, monkeypatch) -> None:
    safe_dir = tmp_path / "hammer-radar"
    safe_dir.mkdir()
    env_file = safe_dir / "binance-readonly.env"
    monkeypatch.setattr(env_contract, "HAMMER_RADAR_CONFIG_DIR", safe_dir)
    monkeypatch.setattr(env_contract, "KNOWN_SAFE_READONLY_ENV_FILE", env_file)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    monkeypatch.delenv("UNRELATED_SECRET", raising=False)
    env_file.write_text(
        "\n".join(
            [
                "BINANCE_API_KEY=loader-key-value",
                "BINANCE_API_SECRET=loader-secret-value",
                "BINANCE_CONNECTOR_MODE=read_only",
                "BINANCE_LIVE_TRADING_ENABLED=false",
                "UNRELATED_SECRET=must-not-load",
            ]
        ),
        encoding="utf-8",
    )
    before = env_file.read_text(encoding="utf-8")

    payload = load_allowed_readonly_env_file(env_file)
    rendered = json.dumps(payload)

    assert payload["loaded_env_file_status"] == "LOADED"
    assert payload["loaded_env_names"] == [
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "BINANCE_CONNECTOR_MODE",
        "BINANCE_LIVE_TRADING_ENABLED",
    ]
    assert payload["ignored_env_names"] == ["UNRELATED_SECRET"]
    assert os.environ["BINANCE_API_KEY"] == "loader-key-value"
    assert os.environ["BINANCE_API_SECRET"] == "loader-secret-value"
    assert "UNRELATED_SECRET" not in os.environ
    assert env_file.read_text(encoding="utf-8") == before
    assert "loader-key-value" not in rendered
    assert "loader-secret-value" not in rendered
    assert payload["loaded_secret_names_redacted"] is True
    assert payload["env_file_values_printed"] is False
    assert payload["env_file_modified"] is False


def test_runtime_env_loader_blocks_non_readonly_mode(tmp_path: Path, monkeypatch) -> None:
    safe_dir = tmp_path / "hammer-radar"
    safe_dir.mkdir()
    env_file = safe_dir / "binance-readonly.env"
    monkeypatch.setattr(env_contract, "HAMMER_RADAR_CONFIG_DIR", safe_dir)
    monkeypatch.setattr(env_contract, "KNOWN_SAFE_READONLY_ENV_FILE", env_file)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    env_file.write_text(
        "BINANCE_API_KEY=key\nBINANCE_API_SECRET=secret\nBINANCE_CONNECTOR_MODE=trading\nBINANCE_LIVE_TRADING_ENABLED=false\n",
        encoding="utf-8",
    )

    payload = load_allowed_readonly_env_file(env_file)

    assert payload["loaded_env_file_status"] == "BLOCKED_UNSAFE_ENV_VALUES"
    assert "connector_mode_not_read_only" in payload["blockers"]
    assert "BINANCE_API_KEY" not in os.environ


def test_runtime_env_loader_blocks_live_trading_true(tmp_path: Path, monkeypatch) -> None:
    safe_dir = tmp_path / "hammer-radar"
    safe_dir.mkdir()
    env_file = safe_dir / "binance-readonly.env"
    monkeypatch.setattr(env_contract, "HAMMER_RADAR_CONFIG_DIR", safe_dir)
    monkeypatch.setattr(env_contract, "KNOWN_SAFE_READONLY_ENV_FILE", env_file)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    env_file.write_text(
        "BINANCE_API_KEY=key\nBINANCE_API_SECRET=secret\nBINANCE_CONNECTOR_MODE=read_only\nBINANCE_LIVE_TRADING_ENABLED=true\n",
        encoding="utf-8",
    )

    payload = load_allowed_readonly_env_file(env_file)

    assert payload["loaded_env_file_status"] == "BLOCKED_UNSAFE_ENV_VALUES"
    assert "live_trading_flag_not_false" in payload["blockers"]
    assert "BINANCE_API_KEY" not in os.environ


def test_discovery_with_runtime_loader_reports_ready_names_only(tmp_path: Path, monkeypatch) -> None:
    safe_dir = tmp_path / "hammer-radar"
    safe_dir.mkdir()
    env_file = safe_dir / "binance-readonly.env"
    monkeypatch.setattr(env_contract, "HAMMER_RADAR_CONFIG_DIR", safe_dir)
    monkeypatch.setattr(env_contract, "KNOWN_SAFE_READONLY_ENV_FILE", env_file)
    for name in ["BINANCE_API_KEY", "BINANCE_API_SECRET", "BINANCE_CONNECTOR_MODE", "BINANCE_LIVE_TRADING_ENABLED"]:
        monkeypatch.delenv(name, raising=False)
    env_file.write_text(
        "BINANCE_API_KEY=discovery-key\nBINANCE_API_SECRET=discovery-secret\nBINANCE_CONNECTOR_MODE=read_only\nBINANCE_LIVE_TRADING_ENABLED=false\n",
        encoding="utf-8",
    )

    payload = build_binance_account_read_env_discovery(
        include_systemd=False,
        load_discovered_binance_readonly_env=True,
        binance_readonly_env_file=env_file,
    )
    names = parse_env_file_names_only(env_file)
    rendered = format_binance_account_read_env_discovery_json(payload)

    assert payload["status"] == ACCOUNT_READ_ENV_READY
    assert payload["cli_runtime_env_loader_supported"] is True
    assert payload["loaded_env_file_status"] == "LOADED"
    assert payload["loaded_env_names"] == [
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "BINANCE_CONNECTOR_MODE",
        "BINANCE_LIVE_TRADING_ENABLED",
    ]
    assert names["names"] == payload["loaded_env_names"]
    assert payload["loaded_secret_names_redacted"] is True
    assert payload["env_file_values_printed"] is False
    assert "discovery-key" not in rendered
    assert "discovery-secret" not in rendered
