from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.tiny_live_manual_operator_dry_run_arming_post_arm_certificate import (
    MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_BLOCKED,
    MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_CERTIFIED,
    MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_NOT_ARMED,
    build_tiny_live_manual_operator_dry_run_arming_post_arm_certificate,
)

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_NEAR_MISS = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_PAPER_ONLY = "BTCUSDT|8m|short|ladder_close_50_618"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_valid_lane_not_armed_returns_not_armed(tmp_path: Path) -> None:
    payload = _build(tmp_path, arming_state_packet=_arming_state_off())

    assert payload["status"] == MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_NOT_ARMED
    assert payload["manual_operator_arming_required_before_certification"] is True
    assert payload["manual_operator_arming_observed"] is False
    assert payload["exact_lane_auto_armed"] is False
    assert payload["any_lane_auto_armed"] is False
    assert payload["lane_is_live_qualified"] is True
    assert payload["blockers"] == []
    assert payload["exact_lane_only"] is True
    assert payload["no_cross_lane_borrowing"] is True
    assert payload["test_only"] is False
    assert payload["fake_candidate_used"] is False
    assert payload["codex_arming_performed"] is False
    assert payload["codex_config_mutation_performed"] is False
    _assert_manual_commands(payload)
    _assert_no_submit_or_order(payload)


def test_valid_lane_armed_fixture_certifies(tmp_path: Path) -> None:
    payload = _build(tmp_path, arming_state_packet=_arming_state_on())

    assert payload["status"] == MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_CERTIFIED
    assert payload["manual_operator_arming_required_before_certification"] is False
    assert payload["manual_operator_arming_observed"] is True
    assert payload["exact_lane_auto_armed"] is True
    assert payload["any_lane_auto_armed"] is True
    assert payload["global_auto_live_enabled"] is True
    assert payload["armed_lane_key"] == LANE_44M_LONG
    assert payload["requested_lane_in_allowed_lane_keys"] is True
    assert payload["requested_lane_in_lane_auto_live_enabled_keys"] is True
    assert payload["allowed_lane_keys_from_arming_state"] == [LANE_44M_LONG]
    _assert_manual_commands(payload)
    _assert_no_submit_or_order(payload)


def test_invalid_lane_blocks(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        lane_key="ETHUSDT|44m|long|ladder_close_50_618",
        arming_state_packet=_arming_state_off(),
    )

    assert payload["status"] == MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_BLOCKED
    assert payload["lane_is_live_qualified"] is False
    assert "requested_lane_not_live_qualified" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_near_miss_lane_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, lane_key=LANE_NEAR_MISS, arming_state_packet=_arming_state_off())

    assert payload["status"] == MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_BLOCKED
    assert payload["lane_is_near_miss"] is True
    assert "requested_lane_is_near_miss" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_paper_only_lane_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, lane_key=LANE_PAPER_ONLY, arming_state_packet=_arming_state_off())

    assert payload["status"] == MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_BLOCKED
    assert payload["lane_is_paper_only"] is True
    assert "requested_lane_is_paper_only" in payload["blockers"]
    _assert_no_submit_or_order(payload)


def test_live_execution_flag_detected_blocks(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        arming_state_packet={**_arming_state_on(), "live_execution_enabled": True},
        env={"HAMMER_LIVE_EXECUTION_ENABLED": "false", "HAMMER_ALLOW_LIVE_ORDERS": "false"},
    )

    assert payload["status"] == MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_BLOCKED
    assert "live_execution_flag_detected" in payload["blockers"]
    assert payload["exact_lane_auto_armed"] is True
    _assert_no_submit_or_order(payload)


