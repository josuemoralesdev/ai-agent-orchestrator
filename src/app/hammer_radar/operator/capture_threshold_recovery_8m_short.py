"""R208 capture threshold recovery for BTCUSDT 8m short.

This module reconciles local paper capture ledgers only. It never calls
Binance/network, mutates env/config/lane/risk state, creates payloads, changes
lane modes, or authorizes live execution.
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
from src.app.hammer_radar.operator.capture_count_sync_8m_short import (
    DEFAULT_LATEST_CAPTURES,
    DEFAULT_LATEST_HEARTBEATS,
    DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    build_safe_watcher_restart_commands,
    count_unique_fresh_captures,
    load_capture_count_sync_records,
    load_short_capture_heartbeats,
    load_short_capture_records as _load_short_capture_records_for_lane,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_harvester_expansion import (
    HEARTBEAT_LEDGER_FILENAME as FULL_SPECTRUM_HEARTBEAT_LEDGER_FILENAME,
    LEDGER_FILENAME as FULL_SPECTRUM_LEDGER_FILENAME,
    build_full_spectrum_harvester_commands,
    build_full_spectrum_lane_candidates,
    full_spectrum_harvester_heartbeats_path,
    load_full_spectrum_harvester_records as _load_full_spectrum_harvester_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import (
    HEARTBEAT_LEDGER_FILENAME as SHORT_CAPTURE_HEARTBEAT_LEDGER_FILENAME,
    LEDGER_FILENAME as SHORT_CAPTURE_LEDGER_FILENAME,
)
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY, MIN_FRESH_CANDIDATES

CAPTURE_THRESHOLD_RECOVERY_READY = "CAPTURE_THRESHOLD_RECOVERY_READY"
CAPTURE_THRESHOLD_RECOVERY_REJECTED = "CAPTURE_THRESHOLD_RECOVERY_REJECTED"
CAPTURE_THRESHOLD_RECOVERY_RECORDED = "CAPTURE_THRESHOLD_RECOVERY_RECORDED"
CAPTURE_THRESHOLD_RECOVERY_BLOCKED = "CAPTURE_THRESHOLD_RECOVERY_BLOCKED"
CAPTURE_THRESHOLD_RECOVERY_ERROR = "CAPTURE_THRESHOLD_RECOVERY_ERROR"

HARVESTER_RUNNING_RECENT_HEARTBEAT = "HARVESTER_RUNNING_RECENT_HEARTBEAT"
HARVESTER_STALE = "HARVESTER_STALE"
HARVESTER_NOT_FOUND = "HARVESTER_NOT_FOUND"
HEARTBEATS_FOUND_BUT_NO_CAPTURES = "HEARTBEATS_FOUND_BUT_NO_CAPTURES"
CAPTURES_FOUND_BUT_COUNT_STALE = "CAPTURES_FOUND_BUT_COUNT_STALE"
COUNT_SYNC_MISMATCH = "COUNT_SYNC_MISMATCH"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

CAPTURE_THRESHOLD_MET = "CAPTURE_THRESHOLD_MET"
CAPTURE_THRESHOLD_NOT_MET = "CAPTURE_THRESHOLD_NOT_MET"
CAPTURE_COUNT_STALE = "CAPTURE_COUNT_STALE"
CAPTURE_COUNT_UNKNOWN = "CAPTURE_COUNT_UNKNOWN"
CAPTURE_LEDGER_MISMATCH = "CAPTURE_LEDGER_MISMATCH"
NO_FRESH_CANDIDATES_FOUND = "NO_FRESH_CANDIDATES_FOUND"

KEEP_FULL_SPECTRUM_HARVESTER_RUNNING = "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"
RESTART_FULL_SPECTRUM_HARVESTER = "RESTART_FULL_SPECTRUM_HARVESTER"
RUN_CAPTURE_COUNT_RECHECK = "RUN_CAPTURE_COUNT_RECHECK"
RUN_R207_EVENT_LEVEL_CONFLUENCE_MATCHER = "RUN_R207_EVENT_LEVEL_CONFLUENCE_MATCHER"

EVENT_TYPE = "CAPTURE_THRESHOLD_RECOVERY_8M_SHORT"
LEDGER_FILENAME = "capture_threshold_recovery_8m_short.ndjson"
CONFIRM_CAPTURE_THRESHOLD_RECOVERY_RECORDING_PHRASE = (
    "I CONFIRM CAPTURE THRESHOLD RECOVERY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_FULL_SPECTRUM_RECORDS = 5000
DEFAULT_LATEST_FULL_SPECTRUM_HEARTBEATS = 1000

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
    "capture_recovery_live_authorized": False,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/capture_count_sync_8m_short.py",
    "src/app/hammer_radar/operator/capture_watcher_supervisor_8m_short.py",
    "src/app/hammer_radar/operator/full_spectrum_harvester_expansion.py",
    "src/app/hammer_radar/operator/tiny_live_readiness_gap_recheck.py",
    "src/app/hammer_radar/operator/multi_lane_paper_capture_harvester.py",
    f"logs/hammer_radar_forward/{FULL_SPECTRUM_HEARTBEAT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{FULL_SPECTRUM_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_HEARTBEAT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_capture_threshold_recovery_8m_short(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    record_recovery: bool = False,
    confirm_capture_threshold_recovery: str | None = None,
    latest_full_spectrum_records: int = DEFAULT_LATEST_FULL_SPECTRUM_RECORDS,
    latest_full_spectrum_heartbeats: int = DEFAULT_LATEST_FULL_SPECTRUM_HEARTBEATS,
    latest_short_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_short_heartbeats: int = DEFAULT_LATEST_HEARTBEATS,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    return build_capture_threshold_recovery_status(
        log_dir=log_dir,
        lane_key=lane_key,
        record_recovery=record_recovery,
        confirm_capture_threshold_recovery=confirm_capture_threshold_recovery,
        latest_full_spectrum_records=latest_full_spectrum_records,
        latest_full_spectrum_heartbeats=latest_full_spectrum_heartbeats,
        latest_short_captures=latest_short_captures,
        latest_short_heartbeats=latest_short_heartbeats,
        stale_after_seconds=stale_after_seconds,
        config_path=config_path,
        now=now,
    )


def build_capture_threshold_recovery_status(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    record_recovery: bool = False,
    confirm_capture_threshold_recovery: str | None = None,
    latest_full_spectrum_records: int = DEFAULT_LATEST_FULL_SPECTRUM_RECORDS,
    latest_full_spectrum_heartbeats: int = DEFAULT_LATEST_FULL_SPECTRUM_HEARTBEATS,
    latest_short_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_short_heartbeats: int = DEFAULT_LATEST_HEARTBEATS,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_capture_threshold_recovery == CONFIRM_CAPTURE_THRESHOLD_RECOVERY_RECORDING_PHRASE
    try:
        full_heartbeats = load_latest_full_spectrum_harvester_heartbeats(
            log_dir=resolved_log_dir,
            limit=latest_full_spectrum_heartbeats,
        )
        full_records = load_latest_full_spectrum_harvester_records(log_dir=resolved_log_dir, limit=latest_full_spectrum_records)
        short_records = load_short_capture_records(log_dir=resolved_log_dir, lane_key=lane_key, limit=latest_short_captures)
        short_heartbeats = load_short_capture_heartbeats(log_dir=resolved_log_dir, lane_key=lane_key, limit=latest_short_heartbeats)
        count_sync_records = load_capture_count_sync_records(log_dir=resolved_log_dir, limit=50)
        primary_count = recompute_8m_short_fresh_capture_count(
            short_capture_records=short_records,
            full_spectrum_records=full_records,
            lane_key=lane_key,
        )
        full_counts = recompute_full_spectrum_capture_counts(
            full_spectrum_records=full_records,
            log_dir=resolved_log_dir,
            config_path=config_path,
        )
        mismatch = detect_capture_count_mismatch(
            lane_key=lane_key,
            short_capture_records=short_records,
            full_spectrum_records=full_records,
            capture_count_sync_records=count_sync_records,
            recomputed_count=primary_count,
            log_dir=resolved_log_dir,
        )
        runtime = detect_harvester_runtime_status_from_ledgers(
            full_spectrum_heartbeats=full_heartbeats,
            full_spectrum_records=full_records,
            short_capture_heartbeats=short_heartbeats,
            mismatch_report=mismatch,
            now=generated_at,
            stale_after_seconds=stale_after_seconds,
        )
        threshold_status = _classify_threshold_status(primary_count, runtime, mismatch)
        status = CAPTURE_THRESHOLD_RECOVERY_READY
        if threshold_status != CAPTURE_THRESHOLD_MET:
            status = CAPTURE_THRESHOLD_RECOVERY_BLOCKED
        if record_recovery and not confirmation_valid:
            status = CAPTURE_THRESHOLD_RECOVERY_REJECTED
        elif record_recovery and confirmation_valid:
            status = CAPTURE_THRESHOLD_RECOVERY_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "recovery_recorded": False,
            "recovery_id": None,
            "record_recovery_requested": bool(record_recovery),
            "confirmation_valid": bool(confirmation_valid),
            "primary_lane": _lane_from_key(lane_key),
            "harvester_runtime_status": runtime,
            "capture_count_recompute": primary_count,
            "full_spectrum_capture_counts": full_counts,
            "capture_count_mismatch_report": mismatch,
            "threshold_status": threshold_status,
            "recovery_actions": build_capture_threshold_recovery_actions(
                threshold_status=threshold_status,
                harvester_runtime_status=runtime,
                capture_count_recompute=primary_count,
                mismatch_report=mismatch,
            ),
            "safe_operator_commands": build_safe_operator_harvester_commands(),
            "recommended_next_operator_move": _recommended_next_operator_move(
                threshold_status=threshold_status,
                harvester_runtime_status=runtime,
                mismatch_report=mismatch,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(
                threshold_status=threshold_status,
                mismatch_report=mismatch,
            ),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_recovery and confirmation_valid:
            record = append_capture_threshold_recovery_record(payload, log_dir=resolved_log_dir)
            payload["recovery_recorded"] = True
            payload["recovery_id"] = record["recovery_id"]
            payload["ledger_path"] = str(capture_threshold_recovery_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": CAPTURE_THRESHOLD_RECOVERY_ERROR,
                "generated_at": generated_at.isoformat(),
                "recovery_recorded": False,
                "recovery_id": None,
                "record_recovery_requested": bool(record_recovery),
                "confirmation_valid": bool(confirmation_valid),
                "primary_lane": _lane_from_key(lane_key),
                "harvester_runtime_status": _empty_runtime_status(),
                "capture_count_recompute": _empty_capture_count(),
                "full_spectrum_capture_counts": _empty_full_spectrum_counts(),
                "capture_count_mismatch_report": _empty_mismatch_report(mismatch_found=True),
                "threshold_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recovery_actions": [
                    {
                        "priority": "HIGH",
                        "action": "Fix R208 capture threshold recovery builder error and rerun preview only.",
                        "why": exc.__class__.__name__,
                        "operator_command_safe": False,
                    }
                ],
                "safe_operator_commands": build_safe_operator_harvester_commands(),
                "recommended_next_operator_move": RUN_CAPTURE_COUNT_RECHECK,
                "recommended_next_engineering_move": "Fix R208 local ledger reconciliation before any readiness interpretation.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_full_spectrum_harvester_heartbeats(
    *,
    log_dir: str | Path | None = None,
    limit: int = DEFAULT_LATEST_FULL_SPECTRUM_HEARTBEATS,
) -> list[dict[str, Any]]:
    path = full_spectrum_harvester_heartbeats_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=max(0, int(limit)), max_bytes=16_777_216)]


def load_latest_full_spectrum_harvester_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = DEFAULT_LATEST_FULL_SPECTRUM_RECORDS,
) -> list[dict[str, Any]]:
    return _load_full_spectrum_harvester_records(log_dir=log_dir, limit=max(0, int(limit)))


def load_short_capture_records(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    limit: int = DEFAULT_LATEST_CAPTURES,
) -> list[dict[str, Any]]:
    return _load_short_capture_records_for_lane(log_dir=log_dir, lane_key=lane_key, limit=max(0, int(limit)))


def recompute_8m_short_fresh_capture_count(
    *,
    short_capture_records: list[Mapping[str, Any]],
    full_spectrum_records: list[Mapping[str, Any]],
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    required_fresh_capture_count: int = MIN_FRESH_CANDIDATES,
) -> dict[str, Any]:
    short_count = count_unique_fresh_captures(list(short_capture_records), required_count=required_fresh_capture_count)
    ids = list(short_count.get("unique_captured_signal_ids") or [])
    latest_at = _latest_capture_at(short_capture_records, full_spectrum_records, lane_key=lane_key, ids=ids)
    latest_signal_id = ids[0] if ids else None
    return {
        "fresh_capture_count": len(ids),
        "required_fresh_capture_count": int(required_fresh_capture_count),
        "threshold_met": len(ids) >= int(required_fresh_capture_count),
        "unique_captured_signal_ids": ids,
        "latest_captured_signal_id": latest_signal_id,
        "latest_capture_at": latest_at,
        "source_ledgers_used": [
            f"logs/hammer_radar_forward/{SHORT_CAPTURE_LEDGER_FILENAME}",
            f"logs/hammer_radar_forward/{FULL_SPECTRUM_LEDGER_FILENAME}",
            "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson",
        ],
    }


def recompute_full_spectrum_capture_counts(
    *,
    full_spectrum_records: list[Mapping[str, Any]],
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    required_fresh_capture_count: int = MIN_FRESH_CANDIDATES,
) -> dict[str, Any]:
    scope = build_full_spectrum_lane_candidates(log_dir=log_dir, config_path=config_path)
    lanes = [
        *scope.get("configured_paper_lanes", []),
        *scope.get("discovered_unconfigured_paper_lanes", []),
        *scope.get("tiny_live_reference_lanes", []),
    ]
    ids_by_lane: dict[str, list[str]] = {str(lane.get("lane_key")): [] for lane in lanes if lane.get("lane_key")}
    stale_by_lane: Counter[str] = Counter()
    for record in full_spectrum_records:
        for candidate in _captured_candidates(record):
            lane = str(candidate.get("lane_key") or "")
            signal_id = str(candidate.get("signal_id") or candidate.get("candidate_id") or "").strip()
            if lane not in ids_by_lane:
                ids_by_lane[lane] = []
            if signal_id and signal_id not in ids_by_lane[lane]:
                ids_by_lane[lane].append(signal_id)
        for lane, count in dict((record.get("capture_summary") or {}).get("stale_by_lane") or {}).items():
            stale_by_lane[str(lane)] += _int_value(count)
    rows = [
        {
            "lane_key": lane,
            "fresh_capture_count": len(ids),
            "required_fresh_capture_count": int(required_fresh_capture_count),
            "threshold_met": len(ids) >= int(required_fresh_capture_count),
            "unique_captured_signal_ids": ids,
            "latest_captured_signal_id": ids[0] if ids else None,
        }
        for lane, ids in sorted(ids_by_lane.items())
    ]
    rows = sorted(rows, key=lambda row: (-int(row["fresh_capture_count"]), str(row["lane_key"])))
    fresh_lanes = [row["lane_key"] for row in rows if int(row["fresh_capture_count"]) > 0]
    stale_only = sorted([lane for lane, count in stale_by_lane.items() if count > 0 and lane not in set(fresh_lanes)])
    return {
        "lanes_in_scope": len(ids_by_lane),
        "lanes_with_fresh_captures": fresh_lanes,
        "lanes_with_stale_only": stale_only,
        "top_capture_counts": rows[:20],
    }


def detect_harvester_runtime_status_from_ledgers(
    *,
    full_spectrum_heartbeats: list[Mapping[str, Any]],
    full_spectrum_records: list[Mapping[str, Any]],
    short_capture_heartbeats: list[Mapping[str, Any]],
    mismatch_report: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    latest_full = full_spectrum_heartbeats[0] if full_spectrum_heartbeats else {}
    latest_short = short_capture_heartbeats[0] if short_capture_heartbeats else {}
    full_age = _age_seconds(latest_full.get("generated_at"), generated_at) if latest_full else None
    short_age = _age_seconds(latest_short.get("generated_at"), generated_at) if latest_short else None
    full_stale = bool(latest_full) and (full_age is None or full_age > int(stale_after_seconds))
    short_stale = bool(latest_short) and (short_age is None or short_age > int(stale_after_seconds))
    captures_found = any(_captured_candidates(record) for record in full_spectrum_records)
    mismatch_found = bool((mismatch_report or {}).get("mismatch_found"))
    if mismatch_found:
        watcher_status = COUNT_SYNC_MISMATCH
    elif latest_full and not full_stale:
        watcher_status = HARVESTER_RUNNING_RECENT_HEARTBEAT if captures_found else HEARTBEATS_FOUND_BUT_NO_CAPTURES
    elif latest_full:
        watcher_status = HARVESTER_STALE
    elif captures_found:
        watcher_status = CAPTURES_FOUND_BUT_COUNT_STALE
    else:
        watcher_status = HARVESTER_NOT_FOUND
    return _sanitize(
        {
            "full_spectrum_heartbeat_found": bool(latest_full),
            "latest_full_spectrum_heartbeat_at": latest_full.get("generated_at") if latest_full else None,
            "latest_full_spectrum_iteration": latest_full.get("iteration") if latest_full else None,
            "full_spectrum_watcher_likely_running": bool(latest_full) and not full_stale,
            "full_spectrum_watcher_stale": bool(full_stale),
            "short_capture_heartbeat_found": bool(latest_short),
            "latest_short_capture_heartbeat_at": latest_short.get("generated_at") if latest_short else None,
            "short_capture_watcher_likely_running": bool(latest_short) and not short_stale,
            "short_capture_watcher_stale": bool(short_stale),
            "watcher_status": watcher_status,
        }
    )


def detect_capture_count_mismatch(
    *,
    lane_key: str,
    short_capture_records: list[Mapping[str, Any]],
    full_spectrum_records: list[Mapping[str, Any]],
    capture_count_sync_records: list[Mapping[str, Any]],
    recomputed_count: Mapping[str, Any],
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    short_ids = set(str(item) for item in recomputed_count.get("unique_captured_signal_ids") or [])
    full_ids = {
        str(candidate.get("signal_id") or candidate.get("candidate_id") or "").strip()
        for record in full_spectrum_records
        for candidate in _captured_candidates(record)
        if str(candidate.get("lane_key") or "") == lane_key
    }
    full_ids.discard("")
    latest_sync = capture_count_sync_records[0] if capture_count_sync_records else {}
    sync_count = dict(latest_sync.get("capture_count") or {})
    sync_ids = {str(item) for item in sync_count.get("unique_captured_signal_ids") or []}
    harvester_not_counted = sorted(full_ids - short_ids)
    counted_not_harvester = sorted(short_ids - full_ids) if full_ids else []
    if sync_ids:
        harvester_not_counted = sorted(set(harvester_not_counted) | (full_ids - sync_ids))
        counted_not_harvester = sorted(set(counted_not_harvester) | (sync_ids - full_ids if full_ids else set()))
    lane_mismatches = _lane_key_mismatches(full_spectrum_records, short_capture_records, expected_lane_key=lane_key)
    warnings: list[str] = []
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    if short_ids or full_ids or sync_ids:
        for filename in (
            FULL_SPECTRUM_LEDGER_FILENAME,
            SHORT_CAPTURE_LEDGER_FILENAME,
            "capture_count_sync_8m_short.ndjson",
        ):
            if not (resolved_log_dir / filename).exists():
                warnings.append(f"missing:{resolved_log_dir / filename}")
    if latest_sync and _int_value(sync_count.get("fresh_capture_count")) != _int_value(recomputed_count.get("fresh_capture_count")):
        warnings.append("latest_capture_count_sync_count_differs_from_recomputed_short_capture_count")
    mismatch_found = bool(harvester_not_counted or counted_not_harvester or lane_mismatches or warnings)
    return {
        "mismatch_found": mismatch_found,
        "harvester_captures_not_counted": harvester_not_counted,
        "counted_captures_not_in_harvester": counted_not_harvester,
        "lane_key_mismatches": lane_mismatches,
        "ledger_path_warnings": warnings,
    }


def build_capture_threshold_recovery_actions(
    *,
    threshold_status: str,
    harvester_runtime_status: Mapping[str, Any],
    capture_count_recompute: Mapping[str, Any],
    mismatch_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if mismatch_report.get("mismatch_found"):
        actions.append(
            {
                "priority": "HIGH",
                "action": "Run capture-count sync preview and inspect ledger path warnings before trusting the 8m short count.",
                "why": "R208 found local ledger mismatch or missing count-sync evidence.",
                "operator_command_safe": True,
            }
        )
    if harvester_runtime_status.get("full_spectrum_watcher_stale") or not harvester_runtime_status.get("full_spectrum_heartbeat_found"):
        actions.append(
            {
                "priority": "HIGH",
                "action": "Check tmux and restart the R198 full-spectrum harvester if no current session is present.",
                "why": "Recent full-spectrum heartbeat evidence is missing or stale.",
                "operator_command_safe": True,
            }
        )
    if threshold_status == CAPTURE_THRESHOLD_MET:
        actions.append(
            {
                "priority": "MEDIUM",
                "action": "Run the next local evidence readiness/confluence review; do not infer live readiness from capture count alone.",
                "why": "The local short capture count meets 10/10, but funding, lane mode, approval, kill switch, and risk contract gates remain separate.",
                "operator_command_safe": True,
            }
        )
    elif not actions:
        actions.append(
            {
                "priority": "MEDIUM",
                "action": "Keep the R198 full-spectrum harvester running and rerun this recovery preview after more paper captures.",
                "why": f"Fresh capture count is {capture_count_recompute.get('fresh_capture_count')}/{capture_count_recompute.get('required_fresh_capture_count')}.",
                "operator_command_safe": True,
            }
        )
    return actions


def build_safe_operator_harvester_commands() -> dict[str, str]:
    full = build_full_spectrum_harvester_commands()
    watcher = build_safe_watcher_restart_commands()
    return {
        "tmux_status_check": "tmux has-session -t r198-full-spectrum-harvest && tmux capture-pane -pt r198-full-spectrum-harvest -S -20",
        "heartbeat_tail": f"tail -n 20 logs/hammer_radar_forward/{FULL_SPECTRUM_HEARTBEAT_LEDGER_FILENAME}",
        "full_spectrum_harvester_restart": (
            "tmux new-session -d -s r198-full-spectrum-harvest "
            f"'{full['bounded_loop_command']}'"
        ),
        "capture_count_recheck": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward capture-count-sync-8m-short"
        ),
        "short_capture_watcher_status_check": watcher["check_command"],
    }


def append_capture_threshold_recovery_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = capture_threshold_recovery_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            **dict(record),
            "event_type": EVENT_TYPE,
            "recovery_id": str(record.get("recovery_id") or f"r208_capture_threshold_recovery_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "recovery_recorded": True,
            "safety": dict(SAFETY),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_capture_threshold_recovery_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = capture_threshold_recovery_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_capture_threshold_recovery_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "last_recovery_id": records[0].get("recovery_id") if records else None,
        "last_threshold_status": records[0].get("threshold_status") if records else None,
        "safety": dict(SAFETY),
    }


def capture_threshold_recovery_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_capture_threshold_recovery_8m_short_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _classify_threshold_status(
    capture_count: Mapping[str, Any],
    runtime: Mapping[str, Any],
    mismatch: Mapping[str, Any],
) -> str:
    if mismatch.get("mismatch_found"):
        return CAPTURE_LEDGER_MISMATCH
    if capture_count.get("threshold_met"):
        return CAPTURE_THRESHOLD_MET
    if not capture_count.get("latest_capture_at") and runtime.get("watcher_status") == HEARTBEATS_FOUND_BUT_NO_CAPTURES:
        return NO_FRESH_CANDIDATES_FOUND
    if runtime.get("watcher_status") in {HARVESTER_STALE, HARVESTER_NOT_FOUND, CAPTURES_FOUND_BUT_COUNT_STALE}:
        return CAPTURE_COUNT_STALE
    if int(capture_count.get("fresh_capture_count") or 0) >= 0:
        return CAPTURE_THRESHOLD_NOT_MET
    return CAPTURE_COUNT_UNKNOWN


def _recommended_next_operator_move(
    *,
    threshold_status: str,
    harvester_runtime_status: Mapping[str, Any],
    mismatch_report: Mapping[str, Any],
) -> str:
    if mismatch_report.get("mismatch_found"):
        return RUN_CAPTURE_COUNT_RECHECK
    if threshold_status == CAPTURE_THRESHOLD_MET:
        return RUN_R207_EVENT_LEVEL_CONFLUENCE_MATCHER
    if harvester_runtime_status.get("full_spectrum_watcher_stale") or not harvester_runtime_status.get("full_spectrum_heartbeat_found"):
        return RESTART_FULL_SPECTRUM_HARVESTER
    return KEEP_FULL_SPECTRUM_HARVESTER_RUNNING


def _recommended_next_engineering_move(*, threshold_status: str, mismatch_report: Mapping[str, Any]) -> str:
    if mismatch_report.get("mismatch_found"):
        return "Reconcile R198 harvester records with R176 capture-count sync paths/lane keys before trusting tiny-live blocker counts."
    if threshold_status == CAPTURE_THRESHOLD_MET:
        return "Run R207 event-level confluence matching as local paper analysis only; capture recovery does not authorize live execution."
    return "Keep R198 running, rerun R208 and R176 previews, and only proceed when local paper evidence reaches 10/10 without ledger mismatch."


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


def _captured_candidates(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates = record.get("captured_candidates") or (record.get("capture_summary") or {}).get("captured_candidates") or []
    return [dict(candidate) for candidate in candidates if isinstance(candidate, Mapping)]


def _latest_capture_at(
    short_records: list[Mapping[str, Any]],
    full_records: list[Mapping[str, Any]],
    *,
    lane_key: str,
    ids: list[str],
) -> str | None:
    wanted = set(ids)
    candidates: list[datetime] = []
    for record in short_records:
        if str(record.get("captured_signal_id") or "") in wanted:
            parsed = _parse_datetime(record.get("generated_at") or record.get("recorded_at_utc"))
            if parsed:
                candidates.append(parsed)
    for record in full_records:
        for candidate in _captured_candidates(record):
            signal_id = str(candidate.get("signal_id") or candidate.get("candidate_id") or "")
            if str(candidate.get("lane_key") or "") == lane_key and signal_id in wanted:
                parsed = _parse_datetime(candidate.get("timestamp") or record.get("generated_at") or record.get("recorded_at_utc"))
                if parsed:
                    candidates.append(parsed)
    if not candidates:
        return None
    return max(candidates).isoformat()


def _lane_key_mismatches(
    full_records: list[Mapping[str, Any]],
    short_records: list[Mapping[str, Any]],
    *,
    expected_lane_key: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in short_records:
        lane_key = str(record.get("captured_lane_key") or (record.get("target_lane") or {}).get("lane_key") or "")
        if record.get("paper_evidence_captured") is True and lane_key and lane_key != expected_lane_key:
            rows.append({"source": SHORT_CAPTURE_LEDGER_FILENAME, "signal_id": record.get("captured_signal_id"), "lane_key": lane_key})
    for record in full_records:
        for candidate in _captured_candidates(record):
            lane_key = str(candidate.get("lane_key") or "")
            if lane_key and _same_primary_shape(lane_key, expected_lane_key) and lane_key != expected_lane_key:
                rows.append(
                    {
                        "source": FULL_SPECTRUM_LEDGER_FILENAME,
                        "signal_id": candidate.get("signal_id") or candidate.get("candidate_id"),
                        "lane_key": lane_key,
                    }
                )
    return rows[:50]


def _same_primary_shape(lane_key: str, expected_lane_key: str) -> bool:
    lane = _lane_from_key(lane_key)
    expected = _lane_from_key(expected_lane_key)
    return lane["symbol"] == expected["symbol"] and lane["timeframe"] == expected["timeframe"] and lane["direction"] == expected["direction"]


def _lane_from_key(lane_key: str) -> dict[str, Any]:
    parts = str(lane_key or "").split("|")
    return {
        "lane_key": lane_key,
        "symbol": parts[0] if len(parts) > 0 else "",
        "timeframe": parts[1] if len(parts) > 1 else "",
        "direction": parts[2] if len(parts) > 2 else "",
        "entry_mode": parts[3] if len(parts) > 3 else "",
    }


def _age_seconds(value: Any, now: datetime) -> float | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return (now - parsed).total_seconds()


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _empty_capture_count() -> dict[str, Any]:
    return {
        "fresh_capture_count": 0,
        "required_fresh_capture_count": int(MIN_FRESH_CANDIDATES),
        "threshold_met": False,
        "unique_captured_signal_ids": [],
        "latest_captured_signal_id": None,
        "latest_capture_at": None,
        "source_ledgers_used": [],
    }


def _empty_runtime_status() -> dict[str, Any]:
    return {
        "full_spectrum_heartbeat_found": False,
        "latest_full_spectrum_heartbeat_at": None,
        "latest_full_spectrum_iteration": None,
        "full_spectrum_watcher_likely_running": False,
        "full_spectrum_watcher_stale": False,
        "short_capture_heartbeat_found": False,
        "latest_short_capture_heartbeat_at": None,
        "short_capture_watcher_likely_running": False,
        "short_capture_watcher_stale": False,
        "watcher_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
    }


def _empty_full_spectrum_counts() -> dict[str, Any]:
    return {
        "lanes_in_scope": 0,
        "lanes_with_fresh_captures": [],
        "lanes_with_stale_only": [],
        "top_capture_counts": [],
    }


def _empty_mismatch_report(*, mismatch_found: bool = False) -> dict[str, Any]:
    return {
        "mismatch_found": bool(mismatch_found),
        "harvester_captures_not_counted": [],
        "counted_captures_not_in_harvester": [],
        "lane_key_mismatches": [],
        "ledger_path_warnings": [],
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
