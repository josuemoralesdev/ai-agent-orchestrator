from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.tiny_live_armed_dry_run_timer_observation_certificate import (
    ARMED_DRY_RUN_TIMER_OBSERVATION_BLOCKED,
    ARMED_DRY_RUN_TIMER_OBSERVATION_NOT_ARMED,
    ARMED_DRY_RUN_TIMER_OBSERVATION_TRIGGER_READY_CERTIFIED,
    ARMED_DRY_RUN_TIMER_OBSERVATION_WAIT_CERTIFIED,
    build_tiny_live_armed_dry_run_timer_observation_certificate,
)

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_NEAR_MISS = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_PAPER_ONLY = "BTCUSDT|8m|short|ladder_close_50_618"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_armed_lane_timer_active_no_candidate_certifies_wait(tmp_path: Path) -> None:
    payload = _build(tmp_path, arming_state_packet=_arming_state_on())

    assert payload["status"] == ARMED_DRY_RUN_TIMER_OBSERVATION_WAIT_CERTIFIED
    assert payload["exact_lane_auto_armed"] is True
    assert payload["armed_lane_key"] == payload["requested_lane_key"]
    assert payload["timer_active"] is True
    assert payload["recent_tick_seen"] is True
    assert payload["scheduler_latest_status"] == "AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED"
    assert payload["scheduler_latest_trigger_loop_status"] == "AUTONOMOUS_TRIGGER_WAIT"
    assert payload["current_real_candidate_exists"] is False
    assert payload["candidate_matches_requested_lane"] is False
    assert payload["no_matching_candidate_action"] == "WAIT"
    assert payload["autonomous_dry_run_execution_recorded"] is False
    assert payload["simulated_dry_run_trigger_recorded"] is False
    assert payload["blockers"] == []
    _assert_no_submit_or_order(payload)
    _assert_r302_safety_flags(payload)


def test_armed_lane_matching_real_candidate_certifies_trigger_ready(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        arming_state_packet=_arming_state_on(),
        r298_bridge_packet=_r298_certified(),
    )

    assert payload["status"] == ARMED_DRY_RUN_TIMER_OBSERVATION_TRIGGER_READY_CERTIFIED
    assert payload["current_real_candidate_exists"] is True
    assert payload["current_real_candidate_lane_key"] == LANE_44M_LONG
    assert payload["candidate_matches_requested_lane"] is True
    assert payload["simulated_dry_run_trigger_recorded"] is True
    assert payload["simulated_lifecycle_status"] == "SIMULATED_DRY_RUN_LIFECYCLE_RECORDED"
    assert payload["dry_run_only"] is True
    _assert_no_submit_or_order(payload)
    _assert_r302_safety_flags(payload)


def test_valid_lane_not_armed_returns_not_armed(tmp_path: Path) -> None:
    payload = _build(tmp_path, arming_state_packet=_arming_state_off())

    assert payload["status"] == ARMED_DRY_RUN_TIMER_OBSERVATION_NOT_ARMED
    assert payload["exact_lane_auto_armed"] is False
    assert "exact_lane_not_armed" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_invalid_lane_blocks(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        lane_key="ETHUSDT|44m|long|ladder_close_50_618",
        arming_state_packet=_arming_state_off(),
    )

    assert payload["status"] == ARMED_DRY_RUN_TIMER_OBSERVATION_BLOCKED
    assert payload["lane_is_live_qualified"] is False
    assert "requested_lane_not_live_qualified" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_near_miss_lane_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, lane_key=LANE_NEAR_MISS, arming_state_packet=_arming_state_off())

    assert payload["status"] == ARMED_DRY_RUN_TIMER_OBSERVATION_BLOCKED
    assert payload["lane_is_near_miss"] is True
    assert "requested_lane_is_near_miss" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_paper_only_lane_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, lane_key=LANE_PAPER_ONLY, arming_state_packet=_arming_state_off())

    assert payload["status"] == ARMED_DRY_RUN_TIMER_OBSERVATION_BLOCKED
    assert payload["lane_is_paper_only"] is True
    assert "requested_lane_is_paper_only" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_timer_inactive_blocks_when_armed(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        arming_state_packet=_arming_state_on(),
        timer_health_packet=_timer_health(active=False, recent=True, count=1),
    )

    assert payload["status"] == ARMED_DRY_RUN_TIMER_OBSERVATION_BLOCKED
    assert "timer_not_active" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_recent_tick_missing_blocks_when_armed(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        arming_state_packet=_arming_state_on(),
        timer_health_packet=_timer_health(active=True, recent=False, count=0),
    )

    assert payload["status"] == ARMED_DRY_RUN_TIMER_OBSERVATION_BLOCKED
    assert "timer_recent_tick_missing" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_live_execution_flag_detected_blocks(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        arming_state_packet={**_arming_state_on(), "live_execution_enabled": True},
    )

    assert payload["status"] == ARMED_DRY_RUN_TIMER_OBSERVATION_BLOCKED
    assert "live_execution_flag_detected" in payload["blockers"]
    assert payload["live_execution_enabled"] is False
    _assert_no_submit_or_order(payload)


