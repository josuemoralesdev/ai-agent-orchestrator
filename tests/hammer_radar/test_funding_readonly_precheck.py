from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.funding_readonly_precheck import (
    CONFIRM_FUNDING_READONLY_PRECHECK_RECORDING_PHRASE,
    FUNDING_READONLY_PRECHECK_READY,
    FUNDING_READONLY_PRECHECK_RECORDED,
    FUNDING_READONLY_PRECHECK_REJECTED,
    LEDGER_FILENAME,
    READONLY_CONNECTOR_MISSING_ENV,
    READONLY_CONNECTOR_READY_BALANCE_NOT_CHECKED,
    build_funding_readonly_precheck,
    load_funding_readonly_precheck_records,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
READ_ONLY_ENV = {
    "BINANCE_CONNECTOR_MODE": "read_only",
    "BINANCE_LIVE_TRADING_ENABLED": "false",
    "BINANCE_API_KEY": "abcd1234wxyz5678",
    "BINANCE_API_SECRET": "secret-not-rendered",
    "HAMMER_LIVE_EXECUTION_ENABLED": "false",
    "HAMMER_ALLOW_LIVE_ORDERS": "false",
    "HAMMER_GLOBAL_KILL_SWITCH": "true",
}
ACCOUNT_READ_ROLE_ENV = {
    **{key: value for key, value in READ_ONLY_ENV.items() if key not in {"BINANCE_API_KEY", "BINANCE_API_SECRET"}},
    "HAMMER_ACCOUNT_READ_BINANCE_API_KEY": "rolekey1234wxyz5678",
    "HAMMER_ACCOUNT_READ_BINANCE_API_SECRET": "role-secret-not-rendered",
}


def test_preview_writes_no_record(tmp_path: Path) -> None:
    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env={},
        now=NOW,
    )

    assert payload["status"] == FUNDING_READONLY_PRECHECK_READY
    assert payload["precheck_recorded"] is False
    assert payload["precheck_id"] is None
    assert payload["record_precheck_requested"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        record_precheck=True,
        confirm_funding_readonly_precheck="wrong",
        now=NOW,
    )

    assert payload["status"] == FUNDING_READONLY_PRECHECK_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["precheck_recorded"] is False
    assert load_funding_readonly_precheck_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_precheck_only(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    before = config_path.read_text(encoding="utf-8")

    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        env=READ_ONLY_ENV,
        record_precheck=True,
        confirm_funding_readonly_precheck=CONFIRM_FUNDING_READONLY_PRECHECK_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_funding_readonly_precheck_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == FUNDING_READONLY_PRECHECK_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["precheck_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "FUNDING_READONLY_PRECHECK"
    assert config_path.read_text(encoding="utf-8") == before


def test_target_lane_default_is_8m_short_and_remains_paper(tmp_path: Path) -> None:
    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        now=NOW,
    )

    assert payload["target_family"]["lane_key"] == LANE_8M_SHORT
    assert payload["target_family"]["symbol"] == "BTCUSDT"
    assert payload["target_family"]["timeframe"] == "8m"
    assert payload["target_family"]["direction"] == "short"
    assert payload["target_family"]["entry_mode"] == "ladder_close_50_618"
    assert payload["target_family"]["current_mode"] == "paper"


def test_missing_env_classified_as_missing_env(tmp_path: Path) -> None:
    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env={},
        now=NOW,
    )

    assert payload["funding_readiness"] == READONLY_CONNECTOR_MISSING_ENV
    assert payload["local_env_readiness"]["binance_connector_mode_present"] is False
    assert payload["local_env_readiness"]["api_key_present"] is False
    assert payload["local_env_readiness"]["api_secret_present"] is False
    assert payload["readonly_connector"]["connector_status"] == "MISSING_ENV"


def test_readonly_env_present_balance_not_checked_without_network_flag(tmp_path: Path) -> None:
    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        now=NOW,
    )

    assert payload["funding_readiness"] == READONLY_CONNECTOR_READY_BALANCE_NOT_CHECKED
    assert payload["readonly_connector"]["connector_status"] == "READY_READ_ONLY"
    assert payload["readonly_connector"]["network_check_available"] is False
    assert payload["readonly_connector"]["network_check_attempted"] is False
    assert payload["balance_gate"]["balance_check_attempted"] is False
    assert payload["balance_gate"]["funding_ready"] is False


