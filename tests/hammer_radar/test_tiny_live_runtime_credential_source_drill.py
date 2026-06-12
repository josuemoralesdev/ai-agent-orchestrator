from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_runtime_credential_source_drill import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
    CONFIRM_TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_PHRASE,
    LEDGER_FILENAME,
    OVERRIDE_ENV_NAME,
    TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_BLOCKED,
    TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_READY,
    TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_RECORDED,
    TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_REJECTED,
    build_tiny_live_runtime_credential_source_drill,
    detect_external_env_file_credential_presence,
    load_tiny_live_runtime_credential_source_drill_records,
)

NOW = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
API_KEY = "R251D_TEST_API_KEY_SHOULD_NOT_APPEAR"
API_SECRET = "R251D_TEST_API_SECRET_SHOULD_NOT_APPEAR"


def test_cli_exists_and_returns_json(tmp_path: Path) -> None:
    missing_external = tmp_path / "missing.env"

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "tiny-live-runtime-credential-source-drill",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=_clean_env({OVERRIDE_ENV_NAME: str(missing_external)}),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["runtime_credential_source_drill_recorded"] is False
    assert payload["process_env_presence"]["credentials_present"] is False
    assert payload["external_env_file_source"]["file_exists"] is False
    assert payload["safety"]["network_allowed"] is False


def test_preview_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    external = _write_external_env(tmp_path, mode=0o600)
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)

    payload = build_tiny_live_runtime_credential_source_drill(log_dir=tmp_path / "logs", now=NOW)

    assert payload["status"] == TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_READY
    assert payload["record_runtime_credential_source_drill_requested"] is False
    assert payload["runtime_credential_source_drill_recorded"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()
    _assert_no_secret_values(payload)


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    external = _write_external_env(tmp_path, mode=0o600)
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)

    payload = build_tiny_live_runtime_credential_source_drill(
        log_dir=tmp_path / "logs",
        record_runtime_credential_source_drill=True,
        confirm_tiny_live_runtime_credential_source_drill="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["runtime_credential_source_drill_recorded"] is False
    assert payload["runtime_credential_source_overall_status"] == (
        "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_REJECTED_BAD_CONFIRMATION"
    )
    assert load_tiny_live_runtime_credential_source_drill_records(
        log_dir=tmp_path / "logs", limit=0
    ) == []
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()
    _assert_no_secret_values(payload)


def test_correct_confirmation_records_presence_only_ledger(tmp_path: Path, monkeypatch) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    external = _write_external_env(tmp_path, mode=0o600)
    before_external = external.read_text(encoding="utf-8")
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)
    env_path = tmp_path / ".env"
    risk_path = tmp_path / "configs" / "hammer_radar" / "tiny_live_risk_contracts.json"
    lane_path = tmp_path / "configs" / "hammer_radar" / "lane_controls.json"
    risk_path.parent.mkdir(parents=True)
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    risk_path.write_text('{"unchanged":true}\n', encoding="utf-8")
    lane_path.write_text('{"unchanged":true}\n', encoding="utf-8")
    before_env = env_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_runtime_credential_source_drill(
            log_dir=tmp_path / "logs",
            record_runtime_credential_source_drill=True,
            confirm_tiny_live_runtime_credential_source_drill=(
                CONFIRM_TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_PHRASE
            ),
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert external.read_text(encoding="utf-8") == before_external
    assert env_path.read_text(encoding="utf-8") == before_env
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane

    records = load_tiny_live_runtime_credential_source_drill_records(
        log_dir=tmp_path / "logs", limit=0
    )
    assert payload["status"] == TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_RECORDED
    assert payload["runtime_credential_source_drill_recorded"] is True
    assert payload["runtime_credential_source_overall_status"] == (
        "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_RECORDED"
    )
    assert len(records) == 1
    assert records[0]["runtime_credential_source_drill_recorded"] is True
    assert records[0]["process_env_presence"]["api_key_hint"] == "<PRESENT_REDACTED>"
    assert records[0]["external_env_file_source"]["api_secret_hint"] == "<PRESENT_REDACTED>"
    raw_ledger = (tmp_path / "logs" / LEDGER_FILENAME).read_text(encoding="utf-8")
    assert API_KEY not in raw_ledger
    assert API_SECRET not in raw_ledger


def test_process_env_credentials_present_case(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(tmp_path / "missing.env"))
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)

    payload = build_tiny_live_runtime_credential_source_drill(log_dir=tmp_path / "logs", now=NOW)

    assert payload["process_env_presence"]["api_key_present"] is True
    assert payload["process_env_presence"]["api_secret_present"] is True
    assert payload["process_env_presence"]["credentials_present"] is True
    assert payload["process_env_presence"]["api_key_hint"] == "<PRESENT_REDACTED>"
    assert payload["process_env_presence"]["api_secret_hint"] == "<PRESENT_REDACTED>"
    assert payload["runtime_credential_source_summary"]["preferred_future_source"] == "process_env"
    _assert_no_secret_values(payload)


