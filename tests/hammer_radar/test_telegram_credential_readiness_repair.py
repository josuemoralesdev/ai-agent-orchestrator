from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import (
    INFO_PREVIEW_NO_SEND,
    build_multi_lane_observation_alerting_preview,
)
from src.app.hammer_radar.operator.multi_lane_observation_health_panel import HEALTH_OK
from src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview import (
    build_real_telegram_observation_alert_send_preview,
    format_real_telegram_preview_json,
    format_real_telegram_preview_text,
)

NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_TOKEN = "1234:abcdefghijklmnopqrstuvwxyz"
RAW_CHAT_ID = "-1001234567890"


def test_json_readiness_field_is_not_null(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={})
    rendered = format_real_telegram_preview_json(payload)
    parsed = json.loads(rendered)

    assert parsed["telegram_config_readiness"] is not None
    assert parsed["telegram_config_readiness"]["secrets_shown"] is False


def test_missing_token_reports_blocker(tmp_path: Path) -> None:
    readiness = _readiness(_preview(tmp_path, env={"TELEGRAM_CHAT_ID": RAW_CHAT_ID}))

    assert readiness["telegram_token_present"] is False
    assert "telegram_token_missing" in readiness["telegram_config_blockers"]


def test_missing_chat_id_reports_blocker(tmp_path: Path) -> None:
    readiness = _readiness(_preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": RAW_TOKEN}))

    assert readiness["telegram_chat_id_present"] is False
    assert "telegram_chat_id_missing" in readiness["telegram_config_blockers"]


def test_present_token_and_chat_id_report_valid_future_config(tmp_path: Path) -> None:
    readiness = _readiness(_preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID}))

    assert readiness["telegram_token_present"] is True
    assert readiness["telegram_chat_id_present"] is True
    assert readiness["telegram_config_source_kind"] == "env"
    assert readiness["telegram_config_valid_for_future_send"] is True
    assert readiness["telegram_config_blockers"] == []


def test_private_env_file_fallback_works_when_process_env_missing(tmp_path: Path) -> None:
    env_file = tmp_path / "notifications.env"
    env_file.write_text(
        "\n".join(
            [
                "# private operator file",
                f"TELEGRAM_BOT_TOKEN='{RAW_TOKEN}'",
                f'TELEGRAM_CHAT_ID="{RAW_CHAT_ID}"',
                "HAMMER_ALERT_TELEGRAM_ENABLED=true",
            ]
        ),
        encoding="utf-8",
    )

    payload = _preview(tmp_path, env={}, env_file_path=env_file)
    readiness = _readiness(payload)
    rendered_json = format_real_telegram_preview_json(payload)
    rendered_text = format_real_telegram_preview_text(payload)
    combined = "\n".join([rendered_json, rendered_text])

    assert readiness["telegram_token_present"] is True
    assert readiness["telegram_chat_id_present"] is True
    assert readiness["telegram_config_valid_for_future_send"] is True
    assert readiness["telegram_config_source_kind"] == "private_env_file"
    assert readiness["telegram_config_source_path"] == str(env_file)
    assert readiness["telegram_config_source_path_present"] is True
    assert readiness["telegram_config_blockers"] == []
    assert payload["real_send_available_for_future"] is True
    assert payload["real_send_blockers"] == []
    assert payload["would_send_real_telegram_now"] is False
    assert payload["real_send_preview_only"] is True
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False
    assert payload["secrets_shown"] is False
    assert RAW_TOKEN not in combined
    assert RAW_CHAT_ID not in combined


