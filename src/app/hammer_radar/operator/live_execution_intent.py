"""R52 protected execution intent for Hammer Radar.

This module converts exact approval plus an exact protected preview into a
durable INTENT_ONLY record for a future executor phase. It never places orders,
signs payloads, enables live trading, or calls Binance.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.live_approval import find_valid_live_approval_for_signal, load_live_approval_requests
from src.app.hammer_radar.operator.live_begins import build_live_begins_status
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview

PHASE = "R52"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "INTENT_ONLY"
LIVE_EXECUTION_INTENTS_FILENAME = "live_execution_intents.ndjson"
ENV_INTENT_TTL_SECONDS = "HAMMER_LIVE_EXECUTION_INTENT_TTL_SECONDS"
DEFAULT_INTENT_TTL_SECONDS = 300

ORDER_PLACED = False
REAL_ORDER_PLACED = False
WOULD_PLACE_ORDER = False
EXECUTION_ATTEMPTED = False
SECRETS_SHOWN = False


def create_live_execution_intent(
    *,
    signal_id: str | None,
    approval_code: str | None = None,
    dry_run: bool = True,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC)
    normalized_signal_id = str(signal_id or "").strip() or None
    live_begins = build_live_begins_status(log_dir=resolved_log_dir, env=source)
    preview = build_live_execution_preview(log_dir=resolved_log_dir, env=source)
    preview_hash = compute_preview_hash(preview) if preview.get("status") != "UNKNOWN" else None
    approvals = (
        load_live_approval_requests(limit=0, signal_id=normalized_signal_id, log_dir=resolved_log_dir)
        if normalized_signal_id
        else []
    )
    approval_lookup = find_valid_live_approval_for_signal(normalized_signal_id, log_dir=resolved_log_dir, now=created_at)
    approval_status = str(approval_lookup.get("approval_status") or _approval_status(approvals, signal_id=normalized_signal_id))
    expires_at = created_at + timedelta(seconds=_ttl_seconds(source))
    checks = _checks(
        signal_id=normalized_signal_id,
        approvals=approvals,
        approval_status=approval_status,
        live_begins=live_begins,
        preview=preview,
        preview_hash=preview_hash,
        log_dir=resolved_log_dir,
    )
    blockers = _blockers(
        signal_id=normalized_signal_id,
        approval_code=approval_code,
        dry_run=dry_run,
        approval_status=approval_status,
        live_begins=live_begins,
        preview=preview,
        checks=checks,
        log_dir=resolved_log_dir,
        preview_hash=preview_hash,
    )
    existing = _active_matching_intent(
        signal_id=normalized_signal_id,
        preview_hash=preview_hash,
        log_dir=resolved_log_dir,
        now=created_at,
    )
    status = _status(checks=checks, blockers=blockers)
    execution_intent_id = None
    if existing is not None and status == "INTENT_READY":
        execution_intent_id = str(existing.get("execution_intent_id") or "")
        expires_at_text = str(existing.get("expires_at") or expires_at.isoformat())
        created_at_text = str(existing.get("created_at") or created_at.isoformat())
    else:
        created_at_text = created_at.isoformat()
        expires_at_text = expires_at.isoformat()

    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "execution_intent_id": execution_intent_id,
        "signal_id": normalized_signal_id,
        "preview_hash": preview_hash,
        "approval_status": approval_status,
        "approval_request_id": approval_lookup.get("request_id"),
        "approval_gate_status": approval_lookup.get("approval_gate_status"),
        "live_begins_status": live_begins.get("status") or "UNKNOWN",
        "preview_status": preview.get("status") or "UNKNOWN",
        "expires_at": expires_at_text if status == "INTENT_READY" else None,
        "created_at": created_at_text,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "would_place_order": WOULD_PLACE_ORDER,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "checks": checks,
        "blockers": blockers,
        "operator_action": _operator_action(status=status, approval_status=approval_status, preview_status=preview.get("status")),
        "secrets_shown": SECRETS_SHOWN,
        "live_execution_intents_path": str(live_execution_intents_path(resolved_log_dir)),
    }
    if status == "INTENT_READY" and execution_intent_id is None:
        payload["execution_intent_id"] = uuid4().hex
        append_live_execution_intent(_intent_record(payload), log_dir=resolved_log_dir)
    return payload


def list_live_execution_intents(
    *,
    limit: int = 20,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_live_execution_intents(limit=limit, signal_id=signal_id, log_dir=get_log_dir(log_dir, use_env=True))
    return {
        "result_status": "ACCEPTED",
        "phase": PHASE,
        "count": len(records),
        "intents": records,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "secrets_shown": SECRETS_SHOWN,
    }


def load_live_execution_intents(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    intent_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = live_execution_intents_path(get_log_dir(log_dir, use_env=True))
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
            if intent_id is not None and record.get("execution_intent_id") != intent_id:
                continue
            records.append(_sanitize_intent_record(record))
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def live_execution_intents_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LIVE_EXECUTION_INTENTS_FILENAME


def append_live_execution_intent(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = live_execution_intents_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def compute_preview_hash(preview: dict[str, Any]) -> str:
    stable = {
        "signal_id": preview.get("latest_signal_id"),
        "symbol": preview.get("symbol"),
        "timeframe": preview.get("timeframe"),
        "direction": preview.get("direction"),
        "entry": preview.get("entry"),
        "stop": preview.get("stop"),
        "take_profit": preview.get("take_profit"),
        "order_side": preview.get("order_side"),
        "position_side": preview.get("position_side"),
        "margin_usdt": preview.get("margin_usdt"),
        "leverage": preview.get("leverage"),
        "notional_usdt": preview.get("notional_usdt"),
        "risk_usdt": preview.get("risk_usdt"),
        "quantity": preview.get("quantity"),
        "protective_orders_preview": preview.get("protective_orders_preview"),
        "execution_mode": preview.get("execution_mode"),
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def format_live_execution_intent_operator_message(payload: dict[str, Any]) -> str:
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:5]) if blockers else "none"
    return "\n".join(
        [
            f"R52 protected execution intent: {payload.get('status')}",
            "INTENT_ONLY. No order placed. real_order_placed=false.",
            f"signal_id: {payload.get('signal_id') or 'none'}",
            f"preview_hash: {payload.get('preview_hash') or 'none'}",
            f"approval_status: {payload.get('approval_status')}",
            f"intent_id: {payload.get('execution_intent_id') or 'none'}",
            f"expires_at: {payload.get('expires_at') or 'n/a'}",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )


def format_live_execution_intents_operator_message(payload: dict[str, Any]) -> str:
    intents = payload.get("intents") or []
    if not intents:
        detail = "none"
    else:
        detail = "; ".join(
            f"{item.get('signal_id')} {item.get('status')} {item.get('execution_intent_id')}" for item in intents[:5]
        )
    return "\n".join(
        [
            "R52 protected execution intents",
            "INTENT_ONLY list. No order placed.",
            f"count: {payload.get('count', 0)}",
            f"intents: {detail}",
        ]
    )


def _checks(
    *,
    signal_id: str | None,
    approvals: list[dict[str, Any]],
    approval_status: str,
    live_begins: dict[str, Any],
    preview: dict[str, Any],
    preview_hash: str | None,
    log_dir: Path,
) -> dict[str, bool]:
    preview_signal_id = preview.get("latest_signal_id")
    return {
        "signal_id_present": bool(signal_id),
        "exact_approval_present": approval_status == "APPROVED",
        "approval_matches_signal": bool(signal_id) and _has_exact_approval(approvals, signal_id=signal_id),
        "approval_not_expired": approval_status == "APPROVED",
        "preview_available": preview.get("status") in {"PREVIEW_READY", "BLOCKED", "NOT_READY"},
        "preview_matches_signal": bool(signal_id) and preview_signal_id == signal_id,
        "preview_hash_valid": bool(preview_hash),
        "live_begins_allows_intent": live_begins.get("status") in {"READY_FOR_OPERATOR_APPROVAL", "ELIGIBLE_TINY_LIVE"},
        "preview_allows_intent": preview.get("status") == "PREVIEW_READY",
        "idempotency_clear": _idempotency_clear(signal_id=signal_id, preview_hash=preview_hash, log_dir=log_dir),
    }


def _blockers(
    *,
    signal_id: str | None,
    approval_code: str | None,
    dry_run: bool,
    approval_status: str,
    live_begins: dict[str, Any],
    preview: dict[str, Any],
    checks: dict[str, bool],
    log_dir: Path,
    preview_hash: str | None,
) -> list[str]:
    blockers: list[str] = []
    if not checks["signal_id_present"]:
        blockers.append("signal_id is required")
    if approval_code:
        blockers.append("approval_code is not accepted by R52; use exact LIVE APPROVE <signal_id> approval record")
    if dry_run is not True:
        blockers.append("dry_run must remain true for R52 intent-only")
    if approval_status != "APPROVED":
        blockers.append(f"exact approval is {approval_status.lower()}")
    if not checks["approval_matches_signal"]:
        blockers.append("exact approval for signal_id is missing")
    if not checks["approval_not_expired"]:
        blockers.append("approval is missing or expired")
    if not checks["preview_available"]:
        blockers.append("preview is unavailable")
    if not checks["preview_matches_signal"]:
        blockers.append("preview does not match signal_id")
    if not checks["preview_hash_valid"]:
        blockers.append("preview hash is unavailable")
    if not checks["live_begins_allows_intent"]:
        blockers.append(f"live begins is {live_begins.get('status', 'UNKNOWN')}")
    if not checks["preview_allows_intent"]:
        blockers.append(f"execution preview is {preview.get('status', 'UNKNOWN')}")
    changed = _active_changed_preview_exists(signal_id=signal_id, preview_hash=preview_hash, log_dir=log_dir, now=datetime.now(UTC))
    if changed:
        blockers.append("preview changed for signal_id; re-approval required")
    if not checks["idempotency_clear"]:
        blockers.append("idempotency is not clear for signal")
    return list(dict.fromkeys(blocker for blocker in blockers if blocker))


def _status(*, checks: dict[str, bool], blockers: list[str]) -> str:
    if not checks["signal_id_present"]:
        return "REJECTED"
    if not blockers:
        return "INTENT_READY"
    return "BLOCKED"


def _operator_action(*, status: str, approval_status: str, preview_status: object) -> str:
    if status == "INTENT_READY":
        return "ready for executor rehearsal"
    if approval_status != "APPROVED":
        return "approve exact signal"
    if preview_status != "PREVIEW_READY":
        return "review preview"
    return "wait"


def _approval_status(records: list[dict[str, Any]], *, signal_id: str | None) -> str:
    if not signal_id:
        return "MISSING"
    if _has_exact_approval(records, signal_id=signal_id):
        return "APPROVED"
    if any(record.get("approval_gate_status") in {"EXPIRED"} for record in records):
        return "EXPIRED"
    if any(record.get("parse_status") == "REJECTED" or record.get("approval_gate_status") == "REJECTED" for record in records):
        return "REJECTED"
    return "MISSING"


def _has_exact_approval(records: list[dict[str, Any]], *, signal_id: str | None) -> bool:
    if not signal_id:
        return False
    now = datetime.now(UTC)
    for record in records:
        if record.get("signal_id") != signal_id:
            continue
        if record.get("normalized_action") != "live_approve_exact":
            continue
        if record.get("parse_status") != "ACCEPTED":
            continue
        if record.get("approval_gate_status") not in {"READY_BUT_EXECUTION_DISABLED", "APPROVED", "BLOCKED"}:
            continue
        if record.get("freshness_status") == "expired":
            continue
        expires_at = _parse_datetime(record.get("expires_at"))
        if expires_at is not None and expires_at <= now:
            continue
        if record.get("used") is True:
            continue
        return True
    return False


def _idempotency_clear(*, signal_id: str | None, preview_hash: str | None, log_dir: Path) -> bool:
    if not signal_id or not preview_hash:
        return False
    return _active_changed_preview_exists(signal_id=signal_id, preview_hash=preview_hash, log_dir=log_dir, now=datetime.now(UTC)) is False


def _active_matching_intent(
    *,
    signal_id: str | None,
    preview_hash: str | None,
    log_dir: Path,
    now: datetime,
) -> dict[str, Any] | None:
    if not signal_id or not preview_hash:
        return None
    for record in load_live_execution_intents(limit=0, signal_id=signal_id, log_dir=log_dir):
        if record.get("preview_hash") != preview_hash:
            continue
        if _intent_unexpired(record, now=now):
            return record
    return None


def _active_changed_preview_exists(
    *,
    signal_id: str | None,
    preview_hash: str | None,
    log_dir: Path,
    now: datetime,
) -> bool:
    if not signal_id or not preview_hash:
        return False
    for record in load_live_execution_intents(limit=0, signal_id=signal_id, log_dir=log_dir):
        if record.get("preview_hash") == preview_hash:
            continue
        if _intent_unexpired(record, now=now):
            return True
    return False


def _intent_unexpired(record: dict[str, Any], *, now: datetime) -> bool:
    expires_at = _parse_datetime(record.get("expires_at"))
    return expires_at is not None and expires_at > now and record.get("status") == "INTENT_READY"


def _intent_record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "execution_intent_id": payload.get("execution_intent_id"),
        "created_at": payload.get("created_at"),
        "expires_at": payload.get("expires_at"),
        "phase": PHASE,
        "event_type": "live_execution_intent",
        "status": payload.get("status"),
        "signal_id": payload.get("signal_id"),
        "preview_hash": payload.get("preview_hash"),
        "approval_status": payload.get("approval_status"),
        "live_begins_status": payload.get("live_begins_status"),
        "preview_status": payload.get("preview_status"),
        "execution_mode": EXECUTION_MODE,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "blockers": list(payload.get("blockers") or []),
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize_intent_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "execution_intent_id",
        "created_at",
        "expires_at",
        "phase",
        "event_type",
        "status",
        "signal_id",
        "preview_hash",
        "approval_status",
        "live_begins_status",
        "preview_status",
        "execution_mode",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "blockers",
        "secrets_shown",
    }
    sanitized = {key: record.get(key) for key in allowed if key in record}
    sanitized["secrets_shown"] = False
    sanitized["order_placed"] = False
    sanitized["real_order_placed"] = False
    sanitized["execution_attempted"] = False
    return sanitized


def _ttl_seconds(source: Mapping[str, str]) -> int:
    value = str(source.get(ENV_INTENT_TTL_SECONDS) or "").strip()
    if not value:
        return DEFAULT_INTENT_TTL_SECONDS
    try:
        parsed = int(value)
    except ValueError:
        return DEFAULT_INTENT_TTL_SECONDS
    return parsed if parsed > 0 else DEFAULT_INTENT_TTL_SECONDS


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
