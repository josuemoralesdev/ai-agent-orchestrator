"""R141 post-clearing live-ready recheck and watcher handoff.

This module composes existing R138/R139/R140 and lane readiness status builders
after safe clearing. It is diagnostic only: it never runs a watcher loop,
creates payloads, signs requests, calls Binance, mutates env/config, changes
live flags, disables kill switches, or places orders.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.autonomous_lane_live_ready_burn_down import (
    DEFAULT_LANE_KEY,
    SAFETY as R138_SAFETY,
    build_autonomous_lane_live_ready_burn_down,
    build_operator_burn_down_command_pack,
    collect_live_ready_source_statuses,
)
from src.app.hammer_radar.operator.live_ready_blocker_clearing_operator_pack import (
    build_live_ready_blocker_clearing_operator_pack,
)
from src.app.hammer_radar.operator.operator_executes_safe_clearing_pack import (
    load_safe_clearing_pack_run_records,
)

POST_CLEARING_RECHECK_READY = "POST_CLEARING_RECHECK_READY"
POST_CLEARING_RECHECK_BLOCKED = "POST_CLEARING_RECHECK_BLOCKED"
POST_CLEARING_RECHECK_REJECTED = "POST_CLEARING_RECHECK_REJECTED"
POST_CLEARING_RECHECK_ERROR = "POST_CLEARING_RECHECK_ERROR"

WAIT_FOR_FRESH_CANDIDATE = "WAIT_FOR_FRESH_CANDIDATE"
RECORD_AUTONOMOUS_PAPER_PROOF = "RECORD_AUTONOMOUS_PAPER_PROOF"
AUTHORIZE_TINY_LIVE_LANE = "AUTHORIZE_TINY_LIVE_LANE"
RERUN_GLOBAL_GATES = "RERUN_GLOBAL_GATES"
RERUN_PROTECTIVE_BOUNDARIES = "RERUN_PROTECTIVE_BOUNDARIES"
LIVE_READY_REVIEW_NEXT = "LIVE_READY_REVIEW_NEXT"
STOP_STILL_BLOCKED = "STOP_STILL_BLOCKED"

NEXT_OPERATOR_MOVES = {
    WAIT_FOR_FRESH_CANDIDATE,
    RECORD_AUTONOMOUS_PAPER_PROOF,
    AUTHORIZE_TINY_LIVE_LANE,
    RERUN_GLOBAL_GATES,
    RERUN_PROTECTIVE_BOUNDARIES,
    LIVE_READY_REVIEW_NEXT,
    STOP_STILL_BLOCKED,
}

EVENT_TYPE = "POST_CLEARING_LIVE_READY_RECHECK"
LEDGER_FILENAME = "post_clearing_live_ready_rechecks.ndjson"
CONFIRM_POST_CLEARING_RECHECK_PHRASE = (
    "I CONFIRM POST CLEARING RECHECK RECORDING ONLY; NO ORDER; NO BINANCE CALL."
)

SAFETY = {
    **R138_SAFETY,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "config_written": False,
    "global_live_flags_changed": False,
}

SAFE_COMMAND_FORBIDDEN_TERMS = (
    "binance",
    "/fapi/v1/order",
    "execute_live_order",
    "submit_test_order",
    "submit_protective_test",
    "build_signed",
    "signature",
    "api_secret",
    "api_key=",
    " export ",
    "sed -i",
    "--apply",
    "--execute-safe-clearing",
    "--record-",
    "--record_",
    "--confirm-",
    "systemctl",
    "sudo",
    "HAMMER_ALLOW_LIVE_ORDERS=true",
    "HAMMER_GLOBAL_KILL_SWITCH=false",
)

SOURCE_SURFACES_USED = [
    "operator.autonomous_lane_live_ready_burn_down.collect_live_ready_source_statuses",
    "operator.autonomous_lane_live_ready_burn_down.build_autonomous_lane_live_ready_burn_down",
    "operator.live_ready_blocker_clearing_operator_pack.build_live_ready_blocker_clearing_operator_pack",
    "operator.operator_executes_safe_clearing_pack.load_safe_clearing_pack_run_records",
    "operator.autonomous_paper_lane_executor_integration via R138 source_statuses",
    "operator.fresh_signal_router via R138 source_statuses",
    "operator.lane_autonomy_scheduler via R129/R138 source_statuses",
    "operator.lane_autonomy_control_loop via R129/R138 source_statuses",
    "operator.first_tiny_live_lane_execution_gate via R138 source_statuses",
    "operator.first_tiny_live_autonomous_lane_authorization via R138 source_statuses",
    "operator.live_lane_kill_switch_rehearsal via R138 source_statuses",
    "operator.live_adapter_boundary_final_review via R138 source_statuses",
    "operator.first_tiny_live_order_payload_dry_authorization via R138 source_statuses",
    "operator.protective_order_dry_policy_review via R138 source_statuses",
    "operator.protective_payload_dry_preview_boundary via R138 source_statuses",
    "operator.final_live_preflight via R138 source_statuses",
    "operator.first_live_activation_gate via R138 source_statuses",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_post_clearing_live_ready_recheck(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    record_recheck: bool = False,
    confirm_post_clearing_recheck: str | None = None,
    source_statuses: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_post_clearing_recheck == CONFIRM_POST_CLEARING_RECHECK_PHRASE
    try:
        statuses = (
            _sanitize(dict(source_statuses))
            if source_statuses is not None
            else collect_post_clearing_source_statuses(
                log_dir=resolved_log_dir,
                lane_key=lane_key,
                now=generated_at,
            )
        )
        burn_down = build_autonomous_lane_live_ready_burn_down(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            source_statuses=statuses,
            now=generated_at,
        )
        operator_pack = build_live_ready_blocker_clearing_operator_pack(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            burn_down=burn_down,
            source_statuses=statuses,
            now=generated_at,
        )
        safe_clearing_comparison = compare_safe_clearing_to_current_burn_down(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            burn_down=burn_down,
        )
        fresh_candidate_status = _fresh_candidate_status(statuses)
        paper_proof_status = _paper_proof_status(statuses)
        lane_mode_status = _lane_mode_status(statuses)
        gate_statuses = _gate_statuses(statuses)
        protective_statuses = _protective_statuses(statuses)
        credential_adapter_statuses = _credential_adapter_statuses(statuses)
        blocker_summary = _blocker_summary(burn_down, operator_pack)
        safety = _combined_safety(statuses, burn_down, operator_pack)
        next_move = determine_next_operator_move(
            source_statuses=statuses,
            fresh_candidate_status=fresh_candidate_status,
            paper_proof_status=paper_proof_status,
            lane_mode_status=lane_mode_status,
            gate_statuses=gate_statuses,
            protective_statuses=protective_statuses,
            credential_adapter_statuses=credential_adapter_statuses,
            safety=safety,
        )
        probability_update = _probability_update(
            burn_down=burn_down,
            next_operator_move=next_move,
            fresh_candidate_status=fresh_candidate_status,
        )
        watcher_mode_handoff = (
            build_watcher_mode_handoff(lane_key=lane_key)
            if next_move == WAIT_FOR_FRESH_CANDIDATE
            else {"enabled_recommendation": False, "mode": "NOT_RECOMMENDED_NOW", "reason": next_move}
        )
        recommended_commands = _recommended_commands(lane_key=lane_key)
        payload = _sanitize(
            {
                "status": POST_CLEARING_RECHECK_READY
                if next_move == LIVE_READY_REVIEW_NEXT
                else POST_CLEARING_RECHECK_BLOCKED,
                "generated_at": generated_at.isoformat(),
                "lane_key": lane_key,
                "live_ready_now": False,
                "next_operator_move": next_move,
                "why": _why(next_move, fresh_candidate_status, paper_proof_status, lane_mode_status, gate_statuses, protective_statuses),
                "source_statuses": statuses,
                "fresh_candidate_status": fresh_candidate_status,
                "paper_proof_status": paper_proof_status,
                "lane_mode_status": lane_mode_status,
                "gate_statuses": gate_statuses,
                "protective_statuses": protective_statuses,
                "credential_adapter_statuses": credential_adapter_statuses,
                "blocker_summary": blocker_summary,
                "probability_update": probability_update,
                "watcher_mode_handoff": watcher_mode_handoff,
                "recommended_commands": recommended_commands,
                "do_not_run_yet": _do_not_run_yet(),
                "record_recheck_requested": bool(record_recheck),
                "confirmation_valid": False,
                "recheck_recorded": False,
                "recheck_id": None,
                "safe_clearing_comparison": safe_clearing_comparison,
                "paper_proof_capture_plan": build_paper_proof_capture_plan(lane_key=lane_key),
                "tiny_live_authorization_readiness": build_tiny_live_authorization_readiness(
                    paper_proof_status=paper_proof_status,
                    lane_mode_status=lane_mode_status,
                    gate_statuses=gate_statuses,
                ),
                "safety": safety,
                "source_surfaces_used": _source_surfaces(statuses, burn_down, operator_pack),
            }
        )
        if not _safety_clean(safety):
            payload["status"] = POST_CLEARING_RECHECK_BLOCKED
            payload["next_operator_move"] = STOP_STILL_BLOCKED
            payload["why"] = "Safety boundary reported a true unsafe flag; stop and inspect before any next step."
        if not record_recheck:
            return payload
        if not confirmation_valid:
            return _sanitize(
                {
                    **payload,
                    "status": POST_CLEARING_RECHECK_REJECTED,
                    "record_recheck_requested": True,
                    "confirmation_valid": False,
                    "recheck_recorded": False,
                    "recording_blockers": ["exact R141 post-clearing recheck recording confirmation phrase is required"],
                }
            )
        record = append_post_clearing_recheck_record(payload, log_dir=resolved_log_dir)
        return _sanitize(
            {
                **payload,
                "record_recheck_requested": True,
                "confirmation_valid": True,
                "recheck_recorded": True,
                "recheck_id": record["recheck_id"],
                "ledger_path": str(post_clearing_recheck_records_path(resolved_log_dir)),
            }
        )
    except Exception as exc:  # pragma: no cover - defensive diagnostic boundary
        return _sanitize(
            {
                "status": POST_CLEARING_RECHECK_ERROR,
                "generated_at": generated_at.isoformat(),
                "lane_key": lane_key,
                "live_ready_now": False,
                "next_operator_move": STOP_STILL_BLOCKED,
                "why": f"R141 source collection failed at diagnostic boundary: {exc.__class__.__name__}",
                "source_statuses": {"error": exc.__class__.__name__},
                "fresh_candidate_status": {"has_fresh_routed_candidate": False},
                "paper_proof_status": {"paper_proof_exists": False},
                "lane_mode_status": {"lane_mode": "unknown"},
                "gate_statuses": {},
                "protective_statuses": {},
                "credential_adapter_statuses": {},
                "blocker_summary": {},
                "probability_update": {"tiny_live_tonight_pct": 0, "tiny_live_next_session_pct": 0, "reason": "source collection error"},
                "watcher_mode_handoff": {"enabled_recommendation": False, "mode": "ERROR"},
                "recommended_commands": _recommended_commands(lane_key=lane_key),
                "do_not_run_yet": _do_not_run_yet(),
                "record_recheck_requested": bool(record_recheck),
                "confirmation_valid": False,
                "recheck_recorded": False,
                "recheck_id": None,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def collect_post_clearing_source_statuses(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    return collect_live_ready_source_statuses(log_dir=log_dir, lane_key=lane_key, now=now)


def compare_safe_clearing_to_current_burn_down(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    burn_down: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    records = load_safe_clearing_pack_run_records(log_dir=log_dir, lane_key=lane_key, limit=1)
    latest = records[0] if records else {}
    current_summary = _mapping((burn_down or {}).get("blocker_summary"))
    latest_delta = _mapping(latest.get("clearing_delta"))
    latest_blockers = _mapping(latest_delta.get("blocker_counts"))
    return _sanitize(
        {
            "latest_r140_run_found": bool(latest),
            "latest_r140_run_id": latest.get("run_id"),
            "latest_r140_status": latest.get("status"),
            "latest_r140_probability_movement": latest.get("probability_movement") or {},
            "latest_r140_blocker_delta": latest_blockers.get("delta_total"),
            "current_burn_down_status": (burn_down or {}).get("status"),
            "current_ranked_blocker_count": int(current_summary.get("total_count") or len(list((burn_down or {}).get("ranked_blockers") or []))),
            "current_live_ready_now": bool((burn_down or {}).get("live_ready_now")),
            "interpretation": "R141 does not execute clearing; it compares the latest R140 evidence to the current R138 burn-down.",
        }
    )


def determine_next_operator_move(
    *,
    source_statuses: Mapping[str, Any],
    fresh_candidate_status: Mapping[str, Any] | None = None,
    paper_proof_status: Mapping[str, Any] | None = None,
    lane_mode_status: Mapping[str, Any] | None = None,
    gate_statuses: Mapping[str, Any] | None = None,
    protective_statuses: Mapping[str, Any] | None = None,
    credential_adapter_statuses: Mapping[str, Any] | None = None,
    safety: Mapping[str, Any] | None = None,
) -> str:
    fresh = _mapping(fresh_candidate_status) or _fresh_candidate_status(source_statuses)
    paper = _mapping(paper_proof_status) or _paper_proof_status(source_statuses)
    lane = _mapping(lane_mode_status) or _lane_mode_status(source_statuses)
    gates = _mapping(gate_statuses) or _gate_statuses(source_statuses)
    protective = _mapping(protective_statuses) or _protective_statuses(source_statuses)
    credentials = _mapping(credential_adapter_statuses) or _credential_adapter_statuses(source_statuses)
    safe = _mapping(safety) or _combined_safety(source_statuses)

    if not _safety_clean(safe):
        return STOP_STILL_BLOCKED
    if not fresh.get("has_fresh_routed_candidate") or paper.get("stale_candidates_only"):
        return WAIT_FOR_FRESH_CANDIDATE
    if int(paper.get("paper_eligible_decisions_count") or 0) > 0 and not paper.get("paper_proof_exists"):
        return RECORD_AUTONOMOUS_PAPER_PROOF
    if paper.get("paper_proof_exists") and lane.get("lane_mode") != "tiny_live":
        return AUTHORIZE_TINY_LIVE_LANE
    if lane.get("lane_mode") == "tiny_live":
        if protective.get("protective_blocked"):
            return RERUN_PROTECTIVE_BOUNDARIES
        if gates.get("global_gate_blocked") or credentials.get("credential_or_adapter_blocked"):
            return RERUN_GLOBAL_GATES
        if gates.get("all_near_ready") and not protective.get("protective_blocked"):
            return LIVE_READY_REVIEW_NEXT
    return STOP_STILL_BLOCKED


def build_fresh_candidate_wait_plan(*, lane_key: str = DEFAULT_LANE_KEY) -> dict[str, Any]:
    return {
        "mode": "WAIT_FOR_FRESH_CANDIDATE",
        "lane_key": lane_key,
        "safe_next_step": "Run read-only router/scheduler/paper previews until a fresh eligible paper decision exists.",
        "do_not_clear_more_gates_without_market_evidence": True,
        "safe_watch_commands": _watch_commands(lane_key),
        "stop_conditions": [
            "fresh eligible paper decision captured",
            "safety violation",
            "router error",
            "lane config changed unexpectedly",
            "operator stops watcher",
            "time limit reached",
        ],
    }


def build_paper_proof_capture_plan(*, lane_key: str = DEFAULT_LANE_KEY) -> dict[str, Any]:
    return {
        "mode": "PAPER_PROOF_CAPTURE_PLAN_ONLY",
        "lane_key": lane_key,
        "preview_command": _inspect(f"autonomous-paper-lane-executor-integration --lane-key {json.dumps(lane_key)}"),
        "recording_path": "R129/R140 only after exact paper-only/safe-clearing confirmation and eligible decision evidence.",
        "r141_records_paper_proof": False,
        "creates_orders": False,
    }


def build_tiny_live_authorization_readiness(
    *,
    paper_proof_status: Mapping[str, Any],
    lane_mode_status: Mapping[str, Any],
    gate_statuses: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "paper_proof_exists": bool(paper_proof_status.get("paper_proof_exists")),
        "lane_mode": lane_mode_status.get("lane_mode"),
        "tiny_live_authorization_planning_allowed": bool(
            paper_proof_status.get("paper_proof_exists") and lane_mode_status.get("lane_mode") != "tiny_live"
        ),
        "r126_status": gate_statuses.get("r126_tiny_live_gate_status"),
        "r130_status": gate_statuses.get("r130_authorization_status"),
        "r141_authorizes_tiny_live": False,
    }


def build_watcher_mode_handoff(*, lane_key: str = DEFAULT_LANE_KEY) -> dict[str, Any]:
    return {
        "enabled_recommendation": True,
        "mode": "SAFE_WATCH_ONLY",
        "purpose": "Wait for a fresh routed lane candidate and capture paper proof through R129/R140 when eligible.",
        "watch_interval_seconds_recommended": 60,
        "max_runtime_minutes_recommended": 180,
        "stop_conditions": [
            "fresh eligible paper decision captured",
            "safety violation",
            "router error",
            "lane config changed unexpectedly",
            "operator stops watcher",
            "time limit reached",
        ],
        "safe_watch_commands": _watch_commands(lane_key),
        "what_to_do_when_fresh_candidate_appears": [
            "Run R129 autonomous-paper-lane-executor-integration preview for the lane.",
            "Run R140 operator-executes-safe-clearing-pack preview.",
            "Record paper proof only through the existing R129/R140 safe confirmation path when eligible.",
            "Rerun R141 post-clearing live-ready recheck after paper proof evidence exists.",
        ],
        "what_not_to_do": _do_not_run_yet(),
        "plan_only": True,
        "daemon_implemented": False,
        "loop_started": False,
        "service_installed": False,
    }


def append_post_clearing_recheck_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = post_clearing_recheck_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "recheck_id": str(record.get("recheck_id") or f"r141_post_clearing_recheck_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "lane_key": record.get("lane_key"),
            "live_ready_now": bool(record.get("live_ready_now")),
            "next_operator_move": record.get("next_operator_move"),
            "why": record.get("why"),
            "fresh_candidate_status": record.get("fresh_candidate_status") or {},
            "paper_proof_status": record.get("paper_proof_status") or {},
            "lane_mode_status": record.get("lane_mode_status") or {},
            "gate_statuses": record.get("gate_statuses") or {},
            "protective_statuses": record.get("protective_statuses") or {},
            "credential_adapter_statuses": record.get("credential_adapter_statuses") or {},
            "blocker_summary": record.get("blocker_summary") or {},
            "probability_update": record.get("probability_update") or {},
            "watcher_mode_handoff": record.get("watcher_mode_handoff") or {},
            "recommended_commands": list(record.get("recommended_commands") or []),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safe_clearing_comparison": record.get("safe_clearing_comparison") or {},
            "safety": record.get("safety") or dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or []),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_post_clearing_recheck_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = post_clearing_recheck_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if lane_key is not None and record.get("lane_key") != lane_key:
                continue
            records.append(_sanitize(record))
    if limit > 0:
        return list(reversed(records))[:limit]
    return records


def summarize_post_clearing_rechecks(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    move_counts = Counter(str(record.get("next_operator_move") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "next_operator_move_counts": dict(sorted(move_counts.items())),
        "last_recheck_id": records[-1].get("recheck_id") if records else None,
        "safety": dict(SAFETY),
    }


def format_post_clearing_live_ready_recheck_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def post_clearing_recheck_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _fresh_candidate_status(source_statuses: Mapping[str, Any]) -> dict[str, Any]:
    router = _mapping(source_statuses.get("fresh_signal_router"))
    routed = [row for row in router.get("routed_candidates") or [] if isinstance(row, Mapping)]
    return {
        "status": router.get("status") or "UNKNOWN",
        "has_fresh_routed_candidate": int(router.get("routed_count") or 0) > 0,
        "routed_count": int(router.get("routed_count") or 0),
        "candidates_seen_count": int(router.get("candidates_seen_count") or 0),
        "expired_count": int(router.get("expired_count") or 0),
        "blocked_count": int(router.get("blocked_count") or 0),
        "fresh_lane_candidates": routed[:5],
        "top_blockers": list(router.get("top_blockers") or []),
    }


def _paper_proof_status(source_statuses: Mapping[str, Any]) -> dict[str, Any]:
    paper = _mapping(source_statuses.get("paper_integration"))
    summary = _mapping(source_statuses.get("paper_integration_records_summary"))
    records_created = int(paper.get("paper_execution_records_created") or 0)
    total_recorded = int(summary.get("paper_execution_records_created") or 0)
    eligible = int(paper.get("paper_eligible_decisions_count") or 0)
    top_blockers = list(paper.get("top_blockers") or [])
    stale_only = eligible <= 0 and any(
        "stale" in json.dumps(item, sort_keys=True).lower()
        or "expired" in json.dumps(item, sort_keys=True).lower()
        or "fresh" in json.dumps(item, sort_keys=True).lower()
        for item in top_blockers
    )
    return {
        "status": paper.get("status") or "UNKNOWN",
        "scheduler_status": paper.get("scheduler_status") or "UNKNOWN",
        "paper_eligible_decisions_count": eligible,
        "paper_blocked_decisions_count": int(paper.get("paper_blocked_decisions_count") or 0),
        "paper_execution_records_created": records_created,
        "paper_execution_records_total_for_lane": total_recorded,
        "integration_recorded": bool(paper.get("integration_recorded")),
        "integration_id": paper.get("integration_id"),
        "paper_proof_exists": bool(records_created > 0 or total_recorded > 0 or paper.get("integration_recorded")),
        "stale_candidates_only": stale_only,
        "top_blockers": top_blockers,
    }


def _lane_mode_status(source_statuses: Mapping[str, Any]) -> dict[str, Any]:
    lane = _mapping(source_statuses.get("lane"))
    mode = str(source_statuses.get("lane_mode") or lane.get("mode") or "missing").strip().lower()
    return {
        "lane_key": lane.get("lane_key"),
        "lane_mode": mode,
        "tiny_live": mode == "tiny_live",
        "config_write_recommended_by_r141": False,
    }


def _gate_statuses(source_statuses: Mapping[str, Any]) -> dict[str, Any]:
    r126 = _surface_status(source_statuses, "r126_tiny_live_gate")
    r130 = _surface_status(source_statuses, "r130_authorization")
    global_gate = _surface_status(source_statuses, "first_live_activation_gate")
    preflight = _surface_status(source_statuses, "final_live_preflight")
    return {
        "r126_tiny_live_gate_status": r126,
        "r130_authorization_status": r130,
        "r131_kill_switch_status": _surface_status(source_statuses, "r131_kill_switch_rehearsal"),
        "r132_adapter_boundary_status": _surface_status(source_statuses, "r132_adapter_boundary"),
        "r134_dry_authorization_status": _surface_status(source_statuses, "r134_dry_authorization"),
        "first_live_activation_gate_status": global_gate,
        "final_live_preflight_status": preflight,
        "global_gate_blocked": _blocked(global_gate) or _blocked(preflight),
        "all_near_ready": not any(_blocked(item) for item in (r126, r130, global_gate, preflight)),
    }


def _protective_statuses(source_statuses: Mapping[str, Any]) -> dict[str, Any]:
    policy = _surface_status(source_statuses, "r136_protective_policy")
    preview = _surface_status(source_statuses, "r137_protective_preview")
    connector = _mapping(source_statuses.get("protective_status"))
    return {
        "r136_protective_policy_status": policy,
        "r137_protective_preview_status": preview,
        "protective_orders_ready": bool(connector.get("protective_orders_ready")),
        "protective_blocked": _blocked(policy) or _blocked(preview) or not bool(connector.get("protective_orders_ready")),
    }


def _credential_adapter_statuses(source_statuses: Mapping[str, Any]) -> dict[str, Any]:
    connector = _mapping(source_statuses.get("connector_status"))
    binance = _mapping(source_statuses.get("binance_live_status"))
    adapter = _surface_status(source_statuses, "r132_adapter_boundary")
    api_key_present = bool(binance.get("api_key_present") or connector.get("api_key_present"))
    api_secret_present = bool(binance.get("api_secret_present") or connector.get("api_secret_present"))
    return {
        "api_key_present": api_key_present,
        "api_secret_present": api_secret_present,
        "credential_ready": api_key_present and api_secret_present,
        "adapter_boundary_status": adapter,
        "connector_mode": connector.get("connector_mode"),
        "global_kill_switch": connector.get("global_kill_switch"),
        "live_execution_enabled": connector.get("live_execution_enabled"),
        "live_orders_allowed": connector.get("allow_live_orders"),
        "credential_or_adapter_blocked": (not api_key_present) or (not api_secret_present) or _blocked(adapter),
    }


def _blocker_summary(burn_down: Mapping[str, Any], operator_pack: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(burn_down.get("blocker_summary"))
    ranked = list(burn_down.get("ranked_blockers") or [])
    categories = Counter(str(item.get("category") or "UNKNOWN") for item in ranked if isinstance(item, Mapping))
    return {
        **summary,
        "ranked_blocker_count": len(ranked),
        "category_counts": dict(sorted(categories.items())),
        "operator_pack_status": operator_pack.get("status"),
        "next_three_actions": list(operator_pack.get("next_three_actions") or [])[:3],
    }


def _probability_update(
    *,
    burn_down: Mapping[str, Any],
    next_operator_move: str,
    fresh_candidate_status: Mapping[str, Any],
) -> dict[str, Any]:
    tonight = _bounded_pct(burn_down.get("tiny_live_today_probability_pct"))
    next_session = _bounded_pct(burn_down.get("tiny_live_next_session_probability_pct"))
    if next_operator_move == WAIT_FOR_FRESH_CANDIDATE:
        tonight = min(tonight, 1)
        next_session = min(max(next_session, tonight), 12)
        reason = "No fresh eligible routed candidate is available; gates cannot honestly clear without fresh market evidence."
    elif next_operator_move == RECORD_AUTONOMOUS_PAPER_PROOF:
        reason = "A fresh eligible paper decision exists, but proof still needs to be captured through R129/R140."
    elif next_operator_move == AUTHORIZE_TINY_LIVE_LANE:
        reason = "Paper proof exists, but selected lane mode is not tiny_live; authorization planning is the next review step."
    elif next_operator_move in {RERUN_GLOBAL_GATES, RERUN_PROTECTIVE_BOUNDARIES}:
        reason = "Lane and proof are aligned enough to rerun blocked readiness boundaries without executing orders."
    elif next_operator_move == LIVE_READY_REVIEW_NEXT:
        reason = "Current diagnostic surfaces are near-ready; a non-executing live-ready review is next."
    else:
        reason = "The lane remains blocked or a safety boundary requires stopping."
    return {
        "tiny_live_tonight_pct": tonight,
        "tiny_live_next_session_pct": next_session,
        "reason": reason,
        "fresh_routed_count": int(fresh_candidate_status.get("routed_count") or 0),
    }


def _recommended_commands(lane_key: str) -> list[str]:
    command_pack = build_operator_burn_down_command_pack(lane_key=lane_key)
    commands = [
        command_pack["fresh_signal_router_status"],
        _inspect(f"lane-autonomy-scheduler --lane-key {json.dumps(lane_key)}"),
        command_pack["autonomous_paper_lane_executor_integration_preview"],
        _inspect(f"operator-executes-safe-clearing-pack --lane-key {json.dumps(lane_key)}"),
        command_pack["first_tiny_live_lane_execution_gate"],
        command_pack["first_tiny_live_autonomous_lane_authorization_preview"],
        command_pack["autonomous_lane_live_ready_burn_down"],
        _inspect(f"live-ready-blocker-clearing-operator-pack --lane-key {json.dumps(lane_key)}"),
        _inspect(f"lane-control-cockpit-state --lane-key {json.dumps(lane_key)}"),
    ]
    return [command for command in commands if _safe_command(command)]


def _watch_commands(lane_key: str) -> list[str]:
    return [
        _inspect("fresh-signal-router-status"),
        _inspect(f"lane-autonomy-scheduler --lane-key {json.dumps(lane_key)}"),
        _inspect(f"autonomous-paper-lane-executor-integration --lane-key {json.dumps(lane_key)}"),
        _inspect(f"operator-executes-safe-clearing-pack --lane-key {json.dumps(lane_key)}"),
        _inspect(f"post-clearing-live-ready-recheck --lane-key {json.dumps(lane_key)}"),
    ]


def _inspect(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


def _safe_command(command: str) -> bool:
    lowered = f" {command.lower()} "
    return not any(term.lower() in lowered for term in SAFE_COMMAND_FORBIDDEN_TERMS)


def _do_not_run_yet() -> list[str]:
    return [
        "Do not run Binance commands.",
        "Do not run order commands.",
        "Do not create signed requests.",
        "Do not mutate .env or lane config.",
        "Do not restart systemd services.",
        "Do not enable live flags.",
        "Do not disable the global kill switch.",
        "Do not run a watcher loop in R141.",
    ]


def _why(
    next_operator_move: str,
    fresh: Mapping[str, Any],
    paper: Mapping[str, Any],
    lane: Mapping[str, Any],
    gates: Mapping[str, Any],
    protective: Mapping[str, Any],
) -> str:
    if next_operator_move == WAIT_FOR_FRESH_CANDIDATE:
        return "No fresh routed candidate or only stale paper evidence is available; the correct mode is safe watch-only handoff."
    if next_operator_move == RECORD_AUTONOMOUS_PAPER_PROOF:
        return "R129 reports eligible paper decisions, but no paper proof record is present yet."
    if next_operator_move == AUTHORIZE_TINY_LIVE_LANE:
        return f"Paper proof exists, but lane mode is {lane.get('lane_mode')}; tiny_live authorization planning is next."
    if next_operator_move == RERUN_PROTECTIVE_BOUNDARIES:
        return f"Lane is tiny_live, but protective boundaries remain blocked: {protective}."
    if next_operator_move == RERUN_GLOBAL_GATES:
        return f"Lane is tiny_live, but global/credential/adapter gates remain blocked: {gates}."
    if next_operator_move == LIVE_READY_REVIEW_NEXT:
        return "All composed diagnostic gates look near-ready; continue with non-executing live-ready review."
    return f"Still blocked after R140 context: fresh={fresh}, paper={paper}."


def _surface_status(source_statuses: Mapping[str, Any], key: str) -> str:
    surface = _mapping(source_statuses.get(key))
    return str(
        surface.get("status")
        or surface.get("boundary_status")
        or surface.get("final_preflight_status")
        or "UNKNOWN"
    )


def _blocked(status: Any) -> bool:
    text = str(status or "").upper()
    return "BLOCK" in text or "ERROR" in text or "REJECT" in text or "NOT_EVALUATED" in text


def _combined_safety(*surfaces: Mapping[str, Any]) -> dict[str, bool]:
    safety = dict(SAFETY)
    for surface in surfaces:
        _merge_safety(safety, surface)
    return safety


def _merge_safety(target: dict[str, bool], surface: Mapping[str, Any]) -> None:
    nested = surface.get("safety")
    if isinstance(nested, Mapping):
        for key, value in nested.items():
            if key == "paper_live_separation_intact":
                target[key] = bool(target.get(key, True)) and bool(value)
            elif key in target:
                target[key] = bool(target.get(key)) or bool(value)
    for value in surface.values():
        if isinstance(value, Mapping):
            _merge_safety(target, value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping):
                    _merge_safety(target, item)


def _safety_clean(safety: Mapping[str, Any]) -> bool:
    for key, value in safety.items():
        if key == "paper_live_separation_intact":
            if not bool(value):
                return False
        elif bool(value):
            return False
    return True


def _source_surfaces(*surfaces: Mapping[str, Any]) -> list[str]:
    values = list(SOURCE_SURFACES_USED)
    for surface in surfaces:
        for item in surface.get("source_surfaces_used") or []:
            if item not in values:
                values.append(str(item))
    return values


def _bounded_pct(value: Any) -> int:
    try:
        return min(100, max(0, int(value)))
    except (TypeError, ValueError):
        return 0


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
