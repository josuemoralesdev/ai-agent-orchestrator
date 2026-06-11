from __future__ import annotations

import json
import os
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
    LEDGER_FILENAME,
    TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED,
    TINY_LIVE_SIGNATURE_GATE_PREVIEW_READY,
    TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDED,
    TINY_LIVE_SIGNATURE_GATE_PREVIEW_REJECTED,
    build_tiny_live_signature_gate_preview,
    load_latest_tiny_live_executable_payload_write_gate,
    load_tiny_live_signature_gate_preview_records,
)
from tests.hammer_radar.test_tiny_live_executable_payload_write_gate import _fixture_r249

NOW = datetime(2026, 6, 11, 9, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_cli_command_exists_and_returns_json(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r250(tmp_path)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-signature-gate-preview",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == TINY_LIVE_SIGNATURE_GATE_PREVIEW_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["signature_gate_preview_recorded"] is False


def test_preview_writes_no_ledger(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r250(tmp_path)

    payload = build_tiny_live_signature_gate_preview(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_SIGNATURE_GATE_PREVIEW_READY
    assert payload["record_signature_gate_preview_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["signature_gate_preview_recorded"] is False
    assert payload["input_summary"]["r249_executable_payload_found"] is True
    assert payload["input_summary"]["r249_executable_payload_valid"] is True
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r250(tmp_path)

    payload = build_tiny_live_signature_gate_preview(
        log_dir=log_dir,
        record_signature_gate_preview=True,
        confirm_tiny_live_signature_gate_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_SIGNATURE_GATE_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["signature_gate_preview_recorded"] is False
    assert payload["signature_gate_preview_overall_status"] == (
        "TINY_LIVE_SIGNATURE_GATE_PREVIEW_REJECTED_BAD_CONFIRMATION"
    )
    assert load_tiny_live_signature_gate_preview_records(log_dir=log_dir, limit=0) == []
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_exact_confirmation_records_preview_only_and_no_mutations(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_r250(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    before_env = dict(os.environ)
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
        payload = build_tiny_live_signature_gate_preview(
            log_dir=log_dir,
            record_signature_gate_preview=True,
            confirm_tiny_live_signature_gate_preview=CONFIRM_TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDING_PHRASE,
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert dict(os.environ) == before_env
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert env_path.read_text(encoding="utf-8") == before_env_file

    records = load_tiny_live_signature_gate_preview_records(log_dir=log_dir, limit=0)
    assert payload["status"] == TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["signature_gate_preview_recorded"] is True
    assert len(records) == 1
    assert records[0]["signature_gate_preview_recorded"] is True
    assert payload["signature_gate_preview_overall_status"] == (
        "TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDED_SIGNED_WRITE_REQUIRED"
    )
    assert payload["operator_signature_gate_preview_packet"]["operator_should_create_signed_request_now"] is False
    assert payload["operator_signature_gate_preview_packet"]["operator_should_submit_now"] is False
    assert payload["operator_signature_gate_preview_packet"]["operator_should_place_order"] is False


def test_loads_r249_executable_payload_and_builds_unsigned_templates(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r250(tmp_path)

    latest = load_latest_tiny_live_executable_payload_write_gate(log_dir=log_dir)
    payload = build_tiny_live_signature_gate_preview(log_dir=log_dir, now=NOW)
    templates = payload["unsigned_request_templates_preview"]

    assert latest["executable_payload_written"] is True
    assert payload["executable_payload_summary"] == {
        "main_order_side": "SELL",
        "main_order_type": "MARKET",
        "quantity": 0.007,
        "stop_order_side": "BUY",
        "stop_order_type": "STOP_MARKET",
        "stop_price": 62844.6,
        "take_profit_order_side": "BUY",
        "take_profit_order_type": "TAKE_PROFIT_MARKET",
        "take_profit_price": 60941.7,
    }
    assert templates["preview_only"] is True
    assert templates["signed"] is False
    for key in ("main_order_template", "stop_order_template", "take_profit_order_template"):
        assert templates[key]["endpoint"] == "/fapi/v1/order"
        assert templates[key]["signed"] is False
        assert templates[key]["query_params_preview"]["signature"] == "<NOT_CREATED>"
        assert templates[key]["query_params_preview"]["timestamp"] == "<FUTURE_TIMESTAMP>"
    assert templates["main_order_template"]["query_params_preview"]["quantity"] == "0.007"
    assert templates["stop_order_template"]["query_params_preview"]["stopPrice"] == "62844.6"
    assert templates["take_profit_order_template"]["query_params_preview"]["stopPrice"] == "60941.7"


def test_blocks_if_r249_executable_payload_missing(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    payload = build_tiny_live_signature_gate_preview(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED
    assert payload["input_summary"]["r249_executable_payload_found"] is False
    assert payload["signature_gate_preview_overall_status"] == "TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED_BY_R249"
    assert "r249_executable_payload_missing" in payload["signature_gate_preview_matrix"]["blocked_by"]


def test_signature_requirements_and_safety_flags_are_false(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r250(tmp_path)

    payload = build_tiny_live_signature_gate_preview(log_dir=log_dir, now=NOW)
    requirements = payload["signature_requirements_preview"]
    safety = payload["safety"]

    assert requirements["requires_api_key_later"] is True
    assert requirements["requires_api_secret_later"] is True
    assert requirements["api_key_loaded"] is False
    assert requirements["api_secret_loaded"] is False
    assert requirements["secrets_read"] is False
    assert requirements["secrets_shown"] is False
    assert requirements["hmac_signature_created"] is False
    assert requirements["signed_request_written"] is False
    assert requirements["future_gate_required"] == "R251_TINY_LIVE_SIGNED_REQUEST_WRITE_GATE"
    for key in (
        "api_key_loaded",
        "api_secret_loaded",
        "secrets_read",
        "secrets_shown",
        "hmac_signature_created",
        "signed_request_written",
        "signed_order_request_created",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "binance_account_endpoint_called",
        "binance_exchange_info_endpoint_called",
        "binance_mark_price_endpoint_called",
        "network_allowed",
        "env_written",
        "env_mutated",
        "config_written",
        "risk_contract_config_written",
        "lane_controls_written",
        "live_config_written",
    ):
        assert safety[key] is False
    assert safety["signature_gate_preview_only"] is True
    assert safety["paper_live_separation_intact"] is True


def _fixture_r250(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_r249(tmp_path)
    payload = build_tiny_live_executable_payload_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        write_executable_payload=True,
        confirm_tiny_live_executable_payload_write=CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_PHRASE,
        now=NOW,
    )
    assert payload["executable_payload_written"] is True
    return log_dir, risk_path, lane_path
