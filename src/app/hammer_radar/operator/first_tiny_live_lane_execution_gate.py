"""R126 first tiny-live lane execution gate.

This module composes existing readiness, lane, router, and paper-proof
surfaces into one non-executing decision packet. It never creates Binance
order payloads, signs requests, calls exchange endpoints, or places orders.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution.binance_futures_connector import build_protective_status
from src.app.hammer_radar.operator.archive import get_log_dir, get_signals_path, load_signals
from src.app.hammer_radar.operator.autonomous_paper_lane_execution import (
    PAPER_BLOCKED,
    load_paper_lane_executions,
)
from src.app.hammer_radar.operator.final_live_preflight import READY, build_final_live_preflight
from src.app.hammer_radar.operator.first_live_activation_gate import (
    FIRST_LIVE_ACTIVATION_READY,
    build_first_live_activation_gate,
)
from src.app.hammer_radar.operator.fresh_signal_router import (
    ROUTED_TO_LANE,
    evaluate_candidate_against_lanes,
)
from src.app.hammer_radar.operator.lane_control import (
    LANE_ALLOWED,
    evaluate_lane_permission,
    load_lane_controls,
)
from src.app.hammer_radar.operator.strategy_performance import (
    ELIGIBLE_FOR_FUTURE_TINY_LIVE,
    build_live_eligibility_matrix,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    DEFAULT_CANDIDATE_ID,
    RISK_CONTRACT_VALID_FOR_PREFLIGHT,
    build_tiny_live_risk_contract_payload,
    risk_contract_hash,
)

TINY_LIVE_EXECUTION_BLOCKED = "TINY_LIVE_EXECUTION_BLOCKED"
TINY_LIVE_EXECUTION_READY = "TINY_LIVE_EXECUTION_READY"
EVENT_TYPE = "FIRST_TINY_LIVE_LANE_EXECUTION_GATE_REVIEW"
LEDGER_FILENAME = "first_tiny_live_lane_execution_gate_reviews.ndjson"
REQUIRED_CONFIRMATION_PHRASE = "I CONFIRM FIRST TINY LIVE LANE EXECUTION REVIEW ONLY; NO ORDER PLACED BY R126."
SOURCE_SURFACE = "operator.first_tiny_live_lane_execution_gate.build_first_tiny_live_lane_execution_gate"

SAFETY = {
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "network_allowed": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
}
BLOCKING_SAFETY_KEYS = (
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "order_payload_created",
    "network_allowed",
    "secrets_shown",
)
SOURCE_SURFACES_USED = [
    SOURCE_SURFACE,
    "operator.first_live_activation_gate.build_first_live_activation_gate",
    "operator.final_live_preflight.build_final_live_preflight",
    "operator.lane_control.load_lane_controls",
    "operator.lane_control.evaluate_lane_permission",
    "operator.fresh_signal_router.evaluate_candidate_against_lanes",
    "operator.autonomous_paper_lane_execution.load_paper_lane_executions",
    "operator.tiny_live_risk_contract.build_tiny_live_risk_contract_payload",
    "execution.binance_futures_connector.build_protective_status",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "logs/hammer_radar_forward/autonomous_paper_lane_executions.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_first_tiny_live_lane_execution_gate(
    *,
    log_dir: str | Path | None = None,
    lane_key: str | None = None,
    candidate_id: str | None = None,
    confirm_review_only: str | None = None,
    record: bool = True,
    config_path: str | Path | None = None,
    candidates: list[Mapping[str, Any] | object] | None = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    r106_gate: Mapping[str, Any] | None = None,
    global_gates: Mapping[str, Any] | None = None,
    risk_contract: Mapping[str, Any] | None = None,
    protective_readiness: Mapping[str, Any] | None = None,
    paper_records: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    try:
        controls = load_lane_controls(config_path)
        selected_lanes = [
            lane
            for lane in controls.get("lanes", [])
            if isinstance(lane, Mapping) and (lane_key is None or lane.get("lane_key") == lane_key)
        ]
        if not candidate_id and not any(str(lane.get("mode") or "").strip().lower() == "tiny_live" for lane in selected_lanes):
            payload = _blocked_no_tiny_live_lane_payload(
                generated_at=generated_at,
                lane_key=lane_key,
                selected_lanes=selected_lanes,
                confirm_review_only=confirm_review_only,
            )
            if record:
                append_tiny_live_gate_review_record(payload, log_dir=resolved_log_dir)
            return _sanitize(payload)
        source_candidates = candidates
        if source_candidates is None:
            source_path = get_signals_path(resolved_log_dir)
            if not source_path.exists():
                payload = _blocked_no_candidate_payload(
                    generated_at=generated_at,
                    reason="signals.ndjson candidate source is missing",
                    confirm_review_only=confirm_review_only,
                )
                if record:
                    append_tiny_live_gate_review_record(payload, log_dir=resolved_log_dir)
                return _sanitize(payload)
            source_candidates = load_signals(resolved_log_dir)
            if not source_candidates:
                payload = _blocked_no_candidate_payload(
                    generated_at=generated_at,
                    reason="no candidates available for routing",
                    confirm_review_only=confirm_review_only,
                )
                if record:
                    append_tiny_live_gate_review_record(payload, log_dir=resolved_log_dir)
                return _sanitize(payload)
        matrix = live_eligibility_matrix if live_eligibility_matrix is not None else build_live_eligibility_matrix(log_dir=resolved_log_dir)
        r106 = dict(
            r106_gate
            if r106_gate is not None
            else build_first_live_activation_gate(
                candidate_id=candidate_id or DEFAULT_CANDIDATE_ID,
                log_dir=resolved_log_dir,
                env=env,
                record=False,
            )
        )
        routed_rows = _build_routed_rows(
            log_dir=resolved_log_dir,
            controls=controls,
            candidates=source_candidates,
            matrix=matrix,
            global_gate=r106,
            now=generated_at,
            lane_key=lane_key,
            candidate_id=candidate_id,
        )
        active_candidate = _select_active_candidate(routed_rows, lane_key=lane_key, candidate_id=candidate_id)
        lane = _lane_for_candidate(active_candidate, controls)
        resolved_candidate_id = str((active_candidate or {}).get("candidate_id") or candidate_id or DEFAULT_CANDIDATE_ID)
        global_status = dict(
            global_gates
            if global_gates is not None
            else build_final_live_preflight(candidate_id=resolved_candidate_id, log_dir=resolved_log_dir, env=env)
        )
        risk_status = dict(risk_contract if risk_contract is not None else build_tiny_live_risk_contract_payload(candidate_id=resolved_candidate_id))
        protective_status = dict(
            protective_readiness
            if protective_readiness is not None
            else build_protective_status(env=os.environ if env is None else env, log_dir=resolved_log_dir)
        )
        records = paper_records if paper_records is not None else load_recent_paper_lane_executions(log_dir=resolved_log_dir, lane_key=lane_key)
        paper_proof = match_paper_proof_for_candidate(
            active_candidate,
            records=records,
            now=generated_at,
            freshness_seconds=_int_or_none((lane or {}).get("freshness_seconds") or (active_candidate or {}).get("freshness_seconds")),
        )
        preconditions = evaluate_tiny_live_lane_preconditions(
            active_candidate=active_candidate,
            lane=lane,
            r106_gate=r106,
            global_gates=global_status,
            risk_contract=risk_status,
            protective_readiness=protective_status,
            paper_proof=paper_proof,
            operator_confirmation=confirm_review_only,
            controls=controls,
            live_eligibility_matrix=matrix,
            log_dir=resolved_log_dir,
        )
        readiness_packet = build_tiny_live_execution_readiness_packet(
            active_candidate=active_candidate,
            lane=lane,
            risk_contract=risk_status,
            paper_proof=paper_proof,
            operator_confirmation=preconditions["operator_confirmation"],
        )
        blockers = _dedupe([*preconditions["blockers"], *_readiness_packet_blockers(readiness_packet)])
        warnings = _dedupe([*preconditions["warnings"], "R126 is review-only and cannot place orders."])
        status = TINY_LIVE_EXECUTION_READY if not blockers else TINY_LIVE_EXECUTION_BLOCKED
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "active_candidate": _compact_candidate(active_candidate),
            "lane": _compact_lane(lane),
            "lane_mode": str((lane or {}).get("mode") or (active_candidate or {}).get("lane_mode") or "missing").strip().lower(),
            "freshness": _freshness(active_candidate, lane),
            "paper_proof": paper_proof,
            "r106_gate": _compact_r106_gate(r106),
            "global_gates": _compact_global_gates(global_status),
            "risk_contract": _compact_risk_contract(risk_status),
            "protective_readiness": _compact_protective_readiness(protective_status, global_status),
            "operator_confirmation": preconditions["operator_confirmation"],
            "readiness_packet": readiness_packet,
            "blockers": blockers,
            "warnings": warnings,
            "next_actions": _next_actions(blockers),
            "safety": dict(SAFETY),
            "source_surfaces_used": _source_surfaces(r106, global_status),
        }
    except Exception as exc:  # pragma: no cover - defensive review surface
        payload = {
            "status": TINY_LIVE_EXECUTION_BLOCKED,
            "generated_at": generated_at.isoformat(),
            "active_candidate": {},
            "lane": {},
            "lane_mode": "missing",
            "freshness": {"fresh": False, "candidate_age_seconds": None, "freshness_seconds": None},
            "paper_proof": {"matched": False, "blockers": ["paper proof not evaluated due to source error"]},
            "r106_gate": {},
            "global_gates": {},
            "risk_contract": {},
            "protective_readiness": {},
            "operator_confirmation": _operator_confirmation(confirm_review_only),
            "readiness_packet": {},
            "blockers": [f"source error: {exc.__class__.__name__}"],
            "warnings": [],
            "next_actions": ["fix source error and rerun R126 gate"],
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    if record:
        append_tiny_live_gate_review_record(payload, log_dir=resolved_log_dir)
    return _sanitize(payload)


def build_tiny_live_execution_readiness_packet(
    *,
    active_candidate: Mapping[str, Any] | None,
    lane: Mapping[str, Any] | None,
    risk_contract: Mapping[str, Any] | None,
    paper_proof: Mapping[str, Any] | None,
    operator_confirmation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidate = dict(active_candidate or {})
    lane_record = dict(lane or {})
    risk = dict(risk_contract or {})
    contract = risk.get("risk_contract") if isinstance(risk.get("risk_contract"), Mapping) else {}
    funding = risk.get("funding_config") if isinstance(risk.get("funding_config"), Mapping) else {}
    proof = dict(paper_proof or {})
    risk_hash = risk.get("risk_contract_hash") or (risk_contract_hash(contract) if contract else None)
    packet = {
        "candidate_id": candidate.get("candidate_id"),
        "lane_key": lane_record.get("lane_key") or candidate.get("lane_key"),
        "symbol": lane_record.get("symbol") or candidate.get("symbol"),
        "timeframe": lane_record.get("timeframe") or candidate.get("timeframe"),
        "direction": lane_record.get("direction") or candidate.get("direction"),
        "entry_mode": lane_record.get("entry_mode") or candidate.get("entry_mode"),
        "lane_mode": lane_record.get("mode") or candidate.get("lane_mode"),
        "risk_contract_hash": risk_hash,
        "packet_hash": risk.get("packet_hash"),
        "max_daily_trades": lane_record.get("max_daily_trades"),
        "max_daily_loss_pct": lane_record.get("max_daily_loss_pct"),
        "max_loss_cap": _first_present(contract, "max_loss_usdt", "max_loss_cap") or funding.get("max_loss_usdt"),
        "freshness_seconds": lane_record.get("freshness_seconds") or candidate.get("freshness_seconds"),
        "paper_proof_id": proof.get("paper_proof_id"),
        "required_confirmation_phrase": REQUIRED_CONFIRMATION_PHRASE,
        "confirmation_valid": bool((operator_confirmation or {}).get("valid")),
    }
    packet["readiness_hash"] = _hash_packet(packet)
    return _sanitize(packet)


def load_recent_paper_lane_executions(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    return load_paper_lane_executions(log_dir=log_dir, limit=limit, lane_key=lane_key)


def match_paper_proof_for_candidate(
    candidate: Mapping[str, Any] | None,
    *,
    records: list[Mapping[str, Any]] | None,
    now: datetime | None = None,
    freshness_seconds: int | None = None,
) -> dict[str, Any]:
    if not candidate:
        return {"matched": False, "paper_proof_id": None, "blockers": ["no active candidate for paper proof match"]}
    generated_at = now or datetime.now(UTC)
    candidate_id = str(candidate.get("candidate_id") or "")
    lane_key = str(candidate.get("lane_key") or "")
    blockers: list[str] = []
    for record in reversed(list(records or [])):
        if str(record.get("candidate_id") or "") != candidate_id:
            continue
        if str(record.get("lane_key") or "") != lane_key:
            continue
        safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
        age_seconds = _age_seconds(record.get("recorded_at_utc"), generated_at)
        if record.get("paper_action") == PAPER_BLOCKED or record.get("blockers"):
            blockers.append("matching paper proof is blocked")
            continue
        if any(bool(safety.get(key)) for key in BLOCKING_SAFETY_KEYS):
            blockers.append("matching paper proof safety is not clean")
            continue
        if safety.get("paper_live_separation_intact") is not True:
            blockers.append("matching paper proof paper/live separation is not intact")
            continue
        if freshness_seconds and age_seconds is not None and age_seconds > freshness_seconds:
            blockers.append("matching paper proof is older than lane freshness_seconds")
            continue
        return {
            "matched": True,
            "paper_proof_id": record.get("paper_execution_id"),
            "paper_action": record.get("paper_action"),
            "recorded_at_utc": record.get("recorded_at_utc"),
            "age_seconds": age_seconds,
            "lane_key": lane_key,
            "candidate_id": candidate_id,
            "safety": {**dict(SAFETY), **{key: bool(safety.get(key, False)) for key in BLOCKING_SAFETY_KEYS}},
            "blockers": [],
        }
    return {
        "matched": False,
        "paper_proof_id": None,
        "lane_key": lane_key,
        "candidate_id": candidate_id,
        "blockers": blockers or ["no recent R125 paper execution or paper shadow for same lane/candidate tuple"],
    }


def evaluate_tiny_live_lane_preconditions(
    *,
    active_candidate: Mapping[str, Any] | None,
    lane: Mapping[str, Any] | None,
    r106_gate: Mapping[str, Any],
    global_gates: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    protective_readiness: Mapping[str, Any],
    paper_proof: Mapping[str, Any],
    operator_confirmation: str | None,
    controls: Mapping[str, Any] | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    confirmation = _operator_confirmation(operator_confirmation)
    if not active_candidate:
        blockers.append("no fresh routed candidate")
    elif active_candidate.get("route_status") != ROUTED_TO_LANE:
        blockers.append("active candidate is not ROUTED_TO_LANE")
    if not lane:
        blockers.append("candidate does not map to a configured lane")
    lane_mode = str((lane or {}).get("mode") or (active_candidate or {}).get("lane_mode") or "").strip().lower()
    if lane_mode != "tiny_live":
        blockers.append(f"lane mode is not tiny_live: {lane_mode or 'MISSING'}")
    freshness = _freshness(active_candidate, lane)
    if not freshness["fresh"]:
        blockers.append("candidate is not fresh under lane freshness_seconds")
    if active_candidate and lane:
        permission = evaluate_lane_permission(
            lane.get("symbol"),
            lane.get("timeframe"),
            lane.get("direction"),
            lane.get("entry_mode"),
            controls=controls,
            live_eligibility_matrix=live_eligibility_matrix,
            global_gate=r106_gate,
            log_dir=log_dir,
        )
        if permission.get("status") != LANE_ALLOWED:
            blockers.append(f"lane permission is not LANE_ALLOWED: {permission.get('status') or 'UNKNOWN'}")
        eligibility = permission.get("live_eligibility") if isinstance(permission.get("live_eligibility"), Mapping) else {}
        if eligibility.get("recommendation") != ELIGIBLE_FOR_FUTURE_TINY_LIVE:
            blockers.append("lane is not eligible for future tiny live")
        blockers.extend(str(item) for item in permission.get("blockers") or [])
    if paper_proof.get("matched") is not True:
        blockers.extend(str(item) for item in paper_proof.get("blockers") or ["paper proof missing"])
    if r106_gate.get("status") != FIRST_LIVE_ACTIVATION_READY:
        blockers.append("R106 first-live activation gate is not FIRST_LIVE_ACTIVATION_READY")
    if global_gates.get("status") != READY:
        blockers.append("global final live preflight is not READY")
    if global_gates.get("global_kill_switch") is not False:
        blockers.append("global kill switch active")
    if global_gates.get("live_execution_enabled") is not True:
        blockers.append("live execution flags are not enabled outside R126")
    if global_gates.get("live_orders_allowed") is not True:
        blockers.append("live order flags are not enabled outside R126")
    credentials = global_gates.get("binance_credentials_present") if isinstance(global_gates.get("binance_credentials_present"), Mapping) else {}
    if credentials.get("api_key_present") is not True or credentials.get("api_secret_present") is not True:
        blockers.append("Binance credential presence is not verified")
    account_status = global_gates.get("binance_account_status") if isinstance(global_gates.get("binance_account_status"), Mapping) else {}
    if not account_status:
        blockers.append("account/funding read-only check is missing")
    if _protective_ready(protective_readiness, global_gates) is not True:
        blockers.append("protective order readiness is false")
    risk_validation = risk_contract.get("validation") if isinstance(risk_contract.get("validation"), Mapping) else {}
    contract = risk_contract.get("risk_contract") if isinstance(risk_contract.get("risk_contract"), Mapping) else {}
    if risk_validation.get("validation_status") != RISK_CONTRACT_VALID_FOR_PREFLIGHT:
        blockers.append("tiny-live risk contract is missing or invalid")
    if _first_present(contract, "max_loss_usdt", "max_loss_cap") is None:
        blockers.append("tiny size/max loss cap is missing")
    if global_gates.get("no_conflicting_position_known") is not True:
        blockers.append("no-conflicting-position proof is missing")
    if global_gates.get("emergency_cancel_reviewed") is not True:
        blockers.append("emergency cancel path review is missing")
    if confirmation["valid"] is not True:
        blockers.append("operator confirmation phrase missing or invalid")
    safety = _combined_safety(active_candidate, paper_proof, r106_gate, global_gates, risk_contract, protective_readiness)
    if safety["paper_live_separation_intact"] is not True:
        blockers.append("paper/live separation is not intact")
    for key in BLOCKING_SAFETY_KEYS:
        if safety.get(key) is True:
            blockers.append(f"safety field is unsafe: {key}=true")
    return {
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "operator_confirmation": confirmation,
        "safety": safety,
    }


def append_tiny_live_gate_review_record(payload: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = tiny_live_gate_review_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    packet = payload.get("readiness_packet") if isinstance(payload.get("readiness_packet"), Mapping) else {}
    active_candidate = payload.get("active_candidate") if isinstance(payload.get("active_candidate"), Mapping) else {}
    record = {
        "event_type": EVENT_TYPE,
        "review_id": f"r126_gate_{uuid4().hex}",
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "status": payload.get("status"),
        "lane_key": packet.get("lane_key") or active_candidate.get("lane_key"),
        "candidate_id": packet.get("candidate_id") or active_candidate.get("candidate_id"),
        "readiness_hash": packet.get("readiness_hash"),
        "blockers": list(payload.get("blockers") or []),
        "warnings": list(payload.get("warnings") or []),
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "order_payload_created": False,
        "network_allowed": False,
        "secrets_shown": False,
        "paper_live_separation_intact": True,
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def tiny_live_gate_review_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_first_tiny_live_lane_execution_gate_json(payload: Mapping[str, Any]) -> str:
    compact = {
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "lane_key": (payload.get("readiness_packet") or {}).get("lane_key") if isinstance(payload.get("readiness_packet"), Mapping) else None,
        "candidate_id": (payload.get("readiness_packet") or {}).get("candidate_id") if isinstance(payload.get("readiness_packet"), Mapping) else None,
        "lane_mode": payload.get("lane_mode"),
        "blockers": list(payload.get("blockers") or []),
        "next_actions": list(payload.get("next_actions") or []),
        "readiness_packet": payload.get("readiness_packet") or {},
        "safety": payload.get("safety") or dict(SAFETY),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    return json.dumps(_sanitize(compact), sort_keys=True, separators=(",", ":"))


def _blocked_no_candidate_payload(*, generated_at: datetime, reason: str, confirm_review_only: str | None) -> dict[str, Any]:
    blockers = ["no fresh routed candidate", reason]
    return {
        "status": TINY_LIVE_EXECUTION_BLOCKED,
        "generated_at": generated_at.isoformat(),
        "active_candidate": {},
        "lane": {},
        "lane_mode": "missing",
        "freshness": {"fresh": False, "candidate_age_seconds": None, "freshness_seconds": None},
        "paper_proof": {"matched": False, "paper_proof_id": None, "blockers": ["no active candidate for paper proof match"]},
        "r106_gate": {"status": "NOT_EVALUATED_NO_FRESH_ROUTED_CANDIDATE"},
        "global_gates": {"status": "NOT_EVALUATED_NO_FRESH_ROUTED_CANDIDATE"},
        "risk_contract": {"validation_status": "NOT_EVALUATED_NO_FRESH_ROUTED_CANDIDATE"},
        "protective_readiness": {"protective_orders_ready": False, "blockers": ["not evaluated without fresh routed candidate"]},
        "operator_confirmation": _operator_confirmation(confirm_review_only),
        "readiness_packet": {},
        "blockers": blockers,
        "warnings": ["R126 skipped heavier live-readiness composition because no candidate source was available."],
        "next_actions": _next_actions(blockers),
        "safety": dict(SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }


def _blocked_no_tiny_live_lane_payload(
    *,
    generated_at: datetime,
    lane_key: str | None,
    selected_lanes: list[Mapping[str, Any]],
    confirm_review_only: str | None,
) -> dict[str, Any]:
    lane = dict(selected_lanes[0]) if len(selected_lanes) == 1 else {}
    mode = str(lane.get("mode") or "no configured tiny_live lane").strip().lower()
    blockers = [f"lane mode is not tiny_live: {mode}"]
    if lane_key and not selected_lanes:
        blockers.append("candidate does not map to a configured lane")
    return {
        "status": TINY_LIVE_EXECUTION_BLOCKED,
        "generated_at": generated_at.isoformat(),
        "active_candidate": {},
        "lane": _compact_lane(lane),
        "lane_mode": mode,
        "freshness": {"fresh": False, "candidate_age_seconds": None, "freshness_seconds": lane.get("freshness_seconds")},
        "paper_proof": {"matched": False, "paper_proof_id": None, "blockers": ["not evaluated without tiny_live lane mode"]},
        "r106_gate": {"status": "NOT_EVALUATED_LANE_NOT_TINY_LIVE"},
        "global_gates": {"status": "NOT_EVALUATED_LANE_NOT_TINY_LIVE"},
        "risk_contract": {"validation_status": "NOT_EVALUATED_LANE_NOT_TINY_LIVE"},
        "protective_readiness": {"protective_orders_ready": False, "blockers": ["not evaluated without tiny_live lane mode"]},
        "operator_confirmation": _operator_confirmation(confirm_review_only),
        "readiness_packet": {},
        "blockers": blockers,
        "warnings": ["R126 skipped heavier live-readiness composition because no selected lane is in tiny_live mode."],
        "next_actions": _next_actions(blockers),
        "safety": dict(SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }


def _build_routed_rows(
    *,
    log_dir: Path,
    controls: Mapping[str, Any],
    candidates: list[Mapping[str, Any] | object] | None,
    matrix: Mapping[str, Any],
    global_gate: Mapping[str, Any],
    now: datetime,
    lane_key: str | None,
    candidate_id: str | None,
) -> list[dict[str, Any]]:
    source_candidates = candidates
    source_path = get_signals_path(log_dir)
    if source_candidates is None:
        if not source_path.exists():
            return []
        source_candidates = load_signals(log_dir)
    rows: list[dict[str, Any]] = []
    for candidate in source_candidates:
        row = evaluate_candidate_against_lanes(
            candidate,
            controls=controls,
            live_eligibility_matrix=matrix,
            global_gate=global_gate,
            now=now,
            log_dir=log_dir,
        )
        if lane_key and row.get("lane_key") != lane_key:
            continue
        if candidate_id and row.get("candidate_id") != candidate_id:
            continue
        rows.append(row)
    return rows


def _select_active_candidate(rows: list[Mapping[str, Any]], *, lane_key: str | None, candidate_id: str | None) -> dict[str, Any] | None:
    routed = [dict(row) for row in rows if row.get("route_status") == ROUTED_TO_LANE]
    if candidate_id:
        for row in routed:
            if row.get("candidate_id") == candidate_id:
                return row
    if lane_key:
        for row in routed:
            if row.get("lane_key") == lane_key:
                return row
    if routed:
        return min(routed, key=lambda row: _float_or_none(row.get("candidate_age_seconds")) if _float_or_none(row.get("candidate_age_seconds")) is not None else 10**12)
    return None


def _lane_for_candidate(candidate: Mapping[str, Any] | None, controls: Mapping[str, Any]) -> dict[str, Any] | None:
    if not candidate:
        return None
    lane = (controls.get("lane_map") or {}).get(candidate.get("lane_key"))
    return dict(lane) if isinstance(lane, Mapping) else None


def _freshness(candidate: Mapping[str, Any] | None, lane: Mapping[str, Any] | None) -> dict[str, Any]:
    age = _float_or_none((candidate or {}).get("candidate_age_seconds"))
    freshness_seconds = _int_or_none((lane or {}).get("freshness_seconds") or (candidate or {}).get("freshness_seconds"))
    fresh = age is not None and freshness_seconds is not None and freshness_seconds > 0 and age <= freshness_seconds
    return {"fresh": fresh, "candidate_age_seconds": age, "freshness_seconds": freshness_seconds}


def _compact_candidate(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    if not candidate:
        return {}
    return {
        "candidate_id": candidate.get("candidate_id"),
        "lane_key": candidate.get("lane_key"),
        "symbol": candidate.get("symbol"),
        "timeframe": candidate.get("timeframe"),
        "direction": candidate.get("direction"),
        "entry_mode": candidate.get("entry_mode"),
        "route_status": candidate.get("route_status"),
        "route_action": candidate.get("route_action"),
        "candidate_age_seconds": candidate.get("candidate_age_seconds"),
        "freshness_seconds": candidate.get("freshness_seconds"),
        "safety": candidate.get("safety"),
    }


def _compact_lane(lane: Mapping[str, Any] | None) -> dict[str, Any]:
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


def _compact_r106_gate(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "candidate_id": payload.get("candidate_id"),
        "risk_contract_hash": payload.get("risk_contract_hash"),
        "packet_hash": payload.get("packet_hash"),
        "blockers": list(payload.get("blockers") or [])[:8],
        "warnings": list(payload.get("warnings") or [])[:5],
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def _compact_global_gates(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "live_execution_enabled": bool(payload.get("live_execution_enabled")),
        "live_orders_allowed": bool(payload.get("live_orders_allowed")),
        "global_kill_switch": bool(payload.get("global_kill_switch")),
        "connector_mode": payload.get("connector_mode"),
        "binance_credentials_present": payload.get("binance_credentials_present"),
        "binance_account_status": payload.get("binance_account_status"),
        "protective_orders_ready": bool(payload.get("protective_orders_ready")),
        "no_conflicting_position_known": payload.get("no_conflicting_position_known"),
        "emergency_cancel_reviewed": payload.get("emergency_cancel_reviewed"),
        "paper_live_separation_intact": payload.get("paper_live_separation_intact"),
        "blockers": list(payload.get("blockers") or [])[:8],
    }


def _compact_risk_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    contract = payload.get("risk_contract") if isinstance(payload.get("risk_contract"), Mapping) else {}
    validation = payload.get("validation") if isinstance(payload.get("validation"), Mapping) else {}
    return {
        "candidate_id": payload.get("candidate_id"),
        "validation_status": validation.get("validation_status"),
        "risk_contract_hash": payload.get("risk_contract_hash") or (risk_contract_hash(contract) if contract else None),
        "max_loss_cap": _first_present(contract, "max_loss_usdt", "max_loss_cap"),
        "max_margin_usdt": contract.get("max_margin_usdt"),
        "max_position_notional_usdt": contract.get("max_position_notional_usdt"),
        "protective_stop_required": contract.get("protective_stop_required"),
        "take_profit_required": contract.get("take_profit_required"),
        "blockers": list(validation.get("blockers") or [])[:8],
    }


def _compact_protective_readiness(protective: Mapping[str, Any], global_gates: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "protective_orders_ready": _protective_ready(protective, global_gates),
        "protective_order_mode": protective.get("protective_order_mode") or global_gates.get("protective_order_mode"),
        "protective_orders_required": protective.get("protective_orders_required"),
        "blockers": list(protective.get("blockers") or [])[:8],
    }


def _protective_ready(protective: Mapping[str, Any], global_gates: Mapping[str, Any]) -> bool:
    if "protective_orders_ready" in protective:
        return protective.get("protective_orders_ready") is True
    return global_gates.get("protective_orders_ready") is True


def _operator_confirmation(value: str | None) -> dict[str, Any]:
    return {
        "required": True,
        "present": bool(value),
        "valid": value == REQUIRED_CONFIRMATION_PHRASE,
        "required_confirmation_phrase": REQUIRED_CONFIRMATION_PHRASE,
        "review_only": True,
        "order_authorized_by_r126": False,
    }


def _combined_safety(*surfaces: Mapping[str, Any] | None) -> dict[str, bool]:
    safety = dict(SAFETY)
    for surface in surfaces:
        if not isinstance(surface, Mapping):
            continue
        source_safety = surface.get("safety") if isinstance(surface.get("safety"), Mapping) else surface
        for key in BLOCKING_SAFETY_KEYS:
            safety[key] = bool(safety[key] or source_safety.get(key) or source_safety.get("network_used" if key == "network_allowed" else key))
        if source_safety.get("paper_live_separation_intact") is False:
            safety["paper_live_separation_intact"] = False
    safety["paper_live_separation_intact"] = safety["paper_live_separation_intact"] and not any(safety[key] for key in BLOCKING_SAFETY_KEYS)
    return safety


def _readiness_packet_blockers(packet: Mapping[str, Any]) -> list[str]:
    required = ("candidate_id", "lane_key", "symbol", "timeframe", "direction", "entry_mode", "lane_mode", "readiness_hash")
    return [f"readiness packet missing {key}" for key in required if not packet.get(key)]


def _next_actions(blockers: list[str]) -> list[str]:
    actions: list[str] = []
    blocker_text = " | ".join(blockers).lower()
    if "no fresh routed candidate" in blocker_text:
        actions.append("wait for a fresh R123 routed candidate in the target lane")
    if "lane mode is not tiny_live" in blocker_text:
        actions.append("use R124 lane-control-command to request tiny_live mode after review")
    if "paper proof" in blocker_text:
        actions.append("run R125 autonomous paper lane execution for the same lane/candidate tuple")
    if "r106" in blocker_text or "global final live preflight" in blocker_text:
        actions.append("clear R106/global live gate blockers without changing R126")
    if "protective" in blocker_text:
        actions.append("complete protective order readiness review before any future authorization")
    if "operator confirmation" in blocker_text:
        actions.append("rerun with the exact R126 review-only confirmation phrase")
    if not actions:
        actions.append("review readiness packet and request a separate future authorization phase")
    return _dedupe(actions)


def _source_surfaces(*surfaces: Mapping[str, Any]) -> list[str]:
    sources = list(SOURCE_SURFACES_USED)
    for surface in surfaces:
        sources.extend(str(item) for item in surface.get("source_surfaces_used") or [])
    return _dedupe(sources)


def _age_seconds(value: object, now: datetime) -> float | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return max((now - parsed).total_seconds(), 0.0)


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _first_present(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _hash_packet(packet: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in packet.items() if key != "readiness_hash"}
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in BLOCKING_SAFETY_KEYS:
            if key in sanitized:
                sanitized[key] = False
        if "network_used" in sanitized:
            sanitized["network_used"] = False
        if "signed_payload_created" in sanitized:
            sanitized["signed_payload_created"] = False
        if "paper_live_separation_intact" in sanitized:
            sanitized["paper_live_separation_intact"] = bool(sanitized["paper_live_separation_intact"])
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
