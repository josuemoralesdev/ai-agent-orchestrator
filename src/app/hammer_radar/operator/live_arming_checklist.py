"""R54 live arming checklist for Hammer Radar.

This module evaluates whether all prerequisites are present for a future
first protected tiny-live arming step. It never arms automatically, places
orders, flips settings, signs payloads, or calls Binance.
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
from src.app.hammer_radar.operator.live_begins import build_live_begins_status
from src.app.hammer_radar.operator.live_execution_intent import compute_preview_hash, load_live_execution_intents
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview
from src.app.hammer_radar.operator.live_executor_rehearsal import load_live_executor_rehearsals

PHASE = "R54"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "ARMING_CHECK_ONLY"
LIVE_ARMING_CHECKS_FILENAME = "live_arming_checks.ndjson"

NETWORK_ALLOWED = False
ORDER_PLACED = False
REAL_ORDER_PLACED = False
WOULD_PLACE_ORDER = False
EXECUTION_ATTEMPTED = False
SECRETS_SHOWN = False
OPERATOR_FINAL_ARM_REQUIRED = True

ENV_TELEGRAM_BOT_TOKEN = "TELEGRAM_BOT_TOKEN"


def build_live_arming_status(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_live_arming(log_dir=log_dir, env=env, persist=False)


def evaluate_and_record_live_arming_check(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_live_arming(log_dir=log_dir, env=env, persist=True)


def list_live_arming_checks(
    *,
    limit: int = 20,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_live_arming_checks(limit=limit, status=status, log_dir=get_log_dir(log_dir, use_env=True))
    return {
        "result_status": "ACCEPTED",
        "phase": PHASE,
        "count": len(records),
        "checks": records,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "secrets_shown": SECRETS_SHOWN,
    }


def load_live_arming_checks(
    *,
    limit: int = 50,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = live_arming_checks_path(get_log_dir(log_dir, use_env=True))
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
            records.append(_sanitize_arming_record(record))
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def live_arming_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LIVE_ARMING_CHECKS_FILENAME


def append_live_arming_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = live_arming_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_live_arming_operator_message(payload: dict[str, Any]) -> str:
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:5]) if blockers else "none"
    return "\n".join(
        [
            f"R54 live arming checklist: {payload.get('status')}",
            "ARMING_CHECK_ONLY. No order placed. real_order_placed=false.",
            f"live flags: live_execution={payload.get('live_execution_enabled')} binance_live={payload.get('binance_live_enabled')} allow_live_orders={payload.get('allow_live_orders')}",
            f"kill_switch: {payload.get('global_kill_switch')} connector_mode: {payload.get('connector_mode')}",
            f"protective: required={payload.get('protective_orders_required')} enabled={payload.get('protective_orders_enabled')} mode={payload.get('protective_order_mode')}",
            f"credential presence: binance_key={payload.get('binance_key_present')} binance_secret={payload.get('binance_secret_present')} telegram_token={payload.get('telegram_token_present')}",
            f"R50/R51/R52/R53: {payload.get('live_begins_status')} / {payload.get('preview_status')} / {payload.get('intent_status')} / {payload.get('rehearsal_status')}",
            f"signal/intent/rehearsal: {payload.get('latest_signal_id') or 'none'} / {payload.get('latest_execution_intent_id') or 'none'} / {payload.get('latest_executor_rehearsal_id') or 'none'}",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )


def format_live_arming_checks_operator_message(payload: dict[str, Any]) -> str:
    checks = payload.get("checks") or []
    if not checks:
        detail = "none"
    else:
        detail = "; ".join(
            f"{item.get('created_at')} {item.get('status')} {item.get('latest_signal_id') or 'none'}"
            for item in checks[:5]
        )
    return "\n".join(
        [
            "R54 live arming checks",
            "ARMING_CHECK_ONLY list. No order placed.",
            f"count: {payload.get('count', 0)}",
            f"checks: {detail}",
        ]
    )


def _evaluate_live_arming(
    *,
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
    signal_id = _latest_signal_id(live_begins=live_begins, preview=preview)
    preview_hash = compute_preview_hash(preview) if preview.get("status") != "UNKNOWN" else None
    intent = _latest_matching_intent(signal_id=signal_id, preview_hash=preview_hash, log_dir=resolved_log_dir, now=created_at)
    intent_status = _intent_status(intent, signal_id=signal_id, preview_hash=preview_hash, log_dir=resolved_log_dir, now=created_at)
    rehearsal = _latest_matching_rehearsal(
        intent=intent,
        signal_id=signal_id,
        preview_hash=preview_hash,
        log_dir=resolved_log_dir,
    )
    rehearsal_status = _rehearsal_status(rehearsal, intent=intent, signal_id=signal_id, preview_hash=preview_hash, log_dir=resolved_log_dir)
    checks = _checks(
        source=source,
        connector=connector,
        protective=protective,
        live_begins=live_begins,
        preview=preview,
        signal_id=signal_id,
        preview_hash=preview_hash,
        intent=intent,
        intent_status=intent_status,
        rehearsal=rehearsal,
        rehearsal_status=rehearsal_status,
        log_dir=resolved_log_dir,
    )
    blockers = _blockers(
        connector=connector,
        protective=protective,
        live_begins=live_begins,
        preview=preview,
        intent_status=intent_status,
        rehearsal_status=rehearsal_status,
        checks=checks,
    )
    status = _status(checks=checks, blockers=blockers)
    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "created_at": created_at.isoformat(),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "would_place_order": WOULD_PLACE_ORDER,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "live_execution_enabled": bool(connector.get("live_execution_enabled")),
        "binance_live_enabled": bool(connector.get("binance_live_enabled")),
        "allow_live_orders": bool(connector.get("allow_live_orders")),
        "global_kill_switch": bool(connector.get("global_kill_switch")),
        "connector_mode": connector.get("connector_mode") or "DRY_RUN_ONLY",
        "protective_orders_required": bool(protective.get("protective_orders_required")),
        "protective_orders_enabled": bool(protective.get("protective_orders_enabled")),
        "protective_order_mode": protective.get("protective_order_mode") or "PREVIEW_ONLY",
        "binance_key_present": bool(connector.get("api_key_present")),
        "binance_secret_present": bool(connector.get("api_secret_present")),
        "telegram_token_present": bool(str(source.get(ENV_TELEGRAM_BOT_TOKEN) or "").strip()),
        "latest_signal_id": signal_id,
        "latest_execution_intent_id": (intent or {}).get("execution_intent_id"),
        "latest_executor_rehearsal_id": (rehearsal or {}).get("executor_rehearsal_id"),
        "live_begins_status": live_begins.get("status") or "UNKNOWN",
        "preview_status": preview.get("status") or "UNKNOWN",
        "intent_status": intent_status,
        "rehearsal_status": rehearsal_status,
        "checks": checks,
        "blockers": blockers,
        "operator_action": _operator_action(status=status, checks=checks),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "live_arming_checks_path": str(live_arming_checks_path(resolved_log_dir)),
    }
    if persist:
        record = _arming_record(payload)
        append_live_arming_check(record, log_dir=resolved_log_dir)
        payload["audit_event_id"] = record["event_id"]
    return payload


def _latest_signal_id(*, live_begins: dict[str, Any], preview: dict[str, Any]) -> str | None:
    value = preview.get("latest_signal_id") or live_begins.get("latest_signal_id")
    return str(value).strip() if value else None


def _latest_matching_intent(
    *,
    signal_id: str | None,
    preview_hash: str | None,
    log_dir: Path,
    now: datetime,
) -> dict[str, Any] | None:
    if not signal_id:
        return None
    latest_unexpired: dict[str, Any] | None = None
    latest_same_hash: dict[str, Any] | None = None
    for record in load_live_execution_intents(limit=0, signal_id=signal_id, log_dir=log_dir):
        if record.get("preview_hash") == preview_hash and latest_same_hash is None:
            latest_same_hash = record
        if _intent_unexpired(record, now=now) and latest_unexpired is None:
            latest_unexpired = record
        if record.get("preview_hash") == preview_hash and _intent_valid(record, now=now):
            return record
    if latest_same_hash is not None:
        return latest_same_hash
    return latest_unexpired


def _latest_matching_rehearsal(
    *,
    intent: dict[str, Any] | None,
    signal_id: str | None,
    preview_hash: str | None,
    log_dir: Path,
) -> dict[str, Any] | None:
    if not signal_id:
        return None
    records = load_live_executor_rehearsals(
        limit=0,
        signal_id=signal_id,
        execution_intent_id=(intent or {}).get("execution_intent_id"),
        log_dir=log_dir,
    )
    latest: dict[str, Any] | None = None
    for record in records:
        if latest is None:
            latest = record
        if record.get("preview_hash") == preview_hash and _rehearsal_valid(record, intent=intent):
            return record
    return latest


def _intent_status(
    intent: dict[str, Any] | None,
    *,
    signal_id: str | None,
    preview_hash: str | None,
    log_dir: Path,
    now: datetime,
) -> str:
    if not signal_id:
        return "MISSING"
    records = load_live_execution_intents(limit=0, signal_id=signal_id, log_dir=log_dir)
    if intent is None:
        return "MISSING" if not records else "UNKNOWN"
    if intent.get("status") != "INTENT_READY":
        return str(intent.get("status") or "UNKNOWN")
    if not _intent_unexpired(intent, now=now):
        return "EXPIRED"
    if intent.get("preview_hash") != preview_hash:
        return "UNKNOWN"
    if not _intent_valid(intent, now=now):
        return "UNKNOWN"
    return "INTENT_READY"


def _rehearsal_status(
    rehearsal: dict[str, Any] | None,
    *,
    intent: dict[str, Any] | None,
    signal_id: str | None,
    preview_hash: str | None,
    log_dir: Path,
) -> str:
    if not signal_id:
        return "MISSING"
    records = load_live_executor_rehearsals(
        limit=0,
        signal_id=signal_id,
        execution_intent_id=(intent or {}).get("execution_intent_id"),
        log_dir=log_dir,
    )
    if rehearsal is None:
        return "MISSING" if not records else "UNKNOWN"
    if rehearsal.get("status") != "REHEARSAL_READY":
        return str(rehearsal.get("status") or "UNKNOWN")
    if rehearsal.get("preview_hash") != preview_hash:
        return "UNKNOWN"
    if not _rehearsal_valid(rehearsal, intent=intent):
        return "UNKNOWN"
    return "REHEARSAL_READY"


def _checks(
    *,
    source: Mapping[str, str],
    connector: dict[str, Any],
    protective: dict[str, Any],
    live_begins: dict[str, Any],
    preview: dict[str, Any],
    signal_id: str | None,
    preview_hash: str | None,
    intent: dict[str, Any] | None,
    intent_status: str,
    rehearsal: dict[str, Any] | None,
    rehearsal_status: str,
    log_dir: Path,
) -> dict[str, bool]:
    return {
        "live_execution_enabled": connector.get("live_execution_enabled") is True,
        "binance_live_enabled": connector.get("binance_live_enabled") is True,
        "allow_live_orders": connector.get("allow_live_orders") is True,
        "global_kill_switch_off": connector.get("global_kill_switch") is False,
        "connector_mode_live_or_allowed": connector.get("connector_mode") == LIVE_ORDER_ENABLED,
        "binance_credentials_present": bool(connector.get("api_key_present")) and bool(connector.get("api_secret_present")),
        "protective_orders_ready": _protective_ready(protective),
        "tiny_live_margin_valid": _positive_number(preview.get("margin_usdt")),
        "min_notional_valid": preview.get("min_notional_ok") is True,
        "latest_signal_present": bool(signal_id),
        "latest_signal_fresh": live_begins.get("freshness_status") == "fresh",
        "live_begins_allows_arming": live_begins.get("status") == "ELIGIBLE_TINY_LIVE",
        "preview_ready": preview.get("status") == "PREVIEW_READY",
        "intent_ready": intent_status == "INTENT_READY",
        "rehearsal_ready": rehearsal_status == "REHEARSAL_READY",
        "idempotency_clear": _idempotency_clear(
            signal_id=signal_id,
            preview_hash=preview_hash,
            intent=intent,
            rehearsal=rehearsal,
            log_dir=log_dir,
        ),
        "operator_final_arm_required": OPERATOR_FINAL_ARM_REQUIRED,
    }


def _blockers(
    *,
    connector: dict[str, Any],
    protective: dict[str, Any],
    live_begins: dict[str, Any],
    preview: dict[str, Any],
    intent_status: str,
    rehearsal_status: str,
    checks: dict[str, bool],
) -> list[str]:
    blockers: list[str] = []
    if not checks["live_execution_enabled"]:
        blockers.append("live_execution_enabled is false")
    if not checks["binance_live_enabled"]:
        blockers.append("HAMMER_BINANCE_LIVE_ENABLED is false")
    if not checks["allow_live_orders"]:
        blockers.append("allow_live_orders is false")
    if not checks["global_kill_switch_off"]:
        blockers.append("global kill switch is active")
    if not checks["connector_mode_live_or_allowed"]:
        blockers.append(f"connector_mode is {connector.get('connector_mode', 'UNKNOWN')}")
    if not checks["binance_credentials_present"]:
        blockers.append("Binance API key and secret presence is required")
    if not checks["protective_orders_ready"]:
        blockers.append(
            f"protective orders are required but not ready/enabled; mode={protective.get('protective_order_mode', 'UNKNOWN')}"
        )
    if not checks["latest_signal_present"]:
        blockers.append("latest signal is missing")
    if not checks["latest_signal_fresh"]:
        blockers.append("latest signal is not fresh")
    if not checks["live_begins_allows_arming"]:
        blockers.append(f"live begins is {live_begins.get('status', 'UNKNOWN')}")
    if not checks["preview_ready"]:
        blockers.append(f"execution preview is {preview.get('status', 'UNKNOWN')}")
    if not checks["tiny_live_margin_valid"]:
        blockers.append("tiny-live margin is invalid")
    if not checks["min_notional_valid"]:
        blockers.append("minimum notional is not valid")
    if not checks["intent_ready"]:
        blockers.append(f"execution intent is {intent_status}")
    if not checks["rehearsal_ready"]:
        blockers.append(f"executor rehearsal is {rehearsal_status}")
    if not checks["idempotency_clear"]:
        blockers.append("idempotency is not clear for arming")
    return list(dict.fromkeys(blocker for blocker in blockers if blocker))


def _status(*, checks: dict[str, bool], blockers: list[str]) -> str:
    if not checks["latest_signal_present"]:
        return "NOT_READY"
    if not blockers:
        return "ARMING_ALLOWED"
    return "BLOCKED"


def _operator_action(*, status: str, checks: dict[str, bool]) -> str:
    if status == "ARMING_ALLOWED":
        return "final arm required"
    if not checks["live_execution_enabled"] or not checks["allow_live_orders"]:
        return "prepare env"
    if not checks["intent_ready"]:
        return "create intent"
    if not checks["rehearsal_ready"]:
        return "rehearse"
    return "keep blocked"


def _protective_ready(protective: dict[str, Any]) -> bool:
    required = protective.get("protective_orders_required") is True
    if not required:
        return False
    return (
        protective.get("protective_orders_enabled") is True
        and protective.get("protective_order_mode") == LIVE_PROTECTIVE_ENABLED
        and protective.get("protective_orders_supported") is True
        and protective.get("protective_stop_supported") is True
        and protective.get("protective_take_profit_supported") is True
    )


def _idempotency_clear(
    *,
    signal_id: str | None,
    preview_hash: str | None,
    intent: dict[str, Any] | None,
    rehearsal: dict[str, Any] | None,
    log_dir: Path,
) -> bool:
    if not signal_id or not preview_hash or not intent or not rehearsal:
        return False
    if _unsafe_order_record_seen(signal_id=signal_id, log_dir=log_dir):
        return False
    for record in load_live_execution_intents(limit=0, signal_id=signal_id, log_dir=log_dir):
        if record.get("preview_hash") != preview_hash and record.get("status") == "INTENT_READY":
            if _parse_datetime(record.get("expires_at")) and _parse_datetime(record.get("expires_at")) > datetime.now(UTC):
                return False
    return True


def _unsafe_order_record_seen(*, signal_id: str, log_dir: Path) -> bool:
    for intent in load_live_execution_intents(limit=0, signal_id=signal_id, log_dir=log_dir):
        if intent.get("order_placed") is True or intent.get("real_order_placed") is True or intent.get("execution_attempted") is True:
            return True
    for rehearsal in load_live_executor_rehearsals(limit=0, signal_id=signal_id, log_dir=log_dir):
        if (
            rehearsal.get("order_placed") is True
            or rehearsal.get("real_order_placed") is True
            or rehearsal.get("execution_attempted") is True
            or rehearsal.get("network_allowed") is True
        ):
            return True
    return False


def _intent_valid(record: dict[str, Any], *, now: datetime) -> bool:
    return (
        record.get("status") == "INTENT_READY"
        and record.get("execution_mode") == "INTENT_ONLY"
        and _intent_unexpired(record, now=now)
        and record.get("order_placed") is not True
        and record.get("real_order_placed") is not True
        and record.get("execution_attempted") is not True
        and record.get("secrets_shown") is not True
        and bool(record.get("preview_hash"))
    )


def _intent_unexpired(record: dict[str, Any], *, now: datetime) -> bool:
    expires_at = _parse_datetime(record.get("expires_at"))
    return expires_at is not None and expires_at > now and record.get("status") == "INTENT_READY"


def _rehearsal_valid(record: dict[str, Any], *, intent: dict[str, Any] | None) -> bool:
    if intent is None:
        return False
    return (
        record.get("status") == "REHEARSAL_READY"
        and record.get("execution_mode") == "REHEARSAL_ONLY"
        and record.get("execution_intent_id") == intent.get("execution_intent_id")
        and record.get("signal_id") == intent.get("signal_id")
        and record.get("preview_hash") == intent.get("preview_hash")
        and record.get("network_allowed") is not True
        and record.get("order_placed") is not True
        and record.get("real_order_placed") is not True
        and record.get("execution_attempted") is not True
        and record.get("secrets_shown") is not True
    )


def _positive_number(value: object) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _arming_record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "live_arming_check",
        "status": payload.get("status"),
        "created_at": payload.get("created_at"),
        "latest_signal_id": payload.get("latest_signal_id"),
        "latest_execution_intent_id": payload.get("latest_execution_intent_id"),
        "latest_executor_rehearsal_id": payload.get("latest_executor_rehearsal_id"),
        "live_begins_status": payload.get("live_begins_status"),
        "preview_status": payload.get("preview_status"),
        "intent_status": payload.get("intent_status"),
        "rehearsal_status": payload.get("rehearsal_status"),
        "execution_mode": EXECUTION_MODE,
        "live_execution_enabled": bool(payload.get("live_execution_enabled")),
        "binance_live_enabled": bool(payload.get("binance_live_enabled")),
        "allow_live_orders": bool(payload.get("allow_live_orders")),
        "global_kill_switch": bool(payload.get("global_kill_switch")),
        "connector_mode": payload.get("connector_mode"),
        "protective_orders_required": bool(payload.get("protective_orders_required")),
        "protective_orders_enabled": bool(payload.get("protective_orders_enabled")),
        "protective_order_mode": payload.get("protective_order_mode"),
        "binance_key_present": bool(payload.get("binance_key_present")),
        "binance_secret_present": bool(payload.get("binance_secret_present")),
        "telegram_token_present": bool(payload.get("telegram_token_present")),
        "blockers": list(payload.get("blockers") or []),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize_arming_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "event_id",
        "phase",
        "event_type",
        "status",
        "created_at",
        "latest_signal_id",
        "latest_execution_intent_id",
        "latest_executor_rehearsal_id",
        "live_begins_status",
        "preview_status",
        "intent_status",
        "rehearsal_status",
        "execution_mode",
        "live_execution_enabled",
        "binance_live_enabled",
        "allow_live_orders",
        "global_kill_switch",
        "connector_mode",
        "protective_orders_required",
        "protective_orders_enabled",
        "protective_order_mode",
        "binance_key_present",
        "binance_secret_present",
        "telegram_token_present",
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
