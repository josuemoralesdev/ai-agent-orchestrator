from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_order_payload_refresh_preview import (
    CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDING_PHRASE,
    build_tiny_live_order_payload_refresh_preview,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_refresh_write_gate import (
    CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_READY,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_REJECTED,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_WRITTEN,
    build_tiny_live_order_payload_refresh_write_gate,
    load_tiny_live_order_payload_refresh_write_gate_records,
    validate_refreshed_non_executable_payload_artifact,
)
from tests.hammer_radar.test_tiny_live_order_payload_refresh_preview import _fixture_r245

NOW = datetime(2026, 6, 11, 2, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_artifact(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r246(tmp_path)

    payload = build_tiny_live_order_payload_refresh_write_gate(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_READY
    assert payload["payload_refresh_written"] is False
    assert payload["write_payload_refresh_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["payload_refresh_write_preview"]["would_write"] is True
    assert payload["payload_refresh_write_preview"]["payload_artifact"] == "ledger_only_non_executable_refreshed_payload"
    assert payload["payload_refresh_write_preview"]["proposed_refreshed_payload"]["quantity"] == 0.007
    assert risk_path.exists()
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_and_writes_no_artifact(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r246(tmp_path)

    payload = build_tiny_live_order_payload_refresh_write_gate(
        log_dir=log_dir,
        write_payload_refresh=True,
        confirm_tiny_live_order_payload_refresh_write="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["payload_refresh_written"] is False
    assert payload["payload_refresh_write_overall_status"] == (
        "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_REJECTED_BAD_CONFIRMATION"
    )
    assert load_tiny_live_order_payload_refresh_write_gate_records(log_dir=log_dir, limit=0) == []
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_exact_confirmation_writes_only_refreshed_non_executable_payload_artifact(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_r246(tmp_path)
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
        payload = build_tiny_live_order_payload_refresh_write_gate(
            log_dir=log_dir,
            write_payload_refresh=True,
            confirm_tiny_live_order_payload_refresh_write=CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_PHRASE,
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

    records = load_tiny_live_order_payload_refresh_write_gate_records(log_dir=log_dir, limit=0)
    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_WRITTEN
    assert payload["payload_refresh_written"] is True
    assert len(records) == 1
    artifact = records[0]["refreshed_payload_artifact"]
    assert validate_refreshed_non_executable_payload_artifact(artifact)["valid"] is True
    assert artifact["order_payload_id"] == "r246_refreshed_order_payload_BTCUSDT_8m_short_ladder_close_50_618"
    assert artifact["order_payload_version"] == "tiny_live_refreshed_non_executable_payload_v1"
    assert artifact["quantity"] == 0.007
    assert artifact["notional_after_rounding"] == 435.4721
    assert artifact["leverage"] == 10
    assert artifact["margin_budget_usdt"] == 44
    assert artifact["notional_cap_usdt"] == 440
    assert artifact["max_loss_usdt"] == 4.44
    assert artifact["max_loss_requires_review"] is True
    assert artifact["executable"] is False
    assert artifact["signed"] is False
    assert artifact["submit_allowed"] is False
    assert artifact["binance_call_allowed"] is False
    assert artifact["network_allowed"] is False
    assert artifact["order_placed"] is False
    assert artifact["executable_payload_created"] is False
    assert artifact["signed_order_request_created"] is False
    assert artifact["signed_trading_request_created"] is False
    assert artifact["stop_required"] is True
    assert artifact["take_profit_required"] is True
    assert payload["post_write_verification"]["matching_payload_refresh_found"] is True
    assert payload["post_write_verification"]["matching_payload_refresh_valid"] is True
    assert payload["post_write_verification"]["quantity"] == 0.007
    assert payload["post_write_verification"]["notional_after_rounding"] == 435.4721
    assert payload["payload_refresh_write_gate_matrix"]["payload_refresh_written"] is True
    assert payload["payload_refresh_write_gate_matrix"]["executable_payload_created"] is False
    assert payload["payload_refresh_write_gate_matrix"]["signed_order_request_created"] is False
    assert payload["payload_refresh_write_gate_matrix"]["order_ready"] is False
    assert payload["payload_refresh_write_gate_matrix"]["live_ready_today"] is False
    assert payload["operator_payload_refresh_write_packet"]["operator_should_create_executable_payload_now"] is False
    assert payload["operator_payload_refresh_write_packet"]["operator_should_place_order"] is False


def test_payload_artifact_validates(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r246(tmp_path)

    payload = build_tiny_live_order_payload_refresh_write_gate(log_dir=log_dir, now=NOW)
    artifact = payload["payload_refresh_write_preview"]["proposed_refreshed_payload"]
    validation = validate_refreshed_non_executable_payload_artifact(artifact)

    assert validation["valid"] is True
    assert artifact["quantity"] == 0.007
    assert artifact["notional_after_rounding"] == 435.4721
    assert artifact["leverage"] == 10
    assert artifact["margin_budget_usdt"] == 44
    assert artifact["notional_cap_usdt"] == 440


def test_safety_flags_preserve_non_actions(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r246(tmp_path)
    payload = build_tiny_live_order_payload_refresh_write_gate(log_dir=log_dir, now=NOW)

    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "risk_contract_config_written",
        "lane_controls_written",
        "live_config_written",
        "order_payload_written",
        "order_payload_created",
        "executable_payload_created",
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
    assert payload["safety"]["paper_live_separation_intact"] is True
    assert payload["safety"]["payload_refresh_write_gate_only"] is True
    assert payload["safety"]["non_executable_artifact_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r246(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-order-payload-refresh-write-gate",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
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
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["payload_refresh_written"] is False
    assert "tiny-live-order-payload-refresh-write-gate" in help_result.stdout


def _fixture_r246(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_r245(tmp_path)
    payload = build_tiny_live_order_payload_refresh_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        record_payload_refresh_preview=True,
        confirm_tiny_live_order_payload_refresh_preview=CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDING_PHRASE,
        now=NOW,
    )
    assert payload["payload_refresh_preview_recorded"] is True
    return log_dir, risk_path, lane_path
