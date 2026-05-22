"""R112 first-live operator evidence recorder.

This module records operator evidence for R111 prerequisite clearing only. It
never enables live execution, places orders, signs payloads, calls Binance order
endpoints, calls account endpoints, or changes environment flags.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir

EVENT_TYPE = "FIRST_LIVE_OPERATOR_EVIDENCE"
LEDGER_FILENAME = "first_live_operator_evidence.ndjson"

EVIDENCE_MISSING = "EVIDENCE_MISSING"
EVIDENCE_PARTIAL = "EVIDENCE_PARTIAL"
EVIDENCE_READY_FOR_PREREQ_RECHECK = "EVIDENCE_READY_FOR_PREREQ_RECHECK"

SUPPORTED_EVIDENCE_TYPES = (
    "APPROVAL_INTENT_REVIEWED",
    "HUMAN_REVIEW_R85",
    "HUMAN_REVIEW_R86",
    "HUMAN_REVIEW_R88",
    "ACCOUNT_FUNDING_READ_ONLY_CHECK",
    "PROTECTIVE_ORDERS_REVIEWED",
    "LIVE_ADAPTER_BOUNDARY_REVIEWED",
    "TINY_SIZE_MAX_LOSS_DEFINED",
    "ENVIRONMENT_FLAGS_REVIEWED",
    "SACRED_BUTTON_INTENT_ONLY_VERIFIED",
    "EMERGENCY_CANCEL_PATH_REVIEWED",
    "NO_CONFLICTING_POSITION_REVIEWED",
)
REQUIRED_EVIDENCE_TYPES = SUPPORTED_EVIDENCE_TYPES

SECRET_RISK_TERMS = (
    "api key",
    "api_secret",
    "secret",
    "private key",
    "token",
    "password",
)

SAFETY_NOTES = (
    "R112 records operator evidence only.",
    "Evidence does not enable live execution.",
    "R106 remains first-live activation authority.",
    "R109 sacred button remains intent-only.",
    "No Binance order endpoint is called.",
)


def record_first_live_operator_evidence(
    *,
    evidence_type: str | None,
    candidate_id: str | None,
    risk_contract_hash: str | None,
    packet_hash: str | None,
    note: str | None,
    log_dir: str | Path | None = None,
    source: str = "CLI",
    persist: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    recorded_at = datetime.now(UTC).isoformat()
    validation_errors = _validation_errors(
        evidence_type=evidence_type,
        candidate_id=candidate_id,
        risk_contract_hash=risk_contract_hash,
        packet_hash=packet_hash,
        note=note,
    )
    accepted = not validation_errors
    rejection_reason = "; ".join(validation_errors) if validation_errors else None
    secret_risk = "note appears to contain secret material" in validation_errors
    safe_note = "[REDACTED_SECRET_RISK]" if secret_risk else str(note or "").strip()

    record = {
        "event_type": EVENT_TYPE,
        "evidence_id": uuid4().hex,
        "recorded_at_utc": recorded_at,
        "evidence_type": str(evidence_type or "").strip(),
        "candidate_id": str(candidate_id or "").strip(),
        "risk_contract_hash": str(risk_contract_hash or "").strip(),
        "packet_hash": str(packet_hash or "").strip(),
        "note": safe_note,
        "accepted": accepted,
        "live_ready": False,
        "execution_enabled_by_evidence": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "source": source,
        "safety_notes": list(SAFETY_NOTES),
        "ledger_path": str(first_live_operator_evidence_path(resolved_log_dir)),
    }
    if rejection_reason is not None:
        record["rejection_reason"] = rejection_reason

    record = _sanitize(record)
    if persist:
        append_first_live_operator_evidence(record, log_dir=resolved_log_dir)
    return record


def build_first_live_evidence_status(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    ledger_path = first_live_operator_evidence_path(resolved_log_dir)
    records = load_first_live_operator_evidence(limit=0, log_dir=resolved_log_dir)
    accepted_records = [record for record in records if record.get("accepted") is True]
    rejected_records = [record for record in records if record.get("accepted") is not True]
    tuple_types: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for record in accepted_records:
        tuple_key = (
            str(record.get("candidate_id") or "").strip(),
            str(record.get("risk_contract_hash") or "").strip(),
            str(record.get("packet_hash") or "").strip(),
        )
        evidence_type = str(record.get("evidence_type") or "").strip()
        if all(tuple_key) and evidence_type in REQUIRED_EVIDENCE_TYPES:
            tuple_types[tuple_key].add(evidence_type)

    ready_tuple = next(
        (tuple_key for tuple_key, evidence_types in tuple_types.items() if _has_all_required(evidence_types)),
        None,
    )
    best_types = _best_evidence_types(tuple_types)
    missing_types = sorted(set(REQUIRED_EVIDENCE_TYPES) - best_types)
    status = _status(records_count=len(records), ready_tuple=ready_tuple)
    latest_recorded_at = max((str(record.get("recorded_at_utc") or "") for record in records), default=None)

    payload = {
        "status": status,
        "records_count": len(records),
        "latest_recorded_at_utc": latest_recorded_at,
        "evidence_types_present": sorted(best_types),
        "evidence_types_missing": missing_types,
        "candidate_ids_seen": sorted({str(record.get("candidate_id") or "") for record in records if record.get("candidate_id")}),
        "risk_contract_hashes_seen": sorted({str(record.get("risk_contract_hash") or "") for record in records if record.get("risk_contract_hash")}),
        "packet_hashes_seen": sorted({str(record.get("packet_hash") or "") for record in records if record.get("packet_hash")}),
        "accepted_records_count": len(accepted_records),
        "rejected_records_count": len(rejected_records),
        "required_evidence_types": list(REQUIRED_EVIDENCE_TYPES),
        "ready_tuple": _ready_tuple_payload(ready_tuple),
        "live_ready": False,
        "execution_enabled_by_evidence": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "ledger_path": str(ledger_path),
        "safety_notes": list(SAFETY_NOTES),
    }
    return _sanitize(payload)


def append_first_live_operator_evidence(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_operator_evidence_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(dict(record)), sort_keys=True) + "\n")


def load_first_live_operator_evidence(
    *,
    limit: int = 50,
    evidence_id: str | None = None,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_operator_evidence_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if evidence_id is not None and record.get("evidence_id") != evidence_id:
                continue
            if candidate_id is not None and record.get("candidate_id") != candidate_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_operator_evidence_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_first_live_operator_evidence_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _validation_errors(
    *,
    evidence_type: str | None,
    candidate_id: str | None,
    risk_contract_hash: str | None,
    packet_hash: str | None,
    note: str | None,
) -> list[str]:
    errors: list[str] = []
    normalized_evidence_type = str(evidence_type or "").strip()
    if not normalized_evidence_type:
        errors.append("missing evidence_type")
    elif normalized_evidence_type not in SUPPORTED_EVIDENCE_TYPES:
        errors.append("unsupported evidence_type")
    if not str(candidate_id or "").strip():
        errors.append("missing candidate_id")
    if not str(risk_contract_hash or "").strip():
        errors.append("missing risk_contract_hash")
    if not str(packet_hash or "").strip():
        errors.append("missing packet_hash")
    if _note_contains_secret_risk(note):
        errors.append("note appears to contain secret material")
    return errors


def _note_contains_secret_risk(note: str | None) -> bool:
    normalized = str(note or "").strip().lower()
    if not normalized:
        return False
    return any(term in normalized for term in SECRET_RISK_TERMS)


def _has_all_required(evidence_types: set[str]) -> bool:
    return set(REQUIRED_EVIDENCE_TYPES).issubset(evidence_types)


def _best_evidence_types(tuple_types: Mapping[tuple[str, str, str], set[str]]) -> set[str]:
    if not tuple_types:
        return set()
    return set(max(tuple_types.values(), key=lambda evidence_types: (len(evidence_types), sorted(evidence_types))))


def _status(*, records_count: int, ready_tuple: tuple[str, str, str] | None) -> str:
    if records_count == 0:
        return EVIDENCE_MISSING
    if ready_tuple is not None:
        return EVIDENCE_READY_FOR_PREREQ_RECHECK
    return EVIDENCE_PARTIAL


def _ready_tuple_payload(tuple_key: tuple[str, str, str] | None) -> dict[str, str] | None:
    if tuple_key is None:
        return None
    candidate_id, risk_contract_hash, packet_hash = tuple_key
    return {
        "candidate_id": candidate_id,
        "risk_contract_hash": risk_contract_hash,
        "packet_hash": packet_hash,
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
