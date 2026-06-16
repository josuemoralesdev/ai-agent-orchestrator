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
    SYSTEMD_TEMPLATE_READY,
    build_autonomous_trigger_scheduler_systemd_template_status,
    build_tiny_live_autonomous_trigger_scheduler_once,
    run_tiny_live_autonomous_trigger_scheduler_loop,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler_activation_readiness import (
    ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL,
    build_autonomous_trigger_scheduler_activation_readiness,
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

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_TEMPLATE_PATH = (
    REPO_ROOT / "ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template"
)
TIMER_TEMPLATE_PATH = (
    REPO_ROOT / "ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template"
)
CHECKLIST_PATH = (
    REPO_ROOT
    / "docs/hammer_radar/live_readiness/R289_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_INSTALL_CHECKLIST.md"
)
PRINT_ONLY_SCRIPT_PATH = REPO_ROOT / "scripts/hammer_print_autonomous_trigger_scheduler_systemd_install_plan.sh"
ACTIVATION_CHECKLIST_PATH = (
    REPO_ROOT
    / "docs/hammer_radar/live_readiness/R290_MANUAL_SYSTEMD_DRY_RUN_TIMER_ACTIVATION_CHECKLIST.md"
)
ACTIVATION_PRINT_ONLY_SCRIPT_PATH = (
    REPO_ROOT / "scripts/hammer_print_r290_manual_systemd_dry_run_activation_plan.sh"
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


def test_systemd_service_template_exists_and_is_dry_run_safe() -> None:
    text = SERVICE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert SERVICE_TEMPLATE_PATH.exists()
    assert "Type=oneshot" in text
    assert "WorkingDirectory=/home/josue/workspace/kernel/ai-agent-orchestrator-main" in text
    assert "tiny-live-autonomous-trigger-scheduler-once" in text
    assert "--record-autonomous-trigger-scheduler" in text
    assert "--operator-id systemd_scheduler" in text
    assert "systemd dry-run autonomous trigger scheduler tick; no submit." in text
    assert "HAMMER_LIVE_EXECUTION_ENABLED=false" in text
    assert "HAMMER_ALLOW_LIVE_ORDERS=false" in text
    assert "HAMMER_GLOBAL_KILL_SWITCH=true" in text
    _assert_template_text_safe(text)


def test_systemd_timer_template_exists_and_is_not_enabled_by_template() -> None:
    text = TIMER_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert TIMER_TEMPLATE_PATH.exists()
    assert "OnUnitActiveSec=2min" in text
    assert "RandomizedDelaySec=5s" in text
    assert "Persistent=false" in text
    assert "WantedBy=timers.target" in text
    assert "systemctl" not in text
    assert "sudo" not in text


def test_systemd_checklist_contains_install_status_and_rollback_commands() -> None:
    text = CHECKLIST_PATH.read_text(encoding="utf-8")

    assert CHECKLIST_PATH.exists()
    assert (
        "sudo install -m 0644 ops/systemd/hammer-radar/"
        "hammer-autonomous-trigger-scheduler-dry-run.service.template"
    ) in text
    assert "sudo systemctl daemon-reload" in text
    assert "sudo /usr/bin/systemctl start hammer-autonomous-trigger-scheduler-dry-run.timer" in text
    assert "journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service" in text
    assert "sudo systemctl disable --now hammer-autonomous-trigger-scheduler-dry-run.timer" in text
    assert "R289 remains dry-run scheduler only, no live orders" in text


def test_print_only_install_plan_script_prints_without_direct_systemd_execution() -> None:
    text = PRINT_ONLY_SCRIPT_PATH.read_text(encoding="utf-8")
    command_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("echo")
    ]

    assert PRINT_ONLY_SCRIPT_PATH.exists()
    assert "DRY RUN PRINT ONLY" in text
    assert "does not run sudo, systemctl, copy files" in text
    assert not any(line.startswith("sudo") for line in command_lines)
    assert not any("systemctl" in line for line in command_lines)
    assert not any("install -m" in line for line in command_lines)
    assert "hammer-autonomous-trigger-scheduler-dry-run.service.template" in text
    assert "R289_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_INSTALL_CHECKLIST.md" in text


def test_systemd_template_status_packet_safe() -> None:
    payload = build_autonomous_trigger_scheduler_systemd_template_status(repo_root=REPO_ROOT)

    assert payload["event_type"] == "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_TEMPLATE_STATUS"
    assert payload["created_by_phase"] == "R289_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_TEMPLATE_AND_INSTALL_CHECKLIST"
    assert payload["status"] == SYSTEMD_TEMPLATE_READY
    assert payload["service_template_present"] is True
    assert payload["timer_template_present"] is True
    assert payload["checklist_present"] is True
    assert payload["print_only_script_present"] is True
    assert payload["template_dry_run_only"] is True
    assert payload["installs_performed_by_codex"] is False
    assert payload["systemctl_called_by_codex"] is False
    assert payload["sudo_called_by_codex"] is False
    assert payload["live_execution_enabled"] is False
    assert payload["forbidden_pattern_hits"] == []
    _assert_no_submit_or_mutation(payload)


def test_systemd_template_status_cli_and_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path),
            "tiny-live-autonomous-trigger-scheduler-systemd-template-status",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    cli_payload = json.loads(result.stdout)
    assert cli_payload["installs_performed_by_codex"] is False
    assert cli_payload["systemctl_called_by_codex"] is False
    assert cli_payload["sudo_called_by_codex"] is False
    assert cli_payload["final_command_available"] is False
    assert cli_payload["submit_allowed"] is False

    response = TestClient(app).get("/tiny-live/autonomous-trigger-scheduler/systemd-template-status")
    api_payload = response.json()
    assert response.status_code == 200
    assert api_payload["installs_performed_by_codex"] is False
    assert api_payload["systemctl_called_by_codex"] is False
    assert api_payload["sudo_called_by_codex"] is False
    assert api_payload["final_command_available"] is False
    assert api_payload["submit_allowed"] is False


