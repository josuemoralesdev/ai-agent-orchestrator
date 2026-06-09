from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    CONFIRM_TINY_LIVE_LIVE_AUTHORIZATION_WRITE_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_READY,
    TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_REJECTED,
    TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_WRITTEN,
    build_tiny_live_live_authorization_write_gate,
    build_live_authorization_object,
    load_tiny_live_live_authorization_write_gate_records,
    validate_live_authorization_object,
)

NOW = datetime(2026, 6, 9, 7, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_authorization(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")

    payload = build_tiny_live_live_authorization_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_READY
    assert payload["authorization_written"] is False
    assert payload["record_gate_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["authorization_write_preview"]["would_write"] is True
    assert payload["authorization_write_preview"]["authorization_artifact"] == "ledger_only"
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_and_writes_no_authorization(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")

    payload = build_tiny_live_live_authorization_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        write_live_authorization=True,
        confirm_tiny_live_live_authorization_write="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_REJECTED
    assert payload["authorization_written"] is False
    assert payload["confirmation_valid"] is False
    assert payload["authorization_write_overall_status"] == "TINY_LIVE_AUTHORIZATION_WRITE_REJECTED_BAD_CONFIRMATION"
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_exact_confirmation_writes_only_authorization_artifact(tmp_path: Path) -> None:
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
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_tiny_live_live_authorization_write_gate(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            write_live_authorization=True,
            confirm_tiny_live_live_authorization_write=CONFIRM_TINY_LIVE_LIVE_AUTHORIZATION_WRITE_PHRASE,
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert dict(os.environ) == before_env
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert env_path.read_text(encoding="utf-8") == before_env_file
    assert {name: path.read_text(encoding="utf-8") for name, path in protected_logs.items()} == before_logs

    records = load_tiny_live_live_authorization_write_gate_records(log_dir=log_dir, limit=0)
    assert payload["status"] == TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_WRITTEN
    assert payload["authorization_written"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE"
    assert records[0]["authorization_written"] is True
    assert records[0]["authorization"]["live_authorized"] is True
    assert records[0]["authorization"]["live_execution_enabled"] is False
    assert records[0]["authorization"]["lane_armed"] is False
    assert records[0]["authorization"]["order_payload_allowed"] is False
    assert records[0]["authorization"]["binance_call_allowed"] is False
    assert payload["post_write_verification"]["matching_authorization_found"] is True
    assert payload["post_write_verification"]["matching_authorization_valid"] is True
    assert payload["post_write_verification"]["live_authorized"] is True
    assert payload["post_write_verification"]["live_execution_enabled"] is False
    assert payload["post_write_verification"]["lane_armed"] is False
    assert payload["post_write_verification"]["order_payload_created"] is False


def test_live_authorization_object_validates() -> None:
    authorization = build_live_authorization_object(
        latest_r231={"authorization_preview_record_id": "r231_fixture"},
        latest_r230={},
        latest_r228={},
        risk_contract_config={"matching_risk_contract": {"contract_id": "r230_contract_BTCUSDT_8m_short_ladder_close_50_618"}},
        input_summary={
            "risk_contract_config_ready": True,
            "r228_evidence_ready": True,
            "fisherman_ready": True,
        },
        now=NOW,
    )

    validation = validate_live_authorization_object(authorization)

    assert validation["valid"] is True
    assert authorization["live_authorized"] is True
    assert authorization["live_execution_enabled"] is False
    assert authorization["lane_armed"] is False
    assert authorization["order_payload_allowed"] is False
    assert authorization["binance_call_allowed"] is False


def test_safety_flags_remain_false_for_live_execution_lane_order_and_network(tmp_path: Path) -> None:
    payload = build_tiny_live_live_authorization_write_gate(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
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
        "order_payload_created",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "signed_readonly_request_created",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "network_allowed",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "secrets_shown",
        "global_live_flags_changed",
        "kill_switch_disabled",
        "live_authorization_created",
        "live_authorization_written",
        "live_execution_enabled",
        "lane_armed",
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
    assert payload["safety"]["authorization_write_gate_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-live-authorization-write-gate",
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
    assert payload["authorization_written"] is False
    assert "tiny-live-live-authorization-write-gate" in help_result.stdout


def _fixture_logs(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    _append(log_dir / "tiny_live_10_of_10_ready_packet.ndjson", _r228_packet_record())
    _append(log_dir / "tiny_live_risk_contract_config_write_gate.ndjson", _r230_gate_record())
    _append(log_dir / "tiny_live_live_authorization_preview.ndjson", _r231_preview_record())
    _append(log_dir / "paper_outcomes.ndjson", {"signal_id": "ordinary-signal", "outcome": "win"})
    _append(log_dir / "strategy_performance.ndjson", {"lane_key": "ordinary", "sample_size": 30, "win_rate_pct": 60.0})
    _append(log_dir / "strategy_promotion_status.ndjson", {"lane_key": "ordinary", "promotion_allowed": False})
    return log_dir


def _r228_packet_record() -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_10_OF_10_READY_PACKET",
        "status": "TINY_LIVE_10_OF_10_READY_PACKET_RECORDED",
        "packet_record_id": "r228_tiny_live_10_of_10_packet_fixture",
        "generated_at": NOW.isoformat(),
        "target_scope": {"official_lane_key": OFFICIAL},
        "capture_threshold_recheck": {
            "official_lane_key": OFFICIAL,
            "evidence_threshold_ready": True,
        },
        "fisherman_health_recheck": {"fisherman_ready": True},
        "tiny_live_gate_matrix": {
            "evidence_ready": True,
            "fisherman_ready": True,
            "operator_review_ready": True,
        },
    }


def _r230_gate_record() -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE",
        "status": "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_WRITTEN",
        "gate_record_id": "r230_config_write_gate_fixture",
        "generated_at": NOW.isoformat(),
        "config_written": True,
        "target_scope": {"official_lane_key": OFFICIAL, "live_authorized": False},
        "post_write_verification": {
            "matching_contract_found": True,
            "matching_contract_valid": True,
            "live_authorized": False,
            "live_execution_enabled": False,
            "order_payload_created": False,
        },
        "config_write_overall_status": "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITTEN_LIVE_AUTH_REQUIRED_LATER",
    }


def _r231_preview_record() -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW",
        "status": "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDED",
        "authorization_preview_record_id": "r231_live_authorization_preview_fixture",
        "generated_at": NOW.isoformat(),
        "target_scope": {"official_lane_key": OFFICIAL, "live_authorized": False},
        "input_summary": {
            "r228_packet_found": True,
            "r228_evidence_ready": True,
            "r228_fisherman_ready": True,
            "r230_config_gate_found": True,
            "risk_contract_config_found": True,
            "matching_risk_contract_found": True,
            "matching_risk_contract_valid": True,
        },
        "live_authorization_requirement_preview": {
            "authorization_preview_id": "r231_live_authorization_preview_inner_fixture",
            "risk_contract_reference": "r230_contract_BTCUSDT_8m_short_ladder_close_50_618",
        },
        "live_authorization_gate_matrix": {
            "evidence_ready": True,
            "fisherman_ready": True,
            "risk_contract_config_ready": True,
            "live_authorization_preview_ready": True,
            "live_authorization_written": False,
            "live_execution_ready": False,
            "lane_armed": False,
            "order_ready": False,
            "live_ready_today": False,
        },
        "live_authorization_preview_overall_status": "TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY_FOR_FUTURE_GATE",
    }


def _write_risk_contract_config(path: Path) -> Path:
    payload = {
        "risk_contracts": [
            {
                "approval_status": "CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED",
                "approved": False,
                "binance_call_forbidden_until_live_gate": True,
                "contract_id": "r230_contract_BTCUSDT_8m_short_ladder_close_50_618",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "kill_switch_required": True,
                "leverage": 1,
                "live_authorization_required_later": True,
                "live_authorized": False,
                "live_execution_enabled": False,
                "max_account_risk_usdt": 44,
                "max_loss_usdt": 4.44,
                "max_margin_usdt": 44,
                "max_notional_usdt": 44,
                "official_lane_key": OFFICIAL,
                "operator_final_approval_required": True,
                "order_payload_forbidden_until_live_gate": True,
                "protective_stop_required": True,
                "stop_required": True,
                "symbol": "BTCUSDT",
                "take_profit_required": True,
                "timeframe": "8m",
                "tiny_live_margin_usdt": 44,
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_lane_controls(path: Path) -> Path:
    payload = {
        "schema_version": "1.0",
        "default_mode": "disabled",
        "lanes": [
            {
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "mode": "paper",
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
