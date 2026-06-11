from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_leverage_notional_risk_contract_write_gate import (
    CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_PHRASE,
    build_tiny_live_leverage_notional_risk_contract_write_gate,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_refresh_preview import (
    CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_R242,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_RISK_CONTRACT,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_CLEARS_PRECISION_AND_MIN_NOTIONAL,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_READY,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDED,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_REJECTED,
    build_tiny_live_order_payload_refresh_preview,
    compute_refreshed_quantity_preview,
    load_tiny_live_order_payload_refresh_preview_records,
)
from tests.hammer_radar.test_tiny_live_leverage_notional_risk_contract_write_gate import (
    _fixture_r244,
)

NOW = datetime(2026, 6, 11, 1, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r245(tmp_path)

    payload = build_tiny_live_order_payload_refresh_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_READY
    assert payload["payload_refresh_preview_recorded"] is False
    assert payload["record_payload_refresh_preview_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["refreshed_quantity_preview"]["quantity_rounded"] == 0.007
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r245(tmp_path)

    payload = build_tiny_live_order_payload_refresh_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        record_payload_refresh_preview=True,
        confirm_tiny_live_order_payload_refresh_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["payload_refresh_preview_recorded"] is False
    assert load_tiny_live_order_payload_refresh_preview_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_preview_only(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_r245(tmp_path)
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
        payload = build_tiny_live_order_payload_refresh_preview(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            record_payload_refresh_preview=True,
            confirm_tiny_live_order_payload_refresh_preview=(
                CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDING_PHRASE
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
    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDED
    assert payload["payload_refresh_preview_recorded"] is True
    records = load_tiny_live_order_payload_refresh_preview_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    assert records[0]["safety"]["payload_refresh_preview_only"] is True
    assert records[0]["safety"]["order_payload_written"] is False
    assert records[0]["safety"]["order_payload_created"] is False
    assert records[0]["safety"]["network_allowed"] is False
    assert records[0]["safety"]["order_placed"] is False


def test_preview_requires_r244_adjusted_risk_contract(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r245(tmp_path)
    config = json.loads(risk_path.read_text(encoding="utf-8"))
    for contract in config["risk_contracts"]:
        if contract.get("official_lane_key") == OFFICIAL:
            contract["max_notional_usdt"] = 44
            contract["leverage"] = 1
    risk_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")

    payload = build_tiny_live_order_payload_refresh_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["input_summary"]["r244_adjusted_contract_valid"] is False
    assert payload["payload_refresh_preview_overall_status"] == (
        TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_RISK_CONTRACT
    )


def test_preview_requires_r242_precision_mark_price_result(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r245(tmp_path)
    (log_dir / "tiny_live_binance_readonly_precision_mark_price_gate.ndjson").unlink()

    payload = build_tiny_live_order_payload_refresh_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["input_summary"]["r242_readonly_found"] is False
    assert payload["payload_refresh_preview_overall_status"] == TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_BLOCKED_BY_R242


def test_preview_requires_r240_payload_artifact(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r245(tmp_path)
    (log_dir / "tiny_live_order_payload_write_gate.ndjson").unlink()

    payload = build_tiny_live_order_payload_refresh_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["input_summary"]["r240_payload_found"] is False
    assert "r240_payload_valid_missing_or_false" in payload["payload_refresh_validation"]["errors"]


def test_computes_refreshed_quantity_from_440_notional() -> None:
    quantity = compute_refreshed_quantity_preview(
        max_notional_usdt=440,
        mark_price=62210.3,
        step_size=0.001,
        min_notional=50.0,
    )

    assert quantity["can_compute"] is True
    assert quantity["quantity_rounded"] == 0.007
    assert quantity["notional_after_rounding"] == 435.4721
    assert quantity["clears_min_notional"] is True


def test_refreshed_payload_preview_shape_and_safety(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r245(tmp_path)

    payload = build_tiny_live_order_payload_refresh_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    preview = payload["refreshed_non_executable_payload_preview"]
    assert payload["payload_refresh_preview_overall_status"] == (
        TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_CLEARS_PRECISION_AND_MIN_NOTIONAL
    )
    assert payload["payload_refresh_validation"]["valid"] is True
    assert payload["payload_refresh_preview_gate_matrix"]["payload_refresh_preview_ready"] is True
    assert payload["operator_payload_refresh_preview_packet"]["operator_should_create_executable_payload_now"] is False
    assert preview["symbol"] == "BTCUSDT"
    assert preview["side"] == "SELL"
    assert preview["order_type"] == "MARKET_PREVIEW_ONLY"
    assert preview["quantity_preview"] == 0.007
    assert preview["notional_after_rounding"] == 435.4721
    assert preview["leverage"] == 10
    assert preview["margin_budget_usdt"] == 44
    assert preview["notional_cap_usdt"] == 440
    assert preview["executable"] is False
    assert preview["signed"] is False
    assert preview["submit_allowed"] is False
    assert preview["stop_payload_preview"]["stop_price"] is None
    assert preview["take_profit_payload_preview"]["take_profit_price"] is None
    for key in (
        "order_payload_written",
        "order_payload_created",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "binance_account_endpoint_called",
        "binance_exchange_info_endpoint_called",
        "binance_mark_price_endpoint_called",
        "network_allowed",
        "config_written",
        "env_written",
        "env_mutated",
        "lane_controls_written",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["paper_live_separation_intact"] is True
    assert payload["safety"]["payload_refresh_preview_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r245(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-order-payload-refresh-preview",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={
            **os.environ,
            "PYTHONPATH": ".",
            "HAMMER_TINY_LIVE_RISK_CONTRACT_CONFIG": str(risk_path),
        },
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
    assert payload["payload_refresh_preview_recorded"] is False
    assert "tiny-live-order-payload-refresh-preview" in help_result.stdout


def _fixture_r245(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_r244(tmp_path)
    payload = build_tiny_live_leverage_notional_risk_contract_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        write_risk_contract=True,
        confirm_tiny_live_leverage_notional_risk_contract_write=(
            CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_PHRASE
        ),
        now=NOW,
    )
    assert payload["risk_contract_written"] is True
    return log_dir, risk_path, lane_path
