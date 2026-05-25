"""R130 first tiny-live autonomous lane authorization.

This module records operator authorization intent for a configured lane only.
It never creates executable order payloads, calls Binance, signs requests,
mutates env files, enables global live flags, or places orders.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.autonomous_paper_lane_execution import (
    PAPER_BLOCKED,
    load_paper_lane_executions,
)
from src.app.hammer_radar.operator.autonomous_paper_lane_executor_integration import (
    PAPER_EXECUTOR_INTEGRATION_RECORDED,
    load_paper_executor_integration_records,
)
from src.app.hammer_radar.operator.first_tiny_live_lane_execution_gate import (
    TINY_LIVE_EXECUTION_READY,
    build_first_tiny_live_lane_execution_gate,
)
from src.app.hammer_radar.operator.lane_command_interface import build_lane_command_preview
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls
from src.app.hammer_radar.operator.strategy_performance import (
    ELIGIBLE_FOR_FUTURE_TINY_LIVE,
    build_live_eligibility_matrix,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    RISK_CONTRACT_VALID_FOR_PREFLIGHT,
    build_tiny_live_risk_contract_payload,
    risk_contract_hash,
)

TINY_LIVE_AUTHORIZATION_PREVIEW = "TINY_LIVE_AUTHORIZATION_PREVIEW"
TINY_LIVE_AUTHORIZATION_REJECTED = "TINY_LIVE_AUTHORIZATION_REJECTED"
TINY_LIVE_AUTHORIZATION_BLOCKED = "TINY_LIVE_AUTHORIZATION_BLOCKED"
TINY_LIVE_AUTHORIZATION_RECORDED = "TINY_LIVE_AUTHORIZATION_RECORDED"
TINY_LIVE_AUTHORIZATION_READY_FOR_GATE_RECHECK = "TINY_LIVE_AUTHORIZATION_READY_FOR_GATE_RECHECK"

EVENT_TYPE = "FIRST_TINY_LIVE_AUTONOMOUS_LANE_AUTHORIZATION"
LEDGER_FILENAME = "first_tiny_live_autonomous_lane_authorizations.ndjson"
CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE = (
    "I CONFIRM TINY LIVE LANE AUTHORIZATION ONLY; NO ORDER; NO BINANCE CALL."
)
REQUIRED_FUTURE_EXECUTION_CONFIRMATION_PHRASE = (
    "FUTURE PHASE REQUIRED: explicit dry authorization for one protected tiny-live order payload."
)
BLOCKING_SAFETY_KEYS = (
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "order_payload_created",
    "network_allowed",
    "secrets_shown",
)
AUTHORIZATION_SAFETY = {
    **SAFETY_FALSE,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "global_live_flags_changed": False,
}
SOURCE_SURFACES_USED = [
    "operator.lane_control.load_lane_controls",
    "operator.strategy_performance.build_live_eligibility_matrix",
    "operator.autonomous_paper_lane_execution.load_paper_lane_executions",
    "operator.autonomous_paper_lane_executor_integration.load_paper_executor_integration_records",
    "operator.first_tiny_live_lane_execution_gate.build_first_tiny_live_lane_execution_gate",
    "operator.tiny_live_risk_contract.build_tiny_live_risk_contract_payload",
    "operator.lane_command_interface.build_lane_command_preview",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "logs/hammer_radar_forward/autonomous_paper_lane_executions.ndjson",
    "logs/hammer_radar_forward/autonomous_paper_lane_executor_integrations.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_first_tiny_live_autonomous_lane_authorization(
    *,
    log_dir: str | Path | None = None,
    lane_key: str | None = None,
    record_authorization: bool = False,
    request_lane_mode_tiny_live: bool = False,
    apply_lane_mode_change: bool = False,
    confirm_tiny_live_authorization: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
    controls: Mapping[str, Any] | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    r126_gate: Mapping[str, Any] | None = None,
    risk_contract: Mapping[str, Any] | None = None,
    paper_records: list[Mapping[str, Any]] | None = None,
    integration_records: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_tiny_live_authorization == CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE
    loaded_controls = dict(controls) if controls is not None else load_lane_controls(config_path)
    lane = _find_lane(loaded_controls, lane_key)
    previous_lane_mode = str((lane or {}).get("mode") or "missing").strip().lower()
    lane_mode_change = _lane_mode_change_preview(
        request_lane_mode_tiny_live=request_lane_mode_tiny_live,
        apply_lane_mode_change=apply_lane_mode_change,
        confirmation_valid=confirmation_valid,
        lane_key=lane_key,
        log_dir=resolved_log_dir,
        config_path=config_path,
    )
    prerequisites = evaluate_lane_authorization_prerequisites(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        controls=loaded_controls,
        live_eligibility_matrix=live_eligibility_matrix,
        r126_gate=r126_gate,
        risk_contract=risk_contract,
        paper_records=paper_records,
        integration_records=integration_records,
        config_path=config_path,
        now=generated_at,
    )
    packet = build_tiny_live_lane_authorization_packet(
        lane=lane,
        prerequisites=prerequisites,
        generated_at=generated_at,
    )
    blockers = _dedupe([*prerequisites["blockers"], *lane_mode_change["blockers"]])
    warnings = _dedupe([*prerequisites["warnings"], *lane_mode_change["warnings"]])
    authorization_recorded = False
    authorization_id = f"tiny_live_lane_auth_{uuid4().hex}" if record_authorization else None

    if record_authorization and not confirmation_valid:
        status = TINY_LIVE_AUTHORIZATION_REJECTED
        blockers = _dedupe(["exact tiny-live authorization confirmation phrase is required", *blockers])
    elif blockers:
        status = TINY_LIVE_AUTHORIZATION_BLOCKED
    elif record_authorization:
        status = TINY_LIVE_AUTHORIZATION_RECORDED
        record = _authorization_record(
            authorization_id=str(authorization_id),
            recorded_at_utc=generated_at.isoformat(),
            lane_key=str(lane_key or ""),
            previous_lane_mode=previous_lane_mode,
            authorization_status=status,
            operator_confirmation_valid=confirmation_valid,
            prerequisites=prerequisites,
            blockers=blockers,
            warnings=warnings,
            authorization_packet=packet,
        )
        append_tiny_live_lane_authorization_record(record, log_dir=resolved_log_dir)
        authorization_recorded = True
    elif request_lane_mode_tiny_live and previous_lane_mode != "tiny_live":
        status = TINY_LIVE_AUTHORIZATION_READY_FOR_GATE_RECHECK
    else:
        status = TINY_LIVE_AUTHORIZATION_PREVIEW

    payload = {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "lane_key": lane_key,
        "previous_lane_mode": previous_lane_mode,
        "requested_mode": "tiny_live",
        "record_authorization_requested": bool(record_authorization),
        "request_lane_mode_tiny_live": bool(request_lane_mode_tiny_live),
        "apply_lane_mode_change": bool(apply_lane_mode_change),
        "confirmation_valid": bool(confirmation_valid),
        "authorization_recorded": authorization_recorded,
        "authorization_id": authorization_id if authorization_recorded else None,
        "config_written": False,
        "authorization_packet": packet,
        "prerequisites": prerequisites,
        "blockers": blockers,
        "warnings": warnings,
        "next_actions": _next_actions(status, blockers, lane_mode_change),
        "safety": dict(AUTHORIZATION_SAFETY),
        "ledger_path": str(_ledger_path(resolved_log_dir)),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }
    if request_lane_mode_tiny_live or apply_lane_mode_change:
        payload["lane_mode_change"] = lane_mode_change
    return _sanitize(payload)


def evaluate_lane_authorization_prerequisites(
    *,
    log_dir: str | Path | None = None,
    lane_key: str | None,
    controls: Mapping[str, Any] | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    r126_gate: Mapping[str, Any] | None = None,
    risk_contract: Mapping[str, Any] | None = None,
    paper_records: list[Mapping[str, Any]] | None = None,
    integration_records: list[Mapping[str, Any]] | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    loaded_controls = dict(controls) if controls is not None else load_lane_controls(config_path)
    lane = _find_lane(loaded_controls, lane_key)
    blockers: list[str] = []
    warnings: list[str] = []
    if not lane:
        blockers.append("unknown lane_key")

    matrix = live_eligibility_matrix if live_eligibility_matrix is not None else build_live_eligibility_matrix(log_dir=resolved_log_dir)
    eligibility = _matching_eligibility(lane, matrix) if lane else None
    if lane and _eligibility_recommendation(eligibility) != ELIGIBLE_FOR_FUTURE_TINY_LIVE:
        blockers.append("lane is not eligible for future tiny live")

    risk = dict(risk_contract) if risk_contract is not None else _risk_contract_for_lane(lane)
    risk_summary = _risk_contract_summary(risk)
    if risk_summary["validation_status"] != RISK_CONTRACT_VALID_FOR_PREFLIGHT:
        blockers.append("tiny-live risk contract is missing or invalid")

    if lane:
        if int(lane.get("max_daily_trades") or 0) <= 0:
            blockers.append("max_daily_trades is missing")
        if float(lane.get("max_daily_loss_pct") or 0.0) <= 0:
            blockers.append("max_daily_loss_pct is missing")
        if int(lane.get("cooldown_after_loss_minutes") or 0) <= 0:
            blockers.append("cooldown_after_loss_minutes is missing")
        if lane.get("require_protective_orders") is not True:
            blockers.append("lane protective order policy is absent")

    contract = risk.get("risk_contract") if isinstance(risk.get("risk_contract"), Mapping) else {}
    if contract.get("protective_stop_required") is not True or contract.get("take_profit_required") is not True:
        blockers.append("protective order policy is absent")

    paper_proof = _paper_proof_summary(
        lane_key=lane_key,
        paper_records=paper_records,
        integration_records=integration_records,
        log_dir=resolved_log_dir,
        now=generated_at,
    )
    if paper_proof["matched"] is not True:
        blockers.append("recent autonomous paper proof is missing")

    gate = dict(r126_gate) if r126_gate is not None else build_first_tiny_live_lane_execution_gate(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        record=False,
        config_path=config_path,
    )
    r126_status = str(gate.get("status") or "UNKNOWN")
    if r126_status != TINY_LIVE_EXECUTION_READY:
        blockers.append(f"R126 tiny-live gate is not {TINY_LIVE_EXECUTION_READY}: {r126_status}")
    gate_safety = gate.get("safety") if isinstance(gate.get("safety"), Mapping) else {}
    blockers.extend(_safety_blockers(gate_safety, "R126 safety field is unsafe"))

    safety = dict(AUTHORIZATION_SAFETY)
    blockers.extend(_safety_blockers(safety, "authorization safety field is unsafe"))
    if safety["paper_live_separation_intact"] is not True:
        blockers.append("paper/live separation is not intact")

    return {
        "lane_exists": bool(lane),
        "lane": _lane_summary(lane),
        "eligibility": _eligibility_summary(eligibility),
        "r126_gate_status": r126_status,
        "r126_readiness_hash": _r126_readiness_hash(gate),
        "r129_paper_integration_status": paper_proof["r129_paper_integration_status"],
        "paper_proof_summary": paper_proof,
        "risk_contract_summary": risk_summary,
        "kill_switch_acknowledged": True,
        "rollback_acknowledged": True,
        "max_daily_trades_present": bool(lane and int(lane.get("max_daily_trades") or 0) > 0),
        "max_daily_loss_present": bool(lane and float(lane.get("max_daily_loss_pct") or 0.0) > 0),
        "cooldown_present": bool(lane and int(lane.get("cooldown_after_loss_minutes") or 0) > 0),
        "protective_order_policy_required": bool(lane and lane.get("require_protective_orders") is True),
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "safety": safety,
    }


def build_tiny_live_lane_authorization_packet(
    *,
    lane: Mapping[str, Any] | None,
    prerequisites: Mapping[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    lane_record = dict(lane or {})
    paper = prerequisites.get("paper_proof_summary") if isinstance(prerequisites.get("paper_proof_summary"), Mapping) else {}
    risk = prerequisites.get("risk_contract_summary") if isinstance(prerequisites.get("risk_contract_summary"), Mapping) else {}
    packet = {
        "lane_key": lane_record.get("lane_key"),
        "symbol": lane_record.get("symbol"),
        "timeframe": lane_record.get("timeframe"),
        "direction": lane_record.get("direction"),
        "entry_mode": lane_record.get("entry_mode"),
        "requested_mode": "tiny_live",
        "max_daily_trades": lane_record.get("max_daily_trades"),
        "max_daily_loss_pct": lane_record.get("max_daily_loss_pct"),
        "cooldown_after_loss_minutes": lane_record.get("cooldown_after_loss_minutes"),
        "freshness_seconds": lane_record.get("freshness_seconds"),
        "require_protective_orders": lane_record.get("require_protective_orders") is True,
        "paper_proof_reference": paper.get("paper_proof_reference"),
        "r126_readiness_hash": prerequisites.get("r126_readiness_hash"),
        "risk_contract_hash": risk.get("risk_contract_hash"),
        "required_future_execution_confirmation_phrase": REQUIRED_FUTURE_EXECUTION_CONFIRMATION_PHRASE,
    }
    packet["authorization_hash"] = _hash_packet({**packet, "generated_at": (generated_at or datetime.now(UTC)).isoformat()})
    return _sanitize(packet)


def append_tiny_live_lane_authorization_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = _ledger_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(dict(record))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_lane_authorization_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = _ledger_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if lane_key is not None and record.get("lane_key") != lane_key:
                continue
            records.append(record)
    if limit > 0:
        return list(reversed(records))[:limit]
    return records


def summarize_tiny_live_lane_authorizations(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("authorization_status") or "UNKNOWN") for record in records)
    lane_counts = Counter(str(record.get("lane_key") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "safety": dict(AUTHORIZATION_SAFETY),
    }


def format_first_tiny_live_autonomous_lane_authorization_json(payload: Mapping[str, Any]) -> str:
    compact = {
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "lane_key": payload.get("lane_key"),
        "previous_lane_mode": payload.get("previous_lane_mode"),
        "requested_mode": payload.get("requested_mode"),
        "record_authorization_requested": payload.get("record_authorization_requested"),
        "request_lane_mode_tiny_live": payload.get("request_lane_mode_tiny_live"),
        "apply_lane_mode_change": payload.get("apply_lane_mode_change"),
        "confirmation_valid": payload.get("confirmation_valid"),
        "authorization_recorded": payload.get("authorization_recorded"),
        "authorization_id": payload.get("authorization_id"),
        "config_written": payload.get("config_written"),
        "authorization_packet": payload.get("authorization_packet") or {},
        "prerequisites": payload.get("prerequisites") or {},
        "blockers": list(payload.get("blockers") or []),
        "warnings": list(payload.get("warnings") or []),
        "next_actions": list(payload.get("next_actions") or []),
        "safety": payload.get("safety") or dict(AUTHORIZATION_SAFETY),
        "ledger_path": payload.get("ledger_path"),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    if "lane_mode_change" in payload:
        compact["lane_mode_change"] = payload.get("lane_mode_change")
    return json.dumps(_sanitize(compact), sort_keys=True, separators=(",", ":"))


def _authorization_record(
    *,
    authorization_id: str,
    recorded_at_utc: str,
    lane_key: str,
    previous_lane_mode: str,
    authorization_status: str,
    operator_confirmation_valid: bool,
    prerequisites: Mapping[str, Any],
    blockers: list[str],
    warnings: list[str],
    authorization_packet: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": EVENT_TYPE,
        "authorization_id": authorization_id,
        "recorded_at_utc": recorded_at_utc,
        "lane_key": lane_key,
        "requested_mode": "tiny_live",
        "previous_lane_mode": previous_lane_mode,
        "authorization_status": authorization_status,
        "operator_confirmation_valid": bool(operator_confirmation_valid),
        "r126_gate_status": prerequisites.get("r126_gate_status"),
        "r129_paper_integration_status": prerequisites.get("r129_paper_integration_status"),
        "paper_proof_summary": prerequisites.get("paper_proof_summary") or {},
        "risk_contract_summary": prerequisites.get("risk_contract_summary") or {},
        "kill_switch_acknowledged": prerequisites.get("kill_switch_acknowledged") is True,
        "rollback_acknowledged": prerequisites.get("rollback_acknowledged") is True,
        "blockers": list(blockers),
        "warnings": list(warnings),
        "authorization_packet": dict(authorization_packet),
        "safety": dict(AUTHORIZATION_SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }


def _lane_mode_change_preview(
    *,
    request_lane_mode_tiny_live: bool,
    apply_lane_mode_change: bool,
    confirmation_valid: bool,
    lane_key: str | None,
    log_dir: Path,
    config_path: str | Path | None,
) -> dict[str, Any]:
    if not request_lane_mode_tiny_live and not apply_lane_mode_change:
        return {"requested": False, "config_written": False, "blockers": [], "warnings": []}
    preview = build_lane_command_preview(
        action="request-tiny-live-mode",
        lane_key=lane_key,
        apply=False,
        request_tiny_live=True,
        log_dir=log_dir,
        config_path=config_path,
    )
    blockers = list(preview.get("blockers") or [])
    warnings = list(preview.get("warnings") or [])
    if apply_lane_mode_change:
        if not confirmation_valid:
            blockers.append("exact tiny-live authorization confirmation phrase is required before lane mode apply can be considered")
        blockers.append("R130 does not mutate lane_controls.json; use R124 lane-control-command with its exact config-change confirmation phrase")
    return {
        "requested": True,
        "status": preview.get("status"),
        "previous_mode": preview.get("previous_mode"),
        "requested_mode": "tiny_live",
        "config_written": False,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "r124_preview": preview,
    }


def _paper_proof_summary(
    *,
    lane_key: str | None,
    paper_records: list[Mapping[str, Any]] | None,
    integration_records: list[Mapping[str, Any]] | None,
    log_dir: Path,
    now: datetime,
) -> dict[str, Any]:
    papers = list(paper_records) if paper_records is not None else load_paper_lane_executions(log_dir=log_dir, lane_key=lane_key)
    integrations = (
        list(integration_records)
        if integration_records is not None
        else load_paper_executor_integration_records(log_dir=log_dir, limit=20)
    )
    latest_integration_status = str(integrations[0].get("status") or "MISSING") if integrations else "MISSING"
    for record in reversed(papers):
        if lane_key and record.get("lane_key") != lane_key:
            continue
        if record.get("paper_action") == PAPER_BLOCKED or record.get("blockers"):
            continue
        safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
        if any(bool(safety.get(key)) for key in BLOCKING_SAFETY_KEYS):
            continue
        if safety.get("paper_live_separation_intact") is False:
            continue
        return {
            "matched": True,
            "source": "R125_AUTONOMOUS_PAPER_LANE_EXECUTION",
            "paper_proof_reference": record.get("paper_execution_id"),
            "recorded_at_utc": record.get("recorded_at_utc"),
            "age_seconds": _age_seconds(record.get("recorded_at_utc"), now),
            "paper_action": record.get("paper_action"),
            "r129_paper_integration_status": latest_integration_status,
            "blockers": [],
        }
    for record in integrations:
        if record.get("status") != PAPER_EXECUTOR_INTEGRATION_RECORDED:
            continue
        safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
        if any(bool(safety.get(key)) for key in BLOCKING_SAFETY_KEYS):
            continue
        if safety.get("paper_live_separation_intact") is False:
            continue
        return {
            "matched": True,
            "source": "R129_AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATION",
            "paper_proof_reference": record.get("integration_id"),
            "recorded_at_utc": record.get("recorded_at_utc"),
            "age_seconds": _age_seconds(record.get("recorded_at_utc"), now),
            "paper_action": "R129_INTEGRATION_PROOF",
            "r129_paper_integration_status": str(record.get("status") or latest_integration_status),
            "blockers": [],
        }
    return {
        "matched": False,
        "source": "MISSING",
        "paper_proof_reference": None,
        "recorded_at_utc": None,
        "age_seconds": None,
        "paper_action": None,
        "r129_paper_integration_status": latest_integration_status,
        "blockers": ["no recent R125/R129 autonomous paper proof for lane"],
    }


def _risk_contract_for_lane(lane: Mapping[str, Any] | None) -> dict[str, Any]:
    lane_key = str((lane or {}).get("lane_key") or "")
    candidate_id = f"normal|{lane_key}" if lane_key else "missing_candidate"
    return build_tiny_live_risk_contract_payload(candidate_id=candidate_id)


def _risk_contract_summary(risk: Mapping[str, Any]) -> dict[str, Any]:
    validation = risk.get("validation") if isinstance(risk.get("validation"), Mapping) else {}
    contract = risk.get("risk_contract") if isinstance(risk.get("risk_contract"), Mapping) else {}
    return {
        "candidate_id": risk.get("candidate_id"),
        "validation_status": validation.get("validation_status"),
        "valid_for_preflight": validation.get("valid_for_preflight") is True,
        "risk_contract_hash": risk.get("risk_contract_hash") or (risk_contract_hash(contract) if contract else None),
        "protective_stop_required": contract.get("protective_stop_required") is True,
        "take_profit_required": contract.get("take_profit_required") is True,
        "max_loss_usdt": contract.get("max_loss_usdt"),
        "max_position_notional_usdt": contract.get("max_position_notional_usdt"),
        "blockers": list(validation.get("blockers") or []),
    }


def _find_lane(controls: Mapping[str, Any], lane_key: str | None) -> dict[str, Any] | None:
    if not lane_key:
        return None
    lane = (controls.get("lane_map") or {}).get(str(lane_key))
    return dict(lane) if isinstance(lane, Mapping) else None


def _matching_eligibility(lane: Mapping[str, Any] | None, matrix: Mapping[str, Any]) -> dict[str, Any] | None:
    if not lane:
        return None
    for row in matrix.get("recommendations", []):
        if (
            str(row.get("timeframe") or "").strip().lower() == lane.get("timeframe")
            and str(row.get("direction") or "").strip().lower() == lane.get("direction")
            and str(row.get("entry_mode") or "").strip().lower() == lane.get("entry_mode")
        ):
            return dict(row)
    return None


def _eligibility_recommendation(row: Mapping[str, Any] | None) -> str | None:
    return str((row or {}).get("recommendation") or "") or None


def _eligibility_summary(row: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "recommendation": _eligibility_recommendation(row) or "MISSING",
        "sample_count": int((row or {}).get("sample_count") or 0),
        "win_rate_pct": float((row or {}).get("win_rate_pct") or 0.0),
        "avg_pnl_pct": float((row or {}).get("avg_pnl_pct") or 0.0),
    }


def _lane_summary(lane: Mapping[str, Any] | None) -> dict[str, Any]:
    if not lane:
        return {}
    return {
        "lane_key": lane.get("lane_key"),
        "symbol": lane.get("symbol"),
        "timeframe": lane.get("timeframe"),
        "direction": lane.get("direction"),
        "entry_mode": lane.get("entry_mode"),
        "mode": lane.get("mode"),
        "max_daily_trades": lane.get("max_daily_trades"),
        "max_daily_loss_pct": lane.get("max_daily_loss_pct"),
        "cooldown_after_loss_minutes": lane.get("cooldown_after_loss_minutes"),
        "freshness_seconds": lane.get("freshness_seconds"),
        "require_protective_orders": lane.get("require_protective_orders"),
    }


def _r126_readiness_hash(gate: Mapping[str, Any]) -> str | None:
    packet = gate.get("readiness_packet") if isinstance(gate.get("readiness_packet"), Mapping) else {}
    return packet.get("readiness_hash") or packet.get("authorization_hash")


def _safety_blockers(safety: Mapping[str, Any], prefix: str) -> list[str]:
    blockers = [f"{prefix}: {key}=true" for key in BLOCKING_SAFETY_KEYS if safety.get(key) is True]
    if safety and safety.get("paper_live_separation_intact") is False:
        blockers.append("paper/live separation is not intact")
    return blockers


def _next_actions(status: str, blockers: list[str], lane_mode_change: Mapping[str, Any]) -> list[str]:
    if status == TINY_LIVE_AUTHORIZATION_RECORDED:
        return ["rerun R126 gate review before any later dry authorization phase"]
    if lane_mode_change.get("blockers"):
        return ["use R124 lane-control-command for any actual lane mode mutation"]
    if blockers:
        return ["clear blockers at source surfaces, then rerun R130 preview"]
    return ["review packet and record authorization only with the exact R130 phrase"]


def _ledger_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _hash_packet(packet: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(_sanitize(dict(packet)), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _age_seconds(value: object, now: datetime) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max((now - parsed).total_seconds(), 0.0)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _sanitize(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_sanitize(value) for value in payload]
    if isinstance(payload, tuple):
        return [_sanitize(value) for value in payload]
    return payload
