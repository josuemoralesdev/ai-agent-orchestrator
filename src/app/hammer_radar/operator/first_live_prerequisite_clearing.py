"""R111 first-live activation prerequisite clearing.

This module turns the R110 burn-down blocker groups into explicit prerequisite
checks for the operator. It is diagnostic only: it never enables live execution,
places orders, signs payloads, calls Binance order endpoints, or changes env
flags.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_burn_down import (
    build_first_live_burn_down,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

PREREQS_BLOCKED = "PREREQS_BLOCKED"
PREREQS_CLEARING_READY = "PREREQS_CLEARING_READY"
EVENT_TYPE = "FIRST_LIVE_PREREQUISITE_CLEARING"
LEDGER_FILENAME = "first_live_prerequisite_clearing.ndjson"
SOURCE_SURFACE = "operator.first_live_prerequisite_clearing.build_first_live_prerequisite_clearing"

GROUP_ORDER = [
    "candidate_freshness",
    "approval_records",
    "binance_credentials_presence",
    "account_funding_read_only_check",
    "protective_orders_readiness",
    "live_adapter_boundary",
    "tiny_position_size_cap",
    "max_loss_cap",
    "environment_flag_review",
    "confirmation_phrase_preparation",
    "sacred_button_safety",
    "duplicate_source_conflicts",
]

MORNING_LIVE_READINESS_SEQUENCE = [
    "Run first-live-burn-down",
    "Confirm candidate freshness",
    "Record approval intent",
    "Complete R85/R86/R88 human review records",
    "Configure Binance credential presence safely",
    "Verify account/funding read-only",
    "Verify protective order readiness",
    "Verify adapter boundary",
    "Define tiny size and max loss cap",
    "Re-run final-live-preflight",
    "Re-run tiny-live-armed-dry-run",
    "Re-run one-tiny-live-order-protocol",
    "Re-run first-live-activation-gate",
    "Verify cockpit sacred button state",
    "Stop if anything remains blocked",
]


def _cmd(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


def build_first_live_prerequisite_clearing(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    burn_down = build_first_live_burn_down(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, record=False)
    chain = burn_down.get("current_gate_chain") if isinstance(burn_down.get("current_gate_chain"), dict) else {}
    groups = burn_down.get("blocker_groups") if isinstance(burn_down.get("blocker_groups"), dict) else {}
    sacred_button = chain.get("sacred_button_state") if isinstance(chain.get("sacred_button_state"), dict) else {}

    prerequisite_groups = {
        "candidate_freshness": _candidate_freshness(groups),
        "approval_records": _approval_records(groups),
        "binance_credentials_presence": _binance_credentials_presence(groups),
        "account_funding_read_only_check": _account_funding_read_only_check(groups),
        "protective_orders_readiness": _protective_orders_readiness(groups),
        "live_adapter_boundary": _live_adapter_boundary(groups),
        "tiny_position_size_cap": _tiny_position_size_cap(groups),
        "max_loss_cap": _max_loss_cap(groups),
        "environment_flag_review": _environment_flag_review(groups),
        "confirmation_phrase_preparation": _confirmation_phrase_preparation(groups),
        "sacred_button_safety": _sacred_button_safety(sacred_button),
        "duplicate_source_conflicts": _duplicate_source_conflicts(burn_down),
    }
    counts = _counts(prerequisite_groups)
    status = PREREQS_CLEARING_READY if counts["blocked_count"] == 0 and counts["operator_evidence_needed_count"] == 0 and counts["unknown_count"] == 0 else PREREQS_BLOCKED
    checked_at = datetime.now(UTC).isoformat()
    source_statuses = _source_statuses(burn_down)
    payload = {
        "event_type": EVENT_TYPE,
        "clearing_id": uuid4().hex,
        "recorded_at_utc": checked_at,
        "status": status,
        "checked_at_utc": checked_at,
        "live_ready": False,
        "execution_enabled_by_prereq_clearing": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "candidate_id": candidate_id,
        "source_statuses": source_statuses,
        "prerequisite_groups": {name: prerequisite_groups[name] for name in GROUP_ORDER},
        **counts,
        "next_operator_actions": _next_operator_actions(prerequisite_groups),
        "morning_live_readiness_sequence": list(MORNING_LIVE_READINESS_SEQUENCE),
        "safety_summary": {
            "R106 remains authority": True,
            "cockpit is intent-only": True,
            "no order was placed": True,
            "live execution remains disabled by this phase": True,
        },
        "ledger_path": str(first_live_prerequisite_clearing_path(resolved_log_dir)),
        "source_surfaces_used": _source_surfaces(burn_down),
        "paper_live_separation_intact": bool(burn_down.get("paper_live_separation_intact")),
    }
    payload = _sanitize(payload)
    if record:
        append_first_live_prerequisite_clearing(payload, log_dir=resolved_log_dir)
    return payload


def append_first_live_prerequisite_clearing(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_prerequisite_clearing_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_ledger_record(record), sort_keys=True) + "\n")


def load_first_live_prerequisite_clearings(
    *,
    limit: int = 50,
    clearing_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_prerequisite_clearing_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if clearing_id is not None and record.get("clearing_id") != clearing_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_prerequisite_clearing_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_first_live_prerequisite_clearing_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _candidate_freshness(groups: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _blockers(groups, "candidate_blockers")
    return _group(
        status="BLOCKED" if blockers else "CLEAR",
        evidence_required="Fresh promoted candidate for the exact candidate id, risk contract hash, and packet hash.",
        evidence_present={"blockers": blockers, "fresh_candidate_confirmed": not blockers},
        next_action="Confirm candidate freshness before recording or relying on approval evidence.",
        verification_command=_cmd("final-live-preflight"),
        owner="MARKET",
        related_phase="R102/R106/R110",
        safety_notes="Freshness is a prerequisite only; it does not authorize execution.",
    )


def _approval_records(groups: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _blockers(groups, "approval_record_blockers")
    return _group(
        status="NEEDS_OPERATOR_EVIDENCE" if blockers else "CLEAR",
        evidence_required="Accepted approval intent and complete R85/R86/R88 human review records for the same candidate and hashes.",
        evidence_present={"blockers": blockers, "approval_records_complete": not blockers},
        next_action="Record approval intent and complete missing human review records as audit evidence only.",
        verification_command=_cmd("tiny-live-armed-dry-run"),
        owner="OPERATOR",
        related_phase="R103/R104/R106",
        safety_notes="Approval records remain intent/evidence only and are not execution authority.",
    )


def _binance_credentials_presence(groups: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _blockers(groups, "binance_credential_blockers")
    return _group(
        status="NEEDS_OPERATOR_EVIDENCE" if blockers else "CLEAR",
        evidence_required="Private operator-managed credential presence booleans only; no credential values.",
        evidence_present={"blockers": blockers, "credential_values_shown": False, "presence_confirmed": not blockers},
        next_action="Configure or verify Binance credential presence outside this phase without printing values.",
        verification_command=_cmd("final-live-preflight"),
        owner="CONFIG",
        related_phase="R102/R106/R110",
        safety_notes="R111 reports presence only and must never expose keys or secrets.",
    )


def _account_funding_read_only_check(groups: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _blockers(groups, "account_funding_blockers", include=("account", "funding", "balance", "conflicting"))
    return _group(
        status="NEEDS_OPERATOR_EVIDENCE" if blockers else "CLEAR",
        evidence_required="Operator read-only account/funding check record with no order placement and no account setting changes.",
        evidence_present={"blockers": blockers, "read_only_check_recorded": not blockers},
        next_action="Record read-only funding/account evidence; do not call order endpoints.",
        verification_command=_cmd("first-live-activation-gate"),
        owner="EXCHANGE",
        related_phase="R106/R111",
        safety_notes="Read-only funding evidence is not execution permission.",
    )


def _protective_orders_readiness(groups: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _blockers(groups, "protective_order_blockers")
    return _group(
        status="BLOCKED" if blockers else "CLEAR",
        evidence_required="Protective stop and take-profit readiness for the exact tiny-live candidate.",
        evidence_present={"blockers": blockers, "protective_orders_ready": not blockers},
        next_action="Verify protective order readiness before any future activation-ready attempt.",
        verification_command=_cmd("one-tiny-live-order-protocol"),
        owner="CODE",
        related_phase="R105/R106",
        safety_notes="Protective readiness does not create or submit protective orders in R111.",
    )


def _live_adapter_boundary(groups: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _blockers(groups, "adapter_blockers")
    return _group(
        status="BLOCKED" if blockers else "CLEAR",
        evidence_required="Live adapter boundary reviewed with paper/live separation intact.",
        evidence_present={"blockers": blockers, "adapter_boundary_clear": not blockers},
        next_action="Verify adapter boundary while keeping R111 non-executing.",
        verification_command=_cmd("first-live-activation-gate"),
        owner="CODE",
        related_phase="R105/R106/R111",
        safety_notes="R111 must not configure or call a live order adapter.",
    )


def _tiny_position_size_cap(groups: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _blockers(groups, "account_funding_blockers", include=("position size",))
    return _group(
        status="NEEDS_OPERATOR_EVIDENCE" if blockers else "CLEAR",
        evidence_required="Explicit tiny notional cap for the first live candidate.",
        evidence_present={"blockers": blockers, "tiny_position_size_cap_recorded": not blockers},
        next_action="Define the tiny size cap as operator evidence for a later phase.",
        verification_command=_cmd("first-live-activation-gate"),
        owner="OPERATOR",
        related_phase="R106/R111",
        safety_notes="A size cap is a prerequisite record only and cannot place an order.",
    )


def _max_loss_cap(groups: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _blockers(groups, "account_funding_blockers", include=("max loss",))
    return _group(
        status="NEEDS_OPERATOR_EVIDENCE" if blockers else "CLEAR",
        evidence_required="Explicit maximum loss cap acknowledged by the operator.",
        evidence_present={"blockers": blockers, "max_loss_cap_recorded": not blockers},
        next_action="Record the max loss cap and acknowledgement before any future authorization phase.",
        verification_command=_cmd("first-live-activation-gate"),
        owner="OPERATOR",
        related_phase="R106/R111",
        safety_notes="A max loss cap record does not authorize execution.",
    )


def _environment_flag_review(groups: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _blockers(groups, "environment_flag_blockers")
    return _group(
        status="BLOCKED" if blockers else "CLEAR",
        evidence_required="Safe live environment and kill-switch review; R111 does not edit flags.",
        evidence_present={"blockers": blockers, "env_flags_changed_by_r111": False, "environment_review_clear": not blockers},
        next_action="Review environment flag blockers without modifying env in this phase.",
        verification_command=_cmd("final-live-preflight"),
        owner="CONFIG",
        related_phase="R102/R106",
        safety_notes="Live flags remain unchanged by prerequisite clearing.",
    )


def _confirmation_phrase_preparation(groups: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _blockers(groups, "confirmation_phrase_blockers")
    return _group(
        status="NEEDS_OPERATOR_EVIDENCE" if blockers else "CLEAR",
        evidence_required="Prepared exact confirmation phrase template for later explicit authorization.",
        evidence_present={"blockers": blockers, "confirmation_phrase_recorded": not blockers},
        next_action="Prepare the phrase evidence only; do not use it to execute in R111.",
        verification_command=_cmd("first-live-activation-gate"),
        owner="OPERATOR",
        related_phase="R105/R106",
        safety_notes="The confirmation phrase remains inactive and non-executing in R111.",
    )


def _sacred_button_safety(sacred_button: Mapping[str, Any]) -> dict[str, Any]:
    can_place_order = bool(sacred_button.get("can_place_order"))
    records_intent_only = sacred_button.get("records_intent_only") is True
    clear = can_place_order is False and records_intent_only
    return _group(
        status="CLEAR" if clear else "BLOCKED",
        evidence_required="Cockpit sacred button state showing can_place_order=false and records_intent_only=true.",
        evidence_present={
            "label": sacred_button.get("label"),
            "enabled": bool(sacred_button.get("enabled")),
            "can_place_order": can_place_order,
            "records_intent_only": records_intent_only,
        },
        next_action="Verify cockpit sacred button remains intent-only.",
        verification_command="curl -s http://127.0.0.1:8015/operator/approval-cockpit/state",
        owner="OPERATOR",
        related_phase="R109/R111",
        safety_notes="R109 sacred button remains intent-only and cannot place orders.",
    )


def _duplicate_source_conflicts(burn_down: Mapping[str, Any]) -> dict[str, Any]:
    source_statuses = _source_statuses(burn_down)
    conflicts = [
        "R110 missing R102 final preflight status" if not source_statuses.get("R102 final preflight") else "",
        "R110 missing R104 tiny-live armed dry run status" if not source_statuses.get("R104 tiny-live armed dry run") else "",
        "R110 missing R105 protocol status" if not source_statuses.get("R105 protocol") else "",
        "R110 missing R106 activation gate status" if not source_statuses.get("R106 activation gate") else "",
        "R110 missing R109 cockpit status" if not source_statuses.get("R109 cockpit") else "",
        "R110 missing R110 burn-down status" if not source_statuses.get("R110 burn-down") else "",
    ]
    conflicts = [item for item in conflicts if item]
    return _group(
        status="UNKNOWN" if conflicts else "CLEAR",
        evidence_required="Consistent source statuses from R102/R104/R105/R106/R109/R110.",
        evidence_present={"source_statuses": source_statuses, "conflicts": conflicts},
        next_action="Resolve missing or conflicting source status records before treating prerequisites as ready.",
        verification_command=_cmd("first-live-burn-down"),
        owner="INDEX",
        related_phase="R102-R111",
        safety_notes="R111 composes existing surfaces and does not become a second activation gate.",
    )


def _group(
    *,
    status: str,
    evidence_required: str,
    evidence_present: Mapping[str, Any],
    next_action: str,
    verification_command: str,
    owner: str,
    related_phase: str,
    safety_notes: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "evidence_required": evidence_required,
        "evidence_present": dict(evidence_present),
        "next_action": next_action,
        "verification_command": verification_command,
        "owner": owner,
        "related_phase": related_phase,
        "safety_notes": safety_notes,
    }


def _blockers(
    groups: Mapping[str, Any],
    group_name: str,
    *,
    include: tuple[str, ...] | None = None,
) -> list[str]:
    group = groups.get(group_name) if isinstance(groups.get(group_name), dict) else {}
    blockers = [str(item) for item in group.get("blockers") or []]
    if include is None:
        return blockers
    return [item for item in blockers if any(term in item.lower() for term in include)]


def _counts(groups: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    statuses = [str(group.get("status") or "UNKNOWN") for group in groups.values()]
    return {
        "cleared_count": statuses.count("CLEAR"),
        "blocked_count": statuses.count("BLOCKED"),
        "operator_evidence_needed_count": statuses.count("NEEDS_OPERATOR_EVIDENCE"),
        "unknown_count": statuses.count("UNKNOWN"),
    }


def _next_operator_actions(groups: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    priority = {"BLOCKED": 0, "NEEDS_OPERATOR_EVIDENCE": 1, "UNKNOWN": 2, "CLEAR": 3}
    actions = []
    for name in GROUP_ORDER:
        group = groups[name]
        if group.get("status") == "CLEAR":
            continue
        actions.append(
            {
                "priority": len(actions) + 1,
                "group": name,
                "status": group.get("status"),
                "action": group.get("next_action"),
                "verification_command": group.get("verification_command"),
                "owner": group.get("owner"),
            }
        )
    actions.sort(key=lambda item: (priority.get(str(item["status"]), 9), GROUP_ORDER.index(str(item["group"]))))
    for index, item in enumerate(actions, start=1):
        item["priority"] = index
    return actions


def _source_statuses(burn_down: Mapping[str, Any]) -> dict[str, Any]:
    chain = burn_down.get("current_gate_chain") if isinstance(burn_down.get("current_gate_chain"), dict) else {}
    return {
        "R102 final preflight": chain.get("final_preflight_status") or _burn_down_source_status(burn_down, "R102"),
        "R104 tiny-live armed dry run": chain.get("tiny_live_armed_dry_run_status") or _burn_down_source_status(burn_down, "R104"),
        "R105 protocol": chain.get("protocol_status") or _burn_down_source_status(burn_down, "R105"),
        "R106 activation gate": chain.get("first_live_activation_gate_status") or _burn_down_source_status(burn_down, "R106"),
        "R109 cockpit": chain.get("cockpit_status") or _burn_down_source_status(burn_down, "R109"),
        "R110 burn-down": burn_down.get("status"),
    }


def _burn_down_source_status(burn_down: Mapping[str, Any], key: str) -> Any:
    statuses = burn_down.get("source_statuses") if isinstance(burn_down.get("source_statuses"), dict) else {}
    return statuses.get(key)


def _source_surfaces(burn_down: Mapping[str, Any]) -> list[str]:
    surfaces = [
        SOURCE_SURFACE,
        "R102 final-live-preflight",
        "R104 tiny-live-armed-dry-run",
        "R105 one-tiny-live-order-protocol",
        "R106 first-live-activation-gate",
        "R109 first-live cockpit sacred button state",
        "R110 first-live-burn-down",
    ]
    surfaces.extend(str(item) for item in burn_down.get("source_surfaces_used") or [])
    return list(dict.fromkeys(surfaces))


def _ledger_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "event_type",
        "clearing_id",
        "recorded_at_utc",
        "status",
        "prerequisite_groups",
        "cleared_count",
        "blocked_count",
        "operator_evidence_needed_count",
        "unknown_count",
        "live_ready",
        "execution_enabled_by_prereq_clearing",
        "order_placed",
        "execution_attempted",
        "real_order_possible",
        "secrets_shown",
        "source_surfaces_used",
    ]
    record = {key: payload.get(key) for key in keys}
    record["real_order_placed"] = False
    return _sanitize(record)


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    rendered = json.dumps(payload, sort_keys=True)
    secret_tokens = ("api_secret", "api key", "telegram_bot_token", "secret-api", "secret-telegram", "auth header")
    if any(token in rendered.lower() for token in secret_tokens):
        payload = dict(payload)
        payload["secrets_shown"] = False
    return payload
