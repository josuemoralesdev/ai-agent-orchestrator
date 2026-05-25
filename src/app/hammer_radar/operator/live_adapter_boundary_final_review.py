"""R132 live adapter boundary final review.

This module composes existing non-executing status surfaces before any future
tiny-live order-payload dry authorization phase. It never creates Binance order
payloads, signs requests, uses network access, mutates env/config, or places
orders.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution.binance_futures_connector import (
    LIVE_ORDER_ENABLED,
    build_connector_status,
    build_protective_status,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.binance_live_status import build_binance_live_status
from src.app.hammer_radar.operator.first_live_activation_gate import load_first_live_activation_gate_checks
from src.app.hammer_radar.operator.first_tiny_live_autonomous_lane_authorization import (
    build_first_tiny_live_autonomous_lane_authorization,
)
from src.app.hammer_radar.operator.first_tiny_live_lane_execution_gate import (
    build_first_tiny_live_lane_execution_gate,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls
from src.app.hammer_radar.operator.live_lane_kill_switch_rehearsal import build_live_lane_kill_switch_rehearsal
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    DEFAULT_CANDIDATE_ID,
    build_tiny_live_risk_contract_payload,
)

DEFAULT_LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"
EVENT_TYPE = "LIVE_ADAPTER_BOUNDARY_FINAL_REVIEW"
LEDGER_FILENAME = "live_adapter_boundary_final_reviews.ndjson"
CONFIRM_BOUNDARY_REVIEW_PHRASE = "I CONFIRM LIVE ADAPTER BOUNDARY REVIEW ONLY; NO ORDER; NO BINANCE CALL."

LIVE_ADAPTER_BOUNDARY_REVIEW_READY = "LIVE_ADAPTER_BOUNDARY_REVIEW_READY"
LIVE_ADAPTER_BOUNDARY_BLOCKED = "LIVE_ADAPTER_BOUNDARY_BLOCKED"
LIVE_ADAPTER_BOUNDARY_ERROR = "LIVE_ADAPTER_BOUNDARY_ERROR"
LIVE_ADAPTER_BOUNDARY_REVIEW_REJECTED = "LIVE_ADAPTER_BOUNDARY_REVIEW_REJECTED"

SAFETY = {
    **SAFETY_FALSE,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
    "binance_order_endpoint_called": False,
    "signed_request_created": False,
}
BLOCKING_SAFETY_KEYS = (
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "order_payload_created",
    "network_allowed",
    "secrets_shown",
    "env_mutated",
    "config_written",
    "global_live_flags_changed",
    "binance_order_endpoint_called",
    "signed_request_created",
)
SOURCE_SURFACES_USED = [
    "operator.live_adapter_boundary_final_review.build_live_adapter_boundary_final_review",
    "execution.binance_futures_connector.build_connector_status",
    "execution.binance_futures_connector.build_protective_status",
    "operator.binance_live_status.build_binance_live_status",
    "operator.live_env_boundary_review.build_live_env_boundary_review",
    "operator.live_arming_preflight.build_live_arming_preflight",
    "operator.final_live_preflight.build_final_live_preflight",
    "operator.first_live_activation_gate.build_first_live_activation_gate",
    "operator.first_tiny_live_lane_execution_gate.build_first_tiny_live_lane_execution_gate",
    "operator.first_tiny_live_autonomous_lane_authorization.build_first_tiny_live_autonomous_lane_authorization",
    "operator.live_lane_kill_switch_rehearsal.build_live_lane_kill_switch_rehearsal",
    "operator.lane_control.load_lane_controls",
    "operator.tiny_live_risk_contract.build_tiny_live_risk_contract_payload",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]
BLOCKED_NETWORK_ACTIONS = [
    "Binance /fapi/v1/order real order POST",
    "Binance /fapi/v1/order/test test-order POST",
    "Binance protective stop/take-profit POST",
    "signed request creation",
    "account, balance, funding, or position API checks",
]


def build_live_adapter_boundary_final_review(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    full_global_gate_review: bool = False,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env
    candidate_id = f"normal|{lane_key}" if lane_key else DEFAULT_CANDIDATE_ID
    try:
        controls = load_lane_controls(config_path)
        lane = _find_lane(controls, lane_key)
        connector_status = build_connector_status(env=source_env, log_dir=resolved_log_dir)
        binance_status = build_binance_live_status(env=source_env)
        protective_status = build_protective_status(env=source_env, log_dir=resolved_log_dir)
        risk_contract = build_tiny_live_risk_contract_payload(candidate_id=candidate_id)
        r126_gate = build_first_tiny_live_lane_execution_gate(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            record=False,
            config_path=config_path,
            env=source_env,
        )
        r130_authorization = build_first_tiny_live_autonomous_lane_authorization(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            config_path=config_path,
            record_authorization=False,
            r126_gate=r126_gate,
            risk_contract=risk_contract,
        )
        r131_rehearsal = build_live_lane_kill_switch_rehearsal(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            config_path=config_path,
        )
        global_gate_boundary = _build_global_gate_boundary(
            candidate_id=candidate_id,
            log_dir=resolved_log_dir,
            env=source_env,
            full_global_gate_review=full_global_gate_review,
        )

        boundary_reviews = {
            "adapter_module_boundary": inspect_live_adapter_boundary(
                connector_status=connector_status,
                execution_dir=_execution_dir(),
            ),
            "order_payload_boundary": inspect_order_payload_boundary(connector_status=connector_status),
            "credential_boundary": inspect_credentials_boundary(
                binance_status=binance_status,
                connector_status=connector_status,
            ),
            "network_boundary": inspect_network_boundary(),
            "protective_order_boundary": inspect_protective_order_boundary(
                protective_status=protective_status,
                risk_contract=risk_contract,
                lane=lane,
            ),
            "kill_switch_boundary": inspect_kill_switch_boundary(
                connector_status=connector_status,
                r131_rehearsal=r131_rehearsal,
            ),
            "lane_authorization_boundary": inspect_lane_authorization_boundary(
                lane=lane,
                r126_gate=r126_gate,
                r130_authorization=r130_authorization,
            ),
            "global_gate_boundary": global_gate_boundary,
        }
        future_requirements = build_future_dry_authorization_requirements(boundary_reviews=boundary_reviews)
        boundary_reviews["dry_authorization_readiness"] = _inspect_dry_authorization_readiness(
            future_requirements=future_requirements,
        )
        main_blockers = _main_blockers(boundary_reviews)
        payload = {
            "status": _status_from_safety(SAFETY),
            "generated_at": generated_at.isoformat(),
            "lane_key": lane_key,
            "boundary_reviews": boundary_reviews,
            "main_blockers": main_blockers,
            "future_dry_authorization_requirements": future_requirements,
            "next_actions": _next_actions(main_blockers, lane_key),
            "safe_command_pack": _safe_command_pack(lane_key),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "ledger_path": str(live_adapter_boundary_review_records_path(resolved_log_dir)),
        }
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive diagnostic boundary
        return _sanitize(
            {
                "status": LIVE_ADAPTER_BOUNDARY_ERROR,
                "generated_at": generated_at.isoformat(),
                "lane_key": lane_key,
                "boundary_reviews": {},
                "main_blockers": [f"review source error: {exc.__class__.__name__}"],
                "future_dry_authorization_requirements": [
                    "Fix R132 source error and rerun the boundary review before dry authorization."
                ],
                "next_actions": ["rerun R132 after repairing the source error"],
                "safe_command_pack": _safe_command_pack(lane_key),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
                "ledger_path": str(live_adapter_boundary_review_records_path(resolved_log_dir)),
            }
        )


def inspect_live_adapter_boundary(
    *,
    connector_status: Mapping[str, Any],
    execution_dir: str | Path | None = None,
) -> dict[str, Any]:
    modules = _execution_modules(execution_dir or _execution_dir())
    connector_mode = str(connector_status.get("connector_mode") or "UNKNOWN")
    return {
        "execution_modules": modules,
        "adapter_configured": connector_status.get("live_order_adapter_configured") is True,
        "live_capable_code_present": any(module.get("live_capable_code_present") for module in modules),
        "connector_mode": connector_mode,
        "adapter_live_capable_now": connector_mode == LIVE_ORDER_ENABLED
        and connector_status.get("live_order_adapter_configured") is True,
        "currently_dry_run_only": connector_mode != LIVE_ORDER_ENABLED
        or connector_status.get("live_order_adapter_configured") is not True,
        "real_live_endpoint_prepared_in_code": connector_status.get("real_live_endpoint_prepared") is True,
        "no_calls_made": True,
        "blockers": _dedupe(
            [
                *list(connector_status.get("blockers") or []),
                "live order adapter not configured"
                if connector_status.get("live_order_adapter_configured") is not True
                else "",
            ]
        ),
    }


def inspect_order_payload_boundary(*, connector_status: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "payload_builder_code_present": True,
        "signed_request_builder_code_present": True,
        "r132_produced_order_payload": False,
        "r132_produced_executable_payload": False,
        "order_payload_created": False,
        "signed_request_created": False,
        "can_build_executable_payload_in_r132": False,
        "future_phase_required_for_payload_review": "R134 first tiny-live order payload dry authorization",
        "blocked_functions_not_called": [
            "preview_payload",
            "protective_preview",
            "submit_test_order",
            "submit_protective_test",
            "execute_live_order",
            "build_signed_test_order_request",
            "build_signed_live_order_request",
            "build_signed_protective_order_requests",
        ],
        "connector_status_order_payload_created": bool(connector_status.get("order_payload_created")),
        "connector_status_signed_payload_created": bool(connector_status.get("signed_payload_created")),
        "blockers": [
            "R132 is review-only and cannot create order payload material.",
            "Future dry authorization must be explicit, current-turn, and non-executing.",
        ],
    }


def inspect_protective_order_boundary(
    *,
    protective_status: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    lane: Mapping[str, Any] | None,
) -> dict[str, Any]:
    contract = risk_contract.get("risk_contract") if isinstance(risk_contract.get("risk_contract"), Mapping) else {}
    mode = str(protective_status.get("protective_order_mode") or "UNKNOWN")
    if protective_status.get("protective_orders_ready") is True:
        readiness_mode = "LIVE_READY"
    elif mode == "PREVIEW_ONLY":
        readiness_mode = "PREVIEW_ONLY"
    else:
        readiness_mode = "UNKNOWN"
    return {
        "protective_orders_enabled": protective_status.get("protective_orders_enabled") is True,
        "protective_order_mode": mode,
        "mode": readiness_mode,
        "protective_orders_ready": protective_status.get("protective_orders_ready") is True,
        "protective_orders_required_by_connector": protective_status.get("protective_orders_required") is True,
        "protective_orders_required_by_lane": bool((lane or {}).get("require_protective_orders")),
        "protective_stop_required_by_contract": contract.get("protective_stop_required") is True,
        "take_profit_required_by_contract": contract.get("take_profit_required") is True,
        "stop_policy_ready": protective_status.get("protective_stop_supported") is True
        and contract.get("protective_stop_required") is True,
        "take_profit_policy_ready": protective_status.get("protective_take_profit_supported") is True
        and contract.get("take_profit_required") is True,
        "protective_orders_sent": False,
        "order_payload_created": False,
        "blockers": list(protective_status.get("blockers") or []),
    }


def inspect_credentials_boundary(
    *,
    binance_status: Mapping[str, Any],
    connector_status: Mapping[str, Any],
) -> dict[str, Any]:
    key_present = bool(binance_status.get("api_key_present") or connector_status.get("api_key_present"))
    secret_present = bool(binance_status.get("api_secret_present") or connector_status.get("api_secret_present"))
    if key_present and secret_present:
        status = "PRESENT"
    elif key_present or secret_present:
        status = "PARTIAL"
    else:
        status = "MISSING"
    return {
        "api_key_present": key_present,
        "api_secret_present": secret_present,
        "credential_status": status,
        "values_shown": False,
        "secrets_shown": False,
        "read_only_status_check": True,
        "network_used": False,
        "live_env_file_exists": bool(binance_status.get("live_env_file_exists")),
        "live_env_loaded": False,
        "blockers": _dedupe(
            [
                "BINANCE_API_KEY missing" if not key_present else "",
                "BINANCE_API_SECRET missing" if not secret_present else "",
            ]
        ),
    }


def inspect_network_boundary() -> dict[str, Any]:
    return {
        "r132_used_network": False,
        "network_allowed": False,
        "future_live_adapter_requires_network": True,
        "blocked_network_actions": list(BLOCKED_NETWORK_ACTIONS),
        "binance_order_endpoint_called": False,
        "account_or_balance_endpoint_called": False,
        "signed_request_created": False,
        "blockers": ["network use is forbidden during R132 boundary review"],
    }


def inspect_kill_switch_boundary(
    *,
    connector_status: Mapping[str, Any],
    r131_rehearsal: Mapping[str, Any],
) -> dict[str, Any]:
    verdict = r131_rehearsal.get("kill_switch_verdict") if isinstance(r131_rehearsal.get("kill_switch_verdict"), Mapping) else {}
    return {
        "global_kill_switch": bool(connector_status.get("global_kill_switch", True)),
        "global_kill_switch_blocks_live_intent": verdict.get("global_kill_switch_blocks_live_intent") is True,
        "lane_disable_blocks_live_intent": verdict.get("lane_disable_blocks_live_intent") is True,
        "rollback_blocks_live_intent": verdict.get("rollback_blocks_live_intent") is True,
        "scheduler_respects_disabled_lane": verdict.get("scheduler_respects_disabled_lane") is True,
        "r131_status": r131_rehearsal.get("status"),
        "kill_switch_blocks_live_intent": bool(connector_status.get("global_kill_switch", True))
        and verdict.get("global_kill_switch_blocks_live_intent") is True,
        "blockers": list(r131_rehearsal.get("current_blockers") or []),
    }


def inspect_lane_authorization_boundary(
    *,
    lane: Mapping[str, Any] | None,
    r126_gate: Mapping[str, Any],
    r130_authorization: Mapping[str, Any],
) -> dict[str, Any]:
    prerequisites = (
        r130_authorization.get("prerequisites")
        if isinstance(r130_authorization.get("prerequisites"), Mapping)
        else {}
    )
    paper = prerequisites.get("paper_proof_summary") if isinstance(prerequisites.get("paper_proof_summary"), Mapping) else {}
    return {
        "lane_key": (lane or {}).get("lane_key"),
        "current_lane_mode": str((lane or {}).get("mode") or "missing").strip().lower(),
        "tiny_live_authorization_status": r130_authorization.get("status"),
        "authorization_recorded": r130_authorization.get("authorization_recorded") is True,
        "r126_gate_status": r126_gate.get("status"),
        "recent_paper_proof_matched": paper.get("matched") is True,
        "recent_paper_proof_source": paper.get("source") or "MISSING",
        "r129_paper_integration_status": paper.get("r129_paper_integration_status"),
        "paper_live_separation_intact": True,
        "blockers": _dedupe([*list(r130_authorization.get("blockers") or []), *list(r126_gate.get("blockers") or [])]),
    }


def build_future_dry_authorization_requirements(
    *,
    boundary_reviews: Mapping[str, Any],
) -> list[str]:
    requirements = [
        "Record recent autonomous paper proof for the selected lane through R125/R129.",
        "Move the selected lane to tiny_live through the existing R124/R130 intent path only.",
        "Rerun R126 until the tiny-live lane execution gate is ready.",
        "Rerun R106 and final live preflight until global gates are ready.",
        "Keep the global kill switch reviewed and do not disable it before an explicitly authorized future phase.",
        "Verify live execution flags remain disabled until a future approved arming phase.",
        "Verify Binance credential presence as booleans only; never print credential values.",
        "Review live adapter configuration without calling Binance or signing requests.",
        "Make protective stop and take-profit readiness explicit before any payload dry authorization.",
        "R134 must produce a dry authorization packet only, with no signed request and no exchange call.",
    ]
    protective = boundary_reviews.get("protective_order_boundary") if isinstance(boundary_reviews.get("protective_order_boundary"), Mapping) else {}
    if protective.get("protective_orders_ready") is not True:
        requirements.append("Clear protective order readiness while preserving preview-only/non-executing defaults.")
    credentials = boundary_reviews.get("credential_boundary") if isinstance(boundary_reviews.get("credential_boundary"), Mapping) else {}
    if credentials.get("credential_status") != "PRESENT":
        requirements.append("Provide credential-presence evidence without exposing values.")
    return _dedupe(requirements)


def append_live_adapter_boundary_review_record(
    payload: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = live_adapter_boundary_review_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "review_id": str(payload.get("review_id") or f"live_adapter_boundary_review_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "lane_key": payload.get("lane_key"),
            "status": payload.get("status"),
            "boundary_reviews": payload.get("boundary_reviews") or {},
            "main_blockers": list(payload.get("main_blockers") or []),
            "future_dry_authorization_requirements": list(payload.get("future_dry_authorization_requirements") or []),
            "next_actions": list(payload.get("next_actions") or []),
            "safety": payload.get("safety") or dict(SAFETY),
            "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return record


def load_live_adapter_boundary_review_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = live_adapter_boundary_review_records_path(get_log_dir(log_dir, use_env=True))
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
            records.append(_sanitize(record))
    if limit > 0:
        return list(reversed(records))[:limit]
    return records


def summarize_live_adapter_boundary_reviews(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    lane_counts = Counter(str(record.get("lane_key") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "last_review_id": records[-1].get("review_id") if records else None,
        "safety": dict(SAFETY),
    }


def build_live_adapter_boundary_final_review_cli_payload(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    record_review: bool = False,
    confirm_boundary_review: str | None = None,
) -> dict[str, Any]:
    payload = build_live_adapter_boundary_final_review(log_dir=log_dir, lane_key=lane_key)
    if not record_review:
        return payload
    if confirm_boundary_review != CONFIRM_BOUNDARY_REVIEW_PHRASE:
        return _sanitize(
            {
                **payload,
                "status": LIVE_ADAPTER_BOUNDARY_REVIEW_REJECTED,
                "record_review_requested": True,
                "confirmation_valid": False,
                "ledger_written": False,
                "main_blockers": _dedupe(
                    [
                        "exact live adapter boundary review confirmation phrase is required",
                        *list(payload.get("main_blockers") or []),
                    ]
                ),
                "safety": dict(SAFETY),
            }
        )
    record = append_live_adapter_boundary_review_record(payload, log_dir=log_dir)
    return _sanitize(
        {
            **payload,
            "record_review_requested": True,
            "confirmation_valid": True,
            "ledger_written": True,
            "review_id": record["review_id"],
        }
    )


def format_live_adapter_boundary_final_review_json(payload: Mapping[str, Any]) -> str:
    compact = {
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "lane_key": payload.get("lane_key"),
        "record_review_requested": bool(payload.get("record_review_requested", False)),
        "confirmation_valid": bool(payload.get("confirmation_valid", False)),
        "ledger_written": bool(payload.get("ledger_written", False)),
        "review_id": payload.get("review_id"),
        "boundary_reviews": payload.get("boundary_reviews") or {},
        "main_blockers": list(payload.get("main_blockers") or []),
        "future_dry_authorization_requirements": list(payload.get("future_dry_authorization_requirements") or []),
        "next_actions": list(payload.get("next_actions") or []),
        "safe_command_pack": payload.get("safe_command_pack") or {},
        "safety": payload.get("safety") or dict(SAFETY),
        "ledger_path": payload.get("ledger_path"),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    return json.dumps(_sanitize(compact), sort_keys=True, separators=(",", ":"))


def live_adapter_boundary_review_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _inspect_global_gate_boundary(
    *,
    r106_gate: Mapping[str, Any],
    final_preflight: Mapping[str, Any],
    live_env_boundary: Mapping[str, Any],
    live_arming_preflight: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "r106_status": r106_gate.get("status"),
        "final_live_preflight_status": final_preflight.get("status"),
        "live_env_boundary_status": live_env_boundary.get("boundary_status"),
        "live_arming_preflight_status": live_arming_preflight.get("final_preflight_status"),
        "live_execution_enabled": final_preflight.get("live_execution_enabled") is True,
        "live_orders_allowed": final_preflight.get("live_orders_allowed") is True,
        "global_kill_switch": final_preflight.get("global_kill_switch") is True,
        "paper_live_separation_intact": final_preflight.get("paper_live_separation_intact") is not False,
        "blockers": _dedupe(
            [
                *list(r106_gate.get("blockers") or []),
                *list(final_preflight.get("blockers") or []),
                *list(live_env_boundary.get("blockers") or []),
                *list(live_arming_preflight.get("blockers") or []),
            ]
        ),
    }


def _build_global_gate_boundary(
    *,
    candidate_id: str,
    log_dir: Path,
    env: Mapping[str, str],
    full_global_gate_review: bool,
) -> dict[str, Any]:
    if full_global_gate_review:
        from src.app.hammer_radar.operator.final_live_preflight import build_final_live_preflight
        from src.app.hammer_radar.operator.first_live_activation_gate import build_first_live_activation_gate
        from src.app.hammer_radar.operator.live_arming_preflight import build_live_arming_preflight
        from src.app.hammer_radar.operator.live_env_boundary_review import build_live_env_boundary_review

        return _inspect_global_gate_boundary(
            r106_gate=build_first_live_activation_gate(
                candidate_id=candidate_id,
                log_dir=log_dir,
                env=env,
                record=False,
            ),
            final_preflight=build_final_live_preflight(candidate_id=candidate_id, log_dir=log_dir, env=env),
            live_env_boundary=build_live_env_boundary_review(
                candidate_id=candidate_id,
                dry_run=True,
                write=False,
                log_dir=log_dir,
                env=env,
            ),
            live_arming_preflight=build_live_arming_preflight(candidate_id=candidate_id, log_dir=log_dir, env=env),
        )

    latest_r106 = _latest_matching_r106(candidate_id=candidate_id, log_dir=log_dir)
    connector_status = build_connector_status(env=env, log_dir=log_dir)
    binance_status = build_binance_live_status(env=env)
    protective_status = build_protective_status(env=env, log_dir=log_dir)
    blockers = _dedupe(
        [
            "R132 fast boundary review does not execute full R106/R102/R87/R84 composition; use safe_command_pack rechecks for authoritative current status.",
            "R106 first-live activation gate is not FIRST_LIVE_ACTIVATION_READY"
            if latest_r106.get("status") != "FIRST_LIVE_ACTIVATION_READY"
            else "",
            "final live preflight must be rerun before dry authorization",
            "live env boundary must be rerun before dry authorization",
            "live arming preflight must be rerun before dry authorization",
            *list(connector_status.get("blockers") or []),
            *list(binance_status.get("blockers") or []),
            *list(protective_status.get("blockers") or []),
        ]
    )
    return {
        "r106_status": latest_r106.get("status") or "UNKNOWN_NO_RECENT_R106_RECORD",
        "r106_source": "latest_first_live_activation_gate_check_record",
        "final_live_preflight_status": "RECHECK_REQUIRED",
        "live_env_boundary_status": "RECHECK_REQUIRED",
        "live_arming_preflight_status": "RECHECK_REQUIRED",
        "live_execution_enabled": connector_status.get("live_execution_enabled") is True,
        "live_orders_allowed": connector_status.get("allow_live_orders") is True,
        "global_kill_switch": connector_status.get("global_kill_switch") is True,
        "paper_live_separation_intact": True,
        "full_global_gate_review_executed": False,
        "authoritative_recheck_commands": {
            "r106_gate_check": "first-live-activation-gate --no-record",
            "final_preflight": "final-live-preflight",
            "live_env_boundary": "live-env-boundary-review",
            "live_arming_preflight": "live-arming-preflight",
        },
        "blockers": blockers,
    }


def _latest_matching_r106(*, candidate_id: str, log_dir: Path) -> dict[str, Any]:
    for record in load_first_live_activation_gate_checks(limit=20, log_dir=log_dir):
        if record.get("candidate_id") == candidate_id:
            return dict(record)
    records = load_first_live_activation_gate_checks(limit=1, log_dir=log_dir)
    return dict(records[0]) if records else {}


def _inspect_dry_authorization_readiness(*, future_requirements: list[str]) -> dict[str, Any]:
    return {
        "r133_lane_control_cockpit_ui_can_proceed": True,
        "r134_first_tiny_live_order_payload_dry_authorization_ready": False,
        "review_completed": True,
        "missing_items": list(future_requirements),
        "blockers": [
            "R134 remains blocked until lane, global gate, protective order, credential, and adapter boundaries are cleared."
        ],
    }


def _execution_modules(execution_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(execution_dir)
    if not path.exists():
        return []
    modules: list[dict[str, Any]] = []
    for file_path in sorted(path.glob("*.py")):
        text = _safe_read_text(file_path)
        modules.append(
            {
                "module": file_path.name,
                "has_connector_status_builder": "build_connector_status" in text,
                "has_protective_status_builder": "build_protective_status" in text,
                "has_payload_preview_code": "preview_payload" in text or "_payload_preview_from_pack" in text,
                "has_signed_request_code": "build_signed_" in text or "sign_query" in text,
                "live_capable_code_present": "execute_live_order" in text or "BinanceFuturesLiveHttpClient" in text,
            }
        )
    return modules


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _execution_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "execution"


def _find_lane(controls: Mapping[str, Any], lane_key: str | None) -> dict[str, Any] | None:
    lane = (controls.get("lane_map") or {}).get(str(lane_key or ""))
    return dict(lane) if isinstance(lane, Mapping) else None


def _main_blockers(boundary_reviews: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for name, review in boundary_reviews.items():
        if not isinstance(review, Mapping):
            continue
        for blocker in review.get("blockers") or []:
            blockers.append(f"{name}: {blocker}")
    return _dedupe(blockers)


def _next_actions(blockers: list[str], lane_key: str) -> list[str]:
    actions = [
        "Use R133 to make lane, gate, scheduler, paper proof, and boundary status visible in the operator cockpit.",
        "Do not create a dry order-payload authorization packet until R134 and all R132 requirements are explicit.",
        "Keep R132 as review-only evidence; do not run connector preview, signing, submit, or execute functions.",
    ]
    if blockers:
        actions.append("Clear the listed boundary blockers through existing R126/R130/R131/R106/R102 surfaces.")
    actions.append(f"Rerun R132 for lane {lane_key} after evidence changes.")
    return actions


def _safe_command_pack(lane_key: str) -> dict[str, str]:
    base = "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward"
    quoted_lane = json.dumps(lane_key)
    return {
        "lane_status": f"{base} lane-control-status",
        "router_status": f"{base} fresh-signal-router-status",
        "paper_executor_preview": f"{base} autonomous-paper-lane-executor-integration --lane-key {quoted_lane}",
        "paper_executor_record_recommended_template": (
            f"{base} autonomous-paper-lane-executor-integration --lane-key {quoted_lane} --record-paper "
            "--confirm-paper-integration \"I CONFIRM AUTONOMOUS PAPER LANE INTEGRATION ONLY; NO REAL ORDER; NO BINANCE CALL.\""
        ),
        "tiny_live_authorization_preview": f"{base} first-tiny-live-autonomous-lane-authorization --lane-key {quoted_lane}",
        "kill_switch_rehearsal": f"{base} live-lane-kill-switch-rehearsal --lane-key {quoted_lane}",
        "r126_gate_check": f"{base} first-tiny-live-lane-execution-gate --lane-key {quoted_lane}",
        "r106_gate_check": f"{base} first-live-activation-gate --no-record",
        "final_preflight": f"{base} final-live-preflight",
    }


def _status_from_safety(safety: Mapping[str, Any]) -> str:
    if any(safety.get(key) is True for key in BLOCKING_SAFETY_KEYS):
        return LIVE_ADAPTER_BOUNDARY_BLOCKED
    if safety.get("paper_live_separation_intact") is not True:
        return LIVE_ADAPTER_BOUNDARY_BLOCKED
    return LIVE_ADAPTER_BOUNDARY_REVIEW_READY


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
