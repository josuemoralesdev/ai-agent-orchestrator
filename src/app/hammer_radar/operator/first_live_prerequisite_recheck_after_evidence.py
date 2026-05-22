"""R113 first-live prerequisite recheck after operator evidence.

This module composes R110/R111/R112 with R106 and R109 to show whether
operator evidence reduces prerequisite blockers. It is diagnostic only: it
never enables live execution, places orders, signs payloads, calls Binance
order endpoints, or changes environment flags.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_operator_evidence import (
    build_first_live_evidence_status,
    load_first_live_operator_evidence,
)
from src.app.hammer_radar.operator.first_live_prerequisite_clearing import (
    GROUP_ORDER,
    build_first_live_prerequisite_clearing,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

RECHECK_BLOCKED = "RECHECK_BLOCKED"
RECHECK_PARTIAL = "RECHECK_PARTIAL"
RECHECK_READY_FOR_R106 = "RECHECK_READY_FOR_R106"
EVENT_TYPE = "FIRST_LIVE_PREREQUISITE_RECHECK_AFTER_EVIDENCE"
LEDGER_FILENAME = "first_live_prerequisite_rechecks.ndjson"
SOURCE_SURFACE = "operator.first_live_prerequisite_recheck_after_evidence.build_first_live_prerequisite_recheck_after_evidence"


def _cmd(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


GROUP_EVIDENCE_TYPES: dict[str, tuple[str, ...]] = {
    "candidate_freshness": (),
    "approval_records": (
        "APPROVAL_INTENT_REVIEWED",
        "HUMAN_REVIEW_R85",
        "HUMAN_REVIEW_R86",
        "HUMAN_REVIEW_R88",
    ),
    "binance_credentials_presence": (),
    "account_funding_read_only_check": (
        "ACCOUNT_FUNDING_READ_ONLY_CHECK",
        "NO_CONFLICTING_POSITION_REVIEWED",
    ),
    "protective_orders_readiness": ("PROTECTIVE_ORDERS_REVIEWED",),
    "live_adapter_boundary": ("LIVE_ADAPTER_BOUNDARY_REVIEWED",),
    "tiny_position_size_cap": ("TINY_SIZE_MAX_LOSS_DEFINED",),
    "max_loss_cap": ("TINY_SIZE_MAX_LOSS_DEFINED",),
    "environment_flag_review": ("ENVIRONMENT_FLAGS_REVIEWED",),
    "confirmation_phrase_preparation": (),
    "sacred_button_safety": ("SACRED_BUTTON_INTENT_ONLY_VERIFIED",),
    "duplicate_source_conflicts": (),
}


def build_first_live_prerequisite_recheck_after_evidence(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    checked_at = datetime.now(UTC).isoformat()

    prerequisite_clearing = build_first_live_prerequisite_clearing(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, record=False)
    evidence_status = _evidence_status_subset(build_first_live_evidence_status(log_dir=resolved_log_dir))
    accepted_types = _accepted_evidence_types_by_tuple(log_dir=resolved_log_dir)
    recheck_tuple = _recheck_tuple(evidence_status=evidence_status, accepted_types=accepted_types)
    evidence_types_for_recheck = set(accepted_types.get(recheck_tuple, set())) if recheck_tuple is not None else set()

    blocker_recheck = _blocker_recheck(
        prerequisite_clearing=prerequisite_clearing,
        evidence_types_for_recheck=evidence_types_for_recheck,
        evidence_status=evidence_status,
    )
    groups_by_status = _groups_by_status(blocker_recheck)
    activation_distance = _activation_distance(
        prerequisite_clearing=prerequisite_clearing,
        blocker_recheck=blocker_recheck,
        evidence_status=evidence_status,
    )
    status = _status(groups_by_status=groups_by_status)
    source_statuses = _source_statuses(
        prerequisite_clearing=prerequisite_clearing,
        evidence_status=evidence_status,
    )
    payload = {
        "event_type": EVENT_TYPE,
        "recheck_id": uuid4().hex,
        "recorded_at_utc": checked_at,
        "checked_at_utc": checked_at,
        "status": status,
        "live_ready": False,
        "execution_enabled_by_recheck": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "candidate_id": candidate_id,
        "recheck_tuple": _tuple_payload(recheck_tuple),
        "source_statuses": source_statuses,
        "evidence_status": evidence_status,
        "blocker_recheck": blocker_recheck,
        "cleared_groups": groups_by_status["cleared_groups"],
        "still_blocked_groups": groups_by_status["still_blocked_groups"],
        "evidence_needed_groups": groups_by_status["evidence_needed_groups"],
        "unknown_groups": groups_by_status["unknown_groups"],
        "activation_distance": activation_distance,
        "operator_next_actions": _operator_next_actions(blocker_recheck),
        "r106_recheck_command": _cmd("first-live-activation-gate"),
        "r111_recheck_command": _cmd("first-live-prerequisite-clearing"),
        "r112_status_command": _cmd("first-live-evidence-status"),
        "cockpit_state_command": "curl -s http://127.0.0.1:8015/operator/approval-cockpit/state",
        "sacred_button_can_place_order": False,
        "cockpit_records_intent_only": True,
        "r106_remains_authority": True,
        "ledger_path": str(first_live_prerequisite_rechecks_path(resolved_log_dir)),
        "source_surfaces_used": _source_surfaces(
            prerequisite_clearing=prerequisite_clearing,
        ),
        "paper_live_separation_intact": bool(
            prerequisite_clearing.get("paper_live_separation_intact")
        ),
    }
    payload = _sanitize(payload)
    if record:
        append_first_live_prerequisite_recheck(payload, log_dir=resolved_log_dir)
    return payload


def append_first_live_prerequisite_recheck(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_prerequisite_rechecks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_ledger_record(record), sort_keys=True) + "\n")


def load_first_live_prerequisite_rechecks(
    *,
    limit: int = 50,
    recheck_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_prerequisite_rechecks_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if recheck_id is not None and record.get("recheck_id") != recheck_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_prerequisite_rechecks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_first_live_prerequisite_recheck_after_evidence_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _evidence_status_subset(status: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "status",
        "records_count",
        "accepted_records_count",
        "rejected_records_count",
        "evidence_types_present",
        "evidence_types_missing",
        "ready_tuple",
    ]
    return {key: status.get(key) for key in keys}


def _accepted_evidence_types_by_tuple(*, log_dir: str | Path) -> dict[tuple[str, str, str], set[str]]:
    by_tuple: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for record in load_first_live_operator_evidence(limit=0, log_dir=log_dir):
        if record.get("accepted") is not True:
            continue
        tuple_key = (
            str(record.get("candidate_id") or "").strip(),
            str(record.get("risk_contract_hash") or "").strip(),
            str(record.get("packet_hash") or "").strip(),
        )
        evidence_type = str(record.get("evidence_type") or "").strip()
        if all(tuple_key) and evidence_type:
            by_tuple[tuple_key].add(evidence_type)
    return dict(by_tuple)


def _recheck_tuple(
    *,
    evidence_status: Mapping[str, Any],
    accepted_types: Mapping[tuple[str, str, str], set[str]],
) -> tuple[str, str, str] | None:
    ready_tuple = evidence_status.get("ready_tuple") if isinstance(evidence_status.get("ready_tuple"), dict) else None
    if ready_tuple:
        tuple_key = (
            str(ready_tuple.get("candidate_id") or "").strip(),
            str(ready_tuple.get("risk_contract_hash") or "").strip(),
            str(ready_tuple.get("packet_hash") or "").strip(),
        )
        if all(tuple_key):
            return tuple_key
    if not accepted_types:
        return None
    return max(accepted_types, key=lambda tuple_key: (len(accepted_types[tuple_key]), tuple_key))


def _blocker_recheck(
    *,
    prerequisite_clearing: Mapping[str, Any],
    evidence_types_for_recheck: set[str],
    evidence_status: Mapping[str, Any],
) -> list[dict[str, Any]]:
    prerequisite_groups = prerequisite_clearing.get("prerequisite_groups") if isinstance(prerequisite_clearing.get("prerequisite_groups"), dict) else {}
    results = []
    for group_name in GROUP_ORDER:
        previous = prerequisite_groups.get(group_name) if isinstance(prerequisite_groups.get(group_name), dict) else {}
        previous_status = str(previous.get("status") or "UNKNOWN")
        evidence_types_used = list(GROUP_EVIDENCE_TYPES[group_name])
        evidence_present = bool(evidence_types_used) and set(evidence_types_used).issubset(evidence_types_for_recheck)
        if group_name == "sacred_button_safety":
            evidence_present = evidence_present or _sacred_button_safe(previous)
        rechecked_status = _rechecked_status(
            group=group_name,
            previous_status=previous_status,
            evidence_present=evidence_present,
            evidence_types_used=evidence_types_used,
            previous=previous,
        )
        blockers_remaining = _blockers_remaining(
            group=group_name,
            previous=previous,
            rechecked_status=rechecked_status,
        )
        results.append(
            {
                "group": group_name,
                "previous_status": previous_status,
                "evidence_present": evidence_present,
                "evidence_types_used": evidence_types_used,
                "rechecked_status": rechecked_status,
                "blockers_remaining": blockers_remaining,
                "next_action": _next_action(
                    group=group_name,
                    previous=previous,
                    rechecked_status=rechecked_status,
                    evidence_status=evidence_status,
                ),
                "verification_command": previous.get("verification_command") or _cmd("first-live-prerequisite-clearing"),
            }
        )
    return results


def _rechecked_status(
    *,
    group: str,
    previous_status: str,
    evidence_present: bool,
    evidence_types_used: list[str],
    previous: Mapping[str, Any],
) -> str:
    if group == "sacred_button_safety":
        return "CLEAR" if _sacred_button_safe(previous) else "STILL_BLOCKED"
    if previous_status == "CLEAR":
        return "CLEAR"
    if evidence_present:
        return "CLEAR"
    if evidence_types_used or previous_status == "NEEDS_OPERATOR_EVIDENCE":
        return "NEEDS_MORE_EVIDENCE"
    if previous_status == "UNKNOWN":
        return "UNKNOWN"
    return "STILL_BLOCKED"


def _blockers_remaining(*, group: str, previous: Mapping[str, Any], rechecked_status: str) -> list[str]:
    if rechecked_status == "CLEAR":
        return []
    evidence_present = previous.get("evidence_present") if isinstance(previous.get("evidence_present"), dict) else {}
    blockers = [str(item) for item in evidence_present.get("blockers") or []]
    if blockers:
        return blockers
    if rechecked_status == "NEEDS_MORE_EVIDENCE":
        return [f"{group} evidence incomplete or not available for the recheck tuple"]
    if rechecked_status == "UNKNOWN":
        return [f"{group} source status is unknown"]
    return [str(previous.get("evidence_required") or f"{group} remains blocked")]


def _next_action(
    *,
    group: str,
    previous: Mapping[str, Any],
    rechecked_status: str,
    evidence_status: Mapping[str, Any],
) -> str:
    if rechecked_status == "CLEAR":
        return "No R113 action; preserve evidence and continue the non-executing R106 recheck sequence."
    if rechecked_status == "NEEDS_MORE_EVIDENCE":
        required = ", ".join(GROUP_EVIDENCE_TYPES[group]) or "operator evidence not represented by R112 yet"
        return f"Record or complete R112 evidence for {group}: {required}; current evidence status is {evidence_status.get('status')}."
    return str(previous.get("next_action") or "Resolve this blocker before treating prerequisites as reduced.")


def _sacred_button_safe(previous: Mapping[str, Any]) -> bool:
    evidence_present = previous.get("evidence_present") if isinstance(previous.get("evidence_present"), dict) else {}
    return evidence_present.get("can_place_order") is False and evidence_present.get("records_intent_only") is True


def _groups_by_status(blocker_recheck: list[Mapping[str, Any]]) -> dict[str, list[str]]:
    return {
        "cleared_groups": [str(item["group"]) for item in blocker_recheck if item.get("rechecked_status") == "CLEAR"],
        "still_blocked_groups": [str(item["group"]) for item in blocker_recheck if item.get("rechecked_status") == "STILL_BLOCKED"],
        "evidence_needed_groups": [str(item["group"]) for item in blocker_recheck if item.get("rechecked_status") == "NEEDS_MORE_EVIDENCE"],
        "unknown_groups": [str(item["group"]) for item in blocker_recheck if item.get("rechecked_status") == "UNKNOWN"],
    }


def _status(*, groups_by_status: Mapping[str, list[str]]) -> str:
    if not groups_by_status["still_blocked_groups"] and not groups_by_status["evidence_needed_groups"] and not groups_by_status["unknown_groups"]:
        return RECHECK_READY_FOR_R106
    if groups_by_status["cleared_groups"]:
        return RECHECK_PARTIAL
    return RECHECK_BLOCKED


def _activation_distance(
    *,
    prerequisite_clearing: Mapping[str, Any],
    blocker_recheck: list[Mapping[str, Any]],
    evidence_status: Mapping[str, Any],
) -> dict[str, Any]:
    remaining = [
        item
        for item in blocker_recheck
        if item.get("rechecked_status") in {"STILL_BLOCKED", "NEEDS_MORE_EVIDENCE", "UNKNOWN"}
    ]
    high_priority = next((item for item in remaining if item.get("rechecked_status") == "STILL_BLOCKED"), None) or (remaining[0] if remaining else None)
    source_statuses = prerequisite_clearing.get("source_statuses") if isinstance(prerequisite_clearing.get("source_statuses"), dict) else {}
    return {
        "r106_current_status": source_statuses.get("R106 activation gate"),
        "blockers_remaining_count": len(remaining),
        "evidence_missing_count": len(evidence_status.get("evidence_types_missing") or []),
        "high_priority_next_blocker": (high_priority or {}).get("group"),
        "next_phase_needed": "R114 evidence-guided clearing actions" if remaining else "R106 activation gate recheck",
    }


def _operator_next_actions(blocker_recheck: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    priority = {"STILL_BLOCKED": 0, "NEEDS_MORE_EVIDENCE": 1, "UNKNOWN": 2, "CLEAR": 3}
    actions = [
        {
            "priority": 0,
            "group": item.get("group"),
            "status": item.get("rechecked_status"),
            "action": item.get("next_action"),
            "verification_command": item.get("verification_command"),
        }
        for item in blocker_recheck
        if item.get("rechecked_status") != "CLEAR"
    ]
    actions.sort(key=lambda item: (priority.get(str(item["status"]), 9), GROUP_ORDER.index(str(item["group"]))))
    for index, item in enumerate(actions, start=1):
        item["priority"] = index
    if actions:
        return actions
    return [
        {
            "priority": 1,
            "group": "r106_recheck",
            "status": "READY_FOR_R106_RECHECK",
            "action": "Run R106 first-live-activation-gate; R113 still does not authorize execution.",
            "verification_command": _cmd("first-live-activation-gate"),
        }
    ]


def _source_statuses(
    *,
    prerequisite_clearing: Mapping[str, Any],
    evidence_status: Mapping[str, Any],
) -> dict[str, Any]:
    statuses = prerequisite_clearing.get("source_statuses") if isinstance(prerequisite_clearing.get("source_statuses"), dict) else {}
    return {
        "R106 activation gate": statuses.get("R106 activation gate"),
        "R109 cockpit": statuses.get("R109 cockpit"),
        "R110 burn-down": statuses.get("R110 burn-down"),
        "R111 prerequisite clearing": prerequisite_clearing.get("status"),
        "R112 evidence status": evidence_status.get("status"),
    }


def _source_surfaces(
    *,
    prerequisite_clearing: Mapping[str, Any],
) -> list[str]:
    surfaces = [
        SOURCE_SURFACE,
        "R106 first-live-activation-gate",
        "R109 first-live cockpit sacred button state",
        "R110 first-live-burn-down",
        "R111 first-live-prerequisite-clearing",
        "R112 first-live-evidence-status",
    ]
    surfaces.extend(str(item) for item in prerequisite_clearing.get("source_surfaces_used") or [])
    return list(dict.fromkeys(surfaces))


def _tuple_payload(tuple_key: tuple[str, str, str] | None) -> dict[str, str] | None:
    if tuple_key is None:
        return None
    candidate_id, risk_contract_hash, packet_hash = tuple_key
    return {
        "candidate_id": candidate_id,
        "risk_contract_hash": risk_contract_hash,
        "packet_hash": packet_hash,
    }


def _ledger_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "event_type",
        "recheck_id",
        "recorded_at_utc",
        "status",
        "source_statuses",
        "evidence_status",
        "blocker_recheck",
        "activation_distance",
        "live_ready",
        "execution_enabled_by_recheck",
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
        secret_tokens = ("api_secret", "api key", "telegram_bot_token", "secret-api", "secret-telegram", "auth header")
        if any(token in rendered.lower() for token in secret_tokens):
            payload["secrets_shown"] = False
        return payload
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
