from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_signed_request_with_credentials_drill import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
    CONFIRM_TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_PHRASE,
    LEDGER_FILENAME as R251C_LEDGER_FILENAME,
    TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_DRILL_BLOCKED,
    TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_DRILL_READY,
    TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_DRILL_REJECTED,
    TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_DRILL_WRITTEN,
    build_tiny_live_signed_request_with_credentials_drill,
    load_tiny_live_signed_request_with_credentials_drill_records,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_write_gate import (
    LEDGER_FILENAME as R251_LEDGER_FILENAME,
    load_tiny_live_signed_request_write_gate_records,
    validate_signed_request_artifact,
)
from src.app.hammer_radar.operator.tiny_live_signing_credential_presence_drill import (
    CONFIRM_TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_PHRASE,
    build_tiny_live_signing_credential_presence_drill,
)
from tests.hammer_radar.test_tiny_live_signed_request_write_gate import _fixture_r251

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
API_KEY = "R251C_TEST_API_KEY_SHOULD_NOT_APPEAR_1234567890"
API_SECRET = "R251C_TEST_API_SECRET_SHOULD_NOT_APPEAR_1234567890"


def test_cli_exists_and_returns_json(tmp_path: Path, monkeypatch) -> None:
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
            "tiny-live-signed-request-with-credentials-drill",
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
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["signed_request_written"] is False
    assert payload["safety"]["network_allowed"] is False


