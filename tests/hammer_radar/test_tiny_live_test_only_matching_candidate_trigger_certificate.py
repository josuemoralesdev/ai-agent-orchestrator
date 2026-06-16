from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.tiny_live_test_only_matching_candidate_trigger_certificate import (
    TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED,
    TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFIED,
    TEST_ONLY_NON_MATCHING_CANDIDATE_NO_TRIGGER,
    build_tiny_live_test_only_matching_candidate_trigger_certificate,
)

NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_44M_SHORT = "BTCUSDT|44m|short|ladder_close_50_618"
LANE_55M_LONG = "BTCUSDT|55m|long|ladder_close_50_618"
LANE_NEAR_MISS = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_PAPER_ONLY = "BTCUSDT|8m|short|ladder_close_50_618"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_matching_test_only_candidate_certifies_simulated_trigger(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        lane_key=LANE_44M_LONG,
        simulate_matching_fresh_candidate_for_tests_only=True,
    )

    assert payload["status"] == TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFIED
    assert payload["requested_lane_key"] == LANE_44M_LONG
    assert payload["simulated_candidate_lane_key"] == LANE_44M_LONG
    assert payload["lane_is_live_qualified"] is True
    assert payload["candidate_matches_requested_lane"] is True
    assert payload["exact_lane_only"] is True
    assert payload["no_cross_lane_borrowing"] is True
    assert payload["dry_run_only"] is True
    assert payload["test_only"] is True
    assert payload["simulated_candidate_source"] == "R296_TEST_ONLY"
    assert payload["simulated_candidate_not_real_market_data"] is True
    assert payload["simulated_fresh_candidate_injected"] is True
    assert payload["simulated_trigger_recorded"] is True
    assert payload["simulated_lifecycle_status"] == "SIMULATED_DRY_RUN_LIFECYCLE_RECORDED"
    assert payload["simulated_open_record"]["mode"] == "SIMULATED_DRY_RUN_ONLY"
    assert payload["simulated_open_record"]["lane_key"] == LANE_44M_LONG
    assert payload["simulated_protective_orders"]["mode"] == "SIMULATED_DRY_RUN_ONLY"
    assert payload["simulated_protective_orders"]["reduce_only"] is True
    assert payload["simulated_close_plan"]["mode"] == "SIMULATED_DRY_RUN_ONLY"
    assert payload["simulated_close_plan"]["no_live_close_order"] is True
    _assert_no_submit_or_order(payload)


def test_nonmatching_test_only_candidate_does_not_trigger(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        lane_key=LANE_44M_LONG,
        simulate_nonmatching_fresh_candidate_for_tests_only=True,
    )

    assert payload["status"] == TEST_ONLY_NON_MATCHING_CANDIDATE_NO_TRIGGER
    assert payload["simulated_candidate_lane_key"] != LANE_44M_LONG
    assert payload["candidate_matches_requested_lane"] is False
    assert payload["simulated_trigger_recorded"] is False
    assert payload["simulated_open_record"] is None
    _assert_no_submit_or_order(payload)


def test_no_simulate_flag_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, lane_key=LANE_44M_LONG)

    assert payload["status"] == TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED
    assert "missing_test_only_simulation_flag" in payload["blockers"]
    assert payload["simulated_fresh_candidate_injected"] is False
    _assert_no_submit_or_order(payload)


def test_both_simulate_flags_block(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        lane_key=LANE_44M_LONG,
        simulate_matching_fresh_candidate_for_tests_only=True,
        simulate_nonmatching_fresh_candidate_for_tests_only=True,
    )

    assert payload["status"] == TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED
    assert "conflicting_test_only_simulation_flags" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_invalid_near_miss_paper_unknown_and_wrong_lane_categories_block(tmp_path: Path) -> None:
    cases = [
        ("", "lane_key_required"),
        ("ETHUSDT|44m|long|ladder_close_50_618", "only_BTCUSDT_lanes_supported_for_r294"),
        ("BTCUSDT|44m|short|wrong_entry_mode", "lane_not_live_qualified_by_strategy_evidence"),
        ("BTCUSDT|99m|long|ladder_close_50_618", "lane_not_live_qualified_by_strategy_evidence"),
        (LANE_NEAR_MISS, "near_miss_lane_rejected"),
        (LANE_PAPER_ONLY, "paper_only_lane_rejected"),
    ]
    for lane_key, blocker in cases:
        payload = _build(
            tmp_path,
            lane_key=lane_key,
            simulate_matching_fresh_candidate_for_tests_only=True,
        )

        assert payload["status"] == TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED
        assert blocker in payload["blockers"]
        assert payload["simulated_trigger_recorded"] is False
        _assert_no_submit_or_order(payload)


