from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_observation_alert_send_gate import (
    CONFIRMATION_PHRASE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    SAFETY,
    SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED,
    SEND_GATE_BLOCKED_NO_ALERT_REQUIRED,
    SEND_GATE_BLOCKED_RATE_LIMIT,
    SEND_GATE_MOCK_SENT,
    SEND_GATE_PREVIEW_READY,
    SEND_GATE_REAL_SEND_AVAILABLE_NOT_USED_IN_CODEX,
    build_multi_lane_observation_alert_send_gate,
)
from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import (
    CRITICAL_PREVIEW_NO_SEND,
    INFO_PREVIEW_NO_SEND,
    WARNING_PREVIEW_NO_SEND,
    build_multi_lane_observation_alerting_preview,
)
from src.app.hammer_radar.operator.multi_lane_observation_health_panel import HEALTH_OK

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_preview_does_not_send(tmp_path: Path) -> None:
    payload = _gate(tmp_path, _preview(alert_required=True))

    assert payload["event_type"] == EVENT_TYPE
    assert payload["send_gate_status"] == SEND_GATE_PREVIEW_READY
    assert payload["send_gate_preview_only"] is True
    assert payload["apply_requested"] is False
    assert payload["confirmation_phrase_matched"] is False
    assert payload["telegram_sender_mode"] == "mock"
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False


def test_healthy_r315_alert_required_false_blocks_apply(tmp_path: Path) -> None:
    payload = _gate(
        tmp_path,
        _preview(alert_required=False, severity=INFO_PREVIEW_NO_SEND, reasons=[]),
        apply=True,
        confirmation=CONFIRMATION_PHRASE,
    )

    assert payload["send_gate_status"] == SEND_GATE_BLOCKED_NO_ALERT_REQUIRED
    assert "alert_required_false" in payload["send_blockers"]
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False


def test_missing_confirmation_blocks_apply(tmp_path: Path) -> None:
    payload = _gate(tmp_path, _preview(alert_required=True), apply=True)

    assert payload["send_gate_status"] == SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED
    assert "confirmation_phrase_required" in payload["send_blockers"]
    assert payload["confirmation_phrase_matched"] is False
    assert payload["telegram_send_called"] is False


def test_wrong_confirmation_blocks_apply(tmp_path: Path) -> None:
    payload = _gate(tmp_path, _preview(alert_required=True), apply=True, confirmation="SEND IT")

    assert payload["send_gate_status"] == SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED
    assert "confirmation_phrase_required" in payload["send_blockers"]
    assert payload["confirmation_phrase_matched"] is False
    assert payload["telegram_message_sent"] is False


def test_mock_apply_with_alert_required_records_mock_send_only(tmp_path: Path) -> None:
    payload = _gate(
        tmp_path,
        _preview(alert_required=True),
        apply=True,
        confirmation=CONFIRMATION_PHRASE,
        write=True,
    )

    assert payload["send_gate_status"] == SEND_GATE_MOCK_SENT
    assert payload["telegram_send_called"] is True
    assert payload["telegram_message_sent"] is True
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False
    assert (tmp_path / LEDGER_FILENAME).exists()


def test_info_no_action_preview_never_sends(tmp_path: Path) -> None:
    payload = _gate(
        tmp_path,
        _preview(alert_required=False, severity=INFO_PREVIEW_NO_SEND, reasons=[]),
        apply=True,
        confirmation=CONFIRMATION_PHRASE,
    )

    assert payload["send_gate_status"] == SEND_GATE_BLOCKED_NO_ALERT_REQUIRED
    assert "info_preview_no_action_never_sends" in payload["send_blockers"]
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False


def test_dedup_rate_limit_blocks_non_critical_duplicate_send(tmp_path: Path) -> None:
    preview = _preview(alert_required=True, severity=WARNING_PREVIEW_NO_SEND, reasons=["stale_observation_tick"])
    first = _gate(tmp_path, preview, apply=True, confirmation=CONFIRMATION_PHRASE, write=True)
    second = _gate(
        tmp_path,
        preview,
        apply=True,
        confirmation=CONFIRMATION_PHRASE,
        now=NOW + timedelta(seconds=60),
    )

    assert first["send_gate_status"] == SEND_GATE_MOCK_SENT
    assert second["send_gate_status"] == SEND_GATE_BLOCKED_RATE_LIMIT
    assert second["would_suppress_duplicate"] is True
    assert "rate_limit_duplicate_non_critical" in second["send_blockers"]
    assert second["telegram_message_sent"] is False


def test_critical_repeat_reports_repeat_behavior_clearly(tmp_path: Path) -> None:
    preview = _preview(alert_required=True, severity=CRITICAL_PREVIEW_NO_SEND, reasons=["health_status_blocked"])
    first = _gate(tmp_path, preview, apply=True, confirmation=CONFIRMATION_PHRASE, write=True)
    second = _gate(
        tmp_path,
        preview,
        apply=True,
        confirmation=CONFIRMATION_PHRASE,
        now=NOW + timedelta(seconds=60),
    )

    assert first["send_gate_status"] == SEND_GATE_MOCK_SENT
    assert second["send_gate_status"] == SEND_GATE_MOCK_SENT
    assert second["would_repeat_critical"] is True
    assert second["would_suppress_duplicate"] is False
    assert second["telegram_message_sent"] is True


