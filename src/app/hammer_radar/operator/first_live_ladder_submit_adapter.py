"""R62 gated first-live ladder submit adapter path.

This module constructs and gates the first-live ladder entry submit path for the
R58 profile. It is preview/check only: no orders, signatures, env edits, or
Binance network calls are performed.
"""

from __future__ import annotations

import json
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
from src.app.hammer_radar.operator.first_live_readiness import build_first_live_readiness_status
from src.app.hammer_radar.operator.first_microscopic_live_attempt import (
    FALLBACK_BTCUSDT_ENTRY,
    FIRST_LIVE_ENTRY_MODE,
    FIRST_LIVE_LEVERAGE,
    FIRST_LIVE_MARGIN_MODE,
    FIRST_LIVE_MARGIN_USDT,
    FIRST_LIVE_MAX_NOTIONAL_USDT,
    FIRST_LIVE_ONE_ATTEMPT_ONLY,
    FIRST_LIVE_PROTECTIVE_REQUIRED,
    FIRST_LIVE_SYMBOL,
    build_first_microscopic_live_profile,
    first_microscopic_live_attempts_path,
)
from src.app.hammer_radar.operator.live_arming_checklist import build_live_arming_status
from src.app.hammer_radar.operator.live_begins import build_live_begins_status
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview
from src.app.hammer_radar.operator.live_executor_transport import check_live_executor_transport

PHASE = "R62"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "FIRST_LIVE_LADDER_SUBMIT_ADAPTER_ONLY"
CHECKS_FILENAME = "first_live_ladder_submit_checks.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

TRANSPORT_MODES = {"MOCK", "DRY_RUN", "LIVE_CHECK", "LIVE"}
DEFAULT_TRANSPORT_MODE = "DRY_RUN"


def build_first_live_ladder_submit_status(
    *,
    executor_rehearsal_id: str | None = None,
    execution_intent_id: str | None = None,
    signal_id: str | None = None,
    transport_mode: str | None = None,
    final_confirmation: bool = False,
    dry_run: bool = True,
    profile: Mapping[str, Any] | None = None,
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
        request_profile=profile,
        log_dir=log_dir,
        env=env,
        persist=False,
    )


def evaluate_and_record_first_live_ladder_submit_check(
    *,
    executor_rehearsal_id: str | None = None,
    execution_intent_id: str | None = None,
    signal_id: str | None = None,
    transport_mode: str | None = None,
    final_confirmation: bool = False,
    dry_run: bool = True,
    profile: Mapping[str, Any] | None = None,
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
        request_profile=profile,
        log_dir=log_dir,
        env=env,
        persist=True,
    )


