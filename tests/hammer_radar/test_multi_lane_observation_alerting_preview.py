from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler import (
    build_multi_lane_dry_run_observation,
)
from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import (
    CRITICAL_PREVIEW_NO_SEND,
    EVENT_TYPE,
    INFO_PREVIEW_NO_SEND,
    LEDGER_FILENAME,
    SAFETY,
    WARNING_PREVIEW_NO_SEND,
    build_dedup_key,
    build_multi_lane_observation_alerting_preview,
)
from src.app.hammer_radar.operator.multi_lane_observation_health_panel import (
    HEALTH_BLOCKED,
    HEALTH_OK,
    build_multi_lane_observation_health_panel,
)
from src.app.hammer_radar.operator.paper_refresh_scheduler import (
    PAPER_REFRESH_CRITICAL_FAILURE,
    PAPER_REFRESH_DEGRADED_NON_CRITICAL,
    TASK_ETH_PAPER_OUTCOME,
)

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
BASELINE = "BTCUSDT|44m|long|ladder_close_50_618"
PRIMARY = [
    "BTCUSDT|44m|short|ladder_382_50_618",
    "BTCUSDT|44m|short|ladder_close_50_618",
    "BTCUSDT|55m|long|ladder_close_50_618",
]
SECONDARY = [
    "BTCUSDT|44m|short|ladder_22_44_22",
    "BTCUSDT|44m|long|ladder_382_50_618",
    "BTCUSDT|55m|long|market_close",
    "BTCUSDT|88m|long|ladder_382_50_618",
]
TIMER_PACKET = {"status": "TIMER_HEALTH_ACTIVE", "timer_active": True, "blockers": []}
FRESH_PACKET = {
    "status": "FRESH_TRIGGER_WAIT",
    "current_fresh_candidate_exists": False,
    "current_candidate_lane_key": None,
}
FINAL_GATE_PANEL = {
    "status": "FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED",
    "blockers": ["live_execution_disabled"],
    "real_order_forbidden": True,
    "submit_allowed": False,
    "final_command_available": False,
    "exact_lane_armed_state": {"armed_lane_key": BASELINE},
    "readiness_matrix": {
        "timer_active": True,
        "timer_health_status": "TIMER_HEALTH_ACTIVE",
    },
}
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_health_ok_produces_no_alert(tmp_path: Path) -> None:
    payload = _preview(tmp_path, _health())

    assert payload["event_type"] == EVENT_TYPE
    assert payload["alert_required"] is False
    assert payload["alert_severity"] == INFO_PREVIEW_NO_SEND
    assert payload["alert_reasons"] == []
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False


def test_stale_tick_produces_warning_preview(tmp_path: Path) -> None:
    health = _health(
        timer_summary={"last_tick_recent": False, "last_tick_age_seconds": 600},
        health_status="MULTI_LANE_OBSERVATION_HEALTH_DEGRADED",
    )

    payload = _preview(tmp_path, health)

    assert payload["alert_required"] is True
    assert payload["alert_severity"] == WARNING_PREVIEW_NO_SEND
    assert "stale_observation_tick" in payload["alert_reasons"]


def test_timer_inactive_produces_alert(tmp_path: Path) -> None:
    payload = _preview(tmp_path, _health(timer_summary={"timer_active": False}))

    assert payload["alert_required"] is True
    assert payload["alert_severity"] == WARNING_PREVIEW_NO_SEND
    assert "timer_not_active" in payload["alert_reasons"]


def test_primary_contract_invalid_produces_critical_alert(tmp_path: Path) -> None:
    payload = _preview(
        tmp_path,
        _health(
            health_status=HEALTH_BLOCKED,
            lane_summary={"all_primary_contracts_valid": False},
        ),
    )

    assert payload["alert_severity"] == CRITICAL_PREVIEW_NO_SEND
    assert "primary_contract_invalid" in payload["alert_reasons"]