def test_preview_writes_no_ledger_and_does_not_sign(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r251c(tmp_path, monkeypatch)

    with patch(
        "src.app.hammer_radar.operator.tiny_live_signed_request_with_credentials_drill.invoke_r251_signed_request_artifact_write"
    ) as invoke_r251:
        payload = build_tiny_live_signed_request_with_credentials_drill(log_dir=log_dir, now=NOW)

    invoke_r251.assert_not_called()
    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_DRILL_READY
    assert payload["write_signed_request_with_credentials_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["signed_request_written"] is False
    assert payload["credential_context"]["r251b_credentials_present"] is True
    assert payload["credential_context"]["env_api_key_present"] is True
    assert payload["credential_context"]["env_api_secret_present"] is True
    assert payload["safety"]["hmac_signature_created"] is False
    assert not (log_dir / R251_LEDGER_FILENAME).exists()
    assert not (log_dir / R251C_LEDGER_FILENAME).exists()
    raw_output = json.dumps(payload, sort_keys=True)
    assert API_KEY not in raw_output
    assert API_SECRET not in raw_output


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r251c(tmp_path, monkeypatch)

    payload = build_tiny_live_signed_request_with_credentials_drill(
        log_dir=log_dir,
        write_signed_request_with_credentials=True,
        confirm_tiny_live_signed_request_with_credentials="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_DRILL_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["signed_request_written"] is False
    assert payload["r251c_overall_status"] == (
        "TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_REJECTED_BAD_CONFIRMATION"
    )
    assert not (log_dir / R251_LEDGER_FILENAME).exists()
    assert not (log_dir / R251C_LEDGER_FILENAME).exists()


def test_missing_env_credentials_blocks(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r251c(tmp_path, monkeypatch)
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)

    payload = build_tiny_live_signed_request_with_credentials_drill(
        log_dir=log_dir,
        write_signed_request_with_credentials=True,
        confirm_tiny_live_signed_request_with_credentials=(
            CONFIRM_TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_PHRASE
        ),
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_DRILL_BLOCKED
    assert payload["r251c_overall_status"] == (
        "TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_BLOCKED_BY_ENV_CREDENTIALS"
    )
    assert payload["credential_context"]["r251b_credentials_present"] is True
    assert payload["credential_context"]["env_api_key_present"] is False
    assert payload["credential_context"]["env_api_secret_present"] is False
    assert payload["signed_request_written"] is False
    assert not (log_dir / R251_LEDGER_FILENAME).exists()
    assert not (log_dir / R251C_LEDGER_FILENAME).exists()


def test_missing_r251b_presence_blocks(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r251(tmp_path)
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)

    payload = build_tiny_live_signed_request_with_credentials_drill(
        log_dir=log_dir,
        write_signed_request_with_credentials=True,
        confirm_tiny_live_signed_request_with_credentials=(
            CONFIRM_TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_PHRASE
        ),
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_DRILL_BLOCKED
    assert payload["r251c_overall_status"] == (
        "TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_BLOCKED_BY_R251B"
    )
    assert payload["credential_context"]["r251b_credentials_present"] is False
    assert payload["credential_context"]["env_api_key_present"] is True
    assert payload["credential_context"]["env_api_secret_present"] is True
    assert payload["signed_request_written"] is False
    assert not (log_dir / R251_LEDGER_FILENAME).exists()
    assert not (log_dir / R251C_LEDGER_FILENAME).exists()


def test_exact_confirmation_with_credentials_writes_signed_request_artifact_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_r251c(tmp_path, monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    before_env = dict(os.environ)
    before_env_file = env_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_signed_request_with_credentials_drill(
            log_dir=log_dir,
            write_signed_request_with_credentials=True,
            confirm_tiny_live_signed_request_with_credentials=(
                CONFIRM_TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_PHRASE
            ),
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert dict(os.environ) == before_env
    assert env_path.read_text(encoding="utf-8") == before_env_file
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane

    assert payload["status"] == TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_DRILL_WRITTEN
    assert payload["confirmation_valid"] is True
    assert payload["signed_request_written"] is True
    assert payload["r251c_overall_status"] == (
        "TINY_LIVE_SIGNED_REQUEST_WITH_CREDENTIALS_WRITTEN_SUBMIT_READINESS_REQUIRED"
    )
    assert payload["signed_request_artifact_summary"]["signed_requests_count"] == 3
    assert payload["signed_request_artifact_summary"]["main_order_signature_present"] is True
    assert payload["signed_request_artifact_summary"]["stop_order_signature_present"] is True
    assert payload["signed_request_artifact_summary"]["take_profit_order_signature_present"] is True
    assert payload["signed_request_artifact_summary"]["submit_allowed"] is False
    assert payload["signed_request_artifact_summary"]["order_placed"] is False
    assert payload["signed_request_artifact_summary"]["binance_call_allowed"] is False
    assert payload["signed_request_artifact_summary"]["network_allowed"] is False
    assert payload["secret_validation"]["valid"] is True
    assert payload["secret_validation"]["raw_api_key_found_in_artifacts"] is False
    assert payload["secret_validation"]["raw_api_secret_found_in_artifacts"] is False
    assert payload["secret_validation"]["secret_values_in_output"] is False
    assert payload["post_write_verification"]["matching_signed_request_found"] is True
    assert payload["post_write_verification"]["matching_signed_request_valid"] is True
    assert payload["post_write_verification"]["submit_allowed"] is False
    assert payload["post_write_verification"]["order_placed"] is False
    assert payload["post_write_verification"]["binance_call_allowed"] is False
    assert payload["post_write_verification"]["network_allowed"] is False
    assert payload["r251c_gate_matrix"]["r251b_credentials_present"] is True
    assert payload["r251c_gate_matrix"]["env_credentials_present"] is True
    assert payload["r251c_gate_matrix"]["signed_request_written"] is True
    assert payload["r251c_gate_matrix"]["secret_validation_passed"] is True
    assert payload["r251c_gate_matrix"]["submit_gate_required"] is True
    assert payload["r251c_gate_matrix"]["order_ready"] is False
    assert payload["r251c_gate_matrix"]["live_ready_today"] is False
    assert payload["operator_r251c_packet"]["operator_should_submit_now"] is False
    assert payload["operator_r251c_packet"]["operator_should_place_order"] is False
    assert payload["operator_r251c_packet"]["next_required_human_action"] == "REVIEW_R251C_RESULT"

    r251_records = load_tiny_live_signed_request_write_gate_records(log_dir=log_dir, limit=0)
    r251c_records = load_tiny_live_signed_request_with_credentials_drill_records(
        log_dir=log_dir,
        limit=0,
    )
    assert len(r251_records) == 1
    assert len(r251c_records) == 1
    artifact = r251_records[0]["signed_request_artifact"]
    assert validate_signed_request_artifact(
        artifact,
        raw_api_key=API_KEY,
        raw_api_secret=API_SECRET,
    )["valid"] is True
    assert set(artifact["signed_requests"]) == {"main_order", "stop_order", "take_profit_order"}
    for request in artifact["signed_requests"].values():
        assert re.fullmatch(r"[0-9a-f]{64}", request["signature"])
        assert request["submit_allowed"] is False
        assert request["network_allowed"] is False
    raw_artifacts = "\n".join(
        [
            (log_dir / R251_LEDGER_FILENAME).read_text(encoding="utf-8"),
            (log_dir / R251C_LEDGER_FILENAME).read_text(encoding="utf-8"),
            json.dumps(payload, sort_keys=True),
        ]
    )
    assert API_KEY not in raw_artifacts
    assert API_SECRET not in raw_artifacts

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
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "kill_switch_disabled",
        "secrets_shown",
        "secrets_persisted",
        "secret_values_in_output",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["hmac_signature_created"] is True
    assert payload["safety"]["signed_request_written"] is True
    assert payload["safety"]["signed_order_request_created"] is True
    assert payload["safety"]["signed_trading_request_created"] is True
    assert payload["safety"]["paper_live_separation_intact"] is True


def _fixture_r251c(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_r251(tmp_path)
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)
    r251b = build_tiny_live_signing_credential_presence_drill(
        log_dir=log_dir,
        record_signing_credential_presence_drill=True,
        confirm_tiny_live_signing_credential_presence_drill=(
            CONFIRM_TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_PHRASE
        ),
        now=NOW,
    )
    assert r251b["credential_presence_drill_recorded"] is True
    return log_dir, risk_path, lane_path
