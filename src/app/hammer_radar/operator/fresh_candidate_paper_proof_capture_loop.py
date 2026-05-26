"""R142 fresh-candidate paper proof capture loop.

This module coordinates an explicitly confirmed, bounded watch loop over
existing safe Hammer Radar surfaces. It never creates proof directly; paper
proof capture is delegated to R140, which delegates to R129 with the paper-only
confirmation phrase.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable, Mapping
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
    run_autonomous_paper_lane_executor_once,
)
from src.app.hammer_radar.operator.fresh_signal_router import build_fresh_signal_router_status
from src.app.hammer_radar.operator.lane_autonomy_scheduler import run_lane_autonomy_scheduler_once
from src.app.hammer_radar.operator.operator_executes_safe_clearing_pack import (
    CONFIRM_SAFE_CLEARING_PHRASE,
    SAFE_CLEARING_EXECUTED,
    SAFE_CLEARING_PARTIAL,
    build_operator_executes_safe_clearing_pack,
)
from src.app.hammer_radar.operator.post_clearing_live_ready_recheck import (
    RECORD_AUTONOMOUS_PAPER_PROOF,
    WAIT_FOR_FRESH_CANDIDATE,
    build_post_clearing_live_ready_recheck,
)

FRESH_CANDIDATE_WATCH_PREVIEW = "FRESH_CANDIDATE_WATCH_PREVIEW"
FRESH_CANDIDATE_WATCH_REJECTED = "FRESH_CANDIDATE_WATCH_REJECTED"
FRESH_CANDIDATE_WATCH_RUNNING = "FRESH_CANDIDATE_WATCH_RUNNING"
FRESH_CANDIDATE_WATCH_CAPTURED_PAPER_PROOF = "FRESH_CANDIDATE_WATCH_CAPTURED_PAPER_PROOF"
FRESH_CANDIDATE_WATCH_TIMEOUT = "FRESH_CANDIDATE_WATCH_TIMEOUT"
FRESH_CANDIDATE_WATCH_SAFETY_STOP = "FRESH_CANDIDATE_WATCH_SAFETY_STOP"
FRESH_CANDIDATE_WATCH_NO_ELIGIBLE_CANDIDATE = "FRESH_CANDIDATE_WATCH_NO_ELIGIBLE_CANDIDATE"
FRESH_CANDIDATE_WATCH_ERROR = "FRESH_CANDIDATE_WATCH_ERROR"

EVENT_TYPE = "FRESH_CANDIDATE_PAPER_PROOF_CAPTURE_LOOP"
LEDGER_FILENAME = "fresh_candidate_paper_proof_capture_loop.ndjson"
CONFIRM_FRESH_CANDIDATE_WATCH_LOOP_PHRASE = (
    "I CONFIRM FRESH CANDIDATE PAPER PROOF WATCH ONLY; NO ORDER; NO BINANCE CALL."
)

PRIMARY_WATCHED_LANE = "BTCUSDT|13m|long|ladder_close_50_618"
SECONDARY_WATCHED_LANE = "BTCUSDT|44m|long|ladder_close_50_618"
RECOMMENDED_WATCHED_LANES = (PRIMARY_WATCHED_LANE, SECONDARY_WATCHED_LANE)

DEFAULT_MAX_ITERATIONS = 5
MAX_MAX_ITERATIONS = 180
DEFAULT_SLEEP_SECONDS = 60
MIN_SLEEP_SECONDS = 10
MAX_SLEEP_SECONDS = 300

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
    "operator.fresh_signal_router.build_fresh_signal_router_status",
    "operator.lane_autonomy_scheduler.run_lane_autonomy_scheduler_once",
    "operator.autonomous_paper_lane_executor_integration.run_autonomous_paper_lane_executor_once",
    "operator.post_clearing_live_ready_recheck.build_post_clearing_live_ready_recheck",
    "operator.autonomous_lane_live_ready_burn_down.build_autonomous_lane_live_ready_burn_down",
    "operator.operator_executes_safe_clearing_pack.build_operator_executes_safe_clearing_pack",
    "operator.operator_executes_safe_clearing_pack -> operator.autonomous_paper_lane_executor_integration",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_watched_lane_specs(
    *,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    watch_all_recommended_lanes: bool = False,
) -> list[dict[str, Any]]:
    keys: list[str] = []
    for value in lane_keys or []:
        keys.extend(_split_lane_keys(value))
    keys.extend(_split_lane_keys(lane_keys_csv))
    if not keys and watch_all_recommended_lanes:
        keys = list(RECOMMENDED_WATCHED_LANES)
    if not keys:
        keys = [DEFAULT_LANE_KEY]
    deduped = _dedupe(keys)
    return [
        {
            "lane_key": lane_key,
            "role": _lane_role(lane_key),
            "symbol": _lane_part(lane_key, 0),
            "timeframe": _lane_part(lane_key, 1),
            "direction": _lane_part(lane_key, 2),
            "entry_mode": _lane_part(lane_key, 3),
        }
        for lane_key in deduped
    ]


def build_fresh_candidate_paper_proof_capture_loop_preview(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    watch_all_recommended_lanes: bool = False,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    record_watch: bool = False,
    confirm_watch_loop: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    lane_specs = build_watched_lane_specs(
        lane_keys=lane_keys,
        lane_keys_csv=lane_keys_csv,
        watch_all_recommended_lanes=watch_all_recommended_lanes,
    )
    bounded_max_iterations = _bounded_int(max_iterations, 1, MAX_MAX_ITERATIONS, DEFAULT_MAX_ITERATIONS)
    bounded_sleep_seconds = _bounded_int(sleep_seconds, MIN_SLEEP_SECONDS, MAX_SLEEP_SECONDS, DEFAULT_SLEEP_SECONDS)
    return build_watcher_loop_summary(
        status=FRESH_CANDIDATE_WATCH_PREVIEW,
        generated_at=generated_at,
        watch_started=False,
        watch_completed=False,
        watch_all_recommended_lanes=watch_all_recommended_lanes,
        watched_lanes=lane_specs,
        max_iterations=bounded_max_iterations,
        sleep_seconds=bounded_sleep_seconds,
        iterations_completed=0,
        paper_proof_captured=False,
        captured_lane_key=None,
        captured_evidence_ids=[],
        iteration_summaries=[],
        final_lane_statuses={},
        next_operator_move=WAIT_FOR_FRESH_CANDIDATE,
        watcher_recommendation="Preview only. Supply the exact R142 phrase to run a bounded watch loop.",
        record_watch_requested=record_watch,
        confirmation_valid=confirm_watch_loop == CONFIRM_FRESH_CANDIDATE_WATCH_LOOP_PHRASE,
        watch_recorded=False,
        watch_id=None,
        source_surfaces_used=SOURCE_SURFACES_USED,
    )


def run_fresh_candidate_paper_proof_capture_loop(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    watch_all_recommended_lanes: bool = False,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    run_watch_loop: bool = False,
    record_watch: bool = False,
    confirm_watch_loop: str | None = None,
    now: datetime | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    lane_specs = build_watched_lane_specs(
        lane_keys=lane_keys,
        lane_keys_csv=lane_keys_csv,
        watch_all_recommended_lanes=watch_all_recommended_lanes,
    )
    bounded_max_iterations = _bounded_int(max_iterations, 1, MAX_MAX_ITERATIONS, DEFAULT_MAX_ITERATIONS)
    bounded_sleep_seconds = _bounded_int(sleep_seconds, MIN_SLEEP_SECONDS, MAX_SLEEP_SECONDS, DEFAULT_SLEEP_SECONDS)
    confirmation_valid = confirm_watch_loop == CONFIRM_FRESH_CANDIDATE_WATCH_LOOP_PHRASE

    if not run_watch_loop:
        return build_fresh_candidate_paper_proof_capture_loop_preview(
            log_dir=resolved_log_dir,
            lane_keys=[spec["lane_key"] for spec in lane_specs],
            watch_all_recommended_lanes=watch_all_recommended_lanes,
            max_iterations=bounded_max_iterations,
            sleep_seconds=bounded_sleep_seconds,
            record_watch=record_watch,
            confirm_watch_loop=confirm_watch_loop,
            now=generated_at,
        )

    if not confirmation_valid:
        return build_watcher_loop_summary(
            status=FRESH_CANDIDATE_WATCH_REJECTED,
            generated_at=generated_at,
            watch_started=False,
            watch_completed=False,
            watch_all_recommended_lanes=watch_all_recommended_lanes,
            watched_lanes=lane_specs,
            max_iterations=bounded_max_iterations,
            sleep_seconds=bounded_sleep_seconds,
            iterations_completed=0,
            paper_proof_captured=False,
            captured_lane_key=None,
            captured_evidence_ids=[],
            iteration_summaries=[],
            final_lane_statuses={},
            next_operator_move=WAIT_FOR_FRESH_CANDIDATE,
            watcher_recommendation="Rejected. Exact R142 watch-only confirmation phrase is required.",
            record_watch_requested=record_watch,
            confirmation_valid=False,
            watch_recorded=False,
            watch_id=None,
            source_surfaces_used=SOURCE_SURFACES_USED,
        )

    iterations: list[dict[str, Any]] = []
    final_lane_statuses: dict[str, Any] = {}
    captured_lane_key: str | None = None
    captured_evidence_ids: list[str] = []
    final_status = FRESH_CANDIDATE_WATCH_TIMEOUT
    next_operator_move = WAIT_FOR_FRESH_CANDIDATE
    sleeper = sleep_fn or time.sleep

    try:
        for iteration in range(1, bounded_max_iterations + 1):
            started_at = datetime.now(UTC)
            lane_summaries: list[dict[str, Any]] = []
            for spec in lane_specs:
                lane_key = str(spec["lane_key"])
                snapshot = collect_watcher_iteration_snapshot(
                    log_dir=resolved_log_dir,
                    lane_key=lane_key,
                    now=datetime.now(UTC),
                )
                evaluation = evaluate_watcher_iteration(snapshot)
                lane_summary = _lane_iteration_summary(
                    lane_key=lane_key,
                    snapshot=snapshot,
                    evaluation=evaluation,
                )
                final_lane_statuses[lane_key] = evaluation
                if not _safety_clean(_mapping(evaluation.get("safety"))):
                    lane_summary["capture_status"] = "BLOCKED"
                    lane_summaries.append(lane_summary)
                    final_status = FRESH_CANDIDATE_WATCH_SAFETY_STOP
                    next_operator_move = "STOP_STILL_BLOCKED"
                    break
                if evaluation.get("eligible_for_paper_capture"):
                    capture = attempt_paper_proof_capture_for_lane(
                        log_dir=resolved_log_dir,
                        lane_key=lane_key,
                        now=datetime.now(UTC),
                    )
                    lane_summary["capture_attempted"] = True
                    lane_summary["capture_status"] = str(capture.get("capture_status") or "ERROR")
                    lane_summary["evidence_ids"] = list(capture.get("evidence_ids") or [])
                    lane_summary["capture_result"] = capture
                    final_lane_statuses[lane_key] = {**evaluation, "capture_result": capture}
                    if capture.get("paper_proof_captured"):
                        captured_lane_key = lane_key
                        captured_evidence_ids = list(capture.get("evidence_ids") or [])
                        final_status = FRESH_CANDIDATE_WATCH_CAPTURED_PAPER_PROOF
                        next_operator_move = "RERUN_R141_POST_CAPTURE_RECHECK"
                    else:
                        next_operator_move = RECORD_AUTONOMOUS_PAPER_PROOF
                    lane_summaries.append(lane_summary)
                    if captured_lane_key:
                        break
                else:
                    lane_summary["capture_status"] = "SKIPPED_NO_ELIGIBLE_DECISION"
                    lane_summaries.append(lane_summary)
            completed_at = datetime.now(UTC)
            iteration_summary = {
                "iteration": iteration,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "lanes": lane_summaries,
                "safety": _combined_safety(*lane_summaries),
            }
            iterations.append(_sanitize(iteration_summary))
            if final_status in {FRESH_CANDIDATE_WATCH_CAPTURED_PAPER_PROOF, FRESH_CANDIDATE_WATCH_SAFETY_STOP}:
                break
            if iteration < bounded_max_iterations:
                sleeper(float(bounded_sleep_seconds))
        if final_status == FRESH_CANDIDATE_WATCH_TIMEOUT and iterations:
            next_operator_move = WAIT_FOR_FRESH_CANDIDATE
    except Exception as exc:  # pragma: no cover - defensive diagnostic boundary
        final_status = FRESH_CANDIDATE_WATCH_ERROR
        next_operator_move = "STOP_STILL_BLOCKED"
        final_lane_statuses["error"] = {"error": exc.__class__.__name__}

    payload = build_watcher_loop_summary(
        status=final_status,
        generated_at=generated_at,
        watch_started=True,
        watch_completed=True,
        watch_all_recommended_lanes=watch_all_recommended_lanes,
        watched_lanes=lane_specs,
        max_iterations=bounded_max_iterations,
        sleep_seconds=bounded_sleep_seconds,
        iterations_completed=len(iterations),
        paper_proof_captured=bool(captured_lane_key),
        captured_lane_key=captured_lane_key,
        captured_evidence_ids=captured_evidence_ids,
        iteration_summaries=iterations,
        final_lane_statuses=final_lane_statuses,
        next_operator_move=next_operator_move,
        watcher_recommendation=_watcher_recommendation(final_status),
        record_watch_requested=record_watch,
        confirmation_valid=True,
        watch_recorded=False,
        watch_id=None,
        source_surfaces_used=SOURCE_SURFACES_USED,
    )
    if record_watch:
        record = append_fresh_candidate_watch_record(payload, log_dir=resolved_log_dir)
        payload = {
            **payload,
            "watch_recorded": True,
            "watch_id": record["watch_id"],
            "ledger_path": str(fresh_candidate_watch_records_path(resolved_log_dir)),
        }
    return _sanitize(payload)


def collect_watcher_iteration_snapshot(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    router = build_fresh_signal_router_status(log_dir=resolved_log_dir, now=generated_at)
    scheduler = run_lane_autonomy_scheduler_once(
        log_dir=resolved_log_dir,
        record_tick=False,
        record_decisions=False,
        lane_key=lane_key,
        now=generated_at,
    )
    paper = run_autonomous_paper_lane_executor_once(
        log_dir=resolved_log_dir,
        record_paper=False,
        record_scheduler_tick=False,
        record_decisions=False,
        lane_key=lane_key,
        now=generated_at,
    )
    r141 = build_post_clearing_live_ready_recheck(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        record_recheck=False,
        now=generated_at,
    )
    burn_down = build_autonomous_lane_live_ready_burn_down(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        now=generated_at,
    )
    return _sanitize(
        {
            "generated_at": generated_at.isoformat(),
            "lane_key": lane_key,
            "fresh_signal_router": router,
            "lane_autonomy_scheduler": scheduler,
            "paper_integration_preview": paper,
            "r141_post_clearing_recheck": r141,
            "r138_burn_down_light_summary": _burn_down_light_summary(burn_down),
            "safety": _combined_safety(router, scheduler, paper, r141, burn_down),
            "source_surfaces_used": _source_surfaces(router, scheduler, paper, r141, burn_down),
        }
    )


def evaluate_watcher_iteration(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    router = _mapping(snapshot.get("fresh_signal_router"))
    paper = _mapping(snapshot.get("paper_integration_preview"))
    r141 = _mapping(snapshot.get("r141_post_clearing_recheck"))
    safety = _combined_safety(snapshot)
    fresh_routed_count = int(router.get("routed_count") or _nested(r141, "fresh_candidate_status", "routed_count") or 0)
    paper_eligible_decisions_count = int(paper.get("paper_eligible_decisions_count") or 0)
    paper_blocked_decisions_count = int(paper.get("paper_blocked_decisions_count") or 0)
    top_blockers = list(paper.get("top_blockers") or router.get("top_blockers") or [])
    eligible = fresh_routed_count > 0 and paper_eligible_decisions_count > 0 and _safety_clean(safety)
    return {
        "lane_key": snapshot.get("lane_key"),
        "fresh_routed_count": fresh_routed_count,
        "paper_eligible_decisions_count": paper_eligible_decisions_count,
        "paper_blocked_decisions_count": paper_blocked_decisions_count,
        "top_blockers": top_blockers[:5],
        "r141_next_operator_move": r141.get("next_operator_move") or WAIT_FOR_FRESH_CANDIDATE,
        "eligible_for_paper_capture": eligible,
        "safety": safety,
    }


def attempt_paper_proof_capture_for_lane(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    result = build_operator_executes_safe_clearing_pack(
        log_dir=log_dir,
        lane_key=lane_key,
        execute_safe_clearing=True,
        confirm_safe_clearing=CONFIRM_SAFE_CLEARING_PHRASE,
        now=now,
    )
    paper_result = _mapping(result.get("paper_proof_result"))
    evidence_ids = [str(item) for item in paper_result.get("paper_execution_ids") or []]
    captured = (
        str(result.get("status")) in {SAFE_CLEARING_EXECUTED, SAFE_CLEARING_PARTIAL}
        and bool(paper_result.get("integration_recorded"))
        and bool(evidence_ids)
    )
    return _sanitize(
        {
            "capture_status": "CAPTURED" if captured else _capture_status_for_result(result, paper_result),
            "paper_proof_captured": captured,
            "lane_key": lane_key,
            "used_r140_path": True,
            "used_r129_path": bool(paper_result.get("used_r129_path")),
            "created_proof_directly_by_r142": False,
            "evidence_ids": evidence_ids,
            "r140_status": result.get("status"),
            "r140_run_id": result.get("safe_clearing_run_id"),
            "r129_integration_id": paper_result.get("integration_id"),
            "top_blockers": list(paper_result.get("top_blockers") or []),
            "safety": _combined_safety(result, paper_result),
            "source_surfaces_used": _source_surfaces(result, paper_result),
        }
    )


def build_watcher_loop_summary(
    *,
    status: str,
    generated_at: datetime,
    watch_started: bool,
    watch_completed: bool,
    watch_all_recommended_lanes: bool,
    watched_lanes: list[Mapping[str, Any]],
    max_iterations: int,
    sleep_seconds: int,
    iterations_completed: int,
    paper_proof_captured: bool,
    captured_lane_key: str | None,
    captured_evidence_ids: list[str],
    iteration_summaries: list[Mapping[str, Any]],
    final_lane_statuses: Mapping[str, Any],
    next_operator_move: str,
    watcher_recommendation: str,
    record_watch_requested: bool,
    confirmation_valid: bool,
    watch_recorded: bool,
    watch_id: str | None,
    source_surfaces_used: list[str],
) -> dict[str, Any]:
    return _sanitize(
        {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "watch_started": watch_started,
            "watch_completed": watch_completed,
            "watch_all_recommended_lanes": watch_all_recommended_lanes,
            "watched_lanes": [dict(item) for item in watched_lanes],
            "max_iterations": int(max_iterations),
            "sleep_seconds": int(sleep_seconds),
            "iterations_completed": int(iterations_completed),
            "paper_proof_captured": paper_proof_captured,
            "captured_lane_key": captured_lane_key,
            "captured_evidence_ids": list(captured_evidence_ids),
            "iteration_summaries": [dict(item) for item in iteration_summaries],
            "final_lane_statuses": dict(final_lane_statuses),
            "next_operator_move": next_operator_move,
            "watcher_recommendation": watcher_recommendation,
            "record_watch_requested": record_watch_requested,
            "confirmation_valid": confirmation_valid,
            "watch_recorded": watch_recorded,
            "watch_id": watch_id,
            "safety": _combined_safety(*iteration_summaries),
            "source_surfaces_used": _dedupe(source_surfaces_used),
        }
    )


def append_fresh_candidate_watch_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = fresh_candidate_watch_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "watch_id": str(record.get("watch_id") or f"r142_fresh_candidate_watch_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "watched_lanes": list(record.get("watched_lanes") or []),
            "max_iterations": int(record.get("max_iterations") or 0),
            "sleep_seconds": int(record.get("sleep_seconds") or 0),
            "iterations_completed": int(record.get("iterations_completed") or 0),
            "paper_proof_captured": bool(record.get("paper_proof_captured")),
            "captured_lane_key": record.get("captured_lane_key"),
            "captured_evidence_ids": list(record.get("captured_evidence_ids") or []),
            "iteration_summaries": list(record.get("iteration_summaries") or []),
            "final_lane_statuses": record.get("final_lane_statuses") or {},
            "next_operator_move": record.get("next_operator_move"),
            "safety": record.get("safety") or dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or []),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_fresh_candidate_watch_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = fresh_candidate_watch_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(_sanitize(json.loads(line)))
    if limit > 0:
        return list(reversed(records))[:limit]
    return records


def summarize_fresh_candidate_watch_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    captured = [record for record in records if record.get("paper_proof_captured")]
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "paper_proof_captures_count": len(captured),
        "last_watch_id": records[-1].get("watch_id") if records else None,
        "last_captured_lane_key": captured[-1].get("captured_lane_key") if captured else None,
        "safety": dict(SAFETY),
    }


def format_fresh_candidate_paper_proof_capture_loop_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def fresh_candidate_watch_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _lane_iteration_summary(
    *,
    lane_key: str,
    snapshot: Mapping[str, Any],
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "lane_key": lane_key,
        "fresh_routed_count": int(evaluation.get("fresh_routed_count") or 0),
        "paper_eligible_decisions_count": int(evaluation.get("paper_eligible_decisions_count") or 0),
        "paper_blocked_decisions_count": int(evaluation.get("paper_blocked_decisions_count") or 0),
        "top_blockers": list(evaluation.get("top_blockers") or []),
        "r141_next_operator_move": evaluation.get("r141_next_operator_move") or WAIT_FOR_FRESH_CANDIDATE,
        "capture_attempted": False,
        "capture_status": "NOT_ATTEMPTED",
        "evidence_ids": [],
        "safety": _combined_safety(snapshot, evaluation),
    }


def _burn_down_light_summary(burn_down: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": burn_down.get("status"),
        "live_ready_now": bool(burn_down.get("live_ready_now")),
        "blocker_summary": burn_down.get("blocker_summary") or {},
        "tiny_live_today_probability_pct": int(burn_down.get("tiny_live_today_probability_pct") or 0),
        "tiny_live_next_session_probability_pct": int(burn_down.get("tiny_live_next_session_probability_pct") or 0),
        "safety": burn_down.get("safety") or dict(SAFETY),
    }


def _capture_status_for_result(result: Mapping[str, Any], paper_result: Mapping[str, Any]) -> str:
    if str(result.get("status") or "").upper().endswith("ERROR"):
        return "ERROR"
    if str(paper_result.get("status") or "") in {"SKIPPED_NO_ELIGIBLE_EVIDENCE", "NOT_ATTEMPTED"}:
        return "SKIPPED_NO_ELIGIBLE_DECISION"
    return "BLOCKED"


def _watcher_recommendation(status: str) -> str:
    if status == FRESH_CANDIDATE_WATCH_CAPTURED_PAPER_PROOF:
        return "Paper proof captured through R140/R129. Run R141/R143 rechecks next; do not proceed to live execution."
    if status == FRESH_CANDIDATE_WATCH_SAFETY_STOP:
        return "Stop and inspect safety fields before running any further watcher command."
    if status == FRESH_CANDIDATE_WATCH_ERROR:
        return "Stop and inspect the diagnostic error before retrying."
    return "No eligible fresh candidate was captured during this bounded loop; wait for the next watch window."


def _split_lane_keys(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _lane_role(lane_key: str) -> str:
    if lane_key == PRIMARY_WATCHED_LANE:
        return "primary"
    if lane_key == SECONDARY_WATCHED_LANE:
        return "secondary"
    return "custom"


def _lane_part(lane_key: str, index: int) -> str:
    parts = lane_key.split("|")
    return parts[index] if len(parts) > index else ""


def _bounded_int(value: Any, lower: int, upper: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(upper, max(lower, parsed))


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
            values.append(str(item))
    return _dedupe(values)


def _nested(mapping: Mapping[str, Any], *keys: str) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = str(value)
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


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
