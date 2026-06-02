from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.funding_gate_key_role_sync import (
    CONFIRM_FUNDING_KEY_ROLE_SYNC_RECORDING_PHRASE,
    FUNDING_GATE_KEY_ROLE_SYNC_RECORDED,
    FUNDING_GATE_KEY_ROLE_SYNC_REJECTED,
    LEDGER_FILENAME,
    build_funding_gate_key_role_sync,
    detect_key_secret_pair_mismatch,
    load_funding_gate_key_role_sync_records,
)
from src.app.hammer_radar.operator.readonly_balance_check import (
    ACCOUNT_NOT_FUNDED,
    LEDGER_FILENAME as READONLY_BALANCE_LEDGER_FILENAME,
)

NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_account_not_funded_balance_record(log_dir)

    payload = build_funding_gate_key_role_sync(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        repo_env_path=_write_env(tmp_path / ".env", key="repo-key", secret="repo-secret"),
        readonly_env_path=_write_env(tmp_path / "readonly.env", key="market-key", secret="market-secret"),
        live_env_path=_write_env(tmp_path / "live.env", key="account-key", secret="account-secret"),
        now=NOW,
    )

    assert payload["sync_recorded"] is False
    assert payload["sync_id"] is None
    assert payload["record_sync_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_account_not_funded_balance_record(log_dir)

    payload = build_funding_gate_key_role_sync(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        repo_env_path=_write_env(tmp_path / ".env", key="repo-key", secret="repo-secret"),
        readonly_env_path=_write_env(tmp_path / "readonly.env", key="market-key", secret="market-secret"),
        live_env_path=_write_env(tmp_path / "live.env", key="account-key", secret="account-secret"),
        record_sync=True,
        confirm_funding_key_role_sync="wrong",
        now=NOW,
    )

    assert payload["status"] == FUNDING_GATE_KEY_ROLE_SYNC_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["sync_recorded"] is False
    assert load_funding_gate_key_role_sync_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_account_not_funded_balance_record(log_dir)
    config_path = _write_config(tmp_path / "lane_controls.json")
    repo_env = _write_env(tmp_path / ".env", key="repo-key", secret="repo-secret")
    readonly_env = _write_env(tmp_path / "readonly.env", key="market-key", secret="market-secret")
    live_env = _write_env(tmp_path / "live.env", key="account-key", secret="account-secret")
    before = {
        "config": config_path.read_text(encoding="utf-8"),
        "repo_env": repo_env.read_text(encoding="utf-8"),
        "readonly_env": readonly_env.read_text(encoding="utf-8"),
        "live_env": live_env.read_text(encoding="utf-8"),
    }

    payload = build_funding_gate_key_role_sync(
        log_dir=log_dir,
        config_path=config_path,
        repo_env_path=repo_env,
        readonly_env_path=readonly_env,
        live_env_path=live_env,
        record_sync=True,
        confirm_funding_key_role_sync=CONFIRM_FUNDING_KEY_ROLE_SYNC_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_funding_gate_key_role_sync_records(log_dir=log_dir, limit=0)

    assert payload["status"] == FUNDING_GATE_KEY_ROLE_SYNC_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["sync_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "FUNDING_GATE_KEY_ROLE_SYNC"
    assert config_path.read_text(encoding="utf-8") == before["config"]
    assert repo_env.read_text(encoding="utf-8") == before["repo_env"]
    assert readonly_env.read_text(encoding="utf-8") == before["readonly_env"]
    assert live_env.read_text(encoding="utf-8") == before["live_env"]


def test_detects_mismatched_repo_env_pair_from_mocked_hash_summaries() -> None:
    summary = {
        "repo_env": {
            "api_key_hash_preview": "key-market",
            "api_key_length": 10,
            "api_secret_hash_preview": "secret-account",
            "api_secret_length": 14,
        },
        "binance_readonly_env": {
            "api_key_hash_preview": "key-market",
            "api_key_length": 10,
            "api_secret_hash_preview": "secret-market",
            "api_secret_length": 13,
        },
        "binance_live_env": {
            "api_key_hash_preview": "key-account",
            "api_key_length": 11,
            "api_secret_hash_preview": "secret-account",
            "api_secret_length": 14,
        },
    }

    mismatch = detect_key_secret_pair_mismatch(summary)

    assert mismatch["mismatched_pair_detected"] is True
    assert mismatch["secrets_shown"] is False
    assert mismatch["mismatch_evidence"]


def test_latest_account_not_funded_balance_result_is_surfaced(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_account_not_funded_balance_record(log_dir)

    payload = build_funding_gate_key_role_sync(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        repo_env_path=_write_env(tmp_path / ".env", key="repo-key", secret="repo-secret"),
        readonly_env_path=_write_env(tmp_path / "readonly.env", key="market-key", secret="market-secret"),
        live_env_path=_write_env(tmp_path / "live.env", key="account-key", secret="account-secret"),
        now=NOW,
    )

    assert payload["target_family"]["lane_key"] == LANE_8M_SHORT
    assert payload["latest_balance_result"]["funding_status"] == ACCOUNT_NOT_FUNDED
    assert payload["latest_balance_result"]["balance_readiness"] == ACCOUNT_NOT_FUNDED
    assert payload["latest_balance_result"]["available_balance_usdt"] == 0.0
    assert payload["latest_balance_result"]["wallet_balance_usdt"] == 0.0
    assert payload["funding_gate"]["funding_ready"] is False
    assert payload["funding_gate"]["funding_status"] == ACCOUNT_NOT_FUNDED


def test_no_secrets_shown(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_account_not_funded_balance_record(log_dir)

    payload = build_funding_gate_key_role_sync(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        repo_env_path=_write_env(tmp_path / ".env", key="repo-key-full-value", secret="repo-secret-full-value"),
        readonly_env_path=_write_env(tmp_path / "readonly.env", key="market-key-full-value", secret="market-secret-full-value"),
        live_env_path=_write_env(tmp_path / "live.env", key="account-key-full-value", secret="account-secret-full-value"),
        now=NOW,
    )
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["key_role_summary"]["secrets_shown"] is False
    assert payload["safety"]["secrets_shown"] is False
    assert "repo-key-full-value" not in rendered
    assert "repo-secret-full-value" not in rendered
    assert "market-key-full-value" not in rendered
    assert "market-secret-full-value" not in rendered
    assert "account-key-full-value" not in rendered
    assert "account-secret-full-value" not in rendered


def test_no_env_config_mutation_and_no_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_account_not_funded_balance_record(log_dir)
    config_path = _write_config(tmp_path / "lane_controls.json")
    repo_env = _write_env(tmp_path / ".env", key="repo-key", secret="repo-secret")
    readonly_env = _write_env(tmp_path / "readonly.env", key="market-key", secret="market-secret")
    live_env = _write_env(tmp_path / "live.env", key="account-key", secret="account-secret")
    before_env = dict(os.environ)
    before_files = {
        path: path.read_text(encoding="utf-8")
        for path in (config_path, repo_env, readonly_env, live_env)
    }

    payload = build_funding_gate_key_role_sync(
        log_dir=log_dir,
        config_path=config_path,
        repo_env_path=repo_env,
        readonly_env_path=readonly_env,
        live_env_path=live_env,
        record_sync=True,
        confirm_funding_key_role_sync=CONFIRM_FUNDING_KEY_ROLE_SYNC_RECORDING_PHRASE,
        now=NOW,
    )

    assert before_env == dict(os.environ)
    assert {path: path.read_text(encoding="utf-8") for path in before_files} == before_files
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        elif key == "signed_request_created_scope":
            assert value == "none"
        else:
            assert value is False, key
    assert "live-connector-submit" in payload["do_not_run_yet"]
    assert "any order endpoint" in payload["do_not_run_yet"]
    assert "transfer" in payload["do_not_run_yet"]
    assert "withdraw" in payload["do_not_run_yet"]


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "funding-gate-key-role-sync" in result.stdout


def _write_account_not_funded_balance_record(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "event_type": "READONLY_BALANCE_CHECK",
        "balance_check_id": "r164_readonly_balance_check_test",
        "recorded_at_utc": NOW.isoformat(),
        "status": "READONLY_BALANCE_CHECK_RECORDED",
        "generated_at": NOW.isoformat(),
        "target_family": {
            "lane_key": LANE_8M_SHORT,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "current_mode": "paper",
        },
        "balance_check": {
            "asset": "USDT",
            "available_balance_usdt": 0.0,
            "wallet_balance_usdt": 0.0,
            "funding_ready": False,
            "funding_status": ACCOUNT_NOT_FUNDED,
            "network_check_attempted": True,
            "balance_check_attempted": True,
            "signed_readonly_request_created": True,
        },
        "balance_readiness": ACCOUNT_NOT_FUNDED,
        "safety": {
            "signed_trading_request_created": False,
            "secrets_shown": False,
        },
    }
    with (log_dir / READONLY_BALANCE_LEDGER_FILENAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def _write_env(path: Path, *, key: str, secret: str) -> Path:
    path.write_text(f"BINANCE_API_KEY={key}\nBINANCE_API_SECRET={secret}\n", encoding="utf-8")
    return path


def _write_config(path: Path) -> Path:
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
