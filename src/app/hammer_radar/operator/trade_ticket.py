"""Machine-prepared paper/manual trade tickets for Hammer Radar.

Tickets are proposals only. This module never places orders and never enables
live execution.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.inspect import (
    LIVE_DECISION_ELIGIBLE,
    LiveCandidateCheck,
    build_live_candidate_snapshot,
)
from src.app.hammer_radar.operator.readiness import (
    LIVE_EXECUTION_ENABLED,
    ORDER_PLACED,
    PROTOCOL,
    build_readiness_payload,
)

TRADE_TICKETS_FILENAME = "trade_tickets.ndjson"
PAPER_EXECUTION_ENABLED = False
PAPER_ORDER_PLACED = False
DEFAULT_MAX_RISK_USD = 5.0
DEFAULT_FRESH_MINUTES = 30
MIN_SCORE = 90


def build_trade_ticket(
    *,
    signal_id: str | None = None,
    latest_only: bool = True,
    allow_short: bool = False,
    max_position_usd: float = 44.0,
    max_risk_usd: float = DEFAULT_MAX_RISK_USD,
    max_leverage: float = 3.0,
    fresh_minutes: int = DEFAULT_FRESH_MINUTES,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    created_at = datetime.now(UTC)
    readiness = build_readiness_payload(log_dir=resolved_log_dir)
    snapshot = build_live_candidate_snapshot(
        limit=1000 if signal_id else 10,
        since_hours=24,
        min_score=MIN_SCORE,
        symbol=PROTOCOL["symbol"],
        allow_short=allow_short,
        allow_oversold=False,
        allow_trigger_flags=False,
        max_risk_usd=max_risk_usd,
        max_leverage=max_leverage,
        max_position_usd=max_position_usd,
        fresh_minutes=fresh_minutes,
        allow_expired=False,
        latest_only=latest_only if not signal_id else False,
        log_dir=resolved_log_dir,
    )
    checks: list[LiveCandidateCheck] = list(snapshot["checks"])
    selected = _select_candidate(checks, signal_id=signal_id)

    blockers = list(readiness.get("blockers") or [])
    if selected is None:
        if signal_id:
            blockers.append(f"signal_id not found in current BTCUSDT live-checklist window: {signal_id}")
        else:
            blockers.append("no current BTCUSDT live-checklist candidate available")
        return _blocked_ticket(
            created_at=created_at,
            readiness=readiness,
            blockers=blockers,
            machine_reason="; ".join(blockers),
            archive_log_dir=resolved_log_dir,
        )

    candidate_blockers = _candidate_blockers(
        selected,
        allow_short=allow_short,
        max_position_usd=max_position_usd,
        max_leverage=max_leverage,
    )
    blockers.extend(candidate_blockers)
    if readiness.get("readiness_status") != "READY":
        blockers.append("readiness is NOT_READY")
    if LIVE_EXECUTION_ENABLED is not False:
        blockers.append("live_execution_enabled safety field is not false")
    if ORDER_PLACED is not False:
        blockers.append("order_placed safety field is not false")

    status = "PROPOSED" if not blockers else ("EXPIRED" if selected.freshness_status == "expired" else "BLOCKED")
    machine_reason = (
        "fresh eligible BTCUSDT candidate converted into a paper/manual proposal"
        if status == "PROPOSED"
        else "; ".join(dict.fromkeys(blockers))
    )
    return _ticket_from_check(
        selected,
        created_at=created_at,
        readiness=readiness,
        ticket_status=status,
        blockers=list(dict.fromkeys(blockers)),
        machine_reason=machine_reason,
        max_position_usd=max_position_usd,
        max_risk_usd=max_risk_usd,
        max_leverage=max_leverage,
        archive_log_dir=resolved_log_dir,
    )


def approve_paper_ticket(
    *,
    ticket_id: str,
    operator: str,
    notes: str = "",
    ticket_snapshot: dict[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    ticket = ticket_snapshot or build_trade_ticket(log_dir=resolved_log_dir)
    if ticket.get("ticket_id") != ticket_id:
        recreated = _recreate_ticket_for_id(ticket_id, log_dir=resolved_log_dir)
        if recreated is not None:
            ticket = recreated
    if ticket.get("ticket_id") != ticket_id:
        raise ValueError("ticket_id does not match current or provided ticket snapshot")
    if ticket.get("ticket_status") != "PROPOSED":
        raise ValueError("only PROPOSED paper tickets can be approved")

    record = {
        "record_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "action": "approve_paper_ticket",
        "operator": operator,
        "notes": notes,
        "ticket": ticket,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "paper_execution_enabled": PAPER_EXECUTION_ENABLED,
        "paper_order_placed": PAPER_ORDER_PLACED,
        "source": "approval_api",
    }
    _append_ticket_record(record, log_dir=resolved_log_dir)
    return record


def load_trade_ticket_records(
    *,
    limit: int = 50,
    ticket_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = _trade_tickets_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            record_ticket_id = (record.get("ticket") or {}).get("ticket_id") or record.get("ticket_id")
            if ticket_id is not None and record_ticket_id != ticket_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def build_trade_ticket_text(*, log_dir: str | Path | None = None) -> str:
    ticket = build_trade_ticket(log_dir=log_dir)
    lines = [
        "HAMMER RADAR MACHINE TRADE TICKET",
        f"ticket_status: {ticket['ticket_status']}",
        f"readiness_status: {ticket['readiness_status']}",
        f"allowed_now: {ticket['allowed_now']}",
        f"ticket_id: {ticket.get('ticket_id') or 'n/a'}",
        f"signal_id: {ticket.get('signal_id') or 'n/a'}",
        f"symbol: {ticket.get('symbol') or 'n/a'}",
        f"direction/timeframe: {ticket.get('direction') or 'n/a'}/{ticket.get('timeframe') or 'n/a'}",
        f"entry: {_format_value(ticket.get('entry'))}",
        f"stop: {_format_value(ticket.get('stop'))}",
        f"take_profit: {_format_value(ticket.get('take_profit'))}",
        f"suggested_position_usd: {_format_value(ticket.get('suggested_position_usd'))}",
        f"suggested_leverage: {_format_value(ticket.get('suggested_leverage'))}",
        f"margin_mode: {ticket.get('margin_mode')}",
        f"max_loss_usd: {_format_value(ticket.get('max_loss_usd'))}",
        f"blockers: {'; '.join(ticket['blockers']) if ticket['blockers'] else 'none'}",
        f"machine_reason: {ticket['machine_reason']}",
        f"operator_required_action: {ticket['operator_required_action']}",
        "live_execution_enabled: false",
        "order_placed: false",
    ]
    return "\n".join(lines)


def build_trade_tickets_text(
    *,
    limit: int = 50,
    ticket_id: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_trade_ticket_records(limit=limit, ticket_id=ticket_id, log_dir=resolved_log_dir)
    lines = [
        "HAMMER RADAR TRADE TICKET RECORDS",
        f"archive_log_dir: {resolved_log_dir}",
        "live_execution_enabled: false",
        "order_placed: false",
        "paper_execution_enabled: false",
        "paper_order_placed: false",
    ]
    if not records:
        return "\n".join([*lines, "no trade ticket records"])
    for record in records:
        ticket = record.get("ticket") or {}
        lines.append(
            f"{record.get('created_at')} | {record.get('record_id')} | action={record.get('action')} | "
            f"ticket={ticket.get('ticket_id')} | signal={ticket.get('signal_id')} | "
            f"status={ticket.get('ticket_status')} | operator={record.get('operator')}"
        )
    return "\n".join(lines)


def _select_candidate(checks: list[LiveCandidateCheck], *, signal_id: str | None) -> LiveCandidateCheck | None:
    if signal_id is not None:
        for check in checks:
            if check.candidate.signal.signal_id == signal_id:
                return check
        return None
    eligible = [
        check
        for check in checks
        if check.decision == LIVE_DECISION_ELIGIBLE and check.freshness_status == "fresh"
    ]
    return eligible[0] if eligible else None


def _candidate_blockers(
    check: LiveCandidateCheck,
    *,
    allow_short: bool,
    max_position_usd: float,
    max_leverage: float,
) -> list[str]:
    signal = check.candidate.signal
    blockers: list[str] = []
    if signal.symbol != PROTOCOL["symbol"]:
        blockers.append("only BTCUSDT tickets are permitted")
    if signal.direction == "short" and not allow_short:
        blockers.append("short ticket requires allow_short=true")
    if signal.direction != "long" and signal.direction != "short":
        blockers.append(f"unsupported direction: {signal.direction}")
    if signal.rsi_state == "oversold":
        blockers.append("oversold forbidden for first live test")
    if check.entry is None:
        blockers.append("missing entry")
    if check.stop is None:
        blockers.append("missing stop")
    if check.take_profit is None:
        blockers.append("missing take_profit")
    if check.freshness_status == "expired":
        blockers.append("candidate expired by freshness gate")
    if check.decision != LIVE_DECISION_ELIGIBLE:
        blockers.append(f"candidate is {check.decision}: {check.reason}")
    if (check.capped_max_position_usd or 0.0) <= 0.0:
        blockers.append("suggested position is unavailable")
    if float(max_position_usd) <= 0.0:
        blockers.append("max_position_usd must be positive")
    if float(max_leverage) <= 0.0:
        blockers.append("max_leverage must be positive")
    return blockers


def _ticket_from_check(
    check: LiveCandidateCheck,
    *,
    created_at: datetime,
    readiness: dict[str, Any],
    ticket_status: str,
    blockers: list[str],
    machine_reason: str,
    max_position_usd: float,
    max_risk_usd: float,
    max_leverage: float,
    archive_log_dir: Path,
) -> dict[str, Any]:
    signal = check.candidate.signal
    suggested_position_usd = _suggested_position_usd(check, max_position_usd=max_position_usd)
    risk_distance_pct = check.risk_distance_pct
    max_loss_usd = (
        round(suggested_position_usd * (risk_distance_pct / 100.0), 4)
        if suggested_position_usd is not None and risk_distance_pct is not None
        else None
    )
    if max_loss_usd is not None:
        max_loss_usd = min(max_loss_usd, float(max_risk_usd))
    return {
        "ticket_id": _ticket_id(signal.signal_id),
        "created_at": created_at.isoformat(),
        "archive_log_dir": str(archive_log_dir),
        "signal_id": signal.signal_id,
        "symbol": signal.symbol,
        "direction": signal.direction,
        "timeframe": signal.timeframe,
        "entry": check.entry,
        "stop": check.stop,
        "take_profit": check.take_profit,
        "risk_distance_pct": risk_distance_pct,
        "max_position_usd": float(max_position_usd),
        "suggested_position_usd": suggested_position_usd,
        "suggested_leverage": _suggested_ticket_leverage(max_leverage),
        "margin_mode": "isolated",
        "max_loss_usd": max_loss_usd,
        "expected_reward_pct": _expected_reward_pct(check.entry, check.take_profit),
        "candidate_score": check.candidate.score,
        "candidate_tier": check.candidate.tier,
        "readiness_status": readiness.get("readiness_status", "UNKNOWN"),
        "allowed_now": bool(readiness.get("allowed_now")),
        "blockers": blockers,
        "machine_reason": machine_reason,
        "operator_required_action": _operator_required_action(ticket_status),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "ticket_status": ticket_status,
    }


def _blocked_ticket(
    *,
    created_at: datetime,
    readiness: dict[str, Any],
    blockers: list[str],
    machine_reason: str,
    archive_log_dir: Path,
) -> dict[str, Any]:
    return {
        "ticket_id": None,
        "created_at": created_at.isoformat(),
        "archive_log_dir": str(archive_log_dir),
        "signal_id": None,
        "symbol": PROTOCOL["symbol"],
        "direction": None,
        "timeframe": None,
        "entry": None,
        "stop": None,
        "take_profit": None,
        "risk_distance_pct": None,
        "max_position_usd": float(PROTOCOL["max_position_usd"]),
        "suggested_position_usd": None,
        "suggested_leverage": None,
        "margin_mode": "isolated",
        "max_loss_usd": None,
        "expected_reward_pct": None,
        "candidate_score": None,
        "candidate_tier": None,
        "readiness_status": readiness.get("readiness_status", "UNKNOWN"),
        "allowed_now": bool(readiness.get("allowed_now")),
        "blockers": list(dict.fromkeys(blockers)),
        "machine_reason": machine_reason,
        "operator_required_action": _operator_required_action("BLOCKED"),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "ticket_status": "BLOCKED",
    }


def _recreate_ticket_for_id(ticket_id: str, *, log_dir: Path) -> dict[str, Any] | None:
    snapshot = build_live_candidate_snapshot(
        limit=1000,
        since_hours=24,
        min_score=MIN_SCORE,
        symbol=PROTOCOL["symbol"],
        allow_short=True,
        allow_oversold=False,
        allow_trigger_flags=False,
        max_risk_usd=DEFAULT_MAX_RISK_USD,
        max_leverage=float(PROTOCOL["max_leverage"]),
        max_position_usd=float(PROTOCOL["max_position_usd"]),
        fresh_minutes=DEFAULT_FRESH_MINUTES,
        allow_expired=False,
        latest_only=False,
        log_dir=log_dir,
    )
    for check in snapshot["checks"]:
        if _ticket_id(check.candidate.signal.signal_id) == ticket_id:
            return build_trade_ticket(signal_id=check.candidate.signal.signal_id, log_dir=log_dir)
    return None


def _append_ticket_record(record: dict[str, Any], *, log_dir: Path) -> None:
    path = _trade_tickets_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _trade_tickets_path(log_dir: Path) -> Path:
    return log_dir / TRADE_TICKETS_FILENAME


def _ticket_id(signal_id: str) -> str:
    digest = hashlib.sha256(signal_id.encode("utf-8")).hexdigest()[:16]
    return f"tt_{digest}"


def _suggested_position_usd(check: LiveCandidateCheck, *, max_position_usd: float) -> float | None:
    if check.capped_max_position_usd is None:
        return None
    return round(min(float(max_position_usd), check.capped_max_position_usd), 4)


def _suggested_ticket_leverage(max_leverage: float) -> float:
    return round(min(float(PROTOCOL["preferred_leverage"]), float(max_leverage)), 4)


def _expected_reward_pct(entry: float | None, take_profit: float | None) -> float | None:
    if entry is None or take_profit is None or entry <= 0.0:
        return None
    return round(abs(take_profit - entry) / entry * 100.0, 4)


def _operator_required_action(ticket_status: str) -> str:
    if ticket_status == "PROPOSED":
        return "Review ticket and optionally approve paper intent only. No order will be placed."
    if ticket_status == "EXPIRED":
        return "Wait for a fresh candidate before approving any paper/manual intent."
    return "Do not approve now; resolve blockers and wait for READY status."


def _format_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
