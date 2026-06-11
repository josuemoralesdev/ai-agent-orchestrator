from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_signing_credential_presence_drill import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
    CONFIRM_TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_READY,
    TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_RECORDED,
    TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_REJECTED,
    build_tiny_live_signing_credential_presence_drill,
    load_tiny_live_signing_credential_presence_drill_records,
)

NOW = datetime(2026, 6, 11, 11, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
API_KEY = "R251B_TEST_API_KEY_SHOULD_NOT_APPEAR"
API_SECRET = "R251B_TEST_API_SECRET_SHOULD_NOT_APPEAR"


def test_cli_command_exists_and_returns_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "tiny-live-signing-credential-presence-drill",
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
    assert payload["status"] == TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["credential_presence_drill_recorded"] is False
    assert payload["credential_presence"]["credentials_present"] is False


def test_preview_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)
    log_dir = tmp_path / "logs"

    payload = build_tiny_live_signing_credential_presence_drill(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_READY
    assert payload["record_credential_presence_drill_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["credential_presence_drill_recorded"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()
    assert API_KEY not in json.dumps(payload, sort_keys=True)
    assert API_SECRET not in json.dumps(payload, sort_keys=True)


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)
    log_dir = tmp_path / "logs"

    payload = build_tiny_live_signing_credential_presence_drill(
        log_dir=log_dir,
        record_signing_credential_presence_drill=True,
        confirm_tiny_live_signing_credential_presence_drill="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["credential_presence_drill_recorded"] is False
    assert payload["credential_presence_overall_status"] == (
        "TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_REJECTED_BAD_CONFIRMATION"
    )
    assert load_tiny_live_signing_credential_presence_drill_records(log_dir=log_dir, limit=0) == []
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_correct_confirmation_records_presence_only_ledger(tmp_path: Path, monkeypatch) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)
    log_dir = tmp_path / "logs"
    env_path = tmp_path / ".env"
    risk_path = tmp_path / "configs" / "hammer_radar" / "tiny_live_risk_contracts.json"
    lane_path = tmp_path / "configs" / "hammer_radar" / "lane_controls.json"
    risk_path.parent.mkdir(parents=True)
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    risk_path.write_text('{"unchanged":true}\n', encoding="utf-8")
    lane_path.write_text('{"unchanged":true}\n', encoding="utf-8")
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
        payload = build_tiny_live_signing_credential_presence_drill(
            log_dir=log_dir,
            record_signing_credential_presence_drill=True,
            confirm_tiny_live_signing_credential_presence_drill=(
                CONFIRM_TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_PHRASE
            ),
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert env_path.read_text(encoding="utf-8") == before_env_file
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane

    records = load_tiny_live_signing_credential_presence_drill_records(log_dir=log_dir, limit=0)
    assert payload["status"] == TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_RECORDED
    assert payload["credential_presence_drill_recorded"] is True
    assert payload["confirmation_valid"] is True
    assert len(records) == 1
    assert records[0]["status"] == TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_RECORDED
    assert records[0]["credential_presence_drill_recorded"] is True
    assert records[0]["credential_presence_overall_status"] == (
        "TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_RECORDED"
    )
    assert records[0]["credential_presence_gate_matrix"]["record_confirmed"] is True
    assert records[0]["credential_presence_gate_matrix"]["recorded"] is True
    assert records[0]["credential_presence"]["api_key_hint"] == "<PRESENT_REDACTED>"
    assert records[0]["credential_presence"]["api_secret_hint"] == "<PRESENT_REDACTED>"
    raw_ledger = (log_dir / LEDGER_FILENAME).read_text(encoding="utf-8")
    assert API_KEY not in raw_ledger
    assert API_SECRET not in raw_ledger


def test_no_credentials_case_reports_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)

    payload = build_tiny_live_signing_credential_presence_drill(log_dir=tmp_path / "logs", now=NOW)

    assert payload["credential_presence"]["api_key_present"] is False
    assert payload["credential_presence"]["api_secret_present"] is False
    assert payload["credential_presence"]["credentials_present"] is False
    assert payload["credential_presence"]["api_key_hint"] is None
    assert payload["credential_presence"]["api_secret_hint"] is None
    assert payload["credential_presence_overall_status"] == (
        "TINY_LIVE_SIGNING_CREDENTIALS_MISSING_SET_ENV_THEN_RERUN"
    )
    assert payload["operator_credential_presence_packet"]["next_required_human_action"] == (
        "SET_SIGNING_CREDENTIALS_OUTSIDE_GIT"
    )


def test_monkeypatched_credentials_report_present_without_printing_or_persisting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)

    payload = build_tiny_live_signing_credential_presence_drill(log_dir=tmp_path / "logs", now=NOW)
    raw_output = json.dumps(payload, sort_keys=True)

    assert payload["credential_presence"]["api_key_present"] is True
    assert payload["credential_presence"]["api_secret_present"] is True
    assert payload["credential_presence"]["credentials_present"] is True
    assert payload["credential_presence"]["api_key_hint"] == "<PRESENT_REDACTED>"
    assert payload["credential_presence"]["api_secret_hint"] == "<PRESENT_REDACTED>"
    assert payload["credential_presence"]["api_key_value_shown"] is False
    assert payload["credential_presence"]["api_secret_value_shown"] is False
    assert payload["credential_presence"]["secrets_read_for_signing"] is False
    assert payload["credential_presence"]["secrets_persisted"] is False
    assert payload["credential_presence_overall_status"] == (
        "TINY_LIVE_SIGNING_CREDENTIALS_PRESENT_R251_CAN_BE_RERUN"
    )
    assert API_KEY not in raw_output
    assert API_SECRET not in raw_output
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_safety_flags_and_gate_matrix_are_non_executing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)

    payload = build_tiny_live_signing_credential_presence_drill(log_dir=tmp_path / "logs", now=NOW)
    safety = payload["safety"]
    matrix = payload["credential_presence_gate_matrix"]

    for key in (
        "env_written",
        "env_mutated",
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
    assert safety["credential_presence_drill_only"] is True
    assert safety["paper_live_separation_intact"] is True
    assert matrix["signing_attempted"] is False
    assert matrix["signed_request_written"] is False
    assert matrix["order_ready"] is False
    assert matrix["live_ready_today"] is False
    assert payload["target_scope"]["hmac_signature_created"] is False
    assert payload["target_scope"]["signed_request_written"] is False
    assert payload["target_scope"]["order_placed"] is False
    assert payload["target_scope"]["binance_call_allowed"] is False
    assert payload["target_scope"]["network_allowed"] is False
