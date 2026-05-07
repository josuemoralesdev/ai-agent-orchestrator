"""R59 first-live safety caps, funds, and adapter readiness for Hammer Radar.

This module is readiness-only. It reports whether the R58 44 USDT x 10x
isolated ladder profile is aligned with connector caps, env state, funds
checking, protective readiness, and adapter availability. It never places
orders, edits env files, signs payloads, or calls Binance.
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
from src.app.hammer_radar.operator.first_live_execution_gate import build_first_live_execution_gate
from src.app.hammer_radar.operator.first_microscopic_live_attempt import build_first_microscopic_live_profile
from src.app.hammer_radar.operator.live_arming_checklist import build_live_arming_status
from src.app.hammer_radar.operator.live_begins import build_live_begins_status
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview
from src.app.hammer_radar.operator.live_executor_transport import build_live_executor_transport_status

PHASE = "R59"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "FIRST_LIVE_READINESS_ONLY"
CHECKS_FILENAME = "first_live_readiness_checks.ndjson"

ENV_FILES = [
    "/home/josue/.config/hammer-radar/binance-readonly.env",
    "/home/josue/.config/hammer-radar/notifications.env",
]

ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False


def build_first_live_readiness_status(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate(log_dir=log_dir, env=env, persist=False)


def evaluate_and_record_first_live_readiness(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate(log_dir=log_dir, env=env, persist=True)


def list_first_live_readiness_checks(
    *,
    limit: int = 20,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_first_live_readiness_checks(limit=limit, status=status, log_dir=get_log_dir(log_dir, use_env=True))
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


def load_first_live_readiness_checks(
    *,
    limit: int = 50,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_readiness_checks_path(get_log_dir(log_dir, use_env=True))
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


def first_live_readiness_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHECKS_FILENAME


def append_first_live_readiness_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_readiness_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_first_live_readiness_operator_message(payload: dict[str, Any], *, section: str = "readiness") -> str:
    cap_status = payload.get("cap_status") or {}
    funds_status = payload.get("funds_status") or {}
    adapter_status = payload.get("adapter_status") or {}
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:6]) if blockers else "none"
    profile = payload.get("profile") or {}
    lines = [
        f"R59 first-live {section}: {payload.get('status')}",
        (
            "R58 profile: "
            f"{profile.get('margin_usdt')} USDT margin, {profile.get('leverage')}x, "
            f"{profile.get('margin_mode')}, {profile.get('entry_mode')}, cap {profile.get('max_notional_usdt')}"
        ),
    ]
    if section in {"readiness", "caps"}:
        lines.append(
            "caps: "
            f"notional={cap_status.get('profile_notional_usdt')} margin_ok={cap_status.get('first_live_margin_cap_ok')} "
            f"notional_ok={cap_status.get('first_live_notional_cap_ok')} leverage_ok={cap_status.get('first_live_leverage_cap_ok')} "
            f"first_live_aligned={cap_status.get('first_live_cap_semantics_ok')} "
            f"global_legacy_preserved={cap_status.get('legacy_caps_preserved_for_global_live')} "
            f"runtime_conflict={cap_status.get('legacy_connector_runtime_conflict')}"
        )
    if section in {"readiness", "funds"}:
        lines.append(
            "funds: "
            f"checked={funds_status.get('checked')} required_margin={funds_status.get('required_margin_usdt')} "
            f"has_required_margin={funds_status.get('has_required_margin')}"
        )
    if section in {"readiness", "adapter"}:
        lines.append(
            "adapter: "
            f"live_submit={adapter_status.get('live_submit_adapter_available')} "
            f"ladder={adapter_status.get('live_ladder_submit_available')} "
            f"protective={adapter_status.get('protective_live_adapter_available')} "
            f"test_order={adapter_status.get('test_order_available')}"
        )
    lines.extend(
        [
            "READINESS_ONLY. No order placed. real_order_placed=false.",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )
    return "\n".join(lines)


def format_first_live_readiness_checks_operator_message(payload: dict[str, Any]) -> str:
    checks = payload.get("checks") or []
    detail = "none"
    if checks:
        detail = "; ".join(f"{item.get('created_at')} {item.get('status')}" for item in checks[:5])
    return "\n".join(
        [
            "R59 first-live readiness checks",
            "READINESS_ONLY list. No order placed.",
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
    connector = build_connector_status(env=source, log_dir=resolved_log_dir)
    protective = build_protective_status(env=source, log_dir=resolved_log_dir)
    cap_status = _cap_status(profile=profile, connector=connector)
    env_status = _env_status(source=source, connector=connector, protective=protective, profile=profile)
    funds_status = _funds_status(profile=profile)
    adapter_status = _adapter_status(protective=protective)
    gate_statuses = _gate_statuses(log_dir=resolved_log_dir, env=source, r58_status=str(r58.get("status") or "UNKNOWN"))
    manual_env_plan = _manual_env_plan()
    blockers = _blockers(
        cap_status=cap_status,
        env_status=env_status,
        funds_status=funds_status,
        adapter_status=adapter_status,
        gate_statuses=gate_statuses,
    )
    status = _status(
        cap_status=cap_status,
        env_status=env_status,
        funds_status=funds_status,
        adapter_status=adapter_status,
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
        "cap_status": cap_status,
        "env_status": env_status,
        "funds_status": funds_status,
        "adapter_status": adapter_status,
        "gate_statuses": gate_statuses,
        "manual_env_plan": manual_env_plan,
        "blockers": blockers,
        "operator_action": _operator_action(
            cap_status=cap_status,
            env_status=env_status,
            funds_status=funds_status,
            adapter_status=adapter_status,
            gate_statuses=gate_statuses,
        ),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "first_live_readiness_checks_path": str(first_live_readiness_checks_path(resolved_log_dir)),
    }
    if persist:
        record = _record(payload)
        append_first_live_readiness_check(record, log_dir=resolved_log_dir)
        payload["readiness_check_id"] = record["readiness_check_id"]
    return payload


def _profile(source: Mapping[str, Any]) -> dict[str, Any]:
    margin = _float(source.get("margin_usdt"), 44.0)
    leverage = int(_float(source.get("leverage"), 10.0))
    max_notional = _float(source.get("max_notional_usdt"), 444.0)
    return {
        "symbol": str(source.get("symbol") or "BTCUSDT"),
        "margin_usdt": margin,
        "leverage": leverage,
        "max_notional_usdt": max_notional,
        "margin_mode": str(source.get("margin_mode") or "ISOLATED").upper(),
        "entry_mode": str(source.get("entry_mode") or "LADDER").upper(),
        "protective_orders_required": bool(source.get("protective_orders_required", True)),
        "one_attempt_only": bool(source.get("one_attempt_only", True)),
    }


def _cap_status(*, profile: dict[str, Any], connector: dict[str, Any]) -> dict[str, Any]:
    notional = float(profile["margin_usdt"]) * float(profile["leverage"])
    legacy_max_position = _float_or_none(connector.get("configured_max_position_usd"))
    legacy_max_leverage = _float_or_none(connector.get("configured_max_leverage"))
    required_margin_cap = 44.0
    required_max_notional = 444.0
    required_max_leverage = 10
    first_live_margin_cap_ok = float(profile["margin_usdt"]) <= required_margin_cap
    first_live_notional_cap_ok = notional <= required_max_notional
    first_live_leverage_cap_ok = float(profile["leverage"]) <= required_max_leverage
    first_live_profile_shape_ok = (
        profile.get("symbol") == "BTCUSDT"
        and profile.get("margin_mode") == "ISOLATED"
        and profile.get("entry_mode") == "LADDER"
        and profile.get("one_attempt_only") is True
        and profile.get("protective_orders_required") is True
    )
    first_live_cap_semantics_ok = bool(
        first_live_profile_shape_ok
        and first_live_margin_cap_ok
        and first_live_notional_cap_ok
        and first_live_leverage_cap_ok
        and float(profile["margin_usdt"]) == required_margin_cap
        and int(profile["leverage"]) == required_max_leverage
        and float(profile["max_notional_usdt"]) == required_max_notional
    )
    legacy_caps_preserved = legacy_max_position == 44.0 and legacy_max_leverage == 3.0
    legacy_runtime_conflict = _legacy_connector_runtime_conflict(connector=connector, first_live_semantics_ok=first_live_cap_semantics_ok)
    legacy_conflict = not first_live_cap_semantics_ok
    blockers = []
    if not first_live_profile_shape_ok:
        blockers.append("first-live profile must be BTCUSDT ISOLATED LADDER with protective orders and one-attempt-only")
    if not first_live_margin_cap_ok:
        blockers.append("first-live margin exceeds required 44 USDT cap")
    if not first_live_notional_cap_ok:
        blockers.append("first-live notional exceeds required 444 USDT cap")
    if not first_live_leverage_cap_ok:
        blockers.append("first-live leverage exceeds required 10x cap")
    if not first_live_cap_semantics_ok and not blockers:
        blockers.append("first-live cap values must be exactly 44 margin, 10x leverage, and 444 max notional")
    if legacy_runtime_conflict:
        blockers.append("legacy connector live guard still enforces old max position/leverage on first-live path")
    return {
        "profile_notional_usdt": notional,
        "margin_cap_ok": first_live_margin_cap_ok,
        "notional_cap_ok": first_live_notional_cap_ok,
        "leverage_cap_ok": first_live_leverage_cap_ok,
        "legacy_cap_conflict": legacy_conflict,
        "legacy_caps_preserved_for_global_live": legacy_caps_preserved,
        "first_live_cap_semantics_ok": first_live_cap_semantics_ok,
        "first_live_margin_cap_ok": first_live_margin_cap_ok,
        "first_live_notional_cap_ok": first_live_notional_cap_ok,
        "first_live_leverage_cap_ok": first_live_leverage_cap_ok,
        "legacy_connector_runtime_conflict": legacy_runtime_conflict,
        "legacy_max_position_usd": legacy_max_position,
        "legacy_max_leverage": legacy_max_leverage,
        "required_margin_cap_usdt": required_margin_cap,
        "required_max_notional_usdt": required_max_notional,
        "required_max_leverage": required_max_leverage,
        "profile_margin_usdt": float(profile["margin_usdt"]),
        "profile_leverage": int(profile["leverage"]),
        "profile_max_notional_usdt": float(profile["max_notional_usdt"]),
        "profile_symbol": profile.get("symbol"),
        "profile_margin_mode": profile.get("margin_mode"),
        "profile_entry_mode": profile.get("entry_mode"),
        "blockers": blockers,
    }


def _legacy_connector_runtime_conflict(*, connector: dict[str, Any], first_live_semantics_ok: bool) -> bool:
    if not first_live_semantics_ok:
        return False
    blockers = connector.get("blockers") or []
    cap_blockers = {
        "HAMMER_LIVE_MAX_POSITION_USD must remain 44",
        "HAMMER_LIVE_MAX_LEVERAGE must remain 3",
        "HAMMER_LIVE_MAX_POSITION_USD exceeds 44",
        "HAMMER_LIVE_MAX_LEVERAGE exceeds 3",
    }
    return any(str(blocker) in cap_blockers for blocker in blockers)


def _env_status(
    *,
    source: Mapping[str, str],
    connector: dict[str, Any],
    protective: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    return {
        "env_files": list(ENV_FILES),
        "live_execution_enabled": bool(connector.get("live_execution_enabled")),
        "binance_live_enabled": bool(connector.get("binance_live_enabled")),
        "allow_live_orders": bool(connector.get("allow_live_orders")),
        "global_kill_switch": bool(connector.get("global_kill_switch")),
        "connector_mode": connector.get("connector_mode") or "DRY_RUN_ONLY",
        "protective_orders_enabled": bool(protective.get("protective_orders_enabled")),
        "protective_order_mode": protective.get("protective_order_mode") or "PREVIEW_ONLY",
        "first_live_margin_usdt": _float(source.get("HAMMER_FIRST_LIVE_MARGIN_USDT"), float(profile["margin_usdt"])),
        "first_live_leverage": int(_float(source.get("HAMMER_FIRST_LIVE_LEVERAGE"), float(profile["leverage"]))),
        "first_live_max_notional_usdt": _float(source.get("HAMMER_FIRST_LIVE_MAX_NOTIONAL_USDT"), float(profile["max_notional_usdt"])),
        "first_live_margin_mode": str(source.get("HAMMER_FIRST_LIVE_MARGIN_MODE") or profile["margin_mode"]).upper(),
        "first_live_entry_mode": str(source.get("HAMMER_FIRST_LIVE_ENTRY_MODE") or profile["entry_mode"]).upper(),
        "binance_key_present": bool(connector.get("api_key_present")),
        "binance_secret_present": bool(connector.get("api_secret_present")),
    }


def _funds_status(*, profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "checked": False,
        "network_used": False,
        "available_usdt": None,
        "required_margin_usdt": float(profile["margin_usdt"]),
        "has_required_margin": False,
        "blockers": ["funds check not implemented or no funds available"],
    }


def _adapter_status(*, protective: dict[str, Any]) -> dict[str, Any]:
    live_submit_class_exists = hasattr(connector_module, "BinanceFuturesLiveHttpClient")
    protective_class_exists = hasattr(connector_module, "BinanceFuturesProtectiveHttpClient")
    test_order_available = hasattr(connector_module, "BinanceFuturesHttpClient")
    blockers = [
        "R58 live ladder submit adapter is not implemented",
        "live submit adapter is not exposed to R58 readiness path",
    ]
    if not protective.get("protective_orders_enabled") or protective.get("protective_order_mode") != "LIVE_PROTECTIVE_ENABLED":
        blockers.append("protective live adapter is not armed")
    return {
        "live_submit_adapter_available": False,
        "live_ladder_submit_available": False,
        "protective_live_adapter_available": False,
        "test_order_available": bool(test_order_available),
        "live_submit_class_exists": bool(live_submit_class_exists),
        "protective_live_class_exists": bool(protective_class_exists),
        "blockers": blockers,
    }


def _gate_statuses(*, log_dir: Path, env: Mapping[str, str], r58_status: str) -> dict[str, str]:
    live_begins = build_live_begins_status(log_dir=log_dir, env=env)
    preview = build_live_execution_preview(log_dir=log_dir, env=env)
    arming = build_live_arming_status(log_dir=log_dir, env=env)
    first_gate = build_first_live_execution_gate(log_dir=log_dir, env=env)
    transport = build_live_executor_transport_status(log_dir=log_dir, env=env)
    return {
        "r50": str(live_begins.get("status") or "UNKNOWN"),
        "r51": str(preview.get("status") or "UNKNOWN"),
        "r52": str(first_gate.get("intent_status") or arming.get("intent_status") or "MISSING"),
        "r53": str(first_gate.get("rehearsal_status") or arming.get("rehearsal_status") or "MISSING"),
        "r54": str(arming.get("status") or "UNKNOWN"),
        "r55": str(first_gate.get("status") or "UNKNOWN"),
        "r56": str(transport.get("status") or "UNKNOWN"),
        "r58": r58_status,
    }


def _manual_env_plan() -> list[dict[str, Any]]:
    profile_values = {
        "HAMMER_FIRST_LIVE_MARGIN_USDT": "44",
        "HAMMER_FIRST_LIVE_LEVERAGE": "10",
        "HAMMER_FIRST_LIVE_MAX_NOTIONAL_USDT": "444",
        "HAMMER_FIRST_LIVE_MARGIN_MODE": "ISOLATED",
        "HAMMER_FIRST_LIVE_ENTRY_MODE": "LADDER",
        "HAMMER_LIVE_ALLOWED_SYMBOLS": "BTCUSDT",
        "HAMMER_LIVE_MARGIN_MODE": "isolated",
    }
    arming_values = {
        "HAMMER_BINANCE_CONNECTOR_MODE": "LIVE_ORDER_ENABLED",
        "HAMMER_BINANCE_LIVE_ENABLED": "true",
        "HAMMER_LIVE_EXECUTION_ENABLED": "true",
        "HAMMER_ALLOW_LIVE_ORDERS": "true",
        "HAMMER_GLOBAL_KILL_SWITCH": "false",
        "HAMMER_PROTECTIVE_ORDERS_ENABLED": "true",
        "HAMMER_PROTECTIVE_ORDER_MODE": "LIVE_PROTECTIVE_ENABLED",
    }
    rollback_values = {
        "HAMMER_BINANCE_CONNECTOR_MODE": "DRY_RUN_ONLY",
        "HAMMER_LIVE_EXECUTION_ENABLED": "false",
        "HAMMER_ALLOW_LIVE_ORDERS": "false",
        "HAMMER_GLOBAL_KILL_SWITCH": "true",
        "HAMMER_PROTECTIVE_ORDERS_ENABLED": "false",
        "HAMMER_PROTECTIVE_ORDER_MODE": "PREVIEW_ONLY",
    }
    return [
        {
            "group": "profile_caps",
            "file": ENV_FILES[0],
            "action": "manual edit only",
            "danger_level": "safe_profile_alignment",
            "notes": "HAMMER_FIRST_LIVE_* values are first-live scoped; do not reinterpret legacy global max position/leverage as first-live notional caps.",
            "values": profile_values,
        },
        {
            "group": "live_arming",
            "file": ENV_FILES[0],
            "action": "manual edit only after funds, adapter, and exact chain are ready",
            "danger_level": "dangerous",
            "values": arming_values,
        },
        {
            "group": "rollback",
            "file": ENV_FILES[0],
            "action": "manual rollback values",
            "danger_level": "safe_blocking",
            "values": rollback_values,
        },
    ]


def _blockers(
    *,
    cap_status: dict[str, Any],
    env_status: dict[str, Any],
    funds_status: dict[str, Any],
    adapter_status: dict[str, Any],
    gate_statuses: dict[str, str],
) -> list[str]:
    blockers: list[str] = []
    blockers.extend(str(item) for item in cap_status.get("blockers") or [])
    if not env_status["live_execution_enabled"]:
        blockers.append("live_execution_enabled is false")
    if not env_status["binance_live_enabled"]:
        blockers.append("HAMMER_BINANCE_LIVE_ENABLED is false")
    if not env_status["allow_live_orders"]:
        blockers.append("HAMMER_ALLOW_LIVE_ORDERS is false")
    if env_status["global_kill_switch"]:
        blockers.append("global kill switch is active")
    if env_status["connector_mode"] != "LIVE_ORDER_ENABLED":
        blockers.append(f"connector_mode is {env_status['connector_mode']}")
    if not env_status["protective_orders_enabled"] or env_status["protective_order_mode"] != "LIVE_PROTECTIVE_ENABLED":
        blockers.append("protective orders are not live-ready")
    blockers.extend(str(item) for item in funds_status.get("blockers") or [])
    blockers.extend(str(item) for item in adapter_status.get("blockers") or [])
    for phase, ready_value in (
        ("r50", "ELIGIBLE_TINY_LIVE"),
        ("r51", "PREVIEW_READY"),
        ("r52", "INTENT_READY"),
        ("r53", "REHEARSAL_READY"),
        ("r54", "ARMING_ALLOWED"),
        ("r55", "EXECUTION_GATE_READY"),
    ):
        if gate_statuses.get(phase) != ready_value:
            blockers.append(f"{phase.upper()} is {gate_statuses.get(phase, 'UNKNOWN')}")
    if gate_statuses.get("r56") not in {"LIVE_READY", "TRANSPORT_READY"}:
        blockers.append(f"R56 is {gate_statuses.get('r56', 'UNKNOWN')}")
    if gate_statuses.get("r58") != "PROFILE_READY":
        blockers.append(f"R58 is {gate_statuses.get('r58', 'UNKNOWN')}")
    return list(dict.fromkeys(item for item in blockers if item))


def _status(
    *,
    cap_status: dict[str, Any],
    env_status: dict[str, Any],
    funds_status: dict[str, Any],
    adapter_status: dict[str, Any],
    gate_statuses: dict[str, str],
    blockers: list[str],
) -> str:
    caps_ok = cap_status["first_live_cap_semantics_ok"] and not cap_status["legacy_connector_runtime_conflict"]
    env_ready = (
        env_status["live_execution_enabled"]
        and env_status["binance_live_enabled"]
        and env_status["allow_live_orders"]
        and not env_status["global_kill_switch"]
        and env_status["connector_mode"] == "LIVE_ORDER_ENABLED"
        and env_status["protective_orders_enabled"]
        and env_status["protective_order_mode"] == "LIVE_PROTECTIVE_ENABLED"
    )
    chain_ready = all(
        (
            gate_statuses.get("r50") == "ELIGIBLE_TINY_LIVE",
            gate_statuses.get("r51") == "PREVIEW_READY",
            gate_statuses.get("r52") == "INTENT_READY",
            gate_statuses.get("r53") == "REHEARSAL_READY",
            gate_statuses.get("r54") == "ARMING_ALLOWED",
            gate_statuses.get("r55") == "EXECUTION_GATE_READY",
            gate_statuses.get("r56") in {"LIVE_READY", "TRANSPORT_READY"},
            gate_statuses.get("r58") == "PROFILE_READY",
        )
    )
    if not caps_ok:
        return "BLOCKED"
    if not env_ready:
        return "READY_FOR_MANUAL_ENV_ARMING" if cap_status["legacy_cap_conflict"] is False else "BLOCKED"
    if not funds_status["has_required_margin"]:
        return "READY_FOR_FUNDS"
    if not chain_ready:
        return "READY_FOR_CHAIN"
    if adapter_status["live_ladder_submit_available"] and adapter_status["protective_live_adapter_available"]:
        return "READY_FOR_R58_LIVE_SUBMIT_TEST"
    return "NOT_READY" if blockers else "BLOCKED"


def _operator_action(
    *,
    cap_status: dict[str, Any],
    env_status: dict[str, Any],
    funds_status: dict[str, Any],
    adapter_status: dict[str, Any],
    gate_statuses: dict[str, str],
) -> str:
    if cap_status.get("legacy_connector_runtime_conflict"):
        return "fix connector runtime caps"
    if not cap_status.get("first_live_cap_semantics_ok") or cap_status.get("blockers"):
        return "fix caps"
    if not funds_status.get("has_required_margin"):
        return "fund account"
    if adapter_status.get("blockers"):
        return "verify adapter"
    if gate_statuses.get("r52") != "INTENT_READY" or gate_statuses.get("r53") != "REHEARSAL_READY":
        return "create fresh chain"
    if not env_status.get("live_execution_enabled") or env_status.get("global_kill_switch"):
        return "arm env manually"
    return "keep blocked"


def _record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "readiness_check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "first_live_readiness_check",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "profile": payload.get("profile"),
        "cap_status": payload.get("cap_status"),
        "env_status": payload.get("env_status"),
        "funds_status": payload.get("funds_status"),
        "adapter_status": payload.get("adapter_status"),
        "gate_statuses": payload.get("gate_statuses"),
        "manual_env_plan": payload.get("manual_env_plan"),
        "blockers": payload.get("blockers"),
        "operator_action": payload.get("operator_action"),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "readiness_check_id",
        "phase",
        "event_type",
        "created_at",
        "status",
        "profile",
        "cap_status",
        "env_status",
        "funds_status",
        "adapter_status",
        "gate_statuses",
        "manual_env_plan",
        "blockers",
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
    return _sanitize_nested(sanitized)


def _sanitize_nested(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("secret", "token", "api_key", "apikey", "signature")):
                continue
            sanitized[key] = _sanitize_nested(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_nested(item) for item in value]
    return value


def _float(value: Any, default: float) -> float:
    parsed = _float_or_none(value)
    return default if parsed is None else parsed


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
