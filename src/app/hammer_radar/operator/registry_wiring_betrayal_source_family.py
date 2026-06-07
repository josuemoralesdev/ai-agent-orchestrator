"""R219 registry wiring for the betrayal source family.

Paper-only audit wiring that consumes the R218 strategy evidence registry and
validates R217/R216/R215 betrayal rows against the registry-backed source
identity contract. It appends only its own R219 ledger when explicitly
confirmed.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.strategy_evidence_registry import validate_registry_entry

REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_READY = "REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_READY"
REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_REJECTED = "REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_REJECTED"
REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_RECORDED = "REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_RECORDED"
REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_BLOCKED = "REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_BLOCKED"
REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_ERROR = "REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_ERROR"

BETRAYAL_SOURCE_FAMILY_REGISTRY_WIRED = "BETRAYAL_SOURCE_FAMILY_REGISTRY_WIRED"
BETRAYAL_SOURCE_FAMILY_REGISTRY_GAPS_REMAIN = "BETRAYAL_SOURCE_FAMILY_REGISTRY_GAPS_REMAIN"
BETRAYAL_SOURCE_FAMILY_SOURCE_IDENTITY_BLOCKED = "BETRAYAL_SOURCE_FAMILY_SOURCE_IDENTITY_BLOCKED"
BETRAYAL_SOURCE_FAMILY_ENTRY_MODE_BLOCKED = "BETRAYAL_SOURCE_FAMILY_ENTRY_MODE_BLOCKED"
BETRAYAL_SOURCE_FAMILY_NOT_LIVE_AUTHORIZED = "BETRAYAL_SOURCE_FAMILY_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY"
LEDGER_FILENAME = "registry_wiring_betrayal_source_family.ndjson"
CONFIRM_REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_RECORDING_PHRASE = (
    "I CONFIRM REGISTRY WIRING BETRAYAL SOURCE FAMILY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

FALLBACK_BETRAYAL_CANDIDATES = (
    {"candidate_id": "222m_aggregate", "label": "222m aggregate", "timeframe": "222m"},
    {"candidate_id": "88m_aggregate", "label": "88m aggregate", "timeframe": "88m"},
    {"candidate_id": "55m_aggregate_if_available", "label": "55m aggregate_if_available", "timeframe": "55m"},
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
    "logs/hammer_radar_forward/strategy_evidence_registry.ndjson",
    "logs/hammer_radar_forward/betrayal_aggregate_decomposition.ndjson",
    "logs/hammer_radar_forward/betrayal_source_emitter_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_direction_split_resolver.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_registry_wiring_betrayal_source_family(
    *,
    log_dir: str | Path | None = None,
    record_wiring: bool = False,
    confirm_registry_wiring_betrayal_source_family: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_registry_wiring_betrayal_source_family
        == CONFIRM_REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_RECORDING_PHRASE
    )
    try:
        registry = load_latest_strategy_evidence_registry(log_dir=resolved_log_dir)
        aggregate = load_latest_betrayal_aggregate_decomposition(log_dir=resolved_log_dir)
        source_refresh = load_latest_betrayal_source_emitter_refresh(log_dir=resolved_log_dir)
        direction_split = load_latest_betrayal_direction_split_resolver(log_dir=resolved_log_dir)
        manifest = _registry_manifest(registry)
        registry_validation = _registry_validation(registry, manifest)
        candidate_view = build_registry_backed_betrayal_candidate_view(manifest)
        candidate_validation = [
            validate_betrayal_candidate_against_registry(candidate, registry_manifest=manifest)
            for candidate in candidate_view["candidates"]
        ]
        source_rows = _collect_source_rows(
            aggregate_decomposition=aggregate,
            source_emitter_refresh=source_refresh,
            direction_split_resolver=direction_split,
        )
        row_validation = [
            validate_betrayal_source_row_against_registry(row, registry_manifest=manifest)
            for row in source_rows
        ]
        missing_report = build_registry_backed_missing_field_report(row_validation)
        gap_report = build_registry_wiring_gap_report(
            registry_found=bool(registry),
            registry_validation=registry_validation,
            candidate_validation=candidate_validation,
            row_validation=row_validation,
            missing_field_report=missing_report,
        )
        wiring_status = classify_registry_wiring_betrayal_status(gap_report=gap_report, row_validation=row_validation)
        payload = {
            "status": _top_level_status(
                record_wiring=record_wiring,
                confirmation_valid=confirmation_valid,
                registry_found=bool(registry),
                registry_valid=bool(registry_validation.get("valid")),
            ),
            "generated_at": generated_at.isoformat(),
            "wiring_recorded": False,
            "wiring_id": None,
            "record_wiring_requested": bool(record_wiring),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "registry_backed": True,
                "family": "betrayal",
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "strategy_evidence_registry_found": bool(registry),
                "registry_valid": bool(registry_validation.get("valid")),
                "aggregate_decomposition_found": bool(aggregate),
                "source_emitter_refresh_found": bool(source_refresh),
                "direction_split_resolver_found": bool(direction_split),
            },
            "registry_backed_betrayal_candidate_view": candidate_view,
            "candidate_registry_validation": candidate_validation,
            "source_row_registry_validation": row_validation,
            "registry_backed_missing_field_report": missing_report,
            "registry_wiring_gap_report": gap_report,
            "registry_wiring_recommendations": build_registry_wiring_recommendations(gap_report=gap_report),
            "wiring_status": wiring_status,
            "recommended_next_operator_move": _recommended_next_operator_move(wiring_status),
            "recommended_next_engineering_move": _recommended_next_engineering_move(wiring_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_wiring and confirmation_valid and registry_validation.get("valid"):
            record = append_registry_wiring_betrayal_source_family_record(payload, log_dir=resolved_log_dir)
            payload["status"] = REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_RECORDED
            payload["wiring_recorded"] = True
            payload["wiring_id"] = record["wiring_id"]
            payload["ledger_path"] = str(registry_wiring_betrayal_source_family_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_ERROR,
                "generated_at": generated_at.isoformat(),
                "wiring_recorded": False,
                "wiring_id": None,
                "record_wiring_requested": bool(record_wiring),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {"registry_backed": True, "family": "betrayal", "paper_only": True, "live_authorized": False},
                "input_summary": {},
                "registry_backed_betrayal_candidate_view": _empty_candidate_view(),
                "candidate_registry_validation": [],
                "source_row_registry_validation": [],
                "registry_backed_missing_field_report": build_registry_backed_missing_field_report([]),
                "registry_wiring_gap_report": {
                    "registry_missing": True,
                    "registry_valid": False,
                    "betrayal_source_identity_blocked": True,
                    "entry_mode_blocked": True,
                    "hard_live_blockers": _hard_live_blockers(),
                },
                "registry_wiring_recommendations": [],
                "wiring_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R219 registry wiring builder error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_strategy_evidence_registry(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "strategy_evidence_registry.ndjson")


def load_latest_betrayal_aggregate_decomposition(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_aggregate_decomposition.ndjson")


def load_latest_betrayal_source_emitter_refresh(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_source_emitter_refresh.ndjson")


def load_latest_betrayal_direction_split_resolver(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_direction_split_resolver.ndjson")


def build_registry_backed_betrayal_candidate_view(registry_manifest: Mapping[str, Any]) -> dict[str, Any]:
    candidates_manifest = registry_manifest.get("betrayal_candidates") if isinstance(registry_manifest, Mapping) else {}
    candidates = []
    if isinstance(candidates_manifest, Mapping) and candidates_manifest:
        iterable = candidates_manifest.items()
    else:
        iterable = [(row["candidate_id"], row) for row in FALLBACK_BETRAYAL_CANDIDATES]
    for candidate_id, row in iterable:
        if not isinstance(row, Mapping):
            continue
        candidates.append(
            _sanitize(
                {
                    "candidate": row.get("label") or candidate_id,
                    "candidate_id": row.get("candidate_id") or candidate_id,
                    "timeframe": row.get("timeframe"),
                    "candidate_type": row.get("candidate_type") or "aggregate",
                    "paper_only": bool(row.get("paper_only", True)),
                    "live_authorized": bool(row.get("live_authorized", False)),
                    "promotion_allowed": bool(row.get("promotion_allowed", False)),
                    "required_before_promotion": list(row.get("required_before_promotion") or []),
                }
            )
        )
    return {
        "candidates": sorted(candidates, key=lambda row: str(row.get("candidate_id"))),
        "required_source_fields": _required_source_fields(registry_manifest),
        "required_evidence": _required_evidence(registry_manifest),
        "safety_defaults": _betrayal_safety_defaults(registry_manifest),
    }


def validate_betrayal_candidate_against_registry(
    candidate: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    registry_candidate = _registry_candidate_for(candidate, registry_manifest=registry_manifest)
    timeframes = {str(item) for item in registry_manifest.get("timeframes") or []} if isinstance(registry_manifest, Mapping) else set()
    safety_defaults = _betrayal_safety_defaults(registry_manifest)
    missing = []
    if not registry_candidate:
        missing.append("candidate")
    if not candidate.get("timeframe") or str(candidate.get("timeframe")) not in timeframes:
        missing.append("timeframe")
    if not safety_defaults.get("paper_only"):
        missing.append("paper_only")
    if safety_defaults.get("live_authorized"):
        missing.append("live_authorized_false")
    if safety_defaults.get("promotion_allowed"):
        missing.append("promotion_allowed_false")
    status = "valid" if not missing else ("missing" if "candidate" in missing else "blocked")
    return _sanitize(
        {
            "candidate": candidate.get("candidate"),
            "candidate_id": candidate.get("candidate_id"),
            "timeframe": candidate.get("timeframe"),
            "exists_in_registry": bool(registry_candidate),
            "paper_only": bool(safety_defaults.get("paper_only", True)),
            "live_authorized": bool(safety_defaults.get("live_authorized", False)),
            "promotion_allowed": bool(safety_defaults.get("promotion_allowed", False)),
            "validation_status": status,
            "missing_fields": missing,
            "why": "Candidate is registry-backed and paper-only." if not missing else f"Candidate registry validation missing: {', '.join(missing)}.",
        }
    )


def validate_betrayal_source_row_against_registry(
    row: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    source = str(row.get("_source") or row.get("source") or row.get("evidence_source") or "unknown")
    candidate = str(row.get("candidate") or "")
    registry_candidate = _registry_candidate_for(row, registry_manifest=registry_manifest)
    timeframes = {str(item) for item in registry_manifest.get("timeframes") or []} if isinstance(registry_manifest, Mapping) else set()
    entry_modes = _entry_mode_map(registry_manifest)
    required = _required_source_fields(registry_manifest)
    missing = [field for field in required if _missing(row.get(field))]
    entry_mode = str(row.get("entry_mode") or "")
    if not registry_candidate and "candidate" not in missing:
        missing.append("candidate")
    if (not row.get("timeframe") or str(row.get("timeframe")) not in timeframes) and "timeframe" not in missing:
        missing.append("timeframe")
    if entry_mode not in entry_modes and "entry_mode" not in missing:
        missing.append("entry_mode")
    elif entry_modes.get(entry_mode, {}).get("blocked_placeholder") and "entry_mode_blocked_placeholder" not in missing:
        missing.append("entry_mode_blocked_placeholder")
    if row.get("paper_only") is not True and "paper_only_true" not in missing:
        missing.append("paper_only_true")
    if row.get("live_authorized") is not False and "live_authorized_false" not in missing:
        missing.append("live_authorized_false")
    if row.get("promotion_allowed") is not False and "promotion_allowed_false" not in missing:
        missing.append("promotion_allowed_false")
    if _normal_direction(row.get("emitted_direction")) != _normal_direction(row.get("inverse_direction")):
        missing.append("emitted_direction_equals_inverse_direction")
    if _normal_direction(row.get("original_direction")) not in {"long", "short"}:
        missing.append("original_direction")
    if _normal_direction(row.get("inverse_direction")) not in {"long", "short"}:
        missing.append("inverse_direction")
    schema_complete = not missing
    return _sanitize(
        {
            "candidate": candidate or None,
            "source": source,
            "row_status": "registry_valid" if schema_complete else "blocked_missing_fields",
            "schema_complete": schema_complete,
            "missing_required_fields": _dedupe(missing),
            "blocked_from_resolver": not schema_complete,
            "paper_only": row.get("paper_only") is True,
            "live_authorized": bool(row.get("live_authorized", False)),
            "why": "Registry-backed source row satisfies betrayal_source_emitter_v2." if schema_complete else "Missing registry-required betrayal_source_emitter_v2 fields.",
        }
    )


def build_registry_backed_missing_field_report(source_row_registry_validation: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "missing_entry_mode_rows": sum(1 for row in source_row_registry_validation if "entry_mode" in (row.get("missing_required_fields") or [])),
        "missing_source_identity_rows": sum(1 for row in source_row_registry_validation if "source_identity" in (row.get("missing_required_fields") or [])),
        "missing_direction_rows": sum(
            1
            for row in source_row_registry_validation
            if any(field in (row.get("missing_required_fields") or []) for field in ("original_direction", "inverse_direction", "emitted_direction"))
        ),
        "blocked_placeholder_entry_mode_rows": sum(
            1 for row in source_row_registry_validation if "entry_mode_blocked_placeholder" in (row.get("missing_required_fields") or [])
        ),
        "resolver_ready_rows": sum(1 for row in source_row_registry_validation if row.get("schema_complete")),
    }


def build_registry_wiring_gap_report(
    *,
    registry_found: bool,
    registry_validation: Mapping[str, Any],
    candidate_validation: Sequence[Mapping[str, Any]],
    row_validation: Sequence[Mapping[str, Any]],
    missing_field_report: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "registry_missing": not registry_found,
        "registry_valid": bool(registry_validation.get("valid")),
        "betrayal_source_identity_blocked": bool(missing_field_report.get("missing_source_identity_rows")),
        "entry_mode_blocked": bool(
            missing_field_report.get("missing_entry_mode_rows") or missing_field_report.get("blocked_placeholder_entry_mode_rows")
        ),
        "candidate_registry_gaps": sum(1 for row in candidate_validation if row.get("validation_status") != "valid"),
        "source_rows_reviewed": len(row_validation),
        "resolver_ready_rows": int(missing_field_report.get("resolver_ready_rows") or 0),
        "hard_live_blockers": _hard_live_blockers(),
    }


def build_registry_wiring_recommendations(*, gap_report: Mapping[str, Any]) -> list[dict[str, str]]:
    recommendations = []
    if gap_report.get("registry_missing") or not gap_report.get("registry_valid"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RECORD_R218_REGISTRY",
                "future_phase": "R218",
                "why": "Betrayal registry wiring cannot proceed as ready without a valid R218 registry manifest.",
            }
        )
    if gap_report.get("entry_mode_blocked"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "WIRE_R217_TO_REGISTRY",
                "future_phase": "R221",
                "why": "Betrayal aggregate rows still need registry-backed entry_mode values before resolver-ready source rows.",
            }
        )
    if gap_report.get("betrayal_source_identity_blocked"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "COLLECT_SOURCE_IDENTITY",
                "future_phase": "R221",
                "why": "Betrayal rows without source_identity remain paper context only and blocked from resolver-ready status.",
            }
        )
    recommendations.append(
        {
            "priority": "MEDIUM",
            "recommended_action": "WIRE_R216_TO_REGISTRY",
            "future_phase": "R221",
            "why": "Future betrayal source emitter rows should consume R218 betrayal_source_emitter_v2 required fields directly.",
        }
    )
    recommendations.append(
        {
            "priority": "LOW",
            "recommended_action": "KEEP_PAPER_ONLY",
            "future_phase": "R219",
            "why": "Registry wiring is audit-only and does not promote betrayal, change lane modes, or authorize live execution.",
        }
    )
    return recommendations


def classify_registry_wiring_betrayal_status(
    *,
    gap_report: Mapping[str, Any],
    row_validation: Sequence[Mapping[str, Any]],
) -> str:
    if gap_report.get("registry_missing") or not gap_report.get("registry_valid"):
        return BETRAYAL_SOURCE_FAMILY_REGISTRY_GAPS_REMAIN
    if gap_report.get("betrayal_source_identity_blocked"):
        return BETRAYAL_SOURCE_FAMILY_SOURCE_IDENTITY_BLOCKED
    if gap_report.get("entry_mode_blocked"):
        return BETRAYAL_SOURCE_FAMILY_ENTRY_MODE_BLOCKED
    if any(row.get("schema_complete") for row in row_validation):
        return BETRAYAL_SOURCE_FAMILY_REGISTRY_WIRED
    return BETRAYAL_SOURCE_FAMILY_NOT_LIVE_AUTHORIZED


def append_registry_wiring_betrayal_source_family_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = registry_wiring_betrayal_source_family_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "wiring_id": str(record.get("wiring_id") or f"r219_registry_wiring_betrayal_source_family_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_wiring_requested": bool(record.get("record_wiring_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "registry_backed_betrayal_candidate_view": dict(record.get("registry_backed_betrayal_candidate_view") or {}),
            "candidate_registry_validation": list(record.get("candidate_registry_validation") or []),
            "source_row_registry_validation": list(record.get("source_row_registry_validation") or []),
            "registry_backed_missing_field_report": dict(record.get("registry_backed_missing_field_report") or {}),
            "registry_wiring_gap_report": dict(record.get("registry_wiring_gap_report") or {}),
            "registry_wiring_recommendations": list(record.get("registry_wiring_recommendations") or []),
            "wiring_status": record.get("wiring_status"),
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


def load_registry_wiring_betrayal_source_family_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = registry_wiring_betrayal_source_family_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_registry_wiring_betrayal_source_family_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    gap = latest.get("registry_wiring_gap_report") if isinstance(latest.get("registry_wiring_gap_report"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "wiring_status_counts": dict(sorted(Counter(str(record.get("wiring_status") or "UNKNOWN") for record in records).items())),
        "last_wiring_id": latest.get("wiring_id") if isinstance(latest, Mapping) else None,
        "last_resolver_ready_rows": gap.get("resolver_ready_rows"),
        "safety": dict(SAFETY),
    }


def registry_wiring_betrayal_source_family_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_registry_wiring_betrayal_source_family_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _collect_source_rows(
    *,
    aggregate_decomposition: Mapping[str, Any],
    source_emitter_refresh: Mapping[str, Any],
    direction_split_resolver: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("decomposition_rows", "v2_source_rows_preview"):
        rows.extend(_tagged_rows(aggregate_decomposition.get(key), "aggregate_decomposition"))
    for key in ("source_candidate_rows", "direction_specific_source_preview"):
        rows.extend(_tagged_rows(source_emitter_refresh.get(key), "source_emitter_refresh"))
    rows.extend(_tagged_rows(direction_split_resolver.get("direction_split_resolution_rows"), "direction_split_resolver"))
    return rows


def _tagged_rows(value: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [_sanitize({**dict(row), "_source": source}) for row in value if isinstance(row, Mapping)]


def _registry_manifest(registry: Mapping[str, Any]) -> dict[str, Any]:
    manifest = registry.get("registry_manifest") if isinstance(registry.get("registry_manifest"), Mapping) else registry
    return dict(manifest) if isinstance(manifest, Mapping) else {}


def _registry_validation(registry: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not registry or not manifest:
        return {"valid": False, "missing_required_sections": ["registry_manifest"]}
    if isinstance(registry.get("registry_validation"), Mapping):
        return dict(registry["registry_validation"])
    return validate_registry_entry(manifest)


def _required_source_fields(registry_manifest: Mapping[str, Any]) -> list[str]:
    requirements = registry_manifest.get("source_identity_requirements") if isinstance(registry_manifest, Mapping) else {}
    fields = requirements.get("betrayal_source_emitter_v2") if isinstance(requirements, Mapping) else None
    return [str(field) for field in fields] if isinstance(fields, Sequence) and not isinstance(fields, str) else []


def _required_evidence(registry_manifest: Mapping[str, Any]) -> list[str]:
    requirements = registry_manifest.get("evidence_requirements_by_family") if isinstance(registry_manifest, Mapping) else {}
    fields = requirements.get("betrayal") if isinstance(requirements, Mapping) else None
    return [str(field) for field in fields] if isinstance(fields, Sequence) and not isinstance(fields, str) else []


def _betrayal_safety_defaults(registry_manifest: Mapping[str, Any]) -> dict[str, bool]:
    safety_manifest = registry_manifest.get("safety_manifest") if isinstance(registry_manifest, Mapping) else {}
    betrayal = safety_manifest.get("betrayal") if isinstance(safety_manifest, Mapping) else {}
    defaults = {
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
        "config_write_allowed": False,
        "order_allowed": False,
        "binance_network_allowed": False,
    }
    if isinstance(betrayal, Mapping):
        defaults.update({key: bool(betrayal.get(key, value)) for key, value in defaults.items()})
    return defaults


def _registry_candidate_for(row: Mapping[str, Any], *, registry_manifest: Mapping[str, Any]) -> dict[str, Any]:
    candidates = registry_manifest.get("betrayal_candidates") if isinstance(registry_manifest, Mapping) else {}
    if not isinstance(candidates, Mapping):
        return {}
    candidate_id = str(row.get("candidate_id") or "")
    candidate = str(row.get("candidate") or row.get("label") or "")
    timeframe = str(row.get("timeframe") or "")
    normalized_id = _candidate_id(candidate)
    for key, value in candidates.items():
        if not isinstance(value, Mapping):
            continue
        labels = {
            str(key),
            str(value.get("candidate_id") or ""),
            str(value.get("label") or ""),
            _candidate_id(str(value.get("label") or "")),
            _candidate_base(str(value.get("label") or "")),
            _candidate_base(str(value.get("candidate_id") or "")),
        }
        if candidate_id in labels or candidate in labels or normalized_id in labels:
            return dict(value)
        if timeframe and timeframe == str(value.get("timeframe") or "") and _candidate_base(candidate) in _candidate_base(str(value.get("label") or "")):
            return dict(value)
    return {}


def _entry_mode_map(registry_manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = registry_manifest.get("entry_modes") if isinstance(registry_manifest, Mapping) else []
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        return {}
    return {str(row.get("entry_mode")): dict(row) for row in rows if isinstance(row, Mapping) and row.get("entry_mode")}


def _top_level_status(*, record_wiring: bool, confirmation_valid: bool, registry_found: bool, registry_valid: bool) -> str:
    if record_wiring and not confirmation_valid:
        return REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_REJECTED
    if not registry_found or not registry_valid:
        return REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_BLOCKED
    if record_wiring and confirmation_valid:
        return REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_RECORDED
    return REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_READY


def _recommended_next_operator_move(wiring_status: str) -> str:
    if wiring_status == BETRAYAL_SOURCE_FAMILY_REGISTRY_WIRED:
        return "RUN_R221_BETRAYAL_REGISTRY_CONSUMER_REFACTOR"
    if wiring_status in {BETRAYAL_SOURCE_FAMILY_SOURCE_IDENTITY_BLOCKED, BETRAYAL_SOURCE_FAMILY_ENTRY_MODE_BLOCKED}:
        return "RUN_R221_BETRAYAL_REGISTRY_CONSUMER_REFACTOR"
    if wiring_status == BETRAYAL_SOURCE_FAMILY_REGISTRY_GAPS_REMAIN:
        return "RUN_R220_REGISTRY_WIRING_FOR_PATTERN_ANCHOR_FAMILIES"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(wiring_status: str, gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("registry_missing"):
        return "Record or repair R218 strategy evidence registry before wiring betrayal consumers."
    if wiring_status in {BETRAYAL_SOURCE_FAMILY_SOURCE_IDENTITY_BLOCKED, BETRAYAL_SOURCE_FAMILY_ENTRY_MODE_BLOCKED}:
        return "Refactor betrayal emitter/decomposition/event tracker consumers to read registry candidates and required fields directly in R221."
    return "Keep betrayal paper-only and use registry wiring output to guide R220/R221 follow-up work."


def _hard_live_blockers() -> list[str]:
    return [
        "registry_inclusion_is_not_live_authorization",
        "betrayal_not_live_authorized",
        "betrayal_not_promoted",
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


def _empty_candidate_view() -> dict[str, Any]:
    return {"candidates": [], "required_source_fields": [], "required_evidence": [], "safety_defaults": {}}


def _latest_record(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    records = read_recent_ndjson_records(path, limit=1, max_bytes=16_777_216)
    return _sanitize(records[0]) if records else {}


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                rows.append(_sanitize(dict(value)))
    return rows


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _normal_direction(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"long", "bull", "bullish", "buy"}:
        return "long"
    if text in {"short", "bear", "bearish", "sell"}:
        return "short"
    return None


def _candidate_id(candidate: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", candidate.lower()).strip("_")


def _candidate_base(candidate: str) -> str:
    return _candidate_id(candidate).replace("_if_available", "")


def _dedupe(values: Sequence[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, set):
        return sorted(_sanitize(item) for item in value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
