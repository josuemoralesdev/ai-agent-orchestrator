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
)
from src.app.hammer_radar.operator.tiny_live_real_candidate_timer_observation_certificate import (
    REAL_CANDIDATE_TIMER_OBSERVATION_BLOCKED,
    REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED,
    REAL_CANDIDATE_TIMER_OBSERVATION_TRIGGER_CERTIFIED,
    build_tiny_live_real_candidate_timer_observation_certificate,
)

NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_PAPER_ONLY = "BTCUSDT|8m|short|ladder_close_50_618"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_r298_ready_to_wait_with_timer_and_scheduler_certifies_wait(tmp_path: Path) -> None:
    payload = _build(tmp_path, r298_bridge_packet=_r298_ready_to_wait())

    assert payload["status"] == REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED
    assert payload["current_real_candidate_exists"] is False
    assert payload["simulated_dry_run_trigger_recorded"] is False
    assert payload["no_matching_candidate_action"] == "WAIT"
    assert payload["blockers"] == []
    assert payload["timer_active"] is True
    assert payload["recent_tick_seen"] is True
    assert len(payload["scheduler_recent_ticks_observed"]) == 2
    _assert_real_candidate_only(payload)
    _assert_no_submit_or_order(payload)


def test_r298_certified_fixture_certifies_trigger(tmp_path: Path) -> None:
    payload = _build(tmp_path, r298_bridge_packet=_r298_certified())

    assert payload["status"] == REAL_CANDIDATE_TIMER_OBSERVATION_TRIGGER_CERTIFIED
    assert payload["current_real_candidate_exists"] is True
    assert payload["candidate_matches_requested_lane"] is True
    assert payload["simulated_dry_run_trigger_recorded"] is True
    assert payload["simulated_lifecycle_status"] == "SIMULATED_DRY_RUN_LIFECYCLE_RECORDED"
    assert payload["simulated_open_record"]["mode"] == "REAL_CANDIDATE_SIMULATED_DRY_RUN_ONLY"
    _assert_real_candidate_only(payload)
    _assert_no_submit_or_order(payload)


def test_r298_blocked_preserves_blockers(tmp_path: Path) -> None:
    payload = _build(tmp_path, r298_bridge_packet=_r298_blocked(["candidate_not_fresh"]))

    assert payload["status"] == REAL_CANDIDATE_TIMER_OBSERVATION_BLOCKED
    assert "candidate_not_fresh" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_timer_missing_blocks(tmp_path: Path) -> None:
    timer = _timer_health(active=False, recent=False, count=0)
    payload = _build(tmp_path, r298_bridge_packet=_r298_ready_to_wait(), timer_health_packet=timer)

    assert payload["status"] == REAL_CANDIDATE_TIMER_OBSERVATION_BLOCKED
    assert "timer_not_active" in payload["blockers"]
    assert "timer_recent_tick_missing" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_scheduler_recent_tick_missing_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, r298_bridge_packet=_r298_ready_to_wait(), scheduler_records=[])

    assert payload["status"] == REAL_CANDIDATE_TIMER_OBSERVATION_BLOCKED
    assert "scheduler_recent_tick_missing" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_invalid_lane_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, lane_key=LANE_PAPER_ONLY, r298_bridge_packet=_r298_ready_to_wait())

    assert payload["status"] == REAL_CANDIDATE_TIMER_OBSERVATION_BLOCKED
    assert "requested_lane_not_live_qualified" in payload["blockers"]
    assert payload["lane_is_live_qualified"] is False
    _assert_no_submit_or_order(payload)


def test_exact_lane_and_real_candidate_only_flags(tmp_path: Path) -> None:
    payload = _build(tmp_path, r298_bridge_packet=_r298_ready_to_wait())

    assert payload["exact_lane_only"] is True
    assert payload["no_cross_lane_borrowing"] is True
    assert payload["test_only"] is False
    assert payload["fake_candidate_used"] is False
    assert payload["real_candidate_source"] == "fresh_trigger_watch_via_r298_bridge"


def test_record_appends_only_r299_ledger(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        r298_bridge_packet=_r298_ready_to_wait(),
        record_real_candidate_timer_observation_certificate=True,
    )

    assert payload["real_candidate_timer_observation_certificate_recorded"] is True
    assert (tmp_path / "tiny_live_real_candidate_timer_observation_certificate.ndjson").exists()
    assert not (tmp_path / "tiny_live_real_candidate_dry_run_trigger_bridge.ndjson").exists()
    _assert_no_submit_or_order(payload)


