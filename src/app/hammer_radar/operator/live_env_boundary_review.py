"""R87 live env toggle design and execution boundary review.

This module is read-only by default. It reports non-secret live-env toggle
state and the execution boundary that prevents accidental live orders. It never
changes env files, calls Binance, checks balances, signs payloads, or creates
order payloads.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.live_arming_preflight import build_live_arming_preflight
from src.app.hammer_radar.operator.live_env_arming_checklist import build_live_env_arming_checklist_status
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID
from src.app.hammer_radar.operator.tiny_live_ticket_builder import build_tiny_live_ticket

PHASE = "R87"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "LIVE_ENV_TOGGLE_DESIGN_EXECUTION_BOUNDARY_REVIEW_ONLY_NO_ORDER"
REPORT_FILENAME = "live_env_boundary_review.json"

LIVE_ENV_BOUNDARY_REVIEW_ONLY = "LIVE_ENV_BOUNDARY_REVIEW_ONLY"
LIVE_ENV_LOCKED_SAFE = "LIVE_ENV_LOCKED_SAFE"
LIVE_ENV_ARMING_NOT_ALLOWED_YET = "LIVE_ENV_ARMING_NOT_ALLOWED_YET"
LIVE_ENV_ARMING_DESIGN_READY_FOR_REVIEW = "LIVE_ENV_ARMING_DESIGN_READY_FOR_REVIEW"
LIVE_ENV_BLOCKED_BY_KILL_SWITCH = "LIVE_ENV_BLOCKED_BY_KILL_SWITCH"
LIVE_ENV_BLOCKED_BY_MISSING_OPERATOR_APPROVAL = "LIVE_ENV_BLOCKED_BY_MISSING_OPERATOR_APPROVAL"
LIVE_ENV_BLOCKED_BY_MISSING_CHECKLIST = "LIVE_ENV_BLOCKED_BY_MISSING_CHECKLIST"
LIVE_ENV_BLOCKED_BY_NO_REAL_BALANCE_CHECK = "LIVE_ENV_BLOCKED_BY_NO_REAL_BALANCE_CHECK"
LIVE_ENV_BLOCKED_BY_EXECUTION_BOUNDARY = "LIVE_ENV_BLOCKED_BY_EXECUTION_BOUNDARY"

TOGGLE_LOCKED_FALSE = "TOGGLE_LOCKED_FALSE"
TOGGLE_KILL_SWITCH_ON = "TOGGLE_KILL_SWITCH_ON"
TOGGLE_REQUIRES_FUTURE_MANUAL_CHANGE = "TOGGLE_REQUIRES_FUTURE_MANUAL_CHANGE"
TOGGLE_NOT_FOUND = "TOGGLE_NOT_FOUND"
TOGGLE_READ_ONLY_REPORTED = "TOGGLE_READ_ONLY_REPORTED"
TOGGLE_UNSAFE_IF_ENABLED_NOW = "TOGGLE_UNSAFE_IF_ENABLED_NOW"

EXECUTION_BOUNDARY_NO_ORDER_PAYLOAD = "EXECUTION_BOUNDARY_NO_ORDER_PAYLOAD"
EXECUTION_BOUNDARY_NO_NETWORK = "EXECUTION_BOUNDARY_NO_NETWORK"
EXECUTION_BOUNDARY_NO_SIGNING = "EXECUTION_BOUNDARY_NO_SIGNING"
EXECUTION_BOUNDARY_NO_BINANCE = "EXECUTION_BOUNDARY_NO_BINANCE"
EXECUTION_BOUNDARY_REVIEW_ONLY = "EXECUTION_BOUNDARY_REVIEW_ONLY"
EXECUTION_BOUNDARY_INTACT = "EXECUTION_BOUNDARY_INTACT"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

TOGGLE_SPECS = (
    ("HAMMER_BINANCE_LIVE_ENABLED", False, "R87+ future explicit live env arming phase"),
    ("HAMMER_LIVE_EXECUTION_ENABLED", False, "R87+ future explicit live env arming phase"),
    ("HAMMER_ALLOW_LIVE_ORDERS", False, "R87+ future explicit live env arming phase"),
    ("HAMMER_GLOBAL_KILL_SWITCH", True, "R87+ future explicit kill switch review phase"),
)

NO_ORDER_NOTE = "R87 is boundary review only. No env changes, no orders, no payloads, no network, no Binance."


def build_live_env_boundary_review(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env
    generated_at = datetime.now(UTC).isoformat()
    preflight = build_live_arming_preflight(candidate_id=candidate_id, log_dir=resolved_log_dir, env=source_env)
    ticket = build_tiny_live_ticket(candidate_id=candidate_id, dry_run=True, write=False, log_dir=resolved_log_dir)
    checklist_status = build_live_env_arming_checklist_status(candidate_id=candidate_id, log_dir=resolved_log_dir)
    toggle_review = build_live_toggle_review(env=source_env)
    execution_boundary = build_execution_boundary_review()
    blockers = _boundary_blockers(preflight=preflight, ticket=ticket, checklist_status=checklist_status, toggle_review=toggle_review)
    boundary_status = LIVE_ENV_LOCKED_SAFE if not blockers else LIVE_ENV_ARMING_NOT_ALLOWED_YET
    payload = _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "candidate_id": candidate_id,
            "risk_contract_hash": ticket.get("risk_contract_hash"),
            "source_preflight_status": preflight.get("final_preflight_status"),
            "source_ticket_status": ticket.get("ticket_status"),
            "source_checklist_status": (checklist_status.get("summary") or {}).get("latest_checklist_status"),
            "live_toggle_review": toggle_review,
            "execution_boundary_review": execution_boundary,
            "future_arming_requirements": future_arming_requirements(),
            "forbidden_actions": forbidden_actions(),
            "boundary_status": boundary_status,
            "blockers": blockers,
            "dry_run": bool(dry_run),
            "write": bool(write),
            "report_written": False,
            "report_path": str(live_env_boundary_report_path(resolved_log_dir)),
            "notes": [
                NO_ORDER_NOTE,
                "Checklist confirmations are review evidence only, not execution permission.",
                "Local funding config and manual funding confirmation are not real account balance checks.",
            ],
            **_safety_fields(),
        }
    )
    if write and not dry_run:
        path = live_env_boundary_report_path(resolved_log_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        payload["report_written"] = True
    return _sanitize(payload)


def build_live_toggle_review(*, env: Mapping[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, expected, future_phase in TOGGLE_SPECS:
        raw = env.get(name)
        current = _bool_or_none(raw)
        if current is None:
            status = TOGGLE_NOT_FOUND
            note = "Toggle is absent from the current process env; safe default remains locked in code."
        elif name == "HAMMER_GLOBAL_KILL_SWITCH" and current is True:
            status = TOGGLE_KILL_SWITCH_ON
            note = "Kill switch is on, which is the required safe review state."
        elif current == expected and expected is False:
            status = TOGGLE_LOCKED_FALSE
            note = "Toggle is explicitly false and locked for this phase."
        elif current == expected:
            status = TOGGLE_READ_ONLY_REPORTED
            note = "Toggle matches expected safe value."
        else:
            status = TOGGLE_UNSAFE_IF_ENABLED_NOW
            note = "This value would be unsafe during R87 review."
        rows.append(
            {
                "toggle_name": name,
                "current_value": current,
                "configured": current is not None,
                "expected_safe_value": expected,
                "toggle_status": status,
                "future_phase_allowed_to_change": future_phase,
                "operator_note": note,
            }
        )
    return rows


def build_execution_boundary_review() -> dict[str, Any]:
    boundaries = [
        EXECUTION_BOUNDARY_NO_ORDER_PAYLOAD,
        EXECUTION_BOUNDARY_NO_NETWORK,
        EXECUTION_BOUNDARY_NO_SIGNING,
        EXECUTION_BOUNDARY_NO_BINANCE,
        EXECUTION_BOUNDARY_REVIEW_ONLY,
    ]
    return {
        "boundary_status": EXECUTION_BOUNDARY_INTACT,
        "boundaries": boundaries,
        "order_payload_created": False,
        "network_allowed": False,
        "signing_allowed": False,
        "binance_allowed": False,
        "execution_attempted": False,
        "operator_note": "R87 cannot create executable order material or contact an exchange.",
    }


def future_arming_requirements() -> list[str]:
    return [
        "R83 top candidate still supports normal|BTCUSDT|13m|long|ladder_close_50_618.",
        "R84 risk contract remains RISK_CONTRACT_VALID_FOR_PREFLIGHT.",
        "R85 non-executable ticket exists with exact approval recorded for review.",
        "R86 checklist exists with exact manual phrases recorded for review.",
        "Manual funding is confirmed by operator but is not treated as account balance verification.",
        "Global kill switch remains intentionally reviewed.",
        "A future phase explicitly changes env outside R87 with operator awareness.",
        "Any real exchange account balance check is separate and explicitly approved.",
        "Protective stop and take-profit are present before any executable payload exists.",
        "Future execution phase still requires final explicit approval.",
    ]


def forbidden_actions() -> list[str]:
    return [
        "no Binance calls",
        "no account balance calls",
        "no env mutation",
        "no service restart",
        "no order payload creation",
        "no signing",
        "no execution attempt",
        "no automatic approval",
        "no kill-switch disablement",
    ]


def live_env_boundary_report_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / REPORT_FILENAME


def format_live_env_boundary_review_text(payload: Mapping[str, Any]) -> str:
    toggles = payload.get("live_toggle_review") if isinstance(payload.get("live_toggle_review"), list) else []
    boundary = payload.get("execution_boundary_review") if isinstance(payload.get("execution_boundary_review"), dict) else {}
    lines = [
        f"R87 Live Env Boundary Review: {payload.get('status')}",
        str(payload.get("execution_mode")),
        f"candidate_id: {payload.get('candidate_id')}",
        f"risk_contract_hash: {payload.get('risk_contract_hash')}",
        f"boundary_status: {payload.get('boundary_status')}",
        f"source_preflight_status: {payload.get('source_preflight_status')}",
        f"source_ticket_status: {payload.get('source_ticket_status')}",
        f"source_checklist_status: {payload.get('source_checklist_status')}",
        "LIVE TOGGLES",
    ]
    for row in toggles:
        lines.append(
            f"  {row.get('toggle_name')}: current={row.get('current_value')} expected={row.get('expected_safe_value')} status={row.get('toggle_status')}"
        )
    lines.extend(
        [
            f"execution_boundary_status: {boundary.get('boundary_status')}",
            f"blockers: {', '.join(str(item) for item in payload.get('blockers') or []) if payload.get('blockers') else 'none'}",
            f"dry_run: {payload.get('dry_run')} write: {payload.get('write')} report_written: {payload.get('report_written')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            NO_ORDER_NOTE,
        ]
    )
    return "\n".join(lines)


def _boundary_blockers(
    *,
    preflight: Mapping[str, Any],
    ticket: Mapping[str, Any],
    checklist_status: Mapping[str, Any],
    toggle_review: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = [LIVE_ENV_BLOCKED_BY_EXECUTION_BOUNDARY, LIVE_ENV_BLOCKED_BY_NO_REAL_BALANCE_CHECK]
    if preflight.get("final_preflight_status") == "BLOCKED_BY_MISSING_OPERATOR_APPROVAL":
        blockers.append(LIVE_ENV_BLOCKED_BY_MISSING_OPERATOR_APPROVAL)
    if ticket.get("operator_approval_status") != "OPERATOR_APPROVAL_RECORDED_FOR_REVIEW":
        blockers.append("ticket_operator_approval_not_recorded")
    summary = checklist_status.get("summary") if isinstance(checklist_status.get("summary"), dict) else {}
    if summary.get("latest_checklist_status") != "CHECKLIST_RECORDED_FOR_REVIEW":
        blockers.append(LIVE_ENV_BLOCKED_BY_MISSING_CHECKLIST)
    for row in toggle_review:
        if row.get("toggle_status") == TOGGLE_UNSAFE_IF_ENABLED_NOW:
            blockers.append(f"unsafe_toggle:{row.get('toggle_name')}")
    return list(dict.fromkeys(blockers))


def _bool_or_none(value: object) -> bool | None:
    if value is None or value == "":
        return None
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in (
            "live_execution_enabled",
            "allow_live_orders",
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "network_allowed",
            "secrets_shown",
        ):
            if key in sanitized:
                sanitized[key] = False
        if "global_kill_switch" in sanitized:
            sanitized["global_kill_switch"] = True
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
