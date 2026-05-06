"""R53 protected executor rehearsal for Hammer Radar.

This module consumes R52 INTENT_ONLY records and builds a deterministic
REHEARSAL_ONLY executor sequence. It never places orders, enables live trading,
signs payloads, or calls Binance.
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
from src.app.hammer_radar.operator.live_begins import build_live_begins_status
from src.app.hammer_radar.operator.live_execution_intent import (
    compute_preview_hash,
    load_live_execution_intents,
)
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview

PHASE = "R53"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "REHEARSAL_ONLY"
LIVE_EXECUTOR_REHEARSALS_FILENAME = "live_executor_rehearsals.ndjson"

NETWORK_ALLOWED = False
ORDER_PLACED = False
REAL_ORDER_PLACED = False
WOULD_PLACE_ORDER = False
EXECUTION_ATTEMPTED = False
SECRETS_SHOWN = False


def create_live_executor_rehearsal(
    *,
    execution_intent_id: str | None = None,
    signal_id: str | None = None,
    dry_run: bool = True,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC)
    intent = _resolve_intent(execution_intent_id=execution_intent_id, signal_id=signal_id, log_dir=resolved_log_dir, now=created_at)
    preview = build_live_execution_preview(log_dir=resolved_log_dir, env=source)
    live_begins = build_live_begins_status(log_dir=resolved_log_dir, env=source)
    current_preview_hash = compute_preview_hash(preview) if preview.get("status") != "UNKNOWN" else None
    entry_order_preview = _entry_order_preview(preview)
    protective_orders_preview = preview.get("protective_orders_preview") if isinstance(preview.get("protective_orders_preview"), dict) else None
    intent_status = _intent_status(intent, now=created_at)
    checks = _checks(
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        intent=intent,
        intent_status=intent_status,
        live_begins=live_begins,
        preview=preview,
        current_preview_hash=current_preview_hash,
        protective_orders_preview=protective_orders_preview,
        log_dir=resolved_log_dir,
    )
    blockers = _blockers(
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        dry_run=dry_run,
        intent=intent,
        intent_status=intent_status,
        live_begins=live_begins,
        preview=preview,
        checks=checks,
    )
    status = _status(checks=checks, blockers=blockers)
    sequence = _sequence(checks=checks, blockers=blockers)
    intent_id = (intent or {}).get("execution_intent_id")
    resolved_signal_id = (intent or {}).get("signal_id") or signal_id
    preview_hash = (intent or {}).get("preview_hash")
    existing = _active_matching_rehearsal(
        execution_intent_id=intent_id,
        preview_hash=preview_hash,
        log_dir=resolved_log_dir,
    )
    rehearsal_id = existing.get("executor_rehearsal_id") if existing and status == "REHEARSAL_READY" else None

    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "executor_rehearsal_id": rehearsal_id,
        "execution_intent_id": intent_id,
        "signal_id": resolved_signal_id,
        "preview_hash": preview_hash,
        "created_at": (existing or {}).get("created_at") or created_at.isoformat(),
        "expires_at": (intent or {}).get("expires_at") if status == "REHEARSAL_READY" else None,
        "intent_status": intent_status,
        "live_begins_status": live_begins.get("status") or "UNKNOWN",
        "preview_status": preview.get("status") or "UNKNOWN",
        "network_allowed": NETWORK_ALLOWED,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "would_place_order": WOULD_PLACE_ORDER,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "sequence": sequence,
        "entry_order_preview": entry_order_preview,
        "protective_orders_preview": protective_orders_preview,
        "checks": checks,
        "blockers": blockers,
        "operator_action": _operator_action(status=status, intent_status=intent_status),
        "secrets_shown": SECRETS_SHOWN,
        "live_executor_rehearsals_path": str(live_executor_rehearsals_path(resolved_log_dir)),
    }
    if status == "REHEARSAL_READY" and rehearsal_id is None:
        payload["executor_rehearsal_id"] = uuid4().hex
        append_live_executor_rehearsal(_rehearsal_record(payload), log_dir=resolved_log_dir)
    return payload


def list_live_executor_rehearsals(
    *,
    limit: int = 20,
    signal_id: str | None = None,
    execution_intent_id: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_live_executor_rehearsals(
        limit=limit,
        signal_id=signal_id,
        execution_intent_id=execution_intent_id,
        log_dir=get_log_dir(log_dir, use_env=True),
    )
    return {
        "result_status": "ACCEPTED",
        "phase": PHASE,
        "count": len(records),
        "rehearsals": records,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "secrets_shown": SECRETS_SHOWN,
    }


def load_live_executor_rehearsals(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    execution_intent_id: str | None = None,
    rehearsal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = live_executor_rehearsals_path(get_log_dir(log_dir, use_env=True))
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
            if execution_intent_id is not None and record.get("execution_intent_id") != execution_intent_id:
                continue
            if rehearsal_id is not None and record.get("executor_rehearsal_id") != rehearsal_id:
                continue
            records.append(_sanitize_rehearsal_record(record))
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def live_executor_rehearsals_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LIVE_EXECUTOR_REHEARSALS_FILENAME


def append_live_executor_rehearsal(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = live_executor_rehearsals_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_live_executor_rehearsal_operator_message(payload: dict[str, Any]) -> str:
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:5]) if blockers else "none"
    return "\n".join(
        [
            f"R53 protected executor rehearsal: {payload.get('status')}",
            "REHEARSAL_ONLY. No order placed. real_order_placed=false.",
            f"intent_id: {payload.get('execution_intent_id') or 'none'}",
            f"signal_id: {payload.get('signal_id') or 'none'}",
            f"preview_hash: {payload.get('preview_hash') or 'none'}",
            f"rehearsal_id: {payload.get('executor_rehearsal_id') or 'none'}",
            f"sequence_status: {payload.get('status')}",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )


def format_live_executor_rehearsals_operator_message(payload: dict[str, Any]) -> str:
    rehearsals = payload.get("rehearsals") or []
    if not rehearsals:
        detail = "none"
    else:
        detail = "; ".join(
            f"{item.get('execution_intent_id')} {item.get('status')} {item.get('executor_rehearsal_id')}"
            for item in rehearsals[:5]
        )
    return "\n".join(
        [
            "R53 protected executor rehearsals",
            "REHEARSAL_ONLY list. No order placed.",
            f"count: {payload.get('count', 0)}",
            f"rehearsals: {detail}",
        ]
    )


def _resolve_intent(*, execution_intent_id: str | None, signal_id: str | None, log_dir: Path, now: datetime) -> dict[str, Any] | None:
    if execution_intent_id:
        records = load_live_execution_intents(limit=0, intent_id=execution_intent_id, log_dir=log_dir)
        return records[0] if records else None
    if signal_id:
        for record in load_live_execution_intents(limit=0, signal_id=signal_id, log_dir=log_dir):
            if _intent_unexpired(record, now=now):
                return record
        records = load_live_execution_intents(limit=1, signal_id=signal_id, log_dir=log_dir)
        return records[0] if records else None
    return None


def _intent_status(intent: dict[str, Any] | None, *, now: datetime) -> str:
    if intent is None:
        return "MISSING"
    if intent.get("status") != "INTENT_READY" or intent.get("execution_mode") != "INTENT_ONLY":
        return str(intent.get("status") or "UNKNOWN")
    if intent.get("order_placed") is True or intent.get("real_order_placed") is True or intent.get("execution_attempted") is True:
        return "UNKNOWN"
    if intent.get("secrets_shown") is True or not intent.get("preview_hash"):
        return "UNKNOWN"
    if not _intent_unexpired(intent, now=now):
        return "EXPIRED"
    return "INTENT_READY"


def _checks(
    *,
    execution_intent_id: str | None,
    signal_id: str | None,
    intent: dict[str, Any] | None,
    intent_status: str,
    live_begins: dict[str, Any],
    preview: dict[str, Any],
    current_preview_hash: str | None,
    protective_orders_preview: dict[str, Any] | None,
    log_dir: Path,
) -> dict[str, bool]:
    intent_hash = (intent or {}).get("preview_hash")
    return {
        "intent_id_or_signal_present": bool(execution_intent_id or signal_id),
        "intent_found": intent is not None,
        "intent_unexpired": intent_status != "EXPIRED" and intent is not None,
        "intent_ready": intent_status == "INTENT_READY",
        "preview_hash_matches": bool(intent_hash and current_preview_hash and intent_hash == current_preview_hash),
        "live_begins_allows_rehearsal": live_begins.get("status") in {"READY_FOR_OPERATOR_APPROVAL", "ELIGIBLE_TINY_LIVE"},
        "preview_allows_rehearsal": preview.get("status") == "PREVIEW_READY",
        "protective_orders_present": _protective_orders_present(protective_orders_preview),
        "network_disabled": NETWORK_ALLOWED is False,
        "idempotency_clear": _idempotency_clear(intent=intent, log_dir=log_dir),
    }


def _blockers(
    *,
    execution_intent_id: str | None,
    signal_id: str | None,
    dry_run: bool,
    intent: dict[str, Any] | None,
    intent_status: str,
    live_begins: dict[str, Any],
    preview: dict[str, Any],
    checks: dict[str, bool],
) -> list[str]:
    blockers: list[str] = []
    if not checks["intent_id_or_signal_present"]:
        blockers.append("execution_intent_id or signal_id is required")
    if not checks["intent_found"]:
        blockers.append("execution intent not found")
    if intent_status == "EXPIRED":
        blockers.append("execution intent is expired")
    elif intent is not None and intent_status != "INTENT_READY":
        blockers.append(f"execution intent status is {intent_status}")
    if dry_run is not True:
        blockers.append("dry_run must remain true for R53 rehearsal-only")
    if not checks["preview_hash_matches"]:
        blockers.append("current preview hash differs from approved intent preview hash; re-approval required")
    if not checks["live_begins_allows_rehearsal"]:
        blockers.append(f"live begins is {live_begins.get('status', 'UNKNOWN')}")
    if not checks["preview_allows_rehearsal"]:
        blockers.append(f"execution preview is {preview.get('status', 'UNKNOWN')}")
    if not checks["protective_orders_present"]:
        blockers.append("protective orders are required but missing or blocked")
    if not checks["network_disabled"]:
        blockers.append("network must remain disabled")
    if not checks["idempotency_clear"]:
        blockers.append("idempotency is not clear for rehearsal")
    return list(dict.fromkeys(blocker for blocker in blockers if blocker))


def _status(*, checks: dict[str, bool], blockers: list[str]) -> str:
    if not checks["intent_id_or_signal_present"]:
        return "REJECTED"
    if not blockers:
        return "REHEARSAL_READY"
    return "BLOCKED"


def _sequence(*, checks: dict[str, bool], blockers: list[str]) -> list[dict[str, Any]]:
    definitions = [
        ("validate_intent", checks["intent_found"] and checks["intent_unexpired"] and checks["intent_ready"], "intent exists, is unexpired, and is INTENT_READY"),
        ("validate_preview_hash", checks["preview_hash_matches"], "current preview hash matches approved intent preview hash"),
        ("validate_live_begins_state", checks["live_begins_allows_rehearsal"], "R50 live-begins allows rehearsal"),
        ("validate_protective_orders", checks["protective_orders_present"], "protective stop-loss and take-profit previews are present"),
        ("validate_idempotency", checks["idempotency_clear"], "no prior ready rehearsal conflicts with this intent/hash"),
        ("prepare_entry_order", not blockers, "entry order preview prepared locally"),
        ("prepare_stop_loss_order", checks["protective_orders_present"] and not blockers, "stop-loss preview prepared locally"),
        ("prepare_take_profit_order", checks["protective_orders_present"] and not blockers, "take-profit preview prepared locally"),
        ("prepare_audit_record", not blockers, "sanitized rehearsal audit record prepared"),
        ("stop_before_network", True, "stop_before_network: no exchange call made; no order placed"),
    ]
    sequence = []
    for index, (name, ready, summary) in enumerate(definitions, start=1):
        if name.startswith("prepare_") and blockers:
            status = "SKIPPED"
        else:
            status = "READY" if ready else "BLOCKED"
        sequence.append({"step": index, "name": name, "status": status, "network": False, "summary": summary})
    return sequence


def _entry_order_preview(preview: dict[str, Any]) -> dict[str, Any] | None:
    if not preview.get("symbol"):
        return None
    return {
        "type": "LIMIT_PREVIEW",
        "symbol": preview.get("symbol"),
        "side": preview.get("order_side"),
        "position_side": preview.get("position_side"),
        "margin_mode": preview.get("margin_mode") or "ISOLATED",
        "quantity": preview.get("quantity"),
        "notional_usdt": preview.get("notional_usdt"),
        "leverage": preview.get("leverage"),
        "reduce_only": False,
        "preview_only": True,
    }


def _protective_orders_present(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return payload.get("status") == "READY" and isinstance(payload.get("stop_loss"), dict) and isinstance(payload.get("take_profit"), dict)


def _idempotency_clear(*, intent: dict[str, Any] | None, log_dir: Path) -> bool:
    if not intent:
        return False
    existing = _active_matching_rehearsal(
        execution_intent_id=intent.get("execution_intent_id"),
        preview_hash=intent.get("preview_hash"),
        log_dir=log_dir,
    )
    return existing is None or existing.get("status") == "REHEARSAL_READY"


def _active_matching_rehearsal(*, execution_intent_id: object, preview_hash: object, log_dir: Path) -> dict[str, Any] | None:
    if not execution_intent_id or not preview_hash:
        return None
    for record in load_live_executor_rehearsals(limit=0, execution_intent_id=str(execution_intent_id), log_dir=log_dir):
        if record.get("preview_hash") == preview_hash and record.get("status") == "REHEARSAL_READY":
            return record
    return None


def _operator_action(*, status: str, intent_status: str) -> str:
    if status == "REHEARSAL_READY":
        return "ready for executor dry-run"
    if intent_status in {"MISSING", "UNKNOWN"}:
        return "create intent"
    if intent_status == "EXPIRED":
        return "refresh approval"
    return "wait"


def _rehearsal_record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "executor_rehearsal_id": payload.get("executor_rehearsal_id"),
        "created_at": payload.get("created_at"),
        "phase": PHASE,
        "event_type": "live_executor_rehearsal",
        "execution_mode": EXECUTION_MODE,
        "execution_intent_id": payload.get("execution_intent_id"),
        "signal_id": payload.get("signal_id"),
        "preview_hash": payload.get("preview_hash"),
        "status": payload.get("status"),
        "sequence": [
            {"step": item.get("step"), "name": item.get("name"), "status": item.get("status"), "network": False}
            for item in payload.get("sequence", [])
        ],
        "entry_order_preview": payload.get("entry_order_preview"),
        "protective_orders_preview": payload.get("protective_orders_preview"),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "blockers": list(payload.get("blockers") or []),
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize_rehearsal_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "executor_rehearsal_id",
        "created_at",
        "phase",
        "event_type",
        "execution_mode",
        "execution_intent_id",
        "signal_id",
        "preview_hash",
        "status",
        "sequence",
        "entry_order_preview",
        "protective_orders_preview",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "network_allowed",
        "blockers",
        "secrets_shown",
    }
    sanitized = {key: record.get(key) for key in allowed if key in record}
    sanitized["order_placed"] = False
    sanitized["real_order_placed"] = False
    sanitized["execution_attempted"] = False
    sanitized["network_allowed"] = False
    sanitized["secrets_shown"] = False
    return sanitized


def _intent_unexpired(intent: dict[str, Any], *, now: datetime) -> bool:
    expires_at = _parse_datetime(intent.get("expires_at"))
    return expires_at is not None and expires_at > now and intent.get("status") == "INTENT_READY"


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
