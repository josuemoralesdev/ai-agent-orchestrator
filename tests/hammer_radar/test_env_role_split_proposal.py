from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.env_role_split_proposal import (
    ACCOUNT_READ_KEY_VAR,
    CONFIRM_ENV_ROLE_SPLIT_PROPOSAL_RECORDING_PHRASE,
    ENV_ROLE_SPLIT_PROPOSAL_RECORDED,
    ENV_ROLE_SPLIT_PROPOSAL_REJECTED,
    LEDGER_FILENAME,
    LIVE_KEY_VAR,
    MARKET_KEY_VAR,
    build_current_env_role_inventory,
    build_env_role_split_proposal,
    build_proposed_env_role_schema,
    load_env_role_split_proposal_records,
)

NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = build_env_role_split_proposal(
        log_dir=log_dir,
        repo_env_path=_write_env(tmp_path / ".env", key="repo-key", secret="repo-secret"),
        readonly_env_path=_write_env(tmp_path / "readonly.env", key="market-key", secret="market-secret"),
        live_env_path=_write_env(tmp_path / "live.env", key="account-key", secret="account-secret"),
        now=NOW,
    )

    assert payload["proposal_recorded"] is False
    assert payload["proposal_id"] is None
    assert payload["record_proposal_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = build_env_role_split_proposal(
        log_dir=log_dir,
        repo_env_path=_write_env(tmp_path / ".env", key="repo-key", secret="repo-secret"),
        readonly_env_path=_write_env(tmp_path / "readonly.env", key="market-key", secret="market-secret"),
        live_env_path=_write_env(tmp_path / "live.env", key="account-key", secret="account-secret"),
        record_proposal=True,
        confirm_env_role_split_proposal="wrong",
        now=NOW,
    )

    assert payload["status"] == ENV_ROLE_SPLIT_PROPOSAL_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["proposal_recorded"] is False
    assert payload["recommended_next_operator_move"] == "KEEP_CURRENT_ENV_UNCHANGED"
    assert load_env_role_split_proposal_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
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

    payload = build_env_role_split_proposal(
        log_dir=log_dir,
        repo_env_path=repo_env,
        readonly_env_path=readonly_env,
        live_env_path=live_env,
        record_proposal=True,
        confirm_env_role_split_proposal=CONFIRM_ENV_ROLE_SPLIT_PROPOSAL_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_env_role_split_proposal_records(log_dir=log_dir, limit=0)

    assert payload["status"] == ENV_ROLE_SPLIT_PROPOSAL_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["proposal_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "ENV_ROLE_SPLIT_PROPOSAL"
    assert config_path.read_text(encoding="utf-8") == before["config"]
    assert repo_env.read_text(encoding="utf-8") == before["repo_env"]
    assert readonly_env.read_text(encoding="utf-8") == before["readonly_env"]
    assert live_env.read_text(encoding="utf-8") == before["live_env"]


def test_current_inventory_uses_hashes_and_lengths_only(tmp_path: Path) -> None:
    inventory = build_current_env_role_inventory(
        repo_env_path=_write_env(tmp_path / ".env", key="repo-key-full-value", secret="repo-secret-full-value"),
        readonly_env_path=_write_env(tmp_path / "readonly.env", key="market-key-full-value", secret="market-secret-full-value"),
        live_env_path=_write_env(tmp_path / "live.env", key="account-key-full-value", secret="account-secret-full-value"),
    )
    rendered = json.dumps(inventory, sort_keys=True)

    assert inventory["repo_env"]["api_key_length"] == len("repo-key-full-value")
    assert inventory["repo_env"]["api_secret_length"] == len("repo-secret-full-value")
    assert inventory["repo_env"]["api_key_hash_preview"]
    assert inventory["repo_env"]["api_secret_hash_preview"]
    assert inventory["secrets_shown"] is False
    assert "repo-key-full-value" not in rendered
    assert "repo-secret-full-value" not in rendered
    assert "market-key-full-value" not in rendered
    assert "market-secret-full-value" not in rendered
    assert "account-key-full-value" not in rendered
    assert "account-secret-full-value" not in rendered


def test_mismatched_repo_env_pair_is_detected_from_mocked_data(tmp_path: Path) -> None:
    inventory = build_current_env_role_inventory(
        repo_env_path=_write_env(tmp_path / ".env", key="account-key", secret="wrong-secret"),
        readonly_env_path=_write_env(tmp_path / "readonly.env", key="market-key", secret="market-secret"),
        live_env_path=_write_env(tmp_path / "live.env", key="account-key", secret="account-secret"),
    )

    assert inventory["mismatched_pair_detected"] is True
    assert inventory["mismatch_evidence"]
    assert inventory["secrets_shown"] is False


def test_proposed_schema_includes_market_account_and_live_roles() -> None:
    schema = build_proposed_env_role_schema()

    assert schema["market_data_role"]["api_key_variable"] == MARKET_KEY_VAR
    assert schema["account_read_role"]["api_key_variable"] == ACCOUNT_READ_KEY_VAR
    assert schema["future_live_role"]["api_key_variable"] == LIVE_KEY_VAR
    assert schema["runtime_safety_flags"]["BINANCE_CONNECTOR_MODE"] == "read_only"
    assert schema["runtime_safety_flags"]["HAMMER_GLOBAL_KILL_SWITCH"] == "true"


def test_backward_compatibility_and_migration_steps_included(tmp_path: Path) -> None:
    payload = build_env_role_split_proposal(
        log_dir=tmp_path / "logs",
        repo_env_path=_write_env(tmp_path / ".env", key="repo-key", secret="repo-secret"),
        readonly_env_path=_write_env(tmp_path / "readonly.env", key="market-key", secret="market-secret"),
        live_env_path=_write_env(tmp_path / "live.env", key="account-key", secret="account-secret"),
        now=NOW,
    )

    assert payload["backward_compatibility_plan"]["short_term_support"] is True
    assert payload["backward_compatibility_plan"]["legacy_variables"] == ["BINANCE_API_KEY", "BINANCE_API_SECRET"]
    assert payload["operator_migration_steps"]
    assert any(step["action"] == "approve_r170_adapter_preview" for step in payload["operator_migration_steps"])


def test_no_env_config_mutation_and_no_binance_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    repo_env = _write_env(tmp_path / ".env", key="repo-key", secret="repo-secret")
    readonly_env = _write_env(tmp_path / "readonly.env", key="market-key", secret="market-secret")
    live_env = _write_env(tmp_path / "live.env", key="account-key", secret="account-secret")
    before_env = dict(os.environ)
    before_files = {
        path: path.read_text(encoding="utf-8")
        for path in (config_path, repo_env, readonly_env, live_env)
    }

    payload = build_env_role_split_proposal(
        log_dir=log_dir,
        repo_env_path=repo_env,
        readonly_env_path=readonly_env,
        live_env_path=live_env,
        record_proposal=True,
        confirm_env_role_split_proposal=CONFIRM_ENV_ROLE_SPLIT_PROPOSAL_RECORDING_PHRASE,
        now=NOW,
    )

    assert before_env == dict(os.environ)
    assert {path: path.read_text(encoding="utf-8") for path in before_files} == before_files
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["binance_test_order_endpoint_called"] is False
    assert payload["safety"]["transfer_endpoint_called"] is False
    assert payload["safety"]["withdraw_endpoint_called"] is False
    assert "write env files" in payload["do_not_run_yet"]
    assert "any order endpoint" in payload["do_not_run_yet"]
    assert "transfer" in payload["do_not_run_yet"]
    assert "withdraw" in payload["do_not_run_yet"]


def test_cli_exists() -> None:
    result = subprocess.run(
        [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "env-role-split-proposal" in result.stdout


def _write_env(path: Path, *, key: str, secret: str) -> Path:
    path.write_text(f"BINANCE_API_KEY={key}\nBINANCE_API_SECRET={secret}\n", encoding="utf-8")
    return path


def _write_config(path: Path) -> Path:
    path.write_text(json.dumps({"lanes": []}), encoding="utf-8")
    return path
