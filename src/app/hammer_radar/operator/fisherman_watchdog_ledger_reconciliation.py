"""R208B fisherman watchdog / capture ledger reconciliation.

This module reconciles local paper ledgers only. It never calls Binance or
network services, mutates env/config/lane/risk state, creates order payloads,
changes lane modes, disables the kill switch, or authorizes live execution.
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
    append_capture_count_sync_record,
    load_capture_count_sync_records as _load_capture_count_sync_records,
    load_short_capture_heartbeats as _load_short_capture_heartbeats,
    load_short_capture_records as _load_short_capture_records,
)
from src.app.hammer_radar.operator.capture_threshold_recovery_8m_short import (
    DEFAULT_LATEST_FULL_SPECTRUM_HEARTBEATS,
    DEFAULT_LATEST_FULL_SPECTRUM_RECORDS,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_harvester_expansion import (
    FULL_SPECTRUM_HARVEST_EXITED,
    HEARTBEAT_LEDGER_FILENAME as FULL_SPECTRUM_HEARTBEAT_LEDGER_FILENAME,
    LEDGER_FILENAME as FULL_SPECTRUM_LEDGER_FILENAME,
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

FISHERMAN_WATCHDOG_RECONCILIATION_READY = "FISHERMAN_WATCHDOG_RECONCILIATION_READY"
FISHERMAN_WATCHDOG_RECONCILIATION_REJECTED = "FISHERMAN_WATCHDOG_RECONCILIATION_REJECTED"
FISHERMAN_WATCHDOG_RECONCILIATION_RECORDED = "FISHERMAN_WATCHDOG_RECONCILIATION_RECORDED"
FISHERMAN_WATCHDOG_RECONCILIATION_BLOCKED = "FISHERMAN_WATCHDOG_RECONCILIATION_BLOCKED"
FISHERMAN_WATCHDOG_RECONCILIATION_ERROR = "FISHERMAN_WATCHDOG_RECONCILIATION_ERROR"

LEDGER_RECONCILED_THRESHOLD_NOT_MET = "LEDGER_RECONCILED_THRESHOLD_NOT_MET"
LEDGER_RECONCILED_THRESHOLD_MET = "LEDGER_RECONCILED_THRESHOLD_MET"
LEDGER_MISMATCH_REMAINS = "LEDGER_MISMATCH_REMAINS"
FISHERMAN_ALIVE_NO_SIGNAL = "FISHERMAN_ALIVE_NO_SIGNAL"
FISHERMAN_ALIVE_CAPTURE_FLOW_PRESENT = "FISHERMAN_ALIVE_CAPTURE_FLOW_PRESENT"
FISHERMAN_STALE = "FISHERMAN_STALE"
CAPTURE_COUNT_SYNC_LEDGER_MISSING = "CAPTURE_COUNT_SYNC_LEDGER_MISSING"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

NO_SIGNAL_LEDGER_MISMATCH = "LEDGER_MISMATCH"
UNKNOWN = "UNKNOWN"

KEEP_FISHERMAN_RUNNING = "KEEP_FISHERMAN_RUNNING"
WAIT_FOR_10_OF_10 = "WAIT_FOR_10_OF_10"
PREPARE_FUNDING_CHECK = "PREPARE_FUNDING_CHECK"
RUN_R227_BETRAYAL_DIRECTION_COMPLETION = "RUN_R227_BETRAYAL_DIRECTION_COMPLETION"
RUN_RISK_CONTRACT_READINESS = "RUN_RISK_CONTRACT_READINESS"

EVENT_TYPE = "FISHERMAN_WATCHDOG_LEDGER_RECONCILIATION"
LEDGER_FILENAME = "fisherman_watchdog_ledger_reconciliation.ndjson"
CAPTURE_COUNT_SYNC_LEDGER_FILENAME = "capture_count_sync_8m_short.ndjson"
CONFIRM_FISHERMAN_WATCHDOG_LEDGER_RECONCILIATION_PHRASE = (
    "I CONFIRM FISHERMAN WATCHDOG LEDGER RECONCILIATION ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT = MIN_FRESH_CANDIDATES

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
    "position_permission_created": False,
    "destructive_write": False,
    "historical_ledger_rewritten": False,
    "capture_count_sync_appended": False,
    "reconciliation_audit_appended": False,
}

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/capture_count_sync_8m_short.py",
    "src/app/hammer_radar/operator/capture_threshold_recovery_8m_short.py",
    "src/app/hammer_radar/operator/weekend_paper_fisherman_supervisor.py",
    "src/app/hammer_radar/operator/full_spectrum_harvester_expansion.py",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_HEARTBEAT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{FULL_SPECTRUM_HEARTBEAT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{FULL_SPECTRUM_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{CAPTURE_COUNT_SYNC_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_fisherman_watchdog_ledger_reconciliation(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    record_reconciliation: bool = False,
    confirm_fisherman_watchdog_ledger_reconciliation: str | None = None,
    latest_short_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_short_heartbeats: int = DEFAULT_LATEST_HEARTBEATS,
    latest_full_spectrum_records: int = DEFAULT_LATEST_FULL_SPECTRUM_RECORDS,
    latest_full_spectrum_heartbeats: int = DEFAULT_LATEST_FULL_SPECTRUM_HEARTBEATS,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_fisherman_watchdog_ledger_reconciliation
        == CONFIRM_FISHERMAN_WATCHDOG_LEDGER_RECONCILIATION_PHRASE
    )
    try:
        short_heartbeats = load_short_capture_heartbeats(log_dir=resolved_log_dir, lane_key=lane_key, limit=latest_short_heartbeats)
        full_heartbeats = load_full_spectrum_heartbeats(log_dir=resolved_log_dir, limit=latest_full_spectrum_heartbeats)
        short_records = load_short_capture_records(log_dir=resolved_log_dir, lane_key=lane_key, limit=latest_short_captures)
        full_records = load_full_spectrum_capture_records(log_dir=resolved_log_dir, limit=latest_full_spectrum_records)
        sync_records = load_capture_count_sync_records(log_dir=resolved_log_dir, limit=50)

        watcher_health = build_watcher_health_snapshot(
            short_capture_heartbeats=short_heartbeats,
            full_spectrum_heartbeats=full_heartbeats,
            now=generated_at,
            stale_after_seconds=stale_after_seconds,
        )
        capture_count = build_reconciled_capture_count_snapshot(
            short_capture_records=short_records,
            full_spectrum_capture_records=full_records,
            lane_key=lane_key,
            required_fresh_capture_count=DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT,
        )
        mismatch = build_ledger_mismatch_report(
            log_dir=resolved_log_dir,
            short_capture_records=short_records,
            full_spectrum_capture_records=full_records,
            capture_count_sync_records=sync_records,
            reconciled_capture_count=capture_count,
            lane_key=lane_key,
        )
        no_signal = build_no_signal_vs_no_fisherman_classification(
            watcher_health=watcher_health,
            reconciled_capture_count=capture_count,
            ledger_mismatch_report=mismatch,
        )
        reconciliation_status = classify_fisherman_reconciliation_status(
            watcher_health=watcher_health,
            reconciled_capture_count=capture_count,
            ledger_mismatch_report=mismatch,
            capture_count_sync_records=sync_records,
            record_reconciliation_requested=record_reconciliation,
            confirmation_valid=confirmation_valid,
        )
        recommendations = build_reconciliation_recommendations(
            watcher_health=watcher_health,
            reconciled_capture_count=capture_count,
            ledger_mismatch_report=mismatch,
            reconciliation_status=reconciliation_status,
        )
        status = _top_level_status(
            record_reconciliation=record_reconciliation,
            confirmation_valid=confirmation_valid,
            watcher_health=watcher_health,
            ledger_mismatch_report=mismatch,
        )
        safety = dict(SAFETY)
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "reconciliation_recorded": False,
            "reconciliation_id": None,
            "record_reconciliation_requested": bool(record_reconciliation),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "primary_lane": lane_key,
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "short_capture_heartbeats_found": bool(short_heartbeats),
                "full_spectrum_heartbeats_found": bool(full_heartbeats),
                "short_capture_records_found": bool(short_records),
                "full_spectrum_capture_records_found": bool(full_records),
                "capture_count_sync_ledger_found": bool((resolved_log_dir / CAPTURE_COUNT_SYNC_LEDGER_FILENAME).exists()),
            },
            "watcher_health": watcher_health,
            "reconciled_capture_count": capture_count,
            "ledger_mismatch_report": mismatch,
            "no_signal_vs_no_fisherman": no_signal,
            "reconciliation_recommendations": recommendations,
            "reconciliation_status": reconciliation_status,
            "recommended_next_operator_move": _recommended_next_operator_move(
                watcher_health=watcher_health,
                reconciled_capture_count=capture_count,
                ledger_mismatch_report=mismatch,
                reconciliation_status=reconciliation_status,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(
                reconciled_capture_count=capture_count,
                ledger_mismatch_report=mismatch,
                reconciliation_status=reconciliation_status,
            ),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_reconciliation and confirmation_valid:
            sync_record = append_capture_count_sync_record(_capture_count_sync_payload(payload), log_dir=resolved_log_dir)
            safety["capture_count_sync_appended"] = True
            safety["reconciliation_audit_appended"] = True
            audit_record = append_fisherman_reconciliation_record({**payload, "safety": safety}, log_dir=resolved_log_dir)
            payload["safety"] = safety
            payload["reconciliation_recorded"] = True
            payload["reconciliation_id"] = audit_record["reconciliation_id"]
            payload["capture_count_sync_id"] = sync_record.get("sync_id")
            payload["capture_count_sync_ledger_path"] = str(resolved_log_dir / CAPTURE_COUNT_SYNC_LEDGER_FILENAME)
            payload["reconciliation_ledger_path"] = str(fisherman_reconciliation_records_path(resolved_log_dir))
            payload["status"] = FISHERMAN_WATCHDOG_RECONCILIATION_RECORDED
            payload["reconciliation_status"] = (
                LEDGER_RECONCILED_THRESHOLD_MET if capture_count.get("threshold_met") else LEDGER_RECONCILED_THRESHOLD_NOT_MET
            )
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": FISHERMAN_WATCHDOG_RECONCILIATION_ERROR,
                "generated_at": generated_at.isoformat(),
                "reconciliation_recorded": False,
                "reconciliation_id": None,
                "record_reconciliation_requested": bool(record_reconciliation),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {"primary_lane": lane_key, "paper_only": True, "live_authorized": False},
                "input_summary": {
                    "short_capture_heartbeats_found": False,
                    "full_spectrum_heartbeats_found": False,
                    "short_capture_records_found": False,
                    "full_spectrum_capture_records_found": False,
                    "capture_count_sync_ledger_found": False,
                },
                "watcher_health": _empty_watcher_health(),
                "reconciled_capture_count": _empty_capture_count(),
                "ledger_mismatch_report": _empty_mismatch_report(mismatch_found=True),
                "no_signal_vs_no_fisherman": {
                    "classification": UNKNOWN,
                    "plain_english": "Local reconciliation hit a parsing/build error; inspect ledgers before acting.",
                },
                "reconciliation_recommendations": [
                    {
                        "priority": "HIGH",
                        "recommended_action": "FIX_RECONCILIATION_SURFACE",
                        "future_phase": "R208B",
                        "why": exc.__class__.__name__,
                    }
                ],
                "reconciliation_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": KEEP_FISHERMAN_RUNNING,
                "recommended_next_engineering_move": "Fix R208B local reconciliation error before trusting fisherman count state.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_short_capture_heartbeats(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    limit: int = DEFAULT_LATEST_HEARTBEATS,
) -> list[dict[str, Any]]:
    return _load_short_capture_heartbeats(log_dir=log_dir, lane_key=lane_key, limit=max(0, int(limit)))


def load_full_spectrum_heartbeats(
    *,
    log_dir: str | Path | None = None,
    limit: int = DEFAULT_LATEST_FULL_SPECTRUM_HEARTBEATS,
) -> list[dict[str, Any]]:
    path = full_spectrum_harvester_heartbeats_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=max(0, int(limit)), max_bytes=16_777_216)]


def load_short_capture_records(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    limit: int = DEFAULT_LATEST_CAPTURES,
) -> list[dict[str, Any]]:
    return _load_short_capture_records(log_dir=log_dir, lane_key=lane_key, limit=max(0, int(limit)))


def load_full_spectrum_capture_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = DEFAULT_LATEST_FULL_SPECTRUM_RECORDS,
) -> list[dict[str, Any]]:
    return _load_full_spectrum_harvester_records(log_dir=log_dir, limit=max(0, int(limit)))


def load_capture_count_sync_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return _load_capture_count_sync_records(log_dir=log_dir, limit=limit)


def parse_8m_short_capture_ids(
    *,
    short_capture_records: list[Mapping[str, Any]],
    full_spectrum_capture_records: list[Mapping[str, Any]],
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(short_capture_records):
        signal_id = str(record.get("captured_signal_id") or "").strip()
        record_lane = _record_lane_key(record)
        if record.get("paper_evidence_captured") is True and signal_id and _is_primary_capture(signal_id, record_lane, lane_key):
            rows.append(
                {
                    "captured_signal_id": signal_id,
                    "lane_key": record_lane or lane_key,
                    "source_ledger": SHORT_CAPTURE_LEDGER_FILENAME,
                    "captured_at": record.get("generated_at") or record.get("recorded_at_utc"),
                    "source_index": index,
                }
            )
    for index, record in enumerate(full_spectrum_capture_records):
        for candidate in _captured_candidates(record):
            signal_id = str(candidate.get("signal_id") or candidate.get("captured_signal_id") or candidate.get("candidate_id") or "").strip()
            candidate_lane = str(candidate.get("lane_key") or "")
            if signal_id and _is_primary_capture(signal_id, candidate_lane, lane_key):
                rows.append(
                    {
                        "captured_signal_id": signal_id,
                        "lane_key": candidate_lane or lane_key,
                        "source_ledger": FULL_SPECTRUM_LEDGER_FILENAME,
                        "captured_at": candidate.get("timestamp") or record.get("generated_at") or record.get("recorded_at_utc"),
                        "source_index": index,
                    }
                )
    return rows


def dedupe_capture_ids(capture_rows: list[Mapping[str, Any]]) -> list[str]:
    ids: list[str] = []
    for row in capture_rows:
        signal_id = str(row.get("captured_signal_id") or "").strip()
        if signal_id and signal_id not in ids:
            ids.append(signal_id)
    return ids


def classify_capture_freshness(
    *,
    capture_count: Mapping[str, Any],
    watcher_health: Mapping[str, Any],
) -> str:
    if capture_count.get("threshold_met"):
        return LEDGER_RECONCILED_THRESHOLD_MET
    if watcher_health.get("short_capture_watcher_stale") or watcher_health.get("full_spectrum_watcher_stale"):
        return FISHERMAN_STALE
    if int(capture_count.get("fresh_capture_count") or 0) > 0:
        return FISHERMAN_ALIVE_CAPTURE_FLOW_PRESENT
    if watcher_health.get("short_capture_watcher_likely_running") or watcher_health.get("full_spectrum_watcher_likely_running"):
        return FISHERMAN_ALIVE_NO_SIGNAL
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def build_reconciled_capture_count_snapshot(
    *,
    short_capture_records: list[Mapping[str, Any]],
    full_spectrum_capture_records: list[Mapping[str, Any]],
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    required_fresh_capture_count: int = DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT,
) -> dict[str, Any]:
    rows = parse_8m_short_capture_ids(
        short_capture_records=short_capture_records,
        full_spectrum_capture_records=full_spectrum_capture_records,
        lane_key=lane_key,
    )
    ids = dedupe_capture_ids(rows)
    return {
        "fresh_capture_count": len(ids),
        "required_fresh_capture_count": int(required_fresh_capture_count),
        "threshold_met": len(ids) >= int(required_fresh_capture_count),
        "latest_captured_signal_id": ids[0] if ids else None,
        "unique_captured_signal_ids": ids,
    }


def build_watcher_health_snapshot(
    *,
    short_capture_heartbeats: list[Mapping[str, Any]],
    full_spectrum_heartbeats: list[Mapping[str, Any]],
    now: datetime | None = None,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    latest_short = short_capture_heartbeats[0] if short_capture_heartbeats else {}
    latest_full = full_spectrum_heartbeats[0] if full_spectrum_heartbeats else {}
    short_age = _age_seconds(latest_short.get("generated_at"), generated_at) if latest_short else None
    full_age = _age_seconds(latest_full.get("generated_at"), generated_at) if latest_full else None
    short_stale = bool(latest_short) and (short_age is None or short_age > int(stale_after_seconds))
    full_stale = bool(latest_full) and (full_age is None or full_age > int(stale_after_seconds))
    short_terminal = str(latest_short.get("status") or "") == SHORT_PAPER_CAPTURE_EXITED
    full_terminal = str(latest_full.get("status") or "") == FULL_SPECTRUM_HARVEST_EXITED
    return {
        "short_capture_watcher_likely_running": bool(latest_short) and not short_stale and not short_terminal,
        "short_capture_watcher_stale": bool(short_stale),
        "short_capture_latest_heartbeat_at": latest_short.get("generated_at") if latest_short else None,
        "short_capture_latest_iteration": latest_short.get("iteration") if latest_short else None,
        "full_spectrum_watcher_likely_running": bool(latest_full) and not full_stale and not full_terminal,
        "full_spectrum_watcher_stale": bool(full_stale),
        "full_spectrum_latest_heartbeat_at": latest_full.get("generated_at") if latest_full else None,
        "full_spectrum_latest_iteration": latest_full.get("iteration") if latest_full else None,
    }


def build_ledger_mismatch_report(
    *,
    log_dir: str | Path | None,
    short_capture_records: list[Mapping[str, Any]],
    full_spectrum_capture_records: list[Mapping[str, Any]],
    capture_count_sync_records: list[Mapping[str, Any]],
    reconciled_capture_count: Mapping[str, Any],
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    missing = [
        f"logs/hammer_radar_forward/{filename}"
        for filename in (CAPTURE_COUNT_SYNC_LEDGER_FILENAME,)
        if not (resolved_log_dir / filename).exists()
    ]
    stale_ledgers: list[str] = []
    latest_sync = capture_count_sync_records[0] if capture_count_sync_records else {}
    sync_count = dict(latest_sync.get("capture_count") or {})
    sync_ids = [str(item) for item in sync_count.get("unique_captured_signal_ids") or [] if str(item)]
    local_ids = list(reconciled_capture_count.get("unique_captured_signal_ids") or [])
    count_differs = bool(latest_sync) and int(sync_count.get("fresh_capture_count") or 0) != int(
        reconciled_capture_count.get("fresh_capture_count") or 0
    )
    ids_differ = bool(sync_ids) and sync_ids != local_ids
    lane_mismatches = _lane_key_mismatches(short_capture_records, full_spectrum_capture_records, expected_lane_key=lane_key)
    reconciliation_possible = bool(local_ids)
    mismatch_found = bool(missing or stale_ledgers or count_differs or ids_differ or lane_mismatches)
    return {
        "ledger_mismatch_found": mismatch_found,
        "missing_ledgers": missing,
        "stale_ledgers": stale_ledgers,
        "reconciliation_possible_from_local_evidence": reconciliation_possible,
        "reconciled_capture_count_would_write": reconciliation_possible,
        "latest_sync_count_differs": bool(count_differs),
        "latest_sync_ids_differ": bool(ids_differ),
        "lane_key_mismatches": lane_mismatches,
    }


def build_no_signal_vs_no_fisherman_classification(
    *,
    watcher_health: Mapping[str, Any],
    reconciled_capture_count: Mapping[str, Any],
    ledger_mismatch_report: Mapping[str, Any],
) -> dict[str, Any]:
    if ledger_mismatch_report.get("ledger_mismatch_found"):
        return {
            "classification": NO_SIGNAL_LEDGER_MISMATCH,
            "plain_english": "Local count-sync ledger state is missing or disagrees; reconcile before interpreting no-signal status.",
        }
    if watcher_health.get("short_capture_watcher_stale") or watcher_health.get("full_spectrum_watcher_stale"):
        return {
            "classification": FISHERMAN_STALE,
            "plain_english": "Watcher heartbeat evidence exists but is stale; this cannot prove live paper fishing coverage.",
        }
    running = bool(watcher_health.get("short_capture_watcher_likely_running") or watcher_health.get("full_spectrum_watcher_likely_running"))
    count = int(reconciled_capture_count.get("fresh_capture_count") or 0)
    if running and count == 0:
        return {
            "classification": FISHERMAN_ALIVE_NO_SIGNAL,
            "plain_english": "Recent watcher heartbeats are present and no fresh 8m short capture is visible yet.",
        }
    if running and count > 0:
        return {
            "classification": FISHERMAN_ALIVE_CAPTURE_FLOW_PRESENT,
            "plain_english": "Recent watcher heartbeats and 8m short capture evidence are both present; evaluate the threshold count.",
        }
    return {
        "classification": UNKNOWN,
        "plain_english": "Reconciliation cannot cleanly distinguish signal absence from missing fisherman evidence.",
    }


def build_reconciliation_recommendations(
    *,
    watcher_health: Mapping[str, Any],
    reconciled_capture_count: Mapping[str, Any],
    ledger_mismatch_report: Mapping[str, Any],
    reconciliation_status: str,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if ledger_mismatch_report.get("ledger_mismatch_found") and ledger_mismatch_report.get("reconciliation_possible_from_local_evidence"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RECORD_RECONCILED_CAPTURE_COUNT",
                "future_phase": "R208B",
                "why": "Local paper ledgers can rebuild the 8m short capture-count sync record append-only.",
            }
        )
    if watcher_health.get("short_capture_watcher_stale") or watcher_health.get("full_spectrum_watcher_stale"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "KEEP_FISHERMAN_RUNNING",
                "future_phase": "R208B",
                "why": "At least one watcher heartbeat is stale; restore paper fishing before interpreting no-signal state.",
            }
        )
    if not reconciled_capture_count.get("threshold_met"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "WAIT_FOR_MORE_CAPTURES",
                "future_phase": "R228",
                "why": f"Current count is {reconciled_capture_count.get('fresh_capture_count')}/{reconciled_capture_count.get('required_fresh_capture_count')}.",
            }
        )
    if reconciled_capture_count.get("threshold_met") and reconciliation_status != LEDGER_MISMATCH_REMAINS:
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "MOVE_TO_RISK_CONTRACT_AFTER_10_OF_10",
                "future_phase": "R228",
                "why": "The local unique 8m short capture threshold is met, but funding/risk contract readiness remains a separate non-executing review.",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "priority": "LOW",
                "recommended_action": "KEEP_FISHERMAN_RUNNING",
                "future_phase": "R208B",
                "why": "No immediate ledger action is available; keep paper watchers alive and rerun preview.",
            }
        )
    return recommendations


def classify_fisherman_reconciliation_status(
    *,
    watcher_health: Mapping[str, Any],
    reconciled_capture_count: Mapping[str, Any],
    ledger_mismatch_report: Mapping[str, Any],
    capture_count_sync_records: list[Mapping[str, Any]],
    record_reconciliation_requested: bool = False,
    confirmation_valid: bool = False,
) -> str:
    if record_reconciliation_requested and confirmation_valid:
        return LEDGER_RECONCILED_THRESHOLD_MET if reconciled_capture_count.get("threshold_met") else LEDGER_RECONCILED_THRESHOLD_NOT_MET
    if ledger_mismatch_report.get("missing_ledgers") and ledger_mismatch_report.get("reconciliation_possible_from_local_evidence"):
        return CAPTURE_COUNT_SYNC_LEDGER_MISSING
    if ledger_mismatch_report.get("ledger_mismatch_found"):
        return LEDGER_MISMATCH_REMAINS
    if watcher_health.get("short_capture_watcher_stale") or watcher_health.get("full_spectrum_watcher_stale"):
        return FISHERMAN_STALE
    if reconciled_capture_count.get("threshold_met"):
        return LEDGER_RECONCILED_THRESHOLD_MET
    if int(reconciled_capture_count.get("fresh_capture_count") or 0) > 0:
        return LEDGER_RECONCILED_THRESHOLD_NOT_MET
    if watcher_health.get("short_capture_watcher_likely_running") or watcher_health.get("full_spectrum_watcher_likely_running"):
        return FISHERMAN_ALIVE_NO_SIGNAL if not capture_count_sync_records else FISHERMAN_ALIVE_CAPTURE_FLOW_PRESENT
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_fisherman_reconciliation_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = fisherman_reconciliation_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            **dict(record),
            "event_type": EVENT_TYPE,
            "reconciliation_id": str(record.get("reconciliation_id") or f"r208b_fisherman_reconciliation_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "reconciliation_recorded": True,
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_fisherman_reconciliation_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = fisherman_reconciliation_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_fisherman_reconciliation_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "reconciliation_status_counts": dict(
            sorted(Counter(str(record.get("reconciliation_status") or "UNKNOWN") for record in records).items())
        ),
        "last_reconciliation_id": records[0].get("reconciliation_id") if records else None,
        "safety": dict(SAFETY),
    }


def fisherman_reconciliation_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_fisherman_watchdog_ledger_reconciliation_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _capture_count_sync_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    capture_count = dict(payload.get("reconciled_capture_count") or {})
    watcher = dict(payload.get("watcher_health") or {})
    target = dict(payload.get("target_scope") or {})
    threshold_met = bool(capture_count.get("threshold_met"))
    return {
        "status": "CAPTURE_COUNT_SYNC_RECORDED",
        "generated_at": payload.get("generated_at"),
        "target_family": _target_family(str(target.get("primary_lane") or DEFAULT_TARGET_LANE_KEY)),
        "capture_count": capture_count,
        "watcher_status": {
            "latest_heartbeat_found": bool(watcher.get("short_capture_latest_heartbeat_at")),
            "latest_heartbeat_iteration": watcher.get("short_capture_latest_iteration"),
            "watcher_likely_running": bool(watcher.get("short_capture_watcher_likely_running")),
            "watcher_stale": bool(watcher.get("short_capture_watcher_stale")),
            "latest_capture_id": capture_count.get("latest_captured_signal_id"),
        },
        "threshold_status": "CAPTURE_THRESHOLD_MET" if threshold_met else "CAPTURE_THRESHOLD_NOT_MET",
        "r158_should_be_rerun": threshold_met,
        "tiny_live_evidence_threshold_met": threshold_met,
        "recommended_next_operator_move": payload.get("recommended_next_operator_move"),
        "recommended_next_engineering_move": payload.get("recommended_next_engineering_move"),
        "safety": dict(payload.get("safety") or SAFETY),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or SOURCE_SURFACES_USED),
    }


def _top_level_status(
    *,
    record_reconciliation: bool,
    confirmation_valid: bool,
    watcher_health: Mapping[str, Any],
    ledger_mismatch_report: Mapping[str, Any],
) -> str:
    if record_reconciliation and not confirmation_valid:
        return FISHERMAN_WATCHDOG_RECONCILIATION_REJECTED
    if record_reconciliation and confirmation_valid:
        return FISHERMAN_WATCHDOG_RECONCILIATION_RECORDED
    if (
        watcher_health.get("short_capture_watcher_stale")
        or watcher_health.get("full_spectrum_watcher_stale")
        or (ledger_mismatch_report.get("ledger_mismatch_found") and not ledger_mismatch_report.get("reconciliation_possible_from_local_evidence"))
    ):
        return FISHERMAN_WATCHDOG_RECONCILIATION_BLOCKED
    return FISHERMAN_WATCHDOG_RECONCILIATION_READY


def _recommended_next_operator_move(
    *,
    watcher_health: Mapping[str, Any],
    reconciled_capture_count: Mapping[str, Any],
    ledger_mismatch_report: Mapping[str, Any],
    reconciliation_status: str,
) -> str:
    if watcher_health.get("short_capture_watcher_stale") or watcher_health.get("full_spectrum_watcher_stale"):
        return KEEP_FISHERMAN_RUNNING
    if ledger_mismatch_report.get("ledger_mismatch_found"):
        return WAIT_FOR_10_OF_10
    if reconciled_capture_count.get("threshold_met") and reconciliation_status != LEDGER_MISMATCH_REMAINS:
        return PREPARE_FUNDING_CHECK
    return WAIT_FOR_10_OF_10


def _recommended_next_engineering_move(
    *,
    reconciled_capture_count: Mapping[str, Any],
    ledger_mismatch_report: Mapping[str, Any],
    reconciliation_status: str,
) -> str:
    if ledger_mismatch_report.get("ledger_mismatch_found"):
        return "Record the R208B append-only reconciliation only after operator confirmation; do not change configs or infer funding readiness."
    if reconciled_capture_count.get("threshold_met") and reconciliation_status == LEDGER_RECONCILED_THRESHOLD_MET:
        return "Prepare R228 10-of-10 ready packet as checklist-only review; keep live execution disabled."
    return "Keep R198/R176 fisherman surfaces running and rerun R208B after additional local paper captures."


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


def _target_family(lane_key: str) -> dict[str, Any]:
    parts = lane_key.split("|")
    return {
        "lane_key": lane_key,
        "symbol": parts[0] if len(parts) > 0 else "",
        "timeframe": parts[1] if len(parts) > 1 else "",
        "direction": parts[2] if len(parts) > 2 else "",
        "entry_mode": parts[3] if len(parts) > 3 else "",
        "current_mode": "paper",
    }


def _record_lane_key(record: Mapping[str, Any]) -> str:
    lane = record.get("target_lane")
    if isinstance(lane, Mapping) and lane.get("lane_key"):
        return str(lane.get("lane_key"))
    return str(record.get("captured_lane_key") or "")


def _captured_candidates(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates = record.get("captured_candidates") or (record.get("capture_summary") or {}).get("captured_candidates") or []
    return [dict(candidate) for candidate in candidates if isinstance(candidate, Mapping)]


def _is_primary_capture(signal_id: str, lane_key: str, expected_lane_key: str) -> bool:
    expected = _lane_from_key(expected_lane_key)
    lane = _lane_from_key(lane_key) if lane_key else {}
    if lane_key:
        return (
            lane.get("symbol") == expected["symbol"]
            and lane.get("timeframe") == expected["timeframe"]
            and lane.get("direction") == expected["direction"]
        )
    parts = signal_id.split("|")
    return len(parts) >= 4 and parts[0] == expected["symbol"] and parts[1] == expected["timeframe"] and parts[2] == expected["direction"]


def _lane_key_mismatches(
    short_records: list[Mapping[str, Any]],
    full_records: list[Mapping[str, Any]],
    *,
    expected_lane_key: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in short_records:
        lane_key = _record_lane_key(record)
        if record.get("paper_evidence_captured") is True and lane_key and not _is_primary_capture(str(record.get("captured_signal_id") or ""), lane_key, expected_lane_key):
            rows.append({"source": SHORT_CAPTURE_LEDGER_FILENAME, "signal_id": record.get("captured_signal_id"), "lane_key": lane_key})
    for record in full_records:
        for candidate in _captured_candidates(record):
            lane_key = str(candidate.get("lane_key") or "")
            signal_id = str(candidate.get("signal_id") or candidate.get("candidate_id") or "")
            if lane_key and _same_symbol_timeframe_direction(lane_key, expected_lane_key) and lane_key != expected_lane_key:
                rows.append({"source": FULL_SPECTRUM_LEDGER_FILENAME, "signal_id": signal_id, "lane_key": lane_key})
    return rows[:50]


def _same_symbol_timeframe_direction(lane_key: str, expected_lane_key: str) -> bool:
    lane = _lane_from_key(lane_key)
    expected = _lane_from_key(expected_lane_key)
    return lane["symbol"] == expected["symbol"] and lane["timeframe"] == expected["timeframe"] and lane["direction"] == expected["direction"]


def _lane_from_key(lane_key: str) -> dict[str, str]:
    parts = str(lane_key or "").split("|")
    return {
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


def _empty_capture_count() -> dict[str, Any]:
    return {
        "fresh_capture_count": 0,
        "required_fresh_capture_count": int(DEFAULT_REQUIRED_FRESH_CAPTURE_COUNT),
        "threshold_met": False,
        "latest_captured_signal_id": None,
        "unique_captured_signal_ids": [],
    }


def _empty_watcher_health() -> dict[str, Any]:
    return {
        "short_capture_watcher_likely_running": False,
        "short_capture_watcher_stale": False,
        "short_capture_latest_heartbeat_at": None,
        "short_capture_latest_iteration": None,
        "full_spectrum_watcher_likely_running": False,
        "full_spectrum_watcher_stale": False,
        "full_spectrum_latest_heartbeat_at": None,
        "full_spectrum_latest_iteration": None,
    }


def _empty_mismatch_report(*, mismatch_found: bool = False) -> dict[str, Any]:
    return {
        "ledger_mismatch_found": bool(mismatch_found),
        "missing_ledgers": [],
        "stale_ledgers": [],
        "reconciliation_possible_from_local_evidence": False,
        "reconciled_capture_count_would_write": False,
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