def test_record_appends_only_r296_ledger(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        lane_key=LANE_44M_SHORT,
        simulate_matching_fresh_candidate_for_tests_only=True,
        record_test_only_matching_candidate_trigger_certificate=True,
    )

    assert payload["test_only_matching_candidate_trigger_certificate_recorded"] is True
    assert (tmp_path / "tiny_live_test_only_matching_candidate_trigger_certificate.ndjson").exists()
    assert not (tmp_path / "tiny_live_dry_run_lane_arming_rehearsal.ndjson").exists()
    assert not (tmp_path / "tiny_live_autonomous_trigger_loop.ndjson").exists()
    _assert_no_submit_or_order(payload)


def test_plain_api_endpoint_does_not_simulate_or_record_even_with_latest_record(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    _build(
        tmp_path,
        lane_key=LANE_44M_LONG,
        simulate_matching_fresh_candidate_for_tests_only=True,
        record_test_only_matching_candidate_trigger_certificate=True,
    )

    response = TestClient(app).get("/tiny-live/test-only-matching-candidate-trigger-certificate/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type"] == "TINY_LIVE_TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFICATE"
    assert payload["status"] == TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED
    assert "missing_test_only_simulation_flag" in payload["blockers"]
    assert payload["simulation_flag_required"] is True
    assert payload["test_only_matching_requested"] is False
    assert payload["test_only_nonmatching_requested"] is False
    assert payload["simulated_fresh_candidate_injected"] is False
    assert payload["simulated_trigger_recorded"] is False
    assert payload["record_test_only_matching_candidate_trigger_certificate_requested"] is False
    assert payload["test_only_matching_candidate_trigger_certificate_recorded"] is False
    assert payload.get("recorded_at_utc") is None
    panel = payload["test_only_matching_candidate_trigger_certificate_panel"]
    assert panel["simulation_flag_required"] is True
    assert panel["test_only_matching_requested"] is False
    assert panel["test_only_nonmatching_requested"] is False
    assert panel["simulated_lifecycle_summary"]["simulated_trigger_recorded"] is False
    _assert_no_submit_or_order(payload)


def test_api_endpoint_query_simulation_does_not_record(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    monkeypatch.setattr(
        "src.app.hammer_radar.operator.tiny_live_test_only_matching_candidate_trigger_certificate."
        "build_latest_or_status_tiny_live_timer_observed_armed_lane_wait_certificate",
        lambda log_dir=None: _wait_certificate(LANE_44M_LONG),
    )

    response = TestClient(app).get(
        "/tiny-live/test-only-matching-candidate-trigger-certificate/status",
        params={"lane_key": LANE_44M_LONG, "simulate_matching_for_tests_only": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFIED
    assert payload["test_only_matching_requested"] is True
    assert payload["test_only_nonmatching_requested"] is False
    assert payload["simulated_fresh_candidate_injected"] is True
    assert payload["simulated_trigger_recorded"] is True
    assert payload["record_test_only_matching_candidate_trigger_certificate_requested"] is False
    assert payload["test_only_matching_candidate_trigger_certificate_recorded"] is False
    assert payload.get("recorded_at_utc") is None
    assert not (tmp_path / "tiny_live_test_only_matching_candidate_trigger_certificate.ndjson").exists()
    _assert_no_submit_or_order(payload)


def test_final_console_includes_safe_r296_panel_without_recording(tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    _build(
        tmp_path,
        lane_key=LANE_44M_LONG,
        simulate_matching_fresh_candidate_for_tests_only=True,
        record_test_only_matching_candidate_trigger_certificate=True,
    )

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["test_only_matching_candidate_trigger_certificate_panel"]

    assert panel["status"] == TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED
    assert panel["simulation_flag_required"] is True
    assert panel["test_only_matching_requested"] is False
    assert panel["test_only_nonmatching_requested"] is False
    assert panel["simulated_lifecycle_summary"]["simulated_trigger_recorded"] is False
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_cli_help_exposes_r296_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-test-only-matching-candidate-trigger-certificate",
            "--help",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--lane-key" in result.stdout
    assert "--simulate-matching-fresh-candidate-for-tests-only" in result.stdout
    assert "--simulate-nonmatching-fresh-candidate-for-tests-only" in result.stdout
    assert "--record-test-only-matching-candidate-trigger-certificate" in result.stdout


def test_print_only_script_contains_no_executable_dangerous_command_behavior() -> None:
    script = REPO_ROOT / "scripts/hammer_print_r296_test_only_matching_candidate_trigger_certificate_plan.sh"
    result = subprocess.run(
        ["bash", str(script)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "R296 PRINT ONLY - test-only matching candidate trigger certificate plan" in result.stdout
    assert "tiny-live-test-only-matching-candidate-trigger-certificate" in result.stdout
    source = script.read_text(encoding="utf-8")
    assert re.search(r"^\s*(sudo|systemctl|curl|install|rm|cp|mv)\s", source, re.MULTILINE) is None
    assert "/fapi/v1/order" not in result.stdout


def _build(tmp_path: Path, **kwargs) -> dict:
    lane_key = kwargs.get("lane_key") if "lane_key" in kwargs else LANE_44M_LONG
    defaults = {
        "log_dir": tmp_path,
        "lane_key": lane_key,
        "operator_id": "local_operator",
        "reason": "R296 test-only certificate",
        "timer_observed_wait_certificate_packet": _wait_certificate(lane_key),
        "timer_health_packet": _timer_health(),
        "now": NOW,
    }
    defaults.update(kwargs)
    return build_tiny_live_test_only_matching_candidate_trigger_certificate(**defaults)


def _wait_certificate(lane_key: str) -> dict:
    return {
        "event_type": "TINY_LIVE_TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFICATE",
        "status": "TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED",
        "requested_lane_key": lane_key,
        "timer_health_status": "TIMER_HEALTH_ACTIVE",
        "timer_active": True,
        "recent_tick_seen": True,
        "recent_tick_count": 1,
        "current_fresh_candidate_exists": False,
        "current_real_fresh_candidate_exists": False,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _timer_health() -> dict:
    return {
        "event_type": "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER_TIMER_HEALTH",
        "status": "TIMER_HEALTH_ACTIVE",
        "timer_active": True,
        "recent_tick_seen": True,
        "documentation_warning_seen": False,
        "installed_unit_refresh_required": False,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "safety": {"order_placed": False, "real_order_placed": False, "secrets_shown": False},
    }


def _api_packet() -> dict:
    return {
        "event_type": "TINY_LIVE_TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFICATE",
        "status": TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "executable_payload_created": False,
        "order_payload_created": False,
        "order_placed": False,
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
        "safety": {"order_placed": False, "real_order_placed": False, "secrets_shown": False},
        "test_only_matching_candidate_trigger_certificate_panel": {
            "status": TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED,
            "requested_lane_key": LANE_44M_LONG,
            "simulation_flag_required": True,
            "timer_observed_wait_certificate_summary": {"status": "TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED"},
            "matching_nonmatching_test_only_path_summary": {
                "simulated_candidate_lane_key": None,
                "candidate_matches_requested_lane": False,
                "exact_lane_only": True,
                "no_cross_lane_borrowing": True,
            },
            "simulated_lifecycle_summary": {"simulated_trigger_recorded": False},
            "blockers": ["missing_test_only_simulation_flag"],
            "recommended_next_operator_move": "PROVIDE_EXPLICIT_R296_TEST_ONLY_SIMULATION_FLAG_OR_CLEAR_BLOCKERS",
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        },
    }


def _assert_no_submit_or_order(payload: dict) -> None:
    rendered = json.dumps(payload)
    assert '"final_command_available": true' not in rendered
    assert '"submit_allowed": true' not in rendered
    assert '"real_order_forbidden": false' not in rendered
    assert '"executable_payload_created": true' not in rendered
    assert '"order_payload_created": true' not in rendered
    assert '"order_placed": true' not in rendered
    assert '"real_order_placed": true' not in rendered
    assert '"execution_attempted": true' not in rendered
    assert '"binance_order_endpoint_called": true' not in rendered
    assert '"binance_test_order_endpoint_called": true' not in rendered
    assert '"per_signal_operator_approval_required": true' not in rendered
    assert '"live_execution_enabled": true' not in rendered
    assert '"allow_live_orders": true' not in rendered
    assert '"secrets_shown": true' not in rendered
