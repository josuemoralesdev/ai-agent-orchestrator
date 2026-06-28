"""R328 read-only Strategy Lab evidence adapter implementation pack."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import (
    ANCHOR_AND_EXIT_LANES,
    BASELINE_LANE,
    BETRAYAL_INVERSE_LANES,
    CAPTURE_8M_SHORT_LANES,
    FEED_IDS,
    NEAR_MISS_13M_LANES,
    READY as R326_READY,
    REVIEW_READY_LANES,
    SAFETY,
    WATCH_88M_LANES,
    build_strategy_lab_candidate_feed_expansion,
    load_strategy_lab_candidate_feed_expansion_records,
)
from src.app.hammer_radar.operator.strategy_lab_promotion_review_packet import (
    READY as R325_READY,
    build_strategy_lab_promotion_review_packet,
    load_strategy_lab_promotion_review_packet_records,
)
from src.app.hammer_radar.operator.strategy_lab_variant_batch_runner import (
    READY as R324_READY,
    build_strategy_lab_variant_batch_runner,
    load_strategy_lab_variant_batch_runner_records,
)

EVENT_TYPE = "R328_STRATEGY_LAB_EVIDENCE_ADAPTER_IMPLEMENTATION_PACK"
CREATED_BY_PHASE = "R328_STRATEGY_LAB_EVIDENCE_ADAPTER_IMPLEMENTATION_PACK"
LEDGER_FILENAME = "strategy_lab_evidence_adapter_pack.ndjson"

READY = "STRATEGY_LAB_EVIDENCE_ADAPTER_PACK_READY"
BLOCKED = "STRATEGY_LAB_EVIDENCE_ADAPTER_PACK_BLOCKED"

ADAPTER_READY = "ADAPTER_READY"
ADAPTER_NEEDS_SOURCE_DATA = "ADAPTER_NEEDS_SOURCE_DATA"
LAB_ONLY = "LAB_ONLY"
WATCH_ONLY = "WATCH_ONLY"

ADAPTER_IDS = FEED_IDS

NEAR_MISS_DIMENSIONS = (
    "timing_repair",
    "partial_entry",
    "early_exit",
    "late_exit",
    "rsi_regime_filter",
    "ma_wma_anchor_context",
    "golden_pocket_context",
)
CAPTURE_8M_SHORT_DIMENSIONS = (
    "faster_capture",
    "tighter_invalidation",
    "partial_exit",
    "trailing",
    "regime_filter",
    "entry_timing_delta",
)
ANCHOR_DIMENSIONS = (
    "wma200_side",
    "ma200_side",
    "close_vs_anchor",
    "anchor_slope",
    "golden_pocket_anchor_confluence",
)
EXIT_DIMENSIONS = (
    "fixed_tp_sl",
    "early_exit",
    "late_exit",
    "trailing_stop",
    "partial_exit",
    "invalidation_tightening",
)
BETRAYAL_DIMENSIONS = (
    "original_signal_source_chain",
    "inverse_signal_source_chain",
    "original_vs_inverse_comparison",
    "exact_risk_mapping",
    "stale_shadow_outcome_rejection",
)
WATCH_88M_DIMENSIONS = (
    "durability",
    "slow_confirmation",
    "htf_bias",
    "exit_variant",
    "anchor_filter",
)
REVIEW_READY_ENRICHMENT_DIMENSIONS = (
    "recent_sample_stability",
    "regime_split",
    "adverse_excursion",
    "exit_sensitivity",
    "anchor_confluence",
)

RAW_SOURCE_GAPS_BY_DIMENSION = {
    "wma200_side": "missing_raw_anchor_timeseries",
    "ma200_side": "missing_raw_anchor_timeseries",
    "close_vs_anchor": "missing_raw_anchor_timeseries",
    "anchor_slope": "missing_raw_anchor_timeseries",
    "golden_pocket_anchor_confluence": "missing_raw_anchor_timeseries",
    "fixed_tp_sl": "missing_exit_outcome_comparison",
    "early_exit": "missing_exit_outcome_comparison",
    "late_exit": "missing_exit_outcome_comparison",
    "trailing_stop": "missing_exit_outcome_comparison",
    "partial_exit": "missing_exit_outcome_comparison",
    "invalidation_tightening": "missing_exit_outcome_comparison",
    "regime_split": "missing_regime_split_capture",
    "adverse_excursion": "missing_mae_mfe",
    "exit_sensitivity": "missing_exit_outcome_comparison",
    "anchor_confluence": "missing_raw_anchor_timeseries",
}


def build_strategy_lab_evidence_adapter_pack(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    adapter: str = "all",
    min_sample_count: int = 30,
    preferred_sample_count: int = 50,
    candidate_feed_expansion_packet: Mapping[str, Any] | None = None,
    promotion_review_packet: Mapping[str, Any] | None = None,
    batch_runner_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    promotion = (
        dict(promotion_review_packet)
        if isinstance(promotion_review_packet, Mapping)
        else _latest_promotion_or_build(resolved_log_dir, generated_at, min_sample_count, preferred_sample_count)
    )
    batch = (
        dict(batch_runner_packet)
        if isinstance(batch_runner_packet, Mapping)
        else _latest_batch_or_build(resolved_log_dir, generated_at, min_sample_count, preferred_sample_count)
    )
    feed = (
        dict(candidate_feed_expansion_packet)
        if isinstance(candidate_feed_expansion_packet, Mapping)
        else _latest_feed_or_build(resolved_log_dir, generated_at, min_sample_count, preferred_sample_count, promotion, batch)
    )
    selected_adapter_ids = _selected_adapter_ids(adapter)
    evidence_by_lane = _evidence_by_lane(promotion=promotion, batch=batch)
    rows = [
        row
        for row in _adapter_rows(
            selected_adapter_ids=selected_adapter_ids,
            evidence_by_lane=evidence_by_lane,
            min_sample_count=min_sample_count,
            preferred_sample_count=preferred_sample_count,
        )
    ]
    adapter_results = _adapter_results(rows, selected_adapter_ids)
    packet_by_adapter = {adapter_id: _adapter_packet(adapter_id, adapter_results, rows) for adapter_id in ADAPTER_IDS}
    blockers = _packet_blockers(
        selected_adapter_ids=selected_adapter_ids,
        rows=rows,
        feed=feed,
        promotion=promotion,
        batch=batch,
    )
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "evidence_adapter_pack_id": f"r328_strategy_lab_evidence_adapter_pack_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_lab_evidence_adapter_pack_path": str(packet_path(resolved_log_dir)),
        "evidence_adapter_pack_status": BLOCKED if blockers else READY,
        "blockers": blockers,
        "source_candidate_feed_expansion_status": feed.get("candidate_feed_expansion_status"),
        "source_promotion_review_status": promotion.get("promotion_review_status"),
        "source_batch_runner_status": batch.get("batch_runner_status"),
        "first_tiny_live_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
        "selected_adapter": adapter,
        "adapter_results": adapter_results,
        "adapter_counts": _adapter_counts(rows, adapter_results),
        "normalized_evidence_rows": rows,
        "near_miss_adapter_packet": packet_by_adapter["near_miss_13m"],
        "capture_8m_short_adapter_packet": packet_by_adapter["capture_8m_short"],
        "ma_wma_anchor_adapter_packet": packet_by_adapter["ma_wma_anchor"],
        "exit_variant_adapter_packet": packet_by_adapter["exits"],
        "betrayal_inverse_lab_adapter_packet": packet_by_adapter["betrayal_inverse_lab"],
        "watch_88m_adapter_packet": packet_by_adapter["watch_88m"],
        "review_ready_enrichment_adapter_packet": packet_by_adapter["review_ready_enrichment"],
        "implemented_adapter_summary": _implemented_adapter_summary(rows),
        "remaining_adapter_gaps": _remaining_adapter_gaps(rows),
        "recommended_r329_path": _recommended_r329_path(),
        "recommended_r330_path": _recommended_r330_path(),
        "recommended_tiny_live_path": _recommended_tiny_live_path(),
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


def load_strategy_lab_evidence_adapter_pack_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(packet_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def packet_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_evidence_adapter_pack_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_evidence_adapter_pack_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R328 STRATEGY LAB EVIDENCE ADAPTER IMPLEMENTATION PACK",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        f"evidence_adapter_pack_status: {payload.get('evidence_adapter_pack_status')}",
        "",
        "FIRST TINY LIVE LANE",
        f"first_tiny_live_lane: {payload.get('first_tiny_live_lane')}",
        f"first_live_lane_change_allowed: {payload.get('first_live_lane_change_allowed')}",
        "",
        "ADAPTER SUMMARY",
    ]
    summary = payload.get("implemented_adapter_summary") if isinstance(payload.get("implemented_adapter_summary"), Mapping) else {}
    lines.append(f"implemented_adapters: {','.join(summary.get('implemented_adapters') or [])}")
    lines.append(f"adapter_row_counts: {summary.get('adapter_row_counts')}")
    lines.append(f"rows_ready: {summary.get('rows_ready')}")
    lines.append(f"rows_needing_source_data: {summary.get('rows_needing_source_data')}")
    lines.append(f"lab_only_rows: {summary.get('lab_only_rows')}")
    lines.append(f"watch_only_rows: {summary.get('watch_only_rows')}")
    lines.extend(["", "NORMALIZED EVIDENCE ROW COUNTS"])
    counts = payload.get("adapter_counts") if isinstance(payload.get("adapter_counts"), Mapping) else {}
    for key, value in counts.items():
        lines.append(f"{key}: {value}")
    for title, key in (
        ("NEAR-MISS ADAPTER SUMMARY", "near_miss_adapter_packet"),
        ("8M CAPTURE ADAPTER SUMMARY", "capture_8m_short_adapter_packet"),
        ("ANCHOR ADAPTER SUMMARY", "ma_wma_anchor_adapter_packet"),
        ("EXIT ADAPTER SUMMARY", "exit_variant_adapter_packet"),
        ("BETRAYAL LAB ADAPTER SUMMARY", "betrayal_inverse_lab_adapter_packet"),
        ("WATCH 88M ADAPTER SUMMARY", "watch_88m_adapter_packet"),
        ("REVIEW-READY ENRICHMENT SUMMARY", "review_ready_enrichment_adapter_packet"),
    ):
        packet = payload.get(key) if isinstance(payload.get(key), Mapping) else {}
        lines.extend(["", title])
        lines.append(
            f"adapter_id: {packet.get('adapter_id')} row_count: {packet.get('row_count')} "
            f"ready_rows: {packet.get('ready_rows')} needs_source_data_rows: {packet.get('needs_source_data_rows')}"
        )
        lines.append(f"candidate_lanes: {','.join(packet.get('candidate_lanes') or []) or 'none'}")
        if packet.get("lab_only") is not None:
            lines.append(f"lab_only: {packet.get('lab_only')}")
        if packet.get("watch_only") is not None:
            lines.append(f"watch_only: {packet.get('watch_only')}")
    lines.extend(["", "REMAINING ADAPTER GAPS"])
    gaps = payload.get("remaining_adapter_gaps") if isinstance(payload.get("remaining_adapter_gaps"), Mapping) else {}
    for item in gaps.get("gaps") or []:
        lines.append(str(item))
    lines.extend(["", "RECOMMENDED R329/R330"])
    lines.append(str(payload.get("recommended_r329_path")))
    lines.append(str(payload.get("recommended_r330_path")))
    lines.extend(["", "TINY LIVE PATH"])
    for item in payload.get("recommended_tiny_live_path") or []:
        lines.append(str(item))
    lines.extend(["", "SAFETY FLAGS"])
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    for key in SAFETY:
        lines.append(f"{key}: {safety.get(key)}")
    return "\n".join(lines)


def _adapter_rows(
    *,
    selected_adapter_ids: set[str],
    evidence_by_lane: Mapping[str, Mapping[str, Any]],
    min_sample_count: int,
    preferred_sample_count: int,
) -> list[dict[str, Any]]:
    builders = {
        "near_miss_13m": lambda: _build_standard_rows(
            adapter_id="near_miss_13m",
            lanes=NEAR_MISS_13M_LANES,
            dimensions=NEAR_MISS_DIMENSIONS,
            variant_family="near_miss_repair",
            evidence_by_lane=evidence_by_lane,
        ),
        "capture_8m_short": lambda: _build_standard_rows(
            adapter_id="capture_8m_short",
            lanes=CAPTURE_8M_SHORT_LANES,
            dimensions=CAPTURE_8M_SHORT_DIMENSIONS,
            variant_family="short_capture_improvement",
            evidence_by_lane=evidence_by_lane,
            extra_derived={"near_threshold": True},
        ),
        "ma_wma_anchor": lambda: _build_standard_rows(
            adapter_id="ma_wma_anchor",
            lanes=ANCHOR_AND_EXIT_LANES,
            dimensions=ANCHOR_DIMENSIONS,
            variant_family="ma_wma200_anchor_confluence",
            evidence_by_lane=evidence_by_lane,
        ),
        "exits": lambda: _build_standard_rows(
            adapter_id="exits",
            lanes=ANCHOR_AND_EXIT_LANES,
            dimensions=EXIT_DIMENSIONS,
            variant_family="exit_tp_sl_trailing_comparison",
            evidence_by_lane=evidence_by_lane,
        ),
        "betrayal_inverse_lab": lambda: _build_betrayal_rows(
            evidence_by_lane=evidence_by_lane,
            min_sample_count=min_sample_count,
            preferred_sample_count=preferred_sample_count,
        ),
        "watch_88m": lambda: _build_standard_rows(
            adapter_id="watch_88m",
            lanes=WATCH_88M_LANES,
            dimensions=WATCH_88M_DIMENSIONS,
            variant_family="watch_only_durability",
            evidence_by_lane=evidence_by_lane,
            evidence_status=WATCH_ONLY,
            extra_derived={"watch_only": True},
        ),
        "review_ready_enrichment": lambda: _build_standard_rows(
            adapter_id="review_ready_enrichment",
            lanes=REVIEW_READY_LANES,
            dimensions=REVIEW_READY_ENRICHMENT_DIMENSIONS,
            variant_family="review_ready_enrichment",
            evidence_by_lane=evidence_by_lane,
        ),
    }
    rows: list[dict[str, Any]] = []
    for adapter_id in ADAPTER_IDS:
        if adapter_id in selected_adapter_ids:
            rows.extend(builders[adapter_id]())
    return rows


def _build_standard_rows(
    *,
    adapter_id: str,
    lanes: Sequence[str],
    dimensions: Sequence[str],
    variant_family: str,
    evidence_by_lane: Mapping[str, Mapping[str, Any]],
    evidence_status: str | None = None,
    extra_derived: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lane in lanes:
        evidence = evidence_by_lane.get(lane, {})
        for dimension in dimensions:
            blockers = _dimension_blockers(dimension, evidence)
            status = evidence_status or (ADAPTER_NEEDS_SOURCE_DATA if blockers else ADAPTER_READY)
            rows.append(
                _normalized_row(
                    adapter_id=adapter_id,
                    lane_key=lane,
                    variant_family=variant_family,
                    variant_name=dimension,
                    evidence=evidence,
                    evidence_status=status,
                    blockers=blockers,
                    derived_fields={
                        "adapter_dimension": dimension,
                        "source_data_available": not blockers,
                        "raw_source_gap": RAW_SOURCE_GAPS_BY_DIMENSION.get(dimension),
                        **dict(extra_derived or {}),
                    },
                )
            )
    return rows


def _build_betrayal_rows(
    *,
    evidence_by_lane: Mapping[str, Mapping[str, Any]],
    min_sample_count: int,
    preferred_sample_count: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lane in BETRAYAL_INVERSE_LANES:
        evidence = evidence_by_lane.get(lane, {})
        for dimension in BETRAYAL_DIMENSIONS:
            rows.append(
                _normalized_row(
                    adapter_id="betrayal_inverse_lab",
                    lane_key=lane,
                    variant_family="betrayal_inverse_source_chain",
                    variant_name=dimension,
                    evidence=evidence,
                    evidence_status=LAB_ONLY,
                    blockers=["lab_only_not_standard_promotion", "missing_betrayal_source_chain_data"],
                    derived_fields={
                        "adapter_dimension": dimension,
                        "lab_only": True,
                        "standard_55_policy_applies": False,
                        "preferred_win_rate_pct": 60,
                        "min_sample_count": min_sample_count,
                        "preferred_sample_count": preferred_sample_count,
                        "avg_pnl_requirement": "positive",
                        "original_vs_inverse_required": True,
                        "source_chain_required": True,
                        "exact_risk_mapping_required": True,
                        "stale_shadow_outcomes_forbidden": True,
                    },
                )
            )
    return rows


def _normalized_row(
    *,
    adapter_id: str,
    lane_key: str,
    variant_family: str,
    variant_name: str,
    evidence: Mapping[str, Any],
    evidence_status: str,
    blockers: Sequence[str],
    derived_fields: Mapping[str, Any],
) -> dict[str, Any]:
    symbol, timeframe, side, entry_mode = _parse_lane(lane_key)
    row_id = f"r328|{adapter_id}|{lane_key}|{variant_name}".replace(" ", "_")
    source_chain = list(evidence.get("source_chain") or [])
    if "strategy_lab_evidence_adapter_pack" not in source_chain:
        source_chain.append("strategy_lab_evidence_adapter_pack")
    return {
        "adapter_id": adapter_id,
        "row_id": row_id,
        "lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "side": side,
        "entry_mode": entry_mode,
        "variant_family": variant_family,
        "variant_name": variant_name,
        "evidence_status": evidence_status,
        "source_chain": source_chain,
        "input_fields": {
            "sample_count": evidence.get("sample_count"),
            "win_rate_pct": evidence.get("win_rate_pct"),
            "avg_pnl_pct": evidence.get("avg_pnl_pct"),
            "source_evidence_status": evidence.get("evidence_status"),
            "recommended_lab_action": evidence.get("recommended_lab_action") or evidence.get("recommended_decision"),
        },
        "derived_fields": dict(derived_fields),
        "sample_count_source": evidence.get("sample_count"),
        "win_rate_source": evidence.get("win_rate_pct"),
        "avg_pnl_source": evidence.get("avg_pnl_pct"),
        "live_permission": False,
        "tiny_live_eligible_now": False,
        "promotion_event_written": False,
        "risk_contract_write_required": False,
        "scheduler_required": False,
        "blockers": list(blockers),
    }


def _dimension_blockers(dimension: str, evidence: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not evidence:
        blockers.append("missing_lane_evidence_snapshot")
    gap = RAW_SOURCE_GAPS_BY_DIMENSION.get(dimension)
    if gap:
        blockers.append(gap)
    return list(dict.fromkeys(blockers))


def _evidence_by_lane(*, promotion: Mapping[str, Any], batch: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for key in ("review_ready_candidates", "needs_more_samples_candidates", "watch_only_candidates"):
        for row in promotion.get(key) or []:
            if isinstance(row, Mapping) and row.get("lane_key"):
                evidence[str(row["lane_key"])] = {
                    **evidence.get(str(row["lane_key"]), {}),
                    "sample_count": row.get("sample_count"),
                    "win_rate_pct": row.get("win_rate_pct"),
                    "avg_pnl_pct": row.get("avg_pnl_pct"),
                    "evidence_status": row.get("evidence_status"),
                    "recommended_decision": row.get("recommended_decision"),
                    "source_chain": ["strategy_lab_promotion_review_packet"],
                }
    for row in batch.get("batch_results") or []:
        if not isinstance(row, Mapping):
            continue
        snapshots = row.get("current_evidence_snapshot") if isinstance(row.get("current_evidence_snapshot"), Mapping) else {}
        for lane, snapshot in snapshots.items():
            if isinstance(snapshot, Mapping):
                current = evidence.get(str(lane), {})
                source_chain = list(snapshot.get("source_chain") or [])
                source_chain.append("strategy_lab_variant_batch_runner")
                evidence[str(lane)] = {**current, **dict(snapshot), "source_chain": list(dict.fromkeys(source_chain))}
    if "BETRAYAL_INVERSE_LANES" in (batch.get("lab_only_candidates") or []):
        evidence.setdefault(
            "BETRAYAL_INVERSE_LANES",
            {
                "sample_count": None,
                "win_rate_pct": None,
                "avg_pnl_pct": None,
                "evidence_status": "LAB_ONLY_SOURCE_CHAIN_REQUIRED",
                "source_chain": ["strategy_evidence_registry", "strategy_lab_variant_batch_runner"],
            },
        )
    return evidence


def _adapter_results(rows: Sequence[Mapping[str, Any]], selected_adapter_ids: set[str]) -> list[dict[str, Any]]:
    results = []
    for adapter_id in ADAPTER_IDS:
        if adapter_id not in selected_adapter_ids:
            continue
        adapter_rows = [row for row in rows if row.get("adapter_id") == adapter_id]
        results.append(_adapter_packet(adapter_id, [], adapter_rows))
    return results


def _adapter_packet(
    adapter_id: str,
    adapter_results: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    adapter_rows = [row for row in rows if row.get("adapter_id") == adapter_id] if adapter_results else list(rows)
    candidate_lanes = list(dict.fromkeys(str(row.get("lane_key")) for row in adapter_rows if row.get("lane_key")))
    return {
        "adapter_id": adapter_id,
        "implemented": bool(adapter_rows),
        "row_count": len(adapter_rows),
        "ready_rows": sum(1 for row in adapter_rows if row.get("evidence_status") == ADAPTER_READY),
        "needs_source_data_rows": sum(1 for row in adapter_rows if row.get("evidence_status") == ADAPTER_NEEDS_SOURCE_DATA),
        "lab_only_rows": sum(1 for row in adapter_rows if row.get("evidence_status") == LAB_ONLY or _derived_bool(row, "lab_only")),
        "watch_only_rows": sum(1 for row in adapter_rows if row.get("evidence_status") == WATCH_ONLY or _derived_bool(row, "watch_only")),
        "candidate_lanes": candidate_lanes,
        "live_permission": False,
        "tiny_live_eligible_now": False,
        "promotion_event_written": False,
        "risk_contract_write_required": False,
        "scheduler_required": False,
        "lab_only": True if adapter_id == "betrayal_inverse_lab" else None,
        "watch_only": True if adapter_id == "watch_88m" else None,
    }


def _adapter_counts(rows: Sequence[Mapping[str, Any]], adapter_results: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "implemented_adapter_count": len(adapter_results),
        "normalized_evidence_row_count": len(rows),
        "candidate_lane_count": len({row.get("lane_key") for row in rows}),
        "rows_ready": sum(1 for row in rows if row.get("evidence_status") == ADAPTER_READY),
        "rows_needing_source_data": sum(1 for row in rows if row.get("evidence_status") == ADAPTER_NEEDS_SOURCE_DATA),
        "lab_only_rows": sum(1 for row in rows if row.get("evidence_status") == LAB_ONLY or _derived_bool(row, "lab_only")),
        "watch_only_rows": sum(1 for row in rows if row.get("evidence_status") == WATCH_ONLY or _derived_bool(row, "watch_only")),
        "live_permission_count": sum(1 for row in rows if row.get("live_permission") is True),
        "promotion_event_written_count": sum(1 for row in rows if row.get("promotion_event_written") is True),
        "risk_contract_write_required_count": sum(1 for row in rows if row.get("risk_contract_write_required") is True),
        "scheduler_required_count": sum(1 for row in rows if row.get("scheduler_required") is True),
    }


def _implemented_adapter_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    adapter_counts = Counter(str(row.get("adapter_id")) for row in rows)
    return {
        "implemented_adapters": [adapter_id for adapter_id in ADAPTER_IDS if adapter_counts.get(adapter_id, 0) > 0],
        "adapter_row_counts": {adapter_id: adapter_counts.get(adapter_id, 0) for adapter_id in ADAPTER_IDS},
        "rows_ready": sum(1 for row in rows if row.get("evidence_status") == ADAPTER_READY),
        "rows_needing_source_data": sum(1 for row in rows if row.get("evidence_status") == ADAPTER_NEEDS_SOURCE_DATA),
        "lab_only_rows": sum(1 for row in rows if row.get("evidence_status") == LAB_ONLY or _derived_bool(row, "lab_only")),
        "watch_only_rows": sum(1 for row in rows if row.get("evidence_status") == WATCH_ONLY or _derived_bool(row, "watch_only")),
        "live_permission_count": sum(1 for row in rows if row.get("live_permission") is True),
        "promotion_event_written_count": sum(1 for row in rows if row.get("promotion_event_written") is True),
        "risk_contract_write_required_count": sum(1 for row in rows if row.get("risk_contract_write_required") is True),
        "scheduler_required_count": sum(1 for row in rows if row.get("scheduler_required") is True),
    }


def _remaining_adapter_gaps(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    gap_counts: Counter[str] = Counter()
    for row in rows:
        for blocker in row.get("blockers") or []:
            if str(blocker).startswith("missing_"):
                gap_counts[str(blocker)] += 1
    required = {
        "missing_raw_anchor_timeseries": "Raw MA/WMA200 and close-vs-anchor timeseries are not attached to Strategy Lab packets.",
        "missing_exit_outcome_comparison": "Comparable fixed TP/SL, early, late, trailing, partial, and invalidation outcome rows are not yet present.",
        "missing_betrayal_source_chain_data": "Betrayal original/inverse source-chain and exact risk mapping remain lab-only source-data gaps.",
        "missing_mae_mfe": "MAE/MFE adverse excursion fields are not available in current packets.",
    }
    gaps = [
        {"gap_id": gap_id, "row_count": gap_counts.get(gap_id, 0), "reason": reason}
        for gap_id, reason in required.items()
        if gap_counts.get(gap_id, 0) > 0 or gap_id in {"missing_betrayal_source_chain_data", "missing_mae_mfe"}
    ]
    return {
        "gaps": gaps,
        "do_not_fake_data": True,
        "adapters_emit_needs_source_data_when_raw_inputs_are_missing": True,
    }


def _packet_blockers(
    *,
    selected_adapter_ids: set[str],
    rows: Sequence[Mapping[str, Any]],
    feed: Mapping[str, Any],
    promotion: Mapping[str, Any],
    batch: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not selected_adapter_ids:
        blockers.append("no_adapter_selected")
    if not rows:
        blockers.append("no_adapter_rows_built")
    if feed.get("candidate_feed_expansion_status") != R326_READY:
        blockers.append("source_r326_candidate_feed_expansion_not_ready")
    if promotion.get("promotion_review_status") != R325_READY:
        blockers.append("source_r325_promotion_review_not_ready")
    if batch.get("batch_runner_status") != R324_READY:
        blockers.append("source_r324_batch_runner_not_ready")
    return blockers


def _selected_adapter_ids(adapter: str) -> set[str]:
    if adapter == "all":
        return set(ADAPTER_IDS)
    if adapter not in ADAPTER_IDS:
        return set()
    return {adapter}


def _parse_lane(lane_key: str) -> tuple[str | None, str | None, str | None, str | None]:
    parts = lane_key.split("|")
    if len(parts) >= 4:
        return parts[0], parts[1], parts[2], parts[3]
    return lane_key, None, None, None


def _derived_bool(row: Mapping[str, Any], key: str) -> bool:
    derived = row.get("derived_fields") if isinstance(row.get("derived_fields"), Mapping) else {}
    return derived.get(key) is True


def _latest_feed_or_build(
    log_dir: Path,
    now: datetime,
    min_sample_count: int,
    preferred_sample_count: int,
    promotion: Mapping[str, Any],
    batch: Mapping[str, Any],
) -> dict[str, Any]:
    records = load_strategy_lab_candidate_feed_expansion_records(log_dir=log_dir, limit=1)
    if records:
        return records[-1]
    return build_strategy_lab_candidate_feed_expansion(
        log_dir=log_dir,
        write=False,
        now=now,
        min_sample_count=min_sample_count,
        preferred_sample_count=preferred_sample_count,
        promotion_review_packet=promotion,
        batch_runner_packet=batch,
    )


def _latest_promotion_or_build(log_dir: Path, now: datetime, min_sample_count: int, preferred_sample_count: int) -> dict[str, Any]:
    records = load_strategy_lab_promotion_review_packet_records(log_dir=log_dir, limit=1)
    if records:
        return records[-1]
    return build_strategy_lab_promotion_review_packet(
        log_dir=log_dir,
        write=False,
        now=now,
        min_sample_count=min_sample_count,
        preferred_sample_count=preferred_sample_count,
    )


def _latest_batch_or_build(log_dir: Path, now: datetime, min_sample_count: int, preferred_sample_count: int) -> dict[str, Any]:
    records = load_strategy_lab_variant_batch_runner_records(log_dir=log_dir, limit=1)
    if records:
        return records[-1]
    return build_strategy_lab_variant_batch_runner(
        log_dir=log_dir,
        write=False,
        now=now,
        min_sample_count=min_sample_count,
        preferred_sample_count=preferred_sample_count,
    )


def _recommended_r329_path() -> dict[str, Any]:
    return {
        "phase": "R329 Strategy Lab Adapter Output Batch Execution Packet",
        "purpose": "Run deterministic batch comparisons over R328 normalized evidence rows.",
        "input_ledger": LEDGER_FILENAME,
        "write_promotion_events": False,
        "write_risk_contracts": False,
        "live_permission": False,
    }


def _recommended_r330_path() -> dict[str, Any]:
    return {
        "phase": "R330 Human-Reviewed Observed Expansion Promotion Gate",
        "purpose": "Alter observed expansion only after human review of R329 comparisons.",
        "can_later_alter_observed_expansion_after_human_review": True,
        "tiny_live_separately_gated": True,
        "live_permission": False,
    }


def _recommended_tiny_live_path() -> list[str]:
    return [
        "First Tiny Live remains BTCUSDT|44m|long|ladder_close_50_618.",
        "R328 does not change Tiny Live, does not arm, does not submit, and does not create a final command.",
        "Tiny Live remains separately gated from Strategy Lab adapter evidence.",
        "Future Tiny Live still requires human approval, exact risk contract, real candidate detection, and final gate clearance.",
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
        "docs/hammer_radar/live_readiness/R326_CANDIDATE_FEED_EXPANSION_FOR_STRATEGY_LAB_VARIANTS.md",
        "docs/hammer_radar/live_readiness/R325_STRATEGY_LAB_PROMOTION_REVIEW_PACKET.md",
        "docs/hammer_radar/live_readiness/R324_STRATEGY_LAB_VARIANT_BATCH_RUNNER.md",
        "docs/hammer_radar/live_readiness/R305_STRATEGY_LAB_VARIANT_TEST_PACK.md",
        "docs/hammer_radar/live_readiness/R304_PAPER_REFRESH_DURABILITY_AND_STRATEGY_LAB_PREVIEW.md",
        "src/app/hammer_radar/operator/strategy_lab_candidate_feed_expansion.py",
        "src/app/hammer_radar/operator/strategy_lab_promotion_review_packet.py",
        "src/app/hammer_radar/operator/strategy_lab_variant_batch_runner.py",
        "src/app/hammer_radar/operator/strategy_lab_variant_test_pack.py",
        "src/app/hammer_radar/operator/strategy_lab_preview.py",
        "src/app/hammer_radar/operator/paper_refresh_scheduler.py",
        "src/app/hammer_radar/operator/inspect.py",
        str(log_dir / "strategy_lab_candidate_feed_expansion.ndjson"),
        str(log_dir / "strategy_lab_promotion_review_packet.ndjson"),
        str(log_dir / "strategy_lab_variant_batch_runner.ndjson"),
        str(log_dir / "strategy_lab_variant_test_pack.ndjson"),
        str(log_dir / "strategy_evidence_registry.ndjson"),
    ]


def _sanitize(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack")
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--adapter", choices=("all", *ADAPTER_IDS), default="all")
    parser.add_argument("--min-sample-count", type=int, default=30)
    parser.add_argument("--preferred-sample-count", type=int, default=50)
    args = parser.parse_args(argv)

    payload = build_strategy_lab_evidence_adapter_pack(
        log_dir=args.log_dir,
        write=not args.no_write,
        adapter=args.adapter,
        min_sample_count=args.min_sample_count,
        preferred_sample_count=args.preferred_sample_count,
    )
    if args.text:
        print(format_evidence_adapter_pack_text(payload))
    else:
        print(format_evidence_adapter_pack_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