def test_api_plain_status_never_records(monkeypatch, tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import approval_api

    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    monkeypatch.setattr(
        approval_api,
        "build_status_tiny_live_real_candidate_timer_observation_certificate",
        lambda **kwargs: _build(tmp_path, r298_bridge_packet=_r298_ready_to_wait()),
    )
    response = TestClient(app).get(
        "/tiny-live/real-candidate-timer-observation-certificate/status"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type"] == "TINY_LIVE_REAL_CANDIDATE_TIMER_OBSERVATION_CERTIFICATE"
    assert payload["record_real_candidate_timer_observation_certificate_requested"] is False
    assert payload["real_candidate_timer_observation_certificate_recorded"] is False
    assert not (tmp_path / "tiny_live_real_candidate_timer_observation_certificate.ndjson").exists()
    _assert_no_submit_or_order(payload)


def test_final_console_includes_real_candidate_timer_observation_panel(
    monkeypatch, tmp_path: Path
) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    monkeypatch.setattr(
        final_console,
        "build_real_candidate_timer_observation_certificate_panel",
        lambda **kwargs: _build(
            tmp_path,
            r298_bridge_packet=_r298_ready_to_wait(),
        )["real_candidate_timer_observation_certificate_panel"],
    )

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["real_candidate_timer_observation_certificate_panel"]

    assert panel["status"] == REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED
    assert panel["real_candidate_summary"]["exists"] is False
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_cli_help_has_no_simulate_args_for_r299() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-real-candidate-timer-observation-certificate",
            "--help",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--record-real-candidate-timer-observation-certificate" in result.stdout
    assert "simulate" not in result.stdout.lower()
    assert "tests-only" not in result.stdout.lower()


def _build(
    tmp_path: Path,
    *,
    lane_key: str | None = LANE_44M_LONG,
    r298_bridge_packet: dict,
    timer_health_packet: dict | None = None,
    scheduler_records: list[dict] | None = None,
    record_real_candidate_timer_observation_certificate: bool = False,
) -> dict:
    return build_tiny_live_real_candidate_timer_observation_certificate(
        log_dir=tmp_path,
        lane_key=lane_key,
        operator_id="local_operator",
        reason="R299 test fixture real bridge observation; no fake candidate; no submit; no order.",
        timer_health_packet=timer_health_packet or _timer_health(),
        scheduler_records=_scheduler_records() if scheduler_records is None else scheduler_records,
        r298_bridge_packet=r298_bridge_packet,
        record_real_candidate_timer_observation_certificate=(
            record_real_candidate_timer_observation_certificate
        ),
        now=NOW,
    )


def _timer_health(*, active: bool = True, recent: bool = True, count: int = 2) -> dict:
    return {
        "status": "TIMER_HEALTH_ACTIVE" if active else "TIMER_HEALTH_INACTIVE",
        "timer_active": active,
        "timer_loaded": active,
        "recent_tick_seen": recent,
        "recent_tick_count": count,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "safety": {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "secrets_shown": False,
        },
    }


def _scheduler_records() -> list[dict]:
    return [
        {
            "event_type": "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER",
            "status": "AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED",
            "trigger_loop_status": "AUTONOMOUS_TRIGGER_WAIT",
            "current_candidate_lane_key": None,
            "generated_at": "2026-06-16T11:58:00+00:00",
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        },
        {
            "event_type": "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER",
            "status": "AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED",
            "trigger_loop_status": "AUTONOMOUS_TRIGGER_WAIT",
            "current_candidate_lane_key": None,
            "generated_at": "2026-06-16T12:00:00+00:00",
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        },
    ]


def _r298_ready_to_wait() -> dict:
    return {
        "event_type": "TINY_LIVE_REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE",
        "status": REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT,
        "requested_lane_key": LANE_44M_LONG,
        "current_real_candidate_exists": False,
        "current_real_candidate_lane_key": None,
        "current_real_candidate_signal_id": None,
        "current_real_candidate_freshness_status": None,
        "current_real_candidate_live_qualification_class": None,
        "candidate_matches_requested_lane": False,
        "test_only": False,
        "fake_candidate_used": False,
        "simulated_dry_run_trigger_recorded": False,
        "simulated_lifecycle_status": "SIMULATED_DRY_RUN_LIFECYCLE_NOT_RECORDED",
        "simulated_open_record": None,
        "simulated_protective_orders": None,
        "simulated_close_plan": None,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "blockers": [],
    }


def _r298_certified() -> dict:
    return {
        **_r298_ready_to_wait(),
        "status": REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED,
        "current_real_candidate_exists": True,
        "current_real_candidate_lane_key": LANE_44M_LONG,
        "current_real_candidate_signal_id": "r299_real_signal_001",
        "current_real_candidate_freshness_status": "fresh",
        "current_real_candidate_live_qualification_class": "LIVE_QUALIFIED",
        "candidate_matches_requested_lane": True,
        "simulated_dry_run_trigger_recorded": True,
        "simulated_lifecycle_status": "SIMULATED_DRY_RUN_LIFECYCLE_RECORDED",
        "simulated_open_record": {
            "mode": "REAL_CANDIDATE_SIMULATED_DRY_RUN_ONLY",
            "order_placed": False,
        },
        "simulated_protective_orders": {
            "mode": "REAL_CANDIDATE_SIMULATED_DRY_RUN_ONLY",
            "order_placed": False,
        },
        "simulated_close_plan": {
            "mode": "REAL_CANDIDATE_SIMULATED_DRY_RUN_ONLY",
            "order_placed": False,
        },
    }


def _r298_blocked(blockers: list[str]) -> dict:
    return {
        **_r298_ready_to_wait(),
        "status": REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED,
        "blockers": blockers,
    }


def _assert_real_candidate_only(payload: dict) -> None:
    assert payload["real_candidate_source"] == "fresh_trigger_watch_via_r298_bridge"
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
