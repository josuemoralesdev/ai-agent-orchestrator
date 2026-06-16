from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.tiny_live_real_candidate_dry_run_trigger_bridge import (
    REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED,
    REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED,
    REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT,
    SIMULATED_DRY_RUN_MODE,
    build_tiny_live_real_candidate_dry_run_trigger_bridge,
)

NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_44M_SHORT = "BTCUSDT|44m|short|ladder_close_50_618"
LANE_NEAR_MISS = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_PAPER_ONLY = "BTCUSDT|8m|short|ladder_close_50_618"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_real_candidate_ready_to_wait(tmp_path: Path) -> None:
    payload = _build(tmp_path, fresh_trigger_watch_packet=_fresh_watch_no_candidate())

    assert payload["status"] == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT
    assert payload["current_real_candidate_exists"] is False
    assert payload["simulated_dry_run_trigger_recorded"] is False
    assert payload["no_matching_candidate_action"] == "WAIT"
    assert payload["blockers"] == []
    _assert_real_candidate_only(payload)
    _assert_no_submit_or_order(payload)


def test_matching_real_candidate_certifies(tmp_path: Path) -> None:
    payload = _build(tmp_path, fresh_trigger_watch_packet=_fresh_watch_candidate())

    assert payload["status"] == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED
    assert payload["requested_lane_key"] == LANE_44M_LONG
    assert payload["current_real_candidate_exists"] is True
    assert payload["current_real_candidate_lane_key"] == LANE_44M_LONG
    assert payload["candidate_matches_requested_lane"] is True
    assert payload["lane_is_live_qualified"] is True
    assert payload["exact_lane_only"] is True
    assert payload["no_cross_lane_borrowing"] is True
    assert payload["simulated_dry_run_trigger_recorded"] is True
    assert payload["simulated_lifecycle_status"] == "SIMULATED_DRY_RUN_LIFECYCLE_RECORDED"
    assert payload["simulated_open_record"]["mode"] == SIMULATED_DRY_RUN_MODE
    assert payload["simulated_protective_orders"]["mode"] == SIMULATED_DRY_RUN_MODE
    assert payload["simulated_close_plan"]["mode"] == SIMULATED_DRY_RUN_MODE
    _assert_real_candidate_only(payload)
    _assert_no_submit_or_order(payload)


def test_nonmatching_real_candidate_blocks_with_lane_mismatch(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        fresh_trigger_watch_packet=_fresh_watch_candidate(lane_key=LANE_44M_SHORT, direction="short"),
    )

    assert payload["status"] == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED
    assert payload["candidate_matches_requested_lane"] is False
    assert "real_candidate_lane_mismatch" in payload["blockers"]
    assert payload["simulated_dry_run_trigger_recorded"] is False
    _assert_no_submit_or_order(payload)


def test_expired_candidate_blocks(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        fresh_trigger_watch_packet=_fresh_watch_candidate(freshness_status="expired"),
    )

    assert payload["status"] == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED
    assert "candidate_not_fresh" in payload["blockers"]
    assert payload["simulated_dry_run_trigger_recorded"] is False
    _assert_no_submit_or_order(payload)


def test_near_miss_and_paper_only_candidates_block(tmp_path: Path) -> None:
    cases = [
        ("NEAR_MISS_INCUBATOR", "candidate_not_live_qualified"),
        ("PAPER_ONLY", "candidate_not_live_qualified"),
    ]
    for live_class, blocker in cases:
        payload = _build(
            tmp_path,
            fresh_trigger_watch_packet=_fresh_watch_candidate(
                live_class=live_class,
                current_candidate_is_live_qualified=False,
                status="FRESH_TRIGGER_BLOCKED",
            ),
        )

        assert payload["status"] == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED
        assert blocker in payload["blockers"]
        assert payload["simulated_dry_run_trigger_recorded"] is False
        _assert_no_submit_or_order(payload)


def test_missing_required_fields_blocks(tmp_path: Path) -> None:
    packet = _fresh_watch_candidate()
    packet["current_candidate_signal_id"] = None

    payload = _build(tmp_path, fresh_trigger_watch_packet=packet)

    assert payload["status"] == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED
    assert "candidate_missing_required_fields" in payload["blockers"]
    assert payload["simulated_dry_run_trigger_recorded"] is False
    _assert_no_submit_or_order(payload)


def test_invalid_lanes_block(tmp_path: Path) -> None:
    cases = [
        ("", "lane_key_required"),
        ("ETHUSDT|44m|long|ladder_close_50_618", "only_BTCUSDT_lanes_supported_for_r294"),
        (LANE_NEAR_MISS, "requested_lane_not_live_qualified"),
        (LANE_PAPER_ONLY, "requested_lane_not_live_qualified"),
        ("BTCUSDT|99m|long|ladder_close_50_618", "requested_lane_not_live_qualified"),
    ]
    for lane_key, blocker in cases:
        payload = _build(
            tmp_path,
            lane_key=lane_key,
            fresh_trigger_watch_packet=_fresh_watch_candidate(),
        )

        assert payload["status"] == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED
        assert blocker in payload["blockers"]
        assert payload["simulated_dry_run_trigger_recorded"] is False
        _assert_no_submit_or_order(payload)


