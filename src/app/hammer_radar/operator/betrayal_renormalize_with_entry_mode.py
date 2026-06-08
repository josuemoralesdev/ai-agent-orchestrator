"""R226 betrayal renormalization with entry_mode evidence.

Paper-only preview surface that joins R225 entry_mode evidence with R224A
source identity evidence and R223 normalized rows. It validates previews
against the R218/R219 betrayal_source_emitter_v2 registry contract and only
appends its own audit ledger after exact confirmation.
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
from src.app.hammer_radar.operator.betrayal_event_tracker import build_betrayal_event_identity
from src.app.hammer_radar.operator.betrayal_source_identity_evidence_collector import (
    build_lane_key_preview as _collector_lane_key_preview,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.registry_wiring_betrayal_source_family import (
    validate_betrayal_source_row_against_registry,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import validate_registry_entry

BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_READY = "BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_READY"
BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_REJECTED = "BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_REJECTED"
BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_RECORDED = "BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_RECORDED"
BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_BLOCKED = "BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_BLOCKED"
BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_ERROR = "BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_ERROR"

RENORMALIZED_RESOLVER_READY_PREVIEWS_AVAILABLE = "RENORMALIZED_RESOLVER_READY_PREVIEWS_AVAILABLE"
RENORMALIZED_PARTIAL_PREVIEWS_AVAILABLE = "RENORMALIZED_PARTIAL_PREVIEWS_AVAILABLE"
RENORMALIZATION_ENTRY_MODE_STILL_BLOCKED = "RENORMALIZATION_ENTRY_MODE_STILL_BLOCKED"
RENORMALIZATION_SOURCE_IDENTITY_STILL_BLOCKED = "RENORMALIZATION_SOURCE_IDENTITY_STILL_BLOCKED"
RENORMALIZATION_NO_RESOLVER_READY_PREVIEWS = "RENORMALIZATION_NO_RESOLVER_READY_PREVIEWS"
RENORMALIZATION_NOT_LIVE_AUTHORIZED = "RENORMALIZATION_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE"
LEDGER_FILENAME = "betrayal_renormalize_with_entry_mode.ndjson"
SCHEMA_VERSION = "betrayal_source_emitter_v2"
SOURCE_TYPE = "betrayal_source_emitter"
DEFAULT_SYMBOL = "BTCUSDT"
OUTCOME_WINDOWS = [1, 3, 5, 10, 21, 34, 55]
CONFIRM_BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL RENORMALIZE WITH ENTRY MODE RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "logs/hammer_radar_forward/betrayal_entry_mode_evidence_wiring.ndjson",
    "logs/hammer_radar_forward/betrayal_source_identity_evidence_collector.ndjson",
    "logs/hammer_radar_forward/betrayal_source_identity_normalizer.ndjson",
    "logs/hammer_radar_forward/strategy_evidence_registry.ndjson",
    "logs/hammer_radar_forward/registry_wiring_betrayal_source_family.ndjson",
    "logs/hammer_radar_forward/betrayal_aggregate_decomposition.ndjson",
    "logs/hammer_radar_forward/betrayal_source_emitter_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_direction_split_resolver.ndjson",
    "logs/hammer_radar_forward/betrayal_event_tracker.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_renormalize_with_entry_mode(
    *,
    log_dir: str | Path | None = None,
    record_renormalization: bool = False,
    confirm_betrayal_renormalize_with_entry_mode: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_renormalize_with_entry_mode
        == CONFIRM_BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_RECORDING_PHRASE
    )
    try:
        entry_mode = load_latest_betrayal_entry_mode_evidence_wiring(log_dir=resolved_log_dir)
        source_identity = load_latest_betrayal_source_identity_evidence_collector(log_dir=resolved_log_dir)
        normalizer = load_latest_betrayal_source_identity_normalizer(log_dir=resolved_log_dir)
        registry = load_latest_strategy_evidence_registry(log_dir=resolved_log_dir)
        registry_wiring = _latest_record(resolved_log_dir / "registry_wiring_betrayal_source_family.ndjson")
        aggregate = _latest_record(resolved_log_dir / "betrayal_aggregate_decomposition.ndjson")
        source_refresh = _latest_record(resolved_log_dir / "betrayal_source_emitter_refresh.ndjson")
        direction_split = _latest_record(resolved_log_dir / "betrayal_direction_split_resolver.ndjson")
        event_tracker = _latest_record(resolved_log_dir / "betrayal_event_tracker.ndjson")
        del registry_wiring, aggregate, source_refresh, direction_split, event_tracker

        manifest = _registry_manifest(registry)
        registry_validation = _registry_validation(registry, manifest)
        rows = build_renormalized_source_rows_preview(
            betrayal_entry_mode_evidence_wiring=entry_mode,
            betrayal_source_identity_evidence_collector=source_identity,
            betrayal_source_identity_normalizer=normalizer,
            strategy_evidence_registry=registry,
            generated_at=generated_at,
        )
        summary = build_renormalization_summary(rows)
        gap_report = build_renormalization_gap_report(rows)
        recommendations = build_renormalization_recommendations(gap_report=gap_report, summary=summary)
        renormalization_status = classify_betrayal_renormalization_status(rows=rows, gap_report=gap_report)
        payload = {
            "status": _top_level_status(
                record_renormalization=record_renormalization,
                confirmation_valid=confirmation_valid,
                registry_valid=bool(registry_validation.get("valid")),
            ),
            "generated_at": generated_at.isoformat(),
            "renormalization_recorded": False,
            "renormalization_id": None,
            "record_renormalization_requested": bool(record_renormalization),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "family": "betrayal",
                "registry_backed": True,
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "entry_mode_evidence_found": bool(entry_mode.get("entry_mode_evidence_rows")),
                "source_identity_evidence_found": bool(source_identity.get("source_identity_evidence_rows")),
                "normalizer_found": bool(normalizer.get("normalized_source_rows_preview")),
                "registry_found": bool(registry),
                "registry_valid": bool(registry_validation.get("valid")),
            },
            "renormalized_source_rows_preview": rows,
            "renormalization_summary": summary,
            "renormalization_gap_report": gap_report,
            "renormalization_recommendations": recommendations,
            "renormalization_status": renormalization_status,
            "recommended_next_operator_move": _recommended_next_operator_move(renormalization_status, summary),
            "recommended_next_engineering_move": _recommended_next_engineering_move(renormalization_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_renormalization and confirmation_valid and registry_validation.get("valid"):
            record = append_betrayal_renormalize_with_entry_mode_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_RECORDED
            payload["renormalization_recorded"] = True
            payload["renormalization_id"] = record["renormalization_id"]
            payload["ledger_path"] = str(betrayal_renormalize_with_entry_mode_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_ERROR,
                "generated_at": generated_at.isoformat(),
                "renormalization_recorded": False,
                "renormalization_id": None,
                "record_renormalization_requested": bool(record_renormalization),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {"family": "betrayal", "registry_backed": True, "paper_only": True, "live_authorized": False},
                "input_summary": {},
                "renormalized_source_rows_preview": [],
                "renormalization_summary": build_renormalization_summary([]),
                "renormalization_gap_report": build_renormalization_gap_report([]),
                "renormalization_recommendations": [],
                "renormalization_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R226 renormalization error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_entry_mode_evidence_wiring(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_entry_mode_evidence_wiring.ndjson")


def load_latest_betrayal_source_identity_evidence_collector(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_source_identity_evidence_collector.ndjson")


def load_latest_betrayal_source_identity_normalizer(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_source_identity_normalizer.ndjson")


def load_latest_strategy_evidence_registry(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "strategy_evidence_registry.ndjson")


def build_join_key_for_betrayal_row(row: Mapping[str, Any]) -> tuple[str, ...]:
    keys = _join_keys_for_row(row)
    return keys[0] if keys else ("empty",)


def index_entry_mode_evidence_rows(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    return _index_rows(rows, require=lambda row: bool(row.get("entry_mode_valid") and row.get("entry_mode")))


def index_source_identity_evidence_rows(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    return _index_rows(rows, require=lambda row: bool(row.get("source_identity") or row.get("source_signal_id")))


def merge_entry_mode_and_source_identity_evidence(
    row: Mapping[str, Any],
    *,
    entry_mode_index: Mapping[tuple[str, ...], Sequence[Mapping[str, Any]]],
    source_identity_index: Mapping[tuple[str, ...], Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    merged = dict(row)
    evidence_sources = list(merged.get("evidence_sources_used") or merged.get("normalization_sources_used") or [])
    for evidence_row in _matching_rows(row, entry_mode_index):
        entry_mode = _string_or_none(evidence_row.get("entry_mode"))
        if entry_mode and not _entry_mode_blocked(entry_mode):
            merged["entry_mode"] = entry_mode.lower()
            evidence_sources.append(f"entry_mode:{evidence_row.get('source') or 'r225'}")
            break
    for evidence_row in _matching_rows(row, source_identity_index):
        for target, aliases in (
            ("source_identity", ("source_identity",)),
            ("source_signal_id", ("source_signal_id", "signal_id")),
            ("source_signal_timestamp", ("source_signal_timestamp", "timestamp", "signal_timestamp")),
            ("original_direction", ("original_direction",)),
            ("inverse_direction", ("inverse_direction",)),
            ("emitted_direction", ("emitted_direction",)),
            ("lane_key", ("lane_key_preview", "lane_key")),
            ("emitted_signal_id", ("emitted_signal_id", "emitted_signal_id_preview")),
        ):
            if not _string_or_none(merged.get(target)):
                value = _first_string(evidence_row, *aliases)
                if value:
                    merged[target] = value
        evidence_sources.append(f"source_identity:{evidence_row.get('source') or 'r224a'}")
        break
    merged["evidence_sources_used"] = _dedupe(evidence_sources)
    return merged


def build_emitted_signal_id_preview(row: Mapping[str, Any]) -> str | None:
    source_identity = _string_or_none(row.get("source_identity"))
    emitted_direction = _normal_direction(row.get("emitted_direction"))
    timestamp = _timestamp(row)
    if not (source_identity and emitted_direction and timestamp):
        return None
    digest = hashlib.sha256(f"{source_identity}|{emitted_direction}|{timestamp}".encode("utf-8")).hexdigest()[:16]
    return f"betrayal_emitted_preview|{source_identity}|{emitted_direction}|{digest}"


def build_lane_key_preview(row: Mapping[str, Any]) -> str | None:
    return _collector_lane_key_preview(row)


def validate_renormalized_row_against_registry(
    row: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    validation = validate_betrayal_source_row_against_registry(row, registry_manifest=registry_manifest)
    missing = list(validation.get("missing_required_fields") or [])
    if _entry_mode_blocked(row.get("entry_mode")) and "entry_mode_blocked_placeholder" not in missing:
        missing.append("entry_mode_blocked_placeholder")
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


def build_renormalized_source_rows_preview(
    *,
    betrayal_entry_mode_evidence_wiring: Mapping[str, Any],
    betrayal_source_identity_evidence_collector: Mapping[str, Any],
    betrayal_source_identity_normalizer: Mapping[str, Any],
    strategy_evidence_registry: Mapping[str, Any],
    generated_at: datetime | str | None = None,
) -> list[dict[str, Any]]:
    manifest = _registry_manifest(strategy_evidence_registry)
    entry_mode_index = index_entry_mode_evidence_rows(betrayal_entry_mode_evidence_wiring.get("entry_mode_evidence_rows") or [])
    source_identity_index = index_source_identity_evidence_rows(
        betrayal_source_identity_evidence_collector.get("source_identity_evidence_rows") or []
    )
    raw_rows = _base_rows(
        normalizer=betrayal_source_identity_normalizer,
        collector=betrayal_source_identity_evidence_collector,
        entry_mode=betrayal_entry_mode_evidence_wiring,
    )
    rows = []
    for raw in raw_rows:
        merged = merge_entry_mode_and_source_identity_evidence(
            raw,
            entry_mode_index=entry_mode_index,
            source_identity_index=source_identity_index,
        )
        rows.append(_build_renormalized_row(merged, registry_manifest=manifest, generated_at=generated_at))
    return _dedupe_renormalized_rows(rows)


def build_renormalization_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "rows_reviewed": len(rows),
        "rows_with_entry_mode": sum(1 for row in rows if row.get("entry_mode")),
        "rows_with_source_identity": sum(1 for row in rows if row.get("source_identity")),
        "rows_with_lane_key_preview": sum(1 for row in rows if row.get("lane_key_preview")),
        "rows_with_emitted_signal_id_preview": sum(1 for row in rows if row.get("emitted_signal_id_preview")),
        "resolver_ready_preview_rows": sum(1 for row in rows if row.get("resolver_ready_preview")),
        "partial_preview_rows": sum(1 for row in rows if row.get("schema_complete_preview") and not row.get("resolver_ready_preview")),
        "blocked_rows": sum(1 for row in rows if not row.get("schema_complete_preview")),
    }


def build_renormalization_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "missing_entry_mode_rows": sum(1 for row in rows if _missing_field(row, "entry_mode")),
        "missing_source_identity_rows": sum(1 for row in rows if _missing_field(row, "source_identity")),
        "missing_direction_rows": sum(
            1
            for row in rows
            if any(
                field in (row.get("missing_required_fields") or [])
                for field in ("original_direction", "inverse_direction", "emitted_direction", "emitted_direction_equals_inverse_direction")
            )
        ),
        "missing_lane_key_rows": sum(1 for row in rows if _missing_field(row, "lane_key")),
        "missing_emitted_signal_id_rows": sum(1 for row in rows if _missing_field(row, "emitted_signal_id")),
        "registry_invalid_rows": sum(1 for row in rows if not row.get("registry_valid")),
        "resolver_ready_preview_rows": sum(1 for row in rows if row.get("resolver_ready_preview")),
        "hard_live_blockers": _hard_live_blockers(),
    }


def build_renormalization_recommendations(
    *,
    gap_report: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    if gap_report.get("resolver_ready_preview_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RUN_R224_APPEND",
                "future_phase": "R224",
                "why": "R226 found registry-complete paper-only resolver-ready previews; append remains a separate guarded phase.",
            }
        )
    if gap_report.get("missing_direction_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RUN_R227_DIRECTION_COMPLETION",
                "future_phase": "R227",
                "why": "Rows still missing original, inverse, or emitted direction cannot become resolver-ready.",
            }
        )
    if gap_report.get("missing_entry_mode_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "COLLECT_MORE_ENTRY_MODE",
                "future_phase": "R225",
                "why": "Entry_mode remains missing for some rows; common ladder mode was not fabricated.",
            }
        )
    if summary.get("rows_reviewed"):
        recommendations.append(
            {
                "priority": "LOW",
                "recommended_action": "KEEP_CONTEXT_ONLY",
                "future_phase": "R226",
                "why": "R226 is renormalization preview only and does not append rows, write configs, or authorize live.",
            }
        )
    return recommendations


def classify_betrayal_renormalization_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if gap_report.get("resolver_ready_preview_rows"):
        return RENORMALIZED_RESOLVER_READY_PREVIEWS_AVAILABLE
    if gap_report.get("missing_entry_mode_rows"):
        return RENORMALIZATION_ENTRY_MODE_STILL_BLOCKED
    if gap_report.get("missing_source_identity_rows"):
        return RENORMALIZATION_SOURCE_IDENTITY_STILL_BLOCKED
    if any(row.get("schema_complete_preview") for row in rows):
        return RENORMALIZED_PARTIAL_PREVIEWS_AVAILABLE
    if gap_report.get("registry_invalid_rows"):
        return RENORMALIZATION_NO_RESOLVER_READY_PREVIEWS
    return RENORMALIZATION_NOT_LIVE_AUTHORIZED


def append_betrayal_renormalize_with_entry_mode_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_renormalize_with_entry_mode_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "renormalization_id": str(
                record.get("renormalization_id") or f"r226_betrayal_renormalize_with_entry_mode_{uuid4().hex}"
            ),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_renormalization_requested": bool(record.get("record_renormalization_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "renormalized_source_rows_preview": list(record.get("renormalized_source_rows_preview") or []),
            "renormalization_summary": dict(record.get("renormalization_summary") or {}),
            "renormalization_gap_report": dict(record.get("renormalization_gap_report") or {}),
            "renormalization_recommendations": list(record.get("renormalization_recommendations") or []),
            "renormalization_status": record.get("renormalization_status"),
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


def load_betrayal_renormalize_with_entry_mode_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_renormalize_with_entry_mode_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def summarize_betrayal_renormalize_with_entry_mode_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    summary = latest.get("renormalization_summary") if isinstance(latest.get("renormalization_summary"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "renormalization_status_counts": dict(
            sorted(Counter(str(record.get("renormalization_status") or "UNKNOWN") for record in records).items())
        ),
        "last_renormalization_id": latest.get("renormalization_id") if isinstance(latest, Mapping) else None,
        "last_rows_reviewed": summary.get("rows_reviewed"),
        "last_resolver_ready_preview_rows": summary.get("resolver_ready_preview_rows"),
        "safety": dict(SAFETY),
    }


def betrayal_renormalize_with_entry_mode_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_renormalize_with_entry_mode_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _build_renormalized_row(
    row: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
    generated_at: datetime | str | None,
) -> dict[str, Any]:
    normalized = dict(row)
    normalized["schema_version"] = _string_or_none(normalized.get("schema_version")) or SCHEMA_VERSION
    normalized["source_type"] = _string_or_none(normalized.get("source_type")) or SOURCE_TYPE
    normalized["candidate"] = _candidate_label(normalized)
    normalized["symbol"] = _string_or_none(normalized.get("symbol")) or DEFAULT_SYMBOL
    normalized["timeframe"] = _string_or_none(normalized.get("timeframe")) or _candidate_timeframe(normalized.get("candidate"))
    normalized["entry_mode"] = _string_or_none(normalized.get("entry_mode"))
    if normalized["entry_mode"]:
        normalized["entry_mode"] = str(normalized["entry_mode"]).lower()
    normalized["original_direction"] = _normal_direction(normalized.get("original_direction"))
    normalized["inverse_direction"] = _normal_direction(normalized.get("inverse_direction"))
    normalized["emitted_direction"] = _normal_direction(normalized.get("emitted_direction"))
    normalized["source_signal_id"] = _first_string(normalized, "source_signal_id", "signal_id")
    normalized["source_signal_timestamp"] = _timestamp(normalized)
    normalized["emitted_at"] = _string_or_none(normalized.get("emitted_at")) or _generated_at_iso(generated_at)
    normalized["source_identity"] = _string_or_none(normalized.get("source_identity"))
    normalized["emitted_signal_id_preview"] = (
        _string_or_none(normalized.get("emitted_signal_id") or normalized.get("emitted_signal_id_preview"))
        or build_emitted_signal_id_preview(normalized)
    )
    normalized["lane_key_preview"] = _string_or_none(normalized.get("lane_key") or normalized.get("lane_key_preview")) or build_lane_key_preview(
        normalized
    )
    event = build_betrayal_event_identity(
        symbol=normalized.get("symbol"),
        timeframe=normalized.get("timeframe"),
        candidate_label=normalized.get("candidate"),
        original_direction=normalized.get("original_direction"),
        inverse_direction=normalized.get("inverse_direction"),
        entry_mode=normalized.get("entry_mode"),
        source_signal_id=normalized.get("source_signal_id"),
        source_capture_id=normalized.get("source_capture_id"),
        signal_timestamp=normalized.get("source_signal_timestamp"),
        event_timeframe=normalized.get("timeframe"),
        outcome_window=normalized.get("outcome_windows") or OUTCOME_WINDOWS,
    )
    validation_row = {
        "schema_version": SCHEMA_VERSION,
        "source_type": SOURCE_TYPE,
        "candidate": normalized.get("candidate"),
        "symbol": normalized.get("symbol"),
        "timeframe": normalized.get("timeframe"),
        "entry_mode": normalized.get("entry_mode"),
        "original_direction": normalized.get("original_direction"),
        "inverse_direction": normalized.get("inverse_direction"),
        "emitted_direction": normalized.get("emitted_direction"),
        "source_identity": normalized.get("source_identity"),
        "source_signal_id": normalized.get("source_signal_id"),
        "emitted_signal_id": normalized.get("emitted_signal_id_preview"),
        "source_signal_timestamp": normalized.get("source_signal_timestamp"),
        "emitted_at": normalized.get("emitted_at"),
        "lane_key": normalized.get("lane_key_preview"),
        "betrayal_event_identity": _string_or_none(normalized.get("betrayal_event_identity")) or event["event_identity"],
        "betrayal_event_identity_hash": _string_or_none(normalized.get("betrayal_event_identity_hash"))
        or event["event_identity_hash"],
        "outcome_windows": list(normalized.get("outcome_windows") or OUTCOME_WINDOWS),
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }
    validation = validate_renormalized_row_against_registry(validation_row, registry_manifest=registry_manifest)
    missing = list(validation.get("missing_required_fields") or [])
    resolver_ready = bool(validation.get("schema_complete") and validation_row["emitted_direction"] == validation_row["inverse_direction"])
    return _sanitize(
        {
            "candidate": validation_row["candidate"],
            "symbol": validation_row["symbol"],
            "timeframe": validation_row["timeframe"],
            "entry_mode": validation_row["entry_mode"],
            "original_direction": validation_row["original_direction"],
            "inverse_direction": validation_row["inverse_direction"],
            "emitted_direction": validation_row["emitted_direction"],
            "source_identity": validation_row["source_identity"],
            "source_signal_id": validation_row["source_signal_id"],
            "emitted_signal_id_preview": validation_row["emitted_signal_id"],
            "source_signal_timestamp": validation_row["source_signal_timestamp"],
            "lane_key_preview": validation_row["lane_key"],
            "betrayal_event_identity": validation_row["betrayal_event_identity"],
            "betrayal_event_identity_hash": validation_row["betrayal_event_identity_hash"],
            "outcome_windows": validation_row["outcome_windows"],
            "registry_valid": bool(validation.get("schema_complete")),
            "schema_complete_preview": bool(validation.get("schema_complete")),
            "resolver_ready_preview": resolver_ready,
            "missing_required_fields": _dedupe(missing),
            "evidence_sources_used": _dedupe(normalized.get("evidence_sources_used") or []),
            "paper_only": True,
            "live_authorized": False,
            "promotion_allowed": False,
            "why": _renormalization_why(resolver_ready=resolver_ready, missing=missing),
        }
    )


def _base_rows(
    *,
    normalizer: Mapping[str, Any],
    collector: Mapping[str, Any],
    entry_mode: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_tagged_rows(normalizer.get("normalized_source_rows_preview"), "r223_normalizer"))
    rows.extend(_tagged_rows(collector.get("source_identity_evidence_rows"), "r224a_source_identity"))
    rows.extend(_tagged_rows(entry_mode.get("entry_mode_evidence_rows"), "r225_entry_mode"))
    return _dedupe_raw_records(rows)


def _join_keys_for_row(row: Mapping[str, Any]) -> list[tuple[str, ...]]:
    keys: list[tuple[str, ...]] = []
    for field in ("source_signal_id", "source_identity", "emitted_signal_id", "emitted_signal_id_preview", "lane_key", "lane_key_preview"):
        value = _string_or_none(row.get(field))
        if value:
            keys.append((field.replace("_preview", ""), value))
    candidate = _candidate_label(row)
    timeframe = _string_or_none(row.get("timeframe")) or _candidate_timeframe(candidate)
    timestamp = _timestamp(row)
    if candidate and timeframe and timestamp:
        keys.append(("candidate_timeframe_timestamp", candidate, timeframe, timestamp))
    return keys


def _index_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    require: Any,
) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    index: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not require(row):
            continue
        for key in _join_keys_for_row(row):
            index.setdefault(key, []).append(dict(row))
    return index


def _matching_rows(row: Mapping[str, Any], index: Mapping[tuple[str, ...], Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in _join_keys_for_row(row):
        for match in index.get(key, []):
            stable = json.dumps(_sanitize(dict(match)), sort_keys=True, separators=(",", ":"))
            if stable in seen:
                continue
            seen.add(stable)
            result.append(dict(match))
    return result


def _top_level_status(*, record_renormalization: bool, confirmation_valid: bool, registry_valid: bool) -> str:
    if record_renormalization and not confirmation_valid:
        return BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_REJECTED
    if not registry_valid:
        return BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_BLOCKED
    return BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_READY


def _recommended_next_operator_move(renormalization_status: str, summary: Mapping[str, Any]) -> str:
    if renormalization_status == RENORMALIZED_RESOLVER_READY_PREVIEWS_AVAILABLE and summary.get("resolver_ready_preview_rows"):
        return "RUN_R224_BETRAYAL_NORMALIZED_SOURCE_ROW_APPEND"
    if renormalization_status in {RENORMALIZATION_NO_RESOLVER_READY_PREVIEWS, RENORMALIZED_PARTIAL_PREVIEWS_AVAILABLE}:
        return "RUN_R227_BETRAYAL_DIRECTION_COMPLETION"
    if renormalization_status in {RENORMALIZATION_ENTRY_MODE_STILL_BLOCKED, RENORMALIZATION_SOURCE_IDENTITY_STILL_BLOCKED}:
        return "CHECK_8M_CAPTURE_THRESHOLD"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(renormalization_status: str, gap_report: Mapping[str, Any]) -> str:
    if renormalization_status == RENORMALIZED_RESOLVER_READY_PREVIEWS_AVAILABLE:
        return "Review R224 append guard with R226 resolver_ready_preview_rows > 0; do not append in R226."
    if gap_report.get("missing_direction_rows"):
        return "Implement R227 direction completion from local evidence only; no config writes or live execution."
    if gap_report.get("missing_entry_mode_rows") or gap_report.get("missing_source_identity_rows"):
        return "Collect more explicit entry_mode/source_identity evidence; do not infer defaults or candidate-label identities."
    return "Keep R226 paper-only and review remaining registry gaps."


def _renormalization_why(*, resolver_ready: bool, missing: Sequence[str]) -> str:
    if resolver_ready:
        return "All registry-required betrayal_source_emitter_v2 fields are present; preview remains paper-only and not appended."
    if not missing:
        return "Schema is complete but row is not live-authorized; renormalization is preview-only."
    return f"Renormalization preview remains blocked; missing registry-required fields: {', '.join(missing)}."


def _registry_manifest(registry: Mapping[str, Any]) -> dict[str, Any]:
    manifest = registry.get("registry_manifest") if isinstance(registry.get("registry_manifest"), Mapping) else registry
    return dict(manifest) if isinstance(manifest, Mapping) else {}


def _registry_validation(registry: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not registry or not manifest:
        return {"valid": False, "missing_required_sections": ["registry_manifest"]}
    existing = registry.get("registry_validation") if isinstance(registry, Mapping) else {}
    if isinstance(existing, Mapping) and existing:
        return dict(existing)
    return validate_registry_entry(manifest)


def _missing_field(row: Mapping[str, Any], field: str) -> bool:
    if field == "lane_key":
        return "lane_key" in (row.get("missing_required_fields") or []) or not row.get("lane_key_preview")
    if field == "emitted_signal_id":
        return "emitted_signal_id" in (row.get("missing_required_fields") or []) or not row.get("emitted_signal_id_preview")
    return field in (row.get("missing_required_fields") or []) or not row.get(field)


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


def _hard_live_blockers() -> list[str]:
    return [
        "renormalization_is_preview_only",
        "betrayal_not_live_authorized",
        "betrayal_not_promoted",
        "config_writes_forbidden",
        "orders_forbidden",
        "binance_calls_forbidden",
        "live_authorization_forbidden",
    ]


def _latest_record(path: Path) -> dict[str, Any]:
    records = _read_ndjson(path)
    return records[-1] if records else {}


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
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                records.append(dict(value))
    return records


def _tagged_rows(value: Any, source: str) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        values = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = list(value)
    else:
        values = []
    return [_sanitize({**dict(row), "_source": source}) for row in values if isinstance(row, Mapping)]


def _dedupe_renormalized_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = (
            row.get("candidate"),
            row.get("symbol"),
            row.get("timeframe"),
            row.get("entry_mode"),
            row.get("source_signal_id"),
            row.get("source_signal_timestamp"),
            row.get("source_identity"),
            row.get("emitted_direction"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(row))
    return result


def _dedupe_raw_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for record in records:
        stable = json.dumps(_sanitize(dict(record)), sort_keys=True, separators=(",", ":"))
        if stable in seen:
            continue
        seen.add(stable)
        result.append(dict(record))
    return result


def _dedupe(values: Sequence[Any]) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _first_string(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _string_or_none(row.get(key))
        if value:
            return value
    return None


def _candidate_label(row: Mapping[str, Any]) -> str | None:
    return _string_or_none(row.get("candidate") or row.get("candidate_label") or row.get("label"))


def _candidate_timeframe(candidate: Any) -> str | None:
    text = _string_or_none(candidate)
    if not text:
        return None
    return text.split()[0] if text.split() else None


def _timestamp(row: Mapping[str, Any]) -> str | None:
    return _first_string(row, "source_signal_timestamp", "timestamp", "signal_timestamp", "emitted_at", "generated_at")


def _normal_direction(value: Any) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"long", "bull", "bullish", "buy"}:
        return "long"
    if lowered in {"short", "bear", "bearish", "sell"}:
        return "short"
    return None


def _entry_mode_blocked(value: Any) -> bool:
    text = _string_or_none(value)
    return text is None or text.lower() in {"unknown", "entry_unknown"}


def _generated_at_iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _string_or_none(value) or datetime.now(UTC).isoformat()


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, set):
        return sorted(_sanitize(item) for item in value)
    return value
