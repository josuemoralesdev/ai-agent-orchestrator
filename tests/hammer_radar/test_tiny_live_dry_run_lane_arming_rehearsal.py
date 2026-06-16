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
from src.app.hammer_radar.operator.tiny_live_dry_run_lane_arming_rehearsal import (
    DRY_RUN_LANE_ARMING_REHEARSAL_BLOCKED,
    DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT,
    DRY_RUN_LANE_ARMING_REHEARSAL_SIMULATED_TRIGGER_RECORDED,
    build_tiny_live_dry_run_lane_arming_rehearsal,
)

NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_44M_SHORT = "BTCUSDT|44m|short|ladder_close_50_618"
LANE_55M_LONG = "BTCUSDT|55m|long|ladder_close_50_618"
LANE_NEAR_MISS = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_PAPER_ONLY = "BTCUSDT|8m|short|ladder_close_50_618"


def test_allowed_live_qualified_lane_waits_without_fresh_candidate(tmp_path: Path) -> None:
    payload = build_tiny_live_dry_run_lane_arming_rehearsal(
        log_dir=tmp_path,
        lane_key=LANE_44M_LONG,
        operator_id="local_operator",
        reason="R294 dry-run rehearsal",
        timer_health_packet=_timer_health(),
        current_candidate_packet=_no_candidate(),
        now=NOW,
    )

    assert payload["status"] == DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT
    assert payload["lane_is_live_qualified"] is True
    assert payload["exact_lane_only"] is True
    assert payload["no_cross_lane_borrowing"] is True
    assert payload["current_fresh_candidate_exists"] is False
    assert payload["simulated_trigger_recorded"] is False
    _assert_no_submit_or_order(payload)


def test_rejected_lane_categories_do_not_trigger(tmp_path: Path) -> None:
    cases = [
        (LANE_NEAR_MISS, "near_miss_lane_rejected", "lane_is_near_miss"),
        (LANE_PAPER_ONLY, "paper_only_lane_rejected", "lane_is_paper_only"),
        ("BTCUSDT|99m|long|ladder_close_50_618", "lane_not_live_qualified_by_strategy_evidence", None),
        ("", "lane_key_required", None),
        ("ETHUSDT|44m|long|ladder_close_50_618", "only_BTCUSDT_lanes_supported_for_r294", None),
    ]
    for lane_key, blocker, flag in cases:
        payload = build_tiny_live_dry_run_lane_arming_rehearsal(
            log_dir=tmp_path,
            lane_key=lane_key,
            operator_id="local_operator",
            reason="R294 dry-run rehearsal",
            timer_health_packet=_timer_health(),
            current_candidate_packet=_no_candidate(),
            now=NOW,
        )

        assert payload["status"] == DRY_RUN_LANE_ARMING_REHEARSAL_BLOCKED
        assert blocker in payload["blockers"]
        if flag:
            assert payload[flag] is True
        _assert_no_submit_or_order(payload)


def test_simulated_matching_fresh_candidate_records_dry_run_lifecycle(tmp_path: Path) -> None:
    payload = build_tiny_live_dry_run_lane_arming_rehearsal(
        log_dir=tmp_path,
        lane_key=LANE_44M_SHORT,
        operator_id="local_operator",
        reason="R294 dry-run rehearsal",
        timer_health_packet=_timer_health(),
        current_candidate_packet=_no_candidate(),
        simulate_fresh_candidate_for_tests_only=True,
        now=NOW,
    )

    assert payload["status"] == DRY_RUN_LANE_ARMING_REHEARSAL_SIMULATED_TRIGGER_RECORDED
    assert payload["current_candidate_matches_armed_lane"] is True
    assert payload["simulated_trigger_recorded"] is True
    assert payload["simulated_open_record"]["dry_run_only"] is True
    assert payload["simulated_protective_orders"]["protective_stop_required"] is True
    assert payload["simulated_close_plan"]["dry_run_only"] is True
    _assert_no_submit_or_order(payload)


def test_simulated_non_matching_candidate_blocks_cross_lane_borrowing(tmp_path: Path) -> None:
    payload = build_tiny_live_dry_run_lane_arming_rehearsal(
        log_dir=tmp_path,
        lane_key=LANE_44M_LONG,
        operator_id="local_operator",
        reason="R294 dry-run rehearsal",
        timer_health_packet=_timer_health(),
        simulate_fresh_candidate_for_tests_only=True,
        simulate_candidate_lane_key=LANE_55M_LONG,
        now=NOW,
    )

    assert payload["status"] == DRY_RUN_LANE_ARMING_REHEARSAL_BLOCKED
    assert payload["current_candidate_matches_armed_lane"] is False
    assert "current_candidate_does_not_match_armed_lane" in payload["blockers"]
    assert payload["simulated_trigger_recorded"] is False
    assert payload["simulated_open_record"] is None
    _assert_no_submit_or_order(payload)