def test_record_appends_only_r298_ledger(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        fresh_trigger_watch_packet=_fresh_watch_candidate(),
        record_real_candidate_dry_run_trigger_bridge=True,
    )

    assert payload["real_candidate_dry_run_trigger_bridge_recorded"] is True
    assert (tmp_path / "tiny_live_real_candidate_dry_run_trigger_bridge.ndjson").exists()
    assert not (tmp_path / "tiny_live_dry_run_lane_arming_rehearsal.ndjson").exists()
    assert not (tmp_path / "tiny_live_autonomous_trigger_loop.ndjson").exists()
    _assert_no_submit_or_order(payload)


def test_api_plain_status_never_records(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    response = TestClient(app).get("/tiny-live/real-candidate-dry-run-trigger-bridge/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type"] == "TINY_LIVE_REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE"
    assert payload["record_real_candidate_dry_run_trigger_bridge_requested"] is False
    assert payload["real_candidate_dry_run_trigger_bridge_recorded"] is False
    assert not (tmp_path / "tiny_live_real_candidate_dry_run_trigger_bridge.ndjson").exists()
    _assert_real_candidate_only(payload)
    _assert_no_submit_or_order(payload)


def test_final_console_includes_real_candidate_bridge_panel(monkeypatch, tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    monkeypatch.setattr(
        final_console,
        "build_status_tiny_live_real_candidate_dry_run_trigger_bridge",
        lambda **kwargs: _build(
            tmp_path,
            fresh_trigger_watch_packet=_fresh_watch_no_candidate(),
        ),
    )

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["real_candidate_dry_run_trigger_bridge_panel"]

    assert panel["status"] == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT
    assert panel["real_candidate_summary"]["exists"] is False
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_cli_help_has_no_simulate_args_for_r298() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-real-candidate-dry-run-trigger-bridge",
            "--help",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--record-real-candidate-dry-run-trigger-bridge" in result.stdout
    assert "simulate" not in result.stdout.lower()
    assert "tests-only" not in result.stdout.lower()


def _build(
    tmp_path: Path,
    *,
    lane_key: str | None = LANE_44M_LONG,
    fresh_trigger_watch_packet: dict,
    record_real_candidate_dry_run_trigger_bridge: bool = False,
) -> dict:
    return build_tiny_live_real_candidate_dry_run_trigger_bridge(
        log_dir=tmp_path,
        lane_key=lane_key,
        operator_id="local_operator",
        reason="R298 test fixture real watcher output; no fake candidate; no submit; no order.",
        fresh_trigger_watch_packet=fresh_trigger_watch_packet,
        timer_health_packet=_timer_health(),
        record_real_candidate_dry_run_trigger_bridge=record_real_candidate_dry_run_trigger_bridge,
        now=NOW,
    )


def _timer_health() -> dict:
    return {
        "status": "TIMER_HEALTH_ACTIVE",
        "timer_active": True,
        "recent_tick_seen": True,
        "recent_tick_count": 2,
        "safety": {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "secrets_shown": False,
        },
    }


def _fresh_watch_no_candidate() -> dict:
    return {
        "event_type": "TINY_LIVE_FRESH_LIVE_QUALIFIED_TRIGGER_WATCH",
        "status": "FRESH_TRIGGER_WAIT",
        "current_fresh_candidate_exists": False,
        "current_candidate_lane_key": None,
        "current_candidate_signal_id": None,
        "current_candidate_is_live_qualified": False,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "safety": {"order_placed": False, "real_order_placed": False, "secrets_shown": False},
    }


def _fresh_watch_candidate(
    *,
    lane_key: str = LANE_44M_LONG,
    direction: str = "long",
    live_class: str = "LIVE_QUALIFIED",
    status: str = "FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW",
    current_candidate_is_live_qualified: bool = True,
    freshness_status: str = "fresh",
) -> dict:
    parts = lane_key.split("|")
    return {
        "event_type": "TINY_LIVE_FRESH_LIVE_QUALIFIED_TRIGGER_WATCH",
        "status": status,
        "current_fresh_candidate_exists": True,
        "current_candidate_lane_key": lane_key,
        "current_candidate_signal_id": "r298_real_signal_001",
        "current_candidate_timeframe": parts[1] if len(parts) == 4 else None,
        "current_candidate_direction": direction,
        "current_candidate_entry_mode": parts[3] if len(parts) == 4 else None,
        "current_candidate_age_minutes": 1.0,
        "current_candidate_freshness_status": freshness_status,
        "current_candidate_watch_category": live_class,
        "current_candidate_is_live_qualified": current_candidate_is_live_qualified,
        "current_candidate_entry": 70000.0,
        "current_candidate_stop": 69300.0 if direction == "long" else 70700.0,
        "current_candidate_take_profit": 71400.0 if direction == "long" else 68600.0,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "safety": {"order_placed": False, "real_order_placed": False, "secrets_shown": False},
    }


def _assert_real_candidate_only(payload: dict) -> None:
    assert payload["real_candidate_source"] == "fresh_trigger_watch"
    assert payload["test_only"] is False
    assert payload["fake_candidate_used"] is False
    assert payload["dry_run_only"] is True


def _assert_no_submit_or_order(payload: dict) -> None:
    for key in (
        "final_command_available",
        "submit_allowed",
        "executable_payload_created",
        "order_payload_created",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "per_signal_operator_approval_required",
        "live_execution_enabled",
        "allow_live_orders",
    ):
        assert payload[key] is False
    assert payload["real_order_forbidden"] is True
    assert payload["global_kill_switch"] is True
    assert payload["safety"]["secrets_shown"] is False
