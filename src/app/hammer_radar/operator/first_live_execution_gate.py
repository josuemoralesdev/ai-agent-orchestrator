"""R55 first protected tiny-live execution gate for Hammer Radar.

This module is the final pre-executor verdict. It composes R50-R54 state,
operator final confirmation, live env gates, protective-order readiness, and
idempotency into one sanitized answer. It does not place orders, sign payloads,
enable live trading, or call Binance.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
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
from src.app.hammer_radar.operator.live_arming_checklist import build_live_arming_status
from src.app.hammer_radar.operator.live_begins import build_live_begins_status
from src.app.hammer_radar.operator.live_execution_intent import compute_preview_hash, load_live_execution_intents
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview
from src.app.hammer_radar.operator.live_executor_rehearsal import load_live_executor_rehearsals

PHASE = "R55"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "FIRST_LIVE_GATE"
FIRST_LIVE_EXECUTION_GATES_FILENAME = "first_live_execution_gates.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
WOULD_PLACE_ORDER = False
EXECUTION_ATTEMPTED = False
SECRETS_SHOWN = False


def build_first_live_execution_gate(
    *,
    execution_intent_id: str | None = None,
    executor_rehearsal_id: str | None = None,
    signal_id: str | None = None,
    final_confirmation: bool = False,
    dry_run: bool = True,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_first_live_execution_gate(
        execution_intent_id=execution_intent_id,
        executor_rehearsal_id=executor_rehearsal_id,
        signal_id=signal_id,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=log_dir,
        env=env,
        persist=False,
    )


def evaluate_and_record_first_live_execution_gate(
    *,
    execution_intent_id: str | None = None,
    executor_rehearsal_id: str | None = None,
    signal_id: str | None = None,
    final_confirmation: bool = False,
    dry_run: bool = True,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_first_live_execution_gate(
        execution_intent_id=execution_intent_id,
        executor_rehearsal_id=executor_rehearsal_id,
        signal_id=signal_id,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=log_dir,
        env=env,
        persist=True,
    )


def list_first_live_execution_gates(
    *,
    limit: int = 20,
    signal_id: str | None = None,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_first_live_execution_gates(limit=limit, signal_id=signal_id, status=status, log_dir=get_log_dir(log_dir, use_env=True))
    return {
        "result_status": "ACCEPTED",
        "phase": PHASE,
        "count": len(records),
        "gates": records,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "secrets_shown": SECRETS_SHOWN,
    }


def load_first_live_execution_gates(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_execution_gates_path(get_log_dir(log_dir, use_env=True))
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
            if status is not None and record.get("status") != status:
                continue
            records.append(_sanitize_gate_record(record))
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def first_live_execution_gates_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / FIRST_LIVE_EXECUTION_GATES_FILENAME


def append_first_live_execution_gate(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_execution_gates_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_first_live_execution_gate_operator_message(payload: dict[str, Any]) -> str:
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:5]) if blockers else "none"
    return "\n".join(
        [
            f"R55 first protected tiny-live execution gate: {payload.get('status')}",
            f"No order placed unless explicitly true. order_placed={payload.get('order_placed')} real_order_placed={payload.get('real_order_placed')}.",
            f"signal_id: {payload.get('signal_id') or 'none'}",
            f"intent/rehearsal: {payload.get('execution_intent_id') or 'none'} / {payload.get('executor_rehearsal_id') or 'none'}",
            f"final_confirmation: {payload.get('final_confirmation')} dry_run: {payload.get('dry_run')}",
            f"live flags: live_execution={payload.get('live_execution_enabled')} binance_live={payload.get('binance_live_enabled')} allow_live_orders={payload.get('allow_live_orders')}",
            f"kill_switch: {payload.get('global_kill_switch')} connector_mode: {payload.get('connector_mode')} arming_status: {payload.get('arming_status')}",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )


def format_first_live_execution_gates_operator_message(payload: dict[str, Any]) -> str:
    gates = payload.get("gates") or []
    if not gates:
        detail = "none"
    else:
        detail = "; ".join(
            f"{item.get('created_at')} {item.get('status')} {item.get('signal_id') or 'none'}"
            for item in gates[:5]
        )
    return "\n".join(
        [
            "R55 first protected tiny-live execution gates",
            "FIRST_LIVE_GATE list. No order placed.",
            f"count: {payload.get('count', 0)}",
            f"gates: {detail}",
        ]
    )


def _evaluate_first_live_execution_gate(
    *,
    execution_intent_id: str | None,
    executor_rehearsal_id: str | None,
    signal_id: str | None,
    final_confirmation: bool,
    dry_run: bool,
    log_dir: str | Path | None,
    env: Mapping[str, str] | None,
    persist: bool,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC)
    connector = build_connector_status(env=source, log_dir=resolved_log_dir)
    protective = build_protective_status(env=source, log_dir=resolved_log_dir)
    live_begins = build_live_begins_status(log_dir=resolved_log_dir, env=source)
    preview = build_live_execution_preview(log_dir=resolved_log_dir, env=source)
    arming = build_live_arming_status(log_dir=resolved_log_dir, env=source)
    resolved = _resolve_path(
        execution_intent_id=execution_intent_id,
        executor_rehearsal_id=executor_rehearsal_id,
        signal_id=signal_id,
        log_dir=resolved_log_dir,
        now=created_at,
    )
    intent = resolved["intent"]
    rehearsal = resolved["rehearsal"]
    resolved_signal_id = str((rehearsal or {}).get("signal_id") or (intent or {}).get("signal_id") or signal_id or "").strip() or None
    resolved_intent_id = (intent or {}).get("execution_intent_id") or execution_intent_id
    resolved_rehearsal_id = (rehearsal or {}).get("executor_rehearsal_id") or executor_rehearsal_id
    preview_hash = compute_preview_hash(preview) if preview.get("status") != "UNKNOWN" else None
    intent_status = _intent_status(intent, preview_hash=preview_hash, now=created_at)
    rehearsal_status = _rehearsal_status(rehearsal, intent=intent, preview_hash=preview_hash)
    entry_payload = _entry_payload_preview(rehearsal)
    protective_payloads = _protective_payloads_preview(rehearsal)
    checks = _checks(
        requested_present=bool(execution_intent_id or executor_rehearsal_id or signal_id),
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        connector=connector,
        protective=protective,
        live_begins=live_begins,
        preview=preview,
        intent_status=intent_status,
        rehearsal_status=rehearsal_status,
        arming=arming,
        entry_payload=entry_payload,
        protective_payloads=protective_payloads,
        signal_id=resolved_signal_id,
        intent_id=resolved_intent_id,
        rehearsal_id=resolved_rehearsal_id,
        log_dir=resolved_log_dir,
    )
    blockers = _blockers(
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        connector=connector,
        protective=protective,
        live_begins=live_begins,
        preview=preview,
        intent_status=intent_status,
        rehearsal_status=rehearsal_status,
        arming=arming,
        checks=checks,
    )
    status = _status(checks=checks, blockers=blockers, final_confirmation=final_confirmation)
    network_allowed = _network_allowed(checks=checks, dry_run=dry_run)
    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "created_at": created_at.isoformat(),
        "signal_id": resolved_signal_id,
        "execution_intent_id": resolved_intent_id,
        "executor_rehearsal_id": resolved_rehearsal_id,
        "gate_evaluation_id": None,
        "final_confirmation": bool(final_confirmation),
        "dry_run": bool(dry_run),
        "live_execution_enabled": bool(connector.get("live_execution_enabled")),
        "binance_live_enabled": bool(connector.get("binance_live_enabled")),
        "allow_live_orders": bool(connector.get("allow_live_orders")),
        "global_kill_switch": bool(connector.get("global_kill_switch")),
        "connector_mode": connector.get("connector_mode") or "DRY_RUN_ONLY",
        "protective_orders_required": bool(protective.get("protective_orders_required")),
        "protective_orders_enabled": bool(protective.get("protective_orders_enabled")),
        "protective_order_mode": protective.get("protective_order_mode") or "PREVIEW_ONLY",
        "live_begins_status": live_begins.get("status") or "UNKNOWN",
        "preview_status": preview.get("status") or "UNKNOWN",
        "intent_status": intent_status,
        "rehearsal_status": rehearsal_status,
        "arming_status": arming.get("status") or "UNKNOWN",
        "network_allowed": network_allowed,
        "would_place_order": WOULD_PLACE_ORDER,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "entry_order_payload_preview": entry_payload,
        "protective_order_payloads_preview": protective_payloads,
        "checks": checks,
        "blockers": blockers,
        "operator_action": _operator_action(status=status, checks=checks),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "first_live_execution_gates_path": str(first_live_execution_gates_path(resolved_log_dir)),
    }
    if persist:
        record = _gate_record(payload)
        append_first_live_execution_gate(record, log_dir=resolved_log_dir)
        payload["gate_evaluation_id"] = record["gate_evaluation_id"]
    return payload


def _resolve_path(
    *,
    execution_intent_id: str | None,
    executor_rehearsal_id: str | None,
    signal_id: str | None,
    log_dir: Path,
    now: datetime,
) -> dict[str, dict[str, Any] | None]:
    rehearsal = None
    intent = None
    if executor_rehearsal_id:
        records = load_live_executor_rehearsals(limit=0, rehearsal_id=executor_rehearsal_id, log_dir=log_dir)
        rehearsal = records[0] if records else None
        intent_id = (rehearsal or {}).get("execution_intent_id")
        if intent_id:
            intent_records = load_live_execution_intents(limit=0, intent_id=str(intent_id), log_dir=log_dir)
            intent = intent_records[0] if intent_records else None
        return {"intent": intent, "rehearsal": rehearsal}
    if execution_intent_id:
        intent_records = load_live_execution_intents(limit=0, intent_id=execution_intent_id, log_dir=log_dir)
        intent = intent_records[0] if intent_records else None
        rehearsal_records = load_live_executor_rehearsals(limit=0, execution_intent_id=execution_intent_id, log_dir=log_dir)
        rehearsal = _latest_ready_rehearsal(rehearsal_records) or (rehearsal_records[0] if rehearsal_records else None)
        return {"intent": intent, "rehearsal": rehearsal}
    if signal_id:
        intent_records = load_live_execution_intents(limit=0, signal_id=signal_id, log_dir=log_dir)
        intent = _latest_ready_intent(intent_records, now=now) or (intent_records[0] if intent_records else None)
        rehearsal_records = load_live_executor_rehearsals(
            limit=0,
            signal_id=signal_id,
            execution_intent_id=(intent or {}).get("execution_intent_id"),
            log_dir=log_dir,
        )
        rehearsal = _latest_ready_rehearsal(rehearsal_records) or (rehearsal_records[0] if rehearsal_records else None)
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


def _intent_status(intent: dict[str, Any] | None, *, preview_hash: str | None, now: datetime) -> str:
    if intent is None:
        return "MISSING"
    if intent.get("status") != "INTENT_READY" or intent.get("execution_mode") != "INTENT_ONLY":
        return str(intent.get("status") or "UNKNOWN")
    if not _intent_unexpired(intent, now=now):
        return "EXPIRED"
    if intent.get("preview_hash") != preview_hash:
        return "UNKNOWN"
    if intent.get("order_placed") is True or intent.get("real_order_placed") is True or intent.get("execution_attempted") is True:
        return "UNKNOWN"
    if intent.get("secrets_shown") is True:
        return "UNKNOWN"
    return "INTENT_READY"


def _rehearsal_status(rehearsal: dict[str, Any] | None, *, intent: dict[str, Any] | None, preview_hash: str | None) -> str:
    if rehearsal is None:
        return "MISSING"
    if rehearsal.get("status") != "REHEARSAL_READY" or rehearsal.get("execution_mode") != "REHEARSAL_ONLY":
        return str(rehearsal.get("status") or "UNKNOWN")
    if intent is None or rehearsal.get("execution_intent_id") != intent.get("execution_intent_id"):
        return "UNKNOWN"
    if rehearsal.get("preview_hash") != preview_hash or rehearsal.get("preview_hash") != intent.get("preview_hash"):
        return "UNKNOWN"
    if rehearsal.get("network_allowed") is True or rehearsal.get("order_placed") is True or rehearsal.get("real_order_placed") is True:
        return "UNKNOWN"
    if rehearsal.get("execution_attempted") is True or rehearsal.get("secrets_shown") is True:
        return "UNKNOWN"
    return "REHEARSAL_READY"


def _checks(
    *,
    requested_present: bool,
    final_confirmation: bool,
    dry_run: bool,
    connector: dict[str, Any],
    protective: dict[str, Any],
    live_begins: dict[str, Any],
    preview: dict[str, Any],
    intent_status: str,
    rehearsal_status: str,
    arming: dict[str, Any],
    entry_payload: dict[str, Any] | None,
    protective_payloads: dict[str, Any] | None,
    signal_id: str | None,
    intent_id: str | None,
    rehearsal_id: str | None,
    log_dir: Path,
) -> dict[str, bool]:
    live_flags_ready = (
        connector.get("live_execution_enabled") is True
        and connector.get("binance_live_enabled") is True
        and connector.get("allow_live_orders") is True
        and connector.get("global_kill_switch") is False
        and connector.get("connector_mode") == LIVE_ORDER_ENABLED
    )
    protective_ready = _protective_ready(protective)
    return {
        "signal_or_intent_or_rehearsal_present": requested_present,
        "final_confirmation_present": final_confirmation is True,
        "live_begins_allows_execution": live_begins.get("status") == "ELIGIBLE_TINY_LIVE",
        "preview_ready": preview.get("status") == "PREVIEW_READY",
        "intent_ready": intent_status == "INTENT_READY",
        "rehearsal_ready": rehearsal_status == "REHEARSAL_READY",
        "arming_allowed": arming.get("status") == "ARMING_ALLOWED",
        "live_execution_enabled": connector.get("live_execution_enabled") is True,
        "binance_live_enabled": connector.get("binance_live_enabled") is True,
        "allow_live_orders": connector.get("allow_live_orders") is True,
        "global_kill_switch_off": connector.get("global_kill_switch") is False,
        "connector_mode_allows_live": connector.get("connector_mode") == LIVE_ORDER_ENABLED,
        "protective_orders_ready": protective_ready,
        "entry_payload_valid": _entry_payload_valid(entry_payload),
        "protective_payloads_valid": _protective_payloads_valid(protective_payloads),
        "idempotency_clear": _idempotency_clear(signal_id=signal_id, intent_id=intent_id, rehearsal_id=rehearsal_id, log_dir=log_dir),
        "dry_run_or_live_path_explicit": dry_run is True or (final_confirmation is True and live_flags_ready and protective_ready),
        "network_gate_open": final_confirmation is True and dry_run is False and live_flags_ready and protective_ready,
    }


def _blockers(
    *,
    final_confirmation: bool,
    dry_run: bool,
    connector: dict[str, Any],
    protective: dict[str, Any],
    live_begins: dict[str, Any],
    preview: dict[str, Any],
    intent_status: str,
    rehearsal_status: str,
    arming: dict[str, Any],
    checks: dict[str, bool],
) -> list[str]:
    blockers: list[str] = []
    if not checks["signal_or_intent_or_rehearsal_present"]:
        blockers.append("signal_id, execution_intent_id, or executor_rehearsal_id is required")
    if final_confirmation is not True:
        blockers.append("final confirmation is required")
    if not checks["live_begins_allows_execution"]:
        blockers.append(f"live begins is {live_begins.get('status', 'UNKNOWN')}")
    if not checks["preview_ready"]:
        blockers.append(f"execution preview is {preview.get('status', 'UNKNOWN')}")
    if not checks["intent_ready"]:
        blockers.append(f"execution intent is {intent_status}")
    if not checks["rehearsal_ready"]:
        blockers.append(f"executor rehearsal is {rehearsal_status}")
    if not checks["arming_allowed"]:
        blockers.append(f"arming status is {arming.get('status', 'UNKNOWN')}")
    if not checks["live_execution_enabled"]:
        blockers.append("live_execution_enabled is false")
    if not checks["binance_live_enabled"]:
        blockers.append("HAMMER_BINANCE_LIVE_ENABLED is false")
    if not checks["allow_live_orders"]:
        blockers.append("allow_live_orders is false")
    if not checks["global_kill_switch_off"]:
        blockers.append("global kill switch is active")
    if not checks["connector_mode_allows_live"]:
        blockers.append(f"connector_mode is {connector.get('connector_mode', 'UNKNOWN')}")
    if not checks["protective_orders_ready"]:
        blockers.append(f"protective orders are required but not ready/enabled; mode={protective.get('protective_order_mode', 'UNKNOWN')}")
    if not checks["entry_payload_valid"]:
        blockers.append("entry order payload preview is missing or invalid")
    if not checks["protective_payloads_valid"]:
        blockers.append("protective order payload previews are missing or invalid")
    if not checks["idempotency_clear"]:
        blockers.append("idempotency is not clear for first-live execution")
    if dry_run is not True and not checks["network_gate_open"]:
        blockers.append("network gate is closed")
    if not checks["dry_run_or_live_path_explicit"]:
        blockers.append("dry-run or explicit live path is required")
    return list(dict.fromkeys(blocker for blocker in blockers if blocker))


def _status(*, checks: dict[str, bool], blockers: list[str], final_confirmation: bool) -> str:
    if not checks["signal_or_intent_or_rehearsal_present"]:
        return "REJECTED"
    non_confirmation_blockers = [blocker for blocker in blockers if blocker != "final confirmation is required"]
    if final_confirmation is not True and not non_confirmation_blockers:
        return "FINAL_CONFIRMATION_REQUIRED"
    if not blockers:
        return "EXECUTION_GATE_READY"
    return "BLOCKED"


def _operator_action(*, status: str, checks: dict[str, bool]) -> str:
    if status == "EXECUTION_GATE_READY":
        return "ready for first tiny live"
    if status == "FINAL_CONFIRMATION_REQUIRED":
        return "final confirmation required"
    if not checks["intent_ready"]:
        return "create intent"
    if not checks["rehearsal_ready"]:
        return "rehearse"
    if not checks["arming_allowed"]:
        return "arm system"
    return "keep blocked"


def _network_allowed(*, checks: dict[str, bool], dry_run: bool) -> bool:
    return dry_run is False and checks.get("network_gate_open") is True


def _protective_ready(protective: dict[str, Any]) -> bool:
    return (
        protective.get("protective_orders_required") is True
        and protective.get("protective_orders_enabled") is True
        and protective.get("protective_order_mode") == LIVE_PROTECTIVE_ENABLED
        and protective.get("protective_orders_supported") is True
        and protective.get("protective_stop_supported") is True
        and protective.get("protective_take_profit_supported") is True
    )


def _entry_payload_preview(rehearsal: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = (rehearsal or {}).get("entry_order_preview")
    if not isinstance(payload, dict):
        return None
    sanitized = dict(payload)
    sanitized["preview_only"] = True
    sanitized["reduce_only"] = False
    for key in ("api_key", "apiKey", "secret", "signature"):
        sanitized.pop(key, None)
    return sanitized


def _protective_payloads_preview(rehearsal: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = (rehearsal or {}).get("protective_orders_preview")
    if not isinstance(payload, dict):
        return None
    sanitized = json.loads(json.dumps(payload, default=str))
    sanitized["preview_only"] = True
    for leg_name in ("stop_loss", "take_profit"):
        leg = sanitized.get(leg_name)
        if isinstance(leg, dict):
            leg["preview_only"] = True
            leg["reduce_only"] = True
            for key in ("api_key", "apiKey", "secret", "signature"):
                leg.pop(key, None)
    return sanitized


def _entry_payload_valid(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("symbol") and payload.get("side") and payload.get("position_side") and payload.get("preview_only") is True)


def _protective_payloads_valid(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("status") != "READY":
        return False
    stop_loss = payload.get("stop_loss")
    take_profit = payload.get("take_profit")
    return (
        isinstance(stop_loss, dict)
        and isinstance(take_profit, dict)
        and stop_loss.get("reduce_only") is True
        and take_profit.get("reduce_only") is True
        and stop_loss.get("preview_only") is True
        and take_profit.get("preview_only") is True
    )


def _idempotency_clear(*, signal_id: str | None, intent_id: str | None, rehearsal_id: str | None, log_dir: Path) -> bool:
    if not (signal_id or intent_id or rehearsal_id):
        return False
    for record in _load_raw_gate_records(log_dir=log_dir, signal_id=signal_id):
        if intent_id and record.get("execution_intent_id") not in {None, intent_id}:
            continue
        if rehearsal_id and record.get("executor_rehearsal_id") not in {None, rehearsal_id}:
            continue
        if record.get("order_placed") is True or record.get("real_order_placed") is True or record.get("execution_attempted") is True:
            return False
        if record.get("status") in {"EXECUTION_GATE_READY"} and record.get("final_confirmation") is True and record.get("dry_run") is False:
            return False
    return True


def _load_raw_gate_records(*, log_dir: Path, signal_id: str | None) -> list[dict[str, Any]]:
    path = first_live_execution_gates_path(log_dir)
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
            records.append(record)
    return list(reversed(records))


def _intent_unexpired(record: dict[str, Any], *, now: datetime) -> bool:
    expires_at = _parse_datetime(record.get("expires_at"))
    return expires_at is not None and expires_at > now and record.get("status") == "INTENT_READY"


def _gate_record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "gate_evaluation_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "first_live_execution_gate",
        "status": payload.get("status"),
        "created_at": payload.get("created_at"),
        "signal_id": payload.get("signal_id"),
        "execution_intent_id": payload.get("execution_intent_id"),
        "executor_rehearsal_id": payload.get("executor_rehearsal_id"),
        "arming_status": payload.get("arming_status"),
        "final_confirmation": bool(payload.get("final_confirmation")),
        "dry_run": bool(payload.get("dry_run")),
        "network_allowed": False,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "blockers": list(payload.get("blockers") or []),
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize_gate_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "gate_evaluation_id",
        "phase",
        "event_type",
        "status",
        "created_at",
        "signal_id",
        "execution_intent_id",
        "executor_rehearsal_id",
        "arming_status",
        "final_confirmation",
        "dry_run",
        "network_allowed",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "blockers",
        "secrets_shown",
    }
    sanitized = {key: record.get(key) for key in allowed if key in record}
    sanitized["network_allowed"] = False
    sanitized["order_placed"] = False
    sanitized["real_order_placed"] = False
    sanitized["execution_attempted"] = False
    sanitized["secrets_shown"] = False
    return sanitized


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
