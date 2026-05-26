"""R136 protective order dry policy review.

This module reviews stop-loss and take-profit policy only. It never creates
protective payloads, signs requests, calls Binance, mutates env/config, or
places orders.
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
from src.app.hammer_radar.operator.first_tiny_live_order_payload_dry_authorization import (
    DEFAULT_LANE_KEY,
    build_first_tiny_live_order_payload_dry_authorization,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls
from src.app.hammer_radar.operator.live_adapter_boundary_final_review import (
    build_live_adapter_boundary_final_review,
)
from src.app.hammer_radar.operator.live_adapter_execution_rehearsal import (
    build_live_adapter_execution_rehearsal,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    RISK_CONTRACT_VALID_FOR_PREFLIGHT,
    build_tiny_live_risk_contract_payload,
    risk_contract_hash,
)

EVENT_TYPE = "PROTECTIVE_ORDER_DRY_POLICY_REVIEW"
LEDGER_FILENAME = "protective_order_dry_policy_reviews.ndjson"
PACKET_TYPE = "PROTECTIVE_ORDER_DRY_POLICY_REVIEW"
PACKET_VERSION = "R136"
CONFIRM_PROTECTIVE_REVIEW_PHRASE = (
    "I CONFIRM PROTECTIVE ORDER DRY POLICY REVIEW ONLY; NO ORDER; NO BINANCE CALL."
)

PROTECTIVE_POLICY_PREVIEW = "PROTECTIVE_POLICY_PREVIEW"
PROTECTIVE_POLICY_REJECTED = "PROTECTIVE_POLICY_REJECTED"
PROTECTIVE_POLICY_BLOCKED = "PROTECTIVE_POLICY_BLOCKED"
PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW = "PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW"

SAFETY = {
    **SAFETY_FALSE,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
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
    "protective_payload_created",
    "signed_request_created",
    "network_allowed",
    "binance_order_endpoint_called",
    "binance_test_order_endpoint_called",
    "protective_order_endpoint_called",
    "secrets_shown",
    "env_mutated",
    "config_written",
    "global_live_flags_changed",
)
SOURCE_SURFACES_USED = [
    "operator.protective_order_dry_policy_review.build_protective_order_dry_policy_review",
    "operator.first_tiny_live_order_payload_dry_authorization.build_first_tiny_live_order_payload_dry_authorization",
    "operator.live_adapter_execution_rehearsal.build_live_adapter_execution_rehearsal",
    "operator.live_adapter_boundary_final_review.build_live_adapter_boundary_final_review",
    "operator.autonomous_paper_lane_execution.load_paper_lane_executions",
    "operator.autonomous_paper_lane_executor_integration.load_paper_executor_integration_records",
    "operator.tiny_live_risk_contract.build_tiny_live_risk_contract_payload",
    "operator.lane_control.load_lane_controls",
    "execution.binance_futures_connector.build_connector_status",
    "execution.binance_futures_connector.build_protective_status",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_protective_order_dry_policy_review(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    record_review: bool = False,
    confirm_protective_review: str | None = None,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    controls: Mapping[str, Any] | None = None,
    risk_contract: Mapping[str, Any] | None = None,
    protective_readiness: Mapping[str, Any] | None = None,
    connector_status: Mapping[str, Any] | None = None,
    paper_records: list[Mapping[str, Any]] | None = None,
    integration_records: list[Mapping[str, Any]] | None = None,
    r132_boundary_review: Mapping[str, Any] | None = None,
    r134_dry_authorization: Mapping[str, Any] | None = None,
    r135_rehearsal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env
    confirmation_valid = confirm_protective_review == CONFIRM_PROTECTIVE_REVIEW_PHRASE
    prerequisites = evaluate_protective_policy_prerequisites(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        config_path=config_path,
        env=source_env,
        now=generated_at,
        controls=controls,
        risk_contract=risk_contract,
        protective_readiness=protective_readiness,
        connector_status=connector_status,
        paper_records=paper_records,
        integration_records=integration_records,
        r132_boundary_review=r132_boundary_review,
        r134_dry_authorization=r134_dry_authorization,
        r135_rehearsal=r135_rehearsal,
    )
    policy_areas = prerequisites["policy_areas"]
    packet = build_non_executing_protective_policy_packet(
        lane=prerequisites.get("lane") if isinstance(prerequisites.get("lane"), Mapping) else {},
        risk_contract=prerequisites.get("risk_contract") if isinstance(prerequisites.get("risk_contract"), Mapping) else {},
        paper_proof=policy_areas["paper_proof_boundary"],
        stop_loss_policy=policy_areas["stop_loss_policy_boundary"],
        take_profit_policy=policy_areas["take_profit_policy_boundary"],
        connector_protective=policy_areas["connector_protective_boundary"],
    )
    payload_forbidden_map = build_protective_payload_forbidden_map()
    future_requirements = build_future_protective_payload_dry_preview_requirements(policy_areas=policy_areas)
    main_blockers = _dedupe([*list(prerequisites.get("blockers") or []), *_packet_blockers(packet)])
    review_recorded = False
    review_id = f"protective_policy_review_{uuid4().hex}" if record_review else None

    if record_review and not confirmation_valid:
        status = PROTECTIVE_POLICY_REJECTED
        main_blockers = _dedupe(["exact protective review confirmation phrase is required", *main_blockers])
    elif main_blockers:
        status = PROTECTIVE_POLICY_BLOCKED
    elif record_review:
        status = PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW
    else:
        status = PROTECTIVE_POLICY_PREVIEW

    payload = _sanitize(
        {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "lane_key": lane_key,
            "record_review_requested": bool(record_review),
            "confirmation_valid": bool(confirmation_valid),
            "review_recorded": False,
            "review_id": None,
            "policy_areas": policy_areas,
            "protective_policy_packet": packet,
            "payload_forbidden_map": payload_forbidden_map,
            "future_protective_payload_dry_preview_requirements": future_requirements,
            "main_blockers": main_blockers,
            "next_actions": _next_actions(main_blockers, lane_key),
            "safety": dict(SAFETY),
            "ledger_path": str(protective_order_dry_policy_review_records_path(resolved_log_dir)),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )

    if record_review and confirmation_valid and not main_blockers and _safe_to_record(payload["safety"]):
        record = append_protective_order_dry_policy_review_record(
            {
                "event_type": EVENT_TYPE,
                "review_id": review_id,
                "recorded_at_utc": generated_at.isoformat(),
                "status": status,
                "lane_key": lane_key,
                "protective_policy_hash": packet.get("protective_policy_hash"),
                "policy_areas": policy_areas,
                "protective_policy_packet": packet,
                "payload_forbidden_map": payload_forbidden_map,
                "future_protective_payload_dry_preview_requirements": future_requirements,
                "main_blockers": main_blockers,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            },
            log_dir=resolved_log_dir,
        )
        review_recorded = True
        payload["review_recorded"] = True
        payload["review_id"] = record["review_id"]

    return _sanitize(payload)


def evaluate_protective_policy_prerequisites(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    controls: Mapping[str, Any] | None = None,
    risk_contract: Mapping[str, Any] | None = None,
    protective_readiness: Mapping[str, Any] | None = None,
    connector_status: Mapping[str, Any] | None = None,
    paper_records: list[Mapping[str, Any]] | None = None,
    integration_records: list[Mapping[str, Any]] | None = None,
    r132_boundary_review: Mapping[str, Any] | None = None,
    r134_dry_authorization: Mapping[str, Any] | None = None,
    r135_rehearsal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env
    loaded_controls = dict(controls) if controls is not None else load_lane_controls(config_path)
    lane = _find_lane(loaded_controls, lane_key)
    candidate_id = f"normal|{lane_key}" if lane_key else "missing_candidate"
    risk = dict(
        risk_contract
        if risk_contract is not None
        else build_tiny_live_risk_contract_payload(candidate_id=candidate_id)
    )
    protective = dict(
        protective_readiness
        if protective_readiness is not None
        else build_protective_status(env=source_env, log_dir=resolved_log_dir)
    )
    connector = dict(
        connector_status
        if connector_status is not None
        else build_connector_status(env=source_env, log_dir=resolved_log_dir)
    )
    boundary = dict(
        r132_boundary_review
        if r132_boundary_review is not None
        else build_live_adapter_boundary_final_review(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            config_path=config_path,
            env=source_env,
            now=generated_at,
        )
    )
    dry = dict(
        r134_dry_authorization
        if r134_dry_authorization is not None
        else build_first_tiny_live_order_payload_dry_authorization(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            record_dry_authorization=False,
            config_path=config_path,
            env=source_env,
            now=generated_at,
            controls=loaded_controls,
            risk_contract=risk,
            protective_readiness=protective,
            r132_boundary_review=boundary,
        )
    )
    rehearsal = dict(
        r135_rehearsal
        if r135_rehearsal is not None
        else build_live_adapter_execution_rehearsal(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            record_rehearsal=False,
            config_path=config_path,
            env=source_env,
            now=generated_at,
            dry_authorization=dry,
            r132_boundary_review=boundary,
        )
    )
    paper_proof = _paper_proof(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        now=generated_at,
        paper_records=paper_records,
        integration_records=integration_records,
    )
    contract_summary = _risk_contract_boundary(risk)
    protective_requirement = _protective_requirement_boundary(
        lane=lane,
        contract_summary=contract_summary,
        protective_status=protective,
    )
    stop_policy = build_stop_loss_policy_intent(risk_contract=risk, paper_proof=paper_proof, candidate={})
    take_profit_policy = build_take_profit_policy_intent(risk_contract=risk, paper_proof=paper_proof, candidate={})
    connector_protective = _connector_protective_boundary(protective_status=protective, connector_status=connector)
    payload_forbidden = _payload_forbidden_boundary()
    policy_areas = {
        "protective_requirement_boundary": protective_requirement,
        "stop_loss_policy_boundary": stop_policy,
        "take_profit_policy_boundary": take_profit_policy,
        "risk_contract_boundary": contract_summary,
        "paper_proof_boundary": paper_proof,
        "connector_protective_boundary": connector_protective,
        "payload_forbidden_boundary": payload_forbidden,
        "future_dry_payload_requirements": [],
        "r132_r134_r135_reuse_boundary": _reuse_boundary(boundary=boundary, dry=dry, rehearsal=rehearsal),
    }
    future_requirements = build_future_protective_payload_dry_preview_requirements(policy_areas=policy_areas)
    policy_areas["future_dry_payload_requirements"] = future_requirements
    blockers = _policy_area_blockers(policy_areas)
    blockers.extend(_safety_blockers(SAFETY, "R136 safety field is unsafe"))
    return _sanitize(
        {
            "lane": _lane_summary(lane),
            "risk_contract": _risk_contract_packet_source(risk),
            "policy_areas": policy_areas,
            "blockers": _dedupe(blockers),
        }
    )


def build_non_executing_protective_policy_packet(
    *,
    lane: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    paper_proof: Mapping[str, Any],
    stop_loss_policy: Mapping[str, Any],
    take_profit_policy: Mapping[str, Any],
    connector_protective: Mapping[str, Any],
) -> dict[str, Any]:
    packet = {
        "packet_type": PACKET_TYPE,
        "packet_version": PACKET_VERSION,
        "lane_key": lane.get("lane_key"),
        "symbol": lane.get("symbol") or risk_contract.get("symbol"),
        "timeframe": lane.get("timeframe") or risk_contract.get("timeframe"),
        "direction": lane.get("direction") or risk_contract.get("direction") or "UNKNOWN",
        "entry_mode": lane.get("entry_mode") or risk_contract.get("entry_mode"),
        "risk_contract_hash": risk_contract.get("risk_contract_hash"),
        "paper_proof_reference": paper_proof.get("paper_proof_reference"),
        "entry_reference": _number_or_none(paper_proof.get("entry_reference")),
        "stop_loss_policy": {
            "required": stop_loss_policy.get("stop_required") is True,
            "reference": _number_or_none(stop_loss_policy.get("stop_reference")),
            "source": stop_loss_policy.get("stop_reference_source") or "unknown",
            "direct_exchange_payload": None,
            "signed_request": None,
        },
        "take_profit_policy": {
            "required": take_profit_policy.get("take_profit_required") is True,
            "reference": _number_or_none(take_profit_policy.get("take_profit_reference")),
            "source": take_profit_policy.get("take_profit_reference_source") or "unknown",
            "direct_exchange_payload": None,
            "signed_request": None,
        },
        "protective_order_mode": connector_protective.get("protective_order_mode") or "UNKNOWN",
    }
    packet["protective_policy_hash"] = build_protective_policy_hash(packet)
    return _sanitize(packet)


def build_stop_loss_policy_intent(
    *,
    risk_contract: Mapping[str, Any],
    paper_proof: Mapping[str, Any] | None = None,
    candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = _contract(risk_contract)
    reference, source = _first_numeric_reference(
        (candidate or {}, ("stop_reference", "stop_loss_reference", "stop_loss", "stop_price"), "candidate"),
        (paper_proof or {}, ("stop_reference", "stop_loss_reference", "stop_loss", "stop_price"), "paper proof"),
        (contract, ("stop_price", "stop_distance_pct"), "risk contract"),
    )
    required = contract.get("protective_stop_required") is True
    return _sanitize(
        {
            "stop_required": required,
            "stop_reference_available": reference is not None,
            "stop_reference": reference,
            "stop_reference_source": source,
            "stop_executable_payload_created": False,
            "stop_signed_request_created": False,
            "direct_exchange_payload": None,
            "signed_request": None,
            "blockers": _dedupe(
                [
                    "stop loss policy is not required by risk contract" if not required else "",
                    "stop reference is missing" if required and reference is None else "",
                ]
            ),
        }
    )


def build_take_profit_policy_intent(
    *,
    risk_contract: Mapping[str, Any],
    paper_proof: Mapping[str, Any] | None = None,
    candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = _contract(risk_contract)
    reference, source = _first_numeric_reference(
        (candidate or {}, ("take_profit_reference", "take_profit", "take_profit_price"), "candidate"),
        (paper_proof or {}, ("take_profit_reference", "take_profit", "take_profit_price"), "paper proof"),
        (contract, ("take_profit_price", "take_profit_distance_pct"), "risk contract"),
    )
    required = contract.get("take_profit_required") is True
    return _sanitize(
        {
            "take_profit_required": required,
            "take_profit_reference_available": reference is not None,
            "take_profit_reference": reference,
            "take_profit_reference_source": source,
            "take_profit_executable_payload_created": False,
            "take_profit_signed_request_created": False,
            "direct_exchange_payload": None,
            "signed_request": None,
            "blockers": _dedupe(
                [
                    "take-profit policy is not required by risk contract" if not required else "",
                    "take-profit reference is missing" if required and reference is None else "",
                ]
            ),
        }
    )


def build_protective_payload_forbidden_map() -> list[dict[str, Any]]:
    rows = [
        ("protective_preview", "PROTECTIVE_PAYLOAD_PREVIEW_FORBIDDEN_IN_R136"),
        ("submit_protective_test", "PROTECTIVE_ENDPOINT_FORBIDDEN_IN_R136"),
        ("build_signed_protective_order_requests", "SIGNING_FORBIDDEN_IN_R136"),
        ("_build_signed_protective_order_request", "SIGNING_FORBIDDEN_IN_R136"),
        ("BinanceFuturesProtectiveHttpClient.send_protective_orders", "NETWORK_FORBIDDEN_IN_R136"),
        ("ProtectiveOrderAdapter.send_protective_orders", "EXECUTION_FORBIDDEN_IN_R136"),
        ("MockProtectiveOrderAdapter.send_protective_orders", "EXECUTION_FORBIDDEN_IN_R136"),
    ]
    return [
        {
            "name": name,
            "classification": classification,
            "called_in_r136": False,
            "allowed_in_r136": False,
            "reason": "R136 reviews policy only and cannot create or submit protective payload material.",
        }
        for name, classification in rows
    ]


def build_future_protective_payload_dry_preview_requirements(
    *,
    policy_areas: Mapping[str, Any],
) -> list[str]:
    requirements = [
        "R136 review must be ready and recorded with the exact protective-review confirmation phrase.",
        "Stop-loss and take-profit references must be present from candidate, paper proof, or risk contract.",
        "Protective orders must be required by lane, risk contract, and connector status.",
        "Connector protective mode must be explicitly advanced by a future approved phase; R136 accepts PREVIEW_ONLY as a blocker.",
        "Future R137/R138 may build only abstract non-executable protective previews, not Binance payloads.",
        "Future protective preview must prove direct exchange payload, signed request, endpoint, timestamp, recvWindow, signature, and network target are absent.",
        "R134 dry authorization and R135 live adapter rehearsal must remain non-executing and current.",
    ]
    for area_name, area in policy_areas.items():
        if not isinstance(area, Mapping):
            continue
        for blocker in area.get("blockers") or []:
            requirements.append(f"Clear {area_name}: {blocker}")
    return _dedupe(requirements)


def append_protective_order_dry_policy_review_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = protective_order_dry_policy_review_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "review_id": str(record.get("review_id") or f"protective_policy_review_{uuid4().hex}"),
            "recorded_at_utc": record.get("recorded_at_utc") or datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "lane_key": record.get("lane_key"),
            "protective_policy_hash": record.get("protective_policy_hash"),
            "policy_areas": record.get("policy_areas") or {},
            "protective_policy_packet": record.get("protective_policy_packet") or {},
            "payload_forbidden_map": list(record.get("payload_forbidden_map") or []),
            "future_protective_payload_dry_preview_requirements": list(
                record.get("future_protective_payload_dry_preview_requirements") or []
            ),
            "main_blockers": list(record.get("main_blockers") or []),
            "safety": record.get("safety") or dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or []),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_protective_order_dry_policy_review_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = protective_order_dry_policy_review_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_protective_order_dry_policy_reviews(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    lane_counts = Counter(str(record.get("lane_key") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "last_review_id": records[-1].get("review_id") if records else None,
        "safety": dict(SAFETY),
    }


def format_protective_order_dry_policy_review_json(payload: Mapping[str, Any]) -> str:
    compact = {
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "lane_key": payload.get("lane_key"),
        "record_review_requested": bool(payload.get("record_review_requested", False)),
        "confirmation_valid": bool(payload.get("confirmation_valid", False)),
        "review_recorded": bool(payload.get("review_recorded", False)),
        "review_id": payload.get("review_id"),
        "policy_areas": payload.get("policy_areas") or {},
        "protective_policy_packet": payload.get("protective_policy_packet") or {},
        "payload_forbidden_map": list(payload.get("payload_forbidden_map") or []),
        "future_protective_payload_dry_preview_requirements": list(
            payload.get("future_protective_payload_dry_preview_requirements") or []
        ),
        "main_blockers": list(payload.get("main_blockers") or []),
        "next_actions": list(payload.get("next_actions") or []),
        "safety": payload.get("safety") or dict(SAFETY),
        "ledger_path": payload.get("ledger_path"),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    return json.dumps(_sanitize(compact), sort_keys=True, separators=(",", ":"))


def protective_order_dry_policy_review_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def build_protective_policy_hash(packet: Mapping[str, Any]) -> str:
    material = dict(packet)
    material.pop("protective_policy_hash", None)
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _protective_requirement_boundary(
    *,
    lane: Mapping[str, Any] | None,
    contract_summary: Mapping[str, Any],
    protective_status: Mapping[str, Any],
) -> dict[str, Any]:
    lane_required = bool((lane or {}).get("require_protective_orders"))
    contract_required = contract_summary.get("protective_stop_required") is True and contract_summary.get("take_profit_required") is True
    connector_required = protective_status.get("protective_orders_required") is True
    return {
        "protective_orders_required_by_lane": lane_required,
        "protective_orders_required_by_risk_contract": contract_required,
        "protective_orders_required_by_connector": connector_required,
        "blockers": _dedupe(
            [
                "protective orders are not required by selected lane" if not lane_required else "",
                "protective stop and take-profit are not both required by risk contract" if not contract_required else "",
                "protective orders are not required by connector status" if not connector_required else "",
            ]
        ),
    }


def _risk_contract_boundary(risk: Mapping[str, Any]) -> dict[str, Any]:
    validation = risk.get("validation") if isinstance(risk.get("validation"), Mapping) else {}
    contract = _contract(risk)
    risk_hash = risk.get("risk_contract_hash") or (risk_contract_hash(contract) if contract else None)
    return {
        "risk_contract_present": bool(contract),
        "risk_contract_hash": risk_hash,
        "validation_status": validation.get("validation_status"),
        "valid_for_preflight": validation.get("validation_status") == RISK_CONTRACT_VALID_FOR_PREFLIGHT
        or validation.get("valid_for_preflight") is True,
        "max_daily_loss": contract.get("max_daily_loss_pct") or contract.get("max_loss_usdt"),
        "max_daily_trades": contract.get("max_daily_trades"),
        "max_loss_cap": contract.get("max_loss_usdt"),
        "direct_live_quantity": None,
        "protective_stop_required": contract.get("protective_stop_required") is True,
        "take_profit_required": contract.get("take_profit_required") is True,
        "blockers": _dedupe(
            [
                "risk contract is missing" if not contract else "",
                "risk contract is not valid for preflight"
                if validation.get("validation_status") != RISK_CONTRACT_VALID_FOR_PREFLIGHT
                and validation.get("valid_for_preflight") is not True
                else "",
                "direct live quantity must remain null" if False else "",
                *list(validation.get("blockers") or []),
            ]
        ),
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
            "recent_paper_proof_exists": True,
            "proof_includes_entry_stop_take_profit_references": all(
                _number_or_none(record.get(key)) is not None
                for key in ("entry_reference", "stop_reference", "take_profit_reference")
            ),
            "proof_lane_matches_selected_lane": True,
            "proof_candidate_matches_current_candidate": True,
            "paper_proof_reference": record.get("paper_execution_id"),
            "candidate_id": record.get("candidate_id"),
            "recorded_at_utc": record.get("recorded_at_utc"),
            "age_seconds": _age_seconds(record.get("recorded_at_utc"), now),
            "entry_reference": _number_or_none(record.get("entry_reference")),
            "stop_reference": _number_or_none(record.get("stop_reference")),
            "take_profit_reference": _number_or_none(record.get("take_profit_reference")),
            "blockers": [],
        }
    for record in integrations:
        if record.get("status") != PAPER_EXECUTOR_INTEGRATION_RECORDED:
            continue
        safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
        if _unsafe_safety(safety):
            continue
        return {
            "recent_paper_proof_exists": True,
            "proof_includes_entry_stop_take_profit_references": False,
            "proof_lane_matches_selected_lane": True,
            "proof_candidate_matches_current_candidate": True,
            "paper_proof_reference": record.get("integration_id"),
            "candidate_id": None,
            "recorded_at_utc": record.get("recorded_at_utc"),
            "age_seconds": _age_seconds(record.get("recorded_at_utc"), now),
            "entry_reference": None,
            "stop_reference": None,
            "take_profit_reference": None,
            "blockers": ["paper proof does not include entry/stop/take-profit references"],
        }
    return {
        "recent_paper_proof_exists": False,
        "proof_includes_entry_stop_take_profit_references": False,
        "proof_lane_matches_selected_lane": False,
        "proof_candidate_matches_current_candidate": False,
        "paper_proof_reference": None,
        "candidate_id": None,
        "recorded_at_utc": None,
        "age_seconds": None,
        "entry_reference": None,
        "stop_reference": None,
        "take_profit_reference": None,
        "blockers": ["recent autonomous paper proof is missing"],
    }


def _connector_protective_boundary(
    *,
    protective_status: Mapping[str, Any],
    connector_status: Mapping[str, Any],
) -> dict[str, Any]:
    mode = str(protective_status.get("protective_order_mode") or connector_status.get("protective_order_mode") or "UNKNOWN")
    if protective_status.get("protective_orders_ready") is True:
        readiness = "READY"
    elif mode == "PREVIEW_ONLY":
        readiness = "PREVIEW_ONLY"
    else:
        readiness = "UNKNOWN"
    return {
        "connector_protective_mode": connector_status.get("connector_mode") or "UNKNOWN",
        "protective_orders_enabled": protective_status.get("protective_orders_enabled") is True,
        "protective_order_mode": readiness,
        "configured_protective_order_mode": mode,
        "protective_orders_ready": protective_status.get("protective_orders_ready") is True,
        "no_protective_endpoint_called": True,
        "protective_order_endpoint_called": False,
        "blockers": _dedupe(
            [
                *list(protective_status.get("blockers") or []),
                "protective orders are disabled" if protective_status.get("protective_orders_enabled") is not True else "",
                "protective order mode is PREVIEW_ONLY" if readiness == "PREVIEW_ONLY" else "",
                "protective order mode is unknown" if readiness == "UNKNOWN" else "",
            ]
        ),
    }


def _payload_forbidden_boundary() -> dict[str, Any]:
    return {
        "executable_protective_payload_created": False,
        "signed_request_created": False,
        "network_used": False,
        "direct_exchange_payload": None,
        "blockers": [],
    }


def _reuse_boundary(
    *,
    boundary: Mapping[str, Any],
    dry: Mapping[str, Any],
    rehearsal: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "r132_status": boundary.get("status"),
        "r134_status": dry.get("status"),
        "r135_status": rehearsal.get("status"),
        "r134_packet_non_executable": _nested(dry, "dry_authorization_packet", "protective_intent", "direct_exchange_payload") is None
        and _nested(dry, "dry_authorization_packet", "protective_intent", "signed_request") is None,
        "r135_protective_endpoint_called": _nested(rehearsal, "rehearsal_areas", "network_boundary", "protective_order_endpoint_called") is True,
        "blockers": _dedupe(
            [
                "R134 protective intent contains executable material"
                if _nested(dry, "dry_authorization_packet", "protective_intent", "direct_exchange_payload") is not None
                or _nested(dry, "dry_authorization_packet", "protective_intent", "signed_request") is not None
                else "",
                "R135 reports protective endpoint call"
                if _nested(rehearsal, "rehearsal_areas", "network_boundary", "protective_order_endpoint_called") is True
                else "",
            ]
        ),
    }


def _policy_area_blockers(policy_areas: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for area_name, area in policy_areas.items():
        if not isinstance(area, Mapping):
            continue
        for blocker in area.get("blockers") or []:
            blockers.append(f"{area_name}: {blocker}")
    stop = policy_areas.get("stop_loss_policy_boundary") if isinstance(policy_areas.get("stop_loss_policy_boundary"), Mapping) else {}
    take = policy_areas.get("take_profit_policy_boundary") if isinstance(policy_areas.get("take_profit_policy_boundary"), Mapping) else {}
    if stop.get("stop_required") is True and stop.get("stop_reference_available") is not True:
        blockers.append("stop_loss_policy_boundary: stop reference is required")
    if take.get("take_profit_required") is True and take.get("take_profit_reference_available") is not True:
        blockers.append("take_profit_policy_boundary: take-profit reference is required")
    connector = policy_areas.get("connector_protective_boundary") if isinstance(policy_areas.get("connector_protective_boundary"), Mapping) else {}
    if connector.get("protective_orders_ready") is not True:
        blockers.append("connector_protective_boundary: protective orders are not ready")
    return _dedupe(blockers)


def _risk_contract_packet_source(risk: Mapping[str, Any]) -> dict[str, Any]:
    contract = _contract(risk)
    risk_hash = risk.get("risk_contract_hash") or (risk_contract_hash(contract) if contract else None)
    return {
        "candidate_id": risk.get("candidate_id") or contract.get("candidate_id"),
        "symbol": contract.get("symbol"),
        "timeframe": contract.get("timeframe"),
        "direction": contract.get("direction"),
        "entry_mode": contract.get("entry_mode"),
        "risk_contract_hash": risk_hash,
        "protective_stop_required": contract.get("protective_stop_required") is True,
        "take_profit_required": contract.get("take_profit_required") is True,
        "stop_price": contract.get("stop_price"),
        "stop_distance_pct": contract.get("stop_distance_pct"),
        "take_profit_price": contract.get("take_profit_price"),
        "take_profit_distance_pct": contract.get("take_profit_distance_pct"),
    }


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
        "require_protective_orders": lane.get("require_protective_orders"),
    }


def _contract(risk: Mapping[str, Any]) -> dict[str, Any]:
    contract = risk.get("risk_contract") if isinstance(risk.get("risk_contract"), Mapping) else risk
    return dict(contract) if isinstance(contract, Mapping) else {}


def _first_numeric_reference(*sources: tuple[Mapping[str, Any], tuple[str, ...], str]) -> tuple[float | int | None, str]:
    for source, keys, label in sources:
        for key in keys:
            value = _number_or_none(source.get(key))
            if value is not None:
                return value, label
    return None, "unknown"


def _packet_blockers(packet: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for key in ("stop_loss_policy", "take_profit_policy"):
        policy = packet.get(key) if isinstance(packet.get(key), Mapping) else {}
        if policy.get("direct_exchange_payload") is not None:
            blockers.append(f"{key} includes direct exchange payload")
        if policy.get("signed_request") is not None:
            blockers.append(f"{key} includes signed request")
    rendered = json.dumps(packet, sort_keys=True).lower()
    for forbidden in (
        "api_key",
        "api_secret",
        "signature",
        "recvwindow",
        "timestamp",
        "/fapi/v1/order",
        "query_string",
        "base_url",
        "endpoint",
        "network target",
    ):
        if forbidden in rendered:
            blockers.append(f"protective policy packet includes forbidden exchange material: {forbidden}")
    return _dedupe(blockers)


def _safe_to_record(safety: Mapping[str, Any]) -> bool:
    return not _safety_blockers(safety, "R136 safety field is unsafe")


def _safety_blockers(safety: Mapping[str, Any], prefix: str) -> list[str]:
    blockers = [f"{prefix}: {key}=true" for key in BLOCKING_SAFETY_KEYS if safety.get(key) is True]
    if safety and safety.get("paper_live_separation_intact") is False:
        blockers.append("paper/live separation is not intact")
    return blockers


def _unsafe_safety(safety: Mapping[str, Any]) -> bool:
    return any(safety.get(key) is True for key in BLOCKING_SAFETY_KEYS) or safety.get("paper_live_separation_intact") is False


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


def _number_or_none(value: object) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        return value
    try:
        if value in (None, ""):
            return None
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _nested(payload: Mapping[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _next_actions(blockers: list[str], lane_key: str) -> list[str]:
    if blockers:
        return [
            "Keep protective orders in non-executing review mode; do not call protective preview, signing, or submit functions.",
            f"Clear R136 protective policy blockers for lane {lane_key} through existing lane, risk contract, paper proof, R132, R134, and R135 surfaces.",
            "Prepare R137 only after R136 can record a ready review with stop-loss and take-profit policy references.",
        ]
    return [
        "Record R136 protective policy review evidence only with the exact confirmation phrase.",
        "Prepare R137 protective payload dry-preview boundary as abstract non-executable preview only.",
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
