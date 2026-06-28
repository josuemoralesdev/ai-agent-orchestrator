from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_observation_alert_send_gate import (
    build_multi_lane_observation_alert_send_gate,
)
from src.app.hammer_radar.operator.observation_alert_send_gate_operator_drill import (
    build_synthetic_health_panel,
)
from src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview import (
    FUTURE_CONFIRMATION_PHRASE,
    build_real_telegram_observation_alert_send_preview,
)
from src.app.hammer_radar.operator.real_telegram_observation_alert_synthetic_send_drill_preview import (
    build_real_telegram_observation_alert_synthetic_send_drill_preview,
)
from src.app.hammer_radar.operator.real_telegram_synthetic_alert_activation_packet import (
    ACTIVATION_PACKET_BLOCKED,
    ACTIVATION_PACKET_READY,
    EVENT_TYPE,
    LEDGER_FILENAME,
    SCENARIO_SYNTHETIC_STALE_OBSERVATION,
    build_real_telegram_synthetic_alert_activation_packet,
    format_real_telegram_synthetic_alert_activation_packet_json,
    format_real_telegram_synthetic_alert_activation_packet_text,
)
from src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate import (
    SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED,
    SEND_GATE_MOCK_SENT,
    SEND_GATE_PREVIEW_READY,
    SEND_GATE_REAL_SEND_DISABLED_IN_CODEX,
    build_real_telegram_synthetic_alert_send_apply_gate,
)

NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_TOKEN = "1234:abcdefghijklmnopqrstuvwxyz"
RAW_CHAT_ID = "-1001234567890"


def test_packet_ready_when_r321_proof_paths_clean_and_credentials_ready(tmp_path: Path) -> None:
    payload = _packet(tmp_path)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["activation_packet_status"] == ACTIVATION_PACKET_READY
    assert payload["activation_packet_blockers"] == []
    assert payload["credentials_ready"] is True
    assert payload["r321_preview_status"] == SEND_GATE_PREVIEW_READY
    assert payload["r321_wrong_phrase_block_status"] == SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED
    assert payload["r321_mock_apply_status"] == SEND_GATE_MOCK_SENT
    assert payload["r321_real_disabled_status"] == SEND_GATE_REAL_SEND_DISABLED_IN_CODEX


def test_packet_blocked_when_credentials_missing(tmp_path: Path) -> None:
    payload = _packet(tmp_path, env={}, env_file_path=tmp_path / "missing.env")

    assert payload["activation_packet_status"] == ACTIVATION_PACKET_BLOCKED
    assert payload["credentials_ready"] is False
    assert "telegram_credentials_missing" in payload["activation_packet_blockers"]


def test_packet_contains_safe_preview_command(tmp_path: Path) -> None:
    payload = _packet(tmp_path)

    assert payload["safe_preview_command"] == (
        "PYTHONPATH=. .venv/bin/python -m "
        "src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate "
        "--log-dir logs/hammer_radar_forward --json"
    )


def test_packet_contains_mock_apply_command(tmp_path: Path) -> None:
    command = str(_packet(tmp_path)["mock_apply_command"])

    assert "--apply" in command
    assert f'--confirmation "{FUTURE_CONFIRMATION_PHRASE}"' in command
    assert "--telegram-sender-mode mock" in command
    assert "--scenario synthetic_stale_observation" in command


def test_packet_contains_real_disabled_command(tmp_path: Path) -> None:
    command = str(_packet(tmp_path)["real_disabled_command"])

    assert "--apply" in command
    assert f'--confirmation "{FUTURE_CONFIRMATION_PHRASE}"' in command
    assert "--telegram-sender-mode real-disabled" in command
    assert "--scenario synthetic_stale_observation" in command


def test_packet_does_not_expose_executable_real_sender_command(tmp_path: Path) -> None:
    payload = _packet(tmp_path)

    assert payload["real_send_command_manual_only_status"] == "not_available_in_current_code_r321_has_no_real_sender_mode"
    assert str(payload["real_send_command_manual_only"]).startswith("# MANUAL ONLY - NOT EXECUTABLE IN R322")
    assert "intentionally unavailable" in str(payload["real_send_command_manual_only"])


