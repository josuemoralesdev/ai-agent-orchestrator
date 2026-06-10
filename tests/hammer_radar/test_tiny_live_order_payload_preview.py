from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_order_payload_preview import (
    CONFIRM_TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_AUTHORIZATION,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_EVIDENCE,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_LANE_ARM,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_PREFLIGHT,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_RISK_CONTRACT,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY_FOR_FUTURE_GATE,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDED,
    TINY_LIVE_ORDER_PAYLOAD_PREVIEW_REJECTED,
    build_tiny_live_order_payload_preview,
    load_tiny_live_order_payload_preview_records,
)
from tests.hammer_radar.test_tiny_live_order_preflight_preview import (
    _append,
    _fixture_logs as _r237_base_fixture_logs,
    _write_lane_controls,
    _write_risk_contract_config,
)
from tests.hammer_radar.test_tiny_live_order_preflight_write_gate import (
    _fixture_logs as _r238_fixture_logs,
)

NOW = datetime(2026, 6, 10, 13, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    payload = build_tiny_live_order_payload_preview(
        log_dir=log_dir,
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY
    assert payload["order_payload_preview_recorded"] is False
    assert payload["record_order_payload_preview_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["order_payload_preview_overall_status"] == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY_FOR_FUTURE_GATE
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    payload = build_tiny_live_order_payload_preview(
        log_dir=log_dir,
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        record_order_payload_preview=True,
        confirm_tiny_live_order_payload_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["order_payload_preview_recorded"] is False
    assert load_tiny_live_order_payload_preview_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_preview_only(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    lane_path = _write_lane_controls(tmp_path / "lane_controls.json")
    env_path = tmp_path / ".env"
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    before_env = dict(os.environ)
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")
    before_env_file = env_path.read_text(encoding="utf-8")
    protected_logs = {
        "paper_outcomes": log_dir / "paper_outcomes.ndjson",
        "strategy_performance": log_dir / "strategy_performance.ndjson",
        "strategy_promotion_status": log_dir / "strategy_promotion_status.ndjson",
    }
    before_logs = {name: path.read_text(encoding="utf-8") for name, path in protected_logs.items()}

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_order_payload_preview(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            record_order_payload_preview=True,
            confirm_tiny_live_order_payload_preview=(
                CONFIRM_TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDING_PHRASE
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
    assert {name: path.read_text(encoding="utf-8") for name, path in protected_logs.items()} == before_logs

    records = load_tiny_live_order_payload_preview_records(log_dir=log_dir, limit=0)
    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDED
    assert payload["order_payload_preview_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "TINY_LIVE_ORDER_PAYLOAD_PREVIEW"
    assert records[0]["safety"]["order_payload_preview_recorded"] is True
    assert records[0]["safety"]["order_payload_preview_only"] is True
    assert records[0]["safety"]["order_payload_created"] is False
    assert records[0]["safety"]["executable_payload_created"] is False
    assert records[0]["safety"]["signed_order_request_created"] is False
    assert records[0]["safety"]["signed_trading_request_created"] is False
    assert records[0]["safety"]["order_placed"] is False


def test_preview_requires_r238_order_preflight_artifact(tmp_path: Path) -> None:
    payload = build_tiny_live_order_payload_preview(
        log_dir=_r237_base_fixture_logs(tmp_path),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["input_summary"]["r238_order_preflight_found"] is False
    assert payload["order_payload_preview_gate_matrix"]["order_payload_preview_ready"] is False
    assert payload["order_payload_preview_overall_status"] == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_PREFLIGHT


def test_preview_requires_upstream_artifacts(tmp_path: Path) -> None:
    cases = [
        ("tiny_live_lane_arm_write_gate.ndjson", TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_LANE_ARM),
        (
            "tiny_live_live_execution_enable_write_gate.ndjson",
            TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE,
        ),
        ("tiny_live_live_authorization_write_gate.ndjson", TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_AUTHORIZATION),
    ]
    for filename, expected_status in cases:
        case_dir = tmp_path / filename
        log_dir = _fixture_logs(case_dir)
        (log_dir / filename).unlink()
        payload = build_tiny_live_order_payload_preview(
            log_dir=log_dir,
            risk_contract_config_path=_write_risk_contract_config(case_dir / "tiny_live_risk_contracts.json"),
            lane_controls_path=_write_lane_controls(case_dir / "lane_controls.json"),
            now=NOW,
        )

        assert payload["order_payload_preview_overall_status"] == expected_status
        assert payload["order_payload_preview_gate_matrix"]["order_payload_preview_ready"] is False


def test_preview_requires_valid_risk_contract_config(tmp_path: Path) -> None:
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    config = json.loads(risk_path.read_text(encoding="utf-8"))
    config["risk_contracts"][0]["max_notional_usdt"] = 45
    risk_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")

    payload = build_tiny_live_order_payload_preview(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=risk_path,
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["input_summary"]["risk_contract_valid"] is False
    assert payload["order_payload_preview_overall_status"] == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_RISK_CONTRACT


def test_preview_requires_evidence_ready(tmp_path: Path) -> None:
    payload = build_tiny_live_order_payload_preview(
        log_dir=_fixture_logs(tmp_path, evidence_ready=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["input_summary"]["r228_evidence_ready"] is False
    assert payload["order_payload_preview_overall_status"] == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_EVIDENCE


def test_preview_creates_non_executable_payload_shape_only(tmp_path: Path) -> None:
    payload = build_tiny_live_order_payload_preview(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    preview = payload["non_executable_order_payload_preview"]

    assert preview["preview_only"] is True
    assert preview["executable"] is False
    assert preview["signed"] is False
    assert preview["submit_allowed"] is False
    assert preview["binance_call_allowed"] is False
    assert preview["network_allowed"] is False
    assert preview["symbol"] == "BTCUSDT"
    assert preview["side"] == "SELL"
    assert preview["quantity_preview"] is None
    assert preview["quantity_source"] == "requires_precision_and_mark_price_later"
    assert preview["notional_cap_usdt"] == 44
    assert preview["max_loss_usdt"] == 4.44
    assert preview["leverage"] == 1
    assert preview["reduce_only"] is False
    assert preview["stop_required"] is True
    assert preview["take_profit_required"] is True
    assert preview["stop_payload_preview"]["reduce_only"] is True
    assert preview["take_profit_payload_preview"]["reduce_only"] is True
    assert payload["order_payload_preview_validation"]["valid"] is True
    assert payload["order_payload_preview_gate_matrix"]["order_payload_created"] is False
    assert payload["order_payload_preview_gate_matrix"]["executable_payload_created"] is False
    assert payload["order_payload_preview_gate_matrix"]["signed_order_request_created"] is False
    assert payload["order_payload_preview_gate_matrix"]["order_ready"] is False
    assert payload["order_payload_preview_gate_matrix"]["live_ready_today"] is False


def test_preview_safety_flags_preserve_non_actions(tmp_path: Path) -> None:
    payload = build_tiny_live_order_payload_preview(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "risk_contract_config_written",
        "lane_config_written",
        "lane_controls_written",
        "fisherman_config_written",
        "scheduler_config_written",
        "live_config_written",
        "live_authorization_written",
        "live_execution_enable_written",
        "lane_arm_written",
        "order_preflight_written",
        "order_payload_preview_recorded",
        "order_payload_allowed",
        "order_payload_created",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "signed_readonly_request_created",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "binance_account_endpoint_called",
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
    assert payload["safety"]["order_payload_preview_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-order-payload-preview",
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
    assert payload["order_payload_preview_recorded"] is False
    assert "tiny-live-order-payload-preview" in help_result.stdout


def _fixture_logs(tmp_path: Path, *, evidence_ready: bool = True) -> Path:
    log_dir = _r238_fixture_logs(tmp_path)
    _append(log_dir / "tiny_live_order_preflight_write_gate.ndjson", _r238_order_preflight_record())
    if not evidence_ready:
        (log_dir / "tiny_live_10_of_10_ready_packet.ndjson").unlink()
        _append(
            log_dir / "tiny_live_10_of_10_ready_packet.ndjson",
            {
                "event_type": "TINY_LIVE_10_OF_10_READY_PACKET",
                "status": "TINY_LIVE_10_OF_10_READY_PACKET_RECORDED",
                "packet_record_id": "r228_tiny_live_10_of_10_packet_fixture",
                "generated_at": NOW.isoformat(),
                "target_scope": {"official_lane_key": OFFICIAL},
                "tiny_live_gate_matrix": {
                    "evidence_ready": False,
                    "fisherman_ready": True,
                    "operator_review_ready": True,
                },
            },
        )
    return log_dir


def _r238_order_preflight_record() -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE",
        "status": "TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_WRITTEN",
        "gate_record_id": "r238_order_preflight_write_gate_fixture",
        "generated_at": NOW.isoformat(),
        "order_preflight_written": True,
        "write_order_preflight_requested": True,
        "confirmation_valid": True,
        "target_scope": {
            "official_lane_key": OFFICIAL,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "live_authorized": True,
            "live_execution_enabled": True,
            "lane_armed": True,
            "order_payload_allowed": False,
            "order_payload_created": False,
            "kill_switch_disabled": False,
        },
        "order_preflight": {
            "order_preflight_id": "r238_order_preflight_BTCUSDT_8m_short_ladder_close_50_618",
            "order_preflight_version": "tiny_live_order_preflight_v1",
            "created_by_phase": "R238_TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE",
            "created_at": NOW.isoformat(),
            "official_lane_key": OFFICIAL,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "source_order_preflight_preview_id": "r237_order_preflight_preview_fixture",
            "source_lane_arm_id": "r236_lane_arm_BTCUSDT_8m_short_ladder_close_50_618",
            "source_execution_enable_id": "r234_execution_enable_BTCUSDT_8m_short_ladder_close_50_618",
            "source_authorization_id": "r232_authorization_BTCUSDT_8m_short_ladder_close_50_618",
            "source_risk_contract_id": "r230_contract_BTCUSDT_8m_short_ladder_close_50_618",
            "risk_contract_config_ready": True,
            "evidence_ready": True,
            "fisherman_ready": True,
            "live_authorized": True,
            "live_execution_enabled": True,
            "lane_armed": True,
            "order_preflight_scope": "tiny_live_single_lane",
            "order_preflight_status": "PREFLIGHT_WRITTEN_NO_PAYLOAD_NO_ORDER",
            "order_preflight_written": True,
            "order_payload_allowed": False,
            "order_payload_created": False,
            "executable_payload_created": False,
            "signed_order_request_created": False,
            "signed_trading_request_created": False,
            "order_placed": False,
            "binance_call_allowed": False,
            "network_allowed": False,
            "kill_switch_required": True,
            "kill_switch_disabled": False,
            "operator_final_approval_required": True,
            "order_payload_preview_required_later": True,
            "binance_connectivity_check_required_later": True,
        },
        "order_preflight_validation": {"valid": True, "errors": [], "warnings": []},
    }
