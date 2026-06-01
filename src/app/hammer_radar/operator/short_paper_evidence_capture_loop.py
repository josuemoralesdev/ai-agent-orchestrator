"""R157 short paper evidence capture loop for BTCUSDT 8m short.

This module is paper evidence collection only. It reads bounded local ledgers,
can append local heartbeat/capture records after exact confirmation, and never
creates executable payloads, signs requests, calls Binance, mutates env/config,
changes lane modes, promotes shorts, or authorizes live execution.
"""

from __future__ import annotations

import json
import signal
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir, get_signals_path
from src.app.hammer_radar.operator.entry_mode_derivation_bridge import normalize_candidates_for_lane_key
from src.app.hammer_radar.operator.expanded_paper_watch import build_expanded_paper_distribution
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE, load_lane_controls, normalize_lane_key
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY

SHORT_PAPER_EVIDENCE_CAPTURE_PREVIEW = "SHORT_PAPER_EVIDENCE_CAPTURE_PREVIEW"
SHORT_PAPER_EVIDENCE_CAPTURE_READY = "SHORT_PAPER_EVIDENCE_CAPTURE_READY"
SHORT_PAPER_EVIDENCE_CAPTURE_REJECTED = "SHORT_PAPER_EVIDENCE_CAPTURE_REJECTED"
SHORT_PAPER_EVIDENCE_CAPTURE_STARTED = "SHORT_PAPER_EVIDENCE_CAPTURE_STARTED"
SHORT_PAPER_EVIDENCE_CAPTURE_ITERATION_COMPLETED = "SHORT_PAPER_EVIDENCE_CAPTURE_ITERATION_COMPLETED"
SHORT_PAPER_EVIDENCE_CAPTURE_TIMEOUT = "SHORT_PAPER_EVIDENCE_CAPTURE_TIMEOUT"
SHORT_PAPER_EVIDENCE_CAPTURED = "SHORT_PAPER_EVIDENCE_CAPTURED"
SHORT_PAPER_EVIDENCE_BLOCKED = "SHORT_PAPER_EVIDENCE_BLOCKED"
SHORT_PAPER_EVIDENCE_ERROR = "SHORT_PAPER_EVIDENCE_ERROR"

SHORT_PAPER_CAPTURE_ITERATION_STARTED = "SHORT_PAPER_CAPTURE_ITERATION_STARTED"
SHORT_PAPER_CAPTURE_ITERATION_COMPLETED = "SHORT_PAPER_CAPTURE_ITERATION_COMPLETED"
SHORT_PAPER_CAPTURE_CANDIDATE_CAPTURED = "SHORT_PAPER_CAPTURE_CANDIDATE_CAPTURED"
SHORT_PAPER_CAPTURE_TIMEOUT = "SHORT_PAPER_CAPTURE_TIMEOUT"
SHORT_PAPER_CAPTURE_EXITED = "SHORT_PAPER_CAPTURE_EXITED"
SHORT_PAPER_CAPTURE_PERFORMANCE_GUARD = "SHORT_PAPER_CAPTURE_PERFORMANCE_GUARD"

EVENT_TYPE = "SHORT_PAPER_EVIDENCE_CAPTURE"
HEARTBEAT_EVENT_TYPE = "SHORT_PAPER_EVIDENCE_CAPTURE_HEARTBEAT"
LEDGER_FILENAME = "short_paper_evidence_capture.ndjson"
HEARTBEAT_LEDGER_FILENAME = "short_paper_evidence_capture_heartbeats.ndjson"
CONFIRM_SHORT_PAPER_CAPTURE_PHRASE = (
    "I CONFIRM SHORT PAPER EVIDENCE CAPTURE ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LANE_KEY = DEFAULT_TARGET_LANE_KEY
DEFAULT_LATEST_SIGNALS = 500
DEFAULT_LATEST_SCANS = 1000
DEFAULT_MAX_ITERATIONS = 60
DEFAULT_SLEEP_SECONDS = 60
DEFAULT_ITERATION_TIMEOUT_SECONDS = 30
DEFAULT_HEARTBEAT_EVERY = 1

MAX_LATEST_SIGNALS = 20000
MAX_LATEST_SCANS = 50000
MAX_MAX_ITERATIONS = 1440
MAX_SLEEP_SECONDS = 300
MAX_ITERATION_TIMEOUT_SECONDS = 300
MAX_HEARTBEAT_EVERY = 1000

TARGET_SYMBOL = "BTCUSDT"
TARGET_TIMEFRAME = "8m"
TARGET_DIRECTION = "short"
TARGET_ENTRY_MODE = "ladder_close_50_618"

WAIT_FOR_SHORT_FRESH_CANDIDATE = "WAIT_FOR_SHORT_FRESH_CANDIDATE"
RUN_R158_SHORT_EVIDENCE_RECHECK = "RUN_R158_SHORT_EVIDENCE_RECHECK"
KEEP_COLLECTING_SHORT_PAPER = "KEEP_COLLECTING_SHORT_PAPER"
STOP_SAFETY_BLOCK = "STOP_SAFETY_BLOCK"

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "network_allowed": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "logs/hammer_radar_forward/short_paper_evidence_capture.ndjson",
    "logs/hammer_radar_forward/short_paper_evidence_capture_heartbeats.ndjson",
    "operator.lane_control.load_lane_controls",
    "operator.lane_control.normalize_lane_key",
    "operator.entry_mode_derivation_bridge.normalize_candidates_for_lane_key",
    "operator.expanded_paper_watch.build_expanded_paper_distribution",
    "operator.short_strategy_packet",
    "operator.full_spectrum_betrayal_short_review",
]