def test_funding_precheck_uses_account_read_role_adapter(tmp_path: Path) -> None:
    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=ACCOUNT_READ_ROLE_ENV,
        now=NOW,
    )
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["funding_readiness"] == READONLY_CONNECTOR_READY_BALANCE_NOT_CHECKED
    assert payload["env_role_resolution"]["role"] == "account_read"
    assert payload["env_role_resolution"]["selected_pair_source"] == "role_specific"
    assert payload["env_role_resolution"]["legacy_fallback_used"] is False
    assert payload["local_env_readiness"]["api_key_present"] is True
    assert payload["local_env_readiness"]["api_secret_present"] is True
    assert payload["readonly_connector"]["connector_status"] == "READY_READ_ONLY"
    assert payload["readonly_connector"]["network_check_attempted"] is False
    assert "rolekey1234wxyz5678" not in rendered
    assert "role-secret-not-rendered" not in rendered


def test_funding_precheck_marks_account_read_legacy_fallback(tmp_path: Path) -> None:
    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        now=NOW,
    )

    assert payload["env_role_resolution"]["selected_pair_source"] == "legacy_fallback"
    assert payload["env_role_resolution"]["legacy_fallback_used"] is True
    assert "account_read uses legacy fallback; role-specific HAMMER_ACCOUNT_READ_* variables are preferred." in payload["readonly_connector"]["warnings"]


def test_default_preview_does_not_attempt_network_and_secrets_are_hidden(tmp_path: Path) -> None:
    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        now=NOW,
    )
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["allow_readonly_network_check"] is False
    assert payload["readonly_connector"]["network_check_attempted"] is False
    assert payload["balance_gate"]["balance_check_attempted"] is False
    assert payload["local_env_readiness"]["api_key_preview"] == "abcd...5678"
    assert payload["local_env_readiness"]["secrets_shown"] is False
    assert payload["safety"]["secrets_shown"] is False
    assert "secret-not-rendered" not in rendered
    assert "abcd1234wxyz5678" not in rendered


def test_live_flags_remain_false_safe_and_minimum_defaults_to_44(tmp_path: Path) -> None:
    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        now=NOW,
    )

    assert payload["live_flag_readiness"]["binance_live_trading_enabled"] is False
    assert payload["live_flag_readiness"]["hammer_live_execution_enabled"] is False
    assert payload["live_flag_readiness"]["hammer_allow_live_orders"] is False
    assert payload["live_flag_readiness"]["global_kill_switch_status"] == "enabled"
    assert payload["live_flag_readiness"]["live_flags_safe"] is True
    assert payload["balance_gate"]["minimum_balance_required_estimate_usdt"] == 44.0


def test_do_not_run_blocks_transfer_withdraw_orders_and_live_commands(tmp_path: Path) -> None:
    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        now=NOW,
    )
    safe_commands = "\n".join(payload["safe_commands"]).lower()
    forbidden = "\n".join(payload["do_not_run_yet"]).lower()

    assert "transfer" in payload["do_not_run_yet"]
    assert "withdraw" in payload["do_not_run_yet"]
    assert "live-connector-submit" in payload["do_not_run_yet"]
    assert "funding-readonly-precheck" in safe_commands
    assert "short-paper-evidence-capture-loop" in safe_commands
    assert "short-evidence-recheck-packet" in safe_commands
    assert "short-risk-contract-apply-review" in safe_commands
    assert "live-connector-submit" not in safe_commands
    assert "lane-control-command" not in safe_commands
    assert "--apply" not in safe_commands
    assert " order endpoint" not in safe_commands
    assert "transfer" in forbidden
    assert "withdraw" in forbidden


def test_safety_flags_clean_and_no_config_or_risk_contract_write(tmp_path: Path) -> None:
    payload = build_funding_readonly_precheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        now=NOW,
    )

    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["risk_contract_config_written"] is False
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
        payload = build_funding_readonly_precheck(
            log_dir=tmp_path / "logs",
            config_path=config_path,
            env=READ_ONLY_ENV,
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
    assert payload["safety"]["risk_contract_config_written"] is False
    assert payload["safety"]["global_live_flags_changed"] is False
    assert payload["safety"]["transfer_endpoint_called"] is False
    assert payload["safety"]["withdraw_endpoint_called"] is False


def test_cli_exists_and_preview_returns_expected_shape(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "funding-readonly-precheck",
            "--minimum-balance-usdt",
            "44",
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
    assert "local_env_readiness" in payload
    assert "live_flag_readiness" in payload
    assert "readonly_connector" in payload
    assert "balance_gate" in payload
    assert "funding-readonly-precheck" in help_result.stdout


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
