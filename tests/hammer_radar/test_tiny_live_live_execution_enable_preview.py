from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_live_execution_enable_preview import (
    CONFIRM_TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_AUTHORIZATION,
    TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_EVIDENCE,
    TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_RISK_CONTRACT,
    TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY,
    TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY_FOR_FUTURE_GATE,
    TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDED,
    TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_REJECTED,
    build_tiny_live_live_execution_enable_preview,
    load_tiny_live_live_execution_enable_preview_records,
)

NOW = datetime(2026, 6, 9, 8, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")

    payload = build_tiny_live_live_execution_enable_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED"
    assert payload["execution_enable_preview_recorded"] is False
    assert payload["execution_enable_preview_record_id"] is None
    assert payload["record_execution_enable_preview_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_tiny_live_live_execution_enable_preview(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        record_execution_enable_preview=True,
        confirm_tiny_live_live_execution_enable_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["execution_enable_preview_recorded"] is False
    assert load_tiny_live_live_execution_enable_preview_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_preview_only(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    lane_path = _write_lane_controls(tmp_path / "lane_controls.json")
    env_path = tmp_path / ".env"
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")
    before_env_file = env_path.read_text(encoding="utf-8")

    payload = build_tiny_live_live_execution_enable_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        record_execution_enable_preview=True,
        confirm_tiny_live_live_execution_enable_preview=(
            CONFIRM_TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDING_PHRASE
        ),
        now=NOW,
    )
    records = load_tiny_live_live_execution_enable_preview_records(log_dir=log_dir, limit=0)

    assert payload["status"] == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_RECORDED
    assert payload["execution_enable_preview_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW"
    assert records[0]["execution_enable_preview_recorded"] is True
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert env_path.read_text(encoding="utf-8") == before_env_file
    assert records[0]["safety"]["live_execution_enable_written"] is False
    assert records[0]["safety"]["live_execution_enabled"] is False
    assert records[0]["safety"]["order_payload_created"] is False


def test_preview_requires_r232_authorization_artifact(tmp_path: Path) -> None:
    payload = build_tiny_live_live_execution_enable_preview(
        log_dir=_fixture_logs(tmp_path, include_r232=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["input_summary"]["r232_authorization_found"] is False
    assert payload["live_execution_enable_gate_matrix"]["live_execution_enable_preview_ready"] is False
    assert (
        payload["live_execution_enable_preview_overall_status"]
        == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_AUTHORIZATION
    )


def test_preview_requires_valid_risk_contract_config(tmp_path: Path) -> None:
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    config = json.loads(risk_path.read_text(encoding="utf-8"))
    config["risk_contracts"][0]["live_execution_enabled"] = True
    risk_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")

    payload = build_tiny_live_live_execution_enable_preview(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["input_summary"]["risk_contract_valid"] is False
    assert payload["live_execution_enable_gate_matrix"]["live_execution_enable_preview_ready"] is False
    assert (
        payload["live_execution_enable_preview_overall_status"]
        == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_RISK_CONTRACT
    )


def test_preview_requires_evidence_ready(tmp_path: Path) -> None:
    payload = build_tiny_live_live_execution_enable_preview(
        log_dir=_fixture_logs(tmp_path, evidence_ready=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["input_summary"]["r228_evidence_ready"] is False
    assert payload["live_execution_enable_gate_matrix"]["live_execution_enable_preview_ready"] is False
    assert (
        payload["live_execution_enable_preview_overall_status"]
        == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_EVIDENCE
    )


def test_preview_requires_live_authorized_true_in_artifact(tmp_path: Path) -> None:
    payload = build_tiny_live_live_execution_enable_preview(
        log_dir=_fixture_logs(tmp_path, live_authorized=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["input_summary"]["live_authorized"] is False
    assert payload["live_execution_enable_gate_matrix"]["live_execution_enable_preview_ready"] is False
    assert (
        payload["live_execution_enable_preview_overall_status"]
        == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_BLOCKED_BY_AUTHORIZATION
    )


def test_preview_keeps_live_execution_lane_and_order_false(tmp_path: Path) -> None:
    payload = build_tiny_live_live_execution_enable_preview(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    matrix = payload["live_execution_enable_gate_matrix"]

    assert matrix["live_execution_enable_preview_ready"] is True
    assert matrix["live_execution_enabled"] is False
    assert matrix["lane_armed"] is False
    assert matrix["order_ready"] is False
    assert matrix["live_ready_today"] is False
    assert payload["target_scope"]["live_execution_enabled"] is False
    assert payload["target_scope"]["lane_armed"] is False
    assert payload["target_scope"]["order_payload_allowed"] is False
    assert payload["safety"]["live_execution_enable_written"] is False
    assert payload["safety"]["live_execution_enabled"] is False
    assert payload["safety"]["lane_armed"] is False
    assert payload["safety"]["order_payload_created"] is False
    assert (
        payload["live_execution_enable_preview_overall_status"]
        == TINY_LIVE_LIVE_EXECUTION_ENABLE_PREVIEW_READY_FOR_FUTURE_GATE
    )


def test_preview_does_not_create_payload_write_configs_mutate_env_or_call_network(tmp_path: Path) -> None:
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
        payload = build_tiny_live_live_execution_enable_preview(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
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
    assert payload["safety"]["live_execution_enable_preview_only"] is True


def test_preview_keeps_official_lane_unchanged(tmp_path: Path) -> None:
    payload = build_tiny_live_live_execution_enable_preview(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["risk_contract_summary"]["official_lane_key"] == OFFICIAL
    assert payload["target_scope"]["live_authorized"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-live-execution-enable-preview",
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
    assert payload["execution_enable_preview_recorded"] is False
    assert "tiny-live-live-execution-enable-preview" in help_result.stdout


def _fixture_logs(
    tmp_path: Path,
    *,
    include_r232: bool = True,
    evidence_ready: bool = True,
    fisherman_ready: bool = True,
    live_authorized: bool = True,
) -> Path:
    log_dir = tmp_path / "logs"
    _append(log_dir / "tiny_live_10_of_10_ready_packet.ndjson", _r228_packet_record(evidence_ready, fisherman_ready))
    _append(log_dir / "tiny_live_risk_contract_config_write_gate.ndjson", _r230_gate_record())
    _append(log_dir / "tiny_live_live_authorization_preview.ndjson", _r231_preview_record())
    if include_r232:
        _append(log_dir / "tiny_live_live_authorization_write_gate.ndjson", _r232_authorization_record(live_authorized))
    _append(log_dir / "paper_outcomes.ndjson", {"signal_id": "ordinary-signal", "outcome": "win"})
    _append(log_dir / "strategy_performance.ndjson", {"lane_key": "ordinary", "sample_size": 30, "win_rate_pct": 60.0})
    _append(log_dir / "strategy_promotion_status.ndjson", {"lane_key": "ordinary", "promotion_allowed": False})
    return log_dir


def _r228_packet_record(evidence_ready: bool = True, fisherman_ready: bool = True) -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_10_OF_10_READY_PACKET",
        "status": "TINY_LIVE_10_OF_10_READY_PACKET_RECORDED",
        "packet_record_id": "r228_tiny_live_10_of_10_packet_fixture",
        "generated_at": NOW.isoformat(),
        "target_scope": {"official_lane_key": OFFICIAL},
        "capture_threshold_recheck": {
            "official_lane_key": OFFICIAL,
            "evidence_threshold_ready": evidence_ready,
        },
        "fisherman_health_recheck": {"fisherman_ready": fisherman_ready},
        "tiny_live_gate_matrix": {
            "evidence_ready": evidence_ready,
            "fisherman_ready": fisherman_ready,
            "operator_review_ready": evidence_ready and fisherman_ready,
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


def _r232_authorization_record(live_authorized: bool = True) -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE",
        "status": "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_WRITTEN",
        "gate_record_id": "r232_authorization_write_gate_fixture",
        "generated_at": NOW.isoformat(),
        "authorization_written": True,
        "target_scope": {"official_lane_key": OFFICIAL},
        "authorization": {
            "authorization_id": "r232_authorization_BTCUSDT_8m_short_ladder_close_50_618",
            "authorization_status": "AUTHORIZED_NOT_ARMED_NOT_EXECUTABLE",
            "official_lane_key": OFFICIAL,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "source_live_authorization_preview_id": "r231_live_authorization_preview_fixture",
            "source_risk_contract_id": "r230_contract_BTCUSDT_8m_short_ladder_close_50_618",
            "risk_contract_config_ready": True,
            "evidence_ready": True,
            "fisherman_ready": True,
            "live_authorized": live_authorized,
            "live_execution_enabled": False,
            "lane_armed": False,
            "order_payload_allowed": False,
            "binance_call_allowed": False,
            "kill_switch_required": True,
            "operator_final_approval_required": True,
            "live_execution_enable_required_later": True,
            "lane_arm_required_later": True,
            "order_preflight_required_later": True,
        },
        "authorization_validation": {"valid": live_authorized, "errors": [], "warnings": []},
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