def build_short_paper_target_lane(
    *,
    lane_key: str = DEFAULT_LANE_KEY,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    normalized_key = _normalize_lane_key_text(lane_key)
    controls = load_lane_controls(Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH)
    lane = (controls.get("lane_map") or {}).get(normalized_key)
    if lane:
        return _compact_lane(lane)
    return _target_from_key(normalized_key, mode="disabled")


def build_short_paper_evidence_capture_preview(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    iteration_timeout_seconds: int = DEFAULT_ITERATION_TIMEOUT_SECONDS,
    heartbeat_every: int = DEFAULT_HEARTBEAT_EVERY,
    record_capture: bool = False,
    confirm_short_paper_capture: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_short_paper_capture == CONFIRM_SHORT_PAPER_CAPTURE_PHRASE
    target_lane = build_short_paper_target_lane(lane_key=lane_key, config_path=config_path)
    bounded = _bounded_settings(
        latest_signals=latest_signals,
        latest_scans=latest_scans,
        max_iterations=max_iterations,
        sleep_seconds=sleep_seconds,
        iteration_timeout_seconds=iteration_timeout_seconds,
        heartbeat_every=heartbeat_every,
    )
    candidate_window = evaluate_short_paper_candidate_window(
        log_dir=resolved_log_dir,
        lane_key=target_lane["lane_key"],
        latest_signals=bounded["latest_signals"],
        latest_scans=bounded["latest_scans"],
        config_path=config_path,
        now=generated_at,
    )
    status = SHORT_PAPER_EVIDENCE_CAPTURE_READY if _target_lane_is_eligible(target_lane) else SHORT_PAPER_EVIDENCE_BLOCKED
    if record_capture and not confirmation_valid:
        status = SHORT_PAPER_EVIDENCE_CAPTURE_REJECTED
    return _build_payload(
        status=status,
        generated_at=generated_at,
        capture_id=None,
        target_lane=target_lane,
        watch_started=False,
        watch_completed=False,
        record_capture_requested=record_capture,
        confirmation_valid=confirmation_valid,
        paper_evidence_captured=False,
        captured_signal_id=None,
        captured_lane_key=None,
        iterations_completed=0,
        max_iterations=bounded["max_iterations"],
        sleep_seconds=bounded["sleep_seconds"],
        iteration_timeout_seconds=bounded["iteration_timeout_seconds"],
        heartbeat_every=bounded["heartbeat_every"],
        latest_signals=bounded["latest_signals"],
        latest_scans=bounded["latest_scans"],
        latest_heartbeat=None,
        candidate_window=candidate_window,
        capture_records_summary=summarize_short_paper_evidence_capture_records(
            load_short_paper_evidence_capture_records(log_dir=resolved_log_dir, limit=200)
        ),
    )


def run_short_paper_evidence_capture_once(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    record_capture: bool = False,
    confirm_short_paper_capture: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    return run_short_paper_evidence_capture_loop(
        log_dir=log_dir,
        lane_key=lane_key,
        latest_signals=latest_signals,
        latest_scans=latest_scans,
        max_iterations=1,
        sleep_seconds=1,
        iteration_timeout_seconds=DEFAULT_ITERATION_TIMEOUT_SECONDS,
        heartbeat_every=1,
        run_capture_loop=True,
        record_capture=record_capture,
        confirm_short_paper_capture=confirm_short_paper_capture,
        config_path=config_path,
        now=now,
        sleep_fn=lambda _seconds: None,
    )


def run_short_paper_evidence_capture_loop(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    iteration_timeout_seconds: int = DEFAULT_ITERATION_TIMEOUT_SECONDS,
    heartbeat_every: int = DEFAULT_HEARTBEAT_EVERY,
    run_capture_loop: bool = False,
    record_capture: bool = False,
    confirm_short_paper_capture: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    progress_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_short_paper_capture == CONFIRM_SHORT_PAPER_CAPTURE_PHRASE
    bounded = _bounded_settings(
        latest_signals=latest_signals,
        latest_scans=latest_scans,
        max_iterations=max_iterations,
        sleep_seconds=sleep_seconds,
        iteration_timeout_seconds=iteration_timeout_seconds,
        heartbeat_every=heartbeat_every,
    )
    if not run_capture_loop:
        return build_short_paper_evidence_capture_preview(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            latest_signals=bounded["latest_signals"],
            latest_scans=bounded["latest_scans"],
            max_iterations=bounded["max_iterations"],
            sleep_seconds=bounded["sleep_seconds"],
            iteration_timeout_seconds=bounded["iteration_timeout_seconds"],
            heartbeat_every=bounded["heartbeat_every"],
            record_capture=record_capture,
            confirm_short_paper_capture=confirm_short_paper_capture,
            config_path=config_path,
            now=generated_at,
        )

    target_lane = build_short_paper_target_lane(lane_key=lane_key, config_path=config_path)
    first_window = evaluate_short_paper_candidate_window(
        log_dir=resolved_log_dir,
        lane_key=target_lane["lane_key"],
        latest_signals=bounded["latest_signals"],
        latest_scans=bounded["latest_scans"],
        config_path=config_path,
        now=generated_at,
    )
    if not confirmation_valid:
        return _build_payload(
            status=SHORT_PAPER_EVIDENCE_CAPTURE_REJECTED,
            generated_at=generated_at,
            capture_id=None,
            target_lane=target_lane,
            watch_started=False,
            watch_completed=False,
            record_capture_requested=record_capture,
            confirmation_valid=False,
            paper_evidence_captured=False,
            captured_signal_id=None,
            captured_lane_key=None,
            iterations_completed=0,
            max_iterations=bounded["max_iterations"],
            sleep_seconds=bounded["sleep_seconds"],
            iteration_timeout_seconds=bounded["iteration_timeout_seconds"],
            heartbeat_every=bounded["heartbeat_every"],
            latest_signals=bounded["latest_signals"],
            latest_scans=bounded["latest_scans"],
            latest_heartbeat=None,
            candidate_window=first_window,
            capture_records_summary=summarize_short_paper_evidence_capture_records(
                load_short_paper_evidence_capture_records(log_dir=resolved_log_dir, limit=200)
            ),
        )
    if not _target_lane_is_eligible(target_lane):
        payload = _build_payload(
            status=SHORT_PAPER_EVIDENCE_BLOCKED,
            generated_at=generated_at,
            capture_id=f"r157_short_paper_capture_{uuid4().hex}",
            target_lane=target_lane,
            watch_started=False,
            watch_completed=False,
            record_capture_requested=record_capture,
            confirmation_valid=True,
            paper_evidence_captured=False,
            captured_signal_id=None,
            captured_lane_key=None,
            iterations_completed=0,
            max_iterations=bounded["max_iterations"],
            sleep_seconds=bounded["sleep_seconds"],
            iteration_timeout_seconds=bounded["iteration_timeout_seconds"],
            heartbeat_every=bounded["heartbeat_every"],
            latest_signals=bounded["latest_signals"],
            latest_scans=bounded["latest_scans"],
            latest_heartbeat=None,
            candidate_window=first_window,
            capture_records_summary=summarize_short_paper_evidence_capture_records(
                load_short_paper_evidence_capture_records(log_dir=resolved_log_dir, limit=200)
            ),
        )
        if record_capture:
            record = append_short_paper_evidence_capture_record(payload, log_dir=resolved_log_dir)
            payload["capture_id"] = record["capture_id"]
            payload["ledger_path"] = str(short_paper_evidence_capture_records_path(resolved_log_dir))
        return _sanitize(payload)

    capture_id = f"r157_short_paper_capture_{uuid4().hex}"
    iterations: list[dict[str, Any]] = []
    latest_heartbeat: dict[str, Any] | None = None
    final_window = first_window
    captured_signal_id: str | None = None
    final_status = SHORT_PAPER_EVIDENCE_CAPTURE_TIMEOUT
    sleeper = sleep_fn or time.sleep

    try:
        for iteration in range(1, bounded["max_iterations"] + 1):
            started_at = datetime.now(UTC)
            if _should_heartbeat(iteration, bounded["heartbeat_every"]):
                latest_heartbeat = append_short_paper_capture_heartbeat(
                    build_short_paper_capture_heartbeat_record(
                        capture_id=capture_id,
                        iteration=iteration,
                        max_iterations=bounded["max_iterations"],
                        sleep_seconds=bounded["sleep_seconds"],
                        status=SHORT_PAPER_CAPTURE_ITERATION_STARTED,
                        target_lane=target_lane,
                    ),
                    log_dir=resolved_log_dir,
                )
            try:
                with _iteration_timeout_guard(float(bounded["iteration_timeout_seconds"])):
                    window = evaluate_short_paper_candidate_window(
                        log_dir=resolved_log_dir,
                        lane_key=target_lane["lane_key"],
                        latest_signals=bounded["latest_signals"],
                        latest_scans=bounded["latest_scans"],
                        config_path=config_path,
                        now=generated_at if now is not None else datetime.now(UTC),
                    )
                final_window = window
                completed_at = datetime.now(UTC)
                elapsed = (completed_at - started_at).total_seconds()
                captured = _first_capture_candidate(window)
                if captured:
                    captured_signal_id = str(captured.get("signal_id") or captured.get("candidate_id") or "")
                    final_status = SHORT_PAPER_EVIDENCE_CAPTURED
                    hb_status = SHORT_PAPER_CAPTURE_CANDIDATE_CAPTURED
                else:
                    hb_status = SHORT_PAPER_CAPTURE_ITERATION_COMPLETED
                iteration_summary = {
                    "iteration": iteration,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "elapsed_seconds": round(elapsed, 6),
                    "candidate_window": window,
                    "paper_evidence_captured": bool(captured),
                    "captured_signal_id": captured_signal_id or None,
                    "safety": dict(SAFETY),
                }
                iterations.append(_sanitize(iteration_summary))
                if _should_heartbeat(iteration, bounded["heartbeat_every"]) or captured:
                    latest_heartbeat = append_short_paper_capture_heartbeat(
                        build_short_paper_capture_heartbeat_record(
                            capture_id=capture_id,
                            iteration=iteration,
                            max_iterations=bounded["max_iterations"],
                            sleep_seconds=bounded["sleep_seconds"],
                            status=hb_status,
                            elapsed_seconds=elapsed,
                            target_lane=target_lane,
                            candidate_window=window,
                            paper_evidence_captured=bool(captured),
                            captured_signal_id=captured_signal_id or None,
                        ),
                        log_dir=resolved_log_dir,
                    )
                    _emit_progress(progress_fn, latest_heartbeat)
                if captured:
                    break
            except IterationTimeoutError:
                completed_at = datetime.now(UTC)
                elapsed = (completed_at - started_at).total_seconds()
                final_status = SHORT_PAPER_EVIDENCE_CAPTURE_TIMEOUT
                timeout_summary = {
                    "iteration": iteration,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "elapsed_seconds": round(elapsed, 6),
                    "timeout_seconds": bounded["iteration_timeout_seconds"],
                    "candidate_window": final_window,
                    "paper_evidence_captured": False,
                    "safety": dict(SAFETY),
                }
                iterations.append(_sanitize(timeout_summary))
                latest_heartbeat = append_short_paper_capture_heartbeat(
                    build_short_paper_capture_heartbeat_record(
                        capture_id=capture_id,
                        iteration=iteration,
                        max_iterations=bounded["max_iterations"],
                        sleep_seconds=bounded["sleep_seconds"],
                        status=SHORT_PAPER_CAPTURE_PERFORMANCE_GUARD,
                        elapsed_seconds=elapsed,
                        target_lane=target_lane,
                        candidate_window=final_window,
                    ),
                    log_dir=resolved_log_dir,
                )
                _emit_progress(progress_fn, latest_heartbeat)
                break
            if iteration < bounded["max_iterations"] and final_status != SHORT_PAPER_EVIDENCE_CAPTURED:
                sleeper(float(bounded["sleep_seconds"]))
    except Exception:
        final_status = SHORT_PAPER_EVIDENCE_ERROR

    latest_heartbeat = append_short_paper_capture_heartbeat(
        build_short_paper_capture_heartbeat_record(
            capture_id=capture_id,
            iteration=len(iterations),
            max_iterations=bounded["max_iterations"],
            sleep_seconds=bounded["sleep_seconds"],
            status=SHORT_PAPER_CAPTURE_EXITED,
            target_lane=target_lane,
            candidate_window=final_window,
            paper_evidence_captured=bool(captured_signal_id),
            captured_signal_id=captured_signal_id,
        ),
        log_dir=resolved_log_dir,
    )
    if final_status == SHORT_PAPER_EVIDENCE_CAPTURE_TIMEOUT and iterations and captured_signal_id is None:
        final_status = SHORT_PAPER_EVIDENCE_CAPTURE_TIMEOUT

    payload = _build_payload(
        status=final_status,
        generated_at=generated_at,
        capture_id=capture_id,
        target_lane=target_lane,
        watch_started=True,
        watch_completed=True,
        record_capture_requested=record_capture,
        confirmation_valid=True,
        paper_evidence_captured=bool(captured_signal_id),
        captured_signal_id=captured_signal_id,
        captured_lane_key=target_lane["lane_key"] if captured_signal_id else None,
        iterations_completed=len(iterations),
        max_iterations=bounded["max_iterations"],
        sleep_seconds=bounded["sleep_seconds"],
        iteration_timeout_seconds=bounded["iteration_timeout_seconds"],
        heartbeat_every=bounded["heartbeat_every"],
        latest_signals=bounded["latest_signals"],
        latest_scans=bounded["latest_scans"],
        latest_heartbeat=latest_heartbeat,
        candidate_window=final_window,
        iteration_summaries=iterations,
        capture_records_summary=summarize_short_paper_evidence_capture_records(
            load_short_paper_evidence_capture_records(log_dir=resolved_log_dir, limit=200)
        ),
    )
    if record_capture:
        record = append_short_paper_evidence_capture_record(payload, log_dir=resolved_log_dir)
        payload["capture_id"] = record["capture_id"]
        payload["ledger_path"] = str(short_paper_evidence_capture_records_path(resolved_log_dir))
        payload["evidence_summary"] = _evidence_summary(
            candidate_window=final_window,
            records_summary=summarize_short_paper_evidence_capture_records(
                load_short_paper_evidence_capture_records(log_dir=resolved_log_dir, limit=200)
            ),
            target_lane=target_lane,
            captured=bool(captured_signal_id),
        )
    return _sanitize(payload)


def evaluate_short_paper_candidate_window(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    target_lane = build_short_paper_target_lane(lane_key=lane_key, config_path=config_path)
    bounded_signals = _bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS)
    bounded_scans = _bounded_int(latest_scans, 1, MAX_LATEST_SCANS, DEFAULT_LATEST_SCANS)
    signals = _candidate_rows(
        read_recent_ndjson_records(get_signals_path(resolved_log_dir), limit=bounded_signals, max_bytes=16_777_216),
        source="signals.ndjson",
    )
    scans = _candidate_rows(
        read_recent_ndjson_records(resolved_log_dir / "multi_symbol_paper_scans.ndjson", limit=bounded_scans, max_bytes=32_000_000),
        source="multi_symbol_paper_scans.ndjson",
    )
    candidates = [*signals, *scans]
    normalized = normalize_candidates_for_lane_key(candidates, lane_key=target_lane["lane_key"], now=generated_at)
    rows: list[dict[str, Any]] = []
    blockers: Counter[str] = Counter()
    matching_lane_count = 0
    fresh_matching_count = 0
    stale_matching_count = 0
    tradable_matching_count = 0
    capture_candidates: list[dict[str, Any]] = []
    for raw, candidate in zip(candidates, normalized, strict=False):
        row = _candidate_window_row(raw, candidate, target_lane, generated_at)
        rows.append(row)
        if not row["matches_target_lane"]:
            blockers[row["blocker"]] += 1
            continue
        matching_lane_count += 1
        if row["fresh"]:
            fresh_matching_count += 1
        else:
            stale_matching_count += 1
        if row["tradable"]:
            tradable_matching_count += 1
        if row["capture_allowed"]:
            capture_candidates.append(row)
        else:
            blockers[row["blocker"]] += 1

    # R153 distribution is included as a reused bounded summary surface, not as
    # an authority for capture.
    distribution = build_expanded_paper_distribution(
        log_dir=resolved_log_dir,
        paper_lanes=[target_lane] if target_lane.get("mode") == "paper" else [],
        latest_signals=bounded_signals,
        latest_scans=bounded_scans,
        now=generated_at,
    )
    return _sanitize(
        {
            "generated_at": generated_at.isoformat(),
            "signals_checked": len(signals),
            "scans_checked": len(scans),
            "matching_lane_count": matching_lane_count,
            "fresh_matching_count": fresh_matching_count,
            "stale_matching_count": stale_matching_count,
            "tradable_matching_count": tradable_matching_count,
            "capture_allowed_count": len(capture_candidates),
            "capturable_candidates": capture_candidates[:5],
            "recent_matching_candidates": [row for row in rows if row["matches_target_lane"]][:10],
            "top_blockers": _top_blockers(blockers),
            "expanded_paper_distribution_reused": {
                "fresh_by_lane": dict(distribution.get("fresh_by_lane") or {}),
                "stale_by_lane": dict(distribution.get("stale_by_lane") or {}),
                "latest_signals_checked": distribution.get("latest_signals_checked"),
                "latest_scans_checked": distribution.get("latest_scans_checked"),
            },
            "safety": dict(SAFETY),
        }
    )


def build_short_paper_capture_heartbeat_record(
    *,
    capture_id: str,
    iteration: int,
    max_iterations: int,
    sleep_seconds: int,
    status: str,
    elapsed_seconds: float = 0.0,
    target_lane: Mapping[str, Any] | None = None,
    candidate_window: Mapping[str, Any] | None = None,
    paper_evidence_captured: bool = False,
    captured_signal_id: str | None = None,
    safety: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    window = dict(candidate_window or {})
    generated = generated_at or datetime.now(UTC)
    return _sanitize(
        {
            "event_type": HEARTBEAT_EVENT_TYPE,
            "capture_id": capture_id,
            "generated_at": generated.isoformat(),
            "iteration": int(iteration),
            "max_iterations": int(max_iterations),
            "sleep_seconds": int(sleep_seconds),
            "status": status,
            "elapsed_seconds": round(float(elapsed_seconds), 6),
            "target_lane": dict(target_lane or {}),
            "signals_checked": int(window.get("signals_checked") or 0),
            "matching_lane_count": int(window.get("matching_lane_count") or 0),
            "fresh_matching_count": int(window.get("fresh_matching_count") or 0),
            "stale_matching_count": int(window.get("stale_matching_count") or 0),
            "tradable_matching_count": int(window.get("tradable_matching_count") or 0),
            "paper_evidence_captured": bool(paper_evidence_captured),
            "captured_signal_id": captured_signal_id,
            "captured_lane_key": (target_lane or {}).get("lane_key") if captured_signal_id else None,
            "safety": _safety(safety),
        }
    )


def append_short_paper_capture_heartbeat(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    heartbeat_ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(heartbeat_ledger_path) if heartbeat_ledger_path else short_paper_capture_heartbeats_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(dict(record))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def append_short_paper_evidence_capture_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = short_paper_evidence_capture_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "capture_id": str(record.get("capture_id") or f"r157_short_paper_capture_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "target_lane": dict(record.get("target_lane") or {}),
            "watch_started": bool(record.get("watch_started")),
            "watch_completed": bool(record.get("watch_completed")),
            "record_capture_requested": bool(record.get("record_capture_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "paper_evidence_captured": bool(record.get("paper_evidence_captured")),
            "captured_signal_id": record.get("captured_signal_id"),
            "captured_lane_key": record.get("captured_lane_key"),
            "iterations_completed": int(record.get("iterations_completed") or 0),
            "max_iterations": int(record.get("max_iterations") or 0),
            "bounded_scan_limits": dict(record.get("bounded_scan_limits") or {}),
            "candidate_window": dict(record.get("candidate_window") or {}),
            "evidence_summary": dict(record.get("evidence_summary") or {}),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safety": _safety(record.get("safety") if isinstance(record.get("safety"), Mapping) else None),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_short_paper_evidence_capture_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = short_paper_evidence_capture_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_short_paper_evidence_capture_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    captured = [record for record in records if record.get("paper_evidence_captured")]
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "fresh_candidate_count_added": len(captured),
        "last_capture_id": records[0].get("capture_id") if records else None,
        "last_captured_signal_id": captured[0].get("captured_signal_id") if captured else None,
        "short_lane_remains_paper": True,
        "tiny_live_not_authorized": True,
        "safety": dict(SAFETY),
    }


def short_paper_evidence_capture_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def short_paper_capture_heartbeats_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / HEARTBEAT_LEDGER_FILENAME


def format_short_paper_evidence_capture_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_payload(
    *,
    status: str,
    generated_at: datetime,
    capture_id: str | None,
    target_lane: Mapping[str, Any],
    watch_started: bool,
    watch_completed: bool,
    record_capture_requested: bool,
    confirmation_valid: bool,
    paper_evidence_captured: bool,
    captured_signal_id: str | None,
    captured_lane_key: str | None,
    iterations_completed: int,
    max_iterations: int,
    sleep_seconds: int,
    iteration_timeout_seconds: int,
    heartbeat_every: int,
    latest_signals: int,
    latest_scans: int,
    latest_heartbeat: Mapping[str, Any] | None,
    candidate_window: Mapping[str, Any],
    capture_records_summary: Mapping[str, Any],
    iteration_summaries: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence_summary = _evidence_summary(
        candidate_window=candidate_window,
        records_summary=capture_records_summary,
        target_lane=target_lane,
        captured=paper_evidence_captured,
    )
    return _sanitize(
        {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "capture_id": capture_id,
            "target_lane": dict(target_lane),
            "watch_started": bool(watch_started),
            "watch_completed": bool(watch_completed),
            "record_capture_requested": bool(record_capture_requested),
            "confirmation_valid": bool(confirmation_valid),
            "paper_evidence_captured": bool(paper_evidence_captured),
            "captured_signal_id": captured_signal_id,
            "captured_lane_key": captured_lane_key,
            "iterations_completed": int(iterations_completed),
            "max_iterations": int(max_iterations),
            "sleep_seconds": int(sleep_seconds),
            "iteration_timeout_seconds": int(iteration_timeout_seconds),
            "heartbeat_every": int(heartbeat_every),
            "bounded_scan_limits": {
                "latest_signals": int(latest_signals),
                "latest_scans": int(latest_scans),
            },
            "performance_guard_enabled": True,
            "latest_heartbeat": dict(latest_heartbeat or {}),
            "candidate_window": dict(candidate_window),
            "iteration_summaries": [dict(item) for item in iteration_summaries or []],
            "evidence_summary": evidence_summary,
            "safe_commands": _safe_commands(),
            "recommended_next_operator_move": _recommended_next_operator_move(status, candidate_window, paper_evidence_captured),
            "recommended_next_engineering_move": _recommended_next_engineering_move(status, candidate_window),
            "do_not_run_yet": [
                "live-connector-submit",
                "any order endpoint",
                "global live flag arming",
                "kill switch disable",
                "set short lane tiny_live",
                "set new lane tiny_live",
            ],
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )


def _candidate_window_row(
    raw: Mapping[str, Any],
    candidate: Mapping[str, Any],
    target_lane: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    entry_mode = str(candidate.get("entry_mode") or raw.get("entry_mode") or TARGET_ENTRY_MODE).strip().lower()
    lane_key = normalize_lane_key(candidate.get("symbol"), candidate.get("timeframe"), candidate.get("direction"), entry_mode)
    timestamp = _first_present(candidate, "timestamp", "generated_at", "closed_at", "detected_at") or raw.get("timestamp")
    age = _age_seconds(timestamp, now)
    freshness_seconds = int(target_lane.get("freshness_seconds") or 0)
    fresh = age is not None and freshness_seconds > 0 and age <= freshness_seconds
    tradable = _tradable(raw) and _tradable(candidate)
    matches = lane_key == target_lane.get("lane_key")
    blocker = "capture allowed"
    if not matches:
        blocker = _mismatch_blocker(candidate, entry_mode, target_lane)
    elif target_lane.get("mode") != "paper":
        blocker = "target lane mode is not paper"
    elif not fresh:
        blocker = "candidate stale or missing timestamp"
    elif not tradable:
        blocker = "candidate not tradable or not eligible"
    capture_allowed = matches and target_lane.get("mode") == "paper" and fresh and tradable
    return _sanitize(
        {
            "signal_id": str(_first_present(candidate, "signal_id", "candidate_id", "id") or _first_present(raw, "signal_id", "candidate_id", "id") or ""),
            "candidate_id": str(_first_present(candidate, "candidate_id", "signal_id", "id") or _first_present(raw, "candidate_id", "signal_id", "id") or ""),
            "source": raw.get("source"),
            "symbol": str(candidate.get("symbol") or "").strip().upper(),
            "timeframe": str(candidate.get("timeframe") or "").strip().lower(),
            "direction": str(candidate.get("direction") or "").strip().lower(),
            "entry_mode": entry_mode,
            "lane_key": lane_key,
            "timestamp": str(timestamp or ""),
            "age_seconds": age,
            "freshness_seconds": freshness_seconds,
            "matches_target_lane": matches,
            "fresh": fresh,
            "stale": not fresh,
            "tradable": tradable,
            "capture_allowed": capture_allowed,
            "blocker": blocker,
            "no_live_permission_implied": True,
        }
    )


def _candidate_rows(records: list[Mapping[str, Any]], *, source: str) -> list[dict[str, Any]]:
    return [_candidate_row(record, source=source) for record in reversed(records)]


def _candidate_row(record: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    raw = dict(record)
    direction = str(_first_present(raw, "direction", "bias_direction", "side") or "").strip().lower()
    if direction in {"buy", "bull", "bullish"}:
        direction = "long"
    if direction in {"sell", "bear", "bearish"}:
        direction = "short"
    timestamp = _first_present(raw, "generated_at", "timestamp", "closed_at", "detected_at")
    entry_mode = str(_first_present(raw, "entry_mode", "mode") or TARGET_ENTRY_MODE).strip().lower()
    return {
        **raw,
        "source": source,
        "signal_id": str(_first_present(raw, "signal_id", "candidate_id", "id") or ""),
        "candidate_id": str(_first_present(raw, "candidate_id", "signal_id", "id") or ""),
        "symbol": str(_first_present(raw, "symbol", "base_symbol") or "").strip().upper(),
        "timeframe": str(_first_present(raw, "timeframe", "tf", "interval") or "").strip().lower(),
        "direction": direction,
        "entry_mode": entry_mode,
        "timestamp": str(timestamp or ""),
    }


def _target_lane_is_eligible(target_lane: Mapping[str, Any]) -> bool:
    return (
        target_lane.get("lane_key") == DEFAULT_LANE_KEY
        and target_lane.get("symbol") == TARGET_SYMBOL
        and target_lane.get("timeframe") == TARGET_TIMEFRAME
        and target_lane.get("direction") == TARGET_DIRECTION
        and target_lane.get("entry_mode") == TARGET_ENTRY_MODE
        and target_lane.get("mode") == "paper"
    )


def _first_capture_candidate(window: Mapping[str, Any]) -> dict[str, Any] | None:
    candidates = window.get("capturable_candidates")
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        return dict(first) if isinstance(first, Mapping) else None
    return None


def _evidence_summary(
    *,
    candidate_window: Mapping[str, Any],
    records_summary: Mapping[str, Any],
    target_lane: Mapping[str, Any],
    captured: bool,
) -> dict[str, Any]:
    return {
        "fresh_candidate_count_added": 1 if captured else 0,
        "total_capture_records_count": int(records_summary.get("records_count") or 0),
        "total_fresh_candidate_count_added": int(records_summary.get("fresh_candidate_count_added") or 0) + (1 if captured else 0),
        "current_fresh_matching_count": int(candidate_window.get("fresh_matching_count") or 0),
        "short_lane_remains_paper": target_lane.get("mode") == "paper",
        "tiny_live_not_authorized": True,
    }


def _recommended_next_operator_move(status: str, window: Mapping[str, Any], captured: bool) -> str:
    if status in {SHORT_PAPER_EVIDENCE_BLOCKED, SHORT_PAPER_EVIDENCE_ERROR, SHORT_PAPER_EVIDENCE_CAPTURE_REJECTED}:
        return STOP_SAFETY_BLOCK if status != SHORT_PAPER_EVIDENCE_CAPTURE_REJECTED else WAIT_FOR_SHORT_FRESH_CANDIDATE
    if captured or int(window.get("fresh_matching_count") or 0) > 0:
        return RUN_R158_SHORT_EVIDENCE_RECHECK
    if status == SHORT_PAPER_EVIDENCE_CAPTURE_TIMEOUT:
        return KEEP_COLLECTING_SHORT_PAPER
    return WAIT_FOR_SHORT_FRESH_CANDIDATE


def _recommended_next_engineering_move(status: str, window: Mapping[str, Any]) -> str:
    if status == SHORT_PAPER_EVIDENCE_CAPTURE_REJECTED:
        return "Rerun only with the exact R157 paper-only confirmation phrase if a bounded capture loop is intended."
    if status in {SHORT_PAPER_EVIDENCE_BLOCKED, SHORT_PAPER_EVIDENCE_ERROR}:
        return "Fix the short paper capture blocker before any R158 recheck."
    if int(window.get("fresh_matching_count") or 0) > 0:
        return "Run R158 short evidence recheck and promotion-readiness packet; do not change lane mode."
    return "Keep the R157 bounded watcher available until fresh BTCUSDT 8m short paper candidates appear."


def _safe_commands() -> list[str]:
    phrase = CONFIRM_SHORT_PAPER_CAPTURE_PHRASE
    return [
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward short-paper-evidence-capture-loop "
            '--lane-key "BTCUSDT|8m|short|ladder_close_50_618" --latest-signals 500 --latest-scans 1000 '
            "--max-iterations 2 --sleep-seconds 1 --iteration-timeout-seconds 30 --heartbeat-every 1 "
            f'--run-capture-loop --record-capture --confirm-short-paper-capture "{phrase}"'
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward short-paper-evidence-capture-loop "
            '--lane-key "BTCUSDT|8m|short|ladder_close_50_618" --latest-signals 500 --latest-scans 1000 '
            "--max-iterations 60 --sleep-seconds 60 --iteration-timeout-seconds 30 --heartbeat-every 1 "
            f'--run-capture-loop --record-capture --confirm-short-paper-capture "{phrase}"'
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward short-strategy-packet "
            "--latest-outcomes 10000 --latest-signals 3000 --latest-betrayal 5000 --latest-watch-records 500"
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward full-spectrum-betrayal-short-review "
            "--latest-outcomes 10000 --latest-signals 3000 --latest-betrayal 5000 --latest-watch-records 500 "
            "--include-paper-lanes --include-tiny-live-incumbents --include-betrayal-inverse"
        ),
    ]


def _compact_lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_key": str(lane.get("lane_key") or normalize_lane_key(lane.get("symbol"), lane.get("timeframe"), lane.get("direction"), lane.get("entry_mode"))),
        "mode": str(lane.get("mode") or "disabled").strip().lower(),
        "symbol": str(lane.get("symbol") or "").strip().upper(),
        "direction": str(lane.get("direction") or "").strip().lower(),
        "timeframe": str(lane.get("timeframe") or "").strip().lower(),
        "entry_mode": str(lane.get("entry_mode") or "").strip().lower(),
        "freshness_seconds": int(lane.get("freshness_seconds") or 0),
        "max_daily_trades": int(lane.get("max_daily_trades") or 0),
        "max_daily_loss_pct": float(lane.get("max_daily_loss_pct") or 0.0),
        "cooldown_after_loss_minutes": int(lane.get("cooldown_after_loss_minutes") or 0),
        "require_protective_orders": bool(lane.get("require_protective_orders")),
    }


def _target_from_key(lane_key: str, *, mode: str) -> dict[str, Any]:
    parts = str(lane_key or "").split("|")
    symbol = parts[0] if len(parts) > 0 else ""
    timeframe = parts[1] if len(parts) > 1 else ""
    direction = parts[2] if len(parts) > 2 else ""
    entry_mode = parts[3] if len(parts) > 3 else ""
    return {
        "lane_key": normalize_lane_key(symbol, timeframe, direction, entry_mode),
        "mode": mode,
        "symbol": str(symbol).strip().upper(),
        "direction": str(direction).strip().lower(),
        "timeframe": str(timeframe).strip().lower(),
        "entry_mode": str(entry_mode).strip().lower(),
        "freshness_seconds": 0,
        "max_daily_trades": 0,
        "max_daily_loss_pct": 0.0,
        "cooldown_after_loss_minutes": 0,
        "require_protective_orders": False,
    }


def _normalize_lane_key_text(lane_key: str) -> str:
    parts = str(lane_key or "").split("|")
    if len(parts) != 4:
        return str(lane_key or "").strip()
    return normalize_lane_key(parts[0], parts[1], parts[2], parts[3])


def _bounded_settings(
    *,
    latest_signals: int,
    latest_scans: int,
    max_iterations: int,
    sleep_seconds: int,
    iteration_timeout_seconds: int,
    heartbeat_every: int,
) -> dict[str, int]:
    return {
        "latest_signals": _bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS),
        "latest_scans": _bounded_int(latest_scans, 1, MAX_LATEST_SCANS, DEFAULT_LATEST_SCANS),
        "max_iterations": _bounded_int(max_iterations, 1, MAX_MAX_ITERATIONS, DEFAULT_MAX_ITERATIONS),
        "sleep_seconds": _bounded_int(sleep_seconds, 1, MAX_SLEEP_SECONDS, DEFAULT_SLEEP_SECONDS),
        "iteration_timeout_seconds": _bounded_int(
            iteration_timeout_seconds,
            1,
            MAX_ITERATION_TIMEOUT_SECONDS,
            DEFAULT_ITERATION_TIMEOUT_SECONDS,
        ),
        "heartbeat_every": _bounded_int(heartbeat_every, 1, MAX_HEARTBEAT_EVERY, DEFAULT_HEARTBEAT_EVERY),
    }


def _bounded_int(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


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


def _tradable(row: Mapping[str, Any]) -> bool:
    for key in ("tradable", "is_tradable", "eligible", "is_eligible", "paper_eligible"):
        if key in row:
            return bool(row.get(key))
    status = str(row.get("status") or row.get("decision") or "").strip().lower()
    if status in {"blocked", "rejected", "stale", "expired", "not_tradable", "not eligible"}:
        return False
    return True


def _mismatch_blocker(candidate: Mapping[str, Any], entry_mode: str, target_lane: Mapping[str, Any]) -> str:
    if str(candidate.get("symbol") or "").strip().upper() != target_lane.get("symbol"):
        return "symbol mismatch"
    if str(candidate.get("timeframe") or "").strip().lower() != target_lane.get("timeframe"):
        return "timeframe mismatch"
    if str(candidate.get("direction") or "").strip().lower() != target_lane.get("direction"):
        return "direction mismatch"
    if entry_mode != target_lane.get("entry_mode"):
        return "entry_mode mismatch"
    return "lane mismatch"


def _top_blockers(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"blocker": key, "count": int(value)} for key, value in counter.most_common(8)]


def _safety(safety: Mapping[str, Any] | None = None) -> dict[str, bool]:
    result = dict(SAFETY)
    for key, value in dict(safety or {}).items():
        if key == "paper_live_separation_intact":
            result[key] = bool(value)
        elif key in result:
            result[key] = bool(value)
    return result


def _should_heartbeat(iteration: int, heartbeat_every: int) -> bool:
    return heartbeat_every <= 1 or iteration % heartbeat_every == 0


def _emit_progress(progress_fn: Callable[[str], None] | None, heartbeat: Mapping[str, Any] | None) -> None:
    if progress_fn is None or not heartbeat:
        return
    progress_fn(
        "SHORT PAPER heartbeat "
        f"iteration={heartbeat.get('iteration')} "
        f"status={_compact_status(heartbeat.get('status'))} "
        f"fresh={heartbeat.get('fresh_matching_count')} "
        f"stale={heartbeat.get('stale_matching_count')} "
        f"captured={str(bool(heartbeat.get('paper_evidence_captured'))).lower()} "
        f"elapsed={float(heartbeat.get('elapsed_seconds') or 0.0):.2f}s"
    )


def _compact_status(value: object) -> str:
    text = str(value or "").lower()
    return text.replace("short_paper_capture_iteration_", "").replace("short_paper_capture_", "")


class IterationTimeoutError(TimeoutError):
    pass


@contextmanager
def _iteration_timeout_guard(seconds: float):
    if seconds <= 0 or threading.current_thread() is not threading.main_thread():
        yield
        return
    previous_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(signum: int, frame: Any) -> None:
        raise IterationTimeoutError(f"short paper capture iteration exceeded {seconds:.3f}s")

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


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


def main(argv: list[str] | None = None) -> int:
    _ = argv
    payload = run_short_paper_evidence_capture_loop(progress_fn=lambda line: print(line, file=sys.stderr, flush=True))
    print(format_short_paper_evidence_capture_json(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
