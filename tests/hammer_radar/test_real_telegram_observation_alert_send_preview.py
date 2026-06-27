from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_observation_alert_send_gate import (
    SEND_GATE_PREVIEW_READY,
    build_multi_lane_observation_alert_send_gate,
)
from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import (
    INFO_PREVIEW_NO_SEND,
    WARNING_PREVIEW_NO_SEND,
    build_multi_lane_observation_alerting_preview,
)
from src.app.hammer_radar.operator.multi_lane_observation_health_panel import HEALTH_OK
from src.app.hammer_radar.operator.observation_alert_send_gate_operator_drill import (
    DRILL_PASSED,
    build_observation_alert_send_gate_operator_drill,
)
from src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview import (
    EVENT_TYPE,
    FUTURE_CONFIRMATION_PHRASE,
    LEDGER_FILENAME,
    SAFETY,
    build_real_telegram_observation_alert_send_preview,
)

NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_preview_does_not_send(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={})

    assert payload["event_type"] == EVENT_TYPE
    assert payload["send_gate_status"] == SEND_GATE_PREVIEW_READY
    assert payload["real_send_preview_only"] is True
    assert payload["would_send_real_telegram_now"] is False
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False


def test_missing_telegram_token_blocks_future_real_send(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={"TELEGRAM_CHAT_ID": "123456789"})

    assert payload["telegram_token_present"] is False
    assert payload["telegram_chat_id_present"] is True
    assert payload["real_send_available_for_future"] is False
    assert "telegram_token_missing" in payload["telegram_config_blockers"]


