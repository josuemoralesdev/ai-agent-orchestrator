"""R312 human-reviewed multi-lane dry-run timer install gate.

Default behavior is preview-only. Apply mode requires the exact R312 phrase and
can be tested against temporary install directories with mocked systemctl calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.multi_lane_dry_run_timer_unit_preview import (
    SERVICE_NAME,
    TIMER_NAME,
    build_multi_lane_dry_run_timer_unit_preview,
)

EVENT_TYPE = "R312_HUMAN_REVIEWED_MULTI_LANE_TIMER_INSTALL_GATE"
CREATED_BY_PHASE = "R312_HUMAN_REVIEWED_MULTI_LANE_TIMER_INSTALL_GATE"
LEDGER_FILENAME = "multi_lane_dry_run_timer_install_gate.ndjson"
CONFIRMATION_PHRASE = "INSTALL MULTI LANE DRY RUN OBSERVATION TIMER"
DEFAULT_INSTALL_DIR = "/etc/systemd/system"

INSTALL_GATE_PREVIEW_READY = "INSTALL_GATE_PREVIEW_READY"
INSTALL_GATE_BLOCKED_CONFIRMATION_REQUIRED = "INSTALL_GATE_BLOCKED_CONFIRMATION_REQUIRED"
INSTALL_GATE_WRITTEN_TEMP_OR_REAL = "INSTALL_GATE_WRITTEN_TEMP_OR_REAL"

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
}


def build_multi_lane_dry_run_timer_install_gate(
    *,
    log_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    user: str = "josue",
    install_dir: str | Path | None = None,
    apply: bool = False,
    confirmation: str | None = None,
    systemctl_mode: str = "mock",
    write_ledger: bool = True,
    now: datetime | None = None,
    systemctl_runner: Callable[[Sequence[str]], None] | None = None,
) -> dict[str, Any]:
    if systemctl_mode not in {"mock", "real"}:
        raise ValueError("systemctl_mode must be 'mock' or 'real'")

    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    target_dir = Path(install_dir or DEFAULT_INSTALL_DIR)
    service_path = target_dir / SERVICE_NAME
    timer_path = target_dir / TIMER_NAME
    preview = build_multi_lane_dry_run_timer_unit_preview(
        log_dir=resolved_log_dir,
        repo_root=root,
        user=user,
        write=False,
        now=generated_at,
    )
    service_content = str(preview["service_content_preview"])
    timer_content = str(preview["timer_content_preview"])
    confirmation_matched = confirmation == CONFIRMATION_PHRASE
    files_written: list[str] = []
    backups_created: list[str] = []
    mocked_systemctl_calls: list[list[str]] = []
    real_systemctl_calls: list[list[str]] = []
    blocked_reasons: list[str] = []
    daemon_reload_called = False
    enable_called = False
    start_called = False

    if apply and not confirmation_matched:
        status = INSTALL_GATE_BLOCKED_CONFIRMATION_REQUIRED
        blocked_reasons = ["exact_confirmation_phrase_required"]
    elif apply:
        target_dir.mkdir(parents=True, exist_ok=True)
        backups_created.extend(_backup_existing(path, generated_at=generated_at) for path in (service_path, timer_path) if path.exists())
        service_path.write_text(service_content, encoding="utf-8")
        timer_path.write_text(timer_content, encoding="utf-8")
        files_written = [str(service_path), str(timer_path)]
        calls = [
            ["systemctl", "daemon-reload"],
            ["systemctl", "enable", TIMER_NAME],
            ["systemctl", "start", TIMER_NAME],
        ]
        if systemctl_mode == "mock":
            mocked_systemctl_calls = [list(call) for call in calls]
        else:
            runner = systemctl_runner or _run_real_systemctl
            for call in calls:
                runner(call)
                real_systemctl_calls.append(list(call))
            daemon_reload_called = True
            enable_called = True
            start_called = True
        status = INSTALL_GATE_WRITTEN_TEMP_OR_REAL
    else:
        status = INSTALL_GATE_PREVIEW_READY

    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "gate_id": f"r312_multi_lane_dry_run_timer_install_gate_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        "service_name": SERVICE_NAME,
        "timer_name": TIMER_NAME,
        "service_install_path": str(service_path),
        "timer_install_path": str(timer_path),
        "service_content_preview": service_content,
        "timer_content_preview": timer_content,
        "service_content_sha256": _sha256(service_content),
        "timer_content_sha256": _sha256(timer_content),
        "command_preview": preview["command_preview"],
        "timer_cadence_preview": preview["timer_cadence_preview"],
        "apply_requested": bool(apply),
        "confirmation_phrase_required": CONFIRMATION_PHRASE,
        "confirmation_phrase_matched": bool(confirmation_matched),
        "systemctl_mode": systemctl_mode,
        "preview_only": not bool(apply and confirmation_matched),
        "would_write_files": [str(service_path), str(timer_path)],
        "would_call_daemon_reload": True,
        "would_enable_timer": TIMER_NAME,
        "would_start_timer": TIMER_NAME,
        "files_written": files_written,
        "backups_created": [path for path in backups_created if path],
        "daemon_reload_called": daemon_reload_called,
        "enable_called": enable_called,
        "start_called": start_called,
        "systemd_unit_installed": str(service_path) in files_written,
        "systemd_timer_installed": str(timer_path) in files_written,
        "systemd_unit_enabled": False,
        "systemd_timer_enabled": enable_called,
        "systemd_timer_started": start_called,
        "mocked_systemctl_calls": mocked_systemctl_calls,
        "real_systemctl_calls": real_systemctl_calls,
        "install_gate_status": status,
        "blocked_reasons": blocked_reasons,
        "manual_apply_command_preview": (
            "PYTHONPATH=. .venv/bin/python -m "
            "src.app.hammer_radar.operator.multi_lane_dry_run_timer_install_gate "
            "--log-dir logs/hammer_radar_forward --apply "
            f'--confirmation "{CONFIRMATION_PHRASE}"'
        ),
        "recommended_r313_path": (
            "R313 Operator Apply Multi-Lane Timer Install + Health Verification"
            if status in {INSTALL_GATE_PREVIEW_READY, INSTALL_GATE_WRITTEN_TEMP_OR_REAL}
            else "R313 Timer Install Gate Repair"
        ),
        "source_surfaces_used": [
            "src/app/hammer_radar/operator/multi_lane_dry_run_timer_unit_preview.py",
            "src/app/hammer_radar/operator/multi_lane_dry_run_observation_scheduler.py",
            "src/app/hammer_radar/operator/inspect.py",
            "docs/hammer_radar/live_readiness/R311_MULTI_LANE_DRY_RUN_TIMER_UNIT_PREVIEW.md",
        ],
        "safety": dict(SAFETY),
        **dict(SAFETY),
    }
    safe_payload = _sanitize(payload)
    if write_ledger:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def load_multi_lane_dry_run_timer_install_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def append_record(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = records_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8") if not path.exists() else None
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def format_gate_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R312 HUMAN-REVIEWED MULTI-LANE TIMER INSTALL GATE",
        f"event_type: {payload.get('event_type')}",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        "",
        "SERVICE/TIMER",
        f"service_name: {payload.get('service_name')}",
        f"timer_name: {payload.get('timer_name')}",
        f"service_install_path: {payload.get('service_install_path')}",
        f"timer_install_path: {payload.get('timer_install_path')}",
        "",
        "COMMAND PREVIEW",
        str(payload.get("command_preview")),
        "",
        "INSTALL GATE",
        f"install_gate_status: {payload.get('install_gate_status')}",
        f"apply_requested: {payload.get('apply_requested')}",
        f"confirmation_phrase_required: {payload.get('confirmation_phrase_required')}",
        f"confirmation_phrase_matched: {payload.get('confirmation_phrase_matched')}",
        f"systemctl_mode: {payload.get('systemctl_mode')}",
        f"preview_only: {payload.get('preview_only')}",
        f"would_write_files: {', '.join(payload.get('would_write_files') or [])}",
        f"would_call_daemon_reload: {payload.get('would_call_daemon_reload')}",
        f"would_enable_timer: {payload.get('would_enable_timer')}",
        f"would_start_timer: {payload.get('would_start_timer')}",
        f"files_written: {', '.join(payload.get('files_written') or []) or 'none'}",
        f"backups_created: {', '.join(payload.get('backups_created') or []) or 'none'}",
        f"daemon_reload_called: {payload.get('daemon_reload_called')}",
        f"enable_called: {payload.get('enable_called')}",
        f"start_called: {payload.get('start_called')}",
        "",
        "APPLY COMMAND PREVIEW",
        str(payload.get("manual_apply_command_preview")),
        "",
        "SAFETY FLAGS",
    ]
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(["", "RECOMMENDED R313 PATH", str(payload.get("recommended_r313_path"))])
    return "\n".join(lines)


def _backup_existing(path: Path, *, generated_at: datetime) -> str:
    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.r312_backup_{stamp}")
    shutil.copy2(path, backup)
    return str(backup)


def _run_real_systemctl(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, Mapping):
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
        prog="python -m src.app.hammer_radar.operator.multi_lane_dry_run_timer_install_gate"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--user", default="josue")
    parser.add_argument("--install-dir", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation", default=None)
    parser.add_argument("--systemctl-mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--no-ledger", action="store_true")
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args()
    payload = build_multi_lane_dry_run_timer_install_gate(
        log_dir=args.log_dir,
        repo_root=args.repo_root,
        user=args.user,
        install_dir=args.install_dir,
        apply=args.apply,
        confirmation=args.confirmation,
        systemctl_mode=args.systemctl_mode,
        write_ledger=not args.no_ledger,
    )
    print(format_gate_text(payload) if args.text else format_gate_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
