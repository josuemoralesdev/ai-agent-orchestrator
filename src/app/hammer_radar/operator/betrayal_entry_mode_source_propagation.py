"""R229 betrayal entry_mode source propagation.

Paper-only source propagation preview for future betrayal rows. It composes
R227 direction completion, R226 renormalization, R225 entry-mode evidence, and
R224A source identity evidence, but only appends its own audit ledger after an
exact confirmation phrase.
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
from src.app.hammer_radar.operator.betrayal_entry_mode_evidence_wiring import (
    extract_entry_mode_from_lane_key,
    extract_entry_mode_from_signal_id,
    validate_entry_mode_against_registry,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.registry_wiring_betrayal_source_family import (
    validate_betrayal_source_row_against_registry,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import validate_registry_entry

BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_READY = "BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_READY"
BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_REJECTED = "BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_REJECTED"
BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_RECORDED = "BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_RECORDED"
BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_BLOCKED = "BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_BLOCKED"
BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_ERROR = "BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_ERROR"

ENTRY_MODE_SOURCE_PROPAGATION_RESOLVER_READY_PREVIEWS_AVAILABLE = (
    "ENTRY_MODE_SOURCE_PROPAGATION_RESOLVER_READY_PREVIEWS_AVAILABLE"
)
ENTRY_MODE_SOURCE_PROPAGATION_PARTIAL_PREVIEWS_AVAILABLE = "ENTRY_MODE_SOURCE_PROPAGATION_PARTIAL_PREVIEWS_AVAILABLE"
ENTRY_MODE_SOURCE_PROPAGATION_STILL_BLOCKED = "ENTRY_MODE_SOURCE_PROPAGATION_STILL_BLOCKED"
ENTRY_MODE_SOURCE_PROPAGATION_NO_RESOLVER_READY_PREVIEWS = "ENTRY_MODE_SOURCE_PROPAGATION_NO_RESOLVER_READY_PREVIEWS"
ENTRY_MODE_SOURCE_PROPAGATION_NOT_LIVE_AUTHORIZED = "ENTRY_MODE_SOURCE_PROPAGATION_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION"
LEDGER_FILENAME = "betrayal_entry_mode_source_propagation.ndjson"
SCHEMA_VERSION = "betrayal_source_emitter_v2"
SOURCE_TYPE = "betrayal_source_emitter"
DEFAULT_SYMBOL = "BTCUSDT"
OUTCOME_WINDOWS = [1, 3, 5, 10, 21, 34, 55]
CONFIRM_BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL ENTRY MODE SOURCE PROPAGATION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "historical_ledger_rewritten": False,
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
    "logs/hammer_radar_forward/betrayal_direction_completion.ndjson",
    "logs/hammer_radar_forward/betrayal_renormalize_with_entry_mode.ndjson",
    "logs/hammer_radar_forward/betrayal_entry_mode_evidence_wiring.ndjson",
    "logs/hammer_radar_forward/betrayal_source_identity_evidence_collector.ndjson",
    "logs/hammer_radar_forward/betrayal_source_identity_normalizer.ndjson",
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
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_entry_mode_source_propagation(
    *,
    log_dir: str | Path | None = None,
    record_propagation: bool = False,
    confirm_betrayal_entry_mode_source_propagation: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_entry_mode_source_propagation
        == CONFIRM_BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_RECORDING_PHRASE
    )
    try:
        direction_completion = load_latest_betrayal_direction_completion(log_dir=resolved_log_dir)
        entry_mode = load_latest_betrayal_entry_mode_evidence_wiring(log_dir=resolved_log_dir)
        source_identity = load_latest_betrayal_source_identity_evidence_collector(log_dir=resolved_log_dir)
        renormalization = load_latest_betrayal_renormalize_with_entry_mode(log_dir=resolved_log_dir)
        registry = load_latest_strategy_evidence_registry(log_dir=resolved_log_dir)
        shadow_outcomes = load_betrayal_shadow_outcomes(log_dir=resolved_log_dir)
        paper_signals = load_betrayal_paper_signals(log_dir=resolved_log_dir)
        for filename in (
            "betrayal_source_identity_normalizer.ndjson",
            "betrayal_aggregate_decomposition.ndjson",
            "betrayal_source_emitter_refresh.ndjson",
            "betrayal_direction_split_resolver.ndjson",
            "betrayal_event_tracker.ndjson",
            "betrayal_true_inverse_refresh.ndjson",
            "betrayal_integration_recheck.ndjson",
        ):
            _latest_record(resolved_log_dir / filename)

        manifest = _registry_manifest(registry)
        registry_validation = _registry_validation(registry, manifest)
        rows = build_entry_mode_propagated_rows_preview(
            betrayal_direction_completion=direction_completion,
            betrayal_entry_mode_evidence_wiring=entry_mode,
            betrayal_source_identity_evidence_collector=source_identity,
            betrayal_renormalize_with_entry_mode=renormalization,
            strategy_evidence_registry=registry,
            betrayal_shadow_outcomes=shadow_outcomes,
            betrayal_paper_signals=paper_signals,
            generated_at=generated_at,
        )
        summary = build_source_propagation_summary(rows)
        gap_report = build_source_propagation_gap_report(rows)
        recommendations = build_source_propagation_recommendations(gap_report=gap_report, summary=summary)
        source_status = classify_betrayal_source_propagation_status(rows=rows, gap_report=gap_report)
        payload = {
            "status": _top_level_status(
                record_propagation=record_propagation,
                confirmation_valid=confirmation_valid,
                registry_valid=bool(registry_validation.get("valid")),
            ),
            "generated_at": generated_at.isoformat(),
            "propagation_recorded": False,
            "propagation_id": None,
            "record_propagation_requested": bool(record_propagation),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "family": "betrayal",
                "registry_backed": True,
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "direction_completion_found": bool(direction_completion.get("direction_completed_rows_preview")),
                "entry_mode_evidence_found": bool(entry_mode.get("entry_mode_evidence_rows")),
                "source_identity_evidence_found": bool(source_identity.get("source_identity_evidence_rows")),
                "renormalization_found": bool(renormalization.get("renormalized_source_rows_preview")),
                "registry_found": bool(registry),
                "registry_valid": bool(registry_validation.get("valid")),
                "shadow_outcomes_found": bool(shadow_outcomes),
                "paper_signals_found": bool(paper_signals),
            },
            "entry_mode_propagated_rows_preview": rows,
            "source_propagation_summary": summary,
            "source_propagation_gap_report": gap_report,
            "source_propagation_recommendations": recommendations,
            "source_propagation_status": source_status,
            "recommended_next_operator_move": _recommended_next_operator_move(source_status, summary),
            "recommended_next_engineering_move": _recommended_next_engineering_move(source_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_propagation and confirmation_valid and registry_validation.get("valid"):
            record = append_betrayal_entry_mode_source_propagation_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_RECORDED
            payload["propagation_recorded"] = True
            payload["propagation_id"] = record["propagation_id"]
            payload["ledger_path"] = str(betrayal_entry_mode_source_propagation_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_ERROR,
                "generated_at": generated_at.isoformat(),
                "propagation_recorded": False,
                "propagation_id": None,
                "record_propagation_requested": bool(record_propagation),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {"family": "betrayal", "registry_backed": True, "paper_only": True, "live_authorized": False},
                "input_summary": {},
                "entry_mode_propagated_rows_preview": [],
                "source_propagation_summary": build_source_propagation_summary([]),
                "source_propagation_gap_report": build_source_propagation_gap_report([]),
                "source_propagation_recommendations": [],
                "source_propagation_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R229 source propagation error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_direction_completion(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_direction_completion.ndjson")


def load_latest_betrayal_entry_mode_evidence_wiring(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_entry_mode_evidence_wiring.ndjson")


def load_latest_betrayal_source_identity_evidence_collector(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_source_identity_evidence_collector.ndjson")


def load_latest_betrayal_renormalize_with_entry_mode(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_renormalize_with_entry_mode.ndjson")


def load_latest_strategy_evidence_registry(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "strategy_evidence_registry.ndjson")


def load_betrayal_shadow_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    resolved = get_log_dir(log_dir, use_env=True)
    rows = []
    for filename in ("betrayal_shadow_outcomes.ndjson", "betrayal_shadow_resolutions.ndjson"):
        rows.extend(_read_ndjson(resolved / filename))
    return _dedupe_raw_records(rows)


def load_betrayal_paper_signals(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_paper_signals.ndjson")


def build_source_propagation_join_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    keys = _join_keys_for_row(row)
    return keys[0] if keys else ("empty",)


def index_entry_mode_source_evidence(
    rows: Sequence[Mapping[str, Any]],
    *,
    registry_manifest: Mapping[str, Any],
) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    index: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        mode, source = _entry_mode_with_source(row, registry_manifest=registry_manifest)
        validation = validate_entry_mode_against_registry(mode, registry_manifest)
        if not validation.get("valid"):
            continue
        indexed = {**dict(row), "_entry_mode_source": source, "entry_mode": validation["entry_mode"]}
        for key in _join_keys_for_row(indexed):
            index.setdefault(key, []).append(indexed)
    return index


def propagate_entry_mode_from_source(
    row: Mapping[str, Any],
    *,
    source_evidence_index: Mapping[tuple[str, ...], Sequence[Mapping[str, Any]]] | None = None,
    registry_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    propagated = dict(row)
    sources = list(propagated.get("evidence_sources_used") or propagated.get("direction_completion_sources_used") or [])
    mode, source = _entry_mode_with_source(propagated, registry_manifest=registry_manifest)
    validation = validate_entry_mode_against_registry(mode, registry_manifest)
    if validation.get("valid"):
        propagated["entry_mode"] = validation["entry_mode"]
        propagated["entry_mode_propagation_source"] = _public_source(source)
        sources.append(f"entry_mode:{_public_source(source)}")
    else:
        for evidence in _matching_rows(propagated, source_evidence_index or {}):
            mode, source = _entry_mode_with_source(evidence, registry_manifest=registry_manifest)
            validation = validate_entry_mode_against_registry(mode, registry_manifest)
            if validation.get("valid"):
                propagated["entry_mode"] = validation["entry_mode"]
                propagated["entry_mode_propagation_source"] = _public_source(source)
                evidence_source = evidence.get("_source") or evidence.get("source") or "source_evidence"
                sources.append(f"entry_mode:{_public_source(source)}:{evidence_source}")
                break
    if "entry_mode_propagation_source" not in propagated:
        propagated["entry_mode_propagation_source"] = "none"
    propagated["evidence_sources_used"] = _dedupe(sources)
    return _sanitize(propagated)


def build_lane_key_preview(row: Mapping[str, Any]) -> str | None:
    symbol = _string_or_none(row.get("symbol"))
    timeframe = _string_or_none(row.get("timeframe"))
    emitted_direction = _normal_direction(row.get("emitted_direction"))
    entry_mode = _string_or_none(row.get("entry_mode"))
    if not (symbol and timeframe and emitted_direction and entry_mode):
        return None
    return f"{symbol}|{timeframe}|{emitted_direction}|{entry_mode.lower()}"


def build_emitted_signal_id_preview(row: Mapping[str, Any]) -> str | None:
    source_identity = _string_or_none(row.get("source_identity"))
    emitted_direction = _normal_direction(row.get("emitted_direction"))
    timestamp = _timestamp(row)
    if not (source_identity and emitted_direction and timestamp):
        return None
    digest = hashlib.sha256(f"{source_identity}|{emitted_direction}|{timestamp}".encode("utf-8")).hexdigest()[:16]
    return f"betrayal_emitted_preview|{source_identity}|{emitted_direction}|{digest}"


def validate_propagated_row_against_registry(
    row: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    validation = validate_betrayal_source_row_against_registry(row, registry_manifest=registry_manifest)
    missing = list(validation.get("missing_required_fields") or [])
    entry_validation = validate_entry_mode_against_registry(row.get("entry_mode"), registry_manifest)
    if not entry_validation.get("valid") and "entry_mode" not in missing:
        missing.append("entry_mode")
    if row.get("paper_only") is not True and "paper_only_true" not in missing:
        missing.append("paper_only_true")
    if row.get("live_authorized") is not False and "live_authorized_false" not in missing:
        missing.append("live_authorized_false")
    if row.get("promotion_allowed") is not False and "promotion_allowed_false" not in missing:
        missing.append("promotion_allowed_false")
    if _normal_direction(row.get("emitted_direction")) != _normal_direction(row.get("inverse_direction")):
        missing.append("emitted_direction_equals_inverse_direction")
    schema_complete = not _dedupe(missing)
    return _sanitize(
        {
            **dict(validation),
            "schema_complete": schema_complete,
            "row_status": "registry_valid" if schema_complete else "blocked_missing_fields",
            "missing_required_fields": _dedupe(missing),
            "blocked_from_resolver": not schema_complete,
        }
    )


def build_entry_mode_propagated_rows_preview(
    *,
    betrayal_direction_completion: Mapping[str, Any],
    betrayal_entry_mode_evidence_wiring: Mapping[str, Any],
    betrayal_source_identity_evidence_collector: Mapping[str, Any],
    betrayal_renormalize_with_entry_mode: Mapping[str, Any],
    strategy_evidence_registry: Mapping[str, Any],
    betrayal_shadow_outcomes: Sequence[Mapping[str, Any]],
    betrayal_paper_signals: Sequence[Mapping[str, Any]],
    generated_at: datetime | str | None = None,
) -> list[dict[str, Any]]:
    manifest = _registry_manifest(strategy_evidence_registry)
    evidence_rows = _collect_entry_mode_source_rows(
        direction_completion=betrayal_direction_completion,
        entry_mode=betrayal_entry_mode_evidence_wiring,
        source_identity=betrayal_source_identity_evidence_collector,
        renormalization=betrayal_renormalize_with_entry_mode,
        shadow_outcomes=betrayal_shadow_outcomes,
        paper_signals=betrayal_paper_signals,
    )
    evidence_index = index_entry_mode_source_evidence(evidence_rows, registry_manifest=manifest)
    rows = []
    for raw in _base_rows(betrayal_direction_completion, betrayal_renormalize_with_entry_mode):
        propagated = propagate_entry_mode_from_source(raw, source_evidence_index=evidence_index, registry_manifest=manifest)
        rows.append(_build_propagated_row(propagated, registry_manifest=manifest, generated_at=generated_at))
    return _dedupe_propagated_rows(rows)


def build_source_propagation_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "rows_reviewed": len(rows),
        "rows_with_entry_mode_before": sum(1 for row in rows if row.get("entry_mode_before")),
        "rows_with_entry_mode_after": sum(1 for row in rows if row.get("entry_mode")),
        "rows_with_lane_key_preview": sum(1 for row in rows if row.get("lane_key_preview")),
        "rows_with_emitted_signal_id_preview": sum(1 for row in rows if row.get("emitted_signal_id_preview")),
        "resolver_ready_preview_rows": sum(1 for row in rows if row.get("resolver_ready_preview")),
        "partial_preview_rows": sum(1 for row in rows if row.get("schema_complete_preview") and not row.get("resolver_ready_preview")),
        "blocked_rows": sum(1 for row in rows if not row.get("schema_complete_preview")),
    }


def build_source_propagation_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "missing_entry_mode_rows": sum(1 for row in rows if _missing_field(row, "entry_mode")),
        "missing_lane_key_rows": sum(1 for row in rows if _missing_field(row, "lane_key")),
        "missing_source_identity_rows": sum(1 for row in rows if _missing_field(row, "source_identity")),
        "missing_direction_rows": sum(
            1
            for row in rows
            if not row.get("original_direction") or not row.get("inverse_direction") or not row.get("emitted_direction")
        ),
        "emitted_direction_mismatch_rows": sum(
            1
            for row in rows
            if row.get("emitted_direction") and row.get("inverse_direction") and row.get("emitted_direction") != row.get("inverse_direction")
        ),
        "registry_invalid_rows": sum(1 for row in rows if not row.get("registry_valid")),
        "resolver_ready_preview_rows": sum(1 for row in rows if row.get("resolver_ready_preview")),
        "hard_live_blockers": _hard_live_blockers(),
    }


def build_source_propagation_recommendations(
    *,
    gap_report: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = []
    if gap_report.get("resolver_ready_preview_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RUN_R224_APPEND",
                "future_phase": "R224",
                "why": "R229 found registry-complete paper-only resolver-ready previews; append remains a separate guarded phase.",
            }
        )
    if gap_report.get("missing_entry_mode_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "WIRE_UPSTREAM_EMITTER_ENTRY_MODE",
                "future_phase": "R230",
                "why": "Rows still lack explicit local entry_mode evidence; R229 did not fabricate common defaults.",
            }
        )
    if gap_report.get("missing_lane_key_rows"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "WIRE_UPSTREAM_EMITTER_ENTRY_MODE",
                "future_phase": "R230",
                "why": "lane_key can only be previewed when symbol, timeframe, emitted_direction, and registry-valid entry_mode exist.",
            }
        )
    recommendations.append(
        {
            "priority": "MEDIUM",
            "recommended_action": "CHECK_8M_CAPTURE_THRESHOLD",
            "future_phase": "R228",
            "why": "Source propagation does not imply tiny-live readiness; BTCUSDT 8m short threshold remains separate.",
        }
    )
    if summary.get("rows_reviewed"):
        recommendations.append(
            {
                "priority": "LOW",
                "recommended_action": "KEEP_CONTEXT_ONLY",
                "future_phase": "R229",
                "why": "R229 is preview/record-only and cannot append normalized rows, write configs, or authorize live.",
            }
        )
    return recommendations


def classify_betrayal_source_propagation_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if gap_report.get("resolver_ready_preview_rows"):
        return ENTRY_MODE_SOURCE_PROPAGATION_RESOLVER_READY_PREVIEWS_AVAILABLE
    if any(row.get("entry_mode") or row.get("lane_key_preview") for row in rows):
        return ENTRY_MODE_SOURCE_PROPAGATION_PARTIAL_PREVIEWS_AVAILABLE
    if gap_report.get("registry_invalid_rows"):
        return ENTRY_MODE_SOURCE_PROPAGATION_NO_RESOLVER_READY_PREVIEWS
    if all(row.get("live_authorized") is False for row in rows):
        return ENTRY_MODE_SOURCE_PROPAGATION_NOT_LIVE_AUTHORIZED
    return ENTRY_MODE_SOURCE_PROPAGATION_STILL_BLOCKED


def append_betrayal_entry_mode_source_propagation_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_entry_mode_source_propagation_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "propagation_id": str(record.get("propagation_id") or f"r229_betrayal_entry_mode_source_propagation_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_propagation_requested": bool(record.get("record_propagation_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "entry_mode_propagated_rows_preview": list(record.get("entry_mode_propagated_rows_preview") or []),
            "source_propagation_summary": dict(record.get("source_propagation_summary") or {}),
            "source_propagation_gap_report": dict(record.get("source_propagation_gap_report") or {}),
            "source_propagation_recommendations": list(record.get("source_propagation_recommendations") or []),
            "source_propagation_status": record.get("source_propagation_status"),
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


def load_betrayal_entry_mode_source_propagation_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_entry_mode_source_propagation_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def summarize_betrayal_entry_mode_source_propagation_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    summary = latest.get("source_propagation_summary") if isinstance(latest.get("source_propagation_summary"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "source_propagation_status_counts": dict(
            sorted(Counter(str(record.get("source_propagation_status") or "UNKNOWN") for record in records).items())
        ),
        "last_propagation_id": latest.get("propagation_id") if isinstance(latest, Mapping) else None,
        "last_rows_reviewed": summary.get("rows_reviewed"),
        "last_resolver_ready_preview_rows": summary.get("resolver_ready_preview_rows"),
        "safety": dict(SAFETY),
    }


def betrayal_entry_mode_source_propagation_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_entry_mode_source_propagation_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _build_propagated_row(
    row: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
    generated_at: datetime | str | None,
) -> dict[str, Any]:
    normalized = dict(row)
    entry_mode_before = _string_or_none(normalized.get("entry_mode_before") or normalized.get("_entry_mode_before"))
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
    normalized["source_identity"] = _string_or_none(normalized.get("source_identity"))
    normalized["source_signal_id"] = _first_string(normalized, "source_signal_id", "signal_id", "original_signal_id")
    normalized["source_signal_timestamp"] = _timestamp(normalized)
    normalized["emitted_at"] = _string_or_none(normalized.get("emitted_at")) or _generated_at_iso(generated_at)
    normalized["emitted_signal_id_preview"] = (
        _string_or_none(normalized.get("emitted_signal_id") or normalized.get("emitted_signal_id_preview"))
        or build_emitted_signal_id_preview(normalized)
    )
    normalized["lane_key_preview"] = _string_or_none(normalized.get("lane_key") or normalized.get("lane_key_preview"))
    if not normalized["lane_key_preview"]:
        normalized["lane_key_preview"] = build_lane_key_preview(normalized)
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
    validation = validate_propagated_row_against_registry(validation_row, registry_manifest=registry_manifest)
    missing = list(validation.get("missing_required_fields") or [])
    resolver_ready = bool(
        validation.get("schema_complete")
        and validation_row["emitted_direction"]
        and validation_row["emitted_direction"] == validation_row["inverse_direction"]
    )
    return _sanitize(
        {
            "candidate": validation_row["candidate"],
            "symbol": validation_row["symbol"],
            "timeframe": validation_row["timeframe"],
            "entry_mode": validation_row["entry_mode"],
            "entry_mode_before": entry_mode_before,
            "entry_mode_propagation_source": normalized.get("entry_mode_propagation_source") or "none",
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
            "why": _propagation_why(resolver_ready=resolver_ready, missing=missing),
        }
    )


def _collect_entry_mode_source_rows(
    *,
    direction_completion: Mapping[str, Any],
    entry_mode: Mapping[str, Any],
    source_identity: Mapping[str, Any],
    renormalization: Mapping[str, Any],
    shadow_outcomes: Sequence[Mapping[str, Any]],
    paper_signals: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_tagged_rows(direction_completion.get("direction_completed_rows_preview"), "r227_direction_completion"))
    rows.extend(_tagged_rows(entry_mode.get("entry_mode_evidence_rows"), "r225_entry_mode"))
    rows.extend(_tagged_rows(source_identity.get("source_identity_evidence_rows"), "r224a_source_identity"))
    rows.extend(_tagged_rows(renormalization.get("renormalized_source_rows_preview"), "r226_renormalization"))
    rows.extend(_tagged_rows(shadow_outcomes, "shadow_outcome"))
    rows.extend(_tagged_rows(paper_signals, "paper_signal"))
    return _dedupe_raw_records(rows)


def _base_rows(direction_completion: Mapping[str, Any], renormalization: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = _tagged_rows(direction_completion.get("direction_completed_rows_preview"), "r227_direction_completion")
    if not rows:
        rows = _tagged_rows(renormalization.get("renormalized_source_rows_preview"), "r226_renormalization")
    for row in rows:
        row["_entry_mode_before"] = _string_or_none(row.get("entry_mode"))
    return _dedupe_raw_records(rows)


def _entry_mode_with_source(row: Mapping[str, Any], *, registry_manifest: Mapping[str, Any]) -> tuple[str | None, str]:
    explicit = _string_or_none(row.get("entry_mode") or row.get("source_entry_mode"))
    if explicit:
        return explicit.lower(), "explicit"
    lane_mode = extract_entry_mode_from_lane_key(row.get("lane_key") or row.get("lane_key_preview"))
    if lane_mode:
        return lane_mode, "lane_key"
    source_signal_mode = extract_entry_mode_from_signal_id(
        _first_string(row, "source_signal_id", "signal_id", "emitted_signal_id", "emitted_signal_id_preview"),
        registry_manifest=registry_manifest,
    )
    if source_signal_mode:
        return source_signal_mode, "source_signal_id"
    source_capture_mode = extract_entry_mode_from_signal_id(
        _first_string(row, "source_capture_id", "capture_id", "candidate_id"),
        registry_manifest=registry_manifest,
    )
    if source_capture_mode:
        return source_capture_mode, "source_signal_id"
    contract_mode = _string_or_none(row.get("registry_contract_entry_mode") or row.get("source_contract_entry_mode"))
    if contract_mode and _source_contract_carries_entry_mode(row):
        return contract_mode.lower(), "source_contract"
    return None, "none"


def _source_contract_carries_entry_mode(row: Mapping[str, Any]) -> bool:
    haystack = "|".join(
        str(row.get(key) or "").lower()
        for key in ("source_family_contract", "entry_mode_contract", "source_contract", "_source", "source")
    )
    return "entry_mode" in haystack or "source_contract" in haystack or "registry_contract" in haystack


def _join_keys_for_row(row: Mapping[str, Any]) -> list[tuple[str, ...]]:
    keys: list[tuple[str, ...]] = []
    for field in (
        "source_signal_id",
        "source_capture_id",
        "source_identity",
        "emitted_signal_id",
        "emitted_signal_id_preview",
        "lane_key",
        "lane_key_preview",
    ):
        value = _string_or_none(row.get(field))
        if value:
            keys.append((field.replace("_preview", ""), value))
    candidate = _candidate_label(row)
    timeframe = _string_or_none(row.get("timeframe")) or _candidate_timeframe(candidate)
    timestamp = _timestamp(row)
    if candidate and timeframe and timestamp:
        keys.append(("candidate_timeframe_timestamp", candidate, timeframe, timestamp))
    return keys


def _matching_rows(row: Mapping[str, Any], index: Mapping[tuple[str, ...], Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    result = []
    seen: set[str] = set()
    for key in _join_keys_for_row(row):
        for match in index.get(key, []):
            stable = json.dumps(_sanitize(dict(match)), sort_keys=True, separators=(",", ":"))
            if stable in seen:
                continue
            seen.add(stable)
            result.append(dict(match))
    return result


def _top_level_status(*, record_propagation: bool, confirmation_valid: bool, registry_valid: bool) -> str:
    if record_propagation and not confirmation_valid:
        return BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_REJECTED
    if not registry_valid:
        return BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_BLOCKED
    return BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_READY


def _recommended_next_operator_move(source_status: str, summary: Mapping[str, Any]) -> str:
    if source_status == ENTRY_MODE_SOURCE_PROPAGATION_RESOLVER_READY_PREVIEWS_AVAILABLE and summary.get("resolver_ready_preview_rows"):
        return "RUN_R224_BETRAYAL_NORMALIZED_SOURCE_ROW_APPEND"
    if source_status == ENTRY_MODE_SOURCE_PROPAGATION_PARTIAL_PREVIEWS_AVAILABLE:
        return "CHECK_8M_CAPTURE_THRESHOLD"
    return "KEEP_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(source_status: str, gap_report: Mapping[str, Any]) -> str:
    if source_status == ENTRY_MODE_SOURCE_PROPAGATION_RESOLVER_READY_PREVIEWS_AVAILABLE:
        return "Update R224 append guard to require R229 resolver_ready_preview_rows > 0; do not append in R229."
    if gap_report.get("missing_entry_mode_rows") or gap_report.get("missing_lane_key_rows"):
        return "Implement R230 upstream emitter entry_mode and lane_key contract for future betrayal rows only."
    return "Keep R229 paper-only and review remaining registry gaps."


def _propagation_why(*, resolver_ready: bool, missing: Sequence[str]) -> str:
    if resolver_ready:
        return "All registry-required fields are present after explicit source propagation; preview remains paper-only and not appended."
    if not missing:
        return "Schema is complete but source propagation remains preview-only and not live-authorized."
    return f"Source propagation preview remains blocked; missing registry-required fields: {', '.join(missing)}."


def _registry_manifest(registry: Mapping[str, Any]) -> dict[str, Any]:
    manifest = registry.get("registry_manifest") if isinstance(registry, Mapping) else {}
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
        "source_propagation_is_preview_only",
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
    rows = []
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
                rows.append(_sanitize(dict(value)))
    return rows


def _tagged_rows(value: Any, source: str) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        values = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = list(value)
    else:
        values = []
    return [{**dict(row), "_source": source} for row in values if isinstance(row, Mapping)]


def _dedupe_propagated_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result = []
    for row in rows:
        key = (
            row.get("candidate"),
            row.get("timeframe"),
            row.get("source_signal_id"),
            row.get("source_signal_timestamp"),
            row.get("entry_mode"),
            row.get("emitted_direction"),
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
        stable = json.dumps(_sanitize(dict(row)), sort_keys=True, separators=(",", ":"))
        if stable in seen:
            continue
        seen.add(stable)
        result.append(_sanitize(dict(row)))
    return result


def _dedupe(values: Sequence[Any]) -> list[Any]:
    result = []
    for value in values:
        if value in result:
            continue
        result.append(value)
    return result


def _public_source(source: str) -> str:
    if source in {"explicit", "lane_key", "source_signal_id", "source_contract"}:
        return source
    if source == "source_capture_id":
        return "source_signal_id"
    return "none"


def _candidate_label(row: Mapping[str, Any]) -> str | None:
    return _string_or_none(row.get("candidate") or row.get("candidate_label") or row.get("label"))


def _candidate_timeframe(candidate: Any) -> str | None:
    text = _string_or_none(candidate)
    if not text:
        return None
    for part in text.replace("_", " ").split():
        if part.endswith(("m", "H", "D")) and any(ch.isdigit() for ch in part):
            return part
    return None


def _normal_direction(value: Any) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    text = text.lower()
    if text in {"long", "bull", "bullish", "up"}:
        return "long"
    if text in {"short", "bear", "bearish", "down"}:
        return "short"
    return None


def _timestamp(row: Mapping[str, Any]) -> str | None:
    return _first_string(
        row,
        "source_signal_timestamp",
        "signal_timestamp",
        "timestamp",
        "event_timestamp",
        "captured_at",
        "emitted_at",
    )


def _generated_at_iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _string_or_none(value) or datetime.now(UTC).isoformat()


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
    if not text or text.lower() in {"none", "null", "nan"}:
        return None
    return text


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
