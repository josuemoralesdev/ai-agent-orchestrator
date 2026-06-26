"""R311 multi-lane dry-run timer/unit preview.

This module renders a proposed systemd service/timer for recurring R310
multi-lane dry-run observation. It never writes systemd files, runs systemctl,
reloads daemons, mutates config, arms lanes, or touches Binance endpoints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records

EVENT_TYPE = "R311_MULTI_LANE_DRY_RUN_TIMER_UNIT_PREVIEW"
CREATED_BY_PHASE = "R311_MULTI_LANE_DRY_RUN_TIMER_UNIT_PREVIEW"
LEDGER_FILENAME = "multi_lane_dry_run_timer_unit_preview.ndjson"

SERVICE_NAME = "hammer-multi-lane-dry-run-observation.service"
TIMER_NAME = "hammer-multi-lane-dry-run-observation.timer"
INSTALL_PATH_PREVIEW = "/etc/systemd/system"
FUTURE_CONFIRMATION_PHRASE_PREVIEW = "INSTALL MULTI LANE DRY RUN OBSERVATION TIMER"
RECOMMENDED_R312_CLEAN = "R312 Human-Reviewed Multi-Lane Timer Install Gate"
RECOMMENDED_R312_BLOCKED = "R312 Timer Preview Repair"

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
    "systemd_unit_installed": False,
    "systemd_timer_installed": False,
    "systemd_unit_enabled": False,
    "systemd_timer_enabled": False,
    "systemd_unit_started": False,
    "systemd_timer_started": False,
    "daemon_reload_called": False,
    "scheduler_started": False,
}

FORBIDDEN_COMMAND_FRAGMENTS = (
    " --live",
    "--allow-live",
    "--submit",
    "final-live-submit",
    "submit-live",
    "fapi/v1/order",
    "test-order",
    "leverage",
    "margin",
)


def build_multi_lane_dry_run_timer_unit_preview(
    *,
    log_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    user: str = "josue",
    write: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    absolute_log_dir = _absolute_path(root, resolved_log_dir)
    generated_at = now or datetime.now(UTC)
    command_preview = _command_preview(root=root, log_dir=absolute_log_dir)
    service_content = _service_content(
        root=root,
        user=user,
        log_dir=absolute_log_dir,
        command_preview=command_preview,
    )
    timer_content = _timer_content(root=root)
    validation_summary = _validation_summary(root=root, command_preview=command_preview)
    blocked_reasons = [key for key, value in validation_summary.items() if value is not True]
    status = "TIMER_UNIT_PREVIEW_READY" if not blocked_reasons else "TIMER_UNIT_PREVIEW_BLOCKED"
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "preview_id": f"r311_multi_lane_dry_run_timer_unit_preview_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "status": status,
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        "preview_only": True,
        "service_name": SERVICE_NAME,
        "timer_name": TIMER_NAME,
        "service_content_preview": service_content,
        "timer_content_preview": timer_content,
        "install_path_preview": INSTALL_PATH_PREVIEW,
        "timer_cadence_preview": {
            "OnBootSec": "2min",
            "OnUnitActiveSec": "60s",
            "AccuracySec": "10s",
        },
        "command_preview": command_preview,
        "working_directory": str(root),
        "user": user,
        "unit_preview_sha256": _sha256(service_content),
        "timer_preview_sha256": _sha256(timer_content),
        "systemd_write_gate_required": True,
        "future_confirmation_phrase_preview": FUTURE_CONFIRMATION_PHRASE_PREVIEW,
        "future_confirmation_phrase_active": False,
        "future_confirmation_phrase_executable": False,
        "validation_summary": validation_summary,
        "blocked_reasons": blocked_reasons,
        "systemd_mutation_summary": {
            "systemd_write_performed": False,
            "systemctl_called": False,
            "daemon_reload_called": False,
            "unit_installed": False,
            "timer_installed": False,
            "unit_enabled": False,
            "timer_enabled": False,
            "unit_started": False,
            "timer_started": False,
        },
        "recommended_r312_path": (
            RECOMMENDED_R312_CLEAN if status == "TIMER_UNIT_PREVIEW_READY" else RECOMMENDED_R312_BLOCKED
        ),
        "source_surfaces_used": [
            "src/app/hammer_radar/operator/multi_lane_dry_run_observation_scheduler.py",
            "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py",
            "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py",
            "ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template",
            "ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template",
            "docs/hammer_radar/live_readiness/R310_MULTI_LANE_DRY_RUN_OBSERVATION_SCHEDULER.md",
        ],
        "safety": dict(SAFETY),
        **dict(SAFETY),
    }
    safe_payload = _sanitize(payload)
    if write:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def load_multi_lane_dry_run_timer_unit_preview_records(
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


def format_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def format_preview_text(payload: Mapping[str, Any]) -> str:
    cadence = payload.get("timer_cadence_preview")
    cadence = cadence if isinstance(cadence, Mapping) else {}
    validation = payload.get("validation_summary")
    validation = validation if isinstance(validation, Mapping) else {}
    lines = [
        "R311 MULTI-LANE DRY-RUN TIMER UNIT PREVIEW",
        f"event_type: {payload.get('event_type')}",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        "",
        "SERVICE/TIMER",
        f"service_name: {payload.get('service_name')}",
        f"timer_name: {payload.get('timer_name')}",
        f"install_path_preview: {payload.get('install_path_preview')}",
        "",
        "COMMAND PREVIEW",
        str(payload.get("command_preview")),
        "",
        "CADENCE",
        f"OnBootSec: {cadence.get('OnBootSec')}",
        f"OnUnitActiveSec: {cadence.get('OnUnitActiveSec')}",
        f"AccuracySec: {cadence.get('AccuracySec')}",
        "",
        "SYSTEMD WRITE GATE",
        f"systemd_write_gate_required: {payload.get('systemd_write_gate_required')}",
        f"future_confirmation_phrase_preview: {payload.get('future_confirmation_phrase_preview')}",
        f"future_confirmation_phrase_active: {payload.get('future_confirmation_phrase_active')}",
        f"future_confirmation_phrase_executable: {payload.get('future_confirmation_phrase_executable')}",
        "",
        "VALIDATION SUMMARY",
    ]
    for key in sorted(validation):
        lines.append(f"{key}: {validation.get(key)}")
    lines.extend(["", "SAFETY FLAGS"])
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(
        [
            "",
            "RECOMMENDED R312 PATH",
            str(payload.get("recommended_r312_path")),
        ]
    )
    return "\n".join(lines)


def _command_preview(*, root: Path, log_dir: Path) -> str:
    return " ".join(
        [
            str(root / ".venv/bin/python"),
            "-m",
            "src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler",
            "--log-dir",
            str(log_dir),
            "--once",
        ]
    )


def _service_content(*, root: Path, user: str, log_dir: Path, command_preview: str) -> str:
    return "\n".join(
        [
            "[Unit]",
            "Description=Hammer Radar multi-lane dry-run observation tick",
            f"Documentation=file:{root}/docs/hammer_radar/live_readiness/R311_MULTI_LANE_DRY_RUN_TIMER_UNIT_PREVIEW.md",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            f"User={user}",
            f"WorkingDirectory={root}",
            "Environment=PYTHONPATH=.",
            f"Environment=HAMMER_RADAR_LOG_DIR={log_dir}",
            "Environment=HAMMER_LIVE_EXECUTION_ENABLED=false",
            "Environment=HAMMER_ALLOW_LIVE_ORDERS=false",
            "Environment=HAMMER_GLOBAL_KILL_SWITCH=true",
            f"ExecStart={command_preview}",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "",
        ]
    )


def _timer_content(*, root: Path) -> str:
    return "\n".join(
        [
            "[Unit]",
            "Description=Run Hammer Radar multi-lane dry-run observation every 60 seconds",
            f"Documentation=file:{root}/docs/hammer_radar/live_readiness/R311_MULTI_LANE_DRY_RUN_TIMER_UNIT_PREVIEW.md",
            "",
            "[Timer]",
            "OnBootSec=2min",
            "OnUnitActiveSec=60s",
            "AccuracySec=10s",
            "Persistent=false",
            f"Unit={SERVICE_NAME}",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]
    )


def _validation_summary(*, root: Path, command_preview: str) -> dict[str, bool]:
    command_lower = command_preview.lower()
    return {
        "command_uses_venv_python": command_preview.startswith(str(root / ".venv/bin/python")),
        "command_uses_once": "--once" in command_preview.split(),
        "command_is_observation_only": (
            "src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler" in command_preview
        ),
        "no_live_flags": "--live" not in command_lower and "--allow-live" not in command_lower,
        "no_apply_flags": "--apply" not in command_lower and "--write-risk" not in command_lower,
        "no_binance_endpoint_flags": not any(fragment in command_lower for fragment in FORBIDDEN_COMMAND_FRAGMENTS),
    }


def _absolute_path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key, value in SAFETY.items():
            if key in sanitized:
                sanitized[key] = value
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload


def _main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.app.hammer_radar.operator.multi_lane_dry_run_timer_unit_preview"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--user", default="josue")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    payload = build_multi_lane_dry_run_timer_unit_preview(
        log_dir=args.log_dir,
        repo_root=args.repo_root,
        user=args.user,
        write=not args.no_write,
    )
    print(format_preview_text(payload) if args.text else format_preview_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
