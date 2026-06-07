"""R224A betrayal source identity evidence collector.

Paper-only evidence collection for betrayal source identity blockers. This
module reads local ledgers only, previews evidence candidates, and can append
only its own collector record after exact confirmation.
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
    validate_betrayal_source_row_against_registry,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import validate_registry_entry

BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_READY = "BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_READY"
BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_REJECTED = "BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_REJECTED"
BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_RECORDED = "BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_RECORDED"
BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_BLOCKED = "BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_BLOCKED"
BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_ERROR = "BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_ERROR"

SOURCE_IDENTITY_EVIDENCE_FOUND = "SOURCE_IDENTITY_EVIDENCE_FOUND"
SOURCE_IDENTITY_EVIDENCE_PARTIAL = "SOURCE_IDENTITY_EVIDENCE_PARTIAL"
SOURCE_IDENTITY_EVIDENCE_INSUFFICIENT = "SOURCE_IDENTITY_EVIDENCE_INSUFFICIENT"
SOURCE_IDENTITY_ENTRY_MODE_STILL_BLOCKED = "SOURCE_IDENTITY_ENTRY_MODE_STILL_BLOCKED"
SOURCE_IDENTITY_READY_FOR_NORMALIZED_APPEND_PREVIEW = "SOURCE_IDENTITY_READY_FOR_NORMALIZED_APPEND_PREVIEW"
SOURCE_IDENTITY_NOT_LIVE_AUTHORIZED = "SOURCE_IDENTITY_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR"
LEDGER_FILENAME = "betrayal_source_identity_evidence_collector.ndjson"
SCHEMA_VERSION = "betrayal_source_emitter_v2"
SOURCE_TYPE = "betrayal_source_emitter"
DEFAULT_SYMBOL = "BTCUSDT"
OUTCOME_WINDOWS = [1, 3, 5, 10, 21, 34, 55]
CONFIRM_BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL SOURCE IDENTITY EVIDENCE COLLECTOR RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "logs/hammer_radar_forward/betrayal_source_identity_normalizer.ndjson",
    "logs/hammer_radar_forward/betrayal_registry_consumer_refactor.ndjson",
    "logs/hammer_radar_forward/registry_wiring_betrayal_source_family.ndjson",
    "logs/hammer_radar_forward/strategy_evidence_registry.ndjson",
    "logs/hammer_radar_forward/betrayal_aggregate_decomposition.ndjson",
    "logs/hammer_radar_forward/betrayal_source_emitter_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_direction_split_resolver.ndjson",
    "logs/hammer_radar_forward/betrayal_event_tracker.ndjson",
    "logs/hammer_radar_forward/betrayal_true_inverse_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_integration_recheck.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_resolutions.ndjson",
    "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_signals.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_heartbeats.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_source_identity_evidence_collector(
    *,
    log_dir: str | Path | None = None,
    record_collector: bool = False,
    confirm_betrayal_source_identity_evidence_collector: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_source_identity_evidence_collector
        == CONFIRM_BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_RECORDING_PHRASE
    )
    try:
        normalizer = load_latest_betrayal_source_identity_normalizer(log_dir=resolved_log_dir)
        registry = load_latest_strategy_evidence_registry(log_dir=resolved_log_dir)
        consumer_refactor = _latest_record(resolved_log_dir / "betrayal_registry_consumer_refactor.ndjson")
        registry_wiring = load_latest_registry_wiring_betrayal_source_family(log_dir=resolved_log_dir)
        aggregate = load_latest_betrayal_aggregate_decomposition(log_dir=resolved_log_dir)
        source_refresh = load_latest_betrayal_source_emitter_refresh(log_dir=resolved_log_dir)
        direction_split = load_latest_betrayal_direction_split_resolver(log_dir=resolved_log_dir)
        event_tracker = load_latest_betrayal_event_tracker(log_dir=resolved_log_dir)
        true_inverse = _latest_record(resolved_log_dir / "betrayal_true_inverse_refresh.ndjson")
        integration_recheck = _latest_record(resolved_log_dir / "betrayal_integration_recheck.ndjson")
        full_spectrum = load_full_spectrum_capture_records(log_dir=resolved_log_dir)
        full_spectrum_heartbeats = _read_ndjson(resolved_log_dir / "full_spectrum_harvester_heartbeats.ndjson")
        shadow_outcomes = load_betrayal_shadow_outcomes(log_dir=resolved_log_dir)
        paper_signals = load_betrayal_paper_signals(log_dir=resolved_log_dir)
        manifest = _registry_manifest(registry)
        registry_validation = _registry_validation(registry, manifest)
        rows = build_source_identity_evidence_rows(
            strategy_evidence_registry=registry,
            betrayal_source_identity_normalizer=normalizer,
            registry_wiring_betrayal_source_family=registry_wiring,
            betrayal_aggregate_decomposition=aggregate,
            betrayal_source_emitter_refresh=source_refresh,
            betrayal_direction_split_resolver=direction_split,
            betrayal_event_tracker=event_tracker,
            full_spectrum_capture_records=full_spectrum,
            betrayal_shadow_outcomes=shadow_outcomes,
            betrayal_paper_signals=paper_signals,
            generated_at=generated_at,
        )
        summary = build_source_identity_evidence_summary(rows)
        gap_report = build_source_identity_evidence_gap_report(rows)
        recommendations = build_source_identity_evidence_recommendations(gap_report=gap_report, summary=summary)
        evidence_status = classify_betrayal_source_identity_evidence_status(rows=rows, gap_report=gap_report)
        payload = {
            "status": _top_level_status(
                record_collector=record_collector,
                confirmation_valid=confirmation_valid,
                registry_valid=bool(registry_validation.get("valid")),
            ),
            "generated_at": generated_at.isoformat(),
            "collector_recorded": False,
            "collector_id": None,
            "record_collector_requested": bool(record_collector),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "family": "betrayal",
                "registry_backed": True,
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "normalizer_found": bool(normalizer),
                "registry_found": bool(registry),
                "registry_valid": bool(registry_validation.get("valid")),
                "consumer_refactor_found": bool(consumer_refactor),
                "registry_wiring_found": bool(registry_wiring),
                "aggregate_decomposition_found": bool(aggregate),
                "source_emitter_refresh_found": bool(source_refresh),
                "direction_split_resolver_found": bool(direction_split),
                "event_tracker_found": bool(event_tracker),
                "true_inverse_refresh_found": bool(true_inverse),
                "integration_recheck_found": bool(integration_recheck),
                "full_spectrum_records_found": bool(full_spectrum),
                "full_spectrum_heartbeats_found": bool(full_spectrum_heartbeats),
                "shadow_outcomes_found": bool(shadow_outcomes),
                "paper_signals_found": bool(paper_signals),
            },
            "source_identity_evidence_rows": rows,
            "source_identity_evidence_summary": summary,
            "source_identity_evidence_gap_report": gap_report,
            "source_identity_evidence_recommendations": recommendations,
            "evidence_status": evidence_status,
            "recommended_next_operator_move": _recommended_next_operator_move(evidence_status, summary),
            "recommended_next_engineering_move": _recommended_next_engineering_move(evidence_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_collector and confirmation_valid and registry_validation.get("valid"):
            record = append_betrayal_source_identity_evidence_collector_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_RECORDED
            payload["collector_recorded"] = True
            payload["collector_id"] = record["collector_id"]
            payload["ledger_path"] = str(betrayal_source_identity_evidence_collector_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_ERROR,
                "generated_at": generated_at.isoformat(),
                "collector_recorded": False,
                "collector_id": None,
                "record_collector_requested": bool(record_collector),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {"family": "betrayal", "registry_backed": True, "paper_only": True, "live_authorized": False},
                "input_summary": {},
                "source_identity_evidence_rows": [],
                "source_identity_evidence_summary": build_source_identity_evidence_summary([]),
                "source_identity_evidence_gap_report": build_source_identity_evidence_gap_report([]),
                "source_identity_evidence_recommendations": [],
                "evidence_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R224A collector error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_source_identity_normalizer(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_source_identity_normalizer.ndjson")


def load_latest_strategy_evidence_registry(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "strategy_evidence_registry.ndjson")


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


def load_betrayal_shadow_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    resolved = get_log_dir(log_dir, use_env=True)
    records = []
    for filename in ("betrayal_shadow_outcomes.ndjson", "betrayal_shadow_resolutions.ndjson", "betrayal_true_paper_outcomes.ndjson"):
        records.extend(_read_ndjson(resolved / filename))
    return _dedupe_raw_records(records)


def load_betrayal_paper_signals(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_paper_signals.ndjson")


def load_full_spectrum_capture_records(*, log_dir: str | Path | None = None, limit: int = 200) -> list[dict[str, Any]]:
    path = get_log_dir(log_dir, use_env=True) / "full_spectrum_harvester_expansion.ndjson"
    records = read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000) if path.exists() else []
    rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        rows.extend(_extract_capture_rows(record))
    return _dedupe_raw_records(rows)


def parse_lane_key_for_entry_mode(lane_key: Any) -> dict[str, Any]:
    parts = [part.strip() for part in str(lane_key or "").split("|")]
    if len(parts) < 4 or not parts[3]:
        return {"entry_mode": None, "symbol": None, "timeframe": None, "direction": None, "evidence": "insufficient"}
    return {
        "entry_mode": parts[3].lower(),
        "symbol": parts[0] or None,
        "timeframe": parts[1] or None,
        "direction": _normal_direction(parts[2]),
        "evidence": "derived_from_lane_key",
    }


def parse_signal_id_for_identity_fields(signal_id: Any) -> dict[str, Any]:
    text = _string_or_none(signal_id)
    if not text:
        return {"source_identity": None, "entry_mode": None, "symbol": None, "timeframe": None, "direction": None, "timestamp": None}
    parts = [part.strip() for part in text.split("|")]
    result = {
        "source_identity": text,
        "source_signal_id": text,
        "symbol": parts[0] if len(parts) > 0 and parts[0] else None,
        "timeframe": parts[1] if len(parts) > 1 and parts[1] else None,
        "direction": _normal_direction(parts[2]) if len(parts) > 2 else None,
        "timestamp": parts[3] if len(parts) > 3 and parts[3] else None,
        "entry_mode": None,
    }
    for part in parts:
        if _looks_like_entry_mode(part):
            result["entry_mode"] = part.lower()
            break
    return result


def collect_entry_mode_evidence(row: Mapping[str, Any]) -> tuple[str | None, str]:
    explicit = _string_or_none(row.get("entry_mode") or row.get("source_entry_mode"))
    if explicit:
        return explicit.lower(), "explicit"
    lane = parse_lane_key_for_entry_mode(row.get("lane_key"))
    if lane.get("entry_mode"):
        return str(lane["entry_mode"]), "lane_key"
    for key, evidence in (("source_signal_id", "signal_id"), ("source_capture_id", "capture_id"), ("capture_id", "capture_id"), ("candidate_id", "capture_id")):
        parsed = parse_signal_id_for_identity_fields(row.get(key))
        if parsed.get("entry_mode"):
            return str(parsed["entry_mode"]), evidence
    return None, "insufficient"


def collect_source_identity_evidence(row: Mapping[str, Any]) -> tuple[str | None, str]:
    explicit = _string_or_none(row.get("source_identity") or row.get("source_id"))
    if explicit:
        return explicit, "explicit"
    for key, evidence in (
        ("source_signal_id", "source_signal_id"),
        ("source_capture_id", "source_capture_id"),
        ("capture_id", "source_capture_id"),
        ("emitted_signal_id", "emitted_signal_id"),
        ("signal_id", "source_signal_id"),
        ("candidate_id", "source_capture_id"),
    ):
        value = _string_or_none(row.get(key))
        if value:
            return value, evidence
    preview = build_deterministic_source_identity_preview(
        symbol=row.get("symbol"),
        timeframe=row.get("timeframe"),
        original_direction=row.get("original_direction"),
        inverse_direction=row.get("inverse_direction"),
        entry_mode=row.get("entry_mode"),
        timestamp=_timestamp(row),
        source_family=_source_family(row),
    )
    if preview:
        return preview, "deterministic_from_complete_local_fields"
    return None, "insufficient"


def build_deterministic_source_identity_preview(
    *,
    symbol: Any = None,
    timeframe: Any = None,
    original_direction: Any = None,
    inverse_direction: Any = None,
    entry_mode: Any = None,
    timestamp: Any = None,
    source_family: Any = None,
) -> str | None:
    fields = {
        "symbol": _string_or_none(symbol),
        "timeframe": _string_or_none(timeframe),
        "original_direction": _normal_direction(original_direction),
        "inverse_direction": _normal_direction(inverse_direction),
        "entry_mode": _string_or_none(entry_mode),
        "timestamp": _string_or_none(timestamp),
        "source_family": _string_or_none(source_family),
    }
    if any(not value for value in fields.values()):
        return None
    stable = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
    return (
        f"betrayal_source_identity_preview|{fields['symbol']}|{fields['timeframe']}|"
        f"{fields['original_direction']}|{fields['inverse_direction']}|{fields['entry_mode']}|"
        f"{fields['timestamp']}|{fields['source_family']}|{digest}"
    )


def build_emitted_signal_id_preview(row: Mapping[str, Any]) -> str | None:
    source_identity = _string_or_none(row.get("source_identity")) or build_deterministic_source_identity_preview(
        symbol=row.get("symbol"),
        timeframe=row.get("timeframe"),
        original_direction=row.get("original_direction"),
        inverse_direction=row.get("inverse_direction"),
        entry_mode=row.get("entry_mode"),
        timestamp=_timestamp(row),
        source_family=_source_family(row),
    )
    if not source_identity:
        return None
    if not (_string_or_none(row.get("schema_version")) and _string_or_none(row.get("candidate")) and _string_or_none(row.get("timeframe")) and _timestamp(row)):
        return None
    emitted_direction = _normal_direction(row.get("emitted_direction") or row.get("inverse_direction"))
    if not emitted_direction:
        return None
    digest = hashlib.sha256(f"{source_identity}|{emitted_direction}|{_timestamp(row)}".encode("utf-8")).hexdigest()[:16]
    return f"betrayal_emitted_preview|{source_identity}|{emitted_direction}|{digest}"


def build_lane_key_preview(row: Mapping[str, Any]) -> str | None:
    symbol = _string_or_none(row.get("symbol"))
    timeframe = _string_or_none(row.get("timeframe"))
    direction = _normal_direction(row.get("emitted_direction"))
    entry_mode = _string_or_none(row.get("entry_mode"))
    if not all((symbol, timeframe, direction, entry_mode)):
        return None
    return f"{symbol}|{timeframe}|{direction}|{entry_mode}"


def build_source_identity_evidence_rows(
    *,
    strategy_evidence_registry: Mapping[str, Any],
    betrayal_source_identity_normalizer: Mapping[str, Any],
    registry_wiring_betrayal_source_family: Mapping[str, Any],
    betrayal_aggregate_decomposition: Mapping[str, Any],
    betrayal_source_emitter_refresh: Mapping[str, Any],
    betrayal_direction_split_resolver: Mapping[str, Any],
    betrayal_event_tracker: Mapping[str, Any],
    full_spectrum_capture_records: Sequence[Mapping[str, Any]],
    betrayal_shadow_outcomes: Sequence[Mapping[str, Any]],
    betrayal_paper_signals: Sequence[Mapping[str, Any]],
    generated_at: datetime | str | None = None,
) -> list[dict[str, Any]]:
    del registry_wiring_betrayal_source_family
    manifest = _registry_manifest(strategy_evidence_registry)
    raw_rows = _collect_raw_rows(
        normalizer=betrayal_source_identity_normalizer,
        aggregate=betrayal_aggregate_decomposition,
        source_refresh=betrayal_source_emitter_refresh,
        direction_split=betrayal_direction_split_resolver,
        event_tracker=betrayal_event_tracker,
        full_spectrum=full_spectrum_capture_records,
        shadow_outcomes=betrayal_shadow_outcomes,
        paper_signals=betrayal_paper_signals,
    )
    rows = [_build_evidence_row(row, registry_manifest=manifest, generated_at=generated_at) for row in raw_rows]
    return _dedupe_evidence_rows(rows)


def build_source_identity_evidence_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "rows_reviewed": len(rows),
        "entry_mode_evidence_rows": sum(1 for row in rows if row.get("entry_mode_evidence") != "insufficient"),
        "source_identity_evidence_rows": sum(1 for row in rows if row.get("source_identity_evidence") != "insufficient"),
        "emitted_signal_id_preview_rows": sum(1 for row in rows if row.get("emitted_signal_id_preview")),
        "lane_key_preview_rows": sum(1 for row in rows if row.get("lane_key_preview")),
        "resolver_ready_preview_rows": sum(1 for row in rows if row.get("resolver_ready_preview")),
        "insufficient_rows": sum(
            1
            for row in rows
            if row.get("entry_mode_evidence") == "insufficient" or row.get("source_identity_evidence") == "insufficient"
        ),
    }


def build_source_identity_evidence_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "missing_entry_mode_rows": sum(1 for row in rows if not row.get("entry_mode")),
        "missing_source_identity_rows": sum(1 for row in rows if not row.get("source_identity")),
        "missing_emitted_signal_id_rows": sum(1 for row in rows if not row.get("emitted_signal_id_preview")),
        "missing_lane_key_rows": sum(1 for row in rows if not row.get("lane_key_preview")),
        "missing_direction_rows": sum(
            1 for row in rows if not (row.get("original_direction") and row.get("inverse_direction") and row.get("emitted_direction"))
        ),
        "resolver_ready_preview_rows": sum(1 for row in rows if row.get("resolver_ready_preview")),
        "hard_live_blockers": _hard_live_blockers(),
    }


def build_source_identity_evidence_recommendations(
    *,
    gap_report: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = []
    if gap_report.get("resolver_ready_preview_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RUN_R224_NORMALIZED_SOURCE_ROW_APPEND",
                "future_phase": "R224",
                "why": "Evidence preview contains resolver-ready paper-only rows; R224 must still validate before append.",
            }
        )
    if gap_report.get("missing_entry_mode_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "COLLECT_MORE_ENTRY_MODE",
                "future_phase": "R225",
                "why": "Rows still lack explicit or parseable entry_mode evidence; do not infer common ladder mode.",
            }
        )
    if gap_report.get("missing_source_identity_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "COLLECT_MORE_SOURCE_IDENTITY",
                "future_phase": "R225",
                "why": "Rows still lack source identity, source signal id, capture id, emitted id, or complete deterministic inputs.",
            }
        )
    if summary.get("rows_reviewed"):
        recommendations.append(
            {
                "priority": "LOW",
                "recommended_action": "KEEP_CONTEXT_ONLY",
                "future_phase": "R224A",
                "why": "R224A is evidence collection only and cannot promote betrayal or authorize live execution.",
            }
        )
    return recommendations


def classify_betrayal_source_identity_evidence_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not rows:
        return SOURCE_IDENTITY_EVIDENCE_INSUFFICIENT
    if gap_report.get("resolver_ready_preview_rows"):
        return SOURCE_IDENTITY_READY_FOR_NORMALIZED_APPEND_PREVIEW
    if gap_report.get("missing_entry_mode_rows"):
        return SOURCE_IDENTITY_ENTRY_MODE_STILL_BLOCKED
    if gap_report.get("missing_source_identity_rows"):
        return SOURCE_IDENTITY_EVIDENCE_PARTIAL
    if any(row.get("entry_mode_evidence") != "insufficient" or row.get("source_identity_evidence") != "insufficient" for row in rows):
        return SOURCE_IDENTITY_EVIDENCE_FOUND
    return SOURCE_IDENTITY_NOT_LIVE_AUTHORIZED


def append_betrayal_source_identity_evidence_collector_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_source_identity_evidence_collector_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "collector_id": str(record.get("collector_id") or f"r224a_betrayal_source_identity_evidence_collector_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_collector_requested": bool(record.get("record_collector_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "source_identity_evidence_rows": list(record.get("source_identity_evidence_rows") or []),
            "source_identity_evidence_summary": dict(record.get("source_identity_evidence_summary") or {}),
            "source_identity_evidence_gap_report": dict(record.get("source_identity_evidence_gap_report") or {}),
            "source_identity_evidence_recommendations": list(record.get("source_identity_evidence_recommendations") or []),
            "evidence_status": record.get("evidence_status"),
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


def load_betrayal_source_identity_evidence_collector_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_source_identity_evidence_collector_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def summarize_betrayal_source_identity_evidence_collector_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    summary = latest.get("source_identity_evidence_summary") if isinstance(latest.get("source_identity_evidence_summary"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "evidence_status_counts": dict(sorted(Counter(str(record.get("evidence_status") or "UNKNOWN") for record in records).items())),
        "last_collector_id": latest.get("collector_id") if isinstance(latest, Mapping) else None,
        "last_rows_reviewed": summary.get("rows_reviewed"),
        "last_resolver_ready_preview_rows": summary.get("resolver_ready_preview_rows"),
        "safety": dict(SAFETY),
    }


def betrayal_source_identity_evidence_collector_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_source_identity_evidence_collector_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _build_evidence_row(
    row: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
    generated_at: datetime | str | None,
) -> dict[str, Any]:
    normalized = dict(row)
    parsed_signal = parse_signal_id_for_identity_fields(
        normalized.get("source_signal_id") or normalized.get("signal_id") or normalized.get("source_capture_id") or normalized.get("capture_id")
    )
    lane = parse_lane_key_for_entry_mode(normalized.get("lane_key"))
    normalized["schema_version"] = _string_or_none(normalized.get("schema_version")) or SCHEMA_VERSION
    normalized["source_type"] = _string_or_none(normalized.get("source_type")) or SOURCE_TYPE
    normalized["candidate"] = _candidate_label(normalized)
    normalized["symbol"] = _string_or_none(normalized.get("symbol") or parsed_signal.get("symbol") or lane.get("symbol")) or DEFAULT_SYMBOL
    normalized["timeframe"] = _string_or_none(normalized.get("timeframe") or parsed_signal.get("timeframe") or lane.get("timeframe")) or _candidate_timeframe(normalized.get("candidate"))
    entry_mode, entry_evidence = collect_entry_mode_evidence(normalized)
    normalized["entry_mode"] = entry_mode
    original = _normal_direction(normalized.get("original_direction") or normalized.get("source_direction") or normalized.get("direction") or parsed_signal.get("direction"))
    inverse = _normal_direction(normalized.get("inverse_direction") or normalized.get("betrayal_direction") or normalized.get("shadow_direction"))
    emitted = _normal_direction(normalized.get("emitted_direction") or inverse or normalized.get("direction") or parsed_signal.get("direction") or lane.get("direction"))
    normalized["original_direction"] = original
    normalized["inverse_direction"] = inverse
    normalized["emitted_direction"] = emitted
    source_signal_id = _first_string(normalized, "source_signal_id", "signal_id", "original_signal_id")
    source_capture_id = _first_string(normalized, "source_capture_id", "capture_id", "candidate_id")
    if not source_signal_id and parsed_signal.get("source_signal_id"):
        source_signal_id = str(parsed_signal["source_signal_id"])
    normalized["source_signal_id"] = source_signal_id
    normalized["source_capture_id"] = source_capture_id
    source_identity, identity_evidence = collect_source_identity_evidence(normalized)
    normalized["source_identity"] = source_identity
    normalized["source_signal_timestamp"] = _timestamp(normalized) or _string_or_none(parsed_signal.get("timestamp"))
    normalized["emitted_at"] = _string_or_none(normalized.get("emitted_at")) or _generated_at_iso(generated_at)
    normalized["emitted_signal_id_preview"] = _string_or_none(normalized.get("emitted_signal_id")) or build_emitted_signal_id_preview(normalized)
    normalized["lane_key_preview"] = _string_or_none(normalized.get("lane_key")) or build_lane_key_preview(normalized)
    event = build_betrayal_event_identity(
        symbol=normalized.get("symbol"),
        timeframe=normalized.get("timeframe"),
        candidate_label=normalized.get("candidate"),
        original_direction=original,
        inverse_direction=inverse,
        entry_mode=entry_mode,
        source_signal_id=source_signal_id,
        source_capture_id=source_capture_id,
        signal_timestamp=normalized.get("source_signal_timestamp"),
        event_timeframe=normalized.get("timeframe"),
        outcome_window=OUTCOME_WINDOWS,
    )
    validation_row = {
        "schema_version": SCHEMA_VERSION,
        "source_type": SOURCE_TYPE,
        "candidate": normalized.get("candidate"),
        "symbol": normalized.get("symbol"),
        "timeframe": normalized.get("timeframe"),
        "entry_mode": entry_mode,
        "original_direction": original,
        "inverse_direction": inverse,
        "emitted_direction": emitted,
        "source_identity": source_identity,
        "source_signal_id": source_signal_id,
        "emitted_signal_id": normalized.get("emitted_signal_id_preview"),
        "source_signal_timestamp": normalized.get("source_signal_timestamp"),
        "emitted_at": normalized.get("emitted_at"),
        "lane_key": normalized.get("lane_key_preview"),
        "betrayal_event_identity": event["event_identity"],
        "betrayal_event_identity_hash": event["event_identity_hash"],
        "outcome_windows": OUTCOME_WINDOWS,
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }
    validation = validate_betrayal_source_row_against_registry(validation_row, registry_manifest=registry_manifest)
    missing = list(validation.get("missing_required_fields") or [])
    if emitted != inverse and "emitted_direction_equals_inverse_direction" not in missing:
        missing.append("emitted_direction_equals_inverse_direction")
    schema_complete = not missing
    source = _collector_source(normalized)
    return _sanitize(
        {
            "candidate": normalized.get("candidate"),
            "source": source,
            "symbol": normalized.get("symbol"),
            "timeframe": normalized.get("timeframe"),
            "entry_mode": entry_mode,
            "entry_mode_evidence": entry_evidence,
            "original_direction": original,
            "inverse_direction": inverse,
            "emitted_direction": emitted,
            "source_identity": source_identity,
            "source_identity_evidence": identity_evidence,
            "source_signal_id": source_signal_id,
            "source_capture_id": source_capture_id,
            "emitted_signal_id_preview": normalized.get("emitted_signal_id_preview"),
            "lane_key_preview": normalized.get("lane_key_preview"),
            "timestamp": normalized.get("source_signal_timestamp"),
            "schema_complete_preview": schema_complete,
            "resolver_ready_preview": bool(schema_complete and validation.get("schema_complete") and emitted == inverse),
            "missing_required_fields": _dedupe(missing),
            "paper_only": True,
            "live_authorized": False,
            "promotion_allowed": False,
            "why": _evidence_why(entry_evidence=entry_evidence, identity_evidence=identity_evidence, missing=missing),
        }
    )


def _collect_raw_rows(
    *,
    normalizer: Mapping[str, Any],
    aggregate: Mapping[str, Any],
    source_refresh: Mapping[str, Any],
    direction_split: Mapping[str, Any],
    event_tracker: Mapping[str, Any],
    full_spectrum: Sequence[Mapping[str, Any]],
    shadow_outcomes: Sequence[Mapping[str, Any]],
    paper_signals: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_tagged_rows(normalizer.get("normalized_source_rows_preview"), "normalizer"))
    for key in ("decomposition_rows", "v2_source_rows_preview"):
        rows.extend(_tagged_rows(aggregate.get(key), "aggregate_decomposition"))
    for key in ("source_candidate_rows", "direction_specific_source_preview"):
        rows.extend(_tagged_rows(source_refresh.get(key), "source_emitter_refresh"))
    rows.extend(_tagged_rows(direction_split.get("direction_split_resolution_rows"), "direction_split_resolver"))
    for key in ("event_tracker_records_preview", "event_seed_candidates"):
        rows.extend(_tagged_rows(event_tracker.get(key), "event_tracker"))
    rows.extend(_tagged_rows(full_spectrum, "full_spectrum_capture"))
    rows.extend(_tagged_rows(shadow_outcomes, "shadow_outcome"))
    rows.extend(_tagged_rows(paper_signals, "paper_signal"))
    return rows


def _extract_capture_rows(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("captured_candidates", "captures", "captured_rows"):
        value = record.get(key)
        if isinstance(value, Sequence) and not isinstance(value, str):
            rows.extend(dict(row) for row in value if isinstance(row, Mapping))
    summary = record.get("capture_summary") if isinstance(record.get("capture_summary"), Mapping) else {}
    value = summary.get("captured_candidates")
    if isinstance(value, Sequence) and not isinstance(value, str):
        rows.extend(dict(row) for row in value if isinstance(row, Mapping))
    examples = summary.get("candidate_examples_by_lane")
    if isinstance(examples, Mapping):
        for lane_key, lane_rows in examples.items():
            if not isinstance(lane_rows, Sequence) or isinstance(lane_rows, str):
                continue
            for row in lane_rows:
                if isinstance(row, Mapping):
                    rows.append({**dict(row), "lane_key": row.get("lane_key") or lane_key})
    return rows


def _tagged_rows(value: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [_sanitize({**dict(row), "_collector_source": source}) for row in value if isinstance(row, Mapping)]


def _top_level_status(*, record_collector: bool, confirmation_valid: bool, registry_valid: bool) -> str:
    if record_collector and not confirmation_valid:
        return BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_REJECTED
    if not registry_valid:
        return BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_BLOCKED
    return BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_READY


def _recommended_next_operator_move(evidence_status: str, summary: Mapping[str, Any]) -> str:
    if evidence_status == SOURCE_IDENTITY_READY_FOR_NORMALIZED_APPEND_PREVIEW and summary.get("resolver_ready_preview_rows"):
        return "RUN_R224_BETRAYAL_NORMALIZED_SOURCE_ROW_APPEND"
    if evidence_status == SOURCE_IDENTITY_ENTRY_MODE_STILL_BLOCKED:
        return "KEEP_WEEKEND_FISHERMAN_RUNNING"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(evidence_status: str, gap_report: Mapping[str, Any]) -> str:
    if evidence_status == SOURCE_IDENTITY_READY_FOR_NORMALIZED_APPEND_PREVIEW:
        return "Run R224 only after independently validating resolver_ready_preview rows; append remains paper-only."
    if gap_report.get("missing_entry_mode_rows"):
        return "Implement R225 entry_mode evidence wiring so future emitters write entry_mode explicitly at source."
    if gap_report.get("missing_source_identity_rows"):
        return "Wire future betrayal emitters and captures to carry source_identity or source_signal_id explicitly."
    return "Keep R224A context-only and continue local evidence collection."


def _registry_manifest(registry: Mapping[str, Any]) -> dict[str, Any]:
    manifest = registry.get("registry_manifest") if isinstance(registry.get("registry_manifest"), Mapping) else registry
    return dict(manifest) if isinstance(manifest, Mapping) else {}


def _registry_validation(registry: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not registry or not manifest:
        return {"valid": False, "missing_required_sections": ["registry_manifest"]}
    if isinstance(registry.get("registry_validation"), Mapping):
        return dict(registry["registry_validation"])
    return validate_registry_entry(manifest)


def _collector_source(row: Mapping[str, Any]) -> str:
    source = str(row.get("_collector_source") or row.get("_source") or row.get("evidence_source") or row.get("source") or "unknown")
    allowed = {
        "normalizer",
        "aggregate_decomposition",
        "source_emitter_refresh",
        "direction_split_resolver",
        "event_tracker",
        "full_spectrum_capture",
        "shadow_outcome",
        "paper_signal",
    }
    return source if source in allowed else "normalizer" if "normalizer" in source else "shadow_outcome" if "shadow" in source else "paper_signal" if "paper" in source else "full_spectrum_capture" if "full_spectrum" in source or "capture" in source else source


def _candidate_label(row: Mapping[str, Any]) -> str | None:
    candidate = _string_or_none(row.get("candidate") or row.get("label"))
    if candidate:
        return candidate
    timeframe = _string_or_none(row.get("timeframe"))
    return f"{timeframe} aggregate" if timeframe else None


def _candidate_timeframe(candidate: Any) -> str | None:
    match = re.match(r"^([0-9]+[mhdMHD])", str(candidate or "").strip())
    return match.group(1) if match else None


def _source_family(row: Mapping[str, Any]) -> str | None:
    return _string_or_none(row.get("source_family") or row.get("_collector_source") or row.get("evidence_source") or row.get("source"))


def _timestamp(row: Mapping[str, Any]) -> str | None:
    return _first_string(row, "source_signal_timestamp", "signal_timestamp", "timestamp", "emitted_at", "created_at", "captured_at")


def _normal_direction(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"long", "bull", "bullish", "buy"}:
        return "long"
    if text in {"short", "bear", "bearish", "sell"}:
        return "short"
    return None


def _looks_like_entry_mode(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and (text.startswith("ladder_") or text.startswith("fib_") or text in {"market_close"})


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


def _evidence_why(*, entry_evidence: str, identity_evidence: str, missing: Sequence[str]) -> str:
    if not missing:
        return "Local evidence previews all registry-required source fields; row remains paper-only and not appended in R224A."
    if entry_evidence == "insufficient":
        return "Entry mode evidence is insufficient; common ladder mode was not fabricated."
    if identity_evidence == "insufficient":
        return "Source identity evidence is insufficient; candidate label alone was not used as identity."
    return f"Partial evidence only; missing registry-required fields: {', '.join(missing)}."


def _hard_live_blockers() -> list[str]:
    return [
        "betrayal_not_live_authorized",
        "betrayal_not_promoted",
        "source_identity_evidence_collector_is_paper_only",
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
    records = read_recent_ndjson_records(path, limit=1, max_bytes=32_000_000)
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


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_evidence_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("source") or ""),
            str(row.get("candidate") or ""),
            str(row.get("source_signal_id") or ""),
            str(row.get("source_identity") or ""),
            str(row.get("timestamp") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(_sanitize(dict(row)))
    return result


def _dedupe_raw_records(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for row in rows:
        key = json.dumps(_sanitize(dict(row)), sort_keys=True, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        result.append(_sanitize(dict(row)))
    return result


def _generated_at_iso(generated_at: datetime | str | None) -> str:
    if isinstance(generated_at, datetime):
        return generated_at.isoformat()
    return str(generated_at or datetime.now(UTC).isoformat())


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
