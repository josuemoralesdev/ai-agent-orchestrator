from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_order_preflight_write_gate import (
    CONFIRM_TINY_LIVE_ORDER_PREFLIGHT_WRITE_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_READY,
    TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_REJECTED,
    TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_WRITTEN,
    build_order_preflight_object,
    build_tiny_live_order_preflight_write_gate,
    load_tiny_live_order_preflight_write_gate_records,
    validate_order_preflight_object,
)
from tests.hammer_radar.test_tiny_live_order_preflight_preview import (
    _append,
    _fixture_logs as _r237_fixture_logs,
    _write_lane_controls,
    _write_risk_contract_config,
)

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_order_preflight_artifact(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    payload = build_tiny_live_order_preflight_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_READY
    assert payload["order_preflight_written"] is False
    assert payload["write_order_preflight_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["order_preflight_write_preview"]["would_write"] is True
    assert payload["order_preflight_write_preview"]["order_preflight_artifact"] == "ledger_only"
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_and_writes_no_artifact(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    payload = build_tiny_live_order_preflight_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        write_order_preflight=True,
        confirm_tiny_live_order_preflight_write="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["order_preflight_written"] is False
    assert payload["order_preflight_write_overall_status"] == "TINY_LIVE_ORDER_PREFLIGHT_WRITE_REJECTED_BAD_CONFIRMATION"
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_exact_confirmation_writes_only_order_preflight_artifact(tmp_path: Path) -> None:
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
        payload = build_tiny_live_order_preflight_write_gate(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            write_order_preflight=True,
            confirm_tiny_live_order_preflight_write=CONFIRM_TINY_LIVE_ORDER_PREFLIGHT_WRITE_PHRASE,
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

    records = load_tiny_live_order_preflight_write_gate_records(log_dir=log_dir, limit=0)
    assert payload["status"] == TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_WRITTEN
    assert payload["order_preflight_written"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE"
    artifact = records[0]["order_preflight"]
    assert artifact["live_authorized"] is True
    assert artifact["live_execution_enabled"] is True
    assert artifact["lane_armed"] is True
    assert artifact["order_payload_allowed"] is False
    assert artifact["order_payload_created"] is False
    assert artifact["executable_payload_created"] is False
    assert artifact["signed_order_request_created"] is False
    assert artifact["signed_trading_request_created"] is False
    assert artifact["order_placed"] is False
    assert artifact["binance_call_allowed"] is False
    assert artifact["network_allowed"] is False
    assert artifact["kill_switch_disabled"] is False
    assert payload["post_write_verification"]["matching_order_preflight_found"] is True
    assert payload["post_write_verification"]["matching_order_preflight_valid"] is True
    assert payload["order_preflight_write_gate_matrix"]["order_payload_created"] is False
    assert payload["order_preflight_write_gate_matrix"]["order_ready"] is False
    assert payload["order_preflight_write_gate_matrix"]["live_ready_today"] is False
    assert payload["operator_order_preflight_write_review_packet"]["operator_should_create_order_payload"] is False
    assert payload["operator_order_preflight_write_review_packet"]["operator_should_place_order"] is False


def test_order_preflight_object_validates() -> None:
    artifact = build_order_preflight_object(
        latest_r237={"order_preflight_preview_record_id": "r237_fixture"},
        latest_r236={"lane_arm": {"lane_arm_id": "r236_lane_arm_BTCUSDT_8m_short_ladder_close_50_618"}},
        latest_r234={"execution_enable": {"execution_enable_id": "r234_execution_enable_BTCUSDT_8m_short_ladder_close_50_618"}},
        latest_r232={"authorization": {"authorization_id": "r232_authorization_BTCUSDT_8m_short_ladder_close_50_618"}},
        latest_r230={},
        latest_r228={},
        input_summary={
            "risk_contract_valid": True,
            "r228_evidence_ready": True,
            "fisherman_ready": True,
            "live_authorized": True,
            "live_execution_enabled": True,
            "lane_armed": True,
        },
        now=NOW,
    )

    validation = validate_order_preflight_object(artifact)

    assert validation["valid"] is True
    assert artifact["live_authorized"] is True
    assert artifact["live_execution_enabled"] is True
    assert artifact["lane_armed"] is True
    assert artifact["order_payload_allowed"] is False
    assert artifact["order_payload_created"] is False
    assert artifact["executable_payload_created"] is False
    assert artifact["signed_order_request_created"] is False
    assert artifact["signed_trading_request_created"] is False
    assert artifact["order_placed"] is False
    assert artifact["binance_call_allowed"] is False
    assert artifact["network_allowed"] is False
    assert artifact["kill_switch_disabled"] is False


def test_safety_flags_preserve_non_actions(tmp_path: Path) -> None:
    payload = build_tiny_live_order_preflight_write_gate(
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
        "live_execution_enabled",
        "lane_armed",
        "order_payload_allowed",
        "order_payload_created",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "registry_config_written",
        "scoring_config_written",
        "matrix_config_written",
        "ledger_rewritten",
        "destructive_write",
        "historical_ledger_rewritten",
        "normalized_rows_appended",
        "paper_outcome_ledger_rewritten",
        "paper_outcomes_appended",
        "strategy_performance_appended",
        "strategy_promotion_status_appended",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "binance_account_endpoint_called",
        "network_allowed",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "secrets_shown",
        "global_live_flags_changed",
        "kill_switch_disabled",
        "live_authorization_created",
        "signal_origin_promoted",
        "lane_promoted",
        "official_tiny_live_lane_changed",
        "alternate_lane_promoted",
        "betrayal_live_authorized",
        "betrayal_promoted",
        "position_permission_created",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["paper_live_separation_intact"] is True
    assert payload["safety"]["order_preflight_write_gate_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-order-preflight-write-gate",
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
    assert payload["order_preflight_written"] is False
    assert "tiny-live-order-preflight-write-gate" in help_result.stdout


def _fixture_logs(tmp_path: Path) -> Path:
    log_dir = _r237_fixture_logs(tmp_path)
    _append(log_dir / "tiny_live_order_preflight_preview.ndjson", _r237_preview_record())
    return log_dir


def _r237_preview_record() -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW",
        "status": "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDED",
        "order_preflight_preview_record_id": "r237_order_preflight_preview_fixture",
        "generated_at": NOW.isoformat(),
        "order_preflight_preview_recorded": True,
        "target_scope": {"official_lane_key": OFFICIAL},
        "input_summary": {
            "r228_evidence_ready": True,
            "r228_fisherman_ready": True,
            "risk_contract_valid": True,
            "r232_authorization_valid": True,
            "r234_execution_enable_valid": True,
            "r236_lane_arm_valid": True,
            "live_authorized": True,
            "live_execution_enabled": True,
            "lane_armed": True,
            "order_payload_created": False,
        },
        "order_preflight_gate_matrix": {
            "evidence_ready": True,
            "fisherman_ready": True,
            "risk_contract_config_ready": True,
            "live_authorization_written": True,
            "live_authorized": True,
            "live_execution_enable_written": True,
            "live_execution_enabled": True,
            "lane_arm_written": True,
            "lane_armed": True,
            "order_preflight_preview_ready": True,
            "order_payload_created": False,
            "order_ready": False,
            "live_ready_today": False,
        },
        "order_preflight_requirement_preview": {
            "order_preflight_preview_id": "r237_order_preflight_preview_BTCUSDT_8m_short_ladder_close_50_618_fixture",
            "official_lane_key": OFFICIAL,
        },
        "order_preflight_preview_overall_status": "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY_FOR_FUTURE_GATE",
    }
