"""R146 post-bridge watcher proof capture recheck.

This module audits whether R145-normalized watched-lane candidates are visible
to the existing R142/R129 paper proof path. It is diagnostic only and never
creates order payloads, signs requests, calls Binance, mutates env/config, or
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
from src.app.hammer_radar.operator.autonomous_paper_lane_executor_integration import (
    load_paper_executor_integration_records,
    run_autonomous_paper_lane_executor_once,
)
from src.app.hammer_radar.operator.entry_mode_derivation_bridge import (
    ENTRY_MODE_DERIVATION_BRIDGE_RECORDED,
    build_entry_mode_derivation_bridge_status,
    build_watched_lane_context,
    load_entry_mode_derivation_bridge_records,
    load_recent_signal_records,
    normalize_signal_for_watched_lane,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop import (
    load_fresh_candidate_watch_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_lane_unlock_contract import build_lane_unlock_contract

POST_BRIDGE_RECHECK_READY = "POST_BRIDGE_RECHECK_READY"
POST_BRIDGE_RECHECK_REJECTED = "POST_BRIDGE_RECHECK_REJECTED"
POST_BRIDGE_RECHECK_RECORDED = "POST_BRIDGE_RECHECK_RECORDED"
POST_BRIDGE_RECHECK_BLOCKED = "POST_BRIDGE_RECHECK_BLOCKED"
POST_BRIDGE_RECHECK_ERROR = "POST_BRIDGE_RECHECK_ERROR"

RUN_R142_WATCHER = "RUN_R142_WATCHER"
CAPTURE_PAPER_PROOF_AVAILABLE = "CAPTURE_PAPER_PROOF_AVAILABLE"
WAIT_FOR_FRESH_NORMALIZED_CANDIDATE = "WAIT_FOR_FRESH_NORMALIZED_CANDIDATE"
RERUN_R145_TRACE = "RERUN_R145_TRACE"
STOP_SAFETY_BLOCK = "STOP_SAFETY_BLOCK"
BUILD_R147_AFTER_PAPER_PROOF_RECHECK = "BUILD_R147_AFTER_PAPER_PROOF_RECHECK"

EVENT_TYPE = "POST_BRIDGE_WATCHER_PROOF_CAPTURE_RECHECK"
LEDGER_FILENAME = "post_bridge_watcher_proof_capture_rechecks.ndjson"
CONFIRM_POST_BRIDGE_RECHECK_RECORDING_PHRASE = (
    "I CONFIRM POST BRIDGE WATCHER RECHECK RECORDING ONLY; NO ORDER; NO BINANCE CALL."
)
DEFAULT_LATEST_SIGNALS = 100
MAX_LATEST_SIGNALS = 1000

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "order_payload_created": False,
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
BLOCKING_SAFETY_KEYS = tuple(key for key, value in SAFETY.items() if value is False)

SOURCE_SURFACES_USED = [
    "operator.entry_mode_derivation_bridge.build_entry_mode_derivation_bridge_status",
    "operator.entry_mode_derivation_bridge.normalize_signal_for_watched_lane",
    "operator.tiny_live_lane_unlock_contract.build_lane_unlock_contract(status_only=True)",
    "operator.autonomous_paper_lane_executor_integration.run_autonomous_paper_lane_executor_once(preview)",
    "operator.fresh_candidate_paper_proof_capture_loop.load_fresh_candidate_watch_records",
    "operator.autonomous_paper_lane_executor_integration.load_paper_executor_integration_records",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/entry_mode_derivation_bridge_records.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_post_bridge_watcher_proof_capture_recheck(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    trace_all_unlocked_lanes: bool = False,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    record_recheck: bool = False,
    confirm_post_bridge_recheck: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_post_bridge_recheck == CONFIRM_POST_BRIDGE_RECHECK_RECORDING_PHRASE
    try:
        state = collect_post_bridge_watcher_state(
            log_dir=resolved_log_dir,
            lane_keys=lane_keys,
            lane_keys_csv=lane_keys_csv,
            trace_all_unlocked_lanes=trace_all_unlocked_lanes,
            latest_signals=latest_signals,
            now=generated_at,
        )
        visibility = evaluate_normalized_candidate_visibility(state)
        readiness = evaluate_post_bridge_paper_capture_readiness(state)
        summary = build_post_bridge_recheck_summary(
            generated_at=generated_at,
            state=state,
            visibility=visibility,
            readiness=readiness,
            record_recheck=record_recheck,
            confirmation_valid=confirmation_valid,
        )
        if record_recheck and not confirmation_valid:
            summary["status"] = POST_BRIDGE_RECHECK_REJECTED
            summary["why"] = "Exact R146 recording-only confirmation phrase is required; no recheck was recorded."
            return _sanitize(summary)
        if record_recheck:
            record = append_post_bridge_recheck_record(summary, log_dir=resolved_log_dir)
            summary.update(
                {
                    "status": POST_BRIDGE_RECHECK_RECORDED,
                    "trace_recorded": True,
                    "recheck_id": record["recheck_id"],
                    "ledger_path": str(post_bridge_recheck_records_path(resolved_log_dir)),
                }
            )
        return _sanitize(summary)
    except Exception as exc:  # pragma: no cover - defensive diagnostic boundary
        return _sanitize(
            {
                "status": POST_BRIDGE_RECHECK_ERROR,
                "generated_at": generated_at.isoformat(),
                "trace_recorded": False,
                "recheck_id": None,
                "unlock_contract_status": {},
                "bridge_status": {},
                "watched_lanes": [],
                "normalized_candidate_visibility": _empty_visibility(),
                "paper_capture_readiness": _empty_readiness(),
                "next_operator_move": STOP_SAFETY_BLOCK,
                "why": f"R146 diagnostic boundary failed: {exc.__class__.__name__}.",
                "recommended_commands": [],
                "do_not_run_yet": _do_not_run_yet(),
                "record_recheck_requested": bool(record_recheck),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def collect_post_bridge_watcher_state(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    trace_all_unlocked_lanes: bool = False,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    bounded_latest = _bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS)
    context = build_watched_lane_context(
        log_dir=resolved_log_dir,
        lane_keys=lane_keys,
        lane_keys_csv=lane_keys_csv,
        trace_all_unlocked_lanes=trace_all_unlocked_lanes,
        now=generated_at,
    )
    watched_lanes = list(context.get("watched_lanes") or [])
    signals = load_recent_signal_records(log_dir=resolved_log_dir, limit=bounded_latest)
    normalized = [
        normalize_signal_for_watched_lane(signal, watched_lanes=watched_lanes, now=generated_at)
        for signal in signals
    ]
    visible = [row for row in normalized if row.get("bridge_would_match_watched_lane")]
    fresh_visible = [row for row in visible if row.get("freshness_status_after_bridge") == "FRESH"]
    paper_previews = [
        _paper_preview_for_lane(
            log_dir=resolved_log_dir,
            lane_key=str(lane.get("lane_key") or ""),
            candidates=[row for row in fresh_visible if row.get("after_bridge_lane_key") == lane.get("lane_key")],
            now=generated_at,
        )
        for lane in watched_lanes
        if lane.get("lane_key")
    ]
    bridge_records = load_entry_mode_derivation_bridge_records(log_dir=resolved_log_dir, limit=10)
    bridge_preview = build_entry_mode_derivation_bridge_status(
        log_dir=resolved_log_dir,
        lane_keys=lane_keys,
        lane_keys_csv=lane_keys_csv,
        trace_all_unlocked_lanes=trace_all_unlocked_lanes,
        latest_signals=bounded_latest,
        now=generated_at,
    )
    watch_records = load_fresh_candidate_watch_records(log_dir=resolved_log_dir, limit=20)
    paper_records = load_paper_executor_integration_records(log_dir=resolved_log_dir, limit=20)
    return _sanitize(
        {
            "generated_at": generated_at.isoformat(),
            "log_dir": str(resolved_log_dir),
            "latest_signals": bounded_latest,
            "unlock_contract_status": build_lane_unlock_contract(log_dir=resolved_log_dir, status_only=True, now=generated_at),
            "watched_lane_context": context,
            "watched_lanes": watched_lanes,
            "bridge_preview": bridge_preview,
            "bridge_records": bridge_records,
            "signals": signals,
            "normalized_signals": normalized,
            "normalized_watched_candidates": visible,
            "fresh_normalized_candidates": fresh_visible,
            "paper_previews": paper_previews,
            "watch_records": watch_records,
            "paper_records": paper_records,
            "safety": _combined_safety(bridge_preview, *paper_previews),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )


def evaluate_normalized_candidate_visibility(state: Mapping[str, Any]) -> dict[str, Any]:
    normalized = [row for row in state.get("normalized_signals") or [] if isinstance(row, Mapping)]
    visible = [row for row in normalized if row.get("bridge_would_match_watched_lane")]
    fresh = [row for row in visible if row.get("freshness_status_after_bridge") == "FRESH"]
    stale = [row for row in visible if row.get("freshness_status_after_bridge") == "STALE"]
    examples = [
        {
            "signal_id": row.get("signal_id") or row.get("candidate_id"),
            "derived_lane_key": row.get("after_bridge_lane_key"),
            "before_bridge_entry_mode": row.get("before_bridge_entry_mode"),
            "after_bridge_entry_mode": row.get("after_bridge_entry_mode"),
            "derived_entry_mode": bool(row.get("derived_entry_mode")),
            "freshness_status_after_bridge": row.get("freshness_status_after_bridge"),
            "blocked_reason_after_bridge": row.get("bridge_would_still_block_reason"),
        }
        for row in visible[:10]
    ]
    return {
        "signals_checked": len(normalized),
        "normalized_watched_lane_count": len(visible),
        "fresh_normalized_count": len(fresh),
        "stale_normalized_count": len(stale),
        "examples": examples,
    }


def evaluate_post_bridge_paper_capture_readiness(state: Mapping[str, Any]) -> dict[str, Any]:
    paper_previews = [row for row in state.get("paper_previews") or [] if isinstance(row, Mapping)]
    watch_records = [row for row in state.get("watch_records") or [] if isinstance(row, Mapping)]
    paper_records = [row for row in state.get("paper_records") or [] if isinstance(row, Mapping)]
    paper_proof_captured = any(bool(row.get("paper_proof_captured")) for row in watch_records) or any(
        int(row.get("paper_execution_records_created") or 0) > 0 for row in paper_records
    )
    eligible = sum(int(row.get("paper_eligible_decisions_count") or 0) for row in paper_previews)
    blocked = sum(int(row.get("paper_blocked_decisions_count") or 0) for row in paper_previews)
    blockers = Counter(
        str(item.get("blocker") or item)
        for preview in paper_previews
        for item in list(preview.get("top_blockers") or [])
        if item
    )
    return {
        "paper_proof_captured": bool(paper_proof_captured),
        "paper_eligible_decisions_count": eligible,
        "paper_blocked_decisions_count": blocked,
        "top_blockers": [{"blocker": blocker, "count": count} for blocker, count in blockers.most_common(5)],
    }


def build_post_bridge_safe_watch_command() -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward "
        "fresh-candidate-paper-proof-capture-loop "
        "--watch-all-recommended-lanes "
        "--max-iterations 60 "
        "--sleep-seconds 60 "
        "--run-watch-loop "
        "--record-watch "
        '--confirm-watch-loop "I CONFIRM FRESH CANDIDATE PAPER PROOF WATCH ONLY; NO ORDER; NO BINANCE CALL."'
    )


def build_post_bridge_recheck_summary(
    *,
    generated_at: datetime,
    state: Mapping[str, Any],
    visibility: Mapping[str, Any],
    readiness: Mapping[str, Any],
    record_recheck: bool,
    confirmation_valid: bool,
) -> dict[str, Any]:
    safety = _combined_safety(state)
    bridge_recorded = any(str(row.get("status") or "") == ENTRY_MODE_DERIVATION_BRIDGE_RECORDED for row in state.get("bridge_records") or [])
    next_move = _next_operator_move(
        safety=safety,
        bridge_recorded=bridge_recorded,
        visibility=visibility,
        readiness=readiness,
    )
    recommended = _recommended_commands(next_move)
    return {
        "status": POST_BRIDGE_RECHECK_BLOCKED if next_move == STOP_SAFETY_BLOCK else POST_BRIDGE_RECHECK_READY,
        "generated_at": generated_at.isoformat(),
        "trace_recorded": False,
        "recheck_id": None,
        "unlock_contract_status": state.get("unlock_contract_status") or {},
        "bridge_status": _bridge_status(state, bridge_recorded=bridge_recorded),
        "watched_lanes": list(state.get("watched_lanes") or []),
        "normalized_candidate_visibility": dict(visibility),
        "paper_capture_readiness": dict(readiness),
        "next_operator_move": next_move,
        "why": _why(next_move, visibility=visibility, readiness=readiness, bridge_recorded=bridge_recorded),
        "recommended_commands": recommended,
        "do_not_run_yet": _do_not_run_yet(),
        "record_recheck_requested": bool(record_recheck),
        "confirmation_valid": bool(confirmation_valid),
        "safety": safety,
        "source_surfaces_used": _dedupe(list(state.get("source_surfaces_used") or []) + SOURCE_SURFACES_USED),
    }


def append_post_bridge_recheck_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = post_bridge_recheck_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "recheck_id": record.get("recheck_id") or f"post_bridge_recheck_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": POST_BRIDGE_RECHECK_RECORDED,
            "next_operator_move": record.get("next_operator_move"),
            "why": record.get("why"),
            "unlock_contract_status": record.get("unlock_contract_status") or {},
            "bridge_status": record.get("bridge_status") or {},
            "watched_lanes": list(record.get("watched_lanes") or []),
            "normalized_candidate_visibility": record.get("normalized_candidate_visibility") or {},
            "paper_capture_readiness": record.get("paper_capture_readiness") or {},
            "recommended_commands": list(record.get("recommended_commands") or []),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_post_bridge_recheck_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = post_bridge_recheck_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=limit if limit > 0 else 100_000, max_bytes=16_777_216)
    if limit <= 0:
        records = list(reversed(records))
    return [_sanitize(row) for row in records]


def summarize_post_bridge_rechecks(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(row.get("status") or "UNKNOWN") for row in records)
    move_counts = Counter(str(row.get("next_operator_move") or "UNKNOWN") for row in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "next_operator_move_counts": dict(sorted(move_counts.items())),
        "last_recheck_id": records[0].get("recheck_id") if records else None,
        "safety": dict(SAFETY),
    }


def format_post_bridge_watcher_proof_capture_recheck_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def post_bridge_recheck_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _paper_preview_for_lane(*, log_dir: Path, lane_key: str, candidates: list[Mapping[str, Any]], now: datetime) -> dict[str, Any]:
    if not candidates:
        return {
            "status": "NO_FRESH_NORMALIZED_CANDIDATE",
            "lane_key": lane_key,
            "paper_eligible_decisions_count": 0,
            "paper_blocked_decisions_count": 0,
            "top_blockers": [],
            "safety": dict(SAFETY),
        }
    try:
        payload = run_autonomous_paper_lane_executor_once(
            log_dir=log_dir,
            record_paper=False,
            record_scheduler_tick=False,
            record_decisions=False,
            lane_key=lane_key,
            candidates=list(candidates),
            now=now,
        )
        return _sanitize({**payload, "lane_key": lane_key})
    except Exception as exc:
        return {
            "status": "PAPER_PREVIEW_BLOCKED",
            "lane_key": lane_key,
            "paper_eligible_decisions_count": 0,
            "paper_blocked_decisions_count": len(candidates),
            "top_blockers": [{"blocker": f"paper preview unavailable: {exc.__class__.__name__}", "count": 1}],
            "safety": dict(SAFETY),
        }


def _next_operator_move(
    *,
    safety: Mapping[str, Any],
    bridge_recorded: bool,
    visibility: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> str:
    if not _safety_clean(safety):
        return STOP_SAFETY_BLOCK
    if not bridge_recorded:
        return RERUN_R145_TRACE
    if readiness.get("paper_proof_captured"):
        return BUILD_R147_AFTER_PAPER_PROOF_RECHECK
    normalized_count = int(visibility.get("normalized_watched_lane_count") or 0)
    fresh_count = int(visibility.get("fresh_normalized_count") or 0)
    stale_count = int(visibility.get("stale_normalized_count") or 0)
    eligible_count = int(readiness.get("paper_eligible_decisions_count") or 0)
    if normalized_count > 0 and fresh_count == 0 and stale_count >= normalized_count:
        return WAIT_FOR_FRESH_NORMALIZED_CANDIDATE
    if fresh_count > 0 and eligible_count > 0:
        return CAPTURE_PAPER_PROOF_AVAILABLE
    if fresh_count > 0:
        return RUN_R142_WATCHER
    return RUN_R142_WATCHER


def _why(next_move: str, *, visibility: Mapping[str, Any], readiness: Mapping[str, Any], bridge_recorded: bool) -> str:
    if next_move == STOP_SAFETY_BLOCK:
        return "A source safety flag was unsafe; stop before any watcher action."
    if next_move == RERUN_R145_TRACE:
        return "No recorded R145 bridge diagnostic was found; rerun and record R145 before relying on the post-bridge watcher recheck."
    if next_move == BUILD_R147_AFTER_PAPER_PROOF_RECHECK:
        return "Paper proof is already captured through existing watcher/paper ledgers; R147 can recheck live-ready gates without orders."
    if next_move == WAIT_FOR_FRESH_NORMALIZED_CANDIDATE:
        return "R145-normalized watched-lane candidates are visible, but all visible candidates are stale and remain blocked by freshness."
    if next_move == CAPTURE_PAPER_PROOF_AVAILABLE:
        return "A fresh normalized watched-lane candidate is visible and the R129 paper preview reports an eligible decision."
    if int(visibility.get("fresh_normalized_count") or 0) > 0:
        return "A fresh normalized watched-lane candidate is visible; run the bounded R142 watcher so existing paper proof logic can decide."
    return "No normalized watched-lane candidate is visible in the latest window; run the bounded R142 watcher during the next signal window."


def _recommended_commands(next_move: str) -> list[str]:
    commands = [
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward entry-mode-derivation-bridge --trace-all-unlocked-lanes",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward signal-to-watcher-eligibility-trace --trace-all-unlocked-lanes",
    ]
    if next_move in {RUN_R142_WATCHER, WAIT_FOR_FRESH_NORMALIZED_CANDIDATE, CAPTURE_PAPER_PROOF_AVAILABLE}:
        return [build_post_bridge_safe_watch_command(), *commands]
    if next_move == BUILD_R147_AFTER_PAPER_PROOF_RECHECK:
        return [
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward post-bridge-watcher-proof-capture-recheck --trace-all-unlocked-lanes",
        ]
    return commands


def _do_not_run_yet() -> list[str]:
    return [
        "Binance order commands",
        "Binance test-order commands",
        "protective order endpoint commands",
        "global live flag mutation commands",
        "kill-switch disable commands",
        "lane widening or short-lane config changes",
    ]


def _bridge_status(state: Mapping[str, Any], *, bridge_recorded: bool) -> dict[str, Any]:
    bridge_preview = state.get("bridge_preview") if isinstance(state.get("bridge_preview"), Mapping) else {}
    latest_record = next(iter(state.get("bridge_records") or []), {})
    return {
        "status": bridge_preview.get("status"),
        "recorded_bridge_available": bridge_recorded,
        "latest_record_status": latest_record.get("status") if isinstance(latest_record, Mapping) else None,
        "latest_bridge_id": latest_record.get("bridge_id") if isinstance(latest_record, Mapping) else None,
        "recent_signal_bridge_summary": bridge_preview.get("recent_signal_bridge_summary") or {},
    }


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
    return all(not bool(safety.get(key)) for key in BLOCKING_SAFETY_KEYS) and safety.get("paper_live_separation_intact") is not False


def _empty_visibility() -> dict[str, Any]:
    return {
        "signals_checked": 0,
        "normalized_watched_lane_count": 0,
        "fresh_normalized_count": 0,
        "stale_normalized_count": 0,
        "examples": [],
    }


def _empty_readiness() -> dict[str, Any]:
    return {
        "paper_proof_captured": False,
        "paper_eligible_decisions_count": 0,
        "paper_blocked_decisions_count": 0,
        "top_blockers": [],
    }


def _bounded_int(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


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
