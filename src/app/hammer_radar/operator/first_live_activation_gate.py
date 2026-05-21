"""R106 first-live activation gate.

This module composes R102/R103/R104/R105 readiness evidence into a final
pre-execution activation decision. It never enables live execution, places
orders, signs payloads, or calls Binance order endpoints.
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
from src.app.hammer_radar.operator.one_tiny_live_order_protocol import (
    CONFIRMATION_PHRASE_TEMPLATE,
    PROTOCOL_PREREQS_READY,
    SOURCE_SURFACE as ONE_TINY_PROTOCOL_SOURCE,
    build_one_tiny_live_order_protocol_check,
)
from src.app.hammer_radar.operator.tiny_live_armed_dry_run import (
    READY_FOR_DRY_RUN,
    SOURCE_SURFACE as TINY_LIVE_ARMED_DRY_RUN_SOURCE,
    build_tiny_live_armed_dry_run,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

FIRST_LIVE_ACTIVATION_READY = "FIRST_LIVE_ACTIVATION_READY"
FIRST_LIVE_BLOCKED = "FIRST_LIVE_BLOCKED"
EVENT_TYPE = "FIRST_LIVE_ACTIVATION_GATE_CHECK"
ACTIVATION_GATE_CHECKS_FILENAME = "first_live_activation_gate_checks.ndjson"
SOURCE_SURFACE = "operator.first_live_activation_gate.build_first_live_activation_gate"


def build_first_live_activation_gate(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    dry_run = build_tiny_live_armed_dry_run(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, record=False)
    protocol = build_one_tiny_live_order_protocol_check(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, record=False)
    blockers = _blockers(dry_run=dry_run, protocol=protocol)
    warnings = _warnings(dry_run=dry_run, protocol=protocol)
    status = FIRST_LIVE_ACTIVATION_READY if not blockers else FIRST_LIVE_BLOCKED

    payload = {
        "event_type": EVENT_TYPE,
        "activation_gate_check_id": uuid4().hex,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "live_ready": False,
        "execution_enabled_by_gate": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "blockers": blockers,
        "warnings": warnings,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "final_preflight_status": dry_run.get("final_preflight_status"),
        "tiny_live_armed_dry_run_status": dry_run.get("status"),
        "one_tiny_live_order_protocol_status": protocol.get("status"),
        "approval_intent_present": bool(dry_run.get("approval_intent_present")),
        "approval_intent_status": dry_run.get("approval_intent_status"),
        "candidate_id": dry_run.get("candidate_id") or protocol.get("candidate_id") or candidate_id,
        "risk_contract_hash": dry_run.get("risk_contract_hash") or protocol.get("risk_contract_hash"),
        "packet_hash": dry_run.get("packet_hash") or protocol.get("packet_hash"),
        "confirmation_phrase_required": True,
        "confirmation_phrase_template": CONFIRMATION_PHRASE_TEMPLATE,
        "operator_confirmation_present": False,
        "live_execution_enabled": bool(dry_run.get("live_execution_enabled")),
        "live_orders_allowed": bool(dry_run.get("live_orders_allowed")),
        "global_kill_switch": bool(dry_run.get("global_kill_switch")),
        "connector_mode": dry_run.get("connector_mode"),
        "binance_credentials_present": dict(dry_run.get("binance_credentials_present") or {}),
        "protective_orders_ready": bool(dry_run.get("protective_orders_ready")),
        "live_order_adapter_configured": bool(dry_run.get("live_order_adapter_configured")),
        "stale_candidate_protection_present": bool(dry_run.get("stale_candidate_protection_present")),
        "paper_live_separation_intact": bool(dry_run.get("paper_live_separation_intact")),
        "source_surfaces_used": _source_surfaces(dry_run=dry_run, protocol=protocol),
        "ledger_path": str(first_live_activation_gate_checks_path(resolved_log_dir)),
        "secrets_shown": False,
    }
    if record:
        append_first_live_activation_gate_check(payload, log_dir=resolved_log_dir)
    return _sanitize(payload)


def append_first_live_activation_gate_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_activation_gate_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_first_live_activation_gate_checks(
    *,
    limit: int = 50,
    activation_gate_check_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_activation_gate_checks_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if activation_gate_check_id is not None and record.get("activation_gate_check_id") != activation_gate_check_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_activation_gate_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / ACTIVATION_GATE_CHECKS_FILENAME


def format_first_live_activation_gate_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _blockers(*, dry_run: Mapping[str, Any], protocol: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if dry_run.get("final_preflight_status") != READY:
        blockers.append("final preflight is not READY")
    if dry_run.get("status") != READY_FOR_DRY_RUN:
        blockers.append("tiny-live armed dry run is not READY_FOR_DRY_RUN")
    if protocol.get("status") != PROTOCOL_PREREQS_READY:
        blockers.append("one tiny live order protocol is not PROTOCOL_PREREQS_READY")
    if dry_run.get("approval_intent_present") is not True:
        blockers.append("approval intent missing")
    if dry_run.get("approval_intent_status") != "ACCEPTED_INTENT_ONLY":
        blockers.append(f"approval intent is not accepted: {dry_run.get('approval_intent_status') or 'UNKNOWN'}")
    if not dry_run.get("candidate_id"):
        blockers.append("candidate_id missing")
    if "stale candidate risk" in [str(item) for item in dry_run.get("blockers") or []]:
        blockers.append("candidate stale")
    if not dry_run.get("risk_contract_hash"):
        blockers.append("risk contract hash missing or mismatch")
    if not dry_run.get("packet_hash"):
        blockers.append("packet hash missing or mismatch")
    if "missing human approval record" in [str(item) for item in dry_run.get("final_preflight_blockers") or []]:
        blockers.append("human approval record missing")
    credentials = dry_run.get("binance_credentials_present") if isinstance(dry_run.get("binance_credentials_present"), dict) else {}
    if credentials.get("api_key_present") is not True or credentials.get("api_secret_present") is not True:
        blockers.append("Binance credentials missing")
    if dry_run.get("connector_mode") != "LIVE_ORDER_ENABLED":
        blockers.append("connector/account boundary not reviewed for live order enabled mode")
    if dry_run.get("protective_orders_ready") is not True:
        blockers.append("protective orders not ready")
    if dry_run.get("live_order_adapter_configured") is not True:
        blockers.append("live order adapter not configured")
    if dry_run.get("global_kill_switch") is not False:
        blockers.append("global kill switch state unsafe or ambiguous")
    if dry_run.get("live_execution_enabled") is not True:
        blockers.append("live execution flag state unsafe or ambiguous")
    if dry_run.get("live_orders_allowed") is not True:
        blockers.append("live orders flag state unsafe or ambiguous")
    blockers.append("open/conflicting position status unknown")
    blockers.append("account balance/funding unknown")
    blockers.append("position size cap unknown")
    blockers.append("max loss cap unknown")
    if dry_run.get("paper_live_separation_intact") is not True:
        blockers.append("paper/live separation not intact")
    blockers.append("operator confirmation phrase missing")
    blockers.extend(f"protocol blocker: {item}" for item in protocol.get("blockers") or [])
    return list(dict.fromkeys(blockers))


def _warnings(*, dry_run: Mapping[str, Any], protocol: Mapping[str, Any]) -> list[str]:
    warnings = [str(item) for item in dry_run.get("warnings") or []]
    warnings.extend(str(item) for item in protocol.get("warnings") or [])
    warnings.append("R106 is an activation gate only; execution remains disabled by this gate")
    warnings.append("FIRST_LIVE_ACTIVATION_READY is not order execution authority")
    return list(dict.fromkeys(warnings))


def _source_surfaces(*, dry_run: Mapping[str, Any], protocol: Mapping[str, Any]) -> list[str]:
    sources = [
        SOURCE_SURFACE,
        "operator.final_live_preflight.build_final_live_preflight",
        FINAL_APPROVAL_SOURCE_SURFACE,
        TINY_LIVE_ARMED_DRY_RUN_SOURCE,
        ONE_TINY_PROTOCOL_SOURCE,
    ]
    sources.extend(str(item) for item in dry_run.get("source_surfaces_used") or [])
    sources.extend(str(item) for item in protocol.get("source_surfaces_used") or [])
    return list(dict.fromkeys(sources))


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    rendered = json.dumps(payload, sort_keys=True)
    if any(secret_word in rendered.lower() for secret_word in ("api_secret", "api key", "telegram_bot_token")):
        payload = dict(payload)
        payload["secrets_shown"] = False
    return payload
