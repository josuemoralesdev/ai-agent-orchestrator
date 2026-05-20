"""R103 final approval intent recorder.

This module records Telegram final approval intent only. It uses the R102 final
live preflight adapter as authority and never arms live execution or places
orders.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.final_live_preflight import (
    BLOCKED,
    READY,
    build_final_live_preflight,
)

FINAL_APPROVAL_INTENTS_FILENAME = "final_approval_intents.ndjson"
FINAL_APPROVAL_EVENT_TYPE = "FINAL_APPROVAL_INTENT"
FINAL_APPROVAL_SOURCE_SURFACE = "operator.final_live_preflight.build_final_live_preflight"


def evaluate_final_approval_intent(
    *,
    candidate_id: str,
    supplied_risk_contract_hash: str,
    supplied_packet_hash: str,
    telegram_user_id: str | None = None,
    chat_id: str | None = None,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    preflight = build_final_live_preflight(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env)
    matched_risk = _hash_match(supplied_risk_contract_hash, preflight.get("risk_contract_hash"))
    matched_packet = _hash_match(supplied_packet_hash, preflight.get("final_review_packet_hash"))
    blockers = list(preflight.get("blockers") or [])
    mismatch_blockers = _mismatch_blockers(matched_risk_contract_hash=matched_risk, matched_packet_hash=matched_packet)
    result_status = _result_status(
        preflight_status=str(preflight.get("status") or BLOCKED),
        matched_risk_contract_hash=matched_risk,
        matched_packet_hash=matched_packet,
    )
    intent_effective = result_status == "ACCEPTED_INTENT_ONLY"

    record = {
        "event_type": FINAL_APPROVAL_EVENT_TYPE,
        "intent_id": uuid4().hex,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "candidate_id": candidate_id,
        "supplied_risk_contract_hash": supplied_risk_contract_hash,
        "supplied_packet_hash": supplied_packet_hash,
        "expected_risk_contract_hash": preflight.get("risk_contract_hash"),
        "expected_packet_hash": preflight.get("final_review_packet_hash"),
        "matched_risk_contract_hash": matched_risk,
        "matched_packet_hash": matched_packet,
        "final_preflight_status": preflight.get("status") or BLOCKED,
        "result_status": result_status,
        "approval_intent_effective": intent_effective,
        "blockers": blockers + mismatch_blockers,
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id,
        "live_execution_enabled": bool(preflight.get("live_execution_enabled")),
        "live_orders_allowed": bool(preflight.get("live_orders_allowed")),
        "global_kill_switch": bool(preflight.get("global_kill_switch")),
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "order_payload_created": False,
        "signed_payload_created": False,
        "secrets_shown": False,
        "source_surfaces_used": _source_surfaces(preflight),
    }
    if persist:
        append_final_approval_intent(record, log_dir=resolved_log_dir)
    record["final_approval_intents_path"] = str(final_approval_intents_path(resolved_log_dir))
    return {
        "status": result_status,
        "record": record,
        "final_live_preflight": _telegram_preflight_payload(preflight),
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def append_final_approval_intent(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = final_approval_intents_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_final_approval_intents(
    *,
    limit: int = 50,
    intent_id: str | None = None,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = final_approval_intents_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if intent_id is not None and record.get("intent_id") != intent_id:
                continue
            if candidate_id is not None and record.get("candidate_id") != candidate_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def final_approval_intents_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / FINAL_APPROVAL_INTENTS_FILENAME


def telegram_final_preflight_payload(preflight: Mapping[str, Any]) -> dict[str, Any]:
    return _telegram_preflight_payload(preflight)


def format_final_preflight_telegram_message(payload: Mapping[str, Any]) -> str:
    blockers = [str(item) for item in payload.get("blockers") or []]
    top_blockers = "; ".join(blockers[:5]) if blockers else "none"
    if len(blockers) > 5:
        top_blockers += f"; +{len(blockers) - 5} more"
    return (
        f"Final preflight: {payload.get('status') or BLOCKED}. "
        f"blockers={top_blockers}. "
        f"risk_contract_hash={payload.get('risk_contract_hash') or 'missing'}. "
        f"final_review_packet_hash={payload.get('final_review_packet_hash') or 'missing'}. "
        f"live_execution_enabled={str(bool(payload.get('live_execution_enabled'))).lower()} "
        f"live_orders_allowed={str(bool(payload.get('live_orders_allowed'))).lower()} "
        f"global_kill_switch={str(bool(payload.get('global_kill_switch'))).lower()} "
        f"connector_mode={payload.get('connector_mode') or 'UNKNOWN'}. "
        "No live order was placed. secrets_shown=false."
    )


def format_final_approval_intent_telegram_message(payload: Mapping[str, Any]) -> str:
    record = payload.get("record") if isinstance(payload.get("record"), dict) else {}
    blockers = [str(item) for item in record.get("blockers") or []]
    top_blockers = "; ".join(blockers[:5]) if blockers else "none"
    if len(blockers) > 5:
        top_blockers += f"; +{len(blockers) - 5} more"
    return (
        f"Final approval intent: {record.get('result_status') or 'REJECTED'}. "
        f"candidate_id={record.get('candidate_id') or 'missing'}. "
        f"matched_risk_contract_hash={record.get('matched_risk_contract_hash')}. "
        f"matched_packet_hash={record.get('matched_packet_hash')}. "
        f"final_preflight_status={record.get('final_preflight_status') or BLOCKED}. "
        f"blockers={top_blockers}. "
        "Approval intent is not live approval and does not arm execution. "
        "No live order was placed. execution_attempted=false secrets_shown=false."
    )


def _telegram_preflight_payload(preflight: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": preflight.get("status") or BLOCKED,
        "blockers": list(preflight.get("blockers") or []),
        "warnings": list(preflight.get("warnings") or []),
        "checked_at_utc": preflight.get("checked_at_utc"),
        "candidate_id": preflight.get("candidate_id"),
        "risk_contract_hash": preflight.get("risk_contract_hash"),
        "final_review_packet_hash": preflight.get("final_review_packet_hash"),
        "live_execution_enabled": bool(preflight.get("live_execution_enabled")),
        "live_orders_allowed": bool(preflight.get("live_orders_allowed")),
        "global_kill_switch": bool(preflight.get("global_kill_switch")),
        "connector_mode": preflight.get("connector_mode"),
        "telegram_configured": bool(preflight.get("telegram_configured")),
        "telegram_operator_path_present": bool(preflight.get("telegram_operator_path_present")),
        "paper_live_separation_intact": bool(preflight.get("paper_live_separation_intact")),
        "source_surfaces_used": _source_surfaces(preflight),
        "safety": {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "secrets_shown": False,
        },
    }


def _source_surfaces(preflight: Mapping[str, Any]) -> list[str]:
    sources = [FINAL_APPROVAL_SOURCE_SURFACE]
    sources.extend(str(item) for item in preflight.get("source_surfaces_used") or [])
    return list(dict.fromkeys(sources))


def _hash_match(supplied_hash: str, expected_hash: Any) -> bool | str:
    expected = str(expected_hash or "").strip()
    if not expected:
        return "unknown"
    return str(supplied_hash or "").strip() == expected


def _mismatch_blockers(
    *,
    matched_risk_contract_hash: bool | str,
    matched_packet_hash: bool | str,
) -> list[str]:
    blockers: list[str] = []
    if matched_risk_contract_hash is not True:
        blockers.append("risk contract hash mismatch or unavailable")
    if matched_packet_hash is not True:
        blockers.append("final review packet hash mismatch or unavailable")
    return blockers


def _result_status(
    *,
    preflight_status: str,
    matched_risk_contract_hash: bool | str,
    matched_packet_hash: bool | str,
) -> str:
    if matched_risk_contract_hash is not True or matched_packet_hash is not True:
        return "REJECTED_HASH_MISMATCH"
    if preflight_status != READY:
        return "BLOCKED_BY_FINAL_PREFLIGHT"
    return "ACCEPTED_INTENT_ONLY"
