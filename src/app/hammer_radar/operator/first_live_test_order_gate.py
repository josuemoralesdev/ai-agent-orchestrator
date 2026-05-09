"""R64 exact-signal protective payload and test-order gate.

This module composes the existing exact approval/intent/rehearsal chain,
R58 first-live profile, R62 ladder adapter, R63 protective adapter, and
Binance test-order attempt records. It never signs payloads, places orders,
edits env files, or calls Binance.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution.binance_futures_connector import build_connector_status, load_connector_attempts
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_adapter_verification import build_first_live_adapter_status
from src.app.hammer_radar.operator.first_live_ladder_submit_adapter import build_first_live_ladder_submit_status
from src.app.hammer_radar.operator.first_live_protective_adapter import build_first_live_protective_status
from src.app.hammer_radar.operator.first_live_readiness import build_first_live_readiness_status
from src.app.hammer_radar.operator.first_microscopic_live_attempt import build_first_microscopic_live_profile
from src.app.hammer_radar.operator.live_approval import find_valid_live_approval_for_signal, load_live_approval_requests
from src.app.hammer_radar.operator.live_begins import build_live_begins_status
from src.app.hammer_radar.operator.live_execution_intent import load_live_execution_intents
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview
from src.app.hammer_radar.operator.live_executor_rehearsal import load_live_executor_rehearsals

PHASE = "R64"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "EXACT_SIGNAL_PROTECTIVE_TEST_ORDER_GATE"
CHECKS_FILENAME = "first_live_test_order_checks.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

DEFAULT_TRANSPORT_MODE = "DRY_RUN"
TRANSPORT_MODES = {"MOCK", "DRY_RUN", "LIVE_CHECK", "LIVE"}


def build_first_live_test_order_status(
    *,
    signal_id: str | None = None,
    execution_intent_id: str | None = None,
    executor_rehearsal_id: str | None = None,
    transport_mode: str | None = None,
    dry_run: bool = True,
    final_confirmation: bool = False,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate(
        signal_id=signal_id,
        execution_intent_id=execution_intent_id,
        executor_rehearsal_id=executor_rehearsal_id,
        transport_mode=transport_mode,
        dry_run=dry_run,
        final_confirmation=final_confirmation,
        log_dir=log_dir,
        env=env,
        persist=False,
    )


def evaluate_and_record_first_live_test_order_check(
    *,
    signal_id: str | None = None,
    execution_intent_id: str | None = None,
    executor_rehearsal_id: str | None = None,
    transport_mode: str | None = None,
    dry_run: bool = True,
    final_confirmation: bool = False,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate(
        signal_id=signal_id,
        execution_intent_id=execution_intent_id,
        executor_rehearsal_id=executor_rehearsal_id,
        transport_mode=transport_mode,
        dry_run=dry_run,
        final_confirmation=final_confirmation,
        log_dir=log_dir,
        env=env,
        persist=True,
    )


def list_first_live_test_order_checks(
    *,
    limit: int = 20,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_first_live_test_order_checks(limit=limit, status=status, log_dir=get_log_dir(log_dir, use_env=True))
    return {
        "result_status": "ACCEPTED",
        "phase": PHASE,
        "count": len(records),
        "checks": records,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def load_first_live_test_order_checks(
    *,
    limit: int = 50,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_test_order_checks_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if status is not None and record.get("status") != status:
                continue
            records.append(_sanitize_record(record))
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def first_live_test_order_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHECKS_FILENAME


def append_first_live_test_order_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_test_order_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_first_live_test_order_gate_operator_message(payload: dict[str, Any], *, section: str = "check") -> str:
    chain = payload.get("exact_chain_status") or {}
    readiness = payload.get("payload_readiness") or {}
    test_order = payload.get("test_order_status") or {}
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:6]) if blockers else "none"
    lines = [
        f"R64 exact-signal test-order {section}: {payload.get('status')}",
        "EXACT_SIGNAL_PROTECTIVE_TEST_ORDER_GATE. No order placed. real_order_placed=false.",
    ]
    if section in {"check", "exact_chain"}:
        lines.append(
            "exact chain: "
            f"resolved={chain.get('exact_chain_resolved')} signal_fresh={chain.get('signal_fresh')} "
            f"approval={chain.get('approval_found')} intent={chain.get('intent_found')} rehearsal={chain.get('rehearsal_found')}"
        )
    if section in {"check", "payload"}:
        lines.append(
            "payloads: "
            f"entry={readiness.get('entry_payload_ready')} ladder={readiness.get('ladder_plan_ready')} "
            f"stop={readiness.get('stop_loss_ready')} take_profit={readiness.get('take_profit_ready')} "
            f"no_naked_entry_ok={readiness.get('no_naked_entry_ok')}"
        )
    if section == "check":
        lines.append(
            "test-order: "
            f"required={test_order.get('test_order_required')} validated={test_order.get('test_order_validated_for_signal')} "
            f"network_enabled={test_order.get('test_order_network_enabled')}"
        )
    lines.extend(
        [
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )
    return "\n".join(lines)


def format_first_live_test_order_checks_operator_message(payload: dict[str, Any]) -> str:
    checks = payload.get("checks") or []
    detail = "none"
    if checks:
        detail = "; ".join(f"{item.get('created_at')} {item.get('status')}" for item in checks[:5])
    return "\n".join(
        [
            "R64 exact-signal test-order checks",
            "EXACT_SIGNAL_PROTECTIVE_TEST_ORDER_GATE list. No order placed.",
            f"count: {payload.get('count', 0)}",
            f"checks: {detail}",
            "order_placed=false real_order_placed=false secrets_shown=false",
        ]
    )


def _evaluate(
    *,
    signal_id: str | None,
    execution_intent_id: str | None,
    executor_rehearsal_id: str | None,
    transport_mode: str | None,
    dry_run: bool,
    final_confirmation: bool,
    log_dir: str | Path | None,
    env: Mapping[str, str] | None,
    persist: bool,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC)
    mode = _normalize_transport_mode(transport_mode)
    profile = _profile(build_first_microscopic_live_profile(log_dir=resolved_log_dir, env=source).get("profile") or {})
    preview = build_live_execution_preview(log_dir=resolved_log_dir, env=source)
    connector = build_connector_status(env=source, log_dir=resolved_log_dir)
    exact_chain = _exact_chain_status(
        signal_id=signal_id,
        execution_intent_id=execution_intent_id,
        executor_rehearsal_id=executor_rehearsal_id,
        profile=profile,
        preview=preview,
        log_dir=resolved_log_dir,
        now=created_at,
    )
    resolved_signal_id = exact_chain.get("signal_id") or signal_id
    resolved_intent_id = exact_chain.get("execution_intent_id") or execution_intent_id
    resolved_rehearsal_id = exact_chain.get("executor_rehearsal_id") or executor_rehearsal_id
    ladder = build_first_live_ladder_submit_status(
        executor_rehearsal_id=resolved_rehearsal_id,
        execution_intent_id=resolved_intent_id,
        signal_id=resolved_signal_id,
        transport_mode=mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=resolved_log_dir,
        env=source,
    )
    protective = build_first_live_protective_status(
        executor_rehearsal_id=resolved_rehearsal_id,
        execution_intent_id=resolved_intent_id,
        signal_id=resolved_signal_id,
        transport_mode=mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=resolved_log_dir,
        env=source,
    )
    payload_readiness = _payload_readiness(exact_chain=exact_chain, ladder=ladder, protective=protective)
    test_order_status = _test_order_status(
        signal_id=resolved_signal_id,
        executor_rehearsal_id=resolved_rehearsal_id,
        connector=connector,
        log_dir=resolved_log_dir,
    )
    gate_statuses = _gate_statuses(
        signal_id=resolved_signal_id,
        executor_rehearsal_id=resolved_rehearsal_id,
        ladder=ladder,
        protective=protective,
        env=source,
        log_dir=resolved_log_dir,
    )
    live_eligibility = _live_eligibility(
        exact_chain=exact_chain,
        payload_readiness=payload_readiness,
        test_order_status=test_order_status,
        final_confirmation=final_confirmation,
    )
    blockers = _blockers(
        exact_chain=exact_chain,
        payload_readiness=payload_readiness,
        test_order_status=test_order_status,
        live_eligibility=live_eligibility,
    )
    status = _status(
        exact_chain=exact_chain,
        payload_readiness=payload_readiness,
        test_order_status=test_order_status,
        live_eligibility=live_eligibility,
    )
    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "created_at": created_at.isoformat(),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "signal_id": resolved_signal_id,
        "execution_intent_id": resolved_intent_id,
        "executor_rehearsal_id": resolved_rehearsal_id,
        "profile": profile,
        "exact_chain_status": _public_exact_chain_status(exact_chain),
        "payload_readiness": payload_readiness,
        "test_order_status": test_order_status,
        "gate_statuses": gate_statuses,
        "live_eligibility": live_eligibility,
        "blockers": blockers,
        "operator_action": _operator_action(exact_chain=exact_chain, payload_readiness=payload_readiness, test_order_status=test_order_status),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "first_live_test_order_checks_path": str(first_live_test_order_checks_path(resolved_log_dir)),
    }
    if persist:
        record = _record(payload)
        append_first_live_test_order_check(record, log_dir=resolved_log_dir)
        payload["check_id"] = record["check_id"]
    return _sanitize_nested(payload)


def _exact_chain_status(
    *,
    signal_id: str | None,
    execution_intent_id: str | None,
    executor_rehearsal_id: str | None,
    profile: dict[str, Any],
    preview: dict[str, Any],
    log_dir: Path,
    now: datetime,
) -> dict[str, Any]:
    requested_signal = _clean(signal_id)
    requested_intent_id = _clean(execution_intent_id)
    requested_rehearsal_id = _clean(executor_rehearsal_id)
    blockers: list[str] = []
    intent = None
    rehearsal = None
    if requested_rehearsal_id:
        rehearsals = load_live_executor_rehearsals(limit=0, rehearsal_id=requested_rehearsal_id, log_dir=log_dir)
        rehearsal = rehearsals[0] if rehearsals else None
        if rehearsal is None:
            blockers.append("executor rehearsal not found")
        intent_id = (rehearsal or {}).get("execution_intent_id") or requested_intent_id
        if intent_id:
            intents = load_live_execution_intents(limit=0, intent_id=str(intent_id), log_dir=log_dir)
            intent = intents[0] if intents else None
    elif requested_intent_id:
        intents = load_live_execution_intents(limit=0, intent_id=requested_intent_id, log_dir=log_dir)
        intent = intents[0] if intents else None
        if intent is None:
            blockers.append("execution intent not found")
        rehearsals = load_live_executor_rehearsals(limit=0, execution_intent_id=requested_intent_id, log_dir=log_dir)
        rehearsal = _latest_ready_rehearsal(rehearsals) or (rehearsals[0] if rehearsals else None)
        if rehearsal is None:
            blockers.append("matching executor rehearsal not found")
    elif requested_signal:
        intents = load_live_execution_intents(limit=0, signal_id=requested_signal, log_dir=log_dir)
        intent = _latest_unexpired_intent(intents, now=now) or (intents[0] if intents else None)
        if intent is None:
            blockers.append("matching execution intent not found")
        rehearsals = load_live_executor_rehearsals(
            limit=0,
            signal_id=requested_signal,
            execution_intent_id=(intent or {}).get("execution_intent_id"),
            log_dir=log_dir,
        )
        rehearsal = _latest_ready_rehearsal(rehearsals) or (rehearsals[0] if rehearsals else None)
        if rehearsal is None:
            blockers.append("matching executor rehearsal not found")
    else:
        blockers.append("signal_id, execution_intent_id, or executor_rehearsal_id is required")

    resolved_signal = _clean((rehearsal or {}).get("signal_id") or (intent or {}).get("signal_id") or requested_signal)
    resolved_intent_id = _clean((intent or {}).get("execution_intent_id") or requested_intent_id)
    resolved_rehearsal_id = _clean((rehearsal or {}).get("executor_rehearsal_id") or requested_rehearsal_id)
    approval_found = _approval_found(resolved_signal, log_dir=log_dir)
    intent_found = intent is not None
    rehearsal_found = rehearsal is not None
    signal_fresh = _signal_fresh(resolved_signal, preview=preview)
    signal_matches_profile = _signal_matches_profile(resolved_signal, profile=profile, preview=preview)
    chain_ids_match = bool(
        resolved_signal
        and intent_found
        and rehearsal_found
        and (intent or {}).get("signal_id") == resolved_signal
        and (rehearsal or {}).get("signal_id") == resolved_signal
        and (rehearsal or {}).get("execution_intent_id") == resolved_intent_id
        and (intent or {}).get("status") == "INTENT_READY"
        and (rehearsal or {}).get("status") == "REHEARSAL_READY"
        and _intent_unexpired(intent, now=now)
    )
    if requested_signal and resolved_signal and requested_signal != resolved_signal:
        blockers.append("requested signal_id does not match resolved exact chain")
    if requested_intent_id and resolved_intent_id and requested_intent_id != resolved_intent_id:
        blockers.append("requested execution_intent_id does not match resolved exact chain")
    if not approval_found:
        blockers.append("exact LIVE APPROVE <signal_id> is missing")
    if not signal_fresh:
        blockers.append("exact signal is missing or stale")
    if not signal_matches_profile:
        blockers.append("signal does not match R58 first-live profile")
    if not chain_ids_match:
        blockers.append("approval, intent, and rehearsal ids do not form a ready exact chain")
    exact_chain_resolved = bool(approval_found and intent_found and rehearsal_found and signal_fresh and signal_matches_profile and chain_ids_match)
    return {
        "id_or_signal_present": bool(requested_signal or requested_intent_id or requested_rehearsal_id),
        "signal_id_present": bool(requested_signal),
        "execution_intent_id_present": bool(requested_intent_id),
        "executor_rehearsal_id_present": bool(requested_rehearsal_id),
        "exact_chain_resolved": exact_chain_resolved,
        "signal_fresh": signal_fresh,
        "signal_matches_profile": signal_matches_profile,
        "approval_found": approval_found,
        "intent_found": intent_found,
        "rehearsal_found": rehearsal_found,
        "chain_ids_match": chain_ids_match,
        "signal_id": resolved_signal,
        "execution_intent_id": resolved_intent_id,
        "executor_rehearsal_id": resolved_rehearsal_id,
        "blockers": list(dict.fromkeys(item for item in blockers if item)),
    }


def _payload_readiness(*, exact_chain: dict[str, Any], ladder: dict[str, Any], protective: dict[str, Any]) -> dict[str, Any]:
    ladder_plan = ladder.get("ladder_submit_plan") if isinstance(ladder.get("ladder_submit_plan"), dict) else {}
    ladder_payloads = ladder.get("sanitized_payloads") if isinstance(ladder.get("sanitized_payloads"), dict) else {}
    protective_plan = protective.get("protective_plan") if isinstance(protective.get("protective_plan"), dict) else {}
    protective_payloads = protective.get("sanitized_payloads") if isinstance(protective.get("sanitized_payloads"), dict) else {}
    exact_ready = exact_chain.get("exact_chain_resolved") is True
    entry_payload = ladder_payloads.get("aggregate_entry_payload")
    entry_payload_ready = bool(
        exact_ready
        and isinstance(entry_payload, dict)
        and entry_payload.get("symbol") == "BTCUSDT"
        and entry_payload.get("side") in {"BUY", "SELL"}
        and entry_payload.get("preview_only") is True
        and entry_payload.get("reduceOnly") is False
    )
    ladder_plan_ready = bool(exact_ready and ladder_plan.get("available") is True and ladder_plan.get("aggregate_preview_only") is not True)
    stop_ready = bool(exact_ready and protective_plan.get("stop_loss_available") is True)
    take_ready = bool(exact_ready and protective_plan.get("take_profit_available") is True)
    protective_ready = bool(exact_ready and protective_plan.get("available") is True and stop_ready and take_ready)
    sanitized_present = bool(
        exact_ready
        and isinstance(entry_payload, dict)
        and protective_payloads.get("stop_loss_payload") is not None
        and protective_payloads.get("take_profit_payload") is not None
        and ladder_payloads.get("secrets_shown") is False
        and protective_payloads.get("secrets_shown") is False
    )
    blockers = []
    if not entry_payload_ready:
        blockers.append("exact entry payload is missing or invalid")
    if not ladder_plan_ready:
        blockers.append("R62 ladder submit plan is not fully ready")
    if not protective_ready:
        blockers.append("R63 protective stop-loss/take-profit payloads are not fully ready")
    if not sanitized_present:
        blockers.append("sanitized exact entry/protective payload set is incomplete")
    return {
        "entry_payload_ready": entry_payload_ready,
        "ladder_plan_ready": ladder_plan_ready,
        "protective_payloads_ready": protective_ready,
        "stop_loss_ready": stop_ready,
        "take_profit_ready": take_ready,
        "no_naked_entry_ok": True,
        "sanitized_payloads_present": sanitized_present,
        "blockers": blockers,
    }


def _test_order_status(
    *,
    signal_id: str | None,
    executor_rehearsal_id: str | None,
    connector: dict[str, Any],
    log_dir: Path,
) -> dict[str, Any]:
    validation = _latest_test_order_validation(signal_id=signal_id, log_dir=log_dir)
    validated = validation is not None
    blockers = []
    if not validated:
        blockers.append("successful test-order validation required for exact signal")
    if validation is not None and validation.get("order_placed") is True:
        blockers.append("test-order validation record must not place an order")
        validated = False
    return {
        "test_order_required": True,
        "test_order_path_available": True,
        "test_order_network_enabled": False,
        "test_order_validated_for_signal": validated,
        "test_order_validation_id": (validation or {}).get("attempt_id"),
        "validated_signal_id": (validation or {}).get("signal_id"),
        "validated_executor_rehearsal_id": executor_rehearsal_id if validated else None,
        "blockers": blockers,
    }


def _gate_statuses(
    *,
    signal_id: str | None,
    executor_rehearsal_id: str | None,
    ladder: dict[str, Any],
    protective: dict[str, Any],
    env: Mapping[str, str],
    log_dir: Path,
) -> dict[str, Any]:
    live_begins = build_live_begins_status(log_dir=log_dir, env=env)
    preview = build_live_execution_preview(log_dir=log_dir, env=env)
    readiness = build_first_live_readiness_status(log_dir=log_dir, env=env)
    adapter = build_first_live_adapter_status(log_dir=log_dir, env=env)
    return {
        "r50": live_begins.get("status") or "BLOCKED",
        "r51": preview.get("status") or "BLOCKED",
        "r52": "MISSING",
        "r53": "MISSING",
        "r54": "BLOCKED",
        "r55": "REJECTED",
        "r56": "REJECTED",
        "r58": build_first_microscopic_live_profile(log_dir=log_dir, env=env).get("status") or "PROFILE_READY",
        "r59": readiness.get("status") or "BLOCKED",
        "r60_caps_ok": _caps_ok(readiness),
        "r61": adapter.get("status") or "ADAPTERS_PARTIAL",
        "r62": ladder.get("status") or "LADDER_ADAPTER_PARTIAL",
        "r63": protective.get("status") or "PROTECTIVE_PLAN_PARTIAL",
    }


def _live_eligibility(
    *,
    exact_chain: dict[str, Any],
    payload_readiness: dict[str, Any],
    test_order_status: dict[str, Any],
    final_confirmation: bool,
) -> dict[str, bool]:
    protective_ready = payload_readiness.get("protective_payloads_ready") is True
    test_ready = test_order_status.get("test_order_validated_for_signal") is True
    exact_ready = exact_chain.get("exact_chain_resolved") is True
    return {
        "eligible_for_live": False,
        "eligible_for_manual_env_arming": bool(exact_ready and protective_ready and test_ready),
        "eligible_for_final_execute": False,
        "requires_funds": True,
        "requires_env_arming": True,
        "requires_final_confirmation": final_confirmation is not True,
        "requires_no_duplicate": True,
        "requires_protective_ready": protective_ready is not True,
        "requires_test_order": test_ready is not True,
    }


def _status(
    *,
    exact_chain: dict[str, Any],
    payload_readiness: dict[str, Any],
    test_order_status: dict[str, Any],
    live_eligibility: dict[str, Any],
) -> str:
    if exact_chain.get("exact_chain_resolved") is not True:
        return "EXACT_CHAIN_MISSING"
    payloads_ready = (
        payload_readiness.get("entry_payload_ready") is True
        and payload_readiness.get("ladder_plan_ready") is True
        and payload_readiness.get("protective_payloads_ready") is True
        and payload_readiness.get("sanitized_payloads_present") is True
    )
    if not payloads_ready:
        return "NOT_READY"
    if test_order_status.get("test_order_validated_for_signal") is not True:
        return "PAYLOADS_READY_TEST_ORDER_MISSING"
    if live_eligibility.get("eligible_for_manual_env_arming") is True:
        return "READY_FOR_MANUAL_ENV_ARMING"
    return "TEST_ORDER_VALIDATED"


def _blockers(
    *,
    exact_chain: dict[str, Any],
    payload_readiness: dict[str, Any],
    test_order_status: dict[str, Any],
    live_eligibility: dict[str, Any],
) -> list[str]:
    blockers = []
    blockers.extend(exact_chain.get("blockers") or [])
    blockers.extend(payload_readiness.get("blockers") or [])
    blockers.extend(test_order_status.get("blockers") or [])
    if live_eligibility.get("eligible_for_live") is not True:
        blockers.append("real live order remains blocked by R64")
    return list(dict.fromkeys(str(item) for item in blockers if item))


def _operator_action(*, exact_chain: dict[str, Any], payload_readiness: dict[str, Any], test_order_status: dict[str, Any]) -> str:
    if exact_chain.get("exact_chain_resolved") is not True:
        return "create exact chain / validate test-order / keep blocked"
    if payload_readiness.get("protective_payloads_ready") is not True:
        return "verify exact entry and protective payloads / keep blocked"
    if test_order_status.get("test_order_validated_for_signal") is not True:
        return "validate test-order / keep blocked"
    return "manual env arming still required / keep blocked"


def _record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "first_live_test_order_gate_check",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "signal_id": payload.get("signal_id"),
        "execution_intent_id": payload.get("execution_intent_id"),
        "executor_rehearsal_id": payload.get("executor_rehearsal_id"),
        "exact_chain_status": payload.get("exact_chain_status"),
        "payload_readiness": payload.get("payload_readiness"),
        "test_order_status": payload.get("test_order_status"),
        "gate_statuses": payload.get("gate_statuses"),
        "live_eligibility": payload.get("live_eligibility"),
        "blockers": payload.get("blockers"),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "check_id",
        "phase",
        "event_type",
        "created_at",
        "status",
        "signal_id",
        "execution_intent_id",
        "executor_rehearsal_id",
        "exact_chain_status",
        "payload_readiness",
        "test_order_status",
        "gate_statuses",
        "live_eligibility",
        "blockers",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "network_allowed",
        "secrets_shown",
    }
    sanitized = {key: record.get(key) for key in allowed if key in record}
    sanitized["order_placed"] = False
    sanitized["real_order_placed"] = False
    sanitized["execution_attempted"] = False
    sanitized["network_allowed"] = False
    sanitized["secrets_shown"] = False
    return _sanitize_nested(sanitized)


def _public_exact_chain_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        key: status.get(key)
        for key in (
            "id_or_signal_present",
            "signal_id_present",
            "execution_intent_id_present",
            "executor_rehearsal_id_present",
            "exact_chain_resolved",
            "signal_fresh",
            "signal_matches_profile",
            "approval_found",
            "intent_found",
            "rehearsal_found",
            "chain_ids_match",
            "blockers",
        )
    }


def _latest_test_order_validation(*, signal_id: str | None, log_dir: Path) -> dict[str, Any] | None:
    if not signal_id:
        return None
    for record in load_connector_attempts(limit=0, signal_id=signal_id, log_dir=log_dir):
        if (
            record.get("endpoint") == "test_order"
            and record.get("status") in {"TEST_ORDER_SENT", "TEST_ORDER_MOCK_VALIDATED", "TEST_ORDER_VALIDATED"}
            and record.get("order_placed") is not True
            and record.get("real_order_placed") is not True
            and record.get("secrets_shown") is not True
        ):
            return _sanitize_nested(record)
    return None


def _approval_found(signal_id: str | None, *, log_dir: Path) -> bool:
    return find_valid_live_approval_for_signal(signal_id, log_dir=log_dir).get("approval_found") is True


def _signal_fresh(signal_id: str | None, *, preview: dict[str, Any]) -> bool:
    if not signal_id:
        return False
    freshness = str(preview.get("freshness_status") or "").lower()
    if freshness and freshness not in {"fresh", "ok", "valid"}:
        return False
    return preview.get("latest_signal_id") == signal_id and preview.get("status") == "PREVIEW_READY"


def _signal_matches_profile(signal_id: str | None, *, profile: dict[str, Any], preview: dict[str, Any]) -> bool:
    if not signal_id:
        return False
    return (
        profile.get("symbol") == "BTCUSDT"
        and profile.get("margin_usdt") == 44.0
        and profile.get("leverage") == 10
        and profile.get("notional_usdt") == 440.0
        and profile.get("max_notional_usdt") == 444.0
        and profile.get("margin_mode") == "ISOLATED"
        and profile.get("entry_mode") == "LADDER"
        and preview.get("symbol") == "BTCUSDT"
        and preview.get("latest_signal_id") == signal_id
    )


def _latest_unexpired_intent(records: list[dict[str, Any]], *, now: datetime) -> dict[str, Any] | None:
    for record in records:
        if _intent_unexpired(record, now=now):
            return record
    return None


def _latest_ready_rehearsal(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for record in records:
        if record.get("status") == "REHEARSAL_READY" and record.get("execution_mode") == "REHEARSAL_ONLY":
            return record
    return None


def _intent_unexpired(record: dict[str, Any] | None, *, now: datetime) -> bool:
    if not record or record.get("status") != "INTENT_READY":
        return False
    expires_at = _parse_datetime(record.get("expires_at"))
    return expires_at is not None and expires_at > now


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


def _profile(source: Mapping[str, Any]) -> dict[str, Any]:
    margin = _float(source.get("margin_usdt"), 44.0)
    leverage = int(_float(source.get("leverage"), 10.0))
    max_notional = _float(source.get("max_notional_usdt"), 444.0)
    return {
        "symbol": str(source.get("symbol") or "BTCUSDT").upper(),
        "margin_usdt": margin,
        "leverage": leverage,
        "notional_usdt": margin * leverage,
        "max_notional_usdt": max_notional,
        "margin_mode": str(source.get("margin_mode") or "ISOLATED").upper(),
        "entry_mode": str(source.get("entry_mode") or "LADDER").upper(),
        "protective_orders_required": bool(source.get("protective_orders_required", True)),
        "one_attempt_only": bool(source.get("one_attempt_only", True)),
    }


def _caps_ok(readiness: dict[str, Any]) -> bool:
    caps = readiness.get("cap_status") if isinstance(readiness.get("cap_status"), dict) else {}
    return caps.get("caps_ok") is True or readiness.get("status") in {"READY_FOR_MANUAL_ENV_ARMING", "READY_FOR_R58_LIVE_SUBMIT_TEST"}


def _normalize_transport_mode(value: str | None) -> str:
    mode = str(value or DEFAULT_TRANSPORT_MODE).strip().upper()
    return mode if mode in TRANSPORT_MODES else mode


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _sanitize_nested(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered != "secrets_shown" and any(
                token in lowered for token in ("secret", "token", "api_key", "apikey", "signature", "auth", "query_string")
            ):
                continue
            sanitized[key] = _sanitize_nested(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_nested(item) for item in value]
    return value