def test_allow_live_orders_detected_blocks(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        arming_state_packet=_arming_state_on(),
        env={"HAMMER_LIVE_EXECUTION_ENABLED": "false", "HAMMER_ALLOW_LIVE_ORDERS": "true"},
    )

    assert payload["status"] == ARMED_DRY_RUN_TIMER_OBSERVATION_BLOCKED
    assert "allow_live_orders_detected" in payload["blockers"]
    assert payload["allow_live_orders"] is False
    _assert_no_submit_or_order(payload)


def test_record_appends_only_r302_ledger(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        arming_state_packet=_arming_state_on(),
        record_armed_dry_run_timer_observation_certificate=True,
    )

    assert payload["armed_dry_run_timer_observation_certificate_recorded"] is True
    assert (tmp_path / "tiny_live_armed_dry_run_timer_observation_certificate.ndjson").exists()
    assert not (
        tmp_path / "tiny_live_manual_operator_dry_run_arming_post_arm_certificate.ndjson"
    ).exists()
    assert not (tmp_path / "tiny_live_operator_exact_lane_dry_run_arming_bridge.ndjson").exists()
    assert not (tmp_path / "tiny_live_real_candidate_timer_observation_certificate.ndjson").exists()
    assert not (tmp_path / "tiny_live_real_candidate_dry_run_trigger_bridge.ndjson").exists()
    _assert_no_submit_or_order(payload)


