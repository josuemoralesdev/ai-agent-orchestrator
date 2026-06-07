"""R223 betrayal source identity normalizer.

Paper-only preview and append-only audit for normalizing betrayal source
identity fields when existing local evidence supports them. This module never
mutates env/config/lane/risk files, calls Binance/network, creates order
payloads, promotes betrayal, or authorizes live execution.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_event_tracker import build_betrayal_event_identity
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.registry_wiring_betrayal_source_family import (
    build_registry_backed_betrayal_candidate_view,
    validate_betrayal_source_row_against_registry,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import validate_registry_entry

BETRAYAL_SOURCE_IDENTITY_NORMALIZER_READY = "BETRAYAL_SOURCE_IDENTITY_NORMALIZER_READY"
BETRAYAL_SOURCE_IDENTITY_NORMALIZER_REJECTED = "BETRAYAL_SOURCE_IDENTITY_NORMALIZER_REJECTED"
BETRAYAL_SOURCE_IDENTITY_NORMALIZER_RECORDED = "BETRAYAL_SOURCE_IDENTITY_NORMALIZER_RECORDED"
BETRAYAL_SOURCE_IDENTITY_NORMALIZER_BLOCKED = "BETRAYAL_SOURCE_IDENTITY_NORMALIZER_BLOCKED"
BETRAYAL_SOURCE_IDENTITY_NORMALIZER_ERROR = "BETRAYAL_SOURCE_IDENTITY_NORMALIZER_ERROR"

SOURCE_IDENTITY_NORMALIZED_ROWS_READY = "SOURCE_IDENTITY_NORMALIZED_ROWS_READY"
SOURCE_IDENTITY_PARTIAL_NORMALIZATION = "SOURCE_IDENTITY_PARTIAL_NORMALIZATION"
SOURCE_IDENTITY_ENTRY_MODE_BLOCKED = "SOURCE_IDENTITY_ENTRY_MODE_BLOCKED"
SOURCE_IDENTITY_IDENTITY_BLOCKED = "SOURCE_IDENTITY_IDENTITY_BLOCKED"
SOURCE_IDENTITY_NO_RESOLVER_READY_ROWS = "SOURCE_IDENTITY_NO_RESOLVER_READY_ROWS"
SOURCE_IDENTITY_NOT_LIVE_AUTHORIZED = "SOURCE_IDENTITY_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_SOURCE_IDENTITY_NORMALIZER"
LEDGER_FILENAME = "betrayal_source_identity_normalizer.ndjson"
SCHEMA_VERSION = "betrayal_source_emitter_v2"
SOURCE_TYPE = "betrayal_source_emitter"
DEFAULT_SYMBOL = "BTCUSDT"
OUTCOME_WINDOWS = [1, 3, 5, 10, 21, 34, 55]
CONFIRM_BETRAYAL_SOURCE_IDENTITY_NORMALIZER_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL SOURCE IDENTITY NORMALIZER RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

NORMALIZER_READY = "normalizer_ready"
PARTIAL_NORMALIZATION = "partial_normalization"
BLOCKED_MISSING_IDENTITY = "blocked_missing_identity"
BLOCKED_MISSING_ENTRY_MODE = "blocked_missing_entry_mode"
BLOCKED_AGGREGATE_CONTEXT_ONLY = "blocked_aggregate_context_only"

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
    "logs/hammer_radar_forward/strategy_evidence_registry.ndjson",
    "logs/hammer_radar_forward/betrayal_registry_consumer_refactor.ndjson",
    "logs/hammer_radar_forward/registry_wiring_betrayal_source_family.ndjson",
    "logs/hammer_radar_forward/betrayal_aggregate_decomposition.ndjson",
    "logs/hammer_radar_forward/betrayal_source_emitter_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_direction_split_resolver.ndjson",
    "logs/hammer_radar_forward/betrayal_event_tracker.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_source_identity_normalizer(
    *,
    log_dir: str | Path | None = None,
    record_normalizer: bool = False,
    confirm_betrayal_source_identity_normalizer: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_source_identity_normalizer
        == CONFIRM_BETRAYAL_SOURCE_IDENTITY_NORMALIZER_RECORDING_PHRASE
    )
    try:
        registry = load_latest_strategy_evidence_registry(log_dir=resolved_log_dir)
        consumer_refactor = load_latest_betrayal_registry_consumer_refactor(log_dir=resolved_log_dir)
        registry_wiring = load_latest_registry_wiring_betrayal_source_family(log_dir=resolved_log_dir)
        aggregate = load_latest_betrayal_aggregate_decomposition(log_dir=resolved_log_dir)
        source_refresh = load_latest_betrayal_source_emitter_refresh(log_dir=resolved_log_dir)
        direction_split = load_latest_betrayal_direction_split_resolver(log_dir=resolved_log_dir)
        event_tracker = load_latest_betrayal_event_tracker(log_dir=resolved_log_dir)
        manifest = _registry_manifest(registry)
        registry_validation = _registry_validation(registry, manifest)
        rows = build_normalized_source_rows_preview(
            strategy_evidence_registry=registry,
            registry_wiring_betrayal_source_family=registry_wiring,
            betrayal_aggregate_decomposition=aggregate,
            betrayal_source_emitter_refresh=source_refresh,
            betrayal_direction_split_resolver=direction_split,
            betrayal_event_tracker=event_tracker,
            generated_at=generated_at,
        )
        summary = _normalization_summary(rows)
        gap_report = build_source_identity_normalizer_gap_report(rows)
        recommendations = build_source_identity_normalizer_recommendations(gap_report=gap_report, rows=rows)
        normalizer_status = classify_betrayal_source_identity_normalizer_status(rows=rows, gap_report=gap_report)
        payload = {
            "status": _top_level_status(
                record_normalizer=record_normalizer,
                confirmation_valid=confirmation_valid,
                registry_valid=bool(registry_validation.get("valid")),
            ),
            "generated_at": generated_at.isoformat(),
            "normalizer_recorded": False,
            "normalizer_id": None,
            "record_normalizer_requested": bool(record_normalizer),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "family": "betrayal",
                "registry_backed": True,
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "strategy_evidence_registry_found": bool(registry),
                "registry_valid": bool(registry_validation.get("valid")),
                "registry_wiring_found": bool(registry_wiring),
                "consumer_refactor_found": bool(consumer_refactor),
                "aggregate_decomposition_found": bool(aggregate),
                "source_emitter_refresh_found": bool(source_refresh),
                "direction_split_resolver_found": bool(direction_split),
                "event_tracker_found": bool(event_tracker),
            },
            "normalized_source_rows_preview": rows,
            "normalization_summary": summary,
            "source_identity_normalizer_gap_report": gap_report,
            "source_identity_normalizer_recommendations": recommendations,
            "normalizer_status": normalizer_status,
            "recommended_next_operator_move": _recommended_next_operator_move(normalizer_status, summary),
            "recommended_next_engineering_move": _recommended_next_engineering_move(normalizer_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_normalizer and confirmation_valid and registry_validation.get("valid"):
            record = append_betrayal_source_identity_normalizer_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_SOURCE_IDENTITY_NORMALIZER_RECORDED
            payload["normalizer_recorded"] = True
            payload["normalizer_id"] = record["normalizer_id"]
            payload["ledger_path"] = str(betrayal_source_identity_normalizer_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_SOURCE_IDENTITY_NORMALIZER_ERROR,
                "generated_at": generated_at.isoformat(),
                "normalizer_recorded": False,
                "normalizer_id": None,
                "record_normalizer_requested": bool(record_normalizer),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {"family": "betrayal", "registry_backed": True, "paper_only": True, "live_authorized": False},
                "input_summary": {},
                "normalized_source_rows_preview": [],
                "normalization_summary": _normalization_summary([]),
                "source_identity_normalizer_gap_report": build_source_identity_normalizer_gap_report([]),
                "source_identity_normalizer_recommendations": [],
                "normalizer_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R223 normalizer error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_strategy_evidence_registry(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "strategy_evidence_registry.ndjson")


def load_latest_betrayal_registry_consumer_refactor(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_registry_consumer_refactor.ndjson")


def load_latest_registry_wiring_betrayal_source_family(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "registry_wiring_betrayal_source_family.ndjson")


def load_latest_betrayal_aggregate_decomposition(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_aggregate_decomposition.ndjson")


def load_latest_betrayal_source_emitter_refresh(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_source_emitter_refresh.ndjson")


def load_latest_betrayal_direction_split_resolver(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_direction_split_resolver.ndjson")


def load_latest_betrayal_event_tracker(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_event_tracker.ndjson")


def extract_entry_mode_from_lane_key(lane_key: Any, *, allowed_entry_modes: Sequence[str] | None = None) -> str | None:
    parts = [part.strip() for part in str(lane_key or "").split("|")]
    if len(parts) < 4:
        return None
    candidate = parts[3].lower()
    allowed = {str(item).strip().lower() for item in allowed_entry_modes or [] if str(item).strip()}
    if allowed and candidate not in allowed:
        return None
    return candidate or None


def build_deterministic_source_identity(
    *,
    symbol: Any = None,
    timeframe: Any = None,
    direction: Any = None,
    entry_mode: Any = None,
    timestamp: Any = None,
    source_family: Any = None,
) -> str | None:
    fields = {
        "symbol": _string_or_none(symbol),
        "timeframe": _string_or_none(timeframe),
        "direction": _normal_direction(direction),
        "entry_mode": _string_or_none(entry_mode),
        "timestamp": _string_or_none(timestamp),
        "source_family": _string_or_none(source_family),
    }
    if any(not value for value in fields.values()):
        return None
    stable = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
    return (
        f"betrayal_source|{fields['symbol']}|{fields['timeframe']}|{fields['direction']}|"
        f"{fields['entry_mode']}|{fields['timestamp']}|{fields['source_family']}|{digest}"
    )


def normalize_betrayal_source_row(
    row: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
    source: str,
    generated_at: datetime | str | None = None,
) -> dict[str, Any]:
    allowed_entry_modes = _allowed_entry_modes(registry_manifest, include_placeholders=False)
    normalized: dict[str, Any] = {**dict(row)}
    sources_used: list[str] = []
    normalized["source"] = source
    normalized["schema_version"] = _string_or_none(normalized.get("schema_version")) or SCHEMA_VERSION
    normalized["source_type"] = _string_or_none(normalized.get("source_type")) or SOURCE_TYPE
    normalized["candidate"] = _candidate_label(normalized)
    normalized["symbol"] = _string_or_none(normalized.get("symbol")) or DEFAULT_SYMBOL
    normalized["timeframe"] = _string_or_none(normalized.get("timeframe")) or _candidate_timeframe(normalized.get("candidate"))
    entry_mode = _string_or_none(normalized.get("entry_mode"))
    if entry_mode:
        entry_mode = entry_mode.lower()
        sources_used.append("entry_mode")
    if not entry_mode:
        entry_mode = extract_entry_mode_from_lane_key(normalized.get("lane_key"), allowed_entry_modes=allowed_entry_modes)
        if entry_mode:
            sources_used.append("lane_key.entry_mode")
    if not entry_mode:
        entry_mode = _entry_mode_from_source_signal_id(normalized.get("source_signal_id"), allowed_entry_modes=allowed_entry_modes)
        if entry_mode:
            sources_used.append("source_signal_id.entry_mode")
    normalized["entry_mode"] = entry_mode
    original = _normal_direction(normalized.get("original_direction"))
    inverse = _normal_direction(normalized.get("inverse_direction") or normalized.get("betrayal_direction"))
    normalized["original_direction"] = original
    normalized["inverse_direction"] = inverse
    if not normalized.get("emitted_direction") and inverse:
        normalized["emitted_direction"] = inverse
        sources_used.append("inverse_direction.emitted_direction")
    else:
        normalized["emitted_direction"] = _normal_direction(normalized.get("emitted_direction"))
    source_signal_id = _first_string(normalized, "source_signal_id", "signal_id")
    source_capture_id = _first_string(normalized, "source_capture_id", "capture_id", "candidate_id")
    emitted_signal_id = _first_string(normalized, "emitted_signal_id")
    signal_timestamp = _first_string(normalized, "source_signal_timestamp", "signal_timestamp", "timestamp", "emitted_at")
    if not source_signal_id and source_capture_id:
        source_signal_id = source_capture_id
        sources_used.append("source_capture_id.source_signal_id")
    normalized["source_signal_id"] = source_signal_id
    normalized["source_signal_timestamp"] = signal_timestamp
    if not emitted_signal_id and source_signal_id and inverse and entry_mode:
        emitted_signal_id = f"betrayal_emitted|{source_signal_id}|{inverse}|{entry_mode}"
        sources_used.append("source_signal_id.emitted_signal_id")
    normalized["emitted_signal_id"] = emitted_signal_id
    source_identity = _first_string(normalized, "source_identity")
    if source_identity:
        sources_used.append("source_identity")
    elif source_signal_id:
        source_identity = source_signal_id
        sources_used.append("source_signal_id.source_identity")
    elif source_capture_id:
        source_identity = source_capture_id
        sources_used.append("source_capture_id.source_identity")
    elif emitted_signal_id:
        source_identity = emitted_signal_id
        sources_used.append("emitted_signal_id.source_identity")
    else:
        source_identity = build_deterministic_source_identity(
            symbol=normalized.get("symbol"),
            timeframe=normalized.get("timeframe"),
            direction=original or _normal_direction(normalized.get("source_direction")) or normalized.get("emitted_direction"),
            entry_mode=entry_mode,
            timestamp=signal_timestamp,
            source_family=_source_family(normalized, source),
        )
        if source_identity:
            sources_used.append("deterministic_source_identity")
    normalized["source_identity"] = source_identity
    normalized["lane_key"] = _string_or_none(normalized.get("lane_key")) or _build_lane_key(normalized)
    normalized["outcome_windows"] = list(normalized.get("outcome_windows") or OUTCOME_WINDOWS)
    normalized["emitted_at"] = _string_or_none(normalized.get("emitted_at")) or _generated_at_iso(generated_at)
    identity = build_betrayal_event_identity(
        symbol=normalized.get("symbol"),
        timeframe=normalized.get("timeframe"),
        candidate_label=normalized.get("candidate"),
        original_direction=original,
        inverse_direction=inverse,
        entry_mode=entry_mode,
        source_signal_id=source_signal_id,
        source_capture_id=source_capture_id,
        signal_timestamp=signal_timestamp,
        event_timeframe=normalized.get("timeframe"),
        outcome_window=normalized.get("outcome_windows"),
    )
    normalized["betrayal_event_identity"] = _string_or_none(normalized.get("betrayal_event_identity")) or identity["event_identity"]
    normalized["betrayal_event_identity_hash"] = (
        _string_or_none(normalized.get("betrayal_event_identity_hash")) or identity["event_identity_hash"]
    )
    normalized["paper_only"] = True
    normalized["live_authorized"] = False
    normalized["promotion_allowed"] = False
    validation = validate_normalized_row_against_registry(normalized, registry_manifest=registry_manifest)
    missing = list(validation.get("missing_required_fields") or [])
    aggregate_context_only = _aggregate_context_only(normalized)
    normalization_status = _row_normalization_status(
        missing=missing,
        validation=validation,
        aggregate_context_only=aggregate_context_only,
    )
    return _sanitize(
        {
            "candidate": normalized.get("candidate"),
            "source": source,
            "schema_version": SCHEMA_VERSION,
            "source_type": SOURCE_TYPE,
            "symbol": normalized.get("symbol"),
            "timeframe": normalized.get("timeframe"),
            "entry_mode": normalized.get("entry_mode"),
            "original_direction": normalized.get("original_direction"),
            "inverse_direction": normalized.get("inverse_direction"),
            "emitted_direction": normalized.get("emitted_direction"),
            "source_identity": normalized.get("source_identity"),
            "source_signal_id": normalized.get("source_signal_id"),
            "emitted_signal_id": normalized.get("emitted_signal_id"),
            "source_signal_timestamp": normalized.get("source_signal_timestamp"),
            "emitted_at": normalized.get("emitted_at"),
            "lane_key": normalized.get("lane_key"),
            "betrayal_event_identity": normalized.get("betrayal_event_identity"),
            "betrayal_event_identity_hash": normalized.get("betrayal_event_identity_hash"),
            "outcome_windows": normalized.get("outcome_windows"),
            "schema_complete": bool(validation.get("schema_complete")),
            "registry_valid": bool(validation.get("schema_complete")),
            "resolver_ready": bool(_resolver_ready(normalized, validation, registry_manifest=registry_manifest)),
            "normalization_status": normalization_status,
            "missing_required_fields": missing,
            "normalization_sources_used": _dedupe(sources_used),
            "paper_only": True,
            "live_authorized": False,
            "promotion_allowed": False,
            "why": _normalization_why(normalization_status, missing),
        }
    )


def validate_normalized_row_against_registry(
    row: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    validation = validate_betrayal_source_row_against_registry(row, registry_manifest=registry_manifest)
    missing = list(validation.get("missing_required_fields") or [])
    if row.get("emitted_direction") != row.get("inverse_direction") and "emitted_direction_equals_inverse_direction" not in missing:
        missing.append("emitted_direction_equals_inverse_direction")
    if row.get("paper_only") is not True and "paper_only_true" not in missing:
        missing.append("paper_only_true")
    if row.get("live_authorized") is not False and "live_authorized_false" not in missing:
        missing.append("live_authorized_false")
    if row.get("promotion_allowed") is not False and "promotion_allowed_false" not in missing:
        missing.append("promotion_allowed_false")
    schema_complete = not missing
    return _sanitize(
        {
            **dict(validation),
            "schema_complete": schema_complete,
            "row_status": "registry_valid" if schema_complete else "blocked_missing_fields",
            "missing_required_fields": _dedupe(missing),
            "blocked_from_resolver": not schema_complete,
        }
    )


def build_normalized_source_rows_preview(
    *,
    strategy_evidence_registry: Mapping[str, Any],
    registry_wiring_betrayal_source_family: Mapping[str, Any],
    betrayal_aggregate_decomposition: Mapping[str, Any],
    betrayal_source_emitter_refresh: Mapping[str, Any],
    betrayal_direction_split_resolver: Mapping[str, Any],
    betrayal_event_tracker: Mapping[str, Any],
    generated_at: datetime | str | None = None,
) -> list[dict[str, Any]]:
    del registry_wiring_betrayal_source_family
    manifest = _registry_manifest(strategy_evidence_registry)
    raw_rows = _collect_source_rows(
        aggregate_decomposition=betrayal_aggregate_decomposition,
        source_emitter_refresh=betrayal_source_emitter_refresh,
        direction_split_resolver=betrayal_direction_split_resolver,
        event_tracker=betrayal_event_tracker,
    )
    rows = [
        normalize_betrayal_source_row(row, registry_manifest=manifest, source=str(row.get("_source") or "unknown"), generated_at=generated_at)
        for row in raw_rows
    ]
    return _dedupe_normalized_rows(rows)


def build_source_identity_normalizer_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "missing_entry_mode_rows": sum(1 for row in rows if "entry_mode" in (row.get("missing_required_fields") or [])),
        "missing_source_identity_rows": sum(1 for row in rows if "source_identity" in (row.get("missing_required_fields") or [])),
        "missing_direction_rows": sum(
            1
            for row in rows
            if any(field in (row.get("missing_required_fields") or []) for field in ("original_direction", "inverse_direction", "emitted_direction"))
        ),
        "registry_invalid_rows": sum(1 for row in rows if not row.get("registry_valid")),
        "resolver_ready_rows": sum(1 for row in rows if row.get("resolver_ready")),
        "hard_live_blockers": _hard_live_blockers(),
    }


def build_source_identity_normalizer_recommendations(
    *,
    gap_report: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    if gap_report.get("resolver_ready_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "APPEND_NORMALIZED_V2_ROWS",
                "future_phase": "R224",
                "why": "At least one normalized paper-only row satisfies betrayal_source_emitter_v2 and registry validation.",
            }
        )
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "RUN_R214_EVENT_OUTCOME_RESOLVER",
                "future_phase": "R214",
                "why": "Resolver-ready normalized rows may be reviewed by the paper-only event outcome resolver after append.",
            }
        )
    if gap_report.get("missing_source_identity_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "COLLECT_MORE_SOURCE_IDENTITY",
                "future_phase": "R224",
                "why": "Rows without explicit source ids or deterministic local source identity inputs remain blocked.",
            }
        )
    if gap_report.get("missing_entry_mode_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "COLLECT_MORE_SOURCE_IDENTITY",
                "future_phase": "R224",
                "why": "Rows without explicit entry_mode evidence remain blocked; common ladder mode is not used as proof.",
            }
        )
    if rows:
        recommendations.append(
            {
                "priority": "LOW",
                "recommended_action": "KEEP_CONTEXT_ONLY",
                "future_phase": "R223",
                "why": "R223 is normalization preview only and cannot promote betrayal or authorize live execution.",
            }
        )
    return recommendations


def classify_betrayal_source_identity_normalizer_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if gap_report.get("resolver_ready_rows"):
        return SOURCE_IDENTITY_NORMALIZED_ROWS_READY
    if gap_report.get("missing_entry_mode_rows"):
        return SOURCE_IDENTITY_ENTRY_MODE_BLOCKED
    if gap_report.get("missing_source_identity_rows"):
        return SOURCE_IDENTITY_IDENTITY_BLOCKED
    if any(row.get("normalization_status") == PARTIAL_NORMALIZATION for row in rows):
        return SOURCE_IDENTITY_PARTIAL_NORMALIZATION
    if gap_report.get("registry_invalid_rows"):
        return SOURCE_IDENTITY_NO_RESOLVER_READY_ROWS
    return SOURCE_IDENTITY_NOT_LIVE_AUTHORIZED


def append_betrayal_source_identity_normalizer_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_source_identity_normalizer_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "normalizer_id": str(record.get("normalizer_id") or f"r223_betrayal_source_identity_normalizer_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_SOURCE_IDENTITY_NORMALIZER_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_normalizer_requested": bool(record.get("record_normalizer_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "normalized_source_rows_preview": list(record.get("normalized_source_rows_preview") or []),
            "normalization_summary": dict(record.get("normalization_summary") or {}),
            "source_identity_normalizer_gap_report": dict(record.get("source_identity_normalizer_gap_report") or {}),
            "source_identity_normalizer_recommendations": list(record.get("source_identity_normalizer_recommendations") or []),
            "normalizer_status": record.get("normalizer_status"),
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


def load_betrayal_source_identity_normalizer_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_source_identity_normalizer_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_betrayal_source_identity_normalizer_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    summary = latest.get("normalization_summary") if isinstance(latest.get("normalization_summary"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "normalizer_status_counts": dict(
            sorted(Counter(str(record.get("normalizer_status") or "UNKNOWN") for record in records).items())
        ),
        "last_normalizer_id": latest.get("normalizer_id") if isinstance(latest, Mapping) else None,
        "last_rows_reviewed": summary.get("rows_reviewed"),
        "last_resolver_ready_rows": summary.get("resolver_ready_rows"),
        "safety": dict(SAFETY),
    }


def betrayal_source_identity_normalizer_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_source_identity_normalizer_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _collect_source_rows(
    *,
    aggregate_decomposition: Mapping[str, Any],
    source_emitter_refresh: Mapping[str, Any],
    direction_split_resolver: Mapping[str, Any],
    event_tracker: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("decomposition_rows", "v2_source_rows_preview"):
        rows.extend(_tagged_rows(aggregate_decomposition.get(key), "aggregate_decomposition"))
    for key in ("source_candidate_rows", "direction_specific_source_preview"):
        rows.extend(_tagged_rows(source_emitter_refresh.get(key), "source_emitter_refresh"))
    rows.extend(_tagged_rows(direction_split_resolver.get("direction_split_resolution_rows"), "direction_split_resolver"))
    for key in ("event_tracker_records_preview", "event_seed_candidates"):
        rows.extend(_tagged_rows(event_tracker.get(key), "event_tracker"))
    return rows


def _tagged_rows(value: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [_sanitize({**dict(row), "_source": source}) for row in value if isinstance(row, Mapping)]


def _normalization_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "rows_reviewed": len(rows),
        "rows_normalized": sum(1 for row in rows if row.get("normalization_status") == NORMALIZER_READY),
        "resolver_ready_rows": sum(1 for row in rows if row.get("resolver_ready")),
        "partial_rows": sum(1 for row in rows if row.get("normalization_status") == PARTIAL_NORMALIZATION),
        "blocked_rows": sum(1 for row in rows if str(row.get("normalization_status") or "").startswith("blocked_")),
        "entry_mode_filled_count": sum(1 for row in rows if "lane_key.entry_mode" in (row.get("normalization_sources_used") or [])),
        "source_identity_filled_count": sum(
            1
            for row in rows
            if any(
                source in (row.get("normalization_sources_used") or [])
                for source in (
                    "source_signal_id.source_identity",
                    "source_capture_id.source_identity",
                    "emitted_signal_id.source_identity",
                    "deterministic_source_identity",
                )
            )
        ),
        "emitted_signal_id_filled_count": sum(
            1 for row in rows if "source_signal_id.emitted_signal_id" in (row.get("normalization_sources_used") or [])
        ),
    }


def _resolver_ready(row: Mapping[str, Any], validation: Mapping[str, Any], *, registry_manifest: Mapping[str, Any]) -> bool:
    if not validation.get("schema_complete"):
        return False
    if row.get("paper_only") is not True or row.get("live_authorized") is not False or row.get("promotion_allowed") is not False:
        return False
    if not _registry_candidate_for(row, registry_manifest=registry_manifest):
        return False
    entry = _entry_mode_map(registry_manifest).get(str(row.get("entry_mode") or ""))
    if not entry or entry.get("blocked_placeholder"):
        return False
    return row.get("emitted_direction") == row.get("inverse_direction")


def _row_normalization_status(
    *,
    missing: Sequence[str],
    validation: Mapping[str, Any],
    aggregate_context_only: bool,
) -> str:
    if aggregate_context_only:
        return BLOCKED_AGGREGATE_CONTEXT_ONLY
    if "entry_mode" in missing or "entry_mode_blocked_placeholder" in missing:
        return BLOCKED_MISSING_ENTRY_MODE
    if "source_identity" in missing:
        return BLOCKED_MISSING_IDENTITY
    if validation.get("schema_complete"):
        return NORMALIZER_READY
    return PARTIAL_NORMALIZATION


def _normalization_why(status: str, missing: Sequence[str]) -> str:
    if status == NORMALIZER_READY:
        return "Local evidence supports all registry-required betrayal_source_emitter_v2 fields; row remains paper-only."
    if status == BLOCKED_AGGREGATE_CONTEXT_ONLY:
        return "Aggregate context is not treated as source identity or direction proof."
    if status == BLOCKED_MISSING_ENTRY_MODE:
        return "Entry mode is missing or blocked; common ladder mode was not fabricated."
    if status == BLOCKED_MISSING_IDENTITY:
        return "Source identity is missing and deterministic identity inputs are incomplete."
    return f"Partial normalization only; missing registry-required fields: {', '.join(missing)}."


def _top_level_status(*, record_normalizer: bool, confirmation_valid: bool, registry_valid: bool) -> str:
    if record_normalizer and not confirmation_valid:
        return BETRAYAL_SOURCE_IDENTITY_NORMALIZER_REJECTED
    if not registry_valid:
        return BETRAYAL_SOURCE_IDENTITY_NORMALIZER_BLOCKED
    return BETRAYAL_SOURCE_IDENTITY_NORMALIZER_READY


def _recommended_next_operator_move(normalizer_status: str, summary: Mapping[str, Any]) -> str:
    if normalizer_status == SOURCE_IDENTITY_NORMALIZED_ROWS_READY and summary.get("resolver_ready_rows"):
        return "RUN_R224_BETRAYAL_NORMALIZED_SOURCE_ROW_APPEND"
    if normalizer_status in {SOURCE_IDENTITY_PARTIAL_NORMALIZATION, SOURCE_IDENTITY_NO_RESOLVER_READY_ROWS}:
        return "RUN_R214_BETRAYAL_EVENT_OUTCOME_RESOLVER"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(normalizer_status: str, gap_report: Mapping[str, Any]) -> str:
    if normalizer_status == SOURCE_IDENTITY_NORMALIZED_ROWS_READY:
        return "Implement R224 append-only normalized v2 row writer guarded by resolver_ready rows."
    if gap_report.get("missing_source_identity_rows") or gap_report.get("missing_entry_mode_rows"):
        return "Collect explicit source identity and entry_mode evidence; do not infer from aggregate labels or common defaults."
    return "Keep R223 paper-only and review unresolved registry gaps before outcome resolution."


def _registry_manifest(registry: Mapping[str, Any]) -> dict[str, Any]:
    manifest = registry.get("registry_manifest") if isinstance(registry.get("registry_manifest"), Mapping) else registry
    return dict(manifest) if isinstance(manifest, Mapping) else {}


def _registry_validation(registry: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not registry or not manifest:
        return {"valid": False, "missing_required_sections": ["registry_manifest"]}
    if isinstance(registry.get("registry_validation"), Mapping):
        return dict(registry["registry_validation"])
    return validate_registry_entry(manifest)


def _allowed_entry_modes(registry_manifest: Mapping[str, Any], *, include_placeholders: bool) -> list[str]:
    rows = registry_manifest.get("entry_modes") if isinstance(registry_manifest, Mapping) else []
    allowed = []
    if isinstance(rows, Sequence) and not isinstance(rows, str):
        for row in rows:
            if not isinstance(row, Mapping) or not row.get("entry_mode"):
                continue
            if row.get("blocked_placeholder") and not include_placeholders:
                continue
            allowed.append(str(row["entry_mode"]).lower())
    return allowed


def _entry_mode_map(registry_manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = registry_manifest.get("entry_modes") if isinstance(registry_manifest, Mapping) else []
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        return {}
    return {str(row.get("entry_mode")): dict(row) for row in rows if isinstance(row, Mapping) and row.get("entry_mode")}


def _registry_candidate_for(row: Mapping[str, Any], *, registry_manifest: Mapping[str, Any]) -> dict[str, Any]:
    candidates = registry_manifest.get("betrayal_candidates") if isinstance(registry_manifest, Mapping) else {}
    if not isinstance(candidates, Mapping):
        return {}
    candidate = _candidate_id(str(row.get("candidate") or ""))
    candidate_id = _candidate_id(str(row.get("candidate_id") or ""))
    timeframe = str(row.get("timeframe") or "")
    for key, value in candidates.items():
        if not isinstance(value, Mapping):
            continue
        labels = {
            _candidate_id(str(key)),
            _candidate_id(str(value.get("candidate_id") or "")),
            _candidate_id(str(value.get("label") or "")),
            _candidate_id(str(value.get("label") or "")).replace("_if_available", ""),
        }
        if candidate in labels or candidate_id in labels:
            return dict(value)
        if timeframe and timeframe == str(value.get("timeframe") or "") and candidate.replace("_if_available", "") in labels:
            return dict(value)
    return {}


def _entry_mode_from_source_signal_id(source_signal_id: Any, *, allowed_entry_modes: Sequence[str]) -> str | None:
    text = str(source_signal_id or "")
    if not text:
        return None
    allowed = {str(item).lower() for item in allowed_entry_modes}
    parts = [part.strip().lower() for part in text.split("|")]
    for part in parts:
        if part in allowed:
            return part
    return None


def _build_lane_key(row: Mapping[str, Any]) -> str | None:
    direction = _normal_direction(row.get("emitted_direction") or row.get("inverse_direction") or row.get("source_direction"))
    values = [row.get("symbol"), row.get("timeframe"), direction, row.get("entry_mode")]
    if any(not _string_or_none(value) for value in values):
        return None
    return "|".join(str(value) for value in values)


def _candidate_label(row: Mapping[str, Any]) -> str | None:
    candidate = _string_or_none(row.get("candidate") or row.get("label"))
    if candidate:
        return candidate
    timeframe = _string_or_none(row.get("timeframe"))
    return f"{timeframe} aggregate" if timeframe else None


def _candidate_timeframe(candidate: Any) -> str | None:
    match = re.match(r"^([0-9]+[mhdMHD])", str(candidate or "").strip())
    return match.group(1) if match else None


def _source_family(row: Mapping[str, Any], source: str) -> str | None:
    return _string_or_none(row.get("source_family") or row.get("evidence_source") or row.get("source") or source)


def _aggregate_context_only(row: Mapping[str, Any]) -> bool:
    if row.get("normalization_status") == BLOCKED_AGGREGATE_CONTEXT_ONLY:
        return True
    if row.get("direction_context") == "aggregate_context_only" or row.get("not_direction_specific") is True:
        return True
    if str(row.get("why") or "").lower().find("aggregate context only") >= 0:
        return True
    return False


def _normal_direction(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"long", "bull", "bullish", "buy"}:
        return "long"
    if text in {"short", "bear", "bearish", "sell"}:
        return "short"
    return None


def _first_string(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _string_or_none(row.get(key))
        if value:
            return value
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _candidate_id(candidate: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", candidate.lower()).strip("_")


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_normalized_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("source") or ""),
            str(row.get("candidate") or ""),
            str(row.get("source_signal_id") or ""),
            str(row.get("source_identity") or ""),
            str(row.get("betrayal_event_identity_hash") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(_sanitize(dict(row)))
    return result


def _generated_at_iso(generated_at: datetime | str | None) -> str:
    if isinstance(generated_at, datetime):
        return generated_at.isoformat()
    return str(generated_at or datetime.now(UTC).isoformat())


def _hard_live_blockers() -> list[str]:
    return [
        "betrayal_not_live_authorized",
        "betrayal_not_promoted",
        "source_identity_normalizer_is_paper_only",
        "config_writes_forbidden",
        "orders_forbidden",
        "binance_calls_forbidden",
        "live_authorization_forbidden",
    ]


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


def _latest_record(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    records = read_recent_ndjson_records(path, limit=1, max_bytes=16_777_216)
    if not records:
        return {}
    return _sanitize(records[0])


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                records.append(_sanitize(value))
    return records


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, set):
        return sorted(_sanitize(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    return value