def test_packet_marks_manual_only_warning(tmp_path: Path) -> None:
    warning = str(_packet(tmp_path)["real_send_command_manual_only_warning"])

    assert "MANUAL ONLY" in warning
    assert "NOT EXECUTED BY CODEX" in warning
    assert "does not add a real sender mode" in warning


def test_packet_includes_preflight_checklist(tmp_path: Path) -> None:
    checklist = _packet(tmp_path)["operator_preflight_checklist"]

    for item in (
        "R321 committed",
        "Telegram credentials ready and masked",
        "safe preview command passes",
        "wrong phrase blocks",
        "mock apply records mock send only",
        "real-disabled path blocks real send",
        "no secret leak scan clean",
        "no env mutation",
        "no config/arming mutation",
        "no systemd mutation",
        "live safety still locked",
        "no current real trade execution triggered",
        "operator understands this is a Telegram synthetic alert only, not a trade",
    ):
        assert item in checklist


def test_packet_includes_abort_conditions(tmp_path: Path) -> None:
    abort_conditions = _packet(tmp_path)["operator_abort_conditions"]

    for item in (
        "credentials missing",
        "any raw secret appears",
        "real_order_forbidden=false",
        "submit_allowed=true",
        "final_command_available=true",
        "config/arming diff present",
        ".env changed",
        "systemd service changed",
        "unexpected Telegram send already occurred",
        "alert scenario is not synthetic",
        "command would touch Binance or trading endpoints",
    ):
        assert item in abort_conditions


def test_packet_never_calls_telegram(tmp_path: Path) -> None:
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = _packet(tmp_path)

    urlopen.assert_not_called()
    assert payload["codex_validation_real_send_forbidden"] is True
    assert payload["codex_validation_sent_real_telegram"] is False


def test_real_telegram_send_called_false(tmp_path: Path) -> None:
    assert _packet(tmp_path)["real_telegram_send_called"] is False


def test_telegram_send_called_false(tmp_path: Path) -> None:
    assert _packet(tmp_path)["telegram_send_called"] is False


def test_full_token_and_chat_id_never_appear_in_json_or_text(tmp_path: Path) -> None:
    payload = _packet(tmp_path)
    combined = "\n".join(
        [
            json.dumps(payload, sort_keys=True),
            format_real_telegram_synthetic_alert_activation_packet_json(payload),
            format_real_telegram_synthetic_alert_activation_packet_text(payload),
        ]
    )

    assert RAW_TOKEN not in combined
    assert RAW_CHAT_ID not in combined


def test_no_secret_leak_passed_true(tmp_path: Path) -> None:
    payload = _packet(tmp_path)

    assert payload["no_secret_leak_passed"] is True
    assert payload["secrets_shown"] is False


def test_no_config_mutation(tmp_path: Path) -> None:
    risk_path = REPO_ROOT / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = REPO_ROOT / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")

    payload = _packet(tmp_path, write=True)

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert (tmp_path / LEDGER_FILENAME).exists()


def test_no_env_mutation(tmp_path: Path) -> None:
    before = dict(os.environ)
    payload = _packet(tmp_path)

    assert dict(os.environ) == before
    assert payload["env_written"] is False
    assert payload["env_mutated"] is False


def test_no_arming_mutation(tmp_path: Path) -> None:
    payload = _packet(tmp_path)

    assert payload["autonomous_arming_state_changed"] is False
    assert payload["global_live_flags_changed"] is False


def test_no_systemd_mutation(tmp_path: Path) -> None:
    payload = _packet(tmp_path)

    assert payload["systemd_unit_mutated"] is False
    assert payload["scheduler_started"] is False


