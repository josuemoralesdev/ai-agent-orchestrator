"""Paper-only execution records for Hammer Radar trade tickets.

This module creates local simulated execution records only. It never imports
exchange clients, never places live orders, and never stores credentials.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.readiness import LIVE_EXECUTION_ENABLED, ORDER_PLACED
from src.app.hammer_radar.operator.trade_ticket import (
    approve_paper_ticket,
    build_trade_ticket,
    load_trade_ticket_records,
)

PAPER_EXECUTIONS_FILENAME = "paper_executions.ndjson"
PAPER_ORDER_PLACED = True


def execute_paper_ticket(
    *,
    ticket_id: str,
    operator: str = "josue",
    notes: str = "",
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    ticket = _current_ticket_for_id(ticket_id, log_dir=resolved_log_dir)
    _validate_executable_ticket(ticket, ticket_id=ticket_id)
    _ensure_approval_intent(ticket, operator=operator, notes=notes, log_dir=resolved_log_dir)

    record = {
        "paper_execution_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "ticket_id": ticket["ticket_id"],
        "signal_id": ticket["signal_id"],
        "symbol": ticket["symbol"],
        "direction": ticket["direction"],
        "timeframe": ticket["timeframe"],
        "entry": ticket["entry"],
        "stop": ticket["stop"],
        "take_profit": ticket["take_profit"],
        "position_usd": ticket["suggested_position_usd"],
        "leverage": ticket["suggested_leverage"],
        "margin_mode": ticket["margin_mode"],
        "max_loss_usd": ticket["max_loss_usd"],
        "status": "PAPER_OPEN",
        "source": "approval_api",
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "paper_order_placed": PAPER_ORDER_PLACED,
        "notes": notes,
        "operator": operator,
        "ticket": ticket,
    }
    _append_paper_execution(record, log_dir=resolved_log_dir)
    return record


def load_paper_executions(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = _paper_executions_path(get_log_dir(log_dir, use_env=True))
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
            if status is not None and record.get("status") != status:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def build_execute_paper_ticket_text(
    *,
    ticket_id: str,
    operator: str = "josue",
    notes: str = "",
    log_dir: str | Path | None = None,
) -> str:
    record = execute_paper_ticket(
        ticket_id=ticket_id,
        operator=operator,
        notes=notes,
        log_dir=log_dir,
    )
    return "\n".join(
        [
            "HAMMER RADAR PAPER EXECUTION RECORDED",
            f"paper_execution_id: {record['paper_execution_id']}",
            f"ticket_id: {record['ticket_id']}",
            f"signal_id: {record['signal_id']}",
            f"status: {record['status']}",
            f"position_usd: {record['position_usd']}",
            f"leverage: {record['leverage']}",
            "live_execution_enabled: false",
            "order_placed: false",
            "paper_order_placed: true",
        ]
    )


def build_paper_executions_text(
    *,
    limit: int = 50,
    signal_id: str | None = None,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_paper_executions(limit=limit, signal_id=signal_id, status=status, log_dir=resolved_log_dir)
    lines = [
        "HAMMER RADAR PAPER EXECUTIONS",
        f"archive_log_dir: {resolved_log_dir}",
        "live_execution_enabled: false",
        "order_placed: false",
    ]
    if not records:
        return "\n".join([*lines, "no paper execution records"])
    for record in records:
        lines.append(
            f"{record.get('created_at')} | {record.get('paper_execution_id')} | "
            f"signal={record.get('signal_id')} | {record.get('direction')}/{record.get('timeframe')} | "
            f"position_usd={record.get('position_usd')} | leverage={record.get('leverage')} | "
            f"status={record.get('status')} | paper_order_placed={record.get('paper_order_placed')} | "
            f"order_placed={record.get('order_placed')}"
        )
    return "\n".join(lines)


def _current_ticket_for_id(ticket_id: str, *, log_dir: Path) -> dict[str, Any]:
    current = build_trade_ticket(log_dir=log_dir)
    if current.get("ticket_id") == ticket_id:
        return current
    for record in load_trade_ticket_records(limit=0, ticket_id=ticket_id, log_dir=log_dir):
        ticket = record.get("ticket") or {}
        signal_id = ticket.get("signal_id")
        if signal_id:
            rebuilt = build_trade_ticket(signal_id=str(signal_id), log_dir=log_dir)
            if rebuilt.get("ticket_id") == ticket_id:
                return rebuilt
    raise ValueError("ticket_id does not match current ticket or known ticket approval")


def _validate_executable_ticket(ticket: dict[str, Any], *, ticket_id: str) -> None:
    if ticket.get("ticket_id") != ticket_id:
        raise ValueError("ticket_id does not match rebuilt ticket")
    if ticket.get("ticket_status") != "PROPOSED":
        raise ValueError("only PROPOSED tickets can be paper executed")
    if ticket.get("readiness_status") != "READY":
        raise ValueError("readiness is NOT_READY")
    if ticket.get("allowed_now") is not True:
        raise ValueError("ticket is not allowed now")
    if ticket.get("live_execution_enabled") is not False:
        raise ValueError("live_execution_enabled safety field is not false")
    if ticket.get("order_placed") is not False:
        raise ValueError("order_placed safety field is not false")
    if ticket.get("blockers"):
        raise ValueError("ticket has blockers")
    if ticket.get("entry") is None or ticket.get("stop") is None or ticket.get("take_profit") is None:
        raise ValueError("ticket is missing entry, stop, or take_profit")


def _ensure_approval_intent(
    ticket: dict[str, Any],
    *,
    operator: str,
    notes: str,
    log_dir: Path,
) -> None:
    if load_trade_ticket_records(limit=1, ticket_id=ticket["ticket_id"], log_dir=log_dir):
        return
    approve_paper_ticket(
        ticket_id=ticket["ticket_id"],
        operator=operator,
        notes=notes,
        ticket_snapshot=ticket,
        log_dir=log_dir,
    )


def _append_paper_execution(record: dict[str, Any], *, log_dir: Path) -> None:
    path = _paper_executions_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _paper_executions_path(log_dir: Path) -> Path:
    return log_dir / PAPER_EXECUTIONS_FILENAME
