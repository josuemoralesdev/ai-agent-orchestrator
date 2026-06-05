"""R196 full-spectrum paper coverage audit.

This module audits local paper coverage only. It reads existing configs and
ledgers, can append one audit record after exact confirmation, and never calls
Binance/network, creates payloads, mutates env/config, changes lane modes, or
promotes lanes/origins.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE, load_lane_controls, normalize_lane_key
from src.app.hammer_radar.operator.signal_origin_registry import (
    DETECTOR_AVAILABLE,
    INFERRED_FROM_EXISTING_FIELDS,
    REGISTRY_ONLY,
    build_signal_origin_registry,
    infer_signal_origin_from_record,
    normalize_signal_origin,
)

FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_READY = "FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_READY"
FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_REJECTED = "FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_REJECTED"
FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_RECORDED = "FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_RECORDED"
FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_BLOCKED = "FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_BLOCKED"
FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_ERROR = "FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_ERROR"

COVERED_ACTIVE = "COVERED_ACTIVE"
COVERED_STALE = "COVERED_STALE"
CONFIGURED_NOT_HARVESTED = "CONFIGURED_NOT_HARVESTED"
SIGNALS_PRESENT_NOT_CONFIGURED = "SIGNALS_PRESENT_NOT_CONFIGURED"
OUTCOMES_PRESENT_NOT_WATCHED = "OUTCOMES_PRESENT_NOT_WATCHED"
ORIGIN_REGISTERED_NO_DETECTOR = "ORIGIN_REGISTERED_NO_DETECTOR"
ORIGIN_DETECTOR_AVAILABLE_NOT_MATRIXED = "ORIGIN_DETECTOR_AVAILABLE_NOT_MATRIXED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "FULL_SPECTRUM_PAPER_COVERAGE_AUDIT"
LEDGER_FILENAME = "full_spectrum_paper_coverage_audit.ndjson"
CONFIRM_FULL_SPECTRUM_PAPER_AUDIT_RECORDING_PHRASE = (
    "I CONFIRM FULL SPECTRUM PAPER COVERAGE AUDIT RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_TIMEFRAMES = ("4m", "8m", "13m", "22m", "44m", "55m", "88m", "222m", "444m", "666m", "888m", "4H", "13H", "13D")
DEFAULT_ENTRY_MODE = "ladder_close_50_618"
DEFAULT_RECORD_LIMIT = 5000
LARGE_RECORD_LIMIT = 50000

LOCAL_LOG_FILES = (
    "signals.ndjson",
    "multi_symbol_paper_scans.ndjson",
    "expanded_paper_watch.ndjson",
    "multi_lane_paper_harvester.ndjson",
    "multi_lane_evidence_rankings.ndjson",
    "paper_executions.ndjson",
    "outcomes.ndjson",
    "short_paper_evidence_capture.ndjson",
    "signal_origin_registry.ndjson",
    "keter_signal_origin_scoring.ndjson",
    "three_black_crows_paper_tags.ndjson",
    "crow_outcome_mapping_preview.ndjson",
    "signal_origin_lane_matrix.ndjson",
    "lane_matrix_after_crow_rescoring.ndjson",
    "lane_matrix_after_crow_outcome_feedback.ndjson",
)

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
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    *[f"logs/hammer_radar_forward/{name}" for name in LOCAL_LOG_FILES],
    "operator.lane_control.load_lane_controls",
    "operator.signal_origin_registry.build_signal_origin_registry",
    "operator.signal_origin_registry.infer_signal_origin_from_record",
]


def build_full_spectrum_paper_coverage_audit(
    *,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    record_audit: bool = False,
    confirm_full_spectrum_paper_audit: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_full_spectrum_paper_audit == CONFIRM_FULL_SPECTRUM_PAPER_AUDIT_RECORDING_PHRASE
    try:
        configured = load_configured_lanes(config_path=config_path)
        paper_lanes = load_paper_lanes(config_path=config_path)
        tiny_refs = load_tiny_live_reference_lanes(config_path=config_path)
        signals = discover_signal_lane_coverage(log_dir=resolved_log_dir)
        active = discover_active_harvester_coverage(log_dir=resolved_log_dir)
        executions = discover_paper_execution_coverage(log_dir=resolved_log_dir)
        outcomes = discover_paper_outcome_coverage(log_dir=resolved_log_dir)
        origins = discover_signal_origin_coverage(log_dir=resolved_log_dir)
        timeframes = discover_timeframes_from_configs_and_logs(log_dir=resolved_log_dir, config_path=config_path)
        symbols = discover_symbols_from_logs(log_dir=resolved_log_dir)

        lane_matrix = build_lane_coverage_matrix(
            configured_lanes=configured,
            signal_coverage=signals,
            execution_coverage=executions,
            outcome_coverage=outcomes,
            harvester_coverage=active,
        )
        timeframe_matrix = build_timeframe_coverage_matrix(
            timeframes=timeframes,
            configured_lanes=configured,
            signal_coverage=signals,
            execution_coverage=executions,
            outcome_coverage=outcomes,
            harvester_coverage=active,
        )
        symbol_matrix = build_symbol_coverage_matrix(
            symbols=symbols,
            configured_lanes=configured,
            signal_coverage=signals,
            execution_coverage=executions,
            outcome_coverage=outcomes,
        )
        origin_matrix = build_signal_origin_coverage_matrix(origin_coverage=origins)
        blind_spots = build_blind_spot_report(
            lane_coverage_matrix=lane_matrix,
            timeframe_coverage_matrix=timeframe_matrix,
            signal_origin_coverage_matrix=origin_matrix,
        )
        action_plan = build_full_spectrum_next_action_plan(blind_spot_report=blind_spots, origin_matrix=origin_matrix)
        status = FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_READY
        if not lane_matrix:
            status = FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_BLOCKED
        if record_audit and not confirmation_valid:
            status = FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_REJECTED
        elif record_audit and confirmation_valid:
            status = FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "audit_recorded": False,
            "audit_id": None,
            "record_audit_requested": bool(record_audit),
            "confirmation_valid": bool(confirmation_valid),
            "coverage_summary": {
                "configured_lanes_count": len(configured),
                "paper_lanes_count": len(paper_lanes),
                "tiny_live_reference_lanes_count": len(tiny_refs),
                "symbols_found_count": len(symbols),
                "timeframes_found": timeframes,
                "paper_executions_found": executions["total_count"],
                "paper_outcomes_found": outcomes["total_count"],
                "signal_origins_registered": origins["registered_count"],
                "detectors_available": origins["detectors_available_count"],
            },
            "lane_coverage_matrix": lane_matrix,
            "timeframe_coverage_matrix": timeframe_matrix,
            "symbol_coverage_matrix": symbol_matrix,
            "signal_origin_coverage_matrix": origin_matrix,
            "blind_spot_report": blind_spots,
            "full_spectrum_next_action_plan": action_plan,
            "recommended_next_operator_move": _recommended_next_operator_move(blind_spots),
            "recommended_next_engineering_move": _recommended_next_engineering_move(blind_spots),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_audit and confirmation_valid:
            record = append_full_spectrum_paper_coverage_audit_record(payload, log_dir=resolved_log_dir)
            payload["audit_recorded"] = True
            payload["audit_id"] = record["audit_id"]
            payload["ledger_path"] = str(full_spectrum_paper_coverage_audit_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_ERROR,
                "generated_at": generated_at.isoformat(),
                "audit_recorded": False,
                "audit_id": None,
                "record_audit_requested": bool(record_audit),
                "confirmation_valid": bool(confirmation_valid),
                "coverage_summary": {},
                "lane_coverage_matrix": [],
                "timeframe_coverage_matrix": {},
                "symbol_coverage_matrix": {},
                "signal_origin_coverage_matrix": {},
                "blind_spot_report": {},
                "full_spectrum_next_action_plan": [],
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R196 audit build error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_configured_lanes(*, config_path: str | Path | None = None) -> list[dict[str, Any]]:
    return sorted([_compact_lane(lane) for lane in load_lane_controls(config_path or DEFAULT_CONFIG_PATH).get("lanes") or []], key=lambda row: row["lane_key"])


def load_paper_lanes(*, config_path: str | Path | None = None) -> list[dict[str, Any]]:
    return [lane for lane in load_configured_lanes(config_path=config_path) if lane["mode"] == "paper"]


def load_tiny_live_reference_lanes(*, config_path: str | Path | None = None) -> list[dict[str, Any]]:
    return [dict(lane, reference_only=True) for lane in load_configured_lanes(config_path=config_path) if lane["mode"] == "tiny_live"]


def discover_timeframes_from_configs_and_logs(*, log_dir: str | Path | None = None, config_path: str | Path | None = None) -> list[str]:
    resolved = get_log_dir(log_dir, use_env=True)
    values = {str(lane["timeframe"]) for lane in load_configured_lanes(config_path=config_path)}
    values.update(DEFAULT_TIMEFRAMES)
    risk_contracts_path = Path(config_path or DEFAULT_CONFIG_PATH).parent / "tiny_live_risk_contracts.json"
    if risk_contracts_path.exists():
        values.update(_collect_field_values_from_json_file(risk_contracts_path, "timeframe"))
    for record in _iter_local_records(resolved, LOCAL_LOG_FILES, limit=LARGE_RECORD_LIMIT):
        values.update(_collect_field_values(record, "timeframe"))
        values.update(_collect_field_values(record, "bias_timeframe"))
    return _ordered_timeframes(values)


def discover_symbols_from_logs(*, log_dir: str | Path | None = None) -> list[str]:
    resolved = get_log_dir(log_dir, use_env=True)
    symbols: set[str] = set()
    for record in _iter_local_records(resolved, LOCAL_LOG_FILES, limit=LARGE_RECORD_LIMIT):
        symbols.update(str(value).strip().upper() for value in _collect_field_values(record, "symbol") if str(value).strip())
    return sorted(symbols)


def discover_paper_execution_coverage(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = read_recent_ndjson_records(get_log_dir(log_dir, use_env=True) / "paper_executions.ndjson", limit=LARGE_RECORD_LIMIT, max_bytes=32_000_000)
    return _coverage_from_records(records, source="paper_executions.ndjson")


def discover_paper_outcome_coverage(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = read_recent_ndjson_records(get_log_dir(log_dir, use_env=True) / "outcomes.ndjson", limit=LARGE_RECORD_LIMIT, max_bytes=64_000_000)
    return _coverage_from_records(records, source="outcomes.ndjson")


def discover_signal_origin_coverage(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved = get_log_dir(log_dir, use_env=True)
    registry = build_signal_origin_registry()
    registered = {str(row["signal_origin"]): dict(row) for row in registry}
    seen = Counter()
    matrixed = set()
    detector_evidence = set()
    for name in ("signals.ndjson", "multi_symbol_paper_scans.ndjson", "multi_lane_paper_harvester.ndjson", "three_black_crows_paper_tags.ndjson"):
        for record in read_recent_ndjson_records(resolved / name, limit=LARGE_RECORD_LIMIT, max_bytes=64_000_000):
            origin = infer_signal_origin_from_record(record)
            seen[origin] += 1
            if origin == "three_black_crows" or str(record.get("event_type") or "") == "THREE_BLACK_CROWS_PAPER_TAG":
                detector_evidence.add("three_black_crows")
    for name in ("signal_origin_lane_matrix.ndjson", "lane_matrix_after_crow_rescoring.ndjson", "lane_matrix_after_crow_outcome_feedback.ndjson", "keter_signal_origin_scoring.ndjson"):
        for record in read_recent_ndjson_records(resolved / name, limit=DEFAULT_RECORD_LIMIT, max_bytes=32_000_000):
            for value in _collect_field_values(record, "signal_origin"):
                origin = normalize_signal_origin(value)
                if origin != "unknown_or_unclassified":
                    matrixed.add(origin)
    for path in (resolved / "three_black_crows_local_detections.ndjson", resolved / "three_black_crows_paper_tags.ndjson"):
        if path.exists() and path.stat().st_size > 0:
            detector_evidence.add("three_black_crows")
    detectors = {
        origin
        for origin, entry in registered.items()
        if entry.get("availability") in {DETECTOR_AVAILABLE, INFERRED_FROM_EXISTING_FIELDS}
    } | detector_evidence
    return {
        "registered": registered,
        "registered_count": len(registered),
        "seen_counts": dict(sorted(seen.items())),
        "detectors_available": sorted(detectors),
        "detectors_available_count": len(detectors),
        "matrixed_origins": sorted(matrixed),
    }


def discover_active_harvester_coverage(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved = get_log_dir(log_dir, use_env=True)
    by_lane: dict[str, dict[str, Any]] = defaultdict(lambda: {"fresh": 0, "stale": 0, "observed": 0, "ranked": False, "watcher": False})
    for record in read_recent_ndjson_records(resolved / "multi_lane_paper_harvester.ndjson", limit=DEFAULT_RECORD_LIMIT, max_bytes=32_000_000):
        summary = record.get("capture_summary") if isinstance(record.get("capture_summary"), Mapping) else {}
        for lane_key, count in dict(summary.get("fresh_by_lane") or {}).items():
            by_lane[str(lane_key)]["fresh"] += int(count or 0)
        for lane_key, count in dict(summary.get("stale_by_lane") or {}).items():
            by_lane[str(lane_key)]["stale"] += int(count or 0)
        for lane_key, count in dict(summary.get("observed_tiny_live_by_lane") or {}).items():
            by_lane[str(lane_key)]["observed"] += int(count or 0)
        for candidate in summary.get("captured_candidates") or []:
            lane_key = str((candidate or {}).get("lane_key") or "")
            if lane_key:
                by_lane[lane_key]["fresh"] += 1
    for record in read_recent_ndjson_records(resolved / "multi_lane_evidence_rankings.ndjson", limit=DEFAULT_RECORD_LIMIT, max_bytes=32_000_000):
        for row in record.get("ranked_lanes") or []:
            lane_key = str((row or {}).get("lane_key") or "")
            if lane_key:
                by_lane[lane_key]["ranked"] = True
    for name in ("expanded_paper_watch.ndjson", "short_paper_evidence_capture.ndjson"):
        for record in read_recent_ndjson_records(resolved / name, limit=DEFAULT_RECORD_LIMIT, max_bytes=32_000_000):
            for lane_key in _collect_field_values(record, "lane_key"):
                if lane_key:
                    by_lane[str(lane_key)]["watcher"] = True
    return {lane: dict(values) for lane, values in sorted(by_lane.items())}


def discover_signal_lane_coverage(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = []
    resolved = get_log_dir(log_dir, use_env=True)
    for name in ("signals.ndjson", "multi_symbol_paper_scans.ndjson", "three_black_crows_paper_tags.ndjson"):
        records.extend(read_recent_ndjson_records(resolved / name, limit=LARGE_RECORD_LIMIT, max_bytes=64_000_000))
    return _coverage_from_records(records, source="signals_and_scans")


def build_lane_coverage_matrix(
    *,
    configured_lanes: list[Mapping[str, Any]],
    signal_coverage: Mapping[str, Any],
    execution_coverage: Mapping[str, Any],
    outcome_coverage: Mapping[str, Any],
    harvester_coverage: Mapping[str, Any],
) -> list[dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {str(lane["lane_key"]): dict(lane) for lane in configured_lanes}
    for coverage in (signal_coverage, execution_coverage, outcome_coverage):
        for lane_key in coverage.get("by_lane", {}):
            lanes.setdefault(str(lane_key), _lane_from_key(str(lane_key)))
    rows = []
    configured_keys = {str(lane["lane_key"]) for lane in configured_lanes}
    for lane_key in sorted(lanes, key=_lane_sort_key):
        lane = lanes[lane_key]
        signals_found = int((signal_coverage.get("by_lane") or {}).get(lane_key, 0))
        executions_found = int((execution_coverage.get("by_lane") or {}).get(lane_key, 0))
        outcomes_found = int((outcome_coverage.get("by_lane") or {}).get(lane_key, 0))
        harvest = dict(harvester_coverage.get(lane_key) or {})
        harvester_status = _covered_missing_stale(harvest.get("fresh"), harvest.get("stale"), harvest.get("observed"))
        watcher_status = "covered" if harvest.get("watcher") else "missing"
        coverage_status = _lane_coverage_status(
            lane_key=lane_key,
            mode=str(lane.get("mode") or "unknown"),
            configured=lane_key in configured_keys,
            signals_found=signals_found,
            executions_found=executions_found,
            outcomes_found=outcomes_found,
            harvester_status=harvester_status,
            watcher_status=watcher_status,
        )
        rows.append(
            {
                "lane_key": lane_key,
                "mode": str(lane.get("mode") or "unknown"),
                "symbol": str(lane.get("symbol") or "UNKNOWN"),
                "timeframe": str(lane.get("timeframe") or "unknown"),
                "direction": str(lane.get("direction") or "unknown"),
                "entry_mode": str(lane.get("entry_mode") or DEFAULT_ENTRY_MODE),
                "signals_found": signals_found,
                "paper_executions_found": executions_found,
                "outcomes_found": outcomes_found,
                "harvester_coverage": harvester_status,
                "watcher_coverage": watcher_status,
                "ranked": bool(harvest.get("ranked")),
                "reference_only": str(lane.get("mode") or "") == "tiny_live",
                "coverage_status": coverage_status,
                "recommended_action": _lane_recommended_action(coverage_status, lane_key),
            }
        )
    return rows


def build_timeframe_coverage_matrix(
    *,
    timeframes: list[str],
    configured_lanes: list[Mapping[str, Any]],
    signal_coverage: Mapping[str, Any],
    execution_coverage: Mapping[str, Any],
    outcome_coverage: Mapping[str, Any],
    harvester_coverage: Mapping[str, Any],
) -> dict[str, Any]:
    configured_by_tf = Counter(str(lane.get("timeframe") or "") for lane in configured_lanes)
    harvested_by_tf = Counter(_lane_from_key(key)["timeframe"] for key, row in harvester_coverage.items() if row.get("fresh") or row.get("stale") or row.get("observed"))
    result = {}
    for timeframe in timeframes:
        result[timeframe] = {
            "configured_lanes": int(configured_by_tf.get(_normalize_timeframe(timeframe), configured_by_tf.get(timeframe, 0))),
            "signals_found": int((signal_coverage.get("by_timeframe") or {}).get(_normalize_timeframe(timeframe), 0)),
            "paper_executions_found": int((execution_coverage.get("by_timeframe") or {}).get(_normalize_timeframe(timeframe), 0)),
            "outcomes_found": int((outcome_coverage.get("by_timeframe") or {}).get(_normalize_timeframe(timeframe), 0)),
            "harvested_or_watched": int(harvested_by_tf.get(_normalize_timeframe(timeframe), 0)),
            "coverage_status": COVERED_ACTIVE if harvested_by_tf.get(_normalize_timeframe(timeframe), 0) else UNKNOWN_NEEDS_MANUAL_REVIEW,
        }
    return result


def build_symbol_coverage_matrix(
    *,
    symbols: list[str],
    configured_lanes: list[Mapping[str, Any]],
    signal_coverage: Mapping[str, Any],
    execution_coverage: Mapping[str, Any],
    outcome_coverage: Mapping[str, Any],
) -> dict[str, Any]:
    configured = Counter(str(lane.get("symbol") or "").upper() for lane in configured_lanes)
    return {
        symbol: {
            "configured_lanes": int(configured.get(symbol, 0)),
            "signals_found": int((signal_coverage.get("by_symbol") or {}).get(symbol, 0)),
            "paper_executions_found": int((execution_coverage.get("by_symbol") or {}).get(symbol, 0)),
            "outcomes_found": int((outcome_coverage.get("by_symbol") or {}).get(symbol, 0)),
            "coverage_status": COVERED_ACTIVE if configured.get(symbol, 0) else SIGNALS_PRESENT_NOT_CONFIGURED,
        }
        for symbol in symbols
    }


def build_signal_origin_coverage_matrix(*, origin_coverage: Mapping[str, Any]) -> dict[str, Any]:
    registered = origin_coverage.get("registered") or {}
    seen = origin_coverage.get("seen_counts") or {}
    detectors = set(origin_coverage.get("detectors_available") or [])
    matrixed = set(origin_coverage.get("matrixed_origins") or [])
    rows = {}
    for origin, entry in sorted(registered.items()):
        detector_available = origin in detectors
        matrixed_origin = origin in matrixed
        availability = str(entry.get("availability") or REGISTRY_ONLY)
        if not detector_available and availability == REGISTRY_ONLY:
            status = ORIGIN_REGISTERED_NO_DETECTOR
        elif detector_available and not matrixed_origin:
            status = ORIGIN_DETECTOR_AVAILABLE_NOT_MATRIXED
        elif detector_available:
            status = COVERED_ACTIVE
        else:
            status = UNKNOWN_NEEDS_MANUAL_REVIEW
        rows[origin] = {
            "registered": True,
            "availability": availability,
            "detector_available": detector_available,
            "matrixed_or_ranked": matrixed_origin,
            "signals_found": int(seen.get(origin, 0)),
            "coverage_status": status,
            "recommended_action": _origin_recommended_action(origin, status),
        }
    return rows


def build_blind_spot_report(
    *,
    lane_coverage_matrix: list[Mapping[str, Any]],
    timeframe_coverage_matrix: Mapping[str, Any],
    signal_origin_coverage_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "configured_not_harvested": [row["lane_key"] for row in lane_coverage_matrix if row.get("coverage_status") == CONFIGURED_NOT_HARVESTED],
        "signals_present_not_configured": [row["lane_key"] for row in lane_coverage_matrix if row.get("coverage_status") == SIGNALS_PRESENT_NOT_CONFIGURED],
        "paper_outcomes_without_current_watcher": [row["lane_key"] for row in lane_coverage_matrix if row.get("coverage_status") == OUTCOMES_PRESENT_NOT_WATCHED],
        "origins_registered_without_detector": [origin for origin, row in signal_origin_coverage_matrix.items() if row.get("coverage_status") == ORIGIN_REGISTERED_NO_DETECTOR],
        "origins_detector_available_but_not_ranked": [origin for origin, row in signal_origin_coverage_matrix.items() if row.get("coverage_status") == ORIGIN_DETECTOR_AVAILABLE_NOT_MATRIXED],
        "timeframes_seen_but_not_currently_harvested": [
            timeframe
            for timeframe, row in timeframe_coverage_matrix.items()
            if int(row.get("signals_found") or 0) + int(row.get("outcomes_found") or 0) > 0 and int(row.get("harvested_or_watched") or 0) == 0
        ],
    }


def build_full_spectrum_next_action_plan(*, blind_spot_report: Mapping[str, Any], origin_matrix: Mapping[str, Any] | None = None) -> list[dict[str, str]]:
    plan: list[dict[str, str]] = []
    if blind_spot_report.get("origins_registered_without_detector"):
        plan.append({"priority": "HIGH", "action": "Expand paper-only detector families for registry-only origins.", "why": "Registered origins without detectors cannot prove full-spectrum origin coverage.", "future_phase": "R197"})
    if blind_spot_report.get("signals_present_not_configured") or blind_spot_report.get("timeframes_seen_but_not_currently_harvested"):
        plan.append({"priority": "HIGH", "action": "Expand paper harvester coverage to discovered signal/timeframe gaps.", "why": "Signals exist outside current configured/harvested paper lanes.", "future_phase": "R198"})
    if blind_spot_report.get("configured_not_harvested"):
        plan.append({"priority": "MEDIUM", "action": "Keep R180 multi-lane harvester running and verify stale configured lanes become active.", "why": "Configured paper lanes are present but have no active fresh harvest evidence.", "future_phase": "R198"})
    if blind_spot_report.get("paper_outcomes_without_current_watcher"):
        plan.append({"priority": "MEDIUM", "action": "Back-map existing paper outcomes to current watcher coverage before tiny-live readiness work.", "why": "Outcome history exists for lanes not currently watched.", "future_phase": "R198"})
    if not plan:
        plan.append({"priority": "LOW", "action": "Keep 8m short watcher and multi-lane harvester running.", "why": "No high-priority paper coverage blind spot was detected in this audit.", "future_phase": "R197"})
    return plan


def append_full_spectrum_paper_coverage_audit_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = full_spectrum_paper_coverage_audit_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            **dict(record),
            "event_type": EVENT_TYPE,
            "audit_id": f"r196_full_spectrum_paper_coverage_audit_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "audit_recorded": True,
            "safety": dict(SAFETY),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_full_spectrum_paper_coverage_audit_records(*, log_dir: str | Path | None = None, limit: int = DEFAULT_RECORD_LIMIT) -> list[dict[str, Any]]:
    path = full_spectrum_paper_coverage_audit_records_path(get_log_dir(log_dir, use_env=True))
    if limit <= 0:
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(_sanitize(json.loads(line)))
        return list(reversed(records))
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=max(0, int(limit)), max_bytes=32_000_000)]


def summarize_full_spectrum_paper_coverage_audit_records(*, log_dir: str | Path | None = None, limit: int = DEFAULT_RECORD_LIMIT) -> dict[str, Any]:
    records = load_full_spectrum_paper_coverage_audit_records(log_dir=log_dir, limit=limit)
    latest = records[0] if records else None
    return {
        "status": "FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_RECORDS_READY",
        "records_count": len(records),
        "latest_audit_id": latest.get("audit_id") if latest else None,
        "latest_generated_at": latest.get("generated_at") if latest else None,
        "safety": dict(SAFETY),
    }


def full_spectrum_paper_coverage_audit_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_full_spectrum_paper_coverage_audit_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _coverage_from_records(records: list[Mapping[str, Any]], *, source: str) -> dict[str, Any]:
    by_lane: Counter[str] = Counter()
    by_symbol: Counter[str] = Counter()
    by_timeframe: Counter[str] = Counter()
    for record in records:
        lane_key = _record_lane_key(record)
        if lane_key:
            by_lane[lane_key] += 1
        symbol = str(record.get("symbol") or _lane_from_key(lane_key).get("symbol") or "").upper()
        timeframe = _normalize_timeframe(record.get("timeframe") or _lane_from_key(lane_key).get("timeframe"))
        if symbol:
            by_symbol[symbol] += 1
        if timeframe:
            by_timeframe[timeframe] += 1
    return {
        "source": source,
        "total_count": len(records),
        "by_lane": dict(sorted(by_lane.items(), key=lambda item: _lane_sort_key(item[0]))),
        "by_symbol": dict(sorted(by_symbol.items())),
        "by_timeframe": dict(sorted(by_timeframe.items(), key=lambda item: _timeframe_sort_key(item[0]))),
    }


def _record_lane_key(record: Mapping[str, Any]) -> str:
    explicit = str(record.get("lane_key") or "").strip()
    if explicit:
        return explicit
    signal_id = str(record.get("signal_id") or record.get("candidate_id") or "").strip()
    if signal_id.count("|") >= 2:
        parts = signal_id.split("|")
        entry = str(record.get("entry_mode") or DEFAULT_ENTRY_MODE)
        return normalize_lane_key(parts[0], parts[1], parts[2], entry)
    symbol = record.get("symbol")
    timeframe = record.get("timeframe")
    direction = record.get("direction") or record.get("latest_direction")
    entry = record.get("entry_mode") or ((record.get("ticket") or {}).get("entry_mode") if isinstance(record.get("ticket"), Mapping) else None) or DEFAULT_ENTRY_MODE
    if symbol and timeframe and direction:
        return normalize_lane_key(symbol, timeframe, direction, entry)
    return ""


def _lane_coverage_status(
    *,
    lane_key: str,
    mode: str,
    configured: bool,
    signals_found: int,
    executions_found: int,
    outcomes_found: int,
    harvester_status: str,
    watcher_status: str,
) -> str:
    if not configured and signals_found:
        return SIGNALS_PRESENT_NOT_CONFIGURED
    if outcomes_found and watcher_status == "missing":
        return OUTCOMES_PRESENT_NOT_WATCHED
    if configured and mode == "paper" and harvester_status == "missing":
        return CONFIGURED_NOT_HARVESTED
    if harvester_status == "covered":
        return COVERED_ACTIVE
    if harvester_status == "stale":
        return COVERED_STALE
    if executions_found or signals_found or outcomes_found:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    return CONFIGURED_NOT_HARVESTED if configured and mode == "paper" else UNKNOWN_NEEDS_MANUAL_REVIEW


def _lane_recommended_action(status: str, lane_key: str) -> str:
    if status == SIGNALS_PRESENT_NOT_CONFIGURED:
        return f"R198 should decide whether to add paper-only coverage for {lane_key}."
    if status == OUTCOMES_PRESENT_NOT_WATCHED:
        return f"R198 should restore watcher/harvester coverage before using {lane_key} outcomes."
    if status == CONFIGURED_NOT_HARVESTED:
        return f"Keep R180/R198 paper harvesting focused on {lane_key}; no live promotion."
    if status == COVERED_STALE:
        return f"Keep watcher running until fresh evidence appears for {lane_key}."
    return "Keep paper-only watcher/harvester evidence flowing."


def _origin_recommended_action(origin: str, status: str) -> str:
    if status == ORIGIN_REGISTERED_NO_DETECTOR:
        return f"R197 should add paper-only detector support for {origin}."
    if status == ORIGIN_DETECTOR_AVAILABLE_NOT_MATRIXED:
        return f"Matrix/rank {origin} after detector evidence is present."
    return "Keep origin evidence paper-only and do not promote."


def _covered_missing_stale(fresh: object, stale: object, observed: object) -> str:
    if int(fresh or 0) > 0 or int(observed or 0) > 0:
        return "covered"
    if int(stale or 0) > 0:
        return "stale"
    return "missing"


def _compact_lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_key": str(lane.get("lane_key") or normalize_lane_key(lane.get("symbol"), lane.get("timeframe"), lane.get("direction"), lane.get("entry_mode"))),
        "symbol": str(lane.get("symbol") or "").upper(),
        "timeframe": _normalize_timeframe(lane.get("timeframe")),
        "direction": str(lane.get("direction") or "").lower(),
        "entry_mode": str(lane.get("entry_mode") or DEFAULT_ENTRY_MODE).lower(),
        "mode": str(lane.get("mode") or "unknown").lower(),
    }


def _lane_from_key(lane_key: str) -> dict[str, Any]:
    parts = str(lane_key or "").split("|")
    return {
        "lane_key": lane_key,
        "symbol": parts[0].upper() if len(parts) > 0 else "UNKNOWN",
        "timeframe": _normalize_timeframe(parts[1] if len(parts) > 1 else "unknown"),
        "direction": parts[2].lower() if len(parts) > 2 else "unknown",
        "entry_mode": parts[3].lower() if len(parts) > 3 else DEFAULT_ENTRY_MODE,
        "mode": "unknown",
    }


def _iter_local_records(log_dir: Path, names: tuple[str, ...], *, limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in names:
        records.extend(read_recent_ndjson_records(log_dir / name, limit=limit, max_bytes=64_000_000))
    return records


def _collect_field_values(value: Any, field: str) -> set[Any]:
    found: set[Any] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == field and item not in (None, ""):
                found.add(item)
            found.update(_collect_field_values(item, field))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_field_values(item, field))
    return found


def _collect_field_values_from_json_file(path: Path, field: str) -> set[Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return _collect_field_values(raw, field)


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


def _ordered_timeframes(values: set[str] | list[str] | tuple[str, ...]) -> list[str]:
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


def _recommended_next_operator_move(blind_spots: Mapping[str, Any]) -> str:
    if blind_spots.get("origins_registered_without_detector"):
        return "RUN_R197_PATTERN_DETECTOR_FAMILY_EXPANSION"
    if blind_spots.get("signals_present_not_configured") or blind_spots.get("timeframes_seen_but_not_currently_harvested"):
        return "RUN_R198_FULL_SPECTRUM_HARVESTER_EXPANSION"
    if blind_spots.get("configured_not_harvested"):
        return "KEEP_MULTI_LANE_HARVESTER_RUNNING"
    return "KEEP_8M_SHORT_WATCHER_RUNNING"


def _recommended_next_engineering_move(blind_spots: Mapping[str, Any]) -> str:
    if blind_spots.get("origins_registered_without_detector"):
        return "Build R197 paper-only detector family expansion before any further tiny-live readiness claims."
    if blind_spots.get("signals_present_not_configured") or blind_spots.get("timeframes_seen_but_not_currently_harvested"):
        return "Build R198 full-spectrum paper harvester expansion from R196 blind spots."
    return "Keep R180/R181/R195 paper-only watchers running and rerun R196 after more evidence."


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


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