def test_no_live_order(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = _packet(tmp_path)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    submit_test_order.assert_not_called()
    preview_payload.assert_not_called()
    signed_order.assert_not_called()
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False


def test_no_submit(tmp_path: Path) -> None:
    assert _packet(tmp_path)["submit_allowed"] is False


def test_no_final_command(tmp_path: Path) -> None:
    assert _packet(tmp_path)["final_command_available"] is False


def test_no_binance_endpoint(tmp_path: Path) -> None:
    payload = _packet(tmp_path)

    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["leverage_change_called"] is False
    assert payload["margin_change_called"] is False


def test_inspect_route_works(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "real-telegram-synthetic-alert-activation-packet",
            "--no-write",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", **_env()},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["activation_packet_status"] == ACTIVATION_PACKET_READY
    assert payload["real_telegram_send_called"] is False


def test_operator_script_exists_and_prints_no_secrets(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts/hammer_print_r322_real_telegram_synthetic_alert_activation_packet.sh"
    script_text = script.read_text(encoding="utf-8")

    assert script.exists()
    assert "--apply" not in script_text
    assert "sendMessage" not in script_text
    result = subprocess.run(
        ["bash", str(script.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs"), **_env()},
        text=True,
        capture_output=True,
        check=True,
    )

    for section in (
        "R322 OPERATOR-RUN REAL TELEGRAM SYNTHETIC ALERT SEND ACTIVATION PACKET",
        "ACTIVATION PACKET STATUS",
        "TELEGRAM READINESS",
        "R321 GATE PROOF SUMMARY",
        "SAFE PREVIEW COMMAND",
        "MOCK APPLY COMMAND",
        "REAL-DISABLED COMMAND",
        "MANUAL-ONLY REAL-SEND STATUS",
        "OPERATOR PREFLIGHT CHECKLIST",
        "OPERATOR ABORT CONDITIONS",
        "SAFETY FLAGS",
        "RECOMMENDED NEXT PHASE",
    ):
        assert section in result.stdout
    assert "real_telegram_send_called: False" in result.stdout
    assert RAW_TOKEN not in result.stdout
    assert RAW_CHAT_ID not in result.stdout


def test_r321_r320_r319_r318_r317_r316_r315_r314_compatibility_remains_intact(tmp_path: Path) -> None:
    r322_payload = _packet(tmp_path)
    r321_payload = build_real_telegram_synthetic_alert_send_apply_gate(
        log_dir=tmp_path,
        env=_env(),
        write=False,
        no_write=True,
        now=NOW,
    )
    r320_payload = build_real_telegram_observation_alert_synthetic_send_drill_preview(
        log_dir=tmp_path,
        scenario=SCENARIO_SYNTHETIC_STALE_OBSERVATION,
        env=_env(),
        write=False,
        no_write=True,
        now=NOW,
    )
    health = build_synthetic_health_panel(
        scenario_name="stale_observation",
        now=NOW,
        max_age_seconds=180,
    )
    r315_preview = r322_payload["source_r321_preview"]["source_alert_preview"]  # type: ignore[index]
    r316_gate = build_multi_lane_observation_alert_send_gate(
        log_dir=tmp_path,
        apply=False,
        alert_preview=r315_preview,  # type: ignore[arg-type]
        write=False,
        no_write=True,
        now=NOW,
    )
    r318_preview = build_real_telegram_observation_alert_send_preview(
        log_dir=tmp_path,
        env=_env(),
        alert_preview=r315_preview,  # type: ignore[arg-type]
        write=False,
        no_write=True,
        now=NOW,
    )

    assert health["event_type"] == "R314_MULTI_LANE_OBSERVATION_HEALTH_PANEL"
    assert r315_preview["event_type"] == "R315_MULTI_LANE_OBSERVATION_ALERTING_PREVIEW"  # type: ignore[index]
    assert r316_gate["event_type"] == "R316_HUMAN_REVIEWED_OBSERVATION_ALERT_SEND_GATE"
    assert r318_preview["event_type"] == "R318_REAL_TELEGRAM_ALERT_SEND_GATE_PREVIEW"
    assert r318_preview["telegram_config_readiness"]["telegram_config_valid_for_future_send"] is True
    assert r320_payload["event_type"] == "R320_REAL_TELEGRAM_OBSERVATION_ALERT_SYNTHETIC_SEND_DRILL_PREVIEW"
    assert r321_payload["event_type"] == "R321_HUMAN_REVIEWED_REAL_TELEGRAM_SYNTHETIC_ALERT_SEND_APPLY_GATE"
    assert r322_payload["event_type"] == EVENT_TYPE


def _packet(
    tmp_path: Path,
    *,
    env: dict[str, str] | None = None,
    env_file_path: str | Path | None = None,
    write: bool = False,
) -> dict[str, object]:
    return build_real_telegram_synthetic_alert_activation_packet(
        log_dir=tmp_path,
        scenario=SCENARIO_SYNTHETIC_STALE_OBSERVATION,
        env=env if env is not None else _env(),
        env_file_path=env_file_path,
        write=write,
        no_write=not write,
        now=NOW,
    )


def _env() -> dict[str, str]:
    return {"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID}
