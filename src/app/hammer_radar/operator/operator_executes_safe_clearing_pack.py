"""R140 operator safe clearing pack executor.

This module executes only the safe, non-live subset of the R139 clearing pack:
read-only snapshots, R129 paper-only proof recording when eligible, and an
append-only R140 run ledger. It never runs generated shell commands, creates
payloads, signs requests, calls Binance order endpoints, mutates env/config, or
places orders.
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
)
from src.app.hammer_radar.operator.autonomous_paper_lane_executor_integration import (
    CONFIRM_PAPER_INTEGRATION_PHRASE,
    PAPER_EXECUTOR_INTEGRATION_PARTIAL,
    PAPER_EXECUTOR_INTEGRATION_RECORDED,
    run_autonomous_paper_lane_executor_once,
)
from src.app.hammer_radar.operator.live_ready_blocker_clearing_operator_pack import (
    BLOCKER_CLEARING_PACK_BLOCKED,
    BLOCKER_CLEARING_PACK_READY,
    build_live_ready_blocker_clearing_operator_pack,
)

SAFE_CLEARING_PREVIEW = "SAFE_CLEARING_PREVIEW"
SAFE_CLEARING_REJECTED = "SAFE_CLEARING_REJECTED"
SAFE_CLEARING_EXECUTED = "SAFE_CLEARING_EXECUTED"
SAFE_CLEARING_PARTIAL = "SAFE_CLEARING_PARTIAL"
SAFE_CLEARING_BLOCKED = "SAFE_CLEARING_BLOCKED"
SAFE_CLEARING_ERROR = "SAFE_CLEARING_ERROR"
NOT_COLLECTED = "NOT_COLLECTED"

EVENT_TYPE = "OPERATOR_SAFE_CLEARING_PACK_RUN"
LEDGER_FILENAME = "operator_safe_clearing_pack_runs.ndjson"
CONFIRM_SAFE_CLEARING_PHRASE = (
    "I CONFIRM SAFE CLEARING PACK EXECUTION ONLY; NO ORDER; NO BINANCE CALL."
)

BLOCKING_SAFETY_KEYS = (
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "order_payload_created",
    "executable_payload_created",
    "protective_payload_created",
    "signed_request_created",
    "network_allowed",
    "binance_order_endpoint_called",
    "binance_test_order_endpoint_called",
    "protective_order_endpoint_called",
    "secrets_shown",
    "env_mutated",
    "config_written",
    "global_live_flags_changed",
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

SOURCE_SURFACES_USED = [
    "operator.autonomous_lane_live_ready_burn_down.build_autonomous_lane_live_ready_burn_down",
    "operator.live_ready_blocker_clearing_operator_pack.build_live_ready_blocker_clearing_operator_pack",
    "operator.autonomous_paper_lane_executor_integration.run_autonomous_paper_lane_executor_once",
    "operator.lane_control.load_lane_controls via R138/R129",
    "operator.fresh_signal_router.build_fresh_signal_router_status via R138/R129",
    "operator.lane_autonomy_scheduler.run_lane_autonomy_scheduler_once via R129",
    "operator.lane_autonomy_control_loop.build_lane_autonomy_control_loop_status via R129",
    "operator.first_tiny_live_lane_execution_gate.build_first_tiny_live_lane_execution_gate via R138",
    "operator.first_tiny_live_autonomous_lane_authorization.build_first_tiny_live_autonomous_lane_authorization via R138",
    "operator.live_lane_kill_switch_rehearsal.build_live_lane_kill_switch_rehearsal via R138",
    "operator.live_adapter_boundary_final_review.build_live_adapter_boundary_final_review via R138",
    "operator.first_tiny_live_order_payload_dry_authorization.build_first_tiny_live_order_payload_dry_authorization via R138",
    "operator.protective_order_dry_policy_review.build_protective_order_dry_policy_review via R138",
    "operator.protective_payload_dry_preview_boundary.build_protective_payload_dry_preview_boundary via R138",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_operator_executes_safe_clearing_pack(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    execute_safe_clearing: bool = False,
    confirm_safe_clearing: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_safe_clearing == CONFIRM_SAFE_CLEARING_PHRASE
    before_snapshot = collect_clearing_before_snapshot(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        now=generated_at,
    )
    attempted_actions = [
        _attempted_action(
            "A001",
            "Collect before snapshot",
            "READ_ONLY_RECHECK",
            "DONE",
            "R138/R139 and source status surfaces were collected through Python builders only.",
            [],
            "Read-only snapshot; no generated shell command was executed.",
        )
    ]

    if not execute_safe_clearing:
        paper_proof_result = _paper_proof_not_attempted(before_snapshot, reason="preview mode does not record evidence")
        after_snapshot: dict[str, Any] = {}
        clearing_delta = build_clearing_delta(before_snapshot=before_snapshot, after_snapshot=after_snapshot)
        summary = build_clearing_result_summary(
            status=SAFE_CLEARING_PREVIEW,
            generated_at=generated_at,
            lane_key=lane_key,
            execute_safe_clearing_requested=False,
            confirmation_valid=False,
            before_snapshot=before_snapshot,
            attempted_actions=attempted_actions
            + [
                _attempted_action(
                    "A002",
                    "Preview R129 paper proof recording",
                    "SKIPPED_NO_ELIGIBLE_EVIDENCE",
                    "SKIPPED",
                    "R140 preview mode never attempts paper proof recording.",
                    [],
                    "No ledger write, no paper record, no network, no payload.",
                )
            ],
            after_snapshot=after_snapshot,
            clearing_delta=clearing_delta,
            paper_proof_result=paper_proof_result,
        )
        return _sanitize(summary)

    if not confirmation_valid:
        paper_proof_result = _paper_proof_not_attempted(before_snapshot, reason="exact R140 confirmation phrase is required")
        after_snapshot = {}
        clearing_delta = build_clearing_delta(before_snapshot=before_snapshot, after_snapshot=after_snapshot)
        summary = build_clearing_result_summary(
            status=SAFE_CLEARING_REJECTED,
            generated_at=generated_at,
            lane_key=lane_key,
            execute_safe_clearing_requested=True,
            confirmation_valid=False,
            before_snapshot=before_snapshot,
            attempted_actions=attempted_actions
            + [
                _attempted_action(
                    "A002",
                    "Reject unsafe clearing execution request",
                    "SKIPPED_UNSAFE",
                    "BLOCKED",
                    "The exact R140 safe-clearing confirmation phrase was not supplied.",
                    [],
                    "No evidence recording or run ledger write is allowed on rejected confirmation.",
                )
            ],
            after_snapshot=after_snapshot,
            clearing_delta=clearing_delta,
            paper_proof_result=paper_proof_result,
        )
        return _sanitize(summary)

    try:
        paper_proof_result = attempt_safe_paper_proof_recording(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            before_snapshot=before_snapshot,
            now=generated_at,
        )
        attempted_actions.append(_paper_attempt_action(paper_proof_result))
        after_snapshot = collect_clearing_after_snapshot(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            now=generated_at,
        )
        attempted_actions.append(
            _attempted_action(
                "A003",
                "Collect after snapshot",
                "READ_ONLY_RECHECK",
                "DONE",
                "R138/R139 and source status surfaces were re-collected after safe evidence handling.",
                [],
                "Read-only snapshot; no generated shell command was executed.",
            )
        )
        clearing_delta = build_clearing_delta(before_snapshot=before_snapshot, after_snapshot=after_snapshot)
        status = _execution_status(paper_proof_result=paper_proof_result, clearing_delta=clearing_delta)
        summary = build_clearing_result_summary(
            status=status,
            generated_at=generated_at,
            lane_key=lane_key,
            execute_safe_clearing_requested=True,
            confirmation_valid=True,
            before_snapshot=before_snapshot,
            attempted_actions=attempted_actions,
            after_snapshot=after_snapshot,
            clearing_delta=clearing_delta,
            paper_proof_result=paper_proof_result,
        )
        record = append_safe_clearing_pack_run_record(summary, log_dir=resolved_log_dir)
        return _sanitize(
            {
                **summary,
                "safe_clearing_run_recorded": True,
                "safe_clearing_run_id": record["run_id"],
                "ledger_path": str(safe_clearing_pack_run_records_path(resolved_log_dir)),
            }
        )
    except Exception as exc:  # pragma: no cover - defensive diagnostic boundary
        after_snapshot = {}
        clearing_delta = build_clearing_delta(before_snapshot=before_snapshot, after_snapshot=after_snapshot)
        return _sanitize(
            build_clearing_result_summary(
                status=SAFE_CLEARING_ERROR,
                generated_at=generated_at,
                lane_key=lane_key,
                execute_safe_clearing_requested=True,
                confirmation_valid=True,
                before_snapshot=before_snapshot,
                attempted_actions=attempted_actions
                + [
                    _attempted_action(
                        "A002",
                        "Safe clearing execution error",
                        "SKIPPED_UNSAFE",
                        "BLOCKED",
                        f"R140 stopped at diagnostic boundary: {exc.__class__.__name__}",
                        [],
                        "Error path records no order, no Binance call, no payload, and no env/config mutation.",
                    )
                ],
                after_snapshot=after_snapshot,
                clearing_delta=clearing_delta,
                paper_proof_result=_paper_proof_not_attempted(before_snapshot, reason="safe clearing diagnostic error"),
            )
        )


def collect_clearing_before_snapshot(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    return _collect_snapshot(log_dir=log_dir, lane_key=lane_key, now=now, snapshot_name="before")


def collect_clearing_after_snapshot(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    return _collect_snapshot(log_dir=log_dir, lane_key=lane_key, now=now, snapshot_name="after")


def attempt_safe_paper_proof_recording(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    before_snapshot: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    if not _safety_clean(_mapping(before_snapshot.get("safety"))):
        return {
            **_paper_proof_not_attempted(before_snapshot, reason="before snapshot safety fields are not clean"),
            "status": "BLOCKED",
            "attempted": False,
        }
    eligible_count = int(_nested(before_snapshot, "paper_proof_status", "paper_eligible_decisions_count") or 0)
    if eligible_count <= 0:
        return {
            **_paper_proof_not_attempted(before_snapshot, reason="R129 preview reported no eligible paper decisions"),
            "status": "SKIPPED_NO_ELIGIBLE_EVIDENCE",
            "attempted": False,
        }
    result = run_autonomous_paper_lane_executor_once(
        log_dir=log_dir,
        lane_key=lane_key,
        record_paper=True,
        record_scheduler_tick=True,
        record_decisions=True,
        confirm_paper_integration=CONFIRM_PAPER_INTEGRATION_PHRASE,
        now=now,
    )
    return {
        "status": str(result.get("status") or "UNKNOWN"),
        "attempted": True,
        "used_r129_path": True,
        "confirmation_phrase_used": "R129_EXACT_PAPER_INTEGRATION_PHRASE",
        "paper_eligible_decisions_count": int(result.get("paper_eligible_decisions_count") or 0),
        "paper_execution_records_created": int(result.get("paper_execution_records_created") or 0),
        "paper_execution_ids": list(result.get("paper_execution_ids") or []),
        "integration_recorded": bool(result.get("integration_recorded")),
        "integration_id": result.get("integration_id"),
        "top_blockers": list(result.get("top_blockers") or []),
        "safety": result.get("safety") or dict(SAFETY),
        "source_surfaces_used": list(result.get("source_surfaces_used") or []),
    }


def build_clearing_delta(
    *,
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    before_counts = _blocker_counts(before_snapshot)
    before_paper = _mapping(before_snapshot.get("paper_proof_status"))
    before_probability = _probability(before_snapshot)
    after_collected = _after_snapshot_collected(after_snapshot)
    if not after_collected:
        return {
            "blocker_counts": {
                "before": before_counts,
                "after": {"status": NOT_COLLECTED},
                "delta_total": 0,
            },
            "paper_proof_status": {
                "before": before_paper.get("status") or "UNKNOWN",
                "after": NOT_COLLECTED,
                "before_records_created": int(before_paper.get("paper_execution_records_created") or 0),
                "after_records_created": None,
                "records_created_delta": 0,
            },
            "lane_status": _status_delta(before_snapshot, after_snapshot, "lane_status"),
            "tiny_live_gate_status": _status_delta(before_snapshot, after_snapshot, "tiny_live_gate_status"),
            "protective_policy_status": _status_delta(before_snapshot, after_snapshot, "protective_policy_status"),
            "global_gate_status": _status_delta(before_snapshot, after_snapshot, "global_gate_status"),
            "probability_movement": {
                "before_today_probability_pct": before_probability["today"],
                "after_today_probability_pct": None,
                "today_delta_pct": 0,
                "before_next_session_probability_pct": before_probability["next_session"],
                "after_next_session_probability_pct": None,
                "next_session_delta_pct": 0,
            },
        }

    after_counts = _blocker_counts(after_snapshot)
    after_paper = _mapping(after_snapshot.get("paper_proof_status"))
    after_probability = _probability(after_snapshot)
    return {
        "blocker_counts": {
            "before": before_counts,
            "after": after_counts,
            "delta_total": after_counts["total_count"] - before_counts["total_count"],
        },
        "paper_proof_status": {
            "before": before_paper.get("status") or "UNKNOWN",
            "after": after_paper.get("status") or "NOT_COLLECTED",
            "before_records_created": int(before_paper.get("paper_execution_records_created") or 0),
            "after_records_created": int(after_paper.get("paper_execution_records_created") or 0),
            "records_created_delta": int(after_paper.get("paper_execution_records_created") or 0)
            - int(before_paper.get("paper_execution_records_created") or 0),
        },
        "lane_status": _status_delta(before_snapshot, after_snapshot, "lane_status"),
        "tiny_live_gate_status": _status_delta(before_snapshot, after_snapshot, "tiny_live_gate_status"),
        "protective_policy_status": _status_delta(before_snapshot, after_snapshot, "protective_policy_status"),
        "global_gate_status": _status_delta(before_snapshot, after_snapshot, "global_gate_status"),
        "probability_movement": {
            "before_today_probability_pct": before_probability["today"],
            "after_today_probability_pct": after_probability["today"],
            "today_delta_pct": after_probability["today"] - before_probability["today"],
            "before_next_session_probability_pct": before_probability["next_session"],
            "after_next_session_probability_pct": after_probability["next_session"],
            "next_session_delta_pct": after_probability["next_session"] - before_probability["next_session"],
        },
    }


def build_clearing_result_summary(
    *,
    status: str,
    generated_at: datetime,
    lane_key: str,
    execute_safe_clearing_requested: bool,
    confirmation_valid: bool,
    before_snapshot: Mapping[str, Any],
    attempted_actions: list[Mapping[str, Any]],
    after_snapshot: Mapping[str, Any],
    clearing_delta: Mapping[str, Any],
    paper_proof_result: Mapping[str, Any],
) -> dict[str, Any]:
    blocker_movement = _mapping(clearing_delta.get("blocker_counts"))
    probability_movement = _mapping(clearing_delta.get("probability_movement"))
    return {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "lane_key": lane_key,
        "execute_safe_clearing_requested": bool(execute_safe_clearing_requested),
        "confirmation_valid": bool(confirmation_valid),
        "safe_clearing_run_recorded": False,
        "safe_clearing_run_id": None,
        "before_snapshot": dict(before_snapshot),
        "attempted_actions": [dict(item) for item in attempted_actions],
        "after_snapshot": dict(after_snapshot),
        "clearing_delta": dict(clearing_delta),
        "paper_proof_result": dict(paper_proof_result),
        "blocker_movement": blocker_movement,
        "probability_movement": probability_movement,
        "next_three_actions": _next_three_actions(before_snapshot, after_snapshot, paper_proof_result),
        "still_blocked_by": _still_blocked_by(after_snapshot or before_snapshot),
        "safety": dict(SAFETY),
        "source_surfaces_used": _source_surfaces(before_snapshot, after_snapshot, paper_proof_result),
    }


def append_safe_clearing_pack_run_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = safe_clearing_pack_run_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "run_id": str(record.get("safe_clearing_run_id") or f"r140_safe_clearing_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "lane_key": record.get("lane_key"),
            "before_snapshot": record.get("before_snapshot") or {},
            "attempted_actions": list(record.get("attempted_actions") or []),
            "after_snapshot": record.get("after_snapshot") or {},
            "clearing_delta": record.get("clearing_delta") or {},
            "paper_proof_result": record.get("paper_proof_result") or {},
            "blocker_movement": record.get("blocker_movement") or {},
            "probability_movement": record.get("probability_movement") or {},
            "next_three_actions": list(record.get("next_three_actions") or []),
            "safety": record.get("safety") or dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or []),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_safe_clearing_pack_run_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = safe_clearing_pack_run_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_safe_clearing_pack_runs(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    lane_counts = Counter(str(record.get("lane_key") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "last_run_id": records[-1].get("run_id") if records else None,
        "safety": dict(SAFETY),
    }


def format_operator_executes_safe_clearing_pack_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def safe_clearing_pack_run_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _collect_snapshot(
    *,
    log_dir: str | Path | None,
    lane_key: str,
    now: datetime | None,
    snapshot_name: str,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    burn_down = build_autonomous_lane_live_ready_burn_down(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        now=generated_at,
    )
    operator_pack = build_live_ready_blocker_clearing_operator_pack(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        burn_down=burn_down,
        now=generated_at,
    )
    source_statuses = _mapping(burn_down.get("source_statuses"))
    return _sanitize(
        {
            "snapshot_name": snapshot_name,
            "generated_at": generated_at.isoformat(),
            "lane_key": lane_key,
            "burn_down_status": burn_down.get("status"),
            "operator_pack_status": operator_pack.get("status"),
            "live_ready_now": bool(burn_down.get("live_ready_now")),
            "blocker_summary": burn_down.get("blocker_summary") or {},
            "ranked_blocker_count": len(list(burn_down.get("ranked_blockers") or [])),
            "ranked_blockers": _compact_blockers(burn_down.get("ranked_blockers") or []),
            "lane_status": _lane_status(source_statuses),
            "router_status": _router_status(source_statuses),
            "scheduler_status": _paper_status(source_statuses).get("scheduler_status") or "UNKNOWN",
            "paper_proof_status": _paper_status(source_statuses),
            "tiny_live_gate_status": _surface_status(source_statuses, "r126_tiny_live_gate"),
            "r130_authorization_status": _surface_status(source_statuses, "r130_authorization"),
            "r131_kill_switch_status": _surface_status(source_statuses, "r131_kill_switch_rehearsal"),
            "r132_adapter_boundary_status": _surface_status(source_statuses, "r132_adapter_boundary"),
            "r134_dry_authorization_status": _surface_status(source_statuses, "r134_dry_authorization"),
            "protective_policy_status": _surface_status(source_statuses, "r136_protective_policy"),
            "protective_preview_status": _surface_status(source_statuses, "r137_protective_preview"),
            "global_gate_status": _surface_status(source_statuses, "first_live_activation_gate"),
            "final_live_preflight_status": _surface_status(source_statuses, "final_live_preflight"),
            "probability": {
                "today_probability_pct": int(burn_down.get("tiny_live_today_probability_pct") or 0),
                "next_session_probability_pct": int(burn_down.get("tiny_live_next_session_probability_pct") or 0),
            },
            "operator_pack_next_three_actions": list(operator_pack.get("next_three_actions") or [])[:3],
            "safety": _combined_safety(burn_down, operator_pack, source_statuses),
            "source_surfaces_used": _source_surfaces(burn_down, operator_pack),
        }
    )


def _execution_status(*, paper_proof_result: Mapping[str, Any], clearing_delta: Mapping[str, Any]) -> str:
    paper_status = str(paper_proof_result.get("status") or "")
    if paper_status in {PAPER_EXECUTOR_INTEGRATION_RECORDED, PAPER_EXECUTOR_INTEGRATION_PARTIAL}:
        return SAFE_CLEARING_EXECUTED if paper_status == PAPER_EXECUTOR_INTEGRATION_RECORDED else SAFE_CLEARING_PARTIAL
    if paper_status in {"SKIPPED_NO_ELIGIBLE_EVIDENCE", "NOT_ATTEMPTED"}:
        return SAFE_CLEARING_BLOCKED
    if paper_status == "BLOCKED":
        return SAFE_CLEARING_BLOCKED
    delta_total = int(_nested(clearing_delta, "blocker_counts", "delta_total") or 0)
    return SAFE_CLEARING_EXECUTED if delta_total <= 0 else SAFE_CLEARING_PARTIAL


def _paper_attempt_action(paper_proof_result: Mapping[str, Any]) -> dict[str, Any]:
    if not paper_proof_result.get("attempted"):
        action_type = "SKIPPED_NO_ELIGIBLE_EVIDENCE"
        status = "SKIPPED" if paper_proof_result.get("status") != "BLOCKED" else "BLOCKED"
    else:
        action_type = "SAFE_EVIDENCE_RECORDING"
        status = "DONE" if paper_proof_result.get("integration_recorded") else "BLOCKED"
    return _attempted_action(
        "A002",
        "Attempt R129 paper-only proof recording",
        action_type,
        status,
        str(paper_proof_result.get("reason") or paper_proof_result.get("status") or "R129 decided paper proof outcome"),
        list(paper_proof_result.get("paper_execution_ids") or []),
        "Delegated to R129 with its exact paper-only confirmation phrase; no direct paper records were created by R140.",
    )


def _attempted_action(
    action_id: str,
    title: str,
    action_type: str,
    status: str,
    why: str,
    evidence_ids: list[str],
    safety_note: str,
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "title": title,
        "action_type": action_type,
        "status": status,
        "why": why,
        "evidence_ids": list(evidence_ids),
        "safety_note": safety_note,
    }


def _paper_proof_not_attempted(snapshot: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    paper = _mapping(snapshot.get("paper_proof_status"))
    return {
        "status": "NOT_ATTEMPTED",
        "attempted": False,
        "used_r129_path": False,
        "reason": reason,
        "paper_eligible_decisions_count": int(paper.get("paper_eligible_decisions_count") or 0),
        "paper_execution_records_created": 0,
        "paper_execution_ids": [],
        "integration_recorded": False,
        "integration_id": None,
        "top_blockers": list(paper.get("top_blockers") or []),
        "safety": dict(SAFETY),
        "source_surfaces_used": [],
    }


def _next_three_actions(
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    paper_proof_result: Mapping[str, Any],
) -> list[str]:
    if not paper_proof_result.get("attempted"):
        return [
            "Wait for a fresh routed candidate / scheduler decision if R129 reports no eligible paper evidence.",
            "Rerun operator-executes-safe-clearing-pack preview to refresh R138/R139 before any confirmed safe clearing.",
            "Keep lane config, environment state, kill switch, and exchange-facing behavior unchanged.",
        ]
    if paper_proof_result.get("integration_recorded"):
        return [
            "Rerun R141 post-clearing live-ready recheck across R138/R139/R140 before any lane-mode or authorization action.",
            "Review R126/R130/R131/R132/R136/R137 blockers from the after snapshot.",
            "Do not proceed to live authorization unless a future explicit phase requests it.",
        ]
    return [
        "Inspect R129 top blockers and wait for a fresh routed candidate if no eligible decision exists.",
        "Rerun R128/R127 previews only; do not mutate lane config or env.",
        "Keep R140 in preview until R129 reports eligible paper-only evidence.",
    ]


def _still_blocked_by(snapshot: Mapping[str, Any]) -> list[str]:
    blockers = []
    for item in snapshot.get("ranked_blockers") or []:
        if isinstance(item, Mapping):
            blockers.append(str(item.get("title") or item.get("category") or "unknown blocker"))
    return blockers[:10]


def _blocker_counts(snapshot: Mapping[str, Any]) -> dict[str, int]:
    summary = _mapping(snapshot.get("blocker_summary"))
    total = int(snapshot.get("ranked_blocker_count") or 0)
    if not total:
        total = sum(int(summary.get(key) or 0) for key in ("critical_count", "high_count", "medium_count", "low_count"))
    return {
        "total_count": total,
        "critical_count": int(summary.get("critical_count") or 0),
        "high_count": int(summary.get("high_count") or 0),
        "medium_count": int(summary.get("medium_count") or 0),
        "low_count": int(summary.get("low_count") or 0),
        "evidence_count": int(summary.get("evidence_count") or 0),
        "future_phase_count": int(summary.get("future_phase_count") or 0),
    }


def _status_delta(before: Mapping[str, Any], after: Mapping[str, Any], key: str) -> dict[str, Any]:
    after_collected = _after_snapshot_collected(after)
    return {
        "before": before.get(key) or "UNKNOWN",
        "after": after.get(key) if after_collected else NOT_COLLECTED,
        "changed": after_collected and before.get(key) != after.get(key),
    }


def _probability(snapshot: Mapping[str, Any]) -> dict[str, int]:
    probability = _mapping(snapshot.get("probability"))
    return {
        "today": int(probability.get("today_probability_pct") or 0),
        "next_session": int(probability.get("next_session_probability_pct") or 0),
    }


def _after_snapshot_collected(snapshot: Mapping[str, Any]) -> bool:
    if not snapshot:
        return False
    for key in ("status", "snapshot_status", "collection_status", "snapshot_name"):
        if str(snapshot.get(key) or "").upper() == NOT_COLLECTED:
            return False
    return True


def _compact_blockers(blockers: list[Any]) -> list[dict[str, Any]]:
    compact = []
    for item in blockers:
        if isinstance(item, Mapping):
            compact.append(
                {
                    "id": item.get("id"),
                    "category": item.get("category"),
                    "severity": item.get("severity"),
                    "title": item.get("title"),
                    "current_status": item.get("current_status"),
                    "clearing_mode": item.get("clearing_mode"),
                    "future_phase_required": item.get("future_phase_required"),
                }
            )
    return compact


def _lane_status(source_statuses: Mapping[str, Any]) -> str:
    lane = _mapping(source_statuses.get("lane"))
    return str(source_statuses.get("lane_mode") or lane.get("mode") or "UNKNOWN")


def _router_status(source_statuses: Mapping[str, Any]) -> str:
    return _surface_status(source_statuses, "fresh_signal_router")


def _paper_status(source_statuses: Mapping[str, Any]) -> dict[str, Any]:
    paper = _mapping(source_statuses.get("paper_integration"))
    return {
        "status": paper.get("status") or "UNKNOWN",
        "scheduler_status": paper.get("scheduler_status") or "UNKNOWN",
        "paper_eligible_decisions_count": int(paper.get("paper_eligible_decisions_count") or 0),
        "paper_blocked_decisions_count": int(paper.get("paper_blocked_decisions_count") or 0),
        "paper_execution_records_created": int(paper.get("paper_execution_records_created") or 0),
        "integration_recorded": bool(paper.get("integration_recorded")),
        "integration_id": paper.get("integration_id"),
        "top_blockers": list(paper.get("top_blockers") or []),
    }


def _surface_status(source_statuses: Mapping[str, Any], key: str) -> str:
    surface = _mapping(source_statuses.get(key))
    return str(
        surface.get("status")
        or surface.get("boundary_status")
        or surface.get("final_preflight_status")
        or "UNKNOWN"
    )


def _combined_safety(*surfaces: Mapping[str, Any]) -> dict[str, bool]:
    safety = dict(SAFETY)
    for surface in surfaces:
        source_safety = surface.get("safety") if isinstance(surface.get("safety"), Mapping) else {}
        for key in BLOCKING_SAFETY_KEYS:
            safety[key] = bool(safety.get(key, False) or source_safety.get(key, False))
        if source_safety.get("paper_live_separation_intact") is False:
            safety["paper_live_separation_intact"] = False
    safety["paper_live_separation_intact"] = bool(
        safety.get("paper_live_separation_intact", True)
        and not any(safety.get(key) is True for key in BLOCKING_SAFETY_KEYS)
    )
    return safety


def _safety_clean(safety: Mapping[str, Any]) -> bool:
    return all(safety.get(key) is False for key in BLOCKING_SAFETY_KEYS) and safety.get("paper_live_separation_intact") is True


def _source_surfaces(*surfaces: Mapping[str, Any]) -> list[str]:
    used = list(SOURCE_SURFACES_USED)
    for surface in surfaces:
        for item in surface.get("source_surfaces_used") or []:
            if isinstance(item, str):
                used.append(item)
    seen: set[str] = set()
    result = []
    for item in used:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nested(mapping: Mapping[str, Any], *keys: str) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


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
