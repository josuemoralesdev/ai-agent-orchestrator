"""R104 tiny-live armed dry-run adapter.

This module composes R102 final preflight and R103 final approval intent
records into an auditable dry-run result. It never places orders, signs
payloads, calls Binance order endpoints, or enables live flags.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.final_approval_intent import (
    FINAL_APPROVAL_SOURCE_SURFACE,
    load_final_approval_intents,
)
from src.app.hammer_radar.operator.final_live_preflight import (
    BLOCKED,
    SOURCE_SURFACES_USED as FINAL_PREFLIGHT_SOURCE_SURFACES,
    build_final_live_preflight,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

READY_FOR_DRY_RUN = "READY_FOR_DRY_RUN"
BLOCKED_FOR_DRY_RUN = "BLOCKED_FOR_DRY_RUN"
EVENT_TYPE = "TINY_LIVE_ARMED_DRY_RUN"
DRY_RUNS_FILENAME = "tiny_live_armed_dry_runs.ndjson"
SOURCE_SURFACE = "operator.tiny_live_armed_dry_run.build_tiny_live_armed_dry_run"


def build_tiny_live_armed_dry_run(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    final_preflight = build_final_live_preflight(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env)
    approval_intent = _latest_approval_intent(candidate_id=candidate_id, log_dir=resolved_log_dir)
    blockers = _blockers(final_preflight=final_preflight, approval_intent=approval_intent)
    warnings = _warnings(final_preflight=final_preflight, approval_intent=approval_intent)
    status = READY_FOR_DRY_RUN if not blockers else BLOCKED_FOR_DRY_RUN

    payload = {
        "event_type": EVENT_TYPE,
        "dry_run_id": uuid4().hex,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "live_ready": False,
        "dry_run_only": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "blockers": blockers,
        "warnings": warnings,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "final_preflight_status": final_preflight.get("status") or BLOCKED,
        "final_preflight_blockers": list(final_preflight.get("blockers") or []),
        "approval_intent_present": approval_intent is not None,
        "approval_intent_status": _approval_intent_status(approval_intent),
        "approval_intent_id": (approval_intent or {}).get("intent_id"),
        "candidate_id": final_preflight.get("candidate_id") or candidate_id,
        "risk_contract_hash": final_preflight.get("risk_contract_hash"),
        "packet_hash": final_preflight.get("final_review_packet_hash"),
        "live_execution_enabled": bool(final_preflight.get("live_execution_enabled")),
        "live_orders_allowed": bool(final_preflight.get("live_orders_allowed")),
        "global_kill_switch": bool(final_preflight.get("global_kill_switch")),
        "connector_mode": final_preflight.get("connector_mode"),
        "binance_credentials_present": dict(final_preflight.get("binance_credentials_present") or {}),
        "protective_orders_ready": bool(final_preflight.get("protective_orders_ready")),
        "live_order_adapter_configured": _live_order_adapter_configured(final_preflight),
        "stale_candidate_protection_present": bool(final_preflight.get("stale_candidate_protection_present")),
        "paper_live_separation_intact": bool(final_preflight.get("paper_live_separation_intact")),
        "source_surfaces_used": _source_surfaces(final_preflight),
        "ledger_path": str(tiny_live_armed_dry_runs_path(resolved_log_dir)),
        "secrets_shown": False,
    }
    if record:
        append_tiny_live_armed_dry_run(payload, log_dir=resolved_log_dir)
    return _sanitize(payload)


def append_tiny_live_armed_dry_run(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = tiny_live_armed_dry_runs_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_tiny_live_armed_dry_runs(
    *,
    limit: int = 50,
    dry_run_id: str | None = None,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = tiny_live_armed_dry_runs_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if dry_run_id is not None and record.get("dry_run_id") != dry_run_id:
                continue
            if candidate_id is not None and record.get("candidate_id") != candidate_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def tiny_live_armed_dry_runs_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / DRY_RUNS_FILENAME


def format_tiny_live_armed_dry_run_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _latest_approval_intent(*, candidate_id: str, log_dir: Path) -> dict[str, Any] | None:
    records = load_final_approval_intents(limit=1, candidate_id=candidate_id, log_dir=log_dir)
    return records[0] if records else None


def _blockers(*, final_preflight: Mapping[str, Any], approval_intent: Mapping[str, Any] | None) -> list[str]:
    blockers: list[str] = []
    final_status = str(final_preflight.get("status") or BLOCKED)
    final_blockers = [str(item) for item in final_preflight.get("blockers") or []]
    if final_status == BLOCKED:
        blockers.append("final preflight is BLOCKED")
    if approval_intent is None:
        blockers.append("missing final approval intent")
    else:
        intent_status = str(approval_intent.get("result_status") or "UNKNOWN")
        if intent_status != "ACCEPTED_INTENT_ONLY":
            blockers.append(f"final approval intent is not accepted for dry-run: {intent_status}")
        if approval_intent.get("supplied_risk_contract_hash") != final_preflight.get("risk_contract_hash"):
            blockers.append("approval intent risk contract hash does not match current final preflight")
        if approval_intent.get("supplied_packet_hash") != final_preflight.get("final_review_packet_hash"):
            blockers.append("approval intent packet hash does not match current final preflight")
    if not final_preflight.get("risk_contract_hash"):
        blockers.append("risk contract hash missing")
    if not final_preflight.get("final_review_packet_hash"):
        blockers.append("final review packet hash missing")
    if "stale candidate risk" in final_blockers or final_preflight.get("fresh_promoted_signal_found") is not True:
        blockers.append("stale candidate risk")
    if final_preflight.get("source_statuses", {}).get("env_boundary_status") != "LIVE_ENV_LOCKED_SAFE":
        blockers.append("environment boundary blocked")
    if not final_preflight.get("protective_orders_ready"):
        blockers.append("protective readiness false")
    if not _live_order_adapter_configured(final_preflight):
        blockers.append("live order adapter not configured")
    if not final_preflight.get("paper_live_separation_intact"):
        blockers.append("paper/live separation violation")
    if final_preflight.get("connector_mode") == "DRY_RUN_ONLY" and _simulation_inputs_incomplete(final_preflight, approval_intent):
        blockers.append("connector mode is DRY_RUN_ONLY and required simulation inputs are incomplete")
    return list(dict.fromkeys(blockers))


def _warnings(*, final_preflight: Mapping[str, Any], approval_intent: Mapping[str, Any] | None) -> list[str]:
    warnings = [str(item) for item in final_preflight.get("warnings") or []]
    warnings.append("READY_FOR_DRY_RUN is not LIVE_READY; this adapter always returns live_ready=false")
    if approval_intent is not None:
        warnings.append("Telegram approval intent is considered as audit input only, not execution approval")
    return list(dict.fromkeys(warnings))


def _approval_intent_status(approval_intent: Mapping[str, Any] | None) -> str:
    if approval_intent is None:
        return "MISSING"
    return str(approval_intent.get("result_status") or "UNKNOWN")


def _live_order_adapter_configured(final_preflight: Mapping[str, Any]) -> bool:
    blockers = [str(item) for item in final_preflight.get("blockers") or []]
    return "live order adapter not configured" not in blockers and final_preflight.get("connector_mode") == "LIVE_ORDER_ENABLED"


def _simulation_inputs_incomplete(
    final_preflight: Mapping[str, Any],
    approval_intent: Mapping[str, Any] | None,
) -> bool:
    if approval_intent is None:
        return True
    return (
        not final_preflight.get("risk_contract_hash")
        or not final_preflight.get("final_review_packet_hash")
        or not final_preflight.get("protective_orders_ready")
        or approval_intent.get("result_status") != "ACCEPTED_INTENT_ONLY"
    )


def _source_surfaces(final_preflight: Mapping[str, Any]) -> list[str]:
    sources = [
        SOURCE_SURFACE,
        "operator.final_live_preflight.build_final_live_preflight",
        "operator.final_approval_intent.load_final_approval_intents",
        FINAL_APPROVAL_SOURCE_SURFACE,
    ]
    sources.extend(str(item) for item in final_preflight.get("source_surfaces_used") or FINAL_PREFLIGHT_SOURCE_SURFACES)
    return list(dict.fromkeys(sources))


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    rendered = json.dumps(payload, sort_keys=True)
    if any(secret_word in rendered.lower() for secret_word in ("api_secret", "api key", "telegram_bot_token")):
        payload = dict(payload)
        payload["secrets_shown"] = False
    return payload
