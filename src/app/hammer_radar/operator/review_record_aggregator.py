"""R90 review record aggregator and arming readiness snapshot.

This module builds a read-only operator snapshot across R83-R89. It never
creates order payloads, calls Binance, checks balances, mutates env files, or
enables live execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.final_human_review_packet import build_final_human_review_packet
from src.app.hammer_radar.operator.human_confirmation_records import (
    REQUIRED_RECORD_TYPES,
    REVIEW_RECORDS_RECORDED_FOR_REVIEW,
    build_human_confirmation_records_status,
)
from src.app.hammer_radar.operator.live_arming_preflight import build_live_arming_preflight
from src.app.hammer_radar.operator.live_env_arming_checklist import build_live_env_arming_checklist_status
from src.app.hammer_radar.operator.live_env_boundary_review import build_live_env_boundary_review
from src.app.hammer_radar.operator.miro_fish_quality_gate import build_miro_fish_quality_gate
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID, build_tiny_live_risk_contract_payload
from src.app.hammer_radar.operator.tiny_live_ticket_builder import build_tiny_live_ticket, build_tiny_live_tickets_payload
from src.app.hammer_radar.operator.final_human_review_packet import build_final_human_review_packets_payload

PHASE = "R90"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "REVIEW_RECORD_AGGREGATOR_ARMING_READINESS_SNAPSHOT_ONLY_NO_ORDER"
SNAPSHOT_FILENAME = "review_record_arming_snapshot.json"

ARMING_SNAPSHOT_REVIEW_ONLY = "ARMING_SNAPSHOT_REVIEW_ONLY"
ARMING_SNAPSHOT_BLOCKED_BY_SOURCE_WARNINGS = "ARMING_SNAPSHOT_BLOCKED_BY_SOURCE_WARNINGS"
ARMING_SNAPSHOT_BLOCKED_BY_MISSING_REVIEW_RECORDS = "ARMING_SNAPSHOT_BLOCKED_BY_MISSING_REVIEW_RECORDS"
ARMING_SNAPSHOT_BLOCKED_BY_LIVE_ENV_BOUNDARY = "ARMING_SNAPSHOT_BLOCKED_BY_LIVE_ENV_BOUNDARY"
ARMING_SNAPSHOT_BLOCKED_BY_HASH_MISMATCH = "ARMING_SNAPSHOT_BLOCKED_BY_HASH_MISMATCH"
ARMING_SNAPSHOT_RECORDS_PARTIAL = "ARMING_SNAPSHOT_RECORDS_PARTIAL"
ARMING_SNAPSHOT_RECORDS_COMPLETE_FOR_REVIEW = "ARMING_SNAPSHOT_RECORDS_COMPLETE_FOR_REVIEW"
ARMING_SNAPSHOT_NON_EXECUTABLE_ONLY = "ARMING_SNAPSHOT_NON_EXECUTABLE_ONLY"

NOT_READY_FOR_LIVE_ARMING = "NOT_READY_FOR_LIVE_ARMING"
READY_FOR_HUMAN_RECORD_COMPLETION = "READY_FOR_HUMAN_RECORD_COMPLETION"
REVIEW_RECORDS_COMPLETE_BUT_ENV_LOCKED = "REVIEW_RECORDS_COMPLETE_BUT_ENV_LOCKED"
SOURCE_CHAIN_NEEDS_REVIEW = "SOURCE_CHAIN_NEEDS_REVIEW"
HASH_CHAIN_INVALID = "HASH_CHAIN_INVALID"
NON_EXECUTABLE_REVIEW_READY = "NON_EXECUTABLE_REVIEW_READY"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R90 aggregates review readiness only. No orders, no payloads, no env changes, no network, no Binance."


def build_review_record_arming_snapshot(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    source = _aggregation_inputs(candidate_id=candidate_id, log_dir=resolved_log_dir)
    source_summary = _source_chain_summary(source)
    review_summary = _review_record_summary(source)
    hash_summary = _hash_chain_summary(
        r85_risk_hash=source["r85_ticket"].get("risk_contract_hash"),
        r88_risk_hash=source["r88_packet"].get("risk_contract_hash"),
        r89_risk_hash=source["r89_human_confirmations"].get("risk_contract_hash"),
        r88_packet_hash=source["r88_packet"].get("packet_hash"),
        r89_packet_hash=source["r89_human_confirmations"].get("packet_hash"),
    )
    boundary_summary = _boundary_summary(source)
    snapshot_status = _snapshot_status(
        source_summary=source_summary,
        review_summary=review_summary,
        hash_summary=hash_summary,
        boundary_summary=boundary_summary,
    )
    readiness_class = _readiness_class(
        snapshot_status=snapshot_status,
        review_summary=review_summary,
        hash_summary=hash_summary,
        boundary_summary=boundary_summary,
        source_summary=source_summary,
    )
    blockers = _blocker_summary(
        source_summary=source_summary,
        review_summary=review_summary,
        hash_summary=hash_summary,
        boundary_summary=boundary_summary,
        snapshot_status=snapshot_status,
    )

    payload = _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "candidate_id": candidate_id,
            "risk_contract_hash": hash_summary["current_risk_contract_hash"],
            "packet_hash": hash_summary["current_packet_hash"],
            "snapshot_status": snapshot_status,
            "readiness_class": readiness_class,
            "source_chain_summary": source_summary,
            "review_record_summary": review_summary,
            "hash_chain_summary": hash_summary,
            "boundary_summary": boundary_summary,
            "blocker_summary": blockers,
            "next_required_actions": _next_required_actions(source_summary, review_summary, boundary_summary),
            "forbidden_actions": boundary_summary.get("forbidden_actions") or [],
            "dry_run": bool(dry_run),
            "write": bool(write),
            "snapshot_written": False,
            "report_written": False,
            "report_path": str(review_record_arming_snapshot_path(resolved_log_dir)),
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
                "Review record completeness is not live execution permission.",
                "R87 live-env boundary remains authoritative until a later explicit phase.",
            ],
            **_safety_fields(),
        }
    )
    if write and not dry_run:
        write_review_record_arming_snapshot(payload, log_dir=resolved_log_dir)
        payload["snapshot_written"] = True
        payload["report_written"] = True
    return _sanitize(payload)


def review_record_arming_snapshot_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / SNAPSHOT_FILENAME


def write_review_record_arming_snapshot(snapshot: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = review_record_arming_snapshot_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_sanitize(dict(snapshot)), handle, sort_keys=True, indent=2)
        handle.write("\n")


def format_review_record_arming_snapshot_text(payload: Mapping[str, Any]) -> str:
    hash_summary = payload.get("hash_chain_summary") if isinstance(payload.get("hash_chain_summary"), dict) else {}
    review_summary = payload.get("review_record_summary") if isinstance(payload.get("review_record_summary"), dict) else {}
    boundary = payload.get("boundary_summary") if isinstance(payload.get("boundary_summary"), dict) else {}
    source = payload.get("source_chain_summary") if isinstance(payload.get("source_chain_summary"), dict) else {}
    blockers = payload.get("blocker_summary") if isinstance(payload.get("blocker_summary"), dict) else {}
    actions = payload.get("next_required_actions") if isinstance(payload.get("next_required_actions"), list) else []
    return "\n".join(
        [
            f"R90 Readiness Snapshot status: {payload.get('status')}",
            str(payload.get("execution_mode")),
            f"candidate_id: {payload.get('candidate_id')}",
            f"risk_contract_hash: {payload.get('risk_contract_hash')}",
            f"packet_hash: {payload.get('packet_hash')}",
            f"readiness_class: {payload.get('readiness_class')}",
            f"snapshot_status: {', '.join(str(item) for item in payload.get('snapshot_status') or [])}",
            f"hash_chain_consistent: {hash_summary.get('hash_chain_consistent')}",
            f"review_records_complete: {review_summary.get('review_records_complete')}",
            f"r87_boundary_status: {boundary.get('r87_boundary_status')}",
            f"source_chain_status: {source.get('source_chain_status')}",
            f"primary_preflight_blockers: {blockers.get('primary_preflight_blockers') or []}",
            f"cascading_preflight_blockers: {blockers.get('cascading_preflight_blockers') or []}",
            f"snapshot_written: {payload.get('snapshot_written')} report_path: {payload.get('report_path')}",
            "next_required_actions:",
            *[f"  {index}. {action}" for index, action in enumerate(actions, start=1)],
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            "No-order/no-network/no-env-change safety note: R90 is aggregation only.",
            NO_ORDER_NOTE,
        ]
    )


def _aggregation_inputs(*, candidate_id: str, log_dir: Path) -> dict[str, Any]:
    quality = build_miro_fish_quality_gate(family="NORMAL", log_dir=log_dir)
    preflight = build_live_arming_preflight(candidate_id=candidate_id, log_dir=log_dir)
    risk_contract = build_tiny_live_risk_contract_payload(candidate_id=candidate_id)
    ticket = build_tiny_live_ticket(candidate_id=candidate_id, dry_run=True, write=False, log_dir=log_dir)
    tickets = build_tiny_live_tickets_payload(candidate_id=candidate_id, limit=20, log_dir=log_dir)
    checklist = build_live_env_arming_checklist_status(candidate_id=candidate_id, log_dir=log_dir)
    boundary = build_live_env_boundary_review(candidate_id=candidate_id, dry_run=True, write=False, log_dir=log_dir)
    packet = build_final_human_review_packet(candidate_id=candidate_id, dry_run=True, write=False, log_dir=log_dir)
    packets = build_final_human_review_packets_payload(candidate_id=candidate_id, limit=20, log_dir=log_dir)
    confirmations = build_human_confirmation_records_status(candidate_id=candidate_id, log_dir=log_dir)
    return {
        "r83_quality": quality,
        "r84_preflight": preflight,
        "r84_1_risk_contract": risk_contract,
        "r85_ticket": ticket,
        "r85_tickets": tickets,
        "r86_checklist": checklist,
        "r87_boundary": boundary,
        "r88_packet": packet,
        "r88_packets": packets,
        "r89_human_confirmations": confirmations,
    }


def _source_chain_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    packet = source["r88_packet"]
    preflight = source["r84_preflight"]
    hierarchy = (
        preflight.get("preflight_blocker_hierarchy")
        if isinstance(preflight.get("preflight_blocker_hierarchy"), dict)
        else {}
    )
    warnings = packet.get("source_warnings") if isinstance(packet.get("source_warnings"), dict) else {}
    packet_status = str(packet.get("packet_status") or "")
    warning_blockers = list(packet.get("remaining_blockers") or [])
    source_warnings_present = packet_status == "REVIEW_PACKET_BLOCKED_BY_SOURCE_WARNINGS" or bool(
        (warnings.get("archive_integrity_warnings") or {}).get("files_with_warnings")
    )
    return {
        "source_chain_status": "SOURCE_CHAIN_WARNINGS_PRESENT" if source_warnings_present else "SOURCE_CHAIN_NO_WARNINGS",
        "source_warning_review_required": bool(source_warnings_present),
        "r83_final_quality_status": _first_supported_candidate(source["r83_quality"]).get("final_quality_status"),
        "r84_final_preflight_status": preflight.get("final_preflight_status"),
        "r84_preflight_blocker_hierarchy": hierarchy,
        "r84_primary_preflight_blockers": hierarchy.get("primary_blockers") or [],
        "r84_secondary_preflight_blockers": hierarchy.get("secondary_blockers") or [],
        "r84_cascading_preflight_blockers": hierarchy.get("cascading_blockers") or [],
        "r84_not_evaluated": hierarchy.get("not_evaluated") or {},
        "r84_independent_continuity": hierarchy.get("independent_continuity") or {},
        "r88_packet_status": packet_status,
        "source_chain_warnings": warnings,
        "source_chain_blockers": warning_blockers,
    }


def _review_record_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    confirmations = source["r89_human_confirmations"]
    summary = confirmations.get("summary") if isinstance(confirmations.get("summary"), dict) else {}
    recorded = list(summary.get("recorded_record_types") or [])
    missing_source = summary.get("missing_record_types")
    missing = list(missing_source) if isinstance(missing_source, list) else list(REQUIRED_RECORD_TYPES)
    r85_summary = source["r85_tickets"].get("summary") if isinstance(source["r85_tickets"].get("summary"), dict) else {}
    r86_summary = source["r86_checklist"].get("summary") if isinstance(source["r86_checklist"].get("summary"), dict) else {}
    r88_summary = source["r88_packets"].get("summary") if isinstance(source["r88_packets"].get("summary"), dict) else {}
    complete = set(recorded) >= set(REQUIRED_RECORD_TYPES) and not missing
    return {
        "required_record_types": list(REQUIRED_RECORD_TYPES),
        "recorded_record_types": recorded,
        "missing_record_types": missing,
        "review_records_complete": bool(complete),
        "review_records_status": confirmations.get("unified_readiness_status"),
        "r85_ticket_records_present": int(r85_summary.get("written_ticket_records") or 0) > 0,
        "r86_checklist_confirmations_present": int(r86_summary.get("written_checklist_records") or 0) > 0,
        "r88_final_review_packet_present": int(r88_summary.get("written_packet_records") or 0) > 0,
        "r89_human_confirmation_records_present": bool(recorded),
        "latest_records": confirmations.get("latest_records") or [],
    }


def _hash_chain_summary(
    *,
    r85_risk_hash: Any,
    r88_risk_hash: Any,
    r89_risk_hash: Any,
    r88_packet_hash: Any,
    r89_packet_hash: Any,
) -> dict[str, Any]:
    risk_values = {
        "r85_risk_contract_hash": str(r85_risk_hash or ""),
        "r88_risk_contract_hash": str(r88_risk_hash or ""),
        "r89_risk_contract_hash": str(r89_risk_hash or ""),
    }
    packet_values = {
        "r88_packet_hash": str(r88_packet_hash or ""),
        "r89_packet_hash": str(r89_packet_hash or ""),
    }
    blockers = []
    if len(set(risk_values.values())) != 1 or not next(iter(risk_values.values())):
        blockers.append("risk_contract_hash_mismatch")
    if len(set(packet_values.values())) != 1 or not next(iter(packet_values.values())):
        blockers.append("packet_hash_mismatch")
    return {
        "hash_chain_consistent": not blockers,
        "current_risk_contract_hash": risk_values["r89_risk_contract_hash"] or risk_values["r88_risk_contract_hash"],
        "current_packet_hash": packet_values["r89_packet_hash"] or packet_values["r88_packet_hash"],
        "hash_chain_items": {**risk_values, **packet_values},
        "hash_chain_blockers": blockers,
    }


def _boundary_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    boundary = source["r87_boundary"]
    execution = boundary.get("execution_boundary_review") if isinstance(boundary.get("execution_boundary_review"), dict) else {}
    return {
        "r87_boundary_status": boundary.get("boundary_status"),
        "r87_execution_boundary_status": execution.get("boundary_status"),
        "live_env_arming_allowed": False,
        "execution_boundary_intact": execution.get("boundary_status") == "EXECUTION_BOUNDARY_INTACT",
        "forbidden_actions": boundary.get("forbidden_actions") or [],
        "boundary_blockers": boundary.get("blockers") or [],
    }


def _snapshot_status(
    *,
    source_summary: Mapping[str, Any],
    review_summary: Mapping[str, Any],
    hash_summary: Mapping[str, Any],
    boundary_summary: Mapping[str, Any],
) -> list[str]:
    statuses = [ARMING_SNAPSHOT_REVIEW_ONLY]
    if not hash_summary.get("hash_chain_consistent"):
        statuses.append(ARMING_SNAPSHOT_BLOCKED_BY_HASH_MISMATCH)
    if source_summary.get("source_warning_review_required"):
        statuses.append(ARMING_SNAPSHOT_BLOCKED_BY_SOURCE_WARNINGS)
    if not review_summary.get("review_records_complete"):
        statuses.append(ARMING_SNAPSHOT_BLOCKED_BY_MISSING_REVIEW_RECORDS)
        if review_summary.get("recorded_record_types"):
            statuses.append(ARMING_SNAPSHOT_RECORDS_PARTIAL)
    else:
        statuses.append(ARMING_SNAPSHOT_RECORDS_COMPLETE_FOR_REVIEW)
    if boundary_summary.get("r87_boundary_status") != "LIVE_ENV_LOCKED_SAFE":
        statuses.append(ARMING_SNAPSHOT_BLOCKED_BY_LIVE_ENV_BOUNDARY)
    statuses.append(ARMING_SNAPSHOT_NON_EXECUTABLE_ONLY)
    return list(dict.fromkeys(statuses))


def _readiness_class(
    *,
    snapshot_status: list[str],
    review_summary: Mapping[str, Any],
    hash_summary: Mapping[str, Any],
    boundary_summary: Mapping[str, Any],
    source_summary: Mapping[str, Any],
) -> str:
    if not hash_summary.get("hash_chain_consistent"):
        return HASH_CHAIN_INVALID
    if source_summary.get("source_warning_review_required"):
        return SOURCE_CHAIN_NEEDS_REVIEW
    if not review_summary.get("review_records_complete"):
        return READY_FOR_HUMAN_RECORD_COMPLETION
    if boundary_summary.get("r87_boundary_status") != "LIVE_ENV_LOCKED_SAFE":
        return REVIEW_RECORDS_COMPLETE_BUT_ENV_LOCKED
    if ARMING_SNAPSHOT_NON_EXECUTABLE_ONLY in snapshot_status:
        return NON_EXECUTABLE_REVIEW_READY
    return NOT_READY_FOR_LIVE_ARMING


def _blocker_summary(
    *,
    source_summary: Mapping[str, Any],
    review_summary: Mapping[str, Any],
    hash_summary: Mapping[str, Any],
    boundary_summary: Mapping[str, Any],
    snapshot_status: list[str],
) -> dict[str, Any]:
    blockers = []
    blockers.extend(source_summary.get("source_chain_blockers") or [])
    blockers.extend(hash_summary.get("hash_chain_blockers") or [])
    blockers.extend(f"missing_review_record:{item}" for item in review_summary.get("missing_record_types") or [])
    blockers.extend(boundary_summary.get("boundary_blockers") or [])
    blockers.extend(snapshot_status)
    primary_preflight = list(source_summary.get("r84_primary_preflight_blockers") or [])
    secondary_preflight = list(source_summary.get("r84_secondary_preflight_blockers") or [])
    cascading_preflight = list(source_summary.get("r84_cascading_preflight_blockers") or [])
    return {
        "blockers": list(dict.fromkeys(str(item) for item in blockers if item)),
        "blocker_count": len(list(dict.fromkeys(str(item) for item in blockers if item))),
        "primary_preflight_blockers": list(dict.fromkeys(str(item) for item in primary_preflight if item)),
        "secondary_preflight_blockers": list(dict.fromkeys(str(item) for item in secondary_preflight if item)),
        "cascading_preflight_blockers": list(dict.fromkeys(str(item) for item in cascading_preflight if item)),
        "preflight_not_evaluated": source_summary.get("r84_not_evaluated") or {},
    }


def _next_required_actions(
    source_summary: Mapping[str, Any],
    review_summary: Mapping[str, Any],
    boundary_summary: Mapping[str, Any],
) -> list[str]:
    actions = []
    if source_summary.get("source_warning_review_required"):
        actions.append("Review or resolve source warnings before treating the source chain as clean.")
    if "R85_TINY_LIVE_TICKET_REVIEW_APPROVAL" in (review_summary.get("missing_record_types") or []):
        actions.append("Persist the R85 approval phrase through R89 when ready.")
    if "R86_MANUAL_FUNDING_AND_ENV_CHECKLIST" in (review_summary.get("missing_record_types") or []):
        actions.append("Persist the R86 checklist phrases through R89 when ready.")
    if "R88_FINAL_HUMAN_REVIEW_APPROVAL" in (review_summary.get("missing_record_types") or []):
        actions.append("Persist the R88 final review phrase through R89 when ready.")
    if boundary_summary.get("r87_boundary_status") != "LIVE_ENV_LOCKED_SAFE":
        actions.append("Keep R87 boundary intact until a later explicit env arming phase.")
    actions.append("Do not execute until a later explicit execution phase authorizes a separate path.")
    return actions


def _first_supported_candidate(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("top_supported_candidates") if isinstance(payload.get("top_supported_candidates"), list) else []
    for row in rows:
        if isinstance(row, dict):
            return row
    return {}


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
            "live_env_arming_allowed",
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
