"""R135 live adapter execution rehearsal.

This module rehearses the path from the R134 dry authorization packet to the
live adapter boundary. It never creates executable exchange payloads, signs
requests, calls Binance, mutates env/config, or places orders.
"""

from __future__ import annotations

import inspect
import json
import os
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_tiny_live_order_payload_dry_authorization import (
    DEFAULT_LANE_KEY,
    DRY_AUTHORIZATION_BLOCKED,
    DRY_AUTHORIZATION_READY,
    build_first_tiny_live_order_payload_dry_authorization,
    load_dry_authorization_review_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.live_adapter_boundary_final_review import (
    LIVE_ADAPTER_BOUNDARY_REVIEW_READY,
    build_live_adapter_boundary_final_review,
)

EVENT_TYPE = "LIVE_ADAPTER_EXECUTION_REHEARSAL"
LEDGER_FILENAME = "live_adapter_execution_rehearsals.ndjson"
CONFIRM_ADAPTER_REHEARSAL_PHRASE = "I CONFIRM LIVE ADAPTER REHEARSAL ONLY; NO ORDER; NO BINANCE CALL."

LIVE_ADAPTER_REHEARSAL_PREVIEW = "LIVE_ADAPTER_REHEARSAL_PREVIEW"
LIVE_ADAPTER_REHEARSAL_REJECTED = "LIVE_ADAPTER_REHEARSAL_REJECTED"
LIVE_ADAPTER_REHEARSAL_BLOCKED = "LIVE_ADAPTER_REHEARSAL_BLOCKED"
LIVE_ADAPTER_REHEARSAL_READY_FOR_FUTURE_IMPLEMENTATION = (
    "LIVE_ADAPTER_REHEARSAL_READY_FOR_FUTURE_IMPLEMENTATION"
)

READ_ONLY_STATUS_OK = "READ_ONLY_STATUS_OK"
PAYLOAD_PREVIEW_FORBIDDEN_IN_R135 = "PAYLOAD_PREVIEW_FORBIDDEN_IN_R135"
SIGNING_FORBIDDEN = "SIGNING_FORBIDDEN"
NETWORK_FORBIDDEN = "NETWORK_FORBIDDEN"
EXECUTION_FORBIDDEN = "EXECUTION_FORBIDDEN"

SAFETY = {
    **SAFETY_FALSE,
    "executable_payload_created": False,
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
    "operator.live_adapter_execution_rehearsal.build_live_adapter_execution_rehearsal",
    "operator.first_tiny_live_order_payload_dry_authorization.build_first_tiny_live_order_payload_dry_authorization",
    "operator.first_tiny_live_order_payload_dry_authorization.load_dry_authorization_review_records",
    "operator.live_adapter_boundary_final_review.build_live_adapter_boundary_final_review",
    "operator.live_lane_kill_switch_rehearsal via R132 kill_switch_boundary",
    "operator.first_live_activation_gate via R132 global_gate_boundary",
    "operator.final_live_preflight via R132 global_gate_boundary",
    "operator.live_env_boundary_review via R132 global_gate_boundary",
    "execution.binance_futures_connector static function map",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_live_adapter_execution_rehearsal(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    record_rehearsal: bool = False,
    confirm_adapter_rehearsal: str | None = None,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    dry_authorization: Mapping[str, Any] | None = None,
    r132_boundary_review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env
    confirmation_valid = confirm_adapter_rehearsal == CONFIRM_ADAPTER_REHEARSAL_PHRASE
    dry = dict(
        dry_authorization
        if dry_authorization is not None
        else build_first_tiny_live_order_payload_dry_authorization(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            record_dry_authorization=False,
            config_path=config_path,
            env=source_env,
            now=generated_at,
        )
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
    latest_dry_records = load_dry_authorization_review_records(log_dir=resolved_log_dir, limit=10, lane_key=lane_key)
    rehearsal_areas = inspect_adapter_rehearsal_path(
        lane_key=lane_key,
        dry_authorization=dry,
        r132_boundary_review=boundary,
        latest_dry_authorization_records=latest_dry_records,
        env=source_env,
    )
    forbidden_function_map = build_forbidden_adapter_function_map()
    stop_conditions = build_rehearsal_stop_conditions(
        rehearsal_areas=rehearsal_areas,
        dry_authorization=dry,
        r132_boundary_review=boundary,
        forbidden_function_map=forbidden_function_map,
        safety=SAFETY,
    )
    future_requirements = build_future_execution_adapter_requirements(
        rehearsal_areas=rehearsal_areas,
        stop_conditions=stop_conditions,
    )
    main_blockers = _main_blockers(stop_conditions)
    rehearsal_recorded = False
    rehearsal_id = f"r135_live_adapter_execution_rehearsal_{uuid4().hex}" if record_rehearsal else None

    if record_rehearsal and not confirmation_valid:
        status = LIVE_ADAPTER_REHEARSAL_REJECTED
        main_blockers = _dedupe(["exact live adapter rehearsal confirmation phrase is required", *main_blockers])
    elif main_blockers:
        status = LIVE_ADAPTER_REHEARSAL_BLOCKED
    elif record_rehearsal:
        status = LIVE_ADAPTER_REHEARSAL_READY_FOR_FUTURE_IMPLEMENTATION
    else:
        status = LIVE_ADAPTER_REHEARSAL_PREVIEW

    payload = _sanitize(
        {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "lane_key": lane_key,
            "record_rehearsal_requested": bool(record_rehearsal),
            "confirmation_valid": bool(confirmation_valid),
            "rehearsal_recorded": False,
            "rehearsal_id": None,
            "rehearsal_areas": rehearsal_areas,
            "forbidden_function_map": forbidden_function_map,
            "stop_conditions": stop_conditions,
            "future_execution_adapter_requirements": future_requirements,
            "main_blockers": main_blockers,
            "next_actions": _next_actions(main_blockers, lane_key),
            "safety": dict(SAFETY),
            "ledger_path": str(live_adapter_execution_rehearsal_records_path(resolved_log_dir)),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )

    if record_rehearsal and confirmation_valid and _safe_to_record(payload["safety"]):
        record = append_live_adapter_execution_rehearsal_record(
            {
                "event_type": EVENT_TYPE,
                "rehearsal_id": rehearsal_id,
                "recorded_at_utc": generated_at.isoformat(),
                "status": status,
                "lane_key": lane_key,
                "rehearsal_areas": rehearsal_areas,
                "forbidden_function_map": forbidden_function_map,
                "stop_conditions": stop_conditions,
                "future_execution_adapter_requirements": future_requirements,
                "main_blockers": main_blockers,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            },
            log_dir=resolved_log_dir,
        )
        rehearsal_recorded = True
        payload["rehearsal_recorded"] = True
        payload["rehearsal_id"] = record["rehearsal_id"]

    return _sanitize(payload)


def inspect_adapter_rehearsal_path(
    *,
    lane_key: str,
    dry_authorization: Mapping[str, Any],
    r132_boundary_review: Mapping[str, Any],
    latest_dry_authorization_records: list[Mapping[str, Any]] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    packet = dry_authorization.get("dry_authorization_packet") if isinstance(dry_authorization.get("dry_authorization_packet"), Mapping) else {}
    prerequisites = dry_authorization.get("prerequisites") if isinstance(dry_authorization.get("prerequisites"), Mapping) else {}
    boundary_reviews = r132_boundary_review.get("boundary_reviews") if isinstance(r132_boundary_review.get("boundary_reviews"), Mapping) else {}
    latest_record = (latest_dry_authorization_records or [{}])[0] if latest_dry_authorization_records else {}
    packet_hash = packet.get("dry_authorization_hash") or latest_record.get("dry_authorization_hash")
    credential_presence = prerequisites.get("credential_presence") if isinstance(prerequisites.get("credential_presence"), Mapping) else {}
    protective = prerequisites.get("protective_readiness") if isinstance(prerequisites.get("protective_readiness"), Mapping) else {}
    global_gate = boundary_reviews.get("global_gate_boundary") if isinstance(boundary_reviews.get("global_gate_boundary"), Mapping) else {}
    kill_switch = boundary_reviews.get("kill_switch_boundary") if isinstance(boundary_reviews.get("kill_switch_boundary"), Mapping) else {}
    protective_boundary = boundary_reviews.get("protective_order_boundary") if isinstance(boundary_reviews.get("protective_order_boundary"), Mapping) else {}
    source_env = os.environ if env is None else env

    return _sanitize(
        {
            "dry_authorization_boundary": {
                "r134_status": dry_authorization.get("status"),
                "dry_authorization_packet_exists": bool(packet),
                "dry_authorization_hash": packet_hash,
                "dry_authorization_record_found": bool(latest_record),
                "must_be_non_executable": True,
                "blockers": list(dry_authorization.get("blockers") or []),
            },
            "adapter_function_boundary": {
                "connector_module": "src.app.hammer_radar.execution.binance_futures_connector",
                "available_connector_functions": _available_connector_functions(),
                "classification_summary": _classification_summary(build_forbidden_adapter_function_map()),
                "forbidden_functions_called": False,
                "read_only_status_builders_only": True,
            },
            "payload_boundary": {
                "executable_payload_created": False,
                "order_payload_created": False,
                "signed_request_created": False,
                "direct_exchange_payload": None,
                "r134_entry_direct_exchange_payload": _nested(packet, "entry_intent", "direct_exchange_payload"),
                "r134_protective_direct_exchange_payload": _nested(packet, "protective_intent", "direct_exchange_payload"),
            },
            "protective_boundary": build_protective_rehearsal_requirements(
                protective_readiness=protective,
                protective_boundary=protective_boundary,
            ),
            "credential_boundary": {
                "api_key_present": bool(credential_presence.get("key_present") or source_env.get("BINANCE_API_KEY")),
                "api_secret_present": bool(
                    credential_presence.get("signing_key_present") or source_env.get("BINANCE_API_SECRET")
                ),
                "values_shown": False,
                "secrets_shown": False,
                "signed_request_created": False,
            },
            "network_boundary": {
                "network_allowed": False,
                "binance_order_endpoint_called": False,
                "binance_test_order_endpoint_called": False,
                "protective_order_endpoint_called": False,
                "account_or_balance_endpoint_called": False,
                "signed_request_created": False,
            },
            "kill_switch_boundary": {
                "r131_status": kill_switch.get("r131_status") or prerequisites.get("r131_rehearsal_status"),
                "global_kill_switch_blocks_live_intent": kill_switch.get("global_kill_switch_blocks_live_intent") is True,
                "lane_disable_blocks_live_intent": kill_switch.get("lane_disable_blocks_live_intent") is True,
                "rollback_blocks_live_intent": kill_switch.get("rollback_blocks_live_intent") is True,
                "blockers": list(kill_switch.get("blockers") or []),
            },
            "global_gate_boundary": {
                "r106_status": global_gate.get("r106_status") or prerequisites.get("r106_gate_status"),
                "final_live_preflight_status": global_gate.get("final_live_preflight_status"),
                "live_env_boundary_status": global_gate.get("live_env_boundary_status"),
                "live_arming_preflight_status": global_gate.get("live_arming_preflight_status"),
                "live_execution_enabled": global_gate.get("live_execution_enabled") is True,
                "live_orders_allowed": global_gate.get("live_orders_allowed") is True,
                "global_kill_switch": global_gate.get("global_kill_switch") is True,
                "blockers": list(global_gate.get("blockers") or []),
            },
            "future_execution_requirements": build_future_execution_adapter_requirements(
                rehearsal_areas={},
                stop_conditions=[],
            ),
        }
    )


def build_forbidden_adapter_function_map() -> list[dict[str, Any]]:
    function_names = {
        READ_ONLY_STATUS_OK: [
            "build_connector_status",
            "build_protective_status",
            "load_connector_attempts",
            "load_protective_attempts",
            "connector_attempts_path",
            "protective_attempts_path",
            "sanitize_signed_params",
            "sanitize_headers",
        ],
        PAYLOAD_PREVIEW_FORBIDDEN_IN_R135: [
            "preview_payload",
            "protective_preview",
            "_payload_preview_from_pack",
            "_protective_payload_previews_from_pack",
        ],
        SIGNING_FORBIDDEN: [
            "build_canonical_query",
            "sign_query",
            "build_signed_test_order_request",
            "build_signed_live_order_request",
            "build_signed_protective_order_requests",
            "_build_signed_protective_order_request",
        ],
        NETWORK_FORBIDDEN: [
            "BinanceFuturesHttpClient.send_test_order",
            "BinanceFuturesLiveHttpClient.send_live_order",
            "BinanceFuturesProtectiveHttpClient.send_protective_orders",
            "submit_test_order",
            "submit_protective_test",
        ],
        EXECUTION_FORBIDDEN: [
            "execute_live_order",
            "BinanceOrderAdapter.submit_order",
            "SignedTestOrderAdapter.send_test_order",
            "SignedLiveOrderAdapter.send_live_order",
            "ProtectiveOrderAdapter.send_protective_orders",
            "MockSignedLiveOrderAdapter.send_live_order",
        ],
    }
    rows: list[dict[str, Any]] = []
    for classification, names in function_names.items():
        for name in names:
            rows.append(
                {
                    "name": name,
                    "available": _connector_member_available(name),
                    "classification": classification,
                    "called_in_r135": False,
                    "allowed_in_r135": classification == READ_ONLY_STATUS_OK,
                    "reason": _classification_reason(classification),
                }
            )
    return rows


def build_rehearsal_stop_conditions(
    *,
    rehearsal_areas: Mapping[str, Any],
    dry_authorization: Mapping[str, Any],
    r132_boundary_review: Mapping[str, Any],
    forbidden_function_map: list[Mapping[str, Any]],
    safety: Mapping[str, Any],
) -> list[dict[str, Any]]:
    dry_boundary = rehearsal_areas.get("dry_authorization_boundary") if isinstance(rehearsal_areas.get("dry_authorization_boundary"), Mapping) else {}
    protective = rehearsal_areas.get("protective_boundary") if isinstance(rehearsal_areas.get("protective_boundary"), Mapping) else {}
    credentials = rehearsal_areas.get("credential_boundary") if isinstance(rehearsal_areas.get("credential_boundary"), Mapping) else {}
    network = rehearsal_areas.get("network_boundary") if isinstance(rehearsal_areas.get("network_boundary"), Mapping) else {}
    kill = rehearsal_areas.get("kill_switch_boundary") if isinstance(rehearsal_areas.get("kill_switch_boundary"), Mapping) else {}
    global_gate = rehearsal_areas.get("global_gate_boundary") if isinstance(rehearsal_areas.get("global_gate_boundary"), Mapping) else {}
    payload = rehearsal_areas.get("payload_boundary") if isinstance(rehearsal_areas.get("payload_boundary"), Mapping) else {}
    forbidden_called = [row.get("name") for row in forbidden_function_map if row.get("called_in_r135") is True]
    conditions = [
        _condition(
            "dry_authorization_boundary",
            "R134 dry authorization must be ready and non-executable before future adapter implementation.",
            dry_authorization.get("status") != DRY_AUTHORIZATION_READY,
            dry_boundary.get("r134_status"),
        ),
        _condition(
            "adapter_function_boundary",
            "R135 must not call payload preview, signing, network, or execution functions.",
            bool(forbidden_called),
            forbidden_called,
        ),
        _condition(
            "payload_boundary",
            "No executable, direct exchange, order, or signed payload may exist in R135.",
            any(
                [
                    payload.get("executable_payload_created") is True,
                    payload.get("order_payload_created") is True,
                    payload.get("signed_request_created") is True,
                    payload.get("direct_exchange_payload") is not None,
                    payload.get("r134_entry_direct_exchange_payload") is not None,
                    payload.get("r134_protective_direct_exchange_payload") is not None,
                ]
            ),
            payload,
        ),
        _condition(
            "protective_boundary",
            "Protective stop/take-profit policy must be ready before live adapter implementation.",
            protective.get("protective_orders_ready") is not True
            or protective.get("stop_policy_ready") is not True
            or protective.get("take_profit_policy_ready") is not True,
            protective.get("blockers") or protective,
        ),
        _condition(
            "credential_boundary",
            "Credentials must be present only as booleans and no signed request may be created.",
            credentials.get("api_key_present") is not True
            or credentials.get("api_secret_present") is not True
            or credentials.get("signed_request_created") is True,
            {"api_key_present": credentials.get("api_key_present"), "api_secret_present": credentials.get("api_secret_present")},
        ),
        _condition(
            "network_boundary",
            "Network, Binance order/test-order/protective endpoints, and account endpoints are forbidden in R135.",
            any(
                [
                    network.get("network_allowed") is True,
                    network.get("binance_order_endpoint_called") is True,
                    network.get("binance_test_order_endpoint_called") is True,
                    network.get("protective_order_endpoint_called") is True,
                    network.get("account_or_balance_endpoint_called") is True,
                ]
            ),
            network,
        ),
        _condition(
            "kill_switch_boundary",
            "Global kill switch, lane disable, and rollback paths must block live intent.",
            kill.get("global_kill_switch_blocks_live_intent") is not True
            or kill.get("lane_disable_blocks_live_intent") is not True
            or kill.get("rollback_blocks_live_intent") is not True,
            kill,
        ),
        _condition(
            "global_gate_boundary",
            "R106/global gate, final preflight, and live env boundary must be clear before implementation.",
            r132_boundary_review.get("status") != LIVE_ADAPTER_BOUNDARY_REVIEW_READY
            or global_gate.get("r106_status") != "FIRST_LIVE_ACTIVATION_READY"
            or global_gate.get("final_live_preflight_status") != "READY"
            or global_gate.get("live_env_boundary_status") != "READY",
            global_gate,
        ),
    ]
    for key in BLOCKING_SAFETY_KEYS:
        conditions.append(
            _condition(
                "safety",
                f"Safety field {key} must remain false.",
                safety.get(key) is True,
                {key: safety.get(key)},
            )
        )
    conditions.append(
        _condition(
            "safety",
            "Paper/live separation must remain intact.",
            safety.get("paper_live_separation_intact") is False,
            {"paper_live_separation_intact": safety.get("paper_live_separation_intact")},
        )
    )
    return [_sanitize(condition) for condition in conditions]


def build_protective_rehearsal_requirements(
    *,
    protective_readiness: Mapping[str, Any] | None = None,
    protective_boundary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    readiness = dict(protective_readiness or {})
    boundary = dict(protective_boundary or {})
    mode = str(readiness.get("protective_order_mode") or boundary.get("protective_order_mode") or "UNKNOWN")
    stop_ready = readiness.get("protective_orders_ready") is True and boundary.get("stop_policy_ready") is True
    take_profit_ready = readiness.get("protective_orders_ready") is True and boundary.get("take_profit_policy_ready") is True
    return _sanitize(
        {
            "protective_orders_required": True,
            "protective_orders_ready": readiness.get("protective_orders_ready") is True
            or boundary.get("protective_orders_ready") is True,
            "protective_readiness_status": "READY" if readiness.get("protective_orders_ready") is True else mode,
            "stop_policy_ready": stop_ready,
            "take_profit_policy_ready": take_profit_ready,
            "protective_payload_creation_forbidden_in_r135": True,
            "protective_order_endpoint_called": False,
            "blockers": _dedupe([*list(readiness.get("blockers") or []), *list(boundary.get("blockers") or [])]),
        }
    )


def build_future_execution_adapter_requirements(
    *,
    rehearsal_areas: Mapping[str, Any],
    stop_conditions: list[Mapping[str, Any]],
) -> list[str]:
    requirements = [
        "R136 must define protective stop/take-profit dry policy without Binance calls or signed requests.",
        "R137 must produce a first tiny-live execution adapter implementation plan with exact adapter methods, payload schema, signing boundary, network boundary, and rollback plan.",
        "R138 must provide final current-turn authorization before any real tiny-live execution attempt.",
        "R134 dry authorization must be ready, recorded, hash-stable, and still non-executable.",
        "R132 live adapter boundary review must be ready and clear.",
        "R106/global gate, final live preflight, live env boundary, and live arming preflight must be rerun and ready.",
        "Protective stop and take-profit requirements must be resolved before any entry order can be attempted.",
        "Credential presence may be checked only as booleans until an authorized signing phase.",
        "Network calls, test orders, account/balance checks, and real orders require an explicit future execution phase.",
    ]
    for condition in stop_conditions:
        if condition.get("blocked") is True:
            requirements.append(f"Clear stop condition: {condition.get('condition')}")
    return _dedupe(requirements)


def append_live_adapter_execution_rehearsal_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = live_adapter_execution_rehearsal_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "rehearsal_id": str(record.get("rehearsal_id") or f"r135_live_adapter_execution_rehearsal_{uuid4().hex}"),
            "recorded_at_utc": record.get("recorded_at_utc") or datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "lane_key": record.get("lane_key"),
            "rehearsal_areas": record.get("rehearsal_areas") or {},
            "forbidden_function_map": list(record.get("forbidden_function_map") or []),
            "stop_conditions": list(record.get("stop_conditions") or []),
            "future_execution_adapter_requirements": list(record.get("future_execution_adapter_requirements") or []),
            "main_blockers": list(record.get("main_blockers") or []),
            "safety": record.get("safety") or dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or []),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_live_adapter_execution_rehearsal_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = live_adapter_execution_rehearsal_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_live_adapter_execution_rehearsals(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    lane_counts = Counter(str(record.get("lane_key") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "last_rehearsal_id": records[-1].get("rehearsal_id") if records else None,
        "safety": dict(SAFETY),
    }


def format_live_adapter_execution_rehearsal_json(payload: Mapping[str, Any]) -> str:
    compact = {
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "lane_key": payload.get("lane_key"),
        "record_rehearsal_requested": bool(payload.get("record_rehearsal_requested", False)),
        "confirmation_valid": bool(payload.get("confirmation_valid", False)),
        "rehearsal_recorded": bool(payload.get("rehearsal_recorded", False)),
        "rehearsal_id": payload.get("rehearsal_id"),
        "rehearsal_areas": payload.get("rehearsal_areas") or {},
        "forbidden_function_map": list(payload.get("forbidden_function_map") or []),
        "stop_conditions": list(payload.get("stop_conditions") or []),
        "future_execution_adapter_requirements": list(payload.get("future_execution_adapter_requirements") or []),
        "main_blockers": list(payload.get("main_blockers") or []),
        "next_actions": list(payload.get("next_actions") or []),
        "safety": payload.get("safety") or dict(SAFETY),
        "ledger_path": payload.get("ledger_path"),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    return json.dumps(_sanitize(compact), sort_keys=True, separators=(",", ":"))


def live_adapter_execution_rehearsal_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _available_connector_functions() -> list[str]:
    names = [
        name
        for name, member in inspect.getmembers(binance_futures_connector)
        if (inspect.isfunction(member) or inspect.isclass(member))
        and not name.startswith("__")
        and getattr(member, "__module__", None) == binance_futures_connector.__name__
    ]
    return sorted(names)


def _connector_member_available(name: str) -> bool:
    if "." not in name:
        return hasattr(binance_futures_connector, name)
    class_name, method_name = name.split(".", 1)
    owner = getattr(binance_futures_connector, class_name, None)
    return owner is not None and hasattr(owner, method_name)


def _classification_reason(classification: str) -> str:
    if classification == READ_ONLY_STATUS_OK:
        return "Read-only status or path helper; safe to reference and call when no network/signing occurs."
    if classification == PAYLOAD_PREVIEW_FORBIDDEN_IN_R135:
        return "Payload preview can create order-shaped material, which R135 forbids."
    if classification == SIGNING_FORBIDDEN:
        return "Signing or signed request material is forbidden in R135."
    if classification == NETWORK_FORBIDDEN:
        return "Network or endpoint submission is forbidden in R135."
    return "Execution adapter behavior is forbidden in R135."


def _classification_summary(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("classification") or "UNKNOWN") for row in rows)
    return dict(sorted(counts.items()))


def _condition(area: str, condition: str, blocked: bool, details: Any) -> dict[str, Any]:
    return {
        "area": area,
        "condition": condition,
        "blocked": bool(blocked),
        "details": details,
    }


def _main_blockers(stop_conditions: list[Mapping[str, Any]]) -> list[str]:
    return _dedupe([str(condition.get("condition")) for condition in stop_conditions if condition.get("blocked") is True])


def _next_actions(blockers: list[str], lane_key: str) -> list[str]:
    if blockers:
        return [
            "Keep R135 in rehearsal-only mode; do not call connector preview, signing, network, or execution functions.",
            f"Clear R134, R132, R106/global, protective, credential, and kill-switch blockers for lane {lane_key}.",
            "Proceed next to R136 protective order dry policy review before any adapter implementation plan.",
        ]
    return [
        "Record R135 as future-implementation evidence only.",
        "Proceed to R136/R137/R138; no live execution is authorized by R135.",
    ]


def _safe_to_record(safety: Mapping[str, Any]) -> bool:
    return not any(safety.get(key) is True for key in BLOCKING_SAFETY_KEYS) and safety.get("paper_live_separation_intact") is not False


def _nested(payload: Mapping[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


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
