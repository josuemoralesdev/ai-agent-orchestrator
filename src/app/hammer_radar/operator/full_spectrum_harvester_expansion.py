"""R198 full-spectrum harvester expansion.

This surface expands local paper harvest visibility from R196 blind spots. It
never writes lane config, creates payloads, calls Binance/network, promotes
lanes/origins, or authorizes live execution.
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
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_paper_coverage_audit import (
    build_full_spectrum_paper_coverage_audit,
    load_full_spectrum_paper_coverage_audit_records,
)
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE, load_lane_controls, normalize_lane_key
from src.app.hammer_radar.operator.multi_lane_paper_capture_harvester import (
    MAX_CAPTURES_PER_ITERATION,
    MAX_HEARTBEAT_EVERY,
    MAX_ITERATION_TIMEOUT_SECONDS,
    MAX_LATEST_SCANS,
    MAX_LATEST_SIGNALS,
    MAX_MAX_ITERATIONS,
    MAX_SLEEP_SECONDS,
    _age_seconds,
    _bounded_int,
    _candidate_row,
    _emit_progress,
    _fallback_candidate_id,
    _first_present,
    _select_capture_candidates,
    _should_heartbeat,
    _tradable,
)
from src.app.hammer_radar.operator.paper_opportunity_expansion import TARGET_ENTRY_MODE, TARGET_SYMBOL

FULL_SPECTRUM_HARVESTER_EXPANSION_READY = "FULL_SPECTRUM_HARVESTER_EXPANSION_READY"
FULL_SPECTRUM_HARVESTER_EXPANSION_REJECTED = "FULL_SPECTRUM_HARVESTER_EXPANSION_REJECTED"
FULL_SPECTRUM_HARVESTER_EXPANSION_RECORDED = "FULL_SPECTRUM_HARVESTER_EXPANSION_RECORDED"
FULL_SPECTRUM_HARVESTER_EXPANSION_TIMEOUT = "FULL_SPECTRUM_HARVESTER_EXPANSION_TIMEOUT"
FULL_SPECTRUM_HARVESTER_EXPANSION_CAPTURED = "FULL_SPECTRUM_HARVESTER_EXPANSION_CAPTURED"
FULL_SPECTRUM_HARVESTER_EXPANSION_BLOCKED = "FULL_SPECTRUM_HARVESTER_EXPANSION_BLOCKED"
FULL_SPECTRUM_HARVESTER_EXPANSION_ERROR = "FULL_SPECTRUM_HARVESTER_EXPANSION_ERROR"

FULL_SPECTRUM_SCOPE_READY = "FULL_SPECTRUM_SCOPE_READY"
NO_FRESH_CANDIDATES = "NO_FRESH_CANDIDATES"
CAPTURED_ONE_OR_MORE_LANES = "CAPTURED_ONE_OR_MORE_LANES"
COVERAGE_GAPS_REMAIN = "COVERAGE_GAPS_REMAIN"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

FULL_SPECTRUM_HARVEST_ITERATION_STARTED = "FULL_SPECTRUM_HARVEST_ITERATION_STARTED"
FULL_SPECTRUM_HARVEST_ITERATION_COMPLETED = "FULL_SPECTRUM_HARVEST_ITERATION_COMPLETED"
FULL_SPECTRUM_HARVEST_CAPTURED = "FULL_SPECTRUM_HARVEST_CAPTURED"
FULL_SPECTRUM_HARVEST_TIMEOUT = "FULL_SPECTRUM_HARVEST_TIMEOUT"
FULL_SPECTRUM_HARVEST_EXITED = "FULL_SPECTRUM_HARVEST_EXITED"

EVENT_TYPE = "FULL_SPECTRUM_HARVESTER_EXPANSION"
HEARTBEAT_EVENT_TYPE = "FULL_SPECTRUM_HARVESTER_EXPANSION_HEARTBEAT"
LEDGER_FILENAME = "full_spectrum_harvester_expansion.ndjson"
HEARTBEAT_LEDGER_FILENAME = "full_spectrum_harvester_heartbeats.ndjson"
CONFIRM_FULL_SPECTRUM_HARVEST_PHRASE = (
    "I CONFIRM FULL SPECTRUM PAPER HARVESTING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_EXPANDED_TIMEFRAMES = ("4m", "8m", "13m", "22m", "44m", "55m", "88m", "222m", "444m", "666m", "888m", "4H", "13H", "13D")
DEFAULT_DIRECTIONS = ("long", "short")
DEFAULT_ENTRY_MODE = TARGET_ENTRY_MODE
DEFAULT_LATEST_SIGNALS = 3000
DEFAULT_LATEST_SCANS = 5000
DEFAULT_MAX_ITERATIONS = 60
DEFAULT_SLEEP_SECONDS = 60
DEFAULT_ITERATION_TIMEOUT_SECONDS = 30
DEFAULT_HEARTBEAT_EVERY = 1
DEFAULT_MAX_CAPTURES_PER_ITERATION = 50
DISCOVERED_UNCONFIGURED_FRESHNESS_SECONDS = 900

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "registry_config_written": False,
    "scoring_config_written": False,
    "matrix_config_written": False,
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
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
    "live_authorization_created": False,
    "signal_origin_promoted": False,
    "lane_promoted": False,
    "wma_anchor_live_authorized": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/full_spectrum_paper_coverage_audit.ndjson",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "logs/hammer_radar_forward/multi_lane_paper_harvester.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{HEARTBEAT_LEDGER_FILENAME}",
    "operator.full_spectrum_paper_coverage_audit",
    "operator.multi_lane_paper_capture_harvester local candidate parsing helpers",
]


def build_full_spectrum_harvester_expansion(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    iteration_timeout_seconds: int = DEFAULT_ITERATION_TIMEOUT_SECONDS,
    heartbeat_every: int = DEFAULT_HEARTBEAT_EVERY,
    max_captures_per_iteration: int = DEFAULT_MAX_CAPTURES_PER_ITERATION,
    run_harvester_loop: bool = False,
    record_harvest: bool = False,
    confirm_full_spectrum_harvest: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    progress_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    return run_full_spectrum_harvester_loop(
        log_dir=log_dir,
        latest_signals=latest_signals,
        latest_scans=latest_scans,
        max_iterations=max_iterations,
        sleep_seconds=sleep_seconds,
        iteration_timeout_seconds=iteration_timeout_seconds,
        heartbeat_every=heartbeat_every,
        max_captures_per_iteration=max_captures_per_iteration,
        run_harvester_loop=run_harvester_loop,
        record_harvest=record_harvest,
        confirm_full_spectrum_harvest=confirm_full_spectrum_harvest,
        config_path=config_path,
        now=now,
        sleep_fn=sleep_fn,
        progress_fn=progress_fn,
    )


def load_latest_full_spectrum_coverage_audit(*, log_dir: str | Path | None = None, config_path: str | Path | None = None) -> dict[str, Any]:
    records = load_full_spectrum_paper_coverage_audit_records(log_dir=log_dir, limit=1)
    if records:
        return records[0]
    return build_full_spectrum_paper_coverage_audit(log_dir=log_dir, config_path=config_path)


def build_expanded_harvest_scope_from_blind_spots(*, audit: Mapping[str, Any]) -> dict[str, Any]:
    blind = dict(audit.get("blind_spot_report") or {})
    signals_present = [
        lane
        for lane in blind.get("signals_present_not_configured") or []
        if _is_default_btc_ladder_lane(str(lane))
    ]
    seen_tfs = [
        _normalize_timeframe(tf)
        for tf in blind.get("timeframes_seen_but_not_currently_harvested") or []
        if _normalize_timeframe(tf)
    ]
    for lane_key in signals_present:
        lane = _lane_from_key(lane_key)
        if lane["timeframe"] not in seen_tfs:
            seen_tfs.append(lane["timeframe"])
    return {
        "signals_present_not_configured": sorted(set(signals_present), key=_lane_sort_key),
        "timeframes_seen_but_not_currently_harvested": _ordered_timeframes(seen_tfs),
        "paper_outcomes_without_current_watcher_count": len(blind.get("paper_outcomes_without_current_watcher") or []),
    }


def build_full_spectrum_lane_candidates(
    *,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    coverage_audit = dict(audit or load_latest_full_spectrum_coverage_audit(log_dir=resolved_log_dir, config_path=config_path))
    coverage_gap_inputs = build_expanded_harvest_scope_from_blind_spots(audit=coverage_audit)
    controls = load_lane_controls(Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH)
    configured: dict[str, dict[str, Any]] = {}
    tiny_refs: dict[str, dict[str, Any]] = {}
    for row in controls.get("lanes") or []:
        lane = _compact_config_lane(row)
        if not _is_default_btc_ladder_lane(lane["lane_key"]):
            continue
        if lane["mode"] == "paper":
            configured[lane["lane_key"]] = {**lane, "config_write_allowed": False, "live_authorized": False}
        elif lane["mode"] == "tiny_live":
            tiny_refs[lane["lane_key"]] = {**lane, "reference_only": True, "config_write_allowed": False, "live_authorized": False}

    desired_keys = {
        normalize_lane_key(TARGET_SYMBOL, timeframe, direction, DEFAULT_ENTRY_MODE)
        for timeframe in DEFAULT_EXPANDED_TIMEFRAMES
        for direction in DEFAULT_DIRECTIONS
    }
    desired_keys.update(coverage_gap_inputs["signals_present_not_configured"])
    discovered = {}
    for lane_key in desired_keys:
        if lane_key in configured or lane_key in tiny_refs:
            continue
        lane = _lane_from_key(lane_key)
        discovered[lane_key] = {
            **lane,
            "mode": "paper_discovered_unconfigured",
            "freshness_seconds": DISCOVERED_UNCONFIGURED_FRESHNESS_SECONDS,
            "config_write_allowed": False,
            "live_authorized": False,
        }

    all_scope = [*configured.values(), *discovered.values(), *tiny_refs.values()]
    return _sanitize(
        {
            "configured_paper_lanes": sorted(configured.values(), key=lambda row: _lane_sort_key(row["lane_key"])),
            "discovered_unconfigured_paper_lanes": sorted(discovered.values(), key=lambda row: _lane_sort_key(row["lane_key"])),
            "tiny_live_reference_lanes": sorted(tiny_refs.values(), key=lambda row: _lane_sort_key(row["lane_key"])),
            "timeframes": _ordered_timeframes([lane["timeframe"] for lane in all_scope] + list(DEFAULT_EXPANDED_TIMEFRAMES)),
            "directions": list(DEFAULT_DIRECTIONS),
            "entry_modes": [DEFAULT_ENTRY_MODE],
        }
    )


def build_full_spectrum_harvester_preview(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    iteration_timeout_seconds: int = DEFAULT_ITERATION_TIMEOUT_SECONDS,
    heartbeat_every: int = DEFAULT_HEARTBEAT_EVERY,
    max_captures_per_iteration: int = DEFAULT_MAX_CAPTURES_PER_ITERATION,
    record_harvest: bool = False,
    confirm_full_spectrum_harvest: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_full_spectrum_harvest == CONFIRM_FULL_SPECTRUM_HARVEST_PHRASE
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
        audit = load_latest_full_spectrum_coverage_audit(log_dir=resolved_log_dir, config_path=config_path)
        scope = build_full_spectrum_lane_candidates(log_dir=resolved_log_dir, config_path=config_path, audit=audit)
        coverage_gap_inputs = build_expanded_harvest_scope_from_blind_spots(audit=audit)
        capture_summary = _evaluate_full_spectrum_candidates(
            log_dir=resolved_log_dir,
            scope=scope,
            latest_signals=bounded["latest_signals"],
            latest_scans=bounded["latest_scans"],
            now=generated_at,
        )["capture_summary"]
        full_summary = build_full_spectrum_harvest_summary(scope=scope, capture_summary=capture_summary, coverage_gap_inputs=coverage_gap_inputs)
        harvest_status = _classify_harvest_status(capture_summary=capture_summary, summary=full_summary)
        status = FULL_SPECTRUM_HARVESTER_EXPANSION_READY if scope["configured_paper_lanes"] or scope["discovered_unconfigured_paper_lanes"] else FULL_SPECTRUM_HARVESTER_EXPANSION_BLOCKED
        if record_harvest and not confirmation_valid:
            status = FULL_SPECTRUM_HARVESTER_EXPANSION_REJECTED
        elif record_harvest and confirmation_valid:
            status = FULL_SPECTRUM_HARVESTER_EXPANSION_RECORDED
        payload = _build_payload(
            status=status,
            generated_at=generated_at,
            harvest_id=None,
            record_harvest_requested=record_harvest,
            confirmation_valid=confirmation_valid,
            harvest_recorded=False,
            scope=scope,
            coverage_gap_inputs=coverage_gap_inputs,
            capture_summary=capture_summary,
            full_spectrum_harvest_summary=full_summary,
            harvest_status=harvest_status,
            bounded=bounded,
            iterations_completed=0,
        )
        if record_harvest and confirmation_valid:
            record = append_full_spectrum_harvester_record(payload, log_dir=resolved_log_dir)
            payload["harvest_recorded"] = True
            payload["harvest_id"] = record["harvest_id"]
            payload["ledger_path"] = str(full_spectrum_harvester_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _error_payload(generated_at=generated_at, record_harvest=record_harvest, confirmation_valid=confirmation_valid, error=exc)


def capture_full_spectrum_paper_evidence_once(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    max_captures_per_iteration: int = DEFAULT_MAX_CAPTURES_PER_ITERATION,
    record_harvest: bool = False,
    confirm_full_spectrum_harvest: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    return run_full_spectrum_harvester_loop(
        log_dir=log_dir,
        latest_signals=latest_signals,
        latest_scans=latest_scans,
        max_iterations=1,
        sleep_seconds=1,
        iteration_timeout_seconds=DEFAULT_ITERATION_TIMEOUT_SECONDS,
        heartbeat_every=1,
        max_captures_per_iteration=max_captures_per_iteration,
        run_harvester_loop=True,
        record_harvest=record_harvest,
        confirm_full_spectrum_harvest=confirm_full_spectrum_harvest,
        config_path=config_path,
        now=now,
        sleep_fn=lambda _seconds: None,
    )


def run_full_spectrum_harvester_loop(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    iteration_timeout_seconds: int = DEFAULT_ITERATION_TIMEOUT_SECONDS,
    heartbeat_every: int = DEFAULT_HEARTBEAT_EVERY,
    max_captures_per_iteration: int = DEFAULT_MAX_CAPTURES_PER_ITERATION,
    run_harvester_loop: bool = False,
    record_harvest: bool = False,
    confirm_full_spectrum_harvest: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    progress_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_full_spectrum_harvest == CONFIRM_FULL_SPECTRUM_HARVEST_PHRASE
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
        return build_full_spectrum_harvester_preview(
            log_dir=resolved_log_dir,
            latest_signals=bounded["latest_signals"],
            latest_scans=bounded["latest_scans"],
            max_iterations=bounded["max_iterations"],
            sleep_seconds=bounded["sleep_seconds"],
            iteration_timeout_seconds=bounded["iteration_timeout_seconds"],
            heartbeat_every=bounded["heartbeat_every"],
            max_captures_per_iteration=bounded["max_captures_per_iteration"],
            record_harvest=record_harvest,
            confirm_full_spectrum_harvest=confirm_full_spectrum_harvest,
            config_path=config_path,
            now=generated_at,
        )

    audit = load_latest_full_spectrum_coverage_audit(log_dir=resolved_log_dir, config_path=config_path)
    scope = build_full_spectrum_lane_candidates(log_dir=resolved_log_dir, config_path=config_path, audit=audit)
    coverage_gap_inputs = build_expanded_harvest_scope_from_blind_spots(audit=audit)
    first_eval = _evaluate_full_spectrum_candidates(
        log_dir=resolved_log_dir,
        scope=scope,
        latest_signals=bounded["latest_signals"],
        latest_scans=bounded["latest_scans"],
        now=generated_at,
    )
    if not confirmation_valid:
        full_summary = build_full_spectrum_harvest_summary(scope=scope, capture_summary=first_eval["capture_summary"], coverage_gap_inputs=coverage_gap_inputs)
        return _build_payload(
            status=FULL_SPECTRUM_HARVESTER_EXPANSION_REJECTED,
            generated_at=generated_at,
            harvest_id=None,
            record_harvest_requested=record_harvest,
            confirmation_valid=False,
            harvest_recorded=False,
            scope=scope,
            coverage_gap_inputs=coverage_gap_inputs,
            capture_summary=first_eval["capture_summary"],
            full_spectrum_harvest_summary=full_summary,
            harvest_status=UNKNOWN_NEEDS_MANUAL_REVIEW,
            bounded=bounded,
            iterations_completed=0,
        )
    if not scope["configured_paper_lanes"] and not scope["discovered_unconfigured_paper_lanes"]:
        full_summary = build_full_spectrum_harvest_summary(scope=scope, capture_summary=first_eval["capture_summary"], coverage_gap_inputs=coverage_gap_inputs)
        return _build_payload(
            status=FULL_SPECTRUM_HARVESTER_EXPANSION_BLOCKED,
            generated_at=generated_at,
            harvest_id=f"r198_full_spectrum_harvest_{uuid4().hex}",
            record_harvest_requested=record_harvest,
            confirmation_valid=True,
            harvest_recorded=False,
            scope=scope,
            coverage_gap_inputs=coverage_gap_inputs,
            capture_summary=first_eval["capture_summary"],
            full_spectrum_harvest_summary=full_summary,
            harvest_status=UNKNOWN_NEEDS_MANUAL_REVIEW,
            bounded=bounded,
            iterations_completed=0,
        )

    harvest_id = f"r198_full_spectrum_harvest_{uuid4().hex}"
    sleeper = sleep_fn or time.sleep
    iterations = []
    latest_heartbeat: dict[str, Any] | None = None
    final_summary = first_eval["capture_summary"]
    final_status = FULL_SPECTRUM_HARVESTER_EXPANSION_TIMEOUT
    captured_candidates: list[dict[str, Any]] = []

    for iteration in range(1, bounded["max_iterations"] + 1):
        started_at = datetime.now(UTC)
        if _should_heartbeat(iteration, bounded["heartbeat_every"]):
            latest_heartbeat = append_full_spectrum_harvester_heartbeat(
                _build_heartbeat_record(
                    harvest_id=harvest_id,
                    iteration=iteration,
                    max_iterations=bounded["max_iterations"],
                    sleep_seconds=bounded["sleep_seconds"],
                    status=FULL_SPECTRUM_HARVEST_ITERATION_STARTED,
                    capture_summary=final_summary,
                ),
                log_dir=resolved_log_dir,
            )
        evaluation_started = time.monotonic()
        evaluation = _evaluate_full_spectrum_candidates(
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
            final_status = FULL_SPECTRUM_HARVESTER_EXPANSION_TIMEOUT
            hb_status = FULL_SPECTRUM_HARVEST_TIMEOUT
        elif selected:
            final_status = FULL_SPECTRUM_HARVESTER_EXPANSION_CAPTURED
            hb_status = FULL_SPECTRUM_HARVEST_CAPTURED
        else:
            hb_status = FULL_SPECTRUM_HARVEST_ITERATION_COMPLETED
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
            latest_heartbeat = append_full_spectrum_harvester_heartbeat(
                _build_heartbeat_record(
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

    latest_heartbeat = append_full_spectrum_harvester_heartbeat(
        _build_heartbeat_record(
            harvest_id=harvest_id,
            iteration=len(iterations),
            max_iterations=bounded["max_iterations"],
            sleep_seconds=bounded["sleep_seconds"],
            status=FULL_SPECTRUM_HARVEST_EXITED,
            capture_summary=final_summary,
            captured_candidates=captured_candidates,
        ),
        log_dir=resolved_log_dir,
    )
    final_summary = {
        **final_summary,
        "captured_candidates": captured_candidates,
        "total_captured": len(captured_candidates),
        "captured_lanes": sorted({row["lane_key"] for row in captured_candidates}),
    }
    full_summary = build_full_spectrum_harvest_summary(scope=scope, capture_summary=final_summary, coverage_gap_inputs=coverage_gap_inputs)
    harvest_status = _classify_harvest_status(capture_summary=final_summary, summary=full_summary)
    payload = _build_payload(
        status=final_status,
        generated_at=generated_at,
        harvest_id=harvest_id,
        record_harvest_requested=record_harvest,
        confirmation_valid=True,
        harvest_recorded=False,
        scope=scope,
        coverage_gap_inputs=coverage_gap_inputs,
        capture_summary=final_summary,
        full_spectrum_harvest_summary=full_summary,
        harvest_status=harvest_status,
        bounded=bounded,
        iterations_completed=len(iterations),
        latest_heartbeat=latest_heartbeat,
        iteration_summaries=iterations,
    )
    if record_harvest:
        record = append_full_spectrum_harvester_record(payload, log_dir=resolved_log_dir)
        payload["harvest_recorded"] = True
        payload["harvest_id"] = record["harvest_id"]
        payload["ledger_path"] = str(full_spectrum_harvester_records_path(resolved_log_dir))
    return _sanitize(payload)


def build_full_spectrum_harvest_summary(
    *,
    scope: Mapping[str, Any],
    capture_summary: Mapping[str, Any],
    coverage_gap_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    configured = list(scope.get("configured_paper_lanes") or [])
    discovered = list(scope.get("discovered_unconfigured_paper_lanes") or [])
    all_capture_lanes = [*configured, *discovered]
    fresh = set((capture_summary.get("fresh_by_lane") or {}).keys())
    stale = set((capture_summary.get("stale_by_lane") or {}).keys())
    remaining = [
        lane["lane_key"]
        for lane in all_capture_lanes
        if lane["lane_key"] in set(coverage_gap_inputs.get("signals_present_not_configured") or []) and lane["lane_key"] not in fresh
    ]
    remaining.extend(tf for tf in coverage_gap_inputs.get("timeframes_seen_but_not_currently_harvested") or [] if not _timeframe_has_fresh_flow(tf, fresh))
    return {
        "lanes_in_scope": len(all_capture_lanes) + len(scope.get("tiny_live_reference_lanes") or []),
        "configured_lanes": len(configured),
        "discovered_unconfigured_lanes": len(discovered),
        "lanes_with_fresh_flow": sorted(fresh, key=_lane_sort_key),
        "lanes_with_stale_only": sorted(stale - fresh, key=_lane_sort_key),
        "coverage_gaps_remaining": sorted(set(remaining), key=str),
    }


def build_full_spectrum_harvester_commands() -> dict[str, str]:
    base = "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward full-spectrum-harvester-expansion"
    return {
        "tmux_session": "r198-full-spectrum-harvest",
        "preview_command": f"{base} --latest-signals 3000 --latest-scans 5000",
        "bounded_loop_command": (
            f'{base} --latest-signals 3000 --latest-scans 5000 --max-iterations 60 --sleep-seconds 60 '
            f'--iteration-timeout-seconds 30 --heartbeat-every 1 --max-captures-per-iteration 50 '
            f'--run-harvester-loop --record-harvest --confirm-full-spectrum-harvest "{CONFIRM_FULL_SPECTRUM_HARVEST_PHRASE}"'
        ),
    }


def append_full_spectrum_harvester_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = full_spectrum_harvester_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            **dict(record),
            "event_type": EVENT_TYPE,
            "harvest_id": str(record.get("harvest_id") or f"r198_full_spectrum_harvest_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "harvest_recorded": True,
            "safety": dict(SAFETY),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def append_full_spectrum_harvester_heartbeat(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = full_spectrum_harvester_heartbeats_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(dict(record))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_full_spectrum_harvester_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = full_spectrum_harvester_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_full_spectrum_harvester_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    captured_by_lane: Counter[str] = Counter()
    for record in records:
        for lane in (record.get("capture_summary") or {}).get("captured_lanes") or []:
            captured_by_lane[str(lane)] += 1
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "captured_by_lane": dict(sorted(captured_by_lane.items())),
        "last_harvest_id": records[0].get("harvest_id") if records else None,
        "safety": dict(SAFETY),
    }


def full_spectrum_harvester_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def full_spectrum_harvester_heartbeats_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / HEARTBEAT_LEDGER_FILENAME


def format_full_spectrum_harvester_expansion_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _evaluate_full_spectrum_candidates(
    *,
    log_dir: str | Path,
    scope: Mapping[str, Any],
    latest_signals: int,
    latest_scans: int,
    now: datetime,
) -> dict[str, Any]:
    raw_candidates = [
        *[_candidate_row(record, source="signals.ndjson") for record in reversed(read_recent_ndjson_records(get_signals_path(log_dir), limit=latest_signals, max_bytes=16_777_216))],
        *[_candidate_row(record, source="multi_symbol_paper_scans.ndjson") for record in reversed(read_recent_ndjson_records(Path(log_dir) / "multi_symbol_paper_scans.ndjson", limit=latest_scans, max_bytes=32_000_000))],
    ]
    lanes = {
        lane["lane_key"]: lane
        for lane in [
            *scope.get("configured_paper_lanes", []),
            *scope.get("discovered_unconfigured_paper_lanes", []),
            *scope.get("tiny_live_reference_lanes", []),
        ]
    }
    tiny_ref_keys = {lane["lane_key"] for lane in scope.get("tiny_live_reference_lanes", [])}
    rows = []
    fresh_by_lane: Counter[str] = Counter()
    stale_by_lane: Counter[str] = Counter()
    blocked_by_lane: Counter[str] = Counter()
    candidates_by_lane: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for raw in raw_candidates:
        lane_key = normalize_lane_key(raw.get("symbol"), raw.get("timeframe"), raw.get("direction"), raw.get("entry_mode") or DEFAULT_ENTRY_MODE)
        lane = lanes.get(lane_key)
        if not lane:
            if str(raw.get("symbol") or "").strip().upper() == TARGET_SYMBOL:
                blocked_by_lane[lane_key] += 1
            continue
        row = _candidate_window_row(raw, lane, now, observed_only=lane_key in tiny_ref_keys)
        rows.append(row)
        if row["capture_allowed"]:
            fresh_by_lane[lane_key] += 1
            if len(candidates_by_lane[lane_key]) < 20:
                candidates_by_lane[lane_key].append(row)
        elif row["stale"]:
            stale_by_lane[lane_key] += 1
        else:
            blocked_by_lane[lane_key] += 1

    fresh = {key: int(value) for key, value in sorted(fresh_by_lane.items(), key=lambda item: _lane_sort_key(item[0]))}
    stale = {key: int(value) for key, value in sorted(stale_by_lane.items(), key=lambda item: _lane_sort_key(item[0]))}
    blocked = {key: int(value) for key, value in sorted(blocked_by_lane.items(), key=lambda item: _lane_sort_key(item[0]))}
    return _sanitize(
        {
            "recent_matching_candidates": rows[:20],
            "capture_summary": {
                "total_fresh_candidates": sum(fresh.values()),
                "total_captured": 0,
                "captured_lanes": [],
                "fresh_by_lane": fresh,
                "stale_by_lane": stale,
                "blocked_by_lane": blocked,
                "candidate_examples_by_lane": {key: rows for key, rows in sorted(candidates_by_lane.items(), key=lambda item: _lane_sort_key(item[0]))},
            },
            "safety": dict(SAFETY),
        }
    )


def _candidate_window_row(raw: Mapping[str, Any], lane: Mapping[str, Any], now: datetime, *, observed_only: bool) -> dict[str, Any]:
    entry_mode = str(raw.get("entry_mode") or DEFAULT_ENTRY_MODE).strip().lower()
    lane_key = normalize_lane_key(raw.get("symbol"), raw.get("timeframe"), raw.get("direction"), entry_mode)
    timestamp = _first_present(raw, "timestamp", "generated_at", "closed_at", "detected_at")
    age = _age_seconds(timestamp, now)
    freshness_seconds = int(lane.get("freshness_seconds") or DISCOVERED_UNCONFIGURED_FRESHNESS_SECONDS)
    fresh = age is not None and freshness_seconds > 0 and age <= freshness_seconds
    tradable = _tradable(raw)
    mode = str(lane.get("mode") or "")
    paper_runtime_mode = mode in {"paper", "paper_discovered_unconfigured"}
    capture_allowed = lane_key == lane.get("lane_key") and not observed_only and paper_runtime_mode and fresh and tradable
    blocker = "capture allowed" if capture_allowed else "candidate stale or missing timestamp"
    if lane_key != lane.get("lane_key"):
        blocker = "lane mismatch"
    elif observed_only:
        blocker = "observed tiny_live reference only"
    elif not paper_runtime_mode:
        blocker = "lane mode is not paper runtime scope"
    elif not tradable:
        blocker = "candidate not tradable or not eligible"
    return _sanitize(
        {
            "signal_id": str(_first_present(raw, "signal_id", "candidate_id", "id") or _fallback_candidate_id(raw)),
            "candidate_id": str(_first_present(raw, "candidate_id", "signal_id", "id") or _fallback_candidate_id(raw)),
            "source": raw.get("source"),
            "symbol": str(raw.get("symbol") or "").strip().upper(),
            "timeframe": _normalize_timeframe(raw.get("timeframe")),
            "direction": str(raw.get("direction") or "").strip().lower(),
            "entry_mode": entry_mode,
            "lane_key": lane_key,
            "lane_mode": mode,
            "timestamp": str(timestamp or ""),
            "age_seconds": age,
            "freshness_seconds": freshness_seconds,
            "fresh": fresh,
            "stale": not fresh,
            "tradable": tradable,
            "capture_allowed": capture_allowed,
            "observed_only": bool(observed_only),
            "config_write_allowed": False,
            "live_authorized": False,
            "blocker": blocker,
            "no_live_permission_implied": True,
        }
    )


def _build_payload(
    *,
    status: str,
    generated_at: datetime,
    harvest_id: str | None,
    record_harvest_requested: bool,
    confirmation_valid: bool,
    harvest_recorded: bool,
    scope: Mapping[str, Any],
    coverage_gap_inputs: Mapping[str, Any],
    capture_summary: Mapping[str, Any],
    full_spectrum_harvest_summary: Mapping[str, Any],
    harvest_status: str,
    bounded: Mapping[str, int],
    iterations_completed: int,
    latest_heartbeat: Mapping[str, Any] | None = None,
    iteration_summaries: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return _sanitize(
        {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "harvest_recorded": bool(harvest_recorded),
            "harvest_id": harvest_id,
            "record_harvest_requested": bool(record_harvest_requested),
            "confirmation_valid": bool(confirmation_valid),
            "scope": dict(scope),
            "coverage_gap_inputs": dict(coverage_gap_inputs),
            "capture_summary": dict(capture_summary),
            "full_spectrum_harvest_summary": dict(full_spectrum_harvest_summary),
            "safe_run_commands": build_full_spectrum_harvester_commands(),
            "anchor_layer_future_note": _anchor_layer_future_note(),
            "harvest_status": harvest_status,
            "recommended_next_operator_move": _recommended_next_operator_move(harvest_status, full_spectrum_harvest_summary),
            "recommended_next_engineering_move": _recommended_next_engineering_move(harvest_status, full_spectrum_harvest_summary),
            "do_not_run_yet": _do_not_run_yet(),
            "bounded_scan_limits": {
                "latest_signals": int(bounded.get("latest_signals") or DEFAULT_LATEST_SIGNALS),
                "latest_scans": int(bounded.get("latest_scans") or DEFAULT_LATEST_SCANS),
            },
            "max_iterations": int(bounded.get("max_iterations") or DEFAULT_MAX_ITERATIONS),
            "sleep_seconds": int(bounded.get("sleep_seconds") or DEFAULT_SLEEP_SECONDS),
            "iteration_timeout_seconds": int(bounded.get("iteration_timeout_seconds") or DEFAULT_ITERATION_TIMEOUT_SECONDS),
            "heartbeat_every": int(bounded.get("heartbeat_every") or DEFAULT_HEARTBEAT_EVERY),
            "max_captures_per_iteration": int(bounded.get("max_captures_per_iteration") or DEFAULT_MAX_CAPTURES_PER_ITERATION),
            "iterations_completed": int(iterations_completed),
            "latest_heartbeat": dict(latest_heartbeat or {}),
            "iteration_summaries": [dict(row) for row in iteration_summaries or []],
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )


def _build_heartbeat_record(
    *,
    harvest_id: str,
    iteration: int,
    max_iterations: int,
    sleep_seconds: int,
    status: str,
    elapsed_seconds: float = 0.0,
    capture_summary: Mapping[str, Any] | None = None,
    captured_candidates: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    summary = dict(capture_summary or {})
    captured = [dict(row) for row in captured_candidates or []]
    return _sanitize(
        {
            "event_type": HEARTBEAT_EVENT_TYPE,
            "harvest_id": harvest_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "iteration": int(iteration),
            "max_iterations": int(max_iterations),
            "sleep_seconds": int(sleep_seconds),
            "status": status,
            "elapsed_seconds": round(float(elapsed_seconds), 6),
            "total_fresh_candidates": int(summary.get("total_fresh_candidates") or 0),
            "total_captured": len(captured),
            "captured_lanes": sorted({str(row.get("lane_key") or "") for row in captured if row.get("lane_key")}),
            "fresh_by_lane": dict(summary.get("fresh_by_lane") or {}),
            "safety": dict(SAFETY),
        }
    )


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


def _classify_harvest_status(*, capture_summary: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    if int(capture_summary.get("total_captured") or 0) > 0 or int(capture_summary.get("total_fresh_candidates") or 0) > 0:
        return CAPTURED_ONE_OR_MORE_LANES
    if summary.get("coverage_gaps_remaining"):
        return COVERAGE_GAPS_REMAIN
    if int(summary.get("lanes_in_scope") or 0) > 0:
        return FULL_SPECTRUM_SCOPE_READY
    return NO_FRESH_CANDIDATES


def _recommended_next_operator_move(harvest_status: str, summary: Mapping[str, Any]) -> str:
    if harvest_status == COVERAGE_GAPS_REMAIN or summary.get("coverage_gaps_remaining"):
        return "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"
    if harvest_status == CAPTURED_ONE_OR_MORE_LANES:
        return "RUN_R197_PATTERN_DETECTOR_FAMILY_EXPANSION"
    return "RUN_R199_WMA_MA_ANCHOR_LAYER_PREVIEW"


def _recommended_next_engineering_move(harvest_status: str, summary: Mapping[str, Any]) -> str:
    if harvest_status == COVERAGE_GAPS_REMAIN or summary.get("coverage_gaps_remaining"):
        return "Keep R198 bounded harvester loops running and compare fresh/stale lane flow before any ranking or promotion work."
    if harvest_status == CAPTURED_ONE_OR_MORE_LANES:
        return "Feed R198 paper-only evidence into later ranking/review surfaces; do not mutate lane config or live flags."
    return "Prepare R199 WMA/MA anchor-layer preview as paper-only context with no live authorization."


def _anchor_layer_future_note() -> dict[str, Any]:
    return {
        "wma_ma_anchor_layer_not_implemented": True,
        "future_phase": "R199_OR_LATER_WMA_MA_ANCHOR_LAYER_PREVIEW",
        "candidate_timeframes": ["13D", "4H", "666m", "13H", "888m"],
        "safety_note": "anchor layer must start paper-only and cannot authorize live",
    }


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


def _compact_config_lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_key": str(lane.get("lane_key") or normalize_lane_key(lane.get("symbol"), lane.get("timeframe"), lane.get("direction"), lane.get("entry_mode"))),
        "symbol": str(lane.get("symbol") or "").strip().upper(),
        "timeframe": _normalize_timeframe(lane.get("timeframe")),
        "direction": str(lane.get("direction") or "").strip().lower(),
        "entry_mode": str(lane.get("entry_mode") or DEFAULT_ENTRY_MODE).strip().lower(),
        "mode": str(lane.get("mode") or "disabled").strip().lower(),
        "freshness_seconds": int(lane.get("freshness_seconds") or DISCOVERED_UNCONFIGURED_FRESHNESS_SECONDS),
    }


def _is_default_btc_ladder_lane(lane_key: str) -> bool:
    lane = _lane_from_key(lane_key)
    return lane["symbol"] == TARGET_SYMBOL and lane["entry_mode"] == DEFAULT_ENTRY_MODE and lane["direction"] in DEFAULT_DIRECTIONS


def _lane_from_key(lane_key: str) -> dict[str, Any]:
    parts = str(lane_key or "").split("|")
    return {
        "lane_key": normalize_lane_key(parts[0] if len(parts) > 0 else TARGET_SYMBOL, parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else "", parts[3] if len(parts) > 3 else DEFAULT_ENTRY_MODE),
        "symbol": parts[0].upper() if len(parts) > 0 else TARGET_SYMBOL,
        "timeframe": _normalize_timeframe(parts[1] if len(parts) > 1 else ""),
        "direction": parts[2].lower() if len(parts) > 2 else "",
        "entry_mode": parts[3].lower() if len(parts) > 3 else DEFAULT_ENTRY_MODE,
    }


def _normalize_timeframe(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lower = text.lower()
    if lower.endswith("h"):
        return f"{lower[:-1]}H"
    if lower.endswith("d"):
        return f"{lower[:-1]}D"
    return lower


def _ordered_timeframes(values: list[str] | tuple[str, ...]) -> list[str]:
    return sorted({_normalize_timeframe(value) for value in values if _normalize_timeframe(value)}, key=_timeframe_sort_key)


def _timeframe_sort_key(value: str) -> tuple[int, int, str]:
    text = _normalize_timeframe(value)
    if text.endswith("m"):
        return (0, int(text[:-1]) if text[:-1].isdigit() else 999999, text)
    if text.endswith("H"):
        return (1, int(text[:-1]) if text[:-1].isdigit() else 999999, text)
    if text.endswith("D"):
        return (2, int(text[:-1]) if text[:-1].isdigit() else 999999, text)
    return (3, 999999, text)


def _lane_sort_key(lane_key: str) -> tuple[str, tuple[int, int, str], str, str]:
    lane = _lane_from_key(lane_key)
    return (lane["symbol"], _timeframe_sort_key(lane["timeframe"]), lane["direction"], lane["entry_mode"])


def _timeframe_has_fresh_flow(timeframe: str, lane_keys: set[str]) -> bool:
    normalized = _normalize_timeframe(timeframe)
    return any(_lane_from_key(lane_key)["timeframe"] == normalized for lane_key in lane_keys)


def _error_payload(*, generated_at: datetime, record_harvest: bool, confirmation_valid: bool, error: Exception) -> dict[str, Any]:
    return _sanitize(
        {
            "status": FULL_SPECTRUM_HARVESTER_EXPANSION_ERROR,
            "generated_at": generated_at.isoformat(),
            "harvest_recorded": False,
            "harvest_id": None,
            "record_harvest_requested": bool(record_harvest),
            "confirmation_valid": bool(confirmation_valid),
            "scope": {"configured_paper_lanes": [], "discovered_unconfigured_paper_lanes": [], "tiny_live_reference_lanes": [], "timeframes": [], "directions": list(DEFAULT_DIRECTIONS), "entry_modes": [DEFAULT_ENTRY_MODE]},
            "coverage_gap_inputs": {"signals_present_not_configured": [], "timeframes_seen_but_not_currently_harvested": [], "paper_outcomes_without_current_watcher_count": 0},
            "capture_summary": {"total_fresh_candidates": 0, "total_captured": 0, "captured_lanes": [], "fresh_by_lane": {}, "stale_by_lane": {}, "blocked_by_lane": {}},
            "full_spectrum_harvest_summary": {"lanes_in_scope": 0, "configured_lanes": 0, "discovered_unconfigured_lanes": 0, "lanes_with_fresh_flow": [], "lanes_with_stale_only": [], "coverage_gaps_remaining": []},
            "safe_run_commands": build_full_spectrum_harvester_commands(),
            "anchor_layer_future_note": _anchor_layer_future_note(),
            "harvest_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
            "recommended_next_operator_move": "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING",
            "recommended_next_engineering_move": "Fix R198 harvester expansion build error and rerun preview only.",
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
