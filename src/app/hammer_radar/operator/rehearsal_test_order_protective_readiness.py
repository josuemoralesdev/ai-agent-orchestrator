"""R78 rehearsal/test-order/protective readiness gate.

This module aggregates the existing R53/R63/R64/R65/R77 readiness surfaces for
the first funded tiny-live chain. It never places orders, enables live trading,
signs payloads, mutates env files, or calls Binance network endpoints.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution.binance_futures_connector import load_connector_attempts
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import build_first_live_chain_status
from src.app.hammer_radar.operator.first_live_protective_adapter import (
    build_first_live_protective_status,
    load_first_live_protective_checks,
)
from src.app.hammer_radar.operator.first_live_test_order_gate import (
    build_first_live_test_order_status,
    load_first_live_test_order_checks,
)
from src.app.hammer_radar.operator.live_execution_intent import load_live_execution_intents
from src.app.hammer_radar.operator.live_executor_rehearsal import load_live_executor_rehearsals
from src.app.hammer_radar.operator.post_funding_balance_verification import (
    build_post_funding_balance_status,
    evaluate_manual_balance,
)

PHASE = "R78"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "REHEARSAL_TEST_ORDER_PROTECTIVE_READINESS_ONLY"
CHECKS_FILENAME = "rehearsal_test_order_protective_readiness_checks.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False


def build_rehearsal_test_order_protective_status(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    return _evaluate(signal_id=None, execution_intent_id=None, available_usdt=None, env=env, log_dir=log_dir, persist=False)


def build_rehearsal_test_order_protective_check(
    *,
    signal_id: str | None = None,
    execution_intent_id: str | None = None,
    available_usdt: object | None = None,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    return _evaluate(
        signal_id=signal_id,
        execution_intent_id=execution_intent_id,
        available_usdt=available_usdt,
        env=env,
        log_dir=log_dir,
        persist=True,
    )


def build_rehearsal_test_order_protective_runbook(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    status = build_rehearsal_test_order_protective_status(env=env, log_dir=log_dir)
    return _sanitize(
        {
            **status,
            "runbook_name": "R78_REHEARSAL_TEST_ORDER_PROTECTIVE_READINESS",
            "manual_steps": [
                "FIRST LIVE NEXT",
                "LIVE APPROVE <signal_id>",
                "FIRST LIVE NEXT",
                "LIVE INTENT <signal_id>",
                "FIRST LIVE NEXT",
                "LIVE REHEARSAL <intent_id>",
                "LIVE REHEARSAL READINESS",
                "FIRST LIVE TEST ORDER",
                "FIRST LIVE PROTECTIVE CHECK",
                "Return to FIRST LIVE NEXT for final manual gate only after R78 is ready.",
            ],
            "safety": [
                "R78_READINESS_ONLY",
                "No order placed",
                "real_order_placed=false",
                "execution_attempted=false",
                "no naked entry",
                "final manual gate still required",
            ],
        }
    )


def load_rehearsal_test_order_protective_checks(
    *,
    limit: int = 50,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = rehearsal_test_order_protective_checks_path(get_log_dir(log_dir, use_env=True))
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


def rehearsal_test_order_protective_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHECKS_FILENAME


def append_rehearsal_test_order_protective_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = rehearsal_test_order_protective_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(record), sort_keys=True) + "\n")


def format_rehearsal_test_order_protective_operator_message(payload: Mapping[str, Any], *, section: str = "status") -> str:
    chain = payload.get("chain_state") if isinstance(payload.get("chain_state"), dict) else {}
    no_naked = payload.get("no_naked_entry_status") if isinstance(payload.get("no_naked_entry_status"), dict) else {}
    protective = payload.get("protective_status") if isinstance(payload.get("protective_status"), dict) else {}
    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    blocker_text = "; ".join(str(item) for item in blockers[:5]) if blockers else "none"
    if section == "runbook":
        steps = payload.get("manual_steps") if isinstance(payload.get("manual_steps"), list) else payload.get("required_next_steps") or []
        return "\n".join(
            [
                f"R78 rehearsal runbook: {payload.get('status')}",
                "R78_READINESS_ONLY. No order placed. real_order_placed=false. execution_attempted=false.",
                "next: " + "; ".join(str(item) for item in steps[:5]),
                "final manual gate still required.",
            ]
        )
    if section == "protective":
        return "\n".join(
            [
                f"R78 protective readiness: {payload.get('status')}",
                "R78_READINESS_ONLY. No order placed. real_order_placed=false. execution_attempted=false.",
                (
                    "protective: "
                    f"stop={protective.get('stop_loss_ready')} take_profit={protective.get('take_profit_ready')} "
                    f"ready={protective.get('protective_payloads_ready')}"
                ),
                (
                    "no_naked_entry: "
                    f"blocked={no_naked.get('naked_entry_blocked')} "
                    f"entry_allowed_without_protective={no_naked.get('entry_allowed_without_protective')}"
                ),
                f"blockers: {blocker_text}",
            ]
        )
    return "\n".join(
        [
            f"R78 rehearsal readiness: {payload.get('status')}",
            "R78_READINESS_ONLY. No order placed. real_order_placed=false. execution_attempted=false.",
            (
                "chain: "
                f"intent={chain.get('execution_intent_found')} rehearsal={chain.get('executor_rehearsal_found')} "
                f"signal={chain.get('signal_id') or 'none'}"
            ),
            f"next: {'; '.join(str(item) for item in (payload.get('required_next_steps') or [])[:3]) or 'none'}",
            f"blockers: {blocker_text}",
        ]
    )


def _evaluate(
    *,
    signal_id: str | None,
    execution_intent_id: str | None,
    available_usdt: object | None,
    env: Mapping[str, str] | None,
    log_dir: str | Path | None,
    persist: bool,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC).isoformat()
    funding = (
        evaluate_manual_balance(available_usdt, env=source, log_dir=resolved_log_dir)
        if available_usdt is not None
        else build_post_funding_balance_status(env=source, log_dir=resolved_log_dir)
    )
    first_chain = build_first_live_chain_status(log_dir=resolved_log_dir, env=source)
    chain_state = _chain_state(
        signal_id=signal_id,
        execution_intent_id=execution_intent_id,
        first_chain=first_chain,
        log_dir=resolved_log_dir,
    )
    rehearsal_status = _rehearsal_status(chain_state=chain_state)
    test_order_status = _test_order_status(chain_state=chain_state, log_dir=resolved_log_dir, env=source)
    protective_status = _protective_status(chain_state=chain_state, log_dir=resolved_log_dir, env=source)
    no_naked_entry_status = _no_naked_entry_status(protective_status=protective_status)
    safety = _safety_scan(chain_state=chain_state, log_dir=resolved_log_dir)
    blockers = _blockers(
        safety=safety,
        no_naked_entry_status=no_naked_entry_status,
        funding=funding,
    )
    warnings = _warnings(funding=funding, first_chain=first_chain)
    status = _status(
        chain_state=chain_state,
        test_order_status=test_order_status,
        protective_status=protective_status,
        no_naked_entry_status=no_naked_entry_status,
        blockers=blockers,
    )
    payload = _sanitize(
        {
            "status": status,
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "created_at": created_at,
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "execution_attempted": EXECUTION_ATTEMPTED,
            "network_allowed": NETWORK_ALLOWED,
            "secrets_shown": SECRETS_SHOWN,
            "funding_balance_status": funding,
            "chain_state": chain_state,
            "rehearsal_status": rehearsal_status,
            "test_order_status": test_order_status,
            "protective_status": protective_status,
            "no_naked_entry_status": no_naked_entry_status,
            "required_next_steps": _required_next_steps(status, chain_state=chain_state),
            "blockers": blockers,
            "warnings": warnings,
            "audit_event_recorded": persist,
            "rehearsal_test_order_protective_readiness_checks_path": str(
                rehearsal_test_order_protective_checks_path(resolved_log_dir)
            ),
        }
    )
    if persist:
        record = _record(payload)
        append_rehearsal_test_order_protective_check(record, log_dir=resolved_log_dir)
        payload["check_id"] = record["check_id"]
    return _sanitize(payload)


def _chain_state(
    *,
    signal_id: str | None,
    execution_intent_id: str | None,
    first_chain: dict[str, Any],
    log_dir: Path,
) -> dict[str, Any]:
    requested_signal = _clean(signal_id)
    requested_intent_id = _clean(execution_intent_id)
    current = first_chain.get("current_signal") if isinstance(first_chain.get("current_signal"), dict) else {}
    first_chain_state = first_chain.get("chain_state") if isinstance(first_chain.get("chain_state"), dict) else {}
    intent = _resolve_intent(
        signal_id=requested_signal or _clean(current.get("signal_id")),
        execution_intent_id=requested_intent_id or _clean(first_chain_state.get("execution_intent_id")),
        log_dir=log_dir,
    )
    resolved_signal = _clean((intent or {}).get("signal_id") or requested_signal or current.get("signal_id"))
    resolved_intent_id = _clean((intent or {}).get("execution_intent_id") or requested_intent_id)
    rehearsal = _resolve_rehearsal(signal_id=resolved_signal, execution_intent_id=resolved_intent_id, log_dir=log_dir)
    resolved_rehearsal_id = _clean((rehearsal or {}).get("executor_rehearsal_id"))
    intent_found = intent is not None and intent.get("status") == "INTENT_READY"
    rehearsal_found = rehearsal is not None and rehearsal.get("status") == "REHEARSAL_READY"
    exact_chain_resolved = bool(
        resolved_signal
        and intent_found
        and rehearsal_found
        and (rehearsal or {}).get("execution_intent_id") == resolved_intent_id
        and (rehearsal or {}).get("signal_id") == resolved_signal
    )
    return {
        "requested_signal_id": requested_signal,
        "requested_execution_intent_id": requested_intent_id,
        "signal_id": resolved_signal,
        "execution_intent_id": resolved_intent_id,
        "executor_rehearsal_id": resolved_rehearsal_id,
        "approval_found": bool(first_chain_state.get("approval_found")),
        "execution_intent_found": intent_found,
        "execution_intent_status": (intent or {}).get("status") or "MISSING",
        "executor_rehearsal_found": rehearsal_found,
        "executor_rehearsal_status": (rehearsal or {}).get("status") or "MISSING",
        "exact_chain_resolved": bool(first_chain_state.get("exact_chain_resolved")) or exact_chain_resolved,
        "first_chain_status": first_chain.get("status"),
        "first_chain_next_action": first_chain.get("next_action") if isinstance(first_chain.get("next_action"), dict) else {},
        "blockers": _chain_blockers(intent_found=intent_found, rehearsal_found=rehearsal_found),
    }


def _resolve_intent(*, signal_id: str | None, execution_intent_id: str | None, log_dir: Path) -> dict[str, Any] | None:
    if execution_intent_id:
        records = load_live_execution_intents(limit=0, intent_id=execution_intent_id, log_dir=log_dir)
        return records[0] if records else None
    if signal_id:
        records = load_live_execution_intents(limit=0, signal_id=signal_id, log_dir=log_dir)
        for record in records:
            if record.get("status") == "INTENT_READY":
                return record
        return records[0] if records else None
    return None


def _resolve_rehearsal(*, signal_id: str | None, execution_intent_id: str | None, log_dir: Path) -> dict[str, Any] | None:
    records = load_live_executor_rehearsals(limit=0, signal_id=signal_id, execution_intent_id=execution_intent_id, log_dir=log_dir)
    for record in records:
        if record.get("status") == "REHEARSAL_READY":
            return record
    return records[0] if records else None


def _rehearsal_status(*, chain_state: Mapping[str, Any]) -> dict[str, Any]:
    found = chain_state.get("executor_rehearsal_found") is True
    return {
        "status": "REHEARSAL_READY" if found else "MISSING",
        "execution_intent_id": chain_state.get("execution_intent_id"),
        "executor_rehearsal_id": chain_state.get("executor_rehearsal_id"),
        "rehearsal_required": True,
        "rehearsal_ready": found,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "network_allowed": False,
        "secrets_shown": False,
    }


def _test_order_status(*, chain_state: Mapping[str, Any], log_dir: Path, env: Mapping[str, str]) -> dict[str, Any]:
    signal_id = _clean(chain_state.get("signal_id"))
    rehearsal_id = _clean(chain_state.get("executor_rehearsal_id"))
    intent_id = _clean(chain_state.get("execution_intent_id"))
    gate = build_first_live_test_order_status(
        signal_id=signal_id,
        execution_intent_id=intent_id,
        executor_rehearsal_id=rehearsal_id,
        log_dir=log_dir,
        env=env,
    )
    nested = gate.get("test_order_status") if isinstance(gate.get("test_order_status"), dict) else {}
    validation = _latest_test_order_validation(signal_id=signal_id, log_dir=log_dir)
    validated = nested.get("test_order_validated_for_signal") is True or validation is not None
    return {
        "status": gate.get("status"),
        "test_order_required": True,
        "test_order_path_available": bool(nested.get("test_order_path_available", True)),
        "test_order_network_enabled": False,
        "test_order_validated_for_signal": validated,
        "test_order_validation_id": nested.get("test_order_validation_id") or (validation or {}).get("attempt_id"),
        "validated_signal_id": nested.get("validated_signal_id") or (validation or {}).get("signal_id"),
        "payload_readiness": gate.get("payload_readiness") if isinstance(gate.get("payload_readiness"), dict) else {},
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "network_allowed": False,
        "secrets_shown": False,
        "blockers": list(dict.fromkeys([*(nested.get("blockers") or []), *(gate.get("blockers") or [])])),
    }


def _latest_test_order_validation(*, signal_id: str | None, log_dir: Path) -> dict[str, Any] | None:
    if not signal_id:
        return None
    for record in load_connector_attempts(limit=0, signal_id=signal_id, log_dir=log_dir):
        if record.get("endpoint") != "test_order":
            continue
        if record.get("order_placed") is True or record.get("real_order_placed") is True:
            continue
        if record.get("status") in {"TEST_ORDER_SENT", "TEST_ORDER_MOCK_VALIDATED", "TEST_ORDER_VALIDATED"}:
            return record
    return None


def _protective_status(*, chain_state: Mapping[str, Any], log_dir: Path, env: Mapping[str, str]) -> dict[str, Any]:
    signal_id = _clean(chain_state.get("signal_id"))
    rehearsal_id = _clean(chain_state.get("executor_rehearsal_id"))
    intent_id = _clean(chain_state.get("execution_intent_id"))
    protective = build_first_live_protective_status(
        signal_id=signal_id,
        execution_intent_id=intent_id,
        executor_rehearsal_id=rehearsal_id,
        log_dir=log_dir,
        env=env,
    )
    plan = protective.get("protective_plan") if isinstance(protective.get("protective_plan"), dict) else {}
    latest = _latest_protective_ready_check(log_dir=log_dir)
    latest_plan = latest.get("protective_plan") if isinstance(latest.get("protective_plan"), dict) else {}
    stop_ready = plan.get("stop_loss_available") is True or latest_plan.get("stop_loss_available") is True
    take_ready = plan.get("take_profit_available") is True or latest_plan.get("take_profit_available") is True
    protective_ready = bool(plan.get("available") is True or latest_plan.get("available") is True or (stop_ready and take_ready))
    gate = protective.get("protective_gate") if isinstance(protective.get("protective_gate"), dict) else {}
    return {
        "status": protective.get("status") or latest.get("status") or "NOT_READY",
        "protective_required": True,
        "protective_payloads_ready": protective_ready,
        "stop_loss_ready": stop_ready,
        "take_profit_ready": take_ready,
        "entry_allowed_without_protective": bool(gate.get("entry_allowed_without_protective")),
        "naked_entry_blocked": gate.get("naked_entry_blocked") is not False,
        "protective_gate": gate,
        "blockers": list(dict.fromkeys([*(plan.get("blockers") or []), *(protective.get("blockers") or [])])),
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "network_allowed": False,
        "secrets_shown": False,
    }


def _latest_protective_ready_check(*, log_dir: Path) -> dict[str, Any]:
    for record in load_first_live_protective_checks(limit=0, log_dir=log_dir):
        plan = record.get("protective_plan") if isinstance(record.get("protective_plan"), dict) else {}
        if plan.get("available") is True:
            return record
    return {}


def _no_naked_entry_status(*, protective_status: Mapping[str, Any]) -> dict[str, Any]:
    protective_ready = protective_status.get("protective_payloads_ready") is True
    entry_allowed_without_protective = protective_status.get("entry_allowed_without_protective") is True
    naked_entry_blocked = protective_status.get("naked_entry_blocked") is not False and not entry_allowed_without_protective
    blockers = []
    if not protective_ready:
        blockers.append("entry remains blocked until protective stop-loss and take-profit readiness exists")
    if entry_allowed_without_protective:
        blockers.append("unsafe naked entry allowance detected")
    return {
        "status": "PROTECTIVE_READY" if protective_ready and not entry_allowed_without_protective else "BLOCKED_UNTIL_PROTECTIVE_READY",
        "entry_requires_protective_ready": True,
        "entry_allowed_without_protective": entry_allowed_without_protective,
        "naked_entry_blocked": naked_entry_blocked,
        "protective_ready": protective_ready,
        "blockers": blockers,
    }


def _safety_scan(*, chain_state: Mapping[str, Any], log_dir: Path) -> dict[str, Any]:
    signal_id = _clean(chain_state.get("signal_id"))
    unsafe_records = []
    for record in load_connector_attempts(limit=0, signal_id=signal_id, log_dir=log_dir) if signal_id else load_connector_attempts(limit=50, log_dir=log_dir):
        if record.get("real_order_placed") is True or record.get("order_placed") is True:
            unsafe_records.append({"source": "connector_attempt", "id": record.get("attempt_id"), "status": record.get("status")})
    for record in load_first_live_test_order_checks(limit=50, log_dir=log_dir):
        if _matches_chain(record, chain_state) and (record.get("real_order_placed") is True or record.get("order_placed") is True):
            unsafe_records.append({"source": "first_live_test_order_check", "id": record.get("check_id"), "status": record.get("status")})
    for record in load_first_live_protective_checks(limit=50, log_dir=log_dir):
        if record.get("real_order_placed") is True or record.get("order_placed") is True:
            unsafe_records.append({"source": "first_live_protective_check", "id": record.get("check_id"), "status": record.get("status")})
    return {
        "unsafe_order_record_found": bool(unsafe_records),
        "unsafe_records": unsafe_records[:10],
    }


def _matches_chain(record: Mapping[str, Any], chain_state: Mapping[str, Any]) -> bool:
    signal_id = _clean(chain_state.get("signal_id"))
    intent_id = _clean(chain_state.get("execution_intent_id"))
    rehearsal_id = _clean(chain_state.get("executor_rehearsal_id"))
    text = json.dumps(record, sort_keys=True, default=str)
    return bool((signal_id and signal_id in text) or (intent_id and intent_id in text) or (rehearsal_id and rehearsal_id in text))


def _status(
    *,
    chain_state: Mapping[str, Any],
    test_order_status: Mapping[str, Any],
    protective_status: Mapping[str, Any],
    no_naked_entry_status: Mapping[str, Any],
    blockers: list[str],
) -> str:
    if blockers:
        return "BLOCKED"
    if chain_state.get("execution_intent_found") is not True:
        return "AWAITING_CHAIN"
    if chain_state.get("executor_rehearsal_found") is not True:
        return "READY_FOR_REHEARSAL"
    if test_order_status.get("test_order_validated_for_signal") is not True:
        return "READY_FOR_TEST_ORDER"
    if protective_status.get("protective_payloads_ready") is not True:
        return "READY_FOR_PROTECTIVE_REVIEW"
    if no_naked_entry_status.get("entry_allowed_without_protective") is True:
        return "BLOCKED"
    return "READY_FOR_FINAL_MANUAL_GATE"


def _blockers(*, safety: Mapping[str, Any], no_naked_entry_status: Mapping[str, Any], funding: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if safety.get("unsafe_order_record_found") is True:
        blockers.append("real/order placement record found; R78 cannot progress")
    if no_naked_entry_status.get("entry_allowed_without_protective") is True:
        blockers.append("naked entry would be allowed")
    if funding.get("status") == "BLOCKED":
        blockers.extend(str(item) for item in funding.get("blockers") or [])
    return list(dict.fromkeys(item for item in blockers if item))


def _warnings(*, funding: Mapping[str, Any], first_chain: Mapping[str, Any]) -> list[str]:
    warnings = [str(item) for item in funding.get("warnings") or []]
    if funding.get("status") == "AWAITING_BALANCE_INPUT":
        warnings.append("funding balance still requires manual input")
    next_action = first_chain.get("next_action") if isinstance(first_chain.get("next_action"), dict) else {}
    if next_action.get("kind") in {"manual_env_review", "final_review"}:
        warnings.append("final manual gate remains required before any live order")
    return list(dict.fromkeys(warnings))


def _required_next_steps(status: str, *, chain_state: Mapping[str, Any]) -> list[str]:
    signal_id = chain_state.get("signal_id") or "<signal_id>"
    intent_id = chain_state.get("execution_intent_id") or "<intent_id>"
    if status == "AWAITING_CHAIN":
        return [f"LIVE APPROVE {signal_id}", f"LIVE INTENT {signal_id}", "FIRST LIVE NEXT"]
    if status == "READY_FOR_REHEARSAL":
        return [f"LIVE REHEARSAL {intent_id}", "LIVE REHEARSAL READINESS"]
    if status == "READY_FOR_TEST_ORDER":
        return ["FIRST LIVE TEST ORDER", "LIVE REHEARSAL READINESS"]
    if status == "READY_FOR_PROTECTIVE_REVIEW":
        return ["FIRST LIVE PROTECTIVE CHECK", "LIVE PROTECTIVE READINESS"]
    if status == "READY_FOR_FINAL_MANUAL_GATE":
        return ["FIRST LIVE NEXT", "manual env/funds review", "final protected live gate"]
    return ["resolve blockers before continuing"]


def _chain_blockers(*, intent_found: bool, rehearsal_found: bool) -> list[str]:
    blockers = []
    if not intent_found:
        blockers.append("LIVE APPROVE + LIVE INTENT required")
    elif not rehearsal_found:
        blockers.append("R53 LIVE REHEARSAL required")
    return blockers


def _record(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "rehearsal_test_order_protective_readiness_check",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "funding_balance_status": payload.get("funding_balance_status"),
        "chain_state": payload.get("chain_state"),
        "rehearsal_status": payload.get("rehearsal_status"),
        "test_order_status": payload.get("test_order_status"),
        "protective_status": payload.get("protective_status"),
        "no_naked_entry_status": payload.get("no_naked_entry_status"),
        "required_next_steps": payload.get("required_next_steps"),
        "blockers": payload.get("blockers"),
        "warnings": payload.get("warnings"),
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


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