def list_first_live_ladder_submit_checks(
    *,
    limit: int = 20,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_first_live_ladder_submit_checks(
        limit=limit,
        status=status,
        log_dir=get_log_dir(log_dir, use_env=True),
    )
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


def load_first_live_ladder_submit_checks(
    *,
    limit: int = 50,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_ladder_submit_checks_path(get_log_dir(log_dir, use_env=True))
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


def first_live_ladder_submit_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHECKS_FILENAME


def append_first_live_ladder_submit_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_ladder_submit_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_first_live_ladder_submit_operator_message(payload: dict[str, Any], *, section: str = "check") -> str:
    profile = payload.get("profile") or {}
    plan = payload.get("ladder_submit_plan") or {}
    gate = payload.get("submit_gate") or {}
    payloads = payload.get("sanitized_payloads") or {}
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:6]) if blockers else "none"
    lines = [
        f"R62 first-live ladder {section}: {payload.get('status')}",
        (
            "R58 profile: "
            f"{profile.get('margin_usdt')} USDT margin, {profile.get('leverage')}x, "
            f"{profile.get('margin_mode')}, {profile.get('entry_mode')}, cap {profile.get('max_notional_usdt')}"
        ),
    ]
    if section in {"check", "plan"}:
        lines.append(
            "ladder plan: "
            f"available={plan.get('available')} aggregate_only={plan.get('aggregate_preview_only')} "
            f"quantity={plan.get('quantity')} quantity_valid={plan.get('quantity_valid')} "
            f"total_margin_cap={plan.get('margin_total_cap_usdt')} planned_notional={plan.get('planned_notional_usdt')}"
        )
    if section in {"check", "payload"}:
        lines.append(
            "payload preview: "
            f"aggregate_present={payloads.get('aggregate_entry_payload') is not None} "
            f"signed_payload_created={payloads.get('signed_payload_created')} secrets_shown={payloads.get('secrets_shown')}"
        )
    if section == "check":
        lines.append(
            "submit gate: "
            f"protective_ready={gate.get('protective_ready')} funds_ready={gate.get('funds_ready')} "
            f"live_env_allows={gate.get('live_env_allows')} live_submit_allowed={gate.get('live_submit_allowed')}"
        )
    lines.extend(
        [
            "LADDER_SUBMIT_ADAPTER_ONLY. No order placed. real_order_placed=false.",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )
    return "\n".join(lines)


def format_first_live_ladder_submit_checks_operator_message(payload: dict[str, Any]) -> str:
    checks = payload.get("checks") or []
    detail = "none"
    if checks:
        detail = "; ".join(f"{item.get('created_at')} {item.get('status')}" for item in checks[:5])
    return "\n".join(
        [
            "R62 first-live ladder submit checks",
            "LADDER_SUBMIT_ADAPTER_ONLY list. No order placed.",
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
    request_profile: Mapping[str, Any] | None,
    log_dir: str | Path | None,
    env: Mapping[str, str] | None,
    persist: bool,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC).isoformat()
    mode = _normalize_transport_mode(transport_mode)
    r58 = build_first_microscopic_live_profile(log_dir=resolved_log_dir, env=source)
    readiness = build_first_live_readiness_status(log_dir=resolved_log_dir, env=source)
    connector = build_connector_status(env=source, log_dir=resolved_log_dir)
    protective = build_protective_status(env=source, log_dir=resolved_log_dir)
    preview = build_live_execution_preview(log_dir=resolved_log_dir, env=source)
    profile = _profile(r58.get("profile") or {}, request_profile)
    ladder_plan = _ladder_submit_plan(profile=profile, preview=preview)
    gate_statuses = _gate_statuses(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        transport_mode=mode,
        log_dir=resolved_log_dir,
        env=source,
        r58=r58,
        readiness=readiness,
    )
    submit_gate = _submit_gate(
        mode=mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        connector=connector,
        protective=protective,
        readiness=readiness,
        gate_statuses=gate_statuses,
        ladder_plan=ladder_plan,
        signal_id=signal_id,
        rehearsal_id=executor_rehearsal_id,
        log_dir=resolved_log_dir,
    )
    payloads = _sanitized_payloads(ladder_plan=ladder_plan)
    blockers = _blockers(ladder_plan=ladder_plan, submit_gate=submit_gate)
    status = _status(ladder_plan=ladder_plan, submit_gate=submit_gate, blockers=blockers)
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
        "ladder_submit_plan": ladder_plan,
        "submit_gate": submit_gate,
        "sanitized_payloads": payloads,
        "blockers": blockers,
        "operator_action": _operator_action(ladder_plan=ladder_plan, submit_gate=submit_gate),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "first_live_ladder_submit_checks_path": str(first_live_ladder_submit_checks_path(resolved_log_dir)),
    }
    if persist:
        record = _record(payload)
        append_first_live_ladder_submit_check(record, log_dir=resolved_log_dir)
        payload["check_id"] = record["check_id"]
    return payload


def _profile(source: Mapping[str, Any], override: Mapping[str, Any] | None) -> dict[str, Any]:
    profile = {
        "symbol": str(source.get("symbol") or FIRST_LIVE_SYMBOL),
        "margin_usdt": _float(source.get("margin_usdt"), FIRST_LIVE_MARGIN_USDT),
        "leverage": int(_float(source.get("leverage"), float(FIRST_LIVE_LEVERAGE))),
        "max_notional_usdt": _float(source.get("max_notional_usdt"), FIRST_LIVE_MAX_NOTIONAL_USDT),
        "margin_mode": str(source.get("margin_mode") or FIRST_LIVE_MARGIN_MODE).upper(),
        "entry_mode": str(source.get("entry_mode") or FIRST_LIVE_ENTRY_MODE).upper(),
        "protective_orders_required": bool(source.get("protective_orders_required", FIRST_LIVE_PROTECTIVE_REQUIRED)),
        "one_attempt_only": bool(source.get("one_attempt_only", FIRST_LIVE_ONE_ATTEMPT_ONLY)),
    }
    if override:
        for key in ("symbol", "margin_usdt", "leverage", "max_notional_usdt", "margin_mode", "entry_mode"):
            if override.get(key) is not None:
                profile[key] = override[key]
    profile["symbol"] = str(profile["symbol"]).upper()
    profile["margin_usdt"] = float(profile["margin_usdt"])
    profile["leverage"] = int(float(profile["leverage"]))
    profile["max_notional_usdt"] = float(profile["max_notional_usdt"])
    profile["margin_mode"] = str(profile["margin_mode"]).upper()
    profile["entry_mode"] = str(profile["entry_mode"]).upper()
    profile["protective_orders_required"] = FIRST_LIVE_PROTECTIVE_REQUIRED
    profile["one_attempt_only"] = FIRST_LIVE_ONE_ATTEMPT_ONLY
    profile["notional_usdt"] = profile["margin_usdt"] * profile["leverage"]
    return profile


def _ladder_submit_plan(*, profile: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    entry = _float_or_none(preview.get("entry")) or FALLBACK_BTCUSDT_ENTRY
    rules = SYMBOL_RULES.get(profile["symbol"])
    quantity_step = float(rules["step_size"]) if rules else None
    raw_quantity = profile["notional_usdt"] / entry if entry else None
    quantity = _round_to_step(raw_quantity, quantity_step) if raw_quantity is not None and quantity_step else None
    quantity_valid = bool(quantity is not None and quantity > 0)
    profile_ok = _profile_ok(profile)
    margin_cap_ok = profile["margin_usdt"] <= FIRST_LIVE_MARGIN_USDT
    notional_cap_ok = profile["notional_usdt"] <= profile["max_notional_usdt"] <= FIRST_LIVE_MAX_NOTIONAL_USDT
    direction = str(preview.get("direction") or "").lower()
    side = "BUY" if direction in {"long", "buy"} else "SELL" if direction in {"short", "sell"} else None
    aggregate = None
    if quantity_valid:
        aggregate = _sanitize_nested(
            {
                "symbol": profile["symbol"],
                "side": side,
                "type": "MARKET",
                "quantity": quantity,
                "margin_mode": profile["margin_mode"],
                "leverage": profile["leverage"],
                "notional_usdt": profile["notional_usdt"],
                "max_notional_usdt": profile["max_notional_usdt"],
                "reduceOnly": False,
                "newClientOrderId": f"r62-preview-{uuid4().hex[:12]}",
                "preview_only": True,
                "aggregate_preview_only": True,
            }
        )
    blockers: list[str] = []
    if not profile_ok:
        blockers.append("profile does not match required BTCUSDT 44/10/444 ISOLATED LADDER first-live profile")
    if profile["symbol"] != FIRST_LIVE_SYMBOL:
        blockers.append("first-live ladder submit supports BTCUSDT only")
    if profile["margin_mode"] != FIRST_LIVE_MARGIN_MODE:
        blockers.append("first-live ladder submit requires ISOLATED margin mode")
    if profile["entry_mode"] != FIRST_LIVE_ENTRY_MODE:
        blockers.append("first-live ladder submit requires LADDER entry mode")
    if not margin_cap_ok:
        blockers.append("planned ladder margin exceeds 44 USDT total margin cap")
    if not notional_cap_ok:
        blockers.append("planned ladder notional exceeds 444 USDT total notional cap")
    if not quantity_valid:
        blockers.append("aggregate ladder quantity is invalid under local BTCUSDT filters")
    blockers.append("ladder child-order generation is not implemented; aggregate preview only")
    return {
        "available": False,
        "plan_id": None,
        "symbol": profile["symbol"],
        "side": side,
        "margin_total_cap_usdt": FIRST_LIVE_MARGIN_USDT,
        "notional_total_cap_usdt": FIRST_LIVE_MAX_NOTIONAL_USDT,
        "planned_margin_usdt": profile["margin_usdt"],
        "planned_notional_usdt": profile["notional_usdt"],
        "quantity": quantity,
        "quantity_valid": quantity_valid,
        "entry": entry,
        "quantity_step": quantity_step,
        "ladder_steps_generated": False,
        "aggregate_preview_only": True,
        "entry_payloads_preview": [],
        "aggregate_entry_payload_preview": aggregate,
        "uses_total_margin_cap": True,
        "per_step_margin_violation": False,
        "notional_cap_ok": notional_cap_ok,
        "margin_cap_ok": margin_cap_ok,
        "profile_ok": profile_ok,
        "no_retry_loop": True,
        "no_averaging_beyond_planned_ladder": True,
        "blockers": list(dict.fromkeys(blockers)),
    }


def _gate_statuses(
    *,
    executor_rehearsal_id: str | None,
    execution_intent_id: str | None,
    signal_id: str | None,
    final_confirmation: bool,
    dry_run: bool,
    transport_mode: str,
    log_dir: Path,
    env: Mapping[str, str],
    r58: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    live_begins = build_live_begins_status(log_dir=log_dir, env=env)
    preview = build_live_execution_preview(log_dir=log_dir, env=env)
    arming = build_live_arming_status(log_dir=log_dir, env=env)
    gate = build_first_live_execution_gate(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=log_dir,
        env=env,
    )
    transport = check_live_executor_transport(
        executor_rehearsal_id=executor_rehearsal_id,
        execution_intent_id=execution_intent_id,
        signal_id=signal_id,
        transport_mode=transport_mode,
        final_confirmation=final_confirmation,
        dry_run=dry_run,
        log_dir=log_dir,
        env=env,
    )
    return {
        "live_begins_status": live_begins.get("status") or "UNKNOWN",
        "preview_status": preview.get("status") or "UNKNOWN",
        "intent_status": gate.get("intent_status") or "MISSING",
        "rehearsal_status": gate.get("rehearsal_status") or "MISSING",
        "arming_status": arming.get("status") or gate.get("arming_status") or "UNKNOWN",
        "first_live_gate_status": gate.get("status") or "UNKNOWN",
        "transport_status": transport.get("status") or "UNKNOWN",
        "r58_status": r58.get("status") or "UNKNOWN",
        "r59_status": readiness.get("status") or "UNKNOWN",
        "r61_status": "ADAPTERS_PARTIAL",
    }


def _submit_gate(
    *,
    mode: str,
    final_confirmation: bool,
    dry_run: bool,
    connector: dict[str, Any],
    protective: dict[str, Any],
    readiness: dict[str, Any],
    gate_statuses: dict[str, Any],
    ladder_plan: dict[str, Any],
    signal_id: str | None,
    rehearsal_id: str | None,
    log_dir: Path,
) -> dict[str, Any]:
    live_env_allows = (
        connector.get("live_execution_enabled") is True
        and connector.get("binance_live_enabled") is True
        and connector.get("allow_live_orders") is True
        and connector.get("global_kill_switch") is False
        and connector.get("connector_mode") == LIVE_ORDER_ENABLED
    )
    protective_ready = _protective_ready(protective)
    funds_status = readiness.get("funds_status") if isinstance(readiness.get("funds_status"), dict) else {}
    funds_ready = funds_status.get("has_required_margin") is True
    r59_allows = readiness.get("status") in {"READY_FOR_MANUAL_ENV_ARMING", "READY_FOR_R58_LIVE_SUBMIT_TEST"}
    r61_allows = False
    idempotency_clear = _idempotency_clear(signal_id=signal_id, rehearsal_id=rehearsal_id, log_dir=log_dir)
    one_attempt_only_clear = idempotency_clear
    network_gate_open = (
        mode == "LIVE"
        and dry_run is False
        and final_confirmation is True
        and live_env_allows
        and protective_ready
        and funds_ready
        and idempotency_clear
        and ladder_plan.get("available") is True
        and _r50_to_r56_allows(gate_statuses)
        and gate_statuses.get("r58_status") == "PROFILE_READY"
        and r59_allows
        and r61_allows
    )
    return {
        "transport_mode": mode,
        "dry_run": bool(dry_run),
        "final_confirmation": bool(final_confirmation),
        "r50_allows": gate_statuses.get("live_begins_status") == "ELIGIBLE_TINY_LIVE",
        "r51_allows": gate_statuses.get("preview_status") == "PREVIEW_READY",
        "r52_allows": gate_statuses.get("intent_status") == "INTENT_READY",
        "r53_allows": gate_statuses.get("rehearsal_status") == "REHEARSAL_READY",
        "r54_allows": gate_statuses.get("arming_status") == "ARMING_ALLOWED",
        "r55_allows": gate_statuses.get("first_live_gate_status") == "EXECUTION_GATE_READY",
        "r56_allows": gate_statuses.get("transport_status") in {"LIVE_READY", "TRANSPORT_READY"},
        "r58_allows": gate_statuses.get("r58_status") == "PROFILE_READY",
        "r59_allows": r59_allows,
        "r61_allows": r61_allows,
        "protective_ready": protective_ready,
        "funds_ready": funds_ready,
        "live_env_allows": live_env_allows,
        "idempotency_clear": idempotency_clear,
        "one_attempt_only_clear": one_attempt_only_clear,
        "network_gate_open": network_gate_open,
        "live_submit_allowed": False,
    }


def _sanitized_payloads(*, ladder_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "aggregate_entry_payload": _sanitize_nested(ladder_plan.get("aggregate_entry_payload_preview")),
        "entry_payloads": _sanitize_nested(ladder_plan.get("entry_payloads_preview") or []),
        "signed_payload_created": False,
        "secrets_shown": SECRETS_SHOWN,
    }


def _blockers(*, ladder_plan: dict[str, Any], submit_gate: dict[str, Any]) -> list[str]:
    blockers: list[str] = [str(item) for item in ladder_plan.get("blockers") or []]
    if submit_gate.get("r50_allows") is not True:
        blockers.append("R50 live-begins gate is not allowing first-live ladder submit")
    if submit_gate.get("r51_allows") is not True:
        blockers.append("R51 preview gate is not ready")
    if submit_gate.get("r52_allows") is not True:
        blockers.append("R52 exact execution intent is missing or not ready")
    if submit_gate.get("r53_allows") is not True:
        blockers.append("R53 executor rehearsal is missing or not ready")
    if submit_gate.get("r54_allows") is not True:
        blockers.append("R54 arming checklist is not allowing live")
    if submit_gate.get("r55_allows") is not True:
        blockers.append("R55 first execution gate is not ready")
    if submit_gate.get("r56_allows") is not True:
        blockers.append("R56 transport is not live-ready")
    if submit_gate.get("r58_allows") is not True:
        blockers.append("R58 first microscopic live profile is not ready")
    if submit_gate.get("r59_allows") is not True:
        blockers.append("R59/R60 first-live readiness is not ready")
    if submit_gate.get("r61_allows") is not True:
        blockers.append("R61 adapter verification is not fully ready")
    if submit_gate.get("protective_ready") is not True:
        blockers.append("protective adapter not ready; no naked entry allowed")
    if submit_gate.get("funds_ready") is not True:
        blockers.append("funds readiness is not confirmed")
    if submit_gate.get("live_env_allows") is not True:
        blockers.append("live env flags do not allow live orders")
    if submit_gate.get("one_attempt_only_clear") is not True:
        blockers.append("one-attempt-only idempotency is not clear")
    if submit_gate.get("network_gate_open") is not True:
        blockers.append("network gate is closed")
    return list(dict.fromkeys(item for item in blockers if item))


def _status(*, ladder_plan: dict[str, Any], submit_gate: dict[str, Any], blockers: list[str]) -> str:
    if not ladder_plan.get("profile_ok") or not ladder_plan.get("margin_cap_ok") or not ladder_plan.get("notional_cap_ok"):
        return "BLOCKED"
    if not ladder_plan.get("quantity_valid"):
        return "NOT_READY"
    if submit_gate.get("network_gate_open") is True:
        return "LIVE_BLOCKED"
    if ladder_plan.get("aggregate_preview_only") is True:
        return "LADDER_ADAPTER_PARTIAL"
    if blockers:
        return "LADDER_PLAN_READY"
    return "READY_FOR_DRY_RUN_LADDER_TEST"


def _operator_action(*, ladder_plan: dict[str, Any], submit_gate: dict[str, Any]) -> str:
    if submit_gate.get("protective_ready") is not True:
        return "verify protective adapter"
    if ladder_plan.get("aggregate_preview_only") is True:
        return "run dry-run ladder test"
    if submit_gate.get("r52_allows") is not True or submit_gate.get("r53_allows") is not True:
        return "create exact chain"
    return "keep blocked"


def _record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "first_live_ladder_submit_adapter_check",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "profile": payload.get("profile"),
        "ladder_submit_plan": payload.get("ladder_submit_plan"),
        "submit_gate": payload.get("submit_gate"),
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
        "ladder_submit_plan",
        "submit_gate",
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


def _protective_ready(protective: dict[str, Any]) -> bool:
    return (
        protective.get("protective_orders_required") is True
        and protective.get("protective_orders_enabled") is True
        and protective.get("protective_order_mode") == LIVE_PROTECTIVE_ENABLED
        and protective.get("protective_orders_supported") is True
        and protective.get("protective_stop_supported") is True
        and protective.get("protective_take_profit_supported") is True
    )


def _r50_to_r56_allows(gate_statuses: dict[str, Any]) -> bool:
    return (
        gate_statuses.get("live_begins_status") == "ELIGIBLE_TINY_LIVE"
        and gate_statuses.get("preview_status") == "PREVIEW_READY"
        and gate_statuses.get("intent_status") == "INTENT_READY"
        and gate_statuses.get("rehearsal_status") == "REHEARSAL_READY"
        and gate_statuses.get("arming_status") == "ARMING_ALLOWED"
        and gate_statuses.get("first_live_gate_status") == "EXECUTION_GATE_READY"
        and gate_statuses.get("transport_status") in {"LIVE_READY", "TRANSPORT_READY"}
    )


def _idempotency_clear(*, signal_id: str | None, rehearsal_id: str | None, log_dir: Path) -> bool:
    if not (signal_id or rehearsal_id):
        return True
    path = first_microscopic_live_attempts_path(log_dir)
    if not path.exists():
        return True
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
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


def _profile_ok(profile: dict[str, Any]) -> bool:
    return (
        profile.get("symbol") == FIRST_LIVE_SYMBOL
        and profile.get("margin_usdt") == FIRST_LIVE_MARGIN_USDT
        and profile.get("leverage") == FIRST_LIVE_LEVERAGE
        and profile.get("max_notional_usdt") == FIRST_LIVE_MAX_NOTIONAL_USDT
        and profile.get("margin_mode") == FIRST_LIVE_MARGIN_MODE
        and profile.get("entry_mode") == FIRST_LIVE_ENTRY_MODE
        and profile.get("protective_orders_required") is True
        and profile.get("one_attempt_only") is True
    )


def _normalize_transport_mode(value: str | None) -> str:
    mode = str(value or DEFAULT_TRANSPORT_MODE).strip().upper()
    return mode if mode in TRANSPORT_MODES else mode


def _round_to_step(value: float | None, step: float | None) -> float | None:
    if value is None or step in (None, 0):
        return None
    value_decimal = Decimal(str(value))
    step_decimal = Decimal(str(step))
    return float((value_decimal / step_decimal).to_integral_value(rounding=ROUND_DOWN) * step_decimal)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any, default: float) -> float:
    parsed = _float_or_none(value)
    return default if parsed is None else parsed


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
