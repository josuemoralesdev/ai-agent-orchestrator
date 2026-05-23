"""R120 first-live targeted clearing pack.

This module selects the next safe R119 clearing lane or reports that R118 is
ready for a later authorization request phase. It never places orders, enables
live execution, calls Binance order endpoints, edits environment flags, or
creates execution authority.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_activation_gate_final_review import (
    READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION,
)
from src.app.hammer_radar.operator.first_live_blocker_clearing_workbench import (
    WORKBENCH_BLOCKED_UNSAFE,
    build_first_live_blocker_clearing_workbench,
)
from src.app.hammer_radar.operator.first_live_evidence_assisted_run import CONFIRMATION_PHRASE
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

TARGETED_CLEARING_READY = "TARGETED_CLEARING_READY"
TARGETED_CLEARING_BLOCKED_UNSAFE = "TARGETED_CLEARING_BLOCKED_UNSAFE"
AUTHORIZATION_REQUEST_NOT_READY = "AUTHORIZATION_REQUEST_NOT_READY"
READY_TO_PREPARE_AUTHORIZATION_REQUEST = "READY_TO_PREPARE_AUTHORIZATION_REQUEST"
EVENT_TYPE = "FIRST_LIVE_TARGETED_CLEARING_PACK"
LEDGER_FILENAME = "first_live_targeted_clearing_packs.ndjson"
SOURCE_SURFACE = "operator.first_live_targeted_clearing_pack.build_first_live_targeted_clearing_pack"

ALLOWED_LANE_IDS = (
    "evidence_records_lane",
    "approval_records_lane",
    "account_funding_read_only_lane",
    "protective_orders_lane",
    "live_adapter_boundary_lane",
    "tiny_size_max_loss_lane",
    "environment_flags_review_lane",
    "sacred_button_safety_lane",
    "emergency_and_position_review_lane",
    "candidate_freshness_lane",
    "final_gate_recheck_lane",
)

DEFAULT_LANE_PRIORITY = (
    "evidence_records_lane",
    "approval_records_lane",
    "sacred_button_safety_lane",
    "tiny_size_max_loss_lane",
    "account_funding_read_only_lane",
    "protective_orders_lane",
    "live_adapter_boundary_lane",
    "environment_flags_review_lane",
    "candidate_freshness_lane",
    "final_gate_recheck_lane",
)

LANE_GROUPS = {
    "evidence_records_lane": None,
    "approval_records_lane": "approval_records",
    "account_funding_read_only_lane": "account_and_funding",
    "protective_orders_lane": "protective_orders",
    "live_adapter_boundary_lane": "adapter_boundary",
    "tiny_size_max_loss_lane": "risk_limits",
    "environment_flags_review_lane": "environment_review",
    "sacred_button_safety_lane": "sacred_button_review",
    "emergency_and_position_review_lane": "emergency_and_position_review",
}

SAFETY_FALSE_FIELDS = (
    "live_ready",
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "real_order_possible",
    "secrets_shown",
)


def _cmd(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


def build_first_live_targeted_clearing_pack(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    lane: str | None = None,
    all_evidence_lanes: bool = False,
    authorization_check: bool = False,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    checked_at = datetime.now(UTC).isoformat()
    workbench = build_first_live_blocker_clearing_workbench(
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
        record=False,
    )
    lanes = _lanes_by_id(workbench)
    selected_lane, lane_errors = _select_lane(requested_lane=lane, lanes=lanes, workbench=workbench)
    active_tuple = _active_tuple(workbench)
    mode_decision = _mode_decision(workbench=workbench, authorization_check=authorization_check)
    authorization_status = _authorization_status(workbench)
    unsafe_reasons = _unsafe_reasons(workbench)
    unsafe_reasons.extend(lane_errors)
    status = _status(
        workbench=workbench,
        authorization_check=authorization_check,
        selected_lane=selected_lane,
        unsafe_reasons=unsafe_reasons,
    )

    payload = {
        "event_type": EVENT_TYPE,
        "targeted_clearing_id": uuid4().hex,
        "recorded_at_utc": checked_at,
        "checked_at_utc": checked_at,
        "status": status,
        "validation_errors": lane_errors,
        "unsafe_reasons": sorted(set(unsafe_reasons)),
        "live_ready": False,
        "execution_enabled_by_targeted_clearing": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "paper_live_separation_intact": "paper_live_separation_intact false" not in unsafe_reasons,
        "active_tuple": active_tuple,
        "mode_decision": mode_decision,
        "selected_lane": selected_lane,
        "operator_commands": _operator_commands(selected_lane),
        "all_relevant_lane_commands": _all_relevant_lane_commands(
            selected_lane=selected_lane,
            lanes=lanes,
            include_all=all_evidence_lanes,
        ),
        "exact_confirmation_phrase": CONFIRMATION_PHRASE,
        "stop_conditions": _stop_conditions(),
        "post_clear_recheck_sequence": _post_clear_recheck_sequence(),
        "authorization_status": authorization_status,
        "safety_summary": _safety_summary(),
        "source_surfaces_used": _source_surfaces(workbench),
        "ledger_path": str(first_live_targeted_clearing_packs_path(resolved_log_dir)),
    }
    payload = _sanitize(payload)
    if record:
        append_first_live_targeted_clearing_pack(payload, log_dir=resolved_log_dir)
    return payload


def append_first_live_targeted_clearing_pack(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_targeted_clearing_packs_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_ledger_record(record), sort_keys=True) + "\n")


def load_first_live_targeted_clearing_packs(
    *,
    limit: int = 50,
    targeted_clearing_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_targeted_clearing_packs_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if targeted_clearing_id is not None and record.get("targeted_clearing_id") != targeted_clearing_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_targeted_clearing_packs_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_first_live_targeted_clearing_pack_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _lanes_by_id(workbench: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    lanes = {
        str(lane.get("lane_id")): dict(lane)
        for lane in workbench.get("clearing_lanes") or []
        if isinstance(lane, Mapping) and str(lane.get("lane_id") or "") in ALLOWED_LANE_IDS
    }
    if "emergency_and_position_review_lane" not in lanes:
        lanes["emergency_and_position_review_lane"] = _emergency_lane(workbench)
    return lanes


def _emergency_lane(workbench: Mapping[str, Any]) -> dict[str, Any]:
    statuses = workbench.get("source_statuses") if isinstance(workbench.get("source_statuses"), Mapping) else {}
    return {
        "lane_id": "emergency_and_position_review_lane",
        "title": "Review emergency cancel path and no-conflicting-position evidence",
        "owner": "OPERATOR",
        "current_status": statuses.get("R112 evidence status"),
        "target_status": "EMERGENCY_AND_POSITION_REVIEWED evidence accepted",
        "can_clear_now": True,
        "requires_secret_handling": False,
        "requires_env_change": False,
        "requires_live_order_capability": False,
        "commands": [_cmd("first-live-prerequisite-clearing")],
        "evidence_commands": [_evidence_execute_command("emergency_and_position_review")],
        "verification_commands": [_cmd("first-live-evidence-status"), _cmd("first-live-prerequisite-recheck-after-evidence")],
        "stop_conditions": ["active tuple changed", "evidence note would contain secrets", "order placed true"],
        "safety_notes": ["Emergency and position review records evidence only; it cannot cancel, open, close, or modify positions."],
    }


def _select_lane(
    *,
    requested_lane: str | None,
    lanes: Mapping[str, Mapping[str, Any]],
    workbench: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    if requested_lane:
        if requested_lane not in ALLOWED_LANE_IDS:
            return _invalid_lane(requested_lane), [f"invalid lane id: {requested_lane}"]
        return _selected_lane_payload(dict(lanes[requested_lane]), f"operator requested lane {requested_lane}"), []

    statuses = workbench.get("source_statuses") if isinstance(workbench.get("source_statuses"), Mapping) else {}
    evidence_status = str(statuses.get("R112 evidence status") or "")
    if evidence_status in {"", "EVIDENCE_MISSING", "EVIDENCE_PARTIAL"}:
        return _selected_lane_payload(dict(lanes["evidence_records_lane"]), "R112 evidence is partial or missing, so evidence_records_lane is first."), []
    for lane_id in DEFAULT_LANE_PRIORITY:
        candidate = lanes.get(lane_id)
        if candidate and candidate.get("can_clear_now") is True:
            return _selected_lane_payload(dict(candidate), f"{lane_id} is the next clearable lane in R120 priority order."), []
    return _selected_lane_payload(dict(lanes["final_gate_recheck_lane"]), "No earlier clearable lane was available; recheck the final gate."), []


def _invalid_lane(requested_lane: str) -> dict[str, Any]:
    return {
        "lane_id": requested_lane,
        "title": "Invalid lane rejected",
        "owner": "NONE",
        "current_status": "INVALID_LANE",
        "target_status": "Use one of the R120 allowed lane ids.",
        "can_clear_now": False,
        "requires_secret_handling": False,
        "requires_env_change": False,
        "requires_live_order_capability": False,
        "priority_reason": "The requested lane is not in the R120 allowed lane set.",
    }


def _selected_lane_payload(lane: dict[str, Any], priority_reason: str) -> dict[str, Any]:
    return {
        "lane_id": lane.get("lane_id"),
        "title": lane.get("title"),
        "owner": lane.get("owner"),
        "current_status": lane.get("current_status"),
        "target_status": lane.get("target_status"),
        "can_clear_now": bool(lane.get("can_clear_now")),
        "requires_secret_handling": bool(lane.get("requires_secret_handling")),
        "requires_env_change": bool(lane.get("requires_env_change")),
        "requires_live_order_capability": bool(lane.get("requires_live_order_capability")),
        "priority_reason": priority_reason,
        "commands": list(lane.get("commands") or []),
        "evidence_commands": list(lane.get("evidence_commands") or []),
        "verification_commands": list(lane.get("verification_commands") or []),
        "stop_conditions": list(lane.get("stop_conditions") or []),
        "safety_notes": list(lane.get("safety_notes") or []),
    }


def _active_tuple(workbench: Mapping[str, Any]) -> dict[str, Any]:
    active = workbench.get("active_tuple") if isinstance(workbench.get("active_tuple"), Mapping) else {}
    return {
        "candidate_id": active.get("candidate_id"),
        "risk_contract_hash": active.get("risk_contract_hash"),
        "packet_hash": active.get("packet_hash"),
        "tuple_status": active.get("tuple_status") or "MISSING",
        "source": active.get("source") or "R119 blocker clearing workbench",
    }


def _mode_decision(*, workbench: Mapping[str, Any], authorization_check: bool) -> dict[str, Any]:
    statuses = workbench.get("source_statuses") if isinstance(workbench.get("source_statuses"), Mapping) else {}
    r118_status = statuses.get("R118 final review")
    ready = r118_status == READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION
    selected_mode = "AUTHORIZATION_PREP_CHECK" if ready or authorization_check else "TARGETED_CLEARING"
    if ready:
        reason = "R118 says READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION, so R120 can prepare a later authorization request artifact only."
    elif authorization_check:
        reason = "Authorization check was requested, but R118 is not ready; targeted clearing remains required."
    else:
        reason = "R118 remains blocked or partial, so R120 chooses targeted clearing instead of authorization."
    return {
        "selected_mode": selected_mode,
        "reason": reason,
        "r118_status": r118_status,
        "r119_status": workbench.get("status"),
        "can_request_authorization_now": bool(ready),
    }


def _authorization_status(workbench: Mapping[str, Any]) -> dict[str, Any]:
    statuses = workbench.get("source_statuses") if isinstance(workbench.get("source_statuses"), Mapping) else {}
    ready = statuses.get("R118 final review") == READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION
    blockers = []
    for lane in workbench.get("clearing_lanes") or []:
        if isinstance(lane, Mapping) and lane.get("lane_id") != "future_authorization_lane" and lane.get("can_clear_now") is True:
            current = lane.get("current_status")
            target = lane.get("target_status")
            blockers.append(f"{lane.get('lane_id')}: {current} -> {target}")
    return {
        "can_prepare_authorization_request": bool(ready),
        "reason": (
            "R118 is ready; a future explicit authorization request phase may be prepared, still without execution."
            if ready
            else "R118 is not READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION; authorization request remains blocked."
        ),
        "required_before_authorization_request": [] if ready else blockers,
        "future_phase_if_ready": "R121_FIRST_LIVE_POST_TARGETED_CLEARING_RECHECK_OR_AUTHORIZATION_REQUEST",
        "future_phase_if_blocked": "R121_FIRST_LIVE_POST_TARGETED_CLEARING_RECHECK",
    }


def _status(
    *,
    workbench: Mapping[str, Any],
    authorization_check: bool,
    selected_lane: Mapping[str, Any],
    unsafe_reasons: list[str],
) -> str:
    statuses = workbench.get("source_statuses") if isinstance(workbench.get("source_statuses"), Mapping) else {}
    ready = statuses.get("R118 final review") == READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION
    if ready:
        return READY_TO_PREPARE_AUTHORIZATION_REQUEST
    if authorization_check:
        return AUTHORIZATION_REQUEST_NOT_READY
    if unsafe_reasons or selected_lane.get("can_clear_now") is not True or workbench.get("status") == WORKBENCH_BLOCKED_UNSAFE:
        return TARGETED_CLEARING_BLOCKED_UNSAFE
    return TARGETED_CLEARING_READY


def _operator_commands(selected_lane: Mapping[str, Any]) -> dict[str, Any]:
    lane_id = str(selected_lane.get("lane_id") or "")
    group = LANE_GROUPS.get(lane_id)
    if lane_id == "evidence_records_lane":
        preview = _cmd("first-live-evidence-assisted-run --all-groups")
        execute = _cmd(f"first-live-evidence-assisted-run --all-groups --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\"")
    elif group:
        preview = _cmd(f"first-live-evidence-assisted-run --group {group}")
        execute = _evidence_execute_command(group)
    else:
        commands = list(selected_lane.get("commands") or [])
        preview = commands[0] if commands else _cmd("first-live-blocker-clearing-workbench --no-record")
        execute = None

    result: dict[str, Any] = {
        "preview_command": preview,
        "status_recheck_commands": [
            _cmd("first-live-evidence-status"),
            _cmd("first-live-prerequisite-recheck-after-evidence"),
            _cmd("first-live-post-evidence-gate-recheck"),
            _cmd("first-live-blocker-clearing-workbench"),
        ],
        "final_review_command": _cmd("first-live-activation-final-review"),
        "cockpit_state_command": "curl -s http://127.0.0.1:8015/operator/approval-cockpit/state",
    }
    if execute:
        result["execute_evidence_command"] = execute
    return result


def _all_relevant_lane_commands(
    *,
    selected_lane: Mapping[str, Any],
    lanes: Mapping[str, Mapping[str, Any]],
    include_all: bool,
) -> dict[str, Any]:
    lane_ids = list(ALLOWED_LANE_IDS) if include_all else [str(selected_lane.get("lane_id") or "")]
    commands: dict[str, Any] = {}
    for lane_id in lane_ids:
        lane = lanes.get(lane_id)
        if not lane:
            continue
        if lane_id in LANE_GROUPS:
            group = LANE_GROUPS[lane_id]
            commands[lane_id] = {
                "preview_command": _cmd("first-live-evidence-assisted-run --all-groups")
                if group is None
                else _cmd(f"first-live-evidence-assisted-run --group {group}"),
                "execute_evidence_command": _cmd(f"first-live-evidence-assisted-run --all-groups --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\"")
                if group is None
                else _evidence_execute_command(group),
                "evidence_commands": list(lane.get("evidence_commands") or []),
            }
        elif not include_all:
            commands[lane_id] = {
                "preview_command": _operator_commands(selected_lane)["preview_command"],
                "evidence_commands": list(selected_lane.get("evidence_commands") or []),
            }
    return commands


def _evidence_execute_command(group: str) -> str:
    return _cmd(f"first-live-evidence-assisted-run --group {group} --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\"")


def _stop_conditions() -> list[str]:
    return [
        "active tuple changed",
        "R118 remains blocked after evidence",
        "sacred button can_place_order true",
        "sacred button records_intent_only false",
        "paper_live_separation_intact false",
        "secrets shown",
        "order placed true",
        "execution attempted true",
        "real_order_possible true",
        "env flag change attempted",
        "Binance order endpoint appears",
        "operator has not personally verified the evidence",
        "evidence note would contain secrets",
    ]


def _post_clear_recheck_sequence() -> list[dict[str, Any]]:
    commands = [
        ("R112", "first-live-evidence-status", _cmd("first-live-evidence-status")),
        ("R113", "first-live-prerequisite-recheck-after-evidence", _cmd("first-live-prerequisite-recheck-after-evidence")),
        ("R117", "first-live-post-evidence-gate-recheck", _cmd("first-live-post-evidence-gate-recheck")),
        ("R119", "first-live-blocker-clearing-workbench", _cmd("first-live-blocker-clearing-workbench")),
        ("R118", "first-live-activation-final-review", _cmd("first-live-activation-final-review")),
        ("R106", "first-live-activation-gate", _cmd("first-live-activation-gate")),
        ("R109", "cockpit state curl", "curl -s http://127.0.0.1:8015/operator/approval-cockpit/state"),
    ]
    return [{"step": index, "phase": phase, "name": name, "command": command} for index, (phase, name, command) in enumerate(commands, start=1)]


def _safety_summary() -> dict[str, Any]:
    return {
        "R120 does not place orders": True,
        "R120 does not enable live execution": True,
        "R120 does not change env flags": True,
        "R120 does not call Binance order endpoints": True,
        "R120 only prepares targeted clearing actions": True,
        "R106 remains authority": True,
        "R109 remains intent-only": True,
    }


def _unsafe_reasons(workbench: Mapping[str, Any]) -> list[str]:
    reasons = list(workbench.get("unsafe_reasons") or [])
    for field in SAFETY_FALSE_FIELDS:
        if workbench.get(field) is not False:
            reasons.append(f"{field} {str(workbench.get(field)).lower()}")
    if workbench.get("paper_live_separation_intact") is False:
        reasons.append("paper_live_separation_intact false")
    return sorted(set(str(reason) for reason in reasons))


def _source_surfaces(workbench: Mapping[str, Any]) -> list[str]:
    surfaces = [SOURCE_SURFACE, "R119 first-live-blocker-clearing-workbench", "R118 first-live-activation-final-review"]
    surfaces.extend(str(item) for item in workbench.get("source_surfaces_used") or [])
    return list(dict.fromkeys(surfaces))


def _ledger_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "event_type",
        "targeted_clearing_id",
        "recorded_at_utc",
        "status",
        "active_tuple",
        "mode_decision",
        "selected_lane",
        "authorization_status",
        "live_ready",
        "execution_enabled_by_targeted_clearing",
        "order_placed",
        "execution_attempted",
        "real_order_possible",
        "secrets_shown",
        "source_surfaces_used",
    ]
    record = {key: payload.get(key) for key in keys}
    record["real_order_placed"] = False
    return _sanitize(record)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        payload = {str(key): _sanitize(item) for key, item in value.items()}
        rendered = json.dumps(payload, sort_keys=True)
        secret_tokens = ("api_secret", "api key", "telegram_bot_token", "secret-api", "secret-telegram", "auth header", "bearer ")
        if any(token in rendered.lower() for token in secret_tokens):
            payload["secrets_shown"] = False
        return payload
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
