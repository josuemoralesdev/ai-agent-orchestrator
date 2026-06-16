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
from src.app.hammer_radar.operator.tiny_live_timer_observed_armed_lane_wait_certificate import (
    TIMER_OBSERVED_ARMED_LANE_WAIT_BLOCKED,
    TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED,
    build_tiny_live_timer_observed_armed_lane_wait_certificate,
)

NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_44M_SHORT = "BTCUSDT|44m|short|ladder_close_50_618"
LANE_55M_LONG = "BTCUSDT|55m|long|ladder_close_50_618"
LANE_NEAR_MISS = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_PAPER_ONLY = "BTCUSDT|8m|short|ladder_close_50_618"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_valid_live_qualified_lane_certifies_timer_observed_wait(tmp_path: Path) -> None:
    payload = _build(tmp_path, lane_key=LANE_44M_LONG)

    assert payload["status"] == TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED
    assert payload["lane_is_live_qualified"] is True
    assert payload["timer_active"] is True
    assert payload["recent_tick_seen"] is True
    assert payload["recent_tick_count"] == 1
    assert payload["scheduler_latest_status"] == "AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED"
    assert payload["scheduler_latest_trigger_loop_status"] == "AUTONOMOUS_TRIGGER_WAIT"
    assert payload["current_fresh_candidate_exists"] is False
    assert payload["no_matching_candidate_action"] == "WAIT"
    assert payload["exact_lane_only"] is True
    assert payload["no_cross_lane_borrowing"] is True
    _assert_no_submit_or_order(payload)


def test_missing_timer_tick_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, scheduler_records=[])

    assert payload["status"] == TIMER_OBSERVED_ARMED_LANE_WAIT_BLOCKED
    assert "timer_recent_tick_missing" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_invalid_near_miss_and_paper_only_lanes_block(tmp_path: Path) -> None:
    cases = [
        ("", "lane_key_required"),
        ("ETHUSDT|44m|long|ladder_close_50_618", "only_BTCUSDT_lanes_supported_for_r294"),
        ("BTCUSDT|99m|long|ladder_close_50_618", "lane_not_live_qualified_by_strategy_evidence"),
        (LANE_NEAR_MISS, "near_miss_lane_rejected"),
        (LANE_PAPER_ONLY, "paper_only_lane_rejected"),
    ]
    for lane_key, blocker in cases:
        payload = _build(tmp_path, lane_key=lane_key)

        assert payload["status"] == TIMER_OBSERVED_ARMED_LANE_WAIT_BLOCKED
        assert blocker in payload["blockers"]
        _assert_no_submit_or_order(payload)


def test_no_current_candidate_wait_is_certified(tmp_path: Path) -> None:
    payload = _build(tmp_path, current_candidate_packet=_no_candidate())

    assert payload["status"] == TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED
    assert payload["current_fresh_candidate_exists"] is False
    assert payload["current_candidate_matches_requested_lane"] is False
    assert payload["timer_observed_armed_lane_wait_certificate_panel"]["current_candidate_summary"][
        "current_fresh_candidate_exists"
    ] is False


def test_matching_simulated_candidate_records_test_only_trigger_without_order(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        lane_key=LANE_44M_SHORT,
        simulate_matching_fresh_candidate_for_tests_only=True,
    )

    assert payload["status"] == TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED
    assert payload["current_candidate_matches_requested_lane"] is True
    assert payload["simulated_trigger_recorded"] is True
    _assert_no_submit_or_order(payload)


def test_non_matching_simulated_candidate_does_not_trigger(tmp_path: Path) -> None:
    payload = build_tiny_live_timer_observed_armed_lane_wait_certificate(
        log_dir=tmp_path,
        lane_key=LANE_44M_LONG,
        operator_id="local_operator",
        reason="R295 test",
        timer_health_packet=_timer_health(),
        scheduler_records=[_scheduler_tick()],
        dry_run_lane_rehearsal_packet=_rehearsal(LANE_44M_LONG),
        simulate_matching_fresh_candidate_for_tests_only=True,
        simulate_candidate_lane_key=LANE_55M_LONG,
        now=NOW,
    )

    assert payload["status"] == TIMER_OBSERVED_ARMED_LANE_WAIT_BLOCKED
    assert payload["current_candidate_matches_requested_lane"] is False
    assert payload["simulated_trigger_recorded"] is False
    assert "current_candidate_does_not_match_requested_lane" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_record_appends_only_r295_ledger(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        record_timer_observed_armed_lane_wait_certificate=True,
    )

    assert payload["timer_observed_armed_lane_wait_certificate_recorded"] is True
    assert (tmp_path / "tiny_live_timer_observed_armed_lane_wait_certificate.ndjson").exists()
    assert not (tmp_path / "tiny_live_autonomous_trigger_loop.ndjson").exists()
    _assert_no_submit_or_order(payload)