def test_timer_health_included_and_record_appends_only_r294_ledger(tmp_path: Path) -> None:
    payload = build_tiny_live_dry_run_lane_arming_rehearsal(
        log_dir=tmp_path,
        lane_key=LANE_44M_LONG,
        operator_id="local_operator",
        reason="R294 dry-run rehearsal",
        timer_health_packet=_timer_health(),
        current_candidate_packet=_no_candidate(),
        record_dry_run_lane_arming_rehearsal=True,
        now=NOW,
    )

    assert payload["dry_run_lane_arming_rehearsal_recorded"] is True
    assert payload["timer_health_status"] == "TIMER_HEALTH_ACTIVE"
    assert payload["timer_active"] is True
    assert payload["recent_tick_seen"] is True
    assert (tmp_path / "tiny_live_dry_run_lane_arming_rehearsal.ndjson").exists()
    assert not (tmp_path / "tiny_live_autonomous_trigger_loop.ndjson").exists()
    _assert_no_submit_or_order(payload)


def test_api_status_returns_panel(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    monkeypatch.setattr(
        "src.app.hammer_radar.operator.approval_api.build_latest_or_status_tiny_live_dry_run_lane_arming_rehearsal",
        lambda log_dir=None: _api_packet(),
    )

    response = TestClient(app).get("/tiny-live/dry-run-lane-arming-rehearsal/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type"] == "TINY_LIVE_DRY_RUN_LANE_ARMING_REHEARSAL"
    assert payload["dry_run_lane_arming_rehearsal_panel"]["final_command_available"] is False
    _assert_no_submit_or_order(payload)


def test_final_console_includes_dry_run_lane_arming_rehearsal_panel(monkeypatch, tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    monkeypatch.setattr(
        final_console,
        "build_dry_run_lane_arming_rehearsal_panel",
        lambda log_dir=None: _api_packet()["dry_run_lane_arming_rehearsal_panel"],
    )

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["dry_run_lane_arming_rehearsal_panel"]

    assert panel["status"] == DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_cli_help_exposes_r294_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-dry-run-lane-arming-rehearsal",
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--lane-key" in result.stdout
    assert "--record-dry-run-lane-arming-rehearsal" in result.stdout
    assert "--simulate-fresh-candidate-for-tests-only" in result.stdout


def test_print_only_script_emits_plan_without_executing_mutations() -> None:
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts/hammer_print_r294_dry_run_lane_arming_rehearsal_plan.sh"
    result = subprocess.run(
        ["bash", str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "R294 PRINT ONLY - dry-run lane arming rehearsal plan" in result.stdout
    assert "tiny-live-dry-run-lane-arming-rehearsal" in result.stdout
    source_without_plan = script.read_text(encoding="utf-8")
    assert "systemctl " not in source_without_plan
    assert "sudo " not in source_without_plan
    assert re.search(r"^\s*rm\s", source_without_plan, flags=re.MULTILINE) is None
    assert re.search(r"^\s*cp\s", source_without_plan, flags=re.MULTILINE) is None
    assert re.search(r"^\s*mv\s", source_without_plan, flags=re.MULTILINE) is None
    assert "curl -X POST" not in result.stdout
    assert "/fapi/v1/order" not in result.stdout


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


def _no_candidate() -> dict:
    return {
        "exists": False,
        "lane_key": None,
        "source_status": "FRESH_TRIGGER_WAIT",
    }


def _api_packet() -> dict:
    return {
        "event_type": "TINY_LIVE_DRY_RUN_LANE_ARMING_REHEARSAL",
        "status": DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "safety": {"order_placed": False, "real_order_placed": False, "secrets_shown": False},
        "dry_run_lane_arming_rehearsal_panel": {
            "status": DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT,
            "allowed_lane_keys": [LANE_44M_LONG, LANE_44M_SHORT, LANE_55M_LONG],
            "requested_armed_lane": LANE_44M_LONG,
            "timer_health_summary": {
                "timer_health_status": "TIMER_HEALTH_ACTIVE",
                "timer_active": True,
                "recent_tick_seen": True,
            },
            "fresh_candidate_match_summary": {
                "current_fresh_candidate_exists": False,
                "current_candidate_lane_key": None,
                "current_candidate_matches_armed_lane": False,
            },
            "simulated_trigger_summary": {"simulated_trigger_recorded": False},
            "blockers": [],
            "recommended_next_operator_move": "KEEP_DRY_RUN_LANE_ARMED_AND_WAIT_FOR_TIMER_MATCHING_FRESH_CANDIDATE",
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
    assert '"secrets_shown": true' not in rendered
