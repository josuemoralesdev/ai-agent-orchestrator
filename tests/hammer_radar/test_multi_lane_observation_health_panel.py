from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler import (
    build_multi_lane_dry_run_observation,
)
from src.app.hammer_radar.operator.multi_lane_observation_health_panel import (
    EVENT_TYPE,
    HEALTH_BLOCKED,
    HEALTH_DEGRADED,
    HEALTH_OK,
    LEDGER_FILENAME,
    SAFETY,
    build_multi_lane_observation_health_panel,
    load_multi_lane_observation_health_panel_records,
)
from src.app.hammer_radar.operator.paper_refresh_scheduler import (
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


def test_panel_reads_latest_observation_ledger_row(tmp_path: Path) -> None:
    log_dir = _seed_observation(tmp_path / "logs", now=NOW)

    payload = _build(log_dir, now=NOW + timedelta(seconds=60))
    records = load_multi_lane_observation_health_panel_records(log_dir=log_dir, limit=1)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["timer_summary"]["last_observation_id"]
    assert payload["timer_summary"]["last_tick_seen"] == NOW.isoformat()
    assert (log_dir / LEDGER_FILENAME).exists()
    assert records[0]["event_type"] == EVENT_TYPE


def test_recent_tick_returns_health_ok(tmp_path: Path) -> None:
    log_dir = _seed_observation(tmp_path / "logs", now=NOW)

    payload = _build(log_dir, now=NOW + timedelta(seconds=30))

    assert payload["health_status"] == HEALTH_OK
    assert payload["timer_summary"]["last_tick_age_seconds"] == 30
    assert payload["timer_summary"]["last_tick_recent"] is True


def test_stale_tick_returns_degraded(tmp_path: Path) -> None:
    log_dir = _seed_observation(tmp_path / "logs", now=NOW - timedelta(seconds=600))

    payload = _build(log_dir, now=NOW)

    assert payload["health_status"] == HEALTH_DEGRADED
    assert "stale_observation_tick" in payload["health_blockers"]
    assert payload["timer_summary"]["last_tick_recent"] is False


def test_missing_tick_returns_blocked(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", now=NOW)

    assert payload["health_status"] == HEALTH_BLOCKED
    assert "missing_observation_tick" in payload["health_blockers"]


def test_baseline_primary_and_secondary_lanes_appear(tmp_path: Path) -> None:
    log_dir = _seed_observation(tmp_path / "logs", now=NOW)

    payload = _build(log_dir, now=NOW)
    lanes = payload["lane_summary"]

    assert lanes["baseline_lane"] == BASELINE
    assert lanes["primary_observed_lanes"] == PRIMARY
    assert lanes["secondary_watch_only_lanes"] == SECONDARY
    assert lanes["primary_observed_count"] == 3
    assert lanes["secondary_watch_only_count"] == 4


def test_candidate_visibility_summary_is_compact(tmp_path: Path) -> None:
    log_dir = _seed_observation(
        tmp_path / "logs",
        now=NOW,
        fresh_packet={
            "status": "FRESH_TRIGGER_READY",
            "current_fresh_candidate_exists": True,
            "current_candidate_lane_key": PRIMARY[0],
        },
    )

    payload = _build(log_dir, now=NOW)
    text = json.dumps(payload["lane_summary"])

    assert payload["lane_summary"]["current_candidate_seen"] is True
    assert payload["lane_summary"]["current_candidate_lane_key"] == PRIMARY[0]
    assert PRIMARY[0] in payload["lane_summary"]["matching_observed_lane_keys"]
    assert "lane_packets" not in text


def test_safety_fields_remain_locked(tmp_path: Path) -> None:
    log_dir = _seed_observation(tmp_path / "logs", now=NOW)

    payload = _build(log_dir, now=NOW)

    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected


def test_no_config_or_arming_mutation(tmp_path: Path) -> None:
    risk_path = REPO_ROOT / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = REPO_ROOT / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")
    log_dir = _seed_observation(tmp_path / "logs", now=NOW)

    payload = _build(log_dir, now=NOW)

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert payload["autonomous_arming_state_changed"] is False


def test_no_systemd_mutation(tmp_path: Path) -> None:
    log_dir = _seed_observation(tmp_path / "logs", now=NOW)
    calls: list[list[str]] = []

    payload = build_multi_lane_observation_health_panel(
        log_dir=log_dir,
        now=NOW,
        write=False,
        final_gate_panel=FINAL_GATE_PANEL,
        systemctl_runner=_recording_systemctl(calls),
    )

    assert payload["systemd_unit_mutated"] is False
    assert payload["scheduler_started"] is False
    assert calls
    assert all(call[:2] in [["systemctl", "is-enabled"], ["systemctl", "is-active"], ["systemctl", "show"]] for call in calls)


def test_no_final_command_or_submit(tmp_path: Path) -> None:
    log_dir = _seed_observation(tmp_path / "logs", now=NOW)

    payload = _build(log_dir, now=NOW)

    assert payload["final_live_safety"]["submit_allowed"] is False
    assert payload["final_live_safety"]["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False


def test_no_binance_endpoint_or_secret_surface_called(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = _seed_observation(tmp_path / "logs", now=NOW)
    env_before = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = _build(log_dir, now=NOW)

    assert dict(os.environ) == env_before
    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    submit_test_order.assert_not_called()
    preview_payload.assert_not_called()
    signed_order.assert_not_called()
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["leverage_change_called"] is False
    assert payload["margin_change_called"] is False
    assert payload["secrets_shown"] is False


def test_operator_script_exists_and_avoids_full_json_flood(tmp_path: Path) -> None:
    _seed_observation(tmp_path / "logs", now=NOW)

    result = subprocess.run(
        ["bash", "scripts/hammer_print_r314_multi_lane_observation_health_panel.sh"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "HEALTH STATUS" in result.stdout
    assert "TIMER" in result.stdout
    assert "LAST TICK" in result.stdout
    assert "LANES" in result.stdout
    assert "CANDIDATE VISIBILITY" in result.stdout
    assert "FINAL LIVE SAFETY" in result.stdout
    assert "PAPER REFRESH" in result.stdout
    assert "SAFETY FLAGS" in result.stdout
    assert "RECOMMENDED NEXT PHASE" in result.stdout
    assert "lane_packets" not in result.stdout


def test_inspect_route_works(tmp_path: Path) -> None:
    _seed_observation(tmp_path / "logs", now=NOW)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "multi-lane-observation-health-panel",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["lane_summary"]["baseline_lane"] == BASELINE
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False


def test_paper_refresh_eth_outcome_only_degraded_is_non_fatal(tmp_path: Path) -> None:
    log_dir = _seed_observation(tmp_path / "logs", now=NOW)
    (log_dir / "paper_refresh_runs.ndjson").write_text(
        json.dumps(
            {
                "created_at": NOW.isoformat(),
                "refresh_run_id": "test",
                "failed_tasks": [TASK_ETH_PAPER_OUTCOME],
                "critical_failed_tasks": [],
                "non_critical_failed_tasks": [TASK_ETH_PAPER_OUTCOME],
                "paper_refresh_health_status": PAPER_REFRESH_DEGRADED_NON_CRITICAL,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = _build(log_dir, now=NOW)

    assert payload["paper_refresh_summary"]["paper_refresh_health_status"] == PAPER_REFRESH_DEGRADED_NON_CRITICAL
    assert payload["paper_refresh_summary"]["last_failed_tasks"] == [TASK_ETH_PAPER_OUTCOME]
    assert payload["paper_refresh_summary"]["degraded_non_critical_accepted"] is True
    assert payload["health_status"] == HEALTH_OK


def _seed_observation(
    log_dir: Path,
    *,
    now: datetime,
    fresh_packet: dict[str, object] | None = None,
) -> Path:
    build_multi_lane_dry_run_observation(
        log_dir=log_dir,
        write=True,
        now=now,
        timer_health_packet=TIMER_PACKET,
        fresh_trigger_packet=fresh_packet or FRESH_PACKET,
    )
    return log_dir


def _build(log_dir: Path, *, now: datetime) -> dict[str, object]:
    return build_multi_lane_observation_health_panel(
        log_dir=log_dir,
        now=now,
        write=True,
        systemctl_runner=_systemctl_ok,
        final_gate_panel=FINAL_GATE_PANEL,
    )


def _systemctl_ok(command: list[str] | tuple[str, ...]) -> tuple[int, str]:
    if list(command[:2]) == ["systemctl", "is-enabled"]:
        return 0, "enabled\n"
    if list(command[:2]) == ["systemctl", "is-active"]:
        return 0, "active\n"
    if list(command[:2]) == ["systemctl", "show"]:
        return 0, "Result=success\nExecMainStatus=0\n"
    return 1, "unsupported\n"


def _recording_systemctl(calls: list[list[str]]):
    def runner(command: list[str] | tuple[str, ...]) -> tuple[int, str]:
        calls.append(list(command))
        return _systemctl_ok(command)

    return runner
