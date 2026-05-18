"""R85 non-executable tiny-live ticket builder.

This module builds local operator-review tickets only. It never creates signed
order payloads, calls Binance, checks balances, or enables execution.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.live_arming_preflight import (
    BLOCKED_BY_MISSING_OPERATOR_APPROVAL,
    build_live_arming_preflight,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    DEFAULT_CANDIDATE_ID,
    risk_contract_hash as canonical_risk_contract_hash,
    stable_json,
)

PHASE = "R85"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "EXACT_OPERATOR_APPROVAL_NON_EXECUTABLE_TICKET_BUILDER_ONLY_NO_ORDER"
TICKETS_FILENAME = "tiny_live_tickets.ndjson"

TICKET_DRY_RUN_ONLY = "TICKET_DRY_RUN_ONLY"
TICKET_CREATED_FOR_OPERATOR_REVIEW = "TICKET_CREATED_FOR_OPERATOR_REVIEW"
TICKET_BLOCKED_BY_PREFLIGHT = "TICKET_BLOCKED_BY_PREFLIGHT"
TICKET_BLOCKED_BY_MISSING_OPERATOR_APPROVAL = "TICKET_BLOCKED_BY_MISSING_OPERATOR_APPROVAL"
TICKET_APPROVAL_REQUIRED = "TICKET_APPROVAL_REQUIRED"
TICKET_INVALID_CANDIDATE = "TICKET_INVALID_CANDIDATE"
TICKET_NON_EXECUTABLE_REVIEW_ONLY = "TICKET_NON_EXECUTABLE_REVIEW_ONLY"

MISSING_OPERATOR_APPROVAL = "MISSING_OPERATOR_APPROVAL"
OPERATOR_APPROVAL_REQUIRED = "OPERATOR_APPROVAL_REQUIRED"
OPERATOR_APPROVAL_RECORDED_FOR_REVIEW = "OPERATOR_APPROVAL_RECORDED_FOR_REVIEW"
OPERATOR_APPROVAL_REJECTED = "OPERATOR_APPROVAL_REJECTED"
OPERATOR_APPROVAL_EXPIRED = "OPERATOR_APPROVAL_EXPIRED"
OPERATOR_APPROVAL_INVALID = "OPERATOR_APPROVAL_INVALID"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R85 creates non-executable operator-review tickets only. No orders, no signed payloads, no Binance."


def build_tiny_live_ticket(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    approval_phrase: str | None = None,
    operator_note: str | None = None,
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    created_at = datetime.now(UTC)
    preflight = build_live_arming_preflight(candidate_id=candidate_id, log_dir=resolved_log_dir)
    top = preflight.get("top_candidate_preflight") if isinstance(preflight.get("top_candidate_preflight"), dict) else {}
    risk = preflight.get("risk_contract") if isinstance(preflight.get("risk_contract"), dict) else {}
    funding = preflight.get("funding_preflight") if isinstance(preflight.get("funding_preflight"), dict) else {}
    live_env = preflight.get("live_env_preflight") if isinstance(preflight.get("live_env_preflight"), dict) else {}

    selected_candidate_id = str(top.get("candidate_id") or "")
    risk_hash = risk_contract_hash(risk)
    required_phrase = approval_phrase_for(candidate_id=selected_candidate_id or candidate_id, risk_contract_hash=risk_hash)
    approval_status = _approval_status(approval_phrase=approval_phrase, required_phrase=required_phrase)
    ticket_status = _ticket_status(
        preflight=preflight,
        selected_candidate_id=selected_candidate_id,
        requested_candidate_id=candidate_id,
        approval_status=approval_status,
        dry_run=dry_run,
        write=write,
    )
    ticket = _ticket_payload(
        candidate_id=selected_candidate_id or candidate_id,
        created_at=created_at,
        preflight=preflight,
        top=top,
        risk=risk,
        funding=funding,
        live_env=live_env,
        risk_hash=risk_hash,
        approval_status=approval_status,
        required_phrase=required_phrase,
        ticket_status=ticket_status,
        operator_note=operator_note,
        dry_run=dry_run,
        write=write,
        log_dir=resolved_log_dir,
    )
    ticket_written = False
    if write and not dry_run:
        append_tiny_live_ticket(ticket, log_dir=resolved_log_dir)
        ticket_written = True
        ticket["ticket_status"] = (
            TICKET_CREATED_FOR_OPERATOR_REVIEW
            if approval_status == OPERATOR_APPROVAL_RECORDED_FOR_REVIEW
            else TICKET_BLOCKED_BY_MISSING_OPERATOR_APPROVAL
        )
        ticket["ticket_written"] = True
    return _sanitize(
        {
            **ticket,
            "ticket_written": ticket_written,
            "notes": [
                NO_ORDER_NOTE,
                "Exact R85 approval records review only. It is not exchange execution approval.",
                "R86 must still handle live env arming checklist and manual funding confirmation.",
            ],
            **_safety_fields(),
        }
    )


def build_tiny_live_tickets_payload(
    *,
    limit: int = 20,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_tiny_live_tickets(limit=limit, candidate_id=candidate_id, log_dir=resolved_log_dir)
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "ticket_path": str(tiny_live_tickets_path(resolved_log_dir)),
            "summary": {
                "tickets_returned": len(records),
                "written_ticket_records": len(load_tiny_live_tickets(limit=0, candidate_id=candidate_id, log_dir=resolved_log_dir)),
                "executable_ticket_records": 0,
                "order_payload_records": 0,
            },
            "tickets": records,
            "notes": [NO_ORDER_NOTE],
            **_safety_fields(),
        }
    )


def risk_contract_hash(snapshot: Mapping[str, Any]) -> str:
    return canonical_risk_contract_hash(snapshot)


def approval_phrase_for(*, candidate_id: str, risk_contract_hash: str) -> str:
    return f"APPROVE_TINY_LIVE_REVIEW {candidate_id} {risk_contract_hash}"


def tiny_live_tickets_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / TICKETS_FILENAME


def append_tiny_live_ticket(ticket: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = tiny_live_tickets_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(dict(ticket)), sort_keys=True) + "\n")


def load_tiny_live_tickets(
    *,
    limit: int = 20,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = tiny_live_tickets_path(log_dir)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if candidate_id and record.get("candidate_id") != candidate_id:
                continue
            records.append(_sanitize(record))
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def format_tiny_live_ticket_text(payload: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"R85 Tiny Live Ticket Builder: {payload.get('status')}",
            str(payload.get("execution_mode")),
            f"candidate_id: {payload.get('candidate_id')}",
            f"ticket_id: {payload.get('ticket_id')}",
            f"ticket_status: {payload.get('ticket_status')}",
            f"risk_contract_hash: {payload.get('risk_contract_hash')}",
            f"approval_status: {payload.get('operator_approval_status')}",
            f"approval_phrase_required: {payload.get('approval_phrase_required')}",
            f"dry_run: {payload.get('dry_run')} write: {payload.get('write')} ticket_written: {payload.get('ticket_written')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            NO_ORDER_NOTE,
        ]
    )


def _approval_status(*, approval_phrase: str | None, required_phrase: str) -> str:
    if approval_phrase is None or not str(approval_phrase).strip():
        return MISSING_OPERATOR_APPROVAL
    if str(approval_phrase).strip() == required_phrase:
        return OPERATOR_APPROVAL_RECORDED_FOR_REVIEW
    return OPERATOR_APPROVAL_INVALID


def _ticket_status(
    *,
    preflight: Mapping[str, Any],
    selected_candidate_id: str,
    requested_candidate_id: str,
    approval_status: str,
    dry_run: bool,
    write: bool,
) -> str:
    if not selected_candidate_id or selected_candidate_id != requested_candidate_id:
        return TICKET_INVALID_CANDIDATE
    if preflight.get("final_preflight_status") != BLOCKED_BY_MISSING_OPERATOR_APPROVAL:
        return TICKET_BLOCKED_BY_PREFLIGHT
    if approval_status == OPERATOR_APPROVAL_INVALID:
        return TICKET_BLOCKED_BY_MISSING_OPERATOR_APPROVAL
    if approval_status == MISSING_OPERATOR_APPROVAL:
        return TICKET_APPROVAL_REQUIRED
    if dry_run or not write:
        return TICKET_DRY_RUN_ONLY
    return TICKET_CREATED_FOR_OPERATOR_REVIEW


def _ticket_payload(
    *,
    candidate_id: str,
    created_at: datetime,
    preflight: Mapping[str, Any],
    top: Mapping[str, Any],
    risk: Mapping[str, Any],
    funding: Mapping[str, Any],
    live_env: Mapping[str, Any],
    risk_hash: str,
    approval_status: str,
    required_phrase: str,
    ticket_status: str,
    operator_note: str | None,
    dry_run: bool,
    write: bool,
    log_dir: Path,
) -> dict[str, Any]:
    ticket_id = _ticket_id(candidate_id=candidate_id, risk_hash=risk_hash)
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "ticket_id": ticket_id,
            "ticket_status": ticket_status,
            "candidate_id": candidate_id,
            "symbol": top.get("symbol"),
            "timeframe": top.get("timeframe"),
            "direction": top.get("direction"),
            "entry_mode": top.get("entry_mode"),
            "source_phase": PHASE,
            "source_candidate_status": preflight.get("final_preflight_status"),
            "miro_fish_status": top.get("miro_fish_status"),
            "miro_fish_score": top.get("miro_fish_score"),
            "markov_regime": top.get("markov_regime"),
            "markov_gate_status": top.get("markov_gate_status"),
            "risk_contract_hash": risk_hash,
            "risk_contract_snapshot": dict(risk),
            "funding_config_snapshot": dict(funding),
            "live_env_snapshot": dict(live_env),
            "operator_approval_status": approval_status,
            "approval_status": approval_status,
            "operator_approval_required": True,
            "exact_candidate_id_required": True,
            "exact_risk_contract_hash_required": True,
            "approval_phrase_required": required_phrase,
            "approval_record_required": True,
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + timedelta(hours=24)).isoformat(),
            "operator_note": operator_note or "",
            "dry_run": bool(dry_run),
            "write": bool(write),
            "ticket_written": False,
            "ticket_path": str(tiny_live_tickets_path(log_dir)),
            "review_only": True,
            "executable": False,
            "order_type": "not_created",
            "order_payload_created": False,
            "execution_attempted": False,
            "network_allowed": False,
            "secrets_shown": False,
            "blockers": _ticket_blockers(ticket_status=ticket_status, approval_status=approval_status),
            **_safety_fields(),
        }
    )


def _ticket_id(*, candidate_id: str, risk_hash: str) -> str:
    digest = hashlib.sha256(f"{candidate_id}|{risk_hash}|R85".encode("utf-8")).hexdigest()[:20]
    return f"r85-tiny-live-{digest}"


def _ticket_blockers(*, ticket_status: str, approval_status: str) -> list[str]:
    blockers: list[str] = []
    if ticket_status == TICKET_INVALID_CANDIDATE:
        blockers.append("invalid_candidate")
    if ticket_status == TICKET_BLOCKED_BY_PREFLIGHT:
        blockers.append("preflight_not_ready_for_ticket_review")
    if approval_status in {MISSING_OPERATOR_APPROVAL, OPERATOR_APPROVAL_INVALID}:
        blockers.append("missing_operator_approval" if approval_status == MISSING_OPERATOR_APPROVAL else "operator_approval_invalid")
    return blockers


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in (
            "live_execution_enabled",
            "allow_live_orders",
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "network_allowed",
            "secrets_shown",
            "executable",
        ):
            if key in sanitized:
                sanitized[key] = False
        if "global_kill_switch" in sanitized:
            sanitized["global_kill_switch"] = True
        if "review_only" in sanitized:
            sanitized["review_only"] = True
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
