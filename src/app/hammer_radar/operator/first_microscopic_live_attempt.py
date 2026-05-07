"""R58 first protected microscopic live attempt gate for Hammer Radar.

This module answers whether the selected 44 USDT / 10x isolated ladder profile
can proceed through the exact approved first-live chain. Default behavior is
blocked and record-only; it never mutates env files or calls Binance.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution.binance_futures_connector import (
    LIVE_ORDER_ENABLED,
    LIVE_PROTECTIVE_ENABLED,
    build_connector_status,
    build_protective_status,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.exchange_dry_run import SYMBOL_RULES
from src.app.hammer_radar.operator.first_live_execution_gate import build_first_live_execution_gate
from src.app.hammer_radar.operator.live_arming_checklist import build_live_arming_status
from src.app.hammer_radar.operator.live_begins import build_live_begins_status
from src.app.hammer_radar.operator.live_execution_intent import compute_preview_hash, load_live_execution_intents
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview
from src.app.hammer_radar.operator.live_executor_rehearsal import load_live_executor_rehearsals
from src.app.hammer_radar.operator.live_executor_transport import check_live_executor_transport

PHASE = "R58"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "FIRST_MICROSCOPIC_LIVE_ATTEMPT"
ATTEMPTS_FILENAME = "first_microscopic_live_attempts.ndjson"

FIRST_LIVE_SYMBOL = "BTCUSDT"
FIRST_LIVE_MARGIN_USDT = 44.0
FIRST_LIVE_LEVERAGE = 10
FIRST_LIVE_MAX_NOTIONAL_USDT = 444.0
FIRST_LIVE_MARGIN_MODE = "ISOLATED"
FIRST_LIVE_ENTRY_MODE = "LADDER"
FIRST_LIVE_PROTECTIVE_REQUIRED = True
FIRST_LIVE_ONE_ATTEMPT_ONLY = True
DEFAULT_TRANSPORT_MODE = "DRY_RUN"
TRANSPORT_MODES = {"MOCK", "DRY_RUN", "LIVE"}
FALLBACK_BTCUSDT_ENTRY = 81300.0

ORDER_PLACED = False
REAL_ORDER_PLACED = False
WOULD_PLACE_ORDER = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False


def build_first_microscopic_live_profile(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate(
        executor_rehearsal_id=None,
        execution_intent_id=None,
        signal_id=None,
        final_confirmation=False,
        transport_mode=DEFAULT_TRANSPORT_MODE,
        dry_run=True,
        request_profile=None,
        log_dir=log_dir,
        env=env,
        persist=False,
        action="profile",
    )


def build_first_microscopic_live_status(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate(
        executor_rehearsal_id=None,
        execution_intent_id=None,
        signal_id=None,
        final_confirmation=False,
        transport_mode=DEFAULT_TRANSPORT_MODE,
        dry_run=True,
        request_profile=None,
        log_dir=log_dir,
        env=env,
        persist=False,
        action="status",
    )


def check_first_microscopic_live_attempt(
    *,
    executor_rehearsal_id: str | None = None,
    execution_intent_id: str | None = None,
    signal_id: str | None = None,
    final_confirmation: bool = False,
    transport_mode: str | None = None,
    dry_run: bool = True,
    profile: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        final_confirmation=final_confirmation,
        transport_mode=transport_mode,
        dry_run=dry_run,
        request_profile=profile,
        log_dir=log_dir,
        env=env,
        persist=True,
        action="check",
    )


def execute_first_microscopic_live_attempt(
    *,
    executor_rehearsal_id: str | None = None,
    execution_intent_id: str | None = None,
    signal_id: str | None = None,
    final_confirmation: bool = False,
    transport_mode: str | None = None,
    dry_run: bool = True,
    profile: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        final_confirmation=final_confirmation,
        transport_mode=transport_mode,
        dry_run=dry_run,
        request_profile=profile,
        log_dir=log_dir,
        env=env,
        persist=True,
        action="execute",
    )


def list_first_microscopic_live_attempts(
    *,
    limit: int = 20,
    signal_id: str | None = None,
    transport_mode: str | None = None,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_first_microscopic_live_attempts(
        limit=limit,
        signal_id=signal_id,
        transport_mode=transport_mode,
        status=status,
        log_dir=get_log_dir(log_dir, use_env=True),
    )
    return {
        "result_status": "ACCEPTED",
        "phase": PHASE,
        "count": len(records),
        "attempts": records,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "secrets_shown": SECRETS_SHOWN,
    }


def load_first_microscopic_live_attempts(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    transport_mode: str | None = None,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_microscopic_live_attempts_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            if transport_mode is not None and record.get("transport_mode") != _normalize_transport_mode(transport_mode):
                continue
            if status is not None and record.get("status") != status:
                continue
            records.append(_sanitize_attempt_record(record))
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def first_microscopic_live_attempts_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / ATTEMPTS_FILENAME


def append_first_microscopic_live_attempt(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_microscopic_live_attempts_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_first_microscopic_live_attempt_operator_message(payload: dict[str, Any]) -> str:
    profile = payload.get("profile") or {}
    profile_status = payload.get("profile_status") or {}
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:6]) if blockers else "none"
    return "\n".join(
        [
            f"R58 first protected microscopic live attempt: {payload.get('status')}",
            (
                "selected profile: "
                f"{profile.get('margin_usdt')} USDT margin, {profile.get('leverage')}x, "
                f"{profile.get('margin_mode')}, {profile.get('entry_mode')}, cap {profile.get('max_notional_usdt')}"
            ),
            "no real order unless explicitly true and all gates/env/live adapter permit",
            f"signal_id: {payload.get('signal_id') or 'none'}",
            f"intent_id: {payload.get('execution_intent_id') or 'none'}",
            f"rehearsal_id: {payload.get('executor_rehearsal_id') or 'none'}",
            f"transport_mode: {payload.get('transport_mode')} final_confirmation: {payload.get('final_confirmation')}",
            f"profile_match: {profile_status.get('profile_matches_required')} sizing_valid: {profile_status.get('sizing_valid')}",
            f"order_placed: {payload.get('order_placed')} real_order_placed: {payload.get('real_order_placed')}",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )


def format_first_microscopic_live_attempts_operator_message(payload: dict[str, Any]) -> str:
    attempts = payload.get("attempts") or []
    detail = "none"
    if attempts:
        detail = "; ".join(
            f"{item.get('created_at')} {item.get('transport_mode')} {item.get('status')} {item.get('executor_rehearsal_id') or 'none'}"
            for item in attempts[:5]
        )
    return "\n".join(
        [
            "R58 first protected microscopic live attempt records",
            "selected profile: 44 USDT margin, 10x, isolated, ladder, cap 444",
            f"count: {payload.get('count', 0)}",
            f"attempts: {detail}",
            "order_placed=false real_order_placed=false secrets_shown=false",
        ]
    )


def _evaluate(
    *,
    executor_rehearsal_id: str | None,
    execution_intent_id: str | None,
    signal_id: str | None,
    final_confirmation: bool,
    transport_mode: str | None,
    dry_run: bool,
    request_profile: Mapping[str, Any] | None,
    log_dir: str | Path | None,
    env: Mapping[str, str] | None,
    persist: bool,
    action: str,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC)
    mode = _normalize_transport_mode(transport_mode)
    connector = build_connector_status(env=source, log_dir=resolved_log_dir)
    protective = build_protective_status(env=source, log_dir=resolved_log_dir)
    required_profile = _required_profile(source)
    profile = _merge_profile(required_profile, request_profile)
    preview = build_live_execution_preview(log_dir=resolved_log_dir, env=source)
    profile_status = _profile_status(profile=profile, preview=preview)
    resolved = _resolve_path(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        log_dir=resolved_log_dir,
        now=created_at,
    )
    intent = resolved["intent"]
    rehearsal = resolved["rehearsal"]
    resolved_signal_id = str((rehearsal or {}).get("signal_id") or (intent or {}).get("signal_id") or signal_id or "").strip() or None
    resolved_intent_id = (intent or {}).get("execution_intent_id") or execution_intent_id
    resolved_rehearsal_id = (rehearsal or {}).get("executor_rehearsal_id") or executor_rehearsal_id
    live_begins = build_live_begins_status(log_dir=resolved_log_dir, env=source)
    arming = build_live_arming_status(log_dir=resolved_log_dir, env=source)
    gate = build_first_live_execution_gate(
        executor_rehearsal_id=resolved_rehearsal_id,
        execution_intent_id=resolved_intent_id,
        signal_id=resolved_signal_id,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=resolved_log_dir,
        env=source,
    )
    transport = check_live_executor_transport(
        executor_rehearsal_id=resolved_rehearsal_id,
        execution_intent_id=resolved_intent_id,
        signal_id=resolved_signal_id,
        transport_mode=mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=resolved_log_dir,
        env=source,
    )
    entry_result = _entry_order_result(rehearsal=rehearsal, profile=profile, profile_status=profile_status, mode=mode, action=action)
    protective_results = _protective_order_results(rehearsal=rehearsal, mode=mode, action=action)
    env_status = _env_status(connector=connector, protective=protective)
    gate_statuses = {
        "live_begins_status": live_begins.get("status") or "UNKNOWN",
        "preview_status": preview.get("status") or "UNKNOWN",
        "intent_status": gate.get("intent_status") or _intent_status(intent, preview=preview, now=created_at),
        "rehearsal_status": gate.get("rehearsal_status") or _rehearsal_status(rehearsal, intent=intent, preview=preview),
        "arming_status": arming.get("status") or gate.get("arming_status") or "UNKNOWN",
        "first_live_gate_status": gate.get("status") or "UNKNOWN",
        "transport_status": transport.get("status") or "UNKNOWN",
    }
    checks = _checks(
        action=action,
        requested_present=bool(executor_rehearsal_id or execution_intent_id or signal_id),
        exact_chain_resolved=rehearsal is not None and bool(resolved_signal_id and resolved_intent_id and resolved_rehearsal_id),
        mode=mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        profile_status=profile_status,
        connector=connector,
        protective=protective,
        gate_statuses=gate_statuses,
        entry_result=entry_result,
        protective_results=protective_results,
        signal_id=resolved_signal_id,
        rehearsal_id=resolved_rehearsal_id,
        log_dir=resolved_log_dir,
    )
    blockers = _blockers(
        action=action,
        mode=mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        profile=profile,
        profile_status=profile_status,
        gate_statuses=gate_statuses,
        checks=checks,
    )
    status = _status(action=action, mode=mode, checks=checks, blockers=blockers)
    simulated_order_placed = bool(action == "execute" and mode == "MOCK" and status == "MOCK_RECORDED")
    dry_run_order_recorded = bool(action == "execute" and mode == "DRY_RUN" and status == "DRY_RUN_RECORDED")
    execution_attempted = bool(action == "execute" and status in {"MOCK_RECORDED", "DRY_RUN_RECORDED", "LIVE_READY"})
    network_allowed = bool(mode == "LIVE" and checks["network_gate_open"] and status in {"LIVE_READY", "LIVE_SUBMIT_NOT_IMPLEMENTED"})
    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "created_at": created_at.isoformat(),
        "attempt_id": None,
        "signal_id": resolved_signal_id,
        "execution_intent_id": resolved_intent_id,
        "executor_rehearsal_id": resolved_rehearsal_id,
        "transport_mode": mode,
        "final_confirmation": bool(final_confirmation),
        "dry_run": bool(dry_run),
        "profile": profile,
        "profile_status": profile_status,
        "gate_statuses": gate_statuses,
        "env_status": env_status,
        "network_allowed": network_allowed,
        "would_place_order": bool(mode == "LIVE" and checks["network_gate_open"]),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "simulated_order_placed": simulated_order_placed,
        "dry_run_order_recorded": dry_run_order_recorded,
        "execution_attempted": execution_attempted,
        "entry_order_result": entry_result if status not in {"REJECTED", "BLOCKED", "LIVE_BLOCKED"} else None,
        "protective_order_results": protective_results if status not in {"REJECTED", "BLOCKED", "LIVE_BLOCKED"} else [],
        "checks": checks,
        "blockers": blockers,
        "operator_action": _operator_action(status=status, mode=mode, checks=checks),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "first_microscopic_live_attempts_path": str(first_microscopic_live_attempts_path(resolved_log_dir)),
    }
    if persist:
        record = _attempt_record(payload, event_type="first_microscopic_live_check" if action == "check" else "first_microscopic_live_attempt")
        append_first_microscopic_live_attempt(record, log_dir=resolved_log_dir)
        payload["attempt_id"] = record["attempt_id"]
    return payload


def _required_profile(source: Mapping[str, str]) -> dict[str, Any]:
    return {
        "symbol": FIRST_LIVE_SYMBOL,
        "margin_usdt": _env_float(source, "HAMMER_FIRST_LIVE_MARGIN_USDT", FIRST_LIVE_MARGIN_USDT),
        "leverage": int(_env_float(source, "HAMMER_FIRST_LIVE_LEVERAGE", float(FIRST_LIVE_LEVERAGE))),
        "margin_mode": str(source.get("HAMMER_FIRST_LIVE_MARGIN_MODE") or FIRST_LIVE_MARGIN_MODE).strip().upper(),
        "entry_mode": str(source.get("HAMMER_FIRST_LIVE_ENTRY_MODE") or FIRST_LIVE_ENTRY_MODE).strip().upper(),
        "max_notional_usdt": _env_float(source, "HAMMER_FIRST_LIVE_MAX_NOTIONAL_USDT", FIRST_LIVE_MAX_NOTIONAL_USDT),
        "protective_orders_required": FIRST_LIVE_PROTECTIVE_REQUIRED,
        "one_attempt_only": FIRST_LIVE_ONE_ATTEMPT_ONLY,
    }


def _merge_profile(required: dict[str, Any], override: Mapping[str, Any] | None) -> dict[str, Any]:
    profile = dict(required)
    if override:
        for key in ("margin_usdt", "leverage", "max_notional_usdt", "margin_mode", "entry_mode"):
            if key in override and override.get(key) is not None:
                profile[key] = override[key]
    profile["symbol"] = FIRST_LIVE_SYMBOL
    profile["margin_usdt"] = float(profile["margin_usdt"])
    profile["leverage"] = int(float(profile["leverage"]))
    profile["max_notional_usdt"] = float(profile["max_notional_usdt"])
    profile["margin_mode"] = str(profile["margin_mode"]).strip().upper()
    profile["entry_mode"] = str(profile["entry_mode"]).strip().upper()
    profile["protective_orders_required"] = FIRST_LIVE_PROTECTIVE_REQUIRED
    profile["one_attempt_only"] = FIRST_LIVE_ONE_ATTEMPT_ONLY
    return profile


def _profile_status(*, profile: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    symbol = str(profile.get("symbol") or FIRST_LIVE_SYMBOL)
    rules = SYMBOL_RULES.get(symbol)
    entry = _float_or_none(preview.get("entry")) or FALLBACK_BTCUSDT_ENTRY
    margin = _float_or_none(profile.get("margin_usdt"))
    leverage = _float_or_none(profile.get("leverage"))
    notional = (margin * leverage) if margin is not None and leverage is not None else None
    max_notional = _float_or_none(profile.get("max_notional_usdt"))
    quantity_step = float(rules["step_size"]) if rules else None
    raw_quantity = (notional / entry) if notional is not None and entry not in (None, 0.0) else None
    quantity = _round_to_step(raw_quantity, quantity_step) if raw_quantity is not None and quantity_step else None
    min_notional = float(rules["min_notional_usd"]) if rules else None
    quantity_step_notional = entry * quantity_step if entry is not None and quantity_step is not None else None
    effective_min_notional = _effective_min_notional(min_notional=min_notional, quantity_step_notional=quantity_step_notional)
    min_notional_ok = bool(min_notional is not None and notional is not None and notional >= min_notional)
    effective_min_notional_ok = bool(effective_min_notional is not None and notional is not None and notional >= effective_min_notional)
    quantity_valid = bool(quantity is not None and quantity > 0)
    cap_ok = bool(notional is not None and max_notional is not None and notional <= max_notional)
    profile_matches = (
        symbol == FIRST_LIVE_SYMBOL
        and margin == FIRST_LIVE_MARGIN_USDT
        and int(leverage or 0) == FIRST_LIVE_LEVERAGE
        and max_notional == FIRST_LIVE_MAX_NOTIONAL_USDT
        and str(profile.get("margin_mode")) == FIRST_LIVE_MARGIN_MODE
        and str(profile.get("entry_mode")) == FIRST_LIVE_ENTRY_MODE
        and profile.get("protective_orders_required") is True
        and profile.get("one_attempt_only") is True
    )
    return {
        "profile_matches_required": profile_matches,
        "notional_usdt": notional,
        "notional_cap_ok": cap_ok,
        "entry": entry,
        "quantity_step": quantity_step,
        "min_notional": min_notional,
        "quantity_step_notional_usdt": quantity_step_notional,
        "effective_min_notional_usdt": effective_min_notional,
        "effective_min_reason": "max(min_notional, entry * quantity_step)",
        "quantity": quantity,
        "quantity_valid": quantity_valid,
        "min_notional_ok": min_notional_ok,
        "effective_min_notional_ok": effective_min_notional_ok,
        "sizing_valid": bool(profile_matches and cap_ok and quantity_valid and min_notional_ok and effective_min_notional_ok),
        "ladder_mode_configured": str(profile.get("entry_mode")) == FIRST_LIVE_ENTRY_MODE,
        "ladder_margin_total_cap_usdt": margin,
        "ladder_margin_is_total_cap": True,
    }


def _resolve_path(
    *,
    executor_rehearsal_id: str | None,
    execution_intent_id: str | None,
    signal_id: str | None,
    log_dir: Path,
    now: datetime,
) -> dict[str, dict[str, Any] | None]:
    rehearsal = None
    intent = None
    if executor_rehearsal_id:
        rehearsals = load_live_executor_rehearsals(limit=0, rehearsal_id=executor_rehearsal_id, log_dir=log_dir)
        rehearsal = rehearsals[0] if rehearsals else None
        intent_id = (rehearsal or {}).get("execution_intent_id")
        if intent_id:
            intents = load_live_execution_intents(limit=0, intent_id=str(intent_id), log_dir=log_dir)
            intent = intents[0] if intents else None
        return {"intent": intent, "rehearsal": rehearsal}
    if execution_intent_id:
        intents = load_live_execution_intents(limit=0, intent_id=execution_intent_id, log_dir=log_dir)
        intent = intents[0] if intents else None
        rehearsals = load_live_executor_rehearsals(limit=0, execution_intent_id=execution_intent_id, log_dir=log_dir)
        rehearsal = _latest_ready_rehearsal(rehearsals) or (rehearsals[0] if rehearsals else None)
        return {"intent": intent, "rehearsal": rehearsal}
    if signal_id:
        intents = load_live_execution_intents(limit=0, signal_id=signal_id, log_dir=log_dir)
        intent = _latest_ready_intent(intents, now=now) or (intents[0] if intents else None)
        rehearsals = load_live_executor_rehearsals(
            limit=0,
            signal_id=signal_id,
            execution_intent_id=(intent or {}).get("execution_intent_id"),
            log_dir=log_dir,
        )
        rehearsal = _latest_ready_rehearsal(rehearsals) or (rehearsals[0] if rehearsals else None)
    return {"intent": intent, "rehearsal": rehearsal}


def _latest_ready_intent(records: list[dict[str, Any]], *, now: datetime) -> dict[str, Any] | None:
    for record in records:
        if _intent_unexpired(record, now=now):
            return record
    return None


def _latest_ready_rehearsal(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for record in records:
        if record.get("status") == "REHEARSAL_READY" and record.get("execution_mode") == "REHEARSAL_ONLY":
            return record
    return None


def _intent_status(intent: dict[str, Any] | None, *, preview: dict[str, Any], now: datetime) -> str:
    if intent is None:
        return "MISSING"
    if intent.get("status") != "INTENT_READY" or intent.get("execution_mode") != "INTENT_ONLY":
        return str(intent.get("status") or "UNKNOWN")
    if not _intent_unexpired(intent, now=now):
        return "EXPIRED"
    if intent.get("preview_hash") != compute_preview_hash(preview):
        return "UNKNOWN"
    if intent.get("order_placed") is True or intent.get("real_order_placed") is True or intent.get("execution_attempted") is True:
        return "UNKNOWN"
    return "INTENT_READY"


def _rehearsal_status(rehearsal: dict[str, Any] | None, *, intent: dict[str, Any] | None, preview: dict[str, Any]) -> str:
    if rehearsal is None:
        return "MISSING"
    if rehearsal.get("status") != "REHEARSAL_READY" or rehearsal.get("execution_mode") != "REHEARSAL_ONLY":
        return str(rehearsal.get("status") or "UNKNOWN")
    if intent is None or rehearsal.get("execution_intent_id") != intent.get("execution_intent_id"):
        return "UNKNOWN"
    if rehearsal.get("preview_hash") != compute_preview_hash(preview) or rehearsal.get("preview_hash") != intent.get("preview_hash"):
        return "UNKNOWN"
    if rehearsal.get("network_allowed") is True or rehearsal.get("order_placed") is True or rehearsal.get("real_order_placed") is True:
        return "UNKNOWN"
    if rehearsal.get("execution_attempted") is True or rehearsal.get("secrets_shown") is True:
        return "UNKNOWN"
    return "REHEARSAL_READY"


def _checks(
    *,
    action: str,
    requested_present: bool,
    exact_chain_resolved: bool,
    mode: str,
    final_confirmation: bool,
    dry_run: bool,
    profile_status: dict[str, Any],
    connector: dict[str, Any],
    protective: dict[str, Any],
    gate_statuses: dict[str, str],
    entry_result: dict[str, Any] | None,
    protective_results: list[dict[str, Any]],
    signal_id: str | None,
    rehearsal_id: str | None,
    log_dir: Path,
) -> dict[str, bool]:
    live_env_allows = (
        connector.get("live_execution_enabled") is True
        and connector.get("binance_live_enabled") is True
        and connector.get("allow_live_orders") is True
        and connector.get("global_kill_switch") is False
        and connector.get("connector_mode") == LIVE_ORDER_ENABLED
    )
    network_gate_open = (
        mode == "LIVE"
        and dry_run is False
        and final_confirmation is True
        and live_env_allows
        and _protective_ready(protective)
        and gate_statuses.get("live_begins_status") == "ELIGIBLE_TINY_LIVE"
        and gate_statuses.get("preview_status") == "PREVIEW_READY"
        and gate_statuses.get("intent_status") == "INTENT_READY"
        and gate_statuses.get("rehearsal_status") == "REHEARSAL_READY"
        and gate_statuses.get("arming_status") == "ARMING_ALLOWED"
        and gate_statuses.get("first_live_gate_status") == "EXECUTION_GATE_READY"
        and gate_statuses.get("transport_status") in {"LIVE_READY", "TRANSPORT_READY"}
    )
    return {
        "id_or_signal_present": requested_present,
        "exact_chain_resolved": exact_chain_resolved,
        "profile_matches_required": profile_status.get("profile_matches_required") is True,
        "profile_notional_valid": profile_status.get("sizing_valid") is True,
        "profile_notional_cap_ok": profile_status.get("notional_cap_ok") is True,
        "quantity_valid": profile_status.get("quantity_valid") is True,
        "protective_orders_ready": _protective_ready(protective),
        "r50_allows": gate_statuses.get("live_begins_status") == "ELIGIBLE_TINY_LIVE",
        "r51_allows": gate_statuses.get("preview_status") == "PREVIEW_READY",
        "r52_allows": gate_statuses.get("intent_status") == "INTENT_READY",
        "r53_allows": gate_statuses.get("rehearsal_status") == "REHEARSAL_READY",
        "r54_allows": gate_statuses.get("arming_status") == "ARMING_ALLOWED",
        "r55_allows": gate_statuses.get("first_live_gate_status") == "EXECUTION_GATE_READY",
        "r56_allows": gate_statuses.get("transport_status") in {"LIVE_READY", "TRANSPORT_READY", "DRY_RUN_ATTEMPT_RECORDED", "MOCK_ATTEMPT_RECORDED"},
        "final_confirmation_present": final_confirmation is True,
        "live_env_allows": live_env_allows,
        "idempotency_clear": _idempotency_clear(signal_id=signal_id, rehearsal_id=rehearsal_id, mode=mode, log_dir=log_dir),
        "one_attempt_only_clear": _idempotency_clear(signal_id=signal_id, rehearsal_id=rehearsal_id, mode="LIVE", log_dir=log_dir),
        "network_gate_open": network_gate_open,
        "live_adapter_available": False,
        "transport_mode_valid": mode in TRANSPORT_MODES,
        "entry_payload_present": isinstance(entry_result, dict),
        "protective_payloads_present": len(protective_results) >= 2,
        "ladder_mode_configured": profile_status.get("ladder_mode_configured") is True,
        "ladder_margin_is_total_cap": profile_status.get("ladder_margin_is_total_cap") is True,
        "profile_only": action == "profile",
        "status_only": action == "status",
    }


def _blockers(
    *,
    action: str,
    mode: str,
    final_confirmation: bool,
    dry_run: bool,
    profile: dict[str, Any],
    profile_status: dict[str, Any],
    gate_statuses: dict[str, str],
    checks: dict[str, bool],
) -> list[str]:
    blockers: list[str] = []
    if not checks["transport_mode_valid"]:
        blockers.append(f"transport_mode is invalid: {mode}")
    if not checks["profile_matches_required"]:
        blockers.append("profile does not match required 44/10/444 ISOLATED LADDER profile")
    if not checks["profile_notional_cap_ok"]:
        blockers.append(f"profile notional exceeds cap {profile.get('max_notional_usdt')}")
    if not checks["quantity_valid"]:
        blockers.append("quantity is invalid under local symbol filters")
    if not checks["profile_notional_valid"]:
        blockers.append("profile notional does not satisfy local min/effective notional filters")
    if action not in {"profile", "status"}:
        if not checks["id_or_signal_present"]:
            blockers.append("executor_rehearsal_id, execution_intent_id, or signal_id is required")
        if not checks["exact_chain_resolved"]:
            blockers.append("exact approved intent/rehearsal chain could not be resolved")
        if not checks["entry_payload_present"]:
            blockers.append("entry order result payload is missing")
        if not checks["protective_payloads_present"]:
            blockers.append("protective order results are missing")
    for key, label in (
        ("r50_allows", "R50 live-begins"),
        ("r51_allows", "R51 preview"),
        ("r52_allows", "R52 intent"),
        ("r53_allows", "R53 rehearsal"),
        ("r54_allows", "R54 arming"),
        ("r55_allows", "R55 first execution gate"),
        ("r56_allows", "R56 transport"),
    ):
        if not checks[key] and action != "profile":
            status_key = {
                "r50_allows": "live_begins_status",
                "r51_allows": "preview_status",
                "r52_allows": "intent_status",
                "r53_allows": "rehearsal_status",
                "r54_allows": "arming_status",
                "r55_allows": "first_live_gate_status",
                "r56_allows": "transport_status",
            }[key]
            blockers.append(f"{label} is {gate_statuses.get(status_key, 'UNKNOWN')}")
    if mode == "LIVE":
        if final_confirmation is not True:
            blockers.append("final confirmation is required for live attempt")
        if dry_run is True:
            blockers.append("dry_run must be false for live attempt")
        if not checks["live_env_allows"]:
            blockers.append("live env flags do not allow live orders")
        if not checks["protective_orders_ready"]:
            blockers.append("protective orders are required but not live-ready")
        if not checks["one_attempt_only_clear"]:
            blockers.append("one-attempt-only idempotency is not clear")
        if not checks["network_gate_open"]:
            blockers.append("network gate is closed")
        if not checks["live_adapter_available"]:
            blockers.append("live submit adapter is not implemented for R58 ladder attempt")
    else:
        if not checks["idempotency_clear"] and action == "execute":
            blockers.append("idempotency is not clear for first microscopic attempt")
    if profile_status.get("ladder_mode_configured") is True:
        blockers.append("ladder live executor is not implemented; dry-run/mock record aggregate preview only") if mode == "LIVE" else None
    return list(dict.fromkeys(blocker for blocker in blockers if blocker))


def _status(*, action: str, mode: str, checks: dict[str, bool], blockers: list[str]) -> str:
    if action == "profile":
        return "PROFILE_READY" if checks["profile_matches_required"] and checks["profile_notional_valid"] else "BLOCKED"
    if not checks["id_or_signal_present"] and action in {"check", "execute"}:
        return "REJECTED"
    if action == "status":
        return "LIVE_READY" if checks["network_gate_open"] and checks["live_adapter_available"] else "BLOCKED"
    if action == "check":
        if blockers:
            return "LIVE_BLOCKED" if mode == "LIVE" else "BLOCKED"
        return "LIVE_READY" if mode == "LIVE" else "CHECK_READY"
    if mode == "LIVE":
        allowed_missing_adapter_blockers = {
            "live submit adapter is not implemented for R58 ladder attempt",
            "ladder live executor is not implemented; dry-run/mock record aggregate preview only",
        }
        if checks["network_gate_open"] and not checks["live_adapter_available"] and set(blockers).issubset(allowed_missing_adapter_blockers):
            return "LIVE_SUBMIT_NOT_IMPLEMENTED"
        return "LIVE_BLOCKED"
    if blockers:
        return "BLOCKED"
    if mode == "MOCK":
        return "MOCK_RECORDED"
    if mode == "DRY_RUN":
        return "DRY_RUN_RECORDED"
    return "BLOCKED"


def _operator_action(*, status: str, mode: str, checks: dict[str, bool]) -> str:
    if status in {"MOCK_RECORDED", "CHECK_READY"} and mode == "MOCK":
        return "run dry-run"
    if status in {"DRY_RUN_RECORDED", "CHECK_READY"} and mode == "DRY_RUN":
        return "final live confirmation required"
    if status == "LIVE_SUBMIT_NOT_IMPLEMENTED":
        return "live adapter missing"
    if mode == "LIVE" and not checks["final_confirmation_present"]:
        return "final live confirmation required"
    if mode == "LIVE" and not checks["live_env_allows"]:
        return "arm env manually"
    if not checks["exact_chain_resolved"]:
        return "create fresh chain"
    return "keep blocked"


def _env_status(*, connector: dict[str, Any], protective: dict[str, Any]) -> dict[str, Any]:
    return {
        "live_execution_enabled": bool(connector.get("live_execution_enabled")),
        "binance_live_enabled": bool(connector.get("binance_live_enabled")),
        "allow_live_orders": bool(connector.get("allow_live_orders")),
        "global_kill_switch": bool(connector.get("global_kill_switch")),
        "connector_mode": connector.get("connector_mode") or "DRY_RUN_ONLY",
        "protective_orders_enabled": bool(protective.get("protective_orders_enabled")),
        "protective_order_mode": protective.get("protective_order_mode") or "PREVIEW_ONLY",
    }


def _protective_ready(protective: dict[str, Any]) -> bool:
    return (
        protective.get("protective_orders_required") is True
        and protective.get("protective_orders_enabled") is True
        and protective.get("protective_order_mode") == LIVE_PROTECTIVE_ENABLED
        and protective.get("protective_orders_supported") is True
        and protective.get("protective_stop_supported") is True
        and protective.get("protective_take_profit_supported") is True
    )


def _entry_order_result(
    *,
    rehearsal: dict[str, Any] | None,
    profile: dict[str, Any],
    profile_status: dict[str, Any],
    mode: str,
    action: str,
) -> dict[str, Any] | None:
    preview = (rehearsal or {}).get("entry_order_preview")
    result = _sanitize_nested(preview) if isinstance(preview, dict) else {}
    result.update(
        {
            "status": "MOCK_VALIDATED" if mode == "MOCK" else "DRY_RUN_RECORDED" if mode == "DRY_RUN" else "LIVE_GUARDED",
            "transport_mode": mode,
            "symbol": profile.get("symbol"),
            "margin_usdt": profile.get("margin_usdt"),
            "leverage": profile.get("leverage"),
            "notional_usdt": profile_status.get("notional_usdt"),
            "quantity": profile_status.get("quantity"),
            "margin_mode": profile.get("margin_mode"),
            "entry_mode": profile.get("entry_mode"),
            "ladder_mode_configured": True,
            "ladder_margin_total_cap_usdt": profile.get("margin_usdt"),
            "aggregate_preview_only": True,
            "order_id": f"mock-r58-{uuid4().hex[:12]}" if action == "execute" and mode == "MOCK" else None,
            "preview_only": mode != "DRY_RUN",
            "dry_run_only": mode == "DRY_RUN",
            "real_order_placed": False,
            "secrets_shown": False,
        }
    )
    return result


def _protective_order_results(*, rehearsal: dict[str, Any] | None, mode: str, action: str) -> list[dict[str, Any]]:
    protective = (rehearsal or {}).get("protective_orders_preview")
    if not isinstance(protective, dict):
        return []
    results = []
    for leg_name in ("stop_loss", "take_profit"):
        leg = protective.get(leg_name)
        if not isinstance(leg, dict):
            continue
        result = _sanitize_nested(leg)
        result.update(
            {
                "leg": leg_name,
                "transport_mode": mode,
                "status": "MOCK_VALIDATED" if mode == "MOCK" else "DRY_RUN_RECORDED" if mode == "DRY_RUN" else "LIVE_GUARDED",
                "order_id": f"mock-r58-{leg_name}-{uuid4().hex[:12]}" if action == "execute" and mode == "MOCK" else None,
                "preview_only": mode != "DRY_RUN",
                "dry_run_only": mode == "DRY_RUN",
                "reduce_only": True,
                "real_order_placed": False,
                "secrets_shown": False,
            }
        )
        results.append(result)
    return results


def _idempotency_clear(*, signal_id: str | None, rehearsal_id: str | None, mode: str, log_dir: Path) -> bool:
    if mode == "LIVE" and not (signal_id or rehearsal_id):
        return False
    for record in _load_raw_attempts(log_dir=log_dir):
        same_signal = signal_id is not None and record.get("signal_id") == signal_id
        same_rehearsal = rehearsal_id is not None and record.get("executor_rehearsal_id") == rehearsal_id
        if not (same_signal or same_rehearsal):
            continue
        if record.get("transport_mode") == "LIVE" and (
            record.get("execution_attempted") is True
            or record.get("order_placed") is True
            or record.get("real_order_placed") is True
            or record.get("status") in {"LIVE_READY", "LIVE_SUBMIT_NOT_IMPLEMENTED", "LIVE_ORDER_PLACED"}
        ):
            return False
    return True


def _load_raw_attempts(*, log_dir: Path) -> list[dict[str, Any]]:
    path = first_microscopic_live_attempts_path(log_dir)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return list(reversed(records))


def _attempt_record(payload: dict[str, Any], *, event_type: str) -> dict[str, Any]:
    return {
        "attempt_id": uuid4().hex,
        "phase": PHASE,
        "event_type": event_type,
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "profile": payload.get("profile"),
        "profile_status": payload.get("profile_status"),
        "signal_id": payload.get("signal_id"),
        "execution_intent_id": payload.get("execution_intent_id"),
        "executor_rehearsal_id": payload.get("executor_rehearsal_id"),
        "transport_mode": payload.get("transport_mode"),
        "final_confirmation": bool(payload.get("final_confirmation")),
        "dry_run": bool(payload.get("dry_run")),
        "network_allowed": bool(payload.get("network_allowed")),
        "order_placed": False,
        "real_order_placed": False,
        "simulated_order_placed": bool(payload.get("simulated_order_placed")),
        "dry_run_order_recorded": bool(payload.get("dry_run_order_recorded")),
        "execution_attempted": bool(payload.get("execution_attempted")),
        "entry_order_result": payload.get("entry_order_result"),
        "protective_order_results": payload.get("protective_order_results") or [],
        "blockers": payload.get("blockers") or [],
        "secrets_shown": False,
    }


def _sanitize_attempt_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "attempt_id",
        "phase",
        "event_type",
        "created_at",
        "status",
        "profile",
        "profile_status",
        "signal_id",
        "execution_intent_id",
        "executor_rehearsal_id",
        "transport_mode",
        "final_confirmation",
        "dry_run",
        "network_allowed",
        "order_placed",
        "real_order_placed",
        "simulated_order_placed",
        "dry_run_order_recorded",
        "execution_attempted",
        "entry_order_result",
        "protective_order_results",
        "blockers",
        "secrets_shown",
    }
    sanitized = {key: record.get(key) for key in allowed if key in record}
    sanitized["order_placed"] = False
    sanitized["real_order_placed"] = False
    sanitized["secrets_shown"] = False
    return _sanitize_nested(sanitized)


def _normalize_transport_mode(value: str | None) -> str:
    mode = str(value or DEFAULT_TRANSPORT_MODE).strip().upper().replace("-", "_")
    if mode in {"MOCK_EXECUTOR", "MOCK"}:
        return "MOCK"
    if mode in {"DRY_RUN_EXECUTOR", "DRY_RUN", "DRYRUN"}:
        return "DRY_RUN"
    if mode in {"LIVE_EXECUTOR", "LIVE"}:
        return "LIVE"
    return mode


def _intent_unexpired(record: dict[str, Any], *, now: datetime) -> bool:
    expires_at = _parse_datetime(record.get("expires_at"))
    return expires_at is not None and expires_at > now and record.get("status") == "INTENT_READY"


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _effective_min_notional(*, min_notional: float | None, quantity_step_notional: float | None) -> float | None:
    values = [value for value in (min_notional, quantity_step_notional) if value is not None and value > 0]
    if not values:
        return None
    return max(values)


def _round_to_step(value: float | None, step: float | None) -> float | None:
    if value is None or step is None or step <= 0:
        return None
    decimal_value = Decimal(str(value))
    decimal_step = Decimal(str(step))
    rounded = (decimal_value / decimal_step).to_integral_value(rounding=ROUND_DOWN) * decimal_step
    precision = max(0, -decimal_step.as_tuple().exponent)
    return float(round(rounded, precision))


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def _env_float(source: Mapping[str, str], key: str, default: float) -> float:
    value = _float_or_none(source.get(key))
    return default if value is None else value


def _sanitize_nested(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("secret", "token", "api_key", "apikey", "signature")):
                continue
            sanitized[key] = _sanitize_nested(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_nested(item) for item in value]
    return value
