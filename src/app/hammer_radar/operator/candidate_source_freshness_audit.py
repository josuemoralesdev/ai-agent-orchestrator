"""R151 candidate source freshness and proof starvation audit.

This diagnostic reads local watcher/source ledgers to explain why a completed
fresh-candidate watch did not capture paper proof. It never calls Binance,
creates payloads, mutates env/config, starts services, or authorizes execution.
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
from src.app.hammer_radar.operator.entry_mode_derivation_bridge import normalize_signal_for_watched_lane
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop import (
    LEDGER_FILENAME as WATCH_LEDGER_FILENAME,
    PRIMARY_WATCHED_LANE,
    SECONDARY_WATCHED_LANE,
    load_fresh_candidate_watch_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls, normalize_lane_key
from src.app.hammer_radar.operator.watch_heartbeat import (
    HEARTBEAT_LEDGER_FILENAME,
    WATCH_EXITED,
    load_recent_watch_heartbeats as _load_recent_watch_heartbeats,
)

CANDIDATE_SOURCE_AUDIT_READY = "CANDIDATE_SOURCE_AUDIT_READY"
CANDIDATE_SOURCE_AUDIT_REJECTED = "CANDIDATE_SOURCE_AUDIT_REJECTED"
CANDIDATE_SOURCE_AUDIT_RECORDED = "CANDIDATE_SOURCE_AUDIT_RECORDED"
CANDIDATE_SOURCE_AUDIT_BLOCKED = "CANDIDATE_SOURCE_AUDIT_BLOCKED"
CANDIDATE_SOURCE_AUDIT_ERROR = "CANDIDATE_SOURCE_AUDIT_ERROR"

SOURCE_FEED_STALE_OR_STOPPED = "SOURCE_FEED_STALE_OR_STOPPED"
NO_TARGET_LANE_SIGNALS_DURING_WINDOW = "NO_TARGET_LANE_SIGNALS_DURING_WINDOW"
TARGET_LANE_SIGNALS_ALL_STALE = "TARGET_LANE_SIGNALS_ALL_STALE"
TARGET_TIMEFRAME_PRESENT_BUT_WRONG_DIRECTION = "TARGET_TIMEFRAME_PRESENT_BUT_WRONG_DIRECTION"
TARGET_DIRECTION_PRESENT_BUT_WRONG_TIMEFRAME = "TARGET_DIRECTION_PRESENT_BUT_WRONG_TIMEFRAME"
ENTRY_MODE_OR_LANE_KEY_MISMATCH = "ENTRY_MODE_OR_LANE_KEY_MISMATCH"
WATCH_SCAN_WINDOW_TOO_NARROW = "WATCH_SCAN_WINDOW_TOO_NARROW"
PAPER_CAPTURE_BLOCKED_AFTER_ELIGIBLE_SIGNAL = "PAPER_CAPTURE_BLOCKED_AFTER_ELIGIBLE_SIGNAL"
WATCHER_HEALTHY_MARKET_QUIET = "WATCHER_HEALTHY_MARKET_QUIET"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "CANDIDATE_SOURCE_FRESHNESS_AUDIT"
LEDGER_FILENAME = "candidate_source_freshness_audits.ndjson"
CONFIRM_CANDIDATE_SOURCE_AUDIT_RECORDING_PHRASE = (
    "I CONFIRM CANDIDATE SOURCE AUDIT RECORDING ONLY; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_SIGNALS = 1000
MAX_LATEST_SIGNALS = 20000
DEFAULT_LATEST_SCANS = 2000
MAX_LATEST_SCANS = 50000
DEFAULT_TARGET_LANES = (PRIMARY_WATCHED_LANE, SECONDARY_WATCHED_LANE)
SOURCE_FEED_LIVE_SECONDS = 15 * 60

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{HEARTBEAT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{WATCH_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "logs/hammer_radar_forward/paper_refresh_runs.ndjson",
    "logs/hammer_radar_forward/market_intelligence_snapshots.ndjson",
    "configs/hammer_radar/lane_controls.json",
    "operator.entry_mode_derivation_bridge.normalize_signal_for_watched_lane",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_candidate_source_freshness_audit(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    watch_id: str | None = None,
    record_audit: bool = False,
    confirm_audit: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    bounded_signals = _bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS)
    bounded_scans = _bounded_int(latest_scans, 1, MAX_LATEST_SCANS, DEFAULT_LATEST_SCANS)
    confirmation_valid = confirm_audit == CONFIRM_CANDIDATE_SOURCE_AUDIT_RECORDING_PHRASE
    try:
        target_lanes = _target_lanes()
        watch_window = _build_watch_window(
            log_dir=resolved_log_dir,
            watch_id=watch_id,
        )
        heartbeats = load_recent_watch_heartbeats(
            log_dir=resolved_log_dir,
            watch_id=watch_window.get("watch_id") or watch_id,
            limit=max(int(watch_window.get("iterations_completed") or 0) * 3 + 20, 2500),
        )
        signals_summary = load_recent_signal_source_summary(
            log_dir=resolved_log_dir,
            target_lanes=target_lanes,
            latest_signals=bounded_signals,
            watch_window=watch_window,
            now=generated_at,
        )
        scans_summary = load_recent_scan_source_summary(
            log_dir=resolved_log_dir,
            latest_scans=bounded_scans,
            watch_window=watch_window,
        )
        source_freshness = _build_source_freshness(
            log_dir=resolved_log_dir,
            signals_summary=signals_summary,
            scans_summary=scans_summary,
            watch_window=watch_window,
            now=generated_at,
        )
        watcher_health = _watcher_health(heartbeats)
        starvation = analyze_watch_window_starvation(
            watch_window=watch_window,
            watcher_health=watcher_health,
            source_freshness=source_freshness,
            signal_source_summary=signals_summary,
            scan_source_summary=scans_summary,
        )
        classification = classify_proof_starvation_reason(starvation)
        next_action = build_candidate_source_next_action(classification)
        status = CANDIDATE_SOURCE_AUDIT_READY
        audit_recorded = False
        audit_id = None
        if record_audit and not confirmation_valid:
            status = CANDIDATE_SOURCE_AUDIT_REJECTED
        elif record_audit:
            status = CANDIDATE_SOURCE_AUDIT_RECORDED
            audit_id = f"candidate_source_audit_{uuid4().hex}"
            audit_recorded = True

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "audit_recorded": audit_recorded,
            "audit_id": audit_id,
            "watch_window": watch_window,
            "target_lanes": target_lanes,
            "source_freshness": source_freshness,
            "watcher_health": watcher_health,
            "candidate_distribution": signals_summary["candidate_distribution"],
            "top_blockers": starvation["top_blockers"],
            "starvation_classification": classification,
            "why_no_proof": starvation["why_no_proof"],
            "recommended_next_operator_move": next_action["recommended_next_operator_move"],
            "recommended_next_engineering_move": next_action["recommended_next_engineering_move"],
            "safe_commands": next_action["safe_commands"],
            "do_not_run_yet": [
                "live-connector-submit",
                "any order endpoint",
                "global live flag arming",
                "kill switch disable",
            ],
            "record_audit_requested": bool(record_audit),
            "confirmation_valid": bool(confirmation_valid),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_audit and confirmation_valid:
            record = append_candidate_source_freshness_audit_record(payload, log_dir=resolved_log_dir)
            payload["audit_id"] = record["audit_id"]
            payload["ledger_path"] = str(candidate_source_freshness_audit_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": CANDIDATE_SOURCE_AUDIT_ERROR,
                "generated_at": generated_at.isoformat(),
                "audit_recorded": False,
                "audit_id": None,
                "watch_window": {},
                "target_lanes": list(DEFAULT_TARGET_LANES),
                "source_freshness": {},
                "watcher_health": {},
                "candidate_distribution": {},
                "top_blockers": [f"audit failed: {exc.__class__.__name__}"],
                "starvation_classification": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "why_no_proof": f"R151 audit failed before classification: {exc.__class__.__name__}.",
                "recommended_next_operator_move": "STOP_AND_REVIEW_R151_ERROR",
                "recommended_next_engineering_move": "Fix the R151 diagnostic error before changing watcher or lane behavior.",
                "safe_commands": _safe_commands(),
                "do_not_run_yet": [
                    "live-connector-submit",
                    "any order endpoint",
                    "global live flag arming",
                    "kill switch disable",
                ],
                "record_audit_requested": bool(record_audit),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_recent_watch_heartbeats(
    *,
    log_dir: str | Path | None = None,
    watch_id: str | None = None,
    limit: int = 2500,
) -> list[dict[str, Any]]:
    records = _load_recent_watch_heartbeats(log_dir=log_dir, limit=_bounded_int(limit, 1, 100000, 2500))
    if watch_id:
        records = [record for record in records if str(record.get("watch_id") or "") == str(watch_id)]
    return [_sanitize(record) for record in records]


def load_recent_signal_source_summary(
    *,
    log_dir: str | Path | None = None,
    target_lanes: list[Mapping[str, Any]] | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    watch_window: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = resolved_log_dir / "signals.ndjson"
    records = read_recent_ndjson_records(
        path,
        limit=_bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS),
        max_bytes=16_777_216,
    )
    lanes = list(target_lanes or _target_lanes())
    window_records = _records_in_window(records, watch_window)
    classified = [_classify_signal(record, lanes, generated_at) for record in records]
    window_classified = [_classify_signal(record, lanes, generated_at) for record in window_records]
    distribution = _candidate_distribution(classified, window_classified, watch_window)
    latest_ts = _latest_timestamp(records)
    return {
        "path": str(path),
        "exists": path.exists(),
        "mtime": _mtime_iso(path),
        "latest_timestamp": latest_ts.isoformat() if latest_ts else None,
        "records_checked": len(records),
        "window_records_checked": len(window_records),
        "records": classified,
        "window_records": window_classified,
        "candidate_distribution": distribution,
        "safety": dict(SAFETY),
    }


def load_recent_scan_source_summary(
    *,
    log_dir: str | Path | None = None,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    watch_window: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = resolved_log_dir / "multi_symbol_paper_scans.ndjson"
    records = read_recent_ndjson_records(
        path,
        limit=_bounded_int(latest_scans, 1, MAX_LATEST_SCANS, DEFAULT_LATEST_SCANS),
        max_bytes=32_000_000,
    )
    window_records = _records_in_window(records, watch_window)
    latest_ts = _latest_timestamp(records)
    return {
        "path": str(path),
        "exists": path.exists(),
        "mtime": _mtime_iso(path),
        "latest_timestamp": latest_ts.isoformat() if latest_ts else None,
        "records_checked": len(records),
        "window_records_checked": len(window_records),
        "symbol_counts": dict(sorted(Counter(_symbol(record) or "UNKNOWN" for record in records).items())),
        "safety": dict(SAFETY),
    }


def analyze_watch_window_starvation(
    *,
    watch_window: Mapping[str, Any],
    watcher_health: Mapping[str, Any],
    source_freshness: Mapping[str, Any],
    signal_source_summary: Mapping[str, Any],
    scan_source_summary: Mapping[str, Any],
) -> dict[str, Any]:
    distribution = dict(signal_source_summary.get("candidate_distribution") or {})
    top_blockers = _top_blockers(distribution, watcher_health, source_freshness, scan_source_summary)
    classification = _classify_from_inputs(watch_window, watcher_health, source_freshness, distribution)
    return {
        "classification_hint": classification,
        "top_blockers": top_blockers,
        "why_no_proof": _why_no_proof(classification, watch_window, watcher_health, source_freshness, distribution),
    }


def classify_proof_starvation_reason(starvation: Mapping[str, Any]) -> str:
    classification = str(starvation.get("classification_hint") or "")
    if classification in {
        SOURCE_FEED_STALE_OR_STOPPED,
        NO_TARGET_LANE_SIGNALS_DURING_WINDOW,
        TARGET_LANE_SIGNALS_ALL_STALE,
        TARGET_TIMEFRAME_PRESENT_BUT_WRONG_DIRECTION,
        TARGET_DIRECTION_PRESENT_BUT_WRONG_TIMEFRAME,
        ENTRY_MODE_OR_LANE_KEY_MISMATCH,
        WATCH_SCAN_WINDOW_TOO_NARROW,
        PAPER_CAPTURE_BLOCKED_AFTER_ELIGIBLE_SIGNAL,
        WATCHER_HEALTHY_MARKET_QUIET,
        UNKNOWN_NEEDS_MANUAL_REVIEW,
    }:
        return classification
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def build_candidate_source_next_action(classification: str) -> dict[str, Any]:
    safe_commands = _safe_commands()
    if classification == SOURCE_FEED_STALE_OR_STOPPED:
        return {
            "recommended_next_operator_move": "CHECK_PAPER_REFRESH_AND_RADAR_SERVICES_MANUALLY",
            "recommended_next_engineering_move": "Inspect paper refresh/radar service health and recent source ledgers; do not restart from Codex.",
            "safe_commands": safe_commands,
        }
    if classification == TARGET_LANE_SIGNALS_ALL_STALE:
        return {
            "recommended_next_operator_move": "CONTINUE_OR_SCHEDULE_BOUNDED_FRESH_PROOF_WATCHER",
            "recommended_next_engineering_move": "Keep the R150 watcher bounded and wait for a fresh BTCUSDT 13m/44m long lane signal.",
            "safe_commands": safe_commands,
        }
    if classification == TARGET_TIMEFRAME_PRESENT_BUT_WRONG_DIRECTION:
        return {
            "recommended_next_operator_move": "WAIT_FOR_LONG_TARGET_LANE_OR_REVIEW_SHORTS_PAPER_ONLY",
            "recommended_next_engineering_move": "R152 short-lane paper-only betrayal/short candidate audit; do not enable live shorts.",
            "safe_commands": safe_commands,
        }
    if classification == NO_TARGET_LANE_SIGNALS_DURING_WINDOW:
        return {
            "recommended_next_operator_move": "WAIT_FOR_FRESH_CANDIDATE",
            "recommended_next_engineering_move": "R152 Candidate Opportunity Expansion Audit across 4m/8m/13m/44m/88m long/short paper stats; no live lane widening.",
            "safe_commands": safe_commands,
        }
    if classification == WATCH_SCAN_WINDOW_TOO_NARROW:
        return {
            "recommended_next_operator_move": "RERUN_WATCHER_WITH_LARGER_LATEST_SIGNALS",
            "recommended_next_engineering_move": "Increase R150 --latest-signals safely while preserving freshness and bounded iteration guards.",
            "safe_commands": safe_commands,
        }
    if classification == PAPER_CAPTURE_BLOCKED_AFTER_ELIGIBLE_SIGNAL:
        return {
            "recommended_next_operator_move": "STOP_AND_FIX_PAPER_CAPTURE_BLOCKER",
            "recommended_next_engineering_move": "Inspect R140/R129 paper proof blockers for the eligible signal before retrying.",
            "safe_commands": safe_commands,
        }
    if classification == WATCHER_HEALTHY_MARKET_QUIET:
        return {
            "recommended_next_operator_move": "WAIT_FOR_FRESH_CANDIDATE",
            "recommended_next_engineering_move": "No watcher code change indicated; use R152 only if opportunity distribution suggests lanes are too narrow.",
            "safe_commands": safe_commands,
        }
    return {
        "recommended_next_operator_move": "MANUAL_REVIEW_REQUIRED",
        "recommended_next_engineering_move": "Compare heartbeats, source ledgers, and R145/R150 normalization before changing eligibility logic.",
        "safe_commands": safe_commands,
    }


def append_candidate_source_freshness_audit_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = candidate_source_freshness_audit_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "audit_id": record.get("audit_id") or f"candidate_source_audit_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "watch_window": dict(record.get("watch_window") or {}),
            "target_lanes": list(record.get("target_lanes") or []),
            "source_freshness": dict(record.get("source_freshness") or {}),
            "watcher_health": dict(record.get("watcher_health") or {}),
            "candidate_distribution": dict(record.get("candidate_distribution") or {}),
            "top_blockers": list(record.get("top_blockers") or []),
            "starvation_classification": record.get("starvation_classification"),
            "why_no_proof": record.get("why_no_proof"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safe_commands": list(record.get("safe_commands") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_candidate_source_freshness_audit_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = candidate_source_freshness_audit_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=limit if limit > 0 else 100000, max_bytes=16_777_216)
    if limit <= 0:
        records = list(reversed(records))
    return [_sanitize(record) for record in records]


def summarize_candidate_source_freshness_audits(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    classification_counts = Counter(str(record.get("starvation_classification") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "starvation_classification_counts": dict(sorted(classification_counts.items())),
        "last_audit_id": records[0].get("audit_id") if records else None,
        "safety": dict(SAFETY),
    }


def candidate_source_freshness_audit_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_candidate_source_freshness_audit_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_watch_window(*, log_dir: Path, watch_id: str | None = None) -> dict[str, Any]:
    records = load_fresh_candidate_watch_records(log_dir=log_dir, limit=100)
    selected = {}
    for record in records:
        if watch_id is None or str(record.get("watch_id") or "") == str(watch_id):
            selected = record
            break
    if not selected:
        heartbeats = load_recent_watch_heartbeats(log_dir=log_dir, watch_id=watch_id, limit=2500)
        selected_watch_id = watch_id or (heartbeats[0].get("watch_id") if heartbeats else None)
        selected_heartbeats = [row for row in heartbeats if not selected_watch_id or row.get("watch_id") == selected_watch_id]
        return _watch_window_from_heartbeats(selected_heartbeats, selected_watch_id)
    started = _first_iteration_timestamp(selected)
    ended = _latest_heartbeat_timestamp(log_dir, str(selected.get("watch_id") or ""))
    return {
        "watch_id": selected.get("watch_id"),
        "max_iterations": int(selected.get("max_iterations") or 0),
        "iterations_completed": int(selected.get("iterations_completed") or 0),
        "started_at": started.isoformat() if started else None,
        "ended_at": ended.isoformat() if ended else selected.get("recorded_at_utc"),
        "paper_proof_captured": bool(selected.get("paper_proof_captured")),
        "captured_lane_key": selected.get("captured_lane_key"),
        "status": selected.get("status"),
        "bounded_scan_limits": _latest_bounded_scan_limits(selected),
    }


def _watch_window_from_heartbeats(heartbeats: list[Mapping[str, Any]], watch_id: str | None) -> dict[str, Any]:
    timestamps = [_parse_timestamp(row.get("generated_at")) for row in heartbeats]
    timestamps = [item for item in timestamps if item is not None]
    exited = next((row for row in heartbeats if row.get("status") == WATCH_EXITED), {})
    return {
        "watch_id": watch_id,
        "max_iterations": int((exited or (heartbeats[0] if heartbeats else {})).get("max_iterations") or 0),
        "iterations_completed": int((exited or (heartbeats[0] if heartbeats else {})).get("iteration") or 0),
        "started_at": min(timestamps).isoformat() if timestamps else None,
        "ended_at": max(timestamps).isoformat() if timestamps else None,
        "paper_proof_captured": any(bool(row.get("paper_proof_captured")) for row in heartbeats),
        "captured_lane_key": next((row.get("captured_lane_key") for row in heartbeats if row.get("captured_lane_key")), None),
        "status": "HEARTBEAT_ONLY",
        "bounded_scan_limits": {},
    }


def _build_source_freshness(
    *,
    log_dir: Path,
    signals_summary: Mapping[str, Any],
    scans_summary: Mapping[str, Any],
    watch_window: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    paper_refresh = _source_file_summary(log_dir / "paper_refresh_runs.ndjson")
    market_intel = _source_file_summary(log_dir / "market_intelligence_snapshots.ndjson")
    source_latest = _latest_of(
        _parse_timestamp(signals_summary.get("latest_timestamp")),
        _parse_timestamp(scans_summary.get("latest_timestamp")),
        _parse_timestamp(paper_refresh.get("latest_timestamp")),
        _parse_timestamp(market_intel.get("latest_timestamp")),
    )
    window_end = _parse_timestamp(watch_window.get("ended_at")) or now
    source_appears_live = False
    if source_latest is not None:
        source_appears_live = (window_end - source_latest).total_seconds() <= SOURCE_FEED_LIVE_SECONDS or bool(
            signals_summary.get("window_records_checked") or scans_summary.get("window_records_checked")
        )
    return {
        "signals_latest_timestamp": signals_summary.get("latest_timestamp"),
        "signals_mtime": signals_summary.get("mtime"),
        "paper_scans_latest_timestamp": scans_summary.get("latest_timestamp"),
        "paper_scans_mtime": scans_summary.get("mtime"),
        "paper_refresh_latest_timestamp": paper_refresh.get("latest_timestamp"),
        "paper_refresh_mtime": paper_refresh.get("mtime"),
        "market_intelligence_latest_timestamp": market_intel.get("latest_timestamp"),
        "market_intelligence_mtime": market_intel.get("mtime"),
        "source_appears_live": bool(source_appears_live),
    }


def _source_file_summary(path: Path) -> dict[str, Any]:
    records = read_recent_ndjson_records(path, limit=100, max_bytes=8_388_608)
    latest = _latest_timestamp(records)
    return {
        "path": str(path),
        "exists": path.exists(),
        "mtime": _mtime_iso(path),
        "latest_timestamp": latest.isoformat() if latest else None,
        "records_checked": len(records),
    }


def _watcher_health(heartbeats: list[Mapping[str, Any]]) -> dict[str, Any]:
    completed = [row for row in heartbeats if str(row.get("status") or "") == "WATCH_ITERATION_COMPLETED"]
    elapsed = [float(row.get("elapsed_seconds") or 0.0) for row in completed]
    statuses = Counter(str(row.get("status") or "UNKNOWN") for row in heartbeats)
    return {
        "heartbeat_count": len(heartbeats),
        "last_heartbeat_status": heartbeats[0].get("status") if heartbeats else None,
        "avg_iteration_elapsed_seconds": round(sum(elapsed) / len(elapsed), 6) if elapsed else 0.0,
        "max_iteration_elapsed_seconds": round(max(elapsed), 6) if elapsed else 0.0,
        "performance_guard_triggered": any(str(row.get("status") or "") == "WATCH_ITERATION_TIMEOUT" for row in heartbeats),
        "status_counts": dict(sorted(statuses.items())),
        "paper_proof_captured": any(bool(row.get("paper_proof_captured")) for row in heartbeats),
        "safety": dict(SAFETY),
    }


def _candidate_distribution(
    classified: list[Mapping[str, Any]],
    window_classified: list[Mapping[str, Any]],
    watch_window: Mapping[str, Any] | None,
) -> dict[str, int]:
    rows = window_classified if watch_window and (watch_window.get("started_at") or watch_window.get("ended_at")) else classified
    if not rows and classified:
        rows = classified
    watch_limit = int(((watch_window or {}).get("bounded_scan_limits") or {}).get("latest_signals") or 0)
    latest_window = classified[:watch_limit] if watch_limit > 0 else classified
    target_full = sum(1 for row in rows if row.get("target_lane_match"))
    target_in_watch_tail = sum(1 for row in latest_window if row.get("target_lane_match"))
    return {
        "latest_signals_checked": len(classified),
        "latest_signals_in_watch_window": len(window_classified),
        "target_lane_exact_or_normalized_count": target_full,
        "target_lane_fresh_count": sum(1 for row in rows if row.get("target_lane_match") and row.get("fresh")),
        "target_lane_stale_count": sum(1 for row in rows if row.get("target_lane_match") and not row.get("fresh")),
        "target_timeframe_wrong_direction_count": sum(1 for row in rows if row.get("target_timeframe_wrong_direction")),
        "short_candidate_count": sum(1 for row in rows if row.get("direction") == "short"),
        "wrong_timeframe_count": sum(1 for row in rows if row.get("target_direction_wrong_timeframe")),
        "entry_mode_or_lane_key_mismatch_count": sum(1 for row in rows if row.get("entry_mode_or_lane_key_mismatch")),
        "paper_capture_eligible_seen_count": 0,
        "target_lane_count_inside_watch_latest_signals": target_in_watch_tail,
        "target_lane_count_outside_watch_latest_signals": max(target_full - target_in_watch_tail, 0),
    }


def _classify_signal(record: Mapping[str, Any], target_lanes: list[Mapping[str, Any]], now: datetime) -> dict[str, Any]:
    raw = dict(record)
    normalized_by_lane = [normalize_signal_for_watched_lane(raw, watched_lanes=[lane], now=now) for lane in target_lanes]
    normalized_lane_keys = {str(row.get("after_bridge_lane_key") or row.get("lane_key") or "") for row in normalized_by_lane}
    lane_keys = {str(lane.get("lane_key") or "") for lane in target_lanes}
    symbol = _symbol(raw)
    timeframe = _timeframe(raw)
    direction = _direction(raw)
    entry_mode = _entry_mode(raw)
    target_symbol = symbol in {str(lane.get("symbol") or "") for lane in target_lanes}
    target_tf = timeframe in {str(lane.get("timeframe") or "") for lane in target_lanes}
    target_dir = direction in {str(lane.get("direction") or "") for lane in target_lanes}
    exact_key = normalize_lane_key(symbol, timeframe, direction, entry_mode)
    target_match = exact_key in lane_keys or bool(normalized_lane_keys & lane_keys)
    matching_lane = next((lane for lane in target_lanes if str(lane.get("lane_key") or "") in ({exact_key} | normalized_lane_keys)), None)
    age = _age_seconds(_timestamp(raw), now)
    freshness_seconds = int((matching_lane or {}).get("freshness_seconds") or 0)
    fresh = target_match and age is not None and freshness_seconds > 0 and age <= freshness_seconds
    return {
        "signal_id": _signal_id(raw),
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "timestamp": _timestamp(raw),
        "exact_lane_key": exact_key,
        "normalized_lane_keys": sorted(key for key in normalized_lane_keys if key),
        "target_lane_match": target_match,
        "fresh": fresh,
        "age_seconds": age,
        "freshness_seconds": freshness_seconds,
        "target_timeframe_wrong_direction": bool(target_symbol and target_tf and not target_dir),
        "target_direction_wrong_timeframe": bool(target_symbol and target_dir and not target_tf),
        "entry_mode_or_lane_key_mismatch": bool(target_symbol and target_tf and target_dir and not target_match),
    }


def _classify_from_inputs(
    watch_window: Mapping[str, Any],
    watcher_health: Mapping[str, Any],
    source_freshness: Mapping[str, Any],
    distribution: Mapping[str, Any],
) -> str:
    if bool(watch_window.get("paper_proof_captured")):
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if bool(watcher_health.get("performance_guard_triggered")):
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if not bool(source_freshness.get("source_appears_live")):
        return SOURCE_FEED_STALE_OR_STOPPED
    if int(distribution.get("paper_capture_eligible_seen_count") or 0) > 0:
        return PAPER_CAPTURE_BLOCKED_AFTER_ELIGIBLE_SIGNAL
    if int(distribution.get("target_lane_count_outside_watch_latest_signals") or 0) > 0 and int(
        distribution.get("target_lane_count_inside_watch_latest_signals") or 0
    ) == 0:
        return WATCH_SCAN_WINDOW_TOO_NARROW
    target_count = int(distribution.get("target_lane_exact_or_normalized_count") or 0)
    fresh_count = int(distribution.get("target_lane_fresh_count") or 0)
    if target_count > 0 and fresh_count == 0:
        return TARGET_LANE_SIGNALS_ALL_STALE
    if target_count == 0 and int(distribution.get("entry_mode_or_lane_key_mismatch_count") or 0) > 0:
        return ENTRY_MODE_OR_LANE_KEY_MISMATCH
    if target_count == 0 and int(distribution.get("target_timeframe_wrong_direction_count") or 0) > 0:
        return TARGET_TIMEFRAME_PRESENT_BUT_WRONG_DIRECTION
    if target_count == 0 and int(distribution.get("wrong_timeframe_count") or 0) > 0:
        return TARGET_DIRECTION_PRESENT_BUT_WRONG_TIMEFRAME
    if target_count == 0:
        if _watcher_healthy(watch_window, watcher_health):
            return WATCHER_HEALTHY_MARKET_QUIET
        return NO_TARGET_LANE_SIGNALS_DURING_WINDOW
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def _watcher_healthy(watch_window: Mapping[str, Any], watcher_health: Mapping[str, Any]) -> bool:
    return (
        str(watcher_health.get("last_heartbeat_status") or "") == WATCH_EXITED
        and not bool(watcher_health.get("performance_guard_triggered"))
        and int(watch_window.get("iterations_completed") or 0) >= int(watch_window.get("max_iterations") or 0) > 0
    )


def _why_no_proof(
    classification: str,
    watch_window: Mapping[str, Any],
    watcher_health: Mapping[str, Any],
    source_freshness: Mapping[str, Any],
    distribution: Mapping[str, Any],
) -> str:
    if classification == SOURCE_FEED_STALE_OR_STOPPED:
        return "The watcher completed without proof because source ledgers did not show live market/scanner input during or near the watch window."
    if classification == TARGET_LANE_SIGNALS_ALL_STALE:
        return "BTCUSDT 13m/44m long target-lane candidates existed, but all were stale under lane freshness rules when audited."
    if classification == TARGET_TIMEFRAME_PRESENT_BUT_WRONG_DIRECTION:
        return "BTCUSDT target timeframes appeared during the audited window, but direction was not the watched long lane."
    if classification == TARGET_DIRECTION_PRESENT_BUT_WRONG_TIMEFRAME:
        return "BTCUSDT long candidates appeared, but on timeframes outside the watched 13m/44m target lanes."
    if classification == ENTRY_MODE_OR_LANE_KEY_MISMATCH:
        return "BTCUSDT target symbol/timeframe/direction existed, but entry mode or lane-key normalization did not match the watched lanes."
    if classification == WATCH_SCAN_WINDOW_TOO_NARROW:
        return "The broader audit tail found target-lane candidates that were outside the watcher's bounded latest-signals tail."
    if classification == PAPER_CAPTURE_BLOCKED_AFTER_ELIGIBLE_SIGNAL:
        return "At least one eligible signal appears to have reached paper-capture eligibility, but the R140/R129 capture path did not record proof."
    if classification == WATCHER_HEALTHY_MARKET_QUIET:
        return "The 720-iteration watcher appears healthy and source ledgers appear live, but no BTCUSDT 13m/44m long target-lane candidate appeared in the audited window."
    if classification == NO_TARGET_LANE_SIGNALS_DURING_WINDOW:
        return "Source ledgers appear live, but the audited source rows contain no BTCUSDT 13m/44m long target-lane signal."
    return "The available source and watcher ledgers do not identify one dominant starvation cause."


def _top_blockers(
    distribution: Mapping[str, Any],
    watcher_health: Mapping[str, Any],
    source_freshness: Mapping[str, Any],
    scan_source_summary: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not source_freshness.get("source_appears_live"):
        blockers.append("source feed stale or stopped")
    if watcher_health.get("performance_guard_triggered"):
        blockers.append("watch performance guard triggered")
    if int(distribution.get("target_lane_exact_or_normalized_count") or 0) == 0:
        blockers.append("no exact or R145-normalized target-lane signals in audited window")
    if int(distribution.get("target_lane_stale_count") or 0) > 0 and int(distribution.get("target_lane_fresh_count") or 0) == 0:
        blockers.append("target-lane signals were stale")
    if int(distribution.get("short_candidate_count") or 0) > 0:
        blockers.append("short candidates present but target lanes are long only")
    if int(scan_source_summary.get("window_records_checked") or 0) == 0:
        blockers.append("no recent paper scan rows inside watcher window")
    return blockers[:6]


def _safe_commands() -> list[str]:
    return [
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward candidate-source-freshness-audit --latest-signals 1000 --latest-scans 2000",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward fresh-candidate-paper-proof-capture-loop --watch-all-recommended-lanes",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward post-tiny-live-mode-fresh-proof-watch --all-target-lanes --include-watch-command",
    ]


def _target_lanes() -> list[dict[str, Any]]:
    controls = load_lane_controls()
    lane_map = controls.get("lane_map") if isinstance(controls.get("lane_map"), Mapping) else {}
    lanes = []
    for key in DEFAULT_TARGET_LANES:
        lane = lane_map.get(key) if isinstance(lane_map, Mapping) else None
        lanes.append(dict(lane) if isinstance(lane, Mapping) else _lane_spec(key))
    return lanes


def _lane_spec(lane_key: str) -> dict[str, Any]:
    parts = [*str(lane_key or "").split("|"), "", "", "", ""][:4]
    return {
        "lane_key": normalize_lane_key(parts[0], parts[1], parts[2], parts[3]),
        "symbol": str(parts[0] or "").strip().upper(),
        "timeframe": str(parts[1] or "").strip().lower(),
        "direction": str(parts[2] or "").strip().lower(),
        "entry_mode": str(parts[3] or "").strip().lower(),
        "freshness_seconds": 0,
    }


def _records_in_window(records: list[Mapping[str, Any]], watch_window: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    start = _parse_timestamp((watch_window or {}).get("started_at"))
    end = _parse_timestamp((watch_window or {}).get("ended_at"))
    if start is None and end is None:
        return list(records)
    result = []
    for record in records:
        ts = _record_timestamp(record)
        if ts is None:
            continue
        if start is not None and ts < start:
            continue
        if end is not None and ts > end:
            continue
        result.append(record)
    return result


def _latest_timestamp(records: list[Mapping[str, Any]]) -> datetime | None:
    return _latest_of(*(_record_timestamp(record) for record in records))


def _latest_of(*values: datetime | None) -> datetime | None:
    parsed = [value for value in values if value is not None]
    return max(parsed) if parsed else None


def _record_timestamp(record: Mapping[str, Any]) -> datetime | None:
    return _parse_timestamp(
        record.get("generated_at")
        or record.get("timestamp")
        or record.get("created_at")
        or record.get("closed_at")
        or record.get("detected_at")
        or record.get("latest_signal_timestamp")
        or record.get("started_at")
        or record.get("completed_at")
        or record.get("recorded_at_utc")
    )


def _first_iteration_timestamp(record: Mapping[str, Any]) -> datetime | None:
    summaries = list(record.get("iteration_summaries") or [])
    timestamps = [_parse_timestamp(item.get("started_at")) for item in summaries if isinstance(item, Mapping)]
    return min((item for item in timestamps if item is not None), default=None)


def _latest_heartbeat_timestamp(log_dir: Path, watch_id: str) -> datetime | None:
    heartbeats = load_recent_watch_heartbeats(log_dir=log_dir, watch_id=watch_id, limit=2500)
    timestamps = [_parse_timestamp(row.get("generated_at")) for row in heartbeats]
    return max((item for item in timestamps if item is not None), default=None)


def _latest_bounded_scan_limits(record: Mapping[str, Any]) -> dict[str, int]:
    limits = dict(record.get("bounded_scan_limits") or {})
    if limits:
        return {"latest_signals": int(limits.get("latest_signals") or 0), "latest_scans": int(limits.get("latest_scans") or 0)}
    summaries = list(record.get("iteration_summaries") or [])
    for summary in summaries:
        if isinstance(summary, Mapping) and isinstance(summary.get("bounded_scan_limits"), Mapping):
            return dict(summary["bounded_scan_limits"])
    return {}


def _mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _timestamp(record: Mapping[str, Any]) -> str | None:
    value = (
        record.get("generated_at")
        or record.get("timestamp")
        or record.get("closed_at")
        or record.get("detected_at")
        or record.get("created_at")
    )
    return str(value) if value not in (None, "") else None


def _age_seconds(timestamp: object, now: datetime) -> float | None:
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        return None
    return max((now - parsed).total_seconds(), 0.0)


def _signal_id(record: Mapping[str, Any]) -> str:
    value = record.get("signal_id") or record.get("candidate_id")
    if value not in (None, ""):
        return str(value)
    return "|".join(part for part in (_symbol(record), _timeframe(record), _direction(record), str(_timestamp(record) or "")) if part)


def _symbol(record: Mapping[str, Any]) -> str:
    return str(record.get("symbol") or "").strip().upper()


def _timeframe(record: Mapping[str, Any]) -> str:
    return str(record.get("timeframe") or "").strip().lower()


def _direction(record: Mapping[str, Any]) -> str:
    return str(record.get("direction") or record.get("latest_direction") or "").strip().lower()


def _entry_mode(record: Mapping[str, Any]) -> str:
    return str(record.get("entry_mode") or "").strip().lower()


def _bounded_int(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


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
