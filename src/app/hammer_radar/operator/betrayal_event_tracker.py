"""R212 betrayal event tracker.

Paper-only event identity and tracker preview for future betrayal samples.
It reads local evidence only and writes an append-only tracker ledger only
after explicit confirmation. It never creates order payloads, calls Binance or
network, mutates env/config, promotes betrayal, or authorizes live execution.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_integration_recheck import load_latest_full_spectrum_222m_capture
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

BETRAYAL_EVENT_TRACKER_READY = "BETRAYAL_EVENT_TRACKER_READY"
BETRAYAL_EVENT_TRACKER_REJECTED = "BETRAYAL_EVENT_TRACKER_REJECTED"
BETRAYAL_EVENT_TRACKER_RECORDED = "BETRAYAL_EVENT_TRACKER_RECORDED"
BETRAYAL_EVENT_TRACKER_BLOCKED = "BETRAYAL_EVENT_TRACKER_BLOCKED"
BETRAYAL_EVENT_TRACKER_ERROR = "BETRAYAL_EVENT_TRACKER_ERROR"

BETRAYAL_EVENT_TRACKER_PREVIEW_READY = "BETRAYAL_EVENT_TRACKER_PREVIEW_READY"
BETRAYAL_EVENT_SEEDS_AVAILABLE = "BETRAYAL_EVENT_SEEDS_AVAILABLE"
BETRAYAL_EVENT_SEEDS_SCHEMA_INCOMPLETE = "BETRAYAL_EVENT_SEEDS_SCHEMA_INCOMPLETE"
BETRAYAL_EVENT_DIRECTION_SPLIT_REQUIRED = "BETRAYAL_EVENT_DIRECTION_SPLIT_REQUIRED"
BETRAYAL_EVENT_TRACKING_APPEND_ONLY_READY = "BETRAYAL_EVENT_TRACKING_APPEND_ONLY_READY"
BETRAYAL_EVENT_TRACKER_NOT_LIVE_AUTHORIZED = "BETRAYAL_EVENT_TRACKER_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_EVENT_TRACKER"
LEDGER_FILENAME = "betrayal_event_tracker.ndjson"
CONFIRM_BETRAYAL_EVENT_TRACKER_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL EVENT TRACKER RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

TARGET_CANDIDATES = ("222m", "88m", "55m")
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_ENTRY_MODE = "ladder_close_50_618"
OUTCOME_WINDOWS = [1, 3, 5, 10, 21, 34, 55]

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
    "ledger_rewritten": False,
    "destructive_write": False,
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
    "betrayal_live_authorized": False,
    "betrayal_promoted": False,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/betrayal_paper_matrix_context.ndjson",
    "logs/hammer_radar_forward/betrayal_true_inverse_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_integration_recheck.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_heartbeats.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_resolutions.ndjson",
    "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_signals.ndjson",
    "logs/hammer_radar_forward/candle_archive/BTCUSDT_222m.ndjson",
    "logs/hammer_radar_forward/candle_archive/BTCUSDT_88m.ndjson",
    "logs/hammer_radar_forward/candle_archive/BTCUSDT_55m.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_event_tracker(
    *,
    log_dir: str | Path | None = None,
    record_tracker: bool = False,
    confirm_betrayal_event_tracker: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_betrayal_event_tracker == CONFIRM_BETRAYAL_EVENT_TRACKER_RECORDING_PHRASE
    try:
        matrix_context = load_latest_betrayal_paper_matrix_context(log_dir=resolved_log_dir)
        true_inverse = load_latest_betrayal_true_inverse_refresh(log_dir=resolved_log_dir)
        integration = load_latest_betrayal_integration_recheck(log_dir=resolved_log_dir)
        captures = load_latest_full_spectrum_captures(log_dir=resolved_log_dir)
        paper_signals = load_existing_betrayal_paper_signals(log_dir=resolved_log_dir)
        true_outcomes = load_existing_betrayal_true_paper_outcomes(log_dir=resolved_log_dir)
        seed_candidates = build_betrayal_event_seed_candidates(
            matrix_context=matrix_context,
            true_inverse_refresh=true_inverse,
            integration_recheck=integration,
            full_spectrum_captures=captures,
            paper_signals=paper_signals,
            true_paper_outcomes=true_outcomes,
        )
        records_preview = build_betrayal_event_tracker_records(seed_candidates)
        preview = build_betrayal_event_tracker_preview(records_preview)
        gap_report = build_betrayal_event_tracker_gap_report(seed_candidates, records_preview)
        recommendations = build_betrayal_event_tracker_recommendations(gap_report=gap_report, seed_candidates=seed_candidates)
        tracker_status = classify_betrayal_event_tracker_status(
            seed_candidates=seed_candidates,
            records_preview=records_preview,
            gap_report=gap_report,
        )
        status = _top_level_status(
            record_tracker=record_tracker,
            confirmation_valid=confirmation_valid,
            seed_candidates=seed_candidates,
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "tracker_recorded": False,
            "tracker_id": None,
            "record_tracker_requested": bool(record_tracker),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "betrayal_candidates": ["222m aggregate", "88m aggregate", "55m aggregate_if_available"],
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "betrayal_matrix_context_found": bool(matrix_context),
                "true_inverse_refresh_found": bool(true_inverse),
                "betrayal_integration_recheck_found": bool(integration),
                "full_spectrum_captures_found": len(captures),
                "existing_betrayal_paper_signals_found": bool(paper_signals),
                "existing_betrayal_paper_signal_count": len(paper_signals),
                "existing_true_paper_outcomes_found": bool(true_outcomes),
                "existing_true_paper_outcome_count": len(true_outcomes),
            },
            "event_seed_candidates": seed_candidates,
            "event_tracker_preview": preview,
            "event_tracker_records_preview": records_preview,
            "event_tracker_gap_report": gap_report,
            "event_tracker_recommendations": recommendations,
            "event_tracker_status": tracker_status,
            "recommended_next_operator_move": _recommended_next_operator_move(gap_report, tracker_status),
            "recommended_next_engineering_move": _recommended_next_engineering_move(gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_tracker and confirmation_valid and records_preview:
            record = append_betrayal_event_tracker_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_EVENT_TRACKER_RECORDED
            payload["tracker_recorded"] = True
            payload["tracker_id"] = record["tracker_id"]
            payload["ledger_path"] = str(betrayal_event_tracker_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_EVENT_TRACKER_ERROR,
                "generated_at": generated_at.isoformat(),
                "tracker_recorded": False,
                "tracker_id": None,
                "record_tracker_requested": bool(record_tracker),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {
                    "betrayal_candidates": ["222m aggregate", "88m aggregate", "55m aggregate_if_available"],
                    "paper_only": True,
                    "live_authorized": False,
                },
                "input_summary": {},
                "event_seed_candidates": [],
                "event_tracker_preview": build_betrayal_event_tracker_preview([]),
                "event_tracker_records_preview": [],
                "event_tracker_gap_report": _empty_gap_report(),
                "event_tracker_recommendations": [],
                "event_tracker_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R212 tracker composer error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_paper_matrix_context(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_paper_matrix_context.ndjson")


def load_latest_betrayal_true_inverse_refresh(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_true_inverse_refresh.ndjson")


def load_latest_betrayal_integration_recheck(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_integration_recheck.ndjson")


def load_latest_full_spectrum_captures(*, log_dir: str | Path | None = None, limit: int = 200) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    captures: list[dict[str, Any]] = []
    for filename in ("full_spectrum_harvester_heartbeats.ndjson", "full_spectrum_harvester_expansion.ndjson"):
        for record in _read_recent(resolved_log_dir / filename, limit=limit):
            captures.extend(_extract_capture_rows(record, source=filename))
    latest_222m = load_latest_full_spectrum_222m_capture(log_dir=resolved_log_dir)
    if latest_222m:
        captures.append({**latest_222m, "source": "full_spectrum_capture"})
    return _dedupe_captures(captures)


def load_existing_betrayal_paper_signals(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_paper_signals.ndjson")


def load_existing_betrayal_true_paper_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_true_paper_outcomes.ndjson")


def build_betrayal_event_identity(
    *,
    symbol: str | None,
    timeframe: str | None,
    candidate_label: str | None,
    original_direction: str | None = None,
    inverse_direction: str | None = None,
    entry_mode: str | None = None,
    source_signal_id: str | None = None,
    source_capture_id: str | None = None,
    signal_timestamp: str | None = None,
    event_timeframe: str | None = None,
    outcome_window: Sequence[int] | None = None,
) -> dict[str, Any]:
    normalized = {
        "symbol": symbol or DEFAULT_SYMBOL,
        "timeframe": timeframe or "unknown",
        "candidate_label": candidate_label or f"{timeframe or 'unknown'} aggregate",
        "original_direction": _normal_direction(original_direction),
        "inverse_direction": _normal_direction(inverse_direction),
        "entry_mode": entry_mode,
        "source_signal_id": source_signal_id,
        "source_capture_id": source_capture_id,
        "signal_timestamp": signal_timestamp,
        "event_timeframe": event_timeframe or timeframe or "unknown",
        "outcome_window": list(outcome_window or OUTCOME_WINDOWS),
    }
    stable = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    event_hash = hashlib.sha256(stable.encode("utf-8")).hexdigest()
    event_identity = (
        f"betrayal_event|{normalized['symbol']}|{normalized['event_timeframe']}|"
        f"{normalized['candidate_label']}|{normalized['original_direction'] or 'aggregate'}|"
        f"{normalized['inverse_direction'] or 'aggregate'}|{normalized['entry_mode'] or 'entry_unknown'}|"
        f"{normalized['signal_timestamp'] or 'timestamp_unknown'}|{event_hash[:16]}"
    )
    return {**normalized, "event_identity": event_identity, "event_identity_hash": event_hash}


def build_betrayal_event_seed_candidates(
    *,
    matrix_context: Mapping[str, Any],
    true_inverse_refresh: Mapping[str, Any],
    integration_recheck: Mapping[str, Any],
    full_spectrum_captures: Sequence[Mapping[str, Any]],
    paper_signals: Sequence[Mapping[str, Any]],
    true_paper_outcomes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = _matrix_rows(matrix_context, true_inverse_refresh, integration_recheck)
    seeds: list[dict[str, Any]] = []
    for timeframe in TARGET_CANDIDATES:
        row = rows.get(timeframe)
        if not row and timeframe == "55m":
            continue
        candidate = f"{timeframe} aggregate"
        capture = _latest_capture_for_timeframe(full_spectrum_captures, timeframe)
        signal = _latest_signal_for_timeframe(paper_signals, timeframe)
        source = "betrayal_paper_signal" if signal else "full_spectrum_capture" if capture else "true_inverse_refresh"
        source_row = signal or capture or row or {}
        direction = classify_betrayal_event_direction_context(source_row, aggregate_default=True)
        schema = validate_betrayal_event_seed_schema(source_row, direction_context=direction)
        lane_key = _lane_key(source_row, timeframe=timeframe)
        seeds.append(
            _sanitize(
                {
                    "candidate": candidate,
                    "source": source,
                    "lane_key": lane_key,
                    "symbol": source_row.get("symbol") or DEFAULT_SYMBOL,
                    "timeframe": timeframe,
                    "signal_timestamp": _signal_timestamp(source_row),
                    "direction_context": direction,
                    "schema_complete": schema["schema_complete"],
                    "can_track_future_outcome": schema["can_track_future_outcome"],
                    "can_count_as_validated_sample_now": False,
                    "not_direction_specific": direction != "direction_specific",
                    "original_direction": _normal_direction(source_row.get("original_direction")),
                    "inverse_direction": _normal_direction(
                        source_row.get("inverse_direction")
                        or source_row.get("betrayal_direction")
                        or source_row.get("shadow_direction")
                    ),
                    "entry_mode": source_row.get("entry_mode"),
                    "source_signal_id": source_row.get("source_signal_id") or source_row.get("signal_id") or source_row.get("emitted_signal_id"),
                    "source_capture_id": source_row.get("source_capture_id") or source_row.get("capture_id") or source_row.get("candidate_id"),
                    "outcome_windows": list(OUTCOME_WINDOWS),
                    "why": _seed_why(
                        candidate=candidate,
                        direction_context=direction,
                        schema=schema,
                        capture=bool(capture),
                        true_paper_outcomes=true_paper_outcomes,
                    ),
                }
            )
        )
    return seeds


def validate_betrayal_event_seed_schema(seed: Mapping[str, Any], *, direction_context: str | None = None) -> dict[str, Any]:
    context = direction_context or classify_betrayal_event_direction_context(seed)
    timestamp = _signal_timestamp(seed)
    entry_mode = seed.get("entry_mode")
    original = _normal_direction(seed.get("original_direction"))
    inverse = _normal_direction(seed.get("inverse_direction") or seed.get("betrayal_direction") or seed.get("shadow_direction"))
    if context == "direction_specific":
        missing = []
        if not original:
            missing.append("original_direction")
        if not inverse:
            missing.append("inverse_direction")
        if not entry_mode:
            missing.append("entry_mode")
        if not timestamp:
            missing.append("signal_timestamp")
        return {
            "schema_complete": not missing,
            "can_track_future_outcome": not missing,
            "missing_fields": missing,
            "outcome_window_declared": True,
        }
    return {
        "schema_complete": bool(timestamp),
        "can_track_future_outcome": bool(timestamp),
        "missing_fields": [] if timestamp else ["signal_timestamp"],
        "outcome_window_declared": True,
    }


def classify_betrayal_event_direction_context(seed: Mapping[str, Any], *, aggregate_default: bool = False) -> str:
    original = _normal_direction(seed.get("original_direction"))
    inverse = _normal_direction(seed.get("inverse_direction") or seed.get("betrayal_direction") or seed.get("shadow_direction"))
    if original and inverse and seed.get("entry_mode") and _signal_timestamp(seed):
        return "direction_specific"
    if aggregate_default or str(seed.get("candidate") or seed.get("timeframe") or "").endswith("aggregate"):
        return "aggregate_context_only"
    return "unknown"


def build_betrayal_event_tracker_preview(records_preview: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "events_previewed": len(records_preview),
        "schema_complete_events": sum(1 for row in records_preview if row.get("schema_complete")),
        "aggregate_context_only_events": sum(1 for row in records_preview if row.get("direction_context") == "aggregate_context_only"),
        "direction_specific_events": sum(1 for row in records_preview if row.get("direction_context") == "direction_specific"),
        "events_ready_for_append_only_tracking": sum(1 for row in records_preview if row.get("can_track_future_outcome")),
        "events_blocked": sum(1 for row in records_preview if not row.get("can_track_future_outcome")),
    }


def build_betrayal_event_tracker_records(seed_candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for seed in seed_candidates:
        identity = build_betrayal_event_identity(
            symbol=str(seed.get("symbol") or DEFAULT_SYMBOL),
            timeframe=str(seed.get("timeframe") or "unknown"),
            candidate_label=str(seed.get("candidate") or "unknown aggregate"),
            original_direction=seed.get("original_direction"),
            inverse_direction=seed.get("inverse_direction"),
            entry_mode=seed.get("entry_mode"),
            source_signal_id=seed.get("source_signal_id"),
            source_capture_id=seed.get("source_capture_id"),
            signal_timestamp=seed.get("signal_timestamp"),
            event_timeframe=str(seed.get("timeframe") or "unknown"),
            outcome_window=seed.get("outcome_windows") or OUTCOME_WINDOWS,
        )
        records.append(
            _sanitize(
                {
                    "event_identity": identity["event_identity"],
                    "event_identity_hash": identity["event_identity_hash"],
                    "candidate": seed.get("candidate"),
                    "symbol": seed.get("symbol") or DEFAULT_SYMBOL,
                    "timeframe": seed.get("timeframe"),
                    "direction_context": seed.get("direction_context"),
                    "not_direction_specific": bool(seed.get("not_direction_specific")),
                    "original_direction": seed.get("original_direction"),
                    "inverse_direction": seed.get("inverse_direction"),
                    "entry_mode": seed.get("entry_mode"),
                    "source_signal_id": seed.get("source_signal_id"),
                    "source_capture_id": seed.get("source_capture_id"),
                    "signal_timestamp": seed.get("signal_timestamp"),
                    "outcome_windows": list(seed.get("outcome_windows") or OUTCOME_WINDOWS),
                    "schema_complete": bool(seed.get("schema_complete")),
                    "can_track_future_outcome": bool(seed.get("can_track_future_outcome")),
                    "can_count_as_validated_sample_now": False,
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            )
        )
    return records


def build_betrayal_event_tracker_gap_report(
    seed_candidates: Sequence[Mapping[str, Any]],
    records_preview: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    direction_specific = [row for row in records_preview if row.get("direction_context") == "direction_specific"]
    missing_original_inverse = [
        row for row in records_preview if row.get("direction_context") != "direction_specific"
    ]
    return {
        "direction_split_missing": bool(missing_original_inverse),
        "entry_mode_missing": any(not row.get("entry_mode") for row in records_preview),
        "timestamp_missing": any(not row.get("signal_timestamp") for row in records_preview),
        "outcome_window_missing": False,
        "aggregate_context_only_count": sum(1 for row in records_preview if row.get("direction_context") == "aggregate_context_only"),
        "schema_incomplete_count": sum(1 for row in records_preview if not row.get("schema_complete")),
        "direction_specific_count": len(direction_specific),
        "seed_candidate_count": len(seed_candidates),
        "required_for_validated_future_samples": [
            "original_direction",
            "inverse_direction",
            "entry_mode",
            "signal_timestamp",
            "declared_outcome_window",
            "future paper outcome resolver",
        ],
        "hard_live_blockers": [
            "betrayal_not_live_authorized",
            "betrayal_not_promoted",
            "event_tracking_is_paper_only",
            "direction_split_required_before_validation",
            "config_writes_forbidden",
            "orders_forbidden",
        ],
    }


def build_betrayal_event_tracker_recommendations(
    *,
    gap_report: Mapping[str, Any],
    seed_candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    recommendations = []
    if seed_candidates:
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "APPEND_TRACKER_EVENTS",
                "future_phase": "R212",
                "why": "Append-only tracker records can preserve deterministic paper event identities without creating outcomes or live permission.",
            }
        )
    if gap_report.get("direction_split_missing"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "COLLECT_DIRECTION_SPLIT",
                "future_phase": "R213",
                "why": "Aggregate betrayal context cannot count as directional proof until original/inverse directions and entry mode are present.",
            }
        )
    recommendations.append(
        {
            "priority": "MEDIUM",
            "recommended_action": "WIRE_SOURCE_EMITTER",
            "future_phase": "R214",
            "why": "Future outcome resolving needs tracked event identities linked to source signals or captures.",
        }
    )
    recommendations.append(
        {
            "priority": "LOW",
            "recommended_action": "KEEP_CONTEXT_ONLY",
            "future_phase": "R212",
            "why": "R212 event tracking remains paper-only and must not promote betrayal or infer live readiness.",
        }
    )
    return recommendations


def classify_betrayal_event_tracker_status(
    *,
    seed_candidates: Sequence[Mapping[str, Any]],
    records_preview: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not seed_candidates:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if any(row.get("can_track_future_outcome") for row in records_preview):
        if gap_report.get("direction_split_missing"):
            return BETRAYAL_EVENT_DIRECTION_SPLIT_REQUIRED
        return BETRAYAL_EVENT_TRACKING_APPEND_ONLY_READY
    if any(row.get("schema_complete") for row in records_preview):
        return BETRAYAL_EVENT_SEEDS_AVAILABLE
    if gap_report.get("schema_incomplete_count"):
        return BETRAYAL_EVENT_SEEDS_SCHEMA_INCOMPLETE
    return BETRAYAL_EVENT_TRACKER_NOT_LIVE_AUTHORIZED


def append_betrayal_event_tracker_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = betrayal_event_tracker_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "tracker_id": str(record.get("tracker_id") or f"r212_betrayal_event_tracker_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_EVENT_TRACKER_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_tracker_requested": bool(record.get("record_tracker_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "event_seed_candidates": list(record.get("event_seed_candidates") or []),
            "event_tracker_preview": dict(record.get("event_tracker_preview") or {}),
            "event_tracker_records_preview": list(record.get("event_tracker_records_preview") or []),
            "event_tracker_gap_report": dict(record.get("event_tracker_gap_report") or {}),
            "event_tracker_recommendations": list(record.get("event_tracker_recommendations") or []),
            "event_tracker_status": record.get("event_tracker_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_betrayal_event_tracker_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = betrayal_event_tracker_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_betrayal_event_tracker_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    preview = latest.get("event_tracker_preview") if isinstance(latest.get("event_tracker_preview"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "event_tracker_status_counts": dict(
            sorted(Counter(str(record.get("event_tracker_status") or "UNKNOWN") for record in records).items())
        ),
        "last_tracker_id": latest.get("tracker_id") if isinstance(latest, Mapping) else None,
        "last_events_previewed": preview.get("events_previewed"),
        "safety": dict(SAFETY),
    }


def betrayal_event_tracker_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_event_tracker_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _matrix_rows(
    matrix_context: Mapping[str, Any],
    true_inverse_refresh: Mapping[str, Any],
    integration_recheck: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rows = {}
    for row in matrix_context.get("betrayal_context_rows") or []:
        if isinstance(row, Mapping):
            timeframe = str(row.get("timeframe") or "").lower()
            if timeframe:
                rows[timeframe] = row
    refresh_summary = true_inverse_refresh.get("candidate_true_inverse_summary") or {}
    integration_summary = integration_recheck.get("betrayal_candidate_summary") or {}
    for timeframe in TARGET_CANDIDATES:
        if timeframe in rows:
            continue
        refresh = refresh_summary.get(timeframe)
        if isinstance(refresh, Mapping):
            rows[timeframe] = {"candidate": f"{timeframe} aggregate", "timeframe": timeframe, **dict(refresh)}
            continue
        integration = integration_summary.get(timeframe)
        if isinstance(integration, Mapping):
            rows[timeframe] = {"candidate": f"{timeframe} aggregate", "timeframe": timeframe, **dict(integration)}
    return rows


def _extract_capture_rows(record: Mapping[str, Any], *, source: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("captured_candidates", "captures", "captured_rows"):
        value = record.get(key)
        if isinstance(value, list):
            rows.extend({**dict(row), "source": source} for row in value if isinstance(row, Mapping))
    capture_summary = record.get("capture_summary") if isinstance(record.get("capture_summary"), Mapping) else {}
    rows.extend(_capture_rows_from_summary(capture_summary, source=source))
    summaries = record.get("iteration_summaries")
    if isinstance(summaries, list):
        for summary in summaries:
            if not isinstance(summary, Mapping):
                continue
            capture_summary = summary.get("capture_summary") if isinstance(summary.get("capture_summary"), Mapping) else {}
            rows.extend(_capture_rows_from_summary(capture_summary, source=source))
    return rows


def _capture_rows_from_summary(capture_summary: Mapping[str, Any], *, source: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("captured_candidates", "captures", "captured_rows"):
        value = capture_summary.get(key)
        if isinstance(value, list):
            rows.extend({**dict(row), "source": source} for row in value if isinstance(row, Mapping))
    examples = capture_summary.get("candidate_examples_by_lane")
    if isinstance(examples, Mapping):
        for lane_rows in examples.values():
            if isinstance(lane_rows, list):
                rows.extend({**dict(row), "source": source} for row in lane_rows if isinstance(row, Mapping))
    return rows


def _dedupe_captures(captures: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in captures:
        key = (
            row.get("candidate_id")
            or row.get("capture_id")
            or row.get("source_capture_id")
            or f"{row.get('lane_key')}|{row.get('timestamp') or row.get('signal_timestamp') or row.get('captured_at')}"
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(_sanitize(dict(row)))
    return deduped


def _latest_capture_for_timeframe(captures: Sequence[Mapping[str, Any]], timeframe: str) -> dict[str, Any]:
    for row in captures:
        lane_key = str(row.get("lane_key") or "")
        if str(row.get("timeframe") or "").lower() == timeframe.lower() or f"|{timeframe.lower()}|" in lane_key.lower():
            return dict(row)
    return {}


def _latest_signal_for_timeframe(signals: Sequence[Mapping[str, Any]], timeframe: str) -> dict[str, Any]:
    for row in reversed(list(signals)):
        if str(row.get("timeframe") or "").lower() == timeframe.lower():
            return dict(row)
    return {}


def _lane_key(row: Mapping[str, Any], *, timeframe: str) -> str:
    lane_key = row.get("lane_key")
    if lane_key:
        return str(lane_key)
    symbol = row.get("symbol") or DEFAULT_SYMBOL
    direction = row.get("direction") or row.get("original_direction") or "aggregate"
    entry_mode = row.get("entry_mode") or DEFAULT_ENTRY_MODE
    return f"{symbol}|{timeframe}|{direction}|{entry_mode}"


def _signal_timestamp(row: Mapping[str, Any]) -> str | None:
    value = (
        row.get("signal_timestamp")
        or row.get("timestamp")
        or row.get("source_timestamp")
        or row.get("captured_at")
        or row.get("created_at")
        or row.get("generated_at")
    )
    return str(value) if value else None


def _normal_direction(value: Any) -> str | None:
    lowered = str(value or "").lower()
    if lowered in {"long", "short"}:
        return lowered
    return None


def _seed_why(
    *,
    candidate: str,
    direction_context: str,
    schema: Mapping[str, Any],
    capture: bool,
    true_paper_outcomes: Sequence[Mapping[str, Any]],
) -> str:
    if direction_context == "direction_specific" and schema.get("schema_complete"):
        return f"{candidate} has direction-specific schema for future paper outcome tracking; it still cannot count as a validated sample now."
    if capture:
        return f"{candidate} has a local full-spectrum capture seed, but capture rows are not resolved outcomes and cannot validate betrayal now."
    if true_paper_outcomes:
        return f"{candidate} can inherit local betrayal context, but R212 does not fabricate or reclassify historical outcomes."
    return f"{candidate} is aggregate context only and needs direction split before validated future samples can be counted."


def _top_level_status(
    *,
    record_tracker: bool,
    confirmation_valid: bool,
    seed_candidates: Sequence[Mapping[str, Any]],
) -> str:
    if record_tracker and not confirmation_valid:
        return BETRAYAL_EVENT_TRACKER_REJECTED
    if not seed_candidates:
        return BETRAYAL_EVENT_TRACKER_BLOCKED
    if record_tracker and confirmation_valid:
        return BETRAYAL_EVENT_TRACKER_RECORDED
    return BETRAYAL_EVENT_TRACKER_READY


def _recommended_next_operator_move(gap_report: Mapping[str, Any], tracker_status: str) -> str:
    if tracker_status == BETRAYAL_EVENT_TRACKING_APPEND_ONLY_READY:
        return "RUN_R214_BETRAYAL_EVENT_OUTCOME_RESOLVER"
    if gap_report.get("direction_split_missing"):
        return "RUN_R213_BETRAYAL_REGIME_MIRO_RECHECK"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("direction_split_missing"):
        return "Build R213 betrayal regime/Miro recheck and preserve direction split requirements for R214 resolver."
    return "Build R214 betrayal event outcome resolver for future paper outcomes only; do not authorize live."


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


def _empty_gap_report() -> dict[str, Any]:
    return {
        "direction_split_missing": True,
        "entry_mode_missing": True,
        "timestamp_missing": True,
        "outcome_window_missing": False,
        "aggregate_context_only_count": 0,
        "schema_incomplete_count": 0,
        "required_for_validated_future_samples": [
            "original_direction",
            "inverse_direction",
            "entry_mode",
            "signal_timestamp",
            "declared_outcome_window",
        ],
    }


def _latest_record(path: Path) -> dict[str, Any]:
    records = _read_recent(path, limit=1)
    return records[0] if records else {}


def _read_recent(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]
    except Exception:
        records = _read_ndjson(path)
        return list(reversed(records[-limit:]))


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(_sanitize(payload))
    return records


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize(child) for child in value]
    if isinstance(value, tuple):
        return [_sanitize(child) for child in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
