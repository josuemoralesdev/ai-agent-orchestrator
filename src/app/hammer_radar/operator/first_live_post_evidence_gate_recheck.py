"""R117 first-live post-evidence gate recheck.

This module composes R112/R113/R116/R111/R110/R106/R109 status surfaces after
operator evidence has been recorded. It is decision support only: it never
enables live execution, places orders, signs payloads, calls Binance endpoints,
or changes environment flags.
"""

from __future__ import annotations

import json
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
    load_first_live_activation_gate_checks,
)
from src.app.hammer_radar.operator.first_live_burn_down import build_first_live_burn_down
from src.app.hammer_radar.operator.first_live_evidence_assisted_run import (
    load_first_live_evidence_assisted_runs,
)
from src.app.hammer_radar.operator.first_live_operator_approval_cockpit import (
    build_operator_approval_cockpit_state,
)
from src.app.hammer_radar.operator.first_live_operator_evidence import (
    EVIDENCE_READY_FOR_PREREQ_RECHECK,
    build_first_live_evidence_status,
)
from src.app.hammer_radar.operator.first_live_prerequisite_clearing import (
    GROUP_ORDER,
    build_first_live_prerequisite_clearing,
)
from src.app.hammer_radar.operator.first_live_prerequisite_recheck_after_evidence import (
    GROUP_EVIDENCE_TYPES,
    RECHECK_READY_FOR_R106,
    build_first_live_prerequisite_recheck_after_evidence,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

POST_EVIDENCE_BLOCKED = "POST_EVIDENCE_BLOCKED"
POST_EVIDENCE_PARTIAL = "POST_EVIDENCE_PARTIAL"
POST_EVIDENCE_READY_FOR_ACTIVATION_GATE_RECHECK = "POST_EVIDENCE_READY_FOR_ACTIVATION_GATE_RECHECK"
EVENT_TYPE = "FIRST_LIVE_POST_EVIDENCE_GATE_RECHECK"
LEDGER_FILENAME = "first_live_post_evidence_gate_rechecks.ndjson"
SOURCE_SURFACE = "operator.first_live_post_evidence_gate_recheck.build_first_live_post_evidence_gate_recheck"


def _cmd(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


def build_first_live_post_evidence_gate_recheck(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    checked_at = datetime.now(UTC).isoformat()

    evidence_status = build_first_live_evidence_status(log_dir=resolved_log_dir)
    prerequisite_recheck = build_first_live_prerequisite_recheck_after_evidence(
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
        record=False,
    )
    assisted_run = _latest_assisted_run(log_dir=resolved_log_dir)
    prerequisite_clearing = build_first_live_prerequisite_clearing(
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
        record=False,
    )
    burn_down = build_first_live_burn_down(
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
        record=False,
    )
    activation_gate = _latest_activation_gate(
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
    )
    cockpit = _cockpit_from_burn_down(
        burn_down=burn_down,
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
    )

    active_tuple = _active_tuple(
        evidence_status=evidence_status,
        prerequisite_recheck=prerequisite_recheck,
        activation_gate=activation_gate,
        cockpit=cockpit,
    )
    evidence_summary = _evidence_summary(
        evidence_status=evidence_status,
        active_tuple=active_tuple,
    )
    blocker_map = _blocker_map(
        prerequisite_recheck=prerequisite_recheck,
        evidence_status=evidence_status,
    )
    source_statuses = _source_statuses(
        evidence_status=evidence_status,
        prerequisite_recheck=prerequisite_recheck,
        assisted_run=assisted_run,
        prerequisite_clearing=prerequisite_clearing,
        burn_down=burn_down,
        activation_gate=activation_gate,
        cockpit=cockpit,
    )
    gate_delta = _gate_delta(
        evidence_summary=evidence_summary,
        prerequisite_recheck=prerequisite_recheck,
        activation_gate=activation_gate,
        blocker_map=blocker_map,
    )
    activation_readiness_summary = _activation_readiness_summary(
        activation_gate=activation_gate,
        cockpit=cockpit,
        gate_delta=gate_delta,
    )
    status = _status(
        evidence_status=evidence_status,
        evidence_summary=evidence_summary,
        gate_delta=gate_delta,
        activation_readiness_summary=activation_readiness_summary,
        activation_gate=activation_gate,
    )
    payload = {
        "event_type": EVENT_TYPE,
        "post_evidence_recheck_id": uuid4().hex,
        "recorded_at_utc": checked_at,
        "checked_at_utc": checked_at,
        "status": status,
        "live_ready": False,
        "execution_enabled_by_post_evidence_recheck": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "active_tuple": active_tuple,
        "source_statuses": source_statuses,
        "evidence_summary": evidence_summary,
        "gate_delta": gate_delta,
        "blocker_map": blocker_map,
        "activation_readiness_summary": activation_readiness_summary,
        "next_operator_actions": _next_operator_actions(
            status=status,
            blocker_map=blocker_map,
            activation_readiness_summary=activation_readiness_summary,
        ),
        "final_recheck_command_pack": _final_recheck_command_pack(),
        "safety_summary": {
            "R106 remains authority": True,
            "R109 sacred button remains intent-only": True,
            "no order was placed": True,
            "live execution remains disabled by this phase": True,
            "evidence does not equal execution authorization": True,
            "no secret values shown": True,
        },
        "source_surfaces_used": _source_surfaces(
            prerequisite_recheck=prerequisite_recheck,
            burn_down=burn_down,
            activation_gate=activation_gate,
            cockpit=cockpit,
            assisted_run=assisted_run,
        ),
        "ledger_path": str(first_live_post_evidence_gate_rechecks_path(resolved_log_dir)),
        "paper_live_separation_intact": activation_readiness_summary["paper_live_separation_intact"],
    }
    payload = _sanitize(payload)
    if record:
        append_first_live_post_evidence_gate_recheck(payload, log_dir=resolved_log_dir)
    return payload


def append_first_live_post_evidence_gate_recheck(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_post_evidence_gate_rechecks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_ledger_record(record), sort_keys=True) + "\n")


def load_first_live_post_evidence_gate_rechecks(
    *,
    limit: int = 50,
    post_evidence_recheck_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_post_evidence_gate_rechecks_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if post_evidence_recheck_id is not None and record.get("post_evidence_recheck_id") != post_evidence_recheck_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_post_evidence_gate_rechecks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_first_live_post_evidence_gate_recheck_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _latest_assisted_run(*, log_dir: str | Path) -> dict[str, Any] | None:
    records = load_first_live_evidence_assisted_runs(limit=1, log_dir=log_dir)
    return records[0] if records else None


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


def _cockpit_from_burn_down(
    *,
    burn_down: Mapping[str, Any],
    candidate_id: str,
    log_dir: str | Path,
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    chain = burn_down.get("current_gate_chain") if isinstance(burn_down.get("current_gate_chain"), Mapping) else {}
    sacred_button = chain.get("sacred_button_state") if isinstance(chain.get("sacred_button_state"), Mapping) else {}
    if chain:
        return {
            "status": chain.get("cockpit_status"),
            "first_live_activation_gate_status": chain.get("first_live_activation_gate_status"),
            "candidate_id": burn_down.get("candidate_id") or candidate_id,
            "risk_contract_hash": None,
            "packet_hash": None,
            "sacred_button_state": sacred_button,
            "backend_authority": {
                "sacred_button_can_place_order": sacred_button.get("can_place_order", False),
            },
            "live_ready": False,
            "execution_enabled_by_ui": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
            "paper_live_separation_intact": burn_down.get("paper_live_separation_intact", True),
            "source_surfaces_used": burn_down.get("source_surfaces_used") or [],
        }
    return build_operator_approval_cockpit_state(
        candidate_id=candidate_id,
        log_dir=log_dir,
        env=env,
    )


def _active_tuple(
    *,
    evidence_status: Mapping[str, Any],
    prerequisite_recheck: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    cockpit: Mapping[str, Any],
) -> dict[str, Any]:
    candidates: list[dict[str, str]] = []
    for surface in (
        evidence_status.get("ready_tuple"),
        prerequisite_recheck.get("recheck_tuple"),
        activation_gate,
        cockpit,
    ):
        tuple_payload = _tuple_from_surface(surface)
        if tuple_payload is not None:
            candidates.append(tuple_payload)
    if not candidates:
        return {
            "candidate_id": None,
            "risk_contract_hash": None,
            "packet_hash": None,
            "tuple_status": "MISSING",
        }
    first = candidates[0]
    if any(candidate != first for candidate in candidates[1:]):
        return {
            **first,
            "tuple_status": "INCONSISTENT",
        }
    return {
        **first,
        "tuple_status": "CONSISTENT",
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


def _evidence_summary(*, evidence_status: Mapping[str, Any], active_tuple: Mapping[str, Any]) -> dict[str, Any]:
    tuple_status = str(active_tuple.get("tuple_status") or "MISSING")
    consistency = "CONSISTENT" if tuple_status == "CONSISTENT" else tuple_status
    return {
        "records_count": int(evidence_status.get("records_count") or 0),
        "accepted_records_count": int(evidence_status.get("accepted_records_count") or 0),
        "rejected_records_count": int(evidence_status.get("rejected_records_count") or 0),
        "evidence_types_present": list(evidence_status.get("evidence_types_present") or []),
        "evidence_types_missing": list(evidence_status.get("evidence_types_missing") or []),
        "ready_tuple": evidence_status.get("ready_tuple"),
        "tuple_consistency_status": consistency if consistency in {"CONSISTENT", "INCONSISTENT"} else "MISSING",
    }


def _source_statuses(
    *,
    evidence_status: Mapping[str, Any],
    prerequisite_recheck: Mapping[str, Any],
    assisted_run: Mapping[str, Any] | None,
    prerequisite_clearing: Mapping[str, Any],
    burn_down: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    cockpit: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "R112 evidence status": evidence_status.get("status"),
        "R113 prerequisite recheck": prerequisite_recheck.get("status"),
        "R116 assisted run status": assisted_run.get("status") if isinstance(assisted_run, Mapping) else None,
        "R111 prerequisite clearing": prerequisite_clearing.get("status"),
        "R110 burn-down": burn_down.get("status"),
        "R106 activation gate": activation_gate.get("status"),
        "R109 cockpit": cockpit.get("status"),
    }


def _gate_delta(
    *,
    evidence_summary: Mapping[str, Any],
    prerequisite_recheck: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    blocker_map: list[Mapping[str, Any]],
) -> dict[str, Any]:
    still_blocked = [item for item in blocker_map if item.get("status_after_evidence") == "STILL_BLOCKED"]
    needs_evidence = [item for item in blocker_map if item.get("status_after_evidence") == "NEEDS_MORE_EVIDENCE"]
    unknown = [item for item in blocker_map if item.get("status_after_evidence") == "UNKNOWN"]
    cleared = [item for item in blocker_map if item.get("status_after_evidence") == "CLEAR"]
    blockers_remaining = still_blocked + needs_evidence + unknown
    did_reduce: bool | str
    if int(evidence_summary.get("accepted_records_count") or 0) <= 0:
        did_reduce = "unknown"
    else:
        did_reduce = bool(cleared)
    return {
        "r106_current_status": activation_gate.get("status"),
        "r113_current_status": prerequisite_recheck.get("status"),
        "blockers_remaining_count": len(blockers_remaining),
        "evidence_missing_count": len(evidence_summary.get("evidence_types_missing") or []),
        "groups_cleared_count": len(cleared),
        "groups_still_blocked_count": len(still_blocked),
        "groups_needing_evidence_count": len(needs_evidence),
        "did_evidence_reduce_blockers": did_reduce,
        "activation_gate_ready": activation_gate.get("status") == FIRST_LIVE_ACTIVATION_READY,
    }


def _blocker_map(
    *,
    prerequisite_recheck: Mapping[str, Any],
    evidence_status: Mapping[str, Any],
) -> list[dict[str, Any]]:
    recheck_items = {
        str(item.get("group")): item
        for item in prerequisite_recheck.get("blocker_recheck") or []
        if isinstance(item, Mapping)
    }
    present = set(str(item) for item in evidence_status.get("evidence_types_present") or [])
    results = []
    for group in GROUP_ORDER:
        item = recheck_items.get(group, {})
        required = list(GROUP_EVIDENCE_TYPES.get(group, ()))
        group_present = [evidence_type for evidence_type in required if evidence_type in present]
        missing = [evidence_type for evidence_type in required if evidence_type not in present]
        results.append(
            {
                "group": group,
                "status_after_evidence": item.get("rechecked_status") or "UNKNOWN",
                "evidence_types_required": required,
                "evidence_types_present": group_present,
                "evidence_types_missing": missing,
                "blockers_remaining": list(item.get("blockers_remaining") or []),
                "next_action": item.get("next_action") or "Run R113 prerequisite recheck before deciding this group.",
                "verification_command": item.get("verification_command") or _cmd("first-live-prerequisite-recheck-after-evidence"),
            }
        )
    return results


def _activation_readiness_summary(
    *,
    activation_gate: Mapping[str, Any],
    cockpit: Mapping[str, Any],
    gate_delta: Mapping[str, Any],
) -> dict[str, Any]:
    sacred_button = cockpit.get("sacred_button_state") if isinstance(cockpit.get("sacred_button_state"), Mapping) else {}
    backend_authority = cockpit.get("backend_authority") if isinstance(cockpit.get("backend_authority"), Mapping) else {}
    can_place_order = (
        sacred_button.get("can_place_order")
        if "can_place_order" in sacred_button
        else backend_authority.get("sacred_button_can_place_order")
    )
    records_intent_only = sacred_button.get("records_intent_only", True)
    paper_live_separation_intact = _paper_live_separation_intact(activation_gate=activation_gate, cockpit=cockpit)
    activation_ready = bool(gate_delta.get("activation_gate_ready"))
    safety_clean = can_place_order is False and records_intent_only is True and paper_live_separation_intact is True
    can_consider = activation_ready and safety_clean
    required = []
    if activation_gate.get("status") == FIRST_LIVE_BLOCKED:
        required.append("R106 must no longer report FIRST_LIVE_BLOCKED.")
    if can_place_order is not False:
        required.append("R109 sacred button must keep can_place_order=false.")
    if records_intent_only is not True:
        required.append("R109 sacred button must record intent only.")
    if paper_live_separation_intact is not True:
        required.append("Paper/live separation must be explicitly intact.")
    if gate_delta.get("blockers_remaining_count"):
        required.append("R113 blocker map must have no remaining blocked, unknown, or evidence-needed groups.")
    return {
        "can_consider_activation_phase": can_consider,
        "reason": "R106 is ready and R109/paper-live safety remains clean." if can_consider else "Post-evidence recheck still has gate, evidence, or safety blockers.",
        "required_before_activation_phase": required,
        "current_r106_status": activation_gate.get("status"),
        "sacred_button_can_place_order": bool(can_place_order),
        "sacred_button_records_intent_only": bool(records_intent_only),
        "paper_live_separation_intact": paper_live_separation_intact,
    }


def _paper_live_separation_intact(*, activation_gate: Mapping[str, Any], cockpit: Mapping[str, Any]) -> bool:
    if activation_gate.get("paper_live_separation_intact") is False or cockpit.get("paper_live_separation_intact") is False:
        return False
    if activation_gate.get("paper_live_separation_intact") is True:
        return True
    local_safety_false = (
        activation_gate.get("live_ready") is False
        and activation_gate.get("execution_attempted") is False
        and activation_gate.get("real_order_possible") is False
        and cockpit.get("live_ready") is False
        and cockpit.get("execution_attempted") is False
        and cockpit.get("real_order_possible") is False
    )
    return bool(local_safety_false)


def _status(
    *,
    evidence_status: Mapping[str, Any],
    evidence_summary: Mapping[str, Any],
    gate_delta: Mapping[str, Any],
    activation_readiness_summary: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
) -> str:
    safety_violation = any(
        activation_gate.get(field) is not False
        for field in ("live_ready", "order_placed", "execution_attempted", "real_order_possible", "secrets_shown")
    )
    if (
        activation_gate.get("status") == FIRST_LIVE_BLOCKED
        or evidence_summary.get("tuple_consistency_status") != "CONSISTENT"
        or activation_readiness_summary.get("sacred_button_can_place_order") is True
        or activation_readiness_summary.get("paper_live_separation_intact") is False
        or safety_violation
        or int(evidence_summary.get("records_count") or 0) == 0
    ):
        return POST_EVIDENCE_BLOCKED
    if (
        evidence_status.get("status") == EVIDENCE_READY_FOR_PREREQ_RECHECK
        and gate_delta.get("r113_current_status") == RECHECK_READY_FOR_R106
        and gate_delta.get("did_evidence_reduce_blockers") is True
        and activation_readiness_summary.get("can_consider_activation_phase") is True
    ):
        return POST_EVIDENCE_READY_FOR_ACTIVATION_GATE_RECHECK
    if int(evidence_summary.get("accepted_records_count") or 0) > 0:
        return POST_EVIDENCE_PARTIAL
    return POST_EVIDENCE_BLOCKED


def _next_operator_actions(
    *,
    status: str,
    blocker_map: list[Mapping[str, Any]],
    activation_readiness_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if status == POST_EVIDENCE_READY_FOR_ACTIVATION_GATE_RECHECK:
        return [
            {
                "priority": 1,
                "action": "Run the R106 activation gate recheck and prepare R118 review.",
                "why": "Evidence and safety checks are clean enough to request final non-executing activation-gate review.",
                "command": _cmd("first-live-activation-gate"),
                "safety_note": "This still does not authorize or place a live order.",
            }
        ]
    actions: list[dict[str, Any]] = []
    for item in blocker_map:
        if item.get("status_after_evidence") == "CLEAR":
            continue
        actions.append(
            {
                "priority": len(actions) + 1,
                "action": str(item.get("next_action")),
                "why": f"{item.get('group')} is {item.get('status_after_evidence')} after evidence.",
                "command": str(item.get("verification_command")),
                "safety_note": "Evidence clearing is non-executing and must not change live flags or place orders.",
            }
        )
    for requirement in activation_readiness_summary.get("required_before_activation_phase") or []:
        actions.append(
            {
                "priority": len(actions) + 1,
                "action": str(requirement),
                "why": "Activation readiness summary still has a required condition.",
                "command": _cmd("first-live-post-evidence-gate-recheck"),
                "safety_note": "R117 reports decision support only.",
            }
        )
    return actions[:8]


def _final_recheck_command_pack() -> dict[str, str]:
    return {
        "evidence_status": _cmd("first-live-evidence-status"),
        "prerequisite_recheck": _cmd("first-live-prerequisite-recheck-after-evidence"),
        "prerequisite_clearing": _cmd("first-live-prerequisite-clearing"),
        "burn_down": _cmd("first-live-burn-down"),
        "activation_gate": _cmd("first-live-activation-gate"),
        "cockpit_state": "curl -s http://127.0.0.1:8015/operator/approval-cockpit/state",
    }


def _source_surfaces(
    *,
    prerequisite_recheck: Mapping[str, Any],
    burn_down: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    cockpit: Mapping[str, Any],
    assisted_run: Mapping[str, Any] | None,
) -> list[str]:
    surfaces = [
        SOURCE_SURFACE,
        "R112 first-live-evidence-status",
        "R113 first-live-prerequisite-recheck-after-evidence",
        "R116 first-live-evidence-assisted-run ledger",
        "R111 first-live-prerequisite-clearing",
        "R110 first-live-burn-down",
        "R106 first-live-activation-gate",
        "R109 first-live cockpit sacred button state",
    ]
    surfaces.extend(str(item) for item in prerequisite_recheck.get("source_surfaces_used") or [])
    surfaces.extend(str(item) for item in burn_down.get("source_surfaces_used") or [])
    surfaces.extend(str(item) for item in activation_gate.get("source_surfaces_used") or [])
    surfaces.extend(str(item) for item in cockpit.get("source_surfaces_used") or [])
    if isinstance(assisted_run, Mapping):
        surfaces.extend(str(item) for item in assisted_run.get("source_surfaces_used") or [])
    return list(dict.fromkeys(surfaces))


def _ledger_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "event_type",
        "post_evidence_recheck_id",
        "recorded_at_utc",
        "status",
        "active_tuple",
        "source_statuses",
        "evidence_summary",
        "gate_delta",
        "blocker_map",
        "activation_readiness_summary",
        "live_ready",
        "execution_enabled_by_post_evidence_recheck",
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
