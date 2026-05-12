"""R79 final protected live gate review for Hammer Radar.

This module aggregates funding, balance, R78 rehearsal/test-order/protective
readiness, and live env posture into a final review-only gate. It never places
orders, flips env switches, signs payloads, or calls Binance network endpoints.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.funded_tiny_live_readiness import build_funded_tiny_live_readiness_status
from src.app.hammer_radar.operator.live_policy_arming import build_live_policy_arming_status
from src.app.hammer_radar.operator.post_funding_balance_verification import (
    build_post_funding_balance_status,
    evaluate_manual_balance,
)
from src.app.hammer_radar.operator.rehearsal_test_order_protective_readiness import (
    build_rehearsal_test_order_protective_status,
    read_recent_ndjson,
)

PHASE = "R79"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "FINAL_PROTECTED_LIVE_GATE_REVIEW_ONLY"
CHECKS_FILENAME = "final_protected_live_gate_checks.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False


def build_final_protected_live_gate_status(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    return _evaluate(env=env, log_dir=log_dir, available_usdt=None, signal_id=None, execution_intent_id=None, persist=False)


def build_final_protected_live_gate_check(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
    available_usdt: object | None = None,
    signal_id: str | None = None,
    execution_intent_id: str | None = None,
) -> dict[str, Any]:
    return _evaluate(
        env=env,
        log_dir=log_dir,
        available_usdt=available_usdt,
        signal_id=signal_id,
        execution_intent_id=execution_intent_id,
        persist=True,
    )


def build_final_protected_live_gate_runbook(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    status = build_final_protected_live_gate_status(env=env, log_dir=log_dir)
    return _sanitize(
        {
            **status,
            "runbook_name": "R79_FINAL_PROTECTED_LIVE_GATE_REVIEW",
            "manual_steps": [
                "LIVE FINAL GATE",
                "LIVE FINAL CHECK",
                "Verify R76 READY_TO_FUND and R77 READY_AFTER_FUNDING.",
                "Verify R78 chain, rehearsal, test-order, protective readiness.",
                "Keep live execution disabled until a future R80 arming procedure.",
                "Do not place a real order from R79.",
            ],
            "remaining_future_gate": "R80 exact one-attempt live arming procedure",
        }
    )


def load_final_protected_live_gate_checks(
    *,
    limit: int = 50,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = final_protected_live_gate_checks_path(get_log_dir(log_dir, use_env=True))
    records = read_recent_ndjson(path, max_lines=limit if limit > 0 else 500)
    return records[:limit] if limit > 0 else records


def final_protected_live_gate_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHECKS_FILENAME


def append_final_protected_live_gate_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = final_protected_live_gate_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(record), sort_keys=True) + "\n")


def format_final_protected_live_gate_operator_message(payload: Mapping[str, Any], *, section: str = "status") -> str:
    checks = payload.get("ready_checks") if isinstance(payload.get("ready_checks"), dict) else {}
    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    blocker_text = "; ".join(str(item) for item in blockers[:5]) if blockers else "none"
    if section == "runbook":
        steps = payload.get("manual_steps") if isinstance(payload.get("manual_steps"), list) else payload.get("required_next_steps") or []
        return "\n".join(
            [
                f"R79 final gate runbook: {payload.get('status')}",
                "R79_FINAL_GATE_REVIEW_ONLY. No order placed. real_order_placed=false. execution_attempted=false.",
                "next: " + "; ".join(str(item) for item in steps[:5]),
                "R80 remains the future exact one-attempt live arming procedure.",
            ]
        )
    return "\n".join(
        [
            f"R79 final protected live gate: {payload.get('status')}",
            "R79_FINAL_GATE_REVIEW_ONLY. No order placed. real_order_placed=false. execution_attempted=false.",
            (
                "checks: "
                f"balance={checks.get('balance_ready')} chain={checks.get('chain_ready')} "
                f"rehearsal={checks.get('rehearsal_ready')} test_order={checks.get('test_order_ready')} "
                f"protective={checks.get('protective_ready')}"
            ),
            f"next: {'; '.join(str(item) for item in (payload.get('required_next_steps') or [])[:3]) or 'none'}",
            f"blockers: {blocker_text}",
        ]
    )


def _evaluate(
    *,
    env: Mapping[str, str] | None,
    log_dir: str | Path | None,
    available_usdt: object | None,
    signal_id: str | None,
    execution_intent_id: str | None,
    persist: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    funding = _compact_funding_readiness(build_funded_tiny_live_readiness_status(env=source, log_dir=resolved_log_dir))
    balance = _compact_balance(
        evaluate_manual_balance(available_usdt, env=source, log_dir=resolved_log_dir)
        if available_usdt is not None
        else build_post_funding_balance_status(env=source, log_dir=resolved_log_dir)
    )
    rehearsal = _compact_rehearsal_readiness(build_rehearsal_test_order_protective_status(env=source, log_dir=resolved_log_dir))
    live_env = _live_env(source)
    ready_checks = _ready_checks(funding=funding, balance=balance, rehearsal=rehearsal, live_env=live_env)
    blockers = _blockers(live_env=live_env, rehearsal=rehearsal, ready_checks=ready_checks)
    warnings = _warnings(funding=funding, balance=balance, rehearsal=rehearsal)
    status = _status(ready_checks=ready_checks, blockers=blockers)
    payload = _sanitize(
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
            "funding_readiness": funding,
            "balance_verification": balance,
            "rehearsal_readiness": rehearsal,
            "live_env": live_env,
            "final_gate_conditions": _final_gate_conditions(),
            "ready_checks": ready_checks,
            "required_next_steps": _required_next_steps(status),
            "blockers": blockers,
            "warnings": warnings,
            "performance": {
                "mode": "fast",
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "bounded_scans": True,
                "heavy_builders_skipped": True,
            },
            "audit_event_recorded": persist,
            "final_protected_live_gate_checks_path": str(final_protected_live_gate_checks_path(resolved_log_dir)),
        }
    )
    if persist:
        record = _record(payload)
        append_final_protected_live_gate_check(record, log_dir=resolved_log_dir)
        payload["check_id"] = record["check_id"]
    return _sanitize(payload)


def _compact_funding_readiness(payload: Mapping[str, Any]) -> dict[str, Any]:
    checks = payload.get("ready_checks") if isinstance(payload.get("ready_checks"), dict) else {}
    return {
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "funding_ready": payload.get("status") == "READY_TO_FUND",
        "live_execution_disabled": checks.get("live_execution_disabled"),
        "global_kill_switch_active": checks.get("global_kill_switch_active"),
        "blockers": payload.get("blockers") if isinstance(payload.get("blockers"), list) else [],
        "warnings": payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def _compact_balance(payload: Mapping[str, Any]) -> dict[str, Any]:
    balance = payload.get("balance_status") if isinstance(payload.get("balance_status"), dict) else {}
    return {
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "available_usdt": balance.get("available_usdt"),
        "buffer_usdt": balance.get("buffer_usdt"),
        "enough_for_first_margin": balance.get("enough_for_first_margin"),
        "preferred_buffer_ok": balance.get("preferred_buffer_ok"),
        "balance_ready": payload.get("status") == "READY_AFTER_FUNDING",
        "blockers": payload.get("blockers") if isinstance(payload.get("blockers"), list) else [],
        "warnings": payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def _compact_rehearsal_readiness(payload: Mapping[str, Any]) -> dict[str, Any]:
    chain = payload.get("chain_state") if isinstance(payload.get("chain_state"), dict) else {}
    rehearsal = payload.get("rehearsal_status") if isinstance(payload.get("rehearsal_status"), dict) else {}
    test_order = payload.get("test_order_status") if isinstance(payload.get("test_order_status"), dict) else {}
    protective = payload.get("protective_status") if isinstance(payload.get("protective_status"), dict) else {}
    no_naked = payload.get("no_naked_entry_status") if isinstance(payload.get("no_naked_entry_status"), dict) else {}
    return {
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "signal_id": chain.get("signal_id"),
        "execution_intent_id": chain.get("execution_intent_id"),
        "executor_rehearsal_id": chain.get("executor_rehearsal_id"),
        "chain_ready": chain.get("execution_intent_found") is True,
        "rehearsal_ready": rehearsal.get("rehearsal_ready") is True,
        "test_order_ready": test_order.get("test_order_validated_for_signal") is True,
        "protective_ready": protective.get("protective_payloads_ready") is True,
        "no_naked_entry_ok": no_naked.get("entry_allowed_without_protective") is not True,
        "blockers": payload.get("blockers") if isinstance(payload.get("blockers"), list) else [],
        "warnings": payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def _live_env(source: Mapping[str, str]) -> dict[str, Any]:
    arming = build_live_policy_arming_status(env=source)
    execution_env = arming.get("execution_env") if isinstance(arming.get("execution_env"), dict) else {}
    return {
        "binance_live_enabled": execution_env.get("binance_live_enabled") is True,
        "live_execution_enabled": execution_env.get("live_execution_enabled") is True,
        "allow_live_orders": execution_env.get("allow_live_orders") is True,
        "global_kill_switch": execution_env.get("global_kill_switch") is not False,
        "connector_mode": execution_env.get("connector_mode") or "DRY_RUN_ONLY",
        "protective_orders_enabled": execution_env.get("protective_orders_enabled") is True,
        "protective_order_mode": execution_env.get("protective_order_mode") or "PREVIEW_ONLY",
    }


def _final_gate_conditions() -> dict[str, bool]:
    return {
        "exact_signal_required": True,
        "approval_required": True,
        "intent_required": True,
        "rehearsal_required": True,
        "test_order_required": True,
        "protective_orders_required": True,
        "manual_env_review_required": True,
        "manual_final_confirmation_required": True,
        "one_attempt_only": True,
        "no_naked_entry": True,
    }


def _ready_checks(*, funding: Mapping[str, Any], balance: Mapping[str, Any], rehearsal: Mapping[str, Any], live_env: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "funding_ready": funding.get("funding_ready") is True,
        "balance_ready": balance.get("balance_ready") is True,
        "chain_ready": rehearsal.get("chain_ready") is True,
        "rehearsal_ready": rehearsal.get("rehearsal_ready") is True,
        "test_order_ready": rehearsal.get("test_order_ready") is True,
        "protective_ready": rehearsal.get("protective_ready") is True,
        "no_naked_entry_ok": rehearsal.get("no_naked_entry_ok") is True,
        "live_execution_still_disabled": live_env.get("live_execution_enabled") is False and live_env.get("allow_live_orders") is False,
        "kill_switch_still_active": live_env.get("global_kill_switch") is True,
        "manual_final_gate_required": True,
    }


def _blockers(*, live_env: Mapping[str, Any], rehearsal: Mapping[str, Any], ready_checks: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if live_env.get("live_execution_enabled") is True:
        blockers.append("HAMMER_LIVE_EXECUTION_ENABLED is true before final gate")
    if live_env.get("allow_live_orders") is True:
        blockers.append("HAMMER_ALLOW_LIVE_ORDERS is true before final gate")
    if live_env.get("global_kill_switch") is not True:
        blockers.append("HAMMER_GLOBAL_KILL_SWITCH is not active before final gate")
    blockers.extend(str(item) for item in rehearsal.get("blockers") or [])
    if ready_checks.get("no_naked_entry_ok") is not True:
        blockers.append("no naked entry check failed")
    return list(dict.fromkeys(item for item in blockers if item))


def _warnings(*, funding: Mapping[str, Any], balance: Mapping[str, Any], rehearsal: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    if funding.get("funding_ready") is not True:
        warnings.append("R76 funding readiness is not READY_TO_FUND")
    if balance.get("balance_ready") is not True:
        warnings.append("R77 balance verification is not READY_AFTER_FUNDING")
    warnings.extend(str(item) for item in funding.get("warnings") or [])
    warnings.extend(str(item) for item in balance.get("warnings") or [])
    warnings.extend(str(item) for item in rehearsal.get("warnings") or [])
    warnings.append("R79 does not arm live execution; R80 remains required")
    return list(dict.fromkeys(item for item in warnings if item))


def _status(*, ready_checks: Mapping[str, Any], blockers: list[str]) -> str:
    hard = [item for item in blockers if "LIVE_EXECUTION_ENABLED" in item or "ALLOW_LIVE_ORDERS" in item or "KILL_SWITCH" in item or "order placement" in item or "naked" in item]
    if hard:
        return "BLOCKED"
    if ready_checks.get("chain_ready") is not True:
        return "AWAITING_CHAIN"
    if ready_checks.get("rehearsal_ready") is not True:
        return "AWAITING_REHEARSAL"
    if ready_checks.get("test_order_ready") is not True:
        return "AWAITING_TEST_ORDER"
    if ready_checks.get("protective_ready") is not True:
        return "AWAITING_PROTECTIVE_READY"
    if ready_checks.get("live_execution_still_disabled") is True and ready_checks.get("kill_switch_still_active") is True:
        return "AWAITING_MANUAL_ENV_ARMING"
    return "READY_FOR_FINAL_OPERATOR_REVIEW"


def _required_next_steps(status: str) -> list[str]:
    if status == "AWAITING_CHAIN":
        return ["FIRST LIVE NEXT", "LIVE APPROVE <signal_id>", "LIVE INTENT <signal_id>"]
    if status == "AWAITING_REHEARSAL":
        return ["LIVE REHEARSAL <intent_id>", "LIVE FINAL CHECK"]
    if status == "AWAITING_TEST_ORDER":
        return ["FIRST LIVE TEST ORDER", "LIVE FINAL CHECK"]
    if status == "AWAITING_PROTECTIVE_READY":
        return ["FIRST LIVE PROTECTIVE CHECK", "LIVE PROTECTIVE READINESS", "LIVE FINAL CHECK"]
    if status == "AWAITING_MANUAL_ENV_ARMING":
        return ["manual env/funds review", "keep live execution disabled until R80", "prepare R80 one-attempt arming procedure"]
    if status == "READY_FOR_FINAL_OPERATOR_REVIEW":
        return ["manual final operator review", "do not execute from R79", "R80 required before arming"]
    return ["resolve blockers before continuing"]


def _record(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "final_protected_live_gate_check",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "funding_readiness": payload.get("funding_readiness"),
        "balance_verification": payload.get("balance_verification"),
        "rehearsal_readiness": payload.get("rehearsal_readiness"),
        "live_env": payload.get("live_env"),
        "final_gate_conditions": payload.get("final_gate_conditions"),
        "ready_checks": payload.get("ready_checks"),
        "required_next_steps": payload.get("required_next_steps"),
        "blockers": payload.get("blockers"),
        "warnings": payload.get("warnings"),
        "performance": payload.get("performance"),
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "network_allowed": False,
        "secrets_shown": False,
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered == "secrets_shown":
                sanitized[key] = False
                continue
            if any(token in lowered for token in ("secret", "token", "api_key", "apikey", "signature", "auth", "query_string")):
                continue
            sanitized[key] = _sanitize(item)
        for key in ("order_placed", "real_order_placed", "execution_attempted", "network_allowed", "secrets_shown"):
            if key in sanitized:
                sanitized[key] = False
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
