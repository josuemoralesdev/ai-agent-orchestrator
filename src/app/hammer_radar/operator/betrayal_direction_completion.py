"""R227 betrayal direction completion.

Paper-only preview surface that completes betrayal source direction fields
only from local, explicit evidence. It does not append normalized source rows,
write configs, call Binance/network, promote betrayal, or authorize live.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_event_tracker import build_betrayal_event_identity
from src.app.hammer_radar.operator.betrayal_renormalize_with_entry_mode import (
    build_emitted_signal_id_preview,
    build_lane_key_preview,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.registry_wiring_betrayal_source_family import (
    validate_betrayal_source_row_against_registry,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import validate_registry_entry

BETRAYAL_DIRECTION_COMPLETION_READY = "BETRAYAL_DIRECTION_COMPLETION_READY"
BETRAYAL_DIRECTION_COMPLETION_REJECTED = "BETRAYAL_DIRECTION_COMPLETION_REJECTED"
BETRAYAL_DIRECTION_COMPLETION_RECORDED = "BETRAYAL_DIRECTION_COMPLETION_RECORDED"
BETRAYAL_DIRECTION_COMPLETION_BLOCKED = "BETRAYAL_DIRECTION_COMPLETION_BLOCKED"
BETRAYAL_DIRECTION_COMPLETION_ERROR = "BETRAYAL_DIRECTION_COMPLETION_ERROR"

DIRECTION_COMPLETION_RESOLVER_READY_PREVIEWS_AVAILABLE = "DIRECTION_COMPLETION_RESOLVER_READY_PREVIEWS_AVAILABLE"
DIRECTION_COMPLETION_PARTIAL_PREVIEWS_AVAILABLE = "DIRECTION_COMPLETION_PARTIAL_PREVIEWS_AVAILABLE"
DIRECTION_COMPLETION_STILL_BLOCKED = "DIRECTION_COMPLETION_STILL_BLOCKED"
DIRECTION_COMPLETION_ENTRY_MODE_STILL_BLOCKED = "DIRECTION_COMPLETION_ENTRY_MODE_STILL_BLOCKED"
DIRECTION_COMPLETION_NO_RESOLVER_READY_PREVIEWS = "DIRECTION_COMPLETION_NO_RESOLVER_READY_PREVIEWS"
DIRECTION_COMPLETION_NOT_LIVE_AUTHORIZED = "DIRECTION_COMPLETION_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_DIRECTION_COMPLETION"
LEDGER_FILENAME = "betrayal_direction_completion.ndjson"
SCHEMA_VERSION = "betrayal_source_emitter_v2"
SOURCE_TYPE = "betrayal_source_emitter"
DEFAULT_SYMBOL = "BTCUSDT"
OUTCOME_WINDOWS = [1, 3, 5, 10, 21, 34, 55]
CONFIRM_BETRAYAL_DIRECTION_COMPLETION_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL DIRECTION COMPLETION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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


def build_betrayal_direction_completion(
    *,
    log_dir: str | Path | None = None,
    record_completion: bool = False,
    confirm_betrayal_direction_completion: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_betrayal_direction_completion == CONFIRM_BETRAYAL_DIRECTION_COMPLETION_RECORDING_PHRASE
    try:
        renormalization = load_latest_betrayal_renormalize_with_entry_mode(log_dir=resolved_log_dir)
        direction_split = load_latest_betrayal_direction_split_resolver(log_dir=resolved_log_dir)
        source_identity = load_latest_betrayal_source_identity_evidence_collector(log_dir=resolved_log_dir)
        entry_mode = load_latest_betrayal_entry_mode_evidence_wiring(log_dir=resolved_log_dir)
        registry = load_latest_strategy_evidence_registry(log_dir=resolved_log_dir)
        shadow_outcomes = load_betrayal_shadow_outcomes(log_dir=resolved_log_dir)
        true_paper_outcomes = load_betrayal_true_paper_outcomes(log_dir=resolved_log_dir)
        paper_signals = load_betrayal_paper_signals(log_dir=resolved_log_dir)
        aggregate = _latest_record(resolved_log_dir / "betrayal_aggregate_decomposition.ndjson")
        source_refresh = _latest_record(resolved_log_dir / "betrayal_source_emitter_refresh.ndjson")
        event_tracker = _latest_record(resolved_log_dir / "betrayal_event_tracker.ndjson")
        true_inverse = _latest_record(resolved_log_dir / "betrayal_true_inverse_refresh.ndjson")
        integration_recheck = _latest_record(resolved_log_dir / "betrayal_integration_recheck.ndjson")
        del aggregate, source_refresh, event_tracker, true_inverse, integration_recheck

        manifest = _registry_manifest(registry)
        registry_validation = _registry_validation(registry, manifest)
        rows = build_direction_completed_rows_preview(
            betrayal_renormalize_with_entry_mode=renormalization,
            betrayal_direction_split_resolver=direction_split,
            betrayal_source_identity_evidence_collector=source_identity,
            betrayal_entry_mode_evidence_wiring=entry_mode,
            strategy_evidence_registry=registry,
            betrayal_shadow_outcomes=shadow_outcomes,
            betrayal_true_paper_outcomes=true_paper_outcomes,
            betrayal_paper_signals=paper_signals,
            generated_at=generated_at,
        )
        summary = build_direction_completion_summary(rows)
        gap_report = build_direction_completion_gap_report(rows)
        recommendations = build_direction_completion_recommendations(gap_report=gap_report, summary=summary)
        completion_status = classify_betrayal_direction_completion_status(rows=rows, gap_report=gap_report)
        payload = {
            "status": _top_level_status(
                record_completion=record_completion,
                confirmation_valid=confirmation_valid,
                registry_valid=bool(registry_validation.get("valid")),
            ),
            "generated_at": generated_at.isoformat(),
            "completion_recorded": False,
            "completion_id": None,
            "record_completion_requested": bool(record_completion),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "family": "betrayal",
                "registry_backed": True,
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "renormalization_found": bool(renormalization.get("renormalized_source_rows_preview")),
                "direction_split_found": bool(direction_split.get("direction_split_resolution_rows")),
                "source_identity_evidence_found": bool(source_identity.get("source_identity_evidence_rows")),
                "entry_mode_evidence_found": bool(entry_mode.get("entry_mode_evidence_rows")),
                "registry_found": bool(registry),
                "registry_valid": bool(registry_validation.get("valid")),
                "shadow_outcomes_found": bool(shadow_outcomes),
                "true_paper_outcomes_found": bool(true_paper_outcomes),
                "paper_signals_found": bool(paper_signals),
            },
            "direction_completed_rows_preview": rows,
            "direction_completion_summary": summary,
            "direction_completion_gap_report": gap_report,
            "direction_completion_recommendations": recommendations,
            "direction_completion_status": completion_status,
            "recommended_next_operator_move": _recommended_next_operator_move(completion_status, summary),
            "recommended_next_engineering_move": _recommended_next_engineering_move(completion_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_completion and confirmation_valid and registry_validation.get("valid"):
            record = append_betrayal_direction_completion_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_DIRECTION_COMPLETION_RECORDED
            payload["completion_recorded"] = True
            payload["completion_id"] = record["completion_id"]
            payload["ledger_path"] = str(betrayal_direction_completion_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_DIRECTION_COMPLETION_ERROR,
                "generated_at": generated_at.isoformat(),
                "completion_recorded": False,
                "completion_id": None,
                "record_completion_requested": bool(record_completion),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {"family": "betrayal", "registry_backed": True, "paper_only": True, "live_authorized": False},
                "input_summary": {},
                "direction_completed_rows_preview": [],
                "direction_completion_summary": build_direction_completion_summary([]),
                "direction_completion_gap_report": build_direction_completion_gap_report([]),
                "direction_completion_recommendations": [],
                "direction_completion_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R227 direction completion error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_renormalize_with_entry_mode(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_renormalize_with_entry_mode.ndjson")


def load_latest_betrayal_direction_split_resolver(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_direction_split_resolver.ndjson")


def load_latest_betrayal_source_identity_evidence_collector(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_source_identity_evidence_collector.ndjson")


def load_latest_betrayal_entry_mode_evidence_wiring(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_entry_mode_evidence_wiring.ndjson")


def load_latest_strategy_evidence_registry(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "strategy_evidence_registry.ndjson")


def load_betrayal_shadow_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    resolved = get_log_dir(log_dir, use_env=True)
    rows = []
    for filename in ("betrayal_shadow_outcomes.ndjson", "betrayal_shadow_resolutions.ndjson"):
        rows.extend(_read_ndjson(resolved / filename))
    return _dedupe_raw_records(rows)


def load_betrayal_true_paper_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_true_paper_outcomes.ndjson")


def load_betrayal_paper_signals(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_paper_signals.ndjson")


def build_direction_join_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    keys = _join_keys_for_row(row)
    return keys[0] if keys else ("empty",)


def index_direction_evidence_rows(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    return _index_rows(rows, require=lambda row: bool(_direction_evidence(row)))


def complete_direction_fields(
    row: Mapping[str, Any],
    *,
    direction_evidence_index: Mapping[tuple[str, ...], Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    completed = dict(row)
    sources = list(completed.get("direction_completion_sources_used") or completed.get("evidence_sources_used") or [])
    original = _normal_direction(completed.get("original_direction"))
    inverse = _normal_direction(completed.get("inverse_direction"))
    emitted = _normal_direction(completed.get("emitted_direction"))

    if original:
        sources.append("original_direction:source_row")
    if inverse:
        sources.append("inverse_direction:source_row")
    if emitted:
        sources.append("emitted_direction:source_row")

    for evidence in _matching_rows(completed, direction_evidence_index or {}):
        evidence_direction = _direction_evidence(evidence)
        if not original and evidence_direction.get("original_direction"):
            original = str(evidence_direction["original_direction"])
            sources.append(f"original_direction:{evidence_direction['source']}")
        if not inverse and evidence_direction.get("inverse_direction") and original:
            inverse = str(evidence_direction["inverse_direction"])
            sources.append(f"inverse_direction:{evidence_direction['source']}")
        if not emitted and evidence_direction.get("emitted_direction") and inverse and evidence_direction.get("emitted_direction") == inverse:
            emitted = str(evidence_direction["emitted_direction"])
            sources.append(f"emitted_direction:{evidence_direction['source']}")
        if original and inverse and emitted:
            break

    parsed = _direction_from_source_signal_id(completed.get("source_signal_id"))
    if not original and parsed:
        original = parsed
        sources.append("original_direction:source_signal_id")
    if not inverse and original and _is_betrayal_inverse_family(completed):
        inverse = _opposite_direction(original)
        if inverse:
            sources.append("inverse_direction:opposite_of_original_for_betrayal_inverse_family")
    if not emitted and inverse and _is_betrayal_inverse_family(completed):
        emitted = inverse
        sources.append("emitted_direction:inverse_for_betrayal_inverse_family")

    completed["original_direction"] = original
    completed["inverse_direction"] = inverse
    completed["emitted_direction"] = emitted
    completed["direction_completion_sources_used"] = _dedupe(sources)
    return _sanitize(completed)


def validate_direction_completion_against_registry(
    row: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    validation = validate_betrayal_source_row_against_registry(row, registry_manifest=registry_manifest)
    missing = list(validation.get("missing_required_fields") or [])
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
            "missing_required_fields": _dedupe(missing),
            "blocked_from_resolver": not schema_complete,
            "row_status": "registry_valid" if schema_complete else "blocked_missing_fields",
        }
    )


def build_direction_completed_rows_preview(
    *,
    betrayal_renormalize_with_entry_mode: Mapping[str, Any],
    betrayal_direction_split_resolver: Mapping[str, Any],
    betrayal_source_identity_evidence_collector: Mapping[str, Any],
    betrayal_entry_mode_evidence_wiring: Mapping[str, Any],
    strategy_evidence_registry: Mapping[str, Any],
    betrayal_shadow_outcomes: Sequence[Mapping[str, Any]],
    betrayal_true_paper_outcomes: Sequence[Mapping[str, Any]],
    betrayal_paper_signals: Sequence[Mapping[str, Any]],
    generated_at: datetime | str | None = None,
) -> list[dict[str, Any]]:
    manifest = _registry_manifest(strategy_evidence_registry)
    evidence_rows = _collect_direction_evidence_rows(
        direction_split=betrayal_direction_split_resolver,
        source_identity=betrayal_source_identity_evidence_collector,
        entry_mode=betrayal_entry_mode_evidence_wiring,
        shadow_outcomes=betrayal_shadow_outcomes,
        true_paper_outcomes=betrayal_true_paper_outcomes,
        paper_signals=betrayal_paper_signals,
    )
    evidence_index = index_direction_evidence_rows(evidence_rows)
    rows = []
    for raw in _base_rows(betrayal_renormalize_with_entry_mode):
        completed = complete_direction_fields(raw, direction_evidence_index=evidence_index)
        rows.append(_build_completion_row(completed, registry_manifest=manifest, generated_at=generated_at))
    return _dedupe_completion_rows(rows)


def build_direction_completion_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "rows_reviewed": len(rows),
        "rows_with_original_direction": sum(1 for row in rows if row.get("original_direction")),
        "rows_with_inverse_direction": sum(1 for row in rows if row.get("inverse_direction")),
        "rows_with_emitted_direction": sum(1 for row in rows if row.get("emitted_direction")),
        "rows_with_emitted_direction_equals_inverse": sum(
            1 for row in rows if row.get("emitted_direction") and row.get("emitted_direction") == row.get("inverse_direction")
        ),
        "rows_with_entry_mode": sum(1 for row in rows if row.get("entry_mode")),
        "resolver_ready_preview_rows": sum(1 for row in rows if row.get("resolver_ready_preview")),
        "partial_preview_rows": sum(1 for row in rows if row.get("schema_complete_preview") and not row.get("resolver_ready_preview")),
        "blocked_rows": sum(1 for row in rows if not row.get("schema_complete_preview")),
    }


def build_direction_completion_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "missing_original_direction_rows": sum(1 for row in rows if not row.get("original_direction")),
        "missing_inverse_direction_rows": sum(1 for row in rows if not row.get("inverse_direction")),
        "missing_emitted_direction_rows": sum(1 for row in rows if not row.get("emitted_direction")),
        "emitted_direction_mismatch_rows": sum(
            1 for row in rows if row.get("emitted_direction") and row.get("inverse_direction") and row.get("emitted_direction") != row.get("inverse_direction")
        ),
        "missing_entry_mode_rows": sum(1 for row in rows if not row.get("entry_mode") or str(row.get("entry_mode")).lower() in {"unknown", "entry_unknown"}),
        "missing_lane_key_rows": sum(1 for row in rows if not row.get("lane_key_preview")),
        "registry_invalid_rows": sum(1 for row in rows if not row.get("registry_valid")),
        "resolver_ready_preview_rows": sum(1 for row in rows if row.get("resolver_ready_preview")),
        "hard_live_blockers": _hard_live_blockers(),
    }


def build_direction_completion_recommendations(
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
                "why": "R227 found registry-complete paper-only resolver-ready previews; append remains a separate guarded phase.",
            }
        )
    if gap_report.get("missing_original_direction_rows") or gap_report.get("missing_inverse_direction_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "WIRE_BETRAYAL_EMITTER_DIRECTION",
                "future_phase": "R228",
                "why": "Rows still need explicit original/inverse direction evidence; aggregate labels were not used as proof.",
            }
        )
    if gap_report.get("missing_entry_mode_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "COLLECT_MORE_ENTRY_MODE",
                "future_phase": "R225",
                "why": "Entry mode remains missing or blocked; common ladder mode was not fabricated.",
            }
        )
    recommendations.append(
        {
            "priority": "MEDIUM",
            "recommended_action": "CHECK_8M_CAPTURE_THRESHOLD",
            "future_phase": "R228",
            "why": "Direction completion is not tiny-live readiness; BTCUSDT 8m short still needs the capture threshold path checked separately.",
        }
    )
    if summary.get("rows_reviewed"):
        recommendations.append(
            {
                "priority": "LOW",
                "recommended_action": "KEEP_CONTEXT_ONLY",
                "future_phase": "R227",
                "why": "R227 is preview/record-only and cannot append normalized rows, promote betrayal, or authorize live.",
            }
        )
    return recommendations


def classify_betrayal_direction_completion_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if gap_report.get("resolver_ready_preview_rows"):
        return DIRECTION_COMPLETION_RESOLVER_READY_PREVIEWS_AVAILABLE
    if gap_report.get("missing_entry_mode_rows"):
        return DIRECTION_COMPLETION_ENTRY_MODE_STILL_BLOCKED
    if any(row.get("original_direction") or row.get("inverse_direction") or row.get("emitted_direction") for row in rows):
        return DIRECTION_COMPLETION_PARTIAL_PREVIEWS_AVAILABLE
    if gap_report.get("registry_invalid_rows"):
        return DIRECTION_COMPLETION_NO_RESOLVER_READY_PREVIEWS
    if all(row.get("live_authorized") is False for row in rows):
        return DIRECTION_COMPLETION_NOT_LIVE_AUTHORIZED
    return DIRECTION_COMPLETION_STILL_BLOCKED


def append_betrayal_direction_completion_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_direction_completion_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "completion_id": str(record.get("completion_id") or f"r227_betrayal_direction_completion_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_DIRECTION_COMPLETION_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_completion_requested": bool(record.get("record_completion_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "direction_completed_rows_preview": list(record.get("direction_completed_rows_preview") or []),
            "direction_completion_summary": dict(record.get("direction_completion_summary") or {}),
            "direction_completion_gap_report": dict(record.get("direction_completion_gap_report") or {}),
            "direction_completion_recommendations": list(record.get("direction_completion_recommendations") or []),
            "direction_completion_status": record.get("direction_completion_status"),
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


def load_betrayal_direction_completion_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_direction_completion_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def summarize_betrayal_direction_completion_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    summary = latest.get("direction_completion_summary") if isinstance(latest.get("direction_completion_summary"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "direction_completion_status_counts": dict(
            sorted(Counter(str(record.get("direction_completion_status") or "UNKNOWN") for record in records).items())
        ),
        "last_completion_id": latest.get("completion_id") if isinstance(latest, Mapping) else None,
        "last_rows_reviewed": summary.get("rows_reviewed"),
        "last_resolver_ready_preview_rows": summary.get("resolver_ready_preview_rows"),
        "safety": dict(SAFETY),
    }


def betrayal_direction_completion_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_direction_completion_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _build_completion_row(
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
    normalized["source_identity"] = _string_or_none(normalized.get("source_identity"))
    normalized["source_signal_id"] = _first_string(normalized, "source_signal_id", "signal_id", "original_signal_id")
    normalized["source_signal_timestamp"] = _timestamp(normalized)
    normalized["emitted_at"] = _string_or_none(normalized.get("emitted_at")) or _generated_at_iso(generated_at)
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
    validation = validate_direction_completion_against_registry(validation_row, registry_manifest=registry_manifest)
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
            "direction_completion_sources_used": _dedupe(normalized.get("direction_completion_sources_used") or []),
            "registry_valid": bool(validation.get("schema_complete")),
            "schema_complete_preview": bool(validation.get("schema_complete")),
            "resolver_ready_preview": resolver_ready,
            "missing_required_fields": _dedupe(missing),
            "paper_only": True,
            "live_authorized": False,
            "promotion_allowed": False,
            "why": _completion_why(resolver_ready=resolver_ready, missing=missing),
        }
    )


def _collect_direction_evidence_rows(
    *,
    direction_split: Mapping[str, Any],
    source_identity: Mapping[str, Any],
    entry_mode: Mapping[str, Any],
    shadow_outcomes: Sequence[Mapping[str, Any]],
    true_paper_outcomes: Sequence[Mapping[str, Any]],
    paper_signals: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_tagged_rows(direction_split.get("direction_split_resolution_rows"), "direction_split_resolver"))
    rows.extend(_tagged_rows(source_identity.get("source_identity_evidence_rows"), "source_identity_evidence"))
    rows.extend(_tagged_rows(entry_mode.get("entry_mode_evidence_rows"), "entry_mode_evidence"))
    rows.extend(_tagged_rows(shadow_outcomes, "shadow_outcome"))
    rows.extend(_tagged_rows(true_paper_outcomes, "true_paper_outcome"))
    rows.extend(_tagged_rows(paper_signals, "paper_signal"))
    return _dedupe_raw_records(rows)


def _base_rows(renormalization: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _tagged_rows(renormalization.get("renormalized_source_rows_preview"), "r226_renormalization")


def _direction_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    source = _evidence_source(row)
    original = _normal_direction(row.get("original_direction") or row.get("source_original_direction"))
    inverse = _normal_direction(row.get("inverse_direction"))
    emitted = _normal_direction(row.get("emitted_direction"))
    if not original and source in {"shadow_outcome", "true_paper_outcome", "paper_signal", "direction_split_resolver"}:
        original = _normal_direction(row.get("source_direction") or row.get("original_direction") or row.get("direction"))
    if not inverse and source in {"shadow_outcome", "true_paper_outcome", "direction_split_resolver", "source_identity_evidence"}:
        inverse = _normal_direction(row.get("shadow_direction") or row.get("betrayal_direction") or row.get("inverse_direction"))
    if not original:
        original = _direction_from_source_signal_id(row.get("source_signal_id") or row.get("original_signal_id") or row.get("signal_id"))
    if not inverse and original and _is_betrayal_inverse_family(row):
        inverse = _opposite_direction(original)
    if not emitted and inverse and _is_betrayal_inverse_family(row):
        emitted = inverse
    return _sanitize(
        {
            "source": source,
            "original_direction": original,
            "inverse_direction": inverse,
            "emitted_direction": emitted,
        }
    )


def _evidence_source(row: Mapping[str, Any]) -> str:
    source = str(row.get("_direction_source") or row.get("_source") or row.get("source") or row.get("_collector_source") or "unknown")
    if "direction_split" in source:
        return "direction_split_resolver"
    if "shadow" in source:
        return "shadow_outcome"
    if "true_paper" in source:
        return "true_paper_outcome"
    if "paper_signal" in source:
        return "paper_signal"
    if "source_identity" in source:
        return "source_identity_evidence"
    if "entry_mode" in source:
        return "entry_mode_evidence"
    return source


def _is_betrayal_inverse_family(row: Mapping[str, Any]) -> bool:
    haystack = "|".join(
        str(row.get(key) or "").lower()
        for key in (
            "schema_version",
            "source_type",
            "source_family",
            "candidate",
            "source",
            "_source",
            "_direction_source",
            "betrayal_event_identity",
        )
    )
    return (
        "betrayal" in haystack
        or "inverse" in haystack
        or "shadow" in haystack
        or "r226_renormalization" in haystack
        or "source_identity_evidence" in haystack
        or "direction_split_resolver" in haystack
    )


def _direction_from_source_signal_id(value: Any) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    parts = [part.strip().lower() for part in text.split("|")]
    for part in parts:
        direction = _normal_direction(part)
        if direction:
            return direction
    return None


def _join_keys_for_row(row: Mapping[str, Any]) -> list[tuple[str, ...]]:
    keys: list[tuple[str, ...]] = []
    for field in (
        "source_signal_id",
        "source_identity",
        "emitted_signal_id",
        "emitted_signal_id_preview",
        "lane_key",
        "lane_key_preview",
        "original_signal_id",
        "signal_id",
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


def _index_rows(rows: Sequence[Mapping[str, Any]], *, require: Any) -> dict[tuple[str, ...], list[dict[str, Any]]]:
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


def _top_level_status(*, record_completion: bool, confirmation_valid: bool, registry_valid: bool) -> str:
    if record_completion and not confirmation_valid:
        return BETRAYAL_DIRECTION_COMPLETION_REJECTED
    if not registry_valid:
        return BETRAYAL_DIRECTION_COMPLETION_BLOCKED
    return BETRAYAL_DIRECTION_COMPLETION_READY


def _recommended_next_operator_move(completion_status: str, summary: Mapping[str, Any]) -> str:
    if completion_status == DIRECTION_COMPLETION_RESOLVER_READY_PREVIEWS_AVAILABLE and summary.get("resolver_ready_preview_rows"):
        return "RUN_R224_BETRAYAL_NORMALIZED_SOURCE_ROW_APPEND"
    return "CHECK_8M_CAPTURE_THRESHOLD"


def _recommended_next_engineering_move(completion_status: str, gap_report: Mapping[str, Any]) -> str:
    if completion_status == DIRECTION_COMPLETION_RESOLVER_READY_PREVIEWS_AVAILABLE:
        return "Update R224 append guard to require R227 resolver_ready_preview_rows > 0; do not append in R227."
    if gap_report.get("missing_entry_mode_rows"):
        return "Collect more explicit entry_mode evidence; do not infer defaults."
    if gap_report.get("missing_original_direction_rows") or gap_report.get("missing_inverse_direction_rows"):
        return "Wire betrayal emitter direction at source; do not infer direction from aggregate labels."
    return "Keep R227 paper-only and continue tiny-live capture threshold monitoring."


def _completion_why(*, resolver_ready: bool, missing: Sequence[str]) -> str:
    if resolver_ready:
        return "All registry-required fields are present after local direction completion; preview remains paper-only and not appended."
    if not missing:
        return "Schema is complete but row is not live-authorized; completion is preview-only."
    return f"Direction completion preview remains blocked; missing registry-required fields: {', '.join(_dedupe(missing))}."


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
        "direction_completion_is_preview_only",
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
                records.append(_sanitize(value))
    return records


def _tagged_rows(value: Any, source: str) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        values = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = list(value)
    else:
        values = []
    return [_sanitize({**dict(row), "_direction_source": source}) for row in values if isinstance(row, Mapping)]


def _dedupe_completion_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
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
    return _first_string(row, "source_signal_timestamp", "timestamp", "signal_timestamp", "emitted_at", "generated_at", "created_at")


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


def _opposite_direction(value: Any) -> str | None:
    direction = _normal_direction(value)
    if direction == "long":
        return "short"
    if direction == "short":
        return "long"
    return None


def _generated_at_iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _string_or_none(value) or datetime.now(UTC).isoformat()


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