def test_activation_readiness_ready_when_templates_checklists_scripts_exist() -> None:
    payload = build_autonomous_trigger_scheduler_activation_readiness(repo_root=REPO_ROOT)

    assert payload["event_type"] == "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER_ACTIVATION_READINESS"
    assert payload["created_by_phase"] == "R290_MANUAL_SYSTEMD_INSTALL_DRY_RUN_ACTIVATION_CHECKLIST"
    assert payload["status"] == ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL
    assert payload["service_template_present"] is True
    assert payload["timer_template_present"] is True
    assert payload["checklist_present"] is True
    assert payload["print_only_script_present"] is True
    assert payload["activation_checklist_present"] is True
    assert payload["activation_print_only_script_present"] is True
    assert payload["templates_safe"] is True
    assert payload["forbidden_pattern_hits"] == []
    assert payload["approval_api_expected_url"] == "http://127.0.0.1:8015"
    assert payload["manual_install_commands"]
    assert payload["manual_start_commands"]
    assert payload["manual_status_commands"]
    assert payload["manual_tick_smoke_commands"]
    assert payload["manual_rollback_commands"]
    assert payload["codex_install_performed"] is False
    assert payload["codex_systemctl_start_performed"] is False
    assert payload["codex_systemctl_enable_performed"] is False
    assert payload["codex_sudo_performed"] is False
    assert payload["dry_run_only"] is True
    assert payload["live_execution_enabled"] is False
    _assert_no_submit_or_mutation(payload)


def test_activation_print_script_exists_and_prints_only() -> None:
    text = ACTIVATION_PRINT_ONLY_SCRIPT_PATH.read_text(encoding="utf-8")
    command_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("echo")
    ]

    assert ACTIVATION_PRINT_ONLY_SCRIPT_PATH.exists()
    assert "R290 DRY RUN PRINT ONLY" in text
    assert "does not run sudo, systemctl, cp, install, rm" in text
    assert not any(line.startswith("sudo") for line in command_lines)
    assert not any(line.startswith("systemctl") for line in command_lines)
    assert not any(line.startswith("cp ") for line in command_lines)
    assert not any(line.startswith("install ") for line in command_lines)
    assert not any(line.startswith("rm ") for line in command_lines)
    assert "sudo install -m 0644" in text
    assert "sudo /usr/bin/systemctl start hammer-autonomous-trigger-scheduler-dry-run.timer" in text
    assert "sudo systemctl disable --now hammer-autonomous-trigger-scheduler-dry-run.timer" in text
    assert "tiny-live-autonomous-trigger-scheduler-activation-readiness" in text


