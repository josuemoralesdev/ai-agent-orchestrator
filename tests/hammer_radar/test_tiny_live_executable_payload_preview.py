from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_executable_payload_preview import (
    CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED,
    TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_STOP_TP_LEVELS,
    TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_RECORDED,
    TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_REJECTED,
    build_tiny_live_executable_payload_preview,
    load_tiny_live_executable_payload_preview_records,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_refresh_write_gate import (
    CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_PHRASE,
    build_tiny_live_order_payload_refresh_write_gate,
)
from tests.hammer_radar.test_tiny_live_order_payload_refresh_write_gate import _fixture_r246

NOW = datetime(2026, 6, 11, 4, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r247(tmp_path)

    payload = build_tiny_live_executable_payload_preview(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED
    assert payload["executable_payload_preview_recorded"] is False
    assert payload["record_executable_payload_preview_requested"] is False
    assert payload["confirmation_valid"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r247(tmp_path)

    payload = build_tiny_live_executable_payload_preview(
        log_dir=log_dir,
        record_executable_payload_preview=True,
        confirm_tiny_live_executable_payload_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["executable_payload_preview_recorded"] is False
    assert load_tiny_live_executable_payload_preview_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_preview_only(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_r247(tmp_path)
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
        payload = build_tiny_live_executable_payload_preview(
            log_dir=log_dir,
            record_executable_payload_preview=True,
            confirm_tiny_live_executable_payload_preview=(
                CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_RECORDING_PHRASE
            ),
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

    assert payload["status"] == TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_RECORDED
    assert payload["executable_payload_preview_recorded"] is True
    records = load_tiny_live_executable_payload_preview_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    record = records[0]
    assert record["safety"]["executable_payload_preview_only"] is True
    assert record["safety"]["executable_payload_created"] is False
    assert record["safety"]["signed_order_request_created"] is False
    assert record["safety"]["order_placed"] is False
    assert record["safety"]["network_allowed"] is False


def test_requires_r246_refreshed_non_executable_payload_artifact(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r247(tmp_path)
    (log_dir / "tiny_live_order_payload_refresh_write_gate.ndjson").unlink()

    payload = build_tiny_live_executable_payload_preview(log_dir=log_dir, now=NOW)

    assert payload["input_summary"]["r246_payload_refresh_found"] is False
    assert payload["input_summary"]["r246_payload_refresh_valid"] is False
    assert payload["executable_payload_preview_gate_matrix"]["r246_payload_refresh_ready"] is False
    assert "r246_payload_refresh_not_ready" in payload["executable_payload_preview_gate_matrix"]["blocked_by"]


def test_consumes_quantity_and_keeps_payload_non_executable(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r247(tmp_path)

    payload = build_tiny_live_executable_payload_preview(log_dir=log_dir, now=NOW)
    base = payload["base_non_executable_payload_summary"]
    readiness = payload["executable_payload_readiness_preview"]

    assert base["quantity"] == 0.007
    assert base["notional_after_rounding"] == 435.4721
    assert base["side"] == "SELL"
    assert base["executable"] is False
    assert base["signed"] is False
    assert base["submit_allowed"] is False
    assert readiness["base_payload"]["quantity"] == 0.007
    assert readiness["would_be_executable_payload_shape_later"]["executable"] is False
    assert readiness["would_be_executable_payload_shape_later"]["signed"] is False
    assert readiness["would_be_executable_payload_shape_later"]["submit_allowed"] is False
    assert readiness["executable_payload_created"] is False
    assert readiness["signed"] is False
    assert readiness["submit_allowed"] is False
    assert readiness["order_placed"] is False


def test_stop_and_take_profit_missing_block_readiness(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r247(tmp_path)

    payload = build_tiny_live_executable_payload_preview(log_dir=log_dir, now=NOW)
    candidates = payload["stop_take_profit_candidate_summary"]
    matrix = payload["executable_payload_preview_gate_matrix"]

    assert candidates["stop_price_found"] is False
    assert candidates["take_profit_price_found"] is False
    assert candidates["stop_price"] is None
    assert candidates["take_profit_price"] is None
    assert "final_stop_price_missing" in candidates["blocked_by"]
    assert "final_take_profit_price_missing" in candidates["blocked_by"]
    assert matrix["stop_price_ready"] is False
    assert matrix["take_profit_price_ready"] is False
    assert matrix["executable_payload_preview_ready"] is False
    assert payload["executable_payload_preview_overall_status"] == (
        TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_STOP_TP_LEVELS
    )


def test_price_precision_and_safety_requirements_included(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r247(tmp_path)

    payload = build_tiny_live_executable_payload_preview(log_dir=log_dir, now=NOW)
    precision = payload["executable_payload_readiness_preview"]["price_precision_requirements"]
    matrix = payload["executable_payload_preview_gate_matrix"]

    assert precision["tick_size"] == 0.1
    assert precision["price_precision"] == 2
    assert precision["requires_stop_price_rounding"] is True
    assert precision["requires_take_profit_price_rounding"] is True
    assert matrix["quantity_ready"] is True
    assert matrix["notional_ready"] is True
    assert matrix["price_precision_ready"] is True
    assert matrix["executable_payload_created"] is False
    assert matrix["signed_order_request_created"] is False
    assert matrix["order_ready"] is False
    assert matrix["live_ready_today"] is False


def test_no_executable_payload_signed_request_order_or_mutations(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r247(tmp_path)
    payload = build_tiny_live_executable_payload_preview(log_dir=log_dir, now=NOW)

    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "risk_contract_config_written",
        "lane_controls_written",
        "live_config_written",
        "order_payload_written",
        "order_payload_created",
        "executable_payload_written",
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
    assert payload["safety"]["executable_payload_preview_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r247(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-executable-payload-preview",
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
    assert payload["executable_payload_preview_recorded"] is False
    assert "tiny-live-executable-payload-preview" in help_result.stdout


def _fixture_r247(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_r246(tmp_path)
    payload = build_tiny_live_order_payload_refresh_write_gate(
        log_dir=log_dir,
        write_payload_refresh=True,
        confirm_tiny_live_order_payload_refresh_write=CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_PHRASE,
        now=NOW,
    )
    assert payload["payload_refresh_written"] is True
    return log_dir, risk_path, lane_path