def test_missing_chat_id_blocks_future_real_send(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": "1234:abcdefghijklmnopqrstuvwxyz"})

    assert payload["telegram_token_present"] is True
    assert payload["telegram_chat_id_present"] is False
    assert payload["real_send_available_for_future"] is False
    assert "telegram_chat_id_missing" in payload["telegram_config_blockers"]


def test_present_token_chat_id_marks_future_ready_without_printing_secrets(tmp_path: Path) -> None:
    token = "1234:abcdefghijklmnopqrstuvwxyz"
    chat_id = "-1001234567890"
    payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": chat_id})
    text = json.dumps(payload, sort_keys=True)

    assert payload["telegram_token_present"] is True
    assert payload["telegram_chat_id_present"] is True
    assert payload["telegram_config_source_kind"] == "env"
    assert payload["telegram_config_valid_for_future_send"] is True
    assert payload["real_send_available_for_future"] is True
    assert token not in text
    assert chat_id not in text


def test_token_is_masked(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": "abcd12345678wxyz", "TELEGRAM_CHAT_ID": "1234567890"})

    assert payload["telegram_token_preview"] == "abcd...wxyz"
    assert "12345678" not in payload["telegram_token_preview"]


def test_chat_id_is_masked(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": "abcd12345678wxyz", "TELEGRAM_CHAT_ID": "-1001234567890"})

    assert payload["telegram_chat_id_preview"] == "-100...7890"
    assert "123456" not in payload["telegram_chat_id_preview"]


def test_secrets_shown_false(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": "abcd12345678wxyz", "TELEGRAM_CHAT_ID": "-1001234567890"})

    assert payload["secrets_shown"] is False
    assert payload["safety"]["secrets_shown"] is False


def test_healthy_alert_required_false_blocks_send_now_even_with_credentials(tmp_path: Path) -> None:
    payload = _preview(
        tmp_path,
        env={"TELEGRAM_BOT_TOKEN": "abcd12345678wxyz", "TELEGRAM_CHAT_ID": "-1001234567890"},
        alert_preview=_alert(alert_required=False),
    )

    assert payload["alert_required"] is False
    assert payload["real_send_available_for_future"] is True
    assert payload["would_send_real_telegram_now"] is False
    assert payload["healthy_state_send_blocked"] is True
    assert "alert_required_false" in payload["send_blockers"]
    assert payload["recommended_next_operator_move"] == "continue_observation_no_send"


def test_future_confirmation_phrase_is_inactive_and_non_executable(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={})

    assert payload["future_confirmation_phrase_required"] == FUTURE_CONFIRMATION_PHRASE
    assert payload["future_confirmation_phrase_active"] is False
    assert payload["future_confirmation_phrase_executable"] is False


def test_no_heartbeat_policy_enforced(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={}, alert_preview=_alert(alert_required=False))

    assert payload["no_heartbeat_policy_enforced"] is True
    assert payload["healthy_state_send_blocked"] is True
    assert "no_heartbeat_policy_blocks_healthy_send" in payload["send_blockers"]


def test_no_real_telegram_send_called(tmp_path: Path) -> None:
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = _preview(
            tmp_path,
            env={"TELEGRAM_BOT_TOKEN": "abcd12345678wxyz", "TELEGRAM_CHAT_ID": "-1001234567890"},
            alert_preview=_alert(alert_required=True),
        )

    urlopen.assert_not_called()
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False


def test_no_mock_telegram_send_called_by_r318(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={}, alert_preview=_alert(alert_required=True))

    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert payload["source_send_gate_preview"]["telegram_send_called"] is False
    assert payload["source_send_gate_preview"]["telegram_message_sent"] is False


def test_no_config_mutation(tmp_path: Path) -> None:
    risk_path = REPO_ROOT / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = REPO_ROOT / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")

    payload = _preview(tmp_path, env={}, write=True)

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert (tmp_path / LEDGER_FILENAME).exists()


def test_no_arming_mutation(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={})

    assert payload["autonomous_arming_state_changed"] is False
    assert payload["global_live_flags_changed"] is False


def test_no_env_mutation(tmp_path: Path) -> None:
    before = dict(os.environ)
    payload = _preview(tmp_path, env={"TELEGRAM_BOT_TOKEN": "abcd12345678wxyz"})

    assert dict(os.environ) == before
    assert payload["env_written"] is False
    assert payload["env_mutated"] is False


def test_no_systemd_mutation(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={})

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
        payload = _preview(tmp_path, env={}, alert_preview=_alert(alert_required=True))

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    submit_test_order.assert_not_called()
    preview_payload.assert_not_called()
    signed_order.assert_not_called()
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False


def test_no_submit(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={})

    assert payload["submit_allowed"] is False


def test_no_final_command(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={})

    assert payload["final_command_available"] is False


def test_no_binance_endpoint(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={})

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
            "real-telegram-observation-alert-send-preview",
            "--no-write",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["would_send_real_telegram_now"] is False
    assert payload["real_telegram_send_called"] is False


def test_operator_script_exists_and_previews_only(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts/hammer_print_r318_real_telegram_observation_alert_send_preview.sh"
    text = script.read_text(encoding="utf-8")

    assert "--apply" not in text
    assert "--send" not in text
    result = subprocess.run(
        ["bash", str(script.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs"), "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""},
        text=True,
        capture_output=True,
        check=True,
    )

    for section in (
        "TELEGRAM CONFIG READINESS",
        "REAL SEND PREVIEW",
        "ALERT SUMMARY",
        "CONFIRMATION PHRASE PREVIEW",
        "SEND BLOCKERS",
        "NO-HEARTBEAT POLICY",
        "SAFETY FLAGS",
        "RECOMMENDED NEXT PHASE",
    ):
        assert section in result.stdout
    assert "would_send_real_telegram_now: False" in result.stdout
    assert "real_telegram_send_called: False" in result.stdout
    assert "sendMessage" not in result.stdout


def test_r317_r316_r315_r314_compatibility_remains_intact(tmp_path: Path) -> None:
    r318 = _preview(tmp_path, env={}, alert_preview=_alert(alert_required=True))
    r316 = build_multi_lane_observation_alert_send_gate(
        log_dir=tmp_path,
        alert_preview=_alert(alert_required=True),
        no_write=True,
        write=False,
        now=NOW,
    )
    r317 = build_observation_alert_send_gate_operator_drill(log_dir=tmp_path, scenario="all", no_write=True, now=NOW)

    assert r318["source_alert_preview"]["event_type"] == "R315_MULTI_LANE_OBSERVATION_ALERTING_PREVIEW"
    assert r318["source_alert_preview"]["source_event_type"] == "R314_MULTI_LANE_OBSERVATION_HEALTH_PANEL"
    assert r316["send_gate_status"] == SEND_GATE_PREVIEW_READY
    assert r317["drill_status"] == DRILL_PASSED
    assert r317["no_real_telegram_passed"] is True


def test_required_safety_fields_are_present(tmp_path: Path) -> None:
    payload = _preview(tmp_path, env={})

    for key, expected in SAFETY.items():
        assert payload[key] == expected
        assert payload["safety"][key] == expected


def _preview(
    tmp_path: Path,
    *,
    env: dict[str, str],
    alert_preview: dict[str, object] | None = None,
    write: bool = False,
) -> dict[str, object]:
    return build_real_telegram_observation_alert_send_preview(
        log_dir=tmp_path,
        env=env,
        env_file_path=tmp_path / "missing-notifications.env",
        alert_preview=alert_preview or _alert(alert_required=False),
        now=NOW,
        write=write,
    )


def _alert(*, alert_required: bool) -> dict[str, object]:
    severity = WARNING_PREVIEW_NO_SEND if alert_required else INFO_PREVIEW_NO_SEND
    reasons = ["stale_observation_tick"] if alert_required else []
    return build_multi_lane_observation_alerting_preview(
        log_dir=Path("/tmp/r318-unused"),
        health_panel=_health(
            health_status=("MULTI_LANE_OBSERVATION_HEALTH_DEGRADED" if alert_required else HEALTH_OK),
            timer_summary={"last_tick_recent": False, "last_tick_age_seconds": 600} if alert_required else {},
        ),
        now=NOW,
        write=False,
    ) | {
        "alert_required": alert_required,
        "alert_severity": severity,
        "alert_reasons": reasons,
        "dedup_key": f"r315:r318-test:{severity}:{','.join(reasons) or 'none'}",
        "telegram_preview_message": "\n".join(
            [
                "R315 Multi-Lane Observation Alert Preview",
                f"severity: {severity}",
                f"reason: {', '.join(reasons) if reasons else 'no actionable alert'}",
                "telegram_send_called=false",
            ]
        ),
        "operator_console_preview_message": "R315 MULTI-LANE OBSERVATION ALERT PREVIEW",
    }


def _health(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
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
    }
    from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import SAFETY as R315_SAFETY

    payload.update({"safety": dict(R315_SAFETY), **R315_SAFETY})
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(payload.get(key), dict):
            nested = deepcopy(payload[key])
            nested.update(value)
            payload[key] = nested
        else:
            payload[key] = value
    return payload
