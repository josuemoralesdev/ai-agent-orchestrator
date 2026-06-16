from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_loop import (
    AUTONOMOUS_TRIGGER_BLOCKED,
    AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED,
    AUTONOMOUS_TRIGGER_NOT_CHECKED,
    AUTONOMOUS_TRIGGER_WAIT,
    build_tiny_live_autonomous_trigger_loop,
)
from tests.hammer_radar.test_tiny_live_one_shot_pre_activation_gate import (
    LANE_44M_LONG,
    LANE_44M_SHORT,
    NOW,
    _binance_ready,
    _contract,
    _post_manual_verified,
    _watch_wait,
    _watch_with_candidate,
    _write_risk_contracts,
)


def test_no_candidate_waits_for_fresh_live_qualified_candidate(tmp_path: Path) -> None:
    payload = build_tiny_live_autonomous_trigger_loop(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_wait(),
        now=NOW,
    )

    assert payload["status"] == AUTONOMOUS_TRIGGER_WAIT
    assert payload["current_fresh_candidate_exists"] is False
    assert payload["next_required_step"] == "WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE"
    assert payload["per_signal_operator_approval_required"] is False
    assert payload["alert_is_visibility_only"] is True
    _assert_no_submit_or_mutation(payload)


def test_paper_only_candidate_blocks_without_approval_prompt(tmp_path: Path) -> None:
    payload = build_tiny_live_autonomous_trigger_loop(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(live_class="PAPER_ONLY", status="BLOCKED_PAPER_ONLY"),
        now=NOW,
    )

    assert payload["status"] == AUTONOMOUS_TRIGGER_BLOCKED
    assert "paper_only" in payload["blockers"]
    assert payload["per_signal_operator_approval_required"] is False
    assert payload["alert_payload"]["permission_gate"] is False
    _assert_no_submit_or_mutation(payload)


def test_near_miss_candidate_blocks(tmp_path: Path) -> None:
    payload = build_tiny_live_autonomous_trigger_loop(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(live_class="NEAR_MISS_INCUBATOR", status="BLOCKED_NEAR_MISS"),
        now=NOW,
    )

    assert payload["status"] == AUTONOMOUS_TRIGGER_BLOCKED
    assert "near_miss" in payload["blockers"]
    _assert_no_submit_or_mutation(payload)


def test_approved_candidate_but_lane_not_armed_blocks_exact_lane_not_armed(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[_contract(LANE_44M_SHORT)])
    payload = build_tiny_live_autonomous_trigger_loop(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_44M_SHORT, direction="short"),
        now=NOW,
    )

    assert payload["status"] == AUTONOMOUS_TRIGGER_BLOCKED
    assert payload["approved_lane_match"] is True
    assert payload["candidate_live_qualified"] is True
    assert "exact_lane_not_armed" in payload["blockers"]
    assert payload["next_required_step"] == "ARM_APPROVED_LANE_DRY_RUN_ONLY_IF_OPERATOR_WANTS_MACHINE_ACTIVE"
    _assert_no_submit_or_mutation(payload)


def test_approved_candidate_lane_armed_gates_green_records_dry_run_lifecycle(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[_contract(LANE_44M_LONG)])
    arming_path = _write_armed_state(tmp_path, LANE_44M_LONG)
    payload = build_tiny_live_autonomous_trigger_loop(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        autonomous_arming_config_path=arming_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_44M_LONG),
        record_autonomous_trigger_loop=True,
        operator_id="local_operator",
        reason="test autonomous dry-run trigger loop",
        now=NOW,
    )

    assert payload["status"] == AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED
    assert payload["autonomous_dry_run_execution_recorded"] is True
    assert payload["exact_lane_auto_armed"] is True
    assert payload["global_auto_live_enabled"] is True
    assert payload["simulated_open_record"]["intended_side"] == "BUY"
    assert payload["simulated_open_record"]["notional_lte_80_usdt"] is True
    assert payload["simulated_open_record"]["leverage"] == 10
    assert payload["simulated_open_record"]["margin_budget_usdt"] == 8.0
    assert payload["simulated_open_record"]["max_loss_usdt"] is not None
    assert payload["simulated_protective_orders"]["status"] == "PROTECTIVE_ORDERS_SIMULATED"
    assert payload["simulated_protective_orders"]["protective_stop_required"] is True
    assert payload["simulated_protective_orders"]["take_profit_required"] is True
    assert payload["simulated_close_plan"]["status"] == "PROTECTIVE_ORDERS_SIMULATED"
    assert (tmp_path / "tiny_live_autonomous_trigger_loop.ndjson").exists()
    _assert_no_submit_or_mutation(payload)


