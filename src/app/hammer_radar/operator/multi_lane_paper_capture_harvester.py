"""R180 multi-lane paper capture harvester.

This module harvests paper evidence from local Hammer Radar ledgers only. It
does not call Binance, create order payloads, mutate env/config, change lane
modes, promote lanes, or authorize live execution.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir, get_signals_path
from src.app.hammer_radar.operator.entry_mode_derivation_bridge import normalize_candidates_for_lane_key
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE, load_lane_controls, normalize_lane_key
from src.app.hammer_radar.operator.paper_opportunity_expansion import TARGET_ENTRY_MODE, TARGET_SYMBOL, TARGET_TINY_LIVE_LANES
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import load_short_paper_evidence_capture_records
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY

MULTI_LANE_PAPER_HARVESTER_PREVIEW = "MULTI_LANE_PAPER_HARVESTER_PREVIEW"
MULTI_LANE_PAPER_HARVESTER_READY = "MULTI_LANE_PAPER_HARVESTER_READY"
MULTI_LANE_PAPER_HARVESTER_REJECTED = "MULTI_LANE_PAPER_HARVESTER_REJECTED"
MULTI_LANE_PAPER_HARVESTER_RECORDED = "MULTI_LANE_PAPER_HARVESTER_RECORDED"
MULTI_LANE_PAPER_HARVESTER_TIMEOUT = "MULTI_LANE_PAPER_HARVESTER_TIMEOUT"
MULTI_LANE_PAPER_HARVESTER_CAPTURED = "MULTI_LANE_PAPER_HARVESTER_CAPTURED"
MULTI_LANE_PAPER_HARVESTER_BLOCKED = "MULTI_LANE_PAPER_HARVESTER_BLOCKED"
MULTI_LANE_PAPER_HARVESTER_ERROR = "MULTI_LANE_PAPER_HARVESTER_ERROR"

NO_FRESH_CANDIDATES = "NO_FRESH_CANDIDATES"
CAPTURED_ONE_OR_MORE_LANES = "CAPTURED_ONE_OR_MORE_LANES"
EIGHT_M_SHORT_STILL_LEAD = "EIGHT_M_SHORT_STILL_LEAD"
NEW_LANE_CANDIDATE_EMERGED = "NEW_LANE_CANDIDATE_EMERGED"
THRESHOLD_MET_FOR_ONE_OR_MORE_LANES = "THRESHOLD_MET_FOR_ONE_OR_MORE_LANES"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

MULTI_LANE_HARVEST_ITERATION_STARTED = "MULTI_LANE_HARVEST_ITERATION_STARTED"
MULTI_LANE_HARVEST_ITERATION_COMPLETED = "MULTI_LANE_HARVEST_ITERATION_COMPLETED"
MULTI_LANE_HARVEST_CAPTURED = "MULTI_LANE_HARVEST_CAPTURED"
MULTI_LANE_HARVEST_TIMEOUT = "MULTI_LANE_HARVEST_TIMEOUT"
MULTI_LANE_HARVEST_EXITED = "MULTI_LANE_HARVEST_EXITED"

EVENT_TYPE = "MULTI_LANE_PAPER_CAPTURE_HARVESTER"
HEARTBEAT_EVENT_TYPE = "MULTI_LANE_PAPER_CAPTURE_HARVESTER_HEARTBEAT"
LEDGER_FILENAME = "multi_lane_paper_harvester.ndjson"
HEARTBEAT_LEDGER_FILENAME = "multi_lane_paper_harvester_heartbeats.ndjson"
CONFIRM_MULTI_LANE_HARVEST_PHRASE = (
    "I CONFIRM MULTI LANE PAPER HARVESTING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_SIGNALS = 1000
DEFAULT_LATEST_SCANS = 2000
DEFAULT_MAX_ITERATIONS = 60
DEFAULT_SLEEP_SECONDS = 60
DEFAULT_ITERATION_TIMEOUT_SECONDS = 30
DEFAULT_HEARTBEAT_EVERY = 1
DEFAULT_CAPTURE_THRESHOLD_PER_LANE = 10
DEFAULT_MAX_CAPTURES_PER_ITERATION = 10

MAX_LATEST_SIGNALS = 20000
MAX_LATEST_SCANS = 50000
MAX_MAX_ITERATIONS = 1440
MAX_SLEEP_SECONDS = 300
MAX_ITERATION_TIMEOUT_SECONDS = 300
MAX_HEARTBEAT_EVERY = 1000
MAX_CAPTURES_PER_ITERATION = 100

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "logs/hammer_radar_forward/short_paper_evidence_capture.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{HEARTBEAT_LEDGER_FILENAME}",
    "operator.entry_mode_derivation_bridge.normalize_candidates_for_lane_key",
    "operator.lane_control.load_lane_controls",
    "operator.lane_control.normalize_lane_key",
]


def build_multi_lane_paper_capture_harvester_preview(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    iteration_timeout_seconds: int = DEFAULT_ITERATION_TIMEOUT_SECONDS,
    heartbeat_every: int = DEFAULT_HEARTBEAT_EVERY,
    capture_threshold_per_lane: int = DEFAULT_CAPTURE_THRESHOLD_PER_LANE,
    max_captures_per_iteration: int = DEFAULT_MAX_CAPTURES_PER_ITERATION,
    record_harvest: bool = False,
    confirm_multi_lane_harvest: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_multi_lane_harvest == CONFIRM_MULTI_LANE_HARVEST_PHRASE
    bounded = _bounded_settings(
        latest_signals=latest_signals,
        latest_scans=latest_scans,
        max_iterations=max_iterations,
        sleep_seconds=sleep_seconds,
        iteration_timeout_seconds=iteration_timeout_seconds,
        heartbeat_every=heartbeat_every,
        max_captures_per_iteration=max_captures_per_iteration,
    )
    try:
        scope = build_multi_lane_harvest_scope(config_path=config_path)
        evaluation = evaluate_multi_lane_paper_candidates(
            log_dir=resolved_log_dir,
            scope=scope,
            latest_signals=bounded["latest_signals"],
            latest_scans=bounded["latest_scans"],
            now=generated_at,
        )
        counts = build_lane_capture_counts(
            log_dir=resolved_log_dir,
            scope=scope,
            required_fresh_capture_count=capture_threshold_per_lane,
        )
        recommendation = build_next_lane_candidate_recommendation(
            lane_capture_counts=counts,
            fresh_by_lane=evaluation["capture_summary"]["fresh_by_lane"],
        )
        harvest_status = classify_multi_lane_harvest_status(
            capture_summary=evaluation["capture_summary"],
            lane_capture_counts=counts,
            recommendation=recommendation,
        )
        status = _preview_status(scope, evaluation["capture_summary"])
        if record_harvest and not confirmation_valid:
            status = MULTI_LANE_PAPER_HARVESTER_REJECTED
        elif record_harvest and confirmation_valid:
            status = MULTI_LANE_PAPER_HARVESTER_RECORDED
        payload = _build_payload(
            status=status,
            generated_at=generated_at,
            harvest_id=None,
            record_harvest_requested=record_harvest,
            confirmation_valid=confirmation_valid,
            harvest_recorded=False,
            watch_started=False,
            watch_completed=False,
            scope=scope,
            capture_summary=evaluation["capture_summary"],
            lane_capture_counts=counts,
            next_lane_candidate_recommendation=recommendation,
            harvest_status=harvest_status,
            iterations_completed=0,
            bounded=bounded,
        )
        if record_harvest and confirmation_valid:
            record = append_multi_lane_harvester_record(payload, log_dir=resolved_log_dir)
            payload["harvest_recorded"] = True
            payload["harvest_id"] = record["harvest_id"]
            payload["ledger_path"] = str(multi_lane_harvester_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _error_payload(generated_at=generated_at, record_harvest=record_harvest, confirmation_valid=confirmation_valid, error=exc)


def build_multi_lane_harvest_scope(*, config_path: str | Path | None = None) -> dict[str, Any]:
    controls = load_lane_controls(Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH)
    lanes = [_compact_lane(lane) for lane in controls.get("lanes") or [] if _is_target_lane(lane)]
    paper_lanes = [lane for lane in lanes if lane["mode"] == "paper"]
    observed = [lane for lane in lanes if lane["mode"] == "tiny_live" and lane["lane_key"] in set(TARGET_TINY_LIVE_LANES)]
    combined = [*paper_lanes, *observed]
    return {
        "paper_lanes": sorted(paper_lanes, key=lambda item: item["lane_key"]),
        "observed_tiny_live_lanes": sorted(observed, key=lambda item: item["lane_key"]),
        "timeframes": _ordered_timeframes([lane["timeframe"] for lane in combined]),
        "directions": [direction for direction in ("long", "short") if direction in {lane["direction"] for lane in combined}],
        "lane_modes": {lane["lane_key"]: lane["mode"] for lane in sorted(combined, key=lambda item: item["lane_key"])},
    }


def evaluate_multi_lane_paper_candidates(
    *,
    log_dir: str | Path | None = None,
    scope: Mapping[str, Any] | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    harvest_scope = dict(scope or build_multi_lane_harvest_scope(config_path=config_path))
    bounded_signals = _bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS)
    bounded_scans = _bounded_int(latest_scans, 1, MAX_LATEST_SCANS, DEFAULT_LATEST_SCANS)
    raw_candidates = [
        *[_candidate_row(record, source="signals.ndjson") for record in reversed(read_recent_ndjson_records(get_signals_path(resolved_log_dir), limit=bounded_signals, max_bytes=16_777_216))],
        *[_candidate_row(record, source="multi_symbol_paper_scans.ndjson") for record in reversed(read_recent_ndjson_records(resolved_log_dir / "multi_symbol_paper_scans.ndjson", limit=bounded_scans, max_bytes=32_000_000))],
    ]
    lanes = {lane["lane_key"]: lane for lane in [*harvest_scope.get("paper_lanes", []), *harvest_scope.get("observed_tiny_live_lanes", [])]}
    paper_lane_keys = {lane["lane_key"] for lane in harvest_scope.get("paper_lanes", [])}
    observed_lane_keys = {lane["lane_key"] for lane in harvest_scope.get("observed_tiny_live_lanes", [])}
    rows: list[dict[str, Any]] = []
    fresh_by_lane: Counter[str] = Counter()
    stale_by_lane: Counter[str] = Counter()
    blocked_by_lane: Counter[str] = Counter()
    observed_by_lane: Counter[str] = Counter()
    candidates_by_lane: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for raw in raw_candidates:
        normalized_rows = _normalize_against_scope(raw, lanes)
        matched = False
        for candidate in normalized_rows:
            lane_key = str(candidate.get("lane_key") or "")
            lane = lanes.get(lane_key)
            if not lane:
                continue
            matched = True
            row = _candidate_window_row(raw, candidate, lane, generated_at, observed_only=lane_key in observed_lane_keys)
            rows.append(row)
            if row["observed_only"]:
                if row["fresh"]:
                    observed_by_lane[lane_key] += 1
                continue
            if row["capture_allowed"]:
                fresh_by_lane[lane_key] += 1
                if len(candidates_by_lane[lane_key]) < 20:
                    candidates_by_lane[lane_key].append(row)
            elif row["stale"]:
                stale_by_lane[lane_key] += 1
            else:
                blocked_by_lane[lane_key] += 1
        if not matched:
            lane_key = normalize_lane_key(raw.get("symbol"), raw.get("timeframe"), raw.get("direction"), raw.get("entry_mode") or TARGET_ENTRY_MODE)
            if str(raw.get("symbol") or "").strip().upper() == TARGET_SYMBOL:
                blocked_by_lane[lane_key] += 1

    summary = build_multi_lane_capture_summary(
        fresh_by_lane=fresh_by_lane,
        stale_by_lane=stale_by_lane,
        blocked_by_lane=blocked_by_lane,
        candidates_by_lane=candidates_by_lane,
        observed_by_lane=observed_by_lane,
    )
    return _sanitize(
        {
            "generated_at": generated_at.isoformat(),
            "signals_checked": bounded_signals,
            "scans_checked": bounded_scans,
            "candidate_rows_checked": len(raw_candidates),
            "recent_matching_candidates": rows[:20],
            "capture_summary": summary,
            "safety": dict(SAFETY),
        }
    )


def capture_multi_lane_paper_evidence_once(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    max_captures_per_iteration: int = DEFAULT_MAX_CAPTURES_PER_ITERATION,
    capture_threshold_per_lane: int = DEFAULT_CAPTURE_THRESHOLD_PER_LANE,
    record_harvest: bool = False,
    confirm_multi_lane_harvest: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    return run_multi_lane_paper_harvester_loop(
        log_dir=log_dir,
        latest_signals=latest_signals,
        latest_scans=latest_scans,
        max_iterations=1,
        sleep_seconds=1,
        iteration_timeout_seconds=DEFAULT_ITERATION_TIMEOUT_SECONDS,
        heartbeat_every=1,
        max_captures_per_iteration=max_captures_per_iteration,
        capture_threshold_per_lane=capture_threshold_per_lane,
        run_harvester_loop=True,
        record_harvest=record_harvest,
        confirm_multi_lane_harvest=confirm_multi_lane_harvest,
        config_path=config_path,
        now=now,
        sleep_fn=lambda _seconds: None,
    )


def run_multi_lane_paper_harvester_loop(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    iteration_timeout_seconds: int = DEFAULT_ITERATION_TIMEOUT_SECONDS,
    heartbeat_every: int = DEFAULT_HEARTBEAT_EVERY,
    capture_threshold_per_lane: int = DEFAULT_CAPTURE_THRESHOLD_PER_LANE,
    max_captures_per_iteration: int = DEFAULT_MAX_CAPTURES_PER_ITERATION,
    run_harvester_loop: bool = False,
    record_harvest: bool = False,
    confirm_multi_lane_harvest: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    progress_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_multi_lane_harvest == CONFIRM_MULTI_LANE_HARVEST_PHRASE
    bounded = _bounded_settings(
        latest_signals=latest_signals,
        latest_scans=latest_scans,
        max_iterations=max_iterations,
        sleep_seconds=sleep_seconds,
        iteration_timeout_seconds=iteration_timeout_seconds,
        heartbeat_every=heartbeat_every,
        max_captures_per_iteration=max_captures_per_iteration,
    )
    if not run_harvester_loop:
        return build_multi_lane_paper_capture_harvester_preview(
            log_dir=resolved_log_dir,
            latest_signals=bounded["latest_signals"],
            latest_scans=bounded["latest_scans"],
            max_iterations=bounded["max_iterations"],
            sleep_seconds=bounded["sleep_seconds"],
            iteration_timeout_seconds=bounded["iteration_timeout_seconds"],
            heartbeat_every=bounded["heartbeat_every"],
            capture_threshold_per_lane=capture_threshold_per_lane,
            max_captures_per_iteration=bounded["max_captures_per_iteration"],
            record_harvest=record_harvest,
            confirm_multi_lane_harvest=confirm_multi_lane_harvest,
            config_path=config_path,
            now=generated_at,
        )
    scope = build_multi_lane_harvest_scope(config_path=config_path)
    first_eval = evaluate_multi_lane_paper_candidates(
        log_dir=resolved_log_dir,
        scope=scope,
        latest_signals=bounded["latest_signals"],
        latest_scans=bounded["latest_scans"],
        now=generated_at,
    )
    if not confirmation_valid:
        return _build_payload(
            status=MULTI_LANE_PAPER_HARVESTER_REJECTED,
            generated_at=generated_at,
            harvest_id=None,
            record_harvest_requested=record_harvest,
            confirmation_valid=False,
            harvest_recorded=False,
            watch_started=False,
            watch_completed=False,
            scope=scope,
            capture_summary=first_eval["capture_summary"],
            lane_capture_counts=build_lane_capture_counts(log_dir=resolved_log_dir, scope=scope, required_fresh_capture_count=capture_threshold_per_lane),
            next_lane_candidate_recommendation=build_next_lane_candidate_recommendation(
                lane_capture_counts=build_lane_capture_counts(log_dir=resolved_log_dir, scope=scope, required_fresh_capture_count=capture_threshold_per_lane),
                fresh_by_lane=first_eval["capture_summary"]["fresh_by_lane"],
            ),
            harvest_status=NO_FRESH_CANDIDATES,
            iterations_completed=0,
            bounded=bounded,
        )
    if not scope.get("paper_lanes"):
        return _build_payload(
            status=MULTI_LANE_PAPER_HARVESTER_BLOCKED,
            generated_at=generated_at,
            harvest_id=f"r180_multi_lane_harvest_{uuid4().hex}",
            record_harvest_requested=record_harvest,
            confirmation_valid=True,
            harvest_recorded=False,
            watch_started=False,
            watch_completed=False,
            scope=scope,
            capture_summary=first_eval["capture_summary"],
            lane_capture_counts=build_lane_capture_counts(log_dir=resolved_log_dir, scope=scope, required_fresh_capture_count=capture_threshold_per_lane),
            next_lane_candidate_recommendation=build_next_lane_candidate_recommendation(lane_capture_counts={}, fresh_by_lane={}),
            harvest_status=UNKNOWN_NEEDS_MANUAL_REVIEW,
            iterations_completed=0,
            bounded=bounded,
        )

    harvest_id = f"r180_multi_lane_harvest_{uuid4().hex}"
    sleeper = sleep_fn or time.sleep
    iterations: list[dict[str, Any]] = []
    latest_heartbeat: dict[str, Any] | None = None
    final_summary = first_eval["capture_summary"]
    final_status = MULTI_LANE_PAPER_HARVESTER_TIMEOUT
    captured_candidates: list[dict[str, Any]] = []

    for iteration in range(1, bounded["max_iterations"] + 1):
        started_at = datetime.now(UTC)
        if _should_heartbeat(iteration, bounded["heartbeat_every"]):
            latest_heartbeat = append_multi_lane_harvester_heartbeat(
                build_harvester_heartbeat_record(
                    harvest_id=harvest_id,
                    iteration=iteration,
                    max_iterations=bounded["max_iterations"],
                    sleep_seconds=bounded["sleep_seconds"],
                    status=MULTI_LANE_HARVEST_ITERATION_STARTED,
                    capture_summary=final_summary,
                ),
                log_dir=resolved_log_dir,
            )
        evaluation_started = time.monotonic()
        evaluation = evaluate_multi_lane_paper_candidates(
            log_dir=resolved_log_dir,
            scope=scope,
            latest_signals=bounded["latest_signals"],
            latest_scans=bounded["latest_scans"],
            now=generated_at if now is not None else datetime.now(UTC),
        )
        elapsed_eval = time.monotonic() - evaluation_started
        final_summary = evaluation["capture_summary"]
        selected = _select_capture_candidates(final_summary, max_captures=bounded["max_captures_per_iteration"])
        captured_candidates.extend(selected)
        completed_at = datetime.now(UTC)
        elapsed = (completed_at - started_at).total_seconds()
        timed_out = elapsed_eval > bounded["iteration_timeout_seconds"]
        if timed_out:
            final_status = MULTI_LANE_PAPER_HARVESTER_TIMEOUT
            hb_status = MULTI_LANE_HARVEST_TIMEOUT
        elif selected:
            final_status = MULTI_LANE_PAPER_HARVESTER_CAPTURED
            hb_status = MULTI_LANE_HARVEST_CAPTURED
        else:
            hb_status = MULTI_LANE_HARVEST_ITERATION_COMPLETED
        iterations.append(
            _sanitize(
                {
                    "iteration": iteration,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "elapsed_seconds": round(elapsed, 6),
                    "total_captured": len(selected),
                    "captured_lanes": sorted({row["lane_key"] for row in selected}),
                    "capture_summary": final_summary,
                    "safety": dict(SAFETY),
                }
            )
        )
        if _should_heartbeat(iteration, bounded["heartbeat_every"]) or selected or timed_out:
            latest_heartbeat = append_multi_lane_harvester_heartbeat(
                build_harvester_heartbeat_record(
                    harvest_id=harvest_id,
                    iteration=iteration,
                    max_iterations=bounded["max_iterations"],
                    sleep_seconds=bounded["sleep_seconds"],
                    status=hb_status,
                    elapsed_seconds=elapsed,
                    capture_summary=final_summary,
                    captured_candidates=selected,
                ),
                log_dir=resolved_log_dir,
            )
            _emit_progress(progress_fn, latest_heartbeat)
        if selected or timed_out:
            break
        if iteration < bounded["max_iterations"]:
            sleeper(float(bounded["sleep_seconds"]))

    latest_heartbeat = append_multi_lane_harvester_heartbeat(
        build_harvester_heartbeat_record(
            harvest_id=harvest_id,
            iteration=len(iterations),
            max_iterations=bounded["max_iterations"],
            sleep_seconds=bounded["sleep_seconds"],
            status=MULTI_LANE_HARVEST_EXITED,
            capture_summary=final_summary,
            captured_candidates=captured_candidates,
        ),
        log_dir=resolved_log_dir,
    )
    counts_before_record = build_lane_capture_counts(log_dir=resolved_log_dir, scope=scope, required_fresh_capture_count=capture_threshold_per_lane)
    recommendation = build_next_lane_candidate_recommendation(
        lane_capture_counts=counts_before_record,
        fresh_by_lane=final_summary["fresh_by_lane"],
    )
    harvest_status = classify_multi_lane_harvest_status(
        capture_summary=final_summary,
        lane_capture_counts=counts_before_record,
        recommendation=recommendation,
    )
    payload = _build_payload(
        status=final_status,
        generated_at=generated_at,
        harvest_id=harvest_id,
        record_harvest_requested=record_harvest,
        confirmation_valid=True,
        harvest_recorded=False,
        watch_started=True,
        watch_completed=True,
        scope=scope,
        capture_summary={**final_summary, "captured_candidates": captured_candidates, "total_captured": len(captured_candidates), "captured_lanes": sorted({row["lane_key"] for row in captured_candidates})},
        lane_capture_counts=counts_before_record,
        next_lane_candidate_recommendation=recommendation,
        harvest_status=harvest_status,
        iterations_completed=len(iterations),
        bounded=bounded,
        latest_heartbeat=latest_heartbeat,
        iteration_summaries=iterations,
    )
    if record_harvest:
        record = append_multi_lane_harvester_record(payload, log_dir=resolved_log_dir)
        payload["harvest_recorded"] = True
        payload["harvest_id"] = record["harvest_id"]
        payload["ledger_path"] = str(multi_lane_harvester_records_path(resolved_log_dir))
        payload["lane_capture_counts"] = build_lane_capture_counts(
            log_dir=resolved_log_dir,
            scope=scope,
            required_fresh_capture_count=capture_threshold_per_lane,
        )
        payload["next_lane_candidate_recommendation"] = build_next_lane_candidate_recommendation(
            lane_capture_counts=payload["lane_capture_counts"],
            fresh_by_lane=final_summary["fresh_by_lane"],
        )
        payload["harvest_status"] = classify_multi_lane_harvest_status(
            capture_summary=payload["capture_summary"],
            lane_capture_counts=payload["lane_capture_counts"],
            recommendation=payload["next_lane_candidate_recommendation"],
        )
    return _sanitize(payload)


def build_multi_lane_capture_summary(
    *,
    fresh_by_lane: Mapping[str, int] | Counter[str],
    stale_by_lane: Mapping[str, int] | Counter[str],
    blocked_by_lane: Mapping[str, int] | Counter[str],
    candidates_by_lane: Mapping[str, list[Mapping[str, Any]]],
    observed_by_lane: Mapping[str, int] | Counter[str] | None = None,
) -> dict[str, Any]:
    fresh = {key: int(value) for key, value in sorted(dict(fresh_by_lane).items())}
    stale = {key: int(value) for key, value in sorted(dict(stale_by_lane).items())}
    blocked = {key: int(value) for key, value in sorted(dict(blocked_by_lane).items())}
    candidates = {key: [_sanitize(dict(item)) for item in value] for key, value in sorted(candidates_by_lane.items()) if value}
    return {
        "total_fresh_candidates": sum(fresh.values()),
        "total_captured": 0,
        "captured_lanes": [],
        "fresh_by_lane": fresh,
        "stale_by_lane": stale,
        "blocked_by_lane": blocked,
        "observed_tiny_live_by_lane": {key: int(value) for key, value in sorted(dict(observed_by_lane or {}).items())},
        "candidate_examples_by_lane": candidates,
    }


def build_lane_capture_counts(
    *,
    log_dir: str | Path | None = None,
    scope: Mapping[str, Any] | None = None,
    required_fresh_capture_count: int = DEFAULT_CAPTURE_THRESHOLD_PER_LANE,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    harvest_scope = dict(scope or build_multi_lane_harvest_scope(config_path=config_path))
    paper_lane_keys = [lane["lane_key"] for lane in harvest_scope.get("paper_lanes", [])]
    ids_by_lane: dict[str, list[str]] = {key: [] for key in paper_lane_keys}
    for record in load_multi_lane_harvester_records(log_dir=resolved_log_dir, limit=0):
        for candidate in (record.get("captured_candidates") or record.get("capture_summary", {}).get("captured_candidates") or []):
            if not isinstance(candidate, Mapping):
                continue
            lane_key = str(candidate.get("lane_key") or "")
            signal_id = str(candidate.get("signal_id") or candidate.get("candidate_id") or "").strip()
            if lane_key in ids_by_lane and signal_id and signal_id not in ids_by_lane[lane_key]:
                ids_by_lane[lane_key].append(signal_id)
    if DEFAULT_TARGET_LANE_KEY in ids_by_lane:
        for record in load_short_paper_evidence_capture_records(log_dir=resolved_log_dir, limit=0):
            if record.get("paper_evidence_captured") is not True:
                continue
            lane_key = str(record.get("captured_lane_key") or (record.get("target_lane") or {}).get("lane_key") or "")
            signal_id = str(record.get("captured_signal_id") or "").strip()
            if lane_key == DEFAULT_TARGET_LANE_KEY and signal_id and signal_id not in ids_by_lane[DEFAULT_TARGET_LANE_KEY]:
                ids_by_lane[DEFAULT_TARGET_LANE_KEY].append(signal_id)
    return {
        lane_key: {
            "fresh_capture_count": len(ids),
            "required_fresh_capture_count": int(required_fresh_capture_count),
            "threshold_met": len(ids) >= int(required_fresh_capture_count),
            "unique_captured_signal_ids": list(ids),
            "latest_captured_signal_id": ids[0] if ids else None,
        }
        for lane_key, ids in sorted(ids_by_lane.items())
    }


def build_harvester_heartbeat_record(
    *,
    harvest_id: str,
    iteration: int,
    max_iterations: int,
    sleep_seconds: int,
    status: str,
    elapsed_seconds: float = 0.0,
    capture_summary: Mapping[str, Any] | None = None,
    captured_candidates: list[Mapping[str, Any]] | None = None,
    generated_at: datetime | None = None,
    safety: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    summary = dict(capture_summary or {})
    captured = [dict(row) for row in captured_candidates or []]
    return _sanitize(
        {
            "event_type": HEARTBEAT_EVENT_TYPE,
            "harvest_id": harvest_id,
            "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
            "iteration": int(iteration),
            "max_iterations": int(max_iterations),
            "sleep_seconds": int(sleep_seconds),
            "status": status,
            "elapsed_seconds": round(float(elapsed_seconds), 6),
            "total_fresh_candidates": int(summary.get("total_fresh_candidates") or 0),
            "total_captured": len(captured),
            "captured_lanes": sorted({str(row.get("lane_key") or "") for row in captured if row.get("lane_key")}),
            "fresh_by_lane": dict(summary.get("fresh_by_lane") or {}),
            "safety": dict(safety or SAFETY),
        }
    )


def append_multi_lane_harvester_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = multi_lane_harvester_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "harvest_id": str(record.get("harvest_id") or f"r180_multi_lane_harvest_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_harvest_requested": bool(record.get("record_harvest_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "watch_started": bool(record.get("watch_started")),
            "watch_completed": bool(record.get("watch_completed")),
            "scope": dict(record.get("scope") or {}),
            "capture_summary": dict(record.get("capture_summary") or {}),
            "captured_candidates": list((record.get("capture_summary") or {}).get("captured_candidates") or []),
            "lane_capture_counts": dict(record.get("lane_capture_counts") or {}),
            "next_lane_candidate_recommendation": dict(record.get("next_lane_candidate_recommendation") or {}),
            "harvest_status": record.get("harvest_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def append_multi_lane_harvester_heartbeat(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = multi_lane_harvester_heartbeats_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(dict(record))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_multi_lane_harvester_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = multi_lane_harvester_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_multi_lane_harvester_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    captured = [record for record in records if (record.get("capture_summary") or {}).get("captured_candidates")]
    lane_counts: Counter[str] = Counter()
    for record in captured:
        for candidate in (record.get("capture_summary") or {}).get("captured_candidates") or []:
            if isinstance(candidate, Mapping) and candidate.get("lane_key"):
                lane_counts[str(candidate["lane_key"])] += 1
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "captured_records_count": len(captured),
        "captured_by_lane": dict(sorted(lane_counts.items())),
        "last_harvest_id": records[0].get("harvest_id") if records else None,
        "safety": dict(SAFETY),
    }


def classify_multi_lane_harvest_status(
    *,
    capture_summary: Mapping[str, Any],
    lane_capture_counts: Mapping[str, Any],
    recommendation: Mapping[str, Any],
) -> str:
    if any((row or {}).get("threshold_met") for row in lane_capture_counts.values()):
        return THRESHOLD_MET_FOR_ONE_OR_MORE_LANES
    if bool(recommendation.get("new_lane_candidate_emerged")):
        return NEW_LANE_CANDIDATE_EMERGED
    if bool(recommendation.get("eight_m_short_still_lead")):
        return EIGHT_M_SHORT_STILL_LEAD
    if int(capture_summary.get("total_captured") or 0) > 0 or int(capture_summary.get("total_fresh_candidates") or 0) > 0:
        return CAPTURED_ONE_OR_MORE_LANES
    return NO_FRESH_CANDIDATES


def build_next_lane_candidate_recommendation(
    *,
    lane_capture_counts: Mapping[str, Any],
    fresh_by_lane: Mapping[str, Any],
) -> dict[str, Any]:
    scores: dict[str, int] = {}
    for lane_key, count in fresh_by_lane.items():
        scores[str(lane_key)] = scores.get(str(lane_key), 0) + int(count or 0)
    for lane_key, row in lane_capture_counts.items():
        scores[str(lane_key)] = scores.get(str(lane_key), 0) + int((row or {}).get("fresh_capture_count") or 0)
    eight_score = scores.get(DEFAULT_TARGET_LANE_KEY, 0)
    max_score = max(scores.values()) if scores else 0
    if eight_score == max_score and eight_score > 0:
        lead_lane = DEFAULT_TARGET_LANE_KEY
    else:
        lead_lane = max(scores.items(), key=lambda item: (item[1], item[0]))[0] if scores else None
    lead_score = scores.get(lead_lane, 0) if lead_lane else 0
    new_lane = bool(lead_lane and lead_lane != DEFAULT_TARGET_LANE_KEY and lead_score > eight_score)
    eight_lead = bool(lead_lane == DEFAULT_TARGET_LANE_KEY or (eight_score > 0 and not new_lane))
    if new_lane:
        reason = f"{lead_lane} has the strongest combined fresh flow/capture count."
    elif eight_lead:
        reason = "BTCUSDT 8m short remains tied or ahead in combined fresh flow/capture count."
    else:
        reason = "No paper lane has enough fresh flow yet; keep harvesting."
    return {
        "lead_lane": lead_lane,
        "reason": reason,
        "eight_m_short_still_lead": eight_lead,
        "new_lane_candidate_emerged": new_lane,
    }


def multi_lane_harvester_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def multi_lane_harvester_heartbeats_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / HEARTBEAT_LEDGER_FILENAME


def format_multi_lane_paper_harvester_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_payload(
    *,
    status: str,
    generated_at: datetime,
    harvest_id: str | None,
    record_harvest_requested: bool,
    confirmation_valid: bool,
    harvest_recorded: bool,
    watch_started: bool,
    watch_completed: bool,
    scope: Mapping[str, Any],
    capture_summary: Mapping[str, Any],
    lane_capture_counts: Mapping[str, Any],
    next_lane_candidate_recommendation: Mapping[str, Any],
    harvest_status: str,
    iterations_completed: int,
    bounded: Mapping[str, int],
    latest_heartbeat: Mapping[str, Any] | None = None,
    iteration_summaries: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return _sanitize(
        {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "harvest_id": harvest_id,
            "record_harvest_requested": bool(record_harvest_requested),
            "confirmation_valid": bool(confirmation_valid),
            "harvest_recorded": bool(harvest_recorded),
            "watch_started": bool(watch_started),
            "watch_completed": bool(watch_completed),
            "scope": {
                "paper_lanes": list(scope.get("paper_lanes") or []),
                "observed_tiny_live_lanes": list(scope.get("observed_tiny_live_lanes") or []),
                "timeframes": list(scope.get("timeframes") or []),
                "directions": list(scope.get("directions") or ["long", "short"]),
            },
            "capture_summary": dict(capture_summary),
            "lane_capture_counts": dict(lane_capture_counts),
            "next_lane_candidate_recommendation": dict(next_lane_candidate_recommendation),
            "harvest_status": harvest_status,
            "recommended_next_operator_move": _recommended_next_operator_move(status, harvest_status),
            "recommended_next_engineering_move": _recommended_next_engineering_move(harvest_status),
            "do_not_run_yet": _do_not_run_yet(),
            "iterations_completed": int(iterations_completed),
            "bounded_scan_limits": {
                "latest_signals": int(bounded.get("latest_signals") or DEFAULT_LATEST_SIGNALS),
                "latest_scans": int(bounded.get("latest_scans") or DEFAULT_LATEST_SCANS),
            },
            "max_iterations": int(bounded.get("max_iterations") or DEFAULT_MAX_ITERATIONS),
            "sleep_seconds": int(bounded.get("sleep_seconds") or DEFAULT_SLEEP_SECONDS),
            "iteration_timeout_seconds": int(bounded.get("iteration_timeout_seconds") or DEFAULT_ITERATION_TIMEOUT_SECONDS),
            "heartbeat_every": int(bounded.get("heartbeat_every") or DEFAULT_HEARTBEAT_EVERY),
            "max_captures_per_iteration": int(bounded.get("max_captures_per_iteration") or DEFAULT_MAX_CAPTURES_PER_ITERATION),
            "latest_heartbeat": dict(latest_heartbeat or {}),
            "iteration_summaries": [dict(row) for row in iteration_summaries or []],
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )


def _candidate_window_row(
    raw: Mapping[str, Any],
    candidate: Mapping[str, Any],
    lane: Mapping[str, Any],
    now: datetime,
    *,
    observed_only: bool,
) -> dict[str, Any]:
    entry_mode = str(candidate.get("entry_mode") or raw.get("entry_mode") or TARGET_ENTRY_MODE).strip().lower()
    lane_key = normalize_lane_key(candidate.get("symbol"), candidate.get("timeframe"), candidate.get("direction"), entry_mode)
    timestamp = _first_present(candidate, "timestamp", "generated_at", "closed_at", "detected_at") or raw.get("timestamp")
    age = _age_seconds(timestamp, now)
    freshness_seconds = int(lane.get("freshness_seconds") or 0)
    fresh = age is not None and freshness_seconds > 0 and age <= freshness_seconds
    tradable = _tradable(raw) and _tradable(candidate)
    matches = lane_key == lane.get("lane_key")
    capture_allowed = matches and not observed_only and lane.get("mode") == "paper" and fresh and tradable
    blocker = "capture allowed" if capture_allowed else "candidate stale or missing timestamp"
    if not matches:
        blocker = "lane mismatch"
    elif observed_only:
        blocker = "observed tiny_live reference only"
    elif lane.get("mode") != "paper":
        blocker = "lane mode is not paper"
    elif not tradable:
        blocker = "candidate not tradable or not eligible"
    return _sanitize(
        {
            "signal_id": str(_first_present(candidate, "signal_id", "candidate_id", "id") or _first_present(raw, "signal_id", "candidate_id", "id") or _fallback_candidate_id(raw)),
            "candidate_id": str(_first_present(candidate, "candidate_id", "signal_id", "id") or _first_present(raw, "candidate_id", "signal_id", "id") or _fallback_candidate_id(raw)),
            "source": raw.get("source"),
            "symbol": str(candidate.get("symbol") or "").strip().upper(),
            "timeframe": str(candidate.get("timeframe") or "").strip().lower(),
            "direction": str(candidate.get("direction") or "").strip().lower(),
            "entry_mode": entry_mode,
            "lane_key": lane_key,
            "timestamp": str(timestamp or ""),
            "age_seconds": age,
            "freshness_seconds": freshness_seconds,
            "fresh": fresh,
            "stale": not fresh,
            "tradable": tradable,
            "capture_allowed": capture_allowed,
            "observed_only": bool(observed_only),
            "blocker": blocker,
            "no_live_permission_implied": True,
        }
    )


def _normalize_against_scope(raw: Mapping[str, Any], lanes: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    if str(raw.get("symbol") or "").strip().upper() != TARGET_SYMBOL:
        return []
    direct_key = normalize_lane_key(raw.get("symbol"), raw.get("timeframe"), raw.get("direction"), raw.get("entry_mode") or TARGET_ENTRY_MODE)
    if direct_key in lanes:
        return [dict(raw, lane_key=direct_key, entry_mode=str(raw.get("entry_mode") or TARGET_ENTRY_MODE).strip().lower())]
    possible = [
        key
        for key, lane in lanes.items()
        if lane["symbol"] == str(raw.get("symbol") or "").strip().upper()
        and lane["timeframe"] == str(raw.get("timeframe") or "").strip().lower()
        and lane["direction"] == str(raw.get("direction") or "").strip().lower()
    ]
    normalized: list[dict[str, Any]] = []
    for lane_key in possible:
        normalized.extend(normalize_candidates_for_lane_key([raw], lane_key=lane_key))
    return normalized


def _candidate_row(record: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    raw = dict(record)
    direction = str(_first_present(raw, "direction", "bias_direction", "side") or "").strip().lower()
    if direction in {"buy", "bull", "bullish"}:
        direction = "long"
    if direction in {"sell", "bear", "bearish"}:
        direction = "short"
    timestamp = _first_present(raw, "generated_at", "timestamp", "closed_at", "detected_at")
    return {
        **raw,
        "source": source,
        "signal_id": str(_first_present(raw, "signal_id", "candidate_id", "id") or ""),
        "candidate_id": str(_first_present(raw, "candidate_id", "signal_id", "id") or ""),
        "symbol": str(_first_present(raw, "symbol", "base_symbol") or "").strip().upper(),
        "timeframe": str(_first_present(raw, "timeframe", "tf", "interval") or "").strip().lower(),
        "direction": direction,
        "entry_mode": str(_first_present(raw, "entry_mode", "mode") or TARGET_ENTRY_MODE).strip().lower(),
        "timestamp": str(timestamp or ""),
    }


def _select_capture_candidates(summary: Mapping[str, Any], *, max_captures: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for lane_key, rows in sorted((summary.get("candidate_examples_by_lane") or {}).items()):
        for row in rows:
            signal_id = str(row.get("signal_id") or row.get("candidate_id") or "")
            key = (str(lane_key), signal_id)
            if key in seen:
                continue
            seen.add(key)
            selected.append(_sanitize(dict(row)))
            if len(selected) >= max_captures:
                return selected
    return selected


def _preview_status(scope: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    if not scope.get("paper_lanes"):
        return MULTI_LANE_PAPER_HARVESTER_BLOCKED
    if int(summary.get("total_fresh_candidates") or 0) > 0:
        return MULTI_LANE_PAPER_HARVESTER_READY
    return MULTI_LANE_PAPER_HARVESTER_PREVIEW


def _recommended_next_operator_move(status: str, harvest_status: str) -> str:
    if status == MULTI_LANE_PAPER_HARVESTER_REJECTED:
        return "START_MULTI_LANE_HARVESTER"
    if harvest_status == THRESHOLD_MET_FOR_ONE_OR_MORE_LANES:
        return "RUN_R181_MULTI_LANE_EVIDENCE_RANKING"
    if harvest_status == EIGHT_M_SHORT_STILL_LEAD:
        return "RUN_R177_IF_8M_SHORT_REACHES_10"
    if status in {MULTI_LANE_PAPER_HARVESTER_PREVIEW, MULTI_LANE_PAPER_HARVESTER_READY}:
        return "START_MULTI_LANE_HARVESTER"
    return "KEEP_MULTI_LANE_HARVESTER_RUNNING"


def _recommended_next_engineering_move(harvest_status: str) -> str:
    if harvest_status in {NEW_LANE_CANDIDATE_EMERGED, THRESHOLD_MET_FOR_ONE_OR_MORE_LANES}:
        return "Prepare R181 multi-lane evidence ranking and next-door selection without live execution or config writes."
    return "Keep R180 harvesting local paper evidence and compare lane counts before any future R181 ranking."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set any lane tiny_live",
        "write risk contract config",
        "transfer",
        "withdraw",
    ]


def _compact_lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_key": str(lane.get("lane_key") or normalize_lane_key(lane.get("symbol"), lane.get("timeframe"), lane.get("direction"), lane.get("entry_mode"))),
        "symbol": str(lane.get("symbol") or "").strip().upper(),
        "timeframe": str(lane.get("timeframe") or "").strip().lower(),
        "direction": str(lane.get("direction") or "").strip().lower(),
        "entry_mode": str(lane.get("entry_mode") or TARGET_ENTRY_MODE).strip().lower(),
        "mode": str(lane.get("mode") or "disabled").strip().lower(),
        "freshness_seconds": int(lane.get("freshness_seconds") or 0),
    }


def _is_target_lane(lane: Mapping[str, Any]) -> bool:
    return str(lane.get("symbol") or "").strip().upper() == TARGET_SYMBOL and str(lane.get("entry_mode") or "").strip().lower() == TARGET_ENTRY_MODE


def _bounded_settings(
    *,
    latest_signals: int,
    latest_scans: int,
    max_iterations: int,
    sleep_seconds: int,
    iteration_timeout_seconds: int,
    heartbeat_every: int,
    max_captures_per_iteration: int,
) -> dict[str, int]:
    return {
        "latest_signals": _bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS),
        "latest_scans": _bounded_int(latest_scans, 1, MAX_LATEST_SCANS, DEFAULT_LATEST_SCANS),
        "max_iterations": _bounded_int(max_iterations, 1, MAX_MAX_ITERATIONS, DEFAULT_MAX_ITERATIONS),
        "sleep_seconds": _bounded_int(sleep_seconds, 1, MAX_SLEEP_SECONDS, DEFAULT_SLEEP_SECONDS),
        "iteration_timeout_seconds": _bounded_int(iteration_timeout_seconds, 1, MAX_ITERATION_TIMEOUT_SECONDS, DEFAULT_ITERATION_TIMEOUT_SECONDS),
        "heartbeat_every": _bounded_int(heartbeat_every, 1, MAX_HEARTBEAT_EVERY, DEFAULT_HEARTBEAT_EVERY),
        "max_captures_per_iteration": _bounded_int(max_captures_per_iteration, 1, MAX_CAPTURES_PER_ITERATION, DEFAULT_MAX_CAPTURES_PER_ITERATION),
    }


def _should_heartbeat(iteration: int, heartbeat_every: int) -> bool:
    return int(heartbeat_every) > 0 and int(iteration) % int(heartbeat_every) == 0


def _emit_progress(progress_fn: Callable[[str], None] | None, heartbeat: Mapping[str, Any]) -> None:
    if progress_fn is None:
        return
    progress_fn(json.dumps(_sanitize(heartbeat), sort_keys=True, separators=(",", ":")))


def _ordered_timeframes(values: list[str] | tuple[str, ...]) -> list[str]:
    return sorted({str(value or "").strip().lower() for value in values if str(value or "").strip()}, key=_timeframe_sort_key)


def _timeframe_sort_key(value: str) -> tuple[int, str]:
    text = str(value or "").lower()
    digits = "".join(ch for ch in text if ch.isdigit())
    unit = "".join(ch for ch in text if ch.isalpha())
    multiplier = {"m": 1, "h": 60, "d": 1440}.get(unit or "m", 1)
    return (int(digits or 0) * multiplier, text)


def _tradable(row: Mapping[str, Any]) -> bool:
    for key in ("tradable", "eligible", "paper_eligible", "capture_allowed"):
        if key in row and row.get(key) is False:
            return False
    return True


def _first_present(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _age_seconds(value: object, now: datetime) -> int | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return max(0, int((now - parsed).total_seconds()))


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _fallback_candidate_id(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("source") or "candidate"),
            str(row.get("symbol") or ""),
            str(row.get("timeframe") or ""),
            str(row.get("direction") or ""),
            str(row.get("timestamp") or ""),
        ]
    )


def _bounded_int(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _error_payload(*, generated_at: datetime, record_harvest: bool, confirmation_valid: bool, error: Exception) -> dict[str, Any]:
    return _sanitize(
        {
            "status": MULTI_LANE_PAPER_HARVESTER_ERROR,
            "generated_at": generated_at.isoformat(),
            "harvest_id": None,
            "record_harvest_requested": bool(record_harvest),
            "confirmation_valid": bool(confirmation_valid),
            "harvest_recorded": False,
            "watch_started": False,
            "watch_completed": False,
            "scope": {"paper_lanes": [], "observed_tiny_live_lanes": [], "timeframes": [], "directions": ["long", "short"]},
            "capture_summary": build_multi_lane_capture_summary(fresh_by_lane={}, stale_by_lane={}, blocked_by_lane={}, candidates_by_lane={}),
            "lane_capture_counts": {},
            "next_lane_candidate_recommendation": build_next_lane_candidate_recommendation(lane_capture_counts={}, fresh_by_lane={}),
            "harvest_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
            "recommended_next_operator_move": "START_MULTI_LANE_HARVESTER",
            "recommended_next_engineering_move": "Fix the R180 harvester error before collecting more evidence.",
            "do_not_run_yet": _do_not_run_yet(),
            "error": error.__class__.__name__,
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )


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