def test_final_safety_violation_produces_critical_alert(tmp_path: Path) -> None:
    payload = _preview(
        tmp_path,
        _health(
            health_status=HEALTH_BLOCKED,
            final_live_safety={"submit_allowed": True, "final_command_available": True},
        ),
    )

    assert payload["alert_severity"] == CRITICAL_PREVIEW_NO_SEND
    assert "final_live_safety_submit_allowed" in payload["alert_reasons"]
    assert "final_live_safety_final_command_available" in payload["alert_reasons"]


def test_paper_refresh_eth_outcome_only_degradation_does_not_alert(tmp_path: Path) -> None:
    payload = _preview(
        tmp_path,
        _health(
            paper_refresh_summary={
                "paper_refresh_health_status": PAPER_REFRESH_DEGRADED_NON_CRITICAL,
                "last_failed_tasks": [TASK_ETH_PAPER_OUTCOME],
                "degraded_non_critical_accepted": True,
            },
        ),
    )

    assert payload["alert_required"] is False
    assert payload["alert_severity"] == INFO_PREVIEW_NO_SEND


def test_paper_refresh_critical_failure_alerts(tmp_path: Path) -> None:
    payload = _preview(
        tmp_path,
        _health(
            health_status=HEALTH_BLOCKED,
            paper_refresh_summary={
                "paper_refresh_health_status": PAPER_REFRESH_CRITICAL_FAILURE,
                "last_failed_tasks": ["paper_refresh"],
                "fatal": True,
            },
        ),
    )

    assert payload["alert_severity"] == CRITICAL_PREVIEW_NO_SEND
    assert "paper_refresh_critical_failure" in payload["alert_reasons"]


def test_dedup_key_is_stable() -> None:
    first = build_dedup_key(
        severity=WARNING_PREVIEW_NO_SEND,
        reasons=["timer_not_active", "stale_observation_tick"],
        affected_surface=["timer"],
    )
    second = build_dedup_key(
        severity=WARNING_PREVIEW_NO_SEND,
        reasons=["stale_observation_tick", "timer_not_active"],
        affected_surface=["timer"],
    )

    assert first == second
    assert first.startswith("r315:")


def test_rate_limit_preview_detects_recent_duplicate_ledger_entry(tmp_path: Path) -> None:
    health = _health(
        timer_summary={"last_tick_recent": False, "last_tick_age_seconds": 600},
        health_status="MULTI_LANE_OBSERVATION_HEALTH_DEGRADED",
    )

    first = build_multi_lane_observation_alerting_preview(
        log_dir=tmp_path,
        health_panel=health,
        now=NOW,
        write=True,
    )
    second = build_multi_lane_observation_alerting_preview(
        log_dir=tmp_path,
        health_panel=health,
        now=NOW + timedelta(seconds=60),
        write=False,
    )

    assert (tmp_path / LEDGER_FILENAME).exists()
    assert first["dedup_key"] == second["dedup_key"]
    assert second["would_suppress_duplicate"] is True
    assert second["previous_matching_preview_generated_at"] == NOW.isoformat()


def test_telegram_send_flags_remain_false(tmp_path: Path) -> None:
    payload = _preview(tmp_path, _health(timer_summary={"timer_enabled": False}))

    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert "telegram_send_called=false" in payload["telegram_preview_message"]


def test_no_config_mutation(tmp_path: Path) -> None:
    risk_path = REPO_ROOT / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = REPO_ROOT / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")

    payload = _preview(tmp_path, _health())

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False


def test_no_arming_mutation(tmp_path: Path) -> None:
    payload = _preview(tmp_path, _health())

    assert payload["autonomous_arming_state_changed"] is False
    assert payload["global_live_flags_changed"] is False


def test_no_systemd_mutation(tmp_path: Path) -> None:
    payload = _preview(tmp_path, _health())

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
        payload = _preview(tmp_path, _health())

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    submit_test_order.assert_not_called()
    preview_payload.assert_not_called()
    signed_order.assert_not_called()
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False


def test_no_submit(tmp_path: Path) -> None:
    payload = _preview(tmp_path, _health())

    assert payload["submit_allowed"] is False


def test_no_final_command(tmp_path: Path) -> None:
    payload = _preview(tmp_path, _health())

    assert payload["final_command_available"] is False


