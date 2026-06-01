from __future__ import annotations

import json
import os
import subprocess
import urllib.error
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.readonly_balance_check import (
    ACCOUNT_FUNDED_BELOW_MINIMUM,
    ACCOUNT_FUNDED_READY_FOR_REVIEW,
    ACCOUNT_NOT_FUNDED,
    CONFIRM_READONLY_BALANCE_CHECK_RECORDING_PHRASE,
    LEDGER_FILENAME,
    READONLY_BALANCE_CHECK_RECORDED,
    READONLY_BALANCE_CHECK_REJECTED,
    READONLY_CONNECTOR_MISSING_ENV,
    READONLY_CONNECTOR_NOT_SAFE,
    READONLY_NETWORK_NOT_ALLOWED,
    build_readonly_balance_check,
    load_readonly_balance_check_records,
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


def test_preview_writes_no_record(tmp_path: Path) -> None:
    payload = build_readonly_balance_check(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        now=NOW,
    )

    assert payload["balance_check_recorded"] is False
    assert payload["balance_check_id"] is None
    assert payload["record_balance_check_requested"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    payload = build_readonly_balance_check(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        record_balance_check=True,
        confirm_readonly_balance_check="wrong",
        now=NOW,
    )

    assert payload["status"] == READONLY_BALANCE_CHECK_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["balance_check_recorded"] is False
    assert load_readonly_balance_check_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_no_network_result_only(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    before = config_path.read_text(encoding="utf-8")

    payload = build_readonly_balance_check(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        env=READ_ONLY_ENV,
        record_balance_check=True,
        confirm_readonly_balance_check=CONFIRM_READONLY_BALANCE_CHECK_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_readonly_balance_check_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == READONLY_BALANCE_CHECK_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["balance_check_recorded"] is True
    assert payload["balance_check"]["network_check_attempted"] is False
    assert payload["balance_readiness"] == READONLY_NETWORK_NOT_ALLOWED
    assert len(records) == 1
    assert records[0]["event_type"] == "READONLY_BALANCE_CHECK"
    assert config_path.read_text(encoding="utf-8") == before


def test_target_lane_default_is_8m_short_and_remains_paper(tmp_path: Path) -> None:
    payload = build_readonly_balance_check(
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


def test_default_preview_does_not_attempt_network_and_minimum_defaults_to_44(tmp_path: Path) -> None:
    with patch("src.app.hammer_radar.operator.readonly_balance_check._request_binance_futures_account_snapshot") as request:
        payload = build_readonly_balance_check(
            log_dir=tmp_path / "logs",
            config_path=_write_config(tmp_path / "lane_controls.json"),
            env=READ_ONLY_ENV,
            now=NOW,
        )

    request.assert_not_called()
    assert payload["allow_readonly_network_check"] is False
    assert payload["balance_check"]["network_check_requested"] is False
    assert payload["balance_check"]["network_check_attempted"] is False
    assert payload["balance_check"]["balance_check_attempted"] is False
    assert payload["balance_check"]["minimum_balance_required_estimate_usdt"] == 44.0


def test_explicit_allow_flag_can_attempt_readonly_network_only_when_preflight_safe(tmp_path: Path) -> None:
    with patch(
        "src.app.hammer_radar.operator.readonly_balance_check._request_binance_futures_account_snapshot",
        return_value=_account(44),
    ) as request:
        payload = build_readonly_balance_check(
            log_dir=tmp_path / "logs",
            config_path=_write_config(tmp_path / "lane_controls.json"),
            env=READ_ONLY_ENV,
            allow_readonly_network_check=True,
            now=NOW,
        )

    request.assert_called_once()
    assert payload["readonly_preflight"]["connector_status"] == "READY_READ_ONLY"
    assert payload["readonly_preflight"]["connector_mode"] == "read_only"
    assert payload["readonly_preflight"]["live_flags_safe"] is True
    assert payload["balance_check"]["network_check_requested"] is True
    assert payload["balance_check"]["network_check_attempted"] is True
    assert payload["balance_check"]["balance_check_attempted"] is True
    assert payload["balance_check"]["funding_status"] == ACCOUNT_FUNDED_READY_FOR_REVIEW
    assert payload["safety"]["network_allowed"] is True
    assert payload["safety"]["signed_readonly_request_created"] is True
    assert payload["safety"]["signed_trading_request_created"] is False
    assert payload["safety"]["signed_order_request_created"] is False


def test_missing_env_blocks_before_network(tmp_path: Path) -> None:
    with patch("src.app.hammer_radar.operator.readonly_balance_check._request_binance_futures_account_snapshot") as request:
        payload = build_readonly_balance_check(
            log_dir=tmp_path / "logs",
            config_path=_write_config(tmp_path / "lane_controls.json"),
            env={},
            allow_readonly_network_check=True,
            now=NOW,
        )

    request.assert_not_called()
    assert payload["balance_readiness"] == READONLY_CONNECTOR_MISSING_ENV
    assert payload["balance_check"]["network_check_attempted"] is False
    assert payload["readonly_preflight"]["api_key_present"] is False
    assert payload["readonly_preflight"]["api_secret_present"] is False


def test_unsafe_live_flags_block_before_network(tmp_path: Path) -> None:
    env = {**READ_ONLY_ENV, "HAMMER_ALLOW_LIVE_ORDERS": "true"}
    with patch("src.app.hammer_radar.operator.readonly_balance_check._request_binance_futures_account_snapshot") as request:
        payload = build_readonly_balance_check(
            log_dir=tmp_path / "logs",
            config_path=_write_config(tmp_path / "lane_controls.json"),
            env=env,
            allow_readonly_network_check=True,
            now=NOW,
        )

    request.assert_not_called()
    assert payload["balance_readiness"] == READONLY_CONNECTOR_NOT_SAFE
    assert payload["readonly_preflight"]["live_flags_safe"] is False
    assert payload["balance_check"]["network_check_attempted"] is False


def test_no_secrets_shown(tmp_path: Path) -> None:
    payload = build_readonly_balance_check(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        now=NOW,
    )
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["readonly_preflight"]["api_key_preview"] == "abcd...5678"
    assert payload["readonly_preflight"]["secrets_shown"] is False
    assert payload["safety"]["secrets_shown"] is False
    assert "secret-not-rendered" not in rendered
    assert "abcd1234wxyz5678" not in rendered


def test_httperror_sanitized_metadata_is_recorded_without_signature_or_secret(tmp_path: Path) -> None:
    error = urllib.error.HTTPError(
        "https://fapi.binance.com/fapi/v2/account?timestamp=1&signature=raw-signature-secret",
        403,
        "Forbidden",
        {},
        BytesIO(b'{"code":-2015,"msg":"Invalid API-key, IP, or permissions."}'),
    )
    with patch(
        "src.app.hammer_radar.operator.readonly_balance_check._request_binance_futures_account_snapshot",
        side_effect=error,
    ):
        payload = build_readonly_balance_check(
            log_dir=tmp_path / "logs",
            config_path=_write_config(tmp_path / "lane_controls.json"),
            env=READ_ONLY_ENV,
            allow_readonly_network_check=True,
            now=NOW,
        )

    rendered = json.dumps(payload, sort_keys=True)
    assert payload["balance_readiness"] == "READONLY_BALANCE_CHECK_FAILED"
    assert payload["balance_check"]["error_type"] == "HTTPError"
    assert payload["balance_check"]["http_status"] == 403
    assert payload["balance_check"]["binance_code"] == -2015
    assert payload["balance_check"]["binance_message"] == "Invalid API-key, IP, or permissions."
    assert payload["balance_check"]["endpoint_family"] == "futures_account_readonly"
    assert "raw-signature-secret" not in rendered
    assert "secret-not-rendered" not in rendered
    assert "abcd1234wxyz5678" not in rendered


def test_account_0_usdt_classified_account_not_funded(tmp_path: Path) -> None:
    payload = _mocked_balance_payload(tmp_path, available=0)
    assert payload["balance_readiness"] == ACCOUNT_NOT_FUNDED
    assert payload["balance_check"]["funding_ready"] is False


def test_account_below_44_classified_below_minimum(tmp_path: Path) -> None:
    payload = _mocked_balance_payload(tmp_path, available=43.99)
    assert payload["balance_readiness"] == ACCOUNT_FUNDED_BELOW_MINIMUM
    assert payload["balance_check"]["funding_ready"] is False


def test_account_at_least_44_classified_ready_for_review(tmp_path: Path) -> None:
    payload = _mocked_balance_payload(tmp_path, available=44)
    assert payload["balance_readiness"] == ACCOUNT_FUNDED_READY_FOR_REVIEW
    assert payload["balance_check"]["funding_ready"] is True
    assert payload["recommended_next_operator_move"] == "RUN_R165_FUNDING_GATE_RECHECK"


def test_no_order_or_live_commands_emitted_and_transfer_withdraw_blocked(tmp_path: Path) -> None:
    payload = build_readonly_balance_check(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        now=NOW,
    )
    safe_commands = "\n".join(payload["safe_commands"]).lower()

    assert "readonly-balance-check" in safe_commands
    assert "--allow-readonly-network-check" in safe_commands
    assert "funding-readonly-precheck" in safe_commands
    assert "short-paper-evidence-capture-loop" in safe_commands
    assert "short-evidence-recheck-packet" in safe_commands
    assert "live-connector-submit" not in safe_commands
    assert "lane-control-command" not in safe_commands
    assert "--apply" not in safe_commands
    assert " order endpoint" not in safe_commands
    assert "transfer" in payload["do_not_run_yet"]
    assert "withdraw" in payload["do_not_run_yet"]


def test_safety_flags_clean_no_config_or_risk_contract_write(tmp_path: Path) -> None:
    payload = build_readonly_balance_check(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        env=READ_ONLY_ENV,
        now=NOW,
    )

    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["risk_contract_config_written"] is False
    for key, value in payload["safety"].items():
        if key in {"paper_live_separation_intact"}:
            assert value is True
        elif key == "signed_request_created_scope":
            assert value == "none"
        else:
            assert value is False, key


def test_no_binance_order_payload_env_config_or_global_mutation(tmp_path: Path) -> None:
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
        payload = build_readonly_balance_check(
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
    assert payload["safety"]["signed_trading_request_created"] is False
    assert payload["safety"]["signed_order_request_created"] is False
    assert payload["safety"]["signed_readonly_request_created"] is False
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
            "readonly-balance-check",
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
    assert "readonly_preflight" in payload
    assert "balance_check" in payload
    assert "balance_readiness" in payload
    assert "readonly-balance-check" in help_result.stdout


def _mocked_balance_payload(tmp_path: Path, *, available: float) -> dict[str, object]:
    with patch(
        "src.app.hammer_radar.operator.readonly_balance_check._request_binance_futures_account_snapshot",
        return_value=_account(available),
    ):
        return build_readonly_balance_check(
            log_dir=tmp_path / "logs",
            config_path=_write_config(tmp_path / "lane_controls.json"),
            env=READ_ONLY_ENV,
            allow_readonly_network_check=True,
            now=NOW,
        )


def _account(available: float) -> dict[str, object]:
    return {
        "assets": [
            {
                "asset": "USDT",
                "availableBalance": str(available),
                "walletBalance": str(available),
            }
        ]
    }


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