def test_record_appends_only_r301_ledger(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        arming_state_packet=_arming_state_off(),
        record_manual_operator_dry_run_arming_post_arm_certificate=True,
    )

    assert payload["manual_operator_dry_run_arming_post_arm_certificate_recorded"] is True
    assert (
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
        "build_status_tiny_live_manual_operator_dry_run_arming_post_arm_certificate",
        lambda **kwargs: _build(tmp_path, arming_state_packet=_arming_state_off()),
    )
    response = TestClient(app).get(
        "/tiny-live/manual-operator-dry-run-arming-post-arm-certificate/status"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type"] == "TINY_LIVE_MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_CERTIFICATE"
    assert payload["record_manual_operator_dry_run_arming_post_arm_certificate_requested"] is False
    assert payload["manual_operator_dry_run_arming_post_arm_certificate_recorded"] is False
    assert payload["codex_arming_performed"] is False
    assert payload["codex_config_mutation_performed"] is False
    assert not (
        tmp_path / "tiny_live_manual_operator_dry_run_arming_post_arm_certificate.ndjson"
    ).exists()
    _assert_no_submit_or_order(payload)


def test_final_console_includes_post_arm_certificate_panel(
    monkeypatch, tmp_path: Path
) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    monkeypatch.setattr(
        final_console,
        "build_manual_operator_dry_run_arming_post_arm_certificate_panel",
        lambda **kwargs: _build(
            tmp_path,
            arming_state_packet=_arming_state_off(),
        )["manual_operator_dry_run_arming_post_arm_certificate_panel"],
    )

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["manual_operator_dry_run_arming_post_arm_certificate_panel"]

    assert panel["status"] == MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_NOT_ARMED
    assert panel["requested_lane_key"] == LANE_44M_LONG
    assert panel["manual_operator_arming_observed"] is False
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True
    assert "manual_operator_arm_command" in panel["manual_operator_commands"]
    assert "post_arm_verification_command" in panel["manual_operator_commands"]


def test_cli_help_has_no_mutate_arm_disarm_or_simulate_args_for_r301() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-manual-operator-dry-run-arming-post-arm-certificate",
            "--help",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--record-manual-operator-dry-run-arming-post-arm-certificate" in result.stdout
    assert "--confirm-dry-run-autonomous-arming" not in result.stdout
    assert "--confirm-dry-run-autonomous-disarm" not in result.stdout
    assert "--simulate" not in result.stdout
    assert "tests-only" not in result.stdout.lower()
    assert "--arm" not in result.stdout
    assert "--disarm" not in result.stdout


def test_cli_rejects_arm_flag_for_r301() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-manual-operator-dry-run-arming-post-arm-certificate",
            "--arm",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "unrecognized arguments: --arm" in result.stderr


def test_print_only_script_outputs_plan_without_running_dangerous_commands(
    tmp_path: Path,
) -> None:
    script = (
        REPO_ROOT
        / "scripts/hammer_print_r301_manual_operator_dry_run_arming_post_arm_certificate_plan.sh"
    )
    before = sorted(tmp_path.iterdir())
    result = subprocess.run(
        ["bash", str(script)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert (
        "R301 PRINT ONLY - manual operator dry-run arming post-arm certificate plan"
        in result.stdout
    )
    assert "curl -sS" in result.stdout
    assert "tiny-live-manual-operator-dry-run-arming-post-arm-certificate" in result.stdout
    assert "tiny-live-autonomous-dry-run-arm-lane" in result.stdout
    assert "tiny-live-autonomous-dry-run-disarm-lane" in result.stdout
    assert "DO_NOT_RUN_FROM_CODEX MANUAL_OPERATOR_ONLY DRY_RUN_ONLY NO_ORDER" in result.stdout
    assert "grep -R" in result.stdout
    assert "sudo" not in result.stdout
    assert "systemctl" not in result.stdout
    assert sorted(tmp_path.iterdir()) == before


def _build(
    tmp_path: Path,
    *,
    lane_key: str | None = LANE_44M_LONG,
    arming_state_packet: dict,
    record_manual_operator_dry_run_arming_post_arm_certificate: bool = False,
    env: dict[str, str] | None = None,
) -> dict:
    return build_tiny_live_manual_operator_dry_run_arming_post_arm_certificate(
        log_dir=tmp_path,
        lane_key=lane_key,
        operator_id="local_operator",
        reason="R301 unit test certificate; no Codex arming; no submit; no order.",
        arming_state_packet=arming_state_packet,
        timer_health_packet=_timer_health(),
        r298_bridge_packet=_r298_ready_to_wait(),
        r299_timer_observation_packet=_r299_ready_to_wait(),
        scheduler_records=_scheduler_records(),
        record_manual_operator_dry_run_arming_post_arm_certificate=(
            record_manual_operator_dry_run_arming_post_arm_certificate
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


def _timer_health() -> dict:
    return {
        "status": "TIMER_HEALTH_ACTIVE",
        "timer_active": True,
        "timer_loaded": True,
        "recent_tick_seen": True,
        "recent_tick_count": 2,
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
            "generated_at": "2026-06-17T11:58:00+00:00",
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
        "test_only": False,
        "fake_candidate_used": False,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _r299_ready_to_wait() -> dict:
    return {
        "event_type": "TINY_LIVE_REAL_CANDIDATE_TIMER_OBSERVATION_CERTIFICATE",
        "status": "REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED",
        "timer_active": True,
        "recent_tick_seen": True,
        "recent_tick_count": 2,
        "test_only": False,
        "fake_candidate_used": False,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _assert_manual_commands(payload: dict) -> None:
    for key in (
        "manual_operator_arm_command",
        "manual_operator_disarm_command",
        "manual_operator_status_command",
        "post_arm_verification_command",
    ):
        command = payload[key]
        if key != "post_arm_verification_command":
            assert "DO_NOT_RUN_FROM_CODEX" in command
            assert "MANUAL_OPERATOR_ONLY" in command
            assert "DRY_RUN_ONLY" in command
            assert "NO_ORDER" in command
    assert "tiny-live-autonomous-dry-run-arm-lane" in payload["manual_operator_arm_command"]
    assert (
        "tiny-live-autonomous-dry-run-disarm-lane"
        in payload["manual_operator_disarm_command"]
    )
    assert (
        "tiny-live-autonomous-dry-run-arming-status"
        in payload["manual_operator_status_command"]
    )
    assert (
        "tiny-live-manual-operator-dry-run-arming-post-arm-certificate"
        in payload["post_arm_verification_command"]
    )


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
    assert payload["safety"]["codex_arming_performed"] is False
    assert payload["safety"]["codex_config_mutation_performed"] is False
