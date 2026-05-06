"""R56 protected executor transport wiring for Hammer Radar.

This module selects and records protected executor transport attempts after the
R55 first-live gate. It supports local MOCK and DRY_RUN lanes and keeps LIVE
transport guarded. It never exposes secrets, mutates env files, or calls
Binance directly.
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
from src.app.hammer_radar.operator.first_live_execution_gate import build_first_live_execution_gate
from src.app.hammer_radar.operator.live_executor_rehearsal import load_live_executor_rehearsals

PHASE = "R56"
SYSTEM = "money_printing_machine_hammer_radar"
TRANSPORT_CHECK = "TRANSPORT_CHECK"
TRANSPORT_ATTEMPT = "TRANSPORT_ATTEMPT"
ATTEMPTS_FILENAME = "live_executor_transport_attempts.ndjson"

TRANSPORT_MODES = {"MOCK", "DRY_RUN", "LIVE"}
DEFAULT_TRANSPORT_MODE = "DRY_RUN"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
SECRETS_SHOWN = False


def build_live_executor_transport_status(
    *,
    executor_rehearsal_id: str | None = None,
    execution_intent_id: str | None = None,
    signal_id: str | None = None,
    transport_mode: str | None = None,
    final_confirmation: bool = False,
    dry_run: bool = True,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_transport(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        transport_mode=transport_mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=log_dir,
        env=env,
        persist=False,
        attempt=False,
    )


def check_live_executor_transport(
    *,
    executor_rehearsal_id: str | None = None,
    execution_intent_id: str | None = None,
    signal_id: str | None = None,
    transport_mode: str | None = None,
    final_confirmation: bool = False,
    dry_run: bool = True,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_transport(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        transport_mode=transport_mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=log_dir,
        env=env,
        persist=False,
        attempt=False,
    )


def attempt_live_executor_transport(
    *,
    executor_rehearsal_id: str | None = None,
    execution_intent_id: str | None = None,
    signal_id: str | None = None,
    transport_mode: str | None = None,
    final_confirmation: bool = False,
    dry_run: bool = True,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_transport(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        transport_mode=transport_mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=log_dir,
        env=env,
        persist=True,
        attempt=True,
    )


def list_live_executor_transport_attempts(
    *,
    limit: int = 20,
    signal_id: str | None = None,
    transport_mode: str | None = None,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_live_executor_transport_attempts(
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


def load_live_executor_transport_attempts(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    transport_mode: str | None = None,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = live_executor_transport_attempts_path(get_log_dir(log_dir, use_env=True))
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
            if transport_mode is not None and record.get("transport_mode") != transport_mode:
                continue
            if status is not None and record.get("status") != status:
                continue
            records.append(_sanitize_attempt_record(record))
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def live_executor_transport_attempts_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / ATTEMPTS_FILENAME


def append_live_executor_transport_attempt(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = live_executor_transport_attempts_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_live_executor_transport_operator_message(payload: dict[str, Any]) -> str:
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:5]) if blockers else "none"
    return "\n".join(
        [
            f"R56 protected executor transport: {payload.get('status')}",
            f"transport_mode: {payload.get('transport_mode')} network_allowed={payload.get('network_allowed')}",
            f"order_placed={payload.get('order_placed')} real_order_placed={payload.get('real_order_placed')} simulated_order_placed={payload.get('simulated_order_placed')}",
            f"signal/intent/rehearsal: {payload.get('signal_id') or 'none'} / {payload.get('execution_intent_id') or 'none'} / {payload.get('executor_rehearsal_id') or 'none'}",
            f"R55 gate: {payload.get('first_live_gate_status')} attempt_id: {payload.get('transport_attempt_id') or 'none'}",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )


def format_live_executor_transport_attempts_operator_message(payload: dict[str, Any]) -> str:
    attempts = payload.get("attempts") or []
    if not attempts:
        detail = "none"
    else:
        detail = "; ".join(
            f"{item.get('transport_mode')} {item.get('status')} {item.get('executor_rehearsal_id') or 'none'}"
            for item in attempts[:5]
        )
    return "\n".join(
        [
            "R56 protected executor transport attempts",
            "Transport attempt list. No real order placed by default.",
            f"count: {payload.get('count', 0)}",
            f"attempts: {detail}",
        ]
    )


def _evaluate_transport(
    *,
    executor_rehearsal_id: str | None,
    execution_intent_id: str | None,
    signal_id: str | None,
    transport_mode: str | None,
    final_confirmation: bool,
    dry_run: bool,
    log_dir: str | Path | None,
    env: Mapping[str, str] | None,
    persist: bool,
    attempt: bool,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC)
    mode = _normalize_transport_mode(transport_mode)
    connector = build_connector_status(env=source, log_dir=resolved_log_dir)
    protective = build_protective_status(env=source, log_dir=resolved_log_dir)
    rehearsal = _resolve_rehearsal(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        log_dir=resolved_log_dir,
    )
    resolved_signal_id = (rehearsal or {}).get("signal_id") or signal_id
    resolved_intent_id = (rehearsal or {}).get("execution_intent_id") or execution_intent_id
    resolved_rehearsal_id = (rehearsal or {}).get("executor_rehearsal_id") or executor_rehearsal_id
    gate = build_first_live_execution_gate(
        executor_rehearsal_id=resolved_rehearsal_id,
        execution_intent_id=resolved_intent_id,
        signal_id=resolved_signal_id,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=resolved_log_dir,
        env=source,
    )
    entry_result = _entry_order_result(rehearsal=rehearsal, mode=mode, attempt=attempt)
    protective_results = _protective_order_results(rehearsal=rehearsal, mode=mode, attempt=attempt)
    checks = _checks(
        requested_present=bool(executor_rehearsal_id or execution_intent_id or signal_id),
        mode=mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        connector=connector,
        protective=protective,
        rehearsal=rehearsal,
        gate=gate,
        entry_result=entry_result,
        protective_results=protective_results,
        signal_id=resolved_signal_id,
        rehearsal_id=resolved_rehearsal_id,
        log_dir=resolved_log_dir,
    )
    blockers = _blockers(mode=mode, final_confirmation=final_confirmation, dry_run=dry_run, gate=gate, checks=checks)
    existing = _existing_successful_attempt(
        rehearsal_id=resolved_rehearsal_id,
        mode=mode,
        log_dir=resolved_log_dir,
    )
    status = _status(mode=mode, attempt=attempt, checks=checks, blockers=blockers)
    if existing is not None and mode in {"MOCK", "DRY_RUN"} and status in {"MOCK_ATTEMPT_RECORDED", "DRY_RUN_ATTEMPT_RECORDED"}:
        return _payload_from_existing(
            existing=existing,
            connector=connector,
            protective=protective,
            gate=gate,
            checks=checks,
            blockers=blockers,
            execution_mode=TRANSPORT_ATTEMPT if attempt else TRANSPORT_CHECK,
        )
    simulated_order_placed = bool(attempt and mode == "MOCK" and status == "MOCK_ATTEMPT_RECORDED")
    dry_run_order_recorded = bool(attempt and mode == "DRY_RUN" and status == "DRY_RUN_ATTEMPT_RECORDED")
    execution_attempted = bool(attempt and status in {"MOCK_ATTEMPT_RECORDED", "DRY_RUN_ATTEMPT_RECORDED", "LIVE_READY"})
    network_allowed = bool(mode == "LIVE" and checks["network_gate_open"])
    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": TRANSPORT_ATTEMPT if attempt else TRANSPORT_CHECK,
        "transport_mode": mode,
        "transport_attempt_id": None,
        "signal_id": resolved_signal_id,
        "execution_intent_id": resolved_intent_id,
        "executor_rehearsal_id": resolved_rehearsal_id,
        "gate_evaluation_id": gate.get("gate_evaluation_id"),
        "final_confirmation": bool(final_confirmation),
        "dry_run": bool(dry_run),
        "network_allowed": network_allowed,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "simulated_order_placed": simulated_order_placed,
        "dry_run_order_recorded": dry_run_order_recorded,
        "execution_attempted": execution_attempted,
        "live_execution_enabled": bool(connector.get("live_execution_enabled")),
        "binance_live_enabled": bool(connector.get("binance_live_enabled")),
        "allow_live_orders": bool(connector.get("allow_live_orders")),
        "global_kill_switch": bool(connector.get("global_kill_switch")),
        "connector_mode": connector.get("connector_mode") or "DRY_RUN_ONLY",
        "live_begins_status": gate.get("live_begins_status") or "UNKNOWN",
        "preview_status": gate.get("preview_status") or "UNKNOWN",
        "intent_status": gate.get("intent_status") or "UNKNOWN",
        "rehearsal_status": gate.get("rehearsal_status") or "UNKNOWN",
        "arming_status": gate.get("arming_status") or "UNKNOWN",
        "first_live_gate_status": gate.get("status") or "UNKNOWN",
        "entry_order_result": entry_result if status not in {"REJECTED", "BLOCKED", "LIVE_BLOCKED"} else None,
        "protective_order_results": protective_results if status not in {"REJECTED", "BLOCKED", "LIVE_BLOCKED"} else [],
        "checks": checks,
        "blockers": blockers,
        "operator_action": _operator_action(status=status, mode=mode, checks=checks),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "live_executor_transport_attempts_path": str(live_executor_transport_attempts_path(resolved_log_dir)),
    }
    if persist and status in {"MOCK_ATTEMPT_RECORDED", "DRY_RUN_ATTEMPT_RECORDED", "LIVE_READY", "LIVE_BLOCKED", "BLOCKED", "REJECTED"}:
        record = _attempt_record(payload, created_at=created_at.isoformat())
        append_live_executor_transport_attempt(record, log_dir=resolved_log_dir)
        payload["transport_attempt_id"] = record["transport_attempt_id"]
    return payload


def _normalize_transport_mode(value: str | None) -> str:
    mode = str(value or DEFAULT_TRANSPORT_MODE).strip().upper().replace("-", "_")
    if mode in {"MOCK_EXECUTOR", "MOCK"}:
        return "MOCK"
    if mode in {"DRY_RUN_EXECUTOR", "DRY_RUN", "DRYRUN"}:
        return "DRY_RUN"
    if mode in {"LIVE_EXECUTOR", "LIVE"}:
        return "LIVE"
    return mode


def _resolve_rehearsal(
    *,
    executor_rehearsal_id: str | None,
    execution_intent_id: str | None,
    signal_id: str | None,
    log_dir: Path,
) -> dict[str, Any] | None:
    if executor_rehearsal_id:
        records = load_live_executor_rehearsals(limit=0, rehearsal_id=executor_rehearsal_id, log_dir=log_dir)
        return records[0] if records else None
    if execution_intent_id:
        records = load_live_executor_rehearsals(limit=0, execution_intent_id=execution_intent_id, log_dir=log_dir)
        return _latest_ready_rehearsal(records) or (records[0] if records else None)
    if signal_id:
        records = load_live_executor_rehearsals(limit=0, signal_id=signal_id, log_dir=log_dir)
        return _latest_ready_rehearsal(records) or (records[0] if records else None)
    return None


def _latest_ready_rehearsal(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for record in records:
        if record.get("status") == "REHEARSAL_READY":
            return record
    return None


def _checks(
    *,
    requested_present: bool,
    mode: str,
    final_confirmation: bool,
    dry_run: bool,
    connector: dict[str, Any],
    protective: dict[str, Any],
    rehearsal: dict[str, Any] | None,
    gate: dict[str, Any],
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
    )
    protective_ready = _protective_ready(protective)
    return {
        "id_or_signal_present": requested_present,
        "rehearsal_found": rehearsal is not None,
        "first_live_gate_ready": gate.get("status") == "EXECUTION_GATE_READY",
        "transport_mode_valid": mode in TRANSPORT_MODES,
        "mock_allowed": mode == "MOCK" and rehearsal is not None,
        "dry_run_allowed": mode == "DRY_RUN" and rehearsal is not None,
        "live_transport_requested": mode == "LIVE",
        "final_confirmation_present": final_confirmation is True,
        "live_env_allows_network": live_env_allows,
        "connector_mode_allows_live": connector.get("connector_mode") == LIVE_ORDER_ENABLED,
        "global_kill_switch_off": connector.get("global_kill_switch") is False,
        "protective_orders_ready": protective_ready,
        "entry_payload_present": isinstance(entry_result, dict),
        "protective_payloads_present": len(protective_results) >= 2,
        "idempotency_clear": _idempotency_clear(mode=mode, signal_id=signal_id, rehearsal_id=rehearsal_id, log_dir=log_dir),
        "network_gate_open": mode == "LIVE" and dry_run is False and final_confirmation is True and gate.get("status") == "EXECUTION_GATE_READY" and live_env_allows and connector.get("connector_mode") == LIVE_ORDER_ENABLED and protective_ready,
    }


def _blockers(*, mode: str, final_confirmation: bool, dry_run: bool, gate: dict[str, Any], checks: dict[str, bool]) -> list[str]:
    blockers: list[str] = []
    if not checks["id_or_signal_present"]:
        blockers.append("executor_rehearsal_id, execution_intent_id, or signal_id is required")
    if not checks["transport_mode_valid"]:
        blockers.append(f"transport_mode is invalid: {mode}")
    if not checks["rehearsal_found"]:
        blockers.append("executor rehearsal not found")
    if not checks["first_live_gate_ready"]:
        blockers.append(f"first live execution gate is {gate.get('status', 'UNKNOWN')}")
    if mode == "LIVE":
        if final_confirmation is not True:
            blockers.append("final confirmation is required for live transport")
        if dry_run is True:
            blockers.append("dry_run must be false for live transport")
        if not checks["live_env_allows_network"]:
            blockers.append("live env flags do not allow network")
        if not checks["connector_mode_allows_live"]:
            blockers.append("connector mode does not allow live")
        if not checks["global_kill_switch_off"]:
            blockers.append("global kill switch is active")
        if not checks["protective_orders_ready"]:
            blockers.append("protective orders are required but not ready")
        if not checks["network_gate_open"]:
            blockers.append("network gate is closed")
        blockers.append("live executor implementation is guarded; no live order submitted by R56")
    if mode in {"MOCK", "DRY_RUN"} and not checks["rehearsal_found"]:
        blockers.append(f"{mode.lower()} transport requires a rehearsal")
    if not checks["entry_payload_present"]:
        blockers.append("entry order result payload is missing")
    if not checks["protective_payloads_present"]:
        blockers.append("protective order results are missing")
    if not checks["idempotency_clear"]:
        blockers.append("idempotency is not clear for transport")
    return list(dict.fromkeys(blocker for blocker in blockers if blocker))


def _status(*, mode: str, attempt: bool, checks: dict[str, bool], blockers: list[str]) -> str:
    if not checks["id_or_signal_present"]:
        return "REJECTED"
    if mode == "LIVE":
        if checks["network_gate_open"] and len(blockers) == 1 and blockers[0].startswith("live executor implementation"):
            return "LIVE_READY"
        return "LIVE_BLOCKED"
    if blockers:
        return "BLOCKED"
    if not attempt:
        return "TRANSPORT_READY"
    if mode == "MOCK":
        return "MOCK_ATTEMPT_RECORDED"
    if mode == "DRY_RUN":
        return "DRY_RUN_ATTEMPT_RECORDED"
    return "BLOCKED"


def _operator_action(*, status: str, mode: str, checks: dict[str, bool]) -> str:
    if status == "MOCK_ATTEMPT_RECORDED" or (status == "TRANSPORT_READY" and mode == "MOCK"):
        return "run mock"
    if status == "DRY_RUN_ATTEMPT_RECORDED" or (status == "TRANSPORT_READY" and mode == "DRY_RUN"):
        return "run dry run"
    if mode == "LIVE" and not checks["final_confirmation_present"]:
        return "final live confirmation required"
    if mode == "LIVE" and not checks["live_env_allows_network"]:
        return "arm live env"
    return "keep blocked"


def _protective_ready(protective: dict[str, Any]) -> bool:
    return (
        protective.get("protective_orders_required") is True
        and protective.get("protective_orders_enabled") is True
        and protective.get("protective_order_mode") == LIVE_PROTECTIVE_ENABLED
        and protective.get("protective_orders_supported") is True
        and protective.get("protective_stop_supported") is True
        and protective.get("protective_take_profit_supported") is True
    )


def _entry_order_result(*, rehearsal: dict[str, Any] | None, mode: str, attempt: bool) -> dict[str, Any] | None:
    preview = (rehearsal or {}).get("entry_order_preview")
    if not isinstance(preview, dict):
        return None
    result = _sanitize_nested(preview)
    result.update(
        {
            "transport_mode": mode,
            "status": "MOCK_VALIDATED" if mode == "MOCK" else "DRY_RUN_RECORDED" if mode == "DRY_RUN" else "LIVE_GUARDED",
            "order_id": f"mock-{uuid4().hex[:12]}" if attempt and mode == "MOCK" else None,
            "preview_only": mode != "DRY_RUN",
            "dry_run_only": mode == "DRY_RUN",
            "real_order_placed": False,
            "secrets_shown": False,
        }
    )
    return result


def _protective_order_results(*, rehearsal: dict[str, Any] | None, mode: str, attempt: bool) -> list[dict[str, Any]]:
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
                "order_id": f"mock-{leg_name}-{uuid4().hex[:12]}" if attempt and mode == "MOCK" else None,
                "preview_only": mode != "DRY_RUN",
                "dry_run_only": mode == "DRY_RUN",
                "reduce_only": True,
                "real_order_placed": False,
                "secrets_shown": False,
            }
        )
        results.append(result)
    return results


def _idempotency_clear(*, mode: str, signal_id: str | None, rehearsal_id: str | None, log_dir: Path) -> bool:
    if not rehearsal_id:
        return False
    for record in _load_raw_attempts(log_dir=log_dir, signal_id=signal_id):
        if record.get("executor_rehearsal_id") != rehearsal_id:
            continue
        if record.get("transport_mode") == mode and record.get("status") in {"MOCK_ATTEMPT_RECORDED", "DRY_RUN_ATTEMPT_RECORDED"}:
            return mode in {"MOCK", "DRY_RUN"}
        if mode == "LIVE" and (
            record.get("order_placed") is True
            or record.get("real_order_placed") is True
            or record.get("execution_attempted") is True
            or record.get("status") in {"LIVE_READY"}
        ):
            return False
    return True


def _existing_successful_attempt(*, rehearsal_id: str | None, mode: str, log_dir: Path) -> dict[str, Any] | None:
    if not rehearsal_id or mode not in {"MOCK", "DRY_RUN"}:
        return None
    expected_status = "MOCK_ATTEMPT_RECORDED" if mode == "MOCK" else "DRY_RUN_ATTEMPT_RECORDED"
    for record in _load_raw_attempts(log_dir=log_dir, signal_id=None):
        if record.get("executor_rehearsal_id") == rehearsal_id and record.get("transport_mode") == mode and record.get("status") == expected_status:
            return record
    return None


def _payload_from_existing(
    *,
    existing: dict[str, Any],
    connector: dict[str, Any],
    protective: dict[str, Any],
    gate: dict[str, Any],
    checks: dict[str, bool],
    blockers: list[str],
    execution_mode: str,
) -> dict[str, Any]:
    return {
        "status": existing.get("status"),
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": execution_mode,
        "transport_mode": existing.get("transport_mode"),
        "transport_attempt_id": existing.get("transport_attempt_id"),
        "signal_id": existing.get("signal_id"),
        "execution_intent_id": existing.get("execution_intent_id"),
        "executor_rehearsal_id": existing.get("executor_rehearsal_id"),
        "gate_evaluation_id": existing.get("gate_evaluation_id"),
        "final_confirmation": bool(existing.get("final_confirmation")),
        "dry_run": bool(existing.get("dry_run")),
        "network_allowed": False,
        "order_placed": False,
        "real_order_placed": False,
        "simulated_order_placed": bool(existing.get("simulated_order_placed")),
        "dry_run_order_recorded": bool(existing.get("dry_run_order_recorded")),
        "execution_attempted": bool(existing.get("execution_attempted")),
        "live_execution_enabled": bool(connector.get("live_execution_enabled")),
        "binance_live_enabled": bool(connector.get("binance_live_enabled")),
        "allow_live_orders": bool(connector.get("allow_live_orders")),
        "global_kill_switch": bool(connector.get("global_kill_switch")),
        "connector_mode": connector.get("connector_mode") or "DRY_RUN_ONLY",
        "live_begins_status": gate.get("live_begins_status") or "UNKNOWN",
        "preview_status": gate.get("preview_status") or "UNKNOWN",
        "intent_status": gate.get("intent_status") or "UNKNOWN",
        "rehearsal_status": gate.get("rehearsal_status") or "UNKNOWN",
        "arming_status": gate.get("arming_status") or "UNKNOWN",
        "first_live_gate_status": gate.get("status") or "UNKNOWN",
        "entry_order_result": existing.get("entry_order_result"),
        "protective_order_results": existing.get("protective_order_results") or [],
        "checks": checks,
        "blockers": blockers,
        "operator_action": "run mock" if existing.get("transport_mode") == "MOCK" else "run dry run",
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": False,
    }


def _attempt_record(payload: dict[str, Any], *, created_at: str) -> dict[str, Any]:
    return {
        "transport_attempt_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "live_executor_transport_attempt",
        "created_at": created_at,
        "status": payload.get("status"),
        "transport_mode": payload.get("transport_mode"),
        "signal_id": payload.get("signal_id"),
        "execution_intent_id": payload.get("execution_intent_id"),
        "executor_rehearsal_id": payload.get("executor_rehearsal_id"),
        "gate_evaluation_id": payload.get("gate_evaluation_id"),
        "final_confirmation": bool(payload.get("final_confirmation")),
        "dry_run": bool(payload.get("dry_run")),
        "network_allowed": False,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "simulated_order_placed": bool(payload.get("simulated_order_placed")),
        "dry_run_order_recorded": bool(payload.get("dry_run_order_recorded")),
        "execution_attempted": bool(payload.get("execution_attempted")),
        "entry_order_result": payload.get("entry_order_result"),
        "protective_order_results": payload.get("protective_order_results") or [],
        "blockers": list(payload.get("blockers") or []),
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize_attempt_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "transport_attempt_id",
        "phase",
        "event_type",
        "created_at",
        "status",
        "transport_mode",
        "signal_id",
        "execution_intent_id",
        "executor_rehearsal_id",
        "gate_evaluation_id",
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
    sanitized["network_allowed"] = False
    sanitized["order_placed"] = False
    sanitized["real_order_placed"] = False
    sanitized["secrets_shown"] = False
    return sanitized


def _load_raw_attempts(*, log_dir: Path, signal_id: str | None) -> list[dict[str, Any]]:
    path = live_executor_transport_attempts_path(log_dir)
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


def _sanitize_nested(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(payload, default=str))
    for key in ("api_key", "apiKey", "secret", "signature", "api_secret"):
        sanitized.pop(key, None)
    return sanitized
