from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    CONFIRM_TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_READY,
    TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_REJECTED,
    TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_WRITTEN,
    build_tiny_live_risk_contract_config_entry,
    build_tiny_live_risk_contract_config_write_gate,
    load_tiny_live_risk_contract_config_write_gate_records,
    validate_tiny_live_risk_contract_config_entry,
)

NOW = datetime(2026, 6, 9, 5, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_config(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    before = risk_path.read_text(encoding="utf-8")

    payload = build_tiny_live_risk_contract_config_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_READY
    assert payload["config_written"] is False
    assert payload["record_gate_requested"] is False
    assert payload["confirmation_valid"] is False
    assert risk_path.read_text(encoding="utf-8") == before
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_and_writes_no_config(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    before = risk_path.read_text(encoding="utf-8")

    payload = build_tiny_live_risk_contract_config_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        write_risk_config=True,
        confirm_tiny_live_risk_contract_config_write="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["config_written"] is False
    assert risk_path.read_text(encoding="utf-8") == before
    assert payload["config_write_overall_status"] == "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_REJECTED_BAD_CONFIRMATION"
    assert load_tiny_live_risk_contract_config_write_gate_records(log_dir=log_dir, limit=0)[0]["config_written"] is False


def test_exact_confirmation_writes_only_risk_contract_config(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    lane_path = _write_lane_controls(tmp_path / "lane_controls.json")
    env_path = tmp_path / ".env"
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")
    before_env_file = env_path.read_text(encoding="utf-8")
    before_env = dict(os.environ)

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_tiny_live_risk_contract_config_write_gate(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            write_risk_config=True,
            confirm_tiny_live_risk_contract_config_write=CONFIRM_TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_PHRASE,
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert dict(os.environ) == before_env
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert env_path.read_text(encoding="utf-8") == before_env_file
    assert payload["status"] == TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_WRITTEN
    assert payload["config_written"] is True
    assert payload["safety"]["config_written"] is True
    assert payload["safety"]["risk_contract_config_written"] is True
    assert payload["safety"]["lane_controls_written"] is False
    assert payload["safety"]["env_mutated"] is False
    config = json.loads(risk_path.read_text(encoding="utf-8"))
    contracts = config["risk_contracts"]
    matching = [contract for contract in contracts if contract.get("official_lane_key") == OFFICIAL]
    assert len(matching) == 1
    assert matching[0]["approval_status"] == "CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED"
    assert matching[0]["live_authorized"] is False
    assert matching[0]["live_execution_enabled"] is False
    assert matching[0]["order_payload_forbidden_until_live_gate"] is True
    assert contracts[0]["candidate_id"] == "normal|BTCUSDT|13m|long|ladder_close_50_618"


def test_config_write_is_bounded_to_official_lane_key(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")

    payload = build_tiny_live_risk_contract_config_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        write_risk_config=True,
        confirm_tiny_live_risk_contract_config_write=CONFIRM_TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_PHRASE,
        now=NOW,
    )

    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["config_write_preview"]["target_contract_key"] == OFFICIAL
    assert payload["post_write_verification"]["matching_contract_found"] is True
    assert payload["risk_contract_config_gate_matrix"]["risk_contract_approved"] is False
    assert payload["risk_contract_config_gate_matrix"]["live_authorization_ready"] is False


def test_existing_config_shape_is_preserved_and_contracts_are_not_removed(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")

    build_tiny_live_risk_contract_config_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        write_risk_config=True,
        confirm_tiny_live_risk_contract_config_write=CONFIRM_TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_PHRASE,
        now=NOW,
    )

    config = json.loads(risk_path.read_text(encoding="utf-8"))
    assert "risk_contracts" in config
    assert isinstance(config["risk_contracts"], list)
    assert len(config["risk_contracts"]) == 2
    assert config["funding_config"]["max_margin_usdt"] == 44.0


def test_dict_config_shape_is_preserved(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    risk_path = tmp_path / "tiny_live_risk_contracts.json"
    risk_path.write_text(json.dumps({"contracts": {"OTHER": {"symbol": "ETHUSDT"}}}), encoding="utf-8")

    build_tiny_live_risk_contract_config_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        write_risk_config=True,
        confirm_tiny_live_risk_contract_config_write=CONFIRM_TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_PHRASE,
        now=NOW,
    )

    config = json.loads(risk_path.read_text(encoding="utf-8"))
    assert "contracts" in config
    assert "OTHER" in config["contracts"]
    assert OFFICIAL in config["contracts"]


def test_config_entry_validation_catches_bad_lane() -> None:
    entry = build_tiny_live_risk_contract_config_entry(latest_preview={}, now=NOW)
    entry["official_lane_key"] = "ETHUSDT|8m|short|ladder_close_50_618"

    validation = validate_tiny_live_risk_contract_config_entry(entry)

    assert validation["valid"] is False
    assert "official_lane_key_invalid" in validation["errors"]


def test_config_entry_validation_catches_invalid_risk_values() -> None:
    entry = build_tiny_live_risk_contract_config_entry(latest_preview={}, now=NOW)
    entry["tiny_live_margin_usdt"] = 0
    entry["leverage"] = 0
    entry["max_notional_usdt"] = 99
    entry["max_loss_usdt"] = 100

    validation = validate_tiny_live_risk_contract_config_entry(entry)

    assert validation["valid"] is False
    assert "tiny_live_margin_usdt_invalid" in validation["errors"]
    assert "leverage_invalid" in validation["errors"]
    assert "max_loss_usdt_exceeds_margin" in validation["errors"]


def test_no_live_order_transfer_withdraw_or_network_actions(tmp_path: Path) -> None:
    payload = build_tiny_live_risk_contract_config_write_gate(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    for key in (
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
        "live_authorization_created",
        "live_execution_enabled",
        "global_live_flags_changed",
        "kill_switch_disabled",
        "lane_promoted",
        "official_tiny_live_lane_changed",
        "alternate_lane_promoted",
        "betrayal_live_authorized",
        "betrayal_promoted",
        "position_permission_created",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["paper_live_separation_intact"] is True
    assert payload["safety"]["risk_contract_config_write_gate_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-risk-contract-config-write-gate",
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
    assert "tiny-live-risk-contract-config-write-gate" in help_result.stdout


def _fixture_logs(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    _append(log_dir / "tiny_live_risk_contract_preview.ndjson", _r229_preview_record())
    _append(log_dir / "paper_outcomes.ndjson", {"signal_id": "ordinary-signal", "outcome": "win"})
    _append(log_dir / "strategy_performance.ndjson", {"lane_key": "ordinary", "sample_size": 30, "win_rate_pct": 60.0})
    _append(log_dir / "strategy_promotion_status.ndjson", {"lane_key": "ordinary", "promotion_allowed": False})
    return log_dir


def _r229_preview_record() -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_RISK_CONTRACT_PREVIEW",
        "status": "TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED",
        "risk_preview_record_id": "r229_preview_fixture",
        "generated_at": NOW.isoformat(),
        "target_scope": {
            "official_lane_key": OFFICIAL,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "live_authorized": False,
        },
        "risk_contract_preview": {
            "contract_id": "r229_preview_BTCUSDT_8m_short_ladder_close_50_618",
            "contract_version": "tiny_live_risk_contract_preview_v1",
            "official_lane_key": OFFICIAL,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "proposed_tiny_live_margin_usdt": 44,
            "proposed_leverage": 1,
            "proposed_max_notional_usdt": 44,
            "proposed_max_loss_usdt": 4.44,
            "risk_reward_ratio_preview": 2.0,
            "stop_required": True,
            "take_profit_required": True,
            "kill_switch_required": True,
            "operator_final_approval_required": True,
            "approval_status": "NOT_APPROVED_PREVIEW_ONLY",
            "order_payload_forbidden_now": True,
            "binance_call_forbidden_now": True,
        },
        "risk_gate_matrix": {
            "evidence_ready": True,
            "fisherman_ready": True,
            "operator_review_ready": True,
            "risk_contract_preview_ready": True,
            "risk_contract_config_written": False,
            "risk_contract_approved": False,
            "live_authorization_ready": False,
            "live_execution_ready": False,
            "order_ready": False,
            "live_ready_today": False,
            "blocked_by": ["risk_contract_config_write_required_later", "live_authorization_absent", "order_payload_forbidden"],
        },
        "risk_preview_overall_status": "TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER",
    }


def _write_risk_contract_config(path: Path) -> Path:
    payload = {
        "funding_config": {"max_margin_usdt": 44.0, "max_loss_usdt": 4.44},
        "risk_contracts": [
            {
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "symbol": "BTCUSDT",
                "timeframe": "13m",
                "direction": "long",
                "entry_mode": "ladder_close_50_618",
                "enabled_for_preflight": True,
                "max_margin_usdt": 44.0,
                "max_position_notional_usdt": 44.0,
                "leverage": 1,
                "max_loss_usdt": 4.44,
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
