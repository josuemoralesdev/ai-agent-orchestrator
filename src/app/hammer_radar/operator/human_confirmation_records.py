"""R89 human confirmation review-record ledger.

This module persists local human confirmation records only. It never creates
order payloads, calls Binance, checks balances, mutates env files, or enables
live execution.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.final_human_review_packet import build_final_human_review_packet
from src.app.hammer_radar.operator.live_env_arming_checklist import required_phrases as r86_required_phrases
from src.app.hammer_radar.operator.live_env_boundary_review import build_live_env_boundary_review
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID
from src.app.hammer_radar.operator.tiny_live_ticket_builder import build_tiny_live_ticket

PHASE = "R89"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "HUMAN_CONFIRMATION_REVIEW_RECORD_LEDGER_ONLY_NO_ORDER"
RECORDS_FILENAME = "human_confirmation_records.ndjson"

R85_TINY_LIVE_TICKET_REVIEW_APPROVAL = "R85_TINY_LIVE_TICKET_REVIEW_APPROVAL"
R86_MANUAL_FUNDING_AND_ENV_CHECKLIST = "R86_MANUAL_FUNDING_AND_ENV_CHECKLIST"
R88_FINAL_HUMAN_REVIEW_APPROVAL = "R88_FINAL_HUMAN_REVIEW_APPROVAL"
REQUIRED_RECORD_TYPES = (
    R85_TINY_LIVE_TICKET_REVIEW_APPROVAL,
    R86_MANUAL_FUNDING_AND_ENV_CHECKLIST,
    R88_FINAL_HUMAN_REVIEW_APPROVAL,
)

HUMAN_CONFIRMATION_DRY_RUN_ONLY = "HUMAN_CONFIRMATION_DRY_RUN_ONLY"
HUMAN_CONFIRMATION_REQUIRED = "HUMAN_CONFIRMATION_REQUIRED"
HUMAN_CONFIRMATION_RECORDED_FOR_REVIEW = "HUMAN_CONFIRMATION_RECORDED_FOR_REVIEW"
HUMAN_CONFIRMATION_INVALID_PHRASE = "HUMAN_CONFIRMATION_INVALID_PHRASE"
HUMAN_CONFIRMATION_BLOCKED_BY_SOURCE_CHAIN = "HUMAN_CONFIRMATION_BLOCKED_BY_SOURCE_CHAIN"
HUMAN_CONFIRMATION_NON_EXECUTABLE_REVIEW_ONLY = "HUMAN_CONFIRMATION_NON_EXECUTABLE_REVIEW_ONLY"

REVIEW_RECORDS_MISSING = "REVIEW_RECORDS_MISSING"
REVIEW_RECORDS_PARTIAL = "REVIEW_RECORDS_PARTIAL"
REVIEW_RECORDS_RECORDED_FOR_REVIEW = "REVIEW_RECORDS_RECORDED_FOR_REVIEW"
REVIEW_RECORDS_BLOCKED_BY_LIVE_ENV_BOUNDARY = "REVIEW_RECORDS_BLOCKED_BY_LIVE_ENV_BOUNDARY"
REVIEW_RECORDS_NON_EXECUTABLE_ONLY = "REVIEW_RECORDS_NON_EXECUTABLE_ONLY"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R89 records local human confirmations only. No orders, no payloads, no env changes, no network, no Binance."


def build_human_confirmation_records(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    r85_approval_phrase: str | None = None,
    r86_manual_funding_phrase: str | None = None,
    r86_live_env_review_phrase: str | None = None,
    r86_max_loss_ack_phrase: str | None = None,
    r86_exact_candidate_ack_phrase: str | None = None,
    r88_final_approval_phrase: str | None = None,
    operator_note: str | None = None,
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    created_at = datetime.now(UTC)
    source = build_source_snapshot(candidate_id=candidate_id, log_dir=resolved_log_dir)
    attempts = _attempts(
        source=source,
        r85_approval_phrase=r85_approval_phrase,
        r86_manual_funding_phrase=r86_manual_funding_phrase,
        r86_live_env_review_phrase=r86_live_env_review_phrase,
        r86_max_loss_ack_phrase=r86_max_loss_ack_phrase,
        r86_exact_candidate_ack_phrase=r86_exact_candidate_ack_phrase,
        r88_final_approval_phrase=r88_final_approval_phrase,
        dry_run=dry_run,
        write=write,
    )

    records_to_write = [
        _record_payload(
            created_at=created_at,
            source=source,
            attempt=attempt,
            operator_note=operator_note,
            dry_run=dry_run,
            write=write,
            log_dir=resolved_log_dir,
        )
        for attempt in attempts
        if attempt["phrase_matched"] and not dry_run and write
    ]
    for record in records_to_write:
        append_human_confirmation_record(record, log_dir=resolved_log_dir)

    written_records = load_human_confirmation_records(limit=0, candidate_id=source["candidate_id"], log_dir=resolved_log_dir)
    latest_records = _latest_by_type(written_records)
    unified_status = _unified_status(latest_records)
    record_statuses = {attempt["record_type"]: attempt["record_status"] for attempt in attempts}

    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "candidate_id": source["candidate_id"],
            "risk_contract_hash": source["risk_contract_hash"],
            "packet_hash": source["packet_hash"],
            "human_confirmation_records_path": str(human_confirmation_records_path(resolved_log_dir)),
            "dry_run": bool(dry_run),
            "write": bool(write),
            "records_written": len(records_to_write),
            "record_statuses": record_statuses,
            "phrase_checks": attempts,
            "required_phrases": source["required_phrases"],
            "required_phrase_hashes": _phrase_hashes(source["required_phrases"]),
            "summary": _summary(written_records, latest_records),
            "latest_records": list(latest_records.values()),
            "unified_readiness_status": unified_status,
            "r87_boundary_status": source["r87_boundary_status"],
            "r87_execution_boundary_status": source["r87_execution_boundary_status"],
            "review_only": True,
            "executable": False,
            "env_modified": False,
            "order_type": "not_created",
            "order_payload_created": False,
            "execution_attempted": False,
            "network_allowed": False,
            "secrets_shown": False,
            "notes": [
                NO_ORDER_NOTE,
                "Persisted review records are not execution permission.",
                "R87 live-env boundary remains authoritative and blocks arming.",
            ],
            **_safety_fields(),
        }
    )


def build_human_confirmation_records_status(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    limit: int = 20,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = build_source_snapshot(candidate_id=candidate_id, log_dir=resolved_log_dir)
    records = load_human_confirmation_records(limit=limit, candidate_id=source["candidate_id"], log_dir=resolved_log_dir)
    all_records = load_human_confirmation_records(limit=0, candidate_id=source["candidate_id"], log_dir=resolved_log_dir)
    latest_records = _latest_by_type(all_records)
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "candidate_id": source["candidate_id"],
            "risk_contract_hash": source["risk_contract_hash"],
            "packet_hash": source["packet_hash"],
            "human_confirmation_records_path": str(human_confirmation_records_path(resolved_log_dir)),
            "summary": _summary(all_records, latest_records),
            "records": records,
            "latest_records": list(latest_records.values()),
            "required_phrases": source["required_phrases"],
            "required_phrase_hashes": _phrase_hashes(source["required_phrases"]),
            "unified_readiness_status": _unified_status(latest_records),
            "r87_boundary_status": source["r87_boundary_status"],
            "r87_execution_boundary_status": source["r87_execution_boundary_status"],
            "review_only": True,
            "executable": False,
            "env_modified": False,
            "order_type": "not_created",
            "order_payload_created": False,
            "execution_attempted": False,
            "network_allowed": False,
            "secrets_shown": False,
            "notes": [NO_ORDER_NOTE, "Read-only status. Persisted records remain non-executable."],
            **_safety_fields(),
        }
    )


def build_source_snapshot(*, candidate_id: str, log_dir: str | Path | None = None) -> dict[str, Any]:
    ticket = build_tiny_live_ticket(candidate_id=candidate_id, dry_run=True, write=False, log_dir=log_dir)
    risk_hash = str(ticket.get("risk_contract_hash") or "")
    selected_candidate_id = str(ticket.get("candidate_id") or candidate_id)
    packet = build_final_human_review_packet(candidate_id=selected_candidate_id, dry_run=True, write=False, log_dir=log_dir)
    boundary = build_live_env_boundary_review(candidate_id=selected_candidate_id, dry_run=True, write=False, log_dir=log_dir)
    required = {
        "r85_approval_phrase": str(ticket.get("approval_phrase_required") or ""),
        **r86_required_phrases(candidate_id=selected_candidate_id, risk_contract_hash=risk_hash),
        "r88_final_approval_phrase": str(packet.get("final_approval_phrase_required") or ""),
    }
    return _sanitize(
        {
            "candidate_id": selected_candidate_id,
            "risk_contract_hash": risk_hash,
            "packet_hash": str(packet.get("packet_hash") or ""),
            "required_phrases": required,
            "r85_ticket_snapshot": {
                "phase": ticket.get("phase"),
                "ticket_id": ticket.get("ticket_id"),
                "ticket_status": ticket.get("ticket_status"),
                "operator_approval_status": ticket.get("operator_approval_status"),
                "review_only": ticket.get("review_only"),
                "executable": ticket.get("executable"),
            },
            "r88_packet_snapshot": {
                "phase": packet.get("phase"),
                "packet_id": packet.get("packet_id"),
                "packet_status": packet.get("packet_status"),
                "final_human_approval_status": packet.get("final_human_approval_status"),
                "review_only": packet.get("review_only"),
                "executable": packet.get("executable"),
            },
            "r87_boundary_status": boundary.get("boundary_status"),
            "r87_execution_boundary_status": (boundary.get("execution_boundary_review") or {}).get("boundary_status"),
        }
    )


def phrase_hash(phrase: str | None) -> str | None:
    if phrase is None:
        return None
    return hashlib.sha256(str(phrase).strip().encode("utf-8")).hexdigest()


def human_confirmation_records_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / RECORDS_FILENAME


def append_human_confirmation_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = human_confirmation_records_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(dict(record)), sort_keys=True) + "\n")


def load_human_confirmation_records(
    *,
    limit: int = 20,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = human_confirmation_records_path(log_dir)
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


def format_human_confirmation_records_text(payload: Mapping[str, Any]) -> str:
    statuses = payload.get("record_statuses") if isinstance(payload.get("record_statuses"), dict) else {}
    return "\n".join(
        [
            f"R89 Human Confirmation Records status: {payload.get('status')}",
            str(payload.get("execution_mode")),
            f"candidate_id: {payload.get('candidate_id')}",
            f"risk_contract_hash: {payload.get('risk_contract_hash')}",
            f"packet_hash: {payload.get('packet_hash')}",
            f"unified_readiness_status: {payload.get('unified_readiness_status')}",
            f"r87_boundary_status: {payload.get('r87_boundary_status')}",
            f"dry_run: {payload.get('dry_run')} write: {payload.get('write')} records_written: {payload.get('records_written', 0)}",
            f"r85_record_status: {statuses.get(R85_TINY_LIVE_TICKET_REVIEW_APPROVAL, 'n/a')}",
            f"r86_record_status: {statuses.get(R86_MANUAL_FUNDING_AND_ENV_CHECKLIST, 'n/a')}",
            f"r88_record_status: {statuses.get(R88_FINAL_HUMAN_REVIEW_APPROVAL, 'n/a')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            "No-order/no-network/no-env-change safety note: R89 is review-record persistence only.",
            NO_ORDER_NOTE,
        ]
    )


def _attempts(
    *,
    source: Mapping[str, Any],
    r85_approval_phrase: str | None,
    r86_manual_funding_phrase: str | None,
    r86_live_env_review_phrase: str | None,
    r86_max_loss_ack_phrase: str | None,
    r86_exact_candidate_ack_phrase: str | None,
    r88_final_approval_phrase: str | None,
    dry_run: bool,
    write: bool,
) -> list[dict[str, Any]]:
    required = source["required_phrases"]
    r86_values = {
        "manual_funding_phrase": r86_manual_funding_phrase,
        "live_env_review_phrase": r86_live_env_review_phrase,
        "max_loss_ack_phrase": r86_max_loss_ack_phrase,
        "exact_candidate_ack_phrase": r86_exact_candidate_ack_phrase,
    }
    return [
        _single_attempt(
            record_type=R85_TINY_LIVE_TICKET_REVIEW_APPROVAL,
            source_phase="R85",
            supplied_phrase=r85_approval_phrase,
            expected_phrase=required["r85_approval_phrase"],
            dry_run=dry_run,
            write=write,
        ),
        _r86_attempt(required=required, supplied=r86_values, dry_run=dry_run, write=write),
        _single_attempt(
            record_type=R88_FINAL_HUMAN_REVIEW_APPROVAL,
            source_phase="R88",
            supplied_phrase=r88_final_approval_phrase,
            expected_phrase=required["r88_final_approval_phrase"],
            dry_run=dry_run,
            write=write,
        ),
    ]


def _single_attempt(
    *,
    record_type: str,
    source_phase: str,
    supplied_phrase: str | None,
    expected_phrase: str,
    dry_run: bool,
    write: bool,
) -> dict[str, Any]:
    supplied = str(supplied_phrase).strip() if supplied_phrase is not None else ""
    expected = str(expected_phrase).strip()
    matched = bool(supplied) and supplied == expected
    status = _record_status(matched=matched, supplied_any=bool(supplied), dry_run=dry_run, write=write)
    return {
        "record_type": record_type,
        "source_phase": source_phase,
        "record_status": status,
        "supplied_phrase_hash": phrase_hash(supplied) if supplied else None,
        "expected_phrase_hash": phrase_hash(expected),
        "phrase_matched": matched,
        "missing_phrase": not bool(supplied),
    }


def _r86_attempt(*, required: Mapping[str, str], supplied: Mapping[str, str | None], dry_run: bool, write: bool) -> dict[str, Any]:
    keys = ("manual_funding_phrase", "live_env_review_phrase", "max_loss_ack_phrase", "exact_candidate_ack_phrase")
    checks = {
        key: _single_phrase_check(supplied.get(key), required[key])
        for key in keys
    }
    supplied_any = any(not check["missing_phrase"] for check in checks.values())
    matched = all(check["phrase_matched"] for check in checks.values())
    any_invalid = any(not check["missing_phrase"] and not check["phrase_matched"] for check in checks.values())
    status = (
        HUMAN_CONFIRMATION_INVALID_PHRASE
        if any_invalid
        else _record_status(matched=matched, supplied_any=supplied_any, dry_run=dry_run, write=write)
    )
    return {
        "record_type": R86_MANUAL_FUNDING_AND_ENV_CHECKLIST,
        "source_phase": "R86",
        "record_status": status,
        "phrase_matched": matched,
        "missing_phrase": not supplied_any,
        "phrase_checks": checks,
        "supplied_phrase_hash": _combined_hash([checks[key]["supplied_phrase_hash"] for key in keys]),
        "expected_phrase_hash": _combined_hash([checks[key]["expected_phrase_hash"] for key in keys]),
    }


def _single_phrase_check(supplied_phrase: str | None, expected_phrase: str) -> dict[str, Any]:
    supplied = str(supplied_phrase).strip() if supplied_phrase is not None else ""
    expected = str(expected_phrase).strip()
    return {
        "supplied_phrase_hash": phrase_hash(supplied) if supplied else None,
        "expected_phrase_hash": phrase_hash(expected),
        "phrase_matched": bool(supplied) and supplied == expected,
        "missing_phrase": not bool(supplied),
    }


def _record_status(*, matched: bool, supplied_any: bool, dry_run: bool, write: bool) -> str:
    if not supplied_any:
        return HUMAN_CONFIRMATION_REQUIRED
    if not matched:
        return HUMAN_CONFIRMATION_INVALID_PHRASE
    if dry_run or not write:
        return HUMAN_CONFIRMATION_DRY_RUN_ONLY
    return HUMAN_CONFIRMATION_RECORDED_FOR_REVIEW


def _record_payload(
    *,
    created_at: datetime,
    source: Mapping[str, Any],
    attempt: Mapping[str, Any],
    operator_note: str | None,
    dry_run: bool,
    write: bool,
    log_dir: Path,
) -> dict[str, Any]:
    record_type = str(attempt["record_type"])
    return _sanitize(
        {
            "confirmation_record_id": _record_id(
                record_type=record_type,
                candidate_id=str(source["candidate_id"]),
                risk_contract_hash=str(source["risk_contract_hash"]),
                packet_hash=str(source["packet_hash"]),
                created_at=created_at.isoformat(),
            ),
            "record_type": record_type,
            "record_status": HUMAN_CONFIRMATION_RECORDED_FOR_REVIEW,
            "candidate_id": source["candidate_id"],
            "risk_contract_hash": source["risk_contract_hash"],
            "packet_hash": source["packet_hash"] if record_type == R88_FINAL_HUMAN_REVIEW_APPROVAL else None,
            "supplied_phrase_hash": attempt.get("supplied_phrase_hash"),
            "expected_phrase_hash": attempt.get("expected_phrase_hash"),
            "phrase_matched": True,
            "source_phase": attempt.get("source_phase"),
            "source_snapshot": _source_snapshot_for_record(source=source, record_type=record_type),
            "created_at": created_at.isoformat(),
            "operator_note": operator_note or "",
            "dry_run": bool(dry_run),
            "write": bool(write),
            "human_confirmation_records_path": str(human_confirmation_records_path(log_dir)),
            "review_only": True,
            "executable": False,
            "env_modified": False,
            "order_type": "not_created",
            "order_payload_created": False,
            "execution_attempted": False,
            "network_allowed": False,
            "secrets_shown": False,
            **_safety_fields(),
        }
    )


def _source_snapshot_for_record(*, source: Mapping[str, Any], record_type: str) -> dict[str, Any]:
    if record_type == R85_TINY_LIVE_TICKET_REVIEW_APPROVAL:
        return dict(source["r85_ticket_snapshot"])
    if record_type == R88_FINAL_HUMAN_REVIEW_APPROVAL:
        return dict(source["r88_packet_snapshot"])
    return {
        "phase": "R86",
        "required_phrase_hashes": {
            key: phrase_hash(value)
            for key, value in source["required_phrases"].items()
            if key in {"manual_funding_phrase", "live_env_review_phrase", "max_loss_ack_phrase", "exact_candidate_ack_phrase"}
        },
    }


def _record_id(*, record_type: str, candidate_id: str, risk_contract_hash: str, packet_hash: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{record_type}|{candidate_id}|{risk_contract_hash}|{packet_hash}|{created_at}".encode("utf-8")).hexdigest()[:20]
    return f"r89-human-confirmation-{digest}"


def _latest_by_type(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        record_type = str(record.get("record_type") or "")
        if record_type in REQUIRED_RECORD_TYPES and record_type not in latest:
            latest[record_type] = record
    return latest


def _unified_status(latest_records: Mapping[str, Mapping[str, Any]]) -> str:
    count = len([record_type for record_type in REQUIRED_RECORD_TYPES if record_type in latest_records])
    if count == 0:
        return REVIEW_RECORDS_MISSING
    if count < len(REQUIRED_RECORD_TYPES):
        return REVIEW_RECORDS_PARTIAL
    return REVIEW_RECORDS_RECORDED_FOR_REVIEW


def _summary(records: list[dict[str, Any]], latest_records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "records_returned": len(records),
        "written_confirmation_records": len(records),
        "recorded_record_types": list(latest_records.keys()),
        "missing_record_types": [record_type for record_type in REQUIRED_RECORD_TYPES if record_type not in latest_records],
        "executable_records": 0,
        "order_payload_records": 0,
        "unified_readiness_status": _unified_status(latest_records),
    }


def _phrase_hashes(required_phrases: Mapping[str, str]) -> dict[str, str | None]:
    return {key: phrase_hash(value) for key, value in required_phrases.items()}


def _combined_hash(parts: list[str | None]) -> str | None:
    if any(part is None for part in parts):
        return None
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


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
            "env_modified",
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
