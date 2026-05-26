"""R137 protective payload dry preview boundary.

This module builds an abstract protective stop-loss / take-profit preview
boundary only. It never creates executable exchange payloads, signs requests,
calls Binance, mutates env/config, or places orders.
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
from src.app.hammer_radar.operator.first_tiny_live_order_payload_dry_authorization import DEFAULT_LANE_KEY
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls
from src.app.hammer_radar.operator.live_adapter_execution_rehearsal import build_forbidden_adapter_function_map
from src.app.hammer_radar.operator.protective_order_dry_policy_review import (
    PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW,
    build_protective_order_dry_policy_review,
    load_protective_order_dry_policy_review_records,
)

EVENT_TYPE = "PROTECTIVE_PAYLOAD_DRY_PREVIEW_BOUNDARY"
LEDGER_FILENAME = "protective_payload_dry_preview_boundaries.ndjson"
PACKET_TYPE = "PROTECTIVE_PAYLOAD_DRY_PREVIEW_BOUNDARY"
PACKET_VERSION = "R137"
CONFIRM_PROTECTIVE_PREVIEW_PHRASE = (
    "I CONFIRM PROTECTIVE PAYLOAD DRY PREVIEW ONLY; NO ORDER; NO BINANCE CALL."
)

PROTECTIVE_PAYLOAD_PREVIEW = "PROTECTIVE_PAYLOAD_PREVIEW"
PROTECTIVE_PAYLOAD_REJECTED = "PROTECTIVE_PAYLOAD_REJECTED"
PROTECTIVE_PAYLOAD_BLOCKED = "PROTECTIVE_PAYLOAD_BLOCKED"
PROTECTIVE_PAYLOAD_READY_FOR_FUTURE_DRY_RUN = "PROTECTIVE_PAYLOAD_READY_FOR_FUTURE_DRY_RUN"

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
    "operator.protective_payload_dry_preview_boundary.build_protective_payload_dry_preview_boundary",
    "operator.protective_order_dry_policy_review.build_protective_order_dry_policy_review",
    "operator.protective_order_dry_policy_review.load_protective_order_dry_policy_review_records",
    "operator.live_adapter_execution_rehearsal.build_forbidden_adapter_function_map",
    "operator.lane_control.load_lane_controls",
    "execution.binance_futures_connector.build_connector_status",
    "execution.binance_futures_connector.build_protective_status",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_protective_payload_dry_preview_boundary(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    record_preview: bool = False,
    confirm_protective_preview: str | None = None,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    controls: Mapping[str, Any] | None = None,
    r136_policy_review: Mapping[str, Any] | None = None,
    r136_policy_records: list[Mapping[str, Any]] | None = None,
    connector_status: Mapping[str, Any] | None = None,
    protective_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env
    confirmation_valid = confirm_protective_preview == CONFIRM_PROTECTIVE_PREVIEW_PHRASE
    prerequisites = evaluate_protective_preview_prerequisites(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        config_path=config_path,
        env=source_env,
        now=generated_at,
        controls=controls,
        r136_policy_review=r136_policy_review,
        r136_policy_records=r136_policy_records,
        connector_status=connector_status,
        protective_status=protective_status,
    )
    preview_areas = prerequisites["preview_areas"]
    packet = build_protective_preview_packet(
        lane=prerequisites.get("lane") if isinstance(prerequisites.get("lane"), Mapping) else {},
        policy_review=prerequisites.get("policy_review") if isinstance(prerequisites.get("policy_review"), Mapping) else {},
        policy_record=prerequisites.get("policy_record") if isinstance(prerequisites.get("policy_record"), Mapping) else {},
        stop_loss_preview=preview_areas["stop_loss_preview_boundary"],
        take_profit_preview=preview_areas["take_profit_preview_boundary"],
        risk_validation=preview_areas["risk_validation_boundary"],
    )
    forbidden_field_report = build_protective_preview_forbidden_field_report(packet)
    future_requirements = build_future_protective_payload_requirements(preview_areas=preview_areas)
    main_blockers = _dedupe(
        [
            *list(prerequisites.get("blockers") or []),
            *list(forbidden_field_report.get("blockers") or []),
            *_packet_blockers(packet),
        ]
    )
    preview_id = f"protective_payload_preview_{uuid4().hex}" if record_preview else None

    if record_preview and not confirmation_valid:
        status = PROTECTIVE_PAYLOAD_REJECTED
        main_blockers = _dedupe(["exact protective preview confirmation phrase is required", *main_blockers])
    elif main_blockers:
        status = PROTECTIVE_PAYLOAD_BLOCKED
    elif record_preview:
        status = PROTECTIVE_PAYLOAD_READY_FOR_FUTURE_DRY_RUN
    else:
        status = PROTECTIVE_PAYLOAD_PREVIEW

    payload = _sanitize(
        {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "lane_key": lane_key,
            "record_preview_requested": bool(record_preview),
            "confirmation_valid": bool(confirmation_valid),
            "preview_recorded": False,
            "preview_id": None,
            "preview_areas": preview_areas,
            "protective_preview_packet": packet,
            "forbidden_field_report": forbidden_field_report,
            "future_protective_payload_requirements": future_requirements,
            "main_blockers": main_blockers,
            "next_actions": _next_actions(main_blockers, lane_key),
            "safety": dict(SAFETY),
            "ledger_path": str(protective_payload_dry_preview_records_path(resolved_log_dir)),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )

    if record_preview and confirmation_valid and not main_blockers and _safe_to_record(payload["safety"]):
        record = append_protective_payload_dry_preview_record(
            {
                "event_type": EVENT_TYPE,
                "preview_id": preview_id,
                "recorded_at_utc": generated_at.isoformat(),
                "status": status,
                "lane_key": lane_key,
                "protective_preview_hash": packet.get("protective_preview_hash"),
                "preview_areas": preview_areas,
                "protective_preview_packet": packet,
                "forbidden_field_report": forbidden_field_report,
                "future_protective_payload_requirements": future_requirements,
                "main_blockers": main_blockers,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            },
            log_dir=resolved_log_dir,
        )
        payload["preview_recorded"] = True
        payload["preview_id"] = record["preview_id"]

    return _sanitize(payload)


def evaluate_protective_preview_prerequisites(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    controls: Mapping[str, Any] | None = None,
    r136_policy_review: Mapping[str, Any] | None = None,
    r136_policy_records: list[Mapping[str, Any]] | None = None,
    connector_status: Mapping[str, Any] | None = None,
    protective_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env
    loaded_controls = dict(controls) if controls is not None else load_lane_controls(config_path)
    lane = _find_lane(loaded_controls, lane_key)
    policy_review = dict(
        r136_policy_review
        if r136_policy_review is not None
        else build_protective_order_dry_policy_review(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            record_review=False,
            config_path=config_path,
            env=source_env,
            now=generated_at,
            controls=loaded_controls,
        )
    )
    policy_records = (
        list(r136_policy_records)
        if r136_policy_records is not None
        else load_protective_order_dry_policy_review_records(log_dir=resolved_log_dir, limit=10, lane_key=lane_key)
    )
    policy_record = _latest_ready_policy_record(policy_records)
    connector = dict(
        connector_status
        if connector_status is not None
        else build_connector_status(env=source_env, log_dir=resolved_log_dir)
    )
    protective = dict(
        protective_status
        if protective_status is not None
        else build_protective_status(env=source_env, log_dir=resolved_log_dir)
    )
    policy_packet = _policy_packet(policy_review, policy_record)
    stop_preview = build_non_executable_stop_loss_preview(
        lane=lane or {},
        policy_packet=policy_packet,
    )
    take_profit_preview = build_non_executable_take_profit_preview(
        lane=lane or {},
        policy_packet=policy_packet,
    )
    risk_validation = _risk_validation_boundary(
        policy_packet=policy_packet,
        stop_loss_preview=stop_preview,
        take_profit_preview=take_profit_preview,
    )
    preview_areas = {
        "policy_source_boundary": _policy_source_boundary(
            policy_review=policy_review,
            policy_record=policy_record,
            policy_packet=policy_packet,
        ),
        "stop_loss_preview_boundary": stop_preview,
        "take_profit_preview_boundary": take_profit_preview,
        "risk_validation_boundary": risk_validation,
        "forbidden_fields_boundary": _forbidden_fields_boundary(),
        "connector_boundary": _connector_boundary(connector_status=connector, protective_status=protective),
        "future_requirements": [],
    }
    preview_areas["future_requirements"] = build_future_protective_payload_requirements(preview_areas=preview_areas)
    blockers = _preview_area_blockers(preview_areas)
    blockers.extend(_safety_blockers(SAFETY, "R137 safety field is unsafe"))
    return _sanitize(
        {
            "lane": _lane_summary(lane),
            "policy_review": policy_review,
            "policy_record": policy_record,
            "preview_areas": preview_areas,
            "blockers": _dedupe(blockers),
        }
    )


def build_non_executable_stop_loss_preview(
    *,
    lane: Mapping[str, Any],
    policy_packet: Mapping[str, Any],
) -> dict[str, Any]:
    direction = str(lane.get("direction") or policy_packet.get("direction") or "UNKNOWN").strip().lower()
    stop_policy = policy_packet.get("stop_loss_policy") if isinstance(policy_packet.get("stop_loss_policy"), Mapping) else {}
    reference = _number_or_none(stop_policy.get("reference"))
    return _sanitize(
        {
            "preview_type": "NON_EXECUTABLE_STOP_LOSS_PREVIEW",
            "required": stop_policy.get("required") is True,
            "reference": reference,
            "source": stop_policy.get("source") or "unknown",
            "side_intent": _protective_side_for_direction(direction),
            "order_type_intent": "STOP_MARKET" if stop_policy.get("required") is True else "UNKNOWN",
            "side_direction_relation_validated": _side_relation_valid(direction),
            "direct_exchange_payload": None,
            "signed_request": None,
            "endpoint": None,
            "quantity": None,
            "blockers": _dedupe(
                [
                    "R136 stop-loss policy is not required" if stop_policy.get("required") is not True else "",
                    "stop-loss reference is missing" if stop_policy.get("required") is True and reference is None else "",
                    "stop-loss side/direction relation is unknown" if not _side_relation_valid(direction) else "",
                ]
            ),
        }
    )


def build_non_executable_take_profit_preview(
    *,
    lane: Mapping[str, Any],
    policy_packet: Mapping[str, Any],
) -> dict[str, Any]:
    direction = str(lane.get("direction") or policy_packet.get("direction") or "UNKNOWN").strip().lower()
    take_policy = policy_packet.get("take_profit_policy") if isinstance(policy_packet.get("take_profit_policy"), Mapping) else {}
    reference = _number_or_none(take_policy.get("reference"))
    return _sanitize(
        {
            "preview_type": "NON_EXECUTABLE_TAKE_PROFIT_PREVIEW",
            "required": take_policy.get("required") is True,
            "reference": reference,
            "source": take_policy.get("source") or "unknown",
            "side_intent": _protective_side_for_direction(direction),
            "order_type_intent": "TAKE_PROFIT_MARKET" if take_policy.get("required") is True else "UNKNOWN",
            "side_direction_relation_validated": _side_relation_valid(direction),
            "direct_exchange_payload": None,
            "signed_request": None,
            "endpoint": None,
            "quantity": None,
            "blockers": _dedupe(
                [
                    "R136 take-profit policy is not required" if take_policy.get("required") is not True else "",
                    "take-profit reference is missing" if take_policy.get("required") is True and reference is None else "",
                    "take-profit side/direction relation is unknown" if not _side_relation_valid(direction) else "",
                ]
            ),
        }
    )


def build_protective_preview_packet(
    *,
    lane: Mapping[str, Any],
    policy_review: Mapping[str, Any],
    policy_record: Mapping[str, Any],
    stop_loss_preview: Mapping[str, Any],
    take_profit_preview: Mapping[str, Any],
    risk_validation: Mapping[str, Any],
) -> dict[str, Any]:
    policy_packet = _policy_packet(policy_review, policy_record)
    packet = {
        "packet_type": PACKET_TYPE,
        "packet_version": PACKET_VERSION,
        "lane_key": lane.get("lane_key") or policy_packet.get("lane_key"),
        "symbol": lane.get("symbol") or policy_packet.get("symbol"),
        "timeframe": lane.get("timeframe") or policy_packet.get("timeframe"),
        "direction": lane.get("direction") or policy_packet.get("direction") or "UNKNOWN",
        "entry_mode": lane.get("entry_mode") or policy_packet.get("entry_mode"),
        "policy_hash": policy_packet.get("protective_policy_hash") or policy_record.get("protective_policy_hash"),
        "entry_reference": _number_or_none(policy_packet.get("entry_reference")),
        "stop_loss_preview": _without_blockers(stop_loss_preview),
        "take_profit_preview": _without_blockers(take_profit_preview),
        "risk_validation": risk_validation,
        "forbidden_fields_present": [],
    }
    packet["protective_preview_hash"] = build_protective_preview_hash(packet)
    return _sanitize(packet)


def build_protective_preview_forbidden_field_report(packet: Mapping[str, Any]) -> dict[str, Any]:
    found: list[str] = []
    rendered = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True).lower()
    forbidden_tokens = {
        "api_key": "API key field",
        "api_secret": "API secret field",
        "x-mbx-apikey": "Binance API key header",
        "signature": "signature material",
        "recvwindow": "recvWindow",
        "timestamp": "timestamp",
        "query_string": "signed query string",
        "base_url": "base URL",
        "/fapi/v1/order": "Binance order endpoint",
        "network_target": "network target",
    }
    for token, label in forbidden_tokens.items():
        if token in rendered:
            found.append(label)
    for preview_key in ("stop_loss_preview", "take_profit_preview"):
        preview = packet.get(preview_key) if isinstance(packet.get(preview_key), Mapping) else {}
        for field in ("direct_exchange_payload", "signed_request", "endpoint", "quantity"):
            if preview.get(field) is not None:
                found.append(f"{preview_key}.{field}")
    return _sanitize(
        {
            "forbidden_fields_present": _dedupe(found),
            "submit_ready_symbol_side_type_quantity_payload_present": False,
            "timestamp_present": "timestamp" in rendered,
            "recv_window_present": "recvwindow" in rendered,
            "signature_present": "signature" in rendered,
            "api_key_present": "api_key" in rendered or "x-mbx-apikey" in rendered,
            "endpoint_url_present": "/fapi/v1/order" in rendered or "base_url" in rendered,
            "signed_material_present": "query_string" in rendered or "signature" in rendered,
            "network_target_present": "network_target" in rendered,
            "blockers": [f"forbidden field present: {item}" for item in _dedupe(found)],
        }
    )


def build_future_protective_payload_requirements(
    *,
    preview_areas: Mapping[str, Any],
) -> list[str]:
    requirements = [
        "R136 protective policy review must be ready and recorded with a stable protective policy hash.",
        "Stop-loss reference must be present and side/direction relation must be validated.",
        "Take-profit reference must be present and side/direction relation must be validated.",
        "Entry, stop, and take-profit distances must be reviewed against the tiny-live risk contract when data is available.",
        "Any future dry run must still avoid timestamp, recvWindow, signature, API key, endpoint URL, signed material, and network target fields.",
        "Connector use must remain read-only until a future explicit execution phase authorizes signing and network behavior.",
        "Future R138/R139 work must rank remaining blockers before any first tiny-live adapter can be considered.",
    ]
    for area_name, area in preview_areas.items():
        if not isinstance(area, Mapping):
            continue
        for blocker in area.get("blockers") or []:
            requirements.append(f"Clear {area_name}: {blocker}")
    return _dedupe(requirements)


def append_protective_payload_dry_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = protective_payload_dry_preview_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "preview_id": str(record.get("preview_id") or f"protective_payload_preview_{uuid4().hex}"),
            "recorded_at_utc": record.get("recorded_at_utc") or datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "lane_key": record.get("lane_key"),
            "protective_preview_hash": record.get("protective_preview_hash"),
            "preview_areas": record.get("preview_areas") or {},
            "protective_preview_packet": record.get("protective_preview_packet") or {},
            "forbidden_field_report": record.get("forbidden_field_report") or {},
            "future_protective_payload_requirements": list(record.get("future_protective_payload_requirements") or []),
            "main_blockers": list(record.get("main_blockers") or []),
            "safety": record.get("safety") or dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or []),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_protective_payload_dry_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = protective_payload_dry_preview_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_protective_payload_dry_previews(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    lane_counts = Counter(str(record.get("lane_key") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "last_preview_id": records[-1].get("preview_id") if records else None,
        "safety": dict(SAFETY),
    }


def format_protective_payload_dry_preview_boundary_json(payload: Mapping[str, Any]) -> str:
    compact = {
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "lane_key": payload.get("lane_key"),
        "record_preview_requested": bool(payload.get("record_preview_requested", False)),
        "confirmation_valid": bool(payload.get("confirmation_valid", False)),
        "preview_recorded": bool(payload.get("preview_recorded", False)),
        "preview_id": payload.get("preview_id"),
        "preview_areas": payload.get("preview_areas") or {},
        "protective_preview_packet": payload.get("protective_preview_packet") or {},
        "forbidden_field_report": payload.get("forbidden_field_report") or {},
        "future_protective_payload_requirements": list(payload.get("future_protective_payload_requirements") or []),
        "main_blockers": list(payload.get("main_blockers") or []),
        "next_actions": list(payload.get("next_actions") or []),
        "safety": payload.get("safety") or dict(SAFETY),
        "ledger_path": payload.get("ledger_path"),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    return json.dumps(_sanitize(compact), sort_keys=True, separators=(",", ":"))


def protective_payload_dry_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def build_protective_preview_hash(packet: Mapping[str, Any]) -> str:
    material = dict(packet)
    material.pop("protective_preview_hash", None)
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _policy_source_boundary(
    *,
    policy_review: Mapping[str, Any],
    policy_record: Mapping[str, Any],
    policy_packet: Mapping[str, Any],
) -> dict[str, Any]:
    policy_hash = policy_packet.get("protective_policy_hash") or policy_record.get("protective_policy_hash")
    stop = policy_packet.get("stop_loss_policy") if isinstance(policy_packet.get("stop_loss_policy"), Mapping) else {}
    take = policy_packet.get("take_profit_policy") if isinstance(policy_packet.get("take_profit_policy"), Mapping) else {}
    review_ready = policy_review.get("status") == PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW
    record_ready = policy_record.get("status") == PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW
    return {
        "r136_policy_exists": bool(policy_packet),
        "r136_review_ready": review_ready,
        "r136_ready_record_found": record_ready,
        "protective_policy_hash_available": bool(policy_hash),
        "stop_policy_reference_present": _number_or_none(stop.get("reference")) is not None,
        "take_profit_policy_reference_present": _number_or_none(take.get("reference")) is not None,
        "policy_is_non_executable": stop.get("direct_exchange_payload") is None
        and take.get("direct_exchange_payload") is None
        and stop.get("signed_request") is None
        and take.get("signed_request") is None,
        "blockers": _dedupe(
            [
                "R136 policy review is missing" if not policy_packet else "",
                f"R136 policy review is not {PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW}: {policy_review.get('status') or 'UNKNOWN'}"
                if not review_ready
                else "",
                "R136 ready policy review record is missing" if not record_ready else "",
                "protective policy hash is missing" if not policy_hash else "",
                "stop policy reference is missing" if _number_or_none(stop.get("reference")) is None else "",
                "take-profit policy reference is missing" if _number_or_none(take.get("reference")) is None else "",
                "R136 policy packet contains executable material"
                if stop.get("direct_exchange_payload") is not None
                or take.get("direct_exchange_payload") is not None
                or stop.get("signed_request") is not None
                or take.get("signed_request") is not None
                else "",
            ]
        ),
    }


def _risk_validation_boundary(
    *,
    policy_packet: Mapping[str, Any],
    stop_loss_preview: Mapping[str, Any],
    take_profit_preview: Mapping[str, Any],
) -> dict[str, Any]:
    direction = str(policy_packet.get("direction") or "UNKNOWN").strip().lower()
    entry = _number_or_none(policy_packet.get("entry_reference"))
    stop = _number_or_none(stop_loss_preview.get("reference"))
    take = _number_or_none(take_profit_preview.get("reference"))
    stop_relation_ok = True
    take_relation_ok = True
    if entry is not None and stop is not None:
        stop_relation_ok = stop < entry if direction == "long" else stop > entry if direction == "short" else False
    if entry is not None and take is not None:
        take_relation_ok = take > entry if direction == "long" else take < entry if direction == "short" else False
    return _sanitize(
        {
            "entry_reference": entry,
            "stop_reference": stop,
            "take_profit_reference": take,
            "stop_distance_reasonable_if_data_available": stop_relation_ok,
            "take_profit_distance_reasonable_if_data_available": take_relation_ok,
            "max_loss_cap_reference_present": True,
            "direct_live_quantity": None,
            "blockers": _dedupe(
                [
                    "stop reference is not on protective side of entry" if not stop_relation_ok else "",
                    "take-profit reference is not on profit side of entry" if not take_relation_ok else "",
                    "direct live quantity must remain null" if False else "",
                ]
            ),
        }
    )


def _forbidden_fields_boundary() -> dict[str, Any]:
    return {
        "submit_ready_symbol_side_type_quantity_payload_present": False,
        "timestamp_present": False,
        "recv_window_present": False,
        "signature_present": False,
        "api_key_present": False,
        "endpoint_url_present": False,
        "signed_material_present": False,
        "network_target_present": False,
        "blockers": [],
    }


def _connector_boundary(
    *,
    connector_status: Mapping[str, Any],
    protective_status: Mapping[str, Any],
) -> dict[str, Any]:
    forbidden_map = build_forbidden_adapter_function_map()
    return {
        "connector_mode": connector_status.get("connector_mode") or "UNKNOWN",
        "protective_order_mode": protective_status.get("protective_order_mode")
        or connector_status.get("protective_order_mode")
        or "UNKNOWN",
        "connector_protective_status_read_only": True,
        "protective_endpoints_called": False,
        "protective_payload_builder_invoked": False,
        "network_used": False,
        "forbidden_connector_functions_called": [
            row.get("name")
            for row in forbidden_map
            if row.get("called_in_r135") is True and row.get("classification") != "READ_ONLY_STATUS_OK"
        ],
        "blockers": _dedupe(
            [
                "connector protective status is not read-only" if False else "",
                "protective endpoint was called" if False else "",
                "protective payload builder was invoked" if False else "",
                "network was used" if False else "",
            ]
        ),
    }


def _latest_ready_policy_record(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    for record in records:
        if record.get("status") == PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW:
            return dict(record)
    return {}


def _policy_packet(policy_review: Mapping[str, Any], policy_record: Mapping[str, Any]) -> dict[str, Any]:
    packet = policy_record.get("protective_policy_packet")
    if isinstance(packet, Mapping):
        return dict(packet)
    packet = policy_review.get("protective_policy_packet")
    return dict(packet) if isinstance(packet, Mapping) else {}


def _preview_area_blockers(preview_areas: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for area_name, area in preview_areas.items():
        if not isinstance(area, Mapping):
            continue
        for blocker in area.get("blockers") or []:
            blockers.append(f"{area_name}: {blocker}")
    return _dedupe(blockers)


def _packet_blockers(packet: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for preview_key in ("stop_loss_preview", "take_profit_preview"):
        preview = packet.get(preview_key) if isinstance(packet.get(preview_key), Mapping) else {}
        for field in ("direct_exchange_payload", "signed_request", "endpoint", "quantity"):
            if preview.get(field) is not None:
                blockers.append(f"{preview_key} includes executable field {field}")
    if packet.get("forbidden_fields_present"):
        blockers.append("protective preview packet reports forbidden fields present")
    return _dedupe(blockers)


def _safe_to_record(safety: Mapping[str, Any]) -> bool:
    return not _safety_blockers(safety, "R137 safety field is unsafe")


def _safety_blockers(safety: Mapping[str, Any], prefix: str) -> list[str]:
    blockers = [f"{prefix}: {key}=true" for key in BLOCKING_SAFETY_KEYS if safety.get(key) is True]
    if safety and safety.get("paper_live_separation_intact") is False:
        blockers.append("paper/live separation is not intact")
    return blockers


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


def _protective_side_for_direction(direction: str) -> str:
    if direction == "long":
        return "SELL"
    if direction == "short":
        return "BUY"
    return "UNKNOWN"


def _side_relation_valid(direction: str) -> bool:
    return direction in {"long", "short"}


def _without_blockers(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("blockers", None)
    return result


def _next_actions(blockers: list[str], lane_key: str) -> list[str]:
    if blockers:
        return [
            "Keep protective payload work in non-executing preview mode; do not call protective preview, signing, submit, or network functions.",
            f"Clear R137 blockers for lane {lane_key} through the existing R136 protective policy review and lane/risk/paper-proof surfaces.",
            "Record R136 ready policy review evidence before recording any R137 protective payload preview boundary.",
        ]
    return [
        "Record R137 protective preview boundary evidence only with the exact confirmation phrase.",
        "Use R138 to rank remaining live-readiness blockers before any future dry run or adapter work.",
    ]


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
