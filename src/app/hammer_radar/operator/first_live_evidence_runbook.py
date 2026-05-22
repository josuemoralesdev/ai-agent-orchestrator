"""R115 first-live evidence recording runbook.

This module wraps the R114 guided action pack into an ordered operator runbook.
It is diagnostic only: it never places orders, enables live execution, calls
Binance endpoints, edits environment flags, or creates execution authority.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_evidence_guided_actions import (
    ACTIONS_READY,
    GROUP_ORDER,
    build_first_live_evidence_guided_actions,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

RUNBOOK_READY = "RUNBOOK_READY"
RUNBOOK_BLOCKED = "RUNBOOK_BLOCKED"
EVENT_TYPE = "FIRST_LIVE_EVIDENCE_RUNBOOK"
LEDGER_FILENAME = "first_live_evidence_runbooks.ndjson"
SOURCE_SURFACE = "operator.first_live_evidence_runbook.build_first_live_evidence_runbook"

RECHECK_COMMANDS = [
    "first-live-evidence-status",
    "first-live-prerequisite-recheck-after-evidence",
    "first-live-prerequisite-clearing",
    "first-live-burn-down",
    "first-live-activation-gate",
    "approval cockpit state curl",
]

STOP_CONDITIONS = [
    "candidate/hash tuple changed",
    "R106 gate reports unexpected status",
    "sacred button can_place_order true",
    "any output exposes secrets",
    "any output reports order_placed true",
    "any output reports execution_attempted true",
    "any Binance order endpoint appears in the flow",
    "any evidence note would include secrets",
    "any source reports paper_live_separation_intact false",
]

SECTION_SPECS = [
    (
        "tuple_verification",
        "Tuple Verification",
        "Verify the active candidate/hash tuple before recording evidence.",
        (),
        ("guided_actions", "first_live_activation_gate"),
        [
            "Stop if the candidate id, risk contract hash, or packet hash differs from R114.",
            "Stop if R114 reports no active tuple.",
        ],
    ),
    (
        "approval_records",
        "Approval Records",
        "Record personally verified approval and human-review evidence for the active tuple.",
        ("approval_records",),
        ("first_live_evidence_status", "first_live_prerequisite_recheck_after_evidence"),
        ["Stop if any approval artifact is missing, stale, rejected, or for a different tuple."],
    ),
    (
        "account_and_funding",
        "Account And Funding",
        "Record read-only account, funding, and position-conflict evidence without account changes.",
        ("account_funding",),
        ("first_live_evidence_status", "first_live_prerequisite_recheck_after_evidence"),
        ["Stop if the review requires account, balance, funding, position, or order API calls from this runbook."],
    ),
    (
        "protective_orders",
        "Protective Orders",
        "Record protective stop and take-profit readiness evidence without creating orders.",
        ("protective_orders",),
        ("first_live_evidence_status", "first_live_prerequisite_recheck_after_evidence"),
        ["Stop if protective orders are ambiguous, incomplete, or require executable payloads."],
    ),
    (
        "adapter_boundary",
        "Adapter Boundary",
        "Record live-adapter boundary review while preserving paper/live separation.",
        ("adapter_boundary",),
        ("first_live_prerequisite_recheck_after_evidence", "first_live_activation_gate"),
        ["Stop if paper/live separation is not explicitly intact."],
    ),
    (
        "risk_limits",
        "Risk Limits",
        "Record tiny size and maximum-loss evidence for the active tuple.",
        ("risk_limits",),
        ("first_live_prerequisite_recheck_after_evidence", "first_live_burn_down"),
        ["Stop if size cap or maximum loss cap is absent, unclear, or not tied to the active tuple."],
    ),
    (
        "environment_review",
        "Environment Review",
        "Record environment flag and kill-switch review without reading or changing secret values.",
        ("environment",),
        ("first_live_prerequisite_recheck_after_evidence", "first_live_activation_gate"),
        ["Stop if any command would print env values, edit env flags, or change kill-switch state."],
    ),
    (
        "sacred_button_review",
        "Sacred Button Review",
        "Record that R109 remains intent-only and cannot place orders.",
        ("sacred_button",),
        ("approval_cockpit_state", "first_live_activation_gate"),
        ["Stop if cockpit state shows can_place_order true or records_intent_only false."],
    ),
    (
        "emergency_and_position_review",
        "Emergency And Position Review",
        "Record emergency procedure and no-conflicting-position review without service actions.",
        ("emergency", "position_conflict"),
        ("first_live_evidence_status", "first_live_prerequisite_recheck_after_evidence"),
        ["Stop if the review would restart services, cancel orders, or query live position endpoints from this runbook."],
    ),
    (
        "final_recheck_sequence",
        "Final Recheck Sequence",
        "Run the non-executing R112/R113/R111/R110/R106/R109 sequence after each evidence group.",
        (),
        ("first_live_evidence_status", "first_live_prerequisite_recheck_after_evidence", "first_live_activation_gate"),
        ["Stop if any recheck reports blockers, unexpected status, execution attempt, order placement, or exposed secrets."],
    ),
]


def build_first_live_evidence_runbook(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    checked_at = datetime.now(UTC).isoformat()
    guided_actions = build_first_live_evidence_guided_actions(
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
        record=False,
    )
    active_tuple = guided_actions.get("active_tuple") if isinstance(guided_actions.get("active_tuple"), Mapping) else {}
    status = _status(guided_actions=guided_actions, active_tuple=active_tuple)
    command_lookup = _command_lookup(guided_actions=guided_actions)
    runbook_sections = _runbook_sections(guided_actions=guided_actions, command_lookup=command_lookup)
    command_pack = _command_pack(guided_actions=guided_actions, command_lookup=command_lookup, runbook_sections=runbook_sections)
    payload = {
        "event_type": EVENT_TYPE,
        "runbook_id": uuid4().hex,
        "recorded_at_utc": checked_at,
        "status": status,
        "checked_at_utc": checked_at,
        "live_ready": False,
        "execution_enabled_by_runbook": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "active_tuple": {
            "candidate_id": active_tuple.get("candidate_id"),
            "risk_contract_hash": active_tuple.get("risk_contract_hash"),
            "packet_hash": active_tuple.get("packet_hash"),
            "tuple_status": active_tuple.get("tuple_status"),
        },
        "runbook_sections": runbook_sections,
        "command_pack": command_pack,
        "stop_conditions": list(STOP_CONDITIONS),
        "operator_script_preview": _operator_script_preview(runbook_sections=runbook_sections),
        "next_recheck_sequence": list(RECHECK_COMMANDS),
        "safety_summary": {
            "evidence runbook does not place orders": True,
            "evidence runbook does not enable live execution": True,
            "R106 remains authority": True,
            "R109 sacred button remains intent-only": True,
            "no secret values should be pasted into notes": True,
        },
        "source_statuses": guided_actions.get("source_statuses"),
        "r114_action_pack_id": guided_actions.get("action_pack_id"),
        "ledger_path": str(first_live_evidence_runbooks_path(resolved_log_dir)),
        "source_surfaces_used": _source_surfaces(guided_actions=guided_actions),
        "paper_live_separation_intact": bool(guided_actions.get("paper_live_separation_intact")),
        "warnings": list(guided_actions.get("warnings") or []),
    }
    payload = _sanitize(payload)
    if record:
        append_first_live_evidence_runbook(payload, log_dir=resolved_log_dir)
    return payload


def append_first_live_evidence_runbook(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_evidence_runbooks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_ledger_record(record), sort_keys=True) + "\n")


def load_first_live_evidence_runbooks(
    *,
    limit: int = 50,
    runbook_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_evidence_runbooks_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if runbook_id is not None and record.get("runbook_id") != runbook_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_evidence_runbooks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_first_live_evidence_runbook_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _status(*, guided_actions: Mapping[str, Any], active_tuple: Mapping[str, Any]) -> str:
    if guided_actions.get("status") != ACTIONS_READY:
        return RUNBOOK_BLOCKED
    if active_tuple.get("tuple_status") != "PRESENT":
        return RUNBOOK_BLOCKED
    if guided_actions.get("paper_live_separation_intact") is False:
        return RUNBOOK_BLOCKED
    return RUNBOOK_READY


def _command_lookup(*, guided_actions: Mapping[str, Any]) -> dict[str, str]:
    recheck_commands = list(guided_actions.get("recheck_commands") or [])
    return {
        "guided_actions": _cmd("first-live-evidence-guided-actions"),
        "first_live_evidence_status": _command_at(recheck_commands, 0, "first-live-evidence-status"),
        "first_live_prerequisite_recheck_after_evidence": _command_at(
            recheck_commands,
            1,
            "first-live-prerequisite-recheck-after-evidence",
        ),
        "first_live_prerequisite_clearing": _command_at(recheck_commands, 2, "first-live-prerequisite-clearing"),
        "first_live_burn_down": _command_at(recheck_commands, 3, "first-live-burn-down"),
        "first_live_activation_gate": _command_at(recheck_commands, 4, "first-live-activation-gate"),
        "approval_cockpit_state": _command_at(
            recheck_commands,
            5,
            "curl -s http://127.0.0.1:8015/operator/approval-cockpit/state",
        ),
    }


def _command_at(commands: list[Any], index: int, fallback: str) -> str:
    if index < len(commands) and commands[index]:
        return str(commands[index])
    if fallback.startswith("curl "):
        return fallback
    return _cmd(fallback)


def _runbook_sections(
    *,
    guided_actions: Mapping[str, Any],
    command_lookup: Mapping[str, str],
) -> list[dict[str, Any]]:
    grouped_actions = guided_actions.get("grouped_actions") if isinstance(guided_actions.get("grouped_actions"), Mapping) else {}
    sections: list[dict[str, Any]] = []
    for section_id, title, purpose, group_names, verification_keys, section_stop_conditions in SECTION_SPECS:
        commands = _section_commands(section_id=section_id, group_names=group_names, grouped_actions=grouped_actions, command_lookup=command_lookup)
        sections.append(
            {
                "section_id": section_id,
                "title": title,
                "purpose": purpose,
                "commands": commands,
                "verification_commands": [command_lookup[key] for key in verification_keys],
                "stop_conditions": list(dict.fromkeys([*section_stop_conditions, *STOP_CONDITIONS])),
                "safety_notes": _safety_notes(section_id),
            }
        )
    return sections


def _section_commands(
    *,
    section_id: str,
    group_names: tuple[str, ...],
    grouped_actions: Mapping[str, Any],
    command_lookup: Mapping[str, str],
) -> list[str]:
    if section_id == "tuple_verification":
        return [command_lookup["guided_actions"]]
    if section_id == "final_recheck_sequence":
        return [
            command_lookup["first_live_evidence_status"],
            command_lookup["first_live_prerequisite_recheck_after_evidence"],
            command_lookup["first_live_prerequisite_clearing"],
            command_lookup["first_live_burn_down"],
            command_lookup["first_live_activation_gate"],
            command_lookup["approval_cockpit_state"],
        ]
    commands: list[str] = []
    for group_name in group_names:
        for action in grouped_actions.get(group_name) or []:
            if isinstance(action, Mapping) and action.get("command"):
                commands.append(str(action["command"]))
    return commands


def _safety_notes(section_id: str) -> list[str]:
    notes = [
        "Review before running; operator must personally verify the evidence.",
        "This section records evidence only and never places an order.",
        "Do not paste secret values, tokens, keys, signatures, auth headers, or env values into notes.",
        "R106 remains authority; R109 remains intent-only.",
    ]
    if section_id == "environment_review":
        notes.append("Review flag state without editing env flags or printing env values.")
    if section_id == "sacred_button_review":
        notes.append("The sacred button must remain records-intent-only with can_place_order false.")
    return notes


def _command_pack(
    *,
    guided_actions: Mapping[str, Any],
    command_lookup: Mapping[str, str],
    runbook_sections: list[Mapping[str, Any]],
) -> dict[str, Any]:
    grouped = guided_actions.get("grouped_actions") if isinstance(guided_actions.get("grouped_actions"), Mapping) else {}
    command_groups = {group: _commands_for_groups(grouped, (group,)) for group in GROUP_ORDER}
    recheck_commands = [
        command_lookup["first_live_evidence_status"],
        command_lookup["first_live_prerequisite_recheck_after_evidence"],
        command_lookup["first_live_prerequisite_clearing"],
        command_lookup["first_live_burn_down"],
        command_lookup["first_live_activation_gate"],
        command_lookup["approval_cockpit_state"],
    ]
    all_commands: list[str] = []
    for section in runbook_sections:
        all_commands.extend(str(command) for command in section.get("commands") or [])
        all_commands.extend(str(command) for command in section.get("verification_commands") or [])
    all_commands = list(dict.fromkeys(all_commands))
    return {
        "all_commands": all_commands,
        "approval_record_commands": command_groups["approval_records"],
        "account_funding_commands": command_groups["account_funding"],
        "protective_order_commands": command_groups["protective_orders"],
        "adapter_boundary_commands": command_groups["adapter_boundary"],
        "risk_limit_commands": command_groups["risk_limits"],
        "environment_commands": command_groups["environment"],
        "sacred_button_commands": command_groups["sacred_button"],
        "emergency_position_commands": [
            *command_groups["emergency"],
            *command_groups["position_conflict"],
        ],
        "recheck_commands": recheck_commands,
    }


def _commands_for_groups(grouped: Mapping[str, Any], group_names: tuple[str, ...]) -> list[str]:
    commands: list[str] = []
    for group_name in group_names:
        for action in grouped.get(group_name) or []:
            if isinstance(action, Mapping) and action.get("command"):
                commands.append(str(action["command"]))
    return commands


def _operator_script_preview(*, runbook_sections: list[Mapping[str, Any]]) -> list[str]:
    lines = [
        "# REVIEW_BEFORE_RUNNING: R115 evidence runbook preview.",
        "# Operator must personally verify each evidence group before running it.",
        "# This script never calls Binance directly, never edits env flags, and never places orders.",
        "set -euo pipefail",
        "",
    ]
    for section in runbook_sections:
        lines.append(f"echo 'REVIEW_BEFORE_RUNNING section: {section['section_id']}'")
        lines.append("echo 'Pause and verify this evidence group before continuing.'")
        for command in section.get("commands") or []:
            lines.append(str(command))
        for command in section.get("verification_commands") or []:
            lines.append(str(command))
        lines.append("")
    return lines


def _source_surfaces(*, guided_actions: Mapping[str, Any]) -> list[str]:
    surfaces = [
        SOURCE_SURFACE,
        "R114 first-live-evidence-guided-actions",
        "R112 first-live-evidence-status",
        "R113 first-live-prerequisite-recheck-after-evidence",
        "R111 first-live-prerequisite-clearing",
        "R110 first-live-burn-down",
        "R106 first-live-activation-gate",
        "R109 first-live cockpit sacred button state",
    ]
    surfaces.extend(str(item) for item in guided_actions.get("source_surfaces_used") or [])
    return list(dict.fromkeys(surfaces))


def _ledger_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    command_pack = payload.get("command_pack") if isinstance(payload.get("command_pack"), Mapping) else {}
    return _sanitize(
        {
            "event_type": EVENT_TYPE,
            "runbook_id": payload.get("runbook_id"),
            "recorded_at_utc": payload.get("recorded_at_utc"),
            "status": payload.get("status"),
            "active_tuple": payload.get("active_tuple"),
            "runbook_sections_count": len(payload.get("runbook_sections") or []),
            "command_count": len(command_pack.get("all_commands") or []),
            "stop_conditions": payload.get("stop_conditions"),
            "live_ready": False,
            "execution_enabled_by_runbook": False,
            "order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "source_surfaces_used": payload.get("source_surfaces_used"),
        }
    )


def _cmd(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        payload = {str(key): _sanitize(item) for key, item in value.items()}
        rendered = json.dumps(payload, sort_keys=True)
        secret_tokens = ("api_secret", "api key", "telegram_bot_token", "secret-api", "secret-telegram", "auth header")
        if any(token in rendered.lower() for token in secret_tokens):
            payload["secrets_shown"] = False
        return payload
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
