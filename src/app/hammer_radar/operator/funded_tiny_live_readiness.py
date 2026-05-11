"""R76 funded tiny-live readiness checklist.

This module evaluates whether the operator is ready to fund controlled tiny
live test capital. It never places orders, edits env files, signs payloads,
funds accounts, restarts services, or calls Binance live endpoints.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.live_policy_arming import build_live_policy_arming_status
from src.app.hammer_radar.operator.live_policy_dry_chain_smoke import load_policy_armed_dry_chain_smokes

PHASE = "R76"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "FUNDED_READINESS_CHECKLIST_ONLY"
CHECKS_FILENAME = "funded_tiny_live_readiness_checks.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

FUNDING_RECOMMENDATION = {
    "minimum_operational_test_usdt": 25.0,
    "maximum_minimum_operational_test_usdt": 50.0,
    "preferred_initial_test_usdt": 88.0,
    "do_not_exceed_initial_funding_usdt": 100.0,
    "do_not_use_444_or_888_margin_yet": True,
    "reason": "first live profile uses 44 USDT margin and requires buffer",
}

FIRST_LIVE_PROFILE = {
    "margin_usdt": 44.0,
    "leverage": 10,
    "max_notional_usdt": 444.0,
    "margin_mode": "ISOLATED",
    "protective_orders_required": True,
    "one_attempt_only": True,
}

SERVICE_STATUS_COMMANDS = [
    "systemctl is-active hammer-approval-api.service",
    "systemctl is-active hammer-telegram-polling.service",
    "systemctl is-active hammer-paper-refresh.service",
    "systemctl is-active radar.service",
]


def build_funded_tiny_live_readiness_status(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    arming = build_live_policy_arming_status(env=source)
    policy_env = arming.get("policy_env") if isinstance(arming.get("policy_env"), dict) else {}
    execution_env = arming.get("execution_env") if isinstance(arming.get("execution_env"), dict) else {}
    dry_smoke = _dry_smoke_status(log_dir=resolved_log_dir)
    ready_checks = _ready_checks(policy_env=policy_env, execution_env=execution_env, dry_smoke=dry_smoke)
    blockers = _blockers(execution_env=execution_env, dry_smoke=dry_smoke, policy_env=policy_env)
    warnings = _warnings(execution_env=execution_env, dry_smoke=dry_smoke)
    status = _status(blockers=blockers, warnings=warnings, ready_checks=ready_checks)
    return _sanitize(
        {
            "status": status,
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "created_at": datetime.now(UTC).isoformat(),
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "execution_attempted": EXECUTION_ATTEMPTED,
            "network_allowed": NETWORK_ALLOWED,
            "secrets_shown": SECRETS_SHOWN,
            "funding_recommendation": dict(FUNDING_RECOMMENDATION),
            "first_live_profile": dict(FIRST_LIVE_PROFILE),
            "policy_env": policy_env,
            "execution_env": execution_env,
            "dry_smoke": dry_smoke,
            "required_before_funding": [
                "verify services active manually",
                "verify /health OK",
                "verify /live/timeframe-policy/status",
                "verify /live/policy-arming/status",
                "verify /live/policy-dry-chain/status",
                "run recent R75 micro dry smoke",
                "run recent R75 higher dry smoke if higher policy is planned",
                "verify order and execution flags remain false",
            ],
            "required_after_funding_before_live_order": [
                "verify balance manually in Binance UI or a known safe readonly checker",
                "keep live execution disabled",
                "keep global kill switch active until final live gate",
                "wait for exact candidate",
                "complete R52 intent",
                "complete R53 rehearsal",
                "verify payload readiness",
                "validate test order",
                "verify protective readiness",
                "complete manual env/funds review",
                "pass final protected gate",
            ],
            "ready_checks": ready_checks,
            "manual_service_status_commands": list(SERVICE_STATUS_COMMANDS),
            "blockers": blockers,
            "warnings": warnings,
            "operator_action": _operator_action({"status": status}),
        }
    )


def build_funded_tiny_live_readiness_check(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    payload = build_funded_tiny_live_readiness_status(env=env, log_dir=resolved_log_dir)
    record = _check_record(payload)
    append_funded_tiny_live_readiness_check(record, log_dir=resolved_log_dir)
    payload["audit_event_recorded"] = True
    payload["funded_tiny_live_readiness_check_id"] = record["check_id"]
    payload["funded_tiny_live_readiness_checks_path"] = str(funded_tiny_live_readiness_checks_path(resolved_log_dir))
    return _sanitize(payload)


def build_funded_tiny_live_readiness_runbook(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    status = build_funded_tiny_live_readiness_status(env=env, log_dir=log_dir)
    return _sanitize(
        {
            **status,
            "runbook_name": "R76_FUNDED_TINY_LIVE_READINESS",
            "pre_funding_steps": [
                "Run manual service active checks.",
                "Verify /health, /live/timeframe-policy/status, /live/policy-arming/status, and /live/policy-dry-chain/status.",
                "Run R75 micro dry smoke.",
                "Run R75 higher dry smoke if higher policy is planned.",
                "Confirm order_placed=false, real_order_placed=false, execution_attempted=false.",
                "Confirm live execution disabled and global kill switch active.",
            ],
            "funding_steps": [
                "Deposit 25-50 USDT only for minimum operational test, or 88 USDT preferred initial tiny test amount.",
                "Do not fund 444/888 USDT sizing tiers yet.",
                "Do not enable live execution during deposit.",
            ],
            "post_funding_steps": [
                "Verify balance manually in Binance UI or a known safe readonly checker.",
                "Run LIVE FUNDING CHECK again.",
                "Wait for a fresh exact candidate.",
                "Walk approval, intent, rehearsal, payload readiness, test-order, protective readiness, manual review, and final gate.",
            ],
            "rollback_steps": [
                "Keep HAMMER_LIVE_EXECUTION_ENABLED=false.",
                "Keep HAMMER_ALLOW_LIVE_ORDERS=false.",
                "Keep HAMMER_GLOBAL_KILL_SWITCH=true.",
                "Disable policy env switches if behavior is unexpected.",
                "Do not attempt a live order until R77/R78 final gates pass.",
            ],
        }
    )


def load_funded_tiny_live_readiness_checks(
    *,
    limit: int = 50,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = funded_tiny_live_readiness_checks_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(_sanitize(json.loads(line)))
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def funded_tiny_live_readiness_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHECKS_FILENAME


def append_funded_tiny_live_readiness_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = funded_tiny_live_readiness_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(record), sort_keys=True) + "\n")


def format_funded_tiny_live_readiness_operator_message(payload: Mapping[str, Any], *, section: str = "status") -> str:
    recommendation = payload.get("funding_recommendation") if isinstance(payload.get("funding_recommendation"), dict) else {}
    checks = payload.get("ready_checks") if isinstance(payload.get("ready_checks"), dict) else {}
    if section == "runbook":
        return "\n".join(
            [
                f"R76 funding runbook: {payload.get('status')}",
                "FUNDING_CHECK_ONLY. No order placed. real_order_placed=false.",
                "funding: 25-50 USDT minimum test, 88 USDT preferred, do not fund 444/888 yet.",
                "next: run R75 dry smoke, deposit only tiny test capital, then rerun LIVE FUNDING CHECK.",
            ]
        )
    return "\n".join(
        [
            f"R76 funding readiness: {payload.get('status')}",
            "FUNDING_CHECK_ONLY. No order placed. real_order_placed=false.",
            (
                f"recommended: {recommendation.get('preferred_initial_test_usdt')} USDT preferred, "
                f"max initial {recommendation.get('do_not_exceed_initial_funding_usdt')} USDT"
            ),
            (
                f"execution_disabled={checks.get('live_execution_disabled')} "
                f"kill_switch_active={checks.get('global_kill_switch_active')} "
                f"dry_smoke_recent={checks.get('dry_chain_smoke_recent')}"
            ),
            f"next: {payload.get('operator_action') or _operator_action(payload)}",
        ]
    )


def _dry_smoke_status(*, log_dir: Path) -> dict[str, Any]:
    records = load_policy_armed_dry_chain_smokes(limit=50, log_dir=log_dir)
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    micro_ok = False
    higher_ok = False
    latest_at: str | None = None
    clean_flags = True
    for record in records:
        created = _parse_datetime(record.get("created_at"))
        if created is None or created < cutoff:
            continue
        latest_at = latest_at or record.get("created_at")
        clean_flags = clean_flags and _clean_record_flags(record)
        micro_ok = micro_ok or _scenario_ok(record, "micro")
        higher_ok = higher_ok or _scenario_ok(record, "higher")
    return {
        "recent_window_hours": 24,
        "record_count": len(records),
        "latest_recent_created_at": latest_at,
        "micro_recent_ok": micro_ok,
        "higher_recent_ok": higher_ok,
        "any_recent_ok": micro_ok or higher_ok,
        "clean_safety_flags": clean_flags,
    }


def _scenario_ok(record: Mapping[str, Any], scenario: str) -> bool:
    if record.get("scenario") == scenario and record.get("status") == "OK":
        return _clean_record_flags(record)
    results = record.get("results") if isinstance(record.get("results"), dict) else {}
    child = results.get(scenario) if isinstance(results.get(scenario), dict) else {}
    return child.get("status") == "OK" and _clean_record_flags(child)


def _clean_record_flags(record: Mapping[str, Any]) -> bool:
    return (
        record.get("order_placed") is False
        and record.get("real_order_placed") is False
        and record.get("execution_attempted") is False
        and record.get("secrets_shown") is False
    )


def _ready_checks(*, policy_env: Mapping[str, Any], execution_env: Mapping[str, Any], dry_smoke: Mapping[str, Any]) -> dict[str, Any]:
    higher_planned = policy_env.get("higher_timeframe_live_allowed") is True
    dry_recent = dry_smoke.get("micro_recent_ok") is True and (not higher_planned or dry_smoke.get("higher_recent_ok") is True)
    return {
        "services_active_required": True,
        "policy_matrix_available": True,
        "policy_arming_available": True,
        "dry_chain_smoke_available": True,
        "dry_chain_smoke_recent": dry_recent,
        "micro_dry_chain_smoke_recent": dry_smoke.get("micro_recent_ok") is True,
        "higher_dry_chain_smoke_recent": dry_smoke.get("higher_recent_ok") is True,
        "telegram_polling_expected": True,
        "live_execution_disabled": execution_env.get("live_execution_enabled") is False and execution_env.get("allow_live_orders") is False,
        "global_kill_switch_active": execution_env.get("global_kill_switch") is True,
        "protective_orders_required": True,
        "test_order_required": True,
        "manual_final_gate_required": True,
    }


def _blockers(*, execution_env: Mapping[str, Any], dry_smoke: Mapping[str, Any], policy_env: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if execution_env.get("live_execution_enabled") is True:
        blockers.append("HAMMER_LIVE_EXECUTION_ENABLED is true; funding readiness expects execution disabled")
    if execution_env.get("allow_live_orders") is True:
        blockers.append("HAMMER_ALLOW_LIVE_ORDERS is true; funding readiness expects live orders disabled")
    if execution_env.get("global_kill_switch") is not True:
        blockers.append("HAMMER_GLOBAL_KILL_SWITCH is not active")
    if dry_smoke.get("clean_safety_flags") is not True:
        blockers.append("recent dry smoke safety flags are not clean")
    if dry_smoke.get("micro_recent_ok") is not True:
        blockers.append("recent R75 micro dry smoke OK is missing")
    if policy_env.get("higher_timeframe_live_allowed") is True and dry_smoke.get("higher_recent_ok") is not True:
        blockers.append("recent R75 higher dry smoke OK is missing while higher policy is planned")
    return blockers


def _warnings(*, execution_env: Mapping[str, Any], dry_smoke: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    if dry_smoke.get("any_recent_ok") is not True:
        warnings.append("run R75 dry smoke before funding")
    if execution_env.get("binance_live_enabled") is True:
        warnings.append("HAMMER_BINANCE_LIVE_ENABLED is true; keep live execution arming separate from funding")
    if execution_env.get("protective_orders_enabled") is True:
        warnings.append("protective order live env appears enabled; R76 expects checklist-only posture")
    return warnings


def _status(*, blockers: list[str], warnings: list[str], ready_checks: Mapping[str, Any]) -> str:
    hard = [item for item in blockers if "LIVE_EXECUTION_ENABLED" in item or "ALLOW_LIVE_ORDERS" in item or "KILL_SWITCH" in item or "safety flags" in item]
    if hard:
        return "BLOCKED"
    if ready_checks.get("dry_chain_smoke_recent") is True and ready_checks.get("live_execution_disabled") is True:
        return "READY_TO_FUND"
    if blockers:
        return "READY_FOR_POLICY_ARMING_ONLY"
    if warnings:
        return "READY_FOR_POLICY_ARMING_ONLY"
    return "NOT_READY_TO_FUND"


def _operator_action(payload: Mapping[str, Any]) -> str:
    status = payload.get("status")
    if status == "READY_TO_FUND":
        return "fund only controlled tiny test capital, then rerun readiness"
    if status == "BLOCKED":
        return "restore disabled execution flags and active kill switch"
    return "run R75 dry smoke and verify policy arming"


def _check_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "funded_tiny_live_readiness_check",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "funding_recommendation": payload.get("funding_recommendation"),
        "first_live_profile": payload.get("first_live_profile"),
        "ready_checks": payload.get("ready_checks"),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in ("order_placed", "real_order_placed", "execution_attempted", "network_allowed", "secrets_shown"):
            if key in sanitized:
                sanitized[key] = False
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
