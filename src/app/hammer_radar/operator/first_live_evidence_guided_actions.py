"""R114 first-live evidence-guided clearing actions.

This module generates copy-pasteable R112 evidence-recording commands for the
active first-live candidate/hash tuple. It is diagnostic only: it never enables
live execution, places orders, signs payloads, calls Binance endpoints, or
changes environment flags.
"""

from __future__ import annotations

import json
import shlex
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_activation_gate import (
    build_first_live_activation_gate,
    load_first_live_activation_gate_checks,
)
from src.app.hammer_radar.operator.first_live_operator_evidence import (
    REQUIRED_EVIDENCE_TYPES,
    build_first_live_evidence_status,
    load_first_live_operator_evidence,
)
from src.app.hammer_radar.operator.first_live_prerequisite_recheck_after_evidence import (
    GROUP_EVIDENCE_TYPES,
    build_first_live_prerequisite_recheck_after_evidence,
    load_first_live_prerequisite_rechecks,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

ACTIONS_READY = "ACTIONS_READY"
ACTIONS_BLOCKED_NO_ACTIVE_TUPLE = "ACTIONS_BLOCKED_NO_ACTIVE_TUPLE"
EVENT_TYPE = "FIRST_LIVE_EVIDENCE_GUIDED_ACTIONS"
LEDGER_FILENAME = "first_live_evidence_guided_actions.ndjson"
SOURCE_SURFACE = "operator.first_live_evidence_guided_actions.build_first_live_evidence_guided_actions"


GROUP_ORDER = [
    "approval_records",
    "account_funding",
    "protective_orders",
    "adapter_boundary",
    "risk_limits",
    "environment",
    "sacred_button",
    "emergency",
    "position_conflict",
]

EVIDENCE_GROUPS = {
    "APPROVAL_INTENT_REVIEWED": "approval_records",
    "HUMAN_REVIEW_R85": "approval_records",
    "HUMAN_REVIEW_R86": "approval_records",
    "HUMAN_REVIEW_R88": "approval_records",
    "ACCOUNT_FUNDING_READ_ONLY_CHECK": "account_funding",
    "PROTECTIVE_ORDERS_REVIEWED": "protective_orders",
    "LIVE_ADAPTER_BOUNDARY_REVIEWED": "adapter_boundary",
    "TINY_SIZE_MAX_LOSS_DEFINED": "risk_limits",
    "ENVIRONMENT_FLAGS_REVIEWED": "environment",
    "SACRED_BUTTON_INTENT_ONLY_VERIFIED": "sacred_button",
    "EMERGENCY_CANCEL_PATH_REVIEWED": "emergency",
    "NO_CONFLICTING_POSITION_REVIEWED": "position_conflict",
}

EVIDENCE_DETAILS = {
    "APPROVAL_INTENT_REVIEWED": {
        "purpose": "Record that the final approval-intent evidence was personally reviewed for the active tuple.",
        "note": "Reviewed approval intent record for this tuple; no key values recorded.",
        "expected_result": "R112 accepts APPROVAL_INTENT_REVIEWED for the same candidate and hashes.",
    },
    "HUMAN_REVIEW_R85": {
        "purpose": "Record that the R85 human review artifact was personally verified for the active tuple.",
        "note": "Reviewed R85 human review artifact for this tuple; no credential values recorded.",
        "expected_result": "R112 accepts HUMAN_REVIEW_R85 for the same candidate and hashes.",
    },
    "HUMAN_REVIEW_R86": {
        "purpose": "Record that the R86 human review artifact was personally verified for the active tuple.",
        "note": "Reviewed R86 human review artifact for this tuple; no credential values recorded.",
        "expected_result": "R112 accepts HUMAN_REVIEW_R86 for the same candidate and hashes.",
    },
    "HUMAN_REVIEW_R88": {
        "purpose": "Record that the R88 human review artifact was personally verified for the active tuple.",
        "note": "Reviewed R88 human review artifact for this tuple; no credential values recorded.",
        "expected_result": "R112 accepts HUMAN_REVIEW_R88 for the same candidate and hashes.",
    },
    "ACCOUNT_FUNDING_READ_ONLY_CHECK": {
        "purpose": "Record a read-only account/funding review without changing account settings or placing orders.",
        "note": "Reviewed funding readiness via read-only operator procedure; no order call made.",
        "expected_result": "R112 accepts ACCOUNT_FUNDING_READ_ONLY_CHECK for the same candidate and hashes.",
    },
    "PROTECTIVE_ORDERS_REVIEWED": {
        "purpose": "Record that protective stop and take-profit readiness was reviewed for the active tuple.",
        "note": "Reviewed protective stop and take-profit readiness for this tuple; no order created.",
        "expected_result": "R112 accepts PROTECTIVE_ORDERS_REVIEWED for the same candidate and hashes.",
    },
    "LIVE_ADAPTER_BOUNDARY_REVIEWED": {
        "purpose": "Record that the live adapter boundary was reviewed while paper/live separation stayed intact.",
        "note": "Reviewed adapter boundary and paper/live separation; no execution wiring changed.",
        "expected_result": "R112 accepts LIVE_ADAPTER_BOUNDARY_REVIEWED for the same candidate and hashes.",
    },
    "TINY_SIZE_MAX_LOSS_DEFINED": {
        "purpose": "Record that the tiny first-live size cap and maximum loss cap were defined.",
        "note": "Defined tiny size cap and max loss cap for this tuple; no trade instruction recorded.",
        "expected_result": "R112 accepts TINY_SIZE_MAX_LOSS_DEFINED for the same candidate and hashes.",
    },
    "ENVIRONMENT_FLAGS_REVIEWED": {
        "purpose": "Record that environment flag and kill-switch state were reviewed without editing flags.",
        "note": "Reviewed live flags and kill-switch state; no env values changed or printed.",
        "expected_result": "R112 accepts ENVIRONMENT_FLAGS_REVIEWED for the same candidate and hashes.",
    },
    "SACRED_BUTTON_INTENT_ONLY_VERIFIED": {
        "purpose": "Record that the R109 sacred button remains intent-only and cannot place orders.",
        "note": "Verified sacred button state is intent-only with can_place_order false.",
        "expected_result": "R112 accepts SACRED_BUTTON_INTENT_ONLY_VERIFIED for the same candidate and hashes.",
    },
    "EMERGENCY_CANCEL_PATH_REVIEWED": {
        "purpose": "Record that the emergency cancel/stop path was reviewed as an operator procedure.",
        "note": "Reviewed emergency cancel path for a later authorized phase; no service action performed.",
        "expected_result": "R112 accepts EMERGENCY_CANCEL_PATH_REVIEWED for the same candidate and hashes.",
    },
    "NO_CONFLICTING_POSITION_REVIEWED": {
        "purpose": "Record that conflicting-position status was reviewed through a safe operator procedure.",
        "note": "Reviewed conflicting-position status for this tuple; no account setting changed.",
        "expected_result": "R112 accepts NO_CONFLICTING_POSITION_REVIEWED for the same candidate and hashes.",
    },
}


def build_first_live_evidence_guided_actions(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    checked_at = datetime.now(UTC).isoformat()

    evidence_status = build_first_live_evidence_status(log_dir=resolved_log_dir)
    recheck = _latest_recheck(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env)
    activation_gate = _latest_activation_gate(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env)

    active_tuple = _active_tuple(
        recheck=recheck,
        evidence_status=evidence_status,
        activation_gate=activation_gate,
    )
    missing_evidence_types = _missing_evidence_types(
        active_tuple=active_tuple,
        recheck=recheck,
        evidence_status=evidence_status,
        log_dir=resolved_log_dir,
    )
    commands = _evidence_recording_commands(active_tuple=active_tuple, missing_evidence_types=missing_evidence_types)
    grouped_actions = _grouped_actions(commands)
    status = ACTIONS_READY if active_tuple["tuple_status"] == "PRESENT" else ACTIONS_BLOCKED_NO_ACTIVE_TUPLE
    local_safety = {
        "live_ready": False,
        "execution_enabled_by_guided_actions": False,
        "order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
    }
    paper_live_separation_intact, warnings = derive_paper_live_separation_intact(
        source_payloads={
            "R112 evidence status": evidence_status,
            "R113 recheck": recheck,
            "R106 activation gate": activation_gate,
        },
        local_safety=local_safety,
    )

    payload = {
        "event_type": EVENT_TYPE,
        "action_pack_id": uuid4().hex,
        "recorded_at_utc": checked_at,
        "status": status,
        "checked_at_utc": checked_at,
        "live_ready": local_safety["live_ready"],
        "execution_enabled_by_guided_actions": local_safety["execution_enabled_by_guided_actions"],
        "order_placed": local_safety["order_placed"],
        "real_order_placed": False,
        "execution_attempted": local_safety["execution_attempted"],
        "real_order_possible": local_safety["real_order_possible"],
        "secrets_shown": local_safety["secrets_shown"],
        "active_tuple": active_tuple,
        "source_statuses": _source_statuses(
            evidence_status=evidence_status,
            recheck=recheck,
            activation_gate=activation_gate,
        ),
        "missing_evidence_types": missing_evidence_types,
        "evidence_recording_commands": commands if status == ACTIONS_READY else [],
        "recheck_commands": _recheck_commands(),
        "recommended_sequence": _recommended_sequence(),
        "grouped_actions": grouped_actions if status == ACTIONS_READY else {group: [] for group in GROUP_ORDER},
        "safety_summary": {
            "evidence recording does not place orders": True,
            "evidence recording does not enable live execution": True,
            "R106 remains authority": True,
            "R109 sacred button remains intent-only": True,
            "no secret values should be pasted into notes": True,
        },
        "ledger_path": str(first_live_evidence_guided_actions_path(resolved_log_dir)),
        "source_surfaces_used": _source_surfaces(recheck=recheck),
        "paper_live_separation_intact": paper_live_separation_intact,
        "warnings": warnings,
    }
    payload = _sanitize(payload)
    if record:
        append_first_live_evidence_guided_actions(payload, log_dir=resolved_log_dir)
    return payload


def append_first_live_evidence_guided_actions(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_evidence_guided_actions_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_ledger_record(record), sort_keys=True) + "\n")


def load_first_live_evidence_guided_actions(
    *,
    limit: int = 50,
    action_pack_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_evidence_guided_actions_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if action_pack_id is not None and record.get("action_pack_id") != action_pack_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_evidence_guided_actions_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_first_live_evidence_guided_actions_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def derive_paper_live_separation_intact(
    *,
    source_payloads: Mapping[str, Mapping[str, Any]],
    local_safety: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    false_sources: list[str] = []
    true_sources: list[str] = []
    for source_name, payload in source_payloads.items():
        if not isinstance(payload, Mapping) or "paper_live_separation_intact" not in payload:
            continue
        value = payload.get("paper_live_separation_intact")
        if value is False:
            false_sources.append(str(source_name))
        elif value is True:
            true_sources.append(str(source_name))

    if false_sources:
        sources = ", ".join(false_sources)
        return False, [f"paper_live_separation_intact explicitly false from source(s): {sources}"]
    if true_sources:
        return True, []

    required_false_fields = (
        "live_ready",
        "execution_enabled_by_guided_actions",
        "order_placed",
        "execution_attempted",
        "real_order_possible",
        "secrets_shown",
    )
    unsafe_fields = [field for field in required_false_fields if local_safety.get(field) is not False]
    if unsafe_fields:
        return False, [
            "paper_live_separation_intact unknown because R114 local safety fields are not all false: "
            + ", ".join(unsafe_fields)
        ]
    return True, []


def _latest_recheck(
    *,
    candidate_id: str,
    log_dir: str | Path,
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    records = load_first_live_prerequisite_rechecks(limit=1, log_dir=log_dir)
    if records:
        return records[0]
    return build_first_live_prerequisite_recheck_after_evidence(
        candidate_id=candidate_id,
        log_dir=log_dir,
        env=env,
        record=False,
    )


def _latest_activation_gate(
    *,
    candidate_id: str,
    log_dir: str | Path,
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    records = load_first_live_activation_gate_checks(limit=1, log_dir=log_dir)
    if records:
        return records[0]
    return build_first_live_activation_gate(
        candidate_id=candidate_id,
        log_dir=log_dir,
        env=env,
        record=False,
    )


def _active_tuple(
    *,
    recheck: Mapping[str, Any],
    evidence_status: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
) -> dict[str, str | None]:
    candidates: list[tuple[str, dict[str, str]]] = []
    for source, surface in (
        ("R113 recheck_tuple", recheck.get("recheck_tuple")),
        ("R112 ready_tuple", evidence_status.get("ready_tuple")),
        ("R106 activation gate", activation_gate),
    ):
        tuple_payload = _tuple_from_surface(surface)
        if tuple_payload is not None:
            candidates.append((source, tuple_payload))

    if not candidates:
        return {
            "candidate_id": None,
            "risk_contract_hash": None,
            "packet_hash": None,
            "source": None,
            "tuple_status": "MISSING",
        }
    first_source, first_tuple = candidates[0]
    if any(item != first_tuple for _, item in candidates[1:]):
        return {
            **first_tuple,
            "source": first_source,
            "tuple_status": "INCONSISTENT",
        }
    return {
        **first_tuple,
        "source": first_source,
        "tuple_status": "PRESENT",
    }


def _tuple_from_surface(surface: Any) -> dict[str, str] | None:
    if not isinstance(surface, Mapping):
        return None
    candidate_id = str(surface.get("candidate_id") or "").strip()
    risk_contract_hash = str(surface.get("risk_contract_hash") or "").strip()
    packet_hash = str(surface.get("packet_hash") or surface.get("final_review_packet_hash") or "").strip()
    if not candidate_id or not risk_contract_hash or not packet_hash:
        return None
    return {
        "candidate_id": candidate_id,
        "risk_contract_hash": risk_contract_hash,
        "packet_hash": packet_hash,
    }


def _missing_evidence_types(
    *,
    active_tuple: Mapping[str, Any],
    recheck: Mapping[str, Any],
    evidence_status: Mapping[str, Any],
    log_dir: str | Path,
) -> list[str]:
    status = str(active_tuple.get("tuple_status") or "")
    if status != "PRESENT":
        return list(REQUIRED_EVIDENCE_TYPES)
    tuple_key = (
        str(active_tuple.get("candidate_id") or ""),
        str(active_tuple.get("risk_contract_hash") or ""),
        str(active_tuple.get("packet_hash") or ""),
    )
    present = _accepted_evidence_types_for_tuple(tuple_key=tuple_key, log_dir=log_dir)
    r112_missing = set(str(item) for item in evidence_status.get("evidence_types_missing") or [])
    r113_missing = set(_r113_missing_evidence_types(recheck))
    missing = (set(REQUIRED_EVIDENCE_TYPES) - present) | r112_missing | r113_missing
    return [item for item in REQUIRED_EVIDENCE_TYPES if item in missing]


def _accepted_evidence_types_for_tuple(*, tuple_key: tuple[str, str, str], log_dir: str | Path) -> set[str]:
    present: set[str] = set()
    for record in load_first_live_operator_evidence(limit=0, log_dir=log_dir):
        if record.get("accepted") is not True:
            continue
        record_tuple = (
            str(record.get("candidate_id") or "").strip(),
            str(record.get("risk_contract_hash") or "").strip(),
            str(record.get("packet_hash") or "").strip(),
        )
        evidence_type = str(record.get("evidence_type") or "").strip()
        if record_tuple == tuple_key and evidence_type in REQUIRED_EVIDENCE_TYPES:
            present.add(evidence_type)
    return present


def _r113_missing_evidence_types(recheck: Mapping[str, Any]) -> set[str]:
    missing: set[str] = set()
    for item in recheck.get("blocker_recheck") or []:
        if not isinstance(item, Mapping):
            continue
        if item.get("rechecked_status") != "NEEDS_MORE_EVIDENCE":
            continue
        group = str(item.get("group") or "")
        missing.update(GROUP_EVIDENCE_TYPES.get(group, ()))
        missing.update(str(evidence_type) for evidence_type in item.get("evidence_types_used") or [])
    return {item for item in missing if item in REQUIRED_EVIDENCE_TYPES}


def _evidence_recording_commands(
    *,
    active_tuple: Mapping[str, Any],
    missing_evidence_types: list[str],
) -> list[dict[str, str]]:
    if active_tuple.get("tuple_status") != "PRESENT":
        return []
    commands = []
    for evidence_type in missing_evidence_types:
        details = EVIDENCE_DETAILS[evidence_type]
        note = details["note"]
        commands.append(
            {
                "evidence_type": evidence_type,
                "purpose": details["purpose"],
                "command": _record_command(
                    evidence_type=evidence_type,
                    candidate_id=str(active_tuple["candidate_id"]),
                    risk_contract_hash=str(active_tuple["risk_contract_hash"]),
                    packet_hash=str(active_tuple["packet_hash"]),
                    note=note,
                ),
                "safety_note": "This records operator evidence only; it does not place orders or enable live execution.",
                "expected_result": details["expected_result"],
            }
        )
    return commands


def _record_command(
    *,
    evidence_type: str,
    candidate_id: str,
    risk_contract_hash: str,
    packet_hash: str,
    note: str,
) -> str:
    parts = [
        "PYTHONPATH=.",
        ".venv/bin/python",
        "-m",
        "src.app.hammer_radar.operator.inspect",
        "--log-dir",
        "logs/hammer_radar_forward",
        "record-first-live-evidence",
        "--evidence-type",
        evidence_type,
        "--candidate-id",
        candidate_id,
        "--risk-contract-hash",
        risk_contract_hash,
        "--packet-hash",
        packet_hash,
        "--note",
        note,
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _recheck_commands() -> list[str]:
    return [
        _cmd("first-live-evidence-status"),
        _cmd("first-live-prerequisite-recheck-after-evidence"),
        _cmd("first-live-prerequisite-clearing"),
        _cmd("first-live-burn-down"),
        _cmd("first-live-activation-gate"),
        "curl -s http://127.0.0.1:8015/operator/approval-cockpit/state",
    ]


def _recommended_sequence() -> list[str]:
    return [
        "Verify active tuple",
        "Record only evidence you personally verified",
        "Do not paste secrets in notes",
        "Run evidence status",
        "Run R113 recheck",
        "Run R111 prerequisite clearing",
        "Run R106 activation gate",
        "Keep sacred button intent-only",
        "Stop if any blocker remains",
    ]


def _grouped_actions(commands: list[Mapping[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for group in GROUP_ORDER:
        grouped[group] = []
    for command in commands:
        group = EVIDENCE_GROUPS.get(str(command.get("evidence_type")), "approval_records")
        grouped[group].append(dict(command))
    return dict(grouped)


def _cmd(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


def _source_statuses(
    *,
    evidence_status: Mapping[str, Any],
    recheck: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
) -> dict[str, Any]:
    recheck_source_statuses = recheck.get("source_statuses") if isinstance(recheck.get("source_statuses"), Mapping) else {}
    return {
        "R112 evidence status": evidence_status.get("status"),
        "R113 recheck status": recheck.get("status"),
        "R111 prerequisite clearing status": recheck_source_statuses.get("R111 prerequisite clearing"),
        "R110 burn-down status": recheck_source_statuses.get("R110 burn-down"),
        "R106 activation gate status": activation_gate.get("status") or recheck_source_statuses.get("R106 activation gate"),
        "R109 cockpit status": recheck_source_statuses.get("R109 cockpit"),
    }


def _source_surfaces(*, recheck: Mapping[str, Any]) -> list[str]:
    surfaces = [
        SOURCE_SURFACE,
        "R112 first-live-evidence-status",
        "R113 first-live-prerequisite-recheck-after-evidence",
        "R111 first-live-prerequisite-clearing",
        "R110 first-live-burn-down",
        "R106 first-live-activation-gate",
        "R109 first-live cockpit sacred button state",
    ]
    surfaces.extend(str(item) for item in recheck.get("source_surfaces_used") or [])
    return list(dict.fromkeys(surfaces))


def _ledger_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "event_type",
        "action_pack_id",
        "recorded_at_utc",
        "status",
        "active_tuple",
        "missing_evidence_types",
        "grouped_actions",
        "live_ready",
        "execution_enabled_by_guided_actions",
        "order_placed",
        "execution_attempted",
        "real_order_possible",
        "secrets_shown",
        "source_surfaces_used",
    ]
    record = {key: payload.get(key) for key in keys}
    record["evidence_recording_commands_count"] = len(payload.get("evidence_recording_commands") or [])
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
