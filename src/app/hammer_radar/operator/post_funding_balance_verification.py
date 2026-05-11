"""R77 post-funding balance verification gate.

This module evaluates operator-provided USDT balance for the first controlled
tiny live test. It never places orders, signs payloads, edits env files, funds
accounts, or calls Binance network endpoints.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.live_policy_arming import build_live_policy_arming_status

PHASE = "R77"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "POST_FUNDING_BALANCE_VERIFICATION_ONLY"
CHECKS_FILENAME = "post_funding_balance_checks.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

MINIMUM_REQUIRED_AVAILABLE_USDT = 44.0
PREFERRED_AVAILABLE_USDT = 88.0
DO_NOT_EXCEED_INITIAL_FUNDING_USDT = 100.0

FIRST_LIVE_PROFILE = {
    "margin_usdt": 44.0,
    "leverage": 10,
    "max_notional_usdt": 444.0,
    "margin_mode": "ISOLATED",
    "protective_orders_required": True,
    "one_attempt_only": True,
}


def build_post_funding_balance_status(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    source = os.environ if env is None else env
    arming = build_live_policy_arming_status(env=source)
    execution_env = arming.get("execution_env") if isinstance(arming.get("execution_env"), dict) else {}
    blockers = _execution_blockers(execution_env)
    status = "BLOCKED" if blockers else "AWAITING_BALANCE_INPUT"
    return _base_payload(
        status=status,
        available_usdt=None,
        execution_env=execution_env,
        blockers=blockers,
        warnings=[],
        balance_source="manual_required",
    )


def evaluate_manual_balance(
    available_usdt: object,
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    source = os.environ if env is None else env
    arming = build_live_policy_arming_status(env=source)
    execution_env = arming.get("execution_env") if isinstance(arming.get("execution_env"), dict) else {}
    blockers = _execution_blockers(execution_env)
    parsed = _float_or_none(available_usdt)
    warnings: list[str] = []
    if parsed is None:
        blockers.append("available_usdt must be a number")
        status = "BLOCKED"
    elif parsed < 0:
        blockers.append("available_usdt must be non-negative")
        status = "BLOCKED"
    elif blockers:
        status = "BLOCKED"
    elif parsed < MINIMUM_REQUIRED_AVAILABLE_USDT:
        status = "NOT_ENOUGH_BALANCE"
        blockers.append("available USDT is below first-live 44 USDT margin")
    elif parsed < PREFERRED_AVAILABLE_USDT:
        status = "MARGINAL_BALANCE"
        warnings.append("available USDT covers 44 margin but is below preferred 88 USDT funding buffer")
    else:
        status = "READY_AFTER_FUNDING"
        if parsed > DO_NOT_EXCEED_INITIAL_FUNDING_USDT:
            warnings.append("available USDT exceeds 100 USDT initial funding cap; do not use 444/888 tiers yet")
    return _base_payload(
        status=status,
        available_usdt=parsed,
        execution_env=execution_env,
        blockers=blockers,
        warnings=warnings,
        balance_source="manual_operator_input",
    )


def build_post_funding_balance_runbook(
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    status = build_post_funding_balance_status(env=env)
    return _sanitize(
        {
            **status,
            "runbook_name": "R77_POST_FUNDING_BALANCE_VERIFICATION",
            "manual_steps": [
                "After funding, verify available USDT manually in Binance UI or a known safe readonly checker.",
                "Run LIVE BALANCE CHECK 88 for the preferred initial test funding amount.",
                "Treat balances below 44 USDT as not enough for first-live margin.",
                "Treat 44-87.99 USDT as marginal and below preferred buffer.",
                "Treat 88-100 USDT as ready after funding for the next checklist gate.",
                "Treat amounts above 100 USDT as over the initial funding cap; do not use 444/888 tiers yet.",
            ],
            "api_examples": [
                'POST /live/funding-balance/check {"available_usdt":88}',
                'POST /live/funding-balance/check {"available_usdt":44}',
                'POST /live/funding-balance/check {"available_usdt":25}',
            ],
            "telegram_examples": [
                "LIVE BALANCE CHECK 88",
                "LIVE BALANCE CHECK 44",
                "LIVE BALANCE CHECK 25",
            ],
            "next_gate": "R78 rehearsal/test-order/protective readiness",
        }
    )


def evaluate_and_record_post_funding_balance_check(
    *,
    available_usdt: object,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    payload = evaluate_manual_balance(available_usdt, env=env, log_dir=resolved_log_dir)
    record = _check_record(payload)
    append_post_funding_balance_check(record, log_dir=resolved_log_dir)
    payload["audit_event_recorded"] = True
    payload["post_funding_balance_check_id"] = record["check_id"]
    payload["post_funding_balance_checks_path"] = str(post_funding_balance_checks_path(resolved_log_dir))
    return _sanitize(payload)


def load_post_funding_balance_checks(
    *,
    limit: int = 50,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = post_funding_balance_checks_path(get_log_dir(log_dir, use_env=True))
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


def post_funding_balance_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHECKS_FILENAME


def append_post_funding_balance_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = post_funding_balance_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(record), sort_keys=True) + "\n")


def format_post_funding_balance_operator_message(payload: Mapping[str, Any], *, section: str = "status") -> str:
    balance = payload.get("balance_status") if isinstance(payload.get("balance_status"), dict) else {}
    if section == "runbook":
        return "\n".join(
            [
                f"R77 balance runbook: {payload.get('status')}",
                "BALANCE_CHECK_ONLY. No order placed. real_order_placed=false.",
                "Run LIVE BALANCE CHECK 88 after funding. 44-87.99 is marginal; below 44 is not enough.",
                "Keep execution disabled and kill switch active. Next gate is R78.",
            ]
        )
    return "\n".join(
        [
            f"R77 balance readiness: {payload.get('status')}",
            "BALANCE_CHECK_ONLY. No order placed. real_order_placed=false.",
            f"available={balance.get('available_usdt')} buffer={balance.get('buffer_usdt')}",
            (
                f"margin_ok={balance.get('enough_for_first_margin')} "
                f"preferred_buffer_ok={balance.get('preferred_buffer_ok')}"
            ),
            f"next: {payload.get('operator_action')}",
        ]
    )


def _base_payload(
    *,
    status: str,
    available_usdt: float | None,
    execution_env: Mapping[str, Any],
    blockers: list[str],
    warnings: list[str],
    balance_source: str,
) -> dict[str, Any]:
    buffer_usdt = None if available_usdt is None else round(available_usdt - MINIMUM_REQUIRED_AVAILABLE_USDT, 2)
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
            "balance_source": balance_source,
            "balance_status": {
                "available_usdt": available_usdt,
                "minimum_required_available_usdt": MINIMUM_REQUIRED_AVAILABLE_USDT,
                "preferred_available_usdt": PREFERRED_AVAILABLE_USDT,
                "do_not_exceed_initial_funding_usdt": DO_NOT_EXCEED_INITIAL_FUNDING_USDT,
                "buffer_usdt": buffer_usdt,
                "enough_for_first_margin": bool(available_usdt is not None and available_usdt >= MINIMUM_REQUIRED_AVAILABLE_USDT),
                "preferred_buffer_ok": bool(available_usdt is not None and available_usdt >= PREFERRED_AVAILABLE_USDT),
            },
            "first_live_profile": dict(FIRST_LIVE_PROFILE),
            "execution_env": dict(execution_env),
            "required_next_steps": _required_next_steps(status),
            "operator_action": _operator_action(status),
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
        }
    )


def _execution_blockers(execution_env: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if execution_env.get("live_execution_enabled") is True:
        blockers.append("HAMMER_LIVE_EXECUTION_ENABLED is true; balance verification expects execution disabled")
    if execution_env.get("allow_live_orders") is True:
        blockers.append("HAMMER_ALLOW_LIVE_ORDERS is true; balance verification expects live orders disabled")
    if execution_env.get("global_kill_switch") is not True:
        blockers.append("HAMMER_GLOBAL_KILL_SWITCH is not active")
    return blockers


def _required_next_steps(status: str) -> list[str]:
    if status == "READY_AFTER_FUNDING":
        return [
            "keep live execution disabled",
            "run R78 rehearsal/test-order/protective readiness",
            "wait for exact candidate and walk the chain manually",
            "do not use 444/888 margin tiers yet",
        ]
    if status == "MARGINAL_BALANCE":
        return [
            "consider topping up to 88 USDT preferred initial funding",
            "keep live execution disabled",
            "do not attempt a live order yet",
        ]
    if status == "NOT_ENOUGH_BALANCE":
        return [
            "fund at least 44 USDT available balance before first-live margin",
            "preferred target remains 88 USDT",
        ]
    if status == "BLOCKED":
        return [
            "restore live execution disabled flags",
            "restore global kill switch active",
            "rerun balance check",
        ]
    return [
        "provide manual available USDT with LIVE BALANCE CHECK <amount>",
        "preferred initial balance check is LIVE BALANCE CHECK 88",
    ]


def _operator_action(status: str) -> str:
    if status == "READY_AFTER_FUNDING":
        return "continue to R78 without enabling live execution"
    if status == "MARGINAL_BALANCE":
        return "top up toward 88 USDT preferred buffer before continuing"
    if status == "NOT_ENOUGH_BALANCE":
        return "fund at least 44 USDT available balance"
    if status == "BLOCKED":
        return "restore no-order execution posture"
    return "provide manual available USDT balance"


def _check_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "post_funding_balance_check",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "balance_source": payload.get("balance_source"),
        "balance_status": payload.get("balance_status"),
        "first_live_profile": payload.get("first_live_profile"),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
