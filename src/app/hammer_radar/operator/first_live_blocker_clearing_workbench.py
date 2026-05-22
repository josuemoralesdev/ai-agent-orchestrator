"""R119 first-live blocker clearing workbench.

This module turns R118 final-review blockers into exact operator clearing
lanes. It is decision support only and never creates execution authority.
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
    build_first_live_activation_final_review,
)
from src.app.hammer_radar.operator.first_live_evidence_assisted_run import (
    CONFIRMATION_PHRASE,
    SUPPORTED_GROUPS,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

WORKBENCH_READY = "WORKBENCH_READY"
WORKBENCH_BLOCKED_UNSAFE = "WORKBENCH_BLOCKED_UNSAFE"
EVENT_TYPE = "FIRST_LIVE_BLOCKER_CLEARING_WORKBENCH"
LEDGER_FILENAME = "first_live_blocker_clearing_workbench.ndjson"
SOURCE_SURFACE = "operator.first_live_blocker_clearing_workbench.build_first_live_blocker_clearing_workbench"

SAFETY_FALSE_FIELDS = {
    "live_ready",
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "real_order_possible",
    "secrets_shown",
}


def _cmd(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


def build_first_live_blocker_clearing_workbench(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    checked_at = datetime.now(UTC).isoformat()
    final_review = build_first_live_activation_final_review(
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=env,
        record=False,
    )
    source_statuses = _source_statuses(final_review)
    active_tuple = _active_tuple(final_review)
    clearing_lanes = _clearing_lanes(source_statuses=source_statuses, active_tuple=active_tuple)
    unsafe_reasons = _unsafe_reasons(final_review)
    status = WORKBENCH_BLOCKED_UNSAFE if unsafe_reasons else WORKBENCH_READY

    payload = {
        "event_type": EVENT_TYPE,
        "workbench_id": uuid4().hex,
        "recorded_at_utc": checked_at,
        "checked_at_utc": checked_at,
        "status": status,
        "unsafe_reasons": unsafe_reasons,
        "live_ready": False,
        "execution_enabled_by_workbench": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "active_tuple": active_tuple,
        "source_statuses": source_statuses,
        "clearing_lanes": clearing_lanes,
        "immediate_operator_sequence": _immediate_operator_sequence(),
        "assisted_evidence_commands": _assisted_evidence_commands(),
        "status_recheck_pack": _status_recheck_pack(),
        "stop_conditions": _stop_conditions(),
        "authorization_boundary": _authorization_boundary(),
        "next_phase_recommendation": _next_phase_recommendation(final_review),
        "source_surfaces_used": _source_surfaces(final_review),
        "ledger_path": str(first_live_blocker_clearing_workbench_path(resolved_log_dir)),
        "paper_live_separation_intact": "paper_live_separation_intact false" not in unsafe_reasons,
    }
    payload = _sanitize(payload)
    if record:
        append_first_live_blocker_clearing_workbench(payload, log_dir=resolved_log_dir)
    return payload


def append_first_live_blocker_clearing_workbench(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_blocker_clearing_workbench_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_ledger_record(record), sort_keys=True) + "\n")


def load_first_live_blocker_clearing_workbenches(
    *,
    limit: int = 50,
    workbench_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_blocker_clearing_workbench_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = _sanitize(json.loads(line))
            if workbench_id is not None and record.get("workbench_id") != workbench_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_blocker_clearing_workbench_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_first_live_blocker_clearing_workbench_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _source_statuses(final_review: Mapping[str, Any]) -> dict[str, Any]:
    statuses = final_review.get("source_statuses") if isinstance(final_review.get("source_statuses"), Mapping) else {}
    return {
        "R102 final preflight": statuses.get("R102 final preflight"),
        "R104 tiny live armed dry run": statuses.get("R104 tiny live armed dry run"),
        "R105 protocol": statuses.get("R105 protocol"),
        "R106 activation gate": statuses.get("R106 activation gate"),
        "R109 cockpit": statuses.get("R109 cockpit"),
        "R112 evidence status": statuses.get("R112 evidence status"),
        "R113 prerequisite recheck": statuses.get("R113 prerequisite recheck"),
        "R116 assisted run": statuses.get("R116 assisted run")
        or statuses.get("R116 assisted run latest status"),
        "R117 post-evidence recheck": statuses.get("R117 post-evidence recheck"),
        "R118 final review": final_review.get("status"),
    }


def _active_tuple(final_review: Mapping[str, Any]) -> dict[str, Any]:
    active = final_review.get("active_tuple") if isinstance(final_review.get("active_tuple"), Mapping) else {}
    return {
        "candidate_id": active.get("candidate_id"),
        "risk_contract_hash": active.get("risk_contract_hash"),
        "packet_hash": active.get("packet_hash"),
        "tuple_status": active.get("tuple_status") or "MISSING",
        "source": active.get("source") or "R118 final review",
    }


def _clearing_lanes(*, source_statuses: Mapping[str, Any], active_tuple: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        _lane(
            lane_id="evidence_records_lane",
            title="Record personally verified R112 evidence",
            blocker_sources=["R112 evidence status", "R113 prerequisite recheck", "R117 post-evidence recheck", "R118 final review"],
            owner="OPERATOR",
            current_status=source_statuses.get("R112 evidence status"),
            target_status="EVIDENCE_READY_FOR_PREREQ_RECHECK",
            can_clear_now=active_tuple.get("tuple_status") == "CONSISTENT",
            commands=[_cmd("first-live-evidence-assisted-run --all-groups")],
            evidence_commands=[
                _cmd(f"first-live-evidence-assisted-run --group {group} --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\"")
                for group in SUPPORTED_GROUPS
            ],
            verification_commands=[_cmd("first-live-evidence-status"), _cmd("first-live-prerequisite-recheck-after-evidence")],
            stop_conditions=["active tuple changed", "evidence note includes secrets", "order placed true", "execution attempted true"],
            safety_notes=["Evidence recording is audit-only and does not authorize execution."],
        ),
        _lane(
            lane_id="candidate_freshness_lane",
            title="Confirm active tuple and market freshness",
            blocker_sources=["R102 final preflight", "R104 tiny live armed dry run", "R118 final review"],
            owner="MARKET",
            current_status=source_statuses.get("R102 final preflight"),
            target_status="READY",
            can_clear_now=True,
            commands=[_cmd("final-live-preflight"), _cmd("tiny-live-armed-dry-run --no-record")],
            evidence_commands=[],
            verification_commands=[_cmd("first-live-activation-final-review --no-record")],
            stop_conditions=["candidate stale", "active tuple changed", "R118 does not say ready"],
            safety_notes=["Freshness review is read-only and must not place orders."],
        ),
        _lane(
            lane_id="approval_records_lane",
            title="Verify approval-intent and human review records",
            blocker_sources=["R106 activation gate", "R112 evidence status", "R113 prerequisite recheck"],
            owner="OPERATOR",
            current_status=source_statuses.get("R106 activation gate"),
            target_status="approval evidence present and R106 rechecked",
            can_clear_now=True,
            commands=[_cmd("first-live-prerequisite-clearing")],
            evidence_commands=[_cmd(f"first-live-evidence-assisted-run --group approval_records --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\"")],
            verification_commands=[_cmd("first-live-evidence-status"), _cmd("first-live-prerequisite-recheck-after-evidence")],
            stop_conditions=["active tuple changed", "evidence note includes secrets", "R106 remains blocked after evidence"],
            safety_notes=["Approval evidence records intent only; it is not execution authority."],
        ),
        _lane(
            lane_id="binance_credentials_lane",
            title="Review Binance credential presence without exposing values",
            blocker_sources=["R102 final preflight", "R105 protocol", "R106 activation gate"],
            owner="CONFIG",
            current_status=source_statuses.get("R102 final preflight"),
            target_status="credential presence reviewed without secret exposure",
            can_clear_now=True,
            requires_secret_handling=True,
            commands=[_cmd("final-live-preflight"), _cmd("one-tiny-live-order-protocol --no-record")],
            evidence_commands=[],
            verification_commands=[_cmd("first-live-activation-final-review --no-record")],
            stop_conditions=["secrets shown", "env flag change attempted", "Binance order endpoint appears"],
            safety_notes=["Report presence booleans only; never paste keys, signatures, tokens, or env values."],
        ),
        _lane(
            lane_id="account_funding_read_only_lane",
            title="Confirm account and funding readiness through read-only operator review",
            blocker_sources=["R105 protocol", "R112 evidence status", "R113 prerequisite recheck"],
            owner="EXCHANGE",
            current_status=source_statuses.get("R105 protocol"),
            target_status="ACCOUNT_FUNDING_READ_ONLY_CHECK evidence accepted",
            can_clear_now=True,
            commands=[_cmd("one-tiny-live-order-protocol --no-record")],
            evidence_commands=[_cmd(f"first-live-evidence-assisted-run --group account_and_funding --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\"")],
            verification_commands=[_cmd("first-live-evidence-status"), _cmd("first-live-prerequisite-recheck-after-evidence")],
            stop_conditions=["Binance order endpoint appears", "secrets shown", "order placed true"],
            safety_notes=["Read-only review must not call account-changing, order, funding-transfer, or permission-changing endpoints."],
        ),
        _lane(
            lane_id="protective_orders_lane",
            title="Review protective stop and take-profit readiness",
            blocker_sources=["R102 final preflight", "R105 protocol", "R112 evidence status"],
            owner="OPERATOR",
            current_status=source_statuses.get("R105 protocol"),
            target_status="PROTECTIVE_ORDERS_REVIEWED evidence accepted",
            can_clear_now=True,
            commands=[_cmd("first-live-prerequisite-clearing")],
            evidence_commands=[_cmd(f"first-live-evidence-assisted-run --group protective_orders --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\"")],
            verification_commands=[_cmd("first-live-evidence-status"), _cmd("first-live-prerequisite-recheck-after-evidence")],
            stop_conditions=["order placed true", "execution attempted true", "R118 does not say ready"],
            safety_notes=["Protective-order review is evidence only; do not submit live protective orders from R119."],
        ),
        _lane(
            lane_id="live_adapter_boundary_lane",
            title="Verify live adapter boundary remains non-executing",
            blocker_sources=["R102 final preflight", "R105 protocol", "R112 evidence status"],
            owner="CODE",
            current_status=source_statuses.get("R102 final preflight"),
            target_status="LIVE_ADAPTER_BOUNDARY_REVIEWED evidence accepted",
            can_clear_now=True,
            requires_live_order_capability=False,
            commands=[_cmd("final-live-preflight")],
            evidence_commands=[_cmd(f"first-live-evidence-assisted-run --group adapter_boundary --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\"")],
            verification_commands=[_cmd("first-live-evidence-status"), _cmd("first-live-activation-final-review --no-record")],
            stop_conditions=["real_order_possible true from any non-execution phase", "Binance order endpoint appears"],
            safety_notes=["Adapter readiness is not authorization and must not make a real order possible."],
        ),
        _lane(
            lane_id="tiny_size_max_loss_lane",
            title="Verify tiny size and max-loss caps",
            blocker_sources=["R105 protocol", "R112 evidence status", "R113 prerequisite recheck"],
            owner="OPERATOR",
            current_status=source_statuses.get("R113 prerequisite recheck"),
            target_status="TINY_SIZE_MAX_LOSS_DEFINED evidence accepted",
            can_clear_now=True,
            commands=[_cmd("first-live-prerequisite-clearing")],
            evidence_commands=[_cmd(f"first-live-evidence-assisted-run --group risk_limits --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\"")],
            verification_commands=[_cmd("first-live-prerequisite-recheck-after-evidence")],
            stop_conditions=["active tuple changed", "R106 remains blocked after evidence"],
            safety_notes=["Caps are review evidence only; R119 cannot size or place an order."],
        ),
        _lane(
            lane_id="environment_flags_review_lane",
            title="Review environment flags without modifying them",
            blocker_sources=["R102 final preflight", "R112 evidence status"],
            owner="CONFIG",
            current_status=source_statuses.get("R102 final preflight"),
            target_status="ENVIRONMENT_FLAGS_REVIEWED evidence accepted",
            can_clear_now=True,
            requires_env_change=False,
            commands=[_cmd("final-live-preflight")],
            evidence_commands=[_cmd(f"first-live-evidence-assisted-run --group environment_review --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\"")],
            verification_commands=[_cmd("first-live-evidence-status")],
            stop_conditions=["env flag change attempted", "secrets shown", "paper_live_separation_intact false"],
            safety_notes=["Do not edit .env or live flags in R119."],
        ),
        _lane(
            lane_id="sacred_button_safety_lane",
            title="Verify R109 sacred button remains intent-only",
            blocker_sources=["R109 cockpit", "R117 post-evidence recheck", "R118 final review"],
            owner="OPERATOR",
            current_status=source_statuses.get("R109 cockpit"),
            target_status="can_place_order=false and records_intent_only=true",
            can_clear_now=True,
            commands=["curl -s http://127.0.0.1:8015/operator/approval-cockpit/state"],
            evidence_commands=[_cmd(f"first-live-evidence-assisted-run --group sacred_button_review --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\"")],
            verification_commands=[_cmd("first-live-post-evidence-gate-recheck --no-record"), _cmd("first-live-activation-final-review --no-record")],
            stop_conditions=["sacred button can_place_order true", "sacred button records_intent_only false"],
            safety_notes=["If the sacred button can place orders, stop immediately."],
        ),
        _lane(
            lane_id="final_gate_recheck_lane",
            title="Run final post-evidence and activation-gate rechecks",
            blocker_sources=["R106 activation gate", "R117 post-evidence recheck", "R118 final review"],
            owner="CODE",
            current_status=source_statuses.get("R118 final review"),
            target_status="READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION",
            can_clear_now=True,
            commands=[_cmd("first-live-post-evidence-gate-recheck"), _cmd("first-live-activation-final-review")],
            evidence_commands=[],
            verification_commands=[_cmd("first-live-activation-gate"), _cmd("first-live-activation-final-review")],
            stop_conditions=["R106 remains blocked after evidence", "R118 does not say ready"],
            safety_notes=["R118 ready only prepares a later explicit authorization request; it does not authorize execution."],
        ),
        _lane(
            lane_id="future_authorization_lane",
            title="Hold future explicit authorization until R118 is ready",
            blocker_sources=["R118 final review"],
            owner="FUTURE_AUTHORIZATION",
            current_status=source_statuses.get("R118 final review"),
            target_status="future R120/R119.5 explicit authorization request may be prepared",
            can_clear_now=False,
            commands=[],
            evidence_commands=[],
            verification_commands=[_cmd("first-live-activation-final-review")],
            stop_conditions=["R118 does not say ready", "order placed true", "execution attempted true"],
            safety_notes=["R119 cannot request authorization and cannot place orders."],
        ),
    ]


def _lane(
    *,
    lane_id: str,
    title: str,
    blocker_sources: list[str],
    owner: str,
    current_status: Any,
    target_status: str,
    can_clear_now: bool,
    commands: list[str],
    evidence_commands: list[str],
    verification_commands: list[str],
    stop_conditions: list[str],
    safety_notes: list[str],
    requires_secret_handling: bool = False,
    requires_env_change: bool = False,
    requires_live_order_capability: bool = False,
) -> dict[str, Any]:
    return {
        "lane_id": lane_id,
        "title": title,
        "blocker_sources": blocker_sources,
        "owner": owner,
        "current_status": current_status,
        "target_status": target_status,
        "can_clear_now": can_clear_now,
        "requires_secret_handling": requires_secret_handling,
        "requires_env_change": requires_env_change,
        "requires_live_order_capability": requires_live_order_capability,
        "commands": commands,
        "evidence_commands": evidence_commands,
        "verification_commands": verification_commands,
        "stop_conditions": stop_conditions,
        "safety_notes": safety_notes,
    }


def _immediate_operator_sequence() -> list[dict[str, Any]]:
    steps = [
        "Confirm current active tuple and freshness.",
        "Run R116 preview for all groups.",
        "Record only personally verified evidence using R116 execute-evidence with exact confirmation.",
        "Run R112 evidence status.",
        "Run R113 prerequisite recheck.",
        "Run R117 post-evidence gate recheck.",
        "Run R118 final review.",
        "If R118 remains blocked, follow remaining clearing lanes.",
        "Do not request authorization until R118 says ready.",
        "Never place order from R119.",
    ]
    return [{"step": index, "action": action} for index, action in enumerate(steps, start=1)]


def _assisted_evidence_commands() -> dict[str, Any]:
    return {
        "preview_all_groups": _cmd("first-live-evidence-assisted-run --all-groups"),
        "preview_each_group": {group: _cmd(f"first-live-evidence-assisted-run --group {group}") for group in SUPPORTED_GROUPS},
        "rejected_execute_example": _cmd("first-live-evidence-assisted-run --group sacred_button_review --execute-evidence --confirm-evidence-only \"WRONG CONFIRMATION\""),
        "valid_execute_template": {
            "label": "OPERATOR_REVIEW_REQUIRED",
            "confirmation_phrase": CONFIRMATION_PHRASE,
            "command": _cmd(f"first-live-evidence-assisted-run --group <group> --execute-evidence --confirm-evidence-only \"{CONFIRMATION_PHRASE}\""),
        },
    }


def _status_recheck_pack() -> dict[str, str]:
    return {
        "first-live-evidence-status": _cmd("first-live-evidence-status"),
        "first-live-prerequisite-recheck-after-evidence": _cmd("first-live-prerequisite-recheck-after-evidence"),
        "first-live-prerequisite-clearing": _cmd("first-live-prerequisite-clearing"),
        "first-live-burn-down": _cmd("first-live-burn-down"),
        "first-live-post-evidence-gate-recheck": _cmd("first-live-post-evidence-gate-recheck"),
        "first-live-activation-final-review": _cmd("first-live-activation-final-review"),
        "first-live-activation-gate": _cmd("first-live-activation-gate"),
        "approval cockpit state curl": "curl -s http://127.0.0.1:8015/operator/approval-cockpit/state",
    }


def _stop_conditions() -> list[str]:
    return [
        "active tuple changed",
        "candidate stale",
        "R106 remains blocked after evidence",
        "sacred button can_place_order true",
        "sacred button records_intent_only false",
        "paper_live_separation_intact false",
        "secrets shown",
        "order placed true",
        "execution attempted true",
        "real_order_possible true from any non-execution phase",
        "env flag change attempted",
        "Binance order endpoint appears",
        "evidence note includes secrets",
        "R118 does not say ready",
    ]


def _authorization_boundary() -> dict[str, Any]:
    return {
        "R119 cannot request authorization": True,
        "R119 cannot authorize execution": True,
        "R119 cannot place orders": True,
        "R119 only organizes clearing work": True,
        "R119 prepares a future R120/R119.5 only if R118 becomes ready": True,
        "execution_authority_created": False,
        "live_order_endpoint_created": False,
    }


def _next_phase_recommendation(final_review: Mapping[str, Any]) -> dict[str, Any]:
    ready = final_review.get("status") == "READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION"
    return {
        "if_blockers_remain": "R120 should be targeted clearing for the highest remaining lane.",
        "if_R118_becomes_ready_after_evidence": "R120 may become explicit authorization request, still non-executing by default.",
        "recommended_path_now": "explicit_authorization_request" if ready else "targeted_clearing",
        "r118_status": final_review.get("status"),
    }


def _unsafe_reasons(value: Any) -> list[str]:
    reasons: list[str] = []

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, raw in item.items():
                key_text = str(key)
                next_path = f"{path}.{key_text}" if path else key_text
                if key_text in SAFETY_FALSE_FIELDS and raw is not False:
                    reasons.append(f"{key_text} {str(raw).lower()}")
                elif key_text == "paper_live_separation_intact" and raw is False:
                    reasons.append("paper_live_separation_intact false")
                elif key_text in {"can_place_order", "sacred_button_can_place_order"} and raw is True:
                    reasons.append("sacred button can_place_order true")
                elif key_text in {"records_intent_only", "sacred_button_records_intent_only"} and raw is False:
                    reasons.append("sacred button records_intent_only false")
                elif key_text == "execution_enabled_by_workbench" and raw is not False:
                    reasons.append("execution_enabled_by_workbench true")
                visit(raw, next_path)
        elif isinstance(item, list):
            for index, raw in enumerate(item):
                visit(raw, f"{path}[{index}]")

    visit(value, "")
    return sorted(set(reasons))


def _source_surfaces(final_review: Mapping[str, Any]) -> list[str]:
    surfaces = [SOURCE_SURFACE, "R118 first-live-activation-final-review"]
    surfaces.extend(str(item) for item in final_review.get("source_surfaces_used") or [])
    return list(dict.fromkeys(surfaces))


def _ledger_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "event_type",
        "workbench_id",
        "recorded_at_utc",
        "status",
        "active_tuple",
        "source_statuses",
        "clearing_lanes",
        "immediate_operator_sequence",
        "live_ready",
        "execution_enabled_by_workbench",
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
