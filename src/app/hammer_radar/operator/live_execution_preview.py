"""R51 protected tiny-live execution preview for Hammer Radar.

This module builds a deterministic, sanitized order plan from local candidate
and gate state only. It never places orders, signs payloads, enables live
trading, or calls Binance.
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

from src.app.hammer_radar.execution.binance_futures_connector import build_protective_status
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.exchange_dry_run import SYMBOL_RULES
from src.app.hammer_radar.operator.inspect import LiveCandidateCheck, build_live_candidate_snapshot
from src.app.hammer_radar.operator.live_begins import build_live_begins_status
from src.app.hammer_radar.operator.trade_ticket import load_trade_ticket_records

PHASE = "R51"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "PREVIEW_ONLY"
LIVE_EXECUTION_PREVIEWS_FILENAME = "live_execution_previews.ndjson"

ENV_PREVIEW_MARGIN_USDT = "HAMMER_TINY_LIVE_PREVIEW_MARGIN_USDT"
ENV_PREVIEW_LEVERAGE = "HAMMER_TINY_LIVE_PREVIEW_LEVERAGE"
DEFAULT_MARGIN_USDT = 4.44
DEFAULT_LEVERAGE = 1.0
DEFAULT_MARGIN_MODE = "ISOLATED"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
WOULD_PLACE_ORDER = False
SECRETS_SHOWN = False


def build_live_execution_preview(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_live_execution_preview(log_dir=log_dir, env=env, persist=False)


def evaluate_and_record_live_execution_preview(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_live_execution_preview(log_dir=log_dir, env=env, persist=True)


def load_live_execution_previews(
    *,
    limit: int = 50,
    event_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = live_execution_previews_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if event_id is not None and record.get("event_id") != event_id:
                continue
            records.append(record)
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def live_execution_previews_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LIVE_EXECUTION_PREVIEWS_FILENAME


def format_live_execution_preview_operator_message(payload: dict[str, Any]) -> str:
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:5]) if blockers else "none"
    return "\n".join(
        [
            f"R51 protected tiny-live preview: {payload.get('status')}",
            "Preview only. No order placed. real_order_placed=false.",
            f"live_begins_status: {payload.get('live_begins_status')}",
            f"signal_id: {payload.get('latest_signal_id') or 'none'}",
            f"symbol/timeframe/direction: {payload.get('symbol') or 'n/a'} / {payload.get('timeframe') or 'n/a'} / {payload.get('direction') or 'n/a'}",
            f"entry/stop/take_profit: {_fmt(payload.get('entry'))} / {_fmt(payload.get('stop'))} / {_fmt(payload.get('take_profit'))}",
            f"margin/leverage/notional/risk: {_fmt(payload.get('margin_usdt'))} / {_fmt(payload.get('leverage'))} / {_fmt(payload.get('notional_usdt'))} / {_fmt(payload.get('risk_usdt'))}",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )


def _evaluate_live_execution_preview(
    *,
    log_dir: str | Path | None,
    env: Mapping[str, str] | None,
    persist: bool,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    live_begins = build_live_begins_status(log_dir=resolved_log_dir, env=source)
    protective = build_protective_status(env=source, log_dir=resolved_log_dir)
    candidate = _latest_candidate(log_dir=resolved_log_dir)
    sizing = _preview_sizing(source)
    mapped = _map_candidate(candidate, sizing=sizing)
    protective_preview = _protective_preview(candidate=candidate, mapped=mapped, protective=protective)
    checks = _checks(
        live_begins=live_begins,
        candidate=candidate,
        mapped=mapped,
        protective=protective,
        protective_preview=protective_preview,
        log_dir=resolved_log_dir,
    )
    blockers = _blockers(
        live_begins=live_begins,
        candidate=candidate,
        mapped=mapped,
        protective=protective,
        checks=checks,
    )
    status = _status(live_begins_status=str(live_begins.get("status") or "UNKNOWN"), checks=checks, blockers=blockers)
    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "created_at": datetime.now(UTC).isoformat(),
        "execution_mode": EXECUTION_MODE,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "would_place_order": WOULD_PLACE_ORDER,
        "live_execution_enabled": bool(live_begins.get("live_execution_enabled")),
        "binance_live_enabled": bool(live_begins.get("binance_live_enabled")),
        "allow_live_orders": bool(live_begins.get("allow_live_orders")),
        "global_kill_switch": bool(live_begins.get("global_kill_switch")),
        "protective_orders_required": bool(protective.get("protective_orders_required")),
        "protective_orders_enabled": bool(protective.get("protective_orders_enabled")),
        "protective_order_mode": protective.get("protective_order_mode") or "PREVIEW_ONLY",
        "live_begins_status": live_begins.get("status") or "UNKNOWN",
        "latest_signal_id": (candidate or {}).get("signal_id"),
        "symbol": (candidate or {}).get("symbol"),
        "timeframe": (candidate or {}).get("timeframe"),
        "direction": (candidate or {}).get("direction"),
        "entry": mapped["entry"],
        "stop": mapped["stop"],
        "take_profit": mapped["take_profit"],
        "position_side": mapped["position_side"],
        "order_side": mapped["order_side"],
        "margin_mode": DEFAULT_MARGIN_MODE,
        "margin_usdt": mapped["margin_usdt"],
        "leverage": mapped["leverage"],
        "notional_usdt": mapped["notional_usdt"],
        "risk_usdt": mapped["risk_usdt"],
        "risk_pct_of_margin": mapped["risk_pct_of_margin"],
        "quantity": mapped["quantity"],
        "quantity_step": mapped["quantity_step"],
        "quantity_is_approximate": mapped["quantity_is_approximate"],
        "min_notional_ok": mapped["min_notional_ok"],
        "protective_orders_preview": protective_preview,
        "checks": checks,
        "blockers": blockers,
        "operator_action": _operator_action(status=status),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "live_execution_previews_path": str(live_execution_previews_path(resolved_log_dir)),
    }
    if persist:
        event = _audit_event(payload)
        append_live_execution_preview_event(event, log_dir=resolved_log_dir)
        payload["audit_event_id"] = event["event_id"]
    return payload


def append_live_execution_preview_event(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = live_execution_previews_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _latest_candidate(*, log_dir: Path) -> dict[str, Any] | None:
    snapshot = build_live_candidate_snapshot(
        limit=1000,
        since_hours=24,
        min_score=0,
        symbol=None,
        allow_short=True,
        allow_oversold=True,
        allow_trigger_flags=True,
        max_risk_usd=5.0,
        max_leverage=3.0,
        max_position_usd=44.0,
        fresh_minutes=30,
        allow_expired=True,
        latest_only=False,
        log_dir=log_dir,
    )
    checks = list(snapshot.get("checks") or [])
    if not checks:
        return None
    checks.sort(key=lambda check: check.candidate.signal.timestamp, reverse=True)
    return _candidate_snapshot(checks[0])


def _candidate_snapshot(check: LiveCandidateCheck) -> dict[str, Any]:
    signal = check.candidate.signal
    return {
        "signal_id": signal.signal_id,
        "timestamp": signal.timestamp,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "direction": signal.direction,
        "entry": check.entry,
        "stop": check.stop,
        "take_profit": check.take_profit,
        "freshness_status": "stale" if check.freshness_status == "expired" else check.freshness_status,
    }


def _preview_sizing(source: Mapping[str, str]) -> dict[str, float]:
    return {
        "margin_usdt": _env_float(source, ENV_PREVIEW_MARGIN_USDT, DEFAULT_MARGIN_USDT),
        "leverage": _env_float(source, ENV_PREVIEW_LEVERAGE, DEFAULT_LEVERAGE),
    }


def _map_candidate(candidate: dict[str, Any] | None, *, sizing: dict[str, float]) -> dict[str, Any]:
    direction = str((candidate or {}).get("direction") or "").lower()
    entry = _float_or_none((candidate or {}).get("entry"))
    stop = _float_or_none((candidate or {}).get("stop"))
    take_profit = _float_or_none((candidate or {}).get("take_profit"))
    margin_usdt = sizing["margin_usdt"]
    leverage = sizing["leverage"]
    notional_usdt = margin_usdt * leverage if margin_usdt is not None and leverage is not None else None
    quantity = (notional_usdt / entry) if notional_usdt is not None and entry not in (None, 0.0) else None
    rules = SYMBOL_RULES.get(str((candidate or {}).get("symbol") or ""))
    quantity_step = float(rules["step_size"]) if rules else None
    quantity_rounded = _round_to_step(quantity, quantity_step) if quantity is not None and quantity_step is not None else None
    risk_per_unit = _risk_per_unit(direction=direction, entry=entry, stop=stop)
    risk_usdt = (risk_per_unit * quantity_rounded) if risk_per_unit is not None and quantity_rounded is not None else None
    risk_pct = (risk_usdt / margin_usdt * 100.0) if risk_usdt is not None and margin_usdt not in (None, 0.0) else None
    min_notional = float(rules["min_notional_usd"]) if rules else None
    return {
        "entry": entry,
        "stop": stop,
        "take_profit": take_profit,
        "position_side": _position_side(direction),
        "order_side": _order_side(direction),
        "margin_usdt": margin_usdt,
        "leverage": leverage,
        "notional_usdt": notional_usdt,
        "risk_per_unit": risk_per_unit,
        "risk_usdt": risk_usdt,
        "risk_pct_of_margin": risk_pct,
        "quantity": quantity_rounded,
        "quantity_step": quantity_step,
        "quantity_is_approximate": quantity_rounded is not None,
        "min_notional_ok": bool(min_notional is not None and notional_usdt is not None and notional_usdt >= min_notional),
        "rules_available": rules is not None,
    }


def _protective_preview(
    *,
    candidate: dict[str, Any] | None,
    mapped: dict[str, Any],
    protective: dict[str, Any],
) -> dict[str, Any]:
    close_side = _close_side(str((candidate or {}).get("direction") or "").lower())
    risk_valid = mapped.get("risk_per_unit") is not None and mapped.get("risk_per_unit") > 0
    ready = risk_valid and _protective_ready(protective)
    return {
        "stop_loss": _protective_leg(
            leg_type="STOP_LOSS",
            side=close_side,
            trigger_price=mapped.get("stop"),
            position_side=mapped.get("position_side"),
            quantity=mapped.get("quantity"),
        )
        if mapped.get("stop") is not None
        else None,
        "take_profit": _protective_leg(
            leg_type="TAKE_PROFIT",
            side=close_side,
            trigger_price=mapped.get("take_profit"),
            position_side=mapped.get("position_side"),
            quantity=mapped.get("quantity"),
        )
        if mapped.get("take_profit") is not None
        else None,
        "reduce_only": True,
        "close_position": False,
        "status": "READY" if ready else "BLOCKED",
    }


def _protective_leg(
    *,
    leg_type: str,
    side: str | None,
    trigger_price: float | None,
    position_side: str | None,
    quantity: float | None,
) -> dict[str, Any]:
    return {
        "type": leg_type,
        "side": side,
        "position_side": position_side,
        "trigger_price": trigger_price,
        "quantity": quantity,
        "reduce_only": True,
        "close_position": False,
        "preview_only": True,
    }


def _checks(
    *,
    live_begins: dict[str, Any],
    candidate: dict[str, Any] | None,
    mapped: dict[str, Any],
    protective: dict[str, Any],
    protective_preview: dict[str, Any],
    log_dir: Path,
) -> dict[str, bool]:
    return {
        "live_begins_allows_preview": live_begins.get("status") in {"READY_FOR_OPERATOR_APPROVAL", "ELIGIBLE_TINY_LIVE"},
        "candidate_present": candidate is not None,
        "candidate_fresh": (candidate or {}).get("freshness_status") == "fresh",
        "signal_complete": _signal_complete(candidate),
        "entry_present": mapped.get("entry") is not None,
        "stop_present": mapped.get("stop") is not None,
        "take_profit_present": mapped.get("take_profit") is not None,
        "risk_valid": mapped.get("risk_per_unit") is not None and mapped.get("risk_per_unit") > 0,
        "margin_valid": mapped.get("margin_usdt") is not None and mapped.get("margin_usdt") > 0,
        "leverage_valid": mapped.get("leverage") is not None and 0 < mapped.get("leverage") <= 3,
        "quantity_valid": mapped.get("quantity") is not None and mapped.get("quantity") > 0 and mapped.get("min_notional_ok") is True,
        "protective_orders_ready": protective_preview.get("status") == "READY",
        "idempotency_clear": _idempotency_clear(candidate=candidate, log_dir=log_dir),
    }


def _blockers(
    *,
    live_begins: dict[str, Any],
    candidate: dict[str, Any] | None,
    mapped: dict[str, Any],
    protective: dict[str, Any],
    checks: dict[str, bool],
) -> list[str]:
    blockers: list[str] = []
    live_begins_status = str(live_begins.get("status") or "UNKNOWN")
    if live_begins_status in {"BLOCKED", "NOT_READY", "UNKNOWN"}:
        blockers.append(f"live begins is {live_begins_status}")
    if candidate is None:
        blockers.append("candidate missing")
    elif (candidate or {}).get("freshness_status") != "fresh":
        blockers.append("candidate stale")
    if not checks["signal_complete"]:
        blockers.append("signal incomplete")
    if not checks["entry_present"]:
        blockers.append("entry is missing")
    if not checks["stop_present"]:
        blockers.append("stop is missing")
    if not checks["take_profit_present"]:
        blockers.append("take_profit is missing")
    if not checks["risk_valid"]:
        blockers.append("risk is invalid")
    if not checks["margin_valid"]:
        blockers.append("margin_usdt is invalid")
    if not checks["leverage_valid"]:
        blockers.append("leverage is invalid")
    if not mapped.get("rules_available"):
        blockers.append("exchange filters unavailable for symbol")
    if not mapped.get("min_notional_ok"):
        blockers.append("notional is below min_notional or unavailable")
    if not checks["quantity_valid"]:
        blockers.append("quantity is invalid")
    if protective.get("protective_orders_required") is True and not _protective_ready(protective):
        blockers.append("protective orders are required but not ready/enabled")
    if not checks["idempotency_clear"]:
        blockers.append("idempotency is not clear for signal")
    return list(dict.fromkeys(blocker for blocker in blockers if blocker))


def _status(*, live_begins_status: str, checks: dict[str, bool], blockers: list[str]) -> str:
    if not checks["candidate_present"]:
        return "NOT_READY"
    if live_begins_status in {"BLOCKED", "NOT_READY", "UNKNOWN"}:
        return "BLOCKED"
    if not blockers:
        return "PREVIEW_READY"
    return "BLOCKED"


def _operator_action(*, status: str) -> str:
    if status == "PREVIEW_READY":
        return "review preview / approve exact signal later"
    if status == "NOT_READY":
        return "wait"
    return "keep blocked"


def _signal_complete(candidate: dict[str, Any] | None) -> bool:
    if candidate is None:
        return False
    required = ("signal_id", "symbol", "timeframe", "direction", "entry", "stop", "take_profit")
    return all(candidate.get(field) not in (None, "") for field in required)


def _protective_ready(protective: dict[str, Any]) -> bool:
    if protective.get("protective_orders_required") is not True:
        return True
    return (
        protective.get("protective_orders_enabled") is True
        and protective.get("protective_order_mode") in {"PREVIEW_ONLY", "TEST_ONLY", "LIVE_PROTECTIVE_ENABLED"}
    )


def _idempotency_clear(*, candidate: dict[str, Any] | None, log_dir: Path) -> bool:
    signal_id = (candidate or {}).get("signal_id")
    if not signal_id:
        return False
    records = load_trade_ticket_records(limit=0, log_dir=log_dir)
    for record in records:
        ticket = record.get("ticket") or {}
        if ticket.get("signal_id") == signal_id and record.get("action") in {"execute_live_order", "live_order"}:
            return False
    return True


def _audit_event(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "phase": PHASE,
        "event_type": "live_execution_preview",
        "status": payload.get("status"),
        "signal_id": payload.get("latest_signal_id"),
        "symbol": payload.get("symbol"),
        "timeframe": payload.get("timeframe"),
        "direction": payload.get("direction"),
        "margin_usdt": payload.get("margin_usdt"),
        "leverage": payload.get("leverage"),
        "notional_usdt": payload.get("notional_usdt"),
        "risk_usdt": payload.get("risk_usdt"),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "secrets_shown": SECRETS_SHOWN,
        "blockers": list(payload.get("blockers") or []),
    }


def _risk_per_unit(*, direction: str, entry: float | None, stop: float | None) -> float | None:
    if entry is None or stop is None or entry <= 0 or stop <= 0:
        return None
    if direction == "long":
        value = entry - stop
    elif direction == "short":
        value = stop - entry
    else:
        return None
    return value if value > 0 else None


def _order_side(direction: str) -> str | None:
    if direction == "long":
        return "BUY"
    if direction == "short":
        return "SELL"
    return None


def _close_side(direction: str) -> str | None:
    if direction == "long":
        return "SELL"
    if direction == "short":
        return "BUY"
    return None


def _position_side(direction: str) -> str | None:
    if direction == "long":
        return "LONG"
    if direction == "short":
        return "SHORT"
    return None


def _round_to_step(value: float | None, step: float | None) -> float | None:
    if value is None or step in (None, 0.0):
        return None
    decimal_value = Decimal(str(value))
    decimal_step = Decimal(str(step))
    return float((decimal_value / decimal_step).to_integral_value(rounding=ROUND_DOWN) * decimal_step)


def _env_float(source: Mapping[str, str], key: str, default: float) -> float:
    value = str(source.get(key) or "").strip()
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: object) -> str:
    return "n/a" if value is None else str(value)
