"""R116 assisted first-live evidence recording run.

This module assists R112 evidence recording from the R115 runbook. It is
evidence-only: it never places orders, enables live execution, calls Binance
order endpoints, edits environment flags, or creates execution authority.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_activation_gate import (
    FIRST_LIVE_ACTIVATION_READY,
    FIRST_LIVE_BLOCKED,
    build_first_live_activation_gate,
)
from src.app.hammer_radar.operator.first_live_evidence_runbook import (
    RUNBOOK_READY,
    build_first_live_evidence_runbook,
)
from src.app.hammer_radar.operator.first_live_operator_approval_cockpit import (
    build_operator_approval_cockpit_state,
)
from src.app.hammer_radar.operator.first_live_operator_evidence import (
    build_first_live_evidence_status,
    record_first_live_operator_evidence,
)
from src.app.hammer_radar.operator.first_live_prerequisite_recheck_after_evidence import (
    build_first_live_prerequisite_recheck_after_evidence,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

ASSISTED_RUN_PREVIEW = "ASSISTED_RUN_PREVIEW"
ASSISTED_RUN_REJECTED = "ASSISTED_RUN_REJECTED"
ASSISTED_RUN_RECORDED = "ASSISTED_RUN_RECORDED"
ASSISTED_RUN_PARTIAL = "ASSISTED_RUN_PARTIAL"
EVENT_TYPE = "FIRST_LIVE_EVIDENCE_ASSISTED_RUN"
LEDGER_FILENAME = "first_live_evidence_assisted_runs.ndjson"
SOURCE_SURFACE = "operator.first_live_evidence_assisted_run.build_first_live_evidence_assisted_run"
CONFIRMATION_PHRASE = "I CONFIRM EVIDENCE RECORDING ONLY; NO LIVE ORDER; NO ENV CHANGE."

SUPPORTED_GROUPS = (
    "approval_records",
    "account_and_funding",
    "protective_orders",
    "adapter_boundary",
    "risk_limits",
    "environment_review",
    "sacred_button_review",
    "emergency_and_position_review",
)

SECRET_RISK_TERMS = (
    "api key",
    "api_secret",
    "private key",
    "token=",
    "password=",
    "bearer ",
    "signature=",
    "auth header",
    "telegram_bot_token",
)

SAFETY_FALSE_FIELDS = (
    "live_ready",
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "real_order_possible",
    "secrets_shown",
)


def build_first_live_evidence_assisted_run(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    group: str | None = None,
    all_groups: bool = False,
    execute_evidence: bool = False,
    confirm_evidence_only: str | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    checked_at = datetime.now(UTC).isoformat()
    selected_groups, group_errors = _selected_groups(group=group, all_groups=all_groups)
    confirmation_valid = str(confirm_evidence_only or "") == CONFIRMATION_PHRASE

    runbook = build_first_live_evidence_runbook(
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
        record=False,
    )
    before_status = _status_snapshot(
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
        runbook=runbook,
    )
    active_tuple = _active_tuple(runbook)
    group_commands = _commands_by_group(runbook=runbook)
    planned_commands = {name: group_commands.get(name, []) for name in selected_groups}
    planned_evidence_types = _planned_evidence_types(planned_commands)
    rejected_evidence: list[dict[str, Any]] = []
    recorded_evidence_ids: list[str] = []
    group_recheck_summaries: list[dict[str, Any]] = []

    stop_conditions = _stop_conditions(
        selected_groups=selected_groups,
        group_errors=group_errors,
        execute_evidence=execute_evidence,
        confirmation_valid=confirmation_valid,
        runbook=runbook,
        before_status=before_status,
        active_tuple=active_tuple,
        planned_commands=planned_commands,
    )

    if execute_evidence and not confirmation_valid:
        rejected_evidence.append(
            {
                "group": None,
                "evidence_type": None,
                "rejection_reason": "missing or invalid evidence-only confirmation",
            }
        )

    status = ASSISTED_RUN_PREVIEW
    if stop_conditions:
        status = ASSISTED_RUN_REJECTED if execute_evidence or group_errors else ASSISTED_RUN_PREVIEW
    elif execute_evidence:
        status = ASSISTED_RUN_RECORDED
        for group_name in selected_groups:
            group_result = _record_group_evidence(
                group_name=group_name,
                commands=group_commands.get(group_name, []),
                log_dir=resolved_log_dir,
            )
            recorded_evidence_ids.extend(group_result["recorded_evidence_ids"])
            rejected_evidence.extend(group_result["rejected_evidence"])
            group_recheck_summaries.append(_group_recheck_summary(candidate_id=candidate_id, group_name=group_name, log_dir=resolved_log_dir, env=env))
            if rejected_evidence or _unsafe_after_group(group_recheck_summaries[-1]):
                status = ASSISTED_RUN_PARTIAL
                break

    after_status = _status_snapshot(
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
        runbook=runbook,
        reuse_runbook_status=not recorded_evidence_ids,
    )
    payload = {
        "event_type": EVENT_TYPE,
        "assisted_run_id": uuid4().hex,
        "recorded_at_utc": checked_at,
        "checked_at_utc": checked_at,
        "status": status,
        "selected_groups": selected_groups,
        "execute_evidence_requested": bool(execute_evidence),
        "confirmation_valid": bool(confirmation_valid),
        "rejection_reason": _rejection_reason(stop_conditions=stop_conditions, rejected_evidence=rejected_evidence),
        "live_ready": False,
        "execution_enabled_by_assisted_run": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "active_tuple": active_tuple,
        "planned_evidence_types": planned_evidence_types,
        "planned_commands": planned_commands,
        "recorded_evidence_ids": recorded_evidence_ids,
        "rejected_evidence": rejected_evidence,
        "before_status": before_status,
        "after_status": after_status,
        "group_recheck_summaries": group_recheck_summaries,
        "recheck_commands": _recheck_commands(runbook),
        "stop_conditions": stop_conditions,
        "safety_summary": {
            "evidence_recording_only": True,
            "does_not_place_orders": True,
            "does_not_enable_live_execution": True,
            "does_not_call_binance_order_endpoints": True,
            "does_not_modify_env_flags": True,
            "R106_remains_authority": True,
            "R109_remains_intent_only": True,
            "paper_live_separation_intact": _paper_live_separation_intact(before_status, runbook, after_status),
        },
        "source_surfaces_used": _source_surfaces(runbook=runbook),
        "ledger_path": str(first_live_evidence_assisted_runs_path(resolved_log_dir)),
    }
    payload = _sanitize(payload)
    if record:
        append_first_live_evidence_assisted_run(payload, log_dir=resolved_log_dir)
    return payload


def append_first_live_evidence_assisted_run(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_evidence_assisted_runs_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_ledger_record(record), sort_keys=True) + "\n")


def load_first_live_evidence_assisted_runs(
    *,
    limit: int = 50,
    assisted_run_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_evidence_assisted_runs_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if assisted_run_id is not None and record.get("assisted_run_id") != assisted_run_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_evidence_assisted_runs_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_first_live_evidence_assisted_run_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _selected_groups(*, group: str | None, all_groups: bool) -> tuple[list[str], list[str]]:
    if all_groups or not group:
        return list(SUPPORTED_GROUPS), []
    normalized = str(group).strip()
    if normalized not in SUPPORTED_GROUPS:
        return [], [f"unsupported group: {normalized or '<empty>'}"]
    return [normalized], []


def _status_snapshot(
    *,
    candidate_id: str,
    log_dir: Path,
    env: Mapping[str, str] | None,
    runbook: Mapping[str, Any] | None = None,
    reuse_runbook_status: bool = True,
) -> dict[str, Any]:
    if runbook is not None and reuse_runbook_status:
        source_statuses = runbook.get("source_statuses") if isinstance(runbook.get("source_statuses"), Mapping) else {}
        return _sanitize(
            {
                "evidence_status": source_statuses.get("R112 evidence status"),
                "recheck_status": source_statuses.get("R113 recheck status"),
                "activation_gate_status": source_statuses.get("R106 activation gate status"),
                "cockpit_status": source_statuses.get("R109 cockpit status"),
                "paper_live_separation_intact": runbook.get("paper_live_separation_intact") is not False,
                "sacred_button_can_place_order": False,
                "cockpit_records_intent_only": True,
                "safety_field_violations": _safety_field_violations(runbook),
                "source_payloads": {
                    "runbook": _source_subset(runbook),
                },
            }
        )

    evidence_status = build_first_live_evidence_status(log_dir=log_dir)
    recheck = build_first_live_prerequisite_recheck_after_evidence(candidate_id=candidate_id, log_dir=log_dir, env=env, record=False)
    activation_gate = build_first_live_activation_gate(candidate_id=candidate_id, log_dir=log_dir, env=env, record=False)
    cockpit = build_operator_approval_cockpit_state(candidate_id=candidate_id, log_dir=log_dir, env=env)
    return _sanitize(
        {
            "evidence_status": evidence_status.get("status"),
            "recheck_status": recheck.get("status"),
            "activation_gate_status": activation_gate.get("status"),
            "cockpit_status": cockpit.get("status"),
            "paper_live_separation_intact": _paper_live_separation_from_sources(evidence_status, recheck, activation_gate, cockpit),
            "sacred_button_can_place_order": _sacred_button_can_place_order(cockpit),
            "cockpit_records_intent_only": _cockpit_records_intent_only(cockpit),
            "safety_field_violations": _safety_field_violations(evidence_status, recheck, activation_gate, cockpit),
            "source_payloads": {
                "evidence_status": _source_subset(evidence_status),
                "recheck": _source_subset(recheck),
                "activation_gate": _source_subset(activation_gate),
                "cockpit": _source_subset(cockpit),
            },
        }
    )


def _commands_by_group(*, runbook: Mapping[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {group: [] for group in SUPPORTED_GROUPS}
    for section in runbook.get("runbook_sections") or []:
        if not isinstance(section, Mapping):
            continue
        section_id = str(section.get("section_id") or "")
        if section_id in result:
            result[section_id] = [str(command) for command in section.get("commands") or [] if command]
    return result


def _planned_evidence_types(planned_commands: Mapping[str, list[str]]) -> dict[str, list[str]]:
    return {
        group: [
            parsed["evidence_type"]
            for parsed in (_parse_evidence_command(command) for command in commands)
            if parsed.get("evidence_type")
        ]
        for group, commands in planned_commands.items()
    }


def _record_group_evidence(*, group_name: str, commands: list[str], log_dir: Path) -> dict[str, list[Any]]:
    recorded_ids: list[str] = []
    rejected: list[dict[str, Any]] = []
    for command in commands:
        parsed = _parse_evidence_command(command)
        if not _parsed_command_complete(parsed):
            rejected.append(
                {
                    "group": group_name,
                    "evidence_type": parsed.get("evidence_type"),
                    "rejection_reason": "could not parse R115 evidence command",
                }
            )
            continue
        record = record_first_live_operator_evidence(
            evidence_type=parsed["evidence_type"],
            candidate_id=parsed["candidate_id"],
            risk_contract_hash=parsed["risk_contract_hash"],
            packet_hash=parsed["packet_hash"],
            note=parsed["note"],
            log_dir=log_dir,
            source="R116_ASSISTED_RUN",
        )
        if record.get("accepted") is True:
            recorded_ids.append(str(record.get("evidence_id")))
        else:
            rejected.append(
                {
                    "group": group_name,
                    "evidence_type": parsed["evidence_type"],
                    "rejection_reason": record.get("rejection_reason") or "evidence rejected by R112",
                }
            )
    return {"recorded_evidence_ids": recorded_ids, "rejected_evidence": rejected}


def _group_recheck_summary(*, candidate_id: str, group_name: str, log_dir: Path, env: Mapping[str, str] | None) -> dict[str, Any]:
    evidence_status = build_first_live_evidence_status(log_dir=log_dir)
    recheck = build_first_live_prerequisite_recheck_after_evidence(candidate_id=candidate_id, log_dir=log_dir, env=env, record=False)
    activation_gate = build_first_live_activation_gate(candidate_id=candidate_id, log_dir=log_dir, env=env, record=False)
    return _sanitize(
        {
            "group": group_name,
            "evidence_status": evidence_status.get("status"),
            "recheck_status": recheck.get("status"),
            "activation_gate_status": activation_gate.get("status"),
            "paper_live_separation_intact": _paper_live_separation_from_sources(evidence_status, recheck, activation_gate),
            "safety_field_violations": _safety_field_violations(evidence_status, recheck, activation_gate),
        }
    )


def _parse_evidence_command(command: str) -> dict[str, str | None]:
    parsed: dict[str, str | None] = {
        "evidence_type": None,
        "candidate_id": None,
        "risk_contract_hash": None,
        "packet_hash": None,
        "note": None,
    }
    try:
        parts = shlex.split(command)
    except ValueError:
        return parsed
    for index, part in enumerate(parts):
        if part in ("--evidence-type", "--candidate-id", "--risk-contract-hash", "--packet-hash", "--note") and index + 1 < len(parts):
            parsed[part.removeprefix("--").replace("-", "_")] = parts[index + 1]
    return parsed


def _parsed_command_complete(parsed: Mapping[str, Any]) -> bool:
    return all(str(parsed.get(key) or "").strip() for key in ("evidence_type", "candidate_id", "risk_contract_hash", "packet_hash"))


def _stop_conditions(
    *,
    selected_groups: list[str],
    group_errors: list[str],
    execute_evidence: bool,
    confirmation_valid: bool,
    runbook: Mapping[str, Any],
    before_status: Mapping[str, Any],
    active_tuple: Mapping[str, Any],
    planned_commands: Mapping[str, list[str]],
) -> list[str]:
    stops: list[str] = []
    stops.extend(group_errors)
    if not selected_groups:
        stops.append("no supported evidence group selected")
    if execute_evidence and not confirmation_valid:
        stops.append("missing or invalid evidence-only confirmation")
    if active_tuple.get("tuple_status") == "MISSING":
        stops.append("no active tuple")
    if active_tuple.get("tuple_status") == "INCONSISTENT":
        stops.append("active tuple is inconsistent")
    if runbook.get("status") != RUNBOOK_READY:
        stops.append("runbook reports unsafe state")
    if before_status.get("activation_gate_status") not in (FIRST_LIVE_BLOCKED, FIRST_LIVE_ACTIVATION_READY):
        stops.append("R106 status is unexpected or missing")
    if before_status.get("sacred_button_can_place_order") is True:
        stops.append("R109 sacred button can_place_order true")
    if before_status.get("paper_live_separation_intact") is False:
        stops.append("source reports paper_live_separation_intact false")
    if before_status.get("safety_field_violations"):
        stops.append("source safety field indicates execution/order/secrets")
    if _commands_contain_secret_risk(planned_commands):
        stops.append("evidence command or note contains secret-looking values")
    return list(dict.fromkeys(stops))


def _active_tuple(runbook: Mapping[str, Any]) -> dict[str, Any]:
    active_tuple = runbook.get("active_tuple") if isinstance(runbook.get("active_tuple"), Mapping) else {}
    return {
        "candidate_id": active_tuple.get("candidate_id"),
        "risk_contract_hash": active_tuple.get("risk_contract_hash"),
        "packet_hash": active_tuple.get("packet_hash"),
        "tuple_status": active_tuple.get("tuple_status") or "MISSING",
    }


def _recheck_commands(runbook: Mapping[str, Any]) -> list[str]:
    command_pack = runbook.get("command_pack") if isinstance(runbook.get("command_pack"), Mapping) else {}
    return [str(command) for command in command_pack.get("recheck_commands") or [] if command]


def _paper_live_separation_intact(before_status: Mapping[str, Any], runbook: Mapping[str, Any], after_status: Mapping[str, Any]) -> bool:
    values = [
        before_status.get("paper_live_separation_intact"),
        runbook.get("paper_live_separation_intact"),
        after_status.get("paper_live_separation_intact"),
    ]
    return all(value is not False for value in values)


def _paper_live_separation_from_sources(*payloads: Mapping[str, Any]) -> bool:
    return all(payload.get("paper_live_separation_intact") is not False for payload in payloads if isinstance(payload, Mapping))


def _sacred_button_can_place_order(cockpit: Mapping[str, Any]) -> bool:
    sacred_button = cockpit.get("sacred_button_state") if isinstance(cockpit.get("sacred_button_state"), Mapping) else {}
    backend_authority = cockpit.get("backend_authority") if isinstance(cockpit.get("backend_authority"), Mapping) else {}
    return sacred_button.get("can_place_order") is True or backend_authority.get("sacred_button_can_place_order") is True


def _cockpit_records_intent_only(cockpit: Mapping[str, Any]) -> bool:
    sacred_button = cockpit.get("sacred_button_state") if isinstance(cockpit.get("sacred_button_state"), Mapping) else {}
    return sacred_button.get("records_intent_only") is True


def _safety_field_violations(*payloads: Mapping[str, Any]) -> list[str]:
    violations: list[str] = []
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        for field in SAFETY_FALSE_FIELDS:
            if payload.get(field) is True:
                violations.append(field)
        for field in ("execution_enabled_by_evidence", "execution_enabled_by_recheck", "execution_enabled_by_gate", "execution_enabled_by_ui"):
            if payload.get(field) is True:
                violations.append(field)
    return list(dict.fromkeys(violations))


def _source_subset(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "status",
        "live_ready",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "real_order_possible",
        "secrets_shown",
        "paper_live_separation_intact",
    )
    return {key: payload.get(key) for key in keys if key in payload}


def _commands_contain_secret_risk(planned_commands: Mapping[str, list[str]]) -> bool:
    for commands in planned_commands.values():
        for command in commands:
            lowered = command.lower()
            if any(term in lowered for term in SECRET_RISK_TERMS):
                return True
    return False


def _unsafe_after_group(summary: Mapping[str, Any]) -> bool:
    return summary.get("paper_live_separation_intact") is False or bool(summary.get("safety_field_violations"))


def _rejection_reason(*, stop_conditions: list[str], rejected_evidence: list[Mapping[str, Any]]) -> str | None:
    if stop_conditions:
        return "; ".join(stop_conditions)
    if rejected_evidence:
        return "; ".join(str(item.get("rejection_reason") or "evidence rejected") for item in rejected_evidence)
    return None


def _source_surfaces(*, runbook: Mapping[str, Any]) -> list[str]:
    surfaces = [
        SOURCE_SURFACE,
        "R115 first-live-evidence-runbook",
        "R114 first-live-evidence-guided-actions",
        "R112 first-live-evidence-status",
        "R112 record-first-live-evidence",
        "R113 first-live-prerequisite-recheck-after-evidence",
        "R106 first-live-activation-gate",
        "R109 first-live cockpit sacred button state",
    ]
    surfaces.extend(str(item) for item in runbook.get("source_surfaces_used") or [])
    return list(dict.fromkeys(surfaces))


def _ledger_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize(
        {
            "event_type": EVENT_TYPE,
            "assisted_run_id": payload.get("assisted_run_id"),
            "recorded_at_utc": payload.get("recorded_at_utc"),
            "status": payload.get("status"),
            "selected_groups": payload.get("selected_groups"),
            "execute_evidence_requested": payload.get("execute_evidence_requested"),
            "confirmation_valid": payload.get("confirmation_valid"),
            "active_tuple": payload.get("active_tuple"),
            "planned_evidence_types": payload.get("planned_evidence_types"),
            "recorded_evidence_ids": payload.get("recorded_evidence_ids"),
            "rejected_evidence": payload.get("rejected_evidence"),
            "live_ready": False,
            "execution_enabled_by_assisted_run": False,
            "order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "source_surfaces_used": payload.get("source_surfaces_used"),
        }
    )


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
