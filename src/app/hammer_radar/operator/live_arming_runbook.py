"""R57 live arming runbook and blocker resolver for Hammer Radar.

This module composes R50-R56 into a sanitized operator runbook. It classifies
blockers, resolves local sizing/filter gaps, and produces manual steps only. It
never edits env files, enables live trading, places orders, or calls Binance.
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

from src.app.hammer_radar.execution.binance_futures_connector import build_connector_status, build_protective_status
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.exchange_dry_run import SYMBOL_RULES
from src.app.hammer_radar.operator.first_live_execution_gate import build_first_live_execution_gate
from src.app.hammer_radar.operator.live_arming_checklist import build_live_arming_status
from src.app.hammer_radar.operator.live_begins import build_live_begins_status
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview
from src.app.hammer_radar.operator.live_executor_transport import check_live_executor_transport

PHASE = "R57"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "RUNBOOK_ONLY"
RUNBOOKS_FILENAME = "live_arming_runbooks.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
WOULD_PLACE_ORDER = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

ENV_TELEGRAM_BOT_TOKEN = "TELEGRAM_BOT_TOKEN"
CATEGORIES = (
    "env",
    "signal",
    "preview",
    "approval",
    "intent",
    "rehearsal",
    "arming",
    "gate",
    "transport",
    "sizing",
    "protective_orders",
    "idempotency",
)


def build_live_arming_runbook(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_runbook(log_dir=log_dir, env=env, persist=False)


def evaluate_and_record_live_arming_runbook(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_runbook(log_dir=log_dir, env=env, persist=True)


def list_live_arming_runbooks(
    *,
    limit: int = 20,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_live_arming_runbooks(limit=limit, status=status, log_dir=get_log_dir(log_dir, use_env=True))
    return {
        "result_status": "ACCEPTED",
        "phase": PHASE,
        "count": len(records),
        "runbooks": records,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "secrets_shown": SECRETS_SHOWN,
    }


def load_live_arming_runbooks(
    *,
    limit: int = 50,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = live_arming_runbooks_path(get_log_dir(log_dir, use_env=True))
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
            records.append(_sanitize_runbook_record(record))
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def live_arming_runbooks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / RUNBOOKS_FILENAME


def append_live_arming_runbook(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = live_arming_runbooks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_live_arming_runbook_operator_message(payload: dict[str, Any]) -> str:
    summary = payload.get("blocker_summary") or {}
    categories = summary.get("categories") or {}
    blockers = []
    for values in categories.values():
        blockers.extend(values)
    blocker_text = "; ".join(str(item) for item in blockers[:5]) if blockers else "none"
    sizing = payload.get("sizing_status") or {}
    return "\n".join(
        [
            f"R57 live arming runbook: {payload.get('status')}",
            "RUNBOOK_ONLY. No order placed. real_order_placed=false.",
            f"blocker_count: {summary.get('count', 0)}",
            f"top_blockers: {blocker_text}",
            f"env_edit_required: {_env_edit_required(categories)} restart_required_after_manual_env_edit: {_env_edit_required(categories)}",
            f"tiny_sizing_valid: {bool(sizing.get('min_notional_ok') and sizing.get('quantity_valid'))}",
            f"signal_chain_complete: {_signal_chain_complete(payload)}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )


def format_live_blockers_operator_message(payload: dict[str, Any]) -> str:
    summary = payload.get("blocker_summary") or {}
    categories = summary.get("categories") or {}
    lines = [
        f"R57 live blockers: {summary.get('count', 0)}",
        "RUNBOOK_ONLY. No order placed.",
    ]
    for category in CATEGORIES:
        values = categories.get(category) or []
        if values:
            lines.append(f"{category}: {'; '.join(str(item) for item in values[:3])}")
    lines.append(f"next operator action: {payload.get('operator_action')}")
    return "\n".join(lines)


def format_live_arming_runbooks_operator_message(payload: dict[str, Any]) -> str:
    records = payload.get("runbooks") or []
    detail = "none"
    if records:
        detail = "; ".join(f"{item.get('created_at')} {item.get('status')} {item.get('latest_signal_id') or 'none'}" for item in records[:5])
    return "\n".join(
        [
            "R57 live arming runbooks",
            "RUNBOOK_ONLY list. No order placed.",
            f"count: {payload.get('count', 0)}",
            f"runbooks: {detail}",
        ]
    )


def _evaluate_runbook(*, log_dir: str | Path | None, env: Mapping[str, str] | None, persist: bool) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC)
    connector = build_connector_status(env=source, log_dir=resolved_log_dir)
    protective = build_protective_status(env=source, log_dir=resolved_log_dir)
    live_begins = build_live_begins_status(log_dir=resolved_log_dir, env=source)
    preview = build_live_execution_preview(log_dir=resolved_log_dir, env=source)
    arming = build_live_arming_status(log_dir=resolved_log_dir, env=source)
    first_gate = build_first_live_execution_gate(signal_id=preview.get("latest_signal_id"), log_dir=resolved_log_dir, env=source)
    transport = check_live_executor_transport(signal_id=preview.get("latest_signal_id"), log_dir=resolved_log_dir, env=source)
    env_status = _env_status(connector=connector, protective=protective, source=source)
    sizing_status = _sizing_status(preview)
    blocker_summary = _blocker_summary(
        live_begins=live_begins,
        preview=preview,
        arming=arming,
        first_gate=first_gate,
        transport=transport,
        env_status=env_status,
        sizing_status=sizing_status,
    )
    status = _status(blocker_summary=blocker_summary, live_begins=live_begins)
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
        "latest_signal_id": preview.get("latest_signal_id") or live_begins.get("latest_signal_id"),
        "live_begins_status": live_begins.get("status") or "UNKNOWN",
        "preview_status": preview.get("status") or "UNKNOWN",
        "intent_status": arming.get("intent_status") or first_gate.get("intent_status") or "UNKNOWN",
        "rehearsal_status": arming.get("rehearsal_status") or first_gate.get("rehearsal_status") or "UNKNOWN",
        "arming_status": arming.get("status") or "UNKNOWN",
        "first_live_gate_status": first_gate.get("status") or "UNKNOWN",
        "transport_status": transport.get("status") or "UNKNOWN",
        "env_status": env_status,
        "sizing_status": sizing_status,
        "blocker_summary": blocker_summary,
        "manual_runbook": _manual_runbook(),
        "operator_action": _operator_action(blocker_summary=blocker_summary, sizing_status=sizing_status),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "live_arming_runbooks_path": str(live_arming_runbooks_path(resolved_log_dir)),
    }
    if persist:
        record = _runbook_record(payload)
        append_live_arming_runbook(record, log_dir=resolved_log_dir)
        payload["runbook_check_id"] = record["runbook_check_id"]
    return payload


def _env_status(*, connector: dict[str, Any], protective: dict[str, Any], source: Mapping[str, str]) -> dict[str, Any]:
    return {
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
    }


def _sizing_status(preview: dict[str, Any]) -> dict[str, Any]:
    symbol = str(preview.get("symbol") or "BTCUSDT")
    rules = SYMBOL_RULES.get(symbol)
    entry = _float_or_none(preview.get("entry"))
    margin = _float_or_none(preview.get("margin_usdt"))
    leverage = _float_or_none(preview.get("leverage"))
    notional = (margin * leverage) if margin is not None and leverage is not None else _float_or_none(preview.get("notional_usdt"))
    raw_quantity = (notional / entry) if notional is not None and entry not in (None, 0.0) else None
    quantity_step = float(rules["step_size"]) if rules else _float_or_none(preview.get("quantity_step"))
    rounded_quantity = _round_to_step(raw_quantity, quantity_step) if raw_quantity is not None and quantity_step else _float_or_none(preview.get("quantity"))
    min_notional = float(rules["min_notional_usd"]) if rules else None
    min_notional_ok = bool(min_notional is not None and notional is not None and notional >= min_notional)
    quantity_valid = bool(rounded_quantity is not None and rounded_quantity > 0)
    suggested_margin = _ceil_to_cent(min_notional / leverage) if min_notional is not None and leverage not in (None, 0.0) else None
    suggested_leverage = math.ceil(min_notional / margin) if min_notional is not None and margin not in (None, 0.0) else None
    if min_notional is None:
        action = "unknown"
    elif not min_notional_ok or not quantity_valid:
        action = "increase_margin_or_leverage"
    elif not preview.get("latest_signal_id"):
        action = "wait"
    else:
        action = "wait"
    return {
        "symbol": symbol,
        "entry": entry,
        "margin_usdt": margin,
        "leverage": leverage,
        "notional_usdt": notional,
        "quantity": rounded_quantity,
        "quantity_step": quantity_step,
        "min_notional": min_notional,
        "min_notional_ok": min_notional_ok,
        "quantity_valid": quantity_valid,
        "suggested_min_margin_usdt": suggested_margin,
        "suggested_min_leverage": suggested_leverage,
        "sizing_action": action,
    }


def _blocker_summary(
    *,
    live_begins: dict[str, Any],
    preview: dict[str, Any],
    arming: dict[str, Any],
    first_gate: dict[str, Any],
    transport: dict[str, Any],
    env_status: dict[str, Any],
    sizing_status: dict[str, Any],
) -> dict[str, Any]:
    categories: dict[str, list[str]] = {category: [] for category in CATEGORIES}
    for payload in (live_begins, preview, arming, first_gate, transport):
        for blocker in payload.get("blockers") or []:
            _add_blocker(categories, str(blocker))
    _env_blockers(categories, env_status)
    _sizing_blockers(categories, sizing_status)
    if live_begins.get("approval_status") == "MISSING":
        categories["approval"].append("operator approval missing")
    if arming.get("intent_status") in {"MISSING", "EXPIRED", "UNKNOWN"}:
        categories["intent"].append(f"execution intent is {arming.get('intent_status', 'UNKNOWN')}")
    if arming.get("rehearsal_status") in {"MISSING", "EXPIRED", "UNKNOWN"}:
        categories["rehearsal"].append(f"executor rehearsal is {arming.get('rehearsal_status', 'UNKNOWN')}")
    for category, values in categories.items():
        categories[category] = list(dict.fromkeys(value for value in values if value))
    return {
        "count": sum(len(values) for values in categories.values()),
        "categories": categories,
    }


def _add_blocker(categories: dict[str, list[str]], blocker: str) -> None:
    lowered = blocker.lower()
    if "protective" in lowered:
        category = "protective_orders"
    elif any(token in lowered for token in ("notional", "quantity", "margin", "leverage", "filter", "min_")):
        category = "sizing"
    elif "approval" in lowered or "approve" in lowered:
        category = "approval"
    elif "intent" in lowered:
        category = "intent"
    elif "rehearsal" in lowered:
        category = "rehearsal"
    elif "arming" in lowered:
        category = "arming"
    elif "gate" in lowered:
        category = "gate"
    elif "transport" in lowered or "network" in lowered:
        category = "transport"
    elif "idempotency" in lowered:
        category = "idempotency"
    elif any(token in lowered for token in ("env", "kill switch", "connector_mode", "live_enabled", "allow_live_orders", "binance_live", "api key", "api secret")):
        category = "env"
    elif any(token in lowered for token in ("candidate", "signal", "fresh")):
        category = "signal"
    elif "preview" in lowered:
        category = "preview"
    else:
        category = "signal"
    categories[category].append(blocker)


def _env_blockers(categories: dict[str, list[str]], env_status: dict[str, Any]) -> None:
    if not env_status["live_execution_enabled"]:
        categories["env"].append("live_execution_enabled is false")
    if not env_status["binance_live_enabled"]:
        categories["env"].append("HAMMER_BINANCE_LIVE_ENABLED is false")
    if not env_status["allow_live_orders"]:
        categories["env"].append("HAMMER_ALLOW_LIVE_ORDERS is false")
    if env_status["global_kill_switch"]:
        categories["env"].append("global kill switch active")
    if env_status["connector_mode"] != "LIVE_ORDER_ENABLED":
        categories["env"].append(f"connector_mode is {env_status['connector_mode']}")
    if not (env_status["binance_key_present"] and env_status["binance_secret_present"]):
        categories["env"].append("Binance credential presence is incomplete")
    if not env_status["protective_orders_enabled"] or env_status["protective_order_mode"] != "LIVE_PROTECTIVE_ENABLED":
        categories["protective_orders"].append("protective orders required but not live-ready/enabled")


def _sizing_blockers(categories: dict[str, list[str]], sizing: dict[str, Any]) -> None:
    if sizing["min_notional"] is None:
        categories["sizing"].append("min_notional unavailable from local filters")
    elif not sizing["min_notional_ok"]:
        categories["sizing"].append("notional is below min_notional")
    if not sizing["quantity_valid"]:
        categories["sizing"].append("quantity is invalid or rounds to zero at current margin/leverage")


def _manual_runbook() -> list[dict[str, Any]]:
    steps = [
        ("review blockers", "inspect /live/arming/runbook", "safe"),
        ("confirm latest signal", "verify latest signal is fresh and complete before approval", "safe"),
        ("check R50-R56", "run /live/begins/status, /live/execution/preview, /live/arming/status, /live/first-execution/gate, /live/executor/transport/status", "safe"),
        ("fix sizing", "increase HAMMER_TINY_LIVE_PREVIEW_MARGIN_USDT or HAMMER_TINY_LIVE_PREVIEW_LEVERAGE if local BTCUSDT filters fail", "manual"),
        ("manual env edit", "operator may edit env: HAMMER_BINANCE_CONNECTOR_MODE=LIVE_ORDER_ENABLED; HAMMER_BINANCE_LIVE_ENABLED=true; HAMMER_LIVE_EXECUTION_ENABLED=true; HAMMER_ALLOW_LIVE_ORDERS=true; HAMMER_GLOBAL_KILL_SWITCH=false; HAMMER_PROTECTIVE_ORDERS_ENABLED=true; HAMMER_PROTECTIVE_ORDER_MODE=LIVE_PROTECTIVE_ENABLED", "dangerous"),
        ("manual restart", "after manual env edit, operator restarts hammer-approval-api.service manually", "manual"),
        ("recheck arming", "curl /live/arming/status and confirm order_placed=false real_order_placed=false", "safe"),
        ("recheck first gate", "curl /live/first-execution/gate and confirm only explicit final confirmation can pass", "safe"),
        ("recheck transport", "curl /live/executor/transport/status and run mock/dry-run only", "safe"),
        ("approve exact signal", "use exact LIVE APPROVE <signal_id> only if still fresh", "manual"),
        ("create intent", "POST /live/execution/intent with exact signal_id", "safe"),
        ("create rehearsal", "POST /live/executor/rehearsal with exact intent_id", "safe"),
        ("run transport mock dry-run", "run LIVE TRANSPORT MOCK <rehearsal_id> then LIVE TRANSPORT DRY RUN <rehearsal_id>", "safe"),
        ("stop before R58", "only R58 may perform the first microscopic protected live attempt", "dangerous"),
    ]
    return [
        {"step": index, "name": name, "action": action, "automated": False, "danger_level": danger}
        for index, (name, action, danger) in enumerate(steps, start=1)
    ]


def _status(*, blocker_summary: dict[str, Any], live_begins: dict[str, Any]) -> str:
    if not live_begins.get("latest_signal_id") and blocker_summary["count"] > 0:
        return "NOT_READY"
    if blocker_summary["count"] == 0:
        return "RUNBOOK_READY"
    return "BLOCKED"


def _operator_action(*, blocker_summary: dict[str, Any], sizing_status: dict[str, Any]) -> str:
    categories = blocker_summary.get("categories") or {}
    if categories.get("sizing") or sizing_status.get("sizing_action") == "increase_margin_or_leverage":
        return "fix env"
    if categories.get("signal"):
        return "wait for fresh signal"
    if categories.get("approval"):
        return "approve exact signal"
    if categories.get("intent"):
        return "create intent"
    if categories.get("rehearsal"):
        return "rehearse"
    if categories.get("env") or categories.get("protective_orders"):
        return "arm manually"
    return "prepare R58"


def _runbook_record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "runbook_check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "live_arming_runbook",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "latest_signal_id": payload.get("latest_signal_id"),
        "live_begins_status": payload.get("live_begins_status"),
        "preview_status": payload.get("preview_status"),
        "intent_status": payload.get("intent_status"),
        "rehearsal_status": payload.get("rehearsal_status"),
        "arming_status": payload.get("arming_status"),
        "first_live_gate_status": payload.get("first_live_gate_status"),
        "transport_status": payload.get("transport_status"),
        "env_status": payload.get("env_status"),
        "sizing_status": payload.get("sizing_status"),
        "blocker_summary": payload.get("blocker_summary"),
        "operator_action": payload.get("operator_action"),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize_runbook_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "runbook_check_id",
        "phase",
        "event_type",
        "created_at",
        "status",
        "latest_signal_id",
        "live_begins_status",
        "preview_status",
        "intent_status",
        "rehearsal_status",
        "arming_status",
        "first_live_gate_status",
        "transport_status",
        "env_status",
        "sizing_status",
        "blocker_summary",
        "operator_action",
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


def _signal_chain_complete(payload: dict[str, Any]) -> bool:
    return (
        bool(payload.get("latest_signal_id"))
        and payload.get("preview_status") == "PREVIEW_READY"
        and payload.get("intent_status") == "INTENT_READY"
        and payload.get("rehearsal_status") == "REHEARSAL_READY"
    )


def _env_edit_required(categories: dict[str, list[str]]) -> bool:
    return bool(categories.get("env") or categories.get("protective_orders") or categories.get("sizing"))


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_to_step(value: float | None, step: float | None) -> float | None:
    if value is None or step in (None, 0.0):
        return None
    quantized = (Decimal(str(value)) / Decimal(str(step))).to_integral_value(rounding=ROUND_DOWN) * Decimal(str(step))
    return float(quantized)


def _ceil_to_cent(value: float) -> float:
    return math.ceil(value * 100.0) / 100.0
