from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_precision_and_mark_price_preview import (
    CONFIRM_TINY_LIVE_PRECISION_MARK_PRICE_PREVIEW_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_NEEDS_BINANCE_READONLY_CHECK,
    TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY,
    TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY_FOR_FUTURE_GATE,
    TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_RECORDED,
    TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_REJECTED,
    build_tiny_live_precision_and_mark_price_preview,
    load_tiny_live_precision_and_mark_price_preview_records,
)
from tests.hammer_radar.test_tiny_live_order_payload_preview import (
    _append,
    _write_lane_controls,
    _write_risk_contract_config,
)
from tests.hammer_radar.test_tiny_live_order_payload_write_gate import (
    CONFIRM_TINY_LIVE_ORDER_PAYLOAD_WRITE_PHRASE,
    build_tiny_live_order_payload_write_gate,
    _fixture_logs as _r240_fixture_logs,
)

NOW = datetime(2026, 6, 10, 16, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    payload = build_tiny_live_precision_and_mark_price_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY
    assert payload["precision_mark_price_preview_recorded"] is False
    assert payload["record_precision_mark_price_preview_requested"] is False
    assert payload["confirmation_valid"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    payload = build_tiny_live_precision_and_mark_price_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        record_precision_mark_price_preview=True,
        confirm_tiny_live_precision_mark_price_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["precision_mark_price_preview_recorded"] is False
    assert load_tiny_live_precision_and_mark_price_preview_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_preview_only(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
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
        payload = build_tiny_live_precision_and_mark_price_preview(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            record_precision_mark_price_preview=True,
            confirm_tiny_live_precision_mark_price_preview=(
                CONFIRM_TINY_LIVE_PRECISION_MARK_PRICE_PREVIEW_RECORDING_PHRASE
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
    assert payload["status"] == TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_RECORDED
    assert payload["precision_mark_price_preview_recorded"] is True
    records = load_tiny_live_precision_and_mark_price_preview_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    assert records[0]["safety"]["precision_mark_price_preview_only"] is True
    assert records[0]["safety"]["order_payload_created"] is False
    assert records[0]["safety"]["executable_payload_created"] is False
    assert records[0]["safety"]["signed_order_request_created"] is False
    assert records[0]["safety"]["signed_trading_request_created"] is False
    assert records[0]["safety"]["order_placed"] is False


def test_preview_requires_r240_payload_artifact(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    (log_dir / "tiny_live_order_payload_write_gate.ndjson").unlink()

    payload = build_tiny_live_precision_and_mark_price_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        now=NOW,
    )

    assert payload["input_summary"]["r240_payload_found"] is False
    assert payload["precision_mark_price_gate_matrix"]["payload_artifact_ready"] is False
    assert payload["precision_mark_price_preview_overall_status"] == "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_PAYLOAD"


def test_preview_requires_r238_order_preflight_artifact(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    (log_dir / "tiny_live_order_preflight_write_gate.ndjson").unlink()

    payload = build_tiny_live_precision_and_mark_price_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        now=NOW,
    )

    assert payload["input_summary"]["r238_order_preflight_found"] is False
    assert payload["precision_mark_price_preview_overall_status"] == "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_PREFLIGHT"


def test_preview_requires_valid_risk_contract(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    config = json.loads(risk_path.read_text(encoding="utf-8"))
    config["risk_contracts"][0]["max_notional_usdt"] = 45
    risk_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")

    payload = build_tiny_live_precision_and_mark_price_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        now=NOW,
    )

    assert payload["input_summary"]["risk_contract_valid"] is False
    assert payload["precision_mark_price_preview_overall_status"] == "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_RISK_CONTRACT"


def test_missing_local_precision_and_price_blocks_quantity(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    payload = build_tiny_live_precision_and_mark_price_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        now=NOW,
    )

    assert payload["local_precision_snapshot"]["found"] is False
    assert payload["local_mark_or_candidate_price_snapshot"]["found"] is False
    assert payload["quantity_preview"]["can_compute"] is False
    assert payload["quantity_preview"]["quantity_rounded"] is None
    assert payload["precision_mark_price_preview_overall_status"] == TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_NEEDS_BINANCE_READONLY_CHECK


def test_local_precision_and_price_compute_quantity_preview(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    _append(
        log_dir / "market_intelligence_snapshots.ndjson",
        {
            "created_at": NOW.isoformat(),
            "network_used": False,
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "exchange_info_status": "STATIC_FIXTURE",
                    "step_size": 0.001,
                    "tick_size": 0.1,
                    "min_notional_usd": 5.0,
                    "last_price": None,
                }
            ],
        },
    )
    _append(
        log_dir / "candles_BTCUSDT_8m.ndjson",
        {
            "symbol": "BTCUSDT",
            "timestamp": NOW.isoformat(),
            "open": 40000,
            "high": 40100,
            "low": 39900,
            "close": 40000,
        },
    )

    payload = build_tiny_live_precision_and_mark_price_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        now=NOW,
    )

    assert payload["local_precision_snapshot"]["found"] is True
    assert payload["local_mark_or_candidate_price_snapshot"]["found"] is True
    assert payload["quantity_preview"]["can_compute"] is True
    assert payload["quantity_preview"]["quantity_raw"] == 0.0011
    assert payload["quantity_preview"]["quantity_rounded"] == 0.001
    assert payload["quantity_preview"]["notional_after_rounding"] == 40.0
    assert payload["quantity_preview"]["min_notional_ok"] is True
    assert payload["precision_mark_price_preview_overall_status"] == TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY_FOR_FUTURE_GATE


def test_safety_flags_preserve_non_actions(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    payload = build_tiny_live_precision_and_mark_price_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        now=NOW,
    )

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
    assert payload["safety"]["precision_mark_price_preview_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-precision-and-mark-price-preview",
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
    assert payload["precision_mark_price_preview_recorded"] is False
    assert "tiny-live-precision-and-mark-price-preview" in help_result.stdout
    assert risk_path.exists()
    assert lane_path.exists()


def _fixture_logs(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir = _r240_fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    lane_path = _write_lane_controls(tmp_path / "lane_controls.json")
    build_tiny_live_order_payload_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        write_order_payload=True,
        confirm_tiny_live_order_payload_write=CONFIRM_TINY_LIVE_ORDER_PAYLOAD_WRITE_PHRASE,
        now=NOW,
    )
    return log_dir, risk_path, lane_path
