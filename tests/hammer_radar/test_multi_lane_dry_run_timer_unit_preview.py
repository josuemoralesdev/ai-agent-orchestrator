from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler import (
    build_multi_lane_dry_run_observation,
)
from src.app.hammer_radar.operator.multi_lane_dry_run_timer_unit_preview import (
    EVENT_TYPE,
    FUTURE_CONFIRMATION_PHRASE_PREVIEW,
    LEDGER_FILENAME,
    SAFETY,
    SERVICE_NAME,
    TIMER_NAME,
    build_multi_lane_dry_run_timer_unit_preview,
    load_multi_lane_dry_run_timer_unit_preview_records,
)

NOW = datetime(2026, 6, 26, 10, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_module_runs_and_writes_preview_ledger(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = _build(log_dir)
    records = load_multi_lane_dry_run_timer_unit_preview_records(log_dir=log_dir, limit=10)

    assert payload["event_type"] == EVENT_TYPE
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1
    assert records[0]["event_type"] == EVENT_TYPE


def test_service_and_timer_names_are_present(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["service_name"] == SERVICE_NAME
    assert payload["timer_name"] == TIMER_NAME
    assert SERVICE_NAME in payload["timer_content_preview"]
    assert TIMER_NAME == "hammer-multi-lane-dry-run-observation.timer"


def test_command_uses_r310_scheduler_with_once_and_repo_venv_python(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)
    command = payload["command_preview"]

    assert command.startswith(str(REPO_ROOT / ".venv/bin/python"))
    assert "src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler" in command
    assert "--once" in command.split()
    assert payload["validation_summary"]["command_uses_venv_python"] is True
    assert payload["validation_summary"]["command_uses_once"] is True
    assert payload["validation_summary"]["command_is_observation_only"] is True


def test_preview_writes_only_ledger_not_systemd_files(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    before = set(log_dir.glob("*")) if log_dir.exists() else set()

    payload = _build(log_dir, write=True)
    after = set(log_dir.glob("*"))

    assert after - before == {log_dir / LEDGER_FILENAME}
    assert payload["systemd_unit_mutated"] is False
    assert payload["systemd_unit_installed"] is False
    assert payload["systemd_timer_installed"] is False


def test_preview_does_not_call_systemctl_or_daemon_reload(tmp_path: Path) -> None:
    with patch("subprocess.run") as run_mock, patch("os.system") as system_mock:
        payload = _build(tmp_path / "logs", write=False)

    run_mock.assert_not_called()
    system_mock.assert_not_called()
    assert "systemctl" not in payload["service_content_preview"]
    assert "systemctl" not in payload["timer_content_preview"]
    assert "daemon-reload" not in payload["service_content_preview"]
    assert "daemon-reload" not in payload["timer_content_preview"]
    assert payload["daemon_reload_called"] is False


def test_safety_fields_remain_locked(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected
    assert payload["validation_summary"]["no_live_flags"] is True
    assert payload["validation_summary"]["no_apply_flags"] is True
    assert payload["validation_summary"]["no_binance_endpoint_flags"] is True


def test_future_confirmation_phrase_is_preview_only_and_inactive(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["systemd_write_gate_required"] is True
    assert payload["future_confirmation_phrase_preview"] == FUTURE_CONFIRMATION_PHRASE_PREVIEW
    assert payload["future_confirmation_phrase_active"] is False
    assert payload["future_confirmation_phrase_executable"] is False


def test_inspect_route_works(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "multi-lane-dry-run-timer-unit-preview",
            "--no-write",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["service_name"] == SERVICE_NAME
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", "scripts/hammer_print_r311_multi_lane_dry_run_timer_unit_preview.sh"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "R311 MULTI-LANE DRY-RUN TIMER UNIT PREVIEW" in result.stdout
    assert "SERVICE/TIMER" in result.stdout
    assert SERVICE_NAME in result.stdout
    assert TIMER_NAME in result.stdout
    assert "COMMAND PREVIEW" in result.stdout
    assert "CADENCE" in result.stdout
    assert "SYSTEMD WRITE GATE" in result.stdout
    assert "future_confirmation_phrase_preview" in result.stdout
    assert "SAFETY FLAGS" in result.stdout
    assert "RECOMMENDED R312 PATH" in result.stdout


def test_r310_compatibility_remains_intact(tmp_path: Path) -> None:
    timer_packet = {"status": "TIMER_HEALTH_ACTIVE", "timer_active": True, "blockers": []}
    fresh_packet = {
        "status": "FRESH_TRIGGER_WAIT",
        "current_fresh_candidate_exists": False,
        "current_candidate_lane_key": None,
    }

    r310 = build_multi_lane_dry_run_observation(
        log_dir=tmp_path / "logs",
        write=False,
        now=NOW,
        timer_health_packet=timer_packet,
        fresh_trigger_packet=fresh_packet,
    )
    r311 = _build(tmp_path / "logs", write=False)

    assert r310["event_type"] == "R310_MULTI_LANE_DRY_RUN_OBSERVATION"
    assert r310["multi_lane_observation_gate_matrix"]["baseline_lane_preserved"] is True
    assert r310["scheduler_started"] is False
    assert r311["command_preview"].endswith("--once")


def test_no_config_or_arming_mutation(tmp_path: Path) -> None:
    risk_path = REPO_ROOT / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = REPO_ROOT / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")

    payload = _build(tmp_path / "logs")

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert payload["autonomous_arming_state_changed"] is False


def test_no_live_flags_or_binance_surfaces_enabled(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    before_env = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = _build(tmp_path / "logs", write=False)

    assert dict(os.environ) == before_env
    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert payload["live_execution_enabled"] is False
    assert payload["allow_live_orders"] is False
    assert payload["global_live_flags_changed"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False


def _build(log_dir: Path, *, write: bool = True) -> dict[str, object]:
    return build_multi_lane_dry_run_timer_unit_preview(
        log_dir=log_dir,
        repo_root=REPO_ROOT,
        write=write,
        now=NOW,
    )
