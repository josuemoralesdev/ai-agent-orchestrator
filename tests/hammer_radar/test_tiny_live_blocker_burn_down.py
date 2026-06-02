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
from src.app.hammer_radar.operator.readonly_balance_check import (
    ACCOUNT_NOT_FUNDED,
    append_readonly_balance_check_record,
)
from src.app.hammer_radar.operator.short_strategy_packet import MIN_FRESH_CANDIDATES
from src.app.hammer_radar.operator.tiny_live_blocker_burn_down import (
    CONFIRM_TINY_LIVE_BURN_DOWN_RECORDING_PHRASE,
    LEDGER_FILENAME,
    NOT_CLOSE_MULTIPLE_HARD_BLOCKERS,
    TINY_LIVE_BLOCKER_BURN_DOWN_RECORDED,
    TINY_LIVE_BLOCKER_BURN_DOWN_REJECTED,
    build_tiny_live_blocker_burn_down,
    load_tiny_live_blocker_burn_down_records,
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
    _record_account_not_funded(log_dir)

    payload = build_tiny_live_blocker_burn_down(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["burn_down_recorded"] is False
    assert payload["burn_down_id"] is None
    assert payload["record_burn_down_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _record_account_not_funded(log_dir)

    payload = build_tiny_live_blocker_burn_down(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        record_burn_down=True,
        confirm_tiny_live_burn_down="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_BLOCKER_BURN_DOWN_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["burn_down_recorded"] is False
    assert load_tiny_live_blocker_burn_down_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    _record_account_not_funded(log_dir)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")

    payload = build_tiny_live_blocker_burn_down(
        log_dir=log_dir,
        config_path=config_path,
        risk_contract_config_path=risk_path,
        record_burn_down=True,
        confirm_tiny_live_burn_down=CONFIRM_TINY_LIVE_BURN_DOWN_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_tiny_live_blocker_burn_down_records(log_dir=log_dir, limit=0)

    assert payload["status"] == TINY_LIVE_BLOCKER_BURN_DOWN_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["burn_down_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "TINY_LIVE_BLOCKER_BURN_DOWN"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert before_risk == risk_path.read_text(encoding="utf-8")


def test_default_target_lane_is_btcusdt_8m_short(tmp_path: Path) -> None:
    payload = build_tiny_live_blocker_burn_down(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["target_family"] == {
        "lane_key": LANE_8M_SHORT,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "current_mode": "paper",
    }


def test_blockers_detect_current_not_funded_below_evidence_draft_paper_and_safety_locks(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _record_account_not_funded(log_dir)
    _write_capture(log_dir, "fresh-short-1")

    payload = build_tiny_live_blocker_burn_down(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )
    blockers = payload["blockers"]

    assert blockers["funding"]["status"] == "blocked"
    assert blockers["funding"]["current"] == "ACCOUNT_NOT_FUNDED / 0.0 USDT"
    assert blockers["fresh_evidence"]["status"] == "blocked"
    assert blockers["fresh_evidence"]["current"] == f"1 / {MIN_FRESH_CANDIDATES} fresh captures"
    assert blockers["risk_contract"]["status"] == "blocked"
    assert blockers["risk_contract"]["current"] == "draft preview only / not applied"
    assert blockers["lane_mode"]["status"] == "blocked"
    assert blockers["lane_mode"]["current"] == "paper"
    assert blockers["protective_policy"]["status"] == "blocked"
    assert blockers["operator_approval"]["status"] == "blocked"
    assert blockers["live_flags"]["status"] == "blocked"
    assert payload["tiny_live_distance"] == NOT_CLOSE_MULTIPLE_HARD_BLOCKERS


def test_cleared_items_next_path_and_recommendations(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _record_account_not_funded(log_dir)

    payload = build_tiny_live_blocker_burn_down(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert "candidate door identified" in payload["cleared_items"]
    assert "account-read role-specific env verified" in payload["cleared_items"]
    assert payload["shortest_safe_path"] == [
        "continue R157 until fresh captures >= 10",
        "fund account later",
        "rerun R158/R174 sync",
        "apply risk contract in future safe config phase",
        "build tiny-live review packet",
        "operator approval",
        "arming phase",
    ]
    assert payload["recommended_next_operator_move"] == "KEEP_R157_RUNNING"
    assert payload["recommended_next_engineering_move"].startswith("Build R176 capture-count sync")
    assert "write risk contract config" in payload["do_not_run_yet"]
    assert "live-connector-submit" in payload["do_not_run_yet"]


def test_no_env_config_mutation_no_binance_calls(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    _record_account_not_funded(log_dir)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_tiny_live_blocker_burn_down(
            log_dir=log_dir,
            config_path=config_path,
            risk_contract_config_path=risk_path,
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert before_risk == risk_path.read_text(encoding="utf-8")
    safety = payload["safety"]
    assert safety["env_written"] is False
    assert safety["env_mutated"] is False
    assert safety["config_written"] is False
    assert safety["risk_contract_config_written"] is False
    assert safety["lane_config_written"] is False
    assert safety["binance_order_endpoint_called"] is False


def test_no_order_live_transfer_withdraw_or_signed_actions(tmp_path: Path) -> None:
    payload = build_tiny_live_blocker_burn_down(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )
    safety = payload["safety"]

    assert safety["order_placed"] is False
    assert safety["real_order_placed"] is False
    assert safety["execution_attempted"] is False
    assert safety["order_payload_created"] is False
    assert safety["executable_payload_created"] is False
    assert safety["signed_order_request_created"] is False
    assert safety["signed_trading_request_created"] is False
    assert safety["signed_readonly_request_created"] is False
    assert safety["binance_test_order_endpoint_called"] is False
    assert safety["transfer_endpoint_called"] is False
    assert safety["withdraw_endpoint_called"] is False
    assert safety["secrets_shown"] is False
    assert safety["full_api_key_shown"] is False
    assert safety["full_api_secret_shown"] is False
    assert safety["global_live_flags_changed"] is False
    assert safety["kill_switch_disabled"] is False
    assert safety["paper_live_separation_intact"] is True


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "tiny-live-blocker-burn-down",
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
    assert "tiny-live-blocker-burn-down" in help_result.stdout


def _record_account_not_funded(log_dir: Path) -> None:
    build_account_read_env_migration_verify(
        log_dir=log_dir,
        record_verify=True,
        confirm_account_read_env_migration_verify=CONFIRM_ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDING_PHRASE,
        env={**SAFE_FLAGS, **ACCOUNT_READ_PAIR},
        now=NOW,
    )
    append_readonly_balance_check_record(
        {
            "status": "READONLY_BALANCE_CHECK_RECORDED",
            "generated_at": NOW.isoformat(),
            "record_balance_check_requested": True,
            "confirmation_valid": True,
            "target_family": {
                "lane_key": LANE_8M_SHORT,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "current_mode": "paper",
            },
            "balance_check": {
                "available_balance_usdt": 0.0,
                "wallet_balance_usdt": 0.0,
                "minimum_balance_required_estimate_usdt": 44.0,
                "funding_status": ACCOUNT_NOT_FUNDED,
                "funding_ready": False,
                "signed_readonly_request_created": True,
            },
            "balance_readiness": ACCOUNT_NOT_FUNDED,
            "safety": {"signed_readonly_request_created": True, "secrets_shown": False},
        },
        log_dir=log_dir,
    )


def _write_capture(log_dir: Path, signal_id: str) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "short_paper_evidence_capture.ndjson").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE",
                    "status": "SHORT_PAPER_EVIDENCE_CAPTURED",
                    "capture_id": f"capture-{signal_id}",
                    "captured_signal_id": signal_id,
                    "captured_lane_key": LANE_8M_SHORT,
                    "paper_evidence_captured": True,
                    "target_lane": {
                        "lane_key": LANE_8M_SHORT,
                        "symbol": "BTCUSDT",
                        "timeframe": "8m",
                        "direction": "short",
                        "entry_mode": "ladder_close_50_618",
                        "mode": "paper",
                    },
                    "safety": {"order_placed": False, "real_order_placed": False, "execution_attempted": False},
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lanes = [
        {
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "mode": "paper",
            "max_daily_trades": 1,
            "max_daily_loss_pct": 0.15,
            "freshness_seconds": 60,
            "cooldown_after_loss_minutes": 120,
            "require_protective_orders": True,
        }
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
                    "funding_check_mode": "LOCAL_CONFIG_ONLY_NO_NETWORK",
                    "max_margin_usdt": 44.0,
                },
                "risk_contracts": [
                    {
                        "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                        "symbol": "BTCUSDT",
                        "timeframe": "13m",
                        "direction": "long",
                        "entry_mode": "ladder_close_50_618",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path
