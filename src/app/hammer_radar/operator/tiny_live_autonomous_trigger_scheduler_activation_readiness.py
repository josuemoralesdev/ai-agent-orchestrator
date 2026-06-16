"""R290 manual systemd dry-run timer activation readiness packet.

This surface prepares operator instructions only. It does not install systemd
units, run sudo, call systemctl, mutate files, or contact Binance.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler import (
    CHECKLIST_PATH,
    PRINT_ONLY_INSTALL_PLAN_SCRIPT_PATH,
    SAFETY,
    SERVICE_TEMPLATE_PATH,
    SYSTEMD_TEMPLATE_FORBIDDEN_PATTERNS,
    TIMER_TEMPLATE_PATH,
)

EVENT_TYPE = "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER_ACTIVATION_READINESS"
CREATED_BY_PHASE = "R290_MANUAL_SYSTEMD_INSTALL_DRY_RUN_ACTIVATION_CHECKLIST"

ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL = "ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL"
ACTIVATION_READINESS_BLOCKED = "ACTIVATION_READINESS_BLOCKED"
ACTIVATION_READINESS_NOT_CHECKED = "ACTIVATION_READINESS_NOT_CHECKED"

ACTIVATION_CHECKLIST_PATH = Path(
    "docs/hammer_radar/live_readiness/R290_MANUAL_SYSTEMD_DRY_RUN_TIMER_ACTIVATION_CHECKLIST.md"
)
ACTIVATION_PRINT_ONLY_SCRIPT_PATH = Path(
    "scripts/hammer_print_r290_manual_systemd_dry_run_activation_plan.sh"
)

APPROVAL_API_EXPECTED_URL = "http://127.0.0.1:8015"

ACTIVATION_FORBIDDEN_PATTERNS = (
    *SYSTEMD_TEMPLATE_FORBIDDEN_PATTERNS,
    "BINANCE_API_SECRET=",
    "BINANCE_API_KEY=",
    "final-live-submit",
    "submit-live",
    "codex_install_performed: true",
    '"codex_install_performed": true',
    "codex_sudo_performed: true",
    '"codex_sudo_performed": true',
    "codex_systemctl_start_performed: true",
    '"codex_systemctl_start_performed": true',
    "codex_systemctl_enable_performed: true",
    '"codex_systemctl_enable_performed": true',
)


def build_autonomous_trigger_scheduler_activation_readiness(
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    paths = {
        "service_template_path": SERVICE_TEMPLATE_PATH,
        "timer_template_path": TIMER_TEMPLATE_PATH,
        "checklist_path": CHECKLIST_PATH,
        "print_only_install_plan_script_path": PRINT_ONLY_INSTALL_PLAN_SCRIPT_PATH,
        "activation_checklist_path": ACTIVATION_CHECKLIST_PATH,
        "activation_print_only_script_path": ACTIVATION_PRINT_ONLY_SCRIPT_PATH,
    }
    present = {
        "service_template_present": (root / SERVICE_TEMPLATE_PATH).exists(),
        "timer_template_present": (root / TIMER_TEMPLATE_PATH).exists(),
        "checklist_present": (root / CHECKLIST_PATH).exists(),
        "print_only_script_present": (root / PRINT_ONLY_INSTALL_PLAN_SCRIPT_PATH).exists(),
        "activation_checklist_present": (root / ACTIVATION_CHECKLIST_PATH).exists(),
        "activation_print_only_script_present": (root / ACTIVATION_PRINT_ONLY_SCRIPT_PATH).exists(),
    }
    scanned_paths = (
        SERVICE_TEMPLATE_PATH,
        TIMER_TEMPLATE_PATH,
        PRINT_ONLY_INSTALL_PLAN_SCRIPT_PATH,
        ACTIVATION_PRINT_ONLY_SCRIPT_PATH,
    )
    scanned_text = "\n".join(_read_text_if_exists(root / path) for path in scanned_paths)
    forbidden_hits = [
        pattern for pattern in ACTIVATION_FORBIDDEN_PATTERNS if pattern.lower() in scanned_text.lower()
    ]
    service_text = _read_text_if_exists(root / SERVICE_TEMPLATE_PATH)
    timer_text = _read_text_if_exists(root / TIMER_TEMPLATE_PATH)
    required_template_checks = {
        "service_type_oneshot": "Type=oneshot" in service_text,
        "service_uses_scheduler_once": "tiny-live-autonomous-trigger-scheduler-once" in service_text,
        "service_records_scheduler": "--record-autonomous-trigger-scheduler" in service_text,
        "service_reason_no_submit": "no submit" in service_text.lower(),
        "service_live_execution_false": "HAMMER_LIVE_EXECUTION_ENABLED=false" in service_text,
        "service_live_orders_false": "HAMMER_ALLOW_LIVE_ORDERS=false" in service_text,
        "service_global_kill_switch_true": "HAMMER_GLOBAL_KILL_SWITCH=true" in service_text,
        "timer_two_minute_interval": "OnUnitActiveSec=2min" in timer_text,
        "timer_persistent_false": "Persistent=false" in timer_text,
    }
    blockers = [
        key for key, value in {**present, **required_template_checks}.items() if value is not True
    ]
    blockers.extend(f"forbidden_pattern:{pattern}" for pattern in forbidden_hits)
    templates_safe = not forbidden_hits and all(required_template_checks.values())
    status = (
        ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL
        if not blockers
        else ACTIVATION_READINESS_BLOCKED
    )
    safety = _safety()
    manual_commands = _manual_commands()
    panel = {
        "activation_readiness_status": status,
        "activation_checklist_path": str(ACTIVATION_CHECKLIST_PATH),
        "activation_print_only_script_path": str(ACTIVATION_PRINT_ONLY_SCRIPT_PATH),
        "next_manual_operator_step": _next_step(status),
        "codex_install_performed": False,
        "codex_systemctl_start_performed": False,
        "codex_systemctl_enable_performed": False,
        "codex_sudo_performed": False,
        "dry_run_only": True,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }
    return _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "status": status,
            "generated_at": datetime.now(UTC).isoformat(),
            **{key: str(value) for key, value in paths.items()},
            **present,
            "templates_safe": templates_safe,
            "required_template_checks": required_template_checks,
            "forbidden_pattern_hits": forbidden_hits,
            "approval_api_expected_url": APPROVAL_API_EXPECTED_URL,
            "approval_api_check_command": "curl -sS http://127.0.0.1:8015/readiness | jq .",
            "scheduler_status_check_command": (
                "curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/status | jq ."
            ),
            "final_console_check_command": (
                "curl -sS http://127.0.0.1:8015/tiny-live/final-console | "
                "jq '.autonomous_trigger_scheduler_activation_panel'"
            ),
            **manual_commands,
            "codex_install_performed": False,
            "codex_systemctl_start_performed": False,
            "codex_systemctl_enable_performed": False,
            "codex_sudo_performed": False,
            "dry_run_only": True,
            "live_execution_enabled": False,
            "per_signal_operator_approval_required": False,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "next_manual_operator_step": _next_step(status),
            "blockers": blockers,
            "autonomous_trigger_scheduler_activation_panel": panel,
            "safety": safety,
        }
    )


def format_autonomous_trigger_scheduler_activation_readiness_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _manual_commands() -> dict[str, list[str]]:
    return {
        "manual_install_commands": [
            "sudo install -m 0644 ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service",
            "sudo install -m 0644 ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer",
            "sudo systemctl daemon-reload",
        ],
        "manual_start_commands": [
            "sudo /usr/bin/systemctl start hammer-autonomous-trigger-scheduler-dry-run.timer",
        ],
        "manual_status_commands": [
            "systemctl status hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager",
            "systemctl status hammer-autonomous-trigger-scheduler-dry-run.service --no-pager",
            "systemctl list-timers hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager",
            "journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service -n 120 --no-pager",
        ],
        "manual_tick_smoke_commands": [
            "sleep 150",
            "systemctl list-timers hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager",
            "journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service -n 120 --no-pager",
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-autonomous-trigger-scheduler-activation-readiness | jq .",
            "curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/status | jq .",
            "curl -sS http://127.0.0.1:8015/tiny-live/final-console | jq '.autonomous_trigger_scheduler_activation_panel'",
        ],
        "manual_rollback_commands": [
            "sudo systemctl disable --now hammer-autonomous-trigger-scheduler-dry-run.timer",
            "sudo systemctl stop hammer-autonomous-trigger-scheduler-dry-run.service",
            "sudo rm -f /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service",
            "sudo rm -f /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer",
            "sudo systemctl daemon-reload",
        ],
    }


def _next_step(status: str) -> str:
    if status == ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL:
        return (
            "Operator may run scripts/hammer_print_r290_manual_systemd_dry_run_activation_plan.sh, "
            "review every printed command, then manually install and start the dry-run timer."
        )
    return "Fix activation readiness blockers before any manual systemd install."


def _safety() -> dict[str, Any]:
    safety = dict(SAFETY)
    safety.update(
        {
            "codex_install_performed": False,
            "codex_systemctl_start_performed": False,
            "codex_systemctl_enable_performed": False,
            "codex_sudo_performed": False,
            "systemctl_called_by_codex": False,
            "sudo_called_by_codex": False,
            "installs_performed_by_codex": False,
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


def _read_text_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _sanitize(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))
