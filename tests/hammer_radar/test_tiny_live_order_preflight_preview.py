from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_order_preflight_preview import (
    CONFIRM_TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_AUTHORIZATION,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EVIDENCE,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_LANE_ARM,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_RISK_CONTRACT,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY_FOR_FUTURE_GATE,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDED,
    TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_REJECTED,
    build_tiny_live_order_preflight_preview,
    load_tiny_live_order_preflight_preview_records,
)

NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    payload = build_tiny_live_order_preflight_preview(
        log_dir=log_dir,
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY
    assert payload["order_preflight_preview_recorded"] is False
    assert payload["record_order_preflight_preview_requested"] is False
    assert payload["confirmation_valid"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    payload = build_tiny_live_order_preflight_preview(
        log_dir=log_dir,
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        record_order_preflight_preview=True,
        confirm_tiny_live_order_preflight_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["order_preflight_preview_recorded"] is False
    assert load_tiny_live_order_preflight_preview_records(log_dir=log_dir, limit=0) == []


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
        payload = build_tiny_live_order_preflight_preview(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            record_order_preflight_preview=True,
            confirm_tiny_live_order_preflight_preview=(
                CONFIRM_TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDING_PHRASE
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

    records = load_tiny_live_order_preflight_preview_records(log_dir=log_dir, limit=0)
    assert payload["status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_RECORDED
    assert payload["order_preflight_preview_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW"
    assert records[0]["safety"]["order_preflight_preview_only"] is True
    assert records[0]["safety"]["order_preflight_written"] is False
    assert records[0]["safety"]["order_payload_created"] is False
    assert records[0]["safety"]["order_placed"] is False


def test_preview_requires_r236_lane_arm_artifact(tmp_path: Path) -> None:
    payload = build_tiny_live_order_preflight_preview(
        log_dir=_fixture_logs(tmp_path, include_r236=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["input_summary"]["r236_lane_arm_found"] is False
    assert payload["order_preflight_gate_matrix"]["order_preflight_preview_ready"] is False
    assert payload["order_preflight_preview_overall_status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_LANE_ARM


def test_preview_requires_r234_execution_enable_artifact(tmp_path: Path) -> None:
    payload = build_tiny_live_order_preflight_preview(
        log_dir=_fixture_logs(tmp_path, include_r234=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["input_summary"]["r234_execution_enable_found"] is False
    assert payload["order_preflight_preview_overall_status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE


def test_preview_requires_r232_authorization_artifact(tmp_path: Path) -> None:
    payload = build_tiny_live_order_preflight_preview(
        log_dir=_fixture_logs(tmp_path, include_r232=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["input_summary"]["r232_authorization_found"] is False
    assert payload["order_preflight_preview_overall_status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_AUTHORIZATION


def test_preview_requires_valid_risk_contract_config(tmp_path: Path) -> None:
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    config = json.loads(risk_path.read_text(encoding="utf-8"))
    config["risk_contracts"][0]["order_payload_forbidden_until_live_gate"] = False
    risk_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")

    payload = build_tiny_live_order_preflight_preview(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=risk_path,
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["input_summary"]["risk_contract_valid"] is False
    assert payload["order_preflight_preview_overall_status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_RISK_CONTRACT


def test_preview_requires_evidence_ready_and_fisherman_ready(tmp_path: Path) -> None:
    evidence_payload = build_tiny_live_order_preflight_preview(
        log_dir=_fixture_logs(tmp_path / "evidence", evidence_ready=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "evidence" / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "evidence" / "lane_controls.json"),
        now=NOW,
    )
    fisherman_payload = build_tiny_live_order_preflight_preview(
        log_dir=_fixture_logs(tmp_path / "fisherman", fisherman_ready=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "fisherman" / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "fisherman" / "lane_controls.json"),
        now=NOW,
    )

    assert evidence_payload["input_summary"]["r228_evidence_ready"] is False
    assert evidence_payload["order_preflight_preview_overall_status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EVIDENCE
    assert fisherman_payload["input_summary"]["r228_fisherman_ready"] is False
    assert fisherman_payload["order_preflight_preview_overall_status"] == "TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_FISHERMAN"


def test_preview_requires_live_authorized_execution_enabled_and_lane_armed(tmp_path: Path) -> None:
    auth_payload = build_tiny_live_order_preflight_preview(
        log_dir=_fixture_logs(tmp_path / "auth", live_authorized=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "auth" / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "auth" / "lane_controls.json"),
        now=NOW,
    )
    execution_payload = build_tiny_live_order_preflight_preview(
        log_dir=_fixture_logs(tmp_path / "execution", live_execution_enabled=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "execution" / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "execution" / "lane_controls.json"),
        now=NOW,
    )
    lane_payload = build_tiny_live_order_preflight_preview(
        log_dir=_fixture_logs(tmp_path / "lane", lane_armed=False),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "lane" / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane" / "lane_controls.json"),
        now=NOW,
    )

    assert auth_payload["input_summary"]["live_authorized"] is False
    assert auth_payload["order_preflight_preview_overall_status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_AUTHORIZATION
    assert execution_payload["input_summary"]["live_execution_enabled"] is False
    assert execution_payload["order_preflight_preview_overall_status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE
    assert lane_payload["input_summary"]["lane_armed"] is False
    assert lane_payload["order_preflight_preview_overall_status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_BLOCKED_BY_LANE_ARM


def test_preview_keeps_order_payload_order_ready_and_official_lane_unchanged(tmp_path: Path) -> None:
    payload = build_tiny_live_order_preflight_preview(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    matrix = payload["order_preflight_gate_matrix"]

    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["target_scope"]["order_payload_allowed"] is False
    assert payload["target_scope"]["order_payload_created"] is False
    assert matrix["order_preflight_preview_ready"] is True
    assert matrix["order_payload_created"] is False
    assert matrix["order_ready"] is False
    assert matrix["live_ready_today"] is False
    assert payload["lane_controls_readonly_summary"]["read_only"] is True
    assert payload["lane_controls_readonly_summary"]["would_mutate"] is False
    assert payload["order_preflight_preview_overall_status"] == TINY_LIVE_ORDER_PREFLIGHT_PREVIEW_READY_FOR_FUTURE_GATE


def test_preview_does_not_write_configs_env_or_call_network(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    lane_path = _write_lane_controls(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_order_preflight_preview(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
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
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "signed_readonly_request_created",
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
    assert payload["safety"]["order_preflight_preview_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-order-preflight-preview",
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
    assert payload["order_preflight_preview_recorded"] is False
    assert "tiny-live-order-preflight-preview" in help_result.stdout


def _fixture_logs(
    tmp_path: Path,
    *,
    include_r232: bool = True,
    include_r234: bool = True,
    include_r236: bool = True,
    evidence_ready: bool = True,
    fisherman_ready: bool = True,
    live_authorized: bool = True,
    live_execution_enabled: bool = True,
    lane_armed: bool = True,
) -> Path:
    log_dir = tmp_path / "logs"
    _append(log_dir / "tiny_live_10_of_10_ready_packet.ndjson", _r228_packet_record(evidence_ready=evidence_ready, fisherman_ready=fisherman_ready))
    _append(log_dir / "tiny_live_risk_contract_config_write_gate.ndjson", _r230_gate_record())
    if include_r232:
        _append(log_dir / "tiny_live_live_authorization_write_gate.ndjson", _r232_authorization_record(live_authorized=live_authorized))
    if include_r234:
        _append(
            log_dir / "tiny_live_live_execution_enable_write_gate.ndjson",
            _r234_execution_enable_record(live_authorized=live_authorized, live_execution_enabled=live_execution_enabled),
        )
    _append(log_dir / "tiny_live_lane_arm_preview.ndjson", _r235_preview_record())
    if include_r236:
        _append(
            log_dir / "tiny_live_lane_arm_write_gate.ndjson",
            _r236_lane_arm_record(
                live_authorized=live_authorized,
                live_execution_enabled=live_execution_enabled,
                lane_armed=lane_armed,
            ),
        )
    _append(log_dir / "paper_outcomes.ndjson", {"signal_id": "ordinary-signal", "outcome": "win"})
    _append(log_dir / "strategy_performance.ndjson", {"lane_key": "ordinary", "sample_size": 30})
    _append(log_dir / "strategy_promotion_status.ndjson", {"lane_key": "ordinary", "promotion_allowed": False})
    return log_dir


def _r228_packet_record(*, evidence_ready: bool = True, fisherman_ready: bool = True) -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_10_OF_10_READY_PACKET",
        "status": "TINY_LIVE_10_OF_10_READY_PACKET_RECORDED",
        "packet_record_id": "r228_tiny_live_10_of_10_packet_fixture",
        "generated_at": NOW.isoformat(),
        "target_scope": {"official_lane_key": OFFICIAL},
        "tiny_live_gate_matrix": {
            "evidence_ready": evidence_ready,
            "fisherman_ready": fisherman_ready,
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
        "target_scope": {"official_lane_key": OFFICIAL},
        "post_write_verification": {"matching_contract_found": True, "matching_contract_valid": True},
    }


def _r232_authorization_record(*, live_authorized: bool = True) -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE",
        "status": "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_WRITTEN",
        "gate_record_id": "r232_authorization_write_gate_fixture",
        "generated_at": NOW.isoformat(),
        "authorization_written": True,
        "target_scope": {"official_lane_key": OFFICIAL},
        "authorization": {
            "authorization_id": "r232_authorization_BTCUSDT_8m_short_ladder_close_50_618",
            "authorization_version": "tiny_live_authorization_v1",
            "created_by_phase": "R232_TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE",
            "created_at": NOW.isoformat(),
            "official_lane_key": OFFICIAL,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "source_live_authorization_preview_id": "r231_fixture",
            "source_risk_contract_id": "r230_contract_BTCUSDT_8m_short_ladder_close_50_618",
            "risk_contract_config_ready": True,
            "evidence_ready": True,
            "fisherman_ready": True,
            "authorization_scope": "tiny_live_single_lane",
            "authorization_status": "AUTHORIZED_NOT_ARMED_NOT_EXECUTABLE",
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
    }


def _r234_execution_enable_record(*, live_authorized: bool = True, live_execution_enabled: bool = True) -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE",
        "status": "TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE_WRITTEN",
        "gate_record_id": "r234_execution_enable_write_gate_fixture",
        "generated_at": NOW.isoformat(),
        "execution_enable_written": True,
        "target_scope": {"official_lane_key": OFFICIAL},
        "execution_enable": {
            "execution_enable_id": "r234_execution_enable_BTCUSDT_8m_short_ladder_close_50_618",
            "execution_enable_version": "tiny_live_execution_enable_v1",
            "created_by_phase": "R234_TINY_LIVE_LIVE_EXECUTION_ENABLE_WRITE_GATE",
            "created_at": NOW.isoformat(),
            "official_lane_key": OFFICIAL,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "source_execution_enable_preview_id": "r233_fixture",
            "source_authorization_id": "r232_authorization_BTCUSDT_8m_short_ladder_close_50_618",
            "source_risk_contract_id": "r230_contract_BTCUSDT_8m_short_ladder_close_50_618",
            "risk_contract_config_ready": True,
            "evidence_ready": True,
            "fisherman_ready": True,
            "live_authorized": live_authorized,
            "execution_enable_scope": "tiny_live_single_lane",
            "execution_enable_status": "LIVE_EXECUTION_ENABLED_NOT_ARMED_NOT_EXECUTABLE",
            "live_execution_enabled": live_execution_enabled,
            "lane_armed": False,
            "order_payload_allowed": False,
            "binance_call_allowed": False,
            "kill_switch_required": True,
            "operator_final_approval_required": True,
            "lane_arm_required_later": True,
            "order_preflight_required_later": True,
            "binance_connectivity_check_required_later": True,
        },
    }


def _r235_preview_record() -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_LANE_ARM_PREVIEW",
        "status": "TINY_LIVE_LANE_ARM_PREVIEW_RECORDED",
        "lane_arm_preview_record_id": "r235_lane_arm_preview_fixture",
        "generated_at": NOW.isoformat(),
        "target_scope": {"official_lane_key": OFFICIAL},
        "lane_arm_gate_matrix": {
            "evidence_ready": True,
            "fisherman_ready": True,
            "risk_contract_config_ready": True,
            "live_authorization_written": True,
            "live_authorized": True,
            "live_execution_enable_written": True,
            "live_execution_enabled": True,
            "lane_arm_preview_ready": True,
            "lane_armed": False,
            "order_ready": False,
            "live_ready_today": False,
        },
        "lane_arm_preview_overall_status": "TINY_LIVE_LANE_ARM_PREVIEW_READY_FOR_FUTURE_GATE",
    }


def _r236_lane_arm_record(
    *,
    live_authorized: bool = True,
    live_execution_enabled: bool = True,
    lane_armed: bool = True,
) -> dict[str, object]:
    lane_arm = {
        "lane_arm_id": "r236_lane_arm_BTCUSDT_8m_short_ladder_close_50_618",
        "lane_arm_version": "tiny_live_lane_arm_v1",
        "created_by_phase": "R236_TINY_LIVE_LANE_ARM_WRITE_GATE",
        "created_at": NOW.isoformat(),
        "official_lane_key": OFFICIAL,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "source_lane_arm_preview_id": "r235_lane_arm_preview_fixture",
        "source_execution_enable_id": "r234_execution_enable_BTCUSDT_8m_short_ladder_close_50_618",
        "source_authorization_id": "r232_authorization_BTCUSDT_8m_short_ladder_close_50_618",
        "source_risk_contract_id": "r230_contract_BTCUSDT_8m_short_ladder_close_50_618",
        "risk_contract_config_ready": True,
        "evidence_ready": True,
        "fisherman_ready": True,
        "live_authorized": live_authorized,
        "live_execution_enabled": live_execution_enabled,
        "lane_arm_scope": "tiny_live_single_lane",
        "lane_arm_status": "LANE_ARMED_NOT_EXECUTABLE_NO_ORDER_PAYLOAD",
        "lane_armed": lane_armed,
        "order_payload_allowed": False,
        "order_payload_created": False,
        "binance_call_allowed": False,
        "kill_switch_required": True,
        "kill_switch_disabled": False,
        "operator_final_approval_required": True,
        "order_preflight_required_later": True,
        "binance_connectivity_check_required_later": True,
    }
    return {
        "event_type": "TINY_LIVE_LANE_ARM_WRITE_GATE",
        "status": "TINY_LIVE_LANE_ARM_WRITE_GATE_WRITTEN",
        "gate_record_id": "r236_lane_arm_write_gate_fixture",
        "generated_at": NOW.isoformat(),
        "lane_arm_written": True,
        "target_scope": {"official_lane_key": OFFICIAL},
        "lane_arm": lane_arm,
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
