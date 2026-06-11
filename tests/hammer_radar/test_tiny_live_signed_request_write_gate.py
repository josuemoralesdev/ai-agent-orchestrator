from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_executable_payload_write_gate import (
    CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_PHRASE,
    build_tiny_live_executable_payload_write_gate,
)
from src.app.hammer_radar.operator.tiny_live_signature_gate_preview import (
    CONFIRM_TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDING_PHRASE,
    build_tiny_live_signature_gate_preview,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_write_gate import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
    CONFIRM_TINY_LIVE_SIGNED_REQUEST_WRITE_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_BLOCKED,
    TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_READY,
    TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_REJECTED,
    TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_WRITTEN,
    build_tiny_live_signed_request_write_gate,
    load_tiny_live_signed_request_write_gate_records,
    validate_signed_request_artifact,
)
from tests.hammer_radar.test_tiny_live_executable_payload_write_gate import _fixture_r249

NOW = datetime(2026, 6, 11, 10, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
API_KEY = "TESTKEY1234567890"
API_SECRET = "TESTSECRET1234567890"


def test_cli_command_exists_and_returns_json(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r251(tmp_path)
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-signed-request-write-gate",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={
            key: value
            for key, value in {**os.environ, "PYTHONPATH": "."}.items()
            if key not in {BINANCE_API_KEY_ENV, BINANCE_API_SECRET_ENV}
        },
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["signed_request_written"] is False


def test_preview_writes_no_ledger_and_does_not_load_secrets(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r251(tmp_path)
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)

    with patch(
        "src.app.hammer_radar.operator.tiny_live_signed_request_write_gate.load_signing_credentials_for_confirmed_write"
    ) as load_credentials:
        payload = build_tiny_live_signed_request_write_gate(log_dir=log_dir, now=NOW)

    load_credentials.assert_not_called()
    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_READY
    assert payload["write_signed_request_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["signed_request_written"] is False
    assert payload["credential_presence_preview"]["api_key_present"] is True
    assert payload["credential_presence_preview"]["api_secret_present"] is True
    assert payload["credential_presence_preview"]["api_key_loaded"] is False
    assert payload["credential_presence_preview"]["api_secret_loaded"] is False
    assert payload["credential_presence_preview"]["secrets_read"] is False
    assert payload["credential_presence_preview"]["secrets_shown"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()
    assert API_KEY not in json.dumps(payload)
    assert API_SECRET not in json.dumps(payload)


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r251(tmp_path)
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)

    payload = build_tiny_live_signed_request_write_gate(
        log_dir=log_dir,
        write_signed_request=True,
        confirm_tiny_live_signed_request_write="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["signed_request_written"] is False
    assert payload["signed_request_write_overall_status"] == (
        "TINY_LIVE_SIGNED_REQUEST_WRITE_REJECTED_BAD_CONFIRMATION"
    )
    assert load_tiny_live_signed_request_write_gate_records(log_dir=log_dir, limit=0) == []
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_missing_credentials_blocks_write(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r251(tmp_path)
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)

    payload = build_tiny_live_signed_request_write_gate(
        log_dir=log_dir,
        write_signed_request=True,
        confirm_tiny_live_signed_request_write=CONFIRM_TINY_LIVE_SIGNED_REQUEST_WRITE_PHRASE,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_BLOCKED
    assert payload["signed_request_write_overall_status"] == (
        "TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_MISSING_SIGNING_CREDENTIALS"
    )
    assert payload["credential_presence_preview"]["api_key_present"] is False
    assert payload["credential_presence_preview"]["api_secret_present"] is False
    assert payload["signed_request_written"] is False
    assert load_tiny_live_signed_request_write_gate_records(log_dir=log_dir, limit=0) == []


def test_exact_confirmation_with_credentials_writes_local_signed_request_artifact_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_r251(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")
    before_env_file = env_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_signed_request_write_gate(
            log_dir=log_dir,
            write_signed_request=True,
            confirm_tiny_live_signed_request_write=CONFIRM_TINY_LIVE_SIGNED_REQUEST_WRITE_PHRASE,
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert env_path.read_text(encoding="utf-8") == before_env_file

    records = load_tiny_live_signed_request_write_gate_records(log_dir=log_dir, limit=0)
    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_WRITTEN
    assert payload["confirmation_valid"] is True
    assert payload["signed_request_written"] is True
    assert len(records) == 1
    artifact = records[0]["signed_request_artifact"]
    assert validate_signed_request_artifact(
        artifact,
        raw_api_key=API_KEY,
        raw_api_secret=API_SECRET,
    )["valid"] is True
    assert artifact["official_lane_key"] == OFFICIAL
    assert artifact["artifact_only"] is True
    assert artifact["credential_context"]["api_key_hint"] == "TEST...7890"
    assert artifact["credential_context"]["api_secret_persisted"] is False
    assert set(artifact["signed_requests"]) == {"main_order", "stop_order", "take_profit_order"}
    for request in artifact["signed_requests"].values():
        assert request["method"] == "POST"
        assert request["endpoint"] == "/fapi/v1/order"
        assert request["signed"] is True
        assert re.fullmatch(r"[0-9a-f]{64}", request["signature"])
        assert API_SECRET not in request["query_string_without_signature"]
        assert API_KEY not in request["query_string_without_signature"]
        assert request["submit_allowed"] is False
        assert request["network_allowed"] is False
    artifact_text = json.dumps(artifact, sort_keys=True)
    assert API_SECRET not in artifact_text
    assert API_KEY not in artifact_text
    assert artifact["controls"]["submit_allowed"] is False
    assert artifact["controls"]["binance_call_allowed"] is False
    assert artifact["controls"]["network_allowed"] is False
    assert artifact["safety"]["order_placed"] is False
    assert artifact["safety"]["binance_order_endpoint_called"] is False
    assert payload["post_write_verification"]["matching_signed_request_found"] is True
    assert payload["post_write_verification"]["matching_signed_request_valid"] is True
    assert payload["post_write_verification"]["submit_allowed"] is False
    assert payload["post_write_verification"]["order_placed"] is False
    assert payload["post_write_verification"]["binance_call_allowed"] is False
    assert payload["post_write_verification"]["network_allowed"] is False
    assert payload["signed_request_write_gate_matrix"]["signed_request_written"] is True
    assert payload["signed_request_write_gate_matrix"]["order_ready"] is False
    assert payload["operator_signed_request_write_packet"]["operator_should_submit_now"] is False
    assert payload["operator_signed_request_write_packet"]["operator_should_place_order"] is False
    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "risk_contract_config_written",
        "lane_controls_written",
        "live_config_written",
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
        "kill_switch_disabled",
        "secrets_shown",
        "secrets_persisted",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["paper_live_separation_intact"] is True


def test_r250_blocker_if_signature_preview_missing(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r251(tmp_path)
    (log_dir / "tiny_live_signature_gate_preview.ndjson").unlink()

    payload = build_tiny_live_signed_request_write_gate(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_BLOCKED
    assert payload["input_summary"]["r250_signature_preview_found"] is False
    assert payload["signed_request_write_overall_status"] == "TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_R250"


def test_r249_blocker_if_executable_payload_missing(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r251(tmp_path)
    (log_dir / "tiny_live_executable_payload_write_gate.ndjson").unlink()

    payload = build_tiny_live_signed_request_write_gate(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_BLOCKED
    assert payload["input_summary"]["r249_executable_payload_found"] is False
    assert payload["signed_request_write_overall_status"] == "TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_R249"


def _fixture_r251(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_r249(tmp_path)
    r249 = build_tiny_live_executable_payload_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        write_executable_payload=True,
        confirm_tiny_live_executable_payload_write=CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_PHRASE,
        now=NOW,
    )
    assert r249["executable_payload_written"] is True
    r250 = build_tiny_live_signature_gate_preview(
        log_dir=log_dir,
        record_signature_gate_preview=True,
        confirm_tiny_live_signature_gate_preview=CONFIRM_TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDING_PHRASE,
        now=NOW,
    )
    assert r250["signature_gate_preview_recorded"] is True
    return log_dir, risk_path, lane_path
