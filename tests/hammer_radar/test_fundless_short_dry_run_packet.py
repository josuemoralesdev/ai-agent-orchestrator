from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.fundless_short_dry_run_packet import (
    CONFIRM_FUNDLESS_SHORT_DRY_RUN_PACKET_RECORDING_PHRASE,
    FUNDLESS_SHORT_DRY_RUN_PACKET_READY,
    FUNDLESS_SHORT_DRY_RUN_PACKET_RECORDED,
    FUNDLESS_SHORT_DRY_RUN_PACKET_REJECTED,
    LEDGER_FILENAME,
    build_fundless_short_dry_run_packet,
    load_fundless_short_dry_run_packet_records,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_packet(tmp_path: Path) -> None:
    payload = build_fundless_short_dry_run_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["status"] == FUNDLESS_SHORT_DRY_RUN_PACKET_READY
    assert payload["packet_recorded"] is False
    assert payload["packet_id"] is None
    assert payload["record_packet_requested"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    payload = build_fundless_short_dry_run_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        record_packet=True,
        confirm_fundless_short_dry_run="wrong",
        now=NOW,
    )

    assert payload["status"] == FUNDLESS_SHORT_DRY_RUN_PACKET_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["packet_recorded"] is False
    assert load_fundless_short_dry_run_packet_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_packet_only(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    before = config_path.read_text(encoding="utf-8")

    payload = build_fundless_short_dry_run_packet(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        record_packet=True,
        confirm_fundless_short_dry_run=CONFIRM_FUNDLESS_SHORT_DRY_RUN_PACKET_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_fundless_short_dry_run_packet_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == FUNDLESS_SHORT_DRY_RUN_PACKET_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["packet_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "FUNDLESS_SHORT_DRY_RUN_PACKET"
    assert config_path.read_text(encoding="utf-8") == before


def test_target_lane_default_is_8m_short_and_remains_paper(tmp_path: Path) -> None:
    payload = build_fundless_short_dry_run_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["target_family"]["lane_key"] == LANE_8M_SHORT
    assert payload["target_family"]["symbol"] == "BTCUSDT"
    assert payload["target_family"]["timeframe"] == "8m"
    assert payload["target_family"]["direction"] == "short"
    assert payload["target_family"]["entry_mode"] == "ladder_close_50_618"
    assert payload["target_family"]["current_mode"] == "paper"


def test_future_conditions_matrix_has_required_gates(tmp_path: Path) -> None:
    payload = build_fundless_short_dry_run_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )
    matrix = payload["future_conditions_matrix"]

    for key in ("fresh_evidence", "funding", "risk_contract", "protective_policy", "operator_approval", "global_live_flags"):
        assert key in matrix
        assert "required" in matrix[key]
        assert "current" in matrix[key]
        assert "satisfied" in matrix[key]


def test_non_executable_dry_run_fields_are_not_executable(tmp_path: Path) -> None:
    payload = build_fundless_short_dry_run_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )
    fields = payload["non_executable_dry_run_fields"]

    assert fields["intent_type"] == "FUNDLESS_SHORT_TINY_LIVE_DRY_RUN_PACKET_ONLY"
    assert fields["symbol"] == "BTCUSDT"
    assert fields["side"] == "SELL"
    assert fields["timeframe"] == "8m"
    assert fields["entry_mode"] == "ladder_close_50_618"
    assert fields["notional_usdt"] is None
    assert fields["quantity"] is None
    assert fields["entry_price"] is None
    assert fields["stop_price"] is None
    assert fields["take_profit_price"] is None
    assert fields["protective_orders_required"] is True
    assert fields["would_build_order_payload"] is False
    assert fields["would_submit_order"] is False
    assert fields["would_call_binance"] is False
    assert fields["executable"] is False


def test_operator_checklist_blocks_live_now_and_commands_are_safe(tmp_path: Path) -> None:
    payload = build_fundless_short_dry_run_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )
    joined = "\n".join(payload["safe_commands"]).lower()

    assert "target short lane remains paper" in payload["operator_arming_checklist"]["currently_true"]
    assert "account balance verified and sufficient" in payload["operator_arming_checklist"]["currently_blocked"]
    assert "short-paper-evidence-capture-loop" in joined
    assert "short-evidence-recheck-packet" in joined
    assert "fundless-short-tiny-live-readiness-rehearsal" in joined
    assert "fundless-short-dry-run-packet" in joined
    assert "live-connector-submit" not in joined
    assert "lane-control-command" not in joined
    assert "--apply" not in joined


def test_forbidden_list_blocks_signed_and_protective_submit(tmp_path: Path) -> None:
    payload = build_fundless_short_dry_run_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert "signed order request" in payload["do_not_run_yet"]
    assert "protective order submit" in payload["do_not_run_yet"]
    assert "set short lane tiny_live" in payload["do_not_run_yet"]
    assert "set new lane tiny_live" in payload["do_not_run_yet"]


def test_plan_requirements_and_lockdown_are_explicit(tmp_path: Path) -> None:
    payload = build_fundless_short_dry_run_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["funding_verification_plan"]["safe_future_check"] == "binance-readonly-status / balance read-only if available"
    assert payload["funding_verification_plan"]["no_network_required_for_this_packet"] is True
    assert payload["risk_contract_requirements"]["must_exist_for_target_lane"] is True
    assert payload["risk_contract_requirements"]["max_daily_trades"] == 1
    assert payload["risk_contract_requirements"]["max_daily_loss_pct"] == 0.15
    assert payload["risk_contract_requirements"]["requires_protective_orders"] is True
    assert payload["risk_contract_requirements"]["short_specific_stop_tp_required"] is True
    assert payload["risk_contract_requirements"]["contract_change_allowed_now"] is False
    assert payload["protective_policy_requirements"]["golden_pocket_role"] == "resistance/retrace zone"
    assert payload["protective_policy_requirements"]["protective_policy_change_allowed_now"] is False
    assert payload["live_flag_lockdown"]["live_execution_enabled"] is False
    assert payload["live_flag_lockdown"]["global_kill_switch_authoritative"] is True
    assert payload["live_flag_lockdown"]["short_tiny_live_authorized"] is False
    assert payload["live_flag_lockdown"]["lane_mode_change_allowed_now"] is False


def test_safety_flags_clean_and_config_written_false(tmp_path: Path) -> None:
    payload = build_fundless_short_dry_run_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["safety"]["config_written"] is False
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_no_binance_order_payload_network_env_config_or_global_mutation(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    with (
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "protective_preview") as protective_preview,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "submit_protective_test") as submit_protective_test,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
        patch.object(binance_futures_connector, "build_signed_test_order_request") as build_signed_test_order_request,
        patch.object(binance_futures_connector, "build_signed_protective_order_requests") as build_signed_protective_order_requests,
    ):
        payload = build_fundless_short_dry_run_packet(
            log_dir=tmp_path / "logs",
            config_path=config_path,
            risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
            now=NOW,
        )

    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    protective_preview.assert_not_called()
    submit_test_order.assert_not_called()
    submit_protective_test.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    build_signed_test_order_request.assert_not_called()
    build_signed_protective_order_requests.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert payload["safety"]["network_allowed"] is False
    assert payload["safety"]["order_payload_created"] is False
    assert payload["safety"]["executable_payload_created"] is False
    assert payload["safety"]["protective_payload_created"] is False
    assert payload["safety"]["signed_request_created"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["binance_test_order_endpoint_called"] is False
    assert payload["safety"]["protective_order_endpoint_called"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["global_live_flags_changed"] is False


def test_cli_exists_and_preview_returns_expected_shape(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "fundless-short-dry-run-packet",
            "--latest-captures",
            "10",
            "--latest-outcomes",
            "10",
            "--latest-signals",
            "20",
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
    assert payload["target_family"]["lane_key"] == LANE_8M_SHORT
    assert "future_conditions_matrix" in payload
    assert "operator_arming_checklist" in payload
    assert "fundless-short-dry-run-packet" in help_result.stdout


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lanes = [
        _lane("13m", "long", "tiny_live"),
        _lane("44m", "long", "tiny_live"),
        _lane("8m", "long", "paper"),
        _lane("4m", "long", "paper"),
        _lane("4m", "short", "paper"),
        _lane("8m", "short", "paper"),
        _lane("13m", "short", "paper"),
        _lane("44m", "short", "paper"),
    ]
    path.write_text(json.dumps({"schema_version": "1.0", "default_mode": "disabled", "lanes": lanes}), encoding="utf-8")
    return path


def _write_risk_contract_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "funding_config": {
                    "account_balance_checked": False,
                    "account_balance_source": "not_checked_no_network",
                    "funding_check_mode": "LOCAL_CONFIG_ONLY_NO_NETWORK",
                },
                "risk_contracts": [
                    {
                        "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                        "symbol": "BTCUSDT",
                        "timeframe": "13m",
                        "direction": "long",
                        "entry_mode": "ladder_close_50_618",
                        "max_position_notional_usdt": 44.0,
                        "protective_stop_required": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _lane(timeframe: str, direction: str, mode: str) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": "ladder_close_50_618",
        "mode": mode,
        "max_daily_trades": 1,
        "max_daily_loss_pct": 0.15,
        "freshness_seconds": 60,
        "cooldown_after_loss_minutes": 120,
        "require_protective_orders": True,
    }
