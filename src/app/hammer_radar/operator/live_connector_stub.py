"""No-order live connector stub for Hammer Radar.

This is the only live connector adapter seam for future phases. In R26 it is
sealed: it never places orders, never imports exchange SDKs, never reads
credentials, and never calls the network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.exchange_dry_run import build_current_exchange_dry_run
from src.app.hammer_radar.operator.live_safety import build_current_live_safety
from src.app.hammer_radar.operator.trade_ticket import build_trade_ticket

CONNECTOR_MODE = "stub_no_order"
LIVE_ATTEMPTS_FILENAME = "live_attempts.ndjson"
LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False


def submit_live_order_stub(
    *,
    ticket_id: str,
    operator: str = "josue",
    notes: str = "",
    log_dir: str | Path | None = None,
    safety_snapshot: dict[str, Any] | None = None,
    dry_run_snapshot: dict[str, Any] | None = None,
    ticket_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    ticket = ticket_snapshot or build_trade_ticket(log_dir=resolved_log_dir)
    dry_run = dry_run_snapshot or build_current_exchange_dry_run(log_dir=resolved_log_dir)
    safety = safety_snapshot or build_current_live_safety(log_dir=resolved_log_dir)
    reason = _rejection_reason(safety)
    record = {
        "live_attempt_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "source": "approval_api",
        "connector_mode": CONNECTOR_MODE,
        "requested_action": "submit_live_order",
        "signal_id": ticket.get("signal_id"),
        "ticket_id": ticket_id,
        "symbol": ticket.get("symbol"),
        "side": dry_run.get("side"),
        "position_side": dry_run.get("position_side"),
        "notional_usd": dry_run.get("notional_usd") or ticket.get("suggested_position_usd"),
        "leverage": dry_run.get("leverage") or ticket.get("suggested_leverage"),
        "margin_mode": dry_run.get("margin_mode") or ticket.get("margin_mode"),
        "live_safety_status": safety.get("live_safety_status", "BLOCKED"),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "rejected": True,
        "rejection_reason": reason,
        "safety_snapshot": safety,
        "dry_run_snapshot": dry_run,
        "ticket_snapshot": ticket,
        "operator": operator,
        "notes": notes,
    }
    record_live_attempt(record, log_dir=resolved_log_dir)
    return record


def load_live_attempts(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    ticket_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = _live_attempts_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            if ticket_id is not None and record.get("ticket_id") != ticket_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def record_live_attempt(record: dict[str, Any], *, log_dir: str | Path | None = None) -> None:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = _live_attempts_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def build_live_connector_submit_text(
    *,
    ticket_id: str,
    operator: str = "josue",
    notes: str = "",
    log_dir: str | Path | None = None,
) -> str:
    record = submit_live_order_stub(ticket_id=ticket_id, operator=operator, notes=notes, log_dir=log_dir)
    return "\n".join(
        [
            "HAMMER RADAR LIVE CONNECTOR STUB ATTEMPT",
            f"live_attempt_id: {record['live_attempt_id']}",
            f"connector_mode: {record['connector_mode']}",
            f"ticket_id: {record['ticket_id']}",
            f"signal_id: {record.get('signal_id') or 'n/a'}",
            f"live_safety_status: {record['live_safety_status']}",
            f"rejected: {record['rejected']}",
            f"rejection_reason: {record['rejection_reason']}",
            "live_execution_enabled: false",
            "order_placed: false",
        ]
    )


def build_live_attempts_text(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    ticket_id: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_live_attempts(limit=limit, signal_id=signal_id, ticket_id=ticket_id, log_dir=resolved_log_dir)
    lines = [
        "HAMMER RADAR LIVE CONNECTOR ATTEMPTS",
        f"archive_log_dir: {resolved_log_dir}",
        "connector_mode: stub_no_order",
        "live_execution_enabled: false",
        "order_placed: false",
    ]
    if not records:
        return "\n".join([*lines, "no live connector attempts"])
    for record in records:
        lines.append(
            f"{record.get('created_at')} | {record.get('live_attempt_id')} | ticket={record.get('ticket_id')} | "
            f"signal={record.get('signal_id')} | status={record.get('live_safety_status')} | "
            f"rejected={record.get('rejected')} | order_placed={record.get('order_placed')}"
        )
    return "\n".join(lines)


def _rejection_reason(safety: dict[str, Any]) -> str:
    status = safety.get("live_safety_status", "BLOCKED")
    blockers = safety.get("blockers") or []
    if status == "WOULD_BE_ALLOWED_IF_LIVE_ENABLED":
        return "stub_no_order connector cannot place live orders"
    if blockers:
        return "; ".join(str(blocker) for blocker in blockers)
    return f"live safety status is {status}; stub_no_order connector rejects all live submissions"


def _live_attempts_path(log_dir: Path) -> Path:
    return log_dir / LIVE_ATTEMPTS_FILENAME