def test_api_status_returns_panel(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    monkeypatch.setattr(
        "src.app.hammer_radar.operator.approval_api."
        "build_latest_or_status_tiny_live_timer_observed_armed_lane_wait_certificate",
        lambda log_dir=None: _api_packet(),
    )

    response = TestClient(app).get("/tiny-live/timer-observed-armed-lane-wait-certificate/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type"] == "TINY_LIVE_TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFICATE"
    assert payload["timer_observed_armed_lane_wait_certificate_panel"]
    _assert_no_submit_or_order(payload)


def test_final_console_includes_timer_observed_certificate_panel(monkeypatch, tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    monkeypatch.setattr(
        final_console,
        "build_timer_observed_armed_lane_wait_certificate_panel",
        lambda log_dir=None: _api_packet()["timer_observed_armed_lane_wait_certificate_panel"],
    )

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["timer_observed_armed_lane_wait_certificate_panel"]

    assert panel["status"] == TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_cli_help_exposes_r295_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-timer-observed-armed-lane-wait-certificate",
            "--help",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--lane-key" in result.stdout
    assert "--record-timer-observed-armed-lane-wait-certificate" in result.stdout
    assert "--simulate-matching-fresh-candidate-for-tests-only" in result.stdout


def test_print_only_script_emits_plan_without_executing_mutations() -> None:
    script = REPO_ROOT / "scripts/hammer_print_r295_timer_observed_armed_lane_wait_certificate_plan.sh"
    result = subprocess.run(
        ["bash", str(script)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "R295 PRINT ONLY - timer-observed armed-lane wait certificate plan" in result.stdout
    assert "tiny-live-timer-observed-armed-lane-wait-certificate" in result.stdout
    source = script.read_text(encoding="utf-8")
    assert re.search(r"^\s*(sudo|systemctl|curl|install|rm|cp|mv)\s", source, re.MULTILINE) is None
    assert "/fapi/v1/order" not in result.stdout


def _build(tmp_path: Path, **kwargs) -> dict:
    defaults = {
        "log_dir": tmp_path,
        "lane_key": LANE_44M_LONG,
        "operator_id": "local_operator",
        "reason": "R295 test",
        "timer_health_packet": _timer_health(),
        "scheduler_records": [_scheduler_tick()],
        "dry_run_lane_rehearsal_packet": _rehearsal(kwargs.get("lane_key") or LANE_44M_LONG),
        "current_candidate_packet": _no_candidate(),
        "now": NOW,
    }
    defaults.update(kwargs)
    return build_tiny_live_timer_observed_armed_lane_wait_certificate(**defaults)


def _timer_health() -> dict:
    return {
        "event_type": "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER_TIMER_HEALTH",
        "status": "TIMER_HEALTH_ACTIVE",
        "timer_active": True,
        "recent_tick_seen": True,
        "recent_tick_count": 1,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _scheduler_tick() -> dict:
    return {
        "event_type": "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER",
        "status": "AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED",
        "trigger_loop_status": "AUTONOMOUS_TRIGGER_WAIT",
        "current_candidate_lane_key": None,
        "generated_at": NOW.isoformat(),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "safety": {
            "order_placed": False,
            "real_order_placed": False,
            "executable_payload_created": False,
        },
    }


def _rehearsal(lane_key: str) -> dict:
    return {
        "event_type": "TINY_LIVE_DRY_RUN_LANE_ARMING_REHEARSAL",
        "status": "DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT",
        "requested_lane_key": lane_key,
        "dry_run_lane_arming_rehearsal_record_id": "r294_test",
        "dry_run_lane_arming_rehearsal_recorded": True,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _no_candidate() -> dict:
    return {
        "exists": False,
        "lane_key": None,
        "source_status": "FRESH_TRIGGER_WAIT",
    }


def _api_packet() -> dict:
    return {
        "event_type": "TINY_LIVE_TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFICATE",
        "status": TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED,
        "requested_lane_key": LANE_44M_LONG,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "safety": {"order_placed": False, "real_order_placed": False, "secrets_shown": False},
        "timer_observed_armed_lane_wait_certificate_panel": {
            "status": TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED,
            "requested_lane_key": LANE_44M_LONG,
            "timer_health": {"timer_health_status": "TIMER_HEALTH_ACTIVE"},
            "recent_scheduler_tick_summary": {"recent_tick_count": 1},
            "current_candidate_summary": {"current_fresh_candidate_exists": False},
            "exact_lane_match_status": {"exact_lane_only": True, "no_cross_lane_borrowing": True},
            "blockers": [],
            "recommended_next_operator_move": (
                "KEEP_DRY_RUN_LANE_ARMED_AND_WAIT_FOR_EXACT_LANE_TIMER_OBSERVED_CANDIDATE"
            ),
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
