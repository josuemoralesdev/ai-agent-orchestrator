"""R88 final human approval record and review packet.

This module bundles R83-R87 evidence into a local review artifact. It never
creates executable order payloads, signs anything, calls Binance, checks
balances, mutates env files, or enables live execution.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_candle_archive import archive_integrity_warnings
from src.app.hammer_radar.operator.live_arming_preflight import build_live_arming_preflight
from src.app.hammer_radar.operator.live_env_arming_checklist import build_live_env_arming_checklist_status
from src.app.hammer_radar.operator.live_env_boundary_review import build_live_env_boundary_review
from src.app.hammer_radar.operator.miro_fish_quality_gate import build_miro_fish_quality_gate
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID, build_tiny_live_risk_contract_payload
from src.app.hammer_radar.operator.tiny_live_ticket_builder import build_tiny_live_ticket

PHASE = "R88"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "FINAL_HUMAN_APPROVAL_RECORD_REVIEW_PACKET_ONLY_NO_ORDER"
PACKETS_FILENAME = "final_human_review_packets.ndjson"

REVIEW_PACKET_DRY_RUN_ONLY = "REVIEW_PACKET_DRY_RUN_ONLY"
REVIEW_PACKET_CREATED_FOR_HUMAN_REVIEW = "REVIEW_PACKET_CREATED_FOR_HUMAN_REVIEW"
REVIEW_PACKET_BLOCKED_BY_MISSING_OPERATOR_APPROVAL = "REVIEW_PACKET_BLOCKED_BY_MISSING_OPERATOR_APPROVAL"
REVIEW_PACKET_BLOCKED_BY_MISSING_CHECKLIST = "REVIEW_PACKET_BLOCKED_BY_MISSING_CHECKLIST"
REVIEW_PACKET_BLOCKED_BY_LIVE_ENV_BOUNDARY = "REVIEW_PACKET_BLOCKED_BY_LIVE_ENV_BOUNDARY"
REVIEW_PACKET_BLOCKED_BY_SOURCE_WARNINGS = "REVIEW_PACKET_BLOCKED_BY_SOURCE_WARNINGS"
REVIEW_PACKET_NON_EXECUTABLE_REVIEW_ONLY = "REVIEW_PACKET_NON_EXECUTABLE_REVIEW_ONLY"
REVIEW_PACKET_INVALID_SOURCE_CHAIN = "REVIEW_PACKET_INVALID_SOURCE_CHAIN"

FINAL_HUMAN_APPROVAL_REQUIRED = "FINAL_HUMAN_APPROVAL_REQUIRED"
FINAL_HUMAN_APPROVAL_RECORDED_FOR_REVIEW = "FINAL_HUMAN_APPROVAL_RECORDED_FOR_REVIEW"
FINAL_HUMAN_APPROVAL_INVALID = "FINAL_HUMAN_APPROVAL_INVALID"
FINAL_HUMAN_APPROVAL_NOT_EXECUTION_PERMISSION = "FINAL_HUMAN_APPROVAL_NOT_EXECUTION_PERMISSION"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R88 creates final review packets only. No orders, no payloads, no env changes, no network, no Binance."


def build_final_human_review_packet(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    final_approval_phrase: str | None = None,
    operator_note: str | None = None,
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    created_at = datetime.now(UTC)
    source = build_source_chain(candidate_id=candidate_id, log_dir=resolved_log_dir)
    packet_hash_value = packet_hash(source)
    risk_hash = str(source["r85_ticket_summary"].get("risk_contract_hash") or "")
    approval_phrase = final_approval_phrase_for(
        candidate_id=source["candidate_id"],
        risk_contract_hash=risk_hash,
        packet_hash=packet_hash_value,
    )
    approval_status = _approval_status(supplied=final_approval_phrase, expected=approval_phrase)
    packet_status = _packet_status(source=source, approval_status=approval_status, dry_run=dry_run, write=write)
    packet = _packet_payload(
        created_at=created_at,
        source=source,
        packet_hash_value=packet_hash_value,
        approval_phrase=approval_phrase,
        approval_status=approval_status,
        packet_status=packet_status,
        operator_note=operator_note,
        dry_run=dry_run,
        write=write,
        log_dir=resolved_log_dir,
    )
    packet_written = False
    if write and not dry_run:
        append_final_human_review_packet(packet, log_dir=resolved_log_dir)
        packet_written = True
        packet["packet_written"] = True
    return _sanitize(
        {
            **packet,
            "packet_written": packet_written,
            "notes": [
                NO_ORDER_NOTE,
                "Final human approval record is review evidence only, not execution permission.",
                "R89 must still persist human confirmation flow separately; later execution remains explicitly gated.",
            ],
            **_safety_fields(),
        }
    )


def build_final_human_review_packets_payload(
    *,
    limit: int = 20,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    packets = load_final_human_review_packets(limit=limit, candidate_id=candidate_id, log_dir=resolved_log_dir)
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "packet_path": str(final_human_review_packets_path(resolved_log_dir)),
            "summary": {
                "packets_returned": len(packets),
                "written_packet_records": len(load_final_human_review_packets(limit=0, candidate_id=candidate_id, log_dir=resolved_log_dir)),
                "executable_packet_records": 0,
                "order_payload_records": 0,
            },
            "packets": packets,
            "notes": [NO_ORDER_NOTE],
            **_safety_fields(),
        }
    )


def build_source_chain(*, candidate_id: str, log_dir: str | Path | None = None) -> dict[str, Any]:
    quality = build_miro_fish_quality_gate(family="NORMAL", log_dir=log_dir)
    supported = [
        row
        for row in quality.get("top_supported_candidates", [])
        if isinstance(row, dict) and row.get("candidate_id") == candidate_id
    ]
    r83 = supported[0] if supported else {}
    preflight = build_live_arming_preflight(candidate_id=candidate_id, log_dir=log_dir)
    risk_contract = build_tiny_live_risk_contract_payload(candidate_id=candidate_id)
    ticket = build_tiny_live_ticket(candidate_id=candidate_id, dry_run=True, write=False, log_dir=log_dir)
    checklist = build_live_env_arming_checklist_status(candidate_id=candidate_id, log_dir=log_dir)
    boundary = build_live_env_boundary_review(candidate_id=candidate_id, dry_run=True, write=False, log_dir=log_dir)
    integrity_warnings = archive_integrity_warnings(log_dir)
    return _sanitize(
        {
            "candidate_id": candidate_id,
            "source_warnings": {
                "archive_integrity_warnings": integrity_warnings,
            },
            "r83_summary": {
                "phase": quality.get("phase"),
                "candidate_id": r83.get("candidate_id"),
                "final_quality_status": r83.get("final_quality_status"),
                "final_quality_score": r83.get("final_quality_score"),
                "source_recommendation": r83.get("source_recommendation"),
                "markov_regime": r83.get("markov_regime"),
                "markov_gate_status": r83.get("markov_gate_status"),
            },
            "r84_preflight_summary": {
                "phase": preflight.get("phase"),
                "final_preflight_status": preflight.get("final_preflight_status"),
                "blockers": preflight.get("blockers"),
                "top_candidate_preflight": preflight.get("top_candidate_preflight"),
            },
            "r84_1_risk_contract_summary": {
                "phase": risk_contract.get("phase"),
                "validation": risk_contract.get("validation"),
                "risk_contract": risk_contract.get("risk_contract"),
                "funding_config": risk_contract.get("funding_config"),
            },
            "r85_ticket_summary": {
                "phase": ticket.get("phase"),
                "ticket_id": ticket.get("ticket_id"),
                "ticket_status": ticket.get("ticket_status"),
                "approval_status": ticket.get("operator_approval_status"),
                "approval_phrase_required": ticket.get("approval_phrase_required"),
                "risk_contract_hash": ticket.get("risk_contract_hash"),
                "executable": ticket.get("executable"),
                "review_only": ticket.get("review_only"),
            },
            "r86_checklist_summary": {
                "phase": checklist.get("phase"),
                "summary": checklist.get("summary"),
                "required_phrases": checklist.get("required_phrases"),
            },
            "r87_boundary_summary": {
                "phase": boundary.get("phase"),
                "boundary_status": boundary.get("boundary_status"),
                "execution_boundary_review": boundary.get("execution_boundary_review"),
                "future_arming_requirements": boundary.get("future_arming_requirements"),
                "forbidden_actions": boundary.get("forbidden_actions"),
                "blockers": boundary.get("blockers"),
            },
        }
    )


def packet_hash(source_snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(stable_json(source_snapshot).encode("utf-8")).hexdigest()


def stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def final_approval_phrase_for(*, candidate_id: str, risk_contract_hash: str, packet_hash: str) -> str:
    return f"FINAL_REVIEW_ACK {candidate_id} {risk_contract_hash} {packet_hash}"


def final_human_review_packets_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / PACKETS_FILENAME


def append_final_human_review_packet(packet: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = final_human_review_packets_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(dict(packet)), sort_keys=True) + "\n")


def load_final_human_review_packets(
    *,
    limit: int = 20,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = final_human_review_packets_path(log_dir)
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


def format_final_human_review_packet_text(payload: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"R88 Final Human Review Packet: {payload.get('status')}",
            str(payload.get("execution_mode")),
            f"packet_id: {payload.get('packet_id')}",
            f"packet_status: {payload.get('packet_status')}",
            f"packet_hash: {payload.get('packet_hash')}",
            f"candidate_id: {payload.get('candidate_id')}",
            f"risk_contract_hash: {payload.get('risk_contract_hash')}",
            f"final_human_approval_status: {payload.get('final_human_approval_status')}",
            f"final_approval_phrase_required: {payload.get('final_approval_phrase_required')}",
            f"remaining_blockers: {', '.join(str(item) for item in payload.get('remaining_blockers') or []) if payload.get('remaining_blockers') else 'none'}",
            f"dry_run: {payload.get('dry_run')} write: {payload.get('write')} packet_written: {payload.get('packet_written')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            NO_ORDER_NOTE,
        ]
    )


def _approval_status(*, supplied: str | None, expected: str) -> str:
    if supplied is None or not str(supplied).strip():
        return FINAL_HUMAN_APPROVAL_REQUIRED
    if str(supplied).strip() == expected:
        return FINAL_HUMAN_APPROVAL_RECORDED_FOR_REVIEW
    return FINAL_HUMAN_APPROVAL_INVALID


def _packet_status(*, source: Mapping[str, Any], approval_status: str, dry_run: bool, write: bool) -> str:
    if _source_warning_blockers(source):
        return REVIEW_PACKET_BLOCKED_BY_SOURCE_WARNINGS
    if not source["r83_summary"].get("candidate_id"):
        return REVIEW_PACKET_BLOCKED_BY_SOURCE_WARNINGS
    if source["r87_boundary_summary"].get("boundary_status") != "LIVE_ENV_LOCKED_SAFE":
        if approval_status == FINAL_HUMAN_APPROVAL_INVALID:
            return REVIEW_PACKET_BLOCKED_BY_MISSING_OPERATOR_APPROVAL
        return REVIEW_PACKET_BLOCKED_BY_LIVE_ENV_BOUNDARY
    checklist_summary = source["r86_checklist_summary"].get("summary") or {}
    if checklist_summary.get("latest_checklist_status") != "CHECKLIST_RECORDED_FOR_REVIEW":
        return REVIEW_PACKET_BLOCKED_BY_MISSING_CHECKLIST
    if approval_status == FINAL_HUMAN_APPROVAL_INVALID:
        return REVIEW_PACKET_BLOCKED_BY_MISSING_OPERATOR_APPROVAL
    if approval_status == FINAL_HUMAN_APPROVAL_REQUIRED:
        return REVIEW_PACKET_BLOCKED_BY_MISSING_OPERATOR_APPROVAL
    if dry_run or not write:
        return REVIEW_PACKET_DRY_RUN_ONLY
    return REVIEW_PACKET_CREATED_FOR_HUMAN_REVIEW


def _packet_payload(
    *,
    created_at: datetime,
    source: Mapping[str, Any],
    packet_hash_value: str,
    approval_phrase: str,
    approval_status: str,
    packet_status: str,
    operator_note: str | None,
    dry_run: bool,
    write: bool,
    log_dir: Path,
) -> dict[str, Any]:
    candidate_id = str(source.get("candidate_id") or DEFAULT_CANDIDATE_ID)
    risk_hash = str(source["r85_ticket_summary"].get("risk_contract_hash") or "")
    packet_id = _packet_id(candidate_id=candidate_id, packet_hash_value=packet_hash_value)
    boundary = source["r87_boundary_summary"]
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "packet_id": packet_id,
            "packet_status": packet_status,
            "packet_hash": packet_hash_value,
            "candidate_id": candidate_id,
            "risk_contract_hash": risk_hash,
            "source_phase": PHASE,
            "source_warnings": source.get("source_warnings") or {},
            "r83_summary": source["r83_summary"],
            "r84_preflight_summary": source["r84_preflight_summary"],
            "r84_1_risk_contract_summary": source["r84_1_risk_contract_summary"],
            "r85_ticket_summary": source["r85_ticket_summary"],
            "r86_checklist_summary": source["r86_checklist_summary"],
            "r87_boundary_summary": boundary,
            "final_human_approval_status": approval_status,
            "final_approval_phrase_required": approval_phrase,
            "required_phrases": {
                "r85_approval_phrase": source["r85_ticket_summary"].get("approval_phrase_required"),
                **((source["r86_checklist_summary"].get("required_phrases") or {})),
                "final_approval_phrase": approval_phrase,
            },
            "remaining_blockers": _remaining_blockers(source=source, approval_status=approval_status),
            "forbidden_actions": boundary.get("forbidden_actions") or [],
            "future_phase_requirements": boundary.get("future_arming_requirements") or [],
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + timedelta(hours=24)).isoformat(),
            "operator_note": operator_note or "",
            "dry_run": bool(dry_run),
            "write": bool(write),
            "packet_written": False,
            "packet_path": str(final_human_review_packets_path(log_dir)),
            "review_only": True,
            "executable": False,
            "order_type": "not_created",
            "order_payload_created": False,
            "execution_attempted": False,
            "network_allowed": False,
            "secrets_shown": False,
            **_safety_fields(),
        }
    )


def _remaining_blockers(*, source: Mapping[str, Any], approval_status: str) -> list[str]:
    blockers: list[str] = []
    blockers.extend(_source_warning_blockers(source))
    if source["r84_preflight_summary"].get("final_preflight_status") == "BLOCKED_BY_MISSING_OPERATOR_APPROVAL":
        blockers.append("r84_missing_operator_approval")
    if source["r85_ticket_summary"].get("approval_status") != "OPERATOR_APPROVAL_RECORDED_FOR_REVIEW":
        blockers.append("r85_ticket_approval_not_recorded")
    checklist_summary = source["r86_checklist_summary"].get("summary") or {}
    if checklist_summary.get("latest_checklist_status") != "CHECKLIST_RECORDED_FOR_REVIEW":
        blockers.append("r86_checklist_not_recorded")
    if source["r87_boundary_summary"].get("boundary_status") != "LIVE_ENV_LOCKED_SAFE":
        blockers.extend(source["r87_boundary_summary"].get("blockers") or [])
    if approval_status != FINAL_HUMAN_APPROVAL_RECORDED_FOR_REVIEW:
        blockers.append("final_human_approval_not_recorded")
    return list(dict.fromkeys(blockers))


def _source_warning_blockers(source: Mapping[str, Any]) -> list[str]:
    warnings = ((source.get("source_warnings") or {}).get("archive_integrity_warnings") or {})
    blockers: list[str] = []
    if int(warnings.get("malformed_json_lines") or 0) > 0:
        blockers.append("source_archive_malformed_json_lines_skipped")
    if int(warnings.get("non_object_json_lines") or 0) > 0:
        blockers.append("source_archive_non_object_json_lines_skipped")
    if not source.get("r83_summary", {}).get("candidate_id"):
        blockers.append("r83_candidate_not_supported_in_current_source_chain")
    return blockers


def _packet_id(*, candidate_id: str, packet_hash_value: str) -> str:
    digest = hashlib.sha256(f"{candidate_id}|{packet_hash_value}|R88".encode("utf-8")).hexdigest()[:20]
    return f"r88-final-review-{digest}"


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