def test_process_env_credentials_missing_case(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(tmp_path / "missing.env"))
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)

    payload = build_tiny_live_runtime_credential_source_drill(log_dir=tmp_path / "logs", now=NOW)

    assert payload["process_env_presence"]["api_key_present"] is False
    assert payload["process_env_presence"]["api_secret_present"] is False
    assert payload["runtime_credential_source_summary"]["credentials_available_for_future_signing"] is False
    assert payload["operator_runtime_credential_source_packet"]["next_required_human_action"] == (
        "CREATE_EXTERNAL_CREDENTIAL_FILE"
    )


def test_external_env_file_present_case_using_tmp_path(tmp_path: Path, monkeypatch) -> None:
    external = _write_external_env(tmp_path, mode=0o600)
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)

    payload = build_tiny_live_runtime_credential_source_drill(log_dir=tmp_path / "logs", now=NOW)

    source = payload["external_env_file_source"]
    assert source["file_exists"] is True
    assert source["path_inside_repo"] is False
    assert source["file_mode"] == "0600"
    assert source["permission_ok"] is True
    assert source["credentials_present"] is True
    assert source["api_key_hint"] == "<PRESENT_REDACTED>"
    assert payload["runtime_credential_source_summary"]["preferred_future_source"] == (
        "external_env_file"
    )
    _assert_no_secret_values(payload)


def test_external_env_file_missing_case(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "missing.env"
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(missing))
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)

    payload = build_tiny_live_runtime_credential_source_drill(log_dir=tmp_path / "logs", now=NOW)

    source = payload["external_env_file_source"]
    assert source["file_exists"] is False
    assert "external_env_file_missing" in source["errors"]
    assert payload["runtime_credential_source_overall_status"] == (
        "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_MISSING_CREATE_EXTERNAL_FILE"
    )


def test_external_env_file_inside_repo_blocks_or_errors(tmp_path: Path, monkeypatch) -> None:
    repo_file = Path(__file__).resolve()
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(repo_file))
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)

    payload = build_tiny_live_runtime_credential_source_drill(log_dir=tmp_path / "logs", now=NOW)

    assert payload["status"] == TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_BLOCKED
    assert payload["external_env_file_source"]["path_inside_repo"] is True
    assert "external_env_file_path_inside_repo" in payload["external_env_file_source"]["errors"]
    assert "external_env_file_path_inside_repo" in (
        payload["runtime_credential_source_gate_matrix"]["blocked_by"]
    )


def test_external_env_file_permission_warning_blocker_works(tmp_path: Path, monkeypatch) -> None:
    external = _write_external_env(tmp_path, mode=0o644)
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)

    payload = build_tiny_live_runtime_credential_source_drill(log_dir=tmp_path / "logs", now=NOW)

    assert payload["external_env_file_source"]["credentials_present"] is True
    assert payload["external_env_file_source"]["permission_ok"] is False
    assert "external_env_file_group_or_world_accessible" in (
        payload["external_env_file_source"]["warnings"]
    )
    assert "external_env_file_permissions_too_open" in (
        payload["runtime_credential_source_gate_matrix"]["blocked_by"]
    )
    assert payload["runtime_credential_source_overall_status"] == (
        "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_PRESENT_BUT_PERMISSION_WARNING"
    )


