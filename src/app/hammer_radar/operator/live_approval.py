"""Exact live approval gate for Hammer Radar.

This module evaluates future live-approval intent only. It never places orders,
never creates signed order payloads, never reads secrets, and never calls the
network.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.exchange_dry_run import build_current_exchange_dry_run
from src.app.hammer_radar.operator.first_live_timeframe_policy import evaluate_first_live_timeframe_candidate
from src.app.hammer_radar.operator.inspect import LIVE_DECISION_ELIGIBLE, LiveCandidateCheck, build_live_candidate_snapshot
from src.app.hammer_radar.operator.live_safety import build_current_live_safety
from src.app.hammer_radar.operator.notification_watcher import load_alert_records
from src.app.hammer_radar.operator.operator_actions import parse_operator_action
from src.app.hammer_radar.operator.readiness import PROTOCOL, build_readiness_payload
from src.app.hammer_radar.operator.trade_ticket import build_trade_ticket

LIVE_APPROVAL_REQUESTS_FILENAME = "live_approval_requests.ndjson"
LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
VALID_EXACT_APPROVAL_GATE_STATUSES = {"APPROVED", "READY_BUT_EXECUTION_DISABLED", "BLOCKED"}
INVALID_EXACT_APPROVAL_GATE_STATUSES = {"EXPIRED", "REJECTED", "NOT_FOUND", "NOT_LIVE_ELIGIBLE"}


def evaluate_live_approval_request(
    *,
    text: str,
    source: str = "approval_api",
    log_dir: str | Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    parsed = parse_operator_action(text)
    created_at = datetime.now(UTC).isoformat()
    signal_id = parsed.get("signal_id")
    matched_alert = _find_alert(signal_id, log_dir=resolved_log_dir) if signal_id else None
    matched_candidate = _find_candidate(signal_id, log_dir=resolved_log_dir) if signal_id else None

    readiness = build_readiness_payload(log_dir=resolved_log_dir)
    ticket = build_trade_ticket(signal_id=signal_id, log_dir=resolved_log_dir) if signal_id else {}
    dry_run = build_current_exchange_dry_run(signal_id=signal_id, log_dir=resolved_log_dir) if signal_id else {}
    live_safety = build_current_live_safety(signal_id=signal_id, log_dir=resolved_log_dir) if signal_id else {}
    blockers = _blockers(
        parsed=parsed,
        signal_id=signal_id,
        candidate=matched_candidate,
        readiness=readiness,
        ticket=ticket,
        dry_run=dry_run,
        live_safety=live_safety,
    )
    approval_gate_status = _approval_gate_status(
        parsed=parsed,
        signal_id=signal_id,
        candidate=matched_candidate,
        readiness=readiness,
        ticket=ticket,
        dry_run=dry_run,
    )

    record = {
        "request_id": uuid4().hex,
        "created_at": created_at,
        "source": source,
        "raw_text": parsed.get("raw_text", text),
        "normalized_action": parsed.get("normalized_action"),
        "parse_status": parsed.get("result_status"),
        "parse_reason": parsed.get("reason"),
        "signal_id": signal_id,
        "approval_gate_status": approval_gate_status,
        "matched_alert": matched_alert,
        "matched_candidate": matched_candidate,
        "freshness_status": (matched_candidate or {}).get("freshness_status") or "UNKNOWN",
        "readiness_status": readiness.get("readiness_status", "UNKNOWN"),
        "ticket_status": ticket.get("ticket_status", "UNKNOWN"),
        "dry_run_status": dry_run.get("validation_status", "UNKNOWN"),
        "live_safety_status": live_safety.get("live_safety_status", "UNKNOWN"),
        "blockers": blockers,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
    }
    if persist:
        append_live_approval_request(record, log_dir=resolved_log_dir)
    record["live_approval_requests_path"] = str(live_approval_requests_path(resolved_log_dir))
    return record


def append_live_approval_request(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = live_approval_requests_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_live_approval_requests(
    *,
    limit: int = 50,
    request_id: str | None = None,
    signal_id: str | None = None,
    log_dir: str | Path,
) -> list[dict[str, Any]]:
    path = live_approval_requests_path(log_dir)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if request_id is not None and record.get("request_id") != request_id:
                continue
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def live_approval_requests_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LIVE_APPROVAL_REQUESTS_FILENAME


def find_valid_live_approval_for_signal(
    signal_id: str | None,
    *,
    log_dir: str | Path,
    now: datetime | None = None,
    max_age_minutes: float | None = None,
) -> dict[str, Any]:
    resolved_signal_id = str(signal_id or "").strip() or None
    if not resolved_signal_id:
        return _approval_lookup_result(approval_found=False, approval_status="MISSING", blockers=["signal_id is required"])
    resolved_now = (now or datetime.now(UTC)).astimezone(UTC)
    latest_rejected: dict[str, Any] | None = None
    latest_expired: dict[str, Any] | None = None
    latest_blocked: dict[str, Any] | None = None
    for record in load_live_approval_requests(limit=0, signal_id=resolved_signal_id, log_dir=Path(log_dir)):
        if record.get("signal_id") != resolved_signal_id:
            continue
        if record.get("normalized_action") != "live_approve_exact":
            continue
        if record.get("parse_status") != "ACCEPTED":
            latest_rejected = latest_rejected or record
            continue
        expires_at = _parse_datetime(record.get("expires_at"))
        if expires_at is not None and expires_at <= resolved_now:
            latest_expired = latest_expired or record
            continue
        if max_age_minutes is not None and _record_too_old(record, now=resolved_now, max_age_minutes=max_age_minutes):
            latest_expired = latest_expired or record
            continue
        gate_status = str(record.get("approval_gate_status") or "").upper()
        if gate_status in INVALID_EXACT_APPROVAL_GATE_STATUSES:
            if gate_status == "EXPIRED":
                latest_expired = latest_expired or record
            else:
                latest_rejected = latest_rejected or record
            continue
        if gate_status in VALID_EXACT_APPROVAL_GATE_STATUSES:
            return _approval_lookup_result(
                approval_found=True,
                approval_status="APPROVED",
                record=record,
                blockers=[],
            )
        latest_blocked = latest_blocked or record
    if latest_expired is not None:
        return _approval_lookup_result(approval_found=False, approval_status="EXPIRED", record=latest_expired, blockers=["exact approval is expired"])
    if latest_rejected is not None:
        return _approval_lookup_result(approval_found=False, approval_status="REJECTED", record=latest_rejected, blockers=["exact approval was rejected"])
    if latest_blocked is not None:
        return _approval_lookup_result(approval_found=False, approval_status="BLOCKED", record=latest_blocked, blockers=["exact approval is blocked"])
    return _approval_lookup_result(approval_found=False, approval_status="MISSING", blockers=["exact approval for signal_id is missing"])


def _approval_gate_status(
    *,
    parsed: dict[str, Any],
    signal_id: str | None,
    candidate: dict[str, Any] | None,
    readiness: dict[str, Any],
    ticket: dict[str, Any],
    dry_run: dict[str, Any],
) -> str:
    if parsed.get("normalized_action") != "live_approve_exact" or parsed.get("result_status") != "ACCEPTED":
        return "BLOCKED"
    if not signal_id or candidate is None:
        return "NOT_FOUND"
    if candidate.get("freshness_status") == "expired":
        return "EXPIRED"
    if not _candidate_live_eligible(candidate):
        return "NOT_LIVE_ELIGIBLE"
    if (
        readiness.get("readiness_status") == "READY"
        and ticket.get("ticket_status") == "PROPOSED"
        and dry_run.get("validation_status") == "VALID"
    ):
        return "READY_BUT_EXECUTION_DISABLED"
    return "BLOCKED"


def _approval_lookup_result(
    *,
    approval_found: bool,
    approval_status: str,
    record: dict[str, Any] | None = None,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "approval_found": approval_found,
        "approval_status": approval_status,
        "request_id": (record or {}).get("request_id"),
        "created_at": (record or {}).get("created_at"),
        "expires_at": (record or {}).get("expires_at"),
        "approval_gate_status": (record or {}).get("approval_gate_status"),
        "parse_status": (record or {}).get("parse_status"),
        "signal_id": (record or {}).get("signal_id"),
        "blockers": list(blockers or []),
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def _record_too_old(record: dict[str, Any], *, now: datetime, max_age_minutes: float) -> bool:
    created_at = _parse_datetime(record.get("created_at"))
    if created_at is None:
        return True
    return (now - created_at).total_seconds() > max_age_minutes * 60.0


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


def _blockers(
    *,
    parsed: dict[str, Any],
    signal_id: str | None,
    candidate: dict[str, Any] | None,
    readiness: dict[str, Any],
    ticket: dict[str, Any],
    dry_run: dict[str, Any],
    live_safety: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if parsed.get("normalized_action") != "live_approve_exact" or parsed.get("result_status") != "ACCEPTED":
        blockers.append(parsed.get("reason") or "exact LIVE APPROVE <signal_id> is required")
    if not signal_id:
        blockers.append("signal_id is required")
    if signal_id and candidate is None:
        blockers.append(f"signal_id not found in current alerts/candidates: {signal_id}")
    if candidate is not None:
        if candidate.get("freshness_status") == "expired":
            blockers.append("candidate expired by freshness gate")
        if not _candidate_live_eligible(candidate):
            blockers.append(_candidate_not_live_eligible_reason(candidate))
    if readiness.get("readiness_status") != "READY":
        blockers.append(f"readiness_status is {readiness.get('readiness_status', 'UNKNOWN')}")
    if ticket.get("ticket_status") != "PROPOSED":
        blockers.append(f"ticket_status is {ticket.get('ticket_status', 'UNKNOWN')}")
    if dry_run.get("validation_status") != "VALID":
        blockers.append(f"dry_run_status is {dry_run.get('validation_status', 'UNKNOWN')}")
    blockers.extend(str(blocker) for blocker in live_safety.get("blockers") or [])
    blockers.extend(
        [
            "live_execution_enabled is false",
            "allow_live_orders is false",
            "global kill switch is active",
            "R39 evaluates only; no live order execution exists",
            "signed order payload creation is disabled",
        ]
    )
    return list(dict.fromkeys(blocker for blocker in blockers if blocker))


def _candidate_live_eligible(candidate: dict[str, Any]) -> bool:
    unified_eval = evaluate_first_live_timeframe_candidate(
        {
            "signal_id": candidate.get("signal_id"),
            "symbol": candidate.get("symbol"),
            "timeframe": candidate.get("timeframe"),
            "direction": candidate.get("direction"),
            "age_minutes": candidate.get("age_minutes"),
            "queue_fresh": candidate.get("freshness_status") == "fresh",
            "selected": candidate.get("unified_timeframe_profile") is True,
        },
        env=os.environ,
        selected=candidate.get("unified_timeframe_profile") is True,
    )
    return (
        candidate.get("symbol") == PROTOCOL["symbol"]
        and candidate.get("direction") == "long"
        and candidate.get("decision") == LIVE_DECISION_ELIGIBLE
        and candidate.get("freshness_status") == "fresh"
        and unified_eval.get("approval_allowed") is True
    )


def _candidate_not_live_eligible_reason(candidate: dict[str, Any]) -> str:
    if candidate.get("symbol") != PROTOCOL["symbol"]:
        return "only BTCUSDT is live-readiness eligible"
    if candidate.get("direction") == "short":
        return "shorts are paper/operator visibility only in R39"
    if candidate.get("decision") != LIVE_DECISION_ELIGIBLE:
        return f"candidate is {candidate.get('decision', 'UNKNOWN')}: {candidate.get('reason', 'no reason')}"
    return "candidate is not live eligible"


def _find_alert(signal_id: str | None, *, log_dir: Path) -> dict[str, Any] | None:
    if not signal_id:
        return None
    for alert in load_alert_records(limit=0, log_dir=log_dir):
        if alert.get("signal_id") == signal_id:
            return alert
    return None


def _find_candidate(signal_id: str | None, *, log_dir: Path) -> dict[str, Any] | None:
    if not signal_id:
        return None
    selected_candidate = _find_selected_unified_timeframe_candidate(signal_id, log_dir=log_dir)
    if selected_candidate is not None:
        return selected_candidate
    snapshot = build_live_candidate_snapshot(
        limit=1000,
        since_hours=24,
        min_score=0,
        symbol=None,
        allow_short=True,
        allow_oversold=True,
        allow_trigger_flags=True,
        allow_expired=True,
        latest_only=False,
        log_dir=log_dir,
    )
    for check in snapshot["checks"]:
        if check.candidate.signal.signal_id == signal_id:
            return _candidate_snapshot(check)
    return None


def _find_selected_unified_timeframe_candidate(signal_id: str, *, log_dir: Path) -> dict[str, Any] | None:
    from src.app.hammer_radar.operator.first_live_candidate_queue import build_first_live_candidate_queue

    queue = build_first_live_candidate_queue(log_dir=log_dir)
    selection = queue.get("selection_status") if isinstance(queue.get("selection_status"), dict) else {}
    candidate = selection.get("candidate") if isinstance(selection.get("candidate"), dict) else {}
    if candidate.get("signal_id") != signal_id:
        return None
    if candidate.get("live_candidate_allowed") is not True or candidate.get("unified_timeframe_profile") is not True:
        return None
    profile_name = candidate.get("unified_policy_profile_name") or candidate.get("profile_name")
    return {
        "signal_id": candidate.get("signal_id"),
        "timestamp": candidate.get("timestamp"),
        "symbol": candidate.get("symbol"),
        "timeframe": candidate.get("timeframe"),
        "direction": candidate.get("direction"),
        "decision": LIVE_DECISION_ELIGIBLE,
        "reason": f"selected unified timeframe profile allowed by R73 policy: {profile_name}",
        "score": candidate.get("score"),
        "tier": candidate.get("tier"),
        "tradable": True,
        "reject_reason": None,
        "entry": candidate.get("entry"),
        "stop": candidate.get("stop"),
        "take_profit": candidate.get("take_profit"),
        "age_minutes": candidate.get("age_minutes"),
        "freshness_status": "fresh" if candidate.get("queue_fresh") is True else "expired",
        "suggested_leverage": None,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "higher_timeframe_profile": candidate.get("higher_timeframe_profile") is True,
        "unified_timeframe_profile": True,
        "profile_name": profile_name,
        "policy_status": candidate.get("unified_policy_status") or candidate.get("policy_status"),
        "order_placed": ORDER_PLACED,
    }


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
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
    }