def test_no_executable_payload_created_in_dry_run_lifecycle(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[_contract(LANE_44M_LONG)])
    arming_path = _write_armed_state(tmp_path, LANE_44M_LONG)
    payload = build_tiny_live_autonomous_trigger_loop(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        autonomous_arming_config_path=arming_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_44M_LONG),
        now=NOW,
    )

    rendered = json.dumps(payload).lower()
    assert '"executable_payload_created": true' not in rendered
    assert '"submit_allowed": true' not in rendered
    assert '"final_command_available": true' not in rendered
    assert '"signed_url_shown": true' not in rendered
    assert "signature=" not in rendered
    _assert_no_submit_or_mutation(payload)


def test_api_default_safe_no_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    with patch.object(urllib.request, "urlopen") as urlopen:
        response = TestClient(app).get("/tiny-live/autonomous-trigger-loop")

    urlopen.assert_not_called()
    payload = response.json()
    assert response.status_code == 200
    assert payload["event_type"] == "TINY_LIVE_AUTONOMOUS_TRIGGER_LOOP"
    assert payload["status"] == AUTONOMOUS_TRIGGER_NOT_CHECKED
    assert payload["autonomous_trigger_loop_panel"]["per_signal_operator_approval_required"] is False
    _assert_no_submit_or_mutation(payload)


def test_final_console_includes_autonomous_trigger_loop_panel(tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["autonomous_trigger_loop_panel"]

    assert panel["operator_role"] == "arms_disarms_tunes_risk_not_per_signal_approval"
    assert panel["machine_role"] == "auto_triggers_when_armed_and_all_gates_open"
    assert panel["per_signal_operator_approval_required"] is False
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_cli_supports_autonomous_trigger_loop_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-autonomous-trigger-loop",
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--load-discovered-binance-readonly-env" in result.stdout
    assert "--fetch-binance-readonly-precision-mark-price" in result.stdout
    assert "--fetch-binance-readonly-account-position" in result.stdout
    assert "--record-autonomous-trigger-loop" in result.stdout
    assert "approval" not in result.stdout.lower()


def _write_armed_state(tmp_path: Path, lane_key: str) -> Path:
    path = tmp_path / "autonomous_arming_state.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "created_by_phase": "R287_TEST",
                "global_auto_live_enabled": True,
                "auto_execute_mode": "dry_run_only",
                "armed_lane_key": lane_key,
                "allowed_lane_keys": [lane_key],
                "max_position_notional_usdt": 80.0,
                "leverage": 10.0,
                "max_trades_per_day": 1,
                "daily_loss_stop_usdt": 5.0,
                "require_protective_orders": True,
                "require_strategy_live_qualified": True,
                "lanes": [
                    {
                        "lane_key": lane_key,
                        "lane_auto_live_enabled": True,
                        "dry_run_only": True,
                        "live_execution_enabled": False,
                        "submit_allowed": False,
                        "real_order_forbidden": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _assert_no_submit_or_mutation(payload: dict) -> None:
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True
    assert payload["per_signal_operator_approval_required"] is False
    safety = payload["safety"]
    for key in (
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "submit_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "leverage_change_called",
        "margin_change_called",
        "mutation_performed",
        "signed_trading_request_created",
        "signed_order_request_created",
        "signed_request_created",
        "signed_url_shown",
        "signature_shown",
        "secrets_shown",
        "secret_values_in_output",
        "env_written",
        "env_mutated",
        "lane_controls_written",
        "risk_contract_config_written",
        "live_config_written",
        "order_payload_created",
        "executable_payload_created",
    ):
        assert safety[key] is False
