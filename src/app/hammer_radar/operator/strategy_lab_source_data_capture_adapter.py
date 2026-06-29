"""R331 read-only Strategy Lab source-data capture adapter packet."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.strategy_lab_adapter_output_batch_execution_packet import (
    READY as R329_READY,
    build_strategy_lab_adapter_output_batch_execution_packet,
    load_strategy_lab_adapter_output_batch_execution_packet_records,
)
from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import (
    ANCHOR_AND_EXIT_LANES,
    BASELINE_LANE,
    BETRAYAL_INVERSE_LANES,
    CAPTURE_8M_SHORT_LANES,
    NEAR_MISS_13M_LANES,
    REVIEW_READY_LANES,
    SAFETY,
    WATCH_88M_LANES,
)
from src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack import (
    ADAPTER_NEEDS_SOURCE_DATA,
    ADAPTER_READY,
    READY as R328_READY,
    build_strategy_lab_evidence_adapter_pack,
    load_strategy_lab_evidence_adapter_pack_records,
)

EVENT_TYPE = "R331_STRATEGY_LAB_SOURCE_DATA_CAPTURE_ADAPTER_IMPLEMENTATION"
CREATED_BY_PHASE = "R331_STRATEGY_LAB_SOURCE_DATA_CAPTURE_ADAPTER_IMPLEMENTATION"
LEDGER_FILENAME = "strategy_lab_source_data_capture_adapter.ndjson"

READY = "STRATEGY_LAB_SOURCE_DATA_CAPTURE_READY"
PARTIAL = "STRATEGY_LAB_SOURCE_DATA_CAPTURE_PARTIAL"
BLOCKED = "STRATEGY_LAB_SOURCE_DATA_CAPTURE_BLOCKED"

SOURCE_READY = "SOURCE_DATA_CAPTURE_READY"
SOURCE_PENDING = "SOURCE_DATA_CAPTURE_PENDING"
SOURCE_LAB_ONLY = "SOURCE_DATA_CAPTURE_LAB_ONLY"
SOURCE_WATCH_ONLY = "SOURCE_DATA_CAPTURE_WATCH_ONLY"

ADAPTER_IDS = (
    "exit_variant_comparison",
    "ma_wma_anchor_enrichment",
    "review_ready_enrichment",
    "short_capture_improvement",
    "near_miss_variant_capture",
    "betrayal_inverse_source_chain",
    "watch_88m_durability",
)

SOURCE_ADAPTER_BY_CAPTURE_ADAPTER = {
    "exit_variant_comparison": "exits",
    "ma_wma_anchor_enrichment": "ma_wma_anchor",
    "review_ready_enrichment": "review_ready_enrichment",
    "short_capture_improvement": "capture_8m_short",
    "near_miss_variant_capture": "near_miss_13m",
    "betrayal_inverse_source_chain": "betrayal_inverse_lab",
    "watch_88m_durability": "watch_88m",
}

CAPTURE_NAMES = {
    "exit_variant_comparison": (
        "fixed_tp_sl_outcome",
        "early_exit_outcome",
        "late_exit_outcome",
        "trailing_stop_outcome",
        "partial_exit_outcome",
        "invalidation_tightening_outcome",
    ),
    "ma_wma_anchor_enrichment": (
        "wma200_value",
        "ma200_value",
        "close_vs_wma200",
        "close_vs_ma200",
        "anchor_slope",
        "golden_pocket_anchor_confluence",
    ),
    "review_ready_enrichment": (
        "recent_sample_stability",
        "regime_split",
        "mae_mfe",
        "exit_sensitivity",
        "anchor_confluence",
    ),
    "short_capture_improvement": (
        "faster_capture_signal_delta",
        "tighter_invalidation_outcome",
        "partial_exit_outcome",
        "trailing_outcome",
        "regime_filter_snapshot",
        "entry_timing_delta",
    ),
    "near_miss_variant_capture": (
        "timing_repair_observation",
        "partial_entry_outcome",
        "early_exit_outcome",
        "late_exit_outcome",
        "rsi_regime_filter_snapshot",
        "ma_wma_anchor_context",
        "golden_pocket_context",
    ),
    "betrayal_inverse_source_chain": (
        "original_signal_identity",
        "inverse_signal_identity",
        "original_vs_inverse_comparison",
        "exact_lane_entry_risk_mapping",
        "paper_outcome_freshness",
        "stale_shadow_outcome_audit",
    ),
    "watch_88m_durability": (
        "slow_lane_durability_observation",
        "confirmation_delay_state",
        "htf_bias_state",
        "exit_variant_outcome",
        "anchor_filter_state",
    ),
}

SOURCE_VARIANT_BY_CAPTURE_NAME = {
    "fixed_tp_sl_outcome": "fixed_tp_sl",
    "early_exit_outcome": "early_exit",
    "late_exit_outcome": "late_exit",
    "trailing_stop_outcome": "trailing_stop",
    "partial_exit_outcome": "partial_exit",
    "invalidation_tightening_outcome": "invalidation_tightening",
    "wma200_value": "wma200_side",
    "ma200_value": "ma200_side",
    "close_vs_wma200": "close_vs_anchor",
    "close_vs_ma200": "close_vs_anchor",
    "anchor_slope": "anchor_slope",
    "golden_pocket_anchor_confluence": "golden_pocket_anchor_confluence",
    "recent_sample_stability": "recent_sample_stability",
    "regime_split": "regime_split",
    "mae_mfe": "adverse_excursion",
    "exit_sensitivity": "exit_sensitivity",
    "anchor_confluence": "anchor_confluence",
    "faster_capture_signal_delta": "faster_capture",
    "tighter_invalidation_outcome": "tighter_invalidation",
    "trailing_outcome": "trailing",
    "regime_filter_snapshot": "regime_filter",
    "entry_timing_delta": "entry_timing_delta",
    "timing_repair_observation": "timing_repair",
    "partial_entry_outcome": "partial_entry",
    "rsi_regime_filter_snapshot": "rsi_regime_filter",
    "ma_wma_anchor_context": "ma_wma_anchor_context",
    "golden_pocket_context": "golden_pocket_context",
    "original_signal_identity": "original_signal_source_chain",
    "inverse_signal_identity": "inverse_signal_source_chain",
    "original_vs_inverse_comparison": "original_vs_inverse_comparison",
    "exact_lane_entry_risk_mapping": "exact_risk_mapping",
    "paper_outcome_freshness": "stale_shadow_outcome_rejection",
    "stale_shadow_outcome_audit": "stale_shadow_outcome_rejection",
    "slow_lane_durability_observation": "durability",
    "confirmation_delay_state": "slow_confirmation",
    "htf_bias_state": "htf_bias",
    "exit_variant_outcome": "exit_variant",
    "anchor_filter_state": "anchor_filter",
}

SOURCE_GAP_BY_CAPTURE_NAME = {
    "fixed_tp_sl_outcome": "missing_exit_outcome_comparison",
    "early_exit_outcome": "missing_exit_outcome_comparison",
    "late_exit_outcome": "missing_exit_outcome_comparison",
    "trailing_stop_outcome": "missing_exit_outcome_comparison",
    "partial_exit_outcome": "missing_exit_outcome_comparison",
    "invalidation_tightening_outcome": "missing_exit_outcome_comparison",
    "wma200_value": "missing_raw_anchor_timeseries",
    "ma200_value": "missing_raw_anchor_timeseries",
    "close_vs_wma200": "missing_raw_anchor_timeseries",
    "close_vs_ma200": "missing_raw_anchor_timeseries",
    "anchor_slope": "missing_raw_anchor_timeseries",
    "golden_pocket_anchor_confluence": "missing_raw_anchor_timeseries",
    "regime_split": "missing_regime_split_capture",
    "mae_mfe": "missing_mae_mfe",
    "exit_sensitivity": "missing_exit_outcome_comparison",
    "anchor_confluence": "missing_raw_anchor_timeseries",
    "tighter_invalidation_outcome": "missing_exit_outcome_comparison",
    "partial_exit_outcome": "missing_exit_outcome_comparison",
    "trailing_outcome": "missing_exit_outcome_comparison",
    "early_exit_outcome": "missing_exit_outcome_comparison",
    "late_exit_outcome": "missing_exit_outcome_comparison",
    "betrayal_inverse_source_chain": "missing_betrayal_source_chain_data",
    "watch_88m_durability": "watch_88m_durability_source_missing",
}


def build_strategy_lab_source_data_capture_adapter(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    adapter: str = "all",
    include_lab_only: bool = True,
    include_watch_only: bool = True,
    max_source_rows: int = 500,
    evidence_adapter_pack: Mapping[str, Any] | None = None,
    adapter_output_batch_execution_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    evidence = (
        dict(evidence_adapter_pack)
        if isinstance(evidence_adapter_pack, Mapping)
        else _latest_evidence_or_build(resolved_log_dir, generated_at, adapter)
    )
    batch = (
        dict(adapter_output_batch_execution_packet)
        if isinstance(adapter_output_batch_execution_packet, Mapping)
        else _latest_batch_or_build(resolved_log_dir, generated_at, adapter, evidence)
    )
    selected_adapter_ids = _selected_adapter_ids(adapter)
    source_rows = list(evidence.get("normalized_evidence_rows") or [])[: max(max_source_rows, 0)]
    rows = _capture_rows(
        source_rows=source_rows,
        selected_adapter_ids=selected_adapter_ids,
        include_lab_only=include_lab_only,
        include_watch_only=include_watch_only,
    )
    adapter_results = [_capture_packet(adapter_id, rows) for adapter_id in ADAPTER_IDS if adapter_id in selected_adapter_ids]
    blockers = _packet_blockers(selected_adapter_ids=selected_adapter_ids, rows=rows, evidence=evidence, batch=batch)
    status = _status(blockers, rows)
    packet_by_adapter = {adapter_id: _capture_packet(adapter_id, rows) for adapter_id in ADAPTER_IDS}
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "source_data_capture_adapter_id": f"r331_strategy_lab_source_data_capture_adapter_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_lab_source_data_capture_adapter_path": str(packet_path(resolved_log_dir)),
        "source_data_capture_status": status,
        "blockers": blockers,
        "source_adapter_batch_execution_status": batch.get("adapter_batch_execution_status"),
        "source_evidence_adapter_pack_status": evidence.get("evidence_adapter_pack_status"),
        "first_tiny_live_lane": evidence.get("first_tiny_live_lane") or batch.get("first_tiny_live_lane") or BASELINE_LANE,
        "first_live_lane_change_allowed": False,
        "selected_adapter": adapter,
        "include_lab_only": include_lab_only,
        "include_watch_only": include_watch_only,
        "max_source_rows": max_source_rows,
        "capture_adapter_results": adapter_results,
        "capture_counts": _capture_counts(rows, adapter_results),
        "normalized_source_data_rows": rows,
        "exit_variant_comparison_packet": packet_by_adapter["exit_variant_comparison"],
        "ma_wma_anchor_enrichment_packet": packet_by_adapter["ma_wma_anchor_enrichment"],
        "review_ready_enrichment_packet": packet_by_adapter["review_ready_enrichment"],
        "short_capture_improvement_packet": packet_by_adapter["short_capture_improvement"],
        "near_miss_variant_capture_packet": packet_by_adapter["near_miss_variant_capture"],
        "betrayal_inverse_source_chain_packet": {
            **packet_by_adapter["betrayal_inverse_source_chain"],
            "lab_only": True,
            "standard_55_policy_applies": False,
            "source_chain_required": True,
            "exact_risk_mapping_required": True,
            "stale_shadow_outcomes_forbidden": True,
            "synthetic_performance_created": False,
            "live_permission": False,
            "tiny_live_eligible_now": False,
        },
        "watch_88m_durability_packet": {**packet_by_adapter["watch_88m_durability"], "watch_only": True, "live_permission": False},
        "remaining_capture_gaps": _remaining_capture_gaps(rows),
        "recommended_r332_path": _recommended_r332_path(),
        "recommended_r330_path": _recommended_r330_path(),
        "recommended_tiny_live_path": _recommended_tiny_live_path(evidence.get("first_tiny_live_lane") or BASELINE_LANE),
        "no_live_mutation_summary": _no_live_mutation_summary(),
        "source_surfaces_used": _source_surfaces(resolved_log_dir),
        "safety": dict(SAFETY),
        **dict(SAFETY),
    }
    safe_payload = _sanitize(payload)
    if write:
        append_packet(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def append_packet(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = packet_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_strategy_lab_source_data_capture_adapter_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(packet_path(get_log_dir(log_dir, use_env=True)), limit=limit, max_bytes=5_000_000)


def packet_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_source_data_capture_adapter_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_source_data_capture_adapter_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R331 STRATEGY LAB SOURCE DATA CAPTURE ADAPTER",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        f"source_data_capture_status: {payload.get('source_data_capture_status')}",
        "",
        "FIRST TINY LIVE LANE",
        f"first_tiny_live_lane: {payload.get('first_tiny_live_lane')}",
        f"first_live_lane_change_allowed: {payload.get('first_live_lane_change_allowed')}",
        "",
        "CAPTURE COUNTS",
    ]
    counts = payload.get("capture_counts") if isinstance(payload.get("capture_counts"), Mapping) else {}
    for key in (
        "normalized_source_data_row_count",
        "capture_ready_rows",
        "capture_pending_rows",
        "lab_only_rows",
        "watch_only_rows",
        "synthetic_performance_created_count",
        "live_permission_count",
        "promotion_event_written_count",
        "risk_contract_write_required_count",
        "observed_expansion_written_count",
        "scheduler_required_count",
    ):
        lines.append(f"{key}: {counts.get(key)}")
    lines.extend(["", "ADAPTER RESULT SUMMARY"])
    for row in payload.get("capture_adapter_results") or []:
        if isinstance(row, Mapping):
            lines.append(
                f"{row.get('capture_adapter_id')}: rows={row.get('row_count')} ready={row.get('ready_rows')} "
                f"pending={row.get('pending_rows')} lab_only={row.get('lab_only_rows')} watch_only={row.get('watch_only_rows')}"
            )
    lines.extend(["", "PENDING GAP SUMMARY"])
    gaps = payload.get("remaining_capture_gaps") if isinstance(payload.get("remaining_capture_gaps"), Mapping) else {}
    for row in gaps.get("gaps") or []:
        if isinstance(row, Mapping):
            lines.append(f"{row.get('gap_id')}: rows={row.get('row_count')} lanes={','.join(row.get('affected_lanes') or [])}")
    lines.extend(["", "BETRAYAL LAB-ONLY SOURCE-CHAIN PACKET"])
    betrayal = payload.get("betrayal_inverse_source_chain_packet") if isinstance(payload.get("betrayal_inverse_source_chain_packet"), Mapping) else {}
    for key in (
        "row_count",
        "lab_only",
        "standard_55_policy_applies",
        "source_chain_required",
        "exact_risk_mapping_required",
        "stale_shadow_outcomes_forbidden",
        "live_permission",
        "tiny_live_eligible_now",
    ):
        lines.append(f"{key}: {betrayal.get(key)}")
    lines.extend(["", "WATCH-ONLY DURABILITY PACKET"])
    watch = payload.get("watch_88m_durability_packet") if isinstance(payload.get("watch_88m_durability_packet"), Mapping) else {}
    lines.append(f"row_count: {watch.get('row_count')}")
    lines.append(f"watch_only: {watch.get('watch_only')}")
    lines.append(f"live_permission: {watch.get('live_permission')}")
    lines.extend(["", "RECOMMENDED R332/R330"])
    lines.append(str(payload.get("recommended_r332_path")))
    lines.append(str(payload.get("recommended_r330_path")))
    lines.extend(["", "TINY LIVE PATH"])
    for item in payload.get("recommended_tiny_live_path") or []:
        lines.append(str(item))
    lines.extend(["", "SAFETY FLAGS"])
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    for key in SAFETY:
        lines.append(f"{key}: {safety.get(key)}")
    return "\n".join(lines)


def _capture_rows(
    *,
    source_rows: Sequence[Mapping[str, Any]],
    selected_adapter_ids: set[str],
    include_lab_only: bool,
    include_watch_only: bool,
) -> list[dict[str, Any]]:
    rows_by_source = {
        (str(row.get("adapter_id")), str(row.get("lane_key")), str(row.get("variant_name"))): row
        for row in source_rows
        if isinstance(row, Mapping)
    }
    capture_rows: list[dict[str, Any]] = []
    for capture_adapter_id in ADAPTER_IDS:
        if capture_adapter_id not in selected_adapter_ids:
            continue
        if capture_adapter_id == "betrayal_inverse_source_chain" and not include_lab_only:
            continue
        if capture_adapter_id == "watch_88m_durability" and not include_watch_only:
            continue
        for lane in _candidate_lanes(capture_adapter_id):
            for capture_name in CAPTURE_NAMES[capture_adapter_id]:
                source_variant = SOURCE_VARIANT_BY_CAPTURE_NAME[capture_name]
                source_adapter_id = SOURCE_ADAPTER_BY_CAPTURE_ADAPTER[capture_adapter_id]
                source = rows_by_source.get((source_adapter_id, lane, source_variant), {})
                capture_rows.append(
                    _normalized_source_data_row(
                        capture_adapter_id=capture_adapter_id,
                        lane_key=lane,
                        source_gap_id=_source_gap_id(capture_adapter_id, capture_name, source),
                        capture_family=capture_adapter_id,
                        capture_name=capture_name,
                        source=source,
                    )
                )
    return capture_rows


def _normalized_source_data_row(
    *,
    capture_adapter_id: str,
    lane_key: str,
    source_gap_id: str,
    capture_family: str,
    capture_name: str,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    symbol, timeframe, side, entry_mode = _parse_lane(lane_key)
    blockers = _capture_blockers(capture_adapter_id, source_gap_id, source)
    status = _capture_status(capture_adapter_id, source, blockers)
    source_chain = list(source.get("source_chain") or [])
    source_chain.extend(["strategy_lab_evidence_adapter_pack", "strategy_lab_source_data_capture_adapter"])
    derived = source.get("derived_fields") if isinstance(source.get("derived_fields"), Mapping) else {}
    return {
        "capture_adapter_id": capture_adapter_id,
        "source_row_id": source.get("row_id") or f"r331|{capture_adapter_id}|{lane_key}|{capture_name}".replace(" ", "_"),
        "lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "side": side,
        "entry_mode": entry_mode,
        "source_gap_id": source_gap_id,
        "capture_family": capture_family,
        "capture_name": capture_name,
        "capture_status": status,
        "source_inputs": {
            "source_adapter_id": source.get("adapter_id"),
            "source_variant_name": source.get("variant_name"),
            "source_evidence_status": source.get("evidence_status"),
            "input_fields": source.get("input_fields") or {},
            "sample_count_source": source.get("sample_count_source"),
            "win_rate_source": source.get("win_rate_source"),
            "avg_pnl_source": source.get("avg_pnl_source"),
        },
        "derived_capture_fields": {
            "source_data_available": status == SOURCE_READY,
            "source_adapter_dimension": derived.get("adapter_dimension"),
            "raw_source_gap": derived.get("raw_source_gap") or source_gap_id,
            "lab_only": capture_adapter_id == "betrayal_inverse_source_chain",
            "watch_only": capture_adapter_id == "watch_88m_durability",
            "standard_55_policy_applies": False if capture_adapter_id == "betrayal_inverse_source_chain" else None,
            "source_chain_required": capture_adapter_id == "betrayal_inverse_source_chain",
            "exact_risk_mapping_required": capture_adapter_id == "betrayal_inverse_source_chain",
            "stale_shadow_outcomes_forbidden": capture_adapter_id == "betrayal_inverse_source_chain",
        },
        "source_chain": list(dict.fromkeys(source_chain)),
        "used_existing_data_only": True,
        "synthetic_performance_created": False,
        "live_permission": False,
        "tiny_live_eligible_now": False,
        "promotion_event_written": False,
        "risk_contract_write_required": False,
        "observed_expansion_written": False,
        "scheduler_required": False,
        "blockers": blockers,
    }


def _capture_status(capture_adapter_id: str, source: Mapping[str, Any], blockers: Sequence[str]) -> str:
    if capture_adapter_id == "betrayal_inverse_source_chain":
        return SOURCE_LAB_ONLY
    if capture_adapter_id == "watch_88m_durability":
        return SOURCE_WATCH_ONLY
    if blockers:
        return SOURCE_PENDING
    if source.get("evidence_status") == ADAPTER_READY:
        return SOURCE_READY
    return SOURCE_PENDING


def _capture_blockers(capture_adapter_id: str, source_gap_id: str, source: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not source:
        blockers.append("source_evidence_row_missing")
    if capture_adapter_id == "betrayal_inverse_source_chain":
        blockers.append("betrayal_source_chain_source_missing")
    elif capture_adapter_id == "watch_88m_durability":
        blockers.append("watch_88m_durability_source_missing")
    elif source.get("evidence_status") == ADAPTER_NEEDS_SOURCE_DATA or source_gap_id:
        blockers.append(_blocker_for_gap(source_gap_id))
    for blocker in source.get("blockers") or []:
        if str(blocker).startswith("missing_"):
            blockers.append(_blocker_for_gap(str(blocker)))
    return list(dict.fromkeys(blockers))


def _source_gap_id(capture_adapter_id: str, capture_name: str, source: Mapping[str, Any]) -> str:
    if capture_adapter_id == "betrayal_inverse_source_chain":
        return "missing_betrayal_source_chain_data"
    if capture_adapter_id == "watch_88m_durability":
        return "watch_88m_durability_source_missing"
    derived = source.get("derived_fields") if isinstance(source.get("derived_fields"), Mapping) else {}
    return str(derived.get("raw_source_gap") or SOURCE_GAP_BY_CAPTURE_NAME.get(capture_name) or "")


def _blocker_for_gap(gap_id: str) -> str:
    return {
        "missing_exit_outcome_comparison": "exit_outcome_source_missing",
        "missing_raw_anchor_timeseries": "anchor_timeseries_source_missing",
        "missing_mae_mfe": "mae_mfe_source_missing",
        "missing_regime_split_capture": "regime_split_source_missing",
        "missing_betrayal_source_chain_data": "betrayal_source_chain_source_missing",
        "watch_88m_durability_source_missing": "watch_88m_durability_source_missing",
    }.get(gap_id, gap_id)


def _capture_packet(capture_adapter_id: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    adapter_rows = [row for row in rows if row.get("capture_adapter_id") == capture_adapter_id]
    return {
        "capture_adapter_id": capture_adapter_id,
        "implemented": bool(adapter_rows),
        "row_count": len(adapter_rows),
        "ready_rows": sum(1 for row in adapter_rows if row.get("capture_status") == SOURCE_READY),
        "pending_rows": sum(1 for row in adapter_rows if row.get("capture_status") == SOURCE_PENDING),
        "lab_only_rows": sum(1 for row in adapter_rows if row.get("capture_status") == SOURCE_LAB_ONLY),
        "watch_only_rows": sum(1 for row in adapter_rows if row.get("capture_status") == SOURCE_WATCH_ONLY),
        "candidate_lanes": list(dict.fromkeys(str(row.get("lane_key")) for row in adapter_rows if row.get("lane_key"))),
        "live_permission": False,
        "tiny_live_eligible_now": False,
        "promotion_event_written": False,
        "risk_contract_write_required": False,
        "observed_expansion_written": False,
        "scheduler_required": False,
    }


def _capture_counts(rows: Sequence[Mapping[str, Any]], adapter_results: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "implemented_capture_adapter_count": len(adapter_results),
        "normalized_source_data_row_count": len(rows),
        "capture_ready_rows": sum(1 for row in rows if row.get("capture_status") == SOURCE_READY),
        "capture_pending_rows": sum(1 for row in rows if row.get("capture_status") == SOURCE_PENDING),
        "lab_only_rows": sum(1 for row in rows if row.get("capture_status") == SOURCE_LAB_ONLY),
        "watch_only_rows": sum(1 for row in rows if row.get("capture_status") == SOURCE_WATCH_ONLY),
        "synthetic_performance_created_count": sum(1 for row in rows if row.get("synthetic_performance_created") is True),
        "live_permission_count": sum(1 for row in rows if row.get("live_permission") is True),
        "promotion_event_written_count": sum(1 for row in rows if row.get("promotion_event_written") is True),
        "risk_contract_write_required_count": sum(1 for row in rows if row.get("risk_contract_write_required") is True),
        "observed_expansion_written_count": sum(1 for row in rows if row.get("observed_expansion_written") is True),
        "scheduler_required_count": sum(1 for row in rows if row.get("scheduler_required") is True),
    }


def _remaining_capture_gaps(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    required = (
        "exit_outcome_source_missing",
        "anchor_timeseries_source_missing",
        "mae_mfe_source_missing",
        "regime_split_source_missing",
        "betrayal_source_chain_source_missing",
        "watch_88m_durability_source_missing",
    )
    for row in rows:
        for blocker in row.get("blockers") or []:
            if blocker in required:
                grouped.setdefault(str(blocker), []).append(row)
    return {
        "gaps": [
            {
                "gap_id": gap_id,
                "row_count": len(grouped.get(gap_id, [])),
                "affected_lanes": list(dict.fromkeys(str(row.get("lane_key")) for row in grouped.get(gap_id, []) if row.get("lane_key"))),
                "do_not_fake_data": True,
            }
            for gap_id in required
        ],
        "source_data_capture_pending_is_required_when_inputs_are_missing": True,
    }


def _status(blockers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    if blockers:
        return BLOCKED
    if any(row.get("capture_status") in {SOURCE_PENDING, SOURCE_LAB_ONLY, SOURCE_WATCH_ONLY} for row in rows):
        return PARTIAL
    return READY


def _packet_blockers(
    *,
    selected_adapter_ids: set[str],
    rows: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    batch: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not selected_adapter_ids:
        blockers.append("no_capture_adapter_selected")
    if not rows:
        blockers.append("no_source_data_capture_rows_built")
    if evidence.get("evidence_adapter_pack_status") != R328_READY:
        blockers.append("source_r328_evidence_adapter_pack_not_ready")
    if batch.get("adapter_batch_execution_status") != R329_READY:
        blockers.append("source_r329_adapter_batch_execution_not_ready")
    return blockers


def _candidate_lanes(capture_adapter_id: str) -> Sequence[str]:
    if capture_adapter_id in {"exit_variant_comparison", "ma_wma_anchor_enrichment"}:
        return ANCHOR_AND_EXIT_LANES
    if capture_adapter_id == "review_ready_enrichment":
        return REVIEW_READY_LANES
    if capture_adapter_id == "short_capture_improvement":
        return CAPTURE_8M_SHORT_LANES
    if capture_adapter_id == "near_miss_variant_capture":
        return NEAR_MISS_13M_LANES
    if capture_adapter_id == "betrayal_inverse_source_chain":
        return BETRAYAL_INVERSE_LANES
    if capture_adapter_id == "watch_88m_durability":
        return WATCH_88M_LANES
    return ()


def _selected_adapter_ids(adapter: str) -> set[str]:
    if adapter == "all":
        return set(ADAPTER_IDS)
    if adapter not in ADAPTER_IDS:
        return set()
    return {adapter}


def _latest_evidence_or_build(log_dir: Path, now: datetime, adapter: str) -> dict[str, Any]:
    records = load_strategy_lab_evidence_adapter_pack_records(log_dir=log_dir, limit=1)
    if records:
        return records[-1]
    source_adapter = SOURCE_ADAPTER_BY_CAPTURE_ADAPTER.get(adapter, "all") if adapter != "all" else "all"
    return build_strategy_lab_evidence_adapter_pack(log_dir=log_dir, write=False, now=now, adapter=source_adapter)


def _latest_batch_or_build(log_dir: Path, now: datetime, adapter: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    records = load_strategy_lab_adapter_output_batch_execution_packet_records(log_dir=log_dir, limit=1)
    if records:
        return records[-1]
    source_adapter = SOURCE_ADAPTER_BY_CAPTURE_ADAPTER.get(adapter, "all") if adapter != "all" else "all"
    return build_strategy_lab_adapter_output_batch_execution_packet(
        log_dir=log_dir,
        write=False,
        now=now,
        adapter=source_adapter,
        evidence_adapter_pack=evidence,
    )


def _parse_lane(lane_key: str) -> tuple[str | None, str | None, str | None, str | None]:
    parts = lane_key.split("|")
    if len(parts) >= 4:
        return parts[0], parts[1], parts[2], parts[3]
    return lane_key, None, None, None


def _recommended_r332_path() -> dict[str, Any]:
    return {
        "phase": "R332 Strategy Lab Captured Source Data Merge Into Adapter Rows",
        "purpose": "Merge captured and pending R331 source-data rows back into the R328/R329 comparison flow.",
        "input_ledger": LEDGER_FILENAME,
        "write_promotion_events": False,
        "write_risk_contracts": False,
        "live_permission": False,
    }


def _recommended_r330_path() -> dict[str, Any]:
    return {
        "phase": "R330 Human-Reviewed Observed Expansion Promotion Gate",
        "purpose": "Observed expansion can change only after human review of R329/R331 evidence.",
        "can_later_alter_observed_expansion_after_human_review": True,
        "tiny_live_separately_gated": True,
        "live_permission": False,
    }


def _recommended_tiny_live_path(first_tiny_live_lane: str) -> list[str]:
    return [
        f"First Tiny Live remains {first_tiny_live_lane}.",
        "R331 captures Strategy Lab source-data artifacts only and does not alter Tiny Live.",
        "No final command is available from R331.",
        "Tiny Live remains separately gated by human approval, exact risk contract, real candidate detection, and final gate clearance.",
    ]


def _no_live_mutation_summary() -> dict[str, bool]:
    return {
        "no_orders": True,
        "no_binance_order_or_test_order_endpoints": True,
        "no_leverage_or_margin_change": True,
        "no_live_flag_mutation": True,
        "no_kill_switch_mutation": True,
        "no_arming_mutation": True,
        "no_final_command": True,
        "no_submit": True,
        "no_first_tiny_live_lane_change": True,
        "no_promotion_event_write": True,
        "no_risk_contract_write": True,
        "no_observed_expansion_write": True,
        "no_config_or_env_mutation": True,
        "no_systemd_mutation": True,
        "no_scheduler_start": True,
        "no_telegram_send": True,
    }


def _source_surfaces(log_dir: Path) -> list[str]:
    return [
        "docs/hammer_radar/live_readiness/R329_STRATEGY_LAB_ADAPTER_OUTPUT_BATCH_EXECUTION_PACKET.md",
        "docs/hammer_radar/live_readiness/R328_STRATEGY_LAB_EVIDENCE_ADAPTER_IMPLEMENTATION_PACK.md",
        "docs/hammer_radar/live_readiness/R326_CANDIDATE_FEED_EXPANSION_FOR_STRATEGY_LAB_VARIANTS.md",
        "docs/hammer_radar/live_readiness/R325_STRATEGY_LAB_PROMOTION_REVIEW_PACKET.md",
        "src/app/hammer_radar/operator/strategy_lab_adapter_output_batch_execution_packet.py",
        "src/app/hammer_radar/operator/strategy_lab_evidence_adapter_pack.py",
        "src/app/hammer_radar/operator/strategy_lab_candidate_feed_expansion.py",
        "src/app/hammer_radar/operator/strategy_lab_variant_batch_runner.py",
        "src/app/hammer_radar/operator/strategy_lab_preview.py",
        "src/app/hammer_radar/operator/paper_refresh_scheduler.py",
        "src/app/hammer_radar/operator/inspect.py",
        str(log_dir / "strategy_lab_adapter_output_batch_execution_packet.ndjson"),
        str(log_dir / "strategy_lab_evidence_adapter_pack.ndjson"),
        str(log_dir / "strategy_lab_candidate_feed_expansion.ndjson"),
        str(log_dir / "strategy_lab_variant_batch_runner.ndjson"),
        str(log_dir / "strategy_lab_preview.ndjson"),
        str(log_dir / "strategy_evidence_registry.ndjson"),
    ]


def _sanitize(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.strategy_lab_source_data_capture_adapter")
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--adapter", choices=("all", *ADAPTER_IDS), default="all")
    parser.add_argument("--include-lab-only", action="store_true", default=True)
    parser.add_argument("--include-watch-only", action="store_true", default=True)
    parser.add_argument("--max-source-rows", type=int, default=500)
    args = parser.parse_args(argv)

    payload = build_strategy_lab_source_data_capture_adapter(
        log_dir=args.log_dir,
        write=not args.no_write,
        adapter=args.adapter,
        include_lab_only=args.include_lab_only,
        include_watch_only=args.include_watch_only,
        max_source_rows=args.max_source_rows,
    )
    if args.text:
        print(format_source_data_capture_adapter_text(payload))
    else:
        print(format_source_data_capture_adapter_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