def test_api_plain_status_never_records_and_never_mutates(monkeypatch, tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import approval_api

    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    monkeypatch.setattr(
        approval_api,
        "build_status_tiny_live_armed_dry_run_timer_observation_certificate",
        lambda **kwargs: _build(tmp_path, arming_state_packet=_arming_state_on()),
    )
    response = TestClient(app).get(
        "/tiny-live/armed-dry-run-timer-observation-certificate/status"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type"] == "TINY_LIVE_ARMED_DRY_RUN_TIMER_OBSERVATION_CERTIFICATE"
    assert payload["record_armed_dry_run_timer_observation_certificate_requested"] is False
    assert payload["armed_dry_run_timer_observation_certificate_recorded"] is False
    assert payload["codex_arming_performed"] is False
    assert payload["codex_config_mutation_performed"] is False
    assert not (tmp_path / "tiny_live_armed_dry_run_timer_observation_certificate.ndjson").exists()
    _assert_no_submit_or_order(payload)


def test_final_console_includes_r302_panel(monkeypatch, tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    monkeypatch.setattr(
        final_console,
        "build_armed_dry_run_timer_observation_certificate_panel",
        lambda **kwargs: _build(
            tmp_path,
            arming_state_packet=_arming_state_on(),
        )["armed_dry_run_timer_observation_certificate_panel"],
    )

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["armed_dry_run_timer_observation_certificate_panel"]

    assert panel["status"] == ARMED_DRY_RUN_TIMER_OBSERVATION_WAIT_CERTIFIED
    assert panel["requested_lane_key"] == LANE_44M_LONG
    assert panel["current_arming_state"]["exact_lane_auto_armed"] is True
    assert panel["timer_scheduler_summary"]["scheduler_latest_trigger_loop_status"] == "AUTONOMOUS_TRIGGER_WAIT"
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_cli_help_has_no_mutate_arm_disarm_or_simulate_args_for_r302() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-armed-dry-run-timer-observation-certificate",
            "--help",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--record-armed-dry-run-timer-observation-certificate" in result.stdout
    assert "--confirm-dry-run-autonomous-arming" not in result.stdout
    assert "--confirm-dry-run-autonomous-disarm" not in result.stdout
    assert "simulate" not in result.stdout.lower()
    assert "--arm" not in result.stdout
    assert "--disarm" not in result.stdout


def test_print_only_script_outputs_plan_without_running_dangerous_commands(
    tmp_path: Path,
) -> None:
    script = (
        REPO_ROOT
        / "scripts/hammer_print_r302_armed_dry_run_timer_observation_certificate_plan.sh"
    )
    before = sorted(tmp_path.iterdir())
    result = subprocess.run(
        ["bash", str(script)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "R302 PRINT ONLY - armed dry-run timer observation certificate plan" in result.stdout
    assert "tiny-live-armed-dry-run-timer-observation-certificate" in result.stdout
    assert "tiny-live-manual-operator-dry-run-arming-post-arm-certificate" in result.stdout
    assert "tiny-live-autonomous-trigger-scheduler-timer-health" in result.stdout
    assert "tiny-live-autonomous-dry-run-disarm-lane" in result.stdout
    assert "DO_NOT_RUN_FROM_CODEX MANUAL_OPERATOR_ONLY DRY_RUN_ONLY NO_ORDER" in result.stdout
    assert "/fapi/v1/order" not in result.stdout
    assert "sudo" not in result.stdout
    assert "systemctl" not in result.stdout
    assert sorted(tmp_path.iterdir()) == before


def _build(
    tmp_path: Path,
    *,
    lane_key: str | None = LANE_44M_LONG,
    arming_state_packet: dict,
    r298_bridge_packet: dict | None = None,
    timer_health_packet: dict | None = None,
    scheduler_records: list[dict] | None = None,
    record_armed_dry_run_timer_observation_certificate: bool = False,
    env: dict[str, str] | None = None,
) -> dict:
    r298 = r298_bridge_packet or _r298_ready_to_wait()
    timer = timer_health_packet or _timer_health()
    records = _scheduler_records() if scheduler_records is None else scheduler_records
    return build_tiny_live_armed_dry_run_timer_observation_certificate(
        log_dir=tmp_path,
        lane_key=lane_key,
        operator_id="local_operator",
        reason="R302 unit test observation; no Codex arming; no submit; no order.",
        arming_state_packet=arming_state_packet,
        timer_health_packet=timer,
        r298_bridge_packet=r298,
        r299_timer_observation_packet=_r299_from_timer(timer, r298),
        r300_bridge_packet=_r300_from_arming(arming_state_packet, lane_key or LANE_44M_LONG),
        r301_post_arm_packet=_r301_from_arming(arming_state_packet, lane_key or LANE_44M_LONG),
        scheduler_records=records,
        record_armed_dry_run_timer_observation_certificate=(
            record_armed_dry_run_timer_observation_certificate
        ),
        env=env or {
            "HAMMER_LIVE_EXECUTION_ENABLED": "false",
            "HAMMER_ALLOW_LIVE_ORDERS": "false",
        },
        now=NOW,
    )


def _arming_state_off() -> dict:
    return {
        "global_auto_live_enabled": False,
        "auto_execute_mode": "dry_run_only",
        "armed_lane_key": None,
        "allowed_lane_keys": [],
        "lane_auto_live_enabled_keys": [],
        "any_lane_auto_armed": False,
        "lanes": [],
        "dry_run_only": True,
        "live_execution_enabled": False,
        "allow_live_orders": False,
    }


def _arming_state_on() -> dict:
    return {
        "global_auto_live_enabled": True,
        "auto_execute_mode": "dry_run_only",
        "armed_lane_key": LANE_44M_LONG,
        "allowed_lane_keys": [LANE_44M_LONG],
        "lane_auto_live_enabled_keys": [LANE_44M_LONG],
        "any_lane_auto_armed": True,
        "lanes": [
            {
                "lane_key": LANE_44M_LONG,
                "lane_auto_live_enabled": True,
                "dry_run_only": True,
                "live_execution_enabled": False,
                "allow_live_orders": False,
                "real_order_forbidden": True,
            }
        ],
        "dry_run_only": True,
        "live_execution_enabled": False,
        "allow_live_orders": False,
    }


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
    }


def _scheduler_records() -> list[dict]:
    return [
        {
            "event_type": "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER",
            "status": "AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED",
            "trigger_loop_status": "AUTONOMOUS_TRIGGER_WAIT",
            "current_candidate_lane_key": None,
            "autonomous_dry_run_execution_recorded": False,
            "generated_at": "2026-06-17T12:00:00+00:00",
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    ]


def _r298_ready_to_wait() -> dict:
    return {
        "event_type": "TINY_LIVE_REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE",
        "status": "REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT",
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
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "blockers": [],
    }


def _r298_certified() -> dict:
    return {
        **_r298_ready_to_wait(),
        "status": "REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED",
        "current_real_candidate_exists": True,
        "current_real_candidate_lane_key": LANE_44M_LONG,
        "current_real_candidate_signal_id": "r302_real_signal_001",
        "current_real_candidate_freshness_status": "fresh",
        "current_real_candidate_live_qualification_class": "LIVE_QUALIFIED",
        "candidate_matches_requested_lane": True,
        "simulated_dry_run_trigger_recorded": True,
        "simulated_lifecycle_status": "SIMULATED_DRY_RUN_LIFECYCLE_RECORDED",
    }


def _r299_from_timer(timer: dict, r298: dict) -> dict:
    return {
        "event_type": "TINY_LIVE_REAL_CANDIDATE_TIMER_OBSERVATION_CERTIFICATE",
        "status": "REAL_CANDIDATE_TIMER_OBSERVATION_TRIGGER_CERTIFIED"
        if r298.get("candidate_matches_requested_lane") is True
        else "REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED",
        "timer_active": timer["timer_active"],
        "timer_loaded": timer["timer_loaded"],
        "recent_tick_seen": timer["recent_tick_seen"],
        "recent_tick_count": timer["recent_tick_count"],
        "test_only": False,
        "fake_candidate_used": False,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _r300_from_arming(arming: dict, lane_key: str) -> dict:
    exact = (
        arming.get("global_auto_live_enabled") is True
        and arming.get("armed_lane_key") == lane_key
        and lane_key in list(arming.get("allowed_lane_keys") or [])
        and lane_key in list(arming.get("lane_auto_live_enabled_keys") or [])
    )
    return {
        "status": "OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_ARMED_CERTIFIED"
        if exact
        else "OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_NOT_ARMED",
        "exact_lane_auto_armed": exact,
        "any_lane_auto_armed": arming.get("any_lane_auto_armed") is True,
        "armed_lane_key": arming.get("armed_lane_key"),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _r301_from_arming(arming: dict, lane_key: str) -> dict:
    exact = _r300_from_arming(arming, lane_key)["exact_lane_auto_armed"]
    return {
        "status": "MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_CERTIFIED"
        if exact
        else "MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_NOT_ARMED",
        "exact_lane_auto_armed": exact,
        "any_lane_auto_armed": arming.get("any_lane_auto_armed") is True,
        "armed_lane_key": arming.get("armed_lane_key"),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _assert_r302_safety_flags(payload: dict) -> None:
    assert payload["exact_lane_only"] is True
    assert payload["no_cross_lane_borrowing"] is True
    assert payload["test_only"] is False
    assert payload["fake_candidate_used"] is False
    assert payload["codex_arming_performed"] is False
    assert payload["codex_config_mutation_performed"] is False


def _assert_no_submit_or_order(payload: dict) -> None:
    assert payload["dry_run_only"] is True
    assert payload["live_execution_enabled"] is False
    assert payload["allow_live_orders"] is False
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True
    assert payload["executable_payload_created"] is False
    assert payload["order_payload_created"] is False
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["per_signal_operator_approval_required"] is False
    assert payload["safety"]["secrets_shown"] is False
