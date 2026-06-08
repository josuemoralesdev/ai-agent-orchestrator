"""R225 betrayal entry mode evidence wiring.

Paper-only evidence wiring for betrayal entry_mode propagation. This module
reads local ledgers, validates entry_mode evidence against the R218 registry,
and can append only its own audit record after exact confirmation.
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
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.strategy_evidence_registry import validate_registry_entry

BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_READY = "BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_READY"
BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_REJECTED = "BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_REJECTED"
BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_RECORDED = "BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_RECORDED"
BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_BLOCKED = "BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_BLOCKED"
BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_ERROR = "BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_ERROR"

ENTRY_MODE_EVIDENCE_WIRING_READY = "ENTRY_MODE_EVIDENCE_WIRING_READY"
ENTRY_MODE_EVIDENCE_PARTIAL = "ENTRY_MODE_EVIDENCE_PARTIAL"
ENTRY_MODE_EVIDENCE_STILL_BLOCKED = "ENTRY_MODE_EVIDENCE_STILL_BLOCKED"
ENTRY_MODE_PROPAGATION_CONTRACT_READY = "ENTRY_MODE_PROPAGATION_CONTRACT_READY"
ENTRY_MODE_NOT_LIVE_AUTHORIZED = "ENTRY_MODE_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING"
LEDGER_FILENAME = "betrayal_entry_mode_evidence_wiring.ndjson"
DEFAULT_SYMBOL = "BTCUSDT"
CONFIRM_BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL ENTRY MODE EVIDENCE WIRING RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "logs/hammer_radar_forward/betrayal_source_identity_evidence_collector.ndjson",
    "logs/hammer_radar_forward/betrayal_source_identity_normalizer.ndjson",
    "logs/hammer_radar_forward/strategy_evidence_registry.ndjson",
    "logs/hammer_radar_forward/registry_wiring_betrayal_source_family.ndjson",
    "logs/hammer_radar_forward/betrayal_aggregate_decomposition.ndjson",
    "logs/hammer_radar_forward/betrayal_source_emitter_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_direction_split_resolver.ndjson",
    "logs/hammer_radar_forward/betrayal_event_tracker.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_heartbeats.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_entry_mode_evidence_wiring(
    *,
    log_dir: str | Path | None = None,
    record_wiring: bool = False,
    confirm_betrayal_entry_mode_evidence_wiring: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_betrayal_entry_mode_evidence_wiring == CONFIRM_BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_RECORDING_PHRASE
    try:
        collector = load_latest_betrayal_source_identity_evidence_collector(log_dir=resolved_log_dir)
        normalizer = load_latest_betrayal_source_identity_normalizer(log_dir=resolved_log_dir)
        registry = load_latest_strategy_evidence_registry(log_dir=resolved_log_dir)
        registry_wiring = load_latest_registry_wiring_betrayal_source_family(log_dir=resolved_log_dir)
        aggregate = load_latest_betrayal_aggregate_decomposition(log_dir=resolved_log_dir)
        source_refresh = load_latest_betrayal_source_emitter_refresh(log_dir=resolved_log_dir)
        direction_split = load_latest_betrayal_direction_split_resolver(log_dir=resolved_log_dir)
        event_tracker = load_latest_betrayal_event_tracker(log_dir=resolved_log_dir)
        full_spectrum = load_full_spectrum_capture_records(log_dir=resolved_log_dir)
        manifest = _registry_manifest(registry)
        registry_validation = _registry_validation(registry, manifest)
        rows = build_entry_mode_evidence_rows(
            source_identity_evidence_collector=collector,
            source_identity_normalizer=normalizer,
            strategy_evidence_registry=registry,
            registry_wiring_betrayal_source_family=registry_wiring,
            betrayal_aggregate_decomposition=aggregate,
            betrayal_source_emitter_refresh=source_refresh,
            betrayal_direction_split_resolver=direction_split,
            betrayal_event_tracker=event_tracker,
            full_spectrum_capture_records=full_spectrum,
        )
        summary = _entry_mode_summary(rows)
        gap_report = build_entry_mode_gap_report(rows, source_identity_evidence_collector=collector)
        contract = build_entry_mode_propagation_contract()
        recommendations = build_entry_mode_wiring_recommendations(gap_report=gap_report, summary=summary)
        entry_mode_status = classify_betrayal_entry_mode_evidence_status(rows=rows, gap_report=gap_report)
        payload = {
            "status": _top_level_status(
                record_wiring=record_wiring,
                confirmation_valid=confirmation_valid,
                registry_valid=bool(registry_validation.get("valid")),
            ),
            "generated_at": generated_at.isoformat(),
            "wiring_recorded": False,
            "wiring_id": None,
            "record_wiring_requested": bool(record_wiring),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "family": "betrayal",
                "registry_backed": True,
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "source_identity_evidence_collector_found": bool(collector),
                "source_identity_normalizer_found": bool(normalizer),
                "registry_found": bool(registry),
                "registry_valid": bool(registry_validation.get("valid")),
                "full_spectrum_records_found": bool(full_spectrum),
                "aggregate_decomposition_found": bool(aggregate),
                "source_emitter_refresh_found": bool(source_refresh),
                "registry_wiring_found": bool(registry_wiring),
                "direction_split_resolver_found": bool(direction_split),
                "event_tracker_found": bool(event_tracker),
            },
            "entry_mode_evidence_rows": rows,
            "entry_mode_summary": summary,
            "entry_mode_propagation_contract": contract,
            "entry_mode_gap_report": gap_report,
            "entry_mode_wiring_recommendations": recommendations,
            "entry_mode_status": entry_mode_status,
            "recommended_next_operator_move": _recommended_next_operator_move(entry_mode_status, summary),
            "recommended_next_engineering_move": _recommended_next_engineering_move(entry_mode_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_wiring and confirmation_valid and registry_validation.get("valid"):
            record = append_betrayal_entry_mode_evidence_wiring_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_RECORDED
            payload["wiring_recorded"] = True
            payload["wiring_id"] = record["wiring_id"]
            payload["ledger_path"] = str(betrayal_entry_mode_evidence_wiring_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_ERROR,
                "generated_at": generated_at.isoformat(),
                "wiring_recorded": False,
                "wiring_id": None,
                "record_wiring_requested": bool(record_wiring),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {"family": "betrayal", "registry_backed": True, "paper_only": True, "live_authorized": False},
                "input_summary": {},
                "entry_mode_evidence_rows": [],
                "entry_mode_summary": _entry_mode_summary([]),
                "entry_mode_propagation_contract": build_entry_mode_propagation_contract(),
                "entry_mode_gap_report": build_entry_mode_gap_report([]),
                "entry_mode_wiring_recommendations": [],
                "entry_mode_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R225 entry_mode wiring error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_source_identity_evidence_collector(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_source_identity_evidence_collector.ndjson")


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


def load_full_spectrum_capture_records(*, log_dir: str | Path | None = None, limit: int = 200) -> list[dict[str, Any]]:
    resolved = get_log_dir(log_dir, use_env=True)
    rows: list[dict[str, Any]] = []
    for filename in ("full_spectrum_harvester_expansion.ndjson", "full_spectrum_harvester_heartbeats.ndjson"):
        path = resolved / filename
        records = read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000) if path.exists() else []
        for record in records:
            if isinstance(record, Mapping):
                rows.extend(_extract_capture_rows(record))
    return _dedupe_raw_records(rows)


def extract_entry_mode_from_lane_key(lane_key: Any) -> str | None:
    parts = [part.strip() for part in str(lane_key or "").split("|")]
    if len(parts) < 4 or not parts[3]:
        return None
    return parts[3].lower()


def extract_entry_mode_from_signal_id(signal_id: Any, *, registry_manifest: Mapping[str, Any] | None = None) -> str | None:
    text = _string_or_none(signal_id)
    if not text:
        return None
    allowed = _allowed_entry_modes(registry_manifest or {}, include_placeholders=False)
    for part in [part.strip().lower() for part in text.split("|") if part.strip()]:
        if part in allowed:
            return part
    return None


def validate_entry_mode_against_registry(entry_mode: Any, registry_manifest: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _string_or_none(entry_mode)
    if not candidate:
        return {"entry_mode": None, "valid": False, "registry_entry_mode_found": False, "blocked_placeholder": False}
    candidate = candidate.lower()
    entry_modes = _entry_mode_manifest_by_name(registry_manifest)
    manifest_row = entry_modes.get(candidate)
    return {
        "entry_mode": candidate,
        "valid": bool(manifest_row and not manifest_row.get("blocked_placeholder") and candidate not in {"unknown", "entry_unknown"}),
        "registry_entry_mode_found": bool(manifest_row),
        "blocked_placeholder": bool(manifest_row.get("blocked_placeholder")) if manifest_row else False,
    }


def build_entry_mode_evidence_rows(
    *,
    source_identity_evidence_collector: Mapping[str, Any],
    source_identity_normalizer: Mapping[str, Any],
    strategy_evidence_registry: Mapping[str, Any],
    registry_wiring_betrayal_source_family: Mapping[str, Any],
    betrayal_aggregate_decomposition: Mapping[str, Any],
    betrayal_source_emitter_refresh: Mapping[str, Any],
    betrayal_direction_split_resolver: Mapping[str, Any],
    betrayal_event_tracker: Mapping[str, Any],
    full_spectrum_capture_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    del registry_wiring_betrayal_source_family
    manifest = _registry_manifest(strategy_evidence_registry)
    raw_rows = _collect_source_rows(
        collector=source_identity_evidence_collector,
        normalizer=source_identity_normalizer,
        aggregate=betrayal_aggregate_decomposition,
        source_refresh=betrayal_source_emitter_refresh,
        direction_split=betrayal_direction_split_resolver,
        event_tracker=betrayal_event_tracker,
        full_spectrum=full_spectrum_capture_records,
    )
    return _dedupe_evidence_rows([_build_entry_mode_evidence_row(row, registry_manifest=manifest) for row in raw_rows])


def build_entry_mode_propagation_contract() -> dict[str, Any]:
    return {
        "contract_name": "betrayal_entry_mode_source_contract_v1",
        "required_for_future_emitters": [
            "entry_mode",
            "lane_key",
            "source_signal_id",
            "source_signal_timestamp",
            "source_family",
        ],
        "source_surfaces": [
            "full_spectrum_harvest_capture_records",
            "betrayal_source_emitter_v2_rows",
            "betrayal_event_tracker_rows",
            "betrayal_aggregate_decomposition_rows",
            "direction_split_rows",
        ],
        "entry_mode_must_exist_in_registry": True,
        "common_default_inference_allowed": False,
        "candidate_label_inference_allowed": False,
        "timeframe_only_inference_allowed": False,
        "paper_only": True,
        "live_authorized": False,
    }


def build_entry_mode_gap_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_identity_evidence_collector: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    collector_summary = (
        source_identity_evidence_collector.get("source_identity_evidence_summary")
        if isinstance(source_identity_evidence_collector, Mapping)
        else {}
    )
    if not isinstance(collector_summary, Mapping):
        collector_summary = {}
    return {
        "missing_entry_mode_rows": sum(1 for row in rows if not row.get("entry_mode")),
        "invalid_entry_mode_rows": sum(1 for row in rows if row.get("entry_mode") and not row.get("entry_mode_valid")),
        "registry_missing_rows": sum(1 for row in rows if row.get("entry_mode") and not row.get("registry_entry_mode_found")),
        "collector_resolver_ready_preview_rows": int(collector_summary.get("resolver_ready_preview_rows") or 0),
        "hard_live_blockers": _hard_live_blockers(),
    }


def build_entry_mode_wiring_recommendations(
    *,
    gap_report: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    if gap_report.get("missing_entry_mode_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "WIRE_FULL_SPECTRUM_ENTRY_MODE",
                "future_phase": "R226",
                "why": "Full-spectrum capture rows commonly carry lane_key evidence; future betrayal source rows must persist entry_mode explicitly.",
            }
        )
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "WIRE_BETRAYAL_EMITTER_ENTRY_MODE",
                "future_phase": "R226",
                "why": "Betrayal emitter, event tracker, aggregate decomposition, and direction split rows need registry-backed entry_mode propagation.",
            }
        )
    if summary.get("can_feed_normalizer_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RUN_R226_RENORMALIZE_WITH_ENTRY_MODE",
                "future_phase": "R226",
                "why": "Registry-valid entry_mode evidence exists, but R225 does not append normalized resolver-ready source rows.",
            }
        )
    if gap_report.get("collector_resolver_ready_preview_rows"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "CHECK_R224_APPEND_PRECONDITIONS",
                "future_phase": "R224",
                "why": "Collector reported resolver-ready previews; operator must still validate append preconditions separately.",
            }
        )
    recommendations.append(
        {
            "priority": "LOW",
            "recommended_action": "KEEP_CONTEXT_ONLY",
            "future_phase": "R225",
            "why": "R225 is paper-only wiring evidence and cannot promote betrayal, write configs, or authorize live execution.",
        }
    )
    return recommendations


def classify_betrayal_entry_mode_evidence_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if gap_report.get("missing_entry_mode_rows") or gap_report.get("invalid_entry_mode_rows") or gap_report.get("registry_missing_rows"):
        return ENTRY_MODE_EVIDENCE_STILL_BLOCKED
    if any(row.get("can_feed_source_identity_normalizer") for row in rows):
        return ENTRY_MODE_EVIDENCE_WIRING_READY
    return ENTRY_MODE_PROPAGATION_CONTRACT_READY


def append_betrayal_entry_mode_evidence_wiring_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_entry_mode_evidence_wiring_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "wiring_id": str(record.get("wiring_id") or f"r225_betrayal_entry_mode_evidence_wiring_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_wiring_requested": bool(record.get("record_wiring_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "entry_mode_evidence_rows": list(record.get("entry_mode_evidence_rows") or []),
            "entry_mode_summary": dict(record.get("entry_mode_summary") or {}),
            "entry_mode_propagation_contract": dict(record.get("entry_mode_propagation_contract") or {}),
            "entry_mode_gap_report": dict(record.get("entry_mode_gap_report") or {}),
            "entry_mode_wiring_recommendations": list(record.get("entry_mode_wiring_recommendations") or []),
            "entry_mode_status": record.get("entry_mode_status"),
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


def load_betrayal_entry_mode_evidence_wiring_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_entry_mode_evidence_wiring_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def summarize_betrayal_entry_mode_evidence_wiring_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    summary = latest.get("entry_mode_summary") if isinstance(latest.get("entry_mode_summary"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "entry_mode_status_counts": dict(sorted(Counter(str(record.get("entry_mode_status") or "UNKNOWN") for record in records).items())),
        "last_wiring_id": latest.get("wiring_id") if isinstance(latest, Mapping) else None,
        "last_rows_reviewed": summary.get("rows_reviewed") if isinstance(summary, Mapping) else None,
        "last_entry_mode_valid_rows": summary.get("entry_mode_valid_rows") if isinstance(summary, Mapping) else None,
        "safety": dict(SAFETY),
    }


def betrayal_entry_mode_evidence_wiring_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_entry_mode_evidence_wiring_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _build_entry_mode_evidence_row(row: Mapping[str, Any], *, registry_manifest: Mapping[str, Any]) -> dict[str, Any]:
    entry_mode, entry_mode_source = _entry_mode_with_source(row, registry_manifest=registry_manifest)
    validation = validate_entry_mode_against_registry(entry_mode, registry_manifest)
    valid = bool(validation["valid"])
    return _sanitize(
        {
            "candidate": _candidate_label(row),
            "source": str(row.get("_source") or row.get("source") or "unknown"),
            "symbol": _string_or_none(row.get("symbol")) or DEFAULT_SYMBOL,
            "timeframe": _string_or_none(row.get("timeframe")) or _candidate_timeframe(row.get("candidate")),
            "entry_mode": validation["entry_mode"],
            "entry_mode_source": entry_mode_source,
            "entry_mode_valid": valid,
            "registry_entry_mode_found": bool(validation["registry_entry_mode_found"]),
            "lane_key": _string_or_none(row.get("lane_key")),
            "source_signal_id": _first_string(row, "source_signal_id", "signal_id", "emitted_signal_id"),
            "source_capture_id": _first_string(row, "source_capture_id", "capture_id", "candidate_id"),
            "timestamp": _timestamp(row),
            "can_feed_source_identity_normalizer": valid,
            "can_feed_resolver_ready_preview": False,
            "paper_only": True,
            "live_authorized": False,
            "why": _entry_mode_why(entry_mode=entry_mode, entry_mode_source=entry_mode_source, validation=validation),
        }
    )


def _entry_mode_with_source(row: Mapping[str, Any], *, registry_manifest: Mapping[str, Any]) -> tuple[str | None, str]:
    explicit = _string_or_none(row.get("entry_mode") or row.get("source_entry_mode"))
    if explicit:
        return explicit.lower(), "explicit"
    lane_mode = extract_entry_mode_from_lane_key(row.get("lane_key"))
    if lane_mode:
        return lane_mode, "lane_key"
    source_signal_mode = extract_entry_mode_from_signal_id(_first_string(row, "source_signal_id", "signal_id", "emitted_signal_id"), registry_manifest=registry_manifest)
    if source_signal_mode:
        return source_signal_mode, "source_signal_id"
    source_capture_mode = extract_entry_mode_from_signal_id(_first_string(row, "source_capture_id", "capture_id", "candidate_id"), registry_manifest=registry_manifest)
    if source_capture_mode:
        return source_capture_mode, "source_capture_id"
    if _registry_contract_evidence(row):
        mode = _string_or_none(row.get("registry_contract_entry_mode"))
        return (mode.lower() if mode else None), "registry_contract"
    return None, "insufficient"


def _entry_mode_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "rows_reviewed": len(rows),
        "entry_mode_valid_rows": sum(1 for row in rows if row.get("entry_mode_valid")),
        "entry_mode_explicit_rows": sum(1 for row in rows if row.get("entry_mode_source") == "explicit"),
        "entry_mode_from_lane_key_rows": sum(1 for row in rows if row.get("entry_mode_source") == "lane_key"),
        "entry_mode_from_signal_id_rows": sum(1 for row in rows if row.get("entry_mode_source") in {"source_signal_id", "source_capture_id"}),
        "entry_mode_still_missing_rows": sum(1 for row in rows if not row.get("entry_mode")),
        "can_feed_normalizer_rows": sum(1 for row in rows if row.get("can_feed_source_identity_normalizer")),
    }


def _collect_source_rows(
    *,
    collector: Mapping[str, Any],
    normalizer: Mapping[str, Any],
    aggregate: Mapping[str, Any],
    source_refresh: Mapping[str, Any],
    direction_split: Mapping[str, Any],
    event_tracker: Mapping[str, Any],
    full_spectrum: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_tag_rows(collector.get("source_identity_evidence_rows"), "collector"))
    rows.extend(_tag_rows(normalizer.get("normalized_source_rows_preview"), "normalizer"))
    rows.extend(_tag_rows(aggregate.get("decomposition_rows"), "aggregate_decomposition"))
    rows.extend(_tag_rows(_first_list(source_refresh, "direction_specific_source_preview", "source_rows_preview", "emitter_rows"), "source_emitter_refresh"))
    rows.extend(_tag_rows(_first_list(direction_split, "direction_split_rows", "resolved_rows", "resolver_rows"), "direction_split_resolver"))
    rows.extend(_tag_rows(_first_list(event_tracker, "event_rows", "tracker_rows", "betrayal_events"), "event_tracker"))
    rows.extend(_tag_rows(full_spectrum, "full_spectrum_capture"))
    return _dedupe_raw_records(rows)


def _extract_capture_rows(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("captured_candidates", "capture_records", "captured_rows"):
        rows.extend(_tag_rows(record.get(key), "full_spectrum_capture"))
    capture_summary = record.get("capture_summary")
    if isinstance(capture_summary, Mapping):
        rows.extend(_tag_rows(capture_summary.get("captured_candidates"), "full_spectrum_capture"))
        examples = capture_summary.get("candidate_examples_by_lane")
        if isinstance(examples, Mapping):
            for lane_rows in examples.values():
                rows.extend(_tag_rows(lane_rows, "full_spectrum_capture"))
    for iteration in record.get("iteration_summaries") or []:
        if isinstance(iteration, Mapping):
            rows.extend(_extract_capture_rows(iteration))
    return rows


def _tag_rows(value: Any, source: str) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        values = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = list(value)
    else:
        values = []
    return [{**dict(row), "_source": source} for row in values if isinstance(row, Mapping)]


def _registry_manifest(registry: Mapping[str, Any]) -> dict[str, Any]:
    manifest = registry.get("registry_manifest") if isinstance(registry, Mapping) else {}
    return dict(manifest) if isinstance(manifest, Mapping) else {}


def _registry_validation(registry: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    existing = registry.get("registry_validation") if isinstance(registry, Mapping) else {}
    if isinstance(existing, Mapping) and existing:
        return dict(existing)
    return validate_registry_entry(manifest)


def _allowed_entry_modes(registry_manifest: Mapping[str, Any], *, include_placeholders: bool) -> set[str]:
    modes = set()
    for item in registry_manifest.get("entry_modes") or []:
        if not isinstance(item, Mapping):
            continue
        mode = _string_or_none(item.get("entry_mode"))
        if mode and (include_placeholders or not item.get("blocked_placeholder")):
            modes.add(mode.lower())
    return modes


def _entry_mode_manifest_by_name(registry_manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in registry_manifest.get("entry_modes") or []:
        if isinstance(item, Mapping) and _string_or_none(item.get("entry_mode")):
            result[str(item["entry_mode"]).lower()] = dict(item)
    return result


def _top_level_status(*, record_wiring: bool, confirmation_valid: bool, registry_valid: bool) -> str:
    if record_wiring and not confirmation_valid:
        return BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_REJECTED
    if not registry_valid:
        return BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_BLOCKED
    return BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_READY


def _recommended_next_operator_move(entry_mode_status: str, summary: Mapping[str, Any]) -> str:
    if entry_mode_status == ENTRY_MODE_EVIDENCE_WIRING_READY and summary.get("can_feed_normalizer_rows"):
        return "RUN_R226_BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(entry_mode_status: str, gap_report: Mapping[str, Any]) -> str:
    if entry_mode_status == ENTRY_MODE_EVIDENCE_STILL_BLOCKED:
        return "Wire registry-backed entry_mode propagation into betrayal capture/emitter/event/decomposition/direction surfaces before R226."
    if gap_report.get("collector_resolver_ready_preview_rows"):
        return "Review R224 append preconditions separately; R225 does not append normalized rows."
    return "Run R226 paper-only renormalization using the R225 entry_mode contract."


def _entry_mode_why(*, entry_mode: str | None, entry_mode_source: str, validation: Mapping[str, Any]) -> str:
    if not entry_mode:
        return "Entry mode is missing; common ladder mode, candidate label, and timeframe-only inference were not used."
    if validation.get("valid"):
        return f"Entry mode is registry-backed from {entry_mode_source}; R225 still does not mark resolver-ready rows."
    if validation.get("blocked_placeholder"):
        return "Entry mode is a blocked placeholder and cannot feed normalization."
    if not validation.get("registry_entry_mode_found"):
        return "Entry mode is not present in the registry and remains blocked."
    return "Entry mode needs manual review before any future normalization."


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
        "entry_mode_wiring_is_paper_only",
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


def _first_string(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _string_or_none(row.get(key))
        if value:
            return value
    return None


def _first_list(row: Mapping[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = row.get(key)
        if isinstance(value, list):
            return value
    return []


def _candidate_label(row: Mapping[str, Any]) -> str | None:
    return _string_or_none(row.get("candidate") or row.get("candidate_label") or row.get("lane_key") or row.get("source_signal_id"))


def _candidate_timeframe(candidate: Any) -> str | None:
    text = _string_or_none(candidate)
    if not text:
        return None
    return text.split()[0] if text.split() else None


def _timestamp(row: Mapping[str, Any]) -> str | None:
    return _first_string(row, "timestamp", "source_signal_timestamp", "signal_timestamp", "emitted_at", "generated_at")


def _registry_contract_evidence(row: Mapping[str, Any]) -> bool:
    return bool(row.get("registry_contract_entry_mode") or row.get("entry_mode_contract_valid"))


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


def _dedupe_evidence_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = (
            row.get("source"),
            row.get("candidate"),
            row.get("symbol"),
            row.get("timeframe"),
            row.get("lane_key"),
            row.get("source_signal_id"),
            row.get("source_capture_id"),
            row.get("timestamp"),
            row.get("entry_mode"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(row))
    return result


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
