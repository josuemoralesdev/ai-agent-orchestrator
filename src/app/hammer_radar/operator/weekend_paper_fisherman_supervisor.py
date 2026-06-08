"""R208A weekend paper fisherman supervisor.

This module supervises local paper-fishing ledgers only. It never calls
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
    load_capture_count_sync_records as _load_capture_count_sync_records,
    load_short_capture_heartbeats as _load_short_capture_heartbeats,
    load_short_capture_records as _load_short_capture_records,
)
from src.app.hammer_radar.operator.capture_threshold_recovery_8m_short import (
    DEFAULT_LATEST_FULL_SPECTRUM_HEARTBEATS,
    DEFAULT_LATEST_FULL_SPECTRUM_RECORDS,
    detect_capture_count_mismatch,
    recompute_8m_short_fresh_capture_count,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.fisherman_watchdog_ledger_reconciliation import (
    load_fisherman_reconciliation_records,
)
from src.app.hammer_radar.operator.full_spectrum_harvester_expansion import (
    FULL_SPECTRUM_HARVEST_CAPTURED,
    FULL_SPECTRUM_HARVEST_EXITED,
    HEARTBEAT_LEDGER_FILENAME as FULL_SPECTRUM_HEARTBEAT_LEDGER_FILENAME,
    LEDGER_FILENAME as FULL_SPECTRUM_LEDGER_FILENAME,
    build_full_spectrum_harvester_commands,
    full_spectrum_harvester_heartbeats_path,
    load_full_spectrum_harvester_records as _load_full_spectrum_harvester_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import (
    HEARTBEAT_LEDGER_FILENAME as SHORT_CAPTURE_HEARTBEAT_LEDGER_FILENAME,
    LEDGER_FILENAME as SHORT_CAPTURE_LEDGER_FILENAME,
    SHORT_PAPER_CAPTURE_EXITED,
)
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY, MIN_FRESH_CANDIDATES

WEEKEND_PAPER_FISHERMAN_SUPERVISOR_READY = "WEEKEND_PAPER_FISHERMAN_SUPERVISOR_READY"
WEEKEND_PAPER_FISHERMAN_SUPERVISOR_REJECTED = "WEEKEND_PAPER_FISHERMAN_SUPERVISOR_REJECTED"
WEEKEND_PAPER_FISHERMAN_SUPERVISOR_RECORDED = "WEEKEND_PAPER_FISHERMAN_SUPERVISOR_RECORDED"
WEEKEND_PAPER_FISHERMAN_SUPERVISOR_BLOCKED = "WEEKEND_PAPER_FISHERMAN_SUPERVISOR_BLOCKED"
WEEKEND_PAPER_FISHERMAN_SUPERVISOR_ERROR = "WEEKEND_PAPER_FISHERMAN_SUPERVISOR_ERROR"

FISHERMAN_RUNNING_RECENT = "FISHERMAN_RUNNING_RECENT"
FISHERMAN_STALE = "FISHERMAN_STALE"
FISHERMAN_EXITED_AFTER_CAPTURE = "FISHERMAN_EXITED_AFTER_CAPTURE"
FISHERMAN_NOT_RUNNING = "FISHERMAN_NOT_RUNNING"
NO_SIGNAL_BUT_FISHERMAN_RUNNING = "NO_SIGNAL_BUT_FISHERMAN_RUNNING"
SIGNAL_CAPTURED_AND_FISHERMAN_EXITED = "SIGNAL_CAPTURED_AND_FISHERMAN_EXITED"
LEDGER_MISMATCH_REQUIRES_RECONCILIATION = "LEDGER_MISMATCH_REQUIRES_RECONCILIATION"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"
UNKNOWN = "UNKNOWN"

RESTART_FULL_SPECTRUM_HARVESTER_24H = "RESTART_FULL_SPECTRUM_HARVESTER_24H"
KEEP_FISHERMAN_RUNNING = "KEEP_FISHERMAN_RUNNING"
RUN_CAPTURE_COUNT_RECHECK = "RUN_CAPTURE_COUNT_RECHECK"
RUN_R209_BETRAYAL_INTEGRATION_RECHECK = "RUN_R209_BETRAYAL_INTEGRATION_RECHECK"

EVENT_TYPE = "WEEKEND_PAPER_FISHERMAN_SUPERVISOR"
LEDGER_FILENAME = "weekend_paper_fisherman_supervisor.ndjson"
CONFIRM_WEEKEND_PAPER_FISHERMAN_SUPERVISOR_RECORDING_PHRASE = (
    "I CONFIRM WEEKEND PAPER FISHERMAN SUPERVISOR RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_STALE_AFTER_SECONDS = DEFAULT_WATCHER_STALE_AFTER_SECONDS
DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT = MIN_FRESH_CANDIDATES
DEFAULT_WEEKEND_LOOP_ITERATIONS = 1440
DEFAULT_WEEKEND_LOOP_SLEEP_SECONDS = 60

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
    "weekend_supervisor_live_authorized": False,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/capture_threshold_recovery_8m_short.py",
    "src/app/hammer_radar/operator/full_spectrum_harvester_expansion.py",
    "src/app/hammer_radar/operator/capture_count_sync_8m_short.py",
    "src/app/hammer_radar/operator/capture_watcher_supervisor_8m_short.py",
    "src/app/hammer_radar/operator/tiny_live_readiness_gap_recheck.py",
    "src/app/hammer_radar/operator/betrayal_strategy_audit.py",
    "src/app/hammer_radar/operator/betrayal_inverse_validation.py",
    f"logs/hammer_radar_forward/{FULL_SPECTRUM_HEARTBEAT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{FULL_SPECTRUM_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_HEARTBEAT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_weekend_paper_fisherman_supervisor(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    record_supervisor: bool = False,
    confirm_weekend_fisherman_supervisor: str | None = None,
    latest_full_spectrum_records: int = DEFAULT_LATEST_FULL_SPECTRUM_RECORDS,
    latest_full_spectrum_heartbeats: int = DEFAULT_LATEST_FULL_SPECTRUM_HEARTBEATS,
    latest_short_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_short_heartbeats: int = DEFAULT_LATEST_HEARTBEATS,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_weekend_fisherman_supervisor
        == CONFIRM_WEEKEND_PAPER_FISHERMAN_SUPERVISOR_RECORDING_PHRASE
    )
    try:
        full_heartbeats = load_latest_full_spectrum_heartbeats(
            log_dir=resolved_log_dir,
            limit=latest_full_spectrum_heartbeats,
        )
        full_records = load_latest_full_spectrum_harvest_records(
            log_dir=resolved_log_dir,
            limit=latest_full_spectrum_records,
        )
        short_heartbeats = load_latest_short_capture_heartbeats(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            limit=latest_short_heartbeats,
        )
        short_records = load_latest_short_capture_records(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            limit=latest_short_captures,
        )
        sync_status = load_capture_count_sync_status(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            short_capture_records=short_records,
            full_spectrum_records=full_records,
        )
        exit_after_capture = detect_harvester_exit_after_capture(
            full_spectrum_heartbeats=full_heartbeats,
            full_spectrum_records=full_records,
        )
        fisherman_health = detect_fisherman_process_health_from_ledgers(
            full_spectrum_heartbeats=full_heartbeats,
            short_capture_heartbeats=short_heartbeats,
            ledger_mismatch_found=bool(sync_status.get("ledger_mismatch_found")),
            harvester_exited_after_capture=bool(exit_after_capture.get("harvester_exited_after_capture")),
            now=generated_at,
            stale_after_seconds=stale_after_seconds,
        )
        capture_summary = build_weekend_capture_watch_summary(
            lane_key=lane_key,
            short_capture_records=short_records,
            full_spectrum_records=full_records,
            capture_count_sync_status=sync_status,
            harvester_exit_status=exit_after_capture,
        )
        betrayal_summary = build_betrayal_watch_summary(
            betrayal_context=load_betrayal_inverse_context(log_dir=resolved_log_dir),
            full_spectrum_records=full_records,
            full_spectrum_heartbeats=full_heartbeats,
        )
        no_signal = detect_no_signal_vs_no_fisherman(
            fisherman_health=fisherman_health,
            capture_watch_summary=capture_summary,
        )
        actions = build_weekend_supervisor_actions(
            fisherman_health=fisherman_health,
            capture_watch_summary=capture_summary,
            betrayal_watch_summary=betrayal_summary,
        )
        status = _top_level_status(
            record_supervisor=record_supervisor,
            confirmation_valid=confirmation_valid,
            fisherman_health=fisherman_health,
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "supervisor_recorded": False,
            "supervisor_id": None,
            "record_supervisor_requested": bool(record_supervisor),
            "confirmation_valid": bool(confirmation_valid),
            "weekend_policy": _weekend_policy(),
            "fisherman_health": fisherman_health,
            "capture_watch_summary": capture_summary,
            "betrayal_watch_summary": betrayal_summary,
            "no_signal_vs_no_fisherman": no_signal,
            "weekend_supervisor_actions": actions,
            "safe_weekend_operator_commands": build_safe_weekend_operator_commands(),
            "recommended_next_operator_move": _recommended_next_operator_move(
                fisherman_health=fisherman_health,
                capture_watch_summary=capture_summary,
                betrayal_watch_summary=betrayal_summary,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(
                fisherman_health=fisherman_health,
                capture_watch_summary=capture_summary,
                betrayal_watch_summary=betrayal_summary,
            ),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_supervisor and confirmation_valid:
            record = append_weekend_paper_fisherman_supervisor_record(payload, log_dir=resolved_log_dir)
            payload["supervisor_recorded"] = True
            payload["supervisor_id"] = record["supervisor_id"]
            payload["ledger_path"] = str(weekend_paper_fisherman_supervisor_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": WEEKEND_PAPER_FISHERMAN_SUPERVISOR_ERROR,
                "generated_at": generated_at.isoformat(),
                "supervisor_recorded": False,
                "supervisor_id": None,
                "record_supervisor_requested": bool(record_supervisor),
                "confirmation_valid": bool(confirmation_valid),
                "weekend_policy": _weekend_policy(),
                "fisherman_health": _empty_fisherman_health(),
                "capture_watch_summary": _empty_capture_watch_summary(lane_key),
                "betrayal_watch_summary": build_betrayal_watch_summary(
                    betrayal_context=load_betrayal_inverse_context(log_dir=resolved_log_dir),
                    full_spectrum_records=[],
                    full_spectrum_heartbeats=[],
                ),
                "no_signal_vs_no_fisherman": {
                    "classification": UNKNOWN,
                    "plain_english": "Supervisor hit a local parsing/build error; inspect ledgers before acting.",
                },
                "weekend_supervisor_actions": [
                    {
                        "priority": "HIGH",
                        "action": "Fix the R208A local supervisor error and rerun preview.",
                        "why": exc.__class__.__name__,
                        "operator_command_safe": False,
                    }
                ],
                "safe_weekend_operator_commands": build_safe_weekend_operator_commands(),
                "recommended_next_operator_move": RUN_CAPTURE_COUNT_RECHECK,
                "recommended_next_engineering_move": "Fix R208A local supervisor error before weekend supervision decisions.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_full_spectrum_heartbeats(
    *,
    log_dir: str | Path | None = None,
    limit: int = DEFAULT_LATEST_FULL_SPECTRUM_HEARTBEATS,
) -> list[dict[str, Any]]:
    path = full_spectrum_harvester_heartbeats_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=max(0, int(limit)), max_bytes=16_777_216)]


def load_latest_full_spectrum_harvest_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = DEFAULT_LATEST_FULL_SPECTRUM_RECORDS,
) -> list[dict[str, Any]]:
    return _load_full_spectrum_harvester_records(log_dir=log_dir, limit=max(0, int(limit)))


def load_latest_short_capture_heartbeats(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    limit: int = DEFAULT_LATEST_HEARTBEATS,
) -> list[dict[str, Any]]:
    return _load_short_capture_heartbeats(log_dir=log_dir, lane_key=lane_key, limit=max(0, int(limit)))


def load_latest_short_capture_records(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    limit: int = DEFAULT_LATEST_CAPTURES,
) -> list[dict[str, Any]]:
    return _load_short_capture_records(log_dir=log_dir, lane_key=lane_key, limit=max(0, int(limit)))


def load_capture_count_sync_status(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    short_capture_records: list[Mapping[str, Any]] | None = None,
    full_spectrum_records: list[Mapping[str, Any]] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    short_records = list(short_capture_records or load_latest_short_capture_records(log_dir=resolved_log_dir, lane_key=lane_key))
    full_records = list(full_spectrum_records or load_latest_full_spectrum_harvest_records(log_dir=resolved_log_dir))
    count = recompute_8m_short_fresh_capture_count(
        short_capture_records=short_records,
        full_spectrum_records=full_records,
        lane_key=lane_key,
    )
    sync_records = _load_capture_count_sync_records(log_dir=resolved_log_dir, limit=limit)
    mismatch = detect_capture_count_mismatch(
        lane_key=lane_key,
        short_capture_records=short_records,
        full_spectrum_records=full_records,
        capture_count_sync_records=sync_records,
        recomputed_count=count,
        log_dir=resolved_log_dir,
    )
    path = resolved_log_dir / "capture_count_sync_8m_short.ndjson"
    warnings = list(mismatch.get("ledger_path_warnings") or [])
    if not path.exists() and (short_records or full_records):
        missing = f"missing:{path}"
        if missing not in warnings:
            warnings.append(missing)
    reconciliation_records = load_fisherman_reconciliation_records(log_dir=resolved_log_dir, limit=1)
    mismatch = _apply_r208b_reconciliation_to_mismatch(
        mismatch=mismatch,
        reconciliation_records=reconciliation_records,
        recomputed_count=count,
        warnings=warnings,
    )
    warnings = list(mismatch.get("ledger_path_warnings") or warnings)
    return {
        "latest_sync_found": bool(sync_records),
        "latest_sync_at": sync_records[0].get("generated_at") if sync_records else None,
        "latest_sync_status": sync_records[0].get("status") if sync_records else None,
        "capture_count": count,
        "ledger_mismatch_found": bool(mismatch.get("mismatch_found") or warnings),
        "ledger_path_warnings": warnings,
        "mismatch_report": {**dict(mismatch), "ledger_path_warnings": warnings, "mismatch_found": bool(mismatch.get("mismatch_found") or warnings)},
    }


def _apply_r208b_reconciliation_to_mismatch(
    *,
    mismatch: Mapping[str, Any],
    reconciliation_records: list[Mapping[str, Any]],
    recomputed_count: Mapping[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    report = dict(mismatch)
    if not reconciliation_records:
        return report
    latest = reconciliation_records[0]
    status = str(latest.get("reconciliation_status") or "")
    reconciled = dict(latest.get("reconciled_capture_count") or {})
    if not status.startswith("LEDGER_RECONCILED_"):
        return report
    if _int_value(reconciled.get("fresh_capture_count")) != _int_value(recomputed_count.get("fresh_capture_count")):
        return report
    if list(reconciled.get("unique_captured_signal_ids") or []) != list(recomputed_count.get("unique_captured_signal_ids") or []):
        return report
    if report.get("harvester_captures_not_counted") or report.get("lane_key_mismatches") or warnings:
        return report
    if report.get("counted_captures_not_in_harvester"):
        report["counted_captures_not_in_harvester"] = []
        report["r208b_reconciliation_applied"] = True
        report["latest_r208b_reconciliation_id"] = latest.get("reconciliation_id")
        report["mismatch_found"] = False
    return report


def load_betrayal_inverse_context(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    betrayal_records = _load_recent_optional(resolved_log_dir / "betrayal_shadow_outcomes.ndjson", limit=100)
    latest = betrayal_records[0] if betrayal_records else {}
    return {
        "source_docs": [
            "docs/hammer_radar/R80_BETRAYAL_STRATEGY_AUDIT.md",
            "docs/hammer_radar/R81_TRUE_INVERSE_PAPER_OUTCOME_VALIDATION.md",
            "docs/hammer_radar/R82_MARKOV_REGIME_GATE.md",
            "docs/hammer_radar/R83_MIRO_FISH_QUALITY_GATE.md",
            "docs/hammer_radar/R95_DUAL_LANE_CANDIDATE_WATCH_NORMAL_BETRAYAL.md",
            "docs/hammer_radar/R100_BETRAYAL_SOURCE_SIGNAL_EMITTER.md",
        ],
        "r80_primary_222m": {
            "candidate": "222m aggregate",
            "original_win_rate_pct": 12.5,
            "naive_inverse_win_rate_pct": 87.5,
            "classification": "BETRAYAL_PRIMARY_CANDIDATE",
        },
        "r80_watchlist_88m": {
            "candidate": "88m aggregate",
            "original_win_rate_pct": 36.67,
            "naive_inverse_win_rate_pct": 63.33,
            "classification": "BETRAYAL_WATCHLIST",
        },
        "latest_betrayal_shadow_record_found": bool(latest),
        "latest_betrayal_shadow_record_at": latest.get("created_at") or latest.get("generated_at") if latest else None,
        "latest_betrayal_shadow_timeframe": latest.get("timeframe") if latest else None,
        "true_inverse_validation_required": True,
        "betrayal_integrated_into_current_matrix": False,
        "betrayal_live_ready": False,
    }


def detect_fisherman_process_health_from_ledgers(
    *,
    full_spectrum_heartbeats: list[Mapping[str, Any]],
    short_capture_heartbeats: list[Mapping[str, Any]],
    ledger_mismatch_found: bool = False,
    harvester_exited_after_capture: bool = False,
    now: datetime | None = None,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    latest_full = full_spectrum_heartbeats[0] if full_spectrum_heartbeats else {}
    latest_short = short_capture_heartbeats[0] if short_capture_heartbeats else {}
    full_age = _age_seconds(latest_full.get("generated_at"), generated_at) if latest_full else None
    short_age = _age_seconds(latest_short.get("generated_at"), generated_at) if latest_short else None
    full_stale = bool(latest_full) and (full_age is None or full_age > int(stale_after_seconds))
    short_stale = bool(latest_short) and (short_age is None or short_age > int(stale_after_seconds))
    full_terminal = str(latest_full.get("status") or "") == FULL_SPECTRUM_HARVEST_EXITED
    short_terminal = str(latest_short.get("status") or "") == SHORT_PAPER_CAPTURE_EXITED
    full_running = bool(latest_full) and not full_stale and not full_terminal
    short_running = bool(latest_short) and not short_stale and not short_terminal
    if harvester_exited_after_capture:
        fisherman_status = SIGNAL_CAPTURED_AND_FISHERMAN_EXITED
    elif ledger_mismatch_found:
        fisherman_status = LEDGER_MISMATCH_REQUIRES_RECONCILIATION
    elif not latest_full and not latest_short:
        fisherman_status = FISHERMAN_NOT_RUNNING
    elif full_stale or short_stale:
        fisherman_status = FISHERMAN_STALE
    elif full_terminal or short_terminal:
        fisherman_status = FISHERMAN_EXITED_AFTER_CAPTURE
    elif full_running and short_running:
        fisherman_status = FISHERMAN_RUNNING_RECENT
    elif full_running or short_running:
        fisherman_status = FISHERMAN_RUNNING_RECENT
    else:
        fisherman_status = UNKNOWN_NEEDS_MANUAL_REVIEW
    return {
        "full_spectrum_heartbeat_found": bool(latest_full),
        "latest_full_spectrum_heartbeat_at": latest_full.get("generated_at") if latest_full else None,
        "latest_full_spectrum_iteration": latest_full.get("iteration") if latest_full else None,
        "latest_full_spectrum_status": latest_full.get("status") if latest_full else None,
        "full_spectrum_watcher_likely_running": bool(full_running),
        "full_spectrum_watcher_stale": bool(full_stale),
        "short_capture_heartbeat_found": bool(latest_short),
        "latest_short_capture_heartbeat_at": latest_short.get("generated_at") if latest_short else None,
        "short_capture_watcher_likely_running": bool(short_running),
        "short_capture_watcher_stale": bool(short_stale),
        "latest_short_capture_status": latest_short.get("status") if latest_short else None,
        "fisherman_status": fisherman_status,
    }


def detect_harvester_exit_after_capture(
    *,
    full_spectrum_heartbeats: list[Mapping[str, Any]],
    full_spectrum_records: list[Mapping[str, Any]],
) -> dict[str, Any]:
    latest_full = full_spectrum_heartbeats[0] if full_spectrum_heartbeats else {}
    latest_status = str(latest_full.get("status") or "")
    latest_lanes = [str(item) for item in latest_full.get("captured_lanes") or []]
    record_lanes = _captured_lanes_from_records(full_spectrum_records)
    heartbeat_captured = _int_value(latest_full.get("total_captured")) > 0 or bool(latest_lanes)
    exited_after_capture = latest_status == FULL_SPECTRUM_HARVEST_EXITED and (heartbeat_captured or bool(record_lanes))
    return {
        "harvester_exited_after_capture": bool(exited_after_capture),
        "latest_full_spectrum_status": latest_status or None,
        "latest_full_spectrum_captured_lanes": latest_lanes,
        "record_captured_lanes": record_lanes,
    }


def detect_no_signal_vs_no_fisherman(
    *,
    fisherman_health: Mapping[str, Any],
    capture_watch_summary: Mapping[str, Any],
) -> dict[str, Any]:
    status = str(fisherman_health.get("fisherman_status") or UNKNOWN_NEEDS_MANUAL_REVIEW)
    fresh_count = _int_value(capture_watch_summary.get("fresh_capture_count"))
    full_captures = _int_value(capture_watch_summary.get("full_spectrum_captures_found"))
    if status == FISHERMAN_NOT_RUNNING:
        return {"classification": FISHERMAN_NOT_RUNNING, "plain_english": "No fisherman heartbeat is visible; this is not the same as no signal."}
    if status == FISHERMAN_STALE:
        return {"classification": FISHERMAN_STALE, "plain_english": "The fisherman has heartbeat evidence, but it is stale and cannot prove weekend coverage."}
    if status in {FISHERMAN_EXITED_AFTER_CAPTURE, SIGNAL_CAPTURED_AND_FISHERMAN_EXITED}:
        return {"classification": FISHERMAN_EXITED_AFTER_CAPTURE, "plain_english": "The harvester captured evidence and then exited; restart is needed for continued fishing."}
    if status == FISHERMAN_RUNNING_RECENT and fresh_count == 0 and full_captures == 0:
        return {"classification": NO_SIGNAL_BUT_FISHERMAN_RUNNING, "plain_english": "No fresh signal is currently captured, but recent fisherman heartbeats indicate the process is watching."}
    if status == FISHERMAN_RUNNING_RECENT:
        return {"classification": FISHERMAN_RUNNING_RECENT, "plain_english": "The fisherman appears recent and capture flow should be evaluated by count and lane."}
    if status == LEDGER_MISMATCH_REQUIRES_RECONCILIATION:
        return {"classification": UNKNOWN, "plain_english": "Local ledgers disagree or a required ledger is missing; reconcile before interpreting no-signal status."}
    return {"classification": UNKNOWN, "plain_english": "Supervisor cannot cleanly distinguish signal absence from fisherman absence; inspect local ledgers."}


def build_weekend_capture_watch_summary(
    *,
    lane_key: str,
    short_capture_records: list[Mapping[str, Any]],
    full_spectrum_records: list[Mapping[str, Any]],
    capture_count_sync_status: Mapping[str, Any],
    harvester_exit_status: Mapping[str, Any],
) -> dict[str, Any]:
    count = dict(capture_count_sync_status.get("capture_count") or {})
    captured_lanes = _captured_lanes_from_records(full_spectrum_records)
    latest_short = short_capture_records[0] if short_capture_records else {}
    return {
        "primary_lane": lane_key,
        "fresh_capture_count": _int_value(count.get("fresh_capture_count")),
        "required_fresh_capture_count": _int_value(count.get("required_fresh_capture_count") or DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT),
        "capture_threshold_met": bool(count.get("threshold_met")),
        "latest_8m_short_capture": latest_short.get("captured_signal_id") or count.get("latest_captured_signal_id"),
        "latest_8m_short_capture_at": latest_short.get("recorded_at_utc") or latest_short.get("generated_at") if latest_short else None,
        "full_spectrum_captures_found": len(captured_lanes),
        "captured_lanes": captured_lanes,
        "harvester_exited_after_capture": bool(harvester_exit_status.get("harvester_exited_after_capture")),
        "ledger_mismatch_found": bool(capture_count_sync_status.get("ledger_mismatch_found")),
        "ledger_path_warnings": list(capture_count_sync_status.get("ledger_path_warnings") or []),
    }


def build_betrayal_watch_summary(
    *,
    betrayal_context: Mapping[str, Any],
    full_spectrum_records: list[Mapping[str, Any]],
    full_spectrum_heartbeats: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    latest_222m = _latest_222m_capture(full_spectrum_records, list(full_spectrum_heartbeats or []))
    return {
        "betrayal_context_included": True,
        "primary_betrayal_candidate": "222m aggregate",
        "primary_betrayal_original_win_rate_pct": 12.5,
        "primary_betrayal_naive_inverse_win_rate_pct": 87.5,
        "watchlist_betrayal_candidate": "88m aggregate",
        "watchlist_betrayal_original_win_rate_pct": 36.67,
        "watchlist_betrayal_naive_inverse_win_rate_pct": 63.33,
        "latest_222m_capture_found": bool(latest_222m),
        "latest_222m_capture_lane": latest_222m.get("lane_key") if latest_222m else None,
        "latest_222m_capture_at": latest_222m.get("captured_at") if latest_222m else None,
        "betrayal_integrated_into_current_matrix": False,
        "betrayal_live_ready": False,
        "true_inverse_validation_required": bool(betrayal_context.get("true_inverse_validation_required", True)),
        "betrayal_matrix_note": "Betrayal data is paper-only context and is not integrated into the current matrix.",
        "required_before_betrayal_promotion": [
            "true inverse paper outcomes",
            "regime support",
            "Miro Fish quality",
            "funding",
            "risk contract",
            "operator approval",
            "live gates",
        ],
    }


def build_weekend_supervisor_actions(
    *,
    fisherman_health: Mapping[str, Any],
    capture_watch_summary: Mapping[str, Any],
    betrayal_watch_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    status = str(fisherman_health.get("fisherman_status") or "")
    if status in {FISHERMAN_NOT_RUNNING, FISHERMAN_STALE, FISHERMAN_EXITED_AFTER_CAPTURE, SIGNAL_CAPTURED_AND_FISHERMAN_EXITED}:
        actions.append(
            {
                "priority": "HIGH",
                "action": "Use the safe tmux commands to restore the full-spectrum harvester and short capture watcher; Codex must not run them automatically.",
                "why": f"Weekend fisherman status is {status}.",
                "operator_command_safe": True,
            }
        )
    if capture_watch_summary.get("ledger_mismatch_found"):
        actions.append(
            {
                "priority": "HIGH",
                "action": "Run capture-count sync preview and reconcile missing or disagreeing local ledgers.",
                "why": "Capture ledger mismatch means the 8m short count cannot be trusted yet.",
                "operator_command_safe": True,
            }
        )
    if not capture_watch_summary.get("capture_threshold_met"):
        actions.append(
            {
                "priority": "MEDIUM",
                "action": "Keep paper fishing until BTCUSDT 8m short reaches 10 fresh captures.",
                "why": f"Current count is {capture_watch_summary.get('fresh_capture_count')}/{capture_watch_summary.get('required_fresh_capture_count')}.",
                "operator_command_safe": True,
            }
        )
    if betrayal_watch_summary.get("latest_222m_capture_found"):
        actions.append(
            {
                "priority": "MEDIUM",
                "action": "Run the future R209 betrayal integration recheck before treating 222m evidence as matrix input.",
                "why": "A 222m full-spectrum capture exists, but betrayal/inverse remains paper-only and not live-ready.",
                "operator_command_safe": True,
            }
        )
    if not actions:
        actions.append(
            {
                "priority": "LOW",
                "action": "Keep fisherman running and rerun the weekend supervisor periodically.",
                "why": "Recent heartbeats are present and no immediate local-ledger blocker was detected.",
                "operator_command_safe": True,
            }
        )
    return actions


def build_safe_weekend_operator_commands() -> dict[str, str]:
    full = build_full_spectrum_harvester_commands()
    watcher = build_safe_watcher_restart_commands()
    full_24h = full["bounded_loop_command"].replace("--max-iterations 60", f"--max-iterations {DEFAULT_WEEKEND_LOOP_ITERATIONS}")
    return {
        "tmux_status_check": (
            "tmux has-session -t r198-full-spectrum-harvest && tmux capture-pane -pt r198-full-spectrum-harvest -S -20; "
            "tmux has-session -t r176-8m-short-capture && tmux capture-pane -pt r176-8m-short-capture -S -20"
        ),
        "heartbeat_tail": (
            f"tail -n 20 logs/hammer_radar_forward/{FULL_SPECTRUM_HEARTBEAT_LEDGER_FILENAME}; "
            f"tail -n 20 logs/hammer_radar_forward/{SHORT_CAPTURE_HEARTBEAT_LEDGER_FILENAME}"
        ),
        "full_spectrum_harvester_restart_24h": f"tmux new-session -d -s r198-full-spectrum-harvest '{full_24h}'",
        "short_capture_watcher_restart_24h": watcher["start_24h_command"],
        "capture_count_recheck": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward capture-count-sync-8m-short"
        ),
        "weekend_supervisor_preview": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward weekend-paper-fisherman-supervisor"
        ),
    }


def append_weekend_paper_fisherman_supervisor_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = weekend_paper_fisherman_supervisor_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            **dict(record),
            "event_type": EVENT_TYPE,
            "supervisor_id": str(record.get("supervisor_id") or f"r208a_weekend_fisherman_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "supervisor_recorded": True,
            "safety": dict(SAFETY),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_weekend_paper_fisherman_supervisor_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = weekend_paper_fisherman_supervisor_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_weekend_paper_fisherman_supervisor_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "fisherman_status_counts": dict(
            sorted(Counter(str((record.get("fisherman_health") or {}).get("fisherman_status") or "UNKNOWN") for record in records).items())
        ),
        "last_supervisor_id": records[0].get("supervisor_id") if records else None,
        "safety": dict(SAFETY),
    }


def weekend_paper_fisherman_supervisor_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_weekend_paper_fisherman_supervisor_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _top_level_status(
    *,
    record_supervisor: bool,
    confirmation_valid: bool,
    fisherman_health: Mapping[str, Any],
) -> str:
    if record_supervisor and not confirmation_valid:
        return WEEKEND_PAPER_FISHERMAN_SUPERVISOR_REJECTED
    if record_supervisor and confirmation_valid:
        return WEEKEND_PAPER_FISHERMAN_SUPERVISOR_RECORDED
    if fisherman_health.get("fisherman_status") in {
        FISHERMAN_NOT_RUNNING,
        FISHERMAN_STALE,
        FISHERMAN_EXITED_AFTER_CAPTURE,
        SIGNAL_CAPTURED_AND_FISHERMAN_EXITED,
        UNKNOWN_NEEDS_MANUAL_REVIEW,
    }:
        return WEEKEND_PAPER_FISHERMAN_SUPERVISOR_BLOCKED
    return WEEKEND_PAPER_FISHERMAN_SUPERVISOR_READY


def _recommended_next_operator_move(
    *,
    fisherman_health: Mapping[str, Any],
    capture_watch_summary: Mapping[str, Any],
    betrayal_watch_summary: Mapping[str, Any],
) -> str:
    status = fisherman_health.get("fisherman_status")
    if status in {FISHERMAN_NOT_RUNNING, FISHERMAN_STALE, FISHERMAN_EXITED_AFTER_CAPTURE, SIGNAL_CAPTURED_AND_FISHERMAN_EXITED}:
        return RESTART_FULL_SPECTRUM_HARVESTER_24H
    if capture_watch_summary.get("ledger_mismatch_found"):
        return RUN_CAPTURE_COUNT_RECHECK
    if betrayal_watch_summary.get("latest_222m_capture_found"):
        return RUN_R209_BETRAYAL_INTEGRATION_RECHECK
    return KEEP_FISHERMAN_RUNNING


def _recommended_next_engineering_move(
    *,
    fisherman_health: Mapping[str, Any],
    capture_watch_summary: Mapping[str, Any],
    betrayal_watch_summary: Mapping[str, Any],
) -> str:
    status = str(fisherman_health.get("fisherman_status") or "")
    if status in {FISHERMAN_NOT_RUNNING, FISHERMAN_STALE, FISHERMAN_EXITED_AFTER_CAPTURE, SIGNAL_CAPTURED_AND_FISHERMAN_EXITED}:
        return "Keep R208A focused on paper supervision and have the operator restart R198/R176 tmux loops with safe commands."
    if capture_watch_summary.get("ledger_mismatch_found"):
        return "Reuse R208/R176 reconciliation until count-sync and capture ledgers agree; do not create a second count philosophy."
    if betrayal_watch_summary.get("latest_222m_capture_found"):
        return "Run R209 betrayal integration recheck as paper-only review before adding betrayal context to ranking/readiness matrices."
    return "Keep collecting local paper evidence and rerun R208A during the weekend; no live-readiness inference from fishing status."


def _weekend_policy() -> dict[str, Any]:
    return {
        "acceptable_no_signal_if_fisherman_running": True,
        "unacceptable_no_fisherman": True,
        "unacceptable_stale_heartbeat": True,
        "unacceptable_exit_after_capture_without_restart": True,
        "paper_only": True,
        "live_authorized": False,
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


def _captured_lanes_from_records(records: list[Mapping[str, Any]]) -> list[str]:
    lanes: list[str] = []
    for record in records:
        for lane in (record.get("capture_summary") or {}).get("captured_lanes") or []:
            lane_text = str(lane)
            if lane_text and lane_text not in lanes:
                lanes.append(lane_text)
        for candidate in (record.get("capture_summary") or {}).get("captured_candidates") or []:
            lane_text = str((candidate or {}).get("lane_key") or "")
            if lane_text and lane_text not in lanes:
                lanes.append(lane_text)
    return sorted(lanes)


def _latest_222m_capture(records: list[Mapping[str, Any]], heartbeats: list[Mapping[str, Any]]) -> dict[str, Any]:
    for heartbeat in heartbeats:
        for lane in heartbeat.get("captured_lanes") or []:
            lane_text = str(lane)
            if "|222m|" in lane_text:
                return {"lane_key": lane_text, "captured_at": heartbeat.get("generated_at")}
    for record in records:
        captured_at = record.get("recorded_at_utc") or record.get("generated_at")
        for lane in (record.get("capture_summary") or {}).get("captured_lanes") or []:
            lane_text = str(lane)
            if "|222m|" in lane_text:
                return {"lane_key": lane_text, "captured_at": captured_at}
        for candidate in (record.get("capture_summary") or {}).get("captured_candidates") or []:
            lane_text = str((candidate or {}).get("lane_key") or "")
            if "|222m|" in lane_text:
                return {"lane_key": lane_text, "captured_at": candidate.get("timestamp") or captured_at}
    return {}


def _load_recent_optional(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


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
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _empty_fisherman_health() -> dict[str, Any]:
    return {
        "full_spectrum_heartbeat_found": False,
        "latest_full_spectrum_heartbeat_at": None,
        "latest_full_spectrum_iteration": None,
        "latest_full_spectrum_status": None,
        "full_spectrum_watcher_likely_running": False,
        "full_spectrum_watcher_stale": False,
        "short_capture_heartbeat_found": False,
        "latest_short_capture_heartbeat_at": None,
        "short_capture_watcher_likely_running": False,
        "short_capture_watcher_stale": False,
        "latest_short_capture_status": None,
        "fisherman_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
    }


def _empty_capture_watch_summary(lane_key: str) -> dict[str, Any]:
    return {
        "primary_lane": lane_key,
        "fresh_capture_count": 0,
        "required_fresh_capture_count": DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT,
        "capture_threshold_met": False,
        "latest_8m_short_capture": None,
        "full_spectrum_captures_found": 0,
        "captured_lanes": [],
        "harvester_exited_after_capture": False,
        "ledger_mismatch_found": False,
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
