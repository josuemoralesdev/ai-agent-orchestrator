"""R237 betrayal true inverse outcome capture bridge.

Preview-only bridge from R236 betrayal paper outcome tracking identities into
true-inverse outcome capture specs. This module never writes normal paper
outcomes, configs, lane controls, risk contracts, or live state.
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
from src.app.hammer_radar.operator.betrayal_gate_ready_lane_packet import (
    build_betrayal_gate_ready_lane_packet,
    load_betrayal_gate_ready_lane_packet_records,
)
from src.app.hammer_radar.operator.betrayal_paper_outcome_tracking_bridge import (
    BRIDGE_READY,
    build_betrayal_paper_outcome_tracking_bridge,
    load_betrayal_paper_outcome_tracking_bridge_records,
    load_existing_paper_outcome_schema_context as _load_r236_paper_outcome_schema_context,
)
from src.app.hammer_radar.operator.betrayal_signal_origin_integration_contract import (
    build_betrayal_signal_origin_integration_contract,
    load_betrayal_signal_origin_integration_contract_records,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import (
    DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    DEFAULT_THRESHOLD_REQUIRED_COUNT,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.strategy_evidence_registry import get_entry_mode_manifest

BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_READY = "BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_READY"
BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_REJECTED = "BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_REJECTED"
BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDED = "BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDED"
BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_BLOCKED = "BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_BLOCKED"
BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_ERROR = "BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_ERROR"

BETRAYAL_TRUE_INVERSE_CAPTURE_READY = "BETRAYAL_TRUE_INVERSE_CAPTURE_READY"
BETRAYAL_TRUE_INVERSE_CAPTURE_PARTIALLY_READY = "BETRAYAL_TRUE_INVERSE_CAPTURE_PARTIALLY_READY"
BETRAYAL_TRUE_INVERSE_CAPTURE_NEEDS_ENTRY_MODE = "BETRAYAL_TRUE_INVERSE_CAPTURE_NEEDS_ENTRY_MODE"
BETRAYAL_TRUE_INVERSE_CAPTURE_NEEDS_MARKET_WINDOW = "BETRAYAL_TRUE_INVERSE_CAPTURE_NEEDS_MARKET_WINDOW"
BETRAYAL_TRUE_INVERSE_CAPTURE_WAITING_FOR_OUTCOMES = "BETRAYAL_TRUE_INVERSE_CAPTURE_WAITING_FOR_OUTCOMES"
BETRAYAL_TRUE_INVERSE_PROMOTION_PATH_KNOWN_BUT_BLOCKED = "BETRAYAL_TRUE_INVERSE_PROMOTION_PATH_KNOWN_BUT_BLOCKED"
BETRAYAL_TRUE_INVERSE_NOT_ENOUGH_DATA = "BETRAYAL_TRUE_INVERSE_NOT_ENOUGH_DATA"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

TRUE_INVERSE_CAPTURE_READY = "TRUE_INVERSE_CAPTURE_READY"
TRUE_INVERSE_CAPTURE_TRACKABLE = "TRUE_INVERSE_CAPTURE_TRACKABLE"
TRUE_INVERSE_OUTCOME_FOUND = "TRUE_INVERSE_OUTCOME_FOUND"
TRUE_INVERSE_OUTCOME_PENDING = "TRUE_INVERSE_OUTCOME_PENDING"
NEEDS_MARKET_WINDOW = "NEEDS_MARKET_WINDOW"
NEEDS_ENTRY_MODE = "NEEDS_ENTRY_MODE"
NEEDS_LANE_KEY = "NEEDS_LANE_KEY"
NEEDS_OUTCOME_IDENTITY = "NEEDS_OUTCOME_IDENTITY"
NEEDS_SOURCE_SIGNAL = "NEEDS_SOURCE_SIGNAL"
BLOCKED = "BLOCKED"

EVENT_TYPE = "BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE"
LEDGER_FILENAME = "betrayal_true_inverse_outcome_capture_bridge.ndjson"
SCHEMA_VERSION = "betrayal_true_inverse_outcome_capture_bridge_v1"
CONFIRM_BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL TRUE INVERSE OUTCOME CAPTURE BRIDGE RECORDING ONLY; "
    "NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "fisherman_config_written": False,
    "scheduler_config_written": False,
    "ledger_rewritten": False,
    "destructive_write": False,
    "historical_ledger_rewritten": False,
    "normalized_rows_appended": False,
    "paper_outcome_ledger_rewritten": False,
    "paper_outcomes_appended": False,
    "true_inverse_outcomes_fabricated": False,
    "capture_bridge_preview_ledger_only": True,
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
    "official_tiny_live_lane_changed": False,
    "alternate_lane_promoted": False,
    "betrayal_live_authorized": False,
    "betrayal_promoted": False,
    "betrayal_true_inverse_capture_preview_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/betrayal_paper_outcome_tracking_bridge.ndjson",
    "logs/hammer_radar_forward/betrayal_signal_origin_integration_contract.ndjson",
    "logs/hammer_radar_forward/betrayal_gate_ready_lane_packet.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_resolutions.ndjson",
    "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_signals.ndjson",
    "logs/hammer_radar_forward/paper_outcomes.ndjson",
    "logs/hammer_radar_forward/outcomes.ndjson",
    "logs/hammer_radar_forward/strategy_performance.ndjson",
    "logs/hammer_radar_forward/strategy_promotion_status.ndjson",
    "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_true_inverse_outcome_capture_bridge(
    *,
    log_dir: str | Path | None = None,
    record_capture_bridge: bool = False,
    confirm_betrayal_true_inverse_outcome_capture_bridge: str | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_true_inverse_outcome_capture_bridge
        == CONFIRM_BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDING_PHRASE
    )
    try:
        r236_bridge = load_latest_betrayal_paper_outcome_tracking_bridge(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        r235_contract = load_latest_betrayal_signal_origin_integration_contract(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        r234_packet = load_latest_betrayal_gate_ready_lane_packet(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        true_outcomes = load_existing_betrayal_true_paper_outcomes(log_dir=resolved_log_dir)
        schema_context = load_existing_paper_outcome_schema_context(log_dir=resolved_log_dir)
        rows = build_true_inverse_capture_preview_rows(
            betrayal_outcome_bridge=r236_bridge,
            signal_origin_contract=r235_contract,
            gate_ready_packet=r234_packet,
            existing_true_paper_outcomes=true_outcomes,
            schema_context=schema_context,
        )
        summary = build_true_inverse_capture_summary(rows)
        gap_report = build_true_inverse_capture_gap_report(rows)
        ranking_projection = build_true_inverse_capture_ranking_projection(rows)
        recommendations = build_true_inverse_capture_recommendations(
            rows=rows,
            gap_report=gap_report,
            official_tiny_live_status=_official_tiny_live_status(
                bridge=r236_bridge,
                gate_packet=r234_packet,
                schema_context=schema_context,
                official_tiny_live_lane=official_tiny_live_lane,
                threshold_required_count=threshold_required_count,
            ),
        )
        overall = classify_betrayal_true_inverse_capture_overall_status(
            rows=rows,
            gap_report=gap_report,
            ranking_projection=ranking_projection,
        )
        status = BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_READY if rows else BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_BLOCKED
        if record_capture_bridge and not confirmation_valid:
            status = BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_REJECTED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "capture_bridge_recorded": False,
            "capture_bridge_record_id": None,
            "record_capture_bridge_requested": bool(record_capture_bridge),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "paper_only": True,
                "live_authorized": False,
                "betrayal_signal_origin_family": "betrayal",
                "true_inverse_capture_preview_only": True,
                "official_tiny_live_lane": official_tiny_live_lane,
                "official_tiny_live_lane_changed": False,
            },
            "input_summary": {
                "betrayal_outcome_bridge_found": bool(r236_bridge.get("bridge_preview_rows")),
                "betrayal_signal_origin_contract_found": bool(r235_contract.get("same_flow_readiness_rows")),
                "betrayal_gate_ready_packet_found": bool(r234_packet.get("betrayal_candidate_lane_registry")),
                "betrayal_true_paper_outcomes_found": bool(true_outcomes),
                "paper_outcome_schema_context_found": bool(schema_context.get("context_found")),
                "tiny_live_capture_sync_found": bool(schema_context.get("latest_records_found", {}).get("capture_count_sync_8m_short"))
                or bool(r236_bridge.get("official_tiny_live_status"))
                or bool(r234_packet.get("official_tiny_live_status")),
            },
            "official_tiny_live_status": _official_tiny_live_status(
                bridge=r236_bridge,
                gate_packet=r234_packet,
                schema_context=schema_context,
                official_tiny_live_lane=official_tiny_live_lane,
                threshold_required_count=threshold_required_count,
            ),
            "true_inverse_capture_preview_rows": rows,
            "capture_summary": summary,
            "capture_gap_report": gap_report,
            "ranking_projection": ranking_projection,
            "capture_recommendations": recommendations,
            "capture_overall_status": overall,
            "recommended_next_operator_move": _recommended_next_operator_move(
                _official_tiny_live_status(
                    bridge=r236_bridge,
                    gate_packet=r234_packet,
                    schema_context=schema_context,
                    official_tiny_live_lane=official_tiny_live_lane,
                    threshold_required_count=threshold_required_count,
                ),
                schema_context=schema_context,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(overall, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_capture_bridge and confirmation_valid:
            record = append_betrayal_true_inverse_outcome_capture_bridge_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDED
            payload["capture_bridge_recorded"] = True
            payload["capture_bridge_record_id"] = record["capture_bridge_record_id"]
            payload["ledger_path"] = str(betrayal_true_inverse_outcome_capture_bridge_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_ERROR,
                "generated_at": generated_at.isoformat(),
                "capture_bridge_recorded": False,
                "capture_bridge_record_id": None,
                "record_capture_bridge_requested": bool(record_capture_bridge),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {
                    "paper_only": True,
                    "live_authorized": False,
                    "betrayal_signal_origin_family": "betrayal",
                    "true_inverse_capture_preview_only": True,
                    "official_tiny_live_lane": official_tiny_live_lane,
                    "official_tiny_live_lane_changed": False,
                },
                "input_summary": {},
                "official_tiny_live_status": _empty_official_tiny_live_status(official_tiny_live_lane, threshold_required_count),
                "true_inverse_capture_preview_rows": [],
                "capture_summary": build_true_inverse_capture_summary([]),
                "capture_gap_report": build_true_inverse_capture_gap_report([]),
                "ranking_projection": build_true_inverse_capture_ranking_projection([]),
                "capture_recommendations": [],
                "capture_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R237 true inverse capture bridge error before recording bridge previews.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_paper_outcome_tracking_bridge(
    *,
    log_dir: str | Path | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
) -> dict[str, Any]:
    records = load_betrayal_paper_outcome_tracking_bridge_records(log_dir=log_dir, limit=1)
    if records:
        return _sanitize(records[0])
    return _sanitize(
        build_betrayal_paper_outcome_tracking_bridge(
            log_dir=log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
    )


def load_latest_betrayal_signal_origin_integration_contract(
    *,
    log_dir: str | Path | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
) -> dict[str, Any]:
    records = load_betrayal_signal_origin_integration_contract_records(log_dir=log_dir, limit=1)
    if records:
        return _sanitize(records[0])
    return _sanitize(
        build_betrayal_signal_origin_integration_contract(
            log_dir=log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
    )


def load_latest_betrayal_gate_ready_lane_packet(
    *,
    log_dir: str | Path | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
) -> dict[str, Any]:
    records = load_betrayal_gate_ready_lane_packet_records(log_dir=log_dir, limit=1)
    if records:
        return _sanitize(records[0])
    return _sanitize(
        build_betrayal_gate_ready_lane_packet(
            log_dir=log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
    )


def load_existing_betrayal_true_paper_outcomes(*, log_dir: str | Path | None = None, limit: int = 0) -> list[dict[str, Any]]:
    path = get_log_dir(log_dir, use_env=True) / "betrayal_true_paper_outcomes.ndjson"
    return _read_records(path, limit=limit)


def load_existing_paper_outcome_schema_context(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    context = _load_r236_paper_outcome_schema_context(log_dir=log_dir)
    resolved = get_log_dir(log_dir, use_env=True)
    extra_files = {
        "betrayal_shadow_outcomes": "betrayal_shadow_outcomes.ndjson",
        "betrayal_shadow_resolutions": "betrayal_shadow_resolutions.ndjson",
    }
    latest = dict(context.get("latest_records") or {})
    found = dict(context.get("latest_records_found") or {})
    counts = dict(context.get("record_counts") or {})
    for name, filename in extra_files.items():
        path = resolved / filename
        latest[name] = _latest_record(path)
        found[name] = bool(latest[name])
        counts[name] = _record_count(path)
    context["latest_records"] = latest
    context["latest_records_found"] = found
    context["record_counts"] = counts
    context["true_inverse_capture_join_fields"] = [
        "capture_id",
        "paper_outcome_tracking_identity",
        "signal_id",
        "source_signal_id",
        "source_identity",
    ]
    return _sanitize(context)


def build_true_inverse_capture_id(row: Mapping[str, Any]) -> str:
    material = "|".join(
        str(row.get(key) or "")
        for key in (
            "signal_origin_family",
            "signal_origin_type",
            "signal_origin_variant",
            "lane_key",
            "signal_id",
            "source_signal_id",
            "paper_outcome_tracking_identity",
        )
    )
    return "betrayal_true_inverse_capture_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def infer_inverse_direction(direction: Any) -> str | None:
    value = str(direction or "").strip().lower()
    if value == "long":
        return "short"
    if value == "short":
        return "long"
    return None


def build_true_inverse_capture_window(
    row: Mapping[str, Any],
    *,
    schema_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    spec = _normalize_outcome_window(row.get("outcome_window_spec"))
    if not spec:
        spec = _normalize_outcome_window((schema_context or {}).get("outcome_window_convention"))
    checkpoints = [
        {
            "checkpoint": checkpoint,
            "checkpoint_type": "bar_offset",
            "result_required": True,
            "result_pending": True,
        }
        for checkpoint in spec
    ]
    return {
        "entry_reference": row.get("signal_id") or row.get("source_signal_id") or row.get("source_identity"),
        "outcome_window_spec": spec,
        "capture_checkpoints": checkpoints,
    }


def normalize_betrayal_bridge_row_for_true_inverse_capture(
    row: Mapping[str, Any],
    *,
    existing_true_paper_outcomes: Sequence[Mapping[str, Any]] | None = None,
    schema_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = dict(row)
    direction = _string_or_none(base.get("direction"))
    original_direction = _string_or_none(base.get("original_direction")) or infer_inverse_direction(direction)
    inverse_direction = _string_or_none(base.get("inverse_direction")) or direction
    window = build_true_inverse_capture_window(base, schema_context=schema_context or {})
    capture_id = build_true_inverse_capture_id(base)
    outcome_match = _find_true_inverse_outcome(
        base,
        capture_id=capture_id,
        existing_true_paper_outcomes=existing_true_paper_outcomes or [],
    )
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "capture_id": capture_id,
        "capture_status": None,
        "signal_origin_family": base.get("signal_origin_family"),
        "signal_origin_type": base.get("signal_origin_type"),
        "signal_origin_variant": base.get("signal_origin_variant"),
        "symbol": _string_or_none(base.get("symbol")),
        "timeframe": _string_or_none(base.get("timeframe")),
        "original_direction": original_direction,
        "inverse_direction": inverse_direction,
        "entry_mode": _string_or_none(base.get("entry_mode")),
        "lane_key": _string_or_none(base.get("lane_key")),
        "signal_id": _string_or_none(base.get("signal_id")),
        "source_signal_id": _string_or_none(base.get("source_signal_id")),
        "source_identity": _string_or_none(base.get("source_identity")),
        "paper_outcome_tracking_identity": _string_or_none(base.get("paper_outcome_tracking_identity")),
        "entry_reference": window["entry_reference"],
        "outcome_window_spec": window["outcome_window_spec"],
        "capture_checkpoints": window["capture_checkpoints"],
        "bridge_status": base.get("bridge_status"),
        "paper_signal_ready": bool(base.get("paper_signal_ready")),
        "paper_outcome_ready": bool(base.get("paper_outcome_ready")),
        "outcome_tracking_ready": bool(base.get("outcome_tracking_ready")),
        "ranking_feed_ready": bool(base.get("ranking_feed_ready")),
        "true_inverse_outcome_found": bool(outcome_match),
        "true_inverse_outcome_reference": _outcome_reference(outcome_match) if outcome_match else None,
        "result_pending": not bool(outcome_match),
        "ranking_projection_ready": False,
        "promotion_review_ready": False,
        "live_ready_today": False,
        "paper_only": bool(base.get("paper_only")),
        "live_authorized": False,
        "promotion_allowed": False,
    }
    status, blockers = classify_true_inverse_capture_status(normalized, schema_context=schema_context or {})
    normalized["capture_status"] = status
    normalized["ranking_projection_ready"] = status in {TRUE_INVERSE_CAPTURE_READY, TRUE_INVERSE_OUTCOME_FOUND}
    normalized["blockers"] = blockers
    normalized["why"] = _capture_row_why(status, blockers)
    return _sanitize(normalized)


def classify_true_inverse_capture_status(
    row: Mapping[str, Any],
    *,
    schema_context: Mapping[str, Any] | None = None,
) -> tuple[str, list[str]]:
    valid_modes = set((schema_context or {}).get("registry_valid_entry_modes") or [])
    blockers = []
    if row.get("signal_origin_family") != "betrayal":
        blockers.append("not_betrayal_signal_origin_family")
    if row.get("bridge_status") != BRIDGE_READY:
        blockers.append("bridge_not_ready")
    if row.get("paper_signal_ready") is not True:
        blockers.append("paper_signal_not_ready")
    if row.get("paper_outcome_ready") is not True:
        blockers.append("paper_outcome_not_ready")
    if row.get("outcome_tracking_ready") is not True:
        blockers.append("outcome_tracking_not_ready")
    if row.get("ranking_feed_ready") is not True:
        blockers.append("ranking_feed_not_ready")
    if not row.get("symbol"):
        blockers.append("missing_symbol")
    if not row.get("timeframe"):
        blockers.append("missing_timeframe")
    if not row.get("original_direction") or not row.get("inverse_direction"):
        blockers.append("missing_direction")
    entry_mode = str(row.get("entry_mode") or "")
    if not entry_mode or entry_mode in {"entry_unknown", "unknown", "None"} or (valid_modes and entry_mode not in valid_modes):
        blockers.append("missing_entry_mode")
    if not row.get("lane_key") or str(row.get("lane_key")).endswith("|entry_unknown"):
        blockers.append("missing_lane_key")
    if not row.get("signal_id") or not row.get("source_signal_id") or not row.get("source_identity"):
        blockers.append("missing_source_signal")
    if not row.get("paper_outcome_tracking_identity"):
        blockers.append("missing_outcome_identity")
    if not row.get("outcome_window_spec") or not row.get("capture_checkpoints"):
        blockers.append("missing_market_window")
    if row.get("paper_only") is not True:
        blockers.append("paper_only_not_true")
    if row.get("live_authorized") is not False:
        blockers.append("live_authorized_not_false")
    if row.get("promotion_allowed") is not False:
        blockers.append("promotion_allowed_not_false")

    hard = set(blockers)
    if row.get("true_inverse_outcome_found") and not hard:
        status = TRUE_INVERSE_OUTCOME_FOUND
    elif "missing_entry_mode" in hard:
        status = NEEDS_ENTRY_MODE
    elif "missing_lane_key" in hard:
        status = NEEDS_LANE_KEY
    elif "missing_outcome_identity" in hard:
        status = NEEDS_OUTCOME_IDENTITY
    elif "missing_source_signal" in hard:
        status = NEEDS_SOURCE_SIGNAL
    elif "missing_market_window" in hard:
        status = NEEDS_MARKET_WINDOW
    elif hard:
        status = BLOCKED
    else:
        status = TRUE_INVERSE_CAPTURE_READY

    if row.get("result_pending") is True and status == TRUE_INVERSE_CAPTURE_READY:
        blockers.append("true_inverse_outcome_pending")
    blockers.extend(["risk_contract_missing", "operator_approval_missing", "global_live_gate_closed"])
    return status, _dedupe(blockers)


def build_true_inverse_capture_preview_rows(
    *,
    betrayal_outcome_bridge: Mapping[str, Any],
    signal_origin_contract: Mapping[str, Any] | None = None,
    gate_ready_packet: Mapping[str, Any] | None = None,
    existing_true_paper_outcomes: Sequence[Mapping[str, Any]] | None = None,
    schema_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del signal_origin_contract, gate_ready_packet
    rows = []
    for row in betrayal_outcome_bridge.get("bridge_preview_rows") or []:
        if not isinstance(row, Mapping) or row.get("signal_origin_family") != "betrayal":
            continue
        rows.append(
            normalize_betrayal_bridge_row_for_true_inverse_capture(
                row,
                existing_true_paper_outcomes=existing_true_paper_outcomes or [],
                schema_context=schema_context or {},
            )
        )
    rows.sort(
        key=lambda row: (
            row.get("capture_status") not in {TRUE_INVERSE_OUTCOME_FOUND, TRUE_INVERSE_CAPTURE_READY},
            str(row.get("lane_key") or ""),
            str(row.get("signal_id") or ""),
            str(row.get("capture_id") or ""),
        )
    )
    return _sanitize(rows)


def build_true_inverse_capture_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "rows_reviewed": len(rows),
        "true_inverse_capture_ready_rows": sum(1 for row in rows if row.get("capture_status") == TRUE_INVERSE_CAPTURE_READY),
        "true_inverse_capture_trackable_rows": sum(
            1 for row in rows if row.get("capture_status") in {TRUE_INVERSE_CAPTURE_READY, TRUE_INVERSE_CAPTURE_TRACKABLE}
        ),
        "true_inverse_outcome_found_rows": sum(1 for row in rows if row.get("true_inverse_outcome_found")),
        "true_inverse_outcome_pending_rows": sum(1 for row in rows if row.get("result_pending")),
        "ranking_projection_ready_rows": sum(1 for row in rows if row.get("ranking_projection_ready")),
        "promotion_review_ready_rows": 0,
        "live_ready_today_rows": 0,
        "blocked_rows": sum(1 for row in rows if row.get("capture_status") in {BLOCKED, NEEDS_ENTRY_MODE, NEEDS_LANE_KEY, NEEDS_OUTCOME_IDENTITY, NEEDS_SOURCE_SIGNAL, NEEDS_MARKET_WINDOW}),
    }


def build_true_inverse_capture_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "missing_entry_mode_rows": _count_blocker(rows, "missing_entry_mode"),
        "missing_lane_key_rows": _count_blocker(rows, "missing_lane_key"),
        "missing_source_signal_rows": _count_blocker(rows, "missing_source_signal"),
        "missing_outcome_identity_rows": _count_blocker(rows, "missing_outcome_identity"),
        "needs_market_window_rows": _count_blocker(rows, "missing_market_window"),
        "pending_true_inverse_outcome_rows": sum(1 for row in rows if row.get("result_pending")),
        "hard_live_blockers": ["risk_contract_missing", "operator_approval_missing", "global_live_gate_closed"],
    }


def build_true_inverse_capture_ranking_projection(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ready_or_found = [row for row in rows if row.get("capture_status") in {TRUE_INVERSE_CAPTURE_READY, TRUE_INVERSE_OUTCOME_FOUND}]
    return {
        "can_feed_ranking_after_outcomes": bool(ready_or_found),
        "promotion_path_known": True,
        "promotion_path_blocked": True,
        "requirements_remaining": [
            "true inverse outcomes must be captured",
            "ranking/performance evidence must be computed",
            "promotion gate review later",
            "risk contract later",
            "operator approval later",
            "global live gate later",
        ],
        "live_ready_today": False,
    }


def build_true_inverse_capture_recommendations(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
    official_tiny_live_status: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "RUN_R228_IF_10_OF_10" if official_tiny_live_status.get("threshold_met") else "WAIT_FOR_10_OF_10",
            "future_phase": "R228",
            "why": "The official protected BTCUSDT 8m short lane remains the only tiny-live readiness path.",
        }
    ]
    if any(row.get("capture_status") == TRUE_INVERSE_CAPTURE_READY for row in rows):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "COLLECT_TRUE_INVERSE_OUTCOMES",
                "future_phase": "R238",
                "why": "Bridge-ready betrayal identities have deterministic true inverse capture specs but still need paper-only outcome evidence.",
            }
        )
    if any(row.get("true_inverse_outcome_found") for row in rows):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "WIRE_BETRAYAL_RANKING_FEED",
                "future_phase": "R238",
                "why": "Existing true inverse outcomes can be previewed for ranking/performance feed readiness without promotion.",
            }
        )
    if gap_report.get("missing_entry_mode_rows") or gap_report.get("missing_lane_key_rows"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "ADOPT_R230_ENTRY_MODE_CONTRACT",
                "future_phase": "R238",
                "why": "Rows missing registry-valid entry_mode or lane_key cannot enter true inverse capture.",
            }
        )
    return recommendations


def classify_betrayal_true_inverse_capture_overall_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
    ranking_projection: Mapping[str, Any],
) -> str:
    if not rows:
        return BETRAYAL_TRUE_INVERSE_NOT_ENOUGH_DATA
    if gap_report.get("missing_entry_mode_rows") or gap_report.get("missing_lane_key_rows"):
        return BETRAYAL_TRUE_INVERSE_CAPTURE_NEEDS_ENTRY_MODE
    if gap_report.get("needs_market_window_rows"):
        return BETRAYAL_TRUE_INVERSE_CAPTURE_NEEDS_MARKET_WINDOW
    if gap_report.get("pending_true_inverse_outcome_rows") and ranking_projection.get("can_feed_ranking_after_outcomes"):
        return BETRAYAL_TRUE_INVERSE_CAPTURE_WAITING_FOR_OUTCOMES
    if ranking_projection.get("promotion_path_blocked") and ranking_projection.get("can_feed_ranking_after_outcomes"):
        return BETRAYAL_TRUE_INVERSE_PROMOTION_PATH_KNOWN_BUT_BLOCKED
    if all(row.get("capture_status") in {TRUE_INVERSE_CAPTURE_READY, TRUE_INVERSE_OUTCOME_FOUND} for row in rows):
        return BETRAYAL_TRUE_INVERSE_CAPTURE_READY
    if any(row.get("capture_status") in {TRUE_INVERSE_CAPTURE_READY, TRUE_INVERSE_OUTCOME_FOUND} for row in rows):
        return BETRAYAL_TRUE_INVERSE_CAPTURE_PARTIALLY_READY
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_betrayal_true_inverse_outcome_capture_bridge_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_true_inverse_outcome_capture_bridge_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "capture_bridge_record_id": str(record.get("capture_bridge_record_id") or f"r237_betrayal_true_inverse_capture_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_capture_bridge_requested": bool(record.get("record_capture_bridge_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "official_tiny_live_status": dict(record.get("official_tiny_live_status") or {}),
            "true_inverse_capture_preview_rows": list(record.get("true_inverse_capture_preview_rows") or []),
            "capture_summary": dict(record.get("capture_summary") or {}),
            "capture_gap_report": dict(record.get("capture_gap_report") or {}),
            "ranking_projection": dict(record.get("ranking_projection") or {}),
            "capture_recommendations": list(record.get("capture_recommendations") or []),
            "capture_overall_status": record.get("capture_overall_status"),
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


def load_betrayal_true_inverse_outcome_capture_bridge_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_true_inverse_outcome_capture_bridge_records_path(get_log_dir(log_dir, use_env=True))
    return _read_records(path, limit=limit)


def summarize_betrayal_true_inverse_outcome_capture_bridge_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "capture_overall_status_counts": dict(
            sorted(Counter(str(record.get("capture_overall_status") or "UNKNOWN") for record in records).items())
        ),
        "latest_capture_bridge_record_id": latest.get("capture_bridge_record_id") if isinstance(latest, Mapping) else None,
        "latest_capture_overall_status": latest.get("capture_overall_status") if isinstance(latest, Mapping) else None,
        "safety": dict(SAFETY),
    }


def betrayal_true_inverse_outcome_capture_bridge_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_true_inverse_outcome_capture_bridge_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _find_true_inverse_outcome(
    row: Mapping[str, Any],
    *,
    capture_id: str,
    existing_true_paper_outcomes: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    keys = {
        _string_or_none(capture_id),
        _string_or_none(row.get("paper_outcome_tracking_identity")),
        _string_or_none(row.get("signal_id")),
        _string_or_none(row.get("source_signal_id")),
        _string_or_none(row.get("source_identity")),
    }
    keys.discard(None)
    for outcome in existing_true_paper_outcomes:
        if not isinstance(outcome, Mapping):
            continue
        outcome_keys = {
            _string_or_none(outcome.get("capture_id")),
            _string_or_none(outcome.get("paper_outcome_tracking_identity")),
            _string_or_none(outcome.get("signal_id")),
            _string_or_none(outcome.get("source_signal_id")),
            _string_or_none(outcome.get("source_identity")),
            _string_or_none(outcome.get("outcome_identity")),
        }
        outcome_keys.discard(None)
        if keys.intersection(outcome_keys):
            return dict(outcome)
    return None


def _outcome_reference(outcome: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "capture_id": outcome.get("capture_id"),
        "paper_outcome_tracking_identity": outcome.get("paper_outcome_tracking_identity"),
        "signal_id": outcome.get("signal_id"),
        "outcome_status": outcome.get("outcome_status") or outcome.get("status") or outcome.get("outcome"),
        "recorded_at_utc": outcome.get("recorded_at_utc") or outcome.get("generated_at"),
    }


def _official_tiny_live_status(
    *,
    bridge: Mapping[str, Any],
    gate_packet: Mapping[str, Any],
    schema_context: Mapping[str, Any],
    official_tiny_live_lane: str,
    threshold_required_count: int,
) -> dict[str, Any]:
    from_bridge = dict(bridge.get("official_tiny_live_status") or {})
    from_gate = dict(gate_packet.get("official_tiny_live_status") or {})
    from_sync = dict((schema_context.get("latest_records") or {}).get("capture_count_sync_8m_short") or {})
    capture = dict(from_sync.get("capture_count") or {})
    fresh = int(from_bridge.get("fresh_capture_count") or from_gate.get("fresh_capture_count") or capture.get("fresh_capture_count") or 0)
    required = int(
        from_bridge.get("required_fresh_capture_count")
        or from_gate.get("required_fresh_capture_count")
        or capture.get("required_fresh_capture_count")
        or threshold_required_count
    )
    threshold_met = bool(
        from_bridge.get("threshold_met") or from_gate.get("threshold_met") or capture.get("threshold_met") or fresh >= required
    )
    return {
        "lane_key": str(from_bridge.get("lane_key") or from_gate.get("lane_key") or official_tiny_live_lane),
        "fresh_capture_count": fresh,
        "required_fresh_capture_count": required,
        "threshold_met": threshold_met,
        "threshold_distance_remaining": max(0, required - fresh),
        "recommended_action": "RUN_R228_IF_10_OF_10" if threshold_met else "WAIT_FOR_10_OF_10",
    }


def _empty_official_tiny_live_status(lane_key: str, required: int) -> dict[str, Any]:
    return {
        "lane_key": lane_key,
        "fresh_capture_count": 0,
        "required_fresh_capture_count": required,
        "threshold_met": False,
        "threshold_distance_remaining": required,
        "recommended_action": "WAIT_FOR_10_OF_10",
    }


def _recommended_next_operator_move(
    official_tiny_live_status: Mapping[str, Any],
    *,
    schema_context: Mapping[str, Any],
) -> str:
    if official_tiny_live_status.get("threshold_met"):
        return "RUN_R228_TINY_LIVE_10_OF_10_READY_PACKET"
    latest_sync = dict((schema_context.get("latest_records") or {}).get("capture_count_sync_8m_short") or {})
    if latest_sync:
        return "WAIT_FOR_10_OF_10"
    return "KEEP_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(overall_status: str, gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("pending_true_inverse_outcome_rows"):
        return "Create R238 betrayal ranking feed preview after true inverse outcomes are captured; do not feed ranking yet."
    if overall_status == BETRAYAL_TRUE_INVERSE_CAPTURE_NEEDS_ENTRY_MODE:
        return "Continue entry_mode/lane_key adoption for blocked betrayal rows before ranking feed preview."
    return "Keep R237 bridge preview-only and wait for more true inverse paper outcome evidence."


def _capture_row_why(status: str, blockers: Sequence[str]) -> str:
    if status == TRUE_INVERSE_CAPTURE_READY:
        return "Betrayal identity has deterministic true inverse capture specs; result is pending and live/promotion remain blocked."
    if status == TRUE_INVERSE_OUTCOME_FOUND:
        return "Existing betrayal true paper outcome matched this identity; ranking can be previewed later without promotion."
    if status == NEEDS_ENTRY_MODE:
        return "Betrayal identity needs registry-valid entry_mode before true inverse capture."
    if status == NEEDS_LANE_KEY:
        return "Betrayal identity needs lane_key before true inverse capture."
    if status == NEEDS_SOURCE_SIGNAL:
        return "Betrayal identity needs signal_id, source_signal_id, and source_identity."
    if status == NEEDS_OUTCOME_IDENTITY:
        return "Betrayal identity needs paper_outcome_tracking_identity before true inverse capture."
    if status == NEEDS_MARKET_WINDOW:
        return "Betrayal identity needs outcome window checkpoints before true inverse capture."
    return "Betrayal true inverse capture remains blocked: " + ", ".join(_dedupe(blockers)[:4])


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
        "betrayal live promotion",
    ]


def _latest_record(path: Path) -> dict[str, Any]:
    records = _read_records(path, limit=1)
    return records[0] if records else {}


def _record_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _read_records(path: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if limit > 0:
        return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping):
                records.append(_sanitize(parsed))
    return records


def _normalize_outcome_window(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _count_blocker(rows: Sequence[Mapping[str, Any]], blocker: str) -> int:
    return sum(1 for row in rows if blocker in (row.get("blockers") or []))


def _dedupe(values: Sequence[Any]) -> list[Any]:
    seen = set()
    out = []
    for value in values:
        key = json.dumps(_sanitize(value), sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, set):
        return sorted(_sanitize(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    return value
