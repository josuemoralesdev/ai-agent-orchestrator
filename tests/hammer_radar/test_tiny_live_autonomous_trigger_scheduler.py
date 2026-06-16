from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler import (
    AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED,
    AUTONOMOUS_TRIGGER_SCHEDULER_LOOP_COMPLETED,
    AUTONOMOUS_TRIGGER_SCHEDULER_NOT_CHECKED,
    build_tiny_live_autonomous_trigger_scheduler_once,
    run_tiny_live_autonomous_trigger_scheduler_loop,
)
from tests.hammer_radar.test_tiny_live_autonomous_trigger_loop import _write_armed_state
from tests.hammer_radar.test_tiny_live_one_shot_pre_activation_gate import (
    LANE_44M_LONG,
    NOW,
    _binance_ready,
    _contract,
    _post_manual_verified,
    _watch_wait,
    _watch_with_candidate,
    _write_risk_contracts,
)


def test_scheduler_once_records_iteration(tmp_path: Path) -> None:
    payload = build_tiny_live_autonomous_trigger_scheduler_once(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_wait(),
        record_autonomous_trigger_scheduler=True,
        operator_id="local_operator",
        reason="test scheduler once",
        now=NOW,
    )

    assert payload["event_type"] == "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER"
    assert payload["status"] == AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED
    assert payload["trigger_loop_status"] == "AUTONOMOUS_TRIGGER_WAIT"
    assert payload["current_fresh_candidate_exists"] is False
    assert payload["per_signal_operator_approval_required"] is False
    assert payload["telegram_payload_prepared"] is True
    assert (tmp_path / "tiny_live_autonomous_trigger_scheduler.ndjson").exists()
    _assert_no_submit_or_mutation(payload)


def test_scheduler_loop_completes_bounded_iterations(tmp_path: Path) -> None:
    payload = run_tiny_live_autonomous_trigger_scheduler_loop(
        log_dir=tmp_path,
        max_iterations=2,
        sleep_seconds=0,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_wait(),
        record_autonomous_trigger_scheduler=True,
        operator_id="local_operator",
        reason="test bounded loop",
    )

    assert payload["status"] == AUTONOMOUS_TRIGGER_SCHEDULER_LOOP_COMPLETED
    assert payload["iterations_requested"] == 2
    assert payload["iterations_completed"] == 2
    assert payload["latest_trigger_loop_status"] == "AUTONOMOUS_TRIGGER_WAIT"
    assert payload["latest_candidate_lane_key"] is None
    assert payload["any_dry_run_execution_recorded"] is False
    assert payload["any_unsafe_flag_detected"] is False
    assert payload["stopped_reason"] == "bounded_loop_completed"
    _assert_no_submit_or_mutation(payload)


def test_scheduler_loop_max_iteration_cap_enforced(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_iterations must be <= 20"):
        run_tiny_live_autonomous_trigger_scheduler_loop(
            log_dir=tmp_path,
            max_iterations=21,
            sleep_seconds=0,
        )


def test_scheduler_rejects_unbounded_sleep(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sleep_seconds must be <= 300"):
        run_tiny_live_autonomous_trigger_scheduler_loop(
            log_dir=tmp_path,
            max_iterations=1,
            sleep_seconds=301,
        )


def test_scheduler_no_executable_payload_or_mutations(tmp_path: Path) -> None:
    payload = build_tiny_live_autonomous_trigger_scheduler_once(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_wait(),
        now=NOW,
    )

    rendered = json.dumps(payload).lower()
    forbidden = (
        '"/fapi/v1/order"',
        '"binance_order_endpoint_called": true',
        '"binance_test_order_endpoint_called": true',
        '"leverage_change_called": true',
        '"margin_change_called": true',
        '"mutation_performed": true',
        '"live_config_written": true',
        '"lane_controls_written": true',
        '"risk_contract_config_written": true',
        '"env_mutated": true',
        '"env_written": true',
        '"executable_payload_created": true',
        '"final_command_available": true',
        '"submit_allowed": true',
        '"per_signal_operator_approval_required": true',
        "signature=",
    )
    for text in forbidden:
        assert text not in rendered
    _assert_no_submit_or_mutation(payload)


def test_scheduler_api_status_default_safe_no_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    with patch.object(urllib.request, "urlopen") as urlopen:
        response = TestClient(app).get("/tiny-live/autonomous-trigger-scheduler/status")

    urlopen.assert_not_called()
    payload = response.json()
    assert response.status_code == 200
    assert payload["event_type"] == "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER"
    assert payload["status"] == AUTONOMOUS_TRIGGER_SCHEDULER_NOT_CHECKED
    assert payload["autonomous_trigger_scheduler_panel"]["scheduler_supported"] is True
    _assert_no_submit_or_mutation(payload)


def test_final_console_includes_scheduler_panel(tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["autonomous_trigger_scheduler_panel"]

    assert panel["scheduler_supported"] is True
    assert panel["operator_role"] == "arms_disarms_tunes_risk_not_per_signal_approval"
    assert panel["machine_role"] == "auto_triggers_when_armed_and_all_gates_open"
    assert panel["per_signal_operator_approval_required"] is False
    assert "tiny-live-autonomous-trigger-scheduler-once" in panel["next_scheduler_command"]
    assert "tiny-live-autonomous-trigger-scheduler-loop" in panel["proposed_safe_loop_command"]
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_scheduler_dry_run_executed_path_can_be_simulated(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[_contract(LANE_44M_LONG)])
    arming_path = _write_armed_state(tmp_path, LANE_44M_LONG)
    payload = build_tiny_live_autonomous_trigger_scheduler_once(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        autonomous_arming_config_path=arming_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_44M_LONG),
        record_autonomous_trigger_scheduler=True,
        operator_id="local_operator",
        reason="fixture dry-run execution",
        now=NOW,
    )

    assert payload["status"] == AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED
    assert payload["trigger_loop_status"] == "AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED"
    assert payload["autonomous_dry_run_execution_recorded"] is True
    assert payload["exact_lane_auto_armed"] is True
    assert (tmp_path / "tiny_live_autonomous_trigger_loop.ndjson").exists()
    assert (tmp_path / "tiny_live_autonomous_trigger_scheduler.ndjson").exists()
    _assert_no_submit_or_mutation(payload)


def test_scheduler_cli_help_exposes_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-autonomous-trigger-scheduler-loop",
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--max-iterations" in result.stdout
    assert "--sleep-seconds" in result.stdout
    assert "--load-discovered-binance-readonly-env" in result.stdout
    assert "--fetch-binance-readonly-precision-mark-price" in result.stdout
    assert "--fetch-binance-readonly-account-position" in result.stdout
    assert "--record-autonomous-trigger-scheduler" in result.stdout
    assert "approval" not in result.stdout.lower()


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
        "executable_payload_created",
        "final_command_available",
        "submit_allowed",
        "per_signal_operator_approval_required",
    ):
        assert safety[key] is False