def test_private_env_file_does_not_override_process_env_credentials(tmp_path: Path) -> None:
    env_file = tmp_path / "notifications.env"
    file_token = "9999:filetokenabcdefghijkl"
    file_chat_id = "-1009999999999"
    env_file.write_text(
        f"TELEGRAM_BOT_TOKEN={file_token}\nTELEGRAM_CHAT_ID={file_chat_id}\n",
        encoding="utf-8",
    )

    payload = _preview(
        tmp_path,
        env={"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID},
        env_file_path=env_file,
    )
    rendered = json.dumps(payload, sort_keys=True)

    assert _readiness(payload)["telegram_config_source_kind"] == "env"
    assert _readiness(payload)["telegram_token_preview"] == "1234...wxyz"
    assert _readiness(payload)["telegram_chat_id_preview"] == "-100...7890"
    assert file_token not in rendered
    assert file_chat_id not in rendered


def test_missing_private_env_file_keeps_missing_blockers(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={}, env_file_path=tmp_path / "missing.env")
    readiness = _readiness(payload)

    assert readiness["telegram_token_present"] is False
    assert readiness["telegram_chat_id_present"] is False
    assert readiness["telegram_config_source_kind"] == "unknown"
    assert readiness["telegram_config_source_path"] is None
    assert readiness["telegram_config_source_path_present"] is False
    assert readiness["telegram_config_blockers"] == ["telegram_token_missing", "telegram_chat_id_missing"]
    assert payload["real_send_available_for_future"] is False
    assert payload["real_send_blockers"] == ["telegram_token_missing", "telegram_chat_id_missing"]


def test_partial_private_env_file_reports_correct_missing_blocker(tmp_path: Path) -> None:
    env_file = tmp_path / "notifications.env"
    env_file.write_text(f"TELEGRAM_BOT_TOKEN={RAW_TOKEN}\n", encoding="utf-8")

    payload = _preview(tmp_path, env={}, env_file_path=env_file)
    readiness = _readiness(payload)

    assert readiness["telegram_token_present"] is True
    assert readiness["telegram_chat_id_present"] is False
    assert readiness["telegram_config_source_kind"] == "private_env_file"
    assert readiness["telegram_config_blockers"] == ["telegram_chat_id_missing"]
    assert payload["real_send_available_for_future"] is False
    assert payload["real_send_blockers"] == ["telegram_chat_id_missing"]


def test_token_is_masked_and_raw_token_not_printed(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID})
    text = json.dumps(payload, sort_keys=True)

    assert _readiness(payload)["telegram_token_preview"] == "1234...wxyz"
    assert RAW_TOKEN not in text


def test_chat_id_is_masked_and_raw_chat_id_not_printed(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID})
    text = json.dumps(payload, sort_keys=True)

    assert _readiness(payload)["telegram_chat_id_preview"] == "-100...7890"
    assert RAW_CHAT_ID not in text


def test_secrets_shown_false(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID})

    assert payload["secrets_shown"] is False
    assert payload["telegram_config_readiness"]["secrets_shown"] is False
    assert payload["safety"]["secrets_shown"] is False


def test_no_env_mutation(tmp_path: Path) -> None:
    before = dict(os.environ)
    env_file = tmp_path / "notifications.env"
    env_file.write_text(f"TELEGRAM_BOT_TOKEN={RAW_TOKEN}\nTELEGRAM_CHAT_ID={RAW_CHAT_ID}\n", encoding="utf-8")

    payload = _preview(tmp_path, env={}, env_file_path=env_file)

    assert dict(os.environ) == before
    assert payload["env_written"] is False
    assert payload["env_mutated"] is False


def test_no_config_mutation(tmp_path: Path) -> None:
    risk_path = REPO_ROOT / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = REPO_ROOT / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")

    payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID}, write=True)

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False


def test_no_telegram_send(tmp_path: Path) -> None:
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID})

    urlopen.assert_not_called()
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False


def test_no_real_telegram_send(tmp_path: Path) -> None:
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID})

    urlopen.assert_not_called()
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False


def test_no_arming_or_systemd_mutation(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={})

    assert payload["autonomous_arming_state_changed"] is False
    assert payload["global_live_flags_changed"] is False
    assert payload["systemd_unit_mutated"] is False
    assert payload["scheduler_started"] is False


def test_no_live_order_submit_final_or_binance_endpoint(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={})

    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["leverage_change_called"] is False
    assert payload["margin_change_called"] is False


