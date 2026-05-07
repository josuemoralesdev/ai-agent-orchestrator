"""R63 first-live protective adapter verification.

This module validates sanitized protective stop-loss and take-profit payload
previews for the R58/R62 first-live profile. It never signs requests, places
orders, edits env files, or calls Binance.
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
    LIVE_PROTECTIVE_ENABLED,
    build_protective_status,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_ladder_submit_adapter import build_first_live_ladder_submit_status
from src.app.hammer_radar.operator.first_microscopic_live_attempt import build_first_microscopic_live_profile
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview

PHASE = "R63"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "FIRST_LIVE_PROTECTIVE_ADAPTER_ONLY"
CHECKS_FILENAME = "first_live_protective_checks.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

DEFAULT_TRANSPORT_MODE = "DRY_RUN"
TRANSPORT_MODES = {"MOCK", "DRY_RUN", "LIVE_CHECK", "LIVE"}
PROTECTIVE_ORDER_TYPES = {"STOP_MARKET", "TAKE_PROFIT_MARKET", "STOP", "TAKE_PROFIT"}


def build_first_live_protective_status(
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
    return _evaluate(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        transport_mode=transport_mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=log_dir,
        env=env,
        persist=False,
    )


def evaluate_and_record_first_live_protective_check(
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
    return _evaluate(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        transport_mode=transport_mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=log_dir,
        env=env,
        persist=True,
    )


def list_first_live_protective_checks(
    *,
    limit: int = 20,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_first_live_protective_checks(limit=limit, status=status, log_dir=get_log_dir(log_dir, use_env=True))
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


def load_first_live_protective_checks(
    *,
    limit: int = 50,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_protective_checks_path(get_log_dir(log_dir, use_env=True))
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


def first_live_protective_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHECKS_FILENAME


def append_first_live_protective_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_protective_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_first_live_protective_operator_message(payload: dict[str, Any], *, section: str = "check") -> str:
    profile = payload.get("profile") or {}
    entry = payload.get("entry_context") or {}
    plan = payload.get("protective_plan") or {}
    gate = payload.get("protective_gate") or {}
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:6]) if blockers else "none"
    lines = [
        f"R63 first-live protective {section}: {payload.get('status')}",
        (
            "R58 profile: "
            f"{profile.get('margin_usdt')} USDT margin, {profile.get('leverage')}x, "
            f"{profile.get('margin_mode')}, {profile.get('entry_mode')}, cap {profile.get('max_notional_usdt')}"
        ),
    ]
    if section in {"check", "stop", "take_profit"}:
        lines.append(
            "protective: "
            f"stop={plan.get('stop_loss_available')} take_profit={plan.get('take_profit_available')} "
            f"reduce_only_ok={plan.get('stop_loss_reduce_only_ok') and plan.get('take_profit_reduce_only_ok')} "
            f"quantity_matches_entry={plan.get('quantity_matches_entry')}"
        )
    if section in {"check", "payload"}:
        lines.append(
            "payload preview: "
            f"stop_present={plan.get('stop_loss_payload_preview') is not None} "
            f"take_profit_present={plan.get('take_profit_payload_preview') is not None} "
            "signed_payload_created=false secrets_shown=false"
        )
    if section == "check":
        lines.append(
            "gate: "
            f"protective_env_allows={gate.get('protective_env_allows')} "
            f"ready_for_live_entry={gate.get('protective_ready_for_live_entry')} "
            f"naked_entry_blocked={gate.get('naked_entry_blocked')}"
        )
        lines.append(f"entry: side={entry.get('entry_side')} quantity={entry.get('entry_quantity')}")
    lines.extend(
        [
            "PROTECTIVE_ADAPTER_VERIFICATION_ONLY. No order placed. real_order_placed=false.",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )
    return "\n".join(lines)


def format_first_live_protective_checks_operator_message(payload: dict[str, Any]) -> str:
    checks = payload.get("checks") or []
    detail = "none"
    if checks:
        detail = "; ".join(f"{item.get('created_at')} {item.get('status')}" for item in checks[:5])
    return "\n".join(
        [
            "R63 first-live protective checks",
            "PROTECTIVE_ADAPTER_VERIFICATION_ONLY list. No order placed.",
            f"count: {payload.get('count', 0)}",
            f"checks: {detail}",
            "order_placed=false real_order_placed=false secrets_shown=false",
        ]
    )


def _evaluate(
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
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC).isoformat()
    mode = _normalize_transport_mode(transport_mode)
    r58 = build_first_microscopic_live_profile(log_dir=resolved_log_dir, env=source)
    profile = _profile(r58.get("profile") or {})
    preview = build_live_execution_preview(log_dir=resolved_log_dir, env=source)
    ladder = build_first_live_ladder_submit_status(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        transport_mode=mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=resolved_log_dir,
        env=source,
    )
    protective_status = build_protective_status(env=source, log_dir=resolved_log_dir)
    entry_context = _entry_context(ladder=ladder, preview=preview)
    protective_plan = _protective_plan(profile=profile, preview=preview, entry_context=entry_context)
    protective_gate = _protective_gate(
        mode=mode,
        dry_run=dry_run,
        final_confirmation=final_confirmation,
        protective_status=protective_status,
        protective_plan=protective_plan,
    )
    payloads = {
        "stop_loss_payload": _sanitize_nested(protective_plan.get("stop_loss_payload_preview")),
        "take_profit_payload": _sanitize_nested(protective_plan.get("take_profit_payload_preview")),
        "signed_payload_created": False,
        "secrets_shown": SECRETS_SHOWN,
    }
    blockers = _blockers(protective_plan=protective_plan, protective_gate=protective_gate)
    status = _status(protective_plan=protective_plan, protective_gate=protective_gate, blockers=blockers)
    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "created_at": created_at,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "profile": profile,
        "entry_context": entry_context,
        "protective_plan": protective_plan,
        "protective_gate": protective_gate,
        "sanitized_payloads": payloads,
        "blockers": blockers,
        "operator_action": _operator_action(protective_plan=protective_plan, protective_gate=protective_gate),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "first_live_protective_checks_path": str(first_live_protective_checks_path(resolved_log_dir)),
    }
    if persist:
        record = _record(payload)
        append_first_live_protective_check(record, log_dir=resolved_log_dir)
        payload["check_id"] = record["check_id"]
    return payload


def _profile(source: Mapping[str, Any]) -> dict[str, Any]:
    margin = _float(source.get("margin_usdt"), 44.0)
    leverage = int(_float(source.get("leverage"), 10.0))
    max_notional = _float(source.get("max_notional_usdt"), 444.0)
    return {
        "symbol": str(source.get("symbol") or "BTCUSDT"),
        "margin_usdt": margin,
        "leverage": leverage,
        "notional_usdt": margin * leverage,
        "max_notional_usdt": max_notional,
        "margin_mode": str(source.get("margin_mode") or "ISOLATED").upper(),
        "entry_mode": str(source.get("entry_mode") or "LADDER").upper(),
        "protective_orders_required": bool(source.get("protective_orders_required", True)),
        "one_attempt_only": bool(source.get("one_attempt_only", True)),
    }


def _entry_context(*, ladder: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    plan = ladder.get("ladder_submit_plan") if isinstance(ladder.get("ladder_submit_plan"), dict) else {}
    direction = str(preview.get("direction") or "").lower()
    side = plan.get("side")
    if side is None:
        side = "BUY" if direction in {"long", "buy"} else "SELL" if direction in {"short", "sell"} else None
    quantity = _float_or_none(plan.get("quantity"))
    return {
        "entry_side": side,
        "entry_quantity": quantity,
        "entry_quantity_valid": bool(quantity is not None and quantity > 0),
        "entry_plan_available": bool(plan.get("quantity_valid") is True),
        "aggregate_preview_only": bool(plan.get("aggregate_preview_only", True)),
    }


def _protective_plan(*, profile: dict[str, Any], preview: dict[str, Any], entry_context: dict[str, Any]) -> dict[str, Any]:
    protective_preview = preview.get("protective_orders_preview") if isinstance(preview.get("protective_orders_preview"), dict) else {}
    stop_payload = _sanitize_nested(protective_preview.get("stop_loss")) if isinstance(protective_preview.get("stop_loss"), dict) else None
    take_payload = (
        _sanitize_nested(protective_preview.get("take_profit")) if isinstance(protective_preview.get("take_profit"), dict) else None
    )
    stop_validation = _validate_leg(stop_payload, role="stop_loss", entry_context=entry_context)
    take_validation = _validate_leg(take_payload, role="take_profit", entry_context=entry_context)
    close_or_quantity_ok = stop_validation["close_position_or_quantity_ok"] and take_validation["close_position_or_quantity_ok"]
    side_reduces = stop_validation["side_reduces_entry"] and take_validation["side_reduces_entry"]
    quantity_matches = stop_validation["quantity_matches_entry"] and take_validation["quantity_matches_entry"]
    trigger_prices = stop_validation["trigger_price_available"] and take_validation["trigger_price_available"]
    available = (
        profile.get("protective_orders_required") is True
        and stop_validation["available"]
        and take_validation["available"]
        and close_or_quantity_ok
        and side_reduces
        and quantity_matches
        and trigger_prices
    )
    blockers: list[str] = []
    if profile.get("protective_orders_required") is not True:
        blockers.append("protective orders must be required")
    blockers.extend(stop_validation["blockers"])
    blockers.extend(take_validation["blockers"])
    if not available:
        blockers.append("protective stop-loss and take-profit payloads are not fully verified")
    return {
        "available": available,
        "plan_id": None,
        "symbol": profile["symbol"],
        "protective_orders_required": True,
        "stop_loss_required": True,
        "take_profit_required": True,
        "stop_loss_payload_preview": stop_payload,
        "take_profit_payload_preview": take_payload,
        "stop_loss_available": stop_validation["available"],
        "take_profit_available": take_validation["available"],
        "reduce_only_required": True,
        "stop_loss_reduce_only_ok": stop_validation["reduce_only_ok"],
        "take_profit_reduce_only_ok": take_validation["reduce_only_ok"],
        "close_position_or_quantity_ok": close_or_quantity_ok,
        "side_reduces_entry": side_reduces,
        "quantity_matches_entry": quantity_matches,
        "trigger_prices_available": trigger_prices,
        "payloads_sanitized": True,
        "blockers": list(dict.fromkeys(blockers)),
    }


def _validate_leg(payload: dict[str, Any] | None, *, role: str, entry_context: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if payload is None:
        return {
            "available": False,
            "reduce_only_ok": False,
            "close_position_or_quantity_ok": False,
            "side_reduces_entry": False,
            "quantity_matches_entry": False,
            "trigger_price_available": False,
            "blockers": [f"protective {role} payload preview is missing"],
        }
    order_type = str(payload.get("order_type") or payload.get("type") or "").upper()
    if order_type not in PROTECTIVE_ORDER_TYPES:
        blockers.append(f"protective {role} order type is not supported")
    reduce_only = _bool(payload.get("reduce_only")) or _bool(payload.get("reduceOnly"))
    close_position = _bool(payload.get("close_position")) or _bool(payload.get("closePosition"))
    reduce_only_ok = reduce_only or close_position
    if not reduce_only_ok:
        blockers.append(f"protective {role} must be reduce_only or closePosition")
    trigger_price = _float_or_none(payload.get("stopPrice") or payload.get("trigger_price") or payload.get("stop_price"))
    trigger_available = bool(trigger_price is not None and trigger_price > 0)
    if not trigger_available:
        blockers.append(f"protective {role} trigger price is missing")
    entry_side = entry_context.get("entry_side")
    close_side = "SELL" if entry_side == "BUY" else "BUY" if entry_side == "SELL" else None
    payload_side = str(payload.get("side") or "").upper() or None
    side_reduces = bool(close_position or (close_side is not None and payload_side == close_side))
    if not side_reduces:
        blockers.append(f"protective {role} side does not reduce entry")
    entry_quantity = _float_or_none(entry_context.get("entry_quantity"))
    payload_quantity = _float_or_none(payload.get("quantity"))
    quantity_matches = bool(close_position or (entry_quantity is not None and payload_quantity is not None and abs(entry_quantity - payload_quantity) < 1e-9))
    if not quantity_matches:
        blockers.append(f"protective {role} quantity does not match entry")
    return {
        "available": bool(not blockers),
        "reduce_only_ok": reduce_only_ok,
        "close_position_or_quantity_ok": bool(close_position or quantity_matches),
        "side_reduces_entry": side_reduces,
        "quantity_matches_entry": quantity_matches,
        "trigger_price_available": trigger_available,
        "blockers": blockers,
    }


def _protective_gate(
    *,
    mode: str,
    dry_run: bool,
    final_confirmation: bool,
    protective_status: dict[str, Any],
    protective_plan: dict[str, Any],
) -> dict[str, Any]:
    env_allows = (
        protective_status.get("protective_orders_enabled") is True
        and protective_status.get("protective_order_mode") == LIVE_PROTECTIVE_ENABLED
        and protective_status.get("protective_stop_supported") is True
        and protective_status.get("protective_take_profit_supported") is True
    )
    test_validated = False
    live_available = False
    ready_for_entry = bool(protective_plan.get("available") is True and env_allows and test_validated and live_available)
    return {
        "transport_mode": mode,
        "dry_run": bool(dry_run),
        "final_confirmation": bool(final_confirmation),
        "protective_orders_enabled": bool(protective_status.get("protective_orders_enabled")),
        "protective_order_mode": protective_status.get("protective_order_mode") or "PREVIEW_ONLY",
        "protective_env_allows": env_allows,
        "test_order_required_before_live": True,
        "test_order_validated_for_signal": test_validated,
        "live_protective_submit_available": live_available,
        "protective_ready_for_live_entry": ready_for_entry,
        "entry_allowed_without_protective": False,
        "naked_entry_blocked": True,
    }


def _blockers(*, protective_plan: dict[str, Any], protective_gate: dict[str, Any]) -> list[str]:
    blockers = [str(item) for item in protective_plan.get("blockers") or []]
    if protective_gate.get("protective_env_allows") is not True:
        blockers.append("protective env is not live-capable")
    if protective_gate.get("test_order_validated_for_signal") is not True:
        blockers.append("exact-signal test-order validation is missing")
    if protective_gate.get("live_protective_submit_available") is not True:
        blockers.append("live protective submit adapter is not enabled")
    if protective_gate.get("protective_ready_for_live_entry") is not True:
        blockers.append("protective path is not ready for live entry")
    blockers.append("no naked entry allowed")
    return list(dict.fromkeys(item for item in blockers if item))


def _status(*, protective_plan: dict[str, Any], protective_gate: dict[str, Any], blockers: list[str]) -> str:
    if protective_gate.get("protective_ready_for_live_entry") is True:
        return "READY_FOR_DRY_RUN_PROTECTIVE_TEST"
    if protective_plan.get("available") is True:
        return "PROTECTIVE_PLAN_READY"
    if protective_plan.get("stop_loss_payload_preview") is not None or protective_plan.get("take_profit_payload_preview") is not None:
        return "PROTECTIVE_PLAN_PARTIAL"
    return "NOT_READY" if blockers else "BLOCKED"


def _operator_action(*, protective_plan: dict[str, Any], protective_gate: dict[str, Any]) -> str:
    if protective_plan.get("available") is not True:
        return "verify protective payloads"
    if protective_gate.get("test_order_validated_for_signal") is not True:
        return "require test-order"
    if protective_gate.get("protective_env_allows") is not True:
        return "keep blocked"
    return "keep no naked entry"


def _record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "first_live_protective_adapter_check",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "profile": payload.get("profile"),
        "entry_context": payload.get("entry_context"),
        "protective_plan": payload.get("protective_plan"),
        "protective_gate": payload.get("protective_gate"),
        "sanitized_payloads": payload.get("sanitized_payloads"),
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
        "profile",
        "entry_context",
        "protective_plan",
        "protective_gate",
        "sanitized_payloads",
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


def _normalize_transport_mode(value: str | None) -> str:
    mode = str(value or DEFAULT_TRANSPORT_MODE).strip().upper()
    return mode if mode in TRANSPORT_MODES else mode


def _sanitize_nested(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("secret", "token", "api_key", "apikey", "signature", "auth", "query_string")):
                continue
            sanitized[key] = _sanitize_nested(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_nested(item) for item in value]
    return value


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any, default: float) -> float:
    parsed = _float_or_none(value)
    return default if parsed is None else parsed


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)
