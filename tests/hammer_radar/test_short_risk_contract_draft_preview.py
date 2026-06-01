from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.short_risk_contract_draft_preview import (
    CONFIRM_SHORT_RISK_CONTRACT_DRAFT_RECORDING_PHRASE,
    LEDGER_FILENAME,
    SHORT_RISK_CONTRACT_DRAFT_PREVIEW_READY,
    SHORT_RISK_CONTRACT_DRAFT_PREVIEW_RECORDED,
    SHORT_RISK_CONTRACT_DRAFT_PREVIEW_REJECTED,
    build_short_risk_contract_draft_preview,
    load_short_risk_contract_draft_records,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_config(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    before_config = config_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")

    payload = build_short_risk_contract_draft_preview(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == SHORT_RISK_CONTRACT_DRAFT_PREVIEW_READY
    assert config_path.read_text(encoding="utf-8") == before_config
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["risk_contract_config_written"] is False


def test_preview_writes_no_draft_record(tmp_path: Path) -> None:
    payload = build_short_risk_contract_draft_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["draft_recorded"] is False
    assert payload["draft_id"] is None
    assert payload["record_draft_requested"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    payload = build_short_risk_contract_draft_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        record_draft=True,
        confirm_short_risk_contract_draft="wrong",
        now=NOW,
    )

    assert payload["status"] == SHORT_RISK_CONTRACT_DRAFT_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["draft_recorded"] is False
    assert load_short_risk_contract_draft_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_draft_only(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    before_config = config_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")

    payload = build_short_risk_contract_draft_preview(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        risk_contract_config_path=risk_path,
        record_draft=True,
        confirm_short_risk_contract_draft=CONFIRM_SHORT_RISK_CONTRACT_DRAFT_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_short_risk_contract_draft_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == SHORT_RISK_CONTRACT_DRAFT_PREVIEW_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["draft_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "SHORT_RISK_CONTRACT_DRAFT_PREVIEW"
    assert config_path.read_text(encoding="utf-8") == before_config
    assert risk_path.read_text(encoding="utf-8") == before_risk


def test_target_lane_default_is_8m_short_and_remains_paper(tmp_path: Path) -> None:
    payload = build_short_risk_contract_draft_preview(
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


def test_contract_draft_values(tmp_path: Path) -> None:
    payload = build_short_risk_contract_draft_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )
    draft = payload["contract_draft"]

    assert draft["max_daily_trades"] == 1
    assert draft["max_daily_loss_pct"] == 0.15
    assert draft["require_protective_orders"] is True
    assert draft["protective_stop_required"] is True
    assert draft["take_profit_required"] is True
    assert draft["require_short_specific_stop_tp"] is True
    assert draft["golden_pocket_role"] == "resistance/retrace zone"
    assert draft["config_write_allowed_now"] is False
    assert draft["execution_allowed_now"] is False


def test_diff_preview_is_non_writing(tmp_path: Path) -> None:
    payload = build_short_risk_contract_draft_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )
    diff = payload["contract_diff_preview"]

    assert diff["would_create_target_contract"] is True
    assert diff["would_modify_existing_contract"] is False
    assert diff["would_write_config_now"] is False
    assert diff["preview_only"] is True
    assert diff["proposed_config_patch"]["apply_allowed_now"] is False


def test_safe_commands_and_forbidden_commands(tmp_path: Path) -> None:
    payload = build_short_risk_contract_draft_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )
    safe_joined = "\n".join(payload["safe_commands"]).lower()

    assert "short-paper-evidence-capture-loop" in safe_joined
    assert "short-evidence-recheck-packet" in safe_joined
    assert "fundless-short-dry-run-packet" in safe_joined
    assert "short-risk-contract-draft-preview" in safe_joined
    assert "live-connector-submit" not in safe_joined
    assert "lane-control-command" not in safe_joined
    assert "--apply" not in safe_joined
    assert "write risk contract config" in payload["do_not_run_yet"]
    assert "set short lane tiny_live" in payload["do_not_run_yet"]
    assert "set new lane tiny_live" in payload["do_not_run_yet"]
    assert "protective order submit" in payload["do_not_run_yet"]


def test_gate_blockers_future_requirements_and_safety(tmp_path: Path) -> None:
    payload = build_short_risk_contract_draft_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert "fresh captures below threshold" in payload["gate_blockers"]
    assert "funding not verified" in payload["gate_blockers"]
    assert "operator approval missing" in payload["gate_blockers"]
    assert "lane remains paper" in payload["gate_blockers"]
    assert "config write not authorized" in payload["gate_blockers"]
    assert payload["future_apply_requirements"]["requires_explicit_future_confirmation"] is True
    assert payload["future_apply_requirements"]["requires_r158_ready"] is True
    assert payload["future_apply_requirements"]["requires_funding_verified"] is True
    assert payload["future_apply_requirements"]["requires_operator_review"] is True
    assert payload["future_apply_requirements"]["requires_config_write_phase"] is True
    assert payload["future_apply_requirements"]["requires_no_live_execution_in_apply_phase"] is True
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_no_binance_order_payload_network_env_config_or_global_mutation(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    config_path = _write_config(tmp_path / "lane_controls.json")
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
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
        payload = build_short_risk_contract_draft_preview(
            log_dir=tmp_path / "logs",
            config_path=config_path,
            risk_contract_config_path=risk_path,
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
    assert before_risk == risk_path.read_text(encoding="utf-8")
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


def test_cli_exists_and_preview_returns_expected_shape(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "short-risk-contract-draft-preview",
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
    assert "existing_contract_summary" in payload
    assert "contract_draft" in payload
    assert "contract_diff_preview" in payload
    assert "short-risk-contract-draft-preview" in help_result.stdout


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
                    "funding_config_present": True,
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
