from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.account_read_env_migration_verify import (
    CONFIRM_ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDING_PHRASE,
    build_account_read_env_migration_verify,
)
from src.app.hammer_radar.operator.funding_gate_role_specific_sync import (
    CONFIRM_FUNDING_ROLE_SPECIFIC_SYNC_RECORDING_PHRASE,
    FUNDING_GATE_ROLE_SPECIFIC_SYNC_BLOCKED,
    FUNDING_GATE_ROLE_SPECIFIC_SYNC_RECORDED,
    FUNDING_GATE_ROLE_SPECIFIC_SYNC_REJECTED,
    FUNDING_SYNC_ACCOUNT_NOT_FUNDED,
    FUNDING_SYNC_BELOW_MINIMUM,
    FUNDING_SYNC_NO_BALANCE_RECORD,
    FUNDING_SYNC_READY_FOR_REVIEW,
    LEDGER_FILENAME,
    build_funding_gate_role_specific_sync,
    load_funding_gate_role_specific_sync_records,
)
from src.app.hammer_radar.operator.readonly_balance_check import (
    ACCOUNT_FUNDED_BELOW_MINIMUM,
    ACCOUNT_FUNDED_READY_FOR_REVIEW,
    ACCOUNT_NOT_FUNDED,
    append_readonly_balance_check_record,
)

NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
SAFE_FLAGS = {
    "BINANCE_CONNECTOR_MODE": "read_only",
    "BINANCE_LIVE_TRADING_ENABLED": "false",
    "HAMMER_LIVE_EXECUTION_ENABLED": "false",
    "HAMMER_ALLOW_LIVE_ORDERS": "false",
    "HAMMER_GLOBAL_KILL_SWITCH": "true",
}
ACCOUNT_READ_PAIR = {
    "HAMMER_ACCOUNT_READ_BINANCE_API_KEY": "account-key-full-value",
    "HAMMER_ACCOUNT_READ_BINANCE_API_SECRET": "account-secret-full-value",
}


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _record_role_specific_verify(log_dir)
    _record_balance(log_dir, ACCOUNT_NOT_FUNDED, available=0.0, wallet=0.0)

    payload = build_funding_gate_role_specific_sync(log_dir=log_dir, config_path=_write_config(tmp_path), now=NOW)

    assert payload["sync_recorded"] is False
    assert payload["sync_id"] is None
    assert payload["record_sync_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _record_role_specific_verify(log_dir)
    _record_balance(log_dir, ACCOUNT_NOT_FUNDED, available=0.0, wallet=0.0)

    payload = build_funding_gate_role_specific_sync(
        log_dir=log_dir,
        config_path=_write_config(tmp_path),
        record_sync=True,
        confirm_funding_role_specific_sync="wrong",
        now=NOW,
    )

    assert payload["status"] == FUNDING_GATE_ROLE_SPECIFIC_SYNC_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["sync_recorded"] is False
    assert load_funding_gate_role_specific_sync_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path)
    _record_role_specific_verify(log_dir)
    _record_balance(log_dir, ACCOUNT_NOT_FUNDED, available=0.0, wallet=0.0)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_funding_gate_role_specific_sync(
        log_dir=log_dir,
        config_path=config_path,
        record_sync=True,
        confirm_funding_role_specific_sync=CONFIRM_FUNDING_ROLE_SPECIFIC_SYNC_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_funding_gate_role_specific_sync_records(log_dir=log_dir, limit=0)

    assert payload["status"] == FUNDING_GATE_ROLE_SPECIFIC_SYNC_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["sync_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "FUNDING_GATE_ROLE_SPECIFIC_SYNC"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_role_specific_account_read_and_account_not_funded_syncs_not_funded(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _record_role_specific_verify(log_dir)
    _record_balance(log_dir, ACCOUNT_NOT_FUNDED, available=0.0, wallet=0.0)

    payload = build_funding_gate_role_specific_sync(log_dir=log_dir, config_path=_write_config(tmp_path), now=NOW)

    assert payload["target_family"]["lane_key"] == LANE_8M_SHORT
    assert payload["target_family"]["current_mode"] == "paper"
    assert payload["account_read_role_state"]["selected_pair_source"] == "role_specific"
    assert payload["account_read_role_state"]["role_specific_pair_present"] is True
    assert payload["account_read_role_state"]["legacy_fallback_used"] is False
    assert payload["account_read_role_state"]["runtime_safety_passed"] is True
    assert payload["account_read_role_state"]["future_live_disabled"] is True
    assert payload["latest_balance_state"]["balance_readiness"] == ACCOUNT_NOT_FUNDED
    assert payload["latest_balance_state"]["available_balance_usdt"] == 0.0
    assert payload["latest_balance_state"]["wallet_balance_usdt"] == 0.0
    assert payload["latest_balance_state"]["minimum_balance_required_estimate_usdt"] == 44
    assert payload["funding_gate"]["funding_sync_status"] == FUNDING_SYNC_ACCOUNT_NOT_FUNDED
    assert payload["funding_gate"]["funding_ready"] is False
    assert payload["funding_gate"]["funding_blocker"] == "account_not_funded"
    assert payload["funding_gate"]["safe_to_arm_live"] is False
    assert payload["tiny_live_blocker_summary"]["funding_blocked"] is True
    assert payload["tiny_live_blocker_summary"]["risk_contract_blocked"] is True
    assert payload["tiny_live_blocker_summary"]["lane_mode_blocked"] is True
    assert payload["recommended_next_operator_move"] == "FUND_ACCOUNT_LATER"


def test_missing_role_verification_blocks(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _record_balance(log_dir, ACCOUNT_NOT_FUNDED, available=0.0, wallet=0.0)

    payload = build_funding_gate_role_specific_sync(log_dir=log_dir, config_path=_write_config(tmp_path), now=NOW)

    assert payload["status"] == FUNDING_GATE_ROLE_SPECIFIC_SYNC_BLOCKED
    assert payload["account_read_role_state"]["selected_pair_source"] == "missing"
    assert payload["funding_gate"]["funding_sync_status"] == "FUNDING_SYNC_ACCOUNT_READ_ROLE_NOT_VERIFIED"
    assert payload["funding_gate"]["funding_blocker"] == "role_not_verified"
    assert payload["recommended_next_operator_move"] == "KEEP_R157_RUNNING"


def test_missing_balance_record_blocks(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _record_role_specific_verify(log_dir)

    payload = build_funding_gate_role_specific_sync(log_dir=log_dir, config_path=_write_config(tmp_path), now=NOW)

    assert payload["status"] == FUNDING_GATE_ROLE_SPECIFIC_SYNC_BLOCKED
    assert payload["latest_balance_state"]["record_found"] is False
    assert payload["funding_gate"]["funding_sync_status"] == FUNDING_SYNC_NO_BALANCE_RECORD
    assert payload["funding_gate"]["funding_blocker"] == "missing_balance_record"


def test_funded_below_minimum_produces_below_minimum(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _record_role_specific_verify(log_dir)
    _record_balance(log_dir, ACCOUNT_FUNDED_BELOW_MINIMUM, available=10.0, wallet=10.0)

    payload = build_funding_gate_role_specific_sync(log_dir=log_dir, config_path=_write_config(tmp_path), now=NOW)

    assert payload["latest_balance_state"]["balance_readiness"] == ACCOUNT_FUNDED_BELOW_MINIMUM
    assert payload["funding_gate"]["funding_sync_status"] == FUNDING_SYNC_BELOW_MINIMUM
    assert payload["funding_gate"]["funding_blocker"] == "below_minimum"
    assert payload["funding_gate"]["funding_ready"] is False


def test_funded_at_minimum_produces_ready_for_review_but_not_live_ready(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _record_role_specific_verify(log_dir)
    _record_balance(log_dir, ACCOUNT_FUNDED_READY_FOR_REVIEW, available=44.0, wallet=44.0)

    payload = build_funding_gate_role_specific_sync(log_dir=log_dir, config_path=_write_config(tmp_path), now=NOW)

    assert payload["latest_balance_state"]["balance_readiness"] == ACCOUNT_FUNDED_READY_FOR_REVIEW
    assert payload["funding_gate"]["funding_sync_status"] == FUNDING_SYNC_READY_FOR_REVIEW
    assert payload["funding_gate"]["funding_ready"] is True
    assert payload["funding_gate"]["safe_to_arm_live"] is False
    assert payload["tiny_live_blocker_summary"]["risk_contract_blocked"] is True
    assert payload["tiny_live_blocker_summary"]["operator_approval_blocked"] is True
    assert payload["tiny_live_blocker_summary"]["global_live_flags_blocked"] is True


def test_no_secrets_shown(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _record_role_specific_verify(log_dir)
    _record_balance(log_dir, ACCOUNT_NOT_FUNDED, available=0.0, wallet=0.0)

    payload = build_funding_gate_role_specific_sync(log_dir=log_dir, config_path=_write_config(tmp_path), now=NOW)
    rendered = json.dumps(payload, sort_keys=True)

    assert "account-key-full-value" not in rendered
    assert "account-secret-full-value" not in rendered
    assert payload["account_read_role_state"]["secrets_shown"] is False
    assert payload["safety"]["secrets_shown"] is False
    assert payload["safety"]["full_api_key_shown"] is False
    assert payload["safety"]["full_api_secret_shown"] is False


def test_no_env_config_mutation_no_binance_calls(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path)
    _record_role_specific_verify(log_dir)
    _record_balance(log_dir, ACCOUNT_NOT_FUNDED, available=0.0, wallet=0.0)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_funding_gate_role_specific_sync(log_dir=log_dir, config_path=config_path, now=NOW)

    urlopen.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["risk_contract_config_written"] is False


def test_no_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    _record_role_specific_verify(log_dir)
    _record_balance(log_dir, ACCOUNT_NOT_FUNDED, available=0.0, wallet=0.0)

    with (
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_funding_gate_role_specific_sync(log_dir=log_dir, config_path=_write_config(tmp_path), now=NOW)

    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    safety = payload["safety"]
    assert safety["order_placed"] is False
    assert safety["real_order_placed"] is False
    assert safety["execution_attempted"] is False
    assert safety["order_payload_created"] is False
    assert safety["executable_payload_created"] is False
    assert safety["signed_order_request_created"] is False
    assert safety["signed_trading_request_created"] is False
    assert safety["signed_readonly_request_created"] is False
    assert safety["binance_order_endpoint_called"] is False
    assert safety["binance_test_order_endpoint_called"] is False
    assert safety["transfer_endpoint_called"] is False
    assert safety["withdraw_endpoint_called"] is False
    assert safety["global_live_flags_changed"] is False
    assert safety["paper_live_separation_intact"] is True


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "funding-gate-role-specific-sync",
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
    assert payload["status"] == FUNDING_GATE_ROLE_SPECIFIC_SYNC_BLOCKED
    assert "funding-gate-role-specific-sync" in help_result.stdout


def _record_role_specific_verify(log_dir: Path) -> None:
    build_account_read_env_migration_verify(
        log_dir=log_dir,
        record_verify=True,
        confirm_account_read_env_migration_verify=CONFIRM_ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDING_PHRASE,
        env={**SAFE_FLAGS, **ACCOUNT_READ_PAIR},
        now=NOW,
    )


def _record_balance(log_dir: Path, readiness: str, *, available: float, wallet: float) -> None:
    append_readonly_balance_check_record(
        {
            "status": "READONLY_BALANCE_CHECK_RECORDED",
            "generated_at": NOW.isoformat(),
            "record_balance_check_requested": True,
            "confirmation_valid": True,
            "allow_readonly_network_check": True,
            "target_family": {
                "lane_key": LANE_8M_SHORT,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "current_mode": "paper",
            },
            "readonly_preflight": {},
            "env_role_resolution": {},
            "balance_check": {
                "available_balance_usdt": available,
                "wallet_balance_usdt": wallet,
                "minimum_balance_required_estimate_usdt": 44.0,
                "funding_ready": readiness == ACCOUNT_FUNDED_READY_FOR_REVIEW,
                "funding_status": readiness,
                "network_check_attempted": True,
                "balance_check_attempted": True,
                "signed_readonly_request_created": True,
            },
            "balance_readiness": readiness,
            "blockers": [],
            "safety": {
                "signed_readonly_request_created": True,
                "signed_trading_request_created": False,
                "signed_order_request_created": False,
                "secrets_shown": False,
            },
        },
        log_dir=log_dir,
    )


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "lane_controls.json"
    path.write_text(
        json.dumps(
            {
                "lanes": [
                    {
                        "symbol": "BTCUSDT",
                        "timeframe": "8m",
                        "direction": "short",
                        "entry_mode": "ladder_close_50_618",
                        "mode": "paper",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path
