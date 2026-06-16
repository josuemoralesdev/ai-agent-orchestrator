"""R292 read-only installed timer health for the dry-run scheduler.

This module inspects local systemd state with read-only commands only. It never
runs sudo, mutates installed units, reloads systemd, starts/stops timers, or
touches trading execution.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler import (
    LEDGER_FILENAME,
    SAFETY,
    SERVICE_TEMPLATE_PATH,
    TIMER_TEMPLATE_PATH,
)

EVENT_TYPE = "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER_TIMER_HEALTH"
CREATED_BY_PHASE = "R292_DRY_RUN_TIMER_OPERATIONAL_HARDENING"

TIMER_HEALTH_ACTIVE = "TIMER_HEALTH_ACTIVE"
TIMER_HEALTH_INACTIVE = "TIMER_HEALTH_INACTIVE"
TIMER_HEALTH_NOT_INSTALLED = "TIMER_HEALTH_NOT_INSTALLED"
TIMER_HEALTH_UNKNOWN = "TIMER_HEALTH_UNKNOWN"

SERVICE_UNIT_NAME = "hammer-autonomous-trigger-scheduler-dry-run.service"
TIMER_UNIT_NAME = "hammer-autonomous-trigger-scheduler-dry-run.timer"

R292_DOC_PATH = Path("docs/hammer_radar/live_readiness/R292_DRY_RUN_TIMER_OPERATIONAL_HARDENING.md")
PRINT_ONLY_REFRESH_SCRIPT_PATH = Path(
    "scripts/hammer_print_r292_refresh_installed_dry_run_timer_units.sh"
)

EXPECTED_SERVICE_DOCUMENTATION = (
    "Documentation=file:/home/josue/workspace/kernel/ai-agent-orchestrator-main/"
    "docs/hammer_radar/live_readiness/R289_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_INSTALL_CHECKLIST.md"
)
EXPECTED_TIMER_DOCUMENTATION = (
    "Documentation=file:/home/josue/workspace/kernel/ai-agent-orchestrator-main/"
    "docs/hammer_radar/live_readiness/R290_MANUAL_SYSTEMD_DRY_RUN_TIMER_ACTIVATION_CHECKLIST.md"
)

READ_ONLY_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("systemctl", "is-active", TIMER_UNIT_NAME),
    ("systemctl", "is-enabled", TIMER_UNIT_NAME),
    ("systemctl", "list-timers", TIMER_UNIT_NAME, "--no-pager", "--all"),
    ("systemctl", "status", TIMER_UNIT_NAME, "--no-pager", "-l"),
    ("journalctl", "-u", SERVICE_UNIT_NAME, "-n", "120", "--no-pager"),
)

FORBIDDEN_COMMAND_TOKENS = {
    "sudo",
    "start",
    "stop",
    "enable",
    "disable",
    "restart",
    "daemon-reload",
    "install",
    "rm",
}

UNSAFE_SAFETY_KEYS = (
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "submit_attempted",
    "binance_order_endpoint_called",
    "binance_test_order_endpoint_called",
    "leverage_change_called",
    "margin_change_called",
    "mutation_performed",
    "signed_trading_request_created",
    "signed_order_request_created",
    "signed_request_created",
    "signed_url_shown",
    "signature_shown",
    "secrets_shown",
    "secret_values_in_output",
    "env_written",
    "env_mutated",
    "lane_controls_written",
    "risk_contract_config_written",
    "live_config_written",
    "executable_payload_created",
    "final_command_available",
    "submit_allowed",
    "per_signal_operator_approval_required",
)


def build_autonomous_trigger_scheduler_timer_health(
    *,
    log_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    generated_at = datetime.now(UTC)
    command_results = _run_read_only_commands(command_runner=command_runner)
    timer_status = command_results.get("timer_status", {})
    timer_list = command_results.get("timer_list", {})
    journal = command_results.get("journal", {})
    timer_active = _stdout(command_results.get("timer_active")).strip() == "active"
    enabled_state = _stdout(command_results.get("timer_enabled")).strip() or None
    timer_loaded = _loaded_seen(_stdout(timer_status), TIMER_UNIT_NAME)
    service_loaded = _journal_checked(journal) or _service_seen_in_journal(_stdout(journal))
    timer_list_text = _stdout(timer_list)
    journal_text = _stdout(journal)
    timer_list_timers_seen = TIMER_UNIT_NAME in timer_list_text
    next_trigger, last_trigger = _parse_list_timers(timer_list_text)
    recent_records = _recent_scheduler_records(log_dir=log_dir)
    recent_tick_count = len(recent_records)
    recent_tick_seen = recent_tick_count > 0 or "AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED" in journal_text
    recent_safety_flags_seen = _recent_safety_flags(recent_records)
    documentation_warning_seen = "Invalid URL" in journal_text or "invalid url" in _stdout(timer_status).lower()
    documentation_warning_fixed_in_repo_template = _repo_templates_have_file_urls(root)
    installed_unit_refresh_required = bool(
        documentation_warning_seen and documentation_warning_fixed_in_repo_template
    )
    blockers = _blockers(
        command_results=command_results,
        timer_loaded=timer_loaded,
        timer_active=timer_active,
        recent_safety_flags_seen=recent_safety_flags_seen,
        documentation_warning_fixed_in_repo_template=documentation_warning_fixed_in_repo_template,
    )
    status = _status(
        command_results=command_results,
        timer_loaded=timer_loaded,
        timer_active=timer_active,
        timer_list_timers_seen=timer_list_timers_seen,
    )
    safety = _safety()
    packet = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "status": status,
        "generated_at": generated_at.isoformat(),
        "service_unit_name": SERVICE_UNIT_NAME,
        "timer_unit_name": TIMER_UNIT_NAME,
        "timer_loaded": timer_loaded,
        "timer_active": timer_active,
        "timer_enabled_state": enabled_state,
        "timer_next_trigger_raw": next_trigger,
        "timer_last_trigger_raw": last_trigger,
        "timer_list_timers_seen": timer_list_timers_seen,
        "service_loaded": service_loaded,
        "service_last_status_seen": _service_last_status_seen(journal_text),
        "recent_journal_checked": _journal_checked(journal),
        "recent_tick_seen": recent_tick_seen,
        "recent_tick_count": recent_tick_count,
        "recent_safety_flags_seen": recent_safety_flags_seen,
        "documentation_warning_seen": documentation_warning_seen,
        "documentation_warning_fixed_in_repo_template": documentation_warning_fixed_in_repo_template,
        "installed_unit_refresh_required": installed_unit_refresh_required,
        "repo_service_template_path": str(SERVICE_TEMPLATE_PATH),
        "repo_timer_template_path": str(TIMER_TEMPLATE_PATH),
        "manual_refresh_commands": _manual_refresh_commands(),
        "manual_rollback_commands": _manual_rollback_commands(),
        "codex_systemctl_mutation_performed": False,
        "codex_sudo_performed": False,
        "codex_install_performed": False,
        "dry_run_only": True,
        "live_execution_enabled": False,
        "per_signal_operator_approval_required": False,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "blockers": blockers,
        "read_only_commands_checked": [" ".join(command) for command in READ_ONLY_COMMANDS],
        "command_results": _public_command_results(command_results),
        "autonomous_trigger_scheduler_timer_health_panel": {
            "timer_health_status": status,
            "timer_active": timer_active,
            "timer_loaded": timer_loaded,
            "timer_installed": timer_loaded or timer_list_timers_seen,
            "recent_tick_seen": recent_tick_seen,
            "recent_tick_count": recent_tick_count,
            "documentation_warning_seen": documentation_warning_seen,
            "repo_template_fixed": documentation_warning_fixed_in_repo_template,
            "installed_unit_refresh_required": installed_unit_refresh_required,
            "manual_refresh_commands": _manual_refresh_commands(),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        },
        "safety": safety,
    }
    return _sanitize(packet)


def format_autonomous_trigger_scheduler_timer_health_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _run_read_only_commands(
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, dict[str, Any]]:
    runner = command_runner or subprocess.run
    names = ("timer_active", "timer_enabled", "timer_list", "timer_status", "journal")
    results: dict[str, dict[str, Any]] = {}
    for name, command in zip(names, READ_ONLY_COMMANDS, strict=True):
        _assert_read_only_command(command)
        try:
            completed = runner(
                list(command),
                text=True,
                capture_output=True,
                check=False,
                timeout=8,
            )
            results[name] = {
                "command": " ".join(command),
                "returncode": completed.returncode,
                "stdout": completed.stdout or "",
                "stderr": completed.stderr or "",
                "checked": True,
            }
        except Exception as exc:  # pragma: no cover - defensive local inspection
            results[name] = {
                "command": " ".join(command),
                "returncode": None,
                "stdout": "",
                "stderr": exc.__class__.__name__,
                "checked": False,
            }
    return results


def _assert_read_only_command(command: Sequence[str]) -> None:
    tokens = [str(token) for token in command]
    lower_tokens = {token.lower() for token in tokens}
    forbidden = sorted(FORBIDDEN_COMMAND_TOKENS.intersection(lower_tokens))
    if forbidden:
        raise ValueError(f"unsafe command token blocked: {forbidden}")
    if tokens[:2] == ["systemctl", "is-enabled"]:
        return
    if tokens[:2] == ["systemctl", "is-active"]:
        return
    if tokens[:2] == ["systemctl", "list-timers"]:
        return
    if tokens[:2] == ["systemctl", "status"]:
        return
    if tokens[:3] == ["journalctl", "-u", SERVICE_UNIT_NAME]:
        return
    raise ValueError(f"unsupported timer health command: {' '.join(tokens)}")


def _recent_scheduler_records(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    if not path.exists():
        return []
    return [
        _sanitize(record)
        for record in read_recent_ndjson_records(path, limit=20, max_bytes=4_194_304)
        if isinstance(record, Mapping)
    ]


def _recent_safety_flags(records: Sequence[Mapping[str, Any]]) -> list[str]:
    seen: set[str] = set()
    flags: list[str] = []
    for record in records:
        safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
        for key in UNSAFE_SAFETY_KEYS:
            if safety.get(key) is True or record.get(key) is True:
                if key not in seen:
                    seen.add(key)
                    flags.append(key)
    return flags


def _repo_templates_have_file_urls(root: Path) -> bool:
    service_text = _read_text(root / SERVICE_TEMPLATE_PATH)
    timer_text = _read_text(root / TIMER_TEMPLATE_PATH)
    return (
        EXPECTED_SERVICE_DOCUMENTATION in service_text
        and EXPECTED_TIMER_DOCUMENTATION in timer_text
        and "Documentation=docs/" not in service_text
        and "Documentation=docs/" not in timer_text
    )


def _blockers(
    *,
    command_results: Mapping[str, Mapping[str, Any]],
    timer_loaded: bool,
    timer_active: bool,
    recent_safety_flags_seen: Sequence[str],
    documentation_warning_fixed_in_repo_template: bool,
) -> list[str]:
    blockers: list[str] = []
    if not _any_command_checked(command_results):
        blockers.append("read_only_systemctl_status_unavailable")
    if not timer_loaded:
        blockers.append("timer_not_loaded")
    if timer_loaded and not timer_active:
        blockers.append("timer_not_active")
    if recent_safety_flags_seen:
        blockers.extend(f"unsafe_recent_safety_flag:{flag}" for flag in recent_safety_flags_seen)
    if not documentation_warning_fixed_in_repo_template:
        blockers.append("repo_template_documentation_file_url_missing")
    return blockers


def _status(
    *,
    command_results: Mapping[str, Mapping[str, Any]],
    timer_loaded: bool,
    timer_active: bool,
    timer_list_timers_seen: bool,
) -> str:
    if not _any_command_checked(command_results):
        return TIMER_HEALTH_UNKNOWN
    if timer_loaded and timer_active:
        return TIMER_HEALTH_ACTIVE
    if not timer_loaded and not timer_list_timers_seen:
        return TIMER_HEALTH_NOT_INSTALLED
    return TIMER_HEALTH_INACTIVE


def _parse_list_timers(text: str) -> tuple[str | None, str | None]:
    for line in text.splitlines():
        if TIMER_UNIT_NAME not in line:
            continue
        normalized = re.sub(r"\s+", " ", line.strip())
        fields = normalized.split(" ")
        if len(fields) >= 6:
            return " ".join(fields[:5]), " ".join(fields[5:10])
        return normalized, None
    return None, None


def _loaded_seen(text: str, unit_name: str) -> bool:
    lower = text.lower()
    return "loaded: loaded" in lower or (unit_name in text and "loaded" in lower)


def _service_seen_in_journal(text: str) -> bool:
    return SERVICE_UNIT_NAME in text or "tiny-live-autonomous-trigger-scheduler-once" in text


def _service_last_status_seen(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        if (
            "AUTONOMOUS_TRIGGER_SCHEDULER_" in line
            or "tiny-live-autonomous-trigger-scheduler-once" in line
            or "no submit" in line.lower()
        ):
            return line[-500:]
    return None


def _journal_checked(result: Mapping[str, Any]) -> bool:
    return result.get("checked") is True and result.get("returncode") in (0, 1)


def _any_command_checked(command_results: Mapping[str, Mapping[str, Any]]) -> bool:
    return any(result.get("checked") is True for result in command_results.values())


def _stdout(result: Mapping[str, Any] | None) -> str:
    if not isinstance(result, Mapping):
        return ""
    return str(result.get("stdout") or "")


def _public_command_results(command_results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        name: {
            "command": result.get("command"),
            "returncode": result.get("returncode"),
            "checked": result.get("checked") is True,
            "stdout_preview": str(result.get("stdout") or "")[-1000:],
            "stderr_preview": str(result.get("stderr") or "")[-1000:],
        }
        for name, result in command_results.items()
    }


def _manual_refresh_commands() -> list[str]:
    return [
        "sudo mkdir -p /tmp/hammer-r292-systemd-backup",
        "sudo cp -a /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service /tmp/hammer-r292-systemd-backup/hammer-autonomous-trigger-scheduler-dry-run.service",
        "sudo cp -a /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer /tmp/hammer-r292-systemd-backup/hammer-autonomous-trigger-scheduler-dry-run.timer",
        "sudo systemctl stop hammer-autonomous-trigger-scheduler-dry-run.timer",
        "sudo install -m 0644 ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service",
        "sudo install -m 0644 ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer",
        "sudo systemctl daemon-reload",
        "sudo systemctl start hammer-autonomous-trigger-scheduler-dry-run.timer",
        "systemctl status hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager -l",
        "systemctl list-timers hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager --all",
        "journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service -n 120 --no-pager",
    ]


def _manual_rollback_commands() -> list[str]:
    return [
        "sudo systemctl stop hammer-autonomous-trigger-scheduler-dry-run.timer",
        "sudo cp -a /tmp/hammer-r292-systemd-backup/hammer-autonomous-trigger-scheduler-dry-run.service /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service",
        "sudo cp -a /tmp/hammer-r292-systemd-backup/hammer-autonomous-trigger-scheduler-dry-run.timer /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer",
        "sudo systemctl daemon-reload",
        "sudo systemctl start hammer-autonomous-trigger-scheduler-dry-run.timer",
    ]


def _safety() -> dict[str, Any]:
    safety = dict(SAFETY)
    safety.update(
        {
            "codex_systemctl_mutation_performed": False,
            "codex_sudo_performed": False,
            "codex_install_performed": False,
            "dry_run_only": True,
            "live_execution_enabled": False,
            "final_command_available": False,
            "submit_allowed": False,
            "submit_attempted": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "leverage_change_called": False,
            "margin_change_called": False,
            "mutation_performed": False,
            "signed_trading_request_created": False,
            "signed_order_request_created": False,
            "signed_request_created": False,
            "signed_url_shown": False,
            "signature_shown": False,
            "secrets_shown": False,
            "secret_values_in_output": False,
            "env_written": False,
            "env_mutated": False,
            "lane_controls_written": False,
            "risk_contract_config_written": False,
            "live_config_written": False,
            "executable_payload_created": False,
            "per_signal_operator_approval_required": False,
            "real_order_forbidden": True,
            "paper_live_separation_intact": True,
        }
    )
    return safety


def _read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _sanitize(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))