def test_activation_docs_templates_and_scripts_do_not_expose_secrets_or_live_submit() -> None:
    paths = [
        SERVICE_TEMPLATE_PATH,
        TIMER_TEMPLATE_PATH,
        CHECKLIST_PATH,
        PRINT_ONLY_SCRIPT_PATH,
        ACTIVATION_CHECKLIST_PATH,
        ACTIVATION_PRINT_ONLY_SCRIPT_PATH,
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden = (
        "BINANCE_API_SECRET=",
        "BINANCE_API_KEY=",
        "/fapi/v1/order",
        "fapi/v1/order",
        "final-live-submit",
        "submit-live",
        "codex_install_performed: true",
        '"codex_install_performed": true',
        "codex_sudo_performed: true",
        '"codex_sudo_performed": true',
        "codex_systemctl_start_performed: true",
        '"codex_systemctl_start_performed": true',
    )
    for token in forbidden:
        assert token not in combined


def test_activation_readiness_cli_and_api_safe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path),
            "tiny-live-autonomous-trigger-scheduler-activation-readiness",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    cli_payload = json.loads(result.stdout)
    assert cli_payload["status"] == ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL
    assert cli_payload["codex_install_performed"] is False
    assert cli_payload["codex_systemctl_start_performed"] is False
    assert cli_payload["codex_systemctl_enable_performed"] is False
    assert cli_payload["codex_sudo_performed"] is False
    assert cli_payload["final_command_available"] is False
    assert cli_payload["submit_allowed"] is False
    assert cli_payload["per_signal_operator_approval_required"] is False

    with patch.object(urllib.request, "urlopen") as urlopen:
        response = TestClient(app).get("/tiny-live/autonomous-trigger-scheduler/activation-readiness")

    urlopen.assert_not_called()
    api_payload = response.json()
    assert response.status_code == 200
    assert api_payload["status"] == ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL
    assert api_payload["autonomous_trigger_scheduler_activation_panel"][
        "activation_readiness_status"
    ] == ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL
    assert api_payload["final_command_available"] is False
    assert api_payload["submit_allowed"] is False
    assert api_payload["real_order_forbidden"] is True
    _assert_no_submit_or_mutation(api_payload)


def test_final_console_includes_scheduler_systemd_panel(tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["autonomous_trigger_scheduler_systemd_panel"]

    assert panel["template_status"] == SYSTEMD_TEMPLATE_READY
    assert panel["service_template_path"] == (
        "ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template"
    )
    assert panel["timer_template_path"] == (
        "ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template"
    )
    assert panel["checklist_path"] == (
        "docs/hammer_radar/live_readiness/R289_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_INSTALL_CHECKLIST.md"
    )
    assert panel["print_only_install_plan_script_path"] == (
        "scripts/hammer_print_autonomous_trigger_scheduler_systemd_install_plan.sh"
    )
    assert panel["install_performed"] is False
    assert panel["systemctl_called_by_codex"] is False
    assert panel["sudo_called_by_codex"] is False
    assert panel["dry_run_only"] is True
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_final_console_includes_scheduler_activation_panel(tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["autonomous_trigger_scheduler_activation_panel"]

    assert panel["activation_readiness_status"] == ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL
    assert panel["activation_checklist_path"] == (
        "docs/hammer_radar/live_readiness/R290_MANUAL_SYSTEMD_DRY_RUN_TIMER_ACTIVATION_CHECKLIST.md"
    )
    assert panel["activation_print_only_script_path"] == (
        "scripts/hammer_print_r290_manual_systemd_dry_run_activation_plan.sh"
    )
    assert panel["codex_install_performed"] is False
    assert panel["codex_systemctl_start_performed"] is False
    assert panel["codex_systemctl_enable_performed"] is False
    assert panel["codex_sudo_performed"] is False
    assert panel["dry_run_only"] is True
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


def _assert_template_text_safe(text: str) -> None:
    forbidden = (
        "/fapi/v1/order",
        "test-order",
        "leverage_change",
        "margin_change",
        "BINANCE_API_SECRET=",
        "BINANCE_API_KEY=",
        "final-live-submit",
        "submit-live",
        "sudo",
        "systemctl",
    )
    for token in forbidden:
        assert token not in text
