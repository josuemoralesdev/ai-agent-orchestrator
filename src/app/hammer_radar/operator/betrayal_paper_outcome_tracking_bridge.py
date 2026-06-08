"""R236 betrayal paper outcome tracking bridge.

Preview-only bridge from R235 betrayal same-flow rows into paper outcome
tracking identities. This module is audit/diagnostic wiring only: it never
mutates paper outcomes, configs, lane controls, risk contracts, or live state.
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

BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_READY = "BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_READY"
BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_REJECTED = "BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_REJECTED"
BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_RECORDED = "BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_RECORDED"
BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_BLOCKED = "BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_BLOCKED"
BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_ERROR = "BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_ERROR"

BETRAYAL_OUTCOME_BRIDGE_READY = "BETRAYAL_OUTCOME_BRIDGE_READY"
BETRAYAL_OUTCOME_BRIDGE_PARTIALLY_READY = "BETRAYAL_OUTCOME_BRIDGE_PARTIALLY_READY"
BETRAYAL_OUTCOME_BRIDGE_NEEDS_ENTRY_MODE = "BETRAYAL_OUTCOME_BRIDGE_NEEDS_ENTRY_MODE"
BETRAYAL_OUTCOME_BRIDGE_NEEDS_TRUE_INVERSE_OUTCOMES = "BETRAYAL_OUTCOME_BRIDGE_NEEDS_TRUE_INVERSE_OUTCOMES"
BETRAYAL_OUTCOME_BRIDGE_PROMOTION_PATH_KNOWN_BUT_BLOCKED = "BETRAYAL_OUTCOME_BRIDGE_PROMOTION_PATH_KNOWN_BUT_BLOCKED"
BETRAYAL_OUTCOME_BRIDGE_NOT_ENOUGH_DATA = "BETRAYAL_OUTCOME_BRIDGE_NOT_ENOUGH_DATA"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

BRIDGE_READY = "BRIDGE_READY"
OUTCOME_TRACKING_READY = "OUTCOME_TRACKING_READY"
RANKING_FEED_READY = "RANKING_FEED_READY"
PROMOTION_GATE_PREVIEW_READY = "PROMOTION_GATE_PREVIEW_READY"
NEEDS_ENTRY_MODE = "NEEDS_ENTRY_MODE"
NEEDS_LANE_KEY = "NEEDS_LANE_KEY"
NEEDS_SIGNAL_ID = "NEEDS_SIGNAL_ID"
NEEDS_SOURCE_IDENTITY = "NEEDS_SOURCE_IDENTITY"
NEEDS_OUTCOME_IDENTITY = "NEEDS_OUTCOME_IDENTITY"
NEEDS_TRUE_INVERSE_OUTCOME = "NEEDS_TRUE_INVERSE_OUTCOME"
BLOCKED = "BLOCKED"

EVENT_TYPE = "BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE"
LEDGER_FILENAME = "betrayal_paper_outcome_tracking_bridge.ndjson"
SCHEMA_VERSION = "betrayal_paper_outcome_bridge_preview_v1"
CONFIRM_BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL PAPER OUTCOME TRACKING BRIDGE RECORDING ONLY; "
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
    "bridge_preview_ledger_only": True,
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
    "betrayal_outcome_bridge_preview_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
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


def build_betrayal_paper_outcome_tracking_bridge(
    *,
    log_dir: str | Path | None = None,
    record_bridge: bool = False,
    confirm_betrayal_paper_outcome_tracking_bridge: str | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_paper_outcome_tracking_bridge
        == CONFIRM_BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_RECORDING_PHRASE
    )
    try:
        contract = load_latest_betrayal_signal_origin_integration_contract(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        gate_packet = load_latest_betrayal_gate_ready_lane_packet(
            log_dir=resolved_log_dir,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        schema_context = load_existing_paper_outcome_schema_context(log_dir=resolved_log_dir)
        rows = build_betrayal_outcome_bridge_preview_rows(
            signal_origin_contract=contract,
            gate_ready_packet=gate_packet,
            schema_context=schema_context,
        )
        summary = build_betrayal_outcome_bridge_summary(rows)
        gap_report = build_betrayal_outcome_bridge_gap_report(rows)
        promotion_path = build_betrayal_outcome_bridge_promotion_path(rows)
        recommendations = build_betrayal_outcome_bridge_recommendations(
            rows=rows,
            gap_report=gap_report,
            official_tiny_live_status=gate_packet.get("official_tiny_live_status") or {},
        )
        overall = classify_betrayal_paper_outcome_bridge_overall_status(
            rows=rows,
            gap_report=gap_report,
            promotion_path=promotion_path,
        )
        status = BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_READY if rows else BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_BLOCKED
        if record_bridge and not confirmation_valid:
            status = BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_REJECTED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "bridge_recorded": False,
            "bridge_record_id": None,
            "record_bridge_requested": bool(record_bridge),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "paper_only": True,
                "live_authorized": False,
                "betrayal_signal_origin_family": "betrayal",
                "paper_outcome_bridge_preview_only": True,
                "official_tiny_live_lane": official_tiny_live_lane,
                "official_tiny_live_lane_changed": False,
            },
            "input_summary": {
                "betrayal_signal_origin_contract_found": bool(contract.get("same_flow_readiness_rows")),
                "betrayal_gate_ready_packet_found": bool(gate_packet.get("betrayal_candidate_lane_registry")),
                "paper_outcome_schema_context_found": bool(schema_context.get("context_found")),
                "tiny_live_capture_sync_found": bool(schema_context.get("latest_records_found", {}).get("capture_count_sync_8m_short"))
                or bool(gate_packet.get("official_tiny_live_status")),
            },
            "official_tiny_live_status": _official_tiny_live_status(
                gate_packet=gate_packet,
                schema_context=schema_context,
                official_tiny_live_lane=official_tiny_live_lane,
                threshold_required_count=threshold_required_count,
            ),
            "bridge_preview_rows": rows,
            "bridge_summary": summary,
            "bridge_gap_report": gap_report,
            "bridge_promotion_path": promotion_path,
            "bridge_recommendations": recommendations,
            "bridge_overall_status": overall,
            "recommended_next_operator_move": _recommended_next_operator_move(
                gate_packet.get("official_tiny_live_status") or {},
                schema_context=schema_context,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(overall, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_bridge and confirmation_valid:
            record = append_betrayal_paper_outcome_tracking_bridge_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_RECORDED
            payload["bridge_recorded"] = True
            payload["bridge_record_id"] = record["bridge_record_id"]
            payload["ledger_path"] = str(betrayal_paper_outcome_tracking_bridge_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_ERROR,
                "generated_at": generated_at.isoformat(),
                "bridge_recorded": False,
                "bridge_record_id": None,
                "record_bridge_requested": bool(record_bridge),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {
                    "paper_only": True,
                    "live_authorized": False,
                    "betrayal_signal_origin_family": "betrayal",
                    "paper_outcome_bridge_preview_only": True,
                    "official_tiny_live_lane": official_tiny_live_lane,
                    "official_tiny_live_lane_changed": False,
                },
                "input_summary": {},
                "official_tiny_live_status": _empty_official_tiny_live_status(official_tiny_live_lane, threshold_required_count),
                "bridge_preview_rows": [],
                "bridge_summary": build_betrayal_outcome_bridge_summary([]),
                "bridge_gap_report": build_betrayal_outcome_bridge_gap_report([]),
                "bridge_promotion_path": build_betrayal_outcome_bridge_promotion_path([]),
                "bridge_recommendations": [],
                "bridge_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R236 bridge error before recording bridge previews.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
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


def load_existing_paper_outcome_schema_context(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved = get_log_dir(log_dir, use_env=True)
    files = {
        "paper_outcomes": "paper_outcomes.ndjson",
        "outcomes": "outcomes.ndjson",
        "strategy_performance": "strategy_performance.ndjson",
        "strategy_promotion_status": "strategy_promotion_status.ndjson",
        "betrayal_true_paper_outcomes": "betrayal_true_paper_outcomes.ndjson",
        "betrayal_paper_signals": "betrayal_paper_signals.ndjson",
        "capture_count_sync_8m_short": "capture_count_sync_8m_short.ndjson",
    }
    latest = {name: _latest_record(resolved / filename) for name, filename in files.items()}
    counts = {name: _record_count(resolved / filename) for name, filename in files.items()}
    entry_modes = [
        row["entry_mode"]
        for row in get_entry_mode_manifest()
        if isinstance(row, Mapping) and row.get("entry_mode") and not row.get("blocked_placeholder")
    ]
    return _sanitize(
        {
            "context_found": any(bool(record) for record in latest.values()),
            "latest_records_found": {name: bool(record) for name, record in latest.items()},
            "record_counts": counts,
            "latest_records": latest,
            "registry_valid_entry_modes": entry_modes,
            "paper_outcome_join_fields": [
                "symbol",
                "timeframe",
                "direction",
                "entry_mode",
                "lane_key",
                "signal_id",
                "source_signal_id",
                "source_identity",
                "paper_outcome_tracking_identity",
            ],
            "outcome_window_convention": [1, 3, 5, 10, 21, 34, 55],
        }
    )


def build_betrayal_paper_outcome_bridge_id(row: Mapping[str, Any]) -> str:
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
    return "betrayal_outcome_bridge_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def build_betrayal_paper_outcome_tracking_identity(row: Mapping[str, Any]) -> str | None:
    existing = _string_or_none(row.get("paper_outcome_tracking_identity"))
    if existing:
        return existing
    required = [
        row.get("signal_origin_family"),
        row.get("lane_key"),
        row.get("signal_id"),
        row.get("source_signal_id"),
        row.get("source_identity"),
    ]
    if not all(_string_or_none(value) for value in required):
        return None
    material = "|".join(str(value) for value in required)
    return "betrayal_paper_outcome_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def normalize_betrayal_same_flow_row_for_outcome_bridge(
    row: Mapping[str, Any],
    *,
    schema_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = dict(row)
    tracking_identity = _string_or_none(base.get("paper_outcome_tracking_identity"))
    outcome_window_spec = base.get("outcome_window_spec")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "signal_origin_family": base.get("signal_origin_family"),
        "signal_origin_type": base.get("signal_origin_type"),
        "signal_origin_variant": base.get("signal_origin_variant"),
        "symbol": _string_or_none(base.get("symbol")),
        "timeframe": _string_or_none(base.get("timeframe")),
        "direction": _string_or_none(base.get("direction")),
        "entry_mode": _string_or_none(base.get("entry_mode")),
        "lane_key": _string_or_none(base.get("lane_key")),
        "signal_id": _string_or_none(base.get("signal_id")),
        "source_signal_id": _string_or_none(base.get("source_signal_id")),
        "source_identity": _string_or_none(base.get("source_identity")),
        "paper_outcome_tracking_identity": tracking_identity,
        "outcome_window_spec": _normalize_outcome_window(outcome_window_spec),
        "paper_signal_ready": bool(base.get("paper_signal_ready")),
        "paper_outcome_ready": bool(base.get("paper_outcome_ready")),
        "source_known_outcome_count": int(base.get("known_outcome_count") or 0),
        "paper_only": bool(base.get("paper_only")),
        "live_ready_today": False,
        "live_authorized": False,
        "promotion_allowed": False,
    }
    normalized["bridge_id"] = build_betrayal_paper_outcome_bridge_id(normalized)
    status, blockers = classify_betrayal_outcome_bridge_status(normalized, schema_context=schema_context or {})
    outcome_tracking_ready = status in {
        BRIDGE_READY,
        OUTCOME_TRACKING_READY,
        RANKING_FEED_READY,
        PROMOTION_GATE_PREVIEW_READY,
    }
    ranking_feed_ready = outcome_tracking_ready and bool(normalized.get("lane_key"))
    promotion_gate_preview = ranking_feed_ready
    normalized.update(
        {
            "bridge_status": status,
            "outcome_tracking_ready": bool(outcome_tracking_ready),
            "ranking_feed_ready": bool(ranking_feed_ready),
            "promotion_gate_preview": bool(promotion_gate_preview),
            "true_inverse_outcome_required": True,
            "live_ready_today": False,
            "live_authorized": False,
            "promotion_allowed": False,
            "blockers": blockers,
            "why": _bridge_row_why(status, blockers),
        }
    )
    return _sanitize(normalized)


def classify_betrayal_outcome_bridge_status(
    row: Mapping[str, Any],
    *,
    schema_context: Mapping[str, Any] | None = None,
) -> tuple[str, list[str]]:
    valid_modes = set((schema_context or {}).get("registry_valid_entry_modes") or [])
    blockers = []
    if row.get("signal_origin_family") != "betrayal":
        blockers.append("not_betrayal_signal_origin_family")
    if row.get("paper_signal_ready") is not True:
        blockers.append("paper_signal_not_ready")
    if row.get("paper_outcome_ready") is not True:
        blockers.append("paper_outcome_not_ready")
    if not row.get("symbol"):
        blockers.append("missing_symbol")
    if not row.get("timeframe"):
        blockers.append("missing_timeframe")
    if not row.get("direction"):
        blockers.append("missing_direction")
    entry_mode = str(row.get("entry_mode") or "")
    if not entry_mode or entry_mode in {"entry_unknown", "unknown", "None"} or (valid_modes and entry_mode not in valid_modes):
        blockers.append("missing_entry_mode")
    if not row.get("lane_key") or str(row.get("lane_key")).endswith("|entry_unknown"):
        blockers.append("missing_lane_key")
    if not row.get("signal_id") or not row.get("source_signal_id"):
        blockers.append("missing_signal_id")
    if not row.get("source_identity") or row.get("source_identity") == "unknown":
        blockers.append("missing_source_identity")
    if not row.get("paper_outcome_tracking_identity") or not row.get("outcome_window_spec"):
        blockers.append("missing_outcome_identity")
    if row.get("paper_only") is not True:
        blockers.append("paper_only_not_true")
    if row.get("live_authorized") is not False:
        blockers.append("live_authorized_not_false")
    if row.get("promotion_allowed") is not False:
        blockers.append("promotion_allowed_not_false")

    hard_blockers = set(blockers)
    if "missing_entry_mode" in hard_blockers:
        status = NEEDS_ENTRY_MODE
    elif "missing_lane_key" in hard_blockers:
        status = NEEDS_LANE_KEY
    elif "missing_signal_id" in hard_blockers:
        status = NEEDS_SIGNAL_ID
    elif "missing_source_identity" in hard_blockers:
        status = NEEDS_SOURCE_IDENTITY
    elif "missing_outcome_identity" in hard_blockers:
        status = NEEDS_OUTCOME_IDENTITY
    elif any(blocker in hard_blockers for blocker in ("not_betrayal_signal_origin_family", "paper_signal_not_ready", "paper_outcome_not_ready")):
        status = BLOCKED
    else:
        status = BRIDGE_READY

    if int(row.get("source_known_outcome_count") or 0) <= 0:
        blockers.append("true_inverse_outcome_required")
    blockers.extend(["risk_contract_missing", "operator_approval_missing", "global_live_gate_closed"])
    return status, _dedupe(blockers)


def build_betrayal_outcome_bridge_preview_rows(
    *,
    signal_origin_contract: Mapping[str, Any],
    gate_ready_packet: Mapping[str, Any] | None = None,
    schema_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del gate_ready_packet
    rows = []
    for row in signal_origin_contract.get("same_flow_readiness_rows") or []:
        if not isinstance(row, Mapping) or row.get("signal_origin_family") != "betrayal":
            continue
        rows.append(normalize_betrayal_same_flow_row_for_outcome_bridge(row, schema_context=schema_context or {}))
    rows.sort(key=lambda row: (row.get("bridge_status") != BRIDGE_READY, str(row.get("lane_key") or ""), str(row.get("signal_id") or "")))
    return _sanitize(rows)


def build_betrayal_outcome_bridge_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "rows_reviewed": len(rows),
        "bridge_ready_rows": sum(1 for row in rows if row.get("bridge_status") == BRIDGE_READY),
        "outcome_tracking_ready_rows": sum(1 for row in rows if row.get("outcome_tracking_ready")),
        "ranking_feed_ready_rows": sum(1 for row in rows if row.get("ranking_feed_ready")),
        "promotion_gate_preview_rows": sum(1 for row in rows if row.get("promotion_gate_preview")),
        "live_ready_today_rows": 0,
        "blocked_rows": sum(1 for row in rows if row.get("blockers")),
    }


def build_betrayal_outcome_bridge_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "missing_entry_mode_rows": _count_blocker(rows, "missing_entry_mode"),
        "missing_lane_key_rows": _count_blocker(rows, "missing_lane_key"),
        "missing_signal_id_rows": _count_blocker(rows, "missing_signal_id"),
        "missing_source_identity_rows": _count_blocker(rows, "missing_source_identity"),
        "missing_outcome_identity_rows": _count_blocker(rows, "missing_outcome_identity"),
        "needs_true_inverse_outcome_rows": _count_blocker(rows, "true_inverse_outcome_required"),
        "hard_live_blockers": ["risk_contract_missing", "operator_approval_missing", "global_live_gate_closed"],
    }


def build_betrayal_outcome_bridge_promotion_path(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    bridge_ready = [row for row in rows if row.get("bridge_status") == BRIDGE_READY]
    return {
        "can_feed_paper_outcome_tracking": bool(bridge_ready),
        "can_feed_ranking_later": any(row.get("ranking_feed_ready") for row in rows),
        "promotion_path_known": True,
        "promotion_path_blocked": True,
        "risk_contract_ready_later_rows": sum(1 for row in rows if row.get("promotion_gate_preview")),
        "live_ready_today": False,
        "requirements_remaining": _dedupe(
            [
                "collect true inverse/paper outcomes for betrayal identities",
                "feed paper outcomes into ranking/performance later",
                "promotion gate review later",
                "risk contract later",
                "operator approval later",
                "global live gate later",
            ]
        ),
    }


def build_betrayal_outcome_bridge_recommendations(
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
    if any(row.get("bridge_status") == BRIDGE_READY for row in rows):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "ADOPT_BETRAYAL_OUTCOME_BRIDGE",
                "future_phase": "R236",
                "why": "Bridge-ready betrayal rows can be tracked as paper-only outcome identities without promotion or live authority.",
            }
        )
    if gap_report.get("needs_true_inverse_outcome_rows"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "COLLECT_TRUE_INVERSE_OUTCOMES",
                "future_phase": "R237",
                "why": "Betrayal ranking and promotion review require true inverse/paper outcome evidence after this bridge.",
            }
        )
    if gap_report.get("missing_entry_mode_rows") or gap_report.get("missing_lane_key_rows"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "ADOPT_R230_ENTRY_MODE_CONTRACT",
                "future_phase": "R237",
                "why": "Rows missing registry-valid entry_mode or lane_key cannot enter paper outcome tracking.",
            }
        )
    return recommendations


def classify_betrayal_paper_outcome_bridge_overall_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
    promotion_path: Mapping[str, Any],
) -> str:
    if not rows:
        return BETRAYAL_OUTCOME_BRIDGE_NOT_ENOUGH_DATA
    if gap_report.get("missing_entry_mode_rows") or gap_report.get("missing_lane_key_rows"):
        return BETRAYAL_OUTCOME_BRIDGE_NEEDS_ENTRY_MODE
    if gap_report.get("needs_true_inverse_outcome_rows") and promotion_path.get("can_feed_paper_outcome_tracking"):
        return BETRAYAL_OUTCOME_BRIDGE_NEEDS_TRUE_INVERSE_OUTCOMES
    if promotion_path.get("promotion_path_blocked") and promotion_path.get("can_feed_paper_outcome_tracking"):
        return BETRAYAL_OUTCOME_BRIDGE_PROMOTION_PATH_KNOWN_BUT_BLOCKED
    if all(row.get("bridge_status") == BRIDGE_READY for row in rows):
        return BETRAYAL_OUTCOME_BRIDGE_READY
    if any(row.get("bridge_status") == BRIDGE_READY for row in rows):
        return BETRAYAL_OUTCOME_BRIDGE_PARTIALLY_READY
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_betrayal_paper_outcome_tracking_bridge_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_paper_outcome_tracking_bridge_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "bridge_record_id": str(record.get("bridge_record_id") or f"r236_betrayal_paper_outcome_bridge_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_bridge_requested": bool(record.get("record_bridge_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "official_tiny_live_status": dict(record.get("official_tiny_live_status") or {}),
            "bridge_preview_rows": list(record.get("bridge_preview_rows") or []),
            "bridge_summary": dict(record.get("bridge_summary") or {}),
            "bridge_gap_report": dict(record.get("bridge_gap_report") or {}),
            "bridge_promotion_path": dict(record.get("bridge_promotion_path") or {}),
            "bridge_recommendations": list(record.get("bridge_recommendations") or []),
            "bridge_overall_status": record.get("bridge_overall_status"),
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


def load_betrayal_paper_outcome_tracking_bridge_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_paper_outcome_tracking_bridge_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_records(path, limit=0)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def summarize_betrayal_paper_outcome_tracking_bridge_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "bridge_overall_status_counts": dict(
            sorted(Counter(str(record.get("bridge_overall_status") or "UNKNOWN") for record in records).items())
        ),
        "latest_bridge_record_id": latest.get("bridge_record_id") if isinstance(latest, Mapping) else None,
        "latest_bridge_overall_status": latest.get("bridge_overall_status") if isinstance(latest, Mapping) else None,
        "safety": dict(SAFETY),
    }


def betrayal_paper_outcome_tracking_bridge_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_paper_outcome_tracking_bridge_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _official_tiny_live_status(
    *,
    gate_packet: Mapping[str, Any],
    schema_context: Mapping[str, Any],
    official_tiny_live_lane: str,
    threshold_required_count: int,
) -> dict[str, Any]:
    from_gate = dict(gate_packet.get("official_tiny_live_status") or {})
    from_sync = dict((schema_context.get("latest_records") or {}).get("capture_count_sync_8m_short") or {})
    capture = dict(from_sync.get("capture_count") or {})
    fresh = int(from_gate.get("fresh_capture_count") or capture.get("fresh_capture_count") or 0)
    required = int(from_gate.get("required_fresh_capture_count") or capture.get("required_fresh_capture_count") or threshold_required_count)
    threshold_met = bool(from_gate.get("threshold_met") or capture.get("threshold_met") or fresh >= required)
    return {
        "lane_key": str(from_gate.get("lane_key") or official_tiny_live_lane),
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
    if gap_report.get("needs_true_inverse_outcome_rows"):
        return "Build R237 betrayal true inverse outcome capture bridge; keep paper-only and no config writes."
    if overall_status == BETRAYAL_OUTCOME_BRIDGE_NEEDS_ENTRY_MODE:
        return "Continue entry_mode/lane_key adoption for blocked betrayal rows before outcome bridge expansion."
    return "Keep R236 bridge as preview-only and wait for more paper outcome evidence."


def _bridge_row_why(status: str, blockers: Sequence[str]) -> str:
    if status == BRIDGE_READY:
        return "Betrayal row can be bridged into paper outcome tracking preview; promotion and live remain blocked."
    if status == NEEDS_ENTRY_MODE:
        return "Betrayal row needs registry-valid entry_mode before paper outcome tracking."
    if status == NEEDS_LANE_KEY:
        return "Betrayal row needs lane_key before paper outcome tracking."
    if status == NEEDS_SIGNAL_ID:
        return "Betrayal row needs signal_id and source_signal_id before paper outcome tracking."
    if status == NEEDS_SOURCE_IDENTITY:
        return "Betrayal row needs source identity before paper outcome tracking."
    if status == NEEDS_OUTCOME_IDENTITY:
        return "Betrayal row needs paper_outcome_tracking_identity and outcome_window_spec."
    if status == NEEDS_TRUE_INVERSE_OUTCOME:
        return "Betrayal row needs true inverse outcome evidence before ranking can be meaningful."
    return "Betrayal row remains blocked: " + ", ".join(_dedupe(blockers)[:4])


def _normalize_outcome_window(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


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
