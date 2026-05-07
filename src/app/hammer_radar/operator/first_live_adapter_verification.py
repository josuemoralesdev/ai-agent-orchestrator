"""R61 first-live ladder and protective adapter verification.

This module verifies the R58 first-live ladder entry and protective order submit
shape without placing orders, signing requests, editing env files, or calling
Binance. It is adapter verification only.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution import binance_futures_connector as connector_module
from src.app.hammer_radar.execution.binance_futures_connector import build_connector_status, build_protective_status
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_readiness import build_first_live_readiness_status
from src.app.hammer_radar.operator.first_live_ladder_submit_adapter import build_first_live_ladder_submit_status
from src.app.hammer_radar.operator.first_live_protective_adapter import build_first_live_protective_status
from src.app.hammer_radar.operator.first_microscopic_live_attempt import build_first_microscopic_live_profile
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview

PHASE = "R61"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "FIRST_LIVE_ADAPTER_VERIFICATION_ONLY"
CHECKS_FILENAME = "first_live_adapter_checks.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False


def build_first_live_adapter_status(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate(log_dir=log_dir, env=env, persist=False)


def evaluate_and_record_first_live_adapter_check(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate(log_dir=log_dir, env=env, persist=True)


def list_first_live_adapter_checks(
    *,
    limit: int = 20,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_first_live_adapter_checks(limit=limit, status=status, log_dir=get_log_dir(log_dir, use_env=True))
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


def load_first_live_adapter_checks(
    *,
    limit: int = 50,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_adapter_checks_path(get_log_dir(log_dir, use_env=True))
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


def first_live_adapter_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHECKS_FILENAME


def append_first_live_adapter_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_adapter_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_first_live_adapter_operator_message(payload: dict[str, Any], *, section: str = "adapter") -> str:
    profile = payload.get("profile") or {}
    ladder = payload.get("ladder_adapter_status") or {}
    protective = payload.get("protective_adapter_status") or {}
    naked = payload.get("no_naked_entry_status") or {}
    test_order = payload.get("test_order_status") or {}
    live = payload.get("live_submit_status") or {}
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:6]) if blockers else "none"
    lines = [
        f"R61 first-live {section}: {payload.get('status')}",
        (
            "R58 profile: "
            f"{profile.get('margin_usdt')} USDT margin, {profile.get('leverage')}x, "
            f"{profile.get('margin_mode')}, {profile.get('entry_mode')}, cap {profile.get('max_notional_usdt')}"
        ),
    ]
    if section in {"adapter", "ladder"}:
        lines.append(
            "ladder: "
            f"available={ladder.get('available')} total_margin_cap={ladder.get('margin_total_cap_usdt')} "
            f"notional_cap={ladder.get('notional_total_cap_usdt')} per_step_violation={ladder.get('per_step_margin_violation')}"
        )
    if section in {"adapter", "protective"}:
        lines.append(
            "protective: "
            f"available={protective.get('available')} stop={protective.get('stop_loss_available')} "
            f"take_profit={protective.get('take_profit_available')} reduce_only_ok={protective.get('reduce_only_ok')}"
        )
    if section in {"adapter", "no_naked_entry"}:
        lines.append(
            "no naked entry: "
            f"blocked={naked.get('naked_entry_blocked')} entry_without_protective={naked.get('entry_allowed_without_protective')}"
        )
    if section == "adapter":
        lines.append(
            "test/live: "
            f"test_order_path={test_order.get('test_order_path_available')} "
            f"test_validated={test_order.get('test_order_validated_for_signal')} "
            f"live_ladder={live.get('live_ladder_submit_available')} live_protective={live.get('live_protective_submit_available')}"
        )
    lines.extend(
        [
            "ADAPTER_VERIFICATION_ONLY. No order placed. real_order_placed=false.",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )
    return "\n".join(lines)


def format_first_live_adapter_checks_operator_message(payload: dict[str, Any]) -> str:
    checks = payload.get("checks") or []
    detail = "none"
    if checks:
        detail = "; ".join(f"{item.get('created_at')} {item.get('status')}" for item in checks[:5])
    return "\n".join(
        [
            "R61 first-live adapter checks",
            "ADAPTER_VERIFICATION_ONLY list. No order placed.",
            f"count: {payload.get('count', 0)}",
            f"checks: {detail}",
            "order_placed=false real_order_placed=false secrets_shown=false",
        ]
    )


def _evaluate(*, log_dir: str | Path | None, env: Mapping[str, str] | None, persist: bool) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC).isoformat()
    r58 = build_first_microscopic_live_profile(log_dir=resolved_log_dir, env=source)
    profile = _profile(r58.get("profile") or {})
    preview = build_live_execution_preview(log_dir=resolved_log_dir, env=source)
    connector = build_connector_status(env=source, log_dir=resolved_log_dir)
    protective = build_protective_status(env=source, log_dir=resolved_log_dir)
    readiness = build_first_live_readiness_status(log_dir=resolved_log_dir, env=source)
    ladder_submit = build_first_live_ladder_submit_status(log_dir=resolved_log_dir, env=source)
    protective_adapter = build_first_live_protective_status(log_dir=resolved_log_dir, env=source)
    ladder_status = _ladder_adapter_status(profile=profile, preview=preview, ladder_submit=ladder_submit)
    protective_status = _protective_adapter_status(
        profile=profile,
        preview=preview,
        protective=protective,
        protective_adapter=protective_adapter,
    )
    no_naked_entry = _no_naked_entry_status(protective_status=protective_status)
    test_order = _test_order_status(connector=connector)
    live_submit = _live_submit_status(protective_status=protective_status)
    gate_statuses = {
        "r58": str(r58.get("status") or "UNKNOWN"),
        "r59": str(readiness.get("status") or "UNKNOWN"),
        "caps_ok": bool((readiness.get("cap_status") or {}).get("first_live_cap_semantics_ok")),
    }
    env_status = _env_status(connector=connector, protective=protective)
    blockers = _blockers(
        ladder_status=ladder_status,
        protective_status=protective_status,
        no_naked_entry=no_naked_entry,
        test_order=test_order,
        live_submit=live_submit,
        gate_statuses=gate_statuses,
    )
    status = _status(
        ladder_status=ladder_status,
        protective_status=protective_status,
        test_order=test_order,
        live_submit=live_submit,
        gate_statuses=gate_statuses,
        blockers=blockers,
    )
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
        "ladder_adapter_status": ladder_status,
        "protective_adapter_status": protective_status,
        "no_naked_entry_status": no_naked_entry,
        "test_order_status": test_order,
        "live_submit_status": live_submit,
        "gate_statuses": gate_statuses,
        "env_status": env_status,
        "manual_next_steps": _manual_next_steps(),
        "blockers": blockers,
        "operator_action": _operator_action(
            ladder_status=ladder_status,
            protective_status=protective_status,
            test_order=test_order,
            live_submit=live_submit,
            gate_statuses=gate_statuses,
        ),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "first_live_adapter_checks_path": str(first_live_adapter_checks_path(resolved_log_dir)),
    }
    if persist:
        record = _record(payload)
        append_first_live_adapter_check(record, log_dir=resolved_log_dir)
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


def _ladder_adapter_status(*, profile: dict[str, Any], preview: dict[str, Any], ladder_submit: dict[str, Any] | None = None) -> dict[str, Any]:
    submit_plan = (ladder_submit or {}).get("ladder_submit_plan") if isinstance(ladder_submit, dict) else {}
    aggregate = _aggregate_entry_preview(profile=profile, preview=preview)
    if isinstance(submit_plan, dict) and submit_plan.get("aggregate_entry_payload_preview") is not None:
        aggregate = _sanitize_nested(submit_plan.get("aggregate_entry_payload_preview"))
        aggregate["margin_usdt_total"] = submit_plan.get("planned_margin_usdt")
        aggregate["notional_usdt_total"] = submit_plan.get("planned_notional_usdt")
    blockers = ["live ladder submit adapter not implemented"]
    if isinstance(submit_plan, dict):
        blockers.extend(str(item) for item in submit_plan.get("blockers") or [])
    if profile["entry_mode"] != "LADDER":
        blockers.append("first-live entry_mode must be LADDER")
    if profile["margin_usdt"] > 44.0:
        blockers.append("ladder total margin exceeds 44 USDT")
    if profile["notional_usdt"] > profile["max_notional_usdt"]:
        blockers.append("ladder total notional exceeds max cap")
    aggregate_only = bool((submit_plan or {}).get("aggregate_preview_only", True))
    child_orders_available = bool((submit_plan or {}).get("ladder_steps_generated") is True and (submit_plan or {}).get("available") is True)
    return {
        "available": bool(child_orders_available),
        "mode": "LADDER",
        "margin_total_cap_usdt": 44.0,
        "notional_total_cap_usdt": 444.0,
        "entry_payloads_preview": [],
        "aggregate_entry_payload_preview": aggregate,
        "uses_total_margin_cap": True,
        "per_step_margin_violation": False,
        "ladder_submit_plan_available": isinstance(submit_plan, dict) and submit_plan.get("quantity_valid") is True,
        "ladder_child_orders_available": child_orders_available,
        "aggregate_preview_only": aggregate_only,
        "blockers": list(dict.fromkeys(blockers)),
    }


def _aggregate_entry_preview(*, profile: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    direction = str(preview.get("direction") or "long").lower()
    return _sanitize_nested(
        {
            "symbol": profile["symbol"],
            "side": "BUY" if direction != "short" else "SELL",
            "position_side": "LONG" if direction != "short" else "SHORT",
            "margin_mode": profile["margin_mode"],
            "entry_mode": profile["entry_mode"],
            "margin_usdt_total": profile["margin_usdt"],
            "notional_usdt_total": profile["notional_usdt"],
            "max_notional_usdt": profile["max_notional_usdt"],
            "reduce_only": False,
            "preview_only": True,
            "ladder_aggregate_only": True,
        }
    )


def _protective_adapter_status(
    *,
    profile: dict[str, Any],
    preview: dict[str, Any],
    protective: dict[str, Any],
    protective_adapter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    r63_plan = (protective_adapter or {}).get("protective_plan") if isinstance(protective_adapter, dict) else {}
    r63_gate = (protective_adapter or {}).get("protective_gate") if isinstance(protective_adapter, dict) else {}
    protective_preview = preview.get("protective_orders_preview") if isinstance(preview.get("protective_orders_preview"), dict) else {}
    stop = protective_preview.get("stop_loss") if isinstance(protective_preview, dict) else None
    take_profit = protective_preview.get("take_profit") if isinstance(protective_preview, dict) else None
    stop_preview = _sanitize_nested(stop) if isinstance(stop, dict) else None
    take_profit_preview = _sanitize_nested(take_profit) if isinstance(take_profit, dict) else None
    if isinstance(r63_plan, dict):
        stop_preview = _sanitize_nested(r63_plan.get("stop_loss_payload_preview")) or stop_preview
        take_profit_preview = _sanitize_nested(r63_plan.get("take_profit_payload_preview")) or take_profit_preview
    stop_reduce = bool((stop_preview or {}).get("reduce_only") is True)
    take_profit_reduce = bool((take_profit_preview or {}).get("reduce_only") is True)
    if isinstance(r63_plan, dict) and (r63_plan.get("stop_loss_payload_preview") or r63_plan.get("take_profit_payload_preview")):
        stop_reduce = bool(r63_plan.get("stop_loss_reduce_only_ok"))
        take_profit_reduce = bool(r63_plan.get("take_profit_reduce_only_ok"))
    reduce_only_ok = stop_reduce and take_profit_reduce
    if isinstance(r63_plan, dict) and (r63_plan.get("stop_loss_payload_preview") or r63_plan.get("take_profit_payload_preview")):
        close_or_quantity_ok = bool(r63_plan.get("close_position_or_quantity_ok"))
    else:
        close_or_quantity_ok = reduce_only_ok and bool(stop_preview and take_profit_preview)
    available = (
        protective.get("protective_orders_enabled") is True
        and protective.get("protective_order_mode") == "LIVE_PROTECTIVE_ENABLED"
        and protective.get("protective_stop_supported") is True
        and protective.get("protective_take_profit_supported") is True
        and reduce_only_ok
        and bool((r63_gate or {}).get("protective_ready_for_live_entry")) is True
    )
    blockers = []
    if profile["protective_orders_required"] is not True:
        blockers.append("protective orders must be required")
    if stop_preview is None:
        blockers.append("protective stop-loss payload preview is missing")
    if take_profit_preview is None:
        blockers.append("protective take-profit payload preview is missing")
    if not reduce_only_ok:
        blockers.append("protective stop-loss and take-profit must be reduce_only")
    if protective.get("protective_order_mode") != "LIVE_PROTECTIVE_ENABLED":
        blockers.append("protective live adapter not armed/verified")
    if isinstance(r63_plan, dict):
        blockers.extend(str(item) for item in r63_plan.get("blockers") or [])
    if not available:
        blockers.append("protective live adapter unavailable")
    return {
        "available": available,
        "protective_orders_required": True,
        "stop_loss_available": stop_preview is not None,
        "take_profit_available": take_profit_preview is not None,
        "stop_loss_payload_preview": stop_preview,
        "take_profit_payload_preview": take_profit_preview,
        "reduce_only_required": True,
        "reduce_only_ok": reduce_only_ok,
        "close_position_or_quantity_ok": close_or_quantity_ok,
        "protective_plan_available": bool((r63_plan or {}).get("available")),
        "protective_ready_for_live_entry": bool((r63_gate or {}).get("protective_ready_for_live_entry")),
        "blockers": list(dict.fromkeys(blockers)),
    }


def _no_naked_entry_status(*, protective_status: dict[str, Any]) -> dict[str, Any]:
    blockers = []
    if protective_status.get("available") is not True:
        blockers.append("entry remains blocked until protective stop-loss and take-profit path is verified")
    return {
        "naked_entry_blocked": True,
        "entry_requires_protective_ready": True,
        "entry_allowed_without_protective": False,
        "blockers": blockers,
    }


def _test_order_status(*, connector: dict[str, Any]) -> dict[str, Any]:
    test_order_available = hasattr(connector_module, "BinanceFuturesHttpClient") and hasattr(connector_module, "submit_test_order")
    network_enabled = bool(connector.get("test_order_network_enabled"))
    return {
        "test_order_path_available": bool(test_order_available),
        "test_order_network_enabled": network_enabled,
        "test_order_required_before_live": True,
        "test_order_validated_for_signal": False,
        "blockers": ["test-order validation for exact signal is missing"],
    }


def _live_submit_status(*, protective_status: dict[str, Any]) -> dict[str, Any]:
    live_class_exists = hasattr(connector_module, "BinanceFuturesLiveHttpClient")
    protective_class_exists = hasattr(connector_module, "BinanceFuturesProtectiveHttpClient")
    blockers = [
        "live ladder submit adapter is not wired to R58",
        "live submit adapter is not verified for R61",
    ]
    if protective_status.get("available") is not True:
        blockers.append("live protective submit adapter is not verified")
    return {
        "live_submit_available": False,
        "live_ladder_submit_available": False,
        "live_protective_submit_available": False,
        "live_adapter_available": False,
        "live_submit_not_implemented": True,
        "live_submit_class_exists": bool(live_class_exists),
        "protective_submit_class_exists": bool(protective_class_exists),
        "blockers": blockers,
    }


def _env_status(*, connector: dict[str, Any], protective: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector_mode": connector.get("connector_mode") or "DRY_RUN_ONLY",
        "live_execution_enabled": bool(connector.get("live_execution_enabled")),
        "binance_live_enabled": bool(connector.get("binance_live_enabled")),
        "allow_live_orders": bool(connector.get("allow_live_orders")),
        "global_kill_switch": bool(connector.get("global_kill_switch")),
        "protective_orders_enabled": bool(protective.get("protective_orders_enabled")),
        "protective_order_mode": protective.get("protective_order_mode") or "PREVIEW_ONLY",
    }


def _blockers(
    *,
    ladder_status: dict[str, Any],
    protective_status: dict[str, Any],
    no_naked_entry: dict[str, Any],
    test_order: dict[str, Any],
    live_submit: dict[str, Any],
    gate_statuses: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    for status in (ladder_status, protective_status, no_naked_entry, test_order, live_submit):
        blockers.extend(str(item) for item in status.get("blockers") or [])
    if gate_statuses.get("r58") != "PROFILE_READY":
        blockers.append(f"R58 is {gate_statuses.get('r58', 'UNKNOWN')}")
    if gate_statuses.get("caps_ok") is not True:
        blockers.append("R59/R60 first-live cap semantics are not ready")
    return list(dict.fromkeys(item for item in blockers if item))


def _status(
    *,
    ladder_status: dict[str, Any],
    protective_status: dict[str, Any],
    test_order: dict[str, Any],
    live_submit: dict[str, Any],
    gate_statuses: dict[str, Any],
    blockers: list[str],
) -> str:
    if gate_statuses.get("r58") != "PROFILE_READY" or gate_statuses.get("caps_ok") is not True:
        return "BLOCKED"
    if ladder_status.get("available") and protective_status.get("available") and test_order.get("test_order_path_available"):
        return "READY_FOR_DRY_RUN_ADAPTER_TEST"
    if protective_status.get("available") or test_order.get("test_order_path_available"):
        return "ADAPTERS_PARTIAL"
    if live_submit.get("live_submit_not_implemented"):
        return "NOT_READY"
    return "BLOCKED" if blockers else "READY_FOR_MANUAL_ENV_ARMING"


def _operator_action(
    *,
    ladder_status: dict[str, Any],
    protective_status: dict[str, Any],
    test_order: dict[str, Any],
    live_submit: dict[str, Any],
    gate_statuses: dict[str, Any],
) -> str:
    if protective_status.get("available") is not True:
        return "verify protective adapter"
    if ladder_status.get("available") is not True:
        return "implement live ladder submit"
    if test_order.get("test_order_validated_for_signal") is not True:
        return "run test-order"
    if live_submit.get("live_adapter_available") is not True:
        return "keep blocked"
    if gate_statuses.get("r59") != "READY_FOR_MANUAL_ENV_ARMING":
        return "keep blocked"
    return "keep blocked"


def _manual_next_steps() -> list[dict[str, Any]]:
    return [
        {"step": 1, "action": "verify protective stop-loss and take-profit payloads", "automated": False},
        {"step": 2, "action": "implement first-live ladder submit adapter behind R50-R60 gates", "automated": False},
        {"step": 3, "action": "validate exact-signal test-order without live order placement", "automated": False},
        {"step": 4, "action": "keep live env blocked until funds, adapter, and exact chain are ready", "automated": False},
    ]


def _record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "first_live_adapter_verification",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "profile": payload.get("profile"),
        "ladder_adapter_status": payload.get("ladder_adapter_status"),
        "protective_adapter_status": payload.get("protective_adapter_status"),
        "no_naked_entry_status": payload.get("no_naked_entry_status"),
        "test_order_status": payload.get("test_order_status"),
        "live_submit_status": payload.get("live_submit_status"),
        "env_status": payload.get("env_status"),
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
        "ladder_adapter_status",
        "protective_adapter_status",
        "no_naked_entry_status",
        "test_order_status",
        "live_submit_status",
        "env_status",
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


def _sanitize_nested(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("secret", "token", "api_key", "apikey", "signature", "auth")):
                continue
            sanitized[key] = _sanitize_nested(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_nested(item) for item in value]
    return value


def _float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
