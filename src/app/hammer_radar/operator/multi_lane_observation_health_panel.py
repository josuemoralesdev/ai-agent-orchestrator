"""R314 multi-lane observation health panel.

This panel is read-only apart from its own R314 health ledger. It summarizes
R310/R313 observation health without installing units, mutating config, arming
lanes, creating final commands, submitting orders, or calling Binance endpoints.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler import (
    BASELINE_CURRENT_FIRST_TINY_LIVE,
    LEDGER_FILENAME as OBSERVATION_LEDGER_FILENAME,
    PRIMARY_DRY_RUN_OBSERVATION,
    SECONDARY_WATCH_ONLY_VISIBLE,
    load_multi_lane_dry_run_observation_records,
)
from src.app.hammer_radar.operator.multi_lane_dry_run_timer_unit_preview import (
    SERVICE_NAME,
    TIMER_NAME,
)
from src.app.hammer_radar.operator.paper_refresh_scheduler import (
    PAPER_REFRESH_CRITICAL_FAILURE,
    PAPER_REFRESH_DEGRADED_NON_CRITICAL,
    PAPER_REFRESH_HEALTHY,
    SERVICE_NAME as PAPER_REFRESH_SERVICE_NAME,
    TASK_ETH_PAPER_OUTCOME,
    load_refresh_runs,
)
from src.app.hammer_radar.operator.tiny_live_final_console import (
    build_final_tiny_live_authorization_gate_panel,
)

EVENT_TYPE = "R314_MULTI_LANE_OBSERVATION_HEALTH_PANEL"
CREATED_BY_PHASE = "R314_MULTI_LANE_OBSERVATION_HEALTH_PANEL"
LEDGER_FILENAME = "multi_lane_observation_health_panel.ndjson"

HEALTH_OK = "MULTI_LANE_OBSERVATION_HEALTH_OK"
HEALTH_DEGRADED = "MULTI_LANE_OBSERVATION_HEALTH_DEGRADED"
HEALTH_BLOCKED = "MULTI_LANE_OBSERVATION_HEALTH_BLOCKED"

RECOMMENDED_R315_ALERTING = "R315 Multi-Lane Observation Alerting Preview"
RECOMMENDED_R315_REPAIR = "R315 Health Panel Repair"

SAFETY = {
    "live_execution_enabled": False,
    "allow_live_orders": False,
    "global_kill_switch": True,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "submit_allowed": False,
    "final_command_available": False,
    "real_order_forbidden": True,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
    "autonomous_arming_state_changed": False,
    "global_live_flags_changed": False,
    "risk_contract_config_mutated": False,
    "config_written": False,
    "env_written": False,
    "env_mutated": False,
    "systemd_unit_mutated": False,
    "scheduler_started": False,
}

SystemctlRunner = Callable[[Sequence[str]], tuple[int, str]]


def build_multi_lane_observation_health_panel(
    *,
    log_dir: str | Path | None = None,
    max_age_seconds: int = 180,
    write: bool = True,
    now: datetime | None = None,
    systemctl_runner: SystemctlRunner | None = None,
    final_gate_panel: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    latest_observation = _latest_observation(resolved_log_dir)
    timer_summary = _timer_summary(
        log_dir=resolved_log_dir,
        observation=latest_observation,
        now=generated_at,
        max_age_seconds=max_age_seconds,
        systemctl_runner=systemctl_runner,
    )
    lane_summary = _lane_summary(latest_observation)
    final_live_safety = _final_live_safety(
        log_dir=resolved_log_dir,
        final_gate_panel=final_gate_panel,
    )
    paper_refresh_summary = _paper_refresh_summary(
        log_dir=resolved_log_dir,
        systemctl_runner=systemctl_runner,
    )
    safety = dict(SAFETY)

    health_blockers = _health_blockers(
        timer_summary=timer_summary,
        lane_summary=lane_summary,
        final_live_safety=final_live_safety,
        paper_refresh_summary=paper_refresh_summary,
        safety=safety,
    )
    health_status = _health_status(health_blockers)
    recommended = (
        "continue_observation_and_prepare_alerting_preview"
        if health_status == HEALTH_OK
        else "repair_health_panel_blockers_before_alerting"
    )
    recommended_r315 = (
        RECOMMENDED_R315_ALERTING if health_status == HEALTH_OK else RECOMMENDED_R315_REPAIR
    )
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "panel_id": f"r314_multi_lane_observation_health_panel_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        "health_status": health_status,
        "health_blockers": health_blockers,
        "recommended_next_operator_move": recommended,
        "recommended_r315_path": recommended_r315,
        "timer_summary": timer_summary,
        "lane_summary": lane_summary,
        "final_live_safety": final_live_safety,
        "paper_refresh_summary": paper_refresh_summary,
        "safety": safety,
        **safety,
    }
    safe_payload = _sanitize(payload)
    if write:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def load_multi_lane_observation_health_panel_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def append_record(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = records_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_health_panel_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def format_health_panel_text(payload: Mapping[str, Any]) -> str:
    timer = _mapping(payload.get("timer_summary"))
    lanes = _mapping(payload.get("lane_summary"))
    final = _mapping(payload.get("final_live_safety"))
    paper = _mapping(payload.get("paper_refresh_summary"))
    lines = [
        "R314 MULTI-LANE OBSERVATION HEALTH PANEL",
        "",
        "HEALTH STATUS",
        f"health_status: {payload.get('health_status')}",
        f"health_blockers: {_join(payload.get('health_blockers'))}",
        f"recommended_next_operator_move: {payload.get('recommended_next_operator_move')}",
        "",
        "TIMER",
        f"service_name: {timer.get('service_name')}",
        f"timer_name: {timer.get('timer_name')}",
        f"timer_installed: {timer.get('timer_installed')}",
        f"timer_enabled: {timer.get('timer_enabled')}",
        f"timer_active: {timer.get('timer_active')}",
        f"service_last_exit_status: {timer.get('service_last_exit_status')}",
        "",
        "LAST TICK",
        f"last_tick_seen: {timer.get('last_tick_seen')}",
        f"last_tick_age_seconds: {timer.get('last_tick_age_seconds')}",
        f"last_tick_recent: {timer.get('last_tick_recent')}",
        f"last_observation_id: {timer.get('last_observation_id')}",
        f"observation_ledger_path: {timer.get('observation_ledger_path')}",
        "",
        "LANES",
        f"baseline_lane: {lanes.get('baseline_lane')}",
        f"primary_observed_count: {lanes.get('primary_observed_count')}",
        f"primary_observed_lanes: {_join(lanes.get('primary_observed_lanes'))}",
        f"secondary_watch_only_count: {lanes.get('secondary_watch_only_count')}",
        f"secondary_watch_only_lanes: {_join(lanes.get('secondary_watch_only_lanes'))}",
        f"all_primary_contracts_valid: {lanes.get('all_primary_contracts_valid')}",
        f"all_primary_observation_status_ok: {lanes.get('all_primary_observation_status_ok')}",
        "",
        "CANDIDATE VISIBILITY",
        f"current_candidate_seen: {lanes.get('current_candidate_seen')}",
        f"current_candidate_lane_key: {lanes.get('current_candidate_lane_key')}",
        f"matching_observed_lane_keys: {_join(lanes.get('matching_observed_lane_keys'))}",
        f"candidate_freshness_status: {lanes.get('candidate_freshness_status')}",
        "",
        "FINAL LIVE SAFETY",
        f"final_gate_status: {final.get('final_gate_status')}",
        f"final_gate_blockers: {_join(final.get('final_gate_blockers'))}",
        f"real_order_forbidden: {final.get('real_order_forbidden')}",
        f"submit_allowed: {final.get('submit_allowed')}",
        f"final_command_available: {final.get('final_command_available')}",
        f"armed_lane_key: {final.get('armed_lane_key')}",
        f"timer_health_status: {final.get('timer_health_status')}",
        "",
        "PAPER REFRESH",
        f"paper_refresh_health_status: {paper.get('paper_refresh_health_status')}",
        f"last_failed_tasks: {_join(paper.get('last_failed_tasks'))}",
        f"service_active: {paper.get('service_active')}",
        f"degraded_non_critical_accepted: {paper.get('degraded_non_critical_accepted')}",
        "",
        "SAFETY FLAGS",
    ]
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(["", "RECOMMENDED NEXT PHASE", str(payload.get("recommended_r315_path"))])
    return "\n".join(lines)


def _latest_observation(log_dir: Path) -> dict[str, Any] | None:
    records = load_multi_lane_dry_run_observation_records(log_dir=log_dir, limit=1)
    return records[0] if records else None


def _timer_summary(
    *,
    log_dir: Path,
    observation: Mapping[str, Any] | None,
    now: datetime,
    max_age_seconds: int,
    systemctl_runner: SystemctlRunner | None,
) -> dict[str, Any]:
    installed_state = _systemctl(["systemctl", "is-enabled", TIMER_NAME], runner=systemctl_runner)
    active_state = _systemctl(["systemctl", "is-active", TIMER_NAME], runner=systemctl_runner)
    service_status = _systemctl_show(SERVICE_NAME, runner=systemctl_runner)
    latest_install_records = read_recent_ndjson_records(log_dir / "multi_lane_dry_run_timer_install_gate.ndjson", limit=1)
    latest_install = latest_install_records[0] if latest_install_records else {}
    installed_from_ledger = bool(
        latest_install.get("systemd_timer_installed") is True
        or latest_install.get("install_gate_status") == "INSTALL_GATE_WRITTEN_TEMP_OR_REAL"
    )
    last_tick_seen = str((observation or {}).get("generated_at") or "") or None
    last_tick_age = _age_seconds(last_tick_seen, now=now)
    last_tick_recent = last_tick_age is not None and last_tick_age <= max(0, int(max_age_seconds))
    return {
        "service_name": SERVICE_NAME,
        "timer_name": TIMER_NAME,
        "timer_installed": installed_from_ledger or installed_state["status"] in {"enabled", "disabled", "static"},
        "timer_enabled": installed_state["status"] == "enabled",
        "timer_active": active_state["status"] == "active",
        "service_last_exit_status": service_status.get("ExecMainStatus") or service_status.get("Result"),
        "last_tick_seen": last_tick_seen,
        "last_tick_age_seconds": last_tick_age,
        "last_tick_recent": last_tick_recent,
        "last_observation_id": (observation or {}).get("observation_id"),
        "observation_ledger_path": str(log_dir / OBSERVATION_LEDGER_FILENAME),
        "systemctl_read_only": True,
        "systemctl_errors": _compact_errors([installed_state, active_state, service_status]),
    }


def _lane_summary(observation: Mapping[str, Any] | None) -> dict[str, Any]:
    if not observation:
        return {
            "baseline_lane": None,
            "primary_observed_lanes": [],
            "secondary_watch_only_lanes": [],
            "primary_observed_count": 0,
            "secondary_watch_only_count": 0,
            "all_primary_contracts_valid": False,
            "all_primary_observation_status_ok": False,
            "current_candidate_seen": False,
            "current_candidate_lane_key": None,
            "matching_observed_lane_keys": [],
            "candidate_freshness_status": "NO_OBSERVATION_LEDGER_ROW",
        }
    packets = [row for row in observation.get("lane_packets") or [] if isinstance(row, Mapping)]
    primary = [row for row in packets if row.get("lane_role") == PRIMARY_DRY_RUN_OBSERVATION]
    secondary = [row for row in packets if row.get("lane_role") == SECONDARY_WATCH_ONLY_VISIBLE]
    baseline = next((row for row in packets if row.get("lane_role") == BASELINE_CURRENT_FIRST_TINY_LIVE), None)
    candidate = _mapping(observation.get("candidate_visibility_summary"))
    return {
        "baseline_lane": observation.get("baseline_lane") or (baseline or {}).get("lane_key"),
        "primary_observed_lanes": [str(row.get("lane_key")) for row in primary if row.get("lane_key")],
        "secondary_watch_only_lanes": [str(row.get("lane_key")) for row in secondary if row.get("lane_key")],
        "primary_observed_count": len(primary),
        "secondary_watch_only_count": len(secondary),
        "all_primary_contracts_valid": bool(primary) and all(row.get("risk_contract_valid") is True for row in primary),
        "all_primary_observation_status_ok": bool(primary)
        and all(row.get("observation_status") == "OBSERVING_DRY_RUN" for row in primary),
        "current_candidate_seen": candidate.get("current_candidate_seen") is True,
        "current_candidate_lane_key": candidate.get("current_candidate_lane_key"),
        "matching_observed_lane_keys": list(candidate.get("matching_observed_lane_keys") or []),
        "candidate_freshness_status": candidate.get("candidate_freshness_status"),
    }


def _final_live_safety(
    *,
    log_dir: Path,
    final_gate_panel: Mapping[str, Any] | None,
) -> dict[str, Any]:
    try:
        panel = dict(final_gate_panel) if final_gate_panel is not None else build_final_tiny_live_authorization_gate_panel(log_dir=log_dir)
        armed = _mapping(panel.get("exact_lane_armed_state"))
        readiness = _mapping(panel.get("readiness_matrix"))
        return {
            "final_gate_status": panel.get("status"),
            "final_gate_blockers": list(panel.get("blockers") or []),
            "real_order_forbidden": panel.get("real_order_forbidden") is not False,
            "submit_allowed": panel.get("submit_allowed") is True,
            "final_command_available": panel.get("final_command_available") is True,
            "armed_lane_key": armed.get("armed_lane_key"),
            "timer_health_status": readiness.get("timer_health_status"),
            "timer_active": readiness.get("timer_active"),
        }
    except Exception as exc:  # pragma: no cover - defensive runtime read-only panel.
        return {
            "final_gate_status": "FINAL_GATE_PANEL_UNAVAILABLE",
            "final_gate_blockers": [exc.__class__.__name__],
            "real_order_forbidden": True,
            "submit_allowed": False,
            "final_command_available": False,
            "armed_lane_key": None,
            "timer_health_status": None,
            "timer_active": None,
        }


def _paper_refresh_summary(
    *,
    log_dir: Path,
    systemctl_runner: SystemctlRunner | None,
) -> dict[str, Any]:
    runs = load_refresh_runs(limit=1, log_dir=log_dir)
    latest = runs[0] if runs else {}
    failed = [str(task) for task in latest.get("failed_tasks") or []]
    health = latest.get("paper_refresh_health_status") or "PAPER_REFRESH_NOT_RECORDED"
    active = _systemctl(["systemctl", "is-active", PAPER_REFRESH_SERVICE_NAME], runner=systemctl_runner)
    return {
        "paper_refresh_health_status": health,
        "last_failed_tasks": failed,
        "service_active": active["status"] == "active",
        "degraded_non_critical_accepted": (
            health == PAPER_REFRESH_DEGRADED_NON_CRITICAL and set(failed) <= {TASK_ETH_PAPER_OUTCOME}
        ),
        "fatal": health == PAPER_REFRESH_CRITICAL_FAILURE,
        "healthy": health == PAPER_REFRESH_HEALTHY,
    }


def _health_blockers(
    *,
    timer_summary: Mapping[str, Any],
    lane_summary: Mapping[str, Any],
    final_live_safety: Mapping[str, Any],
    paper_refresh_summary: Mapping[str, Any],
    safety: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not timer_summary.get("last_tick_seen"):
        blockers.append("missing_observation_tick")
    elif timer_summary.get("last_tick_recent") is not True:
        blockers.append("stale_observation_tick")
    if lane_summary.get("all_primary_contracts_valid") is not True:
        blockers.append("primary_risk_contract_invalid")
    if lane_summary.get("all_primary_observation_status_ok") is not True:
        blockers.append("primary_observation_status_not_ok")
    if final_live_safety.get("real_order_forbidden") is not True:
        blockers.append("real_order_not_forbidden")
    if final_live_safety.get("submit_allowed") is True:
        blockers.append("submit_allowed_unexpected")
    if final_live_safety.get("final_command_available") is True:
        blockers.append("final_command_available_unexpected")
    if paper_refresh_summary.get("fatal") is True:
        blockers.append("paper_refresh_critical_failure")
    blockers.extend(_safety_violations(safety))
    return _dedupe(blockers)


def _health_status(blockers: Sequence[str]) -> str:
    if not blockers:
        return HEALTH_OK
    blocking = {
        "missing_observation_tick",
        "primary_risk_contract_invalid",
        "primary_observation_status_not_ok",
        "real_order_not_forbidden",
        "submit_allowed_unexpected",
        "final_command_available_unexpected",
        "paper_refresh_critical_failure",
    }
    if any(blocker in blocking or blocker.startswith("safety_flag_") for blocker in blockers):
        return HEALTH_BLOCKED
    return HEALTH_DEGRADED


def _safety_violations(safety: Mapping[str, Any]) -> list[str]:
    return [
        f"safety_flag_{key}_unexpected"
        for key, expected in SAFETY.items()
        if safety.get(key) is not expected
    ]


def _systemctl(command: Sequence[str], *, runner: SystemctlRunner | None) -> dict[str, Any]:
    run = runner or _run_systemctl
    try:
        code, stdout = run(command)
    except Exception as exc:  # pragma: no cover - local systems may not expose systemd.
        return {"status": "unknown", "returncode": 1, "error": exc.__class__.__name__}
    status = str(stdout or "").strip().splitlines()[0] if str(stdout or "").strip() else "unknown"
    return {"status": status, "returncode": code, "raw": stdout}


def _systemctl_show(unit: str, *, runner: SystemctlRunner | None) -> dict[str, Any]:
    result = _systemctl(["systemctl", "show", unit, "-p", "Result", "-p", "ExecMainStatus"], runner=runner)
    values: dict[str, Any] = dict(result)
    for line in str(result.get("raw") or "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _run_systemctl(command: Sequence[str]) -> tuple[int, str]:
    result = subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
        timeout=2,
    )
    output = result.stdout.strip() or result.stderr.strip()
    return result.returncode, output


def _age_seconds(timestamp: str | None, *, now: datetime) -> int | None:
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0, int((now - parsed.astimezone(UTC)).total_seconds()))


def _compact_errors(items: Sequence[Mapping[str, Any]]) -> list[str]:
    return _dedupe(str(item.get("error")) for item in items if item.get("error"))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _join(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) if value else "none"
    return str(value) if value not in (None, "") else "none"


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value)
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.app.hammer_radar.operator.multi_lane_observation_health_panel"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--max-age-seconds", type=int, default=180)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload = build_multi_lane_observation_health_panel(
        log_dir=args.log_dir,
        max_age_seconds=args.max_age_seconds,
        write=not args.no_write,
    )
    if args.json and not args.text:
        print(format_health_panel_json(payload))
    else:
        print(format_health_panel_text(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint.
    raise SystemExit(main())
