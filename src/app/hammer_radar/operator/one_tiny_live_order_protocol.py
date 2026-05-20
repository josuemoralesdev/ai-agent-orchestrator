"""R105 one tiny live order protocol checker.

This checker is protocol evidence only. It composes R102/R104 readiness
surfaces, records an audit row, and never enables execution or places orders.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.final_approval_intent import FINAL_APPROVAL_SOURCE_SURFACE
from src.app.hammer_radar.operator.final_live_preflight import READY
from src.app.hammer_radar.operator.tiny_live_armed_dry_run import (
    READY_FOR_DRY_RUN,
    SOURCE_SURFACE as TINY_LIVE_ARMED_DRY_RUN_SOURCE,
    build_tiny_live_armed_dry_run,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

PROTOCOL_PREREQS_READY = "PROTOCOL_PREREQS_READY"
PROTOCOL_BLOCKED = "PROTOCOL_BLOCKED"
EVENT_TYPE = "ONE_TINY_LIVE_ORDER_PROTOCOL_CHECK"
PROTOCOL_CHECKS_FILENAME = "one_tiny_live_order_protocol_checks.ndjson"
SOURCE_SURFACE = "operator.one_tiny_live_order_protocol.build_one_tiny_live_order_protocol_check"
CONFIRMATION_PHRASE_TEMPLATE = (
    "I CONFIRM ONE TINY LIVE ORDER FOR <candidate_id> WITH RISK <risk_contract_hash> "
    "AND PACKET <packet_hash>; MAX LOSS <amount>; I UNDERSTAND THIS CAN LOSE REAL MONEY."
)


def build_one_tiny_live_order_protocol_check(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    dry_run = build_tiny_live_armed_dry_run(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, record=False)
    blockers = _blockers(dry_run)
    warnings = _warnings(dry_run)
    status = PROTOCOL_PREREQS_READY if not blockers else PROTOCOL_BLOCKED
    payload = {
        "event_type": EVENT_TYPE,
        "protocol_check_id": uuid4().hex,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "live_ready": False,
        "execution_enabled_by_protocol": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "blockers": blockers,
        "warnings": warnings,
        "final_preflight_status": dry_run.get("final_preflight_status"),
        "tiny_live_armed_dry_run_status": dry_run.get("status"),
        "approval_intent_present": bool(dry_run.get("approval_intent_present")),
        "approval_intent_status": dry_run.get("approval_intent_status"),
        "candidate_id": dry_run.get("candidate_id") or candidate_id,
        "risk_contract_hash": dry_run.get("risk_contract_hash"),
        "packet_hash": dry_run.get("packet_hash"),
        "confirmation_phrase_template": CONFIRMATION_PHRASE_TEMPLATE,
        "paper_live_separation_intact": bool(dry_run.get("paper_live_separation_intact")),
        "source_surfaces_used": _source_surfaces(dry_run),
        "ledger_path": str(one_tiny_live_order_protocol_checks_path(resolved_log_dir)),
        "secrets_shown": False,
        "dry_run_snapshot": {
            "live_ready": False,
            "dry_run_only": True,
            "order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "live_execution_enabled": bool(dry_run.get("live_execution_enabled")),
            "live_orders_allowed": bool(dry_run.get("live_orders_allowed")),
            "global_kill_switch": bool(dry_run.get("global_kill_switch")),
            "connector_mode": dry_run.get("connector_mode"),
            "protective_orders_ready": bool(dry_run.get("protective_orders_ready")),
            "live_order_adapter_configured": bool(dry_run.get("live_order_adapter_configured")),
        },
    }
    if record:
        append_one_tiny_live_order_protocol_check(payload, log_dir=resolved_log_dir)
    return _sanitize(payload)


def append_one_tiny_live_order_protocol_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = one_tiny_live_order_protocol_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_one_tiny_live_order_protocol_checks(
    *,
    limit: int = 50,
    protocol_check_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = one_tiny_live_order_protocol_checks_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if protocol_check_id is not None and record.get("protocol_check_id") != protocol_check_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def one_tiny_live_order_protocol_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / PROTOCOL_CHECKS_FILENAME


def format_one_tiny_live_order_protocol_check_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _blockers(dry_run: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if dry_run.get("final_preflight_status") != READY:
        blockers.append("final preflight is not READY")
    if dry_run.get("status") != READY_FOR_DRY_RUN:
        blockers.append("tiny-live armed dry run is not READY_FOR_DRY_RUN")
    if dry_run.get("live_ready") is not False:
        blockers.append("live_ready must remain false until final human activation")
    if not dry_run.get("candidate_id"):
        blockers.append("candidate_id missing")
    if not dry_run.get("risk_contract_hash"):
        blockers.append("risk contract hash missing")
    if not dry_run.get("packet_hash"):
        blockers.append("final review packet hash missing")
    if dry_run.get("approval_intent_present") is not True:
        blockers.append("missing final approval intent")
    if dry_run.get("approval_intent_status") != "ACCEPTED_INTENT_ONLY":
        blockers.append(f"approval intent is not accepted: {dry_run.get('approval_intent_status') or 'UNKNOWN'}")
    if "stale candidate risk" in [str(item) for item in dry_run.get("blockers") or []]:
        blockers.append("stale candidate risk")
    if not dry_run.get("protective_orders_ready"):
        blockers.append("protective orders are not ready")
    if not dry_run.get("live_order_adapter_configured"):
        blockers.append("live order adapter is not configured")
    if not dry_run.get("paper_live_separation_intact"):
        blockers.append("paper/live separation is not intact")
    if dry_run.get("real_order_possible") is not False:
        blockers.append("real order possible must remain false in R105")
    blockers.extend(f"dry-run blocker: {item}" for item in dry_run.get("blockers") or [])
    return list(dict.fromkeys(blockers))


def _warnings(dry_run: Mapping[str, Any]) -> list[str]:
    warnings = [str(item) for item in dry_run.get("warnings") or []]
    warnings.append("R105 is protocol evidence only and must never return LIVE_READY")
    warnings.append("The confirmation phrase template is inactive in R105 and cannot execute an order")
    return list(dict.fromkeys(warnings))


def _source_surfaces(dry_run: Mapping[str, Any]) -> list[str]:
    sources = [
        SOURCE_SURFACE,
        "operator.final_live_preflight.build_final_live_preflight",
        TINY_LIVE_ARMED_DRY_RUN_SOURCE,
        FINAL_APPROVAL_SOURCE_SURFACE,
    ]
    sources.extend(str(item) for item in dry_run.get("source_surfaces_used") or [])
    return list(dict.fromkeys(sources))


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    rendered = json.dumps(payload, sort_keys=True)
    if any(secret_word in rendered.lower() for secret_word in ("api_secret", "api key", "telegram_bot_token")):
        payload = dict(payload)
        payload["secrets_shown"] = False
    return payload
