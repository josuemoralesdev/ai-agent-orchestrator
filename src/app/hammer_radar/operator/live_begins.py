"""R50 live-begins gate for Hammer Radar.

This module composes existing local readiness, candidate, approval, dry-run,
and connector metadata into one explicit first tiny-live eligibility answer. It
never places orders, enables live flags, signs payloads, or calls Binance.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution.binance_futures_connector import build_connector_status, build_protective_status
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.exchange_dry_run import build_current_exchange_dry_run
from src.app.hammer_radar.operator.inspect import LIVE_DECISION_ELIGIBLE, LiveCandidateCheck, build_live_candidate_snapshot
from src.app.hammer_radar.operator.live_approval import load_live_approval_requests
from src.app.hammer_radar.operator.live_preflight import PROMOTED_STRATEGY_KEY, build_promoted_strategy_preflight
from src.app.hammer_radar.operator.readiness import build_readiness_payload
from src.app.hammer_radar.operator.trade_ticket import build_trade_ticket, load_trade_ticket_records

PHASE = "R50"
SYSTEM = "money_printing_machine_hammer_radar"
LIVE_BEGINS_EVENTS_FILENAME = "live_begins_checks.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
WOULD_PLACE_ORDER = False
SECRETS_SHOWN = False


def build_live_begins_status(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_live_begins(log_dir=log_dir, env=env, persist=False)


def evaluate_and_record_live_begins(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _evaluate_live_begins(log_dir=log_dir, env=env, persist=True)


def load_live_begins_events(
    *,
    limit: int = 50,
    event_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = live_begins_events_path(get_log_dir(log_dir, use_env=True))
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


def live_begins_events_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LIVE_BEGINS_EVENTS_FILENAME


def format_live_begins_operator_message(payload: dict[str, Any]) -> str:
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:5]) if blockers else "none"
    return "\n".join(
        [
            f"R50 live-begins gate: {payload.get('status')}",
            f"signal_id: {payload.get('latest_signal_id') or 'none'}",
            f"symbol/timeframe/direction: {payload.get('symbol') or 'n/a'} / {payload.get('timeframe') or 'n/a'} / {payload.get('direction') or 'n/a'}",
            "No order placed. Approval is not execution.",
            f"blockers: {blocker_text}",
            f"next operator action: {payload.get('operator_action')}",
        ]
    )


def _evaluate_live_begins(
    *,
    log_dir: str | Path | None,
    env: Mapping[str, str] | None,
    persist: bool,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    connector = build_connector_status(env=source, log_dir=resolved_log_dir)
    protective = build_protective_status(env=source, log_dir=resolved_log_dir)
    preflight = build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    candidate = _latest_candidate(log_dir=resolved_log_dir)
    signal_id = str((candidate or {}).get("signal_id") or "")
    readiness = build_readiness_payload(log_dir=resolved_log_dir)
    ticket = build_trade_ticket(signal_id=signal_id, log_dir=resolved_log_dir) if signal_id else {}
    dry_run = build_current_exchange_dry_run(signal_id=signal_id, log_dir=resolved_log_dir) if signal_id else {}
    approvals = load_live_approval_requests(limit=0, signal_id=signal_id, log_dir=resolved_log_dir) if signal_id else []

    checks = _checks(
        candidate=candidate,
        preflight=preflight,
        readiness=readiness,
        ticket=ticket,
        dry_run=dry_run,
        connector=connector,
        protective=protective,
        approvals=approvals,
    )
    blockers = _blockers(
        candidate=candidate,
        readiness=readiness,
        ticket=ticket,
        dry_run=dry_run,
        connector=connector,
        protective=protective,
        approvals=approvals,
        checks=checks,
    )
    approval_status = _approval_status(approvals)
    status = _status(checks=checks, blockers=blockers, approval_status=approval_status)
    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "created_at": datetime.now(UTC).isoformat(),
        "live_execution_enabled": bool(connector.get("live_execution_enabled")),
        "binance_live_enabled": bool(connector.get("binance_live_enabled")),
        "allow_live_orders": bool(connector.get("allow_live_orders")),
        "global_kill_switch": bool(connector.get("global_kill_switch")),
        "protective_orders_required": bool(protective.get("protective_orders_required")),
        "protective_orders_enabled": bool(protective.get("protective_orders_enabled")),
        "protective_order_mode": protective.get("protective_order_mode") or "PREVIEW_ONLY",
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "would_place_order": WOULD_PLACE_ORDER,
        "latest_signal_id": signal_id or None,
        "symbol": (candidate or {}).get("symbol"),
        "timeframe": (candidate or {}).get("timeframe"),
        "direction": (candidate or {}).get("direction"),
        "freshness_status": _freshness_status(candidate),
        "readiness_status": readiness.get("readiness_status", "UNKNOWN"),
        "ticket_status": _ticket_status(ticket),
        "dry_run_status": _dry_run_status(dry_run),
        "live_safety_status": "ELIGIBLE" if _live_flags_eligible(connector) else "BLOCKED",
        "approval_status": approval_status,
        "checks": checks,
        "blockers": blockers,
        "operator_action": _operator_action(status=status, blockers=blockers),
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "live_begins_events_path": str(live_begins_events_path(resolved_log_dir)),
    }
    if persist:
        event = _audit_event(payload)
        append_live_begins_event(event, log_dir=resolved_log_dir)
        payload["audit_event_id"] = event["event_id"]
    return payload


def append_live_begins_event(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = live_begins_events_path(log_dir)
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
        "decision": check.decision,
        "reason": check.reason,
        "score": check.candidate.score,
        "tier": check.candidate.tier,
        "tradable": signal.tradable,
        "reject_reason": signal.reject_reason,
        "entry": check.entry,
        "stop": check.stop,
        "take_profit": check.take_profit,
        "age_minutes": check.age_minutes,
        "freshness_status": check.freshness_status,
        "suggested_leverage": check.suggested_leverage,
    }


def _checks(
    *,
    candidate: dict[str, Any] | None,
    preflight: dict[str, Any],
    readiness: dict[str, Any],
    ticket: dict[str, Any],
    dry_run: dict[str, Any],
    connector: dict[str, Any],
    protective: dict[str, Any],
    approvals: list[dict[str, Any]],
) -> dict[str, bool]:
    return {
        "candidate_present": candidate is not None,
        "candidate_fresh": _freshness_status(candidate) == "fresh",
        "signal_complete": _signal_complete(candidate),
        "strategy_live_eligible": _strategy_live_eligible(candidate=candidate, preflight=preflight),
        "tiny_live_eligible": (candidate or {}).get("decision") == LIVE_DECISION_ELIGIBLE,
        "dry_run_valid": dry_run.get("validation_status") == "VALID",
        "operator_approved": _has_exact_approval(approvals),
        "live_execution_enabled": connector.get("live_execution_enabled") is True,
        "binance_live_enabled": connector.get("binance_live_enabled") is True,
        "allow_live_orders": connector.get("allow_live_orders") is True,
        "global_kill_switch_off": connector.get("global_kill_switch") is False,
        "protective_orders_ready": _protective_orders_ready(protective),
        "idempotency_clear": _idempotency_clear(candidate=candidate, log_dir=Path(connector.get("attempts_path", "")).parent),
    }


def _blockers(
    *,
    candidate: dict[str, Any] | None,
    readiness: dict[str, Any],
    ticket: dict[str, Any],
    dry_run: dict[str, Any],
    connector: dict[str, Any],
    protective: dict[str, Any],
    approvals: list[dict[str, Any]],
    checks: dict[str, bool],
) -> list[str]:
    blockers: list[str] = []
    if candidate is None:
        blockers.append("candidate missing")
    elif _freshness_status(candidate) != "fresh":
        blockers.append("candidate stale")
    if candidate is not None and not _signal_complete(candidate):
        blockers.append("signal incomplete")
    if candidate is not None and candidate.get("decision") != LIVE_DECISION_ELIGIBLE:
        blockers.append(f"candidate is not tiny-live eligible: {candidate.get('decision', 'UNKNOWN')}")
    if candidate is not None and not checks["strategy_live_eligible"]:
        blockers.append(f"strategy is not live eligible for {PROMOTED_STRATEGY_KEY}")
    if readiness.get("readiness_status") != "READY":
        blockers.append(f"readiness_status is {readiness.get('readiness_status', 'UNKNOWN')}")
    if _ticket_status(ticket) != "ELIGIBLE":
        blockers.append(f"ticket_status is {_ticket_status(ticket)}")
    if _dry_run_status(dry_run) != "VALID":
        blockers.append(f"dry-run not valid: {_dry_run_status(dry_run)}")
    if connector.get("binance_live_enabled") is not True:
        blockers.append("HAMMER_BINANCE_LIVE_ENABLED is false")
    if connector.get("live_execution_enabled") is not True:
        blockers.append("live_execution_enabled is false")
    if connector.get("allow_live_orders") is not True:
        blockers.append("allow_live_orders is false")
    if connector.get("global_kill_switch") is not False:
        blockers.append("global kill switch active")
    if protective.get("protective_orders_required") is True and not _protective_orders_ready(protective):
        blockers.append("protective orders are required but not ready/enabled")
    if not _has_exact_approval(approvals):
        blockers.append("operator approval missing")
    if not checks["idempotency_clear"]:
        blockers.append("idempotency is not clear for signal")
    return list(dict.fromkeys(blocker for blocker in blockers if blocker))


def _status(*, checks: dict[str, bool], blockers: list[str], approval_status: str) -> str:
    if not checks["candidate_present"]:
        return "NOT_READY"
    non_approval_blockers = [blocker for blocker in blockers if blocker != "operator approval missing"]
    if not non_approval_blockers and approval_status == "MISSING":
        return "READY_FOR_OPERATOR_APPROVAL"
    if not blockers and approval_status == "APPROVED":
        return "ELIGIBLE_TINY_LIVE"
    return "BLOCKED"


def _operator_action(*, status: str, blockers: list[str]) -> str:
    if status == "ELIGIBLE_TINY_LIVE":
        return "approve tiny live"
    if status == "READY_FOR_OPERATOR_APPROVAL":
        return "approve tiny live"
    if any("candidate" in blocker for blocker in blockers):
        return "wait for next fresh candidate"
    if blockers:
        return "keep blocked"
    return "watch"


def _freshness_status(candidate: dict[str, Any] | None) -> str:
    if candidate is None:
        return "missing"
    value = str(candidate.get("freshness_status") or "unknown").lower()
    if value == "expired":
        return "stale"
    if value in {"fresh", "stale", "unknown"}:
        return value
    return "unknown"


def _ticket_status(ticket: dict[str, Any]) -> str:
    if not ticket:
        return "UNKNOWN"
    return "ELIGIBLE" if ticket.get("ticket_status") == "PROPOSED" else "BLOCKED"


def _dry_run_status(dry_run: dict[str, Any]) -> str:
    if not dry_run:
        return "UNKNOWN"
    return "VALID" if dry_run.get("validation_status") == "VALID" else "BLOCKED"


def _approval_status(approvals: list[dict[str, Any]]) -> str:
    if _has_exact_approval(approvals):
        return "APPROVED"
    if not approvals:
        return "MISSING"
    if any(record.get("approval_gate_status") == "REJECTED" for record in approvals):
        return "REJECTED"
    return "MISSING"


def _has_exact_approval(approvals: list[dict[str, Any]]) -> bool:
    return any(
        record.get("normalized_action") == "live_approve_exact"
        and record.get("parse_status") == "ACCEPTED"
        and record.get("signal_id")
        and record.get("approval_gate_status") in {"READY_BUT_EXECUTION_DISABLED", "APPROVED"}
        for record in approvals
    )


def _signal_complete(candidate: dict[str, Any] | None) -> bool:
    if candidate is None:
        return False
    required = ("signal_id", "symbol", "timeframe", "direction", "entry", "stop", "take_profit")
    return all(candidate.get(field) not in (None, "") for field in required)


def _strategy_live_eligible(*, candidate: dict[str, Any] | None, preflight: dict[str, Any]) -> bool:
    if candidate is None:
        return False
    return (
        preflight.get("promoted_strategy_ready") is True
        and preflight.get("strategy_key") == PROMOTED_STRATEGY_KEY
        and preflight.get("candidate_signal_id") == candidate.get("signal_id")
    )


def _live_flags_eligible(connector: dict[str, Any]) -> bool:
    return (
        connector.get("binance_live_enabled") is True
        and connector.get("live_execution_enabled") is True
        and connector.get("allow_live_orders") is True
        and connector.get("global_kill_switch") is False
    )


def _protective_orders_ready(protective: dict[str, Any]) -> bool:
    if protective.get("protective_orders_required") is not True:
        return True
    return (
        protective.get("protective_orders_enabled") is True
        and protective.get("protective_order_mode") == "LIVE_PROTECTIVE_ENABLED"
        and protective.get("protective_orders_supported") is True
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
        "event_type": "live_begins_check",
        "status": payload.get("status"),
        "blockers": list(payload.get("blockers") or []),
        "signal_id": payload.get("latest_signal_id"),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "secrets_shown": SECRETS_SHOWN,
    }
