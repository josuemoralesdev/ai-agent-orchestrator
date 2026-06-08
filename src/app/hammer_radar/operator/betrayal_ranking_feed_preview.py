"""R238 betrayal ranking feed preview.

Preview-only contract from R237 true-inverse capture rows into the ranking feed
shape. This module never writes normal ranking/performance/promotion ledgers,
configs, paper outcomes, or live state.
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
from src.app.hammer_radar.operator.betrayal_paper_outcome_tracking_bridge import (
    build_betrayal_paper_outcome_tracking_bridge,
    load_betrayal_paper_outcome_tracking_bridge_records,
)
from src.app.hammer_radar.operator.betrayal_signal_origin_integration_contract import (
    build_betrayal_signal_origin_integration_contract,
    load_betrayal_signal_origin_integration_contract_records,
)
from src.app.hammer_radar.operator.betrayal_true_inverse_outcome_capture_bridge import (
    TRUE_INVERSE_CAPTURE_READY,
    TRUE_INVERSE_CAPTURE_TRACKABLE,
    TRUE_INVERSE_OUTCOME_FOUND,
    build_betrayal_true_inverse_outcome_capture_bridge,
    load_betrayal_true_inverse_outcome_capture_bridge_records,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import (
    DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    DEFAULT_THRESHOLD_REQUIRED_COUNT,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.strategy_evidence_registry import get_entry_mode_manifest

BETRAYAL_RANKING_FEED_PREVIEW_READY = "BETRAYAL_RANKING_FEED_PREVIEW_READY"
BETRAYAL_RANKING_FEED_PREVIEW_REJECTED = "BETRAYAL_RANKING_FEED_PREVIEW_REJECTED"
BETRAYAL_RANKING_FEED_PREVIEW_RECORDED = "BETRAYAL_RANKING_FEED_PREVIEW_RECORDED"
BETRAYAL_RANKING_FEED_PREVIEW_BLOCKED = "BETRAYAL_RANKING_FEED_PREVIEW_BLOCKED"
BETRAYAL_RANKING_FEED_PREVIEW_ERROR = "BETRAYAL_RANKING_FEED_PREVIEW_ERROR"

BETRAYAL_RANKING_FEED_STRUCTURALLY_READY = "BETRAYAL_RANKING_FEED_STRUCTURALLY_READY"
BETRAYAL_RANKING_FEED_WAITING_FOR_TRUE_INVERSE_OUTCOMES = "BETRAYAL_RANKING_FEED_WAITING_FOR_TRUE_INVERSE_OUTCOMES"
BETRAYAL_RANKING_FEED_NEEDS_ENTRY_MODE = "BETRAYAL_RANKING_FEED_NEEDS_ENTRY_MODE"
BETRAYAL_RANKING_FEED_PROMOTION_PATH_KNOWN_BUT_BLOCKED = "BETRAYAL_RANKING_FEED_PROMOTION_PATH_KNOWN_BUT_BLOCKED"
BETRAYAL_TRACK_B_STRUCTURALLY_COMPLETE_WAITING_FOR_DATA = "BETRAYAL_TRACK_B_STRUCTURALLY_COMPLETE_WAITING_FOR_DATA"
BETRAYAL_RANKING_FEED_NOT_ENOUGH_DATA = "BETRAYAL_RANKING_FEED_NOT_ENOUGH_DATA"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

RANKING_FEED_PREVIEW_READY = "RANKING_FEED_PREVIEW_READY"
WAITING_FOR_TRUE_INVERSE_OUTCOMES = "WAITING_FOR_TRUE_INVERSE_OUTCOMES"
NEEDS_ENTRY_MODE = "NEEDS_ENTRY_MODE"
NEEDS_LANE_KEY = "NEEDS_LANE_KEY"
NEEDS_OUTCOME_IDENTITY = "NEEDS_OUTCOME_IDENTITY"
NEEDS_SOURCE_SIGNAL = "NEEDS_SOURCE_SIGNAL"
BLOCKED = "BLOCKED"

EVENT_TYPE = "BETRAYAL_RANKING_FEED_PREVIEW"
LEDGER_FILENAME = "betrayal_ranking_feed_preview.ndjson"
SCHEMA_VERSION = "betrayal_ranking_feed_preview_v1"
CONFIRM_BETRAYAL_RANKING_FEED_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL RANKING FEED PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "ranking_scores_fabricated": False,
    "win_rates_fabricated": False,
    "promotion_eligibility_fabricated": False,
    "ranking_feed_preview_ledger_only": True,
    "normal_ranking_ledger_appended": False,
    "strategy_performance_appended": False,
    "strategy_promotion_status_appended": False,
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
    "betrayal_ranking_feed_preview_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/betrayal_true_inverse_outcome_capture_bridge.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_outcome_tracking_bridge.ndjson",
    "logs/hammer_radar_forward/betrayal_signal_origin_integration_contract.ndjson",
    "logs/hammer_radar_forward/betrayal_gate_ready_lane_packet.ndjson",
    "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_signals.ndjson",
    "logs/hammer_radar_forward/paper_outcomes.ndjson",
    "logs/hammer_radar_forward/strategy_performance.ndjson",
    "logs/hammer_radar_forward/strategy_promotion_status.ndjson",
    "logs/hammer_radar_forward/full_spectrum_lane_scoreboard.ndjson",
    "logs/hammer_radar_forward/lane_outcome_enrichment.ndjson",
    "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_ranking_feed_preview(
    *,
    log_dir: str | Path | None = None,
    record_ranking_preview: bool = False,
    confirm_betrayal_ranking_feed_preview: str | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_betrayal_ranking_feed_preview == CONFIRM_BETRAYAL_RANKING_FEED_PREVIEW_RECORDING_PHRASE
    try:
        capture_bridge = load_latest_betrayal_true_inverse_outcome_capture_bridge(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        outcome_bridge = load_latest_betrayal_paper_outcome_tracking_bridge(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        signal_origin_contract = load_latest_betrayal_signal_origin_integration_contract(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        schema_context = load_existing_strategy_ranking_schema_context(log_dir=resolved_log_dir)
        official_status = _official_tiny_live_status(
            capture_bridge=capture_bridge,
            outcome_bridge=outcome_bridge,
            schema_context=schema_context,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        rows = build_betrayal_ranking_feed_preview_rows(
            true_inverse_capture_bridge=capture_bridge,
            paper_outcome_tracking_bridge=outcome_bridge,
            signal_origin_contract=signal_origin_contract,
            schema_context=schema_context,
        )
        summary = build_betrayal_ranking_feed_summary(rows)
        gap_report = build_betrayal_ranking_gap_report(rows)
        promotion_preview = build_betrayal_promotion_gate_preview(rows)
        track_b = build_track_b_structural_completion_report(
            true_inverse_capture_bridge=capture_bridge,
            paper_outcome_tracking_bridge=outcome_bridge,
            signal_origin_contract=signal_origin_contract,
            ranking_feed_preview_rows=rows,
        )
        recommendations = build_betrayal_ranking_feed_recommendations(
            rows=rows,
            gap_report=gap_report,
            official_tiny_live_status=official_status,
            track_b_structural_completion_report=track_b,
        )
        overall = classify_betrayal_ranking_feed_overall_status(
            rows=rows,
            gap_report=gap_report,
            promotion_gate_preview=promotion_preview,
            track_b_structural_completion_report=track_b,
        )
        status = BETRAYAL_RANKING_FEED_PREVIEW_READY if rows else BETRAYAL_RANKING_FEED_PREVIEW_BLOCKED
        if record_ranking_preview and not confirmation_valid:
            status = BETRAYAL_RANKING_FEED_PREVIEW_REJECTED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "ranking_preview_recorded": False,
            "ranking_preview_record_id": None,
            "record_ranking_preview_requested": bool(record_ranking_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "paper_only": True,
                "live_authorized": False,
                "betrayal_signal_origin_family": "betrayal",
                "ranking_feed_preview_only": True,
                "official_tiny_live_lane": official_tiny_live_lane,
                "official_tiny_live_lane_changed": False,
            },
            "input_summary": {
                "betrayal_true_inverse_capture_bridge_found": bool(capture_bridge.get("true_inverse_capture_preview_rows")),
                "betrayal_outcome_bridge_found": bool(outcome_bridge.get("bridge_preview_rows")),
                "betrayal_signal_origin_contract_found": bool(signal_origin_contract.get("same_flow_readiness_rows")),
                "strategy_ranking_schema_context_found": bool(schema_context.get("context_found")),
                "tiny_live_capture_sync_found": bool(schema_context.get("latest_records_found", {}).get("capture_count_sync_8m_short"))
                or bool(capture_bridge.get("official_tiny_live_status"))
                or bool(outcome_bridge.get("official_tiny_live_status")),
            },
            "official_tiny_live_status": official_status,
            "ranking_feed_preview_rows": rows,
            "ranking_feed_summary": summary,
            "ranking_gap_report": gap_report,
            "promotion_gate_preview": promotion_preview,
            "track_b_structural_completion_report": track_b,
            "ranking_feed_recommendations": recommendations,
            "ranking_overall_status": overall,
            "recommended_next_operator_move": _recommended_next_operator_move(official_status),
            "recommended_next_engineering_move": _recommended_next_engineering_move(overall, track_b, summary),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_ranking_preview and confirmation_valid:
            record = append_betrayal_ranking_feed_preview_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_RANKING_FEED_PREVIEW_RECORDED
            payload["ranking_preview_recorded"] = True
            payload["ranking_preview_record_id"] = record["ranking_preview_record_id"]
            payload["ledger_path"] = str(betrayal_ranking_feed_preview_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_RANKING_FEED_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "ranking_preview_recorded": False,
                "ranking_preview_record_id": None,
                "record_ranking_preview_requested": bool(record_ranking_preview),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {
                    "paper_only": True,
                    "live_authorized": False,
                    "betrayal_signal_origin_family": "betrayal",
                    "ranking_feed_preview_only": True,
                    "official_tiny_live_lane": official_tiny_live_lane,
                    "official_tiny_live_lane_changed": False,
                },
                "input_summary": {},
                "official_tiny_live_status": _empty_official_tiny_live_status(official_tiny_live_lane, threshold_required_count),
                "ranking_feed_preview_rows": [],
                "ranking_feed_summary": build_betrayal_ranking_feed_summary([]),
                "ranking_gap_report": build_betrayal_ranking_gap_report([]),
                "promotion_gate_preview": build_betrayal_promotion_gate_preview([]),
                "track_b_structural_completion_report": build_track_b_structural_completion_report(
                    true_inverse_capture_bridge={},
                    paper_outcome_tracking_bridge={},
                    signal_origin_contract={},
                    ranking_feed_preview_rows=[],
                ),
                "ranking_feed_recommendations": [],
                "ranking_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R238 ranking feed preview error before recording preview.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_true_inverse_outcome_capture_bridge(
    *,
    log_dir: str | Path | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
) -> dict[str, Any]:
    records = load_betrayal_true_inverse_outcome_capture_bridge_records(log_dir=log_dir, limit=1)
    if records:
        return _sanitize(records[0])
    return _sanitize(
        build_betrayal_true_inverse_outcome_capture_bridge(
            log_dir=log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
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


def load_existing_strategy_ranking_schema_context(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved = get_log_dir(log_dir, use_env=True)
    files = {
        "paper_outcomes": "paper_outcomes.ndjson",
        "outcomes": "outcomes.ndjson",
        "strategy_performance": "strategy_performance.ndjson",
        "strategy_promotion_status": "strategy_promotion_status.ndjson",
        "full_spectrum_lane_scoreboard": "full_spectrum_lane_scoreboard.ndjson",
        "lane_outcome_enrichment": "lane_outcome_enrichment.ndjson",
        "capture_count_sync_8m_short": "capture_count_sync_8m_short.ndjson",
        "betrayal_true_paper_outcomes": "betrayal_true_paper_outcomes.ndjson",
        "betrayal_paper_signals": "betrayal_paper_signals.ndjson",
    }
    latest = {}
    found = {}
    counts = {}
    for name, filename in files.items():
        path = resolved / filename
        latest[name] = _latest_record(path)
        found[name] = bool(latest[name])
        counts[name] = _record_count(path)
    valid_modes = [
        str(row.get("entry_mode"))
        for row in get_entry_mode_manifest()
        if isinstance(row, Mapping) and not row.get("blocked_placeholder")
    ]
    return _sanitize(
        {
            "context_found": any(found.values()) or bool(valid_modes),
            "latest_records": latest,
            "latest_records_found": found,
            "record_counts": counts,
            "registry_valid_entry_modes": valid_modes,
            "ranking_feed_target_ledgers": [
                "strategy_performance.ndjson",
                "strategy_promotion_status.ndjson",
                "multi_lane_evidence_rankings.ndjson",
            ],
            "preview_does_not_append_target_ledgers": True,
        }
    )


def build_betrayal_ranking_preview_id(row: Mapping[str, Any]) -> str:
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
            "capture_id",
        )
    )
    return "betrayal_ranking_preview_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def normalize_true_inverse_capture_row_for_ranking_preview(
    row: Mapping[str, Any],
    *,
    schema_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = dict(row)
    true_inverse_found = bool(base.get("true_inverse_outcome_found"))
    true_inverse_pending = bool(base.get("true_inverse_outcome_pending") or base.get("result_pending"))
    ranking_evidence_available = true_inverse_found and _has_existing_ranking_metrics(base)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "ranking_preview_id": build_betrayal_ranking_preview_id(base),
        "ranking_feed_status": None,
        "signal_origin_family": base.get("signal_origin_family"),
        "signal_origin_type": base.get("signal_origin_type"),
        "signal_origin_variant": base.get("signal_origin_variant"),
        "symbol": _string_or_none(base.get("symbol")),
        "timeframe": _string_or_none(base.get("timeframe")),
        "direction": _string_or_none(base.get("direction") or base.get("original_direction")),
        "inverse_direction": _string_or_none(base.get("inverse_direction")),
        "entry_mode": _string_or_none(base.get("entry_mode")),
        "lane_key": _string_or_none(base.get("lane_key")),
        "signal_id": _string_or_none(base.get("signal_id")),
        "source_signal_id": _string_or_none(base.get("source_signal_id")),
        "source_identity": _string_or_none(base.get("source_identity")),
        "paper_outcome_tracking_identity": _string_or_none(base.get("paper_outcome_tracking_identity")),
        "true_inverse_capture_id": _string_or_none(base.get("capture_id") or base.get("true_inverse_capture_id")),
        "outcome_window_spec": list(base.get("outcome_window_spec") or []),
        "capture_status": base.get("capture_status"),
        "true_inverse_outcome_found": true_inverse_found,
        "true_inverse_outcome_pending": true_inverse_pending,
        "ranking_projection_ready": bool(base.get("ranking_projection_ready")),
        "ranking_evidence_available": ranking_evidence_available,
        "ranking_score": _existing_metric(base, "ranking_score") if ranking_evidence_available else None,
        "win_rate_pct": _existing_metric(base, "win_rate_pct") if ranking_evidence_available else None,
        "sample_size": _existing_metric(base, "sample_size") if ranking_evidence_available else None,
        "promotion_gate_preview": False,
        "promotion_review_ready": False,
        "live_ready_today": False,
        "live_authorized": False,
        "promotion_allowed": False,
    }
    status, blockers = classify_betrayal_ranking_feed_status(normalized, schema_context=schema_context or {})
    normalized["ranking_feed_status"] = status
    normalized["promotion_gate_preview"] = status == RANKING_FEED_PREVIEW_READY
    normalized["blockers"] = blockers
    normalized["why"] = _ranking_row_why(status, blockers, normalized)
    return _sanitize(normalized)


def classify_betrayal_ranking_feed_status(
    row: Mapping[str, Any],
    *,
    schema_context: Mapping[str, Any] | None = None,
) -> tuple[str, list[str]]:
    valid_modes = set((schema_context or {}).get("registry_valid_entry_modes") or [])
    blockers = []
    if row.get("signal_origin_family") != "betrayal":
        blockers.append("not_betrayal_signal_origin_family")
    if row.get("capture_status") not in {TRUE_INVERSE_CAPTURE_READY, TRUE_INVERSE_CAPTURE_TRACKABLE, TRUE_INVERSE_OUTCOME_FOUND}:
        blockers.append("capture_not_ready_or_trackable")
    if row.get("ranking_projection_ready") is not True:
        blockers.append("ranking_projection_not_ready")
    if not row.get("symbol"):
        blockers.append("missing_symbol")
    if not row.get("timeframe"):
        blockers.append("missing_timeframe")
    if not row.get("direction") or not row.get("inverse_direction"):
        blockers.append("missing_direction")
    entry_mode = str(row.get("entry_mode") or "")
    if not entry_mode or entry_mode in {"entry_unknown", "unknown", "None"} or (valid_modes and entry_mode not in valid_modes):
        blockers.append("missing_entry_mode")
    if not row.get("lane_key") or str(row.get("lane_key")).endswith("|entry_unknown"):
        blockers.append("missing_lane_key")
    if not row.get("signal_id") or not row.get("source_signal_id") or not row.get("source_identity"):
        blockers.append("missing_source_signal")
    if not row.get("paper_outcome_tracking_identity") or not row.get("true_inverse_capture_id") or not row.get("outcome_window_spec"):
        blockers.append("missing_outcome_identity")
    if row.get("live_authorized") is not False:
        blockers.append("live_authorized_not_false")
    if row.get("promotion_allowed") is not False:
        blockers.append("promotion_allowed_not_false")
    if row.get("true_inverse_outcome_found") is False:
        blockers.append("true_inverse_outcome_pending")

    hard = set(blockers) - {"true_inverse_outcome_pending"}
    if "missing_entry_mode" in hard:
        status = NEEDS_ENTRY_MODE
    elif "missing_lane_key" in hard:
        status = NEEDS_LANE_KEY
    elif "missing_outcome_identity" in hard:
        status = NEEDS_OUTCOME_IDENTITY
    elif "missing_source_signal" in hard:
        status = NEEDS_SOURCE_SIGNAL
    elif hard:
        status = BLOCKED
    else:
        status = RANKING_FEED_PREVIEW_READY
    blockers.extend(["risk_contract_missing", "operator_approval_missing", "global_live_gate_closed"])
    return status, _dedupe(blockers)


def build_betrayal_ranking_feed_preview_rows(
    *,
    true_inverse_capture_bridge: Mapping[str, Any],
    paper_outcome_tracking_bridge: Mapping[str, Any] | None = None,
    signal_origin_contract: Mapping[str, Any] | None = None,
    schema_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del paper_outcome_tracking_bridge, signal_origin_contract
    rows = []
    for row in true_inverse_capture_bridge.get("true_inverse_capture_preview_rows") or []:
        if not isinstance(row, Mapping) or row.get("signal_origin_family") != "betrayal":
            continue
        rows.append(normalize_true_inverse_capture_row_for_ranking_preview(row, schema_context=schema_context or {}))
    rows.sort(
        key=lambda row: (
            row.get("ranking_feed_status") != RANKING_FEED_PREVIEW_READY,
            str(row.get("lane_key") or ""),
            str(row.get("signal_id") or ""),
            str(row.get("ranking_preview_id") or ""),
        )
    )
    return _sanitize(rows)


def build_betrayal_ranking_feed_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "rows_reviewed": len(rows),
        "ranking_feed_preview_ready_rows": sum(1 for row in rows if row.get("ranking_feed_status") == RANKING_FEED_PREVIEW_READY),
        "waiting_for_true_inverse_outcome_rows": sum(1 for row in rows if row.get("true_inverse_outcome_pending")),
        "ranking_evidence_available_rows": sum(1 for row in rows if row.get("ranking_evidence_available")),
        "promotion_gate_preview_rows": sum(1 for row in rows if row.get("promotion_gate_preview")),
        "promotion_review_ready_rows": 0,
        "live_ready_today_rows": 0,
        "blocked_rows": sum(1 for row in rows if row.get("ranking_feed_status") != RANKING_FEED_PREVIEW_READY),
    }


def build_betrayal_ranking_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "missing_entry_mode_rows": _count_blocker(rows, "missing_entry_mode"),
        "missing_lane_key_rows": _count_blocker(rows, "missing_lane_key"),
        "missing_source_signal_rows": _count_blocker(rows, "missing_source_signal"),
        "missing_outcome_identity_rows": _count_blocker(rows, "missing_outcome_identity"),
        "waiting_for_true_inverse_outcome_rows": _count_blocker(rows, "true_inverse_outcome_pending"),
        "hard_live_blockers": ["risk_contract_missing", "operator_approval_missing", "global_live_gate_closed"],
    }


def build_betrayal_promotion_gate_preview(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ready_rows = [row for row in rows if row.get("ranking_feed_status") == RANKING_FEED_PREVIEW_READY]
    evidence_rows = [row for row in ready_rows if row.get("ranking_evidence_available")]
    return {
        "promotion_path_known": True,
        "promotion_path_blocked": True,
        "can_promote_today": False,
        "can_review_after_outcomes": bool(ready_rows),
        "requirements_remaining": [
            "true inverse outcomes must be captured",
            "ranking/performance evidence must be computed",
            "sample threshold must be met",
            "promotion gate review later",
            "risk contract later",
            "operator approval later",
            "global live gate later",
        ],
        "preview_ready_rows": len(ready_rows),
        "ranking_evidence_available_rows": len(evidence_rows),
    }


def build_track_b_structural_completion_report(
    *,
    true_inverse_capture_bridge: Mapping[str, Any],
    paper_outcome_tracking_bridge: Mapping[str, Any],
    signal_origin_contract: Mapping[str, Any],
    ranking_feed_preview_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    same_flow_ready = bool(signal_origin_contract.get("same_flow_readiness_rows"))
    outcome_bridge_ready = bool(paper_outcome_tracking_bridge.get("bridge_preview_rows"))
    capture_ready = bool(true_inverse_capture_bridge.get("true_inverse_capture_preview_rows"))
    ranking_preview_ready = any(row.get("ranking_feed_status") == RANKING_FEED_PREVIEW_READY for row in ranking_feed_preview_rows)
    remaining_architecture_gaps = []
    if not same_flow_ready:
        remaining_architecture_gaps.append("same_flow_contract_missing")
    if not outcome_bridge_ready:
        remaining_architecture_gaps.append("paper_outcome_bridge_missing")
    if not capture_ready:
        remaining_architecture_gaps.append("true_inverse_capture_bridge_missing")
    if not ranking_preview_ready:
        remaining_architecture_gaps.append("ranking_feed_preview_missing")
    remaining_data_gaps = []
    if any(row.get("true_inverse_outcome_pending") for row in ranking_feed_preview_rows):
        remaining_data_gaps.append("true_inverse_outcomes_pending")
    if not any(row.get("ranking_evidence_available") for row in ranking_feed_preview_rows):
        remaining_data_gaps.append("ranking_performance_evidence_missing")
    structurally_complete = same_flow_ready and outcome_bridge_ready and capture_ready and ranking_preview_ready
    return {
        "same_flow_contract_ready": same_flow_ready,
        "paper_outcome_bridge_ready": outcome_bridge_ready,
        "true_inverse_capture_bridge_ready": capture_ready,
        "ranking_feed_preview_ready": ranking_preview_ready,
        "structurally_complete_for_now": structurally_complete,
        "waiting_for_data_not_architecture": structurally_complete and bool(remaining_data_gaps),
        "remaining_architecture_gaps": remaining_architecture_gaps,
        "remaining_data_gaps": remaining_data_gaps,
    }


def build_betrayal_ranking_feed_recommendations(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
    official_tiny_live_status: Mapping[str, Any],
    track_b_structural_completion_report: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "RUN_R228_IF_10_OF_10" if official_tiny_live_status.get("threshold_met") else "WAIT_FOR_10_OF_10",
            "future_phase": "R228",
            "why": "The official BTCUSDT 8m short tiny-live path remains separate from betrayal ranking preview.",
        }
    ]
    if gap_report.get("waiting_for_true_inverse_outcome_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "WAIT_FOR_TRUE_INVERSE_OUTCOMES",
                "future_phase": "R239",
                "why": "Betrayal ranking feed shape is prepared, but ranking evidence must come from real true inverse outcomes.",
            }
        )
    if track_b_structural_completion_report.get("structurally_complete_for_now"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "RUN_LIGHTWEIGHT_STATUS_ONLY",
                "future_phase": "R239",
                "why": "Track B is structurally complete for now and should wait without promotion or config writes.",
            }
        )
    if not rows or gap_report.get("missing_entry_mode_rows") or gap_report.get("missing_lane_key_rows"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "CONTINUE_ENTRY_MODE_AND_LANE_KEY_ADOPTION",
                "future_phase": "R239",
                "why": "Rows without registry-valid entry_mode or lane_key cannot become ranking feed preview ready.",
            }
        )
    return recommendations


def classify_betrayal_ranking_feed_overall_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
    promotion_gate_preview: Mapping[str, Any],
    track_b_structural_completion_report: Mapping[str, Any],
) -> str:
    if not rows:
        return BETRAYAL_RANKING_FEED_NOT_ENOUGH_DATA
    if track_b_structural_completion_report.get("structurally_complete_for_now") and track_b_structural_completion_report.get(
        "waiting_for_data_not_architecture"
    ):
        return BETRAYAL_TRACK_B_STRUCTURALLY_COMPLETE_WAITING_FOR_DATA
    if gap_report.get("missing_entry_mode_rows") or gap_report.get("missing_lane_key_rows"):
        return BETRAYAL_RANKING_FEED_NEEDS_ENTRY_MODE
    if gap_report.get("waiting_for_true_inverse_outcome_rows"):
        return BETRAYAL_RANKING_FEED_WAITING_FOR_TRUE_INVERSE_OUTCOMES
    if promotion_gate_preview.get("promotion_path_blocked"):
        return BETRAYAL_RANKING_FEED_PROMOTION_PATH_KNOWN_BUT_BLOCKED
    if any(row.get("ranking_feed_status") == RANKING_FEED_PREVIEW_READY for row in rows):
        return BETRAYAL_RANKING_FEED_STRUCTURALLY_READY
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_betrayal_ranking_feed_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_ranking_feed_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "ranking_preview_record_id": str(record.get("ranking_preview_record_id") or f"r238_betrayal_ranking_feed_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_RANKING_FEED_PREVIEW_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_ranking_preview_requested": bool(record.get("record_ranking_preview_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "official_tiny_live_status": dict(record.get("official_tiny_live_status") or {}),
            "ranking_feed_preview_rows": list(record.get("ranking_feed_preview_rows") or []),
            "ranking_feed_summary": dict(record.get("ranking_feed_summary") or {}),
            "ranking_gap_report": dict(record.get("ranking_gap_report") or {}),
            "promotion_gate_preview": dict(record.get("promotion_gate_preview") or {}),
            "track_b_structural_completion_report": dict(record.get("track_b_structural_completion_report") or {}),
            "ranking_feed_recommendations": list(record.get("ranking_feed_recommendations") or []),
            "ranking_overall_status": record.get("ranking_overall_status"),
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


def load_betrayal_ranking_feed_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_ranking_feed_preview_records_path(get_log_dir(log_dir, use_env=True))
    return _read_records(path, limit=limit)


def summarize_betrayal_ranking_feed_preview_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "ranking_overall_status_counts": dict(
            sorted(Counter(str(record.get("ranking_overall_status") or "UNKNOWN") for record in records).items())
        ),
        "latest_ranking_preview_record_id": latest.get("ranking_preview_record_id") if isinstance(latest, Mapping) else None,
        "latest_ranking_overall_status": latest.get("ranking_overall_status") if isinstance(latest, Mapping) else None,
        "safety": dict(SAFETY),
    }


def betrayal_ranking_feed_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_ranking_feed_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _official_tiny_live_status(
    *,
    capture_bridge: Mapping[str, Any],
    outcome_bridge: Mapping[str, Any],
    schema_context: Mapping[str, Any],
    official_tiny_live_lane: str,
    threshold_required_count: int,
) -> dict[str, Any]:
    from_capture = dict(capture_bridge.get("official_tiny_live_status") or {})
    from_outcome = dict(outcome_bridge.get("official_tiny_live_status") or {})
    from_sync = dict((schema_context.get("latest_records") or {}).get("capture_count_sync_8m_short") or {})
    capture = dict(from_sync.get("capture_count") or {})
    fresh = int(from_capture.get("fresh_capture_count") or from_outcome.get("fresh_capture_count") or capture.get("fresh_capture_count") or 0)
    required = int(
        from_capture.get("required_fresh_capture_count")
        or from_outcome.get("required_fresh_capture_count")
        or capture.get("required_fresh_capture_count")
        or threshold_required_count
    )
    threshold_met = bool(
        from_capture.get("threshold_met") or from_outcome.get("threshold_met") or capture.get("threshold_met") or fresh >= required
    )
    return {
        "lane_key": str(from_capture.get("lane_key") or from_outcome.get("lane_key") or official_tiny_live_lane),
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


def _recommended_next_operator_move(official_tiny_live_status: Mapping[str, Any]) -> str:
    if official_tiny_live_status.get("threshold_met"):
        return "RUN_R228_TINY_LIVE_10_OF_10_READY_PACKET"
    return "WAIT_FOR_10_OF_10"


def _recommended_next_engineering_move(
    overall_status: str,
    track_b_structural_completion_report: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> str:
    if track_b_structural_completion_report.get("structurally_complete_for_now") and summary.get(
        "waiting_for_true_inverse_outcome_rows"
    ):
        return "Create R239 lightweight Track B wait/status check; do not feed ranking until true inverse outcomes exist."
    if overall_status == BETRAYAL_RANKING_FEED_NEEDS_ENTRY_MODE:
        return "Continue entry_mode/lane_key adoption for blocked betrayal rows; keep R238 preview-only."
    return "Keep betrayal ranking feed preview-only and wait for true inverse outcome data."


def _ranking_row_why(status: str, blockers: Sequence[str], row: Mapping[str, Any]) -> str:
    if status == RANKING_FEED_PREVIEW_READY and row.get("true_inverse_outcome_pending"):
        return "Betrayal row has ranking feed structure, but true inverse outcome evidence is still pending."
    if status == RANKING_FEED_PREVIEW_READY:
        return "Betrayal row has ranking feed structure; promotion and live remain blocked."
    if status == NEEDS_ENTRY_MODE:
        return "Betrayal row needs registry-valid entry_mode before ranking feed preview."
    if status == NEEDS_LANE_KEY:
        return "Betrayal row needs lane_key before ranking feed preview."
    if status == NEEDS_SOURCE_SIGNAL:
        return "Betrayal row needs signal_id, source_signal_id, and source_identity."
    if status == NEEDS_OUTCOME_IDENTITY:
        return "Betrayal row needs outcome identity and true inverse capture identity."
    if status == WAITING_FOR_TRUE_INVERSE_OUTCOMES:
        return "Betrayal row is waiting for true inverse outcomes."
    return "Betrayal ranking feed preview remains blocked: " + ", ".join(_dedupe(blockers)[:4])


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


def _has_existing_ranking_metrics(row: Mapping[str, Any]) -> bool:
    return any(_existing_metric(row, key) is not None for key in ("ranking_score", "win_rate_pct", "sample_size"))


def _existing_metric(row: Mapping[str, Any], key: str) -> Any:
    if row.get(key) is not None:
        return row.get(key)
    ref = row.get("true_inverse_outcome_reference")
    if isinstance(ref, Mapping):
        return ref.get(key)
    return None


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