def test_operator_script_exists_and_prints_no_secrets(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts/hammer_print_r319_telegram_credential_readiness_repair.sh"
    script_text = script.read_text(encoding="utf-8")

    assert script.exists()
    assert "--send" not in script_text
    assert "--apply" not in script_text
    result = subprocess.run(
        ["bash", str(script.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHONPATH": ".",
            "LOG_DIR": str(tmp_path / "logs"),
            "TELEGRAM_BOT_TOKEN": RAW_TOKEN,
            "TELEGRAM_CHAT_ID": RAW_CHAT_ID,
        },
        text=True,
        capture_output=True,
        check=True,
    )

    assert "EXPECTED ENV / CONFIG NAMES" in result.stdout
    assert "CURRENT MASKED READINESS STATUS" in result.stdout
    assert "SAFE MANUAL SETUP INSTRUCTIONS" in result.stdout
    assert "telegram_config_readiness_present: True" in result.stdout
    assert RAW_TOKEN not in result.stdout
    assert RAW_CHAT_ID not in result.stdout
    assert "real_telegram_send_called: False" in result.stdout
    assert "real_telegram_message_sent: False" in result.stdout


def test_r318_compatibility_remains_intact(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID})

    assert payload["telegram_token_present"] is True
    assert payload["telegram_chat_id_present"] is True
    assert payload["telegram_config_valid_for_future_send"] is True
    assert payload["real_send_available_for_future"] is True
    assert payload["would_send_real_telegram_now"] is False


def test_inspect_route_returns_readiness_object(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "real-telegram-observation-alert-send-preview",
            "--no-write",
        ],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHONPATH": ".",
            "TELEGRAM_BOT_TOKEN": RAW_TOKEN,
            "TELEGRAM_CHAT_ID": RAW_CHAT_ID,
        },
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["telegram_config_readiness"] is not None
    assert payload["telegram_config_readiness"]["telegram_config_valid_for_future_send"] is True
    assert payload["real_telegram_send_called"] is False
    assert RAW_TOKEN not in rendered
    assert RAW_CHAT_ID not in rendered


def _readiness(payload: dict[str, object]) -> dict[str, object]:
    readiness = payload["telegram_config_readiness"]
    assert isinstance(readiness, dict)
    return readiness


def _preview(
    tmp_path: Path,
    *,
    env: dict[str, str],
    write: bool = False,
    env_file_path: Path | None = None,
) -> dict[str, object]:
    return build_real_telegram_observation_alert_send_preview(
        log_dir=tmp_path,
        env=env,
        env_file_path=env_file_path or tmp_path / "missing-notifications.env",
        alert_preview=_alert(),
        now=NOW,
        write=write,
    )


def _alert() -> dict[str, object]:
    payload = build_multi_lane_observation_alerting_preview(
        log_dir=Path("/tmp/r319-unused"),
        health_panel={
            "event_type": "R314_MULTI_LANE_OBSERVATION_HEALTH_PANEL",
            "health_status": HEALTH_OK,
            "timer_summary": {
                "timer_installed": True,
                "timer_enabled": True,
                "timer_active": True,
                "service_last_exit_status": "0",
                "last_tick_seen": NOW.isoformat(),
                "last_tick_age_seconds": 30,
                "last_tick_recent": True,
            },
            "lane_summary": {
                "baseline_lane": "BTCUSDT|44m|long|ladder_close_50_618",
                "all_primary_contracts_valid": True,
                "all_primary_observation_status_ok": True,
                "current_candidate_seen": False,
                "current_candidate_lane_key": None,
                "matching_observed_lane_keys": [],
                "candidate_freshness_status": "FRESH_TRIGGER_WAIT",
            },
            "final_live_safety": {
                "real_order_forbidden": True,
                "submit_allowed": False,
                "final_command_available": False,
                "armed_lane_key": "BTCUSDT|44m|long|ladder_close_50_618",
            },
            "paper_refresh_summary": {
                "paper_refresh_health_status": "PAPER_REFRESH_HEALTHY",
                "last_failed_tasks": [],
                "degraded_non_critical_accepted": False,
                "fatal": False,
                "healthy": True,
            },
        },
        now=NOW,
        write=False,
    )
    return payload | {
        "alert_required": False,
        "alert_severity": INFO_PREVIEW_NO_SEND,
        "alert_reasons": [],
        "dedup_key": f"r315:r319-test:{INFO_PREVIEW_NO_SEND}:none",
        "telegram_preview_message": "\n".join(
            [
                "R315 Multi-Lane Observation Alert Preview",
                f"severity: {INFO_PREVIEW_NO_SEND}",
                "reason: no actionable alert",
                "telegram_send_called=false",
            ]
        ),
        "operator_console_preview_message": "R315 MULTI-LANE OBSERVATION ALERT PREVIEW",
    }