def test_monkeypatched_credentials_are_not_printed_or_persisted(tmp_path: Path, monkeypatch) -> None:
    external = _write_external_env(tmp_path, mode=0o600)
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)

    payload = build_tiny_live_runtime_credential_source_drill(log_dir=tmp_path / "logs", now=NOW)
    raw_output = json.dumps(payload, sort_keys=True)

    assert API_KEY not in raw_output
    assert API_SECRET not in raw_output
    assert payload["process_env_presence"]["secrets_shown"] is False
    assert payload["process_env_presence"]["secrets_persisted"] is False
    assert payload["external_env_file_source"]["secrets_shown"] is False
    assert payload["external_env_file_source"]["secrets_persisted"] is False
    assert payload["safety"]["secret_values_in_output"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_safety_flags_are_non_executing_and_no_mutation(tmp_path: Path, monkeypatch) -> None:
    external = _write_external_env(tmp_path, mode=0o600)
    before_external = external.read_text(encoding="utf-8")
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)

    payload = build_tiny_live_runtime_credential_source_drill(log_dir=tmp_path / "logs", now=NOW)
    safety = payload["safety"]

    for key in (
        "env_written",
        "env_mutated",
        "external_env_file_written",
        "config_written",
        "risk_contract_config_written",
        "lane_controls_written",
        "live_config_written",
        "signing_attempted",
        "hmac_signature_created",
        "signed_request_written",
        "signed_order_request_created",
        "signed_trading_request_created",
        "submit_allowed",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "binance_account_endpoint_called",
        "binance_exchange_info_endpoint_called",
        "binance_mark_price_endpoint_called",
        "network_allowed",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "kill_switch_disabled",
        "secrets_shown",
        "secrets_persisted",
        "secret_values_in_output",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert safety[key] is False
    assert safety["runtime_credential_source_drill_only"] is True
    assert safety["paper_live_separation_intact"] is True
    assert payload["target_scope"]["signing_attempted"] is False
    assert payload["target_scope"]["hmac_signature_created"] is False
    assert payload["target_scope"]["signed_request_written"] is False
    assert payload["target_scope"]["order_placed"] is False
    assert payload["target_scope"]["binance_call_allowed"] is False
    assert payload["target_scope"]["network_allowed"] is False
    assert external.read_text(encoding="utf-8") == before_external


def test_detect_external_env_file_does_not_return_internal_secret_values(tmp_path: Path) -> None:
    external = _write_external_env(tmp_path, mode=0o600)

    source = detect_external_env_file_credential_presence(
        env={OVERRIDE_ENV_NAME: str(external)}
    )

    assert "_secret_values_for_validation" not in source
    assert API_KEY not in json.dumps(source, sort_keys=True)
    assert API_SECRET not in json.dumps(source, sort_keys=True)


def _write_external_env(tmp_path: Path, *, mode: int) -> Path:
    external = tmp_path / "binance-signing.env"
    external.write_text(
        f"{BINANCE_API_KEY_ENV}={API_KEY}\n{BINANCE_API_SECRET_ENV}={API_SECRET}\n",
        encoding="utf-8",
    )
    os.chmod(external, mode)
    return external


def _clean_env(extra: dict[str, str]) -> dict[str, str]:
    env = {**os.environ, "PYTHONPATH": ".", **extra}
    env.pop(BINANCE_API_KEY_ENV, None)
    env.pop(BINANCE_API_SECRET_ENV, None)
    return env


def _assert_no_secret_values(payload: dict) -> None:
    raw_output = json.dumps(payload, sort_keys=True)
    assert API_KEY not in raw_output
    assert API_SECRET not in raw_output
