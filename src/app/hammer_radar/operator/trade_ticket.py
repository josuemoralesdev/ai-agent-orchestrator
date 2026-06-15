"""Machine-prepared paper/manual trade tickets for Hammer Radar.

Tickets are proposals only. This module never places orders and never enables
live execution.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Mapping
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
from src.app.hammer_radar.operator.tiny_live_risk_contract_validation import (
    DEFAULT_OFFICIAL_LANE_KEY as TINY_LIVE_OFFICIAL_LANE_KEY,
    DEFAULT_RISK_CONTRACT_CONFIG_PATH,
    EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE,
    R267_MAX_POSITION_NOTIONAL_USDT,
    build_tiny_live_risk_contract_validation_summary,
    load_tiny_live_risk_contract_for_lane,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    build_exact_lane_risk_contract_status,
    build_strategy_lane_qualification,
)

TRADE_TICKETS_FILENAME = "trade_tickets.ndjson"
DEFAULT_ENTRY_MODE = "ladder_close_50_618"
PAPER_EXECUTION_ENABLED = False
PAPER_ORDER_PLACED = False
SUBMIT_ATTEMPTED = False
BINANCE_ORDER_ENDPOINT_CALLED = False
REAL_ORDER_PLACED = False
DEFAULT_MAX_RISK_USD = 5.0
DEFAULT_FRESH_MINUTES = 30
MIN_SCORE = 90


def build_trade_ticket(
    *,
    signal_id: str | None = None,
    latest_only: bool = True,
    allow_short: bool = False,
    max_position_usd: float | None = None,
    max_risk_usd: float = DEFAULT_MAX_RISK_USD,
    max_leverage: float | None = None,
    fresh_minutes: int = DEFAULT_FRESH_MINUTES,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    use_active_tiny_live_contract: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    created_at = datetime.now(UTC)
    contract_limits = (
        _active_tiny_live_contract_limits(risk_contract_config_path=risk_contract_config_path)
        if use_active_tiny_live_contract
        else {}
    )
    resolved_max_position_usd = _resolve_max_position_usd(max_position_usd, contract_limits=contract_limits)
    resolved_max_leverage = _resolve_max_leverage(max_leverage, contract_limits=contract_limits)
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
        max_leverage=resolved_max_leverage,
        max_position_usd=resolved_max_position_usd,
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
            max_position_usd=resolved_max_position_usd,
            risk_contract=contract_limits,
        )

    selected_lane_key = build_lane_key(
        symbol=selected.candidate.signal.symbol,
        timeframe=selected.candidate.signal.timeframe,
        direction=selected.candidate.signal.direction,
        entry_mode=DEFAULT_ENTRY_MODE,
    )
    strategy_qualification = build_strategy_lane_qualification(
        symbol=selected.candidate.signal.symbol,
        timeframe=selected.candidate.signal.timeframe,
        direction=selected.candidate.signal.direction,
        entry_mode=DEFAULT_ENTRY_MODE,
        log_dir=resolved_log_dir,
    )
    exact_risk_contract_status = build_exact_lane_risk_contract_status(
        lane_key=selected_lane_key,
        risk_contract_config_path=risk_contract_config_path,
        strategy_qualification=strategy_qualification,
    )
    contract_limits = _active_tiny_live_contract_limits(
        risk_contract_config_path=risk_contract_config_path,
        official_lane_key=selected_lane_key,
    )
    candidate_contract_limits = contract_limits if contract_limits.get("risk_contract_valid") else {}
    ticket_max_position_usd = (
        _resolve_max_position_usd(max_position_usd, contract_limits=contract_limits)
        if candidate_contract_limits
        else float(max_position_usd or R267_MAX_POSITION_NOTIONAL_USDT)
    )
    ticket_max_leverage = (
        _resolve_max_leverage(max_leverage, contract_limits=contract_limits)
        if candidate_contract_limits
        else float(max_leverage or 10.0)
    )
    candidate_blockers = _candidate_blockers(
        selected,
        allow_short=allow_short,
        max_position_usd=ticket_max_position_usd,
        max_leverage=ticket_max_leverage,
    )
    blockers.extend(candidate_blockers)
    blockers.extend(_strategy_ticket_blockers(strategy_qualification, exact_risk_contract_status))
    if readiness.get("readiness_status") != "READY":
        blockers.append("readiness is NOT_READY")
    if LIVE_EXECUTION_ENABLED is not False:
        blockers.append("live_execution_enabled safety field is not false")
    if ORDER_PLACED is not False:
        blockers.append("order_placed safety field is not false")
    status = "PROPOSED" if not blockers else ("EXPIRED" if selected.freshness_status == "expired" else "BLOCKED")
    signal_origin = build_signal_origin_status(
        signal_id=selected.candidate.signal.signal_id,
        symbol=selected.candidate.signal.symbol,
        timeframe=selected.candidate.signal.timeframe,
        direction=selected.candidate.signal.direction,
        entry_mode=DEFAULT_ENTRY_MODE,
        log_dir=resolved_log_dir,
    )
    if signal_origin.get("manual_unlock_allowed") is not True:
        blockers.extend(str(item) for item in signal_origin.get("blocked_by") or [])
        status = "EXPIRED" if selected.freshness_status == "expired" else "BLOCKED"
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
        max_position_usd=ticket_max_position_usd,
        max_risk_usd=max_risk_usd,
        max_leverage=ticket_max_leverage,
        archive_log_dir=resolved_log_dir,
        risk_contract=contract_limits,
        candidate_contract_limits=candidate_contract_limits,
        strategy_qualification=strategy_qualification,
        exact_risk_contract_status=exact_risk_contract_status,
        signal_origin=signal_origin,
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


def _strategy_ticket_blockers(
    strategy_qualification: Mapping[str, Any],
    exact_risk_contract_status: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if strategy_qualification.get("strategy_qualified") is not True:
        blockers.extend(str(item) for item in strategy_qualification.get("blocked_by") or [])
        if not strategy_qualification.get("evidence_found"):
            blockers.append("strategy_evidence_missing")
    if exact_risk_contract_status.get("exact_contract_found") is not True:
        blockers.append("exact_lane_risk_contract_missing")
    if exact_risk_contract_status.get("risk_contract_valid") is not True:
        blockers.extend(str(item) for item in exact_risk_contract_status.get("blocked_by") or [])
    return list(dict.fromkeys(blockers))


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
    risk_contract: dict[str, Any],
    candidate_contract_limits: dict[str, Any],
    strategy_qualification: dict[str, Any],
    exact_risk_contract_status: dict[str, Any],
    signal_origin: dict[str, Any],
) -> dict[str, Any]:
    signal = check.candidate.signal
    lane_key = build_lane_key(
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        direction=signal.direction,
        entry_mode=DEFAULT_ENTRY_MODE,
    )
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
        "entry_mode": DEFAULT_ENTRY_MODE,
        "lane_key": lane_key,
        "entry": check.entry,
        "stop": check.stop,
        "take_profit": check.take_profit,
        "risk_distance_pct": risk_distance_pct,
        "max_position_usd": float(max_position_usd),
        "active_contract_mode": risk_contract.get("tiny_live_contract_mode"),
        "active_contract_leverage": risk_contract.get("leverage"),
        "active_contract_max_notional_usdt": risk_contract.get("max_position_notional_usdt"),
        "active_contract_max_position_notional_usdt": risk_contract.get("max_position_notional_usdt"),
        "active_contract_margin_budget_usdt": risk_contract.get("derived_margin_budget_usdt"),
        "suggested_position_usd": suggested_position_usd,
        "suggested_leverage": _suggested_ticket_leverage(max_leverage, contract_limits=candidate_contract_limits),
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
        "signal_origin": signal_origin,
        "strategy_qualification": strategy_qualification,
        "strategy_qualified": strategy_qualification.get("strategy_qualified") is True,
        "strategy_win_rate_pct": strategy_qualification.get("win_rate_pct"),
        "strategy_sample_count": strategy_qualification.get("sample_count"),
        "strategy_avg_pnl_pct": strategy_qualification.get("avg_pnl_pct"),
        "strategy_min_sample": strategy_qualification.get("min_sample"),
        "exact_risk_contract_status": exact_risk_contract_status,
        "exact_risk_contract_found": exact_risk_contract_status.get("exact_contract_found") is True,
        "exact_risk_contract_valid": exact_risk_contract_status.get("risk_contract_valid") is True,
        "signal_origin_family": signal_origin.get("signal_origin_family"),
        "betrayal_mode_involved": signal_origin.get("betrayal_mode_involved"),
        "betrayal_inverse_involved": signal_origin.get("betrayal_inverse_involved"),
        "promotion_family": signal_origin.get("promotion_family"),
        "promotion_status": signal_origin.get("promotion_status"),
        "candidate_origin_classification": signal_origin.get("candidate_origin_classification"),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "submit_attempted": SUBMIT_ATTEMPTED,
        "binance_order_endpoint_called": BINANCE_ORDER_ENDPOINT_CALLED,
        "real_order_placed": REAL_ORDER_PLACED,
        "risk_contract": risk_contract,
        "ticket_status": ticket_status,
    }


def _blocked_ticket(
    *,
    created_at: datetime,
    readiness: dict[str, Any],
    blockers: list[str],
    machine_reason: str,
    archive_log_dir: Path,
    max_position_usd: float,
    risk_contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ticket_id": None,
        "created_at": created_at.isoformat(),
        "archive_log_dir": str(archive_log_dir),
        "signal_id": None,
        "symbol": PROTOCOL["symbol"],
        "direction": None,
        "timeframe": None,
        "entry_mode": None,
        "lane_key": None,
        "entry": None,
        "stop": None,
        "take_profit": None,
        "risk_distance_pct": None,
        "max_position_usd": float(max_position_usd),
        "active_contract_mode": risk_contract.get("tiny_live_contract_mode"),
        "active_contract_leverage": risk_contract.get("leverage"),
        "active_contract_max_notional_usdt": risk_contract.get("max_position_notional_usdt"),
        "active_contract_max_position_notional_usdt": risk_contract.get("max_position_notional_usdt"),
        "active_contract_margin_budget_usdt": risk_contract.get("derived_margin_budget_usdt"),
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
        "signal_origin": _unknown_signal_origin_status(blocked_by=["no_current_proposed_ticket"]),
        "signal_origin_family": "unknown",
        "betrayal_mode_involved": "unknown",
        "betrayal_inverse_involved": "unknown",
        "promotion_family": "unknown",
        "promotion_status": "unknown",
        "candidate_origin_classification": "unknown",
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "submit_attempted": SUBMIT_ATTEMPTED,
        "binance_order_endpoint_called": BINANCE_ORDER_ENDPOINT_CALLED,
        "real_order_placed": REAL_ORDER_PLACED,
        "risk_contract": risk_contract,
        "ticket_status": "BLOCKED",
    }


def _recreate_ticket_for_id(ticket_id: str, *, log_dir: Path) -> dict[str, Any] | None:
    contract_limits = _active_tiny_live_contract_limits()
    max_position_usd = _resolve_max_position_usd(None, contract_limits=contract_limits)
    max_leverage = _resolve_max_leverage(None, contract_limits=contract_limits)
    snapshot = build_live_candidate_snapshot(
        limit=1000,
        since_hours=24,
        min_score=MIN_SCORE,
        symbol=PROTOCOL["symbol"],
        allow_short=True,
        allow_oversold=False,
        allow_trigger_flags=False,
        max_risk_usd=DEFAULT_MAX_RISK_USD,
        max_leverage=max_leverage,
        max_position_usd=max_position_usd,
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


def _suggested_ticket_leverage(max_leverage: float, *, contract_limits: dict[str, Any]) -> float:
    if contract_limits.get("risk_contract_valid") and contract_limits.get("suggested_leverage") is not None:
        return round(float(contract_limits["suggested_leverage"]), 4)
    if float(max_leverage) > float(PROTOCOL["max_leverage"]):
        return round(float(max_leverage), 4)
    return round(min(float(PROTOCOL["preferred_leverage"]), float(max_leverage)), 4)


def _active_tiny_live_contract_limits(
    *,
    risk_contract_config_path: str | Path | None = None,
    official_lane_key: str = TINY_LIVE_OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    path = (
        Path(risk_contract_config_path)
        if risk_contract_config_path is not None
        else DEFAULT_RISK_CONTRACT_CONFIG_PATH
    )
    loaded = load_tiny_live_risk_contract_for_lane(risk_contract_config_path=path, official_lane_key=official_lane_key)
    contract = loaded.get("contract") if isinstance(loaded.get("contract"), dict) else {}
    summary = build_tiny_live_risk_contract_validation_summary(risk_contract=loaded)
    official_contract_found = bool(loaded.get("official_contract_found"))
    max_position_notional = summary.get("max_position_notional_usdt")
    leverage = summary.get("leverage")
    derived_margin_budget = summary.get("derived_margin_budget_usdt")
    if not official_contract_found:
        max_position_notional = R267_MAX_POSITION_NOTIONAL_USDT
        leverage = 10.0
        derived_margin_budget = 8.0
    return {
        "found": bool(loaded.get("found")),
        "path": str(loaded.get("path") or path),
        "official_lane_key": official_lane_key,
        "official_contract_found": official_contract_found,
        "risk_contract_valid": official_contract_found and bool(summary.get("risk_contract_valid")),
        "tiny_live_contract_mode": summary.get("tiny_live_contract_mode")
        if official_contract_found
        else EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE,
        "max_position_notional_usdt": max_position_notional,
        "max_notional_usdt": max_position_notional,
        "max_position_usd": max_position_notional,
        "suggested_leverage": leverage,
        "leverage": leverage,
        "derived_margin_budget_usdt": derived_margin_budget,
        "margin_budget_usdt": derived_margin_budget,
        "max_loss_usdt": summary.get("max_loss_usdt"),
        "blocked_by": list(summary.get("blocked_by") or []),
        "contract_symbol": contract.get("symbol"),
        "contract_timeframe": contract.get("timeframe"),
        "contract_direction": contract.get("direction"),
        "contract_entry_mode": contract.get("entry_mode"),
        "live_execution_enabled": summary.get("live_execution_enabled") is True,
    }


def _resolve_max_position_usd(value: float | None, *, contract_limits: dict[str, Any]) -> float:
    contract_cap = contract_limits.get("max_position_usd")
    if contract_limits.get("risk_contract_valid") and contract_cap is not None:
        if value is not None:
            return min(float(value), float(contract_cap))
        return float(contract_cap)
    if value is not None:
        return float(value)
    return float(PROTOCOL["max_position_usd"])


def _resolve_max_leverage(value: float | None, *, contract_limits: dict[str, Any]) -> float:
    if value is not None:
        return float(value)
    contract_leverage = contract_limits.get("suggested_leverage")
    if (
        contract_limits.get("risk_contract_valid")
        and contract_limits.get("tiny_live_contract_mode") == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE
        and contract_leverage is not None
    ):
        return float(contract_leverage)
    return float(PROTOCOL["max_leverage"])


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


def build_lane_key(
    *,
    symbol: object,
    timeframe: object,
    direction: object,
    entry_mode: object = DEFAULT_ENTRY_MODE,
) -> str:
    return "|".join(
        [
            str(symbol or ""),
            str(timeframe or ""),
            str(direction or ""),
            str(entry_mode or DEFAULT_ENTRY_MODE),
        ]
    )


def build_signal_origin_status(
    *,
    signal_id: str | None,
    symbol: str | None,
    timeframe: str | None,
    direction: str | None,
    entry_mode: str | None = DEFAULT_ENTRY_MODE,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    lane_key = build_lane_key(
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        entry_mode=entry_mode or DEFAULT_ENTRY_MODE,
    )
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    row = _find_origin_row(resolved_log_dir, signal_id=signal_id, lane_key=lane_key)
    if row is None:
        return _unknown_signal_origin_status(
            signal_id=signal_id,
            lane_key=lane_key,
            blocked_by=["needs_manual_origin_review"],
        )

    family = _first_string(
        row,
        "signal_origin_family",
        "origin_family",
        "family",
        "source_family",
    )
    source_type = _first_string(row, "source_type", "source_identity", "candidate_id", "identity")
    variant = _first_string(row, "signal_origin_variant", "origin_variant", "variant")
    text = " ".join(str(value or "") for value in (family, source_type, variant, row.get("lane_key")))
    lowered = text.lower()
    betrayal_mode: bool | str = "betrayal" in lowered
    inverse_mode: bool | str = "inverse" in lowered or str(direction or "").lower() == "inverse"
    if family is None:
        family = "betrayal" if betrayal_mode else "standard"
    classification = (
        "inverse-derived"
        if inverse_mode is True
        else "betrayal-derived"
        if betrayal_mode is True
        else "standard checklist"
        if str(family).lower() in {"standard", "normal", "checklist", "live_checklist"}
        else "unknown"
    )
    promotion = _promotion_status_for_lane(resolved_log_dir, lane_key=lane_key)
    blocked_by: list[str] = []
    if betrayal_mode is True or inverse_mode is True:
        blocked_by.append("betrayal_first_tiny_live_not_explicitly_accepted")
    if classification == "unknown":
        blocked_by.append("needs_manual_origin_review")
    return {
        "signal_id": signal_id,
        "lane_key": lane_key,
        "signal_origin_family": family,
        "betrayal_mode_involved": betrayal_mode,
        "betrayal_inverse_involved": inverse_mode,
        "promotion_family": promotion.get("promotion_family"),
        "promotion_status": promotion.get("promotion_status"),
        "promotion_record": promotion.get("promotion_record"),
        "candidate_origin_classification": classification,
        "manual_unlock_allowed": not blocked_by,
        "blocked_by": list(dict.fromkeys(blocked_by)),
        "source_record_found": True,
        "source_record_path": row.get("_source_path"),
    }


def _unknown_signal_origin_status(
    *,
    signal_id: str | None = None,
    lane_key: str | None = None,
    blocked_by: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "signal_id": signal_id,
        "lane_key": lane_key,
        "signal_origin_family": "unknown",
        "betrayal_mode_involved": "unknown",
        "betrayal_inverse_involved": "unknown",
        "promotion_family": "unknown",
        "promotion_status": "unknown",
        "promotion_record": {},
        "candidate_origin_classification": "unknown",
        "manual_unlock_allowed": False,
        "blocked_by": list(dict.fromkeys(blocked_by or ["needs_manual_origin_review"])),
        "source_record_found": False,
        "source_record_path": None,
    }


def _find_origin_row(log_dir: Path, *, signal_id: str | None, lane_key: str) -> dict[str, Any] | None:
    filenames = [
        "betrayal_signal_origin_integration_contract.ndjson",
        "betrayal_source_identity_normalizer.ndjson",
        "betrayal_source_identity_evidence_collector.ndjson",
        "betrayal_paper_signals.ndjson",
        "signals.ndjson",
        "strategy_promotion_status.ndjson",
    ]
    for filename in filenames:
        for row in _read_ndjson_reverse(log_dir / filename):
            candidates = _candidate_origin_rows(row)
            for candidate in candidates:
                candidate_signal_id = candidate.get("signal_id") or candidate.get("emitted_signal_id")
                candidate_lane = candidate.get("lane_key") or candidate.get("strategy_key") or _lane_key_from_mapping(candidate)
                if signal_id and candidate_signal_id == signal_id:
                    return {**candidate, "_source_path": str(log_dir / filename)}
                if candidate_lane == lane_key:
                    return {**candidate, "_source_path": str(log_dir / filename)}
    return None


def _candidate_origin_rows(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [dict(row)]
    for key in (
        "normalized_source_rows_preview",
        "source_identity_evidence_rows",
        "paper_signal_rows",
        "emitted_signal_rows",
        "promotion_ready",
        "near_promotion",
        "blocked_candidates",
    ):
        value = row.get(key)
        if isinstance(value, list):
            rows.extend(dict(item) for item in value if isinstance(item, Mapping))
    return rows


def _promotion_status_for_lane(log_dir: Path, *, lane_key: str) -> dict[str, Any]:
    for row in _read_ndjson_reverse(log_dir / "strategy_promotion_status.ndjson"):
        for candidate in _candidate_origin_rows(row):
            candidate_lane = candidate.get("strategy_key") or candidate.get("lane_key") or _lane_key_from_mapping(candidate)
            if candidate_lane == lane_key:
                event = str(candidate.get("event_type") or "")
                status = "promotion_ready" if event == "STRATEGY_PROMOTION_READY" else "known_not_promotion_ready"
                return {
                    "promotion_family": "standard",
                    "promotion_status": status,
                    "promotion_record": candidate,
                }
    return {"promotion_family": "unknown", "promotion_status": "unknown", "promotion_record": {}}


def _read_ndjson_reverse(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
    return list(reversed(records))


def _lane_key_from_mapping(row: Mapping[str, Any]) -> str | None:
    if not any(row.get(key) for key in ("symbol", "timeframe", "direction")):
        return None
    return build_lane_key(
        symbol=row.get("symbol") or PROTOCOL["symbol"],
        timeframe=row.get("timeframe"),
        direction=row.get("direction") or row.get("betrayal_direction"),
        entry_mode=row.get("entry_mode") or DEFAULT_ENTRY_MODE,
    )


def _first_string(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _format_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
