"""Live execution safety envelope for Hammer Radar.

This module evaluates gates for a future live connector path. It never places
orders, never imports exchange clients, never reads secrets, and never calls the
network.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.exchange_dry_run import build_current_exchange_dry_run
from src.app.hammer_radar.operator.manual_outcomes import load_manual_outcomes
from src.app.hammer_radar.operator.paper_execution import load_paper_executions
from src.app.hammer_radar.operator.readiness import build_readiness_payload
from src.app.hammer_radar.operator.trade_ticket import build_trade_ticket, load_trade_ticket_records

LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False

DEFAULT_SAFETY_CONFIG: dict[str, Any] = {
    "live_execution_enabled": False,
    "global_kill_switch": True,
    "allow_live_orders": False,
    "max_position_usd": 44.0,
    "max_leverage": 3.0,
    "preferred_leverage": 2.0,
    "max_daily_loss_usd": 5.0,
    "max_trades_per_day": 1,
    "require_isolated_margin": True,
    "require_ready_status": True,
    "require_proposed_ticket": True,
    "require_exchange_dry_run_valid": True,
    "require_human_approval": True,
    "require_paper_execution_first": True,
    "require_manual_outcome_log_available": True,
    "allowed_symbols": ["BTCUSDT"],
    "allow_short": False,
    "allow_oversold": False,
}

PROTOCOL_SUMMARY = {
    "max_position_usd": 44.0,
    "preferred_leverage": 2.0,
    "max_leverage": 3.0,
    "margin_mode": "isolated",
    "max_trades_per_day": 1,
    "hard_daily_stop": "one live loss or 5 USDT loss",
    "allowed_symbols": ["BTCUSDT"],
}


def build_current_live_safety(
    *,
    signal_id: str | None = None,
    allow_short: bool = False,
    max_position_usd: float = 44.0,
    max_leverage: float = 3.0,
    fresh_minutes: int = 30,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    readiness = build_readiness_payload(log_dir=resolved_log_dir)
    ticket = build_trade_ticket(
        signal_id=signal_id,
        allow_short=allow_short,
        max_position_usd=max_position_usd,
        max_leverage=max_leverage,
        fresh_minutes=fresh_minutes,
        log_dir=resolved_log_dir,
    )
    exchange_dry_run = build_current_exchange_dry_run(
        signal_id=signal_id,
        allow_short=allow_short,
        max_position_usd=max_position_usd,
        max_leverage=max_leverage,
        fresh_minutes=fresh_minutes,
        log_dir=resolved_log_dir,
    )
    decisions = load_trade_ticket_records(limit=0, log_dir=resolved_log_dir)
    paper_executions = load_paper_executions(limit=0, log_dir=resolved_log_dir)
    manual_outcomes = load_manual_outcomes(limit=0, log_dir=resolved_log_dir)
    return evaluate_live_safety(
        readiness=readiness,
        ticket=ticket,
        exchange_dry_run=exchange_dry_run,
        decisions=decisions,
        paper_executions=paper_executions,
        manual_outcomes=manual_outcomes,
        config_override={"allow_short": allow_short, "max_position_usd": max_position_usd, "max_leverage": max_leverage},
    )


def evaluate_live_safety(
    *,
    readiness: dict[str, Any] | None,
    ticket: dict[str, Any] | None,
    exchange_dry_run: dict[str, Any] | None,
    decisions: list[dict[str, Any]] | None,
    paper_executions: list[dict[str, Any]] | None,
    manual_outcomes: list[dict[str, Any]] | None,
    config_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = dict(DEFAULT_SAFETY_CONFIG)
    if config_override:
        config.update(config_override)

    readiness = readiness or {}
    ticket = ticket or {}
    exchange_dry_run = exchange_dry_run or {}
    decisions = decisions or []
    paper_executions = paper_executions or []
    manual_outcomes = manual_outcomes or []
    today = datetime.now(UTC).date()
    manual_today = _manual_outcomes_today(manual_outcomes, today=today)
    losses_today = _losses_today(readiness, manual_today)
    pnl_usd_today = _pnl_today(readiness, manual_today)
    ticket_id = ticket.get("ticket_id")
    signal_id = ticket.get("signal_id")

    gates = [
        ("live_execution_enabled", config.get("live_execution_enabled") is True, "live_execution_enabled is false"),
        ("global_kill_switch", config.get("global_kill_switch") is False, "global kill switch is active"),
        ("allow_live_orders", config.get("allow_live_orders") is True, "allow_live_orders is false"),
        (
            "readiness_status",
            (not config.get("require_ready_status")) or readiness.get("readiness_status") == "READY",
            f"readiness_status is {readiness.get('readiness_status', 'UNKNOWN')}",
        ),
        (
            "allowed_now",
            readiness.get("allowed_now") is True,
            "readiness allowed_now is false",
        ),
        (
            "ticket_status",
            (not config.get("require_proposed_ticket")) or ticket.get("ticket_status") == "PROPOSED",
            f"ticket_status is {ticket.get('ticket_status', 'UNKNOWN')}",
        ),
        (
            "exchange_dry_run_valid",
            (not config.get("require_exchange_dry_run_valid"))
            or exchange_dry_run.get("validation_status") == "VALID",
            f"exchange dry-run status is {exchange_dry_run.get('validation_status', 'UNKNOWN')}",
        ),
        (
            "exchange_dry_run_true",
            exchange_dry_run.get("dry_run") is True,
            "exchange dry_run is not true",
        ),
        (
            "exchange_order_not_placed",
            exchange_dry_run.get("order_placed") is False,
            "exchange dry-run order_placed is not false",
        ),
        (
            "symbol_allowed",
            ticket.get("symbol") in set(config.get("allowed_symbols") or []),
            f"symbol is not allowed: {ticket.get('symbol')}",
        ),
        (
            "position_cap",
            _float_or_none(ticket.get("suggested_position_usd")) is not None
            and _float_or_none(ticket.get("suggested_position_usd")) <= float(config["max_position_usd"]),
            f"position_usd exceeds {config['max_position_usd']}: {ticket.get('suggested_position_usd')}",
        ),
        (
            "leverage_cap",
            _float_or_none(ticket.get("suggested_leverage")) is not None
            and _float_or_none(ticket.get("suggested_leverage")) <= float(config["max_leverage"]),
            f"leverage exceeds {config['max_leverage']}: {ticket.get('suggested_leverage')}",
        ),
        (
            "isolated_margin",
            (not config.get("require_isolated_margin")) or ticket.get("margin_mode") == "isolated",
            f"margin_mode is not isolated: {ticket.get('margin_mode')}",
        ),
        (
            "manual_trades_today",
            len(manual_today) < int(config["max_trades_per_day"]),
            "manual outcomes today already reached max_trades_per_day",
        ),
        (
            "no_losses_today",
            losses_today == 0,
            "manual outcome loss exists today",
        ),
        (
            "daily_loss_limit",
            pnl_usd_today > -float(config["max_daily_loss_usd"]),
            f"daily pnl is at or below -{config['max_daily_loss_usd']} USDT",
        ),
        (
            "human_approval",
            (not config.get("require_human_approval"))
            or _has_human_approval(decisions, ticket_id=ticket_id, signal_id=signal_id),
            "human approval decision is missing",
        ),
        (
            "paper_execution_first",
            (not config.get("require_paper_execution_first"))
            or _has_paper_execution(paper_executions, ticket_id=ticket_id, signal_id=signal_id),
            "paper execution record is missing",
        ),
    ]

    passed_gates = [name for name, passed, _reason in gates if passed]
    failed_gates = [name for name, passed, _reason in gates if not passed]
    blockers = [_reason for _name, passed, _reason in gates if not passed]
    live_safety_status = "WOULD_BE_ALLOWED_IF_LIVE_ENABLED" if not blockers else "BLOCKED"
    next_required_action = (
        "All safety gates passed in explicit simulation. Keep live execution disabled until a future approved phase."
        if live_safety_status == "WOULD_BE_ALLOWED_IF_LIVE_ENABLED"
        else "Keep live execution disabled. Resolve failed gates before any future connector work."
    )

    return {
        "live_safety_status": live_safety_status,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "kill_switch_active": bool(config.get("global_kill_switch")),
        "allow_live_orders": bool(config.get("allow_live_orders")),
        "blockers": list(dict.fromkeys(blockers)),
        "passed_gates": passed_gates,
        "failed_gates": failed_gates,
        "protocol": dict(PROTOCOL_SUMMARY),
        "next_required_action": next_required_action,
        "readiness": readiness,
        "ticket": ticket,
        "exchange_dry_run": exchange_dry_run,
    }


def build_live_safety_text(*, log_dir: str | Path | None = None) -> str:
    payload = build_current_live_safety(log_dir=log_dir)
    return "\n".join(
        [
            "HAMMER RADAR LIVE SAFETY ENVELOPE",
            f"live_safety_status: {payload['live_safety_status']}",
            f"live_execution_enabled: {str(payload['live_execution_enabled']).lower()}",
            f"order_placed: {str(payload['order_placed']).lower()}",
            f"kill_switch_active: {payload['kill_switch_active']}",
            f"allow_live_orders: {payload['allow_live_orders']}",
            f"blockers: {'; '.join(payload['blockers']) if payload['blockers'] else 'none'}",
            f"passed_gates: {', '.join(payload['passed_gates']) if payload['passed_gates'] else 'none'}",
            f"failed_gates: {', '.join(payload['failed_gates']) if payload['failed_gates'] else 'none'}",
            f"next_required_action: {payload['next_required_action']}",
            "Live execution is disabled.",
            "Kill switch is active by default.",
            "No live order can be placed from this system in the current mode.",
        ]
    )


def _has_human_approval(records: list[dict[str, Any]], *, ticket_id: object, signal_id: object) -> bool:
    for record in records:
        ticket = record.get("ticket") or {}
        if record.get("action") == "approve_paper_ticket" and ticket.get("ticket_id") == ticket_id:
            return True
        if record.get("decision") in {"approve_manual_live", "approve_paper_ticket"} and record.get("signal_id") == signal_id:
            return True
    return False


def _has_paper_execution(records: list[dict[str, Any]], *, ticket_id: object, signal_id: object) -> bool:
    return any(
        record.get("ticket_id") == ticket_id
        or (ticket_id is None and record.get("signal_id") == signal_id)
        or (ticket_id is not None and record.get("signal_id") == signal_id)
        for record in records
    )


def _manual_outcomes_today(records: list[dict[str, Any]], *, today: date) -> list[dict[str, Any]]:
    return [record for record in records if _record_date(record.get("created_at")) == today]


def _losses_today(readiness: dict[str, Any], records_today: list[dict[str, Any]]) -> int:
    if records_today:
        return sum(1 for record in records_today if record.get("result") == "loss")
    state = readiness.get("current_state") or {}
    if "losses_today" in state:
        return int(state.get("losses_today") or 0)
    return 0


def _pnl_today(readiness: dict[str, Any], records_today: list[dict[str, Any]]) -> float:
    if records_today:
        return sum(float(record.get("pnl_usd") or 0.0) for record in records_today)
    state = readiness.get("current_state") or {}
    if "pnl_usd_today" in state:
        return float(state.get("pnl_usd_today") or 0.0)
    return 0.0


def _record_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).date()


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