def test_no_binance_endpoint(tmp_path: Path) -> None:
    payload = _preview(tmp_path, _health())

    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["leverage_change_called"] is False
    assert payload["margin_change_called"] is False


def test_inspect_route_works(tmp_path: Path) -> None:
    _seed_observation(tmp_path / "logs", now=NOW)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "multi-lane-observation-alerting-preview",
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
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False


def test_operator_script_exists_and_prints_preview_only(tmp_path: Path) -> None:
    _seed_observation(tmp_path / "logs", now=NOW)

    result = subprocess.run(
        ["bash", "scripts/hammer_print_r315_multi_lane_observation_alerting_preview.sh"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "ALERT STATUS" in result.stdout
    assert "SEVERITY" in result.stdout
    assert "REASONS" in result.stdout
    assert "DEDUP/RATE LIMIT PREVIEW" in result.stdout
    assert "TELEGRAM PREVIEW MESSAGE" in result.stdout
    assert "OPERATOR CONSOLE PREVIEW MESSAGE" in result.stdout
    assert "SAFETY FLAGS" in result.stdout
    assert "telegram_send_called: False" in result.stdout
    assert "telegram_message_sent: False" in result.stdout
    assert "sendMessage" not in result.stdout


def test_r314_health_panel_compatibility_remains_intact(tmp_path: Path) -> None:
    log_dir = _seed_observation(tmp_path / "logs", now=NOW)
    health = build_multi_lane_observation_health_panel(
        log_dir=log_dir,
        now=NOW + timedelta(seconds=30),
        write=False,
        systemctl_runner=_systemctl_ok,
        final_gate_panel=FINAL_GATE_PANEL,
    )

    payload = build_multi_lane_observation_alerting_preview(
        log_dir=log_dir,
        health_panel=health,
        now=NOW + timedelta(seconds=30),
        write=False,
    )

    assert health["health_status"] == HEALTH_OK
    assert health["lane_summary"]["primary_observed_lanes"] == PRIMARY
    assert health["lane_summary"]["secondary_watch_only_lanes"] == SECONDARY
    assert payload["source_event_type"] == "R314_MULTI_LANE_OBSERVATION_HEALTH_PANEL"
    assert payload["source_health_status"] == HEALTH_OK


def test_required_safety_fields_are_present(tmp_path: Path) -> None:
    payload = _preview(tmp_path, _health())

    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected


def _preview(tmp_path: Path, health: dict[str, object]) -> dict[str, object]:
    return build_multi_lane_observation_alerting_preview(
        log_dir=tmp_path,
        health_panel=health,
        now=NOW,
        write=False,
    )


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
            "baseline_lane": BASELINE,
            "primary_observed_lanes": PRIMARY,
            "secondary_watch_only_lanes": SECONDARY,
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
            "armed_lane_key": BASELINE,
        },
        "paper_refresh_summary": {
            "paper_refresh_health_status": "PAPER_REFRESH_HEALTHY",
            "last_failed_tasks": [],
            "degraded_non_critical_accepted": False,
            "fatal": False,
            "healthy": True,
        },
        "safety": dict(SAFETY),
        **SAFETY,
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(payload.get(key), dict):
            nested = deepcopy(payload[key])
            nested.update(value)
            payload[key] = nested
        else:
            payload[key] = value
    return payload


def _seed_observation(log_dir: Path, *, now: datetime) -> Path:
    build_multi_lane_dry_run_observation(
        log_dir=log_dir,
        write=True,
        now=now,
        timer_health_packet=TIMER_PACKET,
        fresh_trigger_packet=FRESH_PACKET,
    )
    return log_dir


def _systemctl_ok(command: list[str] | tuple[str, ...]) -> tuple[int, str]:
    if list(command[:2]) == ["systemctl", "is-enabled"]:
        return 0, "enabled\n"
    if list(command[:2]) == ["systemctl", "is-active"]:
        return 0, "active\n"
    if list(command[:2]) == ["systemctl", "show"]:
        return 0, "Result=success\nExecMainStatus=0\n"
    return 1, "unsupported\n"
