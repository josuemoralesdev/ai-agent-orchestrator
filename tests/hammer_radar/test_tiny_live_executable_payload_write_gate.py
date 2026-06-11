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
    LEDGER_FILENAME,
    TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_R247,
    TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_R248,
    TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_BLOCKED,
    TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_READY,
    TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_REJECTED,
    TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_WRITTEN,
    build_tiny_live_executable_payload_write_gate,
    load_tiny_live_executable_payload_write_gate_records,
    validate_executable_payload_artifact,
)
from src.app.hammer_radar.operator.tiny_live_stop_take_profit_source_gate import (
    CONFIRM_TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_PREVIEW_RECORDING_PHRASE,
    build_tiny_live_stop_take_profit_source_gate,
)
from tests.hammer_radar.test_tiny_live_stop_take_profit_source_gate import _fixture_r248

NOW = datetime(2026, 6, 11, 8, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_cli_command_exists_and_returns_json(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r249(tmp_path)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-executable-payload-write-gate",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["executable_payload_written"] is False


def test_preview_writes_no_ledger(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r249(tmp_path)

    payload = build_tiny_live_executable_payload_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_READY
    assert payload["write_executable_payload_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["executable_payload_written"] is False
    assert payload["payload_artifact_preview"]["would_write"] is True
    assert payload["payload_artifact_preview"]["artifact_only"] is True
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r249(tmp_path)

    payload = build_tiny_live_executable_payload_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        write_executable_payload=True,
        confirm_tiny_live_executable_payload_write="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["executable_payload_written"] is False
    assert payload["executable_payload_write_overall_status"] == (
        "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_REJECTED_BAD_CONFIRMATION"
    )
    assert load_tiny_live_executable_payload_write_gate_records(log_dir=log_dir, limit=0) == []
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_exact_confirmation_writes_local_executable_payload_artifact_only(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_r249(tmp_path)
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
        payload = build_tiny_live_executable_payload_write_gate(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            write_executable_payload=True,
            confirm_tiny_live_executable_payload_write=CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_PHRASE,
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

    records = load_tiny_live_executable_payload_write_gate_records(log_dir=log_dir, limit=0)
    assert payload["status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_WRITTEN
    assert payload["confirmation_valid"] is True
    assert payload["executable_payload_written"] is True
    assert len(records) == 1
    artifact = records[0]["executable_payload_artifact"]
    assert validate_executable_payload_artifact(artifact)["valid"] is True
    assert artifact["official_lane_key"] == OFFICIAL
    assert artifact["artifact_only"] is True
    assert artifact["main_order"]["side"] == "SELL"
    assert artifact["main_order"]["type"] == "MARKET"
    assert artifact["main_order"]["quantity"] == 0.007
    assert artifact["stop_order"]["side"] == "BUY"
    assert artifact["stop_order"]["type"] == "STOP_MARKET"
    assert artifact["stop_order"]["reduceOnly"] is True
    assert artifact["stop_order"]["stopPrice"] > artifact["reference_price"]
    assert artifact["take_profit_order"]["side"] == "BUY"
    assert artifact["take_profit_order"]["type"] == "TAKE_PROFIT_MARKET"
    assert artifact["take_profit_order"]["reduceOnly"] is True
    assert artifact["take_profit_order"]["stopPrice"] < artifact["reference_price"]
    assert artifact["risk"]["margin_budget_usdt"] == 44
    assert artifact["risk"]["leverage"] == 10
    assert artifact["risk"]["max_notional_usdt"] == 440
    assert artifact["risk"]["estimated_loss_at_stop_usdt"] <= artifact["risk"]["max_loss_usdt"] + 0.01
    assert artifact["controls"]["signed"] is False
    assert artifact["controls"]["submit_allowed"] is False
    assert artifact["controls"]["binance_call_allowed"] is False
    assert artifact["controls"]["network_allowed"] is False
    assert artifact["safety"]["signed_order_request_created"] is False
    assert artifact["safety"]["order_placed"] is False
    assert payload["post_write_verification"]["matching_executable_payload_found"] is True
    assert payload["post_write_verification"]["matching_executable_payload_valid"] is True
    assert payload["post_write_verification"]["signed"] is False
    assert payload["post_write_verification"]["submit_allowed"] is False
    assert payload["post_write_verification"]["order_placed"] is False
    assert payload["executable_payload_write_gate_matrix"]["executable_payload_written"] is True
    assert payload["executable_payload_write_gate_matrix"]["signed_order_request_created"] is False
    assert payload["executable_payload_write_gate_matrix"]["order_ready"] is False
    assert payload["operator_executable_payload_write_packet"]["operator_should_sign_now"] is False
    assert payload["operator_executable_payload_write_packet"]["operator_should_submit_now"] is False
    assert payload["operator_executable_payload_write_packet"]["operator_should_place_order"] is False


def test_artifact_validates_official_lane_and_safety_flags(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r249(tmp_path)

    payload = build_tiny_live_executable_payload_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )
    artifact = payload["payload_artifact_preview"]["proposed_executable_payload_artifact"]

    assert validate_executable_payload_artifact(artifact)["valid"] is True
    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "risk_contract_config_written",
        "lane_controls_written",
        "live_config_written",
        "signed_order_request_created",
        "signed_trading_request_created",
        "signed_readonly_request_created",
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
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["executable_payload_created"] is False
    assert payload["safety"]["executable_payload_written"] is False
    assert payload["safety"]["paper_live_separation_intact"] is True
    assert payload["safety"]["executable_payload_write_gate_only"] is True


def test_r248_blocker_if_stop_take_profit_source_missing(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r248(tmp_path, with_source=False)

    payload = build_tiny_live_executable_payload_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_BLOCKED
    assert payload["input_summary"]["r248_stop_take_profit_source_found"] is False
    assert payload["executable_payload_write_overall_status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_R248


def test_r247_blocker_if_executable_preview_missing(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r249(tmp_path)
    (log_dir / "tiny_live_executable_payload_preview.ndjson").unlink()

    payload = build_tiny_live_executable_payload_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_BLOCKED
    assert payload["input_summary"]["r247_executable_payload_preview_found"] is False
    assert payload["executable_payload_write_overall_status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_R247


def test_r246_blocker_if_payload_refresh_write_missing(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r249(tmp_path)
    (log_dir / "tiny_live_order_payload_refresh_write_gate.ndjson").unlink()

    payload = build_tiny_live_executable_payload_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_BLOCKED
    assert payload["input_summary"]["r246_payload_refresh_write_found"] is False
    assert "r246_payload_refresh_write_not_ready" in payload["executable_payload_write_gate_matrix"]["blocked_by"]


def _fixture_r249(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_r248(tmp_path, with_source=True)
    payload = build_tiny_live_stop_take_profit_source_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        record_stop_take_profit_source_preview=True,
        confirm_tiny_live_stop_take_profit_source_preview=(
            CONFIRM_TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_PREVIEW_RECORDING_PHRASE
        ),
        now=NOW,
    )
    assert payload["stop_take_profit_source_preview_recorded"] is True
    return log_dir, risk_path, lane_path
