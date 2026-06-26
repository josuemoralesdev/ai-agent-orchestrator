from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_dry_run_timer_install_gate import (
    CONFIRMATION_PHRASE,
    EVENT_TYPE,
    INSTALL_GATE_BLOCKED_CONFIRMATION_REQUIRED,
    INSTALL_GATE_PREVIEW_READY,
    INSTALL_GATE_WRITTEN_TEMP_OR_REAL,
    LEDGER_FILENAME,
    SAFETY,
    SERVICE_NAME,
    TIMER_NAME,
    build_multi_lane_dry_run_timer_install_gate,
    load_multi_lane_dry_run_timer_install_gate_records,
)
from src.app.hammer_radar.operator.multi_lane_dry_run_timer_unit_preview import (
    build_multi_lane_dry_run_timer_unit_preview,
)

NOW = datetime(2026, 6, 26, 11, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_run_previews_only_and_writes_no_systemd_files(tmp_path: Path) -> None:
    install_dir = tmp_path / "systemd"
    payload = _build(tmp_path / "logs", install_dir=install_dir)
    records = load_multi_lane_dry_run_timer_install_gate_records(log_dir=tmp_path / "logs", limit=10)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["install_gate_status"] == INSTALL_GATE_PREVIEW_READY
    assert payload["preview_only"] is True
    assert payload["apply_requested"] is False
    assert payload["confirmation_phrase_matched"] is False
    assert payload["files_written"] == []
    assert payload["daemon_reload_called"] is False
    assert payload["enable_called"] is False
    assert payload["start_called"] is False
    assert not (install_dir / SERVICE_NAME).exists()
    assert not (install_dir / TIMER_NAME).exists()
    assert (tmp_path / "logs" / LEDGER_FILENAME).exists()
    assert records[0]["event_type"] == EVENT_TYPE


def test_wrong_or_missing_phrase_blocks_apply(tmp_path: Path) -> None:
    missing = _build(tmp_path / "logs1", install_dir=tmp_path / "systemd1", apply=True, confirmation=None)
    wrong = _build(tmp_path / "logs2", install_dir=tmp_path / "systemd2", apply=True, confirmation="wrong")

    for payload in (missing, wrong):
        assert payload["install_gate_status"] == INSTALL_GATE_BLOCKED_CONFIRMATION_REQUIRED
        assert payload["apply_requested"] is True
        assert payload["confirmation_phrase_matched"] is False
        assert payload["preview_only"] is True
        assert payload["files_written"] == []
        assert payload["mocked_systemctl_calls"] == []
        assert payload["daemon_reload_called"] is False
        assert payload["systemd_unit_installed"] is False
        assert payload["systemd_timer_installed"] is False


def test_apply_exact_phrase_writes_only_service_and_timer_to_temp_install_dir(tmp_path: Path) -> None:
    install_dir = tmp_path / "systemd"
    before = set(install_dir.glob("*")) if install_dir.exists() else set()

    payload = _build(tmp_path / "logs", install_dir=install_dir, apply=True, confirmation=CONFIRMATION_PHRASE)
    after = set(install_dir.glob("*"))

    assert payload["install_gate_status"] == INSTALL_GATE_WRITTEN_TEMP_OR_REAL
    assert payload["confirmation_phrase_matched"] is True
    assert payload["preview_only"] is False
    assert after - before == {install_dir / SERVICE_NAME, install_dir / TIMER_NAME}
    assert payload["files_written"] == [str(install_dir / SERVICE_NAME), str(install_dir / TIMER_NAME)]
    assert payload["systemd_unit_installed"] is True
    assert payload["systemd_timer_installed"] is True
    assert "multi_lane_dry_run_observation_scheduler" in (install_dir / SERVICE_NAME).read_text(encoding="utf-8")
    assert (install_dir / TIMER_NAME).read_text(encoding="utf-8").endswith("\n")


def test_apply_creates_backups_when_files_already_exist(tmp_path: Path) -> None:
    install_dir = tmp_path / "systemd"
    install_dir.mkdir()
    (install_dir / SERVICE_NAME).write_text("old service\n", encoding="utf-8")
    (install_dir / TIMER_NAME).write_text("old timer\n", encoding="utf-8")

    payload = _build(tmp_path / "logs", install_dir=install_dir, apply=True, confirmation=CONFIRMATION_PHRASE)

    assert len(payload["backups_created"]) == 2
    assert all(Path(path).exists() for path in payload["backups_created"])
    assert "old service" in Path(payload["backups_created"][0]).read_text(encoding="utf-8")


def test_mock_systemctl_records_daemon_reload_enable_start_without_executing(tmp_path: Path) -> None:
    with patch("subprocess.run") as run_mock:
        payload = _build(
            tmp_path / "logs",
            install_dir=tmp_path / "systemd",
            apply=True,
            confirmation=CONFIRMATION_PHRASE,
            systemctl_mode="mock",
        )

    run_mock.assert_not_called()
    assert payload["mocked_systemctl_calls"] == [
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", TIMER_NAME],
        ["systemctl", "start", TIMER_NAME],
    ]
    assert payload["real_systemctl_calls"] == []
    assert payload["daemon_reload_called"] is False
    assert payload["enable_called"] is False
    assert payload["start_called"] is False


def test_real_systemctl_mode_is_not_used_in_tests(tmp_path: Path) -> None:
    with patch("src.app.hammer_radar.operator.multi_lane_dry_run_timer_install_gate._run_real_systemctl") as real:
        payload = _build(
            tmp_path / "logs",
            install_dir=tmp_path / "systemd",
            apply=True,
            confirmation=CONFIRMATION_PHRASE,
            systemctl_mode="mock",
            write_ledger=False,
        )

    real.assert_not_called()
    assert payload["systemctl_mode"] == "mock"
    assert payload["real_systemctl_calls"] == []


def test_service_command_uses_r310_scheduler_with_once_and_repo_venv_python(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", install_dir=tmp_path / "systemd", write_ledger=False)
    command = payload["command_preview"]
    service = payload["service_content_preview"]

    assert command.startswith(str(REPO_ROOT / ".venv/bin/python"))
    assert "src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler" in command
    assert "--once" in command.split()
    assert f"ExecStart={command}" in service


def test_safety_fields_remain_locked(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", install_dir=tmp_path / "systemd", write_ledger=False)

    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected


def test_no_config_arming_live_flag_or_env_mutation(tmp_path: Path) -> None:
    risk_path = REPO_ROOT / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = REPO_ROOT / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")
    env_before = dict(os.environ)

    payload = _build(tmp_path / "logs", install_dir=tmp_path / "systemd", write_ledger=False)

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert dict(os.environ) == env_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert payload["autonomous_arming_state_changed"] is False
    assert payload["global_live_flags_changed"] is False
    assert payload["env_written"] is False
    assert payload["env_mutated"] is False


def test_no_binance_order_or_secret_surfaces_called(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = _build(tmp_path / "logs", install_dir=tmp_path / "systemd", write_ledger=False)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["leverage_change_called"] is False
    assert payload["margin_change_called"] is False
    assert payload["secrets_shown"] is False


def test_inspect_route_works_and_previews_only(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "multi-lane-dry-run-timer-install-gate",
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
    assert payload["install_gate_status"] == INSTALL_GATE_PREVIEW_READY
    assert payload["preview_only"] is True
    assert payload["apply_requested"] is False
    assert payload["files_written"] == []
    assert payload["daemon_reload_called"] is False
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False


def test_operator_script_exists_and_previews_only(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", "scripts/hammer_print_r312_multi_lane_timer_install_gate.sh"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "R312 HUMAN-REVIEWED MULTI-LANE TIMER INSTALL GATE" in result.stdout
    assert SERVICE_NAME in result.stdout
    assert TIMER_NAME in result.stdout
    assert "INSTALL PATH PREVIEW" in result.stdout
    assert "COMMAND PREVIEW" in result.stdout
    assert CONFIRMATION_PHRASE in result.stdout
    assert "APPLY COMMAND PREVIEW" in result.stdout
    assert "SAFETY FLAGS" in result.stdout
    assert "Recommended R313 path" in result.stdout
    assert "--apply --confirmation" in result.stdout
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_r311_compatibility_remains_intact(tmp_path: Path) -> None:
    r311 = build_multi_lane_dry_run_timer_unit_preview(
        log_dir=tmp_path / "logs",
        repo_root=REPO_ROOT,
        write=False,
        now=NOW,
    )
    r312 = _build(tmp_path / "logs", install_dir=tmp_path / "systemd", write_ledger=False)

    assert r312["service_content_preview"] == r311["service_content_preview"]
    assert r312["timer_content_preview"] == r311["timer_content_preview"]
    assert r312["service_content_sha256"] == r311["unit_preview_sha256"]
    assert r312["timer_content_sha256"] == r311["timer_preview_sha256"]


def _build(
    log_dir: Path,
    *,
    install_dir: Path,
    apply: bool = False,
    confirmation: str | None = None,
    systemctl_mode: str = "mock",
    write_ledger: bool = True,
) -> dict[str, object]:
    return build_multi_lane_dry_run_timer_install_gate(
        log_dir=log_dir,
        repo_root=REPO_ROOT,
        install_dir=install_dir,
        apply=apply,
        confirmation=confirmation,
        systemctl_mode=systemctl_mode,
        write_ledger=write_ledger,
        now=NOW,
    )
