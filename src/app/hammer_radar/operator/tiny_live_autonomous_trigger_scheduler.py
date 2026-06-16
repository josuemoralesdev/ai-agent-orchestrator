"""R288 autonomous trigger scheduler dry-run loop.

This module wraps the R287 autonomous trigger loop in a bounded, append-only
scheduler surface. It never submits, signs, mutates config, creates executable
payloads, starts a daemon, or calls Binance mutation endpoints.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_loop import (
    MACHINE_ROLE,
    OPERATOR_ROLE,
    build_tiny_live_autonomous_trigger_loop,
)

EVENT_TYPE = "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER"
SYSTEMD_TEMPLATE_EVENT_TYPE = "TINY_LIVE_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_TEMPLATE_STATUS"
CREATED_BY_PHASE = "R288_AUTONOMOUS_TRIGGER_SCHEDULER_SERVICE_DRY_RUN_LOOP"
SYSTEMD_TEMPLATE_CREATED_BY_PHASE = "R289_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_TEMPLATE_AND_INSTALL_CHECKLIST"
LEDGER_FILENAME = "tiny_live_autonomous_trigger_scheduler.ndjson"

SERVICE_TEMPLATE_PATH = Path(
    "ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template"
)
TIMER_TEMPLATE_PATH = Path(
    "ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template"
)
CHECKLIST_PATH = Path(
    "docs/hammer_radar/live_readiness/R289_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_INSTALL_CHECKLIST.md"
)
PRINT_ONLY_INSTALL_PLAN_SCRIPT_PATH = Path(
    "scripts/hammer_print_autonomous_trigger_scheduler_systemd_install_plan.sh"
)

AUTONOMOUS_TRIGGER_SCHEDULER_IDLE = "AUTONOMOUS_TRIGGER_SCHEDULER_IDLE"
AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED = (
    "AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED"
)
AUTONOMOUS_TRIGGER_SCHEDULER_LOOP_COMPLETED = "AUTONOMOUS_TRIGGER_SCHEDULER_LOOP_COMPLETED"
AUTONOMOUS_TRIGGER_SCHEDULER_BLOCKED = "AUTONOMOUS_TRIGGER_SCHEDULER_BLOCKED"
AUTONOMOUS_TRIGGER_SCHEDULER_NOT_CHECKED = "AUTONOMOUS_TRIGGER_SCHEDULER_NOT_CHECKED"
SYSTEMD_TEMPLATE_READY = "SYSTEMD_TEMPLATE_READY"
SYSTEMD_TEMPLATE_BLOCKED = "SYSTEMD_TEMPLATE_BLOCKED"
SYSTEMD_TEMPLATE_NOT_CHECKED = "SYSTEMD_TEMPLATE_NOT_CHECKED"

DEFAULT_MAX_ITERATIONS = 1
PUBLIC_MAX_ITERATIONS_CAP = 20
MAX_SLEEP_SECONDS = 300.0

WAIT_FOR_NEXT_SCHEDULER_TICK = "WAIT_FOR_NEXT_SCHEDULER_TICK"
REVIEW_SCHEDULER_BLOCKERS = "REVIEW_SCHEDULER_BLOCKERS"

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "risk_contract_mutated": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "order_payload_created": False,
    "executable_payload_created": False,
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
    "kill_switch_disabled": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "real_order_forbidden": True,
    "per_signal_operator_approval_required": False,
}

UNSAFE_TRUE_KEYS = {
    "env_written",
    "env_mutated",
    "config_written",
    "risk_contract_config_written",
    "risk_contract_mutated",
    "lane_controls_written",
    "live_config_written",
    "order_payload_created",
    "executable_payload_created",
    "final_command_available",
    "submit_allowed",
    "submit_attempted",
    "order_placed",
    "real_order_placed",
    "execution_attempted",
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
    "kill_switch_disabled",
    "global_live_flags_changed",
    "per_signal_operator_approval_required",
}

SYSTEMD_TEMPLATE_FORBIDDEN_PATTERNS = (
    "/fapi/v1/order",
    "fapi/v1/order",
    "test-order",
    "test order endpoint",
    "leverage_change",
    "margin_change",
    "BINANCE_API_SECRET=",
    "BINANCE_API_KEY=",
    "final-live-submit",
    "submit-live",
    "sudo systemctl start",
    "sudo systemctl enable",
)


def build_tiny_live_autonomous_trigger_scheduler_once(
    *,
    log_dir: str | Path | None = None,
    fetch_binance_readonly_precision_mark_price: bool = False,
    confirm_tiny_live_binance_readonly_fetch: str | None = None,
    fetch_binance_readonly_account_position: bool = False,
    confirm_binance_readonly_account_position: str | None = None,
    load_discovered_binance_readonly_env: bool = False,
    binance_readonly_env_file: str | Path | None = None,
    record_autonomous_trigger_scheduler: bool = False,
    operator_id: str = "local_operator",
    reason: str | None = None,
    risk_contract_config_path: str | Path | None = None,
    autonomous_arming_config_path: str | Path | None = None,
    pre_activation_packet: Mapping[str, Any] | None = None,
    candidate_watch: Mapping[str, Any] | None = None,
    binance_readiness: Mapping[str, Any] | None = None,
    post_manual_verification: Mapping[str, Any] | None = None,
    iteration_id: str | None = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
    urlopen_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    trigger_loop = build_tiny_live_autonomous_trigger_loop(
        log_dir=resolved_log_dir,
        fetch_binance_readonly_precision_mark_price=fetch_binance_readonly_precision_mark_price,
        confirm_tiny_live_binance_readonly_fetch=confirm_tiny_live_binance_readonly_fetch,
        fetch_binance_readonly_account_position=fetch_binance_readonly_account_position,
        confirm_binance_readonly_account_position=confirm_binance_readonly_account_position,
        load_discovered_binance_readonly_env=load_discovered_binance_readonly_env,
        binance_readonly_env_file=binance_readonly_env_file,
        record_autonomous_trigger_loop=record_autonomous_trigger_scheduler,
        operator_id=operator_id,
        reason=reason,
        risk_contract_config_path=risk_contract_config_path,
        autonomous_arming_config_path=autonomous_arming_config_path,
        pre_activation_packet=pre_activation_packet,
        candidate_watch=candidate_watch,
        binance_readiness=binance_readiness,
        post_manual_verification=post_manual_verification,
        now=generated_at,
        env=env,
        urlopen_func=urlopen_func,
    )
    safety = _merged_safety(trigger_loop)
    unsafe = _unsafe_flags(safety)
    status = (
        AUTONOMOUS_TRIGGER_SCHEDULER_BLOCKED
        if unsafe
        else AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED
    )
    scheduler_iteration_id = iteration_id or f"r288_scheduler_iteration_{uuid4().hex}"
    telegram_payload = _telegram_payload(trigger_loop=trigger_loop, status=status)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "status": status,
            "iteration_id": scheduler_iteration_id,
            "generated_at": generated_at.isoformat(),
            "operator_role": OPERATOR_ROLE,
            "machine_role": MACHINE_ROLE,
            "per_signal_operator_approval_required": False,
            "autonomous_mode": "dry_run_only",
            "trigger_loop_status": trigger_loop.get("status"),
            "current_fresh_candidate_exists": trigger_loop.get("current_fresh_candidate_exists") is True,
            "current_candidate_lane_key": trigger_loop.get("current_candidate_lane_key"),
            "exact_lane_auto_armed": trigger_loop.get("exact_lane_auto_armed") is True,
            "autonomous_dry_run_execution_recorded": (
                trigger_loop.get("autonomous_dry_run_execution_recorded") is True
            ),
            "alert_visibility_only": True,
            "telegram_payload_prepared": bool(telegram_payload),
            "telegram_send_enabled": False,
            "telegram_compatible_payload": telegram_payload,
            "next_required_step": REVIEW_SCHEDULER_BLOCKERS if unsafe else WAIT_FOR_NEXT_SCHEDULER_TICK,
            "unsafe_flags_detected": unsafe,
            "trigger_loop_packet": trigger_loop,
            "record_autonomous_trigger_scheduler_requested": bool(record_autonomous_trigger_scheduler),
            "operator_intent": {
                "operator_id": str(operator_id or "local_operator"),
                "reason": str(reason or ""),
                "record_only": True,
                "scheduler_dry_run_only": True,
                "per_signal_approval": False,
            },
            "autonomous_trigger_scheduler_panel": _panel(
                status=status,
                trigger_loop=trigger_loop,
                iteration_summary={
                    "iterations_requested": 1,
                    "iterations_completed": 1,
                    "statuses_seen": [status],
                    "latest_status": status,
                    "latest_trigger_loop_status": trigger_loop.get("status"),
                    "latest_candidate_lane_key": trigger_loop.get("current_candidate_lane_key"),
                    "any_dry_run_execution_recorded": (
                        trigger_loop.get("autonomous_dry_run_execution_recorded") is True
                    ),
                    "any_unsafe_flag_detected": bool(unsafe),
                    "stopped_reason": "single_iteration_completed",
                },
            ),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safety": safety,
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_loop.py",
                "src/app/hammer_radar/operator/tiny_live_one_shot_pre_activation_gate.py",
                f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
            ],
        }
    )
    if record_autonomous_trigger_scheduler:
        payload = append_tiny_live_autonomous_trigger_scheduler(payload, log_dir=resolved_log_dir)
    return payload


def run_tiny_live_autonomous_trigger_scheduler_loop(
    *,
    log_dir: str | Path | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    sleep_seconds: float = 0.0,
    internal_allow_more_than_cap: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    requested = int(max_iterations)
    sleep_value = float(sleep_seconds)
    if requested < 1:
        raise ValueError("max_iterations must be >= 1")
    if requested > PUBLIC_MAX_ITERATIONS_CAP and not internal_allow_more_than_cap:
        raise ValueError("max_iterations must be <= 20")
    if sleep_value < 0:
        raise ValueError("sleep_seconds must be >= 0")
    if sleep_value > MAX_SLEEP_SECONDS:
        raise ValueError("sleep_seconds must be <= 300")

    iterations: list[dict[str, Any]] = []
    for index in range(requested):
        iteration = build_tiny_live_autonomous_trigger_scheduler_once(
            log_dir=resolved_log_dir,
            iteration_id=f"r288_scheduler_iteration_{index + 1}_{uuid4().hex}",
            **kwargs,
        )
        iterations.append(iteration)
        if sleep_value and index < requested - 1:
            time.sleep(sleep_value)

    statuses = [str(item.get("status") or "") for item in iterations]
    latest = iterations[-1] if iterations else {}
    unsafe = any(bool(item.get("unsafe_flags_detected")) for item in iterations)
    status = AUTONOMOUS_TRIGGER_SCHEDULER_BLOCKED if unsafe else AUTONOMOUS_TRIGGER_SCHEDULER_LOOP_COMPLETED
    summary = {
        "iterations_requested": requested,
        "iterations_completed": len(iterations),
        "statuses_seen": _dedupe(statuses),
        "latest_status": latest.get("status"),
        "latest_trigger_loop_status": latest.get("trigger_loop_status"),
        "latest_candidate_lane_key": latest.get("current_candidate_lane_key"),
        "any_dry_run_execution_recorded": any(
            item.get("autonomous_dry_run_execution_recorded") is True for item in iterations
        ),
        "any_unsafe_flag_detected": unsafe,
        "stopped_reason": "bounded_loop_completed",
    }
    return _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "status": status,
            "generated_at": datetime.now(UTC).isoformat(),
            "operator_role": OPERATOR_ROLE,
            "machine_role": MACHINE_ROLE,
            "per_signal_operator_approval_required": False,
            "autonomous_mode": "dry_run_only",
            **summary,
            "iterations": iterations,
            "autonomous_trigger_scheduler_panel": _panel(
                status=status,
                trigger_loop=latest.get("trigger_loop_packet") if isinstance(latest, Mapping) else {},
                iteration_summary=summary,
            ),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safety": _merged_safety(latest),
        }
    )


def load_latest_tiny_live_autonomous_trigger_scheduler(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_tiny_live_autonomous_trigger_scheduler_records(log_dir=log_dir, limit=1)
    return records[0] if records else {}


def load_tiny_live_autonomous_trigger_scheduler_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_autonomous_trigger_scheduler_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)]


def append_tiny_live_autonomous_trigger_scheduler(
    record: Mapping[str, Any], *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    payload = _sanitize(
        {
            **dict(record),
            "autonomous_trigger_scheduler_record_id": record.get("autonomous_trigger_scheduler_record_id")
            or f"r288_autonomous_trigger_scheduler_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safety": _merged_safety(record),
        }
    )
    path = tiny_live_autonomous_trigger_scheduler_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def tiny_live_autonomous_trigger_scheduler_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def build_latest_or_idle_autonomous_trigger_scheduler(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    latest = load_latest_tiny_live_autonomous_trigger_scheduler(log_dir=log_dir)
    if latest:
        latest["final_command_available"] = False
        latest["submit_allowed"] = False
        latest["real_order_forbidden"] = True
        latest["safety"] = _merged_safety(latest)
        return _sanitize(latest)
    return _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "status": AUTONOMOUS_TRIGGER_SCHEDULER_NOT_CHECKED,
            "generated_at": datetime.now(UTC).isoformat(),
            "operator_role": OPERATOR_ROLE,
            "machine_role": MACHINE_ROLE,
            "per_signal_operator_approval_required": False,
            "autonomous_mode": "dry_run_only",
            "trigger_loop_status": None,
            "current_fresh_candidate_exists": False,
            "current_candidate_lane_key": None,
            "exact_lane_auto_armed": False,
            "autonomous_dry_run_execution_recorded": False,
            "alert_visibility_only": True,
            "telegram_payload_prepared": False,
            "telegram_send_enabled": False,
            "next_required_step": "RUN_SCHEDULER_ONCE_OR_BOUNDED_LOOP",
            "autonomous_trigger_scheduler_panel": _idle_panel(),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safety": dict(SAFETY),
        }
    )


def build_autonomous_trigger_scheduler_systemd_template_status(
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    service_path = SERVICE_TEMPLATE_PATH
    timer_path = TIMER_TEMPLATE_PATH
    checklist_path = CHECKLIST_PATH
    script_path = PRINT_ONLY_INSTALL_PLAN_SCRIPT_PATH
    present = {
        "service_template_present": (root / service_path).exists(),
        "timer_template_present": (root / timer_path).exists(),
        "checklist_present": (root / checklist_path).exists(),
        "print_only_script_present": (root / script_path).exists(),
    }
    scanned_text = "\n".join(_read_text_if_exists(root / path) for path in (service_path, timer_path, script_path))
    forbidden_hits = [
        pattern for pattern in SYSTEMD_TEMPLATE_FORBIDDEN_PATTERNS if pattern.lower() in scanned_text.lower()
    ]
    service_text = _read_text_if_exists(root / service_path)
    timer_text = _read_text_if_exists(root / timer_path)
    required_hits = {
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
    blocked_reasons = [
        key for key, value in {**present, **required_hits}.items() if value is not True
    ]
    blocked_reasons.extend(f"forbidden_pattern:{pattern}" for pattern in forbidden_hits)
    status = SYSTEMD_TEMPLATE_READY if not blocked_reasons else SYSTEMD_TEMPLATE_BLOCKED
    safety = _merged_safety(
        {
            "safety": {
                "template_dry_run_only": True,
                "installs_performed_by_codex": False,
                "systemctl_called_by_codex": False,
                "sudo_called_by_codex": False,
                "live_execution_enabled": False,
            }
        }
    )
    safety.update(
        {
            "template_dry_run_only": True,
            "installs_performed_by_codex": False,
            "systemctl_called_by_codex": False,
            "sudo_called_by_codex": False,
            "live_execution_enabled": False,
        }
    )
    packet = {
        "event_type": SYSTEMD_TEMPLATE_EVENT_TYPE,
        "created_by_phase": SYSTEMD_TEMPLATE_CREATED_BY_PHASE,
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "service_template_path": str(service_path),
        "timer_template_path": str(timer_path),
        "checklist_path": str(checklist_path),
        "print_only_install_plan_script_path": str(script_path),
        **present,
        "template_dry_run_only": True,
        "installs_performed_by_codex": False,
        "systemctl_called_by_codex": False,
        "sudo_called_by_codex": False,
        "live_execution_enabled": False,
        "per_signal_operator_approval_required": False,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "required_template_checks": required_hits,
        "forbidden_pattern_hits": forbidden_hits,
        "blocked_reasons": blocked_reasons,
        "next_manual_operator_step": (
            "Review checklist and print-only install plan before any manual systemd install."
            if status == SYSTEMD_TEMPLATE_READY
            else "Fix missing or unsafe template/checklist/script content before install."
        ),
        "autonomous_trigger_scheduler_systemd_panel": {
            "template_status": status,
            "service_template_path": str(service_path),
            "timer_template_path": str(timer_path),
            "checklist_path": str(checklist_path),
            "print_only_install_plan_script_path": str(script_path),
            **present,
            "install_performed": False,
            "installs_performed_by_codex": False,
            "systemctl_called": False,
            "systemctl_called_by_codex": False,
            "sudo_called": False,
            "sudo_called_by_codex": False,
            "dry_run_only": True,
            "template_dry_run_only": True,
            "next_manual_operator_step": (
                "Run scripts/hammer_print_autonomous_trigger_scheduler_systemd_install_plan.sh, "
                "then follow the R289 checklist manually."
            ),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        },
        "safety": safety,
    }
    return _sanitize(packet)


def format_tiny_live_autonomous_trigger_scheduler_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _panel(
    *,
    status: str,
    trigger_loop: Mapping[str, Any],
    iteration_summary: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "scheduler_supported": True,
        "status": status,
        "latest_scheduler_status": status,
        "latest_trigger_loop_status": trigger_loop.get("status"),
        "iterations_summary": dict(iteration_summary),
        "operator_role": OPERATOR_ROLE,
        "machine_role": MACHINE_ROLE,
        "per_signal_operator_approval_required": False,
        "next_scheduler_command": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward tiny-live-autonomous-trigger-scheduler-once "
            "--record-autonomous-trigger-scheduler --operator-id local_operator "
            "--reason \"R288 autonomous trigger scheduler dry-run loop; no submit.\""
        ),
        "proposed_safe_loop_command": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward tiny-live-autonomous-trigger-scheduler-loop "
            "--max-iterations 2 --sleep-seconds 0 --record-autonomous-trigger-scheduler "
            "--operator-id local_operator --reason \"R288 bounded dry-run scheduler validation; no submit.\""
        ),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _idle_panel() -> dict[str, Any]:
    return _panel(
        status=AUTONOMOUS_TRIGGER_SCHEDULER_NOT_CHECKED,
        trigger_loop={},
        iteration_summary={
            "iterations_requested": 0,
            "iterations_completed": 0,
            "statuses_seen": [],
            "latest_status": AUTONOMOUS_TRIGGER_SCHEDULER_NOT_CHECKED,
            "latest_trigger_loop_status": None,
            "latest_candidate_lane_key": None,
            "any_dry_run_execution_recorded": False,
            "any_unsafe_flag_detected": False,
            "stopped_reason": "no_scheduler_packet_recorded",
        },
    )


def _telegram_payload(*, trigger_loop: Mapping[str, Any], status: str) -> dict[str, Any]:
    return {
        "channel": "telegram_compatible",
        "send_enabled": False,
        "sent": False,
        "status": "prepared_not_sent",
        "visibility_only": True,
        "message": "\n".join(
            [
                "Hammer Radar autonomous trigger scheduler dry-run tick",
                f"scheduler_status: {status}",
                f"trigger_loop_status: {trigger_loop.get('status') or 'n/a'}",
                f"lane: {trigger_loop.get('current_candidate_lane_key') or 'n/a'}",
                "No submit. No order. No executable payload.",
            ]
        ),
        "secrets_shown": False,
    }


def _merged_safety(record: Mapping[str, Any] | None) -> dict[str, Any]:
    safety = dict(SAFETY)
    if isinstance(record, Mapping):
        nested = record.get("safety")
        if isinstance(nested, Mapping):
            safety.update(dict(nested))
    safety.update(
        {
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
            "executable_payload_created": False,
            "real_order_forbidden": True,
            "per_signal_operator_approval_required": False,
        }
    )
    return _sanitize(safety)


def _unsafe_flags(safety: Mapping[str, Any]) -> list[str]:
    return sorted(key for key in UNSAFE_TRUE_KEYS if safety.get(key) is True)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _read_text_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _sanitize(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))
