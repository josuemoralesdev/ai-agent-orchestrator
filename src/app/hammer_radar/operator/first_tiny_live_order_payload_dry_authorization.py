"""R134 first tiny-live order payload dry authorization.

This module creates a non-executing dry authorization review packet only. It
does not create exchange payloads, sign requests, call Binance, mutate env or
config, enable live flags, or place orders.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution.binance_futures_connector import (
    build_connector_status,
    build_protective_status,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.autonomous_paper_lane_execution import (
    PAPER_BLOCKED,
    load_paper_lane_executions,
)
from src.app.hammer_radar.operator.autonomous_paper_lane_executor_integration import (
    PAPER_EXECUTOR_INTEGRATION_RECORDED,
    load_paper_executor_integration_records,
)
from src.app.hammer_radar.operator.first_live_activation_gate import FIRST_LIVE_ACTIVATION_READY
from src.app.hammer_radar.operator.first_tiny_live_autonomous_lane_authorization import (
    TINY_LIVE_AUTHORIZATION_READY_FOR_GATE_RECHECK,
    TINY_LIVE_AUTHORIZATION_RECORDED,
    build_first_tiny_live_autonomous_lane_authorization,
    load_tiny_live_lane_authorization_records,
)
from src.app.hammer_radar.operator.first_tiny_live_lane_execution_gate import (
    TINY_LIVE_EXECUTION_READY,
    build_first_tiny_live_lane_execution_gate,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls
from src.app.hammer_radar.operator.live_adapter_boundary_final_review import (
    LIVE_ADAPTER_BOUNDARY_REVIEW_READY,
    build_live_adapter_boundary_final_review,
    load_live_adapter_boundary_review_records,
)
from src.app.hammer_radar.operator.live_lane_kill_switch_rehearsal import (
    KILL_SWITCH_REHEARSAL_READY,
    build_live_lane_kill_switch_rehearsal,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    RISK_CONTRACT_VALID_FOR_PREFLIGHT,
    build_tiny_live_risk_contract_payload,
    risk_contract_hash,
)

DEFAULT_LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"
EVENT_TYPE = "FIRST_TINY_LIVE_ORDER_PAYLOAD_DRY_AUTHORIZATION"
LEDGER_FILENAME = "first_tiny_live_order_payload_dry_authorizations.ndjson"
PACKET_TYPE = "FIRST_TINY_LIVE_ORDER_PAYLOAD_DRY_AUTHORIZATION"
PACKET_VERSION = "R134"
CONFIRM_DRY_AUTHORIZATION_PHRASE = (
    "I CONFIRM FIRST TINY LIVE DRY AUTHORIZATION ONLY; NO ORDER; NO BINANCE CALL."
)
REQUIRED_FUTURE_EXECUTION_CONFIRMATION_PHRASE = (
    "FUTURE PHASE REQUIRED: explicit R135 live adapter execution rehearsal; no order; no Binance call."
)

DRY_AUTHORIZATION_PREVIEW = "DRY_AUTHORIZATION_PREVIEW"
DRY_AUTHORIZATION_REJECTED = "DRY_AUTHORIZATION_REJECTED"
DRY_AUTHORIZATION_BLOCKED = "DRY_AUTHORIZATION_BLOCKED"
DRY_AUTHORIZATION_READY = "DRY_AUTHORIZATION_READY"

DRY_AUTHORIZATION_SAFETY = {
    **SAFETY_FALSE,
    "executable_payload_created": False,
    "signed_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}
BLOCKING_SAFETY_KEYS = (
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "order_payload_created",
    "executable_payload_created",
    "signed_request_created",
    "network_allowed",
    "binance_order_endpoint_called",
    "binance_test_order_endpoint_called",
    "secrets_shown",
    "env_mutated",
    "config_written",
    "global_live_flags_changed",
)
SOURCE_SURFACES_USED = [
    "operator.first_tiny_live_order_payload_dry_authorization.build_first_tiny_live_order_payload_dry_authorization",
    "operator.lane_control.load_lane_controls",
    "operator.first_tiny_live_lane_execution_gate.build_first_tiny_live_lane_execution_gate",
    "operator.first_tiny_live_autonomous_lane_authorization.build_first_tiny_live_autonomous_lane_authorization",
    "operator.first_tiny_live_autonomous_lane_authorization.load_tiny_live_lane_authorization_records",
    "operator.live_lane_kill_switch_rehearsal.build_live_lane_kill_switch_rehearsal",
    "operator.live_adapter_boundary_final_review.build_live_adapter_boundary_final_review",
    "operator.live_adapter_boundary_final_review.load_live_adapter_boundary_review_records",
    "operator.autonomous_paper_lane_execution.load_paper_lane_executions",
    "operator.autonomous_paper_lane_executor_integration.load_paper_executor_integration_records",
    "operator.tiny_live_risk_contract.build_tiny_live_risk_contract_payload",
    "execution.binance_futures_connector.build_connector_status",
    "execution.binance_futures_connector.build_protective_status",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_first_tiny_live_order_payload_dry_authorization(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    record_dry_authorization: bool = False,
    confirm_dry_authorization: str | None = None,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    controls: Mapping[str, Any] | None = None,
    r126_gate: Mapping[str, Any] | None = None,
    r130_authorization: Mapping[str, Any] | None = None,
    r131_rehearsal: Mapping[str, Any] | None = None,
    r132_boundary_review: Mapping[str, Any] | None = None,
    r106_gate: Mapping[str, Any] | None = None,
    risk_contract: Mapping[str, Any] | None = None,
    protective_readiness: Mapping[str, Any] | None = None,
    paper_records: list[Mapping[str, Any]] | None = None,
    integration_records: list[Mapping[str, Any]] | None = None,
    authorization_records: list[Mapping[str, Any]] | None = None,
    boundary_review_records: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env
    confirmation_valid = confirm_dry_authorization == CONFIRM_DRY_AUTHORIZATION_PHRASE
    prerequisites = evaluate_dry_authorization_prerequisites(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        config_path=config_path,
        env=source_env,
        now=generated_at,
        controls=controls,
        r126_gate=r126_gate,
        r130_authorization=r130_authorization,
        r131_rehearsal=r131_rehearsal,
        r132_boundary_review=r132_boundary_review,
        r106_gate=r106_gate,
        risk_contract=risk_contract,
        protective_readiness=protective_readiness,
        paper_records=paper_records,
        integration_records=integration_records,
        authorization_records=authorization_records,
        boundary_review_records=boundary_review_records,
    )
    packet = build_non_executable_order_intent_packet(
        lane=prerequisites.get("lane") if isinstance(prerequisites.get("lane"), Mapping) else {},
        risk_contract=prerequisites.get("risk_contract") if isinstance(prerequisites.get("risk_contract"), Mapping) else {},
        paper_proof=prerequisites.get("paper_proof") if isinstance(prerequisites.get("paper_proof"), Mapping) else {},
        r126_gate=prerequisites.get("r126_gate") if isinstance(prerequisites.get("r126_gate"), Mapping) else {},
        r130_authorization=prerequisites.get("r130_authorization") if isinstance(prerequisites.get("r130_authorization"), Mapping) else {},
        r132_boundary_review=prerequisites.get("r132_boundary_review") if isinstance(prerequisites.get("r132_boundary_review"), Mapping) else {},
    )
    blockers = _dedupe([*list(prerequisites.get("blockers") or []), *_packet_blockers(packet)])
    warnings = _dedupe(
        [
            *list(prerequisites.get("warnings") or []),
            "R134 dry authorization is review-only and cannot be sent to an exchange.",
        ]
    )
    dry_authorization_recorded = False
    dry_authorization_id = f"r134_dry_authorization_{uuid4().hex}" if record_dry_authorization else None

    if record_dry_authorization and not confirmation_valid:
        status = DRY_AUTHORIZATION_REJECTED
        blockers = _dedupe(["exact dry authorization confirmation phrase is required", *blockers])
    elif blockers:
        status = DRY_AUTHORIZATION_BLOCKED
    elif record_dry_authorization:
        status = DRY_AUTHORIZATION_READY
        record = {
            "event_type": EVENT_TYPE,
            "dry_authorization_id": str(dry_authorization_id),
            "recorded_at_utc": generated_at.isoformat(),
            "status": status,
            "lane_key": lane_key,
            "dry_authorization_hash": packet.get("dry_authorization_hash"),
            "prerequisites": prerequisites,
            "blockers": blockers,
            "warnings": warnings,
            "dry_authorization_packet": packet,
            "safety": dict(DRY_AUTHORIZATION_SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        append_dry_authorization_review_record(record, log_dir=resolved_log_dir)
        dry_authorization_recorded = True
    else:
        status = DRY_AUTHORIZATION_PREVIEW

    return _sanitize(
        {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "lane_key": lane_key,
            "record_dry_authorization_requested": bool(record_dry_authorization),
            "confirmation_valid": bool(confirmation_valid),
            "dry_authorization_recorded": dry_authorization_recorded,
            "dry_authorization_id": dry_authorization_id if dry_authorization_recorded else None,
            "dry_authorization_packet": packet,
            "prerequisites": prerequisites,
            "blockers": blockers,
            "warnings": warnings,
            "next_actions": _next_actions(blockers, lane_key),
            "safety": dict(DRY_AUTHORIZATION_SAFETY),
            "ledger_path": str(dry_authorization_review_records_path(resolved_log_dir)),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )


def evaluate_dry_authorization_prerequisites(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    controls: Mapping[str, Any] | None = None,
    r126_gate: Mapping[str, Any] | None = None,
    r130_authorization: Mapping[str, Any] | None = None,
    r131_rehearsal: Mapping[str, Any] | None = None,
    r132_boundary_review: Mapping[str, Any] | None = None,
    r106_gate: Mapping[str, Any] | None = None,
    risk_contract: Mapping[str, Any] | None = None,
    protective_readiness: Mapping[str, Any] | None = None,
    paper_records: list[Mapping[str, Any]] | None = None,
    integration_records: list[Mapping[str, Any]] | None = None,
    authorization_records: list[Mapping[str, Any]] | None = None,
    boundary_review_records: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env
    loaded_controls = dict(controls) if controls is not None else load_lane_controls(config_path)
    lane = _find_lane(loaded_controls, lane_key)
    candidate_id = f"normal|{lane_key}" if lane_key else None
    risk = dict(
        risk_contract
        if risk_contract is not None
        else build_tiny_live_risk_contract_payload(candidate_id=candidate_id or "missing_candidate")
    )
    connector_status = build_connector_status(env=source_env, log_dir=resolved_log_dir)
    protective = dict(
        protective_readiness
        if protective_readiness is not None
        else build_protective_status(env=source_env, log_dir=resolved_log_dir)
    )
    gate = dict(
        r126_gate
        if r126_gate is not None
        else build_first_tiny_live_lane_execution_gate(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            record=False,
            config_path=config_path,
            env=source_env,
        )
    )
    authorization = dict(
        r130_authorization
        if r130_authorization is not None
        else build_first_tiny_live_autonomous_lane_authorization(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            config_path=config_path,
            record_authorization=False,
            r126_gate=gate,
            risk_contract=risk,
        )
    )
    rehearsal = dict(
        r131_rehearsal
        if r131_rehearsal is not None
        else build_live_lane_kill_switch_rehearsal(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            config_path=config_path,
            controls=loaded_controls,
        )
    )
    boundary_review = dict(
        r132_boundary_review
        if r132_boundary_review is not None
        else build_live_adapter_boundary_final_review(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            config_path=config_path,
            env=source_env,
        )
    )
    r106 = dict(r106_gate if r106_gate is not None else _r106_from_gate_or_boundary(gate, boundary_review))
    authorizations = (
        list(authorization_records)
        if authorization_records is not None
        else load_tiny_live_lane_authorization_records(log_dir=resolved_log_dir, lane_key=lane_key, limit=20)
    )
    boundary_records = (
        list(boundary_review_records)
        if boundary_review_records is not None
        else load_live_adapter_boundary_review_records(log_dir=resolved_log_dir, lane_key=lane_key, limit=20)
    )
    paper_proof = _paper_proof(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        now=generated_at,
        paper_records=paper_records,
        integration_records=integration_records,
    )
    risk_summary = _risk_summary(risk)
    boundary_summary = _boundary_summary(boundary_review, boundary_records=boundary_records)
    authorization_summary = _authorization_summary(authorization, authorizations=authorizations)
    credential_presence = _credential_presence(connector_status)
    blockers: list[str] = []
    warnings: list[str] = []

    if not lane:
        blockers.append("selected lane does not exist")
    lane_mode = str((lane or {}).get("mode") or "missing").strip().lower()
    if lane_mode != "tiny_live":
        blockers.append(f"lane mode is not tiny_live: {lane_mode}")
    if gate.get("status") != TINY_LIVE_EXECUTION_READY:
        blockers.append(f"R126 tiny-live execution gate is not {TINY_LIVE_EXECUTION_READY}: {gate.get('status') or 'UNKNOWN'}")
    if authorization_summary["ready"] is not True:
        blockers.append("R130 tiny-live authorization is missing or blocked")
    if rehearsal.get("status") != KILL_SWITCH_REHEARSAL_READY:
        blockers.append(f"R131 kill-switch rehearsal is not {KILL_SWITCH_REHEARSAL_READY}: {rehearsal.get('status') or 'UNKNOWN'}")
    if boundary_summary["ready_and_clear"] is not True:
        blockers.append("R132 live adapter boundary review is not ready and clear")
    if paper_proof.get("matched") is not True:
        blockers.append("recent autonomous paper proof is missing")
    if risk_summary["valid_for_preflight"] is not True:
        blockers.append("tiny-live risk contract is missing or invalid")
    if risk_summary["max_loss_present"] is not True:
        blockers.append("risk contract max loss is missing")
    if risk_summary["protective_policy_present"] is not True:
        blockers.append("risk contract protective policy is missing")
    protective_mode = str(protective.get("protective_order_mode") or "UNKNOWN")
    protective_ready = protective.get("protective_orders_ready") is True
    if not protective_ready and protective_mode != "PREVIEW_ONLY":
        blockers.append("protective readiness is missing")
    elif not protective_ready:
        warnings.append("protective orders are represented as non-executing dry requirements only")
    if credential_presence["key_present"] is not True or credential_presence["signing_key_present"] is not True:
        blockers.append("credential presence is missing or incomplete")
    if r106.get("status") != FIRST_LIVE_ACTIVATION_READY:
        blockers.append("R106/global first-live activation gate is blocked")
    blockers.extend(_safety_blockers(dict(DRY_AUTHORIZATION_SAFETY), "R134 safety field is unsafe"))
    blockers.extend(_safety_blockers(gate.get("safety") if isinstance(gate.get("safety"), Mapping) else {}, "R126 safety field is unsafe"))
    blockers.extend(_safety_blockers(authorization.get("safety") if isinstance(authorization.get("safety"), Mapping) else {}, "R130 safety field is unsafe"))
    blockers.extend(_safety_blockers(rehearsal.get("safety") if isinstance(rehearsal.get("safety"), Mapping) else {}, "R131 safety field is unsafe"))
    blockers.extend(_safety_blockers(boundary_review.get("safety") if isinstance(boundary_review.get("safety"), Mapping) else {}, "R132 safety field is unsafe"))

    return _sanitize(
        {
            "lane_exists": bool(lane),
            "lane_mode": lane_mode,
            "lane": _lane_summary(lane),
            "candidate_id": candidate_id,
            "r126_ready": gate.get("status") == TINY_LIVE_EXECUTION_READY,
            "r126_gate_status": gate.get("status"),
            "r126_readiness_hash": _r126_hash(gate),
            "r126_gate": _compact_gate(gate),
            "r130_authorization_ready": authorization_summary["ready"],
            "r130_authorization_hash": authorization_summary["authorization_hash"],
            "r130_authorization": authorization_summary,
            "r131_kill_switch_ready": rehearsal.get("status") == KILL_SWITCH_REHEARSAL_READY,
            "r131_rehearsal_status": rehearsal.get("status"),
            "r132_boundary_review_ready": boundary_summary["ready_and_clear"],
            "r132_boundary_review_reference": boundary_summary["reference"],
            "r132_boundary_review": boundary_summary,
            "paper_proof": paper_proof,
            "paper_proof_reference": paper_proof.get("paper_proof_reference"),
            "risk_contract": risk_summary,
            "risk_contract_hash": risk_summary.get("risk_contract_hash"),
            "protective_readiness": {
                "protective_orders_ready": protective_ready,
                "protective_order_mode": protective_mode,
                "non_executing_dry_requirement": not protective_ready and protective_mode == "PREVIEW_ONLY",
                "blockers": list(protective.get("blockers") or []),
            },
            "credential_presence": credential_presence,
            "r106_gate_status": r106.get("status") or "UNKNOWN",
            "safety": dict(DRY_AUTHORIZATION_SAFETY),
            "blockers": _dedupe(blockers),
            "warnings": _dedupe(warnings),
        }
    )


def build_non_executable_order_intent_packet(
    *,
    lane: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    paper_proof: Mapping[str, Any],
    r126_gate: Mapping[str, Any],
    r130_authorization: Mapping[str, Any],
    r132_boundary_review: Mapping[str, Any],
    entry_reference: float | int | None = None,
    stop_reference: float | int | None = None,
    take_profit_reference: float | int | None = None,
) -> dict[str, Any]:
    direction = str(lane.get("direction") or "UNKNOWN").strip().lower()
    packet = {
        "packet_type": PACKET_TYPE,
        "packet_version": PACKET_VERSION,
        "lane_key": lane.get("lane_key"),
        "candidate_id": risk_contract.get("candidate_id"),
        "symbol": lane.get("symbol") or risk_contract.get("symbol"),
        "timeframe": lane.get("timeframe") or risk_contract.get("timeframe"),
        "direction": lane.get("direction") or risk_contract.get("direction") or "UNKNOWN",
        "entry_mode": lane.get("entry_mode") or risk_contract.get("entry_mode"),
        "lane_mode": lane.get("mode") or "missing",
        "risk_contract_hash": risk_contract.get("risk_contract_hash"),
        "paper_proof_reference": paper_proof.get("paper_proof_reference"),
        "r126_readiness_hash": _r126_hash(r126_gate),
        "r130_authorization_hash": r130_authorization.get("authorization_hash"),
        "r132_boundary_review_reference": r132_boundary_review.get("reference"),
        "entry_intent": {
            "entry_reference": _number_or_none(entry_reference),
            "side": _side_for_direction(direction),
            "order_type_intent": "MARKET",
            "direct_exchange_payload": None,
            "signed_request": None,
        },
        "size_policy": {
            "type": "risk_contract_reference",
            "direct_live_quantity": None,
            "max_daily_loss_pct": lane.get("max_daily_loss_pct"),
            "max_daily_trades": lane.get("max_daily_trades"),
        },
        "protective_intent": build_non_executable_protective_intent_packet(
            risk_contract=risk_contract,
            stop_reference=stop_reference,
            take_profit_reference=take_profit_reference,
        ),
        "kill_switch_policy": {
            "requires_r131_ready": True,
            "global_kill_switch_must_be_reviewed": True,
            "r134_changes_kill_switch": False,
            "config_written": False,
            "global_live_flags_changed": False,
        },
        "required_future_execution_confirmation_phrase": REQUIRED_FUTURE_EXECUTION_CONFIRMATION_PHRASE,
    }
    packet["dry_authorization_hash"] = build_dry_authorization_hash(packet)
    return _sanitize(packet)


def build_non_executable_protective_intent_packet(
    *,
    risk_contract: Mapping[str, Any],
    stop_reference: float | int | None = None,
    take_profit_reference: float | int | None = None,
) -> dict[str, Any]:
    return {
        "stop_required": risk_contract.get("protective_stop_required") is True,
        "take_profit_required": risk_contract.get("take_profit_required") is True,
        "stop_reference": _number_or_none(stop_reference),
        "take_profit_reference": _number_or_none(take_profit_reference),
        "direct_exchange_payload": None,
        "signed_request": None,
    }


def build_dry_authorization_hash(packet: Mapping[str, Any]) -> str:
    material = dict(packet)
    material.pop("dry_authorization_hash", None)
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def append_dry_authorization_review_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = dry_authorization_review_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(dict(record))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_dry_authorization_review_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = dry_authorization_review_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if lane_key is not None and record.get("lane_key") != lane_key:
                continue
            records.append(record)
    if limit > 0:
        return list(reversed(records))[:limit]
    return records


def summarize_dry_authorization_reviews(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    lane_counts = Counter(str(record.get("lane_key") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "last_dry_authorization_id": records[-1].get("dry_authorization_id") if records else None,
        "safety": dict(DRY_AUTHORIZATION_SAFETY),
    }


def format_first_tiny_live_order_payload_dry_authorization_json(payload: Mapping[str, Any]) -> str:
    compact = {
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "lane_key": payload.get("lane_key"),
        "record_dry_authorization_requested": bool(payload.get("record_dry_authorization_requested", False)),
        "confirmation_valid": bool(payload.get("confirmation_valid", False)),
        "dry_authorization_recorded": bool(payload.get("dry_authorization_recorded", False)),
        "dry_authorization_id": payload.get("dry_authorization_id"),
        "dry_authorization_packet": payload.get("dry_authorization_packet") or {},
        "prerequisites": payload.get("prerequisites") or {},
        "blockers": list(payload.get("blockers") or []),
        "warnings": list(payload.get("warnings") or []),
        "next_actions": list(payload.get("next_actions") or []),
        "safety": payload.get("safety") or dict(DRY_AUTHORIZATION_SAFETY),
        "ledger_path": payload.get("ledger_path"),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    return json.dumps(_sanitize(compact), sort_keys=True, separators=(",", ":"))


def dry_authorization_review_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _find_lane(controls: Mapping[str, Any], lane_key: str | None) -> dict[str, Any] | None:
    lane = (controls.get("lane_map") or {}).get(str(lane_key or ""))
    return dict(lane) if isinstance(lane, Mapping) else None


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
        "freshness_seconds": lane.get("freshness_seconds"),
        "cooldown_after_loss_minutes": lane.get("cooldown_after_loss_minutes"),
        "require_protective_orders": lane.get("require_protective_orders"),
    }


def _paper_proof(
    *,
    log_dir: Path,
    lane_key: str,
    now: datetime,
    paper_records: list[Mapping[str, Any]] | None,
    integration_records: list[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    papers = list(paper_records) if paper_records is not None else load_paper_lane_executions(log_dir=log_dir, lane_key=lane_key)
    integrations = (
        list(integration_records)
        if integration_records is not None
        else load_paper_executor_integration_records(log_dir=log_dir, limit=20)
    )
    for record in reversed(papers):
        if record.get("lane_key") != lane_key:
            continue
        if record.get("paper_action") == PAPER_BLOCKED or record.get("blockers"):
            continue
        safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
        if _unsafe_safety(safety):
            continue
        return {
            "matched": True,
            "source": "R125_AUTONOMOUS_PAPER_LANE_EXECUTION",
            "paper_proof_reference": record.get("paper_execution_id"),
            "recorded_at_utc": record.get("recorded_at_utc"),
            "age_seconds": _age_seconds(record.get("recorded_at_utc"), now),
            "blockers": [],
        }
    for record in integrations:
        if record.get("status") != PAPER_EXECUTOR_INTEGRATION_RECORDED:
            continue
        safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
        if _unsafe_safety(safety):
            continue
        return {
            "matched": True,
            "source": "R129_AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATION",
            "paper_proof_reference": record.get("integration_id"),
            "recorded_at_utc": record.get("recorded_at_utc"),
            "age_seconds": _age_seconds(record.get("recorded_at_utc"), now),
            "blockers": [],
        }
    return {
        "matched": False,
        "source": "MISSING",
        "paper_proof_reference": None,
        "recorded_at_utc": None,
        "age_seconds": None,
        "blockers": ["no recent R125/R129 autonomous paper proof for lane"],
    }


def _risk_summary(risk: Mapping[str, Any]) -> dict[str, Any]:
    validation = risk.get("validation") if isinstance(risk.get("validation"), Mapping) else {}
    contract = risk.get("risk_contract") if isinstance(risk.get("risk_contract"), Mapping) else {}
    risk_hash = risk.get("risk_contract_hash") or (risk_contract_hash(contract) if contract else None)
    return {
        "candidate_id": risk.get("candidate_id"),
        "symbol": contract.get("symbol"),
        "timeframe": contract.get("timeframe"),
        "direction": contract.get("direction"),
        "entry_mode": contract.get("entry_mode"),
        "validation_status": validation.get("validation_status"),
        "valid_for_preflight": validation.get("validation_status") == RISK_CONTRACT_VALID_FOR_PREFLIGHT
        or validation.get("valid_for_preflight") is True,
        "risk_contract_hash": risk_hash,
        "max_loss_usdt": contract.get("max_loss_usdt"),
        "max_position_notional_usdt": contract.get("max_position_notional_usdt"),
        "max_loss_present": contract.get("max_loss_usdt") is not None,
        "protective_policy_present": contract.get("protective_stop_required") is True
        and contract.get("take_profit_required") is True,
        "protective_stop_required": contract.get("protective_stop_required") is True,
        "take_profit_required": contract.get("take_profit_required") is True,
        "blockers": list(validation.get("blockers") or []),
    }


def _authorization_summary(
    authorization: Mapping[str, Any],
    *,
    authorizations: list[Mapping[str, Any]],
) -> dict[str, Any]:
    latest_record = authorizations[0] if authorizations else {}
    packet = authorization.get("authorization_packet") if isinstance(authorization.get("authorization_packet"), Mapping) else {}
    latest_packet = latest_record.get("authorization_packet") if isinstance(latest_record.get("authorization_packet"), Mapping) else {}
    status = str(authorization.get("status") or latest_record.get("authorization_status") or "UNKNOWN")
    ready = (
        authorization.get("authorization_recorded") is True
        or status in {TINY_LIVE_AUTHORIZATION_RECORDED, TINY_LIVE_AUTHORIZATION_READY_FOR_GATE_RECHECK}
        or latest_record.get("authorization_status") == TINY_LIVE_AUTHORIZATION_RECORDED
    )
    return {
        "ready": ready,
        "status": status,
        "recorded_authorization_present": latest_record.get("authorization_status") == TINY_LIVE_AUTHORIZATION_RECORDED,
        "authorization_id": authorization.get("authorization_id") or latest_record.get("authorization_id"),
        "authorization_hash": packet.get("authorization_hash") or latest_packet.get("authorization_hash"),
        "blockers": _dedupe([*list(authorization.get("blockers") or []), *list(latest_record.get("blockers") or [])]),
    }


def _boundary_summary(
    boundary_review: Mapping[str, Any],
    *,
    boundary_records: list[Mapping[str, Any]],
) -> dict[str, Any]:
    latest_record = boundary_records[0] if boundary_records else {}
    review_status = boundary_review.get("status") or latest_record.get("status")
    main_blockers = _dedupe([*list(boundary_review.get("main_blockers") or []), *list(latest_record.get("main_blockers") or [])])
    boundary_reviews = boundary_review.get("boundary_reviews") if isinstance(boundary_review.get("boundary_reviews"), Mapping) else {}
    dry_readiness = boundary_reviews.get("dry_authorization_readiness") if isinstance(boundary_reviews.get("dry_authorization_readiness"), Mapping) else {}
    review_completed = dry_readiness.get("review_completed") is True or bool(boundary_reviews)
    reference = boundary_review.get("review_id") or latest_record.get("review_id")
    return {
        "ready_and_clear": review_status == LIVE_ADAPTER_BOUNDARY_REVIEW_READY and not main_blockers and review_completed,
        "status": review_status or "UNKNOWN",
        "review_completed": review_completed,
        "reference": reference,
        "main_blockers": main_blockers,
    }


def _credential_presence(connector_status: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "key_present": bool(connector_status.get("api_key_present")),
        "signing_key_present": bool(connector_status.get("api_secret_present")),
        "values_shown": False,
    }


def _r106_from_gate_or_boundary(gate: Mapping[str, Any], boundary_review: Mapping[str, Any]) -> dict[str, Any]:
    r106 = gate.get("r106_gate") if isinstance(gate.get("r106_gate"), Mapping) else {}
    if r106:
        return dict(r106)
    boundary_reviews = boundary_review.get("boundary_reviews") if isinstance(boundary_review.get("boundary_reviews"), Mapping) else {}
    global_gate = boundary_reviews.get("global_gate_boundary") if isinstance(boundary_reviews.get("global_gate_boundary"), Mapping) else {}
    return {"status": global_gate.get("r106_status")}


def _compact_gate(gate: Mapping[str, Any]) -> dict[str, Any]:
    packet = gate.get("readiness_packet") if isinstance(gate.get("readiness_packet"), Mapping) else {}
    return {
        "status": gate.get("status"),
        "candidate_id": packet.get("candidate_id"),
        "readiness_hash": packet.get("readiness_hash"),
        "blockers": list(gate.get("blockers") or []),
        "safety": gate.get("safety") or {},
    }


def _r126_hash(gate: Mapping[str, Any]) -> str | None:
    if gate.get("readiness_hash"):
        return str(gate.get("readiness_hash"))
    packet = gate.get("readiness_packet") if isinstance(gate.get("readiness_packet"), Mapping) else {}
    return packet.get("readiness_hash")


def _packet_blockers(packet: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    entry = packet.get("entry_intent") if isinstance(packet.get("entry_intent"), Mapping) else {}
    protective = packet.get("protective_intent") if isinstance(packet.get("protective_intent"), Mapping) else {}
    size = packet.get("size_policy") if isinstance(packet.get("size_policy"), Mapping) else {}
    if entry.get("direct_exchange_payload") is not None or protective.get("direct_exchange_payload") is not None:
        blockers.append("packet would include executable exchange payload")
    if entry.get("signed_request") is not None or protective.get("signed_request") is not None:
        blockers.append("packet would include signed request")
    if size.get("direct_live_quantity") is not None:
        blockers.append("packet would include direct live quantity")
    rendered = json.dumps(packet, sort_keys=True).lower()
    for forbidden in ("signature", "recvwindow", "timestamp", "/fapi/v1/order", "query_string", "base_url", "endpoint"):
        if forbidden in rendered:
            blockers.append(f"packet includes forbidden exchange material: {forbidden}")
    return _dedupe(blockers)


def _safety_blockers(safety: Mapping[str, Any], prefix: str) -> list[str]:
    blockers = [f"{prefix}: {key}=true" for key in BLOCKING_SAFETY_KEYS if safety.get(key) is True]
    if safety and safety.get("paper_live_separation_intact") is False:
        blockers.append("paper/live separation is not intact")
    return blockers


def _unsafe_safety(safety: Mapping[str, Any]) -> bool:
    return any(safety.get(key) is True for key in BLOCKING_SAFETY_KEYS) or safety.get("paper_live_separation_intact") is False


def _side_for_direction(direction: str) -> str:
    if direction == "long":
        return "BUY"
    if direction == "short":
        return "SELL"
    return "UNKNOWN"


def _number_or_none(value: float | int | None) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        return value
    return None


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


def _next_actions(blockers: list[str], lane_key: str) -> list[str]:
    if blockers:
        return [
            "Clear R126, R130, R131, R132, R106/global, paper proof, risk contract, protective, and credential blockers through existing surfaces.",
            f"Rerun R134 preview for lane {lane_key} after blockers clear.",
            "Do not run any connector preview, signing, test-order, or live-order functions.",
        ]
    return [
        "Confirmed R134 record is dry authorization evidence only.",
        "Prepare R135 live adapter execution rehearsal without placing orders or calling Binance.",
    ]


def _dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in BLOCKING_SAFETY_KEYS:
            if key in sanitized:
                sanitized[key] = False
        if "paper_live_separation_intact" in sanitized:
            sanitized["paper_live_separation_intact"] = True
        for key in ("signature", "query_string", "X-MBX-APIKEY", "api_key", "api_secret", "secret"):
            if key in sanitized:
                sanitized[key] = "<hidden>"
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