def test_real_sender_mode_is_not_executed_in_tests(tmp_path: Path) -> None:
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = _gate(
            tmp_path,
            _preview(alert_required=True),
            apply=True,
            confirmation=CONFIRMATION_PHRASE,
            telegram_sender_mode="real",
        )

    urlopen.assert_not_called()
    assert payload["send_gate_status"] == SEND_GATE_REAL_SEND_AVAILABLE_NOT_USED_IN_CODEX
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False


def test_telegram_send_flags_remain_false_in_preview(tmp_path: Path) -> None:
    payload = _gate(tmp_path, _preview(alert_required=True))

    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False


def test_real_telegram_send_called_false_in_all_codex_validation_paths(tmp_path: Path) -> None:
    paths = [
        _gate(tmp_path, _preview(alert_required=True)),
        _gate(tmp_path, _preview(alert_required=True), apply=True, confirmation="wrong"),
        _gate(tmp_path, _preview(alert_required=True), apply=True, confirmation=CONFIRMATION_PHRASE),
        _gate(
            tmp_path,
            _preview(alert_required=True),
            apply=True,
            confirmation=CONFIRMATION_PHRASE,
            telegram_sender_mode="real",
        ),
    ]

    assert all(payload["real_telegram_send_called"] is False for payload in paths)
    assert all(payload["real_telegram_message_sent"] is False for payload in paths)


def test_no_config_mutation(tmp_path: Path) -> None:
    risk_path = REPO_ROOT / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = REPO_ROOT / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")

    payload = _gate(tmp_path, _preview(alert_required=True), apply=True, confirmation=CONFIRMATION_PHRASE)

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False


def test_no_arming_mutation(tmp_path: Path) -> None:
    payload = _gate(tmp_path, _preview(alert_required=True))

    assert payload["autonomous_arming_state_changed"] is False
    assert payload["global_live_flags_changed"] is False


def test_no_systemd_mutation(tmp_path: Path) -> None:
    payload = _gate(tmp_path, _preview(alert_required=True))

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
        payload = _gate(tmp_path, _preview(alert_required=True), apply=True, confirmation=CONFIRMATION_PHRASE)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    submit_test_order.assert_not_called()
    preview_payload.assert_not_called()
    signed_order.assert_not_called()
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False


def test_no_submit(tmp_path: Path) -> None:
    payload = _gate(tmp_path, _preview(alert_required=True))

    assert payload["submit_allowed"] is False


def test_no_final_command(tmp_path: Path) -> None:
    payload = _gate(tmp_path, _preview(alert_required=True))

    assert payload["final_command_available"] is False


def test_no_binance_endpoint(tmp_path: Path) -> None:
    payload = _gate(tmp_path, _preview(alert_required=True))

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
            "multi-lane-observation-alert-send-gate",
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
    assert payload["apply_requested"] is False
    assert payload["telegram_send_called"] is False
    assert payload["real_telegram_send_called"] is False


def test_operator_script_exists_and_previews_only(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts/hammer_print_r316_observation_alert_send_gate.sh"
    text = script.read_text(encoding="utf-8")

    assert "--apply" not in text
    result = subprocess.run(
        ["bash", str(script.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "SEND GATE STATUS" in result.stdout
    assert "ALERT SUMMARY" in result.stdout
    assert "CONFIRMATION STATUS" in result.stdout
    assert "SEND BLOCKERS" in result.stdout
    assert "TELEGRAM PREVIEW MESSAGE" in result.stdout
    assert "MOCK/REAL SEND FLAGS" in result.stdout
    assert "SAFETY FLAGS" in result.stdout
    assert "RECOMMENDED NEXT PHASE" in result.stdout
    assert "telegram_send_called: False" in result.stdout
    assert "real_telegram_send_called: False" in result.stdout
    assert "sendMessage" not in result.stdout


def test_r315_compatibility_remains_intact(tmp_path: Path) -> None:
    preview = build_multi_lane_observation_alerting_preview(
        log_dir=tmp_path,
        health_panel=_health(),
        now=NOW,
        write=False,
    )
    payload = _gate(tmp_path, preview)

    assert preview["source_event_type"] == "R314_MULTI_LANE_OBSERVATION_HEALTH_PANEL"
    assert preview["source_health_status"] == HEALTH_OK
    assert payload["source_alert_preview"]["event_type"] == "R315_MULTI_LANE_OBSERVATION_ALERTING_PREVIEW"
    assert payload["telegram_send_called"] is False


def test_required_safety_fields_are_present(tmp_path: Path) -> None:
    payload = _gate(tmp_path, _preview(alert_required=True))

    for key, expected in SAFETY.items():
        assert payload[key] == expected
        assert payload["safety"][key] == expected


def _gate(
    tmp_path: Path,
    preview: dict[str, object],
    *,
    apply: bool = False,
    confirmation: str | None = None,
    telegram_sender_mode: str = "mock",
    now: datetime = NOW,
    write: bool = False,
) -> dict[str, object]:
    return build_multi_lane_observation_alert_send_gate(
        log_dir=tmp_path,
        alert_preview=preview,
        apply=apply,
        confirmation=confirmation,
        telegram_sender_mode=telegram_sender_mode,
        now=now,
        write=write,
    )


def _preview(
    *,
    alert_required: bool,
    severity: str = WARNING_PREVIEW_NO_SEND,
    reasons: list[str] | None = None,
) -> dict[str, object]:
    reasons = ["stale_observation_tick"] if reasons is None and alert_required else (reasons or [])
    return build_multi_lane_observation_alerting_preview(
        log_dir=Path("/tmp/r316-unused"),
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
        "dedup_key": f"r315:test:{severity}:{','.join(reasons) or 'none'}",
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
