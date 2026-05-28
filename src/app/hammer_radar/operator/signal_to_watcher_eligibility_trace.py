"""R144 signal-to-watcher eligibility trace.

This module explains why visible signal records do or do not become R142
watcher-eligible lane candidates. It is diagnostic only: it never creates order
payloads, calls Binance, signs requests, mutates env files, changes lane config,
or enables live execution.
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
from src.app.hammer_radar.operator.autonomous_paper_lane_executor_integration import (
    run_autonomous_paper_lane_executor_once,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop import (
    PRIMARY_WATCHED_LANE,
    SECONDARY_WATCHED_LANE,
    evaluate_watcher_iteration,
    load_fresh_candidate_watch_records,
)
from src.app.hammer_radar.operator.entry_mode_derivation_bridge import (
    DERIVATION_SOURCE,
    normalize_signal_for_watched_lane,
)
from src.app.hammer_radar.operator.fresh_signal_router import (
    ROUTED_TO_LANE,
    build_lane_key_from_candidate,
    evaluate_candidate_against_lanes,
    normalize_candidate,
)
from src.app.hammer_radar.operator.lane_control import normalize_lane_key
from src.app.hammer_radar.operator.tiny_live_lane_unlock_contract import (
    UNLOCKED_WAITING_FOR_CONDITIONS,
    build_lane_unlock_contract,
)

SIGNAL_WATCHER_TRACE_READY = "SIGNAL_WATCHER_TRACE_READY"
SIGNAL_WATCHER_TRACE_REJECTED = "SIGNAL_WATCHER_TRACE_REJECTED"
SIGNAL_WATCHER_TRACE_RECORDED = "SIGNAL_WATCHER_TRACE_RECORDED"
SIGNAL_WATCHER_TRACE_BLOCKED = "SIGNAL_WATCHER_TRACE_BLOCKED"
SIGNAL_WATCHER_TRACE_ERROR = "SIGNAL_WATCHER_TRACE_ERROR"

SIGNAL_MATCHES_WATCHED_LANE_AND_ELIGIBLE = "SIGNAL_MATCHES_WATCHED_LANE_AND_ELIGIBLE"
SIGNAL_MATCHES_WATCHED_LANE_BUT_ENTRY_MODE_MISSING = "SIGNAL_MATCHES_WATCHED_LANE_BUT_ENTRY_MODE_MISSING"
SIGNAL_MATCHES_TIMEFRAME_DIRECTION_BUT_ENTRY_MODE_MISMATCH = "SIGNAL_MATCHES_TIMEFRAME_DIRECTION_BUT_ENTRY_MODE_MISMATCH"
SIGNAL_TIMEFRAME_NOT_WATCHED = "SIGNAL_TIMEFRAME_NOT_WATCHED"
SIGNAL_DIRECTION_NOT_WATCHED = "SIGNAL_DIRECTION_NOT_WATCHED"
SIGNAL_SYMBOL_NOT_WATCHED = "SIGNAL_SYMBOL_NOT_WATCHED"
SIGNAL_STALE_BY_WATCHER_RULES = "SIGNAL_STALE_BY_WATCHER_RULES"
SIGNAL_NOT_FOUND_IN_PAPER_SCAN = "SIGNAL_NOT_FOUND_IN_PAPER_SCAN"
SIGNAL_FOUND_IN_SCAN_BUT_NOT_ROUTED = "SIGNAL_FOUND_IN_SCAN_BUT_NOT_ROUTED"
SIGNAL_ROUTED_BUT_NOT_PAPER_ELIGIBLE = "SIGNAL_ROUTED_BUT_NOT_PAPER_ELIGIBLE"
SIGNAL_BLOCKED_BY_PAPER_EXECUTOR = "SIGNAL_BLOCKED_BY_PAPER_EXECUTOR"
SIGNAL_BLOCKED_BY_UNLOCK_CONTRACT_ABSENCE = "SIGNAL_BLOCKED_BY_UNLOCK_CONTRACT_ABSENCE"
SIGNAL_BLOCKED_BY_LANE_MODE = "SIGNAL_BLOCKED_BY_LANE_MODE"
SIGNAL_BLOCKED_BY_UNKNOWN_REASON = "SIGNAL_BLOCKED_BY_UNKNOWN_REASON"

EVENT_TYPE = "SIGNAL_TO_WATCHER_ELIGIBILITY_TRACE"
LEDGER_FILENAME = "signal_to_watcher_eligibility_traces.ndjson"
CONFIRM_SIGNAL_TO_WATCHER_TRACE_PHRASE = (
    "I CONFIRM SIGNAL TO WATCHER TRACE RECORDING ONLY; NO ORDER; NO BINANCE CALL."
)
DEFAULT_LATEST_SIGNALS = 100
MAX_LATEST_SIGNALS = 1000
DEFAULT_LATEST_SCANS = 200
MAX_LATEST_SCANS = 5000
FALLBACK_WATCHED_LANES = (PRIMARY_WATCHED_LANE, SECONDARY_WATCHED_LANE)

SAFETY = {
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
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
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "logs/hammer_radar_forward/fresh_candidate_paper_proof_capture_loop.ndjson",
    "operator.tiny_live_lane_unlock_contract.build_lane_unlock_contract(status_only=True)",
    "operator.fresh_signal_router.evaluate_candidate_against_lanes",
    "operator.entry_mode_derivation_bridge.normalize_signal_for_watched_lane",
    "operator.autonomous_paper_lane_executor_integration.run_autonomous_paper_lane_executor_once(preview)",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_signal_to_watcher_eligibility_trace(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    trace_all_unlocked_lanes: bool = False,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    signal_id: str | None = None,
    record_trace: bool = False,
    confirm_trace: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    bounded_signals = _bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS)
    bounded_scans = _bounded_int(latest_scans, 1, MAX_LATEST_SCANS, DEFAULT_LATEST_SCANS)
    confirmation_valid = confirm_trace == CONFIRM_SIGNAL_TO_WATCHER_TRACE_PHRASE

    try:
        signals = load_recent_signal_records(log_dir=resolved_log_dir, limit=bounded_signals)
        if signal_id:
            signals = [record for record in signals if str(record.get("signal_id") or "") == signal_id]
        scans = load_recent_paper_scan_records(log_dir=resolved_log_dir, limit=bounded_scans)
        lane_context = build_unlocked_watched_lane_context(
            log_dir=resolved_log_dir,
            lane_keys=lane_keys,
            lane_keys_csv=lane_keys_csv,
            trace_all_unlocked_lanes=trace_all_unlocked_lanes,
            now=generated_at,
        )
        watched_lanes = list(lane_context["watched_lanes"])
        signal_traces = [
            _build_single_signal_trace(
                signal=signal,
                paper_scans=scans,
                watched_lanes=watched_lanes,
                unlock_contract_status=lane_context["unlock_contract_status"],
                log_dir=resolved_log_dir,
                now=generated_at,
            )
            for signal in signals
        ]
        summary = build_signal_trace_summary(
            signals=signals,
            paper_scans=scans,
            signal_traces=signal_traces,
        )
        status = SIGNAL_WATCHER_TRACE_READY
        trace_recorded = False
        trace_id = None
        if record_trace and not confirmation_valid:
            status = SIGNAL_WATCHER_TRACE_REJECTED
        elif record_trace:
            status = SIGNAL_WATCHER_TRACE_RECORDED
            trace_id = f"signal_to_watcher_trace_{uuid4().hex}"
            trace_recorded = True

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "trace_recorded": trace_recorded,
            "trace_id": trace_id,
            "trace_scope": {
                "latest_signals": bounded_signals,
                "latest_scans": bounded_scans,
                "signal_id": signal_id,
                "trace_all_unlocked_lanes": bool(trace_all_unlocked_lanes),
                "lane_keys": [lane["lane_key"] for lane in watched_lanes],
            },
            "unlock_contract_status": lane_context["unlock_contract_status"],
            "watched_lanes": watched_lanes,
            "latest_signal_summary": summary["latest_signal_summary"],
            "paper_scan_summary": summary["paper_scan_summary"],
            "signal_traces": signal_traces,
            "aggregate_gap_counts": summary["aggregate_gap_counts"],
            "best_next_engineering_move": _best_next_engineering_move(summary["aggregate_gap_counts"]),
            "recommended_next_commands": _recommended_next_commands(signal_id=signal_id),
            "record_trace_requested": bool(record_trace),
            "confirmation_valid": bool(confirmation_valid),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_trace and confirmation_valid:
            append_signal_to_watcher_trace_record(payload, log_dir=resolved_log_dir)
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive diagnostic boundary
        return _sanitize(
            {
                "status": SIGNAL_WATCHER_TRACE_ERROR,
                "generated_at": generated_at.isoformat(),
                "trace_recorded": False,
                "trace_id": None,
                "trace_scope": {
                    "latest_signals": bounded_signals,
                    "latest_scans": bounded_scans,
                    "signal_id": signal_id,
                },
                "unlock_contract_status": {},
                "watched_lanes": [],
                "latest_signal_summary": {},
                "paper_scan_summary": {},
                "signal_traces": [],
                "aggregate_gap_counts": {},
                "best_next_engineering_move": "Fix R144 trace source error before changing router or eligibility logic.",
                "recommended_next_commands": _recommended_next_commands(signal_id=signal_id),
                "record_trace_requested": bool(record_trace),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_recent_signal_records(*, log_dir: str | Path | None = None, limit: int = DEFAULT_LATEST_SIGNALS) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = read_recent_ndjson_records(
        resolved_log_dir / "signals.ndjson",
        limit=_bounded_int(limit, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS),
        max_bytes=2_097_152,
    )
    return [_normalize_signal_record(record) for record in records]


def load_recent_paper_scan_records(*, log_dir: str | Path | None = None, limit: int = DEFAULT_LATEST_SCANS) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = read_recent_ndjson_records(
        resolved_log_dir / "multi_symbol_paper_scans.ndjson",
        limit=_bounded_int(limit, 1, MAX_LATEST_SCANS, DEFAULT_LATEST_SCANS),
        max_bytes=8_388_608,
    )
    return [_sanitize(dict(record)) for record in records]


def build_unlocked_watched_lane_context(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    trace_all_unlocked_lanes: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    explicit_keys = _dedupe([*list(lane_keys or []), *_split_lane_keys(lane_keys_csv)])
    unlock_status = build_lane_unlock_contract(log_dir=log_dir, status_only=True, now=now)
    unlocked_lanes = [
        _lane_spec(str(lane.get("lane_key") or ""))
        for lane in unlock_status.get("lanes") or []
        if isinstance(lane, Mapping) and lane.get("lane_key")
    ]
    if explicit_keys:
        selected = [_lane_spec(key) for key in explicit_keys]
        source = "explicit_lane_keys"
    elif trace_all_unlocked_lanes and unlocked_lanes:
        selected = unlocked_lanes
        source = "r143_unlock_contract"
    elif unlocked_lanes:
        selected = unlocked_lanes
        source = "r143_unlock_contract"
    else:
        selected = [_lane_spec(key) for key in FALLBACK_WATCHED_LANES]
        source = "fallback_watched_lanes"
    return {
        "watched_lanes": selected,
        "unlock_contract_status": {
            "status": unlock_status.get("status"),
            "execution_state": unlock_status.get("execution_state"),
            "unlock_contract_id": unlock_status.get("unlock_contract_id"),
            "latest_contract_id": unlock_status.get("latest_contract_id"),
            "source": source,
            "fallback_used": source == "fallback_watched_lanes",
            "unlocked_lane_keys": [lane["lane_key"] for lane in unlocked_lanes],
        },
    }


def match_signals_to_watched_lanes(
    signals: list[Mapping[str, Any]],
    watched_lanes: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "signal_id": _signal_id(signal),
            "matched_watched_lane_keys": _matched_lane_keys(signal, watched_lanes, exact=True),
            "possible_watched_lane_keys": _matched_lane_keys(signal, watched_lanes, exact=False),
        }
        for signal in signals
    ]


def trace_signal_entry_mode_derivation(signal: Mapping[str, Any]) -> dict[str, Any]:
    raw_entry_mode = _entry_mode(signal)
    normalized = normalize_candidate(_candidate_for_preview(signal))
    derived_entry_mode = normalized.get("entry_mode")
    return {
        "raw_entry_mode": raw_entry_mode,
        "fresh_router_derived_entry_mode": derived_entry_mode,
        "entry_mode_missing": raw_entry_mode is None,
        "derivation_source": "fresh_signal_router.normalize_candidate_default" if raw_entry_mode is None else "signal_record",
        "derived_lane_key": build_lane_key_from_candidate(normalized),
    }


def trace_signal_entry_mode_bridge(
    signal: Mapping[str, Any],
    *,
    watched_lanes: list[Mapping[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized = normalize_signal_for_watched_lane(signal, watched_lanes=watched_lanes, now=now)
    return {
        "before_bridge_entry_mode": normalized.get("before_bridge_entry_mode"),
        "after_bridge_entry_mode": normalized.get("after_bridge_entry_mode"),
        "after_bridge_lane_key": normalized.get("after_bridge_lane_key"),
        "bridge_would_match_watched_lane": bool(normalized.get("bridge_would_match_watched_lane")),
        "bridge_would_still_block_reason": normalized.get("bridge_would_still_block_reason"),
        "freshness_status_after_bridge": normalized.get("freshness_status_after_bridge"),
        "derived_entry_mode": bool(normalized.get("derived_entry_mode")),
        "derivation_source": normalized.get("derivation_source") or DERIVATION_SOURCE,
        "normalized_signal": normalized,
    }


def trace_signal_to_paper_scan(signal: Mapping[str, Any], paper_scans: list[Mapping[str, Any]]) -> dict[str, Any]:
    matches = []
    signal_ts = _timestamp(signal)
    for scan in paper_scans:
        if _symbol(scan) != _symbol(signal):
            continue
        if _timeframe(scan) != _timeframe(signal):
            continue
        scan_direction = _direction(scan)
        latest_direction = str(scan.get("latest_direction") or "").strip().lower()
        if scan_direction != _direction(signal) and latest_direction != _direction(signal):
            continue
        matches.append(scan)
    best = _best_scan_match(matches, signal_ts)
    if best is None:
        return {"found": False, "match_count": 0, "reason": "no recent paper scan matched symbol/timeframe/direction"}
    return {
        "found": True,
        "match_count": len(matches),
        "scan_id": best.get("scan_id"),
        "created_at": best.get("created_at"),
        "latest_signal_timestamp": best.get("latest_signal_timestamp"),
        "symbol": best.get("symbol"),
        "timeframe": best.get("timeframe"),
        "direction": best.get("direction"),
        "entry_mode": best.get("entry_mode"),
        "paper_signal_status": best.get("paper_signal_status"),
        "paper_eligible": best.get("paper_eligible"),
        "score": best.get("score"),
        "tier": best.get("tier"),
        "blockers": list(best.get("blockers") or []),
        "reason": best.get("reason"),
    }


def trace_signal_to_fresh_router(
    signal: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    try:
        routed = evaluate_candidate_against_lanes(
            _candidate_for_preview(signal),
            now=now or datetime.now(UTC),
            log_dir=log_dir,
        )
        return {
            "available": True,
            "candidate_id": routed.get("candidate_id"),
            "lane_key": routed.get("lane_key"),
            "route_status": routed.get("route_status"),
            "route_action": routed.get("route_action"),
            "lane_mode": routed.get("lane_mode"),
            "lane_status": routed.get("lane_status"),
            "candidate_age_seconds": routed.get("candidate_age_seconds"),
            "freshness_seconds": routed.get("freshness_seconds"),
            "blockers": list(routed.get("blockers") or []),
            "safety": dict(SAFETY),
        }
    except Exception as exc:  # pragma: no cover - defensive diagnostic boundary
        return {"available": False, "error": exc.__class__.__name__, "safety": dict(SAFETY)}


def trace_signal_to_paper_executor(
    signal: Mapping[str, Any],
    *,
    lane_key: str | None = None,
    log_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    try:
        preview = run_autonomous_paper_lane_executor_once(
            log_dir=log_dir,
            record_paper=False,
            record_scheduler_tick=False,
            record_decisions=False,
            lane_key=lane_key,
            candidates=[_candidate_for_preview(signal)],
            now=now or datetime.now(UTC),
        )
        return {
            "available": True,
            "status": preview.get("status"),
            "selected_lane_keys": list(preview.get("selected_lane_keys") or []),
            "candidates_seen_count": int(preview.get("candidates_seen_count") or 0),
            "decisions_seen_count": int(preview.get("decisions_seen_count") or 0),
            "paper_eligible_decisions_count": int(preview.get("paper_eligible_decisions_count") or 0),
            "paper_blocked_decisions_count": int(preview.get("paper_blocked_decisions_count") or 0),
            "candidate_decisions": list(preview.get("candidate_decisions") or []),
            "blocked_decisions": list(preview.get("blocked_decisions") or [])[:5],
            "top_blockers": list(preview.get("top_blockers") or []),
            "integration_recorded": bool(preview.get("integration_recorded")),
            "safety": dict(SAFETY),
        }
    except Exception as exc:  # pragma: no cover - defensive diagnostic boundary
        return {"available": False, "error": exc.__class__.__name__, "safety": dict(SAFETY)}


def trace_signal_to_watcher_consumption(
    signal: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    lane_key: str | None = None,
) -> dict[str, Any]:
    records = load_fresh_candidate_watch_records(log_dir=log_dir, limit=5)
    latest = records[0] if records else {}
    final_lane_statuses = latest.get("final_lane_statuses") if isinstance(latest.get("final_lane_statuses"), Mapping) else {}
    lane_status = final_lane_statuses.get(lane_key or "") if isinstance(final_lane_statuses, Mapping) else None
    return {
        "found_recent_watcher_record": bool(latest),
        "latest_watch_id": latest.get("watch_id"),
        "latest_status": latest.get("status"),
        "paper_proof_captured": bool(latest.get("paper_proof_captured")),
        "lane_key": lane_key,
        "lane_evaluation": lane_status or {},
        "watcher_rule": "R142 requires fresh_routed_count > 0 and paper_eligible_decisions_count > 0 with clean safety.",
        "signal_id_present_in_watcher_record": _signal_id(signal) in json.dumps(latest, sort_keys=True) if latest else False,
    }


def classify_signal_watcher_gap(
    *,
    signal: Mapping[str, Any],
    watched_lanes: list[Mapping[str, Any]],
    paper_scan_match: Mapping[str, Any],
    fresh_router_match: Mapping[str, Any],
    paper_executor_match: Mapping[str, Any],
    unlock_contract_status: Mapping[str, Any],
) -> str:
    symbol = _symbol(signal)
    timeframe = _timeframe(signal)
    direction = _direction(signal)
    entry_mode = _entry_mode(signal)
    symbol_lanes = [lane for lane in watched_lanes if lane.get("symbol") == symbol]
    if not symbol_lanes:
        return SIGNAL_SYMBOL_NOT_WATCHED
    timeframe_lanes = [lane for lane in symbol_lanes if lane.get("timeframe") == timeframe]
    if not timeframe_lanes:
        return SIGNAL_TIMEFRAME_NOT_WATCHED
    direction_lanes = [lane for lane in timeframe_lanes if lane.get("direction") == direction]
    if not direction_lanes:
        return SIGNAL_DIRECTION_NOT_WATCHED
    if entry_mode is None:
        return SIGNAL_MATCHES_WATCHED_LANE_BUT_ENTRY_MODE_MISSING
    exact_lanes = [lane for lane in direction_lanes if lane.get("entry_mode") == entry_mode]
    if not exact_lanes:
        return SIGNAL_MATCHES_TIMEFRAME_DIRECTION_BUT_ENTRY_MODE_MISMATCH
    if unlock_contract_status.get("fallback_used") and not unlock_contract_status.get("unlocked_lane_keys"):
        return SIGNAL_BLOCKED_BY_UNLOCK_CONTRACT_ABSENCE
    if fresh_router_match.get("route_status") == "EXPIRED_SIGNAL":
        return SIGNAL_STALE_BY_WATCHER_RULES
    if not paper_scan_match.get("found"):
        return SIGNAL_NOT_FOUND_IN_PAPER_SCAN
    if fresh_router_match.get("route_status") != ROUTED_TO_LANE:
        if str(fresh_router_match.get("lane_status") or "").upper() in {"LANE_DISABLED", "LANE_BLOCKED"}:
            return SIGNAL_BLOCKED_BY_LANE_MODE
        return SIGNAL_FOUND_IN_SCAN_BUT_NOT_ROUTED
    if int(paper_executor_match.get("paper_eligible_decisions_count") or 0) > 0:
        return SIGNAL_MATCHES_WATCHED_LANE_AND_ELIGIBLE
    if paper_executor_match.get("top_blockers") or paper_executor_match.get("blocked_decisions"):
        return SIGNAL_BLOCKED_BY_PAPER_EXECUTOR
    return SIGNAL_ROUTED_BUT_NOT_PAPER_ELIGIBLE


def build_signal_trace_summary(
    *,
    signals: list[Mapping[str, Any]],
    paper_scans: list[Mapping[str, Any]],
    signal_traces: list[Mapping[str, Any]],
) -> dict[str, Any]:
    gap_counts = Counter(str(trace.get("gap_classification") or "UNKNOWN") for trace in signal_traces)
    signal_timeframes = Counter(_timeframe(signal) or "UNKNOWN" for signal in signals)
    signal_directions = Counter(_direction(signal) or "UNKNOWN" for signal in signals)
    missing_entry_mode = sum(1 for signal in signals if _entry_mode(signal) is None)
    scan_symbols = Counter(_symbol(scan) or "UNKNOWN" for scan in paper_scans)
    return {
        "latest_signal_summary": {
            "signals_seen_count": len(signals),
            "missing_entry_mode_count": missing_entry_mode,
            "timeframe_counts": dict(sorted(signal_timeframes.items())),
            "direction_counts": dict(sorted(signal_directions.items())),
        },
        "paper_scan_summary": {
            "paper_scans_seen_count": len(paper_scans),
            "symbol_counts": dict(sorted(scan_symbols.items())),
            "btc_scan_count": scan_symbols.get("BTCUSDT", 0),
        },
        "aggregate_gap_counts": dict(sorted(gap_counts.items())),
    }


def append_signal_to_watcher_trace_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = signal_to_watcher_trace_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "trace_id": record.get("trace_id") or f"signal_to_watcher_trace_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "watched_lanes": list(record.get("watched_lanes") or []),
            "trace_scope": dict(record.get("trace_scope") or {}),
            "aggregate_gap_counts": dict(record.get("aggregate_gap_counts") or {}),
            "signal_traces": list(record.get("signal_traces") or []),
            "best_next_engineering_move": record.get("best_next_engineering_move"),
            "recommended_next_commands": list(record.get("recommended_next_commands") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_signal_to_watcher_trace_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = signal_to_watcher_trace_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=limit if limit > 0 else 100_000, max_bytes=16_777_216)
    if limit <= 0:
        records = list(reversed(records))
    return [_sanitize(record) for record in records]


def summarize_signal_to_watcher_traces(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    gap_counts: Counter[str] = Counter()
    for record in records:
        gap_counts.update({str(key): int(value) for key, value in dict(record.get("aggregate_gap_counts") or {}).items()})
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "aggregate_gap_counts": dict(sorted(gap_counts.items())),
        "last_trace_id": records[0].get("trace_id") if records else None,
        "safety": dict(SAFETY),
    }


def format_signal_to_watcher_eligibility_trace_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def signal_to_watcher_trace_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _build_single_signal_trace(
    *,
    signal: Mapping[str, Any],
    paper_scans: list[Mapping[str, Any]],
    watched_lanes: list[Mapping[str, Any]],
    unlock_contract_status: Mapping[str, Any],
    log_dir: Path,
    now: datetime,
) -> dict[str, Any]:
    entry_trace = trace_signal_entry_mode_derivation(signal)
    bridge = trace_signal_entry_mode_bridge(signal, watched_lanes=watched_lanes, now=now)
    bridged_signal = bridge["normalized_signal"] if isinstance(bridge.get("normalized_signal"), Mapping) else signal
    matched_exact = _matched_lane_keys(bridged_signal, watched_lanes, exact=True)
    possible = _matched_lane_keys(signal, watched_lanes, exact=False)
    lane_key_for_preview = matched_exact[0] if matched_exact else (bridge.get("after_bridge_lane_key") if possible else None)
    paper_scan = trace_signal_to_paper_scan(signal, paper_scans)
    router = trace_signal_to_fresh_router(bridged_signal, log_dir=log_dir, now=now)
    paper_executor = trace_signal_to_paper_executor(bridged_signal, lane_key=lane_key_for_preview, log_dir=log_dir, now=now)
    watcher = trace_signal_to_watcher_consumption(signal, log_dir=log_dir, lane_key=lane_key_for_preview)
    gap = classify_signal_watcher_gap(
        signal=bridged_signal,
        watched_lanes=watched_lanes,
        paper_scan_match=paper_scan,
        fresh_router_match=router,
        paper_executor_match=paper_executor,
        unlock_contract_status=unlock_contract_status,
    )
    return {
        "signal_id": _signal_id(signal),
        "symbol": _symbol(signal),
        "timeframe": _timeframe(signal),
        "direction": _direction(signal),
        "entry_mode": _entry_mode(signal),
        "before_bridge_entry_mode": bridge.get("before_bridge_entry_mode"),
        "after_bridge_entry_mode": bridge.get("after_bridge_entry_mode"),
        "after_bridge_lane_key": bridge.get("after_bridge_lane_key"),
        "bridge_would_match_watched_lane": bool(bridge.get("bridge_would_match_watched_lane")),
        "bridge_would_still_block_reason": bridge.get("bridge_would_still_block_reason"),
        "signal_timestamp": _timestamp(signal),
        "matched_watched_lane_keys": matched_exact,
        "possible_watched_lane_keys": possible,
        "entry_mode_derivation": entry_trace,
        "entry_mode_derivation_bridge": {key: value for key, value in bridge.items() if key != "normalized_signal"},
        "paper_scan_match": paper_scan,
        "fresh_router_match": router,
        "paper_executor_match": paper_executor,
        "watcher_consumption_match": watcher,
        "gap_classification": gap,
        "why_not_watcher_eligible": _why_not_watcher_eligible(gap, signal, router, paper_executor),
        "next_fix_hint": _next_fix_hint(gap),
    }


def _normalize_signal_record(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    payload["symbol"] = _symbol(payload)
    payload["timeframe"] = _timeframe(payload)
    payload["direction"] = _direction(payload)
    payload["entry_mode"] = _entry_mode(payload)
    payload["signal_id"] = _signal_id(payload)
    payload["timestamp"] = _timestamp(payload)
    return _sanitize(payload)


def _candidate_for_preview(signal: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": _signal_id(signal),
        "signal_id": _signal_id(signal),
        "symbol": _symbol(signal),
        "timeframe": _timeframe(signal),
        "direction": _direction(signal),
        "entry_mode": _entry_mode(signal),
        "generated_at": _timestamp(signal),
        "timestamp": _timestamp(signal),
        "score": signal.get("score") or signal.get("latest_score"),
        "tier": signal.get("tier"),
        "freshness_status": signal.get("freshness_status"),
    }


def _lane_spec(lane_key: str) -> dict[str, Any]:
    parts = [*str(lane_key or "").split("|"), "", "", "", ""][:4]
    return {
        "lane_key": normalize_lane_key(parts[0], parts[1], parts[2], parts[3]),
        "symbol": str(parts[0] or "").strip().upper(),
        "timeframe": str(parts[1] or "").strip().lower(),
        "direction": str(parts[2] or "").strip().lower(),
        "entry_mode": str(parts[3] or "").strip().lower(),
    }


def _matched_lane_keys(signal: Mapping[str, Any], watched_lanes: list[Mapping[str, Any]], *, exact: bool) -> list[str]:
    result: list[str] = []
    for lane in watched_lanes:
        if lane.get("symbol") != _symbol(signal):
            continue
        if lane.get("timeframe") != _timeframe(signal):
            continue
        if lane.get("direction") != _direction(signal):
            continue
        if exact and lane.get("entry_mode") != _entry_mode(signal):
            continue
        result.append(str(lane.get("lane_key") or ""))
    return _dedupe(result)


def _best_scan_match(matches: list[Mapping[str, Any]], signal_ts: str | None) -> Mapping[str, Any] | None:
    if not matches:
        return None
    exact = [scan for scan in matches if str(scan.get("latest_signal_timestamp") or "") == str(signal_ts or "")]
    if exact:
        return exact[0]
    return matches[0]


def _best_next_engineering_move(gap_counts: Mapping[str, int]) -> str:
    if int(gap_counts.get(SIGNAL_MATCHES_WATCHED_LANE_BUT_ENTRY_MODE_MISSING) or 0) > 0:
        return "R145 Entry Mode Derivation Bridge / Paper Scan Candidate Normalization"
    if int(gap_counts.get(SIGNAL_NOT_FOUND_IN_PAPER_SCAN) or 0) > 0:
        return "R145 normalize paper scan candidates into lane-key-addressable watcher inputs."
    if int(gap_counts.get(SIGNAL_FOUND_IN_SCAN_BUT_NOT_ROUTED) or 0) > 0:
        return "Inspect R123 route normalization before changing watcher behavior."
    return "Review the highest aggregate gap before patching production eligibility logic."


def _recommended_next_commands(*, signal_id: str | None = None) -> list[str]:
    commands = [
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward signal-to-watcher-eligibility-trace --trace-all-unlocked-lanes",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward fresh-candidate-paper-proof-capture-loop --watch-all-recommended-lanes",
    ]
    if signal_id:
        commands.insert(
            1,
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            f"--log-dir logs/hammer_radar_forward signal-to-watcher-eligibility-trace --trace-all-unlocked-lanes --signal-id \"{signal_id}\"",
        )
    return commands


def _why_not_watcher_eligible(
    gap: str,
    signal: Mapping[str, Any],
    router: Mapping[str, Any],
    paper_executor: Mapping[str, Any],
) -> str:
    if gap == SIGNAL_MATCHES_WATCHED_LANE_AND_ELIGIBLE:
        return "The signal matches a watched lane and current preview surfaces show watcher eligibility."
    if gap == SIGNAL_MATCHES_WATCHED_LANE_BUT_ENTRY_MODE_MISSING:
        return "The signal matches watched symbol/timeframe/direction, but the signal record has no entry_mode, so it does not exactly match the watched lane key."
    if gap == SIGNAL_MATCHES_TIMEFRAME_DIRECTION_BUT_ENTRY_MODE_MISMATCH:
        return f"The signal entry_mode={_entry_mode(signal)} does not match the watched lane entry mode."
    if gap == SIGNAL_TIMEFRAME_NOT_WATCHED:
        return "The signal symbol is watched, but its timeframe is not one of the watched lane timeframes."
    if gap == SIGNAL_DIRECTION_NOT_WATCHED:
        return "The signal symbol/timeframe is watched, but its direction is not watched for that lane."
    if gap == SIGNAL_SYMBOL_NOT_WATCHED:
        return "The signal symbol is not present in the watched lane set."
    if gap == SIGNAL_STALE_BY_WATCHER_RULES:
        return "The fresh router preview marks the candidate stale under lane freshness rules."
    if gap == SIGNAL_NOT_FOUND_IN_PAPER_SCAN:
        return "No recent multi-symbol paper scan row matched this signal's symbol/timeframe/direction."
    if gap == SIGNAL_FOUND_IN_SCAN_BUT_NOT_ROUTED:
        return f"The signal appears in paper scan context, but router status is {router.get('route_status')}."
    if gap == SIGNAL_ROUTED_BUT_NOT_PAPER_ELIGIBLE:
        return "The router can route the signal, but the paper executor preview has zero eligible decisions."
    if gap == SIGNAL_BLOCKED_BY_PAPER_EXECUTOR:
        return f"Paper executor preview blockers: {_blocker_text(paper_executor)}"
    if gap == SIGNAL_BLOCKED_BY_UNLOCK_CONTRACT_ABSENCE:
        return "No R143 unlock contract was found; fallback watched lanes were used for diagnostics only."
    if gap == SIGNAL_BLOCKED_BY_LANE_MODE:
        return "The router matched lane identity but lane mode or lane permission blocked routing."
    return "The available trace surfaces did not expose a more specific reason."


def _next_fix_hint(gap: str) -> str:
    hints = {
        SIGNAL_MATCHES_WATCHED_LANE_AND_ELIGIBLE: "No R144 fix required; rerun R142 watcher during a fresh window.",
        SIGNAL_MATCHES_WATCHED_LANE_BUT_ENTRY_MODE_MISSING: "R145 should derive or attach entry_mode before watcher lane-key matching.",
        SIGNAL_MATCHES_TIMEFRAME_DIRECTION_BUT_ENTRY_MODE_MISMATCH: "Normalize candidate entry_mode to the watched lane key or update the watched lane in a future explicit config phase.",
        SIGNAL_TIMEFRAME_NOT_WATCHED: "Confirm whether this timeframe should be added to a future watched-lane contract.",
        SIGNAL_DIRECTION_NOT_WATCHED: "Confirm whether this direction should be watched; do not change R142 in R144.",
        SIGNAL_SYMBOL_NOT_WATCHED: "Keep R144 diagnostic-only; add watched symbols only in a future lane-control phase.",
        SIGNAL_STALE_BY_WATCHER_RULES: "Rerun watcher during a fresh signal window or review freshness_seconds in a future phase.",
        SIGNAL_NOT_FOUND_IN_PAPER_SCAN: "R145 should normalize paper scan candidates into lane-key-addressable records.",
        SIGNAL_FOUND_IN_SCAN_BUT_NOT_ROUTED: "Inspect R123 candidate normalization and lane matching in a follow-up phase.",
        SIGNAL_ROUTED_BUT_NOT_PAPER_ELIGIBLE: "Inspect R127/R129 blockers before changing watcher behavior.",
        SIGNAL_BLOCKED_BY_PAPER_EXECUTOR: "Clear paper executor blockers through existing R129/R140 surfaces.",
        SIGNAL_BLOCKED_BY_UNLOCK_CONTRACT_ABSENCE: "Record or inspect R143 unlock contract before expecting watcher eligibility.",
        SIGNAL_BLOCKED_BY_LANE_MODE: "Use existing R124/R122 lane-control surfaces in a future approved phase if lane mode is wrong.",
    }
    return hints.get(gap, "Collect another R144 trace with a specific signal id.")


def _blocker_text(payload: Mapping[str, Any]) -> str:
    blockers = []
    for item in payload.get("top_blockers") or []:
        if isinstance(item, Mapping):
            blockers.append(str(item.get("blocker") or ""))
        else:
            blockers.append(str(item))
    for item in payload.get("blocked_decisions") or []:
        if isinstance(item, Mapping):
            blockers.extend(str(value) for value in item.get("blockers") or [])
    return "; ".join(_dedupe(blockers)) or "none exposed"


def _symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or "").strip().upper()


def _timeframe(row: Mapping[str, Any]) -> str:
    return str(row.get("timeframe") or "").strip().lower()


def _direction(row: Mapping[str, Any]) -> str:
    return str(row.get("direction") or row.get("latest_direction") or "").strip().lower()


def _entry_mode(row: Mapping[str, Any]) -> str | None:
    value = row.get("entry_mode")
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    return text or None


def _timestamp(row: Mapping[str, Any]) -> str | None:
    value = row.get("timestamp") or row.get("generated_at") or row.get("closed_at") or row.get("detected_at")
    return str(value) if value not in (None, "") else None


def _signal_id(row: Mapping[str, Any]) -> str:
    value = row.get("signal_id") or row.get("candidate_id")
    if value not in (None, ""):
        return str(value)
    return "|".join(part for part in (_symbol(row), _timeframe(row), _direction(row), str(_timestamp(row) or "")) if part)


def _split_lane_keys(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _bounded_int(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _sanitize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
