"""R230 betrayal upstream emitter entry-mode contract.

Future-row-only helper and report surface for betrayal source emitters. This
module does not rewrite historical ledgers, append normalized rows, mutate
configs/env, call Binance/network, create order payloads, promote betrayal, or
authorize live execution.
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
from src.app.hammer_radar.operator.betrayal_event_tracker import (
    build_betrayal_event_identity as _build_tracker_event_identity,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.strategy_evidence_registry import validate_registry_entry

BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_READY = "BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_READY"
BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_REJECTED = "BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_REJECTED"
BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_RECORDED = "BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_RECORDED"
BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_BLOCKED = "BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_BLOCKED"
BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_ERROR = "BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_ERROR"

UPSTREAM_EMITTER_CONTRACT_READY_FOR_FUTURE_ROWS = "UPSTREAM_EMITTER_CONTRACT_READY_FOR_FUTURE_ROWS"
UPSTREAM_EMITTER_CONTRACT_PARTIALLY_READY = "UPSTREAM_EMITTER_CONTRACT_PARTIALLY_READY"
UPSTREAM_EMITTER_CONTRACT_GAPS_REMAIN = "UPSTREAM_EMITTER_CONTRACT_GAPS_REMAIN"
UPSTREAM_EMITTER_CONTRACT_NOT_LIVE_AUTHORIZED = "UPSTREAM_EMITTER_CONTRACT_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT"
LEDGER_FILENAME = "betrayal_upstream_emitter_entry_mode_contract.ndjson"
CONTRACT_NAME = "betrayal_upstream_emitter_entry_mode_contract_v1"
SCHEMA_VERSION = "betrayal_source_emitter_v2"
SOURCE_FAMILY = "betrayal"
OUTCOME_WINDOWS = [1, 3, 5, 10, 21, 34, 55]
CONFIRM_BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL UPSTREAM EMITTER ENTRY MODE CONTRACT RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

REQUIRED_FIELDS = [
    "schema_version",
    "source_family",
    "candidate",
    "symbol",
    "timeframe",
    "entry_mode",
    "original_direction",
    "inverse_direction",
    "emitted_direction",
    "source_identity",
    "source_signal_id",
    "source_signal_timestamp",
    "emitted_signal_id",
    "lane_key",
    "betrayal_event_identity",
    "betrayal_event_identity_hash",
    "outcome_windows",
    "paper_only",
    "live_authorized",
    "promotion_allowed",
]

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
    "future_contract_only": True,
    "historical_rows_rewritten": False,
    "normalized_rows_appended": False,
}

SURFACE_FILES = {
    "betrayal_source_emitter_refresh": "src/app/hammer_radar/operator/betrayal_source_emitter_refresh.py",
    "betrayal_event_tracker": "src/app/hammer_radar/operator/betrayal_event_tracker.py",
    "betrayal_aggregate_decomposition": "src/app/hammer_radar/operator/betrayal_aggregate_decomposition.py",
    "betrayal_direction_split_resolver": "src/app/hammer_radar/operator/betrayal_direction_split_resolver.py",
    "full_spectrum_harvester_expansion": "src/app/hammer_radar/operator/full_spectrum_harvester_expansion.py",
}


def build_betrayal_upstream_emitter_entry_mode_contract(
    *,
    log_dir: str | Path | None = None,
    record_contract: bool = False,
    confirm_betrayal_upstream_emitter_entry_mode_contract: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_upstream_emitter_entry_mode_contract
        == CONFIRM_BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_RECORDING_PHRASE
    )
    try:
        source_propagation = load_latest_betrayal_entry_mode_source_propagation(log_dir=resolved_log_dir)
        registry = load_latest_strategy_evidence_registry(log_dir=resolved_log_dir)
        registry_manifest = _registry_manifest(registry)
        registry_validation = validate_registry_entry(registry_manifest) if registry_manifest else {"valid": False}
        surface_inventory = build_upstream_surface_inventory(repo_root=Path.cwd())
        readiness_report = build_future_emitter_contract_readiness_report(surface_inventory)
        compatibility_report = build_existing_row_compatibility_report(source_propagation)
        gap_report = build_upstream_contract_gap_report(
            source_propagation=source_propagation,
            readiness_report=readiness_report,
            compatibility_report=compatibility_report,
        )
        recommendations = build_upstream_contract_recommendations(
            gap_report=gap_report,
            readiness_report=readiness_report,
        )
        contract_status = classify_betrayal_upstream_contract_status(
            readiness_report=readiness_report,
            gap_report=gap_report,
        )
        payload = {
            "status": _top_level_status(
                record_contract=record_contract,
                confirmation_valid=confirmation_valid,
                registry_valid=bool(registry_validation.get("valid")),
            ),
            "generated_at": generated_at.isoformat(),
            "contract_recorded": False,
            "contract_id": None,
            "record_contract_requested": bool(record_contract),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "family": "betrayal",
                "future_rows_only": True,
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "source_propagation_found": bool(source_propagation),
                "registry_found": bool(registry),
                "registry_valid": bool(registry_validation.get("valid")),
            },
            "upstream_contract": _upstream_contract_manifest(),
            "upstream_surface_inventory": surface_inventory,
            "future_emitter_contract_readiness_report": readiness_report,
            "existing_row_compatibility_report": compatibility_report,
            "upstream_contract_gap_report": gap_report,
            "upstream_contract_recommendations": recommendations,
            "upstream_contract_status": contract_status,
            "recommended_next_operator_move": _recommended_next_operator_move(contract_status, readiness_report),
            "recommended_next_engineering_move": _recommended_next_engineering_move(contract_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
        }
        if record_contract and confirmation_valid and registry_validation.get("valid"):
            record = append_betrayal_upstream_contract_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_RECORDED
            payload["contract_recorded"] = True
            payload["contract_id"] = record["contract_id"]
            payload["ledger_path"] = str(betrayal_upstream_contract_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_ERROR,
                "generated_at": generated_at.isoformat(),
                "contract_recorded": False,
                "contract_id": None,
                "record_contract_requested": bool(record_contract),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {"family": "betrayal", "future_rows_only": True, "paper_only": True, "live_authorized": False},
                "input_summary": {"source_propagation_found": False, "registry_found": False, "registry_valid": False},
                "upstream_contract": _upstream_contract_manifest(),
                "upstream_surface_inventory": [],
                "future_emitter_contract_readiness_report": build_future_emitter_contract_readiness_report([]),
                "existing_row_compatibility_report": build_existing_row_compatibility_report({}),
                "upstream_contract_gap_report": build_upstream_contract_gap_report(
                    source_propagation={},
                    readiness_report=build_future_emitter_contract_readiness_report([]),
                    compatibility_report=build_existing_row_compatibility_report({}),
                ),
                "upstream_contract_recommendations": [],
                "upstream_contract_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R230 contract report error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
            }
        )


def load_latest_betrayal_entry_mode_source_propagation(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_entry_mode_source_propagation.ndjson")


def load_latest_strategy_evidence_registry(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "strategy_evidence_registry.ndjson")


def get_betrayal_upstream_required_fields() -> list[str]:
    return list(REQUIRED_FIELDS)


def get_registry_valid_entry_modes(registry_manifest: Mapping[str, Any]) -> set[str]:
    valid = set()
    for row in registry_manifest.get("entry_modes") or []:
        if not isinstance(row, Mapping):
            continue
        mode = _string_or_none(row.get("entry_mode"))
        if mode and not row.get("blocked_placeholder") and mode not in {"unknown", "entry_unknown"}:
            valid.add(mode)
    return valid


def validate_entry_mode_for_upstream_contract(
    entry_mode: Any,
    *,
    registry_manifest: Mapping[str, Any],
    inference_source: str = "explicit",
) -> dict[str, Any]:
    mode = _string_or_none(entry_mode)
    forbidden_inference = inference_source in {"common_default", "candidate_label", "timeframe_only"}
    valid_modes = get_registry_valid_entry_modes(registry_manifest)
    return {
        "entry_mode": mode,
        "valid": bool(mode and mode in valid_modes and not forbidden_inference),
        "registry_entry_mode_found": bool(mode and mode in valid_modes),
        "blocked_placeholder": mode in {"unknown", "entry_unknown"},
        "inference_source": inference_source,
        "common_default_inference_allowed": False,
        "candidate_label_inference_allowed": False,
        "timeframe_only_inference_allowed": False,
        "rejection_reason": _entry_mode_rejection_reason(
            mode=mode,
            valid_modes=valid_modes,
            forbidden_inference=forbidden_inference,
            inference_source=inference_source,
        ),
    }


def build_betrayal_lane_key(*, symbol: Any, timeframe: Any, emitted_direction: Any, entry_mode: Any) -> str | None:
    normalized_symbol = _string_or_none(symbol)
    normalized_timeframe = _string_or_none(timeframe)
    normalized_direction = _normal_direction(emitted_direction)
    normalized_entry_mode = _string_or_none(entry_mode)
    if not (normalized_symbol and normalized_timeframe and normalized_direction and normalized_entry_mode):
        return None
    return f"{normalized_symbol}|{normalized_timeframe}|{normalized_direction}|{normalized_entry_mode}"


def build_betrayal_emitted_signal_id(row: Mapping[str, Any]) -> str | None:
    source_identity = _string_or_none(row.get("source_identity") or row.get("source_signal_id"))
    source_signal_id = _string_or_none(row.get("source_signal_id"))
    timestamp = _string_or_none(row.get("source_signal_timestamp") or row.get("signal_timestamp") or row.get("timestamp"))
    emitted_direction = _normal_direction(row.get("emitted_direction"))
    entry_mode = _string_or_none(row.get("entry_mode"))
    if not (source_identity and source_signal_id and timestamp and emitted_direction and entry_mode):
        return None
    digest = hashlib.sha256(
        f"{source_identity}|{source_signal_id}|{timestamp}|{emitted_direction}|{entry_mode}".encode("utf-8")
    ).hexdigest()[:16]
    return f"betrayal_emitted|{source_identity}|{emitted_direction}|{entry_mode}|{digest}"


def build_betrayal_event_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    return _build_tracker_event_identity(
        symbol=_string_or_none(row.get("symbol")),
        timeframe=_string_or_none(row.get("timeframe")),
        candidate_label=_string_or_none(row.get("candidate")),
        original_direction=_normal_direction(row.get("original_direction")),
        inverse_direction=_normal_direction(row.get("inverse_direction")),
        entry_mode=_string_or_none(row.get("entry_mode")),
        source_signal_id=_string_or_none(row.get("source_signal_id")),
        signal_timestamp=_string_or_none(row.get("source_signal_timestamp")),
        event_timeframe=_string_or_none(row.get("timeframe")),
        outcome_window=OUTCOME_WINDOWS,
    )


def build_betrayal_upstream_contract_row(
    row: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
    inference_source: str = "explicit",
) -> dict[str, Any]:
    base = dict(row)
    entry_validation = validate_entry_mode_for_upstream_contract(
        base.get("entry_mode"),
        registry_manifest=registry_manifest,
        inference_source=inference_source,
    )
    original = _normal_direction(base.get("original_direction"))
    inverse = _normal_direction(base.get("inverse_direction"))
    emitted = _normal_direction(base.get("emitted_direction") or inverse)
    source_signal_timestamp = _string_or_none(
        base.get("source_signal_timestamp") or base.get("signal_timestamp") or base.get("timestamp")
    )
    normalized = {
        "schema_version": _string_or_none(base.get("schema_version")) or SCHEMA_VERSION,
        "source_family": SOURCE_FAMILY,
        "candidate": _string_or_none(base.get("candidate")),
        "symbol": _string_or_none(base.get("symbol")),
        "timeframe": _string_or_none(base.get("timeframe")),
        "entry_mode": entry_validation["entry_mode"] if entry_validation["valid"] else _string_or_none(base.get("entry_mode")),
        "original_direction": original,
        "inverse_direction": inverse,
        "emitted_direction": emitted,
        "source_identity": _string_or_none(base.get("source_identity") or base.get("source_signal_id")),
        "source_signal_id": _string_or_none(base.get("source_signal_id")),
        "source_signal_timestamp": source_signal_timestamp,
        "outcome_windows": list(base.get("outcome_windows") or OUTCOME_WINDOWS),
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }
    normalized["lane_key"] = build_betrayal_lane_key(
        symbol=normalized["symbol"],
        timeframe=normalized["timeframe"],
        emitted_direction=normalized["emitted_direction"],
        entry_mode=normalized["entry_mode"],
    )
    normalized["emitted_signal_id"] = build_betrayal_emitted_signal_id(normalized)
    identity = build_betrayal_event_identity(normalized)
    normalized["betrayal_event_identity"] = identity["event_identity"]
    normalized["betrayal_event_identity_hash"] = identity["event_identity_hash"]
    validation = validate_betrayal_upstream_contract_row(normalized, registry_manifest=registry_manifest)
    return _sanitize({**normalized, "entry_mode_validation": entry_validation, "contract_validation": validation})


def validate_betrayal_upstream_contract_row(
    row: Mapping[str, Any],
    *,
    registry_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if _missing_contract_field(row, field)]
    entry_validation = validate_entry_mode_for_upstream_contract(
        row.get("entry_mode"),
        registry_manifest=registry_manifest,
        inference_source=str(row.get("entry_mode_inference_source") or "explicit"),
    )
    if not entry_validation["valid"] and "entry_mode_registry_valid" not in missing:
        missing.append("entry_mode_registry_valid")
    if _normal_direction(row.get("emitted_direction")) != _normal_direction(row.get("inverse_direction")):
        missing.append("emitted_direction_equals_inverse_direction")
    expected_lane_key = build_betrayal_lane_key(
        symbol=row.get("symbol"),
        timeframe=row.get("timeframe"),
        emitted_direction=row.get("emitted_direction"),
        entry_mode=row.get("entry_mode"),
    )
    if row.get("lane_key") != expected_lane_key:
        missing.append("lane_key_from_symbol_timeframe_emitted_direction_entry_mode")
    if row.get("paper_only") is not True:
        missing.append("paper_only_true")
    if row.get("live_authorized") is not False:
        missing.append("live_authorized_false")
    if row.get("promotion_allowed") is not False:
        missing.append("promotion_allowed_false")
    missing = _dedupe(missing)
    return {
        "valid": not missing,
        "schema_complete": not missing,
        "missing_required_fields": missing,
        "entry_mode_validation": entry_validation,
        "future_contract_ready": not missing,
    }


def build_upstream_surface_inventory(*, repo_root: str | Path | None = None) -> list[dict[str, Any]]:
    root = Path(repo_root or Path.cwd())
    inventory = []
    for surface, rel_path in SURFACE_FILES.items():
        path = root / rel_path
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        uses_helper = "betrayal_upstream_emitter_entry_mode_contract" in text
        can_emit_entry_mode = "entry_mode" in text
        can_emit_lane_key = "lane_key" in text
        can_emit_source_signal_id = "source_signal_id" in text or "source_identity" in text
        can_emit_direction_fields = all(token in text for token in ("original_direction", "inverse_direction", "emitted_direction"))
        ready = bool(uses_helper and can_emit_entry_mode and can_emit_lane_key and can_emit_source_signal_id and can_emit_direction_fields)
        notes = []
        if uses_helper:
            notes.append("R230 registry-backed upstream contract helper is referenced by this surface.")
        else:
            notes.append("Surface still needs direct R230 helper adoption before future rows are guaranteed complete.")
        if surface == "full_spectrum_harvester_expansion":
            notes.append("Full-spectrum harvester is only a betrayal source when it seeds betrayal rows; no config writes are allowed.")
        inventory.append(
            {
                "surface": surface,
                "path": rel_path,
                "can_emit_entry_mode": can_emit_entry_mode,
                "can_emit_lane_key": can_emit_lane_key,
                "can_emit_source_signal_id": can_emit_source_signal_id,
                "can_emit_direction_fields": can_emit_direction_fields,
                "uses_registry_contract_helper": uses_helper,
                "future_contract_ready": ready,
                "notes": notes,
            }
        )
    return inventory


def build_future_emitter_contract_readiness_report(upstream_surface_inventory: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    inspected = len(upstream_surface_inventory)
    ready = sum(1 for row in upstream_surface_inventory if row.get("future_contract_ready"))
    missing_entry = sum(1 for row in upstream_surface_inventory if not row.get("can_emit_entry_mode"))
    missing_lane = sum(1 for row in upstream_surface_inventory if not row.get("can_emit_lane_key"))
    partial = sum(1 for row in upstream_surface_inventory if not row.get("future_contract_ready") and (row.get("can_emit_entry_mode") or row.get("can_emit_lane_key")))
    return {
        "surfaces_inspected": inspected,
        "surfaces_future_contract_ready": ready,
        "surfaces_partially_ready": partial,
        "surfaces_missing_entry_mode": missing_entry,
        "surfaces_missing_lane_key": missing_lane,
        "future_rows_can_be_born_complete": bool(inspected and ready == inspected),
    }


def build_existing_row_compatibility_report(source_propagation: Mapping[str, Any]) -> dict[str, Any]:
    gap = source_propagation.get("source_propagation_gap_report") if isinstance(source_propagation.get("source_propagation_gap_report"), Mapping) else {}
    return {
        "historical_rows_rewritten": False,
        "historical_rows_still_missing_entry_mode": int(gap.get("missing_entry_mode_rows") or 0),
        "historical_rows_still_missing_lane_key": int(gap.get("missing_lane_key_rows") or 0),
        "historical_resolver_ready_rows_created": 0,
        "why": "Historical rows are not rewritten; future source rows must carry the contract.",
    }


def build_upstream_contract_gap_report(
    *,
    source_propagation: Mapping[str, Any],
    readiness_report: Mapping[str, Any],
    compatibility_report: Mapping[str, Any],
) -> dict[str, Any]:
    gaps = []
    if not readiness_report.get("future_rows_can_be_born_complete"):
        gaps.append("not_all_future_surfaces_reference_r230_contract_helper")
    if readiness_report.get("surfaces_missing_entry_mode"):
        gaps.append("some_future_surfaces_cannot_emit_entry_mode")
    if readiness_report.get("surfaces_missing_lane_key"):
        gaps.append("some_future_surfaces_cannot_emit_lane_key")
    source_gap = source_propagation.get("source_propagation_gap_report") if isinstance(source_propagation.get("source_propagation_gap_report"), Mapping) else {}
    return {
        "future_contract_gaps_remaining": gaps,
        "historical_entry_mode_gap_remaining": bool(compatibility_report.get("historical_rows_still_missing_entry_mode")),
        "historical_lane_key_gap_remaining": bool(compatibility_report.get("historical_rows_still_missing_lane_key")),
        "resolver_ready_preview_rows": int(source_gap.get("resolver_ready_preview_rows") or 0),
        "hard_live_blockers": [
            "future_contract_wiring_is_not_live_authorization",
            "betrayal_not_live_authorized",
            "betrayal_not_promoted",
            "historical_rows_not_rewritten",
            "tiny_live_capture_threshold_separate",
            "config_writes_forbidden",
            "orders_forbidden",
            "binance_calls_forbidden",
        ],
    }


def build_upstream_contract_recommendations(
    *,
    gap_report: Mapping[str, Any],
    readiness_report: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "RUN_R231_FUTURE_CONTRACT_SMOKE",
            "future_phase": "R231",
            "why": "R230 defines the future emitter contract; R231 should prove a local synthetic future row is born complete without touching configs or live paths.",
        },
        {
            "priority": "MEDIUM",
            "recommended_action": "CHECK_8M_CAPTURE_THRESHOLD",
            "future_phase": "R228",
            "why": "Emitter contract readiness does not infer tiny-live readiness; BTCUSDT 8m short still needs the capture threshold.",
        },
    ]
    if gap_report.get("future_contract_gaps_remaining"):
        recommendations.insert(
            0,
            {
                "priority": "HIGH",
                "recommended_action": "RUN_FUTURE_BETRAYAL_EMITTER_WITH_CONTRACT",
                "future_phase": "R231",
                "why": "Not every inspected future surface references the R230 helper yet; future rows should be routed through the helper before source append work resumes.",
            },
        )
    if not readiness_report.get("future_rows_can_be_born_complete"):
        recommendations.append(
            {
                "priority": "LOW",
                "recommended_action": "KEEP_CONTEXT_ONLY",
                "future_phase": "R230",
                "why": "R230 is contract/report/ledger only and must not count as historical resolver readiness.",
            }
        )
    return recommendations


def classify_betrayal_upstream_contract_status(
    *,
    readiness_report: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> str:
    if "betrayal_not_live_authorized" in (gap_report.get("hard_live_blockers") or []):
        if readiness_report.get("future_rows_can_be_born_complete"):
            return UPSTREAM_EMITTER_CONTRACT_NOT_LIVE_AUTHORIZED
    if readiness_report.get("future_rows_can_be_born_complete"):
        return UPSTREAM_EMITTER_CONTRACT_READY_FOR_FUTURE_ROWS
    if readiness_report.get("surfaces_future_contract_ready") or readiness_report.get("surfaces_partially_ready"):
        return UPSTREAM_EMITTER_CONTRACT_PARTIALLY_READY
    if gap_report.get("future_contract_gaps_remaining"):
        return UPSTREAM_EMITTER_CONTRACT_GAPS_REMAIN
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_betrayal_upstream_contract_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = betrayal_upstream_contract_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "contract_id": str(record.get("contract_id") or f"r230_betrayal_upstream_emitter_entry_mode_contract_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_contract_requested": bool(record.get("record_contract_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "upstream_contract": dict(record.get("upstream_contract") or {}),
            "upstream_surface_inventory": list(record.get("upstream_surface_inventory") or []),
            "future_emitter_contract_readiness_report": dict(record.get("future_emitter_contract_readiness_report") or {}),
            "existing_row_compatibility_report": dict(record.get("existing_row_compatibility_report") or {}),
            "upstream_contract_gap_report": dict(record.get("upstream_contract_gap_report") or {}),
            "upstream_contract_recommendations": list(record.get("upstream_contract_recommendations") or []),
            "upstream_contract_status": record.get("upstream_contract_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(SAFETY),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_betrayal_upstream_contract_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = betrayal_upstream_contract_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_betrayal_upstream_contract_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    readiness = latest.get("future_emitter_contract_readiness_report") if isinstance(latest.get("future_emitter_contract_readiness_report"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "contract_status_counts": dict(sorted(Counter(str(record.get("upstream_contract_status") or "UNKNOWN") for record in records).items())),
        "last_contract_id": latest.get("contract_id") if isinstance(latest, Mapping) else None,
        "last_upstream_contract_status": latest.get("upstream_contract_status") if isinstance(latest, Mapping) else None,
        "last_surfaces_future_contract_ready": readiness.get("surfaces_future_contract_ready") if isinstance(readiness, Mapping) else None,
        "safety": dict(SAFETY),
    }


def betrayal_upstream_contract_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_upstream_emitter_entry_mode_contract_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _upstream_contract_manifest() -> dict[str, Any]:
    return {
        "contract_name": CONTRACT_NAME,
        "future_rows_only": True,
        "required_fields": get_betrayal_upstream_required_fields(),
        "entry_mode_must_exist_in_registry": True,
        "common_default_inference_allowed": False,
        "candidate_label_inference_allowed": False,
        "timeframe_only_inference_allowed": False,
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _top_level_status(*, record_contract: bool, confirmation_valid: bool, registry_valid: bool) -> str:
    if record_contract and not confirmation_valid:
        return BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_REJECTED
    if not registry_valid:
        return BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_BLOCKED
    if record_contract and confirmation_valid:
        return BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_RECORDED
    return BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_READY


def _recommended_next_operator_move(contract_status: str, readiness_report: Mapping[str, Any]) -> str:
    if readiness_report.get("future_rows_can_be_born_complete"):
        return "RUN_R231_FUTURE_BETRAYAL_CONTRACT_SMOKE"
    if contract_status == UPSTREAM_EMITTER_CONTRACT_GAPS_REMAIN:
        return "KEEP_FISHERMAN_RUNNING"
    return "CHECK_8M_CAPTURE_THRESHOLD"


def _recommended_next_engineering_move(contract_status: str, gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("future_contract_gaps_remaining"):
        return "Adopt the R230 contract helper in remaining future betrayal emitter surfaces before any normalized source append phase."
    if contract_status == UPSTREAM_EMITTER_CONTRACT_NOT_LIVE_AUTHORIZED:
        return "Run R231 local future-row contract smoke; keep betrayal paper-only and do not infer live readiness."
    return "Keep R230 as the future upstream contract and proceed only to paper-only local smoke validation."


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


def _registry_manifest(registry: Mapping[str, Any]) -> dict[str, Any]:
    manifest = registry.get("registry_manifest") if isinstance(registry, Mapping) else {}
    return dict(manifest) if isinstance(manifest, Mapping) else {}


def _entry_mode_rejection_reason(
    *,
    mode: str | None,
    valid_modes: set[str],
    forbidden_inference: bool,
    inference_source: str,
) -> str | None:
    if forbidden_inference:
        return f"entry_mode_inference_forbidden:{inference_source}"
    if not mode:
        return "entry_mode_missing"
    if mode in {"unknown", "entry_unknown"}:
        return "entry_mode_placeholder_blocked"
    if mode not in valid_modes:
        return "entry_mode_not_in_registry"
    return None


def _missing_contract_field(row: Mapping[str, Any], field: str) -> bool:
    value = row.get(field)
    if field in {"paper_only", "live_authorized", "promotion_allowed"}:
        return value is None
    if isinstance(value, Sequence) and not isinstance(value, str):
        return not bool(value)
    return not bool(_string_or_none(value))


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


def _normal_direction(value: Any) -> str | None:
    normalized = _string_or_none(value)
    if normalized in {"long", "short"}:
        return normalized
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.lower() if text.lower() in {"long", "short", "unknown", "entry_unknown"} else text


def _dedupe(values: Sequence[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
