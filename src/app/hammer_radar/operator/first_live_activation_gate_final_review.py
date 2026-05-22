"""R118 first-live activation gate final review.

This module composes existing non-executing first-live readiness surfaces into
one final review before a later explicit authorization-request phase. It never
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
from src.app.hammer_radar.operator.final_live_preflight import READY, build_final_live_preflight
from src.app.hammer_radar.operator.first_live_activation_gate import (
    FIRST_LIVE_ACTIVATION_READY,
    FIRST_LIVE_BLOCKED,
    build_first_live_activation_gate,
    load_first_live_activation_gate_checks,
)
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
from src.app.hammer_radar.operator.first_live_post_evidence_gate_recheck import (
    POST_EVIDENCE_PARTIAL,
    POST_EVIDENCE_READY_FOR_ACTIVATION_GATE_RECHECK,
    build_first_live_post_evidence_gate_recheck,
    load_first_live_post_evidence_gate_rechecks,
)
from src.app.hammer_radar.operator.first_live_prerequisite_recheck_after_evidence import (
    RECHECK_READY_FOR_R106,
    build_first_live_prerequisite_recheck_after_evidence,
    load_first_live_prerequisite_rechecks,
)
from src.app.hammer_radar.operator.one_tiny_live_order_protocol import (
    CONFIRMATION_PHRASE_TEMPLATE,
    PROTOCOL_PREREQS_READY,
    build_one_tiny_live_order_protocol_check,
    load_one_tiny_live_order_protocol_checks,
)
from src.app.hammer_radar.operator.tiny_live_armed_dry_run import (
    READY_FOR_DRY_RUN,
    build_tiny_live_armed_dry_run,
    load_tiny_live_armed_dry_runs,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

FINAL_REVIEW_BLOCKED = "FINAL_REVIEW_BLOCKED"
FINAL_REVIEW_PARTIAL = "FINAL_REVIEW_PARTIAL"
READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION = "READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION"

EVENT_TYPE = "FIRST_LIVE_ACTIVATION_FINAL_REVIEW"
LEDGER_FILENAME = "first_live_activation_final_reviews.ndjson"
SOURCE_SURFACE = "operator.first_live_activation_gate_final_review.build_first_live_activation_final_review"
FUTURE_PHASE = "R119_FIRST_LIVE_EXPLICIT_AUTHORIZATION_REQUEST"


def _cmd(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


def build_first_live_activation_final_review(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    checked_at = datetime.now(UTC).isoformat()

    dry_run = _latest_dry_run(candidate_id=candidate_id, log_dir=resolved_log_dir)
    if dry_run is None:
        dry_run = build_tiny_live_armed_dry_run(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, record=False)
    protocol = _latest_protocol(log_dir=resolved_log_dir)
    if protocol is None:
        protocol = build_one_tiny_live_order_protocol_check(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, record=False)
    activation_gate = _latest_activation_gate(log_dir=resolved_log_dir)
    if activation_gate is None:
        activation_gate = build_first_live_activation_gate(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env, record=False)
    final_preflight = _final_preflight_from_sources(
        dry_run=dry_run,
        activation_gate=activation_gate,
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
    )
    evidence_status = build_first_live_evidence_status(log_dir=resolved_log_dir)
    prerequisite_recheck = _latest_prerequisite_recheck(log_dir=resolved_log_dir)
    if prerequisite_recheck is None:
        prerequisite_recheck = build_first_live_prerequisite_recheck_after_evidence(
            candidate_id=candidate_id,
            log_dir=resolved_log_dir,
            env=env,
            record=False,
        )
    assisted_run = _latest_assisted_run(log_dir=resolved_log_dir)
    post_evidence_recheck = _latest_post_evidence_recheck(log_dir=resolved_log_dir)
    if post_evidence_recheck is None:
        post_evidence_recheck = build_first_live_post_evidence_gate_recheck(
            candidate_id=candidate_id,
            log_dir=resolved_log_dir,
            env=env,
            record=False,
        )
    cockpit = _cockpit_from_post_evidence(post_evidence_recheck=post_evidence_recheck, activation_gate=activation_gate)
    if cockpit is None:
        cockpit = build_operator_approval_cockpit_state(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env)

    active_tuple = _active_tuple(
        final_preflight=final_preflight,
        dry_run=dry_run,
        protocol=protocol,
        activation_gate=activation_gate,
        cockpit=cockpit,
        evidence_status=evidence_status,
        prerequisite_recheck=prerequisite_recheck,
        post_evidence_recheck=post_evidence_recheck,
    )
    source_statuses = _source_statuses(
        final_preflight=final_preflight,
        dry_run=dry_run,
        protocol=protocol,
        activation_gate=activation_gate,
        cockpit=cockpit,
        evidence_status=evidence_status,
        prerequisite_recheck=prerequisite_recheck,
        assisted_run=assisted_run,
        post_evidence_recheck=post_evidence_recheck,
    )
    safety = _safety_summary(
        final_preflight=final_preflight,
        dry_run=dry_run,
        protocol=protocol,
        activation_gate=activation_gate,
        cockpit=cockpit,
        evidence_status=evidence_status,
        prerequisite_recheck=prerequisite_recheck,
        assisted_run=assisted_run,
        post_evidence_recheck=post_evidence_recheck,
    )
    readiness_matrix = _readiness_matrix(
        active_tuple=active_tuple,
        source_statuses=source_statuses,
        cockpit=cockpit,
        activation_gate=activation_gate,
        evidence_status=evidence_status,
        prerequisite_recheck=prerequisite_recheck,
        post_evidence_recheck=post_evidence_recheck,
        safety=safety,
    )
    remaining_blockers = _remaining_blockers(readiness_matrix=readiness_matrix)
    status = _final_status(
        active_tuple=active_tuple,
        readiness_matrix=readiness_matrix,
        remaining_blockers=remaining_blockers,
        evidence_status=evidence_status,
        prerequisite_recheck=prerequisite_recheck,
        post_evidence_recheck=post_evidence_recheck,
        safety=safety,
    )
    authorization_request_readiness = _authorization_request_readiness(
        status=status,
        remaining_blockers=remaining_blockers,
    )

    payload = {
        "event_type": EVENT_TYPE,
        "final_review_id": uuid4().hex,
        "recorded_at_utc": checked_at,
        "checked_at_utc": checked_at,
        "status": status,
        "live_ready": False,
        "execution_enabled_by_final_review": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "active_tuple": active_tuple,
        "source_statuses": source_statuses,
        "readiness_matrix": readiness_matrix,
        "authorization_request_readiness": authorization_request_readiness,
        "remaining_blockers": remaining_blockers,
        "final_operator_readiness_checklist": _final_operator_readiness_checklist(
            active_tuple=active_tuple,
            source_statuses=source_statuses,
            cockpit=cockpit,
            activation_gate=activation_gate,
            final_preflight=final_preflight,
            evidence_status=evidence_status,
            prerequisite_recheck=prerequisite_recheck,
            post_evidence_recheck=post_evidence_recheck,
            safety=safety,
        ),
        "authorization_boundary": _authorization_boundary(),
        "next_operator_actions": _next_operator_actions(
            status=status,
            remaining_blockers=remaining_blockers,
        ),
        "final_recheck_command_pack": _final_recheck_command_pack(),
        "source_surfaces_used": _source_surfaces(
            final_preflight=final_preflight,
            dry_run=dry_run,
            protocol=protocol,
            activation_gate=activation_gate,
            cockpit=cockpit,
            evidence_status=evidence_status,
            prerequisite_recheck=prerequisite_recheck,
            assisted_run=assisted_run,
            post_evidence_recheck=post_evidence_recheck,
        ),
        "ledger_path": str(first_live_activation_final_reviews_path(resolved_log_dir)),
        "paper_live_separation_intact": safety["paper_live_separation_intact"],
    }
    payload = _sanitize(payload)
    if record:
        append_first_live_activation_final_review(payload, log_dir=resolved_log_dir)
    return payload


def append_first_live_activation_final_review(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_activation_final_reviews_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_ledger_record(record), sort_keys=True) + "\n")


def load_first_live_activation_final_reviews(
    *,
    limit: int = 50,
    final_review_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_activation_final_reviews_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if final_review_id is not None and record.get("final_review_id") != final_review_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_activation_final_reviews_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_first_live_activation_final_review_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _latest_assisted_run(*, log_dir: str | Path) -> dict[str, Any] | None:
    records = load_first_live_evidence_assisted_runs(limit=1, log_dir=log_dir)
    return records[0] if records else None


def _latest_dry_run(*, candidate_id: str, log_dir: str | Path) -> dict[str, Any] | None:
    records = load_tiny_live_armed_dry_runs(limit=1, candidate_id=candidate_id, log_dir=log_dir)
    return records[0] if records else None


def _latest_protocol(*, log_dir: str | Path) -> dict[str, Any] | None:
    records = load_one_tiny_live_order_protocol_checks(limit=1, log_dir=log_dir)
    return records[0] if records else None


def _latest_activation_gate(*, log_dir: str | Path) -> dict[str, Any] | None:
    records = load_first_live_activation_gate_checks(limit=1, log_dir=log_dir)
    return records[0] if records else None


def _latest_prerequisite_recheck(*, log_dir: str | Path) -> dict[str, Any] | None:
    records = load_first_live_prerequisite_rechecks(limit=1, log_dir=log_dir)
    return records[0] if records else None


def _latest_post_evidence_recheck(*, log_dir: str | Path) -> dict[str, Any] | None:
    records = load_first_live_post_evidence_gate_rechecks(limit=1, log_dir=log_dir)
    return records[0] if records else None


def _final_preflight_from_sources(
    *,
    dry_run: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    candidate_id: str,
    log_dir: str | Path,
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    status = dry_run.get("final_preflight_status")
    if status is None:
        return build_final_live_preflight(candidate_id=candidate_id, log_dir=log_dir, env=env)
    return {
        "status": status,
        "candidate_id": dry_run.get("candidate_id") or activation_gate.get("candidate_id") or candidate_id,
        "risk_contract_hash": dry_run.get("risk_contract_hash") or activation_gate.get("risk_contract_hash"),
        "final_review_packet_hash": dry_run.get("packet_hash") or activation_gate.get("packet_hash"),
        "blockers": list(dry_run.get("final_preflight_blockers") or []),
        "protective_orders_ready": bool(dry_run.get("protective_orders_ready") or activation_gate.get("protective_orders_ready")),
        "paper_live_separation_intact": dry_run.get("paper_live_separation_intact") is not False
        and activation_gate.get("paper_live_separation_intact") is not False,
        "live_ready": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "source_surfaces_used": ["R102 final-live-preflight status from latest R104/R106 records"],
    }


def _cockpit_from_post_evidence(
    *,
    post_evidence_recheck: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
) -> dict[str, Any] | None:
    source_statuses = post_evidence_recheck.get("source_statuses") if isinstance(post_evidence_recheck.get("source_statuses"), Mapping) else {}
    summary = (
        post_evidence_recheck.get("activation_readiness_summary")
        if isinstance(post_evidence_recheck.get("activation_readiness_summary"), Mapping)
        else {}
    )
    if not source_statuses and not summary:
        return None
    return {
        "status": source_statuses.get("R109 cockpit"),
        "candidate_id": activation_gate.get("candidate_id"),
        "risk_contract_hash": activation_gate.get("risk_contract_hash"),
        "packet_hash": activation_gate.get("packet_hash"),
        "sacred_button_state": {
            "can_place_order": bool(summary.get("sacred_button_can_place_order")),
            "records_intent_only": summary.get("sacred_button_records_intent_only", True) is True,
        },
        "backend_authority": {"sacred_button_can_place_order": bool(summary.get("sacred_button_can_place_order"))},
        "live_ready": False,
        "execution_enabled_by_ui": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "paper_live_separation_intact": summary.get("paper_live_separation_intact") is not False
        and post_evidence_recheck.get("paper_live_separation_intact") is not False,
        "source_surfaces_used": ["R109 cockpit sacred button state from latest R117 record"],
    }


def _source_statuses(
    *,
    final_preflight: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    protocol: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    cockpit: Mapping[str, Any],
    evidence_status: Mapping[str, Any],
    prerequisite_recheck: Mapping[str, Any],
    assisted_run: Mapping[str, Any] | None,
    post_evidence_recheck: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "R102 final preflight": final_preflight.get("status"),
        "R104 tiny live armed dry run": dry_run.get("status"),
        "R105 protocol": protocol.get("status"),
        "R106 activation gate": activation_gate.get("status"),
        "R109 cockpit": cockpit.get("status"),
        "R112 evidence status": evidence_status.get("status"),
        "R113 prerequisite recheck": prerequisite_recheck.get("status"),
        "R116 assisted run latest status": assisted_run.get("status") if isinstance(assisted_run, Mapping) else None,
        "R117 post-evidence recheck": post_evidence_recheck.get("status"),
    }


def _readiness_matrix(
    *,
    active_tuple: Mapping[str, Any],
    source_statuses: Mapping[str, Any],
    cockpit: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    evidence_status: Mapping[str, Any],
    prerequisite_recheck: Mapping[str, Any],
    post_evidence_recheck: Mapping[str, Any],
    safety: Mapping[str, Any],
) -> list[dict[str, Any]]:
    sacred = _sacred_button(cockpit)
    matrix = [
        _layer("final_preflight", READY, source_statuses.get("R102 final preflight"), _cmd("final-live-preflight")),
        _layer("armed_dry_run", READY_FOR_DRY_RUN, source_statuses.get("R104 tiny live armed dry run"), _cmd("tiny-live-armed-dry-run")),
        _layer("one_tiny_live_order_protocol", PROTOCOL_PREREQS_READY, source_statuses.get("R105 protocol"), _cmd("one-tiny-live-order-protocol")),
        _layer("activation_gate", FIRST_LIVE_ACTIVATION_READY, source_statuses.get("R106 activation gate"), _cmd("first-live-activation-gate")),
        {
            "layer": "cockpit_sacred_button",
            "required_status": "can_place_order=false; records_intent_only=true",
            "current_status": f"can_place_order={str(sacred['can_place_order']).lower()}; records_intent_only={str(sacred['records_intent_only']).lower()}",
            "satisfied": sacred["can_place_order"] is False and sacred["records_intent_only"] is True,
            "blockers": _bool_blockers(
                ("R109 sacred button can_place_order must remain false", sacred["can_place_order"] is False),
                ("R109 sacred button records_intent_only must remain true", sacred["records_intent_only"] is True),
            ),
            "verification_command": "curl -s http://127.0.0.1:8015/operator/approval-cockpit/state",
        },
        _layer("evidence_status", EVIDENCE_READY_FOR_PREREQ_RECHECK, source_statuses.get("R112 evidence status"), _cmd("first-live-evidence-status")),
        _layer("prerequisite_recheck", RECHECK_READY_FOR_R106, source_statuses.get("R113 prerequisite recheck"), _cmd("first-live-prerequisite-recheck-after-evidence")),
        _layer(
            "post_evidence_recheck",
            POST_EVIDENCE_READY_FOR_ACTIVATION_GATE_RECHECK,
            source_statuses.get("R117 post-evidence recheck"),
            _cmd("first-live-post-evidence-gate-recheck"),
        ),
        {
            "layer": "paper_live_separation",
            "required_status": "paper_live_separation_intact=true",
            "current_status": f"paper_live_separation_intact={str(safety['paper_live_separation_intact']).lower()}",
            "satisfied": safety["paper_live_separation_intact"] is True,
            "blockers": [] if safety["paper_live_separation_intact"] is True else ["paper/live separation is not intact"],
            "verification_command": _cmd("final-live-preflight"),
        },
        {
            "layer": "secret_safety",
            "required_status": "secrets_shown=false",
            "current_status": f"secrets_shown={str(safety['secrets_shown']).lower()}",
            "satisfied": safety["secrets_shown"] is False,
            "blockers": [] if safety["secrets_shown"] is False else ["a source surface reported secrets_shown=true"],
            "verification_command": _cmd("first-live-activation-final-review --no-record"),
        },
        {
            "layer": "no_order_safety",
            "required_status": "order_placed=false; execution_attempted=false; real_order_possible=false",
            "current_status": (
                f"order_placed={str(safety['order_placed']).lower()}; "
                f"execution_attempted={str(safety['execution_attempted']).lower()}; "
                f"real_order_possible={str(safety['real_order_possible']).lower()}"
            ),
            "satisfied": not safety["order_placed"] and not safety["execution_attempted"] and not safety["real_order_possible"],
            "blockers": _bool_blockers(
                ("a source surface reported order_placed=true", safety["order_placed"] is False),
                ("a source surface reported execution_attempted=true", safety["execution_attempted"] is False),
                ("a source surface reported real_order_possible=true", safety["real_order_possible"] is False),
            ),
            "verification_command": _cmd("first-live-activation-final-review --no-record"),
        },
    ]
    tuple_blockers = []
    if active_tuple.get("tuple_status") != "CONSISTENT":
        tuple_blockers.append(f"active tuple is {active_tuple.get('tuple_status')}")
    if tuple_blockers:
        matrix.insert(
            0,
            {
                "layer": "active_tuple",
                "required_status": "CONSISTENT",
                "current_status": active_tuple.get("tuple_status"),
                "satisfied": False,
                "blockers": tuple_blockers,
                "verification_command": _cmd("first-live-post-evidence-gate-recheck"),
            },
        )
    return matrix


def _layer(layer: str, required: str, current: Any, command: str) -> dict[str, Any]:
    satisfied = current == required
    return {
        "layer": layer,
        "required_status": required,
        "current_status": current,
        "satisfied": satisfied,
        "blockers": [] if satisfied else [f"{layer} is {current or 'MISSING'}, expected {required}"],
        "verification_command": command,
    }


def _remaining_blockers(*, readiness_matrix: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in readiness_matrix:
        if item.get("satisfied") is True:
            continue
        blockers = item.get("blockers") or [f"{item.get('layer')} is not satisfied"]
        for blocker in blockers:
            results.append(
                {
                    "blocker": str(blocker),
                    "source": str(item.get("layer")),
                    "owner": _owner_for_layer(str(item.get("layer"))),
                    "severity": _severity_for_layer(str(item.get("layer"))),
                    "next_action": _next_action_for_layer(str(item.get("layer"))),
                    "command": str(item.get("verification_command")),
                }
            )
    return results


def _final_status(
    *,
    active_tuple: Mapping[str, Any],
    readiness_matrix: list[Mapping[str, Any]],
    remaining_blockers: list[Mapping[str, Any]],
    evidence_status: Mapping[str, Any],
    prerequisite_recheck: Mapping[str, Any],
    post_evidence_recheck: Mapping[str, Any],
    safety: Mapping[str, Any],
) -> str:
    if not remaining_blockers:
        return READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION
    hard_safety_violation = (
        active_tuple.get("tuple_status") != "CONSISTENT"
        or safety["sacred_button_can_place_order"] is True
        or safety["sacred_button_records_intent_only"] is not True
        or safety["paper_live_separation_intact"] is False
        or safety["live_ready"] is not False
        or safety["order_placed"] is not False
        or safety["execution_attempted"] is not False
        or safety["real_order_possible"] is not False
        or safety["secrets_shown"] is not False
    )
    critical_layers = {"final_preflight", "armed_dry_run", "one_tiny_live_order_protocol", "activation_gate"}
    critical_blocked = any(
        item.get("layer") in critical_layers and item.get("satisfied") is not True
        for item in readiness_matrix
    )
    if hard_safety_violation or critical_blocked:
        return FINAL_REVIEW_BLOCKED
    improved = (
        int(evidence_status.get("accepted_records_count") or 0) > 0
        or prerequisite_recheck.get("status") == "RECHECK_PARTIAL"
        or post_evidence_recheck.get("status") == POST_EVIDENCE_PARTIAL
    )
    return FINAL_REVIEW_PARTIAL if improved else FINAL_REVIEW_BLOCKED


def _authorization_request_readiness(
    *,
    status: str,
    remaining_blockers: list[Mapping[str, Any]],
) -> dict[str, Any]:
    can_request = status == READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION
    missing = [str(item.get("blocker")) for item in remaining_blockers]
    return {
        "can_request_authorization": can_request,
        "reason": (
            "All R102/R104/R105/R106/R109/R112/R113/R117 layers are satisfied; R118 may open an explicit human authorization request phase."
            if can_request
            else "One or more required final-review layers remain blocked or partial."
        ),
        "missing_requirements": missing,
        "required_confirmation_phrase_template": CONFIRMATION_PHRASE_TEMPLATE,
        "future_phase_required": True,
        "future_phase_suggestion": FUTURE_PHASE,
    }


def _final_operator_readiness_checklist(
    *,
    active_tuple: Mapping[str, Any],
    source_statuses: Mapping[str, Any],
    cockpit: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    final_preflight: Mapping[str, Any],
    evidence_status: Mapping[str, Any],
    prerequisite_recheck: Mapping[str, Any],
    post_evidence_recheck: Mapping[str, Any],
    safety: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        _check("active tuple consistent?", active_tuple.get("tuple_status") == "CONSISTENT"),
        _check("evidence ready?", evidence_status.get("status") == EVIDENCE_READY_FOR_PREREQ_RECHECK),
        _check("R106 activation gate ready?", activation_gate.get("status") == FIRST_LIVE_ACTIVATION_READY),
        _check("sacred button still intent-only?", safety["sacred_button_can_place_order"] is False and safety["sacred_button_records_intent_only"] is True),
        _check("paper/live separation intact?", safety["paper_live_separation_intact"] is True),
        _check("no secrets shown?", safety["secrets_shown"] is False),
        _check("no order placed?", safety["order_placed"] is False),
        _check("no execution attempted?", safety["execution_attempted"] is False),
        _check("protective orders ready?", final_preflight.get("protective_orders_ready") is True),
        _check("tiny size/max loss defined?", "TINY_SIZE_MAX_LOSS_DEFINED" in set(evidence_status.get("evidence_types_present") or [])),
        _check("kill switch understood?", "ENVIRONMENT_FLAGS_REVIEWED" in set(evidence_status.get("evidence_types_present") or [])),
        _check("emergency cancel path reviewed?", "EMERGENCY_CANCEL_PATH_REVIEWED" in set(evidence_status.get("evidence_types_present") or [])),
        _check("no conflicting position reviewed?", "NO_CONFLICTING_POSITION_REVIEWED" in set(evidence_status.get("evidence_types_present") or [])),
        _check("candidate fresh?", "stale candidate risk" not in [str(item) for item in final_preflight.get("blockers") or []]),
    ]


def _check(label: str, ok: bool) -> dict[str, Any]:
    return {"item": label, "satisfied": bool(ok)}


def _authorization_boundary() -> dict[str, Any]:
    return {
        "R118 does not place orders": True,
        "R118 does not enable live trading": True,
        "R118 does not change env flags": True,
        "R118 does not call Binance order endpoints": True,
        "R118 only determines whether a later explicit authorization request phase may be opened": True,
        "execution_authority_created": False,
        "live_order_endpoint_created": False,
    }


def _next_operator_actions(
    *,
    status: str,
    remaining_blockers: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if status == READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION:
        return [
            {
                "priority": 1,
                "action": "Open R119 explicit authorization request as the next phase.",
                "why": "R118 says the system is ready to request explicit human authorization, not to execute.",
                "command": _cmd("first-live-activation-final-review --no-record"),
                "safety_note": "R119 remains non-executing unless a later phase is explicitly authorized for execution.",
            }
        ]
    actions = []
    for blocker in remaining_blockers[:8]:
        actions.append(
            {
                "priority": len(actions) + 1,
                "action": blocker.get("next_action"),
                "why": blocker.get("blocker"),
                "command": blocker.get("command"),
                "safety_note": "This action must remain review/evidence/recheck only.",
            }
        )
    return actions


def _final_recheck_command_pack() -> dict[str, str]:
    return {
        "final-live-preflight": _cmd("final-live-preflight"),
        "tiny-live-armed-dry-run": _cmd("tiny-live-armed-dry-run"),
        "one-tiny-live-order-protocol": _cmd("one-tiny-live-order-protocol"),
        "first-live-activation-gate": _cmd("first-live-activation-gate"),
        "first-live-evidence-status": _cmd("first-live-evidence-status"),
        "first-live-prerequisite-recheck-after-evidence": _cmd("first-live-prerequisite-recheck-after-evidence"),
        "first-live-post-evidence-gate-recheck": _cmd("first-live-post-evidence-gate-recheck"),
        "cockpit state curl": "curl -s http://127.0.0.1:8015/operator/approval-cockpit/state",
    }


def _active_tuple(**surfaces: Mapping[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, str]] = []
    sources: list[str] = []
    for name, surface in surfaces.items():
        tuple_payload = _tuple_from_surface(surface.get("active_tuple") if isinstance(surface.get("active_tuple"), Mapping) else surface)
        if tuple_payload is None and isinstance(surface.get("ready_tuple"), Mapping):
            tuple_payload = _tuple_from_surface(surface.get("ready_tuple"))
        if tuple_payload is None and isinstance(surface.get("recheck_tuple"), Mapping):
            tuple_payload = _tuple_from_surface(surface.get("recheck_tuple"))
        if tuple_payload is not None:
            candidates.append(tuple_payload)
            sources.append(name)
    if not candidates:
        return {
            "candidate_id": None,
            "risk_contract_hash": None,
            "packet_hash": None,
            "tuple_status": "MISSING",
            "source": None,
        }
    first = candidates[0]
    status = "CONSISTENT" if all(candidate == first for candidate in candidates[1:]) else "INCONSISTENT"
    return {**first, "tuple_status": status, "source": ",".join(sources)}


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


def _safety_summary(**surfaces: Mapping[str, Any] | None) -> dict[str, Any]:
    payloads = [surface for surface in surfaces.values() if isinstance(surface, Mapping)]
    sacred = _sacred_button(surfaces.get("cockpit") if isinstance(surfaces.get("cockpit"), Mapping) else {})
    return {
        "live_ready": any(surface.get("live_ready") is not False for surface in payloads if "live_ready" in surface),
        "order_placed": any(surface.get("order_placed") is not False for surface in payloads if "order_placed" in surface),
        "real_order_placed": any(surface.get("real_order_placed") is not False for surface in payloads if "real_order_placed" in surface),
        "execution_attempted": any(surface.get("execution_attempted") is not False for surface in payloads if "execution_attempted" in surface),
        "real_order_possible": any(surface.get("real_order_possible") is not False for surface in payloads if "real_order_possible" in surface),
        "secrets_shown": any(surface.get("secrets_shown") is not False for surface in payloads if "secrets_shown" in surface),
        "paper_live_separation_intact": all(surface.get("paper_live_separation_intact") is not False for surface in payloads),
        "sacred_button_can_place_order": sacred["can_place_order"],
        "sacred_button_records_intent_only": sacred["records_intent_only"],
    }


def _sacred_button(cockpit: Mapping[str, Any]) -> dict[str, Any]:
    sacred = cockpit.get("sacred_button_state") if isinstance(cockpit.get("sacred_button_state"), Mapping) else {}
    backend = cockpit.get("backend_authority") if isinstance(cockpit.get("backend_authority"), Mapping) else {}
    can_place_order = sacred.get("can_place_order") if "can_place_order" in sacred else backend.get("sacred_button_can_place_order", False)
    records_intent_only = sacred.get("records_intent_only", True)
    return {
        "can_place_order": bool(can_place_order),
        "records_intent_only": records_intent_only is True,
    }


def _bool_blockers(*checks: tuple[str, bool]) -> list[str]:
    return [message for message, passed in checks if not passed]


def _owner_for_layer(layer: str) -> str:
    if layer in {"final_preflight", "armed_dry_run", "one_tiny_live_order_protocol", "activation_gate", "post_evidence_recheck"}:
        return "CODE"
    if layer in {"evidence_status", "prerequisite_recheck", "active_tuple"}:
        return "OPERATOR"
    if layer in {"paper_live_separation", "secret_safety", "no_order_safety", "cockpit_sacred_button"}:
        return "CODE"
    return "UNKNOWN"


def _severity_for_layer(layer: str) -> str:
    if layer in {"active_tuple", "activation_gate", "cockpit_sacred_button", "paper_live_separation", "secret_safety", "no_order_safety"}:
        return "HIGH"
    if layer in {"final_preflight", "armed_dry_run", "one_tiny_live_order_protocol", "evidence_status", "prerequisite_recheck", "post_evidence_recheck"}:
        return "MEDIUM"
    return "LOW"


def _next_action_for_layer(layer: str) -> str:
    actions = {
        "active_tuple": "Rebuild or rerecord evidence so candidate_id, risk_contract_hash, and packet_hash match across R102-R117.",
        "final_preflight": "Run R102 final-live-preflight and clear reported blockers.",
        "armed_dry_run": "Run R104 tiny-live-armed-dry-run after R102 is READY.",
        "one_tiny_live_order_protocol": "Run R105 one-tiny-live-order-protocol and clear protocol blockers.",
        "activation_gate": "Run R106 first-live-activation-gate and keep it as the activation authority.",
        "cockpit_sacred_button": "Verify R109 cockpit state keeps the sacred button intent-only.",
        "evidence_status": "Record only personally verified R112 evidence, then rerun evidence status.",
        "prerequisite_recheck": "Run R113 prerequisite recheck after evidence.",
        "post_evidence_recheck": "Run R117 post-evidence gate recheck after R112/R113 are ready.",
        "paper_live_separation": "Stop and repair the source reporting paper/live separation false before continuing.",
        "secret_safety": "Stop and remove secret exposure from the reporting surface before continuing.",
        "no_order_safety": "Stop; investigate any source that reports order placement or execution attempt.",
    }
    return actions.get(layer, "Review this layer and rerun the command.")


def _source_surfaces(**surfaces: Mapping[str, Any] | None) -> list[str]:
    result = [SOURCE_SURFACE]
    for name, surface in surfaces.items():
        if not isinstance(surface, Mapping):
            if name == "assisted_run":
                result.append("R116 first-live-evidence-assisted-run ledger")
            continue
        result.append(f"R118 source: {name}")
        result.extend(str(item) for item in surface.get("source_surfaces_used") or [])
    return list(dict.fromkeys(result))


def _ledger_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "event_type",
        "final_review_id",
        "recorded_at_utc",
        "status",
        "active_tuple",
        "source_statuses",
        "readiness_matrix",
        "authorization_request_readiness",
        "remaining_blockers",
        "live_ready",
        "execution_enabled_by_final_review",
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
