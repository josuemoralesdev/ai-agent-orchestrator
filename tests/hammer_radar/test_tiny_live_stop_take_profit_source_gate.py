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
    build_tiny_live_executable_payload_preview,
)
from src.app.hammer_radar.operator.tiny_live_stop_take_profit_source_gate import (
    CONFIRM_TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_PREVIEW_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_DIRECTIONAL_VALIDATION,
    TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_MISSING_SOURCE,
    TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_BLOCKED,
    TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_READY,
    TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_RECORDED,
    TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_REJECTED,
    TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_RECORDED_EXECUTABLE_WRITE_STILL_BLOCKED,
    build_tiny_live_stop_take_profit_source_gate,
    compute_stop_take_profit_risk_preview,
    load_tiny_live_stop_take_profit_source_gate_records,
    round_price_to_tick,
    validate_short_stop_take_profit_levels,
)
from tests.hammer_radar.test_tiny_live_executable_payload_preview import _fixture_r247

NOW = datetime(2026, 6, 11, 6, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_cli_command_exists_and_returns_json(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r248(tmp_path, with_source=True)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-stop-take-profit-source-gate",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["stop_take_profit_source_preview_recorded"] is False


def test_preview_writes_no_ledger(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r248(tmp_path, with_source=True)

    payload = build_tiny_live_stop_take_profit_source_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_READY
    assert payload["record_stop_take_profit_source_preview_requested"] is False
    assert payload["stop_take_profit_source_preview_recorded"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_and_writes_no_valid_record(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r248(tmp_path, with_source=True)

    payload = build_tiny_live_stop_take_profit_source_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        record_stop_take_profit_source_preview=True,
        confirm_tiny_live_stop_take_profit_source_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["stop_take_profit_source_preview_recorded"] is False
    assert load_tiny_live_stop_take_profit_source_gate_records(log_dir=log_dir, limit=0) == []
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_exact_confirmation_records_preview_only(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_r248(tmp_path, with_source=True)
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
        payload = build_tiny_live_stop_take_profit_source_gate(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            record_stop_take_profit_source_preview=True,
            confirm_tiny_live_stop_take_profit_source_preview=(
                CONFIRM_TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_PREVIEW_RECORDING_PHRASE
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

    assert payload["status"] == TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_RECORDED
    assert payload["stop_take_profit_source_preview_recorded"] is True
    assert payload["stop_take_profit_source_overall_status"] == (
        TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_RECORDED_EXECUTABLE_WRITE_STILL_BLOCKED
    )
    assert payload["stop_take_profit_source_preview"]["artifact_written"] is False
    assert payload["stop_take_profit_source_preview"]["executable"] is False
    assert payload["stop_take_profit_source_preview"]["signed"] is False
    assert payload["stop_take_profit_source_gate_matrix"]["executable_payload_created"] is False
    assert payload["stop_take_profit_source_gate_matrix"]["signed_order_request_created"] is False
    assert payload["stop_take_profit_source_gate_matrix"]["order_ready"] is False
    assert payload["safety"]["order_placed"] is False
    records = load_tiny_live_stop_take_profit_source_gate_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    assert records[0]["stop_take_profit_source_preview_recorded"] is True


def test_source_missing_produces_blocked_status(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r248(tmp_path, with_source=False)

    payload = build_tiny_live_stop_take_profit_source_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_BLOCKED
    assert payload["input_summary"]["local_stop_take_profit_source_found"] is False
    assert payload["stop_take_profit_source_overall_status"] == (
        TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_MISSING_SOURCE
    )
    assert "local_stop_take_profit_source_missing" in payload["stop_take_profit_source_gate_matrix"]["blocked_by"]


def test_source_present_validates_short_stop_above_entry_and_tp_below_entry(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r248(tmp_path, with_source=True)

    payload = build_tiny_live_stop_take_profit_source_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    selected = payload["selected_stop_take_profit_source"]
    assert selected["source_name"] == "r247_executable_payload_preview"
    assert selected["entry_reference_price"] == 62210.3
    assert selected["rounded_stop_price"] == 62844.6
    assert selected["rounded_take_profit_price"] == 60941.7
    assert payload["short_direction_validation"]["valid"] is True
    assert payload["risk_reward_validation"]["valid"] is True
    assert payload["stop_take_profit_source_gate_matrix"]["stop_take_profit_preview_ready"] is True


def test_invalid_short_direction_blocks(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r248(tmp_path, with_source=True, stop_price=62100.0)

    payload = build_tiny_live_stop_take_profit_source_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_BLOCKED
    assert payload["short_direction_validation"]["valid"] is False
    assert payload["stop_take_profit_source_overall_status"] == (
        TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_DIRECTIONAL_VALIDATION
    )


def test_tick_rounding_works() -> None:
    assert round_price_to_tick(62844.64, 0.1) == 62844.6
    assert round_price_to_tick(62844.65, 0.1) == 62844.7
    assert round_price_to_tick(None, 0.1) is None


def test_risk_reward_preview_computes() -> None:
    selected = {
        "entry_reference_price": 62210.3,
        "rounded_stop_price": 62844.6,
        "rounded_take_profit_price": 60941.7,
        "source_valid": True,
        "blocked_by": [],
    }

    validation = validate_short_stop_take_profit_levels(selected)
    risk = compute_stop_take_profit_risk_preview(
        selected_source=selected,
        quantity_preview=0.007,
        max_loss_usdt=4.44,
    )

    assert validation["valid"] is True
    assert risk["valid"] is True
    assert risk["max_loss_ok"] is True
    assert round(risk["loss_usdt_preview"], 4) == 4.4401
    assert round(risk["reward_usdt_preview"], 4) == 8.8802
    assert round(risk["risk_reward_ratio_preview"], 3) == 2.0


def test_no_binance_network_env_config_lane_control_mutation(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_r248(tmp_path, with_source=True)
    before_env = dict(os.environ)
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    payload = build_tiny_live_stop_take_profit_source_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert dict(os.environ) == before_env
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
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
    assert payload["safety"]["stop_take_profit_source_gate_only"] is True


def _fixture_r248(
    tmp_path: Path,
    *,
    with_source: bool,
    stop_price: float = 62844.6,
    take_profit_price: float = 60941.7,
) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_r247(tmp_path)
    payload = build_tiny_live_executable_payload_preview(
        log_dir=log_dir,
        record_executable_payload_preview=True,
        confirm_tiny_live_executable_payload_preview=CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_RECORDING_PHRASE,
        now=NOW,
    )
    assert payload["executable_payload_preview_recorded"] is True
    if with_source:
        path = log_dir / "tiny_live_executable_payload_preview.ndjson"
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        record = records[-1]
        record["local_stop_take_profit_source"] = {
            "official_lane_key": OFFICIAL,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "entry_reference_price": 62210.3,
            "stop_price": stop_price,
            "take_profit_price": take_profit_price,
        }
        records[-1] = record
        path.write_text(
            "".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in records),
            encoding="utf-8",
        )
    return log_dir, risk_path, lane_path
