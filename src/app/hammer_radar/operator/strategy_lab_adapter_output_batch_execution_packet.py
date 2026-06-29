"""R329 read-only Strategy Lab adapter output batch execution packet."""

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
    BASELINE_LANE,
    FEED_IDS,
    REVIEW_READY_LANES,
    SAFETY,
)
from src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack import (
    ADAPTER_NEEDS_SOURCE_DATA,
    ADAPTER_READY,
    BLOCKED as R328_BLOCKED,
    LAB_ONLY,
    READY as R328_READY,
    WATCH_ONLY,
    build_strategy_lab_evidence_adapter_pack,
    load_strategy_lab_evidence_adapter_pack_records,
)

EVENT_TYPE = "R329_STRATEGY_LAB_ADAPTER_OUTPUT_BATCH_EXECUTION_PACKET"
CREATED_BY_PHASE = "R329_STRATEGY_LAB_ADAPTER_OUTPUT_BATCH_EXECUTION_PACKET"
LEDGER_FILENAME = "strategy_lab_adapter_output_batch_execution_packet.ndjson"

READY = "STRATEGY_LAB_ADAPTER_BATCH_EXECUTION_READY"
BLOCKED = "STRATEGY_LAB_ADAPTER_BATCH_EXECUTION_BLOCKED"

READINESS_READY_FOR_COMPARISON = "READY_FOR_COMPARISON"
READINESS_NEEDS_SOURCE_DATA_CAPTURE = "NEEDS_SOURCE_DATA_CAPTURE"
READINESS_LAB_ONLY_REVIEW_BLOCKED = "LAB_ONLY_REVIEW_BLOCKED"
READINESS_WATCH_ONLY_REVIEW = "WATCH_ONLY_REVIEW"

ADAPTER_IDS = FEED_IDS

CAPTURE_PRIORITY_IDS = (
    "short_capture_improvement_adapter",
    "exit_variant_comparison_adapter",
    "ma_wma_anchor_enrichment_adapter",
    "review_ready_enrichment_adapter",
    "near_miss_variant_capture_adapter",
    "betrayal_inverse_source_chain_adapter",
    "watch_88m_durability_adapter",
)

OBSERVED_EXPANSION_REVIEW_INPUTS = REVIEW_READY_LANES


def build_strategy_lab_adapter_output_batch_execution_packet(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    adapter: str = "all",
    min_ready_rows: int = 1,
    include_source_data_gaps: bool = True,
    include_lab_only: bool = True,
    include_watch_only: bool = True,
    evidence_adapter_pack: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    source = (
        dict(evidence_adapter_pack)
        if isinstance(evidence_adapter_pack, Mapping)
        else _latest_evidence_adapter_pack_or_build(resolved_log_dir, generated_at, adapter)
    )
    selected_adapter_ids = _selected_adapter_ids(adapter)
    source_rows = list(source.get("normalized_evidence_rows") or [])
    rows = _filter_rows(
        source_rows,
        selected_adapter_ids=selected_adapter_ids,
        include_lab_only=include_lab_only,
        include_watch_only=include_watch_only,
    )
    input_summary = _input_row_summary(source_rows)
    family_summaries = _adapter_family_summaries(rows, selected_adapter_ids)
    ready_rankings = _ready_row_rankings(rows)
    gap_rankings = _source_data_gap_rankings(rows) if include_source_data_gaps else []
    usefulness = _adapter_usefulness_ranking(family_summaries)
    blockers = _packet_blockers(
        selected_adapter_ids=selected_adapter_ids,
        rows=rows,
        ready_rows=input_summary["ready_rows"],
        min_ready_rows=min_ready_rows,
        source=source,
    )
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "adapter_output_batch_execution_packet_id": f"r329_strategy_lab_adapter_output_batch_execution_packet_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_lab_adapter_output_batch_execution_packet_path": str(packet_path(resolved_log_dir)),
        "adapter_batch_execution_status": BLOCKED if blockers else READY,
        "blockers": blockers,
        "source_evidence_adapter_pack_status": source.get("evidence_adapter_pack_status") or R328_BLOCKED,
        "source_candidate_feed_expansion_status": source.get("source_candidate_feed_expansion_status"),
        "first_tiny_live_lane": source.get("first_tiny_live_lane") or BASELINE_LANE,
        "first_live_lane_change_allowed": False,
        "selected_adapter": adapter,
        "include_source_data_gaps": include_source_data_gaps,
        "include_lab_only": include_lab_only,
        "include_watch_only": include_watch_only,
        "input_row_summary": input_summary,
        "adapter_family_summaries": family_summaries,
        "ready_row_rankings": ready_rankings,
        "source_data_gap_rankings": gap_rankings,
        "lab_only_summary": _lab_only_summary(source_rows),
        "watch_only_summary": _watch_only_summary(source_rows),
        "adapter_usefulness_ranking": usefulness,
        "recommended_capture_priorities": _recommended_capture_priorities(family_summaries),
        "recommended_observed_expansion_review_inputs": _observed_expansion_review_inputs(),
        "recommended_r330_path": _recommended_r330_path(),
        "recommended_r331_path": _recommended_r331_path(),
        "recommended_tiny_live_path": _recommended_tiny_live_path(source.get("first_tiny_live_lane") or BASELINE_LANE),
        "betrayal_inverse_lab_only_summary": _betrayal_lab_only_summary(source_rows),
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


def load_strategy_lab_adapter_output_batch_execution_packet_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(packet_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def packet_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_adapter_output_batch_execution_packet_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_adapter_output_batch_execution_packet_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R329 STRATEGY LAB ADAPTER OUTPUT BATCH EXECUTION PACKET",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        f"adapter_batch_execution_status: {payload.get('adapter_batch_execution_status')}",
        "",
        "FIRST TINY LIVE LANE",
        f"first_tiny_live_lane: {payload.get('first_tiny_live_lane')}",
        f"first_live_lane_change_allowed: {payload.get('first_live_lane_change_allowed')}",
        "",
        "INPUT ROW SUMMARY",
    ]
    summary = payload.get("input_row_summary") if isinstance(payload.get("input_row_summary"), Mapping) else {}
    for key in (
        "normalized_evidence_row_count",
        "ready_rows",
        "rows_needing_source_data",
        "lab_only_rows",
        "watch_only_rows",
        "live_permission_count",
        "promotion_event_written_count",
        "risk_contract_write_required_count",
        "scheduler_required_count",
    ):
        lines.append(f"{key}: {summary.get(key)}")
    lines.extend(["", "ADAPTER USEFULNESS RANKING"])
    for row in payload.get("adapter_usefulness_ranking") or []:
        if isinstance(row, Mapping):
            lines.append(f"{row.get('rank')}. {row.get('adapter_id')} score={row.get('usefulness_score')} action={row.get('recommended_next_action')}")
    lines.extend(["", "SOURCE-DATA GAP RANKING"])
    for row in payload.get("source_data_gap_rankings") or []:
        if isinstance(row, Mapping):
            lines.append(f"{row.get('rank')}. {row.get('adapter_id')} gap={row.get('gap_id')} score={row.get('source_data_gap_score')} rows={row.get('row_count')}")
    lines.extend(["", "RECOMMENDED CAPTURE PRIORITIES"])
    for row in payload.get("recommended_capture_priorities") or []:
        if isinstance(row, Mapping):
            lines.append(f"{row.get('priority')}. {row.get('adapter')} action={row.get('recommended_next_action')} lab_only={row.get('lab_only')}")
    lines.extend(["", "OBSERVED EXPANSION REVIEW INPUTS"])
    for row in payload.get("recommended_observed_expansion_review_inputs") or []:
        if isinstance(row, Mapping):
            lines.append(f"{row.get('lane_key')} live_permission={row.get('live_permission')} final_command_available={row.get('final_command_available')}")
    lines.extend(["", "BETRAYAL LAB-ONLY SUMMARY"])
    betrayal = payload.get("betrayal_inverse_lab_only_summary") if isinstance(payload.get("betrayal_inverse_lab_only_summary"), Mapping) else {}
    for key in (
        "lab_only",
        "standard_55_policy_applies",
        "live_permission",
        "tiny_live_eligible_now",
        "source_chain_required",
        "exact_risk_mapping_required",
        "stale_shadow_outcomes_forbidden",
        "excluded_from_standard_ranking",
        "recommended_next_action",
    ):
        lines.append(f"{key}: {betrayal.get(key)}")
    lines.extend(["", "WATCH-ONLY SUMMARY"])
    watch = payload.get("watch_only_summary") if isinstance(payload.get("watch_only_summary"), Mapping) else {}
    lines.append(f"watch_only_rows: {watch.get('watch_only_rows')}")
    lines.append(f"candidate_lanes: {','.join(watch.get('candidate_lanes') or []) or 'none'}")
    lines.extend(["", "RECOMMENDED R330/R331"])
    lines.append(str(payload.get("recommended_r330_path")))
    lines.append(str(payload.get("recommended_r331_path")))
    lines.extend(["", "TINY LIVE PATH"])
    for item in payload.get("recommended_tiny_live_path") or []:
        lines.append(str(item))
    lines.extend(["", "SAFETY FLAGS"])
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    for key in SAFETY:
        lines.append(f"{key}: {safety.get(key)}")
    return "\n".join(lines)


def _latest_evidence_adapter_pack_or_build(log_dir: Path, now: datetime, adapter: str) -> dict[str, Any]:
    records = load_strategy_lab_evidence_adapter_pack_records(log_dir=log_dir, limit=1)
    if records:
        return records[-1]
    return build_strategy_lab_evidence_adapter_pack(log_dir=log_dir, write=False, now=now, adapter=adapter)


def _selected_adapter_ids(adapter: str) -> set[str]:
    if adapter == "all":
        return set(ADAPTER_IDS)
    if adapter not in ADAPTER_IDS:
        return set()
    return {adapter}


def _filter_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    selected_adapter_ids: set[str],
    include_lab_only: bool,
    include_watch_only: bool,
) -> list[Mapping[str, Any]]:
    selected: list[Mapping[str, Any]] = []
    for row in rows:
        if row.get("adapter_id") not in selected_adapter_ids:
            continue
        if not include_lab_only and _is_lab_only(row):
            continue
        if not include_watch_only and _is_watch_only(row):
            continue
        selected.append(row)
    return selected


def _input_row_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "normalized_evidence_row_count": len(rows),
        "ready_rows": sum(1 for row in rows if row.get("evidence_status") == ADAPTER_READY),
        "rows_needing_source_data": sum(1 for row in rows if row.get("evidence_status") == ADAPTER_NEEDS_SOURCE_DATA),
        "lab_only_rows": sum(1 for row in rows if _is_lab_only(row)),
        "watch_only_rows": sum(1 for row in rows if _is_watch_only(row)),
        "live_permission_count": sum(1 for row in rows if row.get("live_permission") is True),
        "promotion_event_written_count": sum(1 for row in rows if row.get("promotion_event_written") is True),
        "risk_contract_write_required_count": sum(1 for row in rows if row.get("risk_contract_write_required") is True),
        "scheduler_required_count": sum(1 for row in rows if row.get("scheduler_required") is True),
    }


def _adapter_family_summaries(rows: Sequence[Mapping[str, Any]], selected_adapter_ids: set[str]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for adapter_id in ADAPTER_IDS:
        if adapter_id not in selected_adapter_ids:
            continue
        adapter_rows = [row for row in rows if row.get("adapter_id") == adapter_id]
        candidate_lanes = list(dict.fromkeys(str(row.get("lane_key")) for row in adapter_rows if row.get("lane_key")))
        variant_families = Counter(str(row.get("variant_family")) for row in adapter_rows if row.get("variant_family"))
        ready_rows = [row for row in adapter_rows if row.get("evidence_status") == ADAPTER_READY]
        needs_rows = [row for row in adapter_rows if row.get("evidence_status") == ADAPTER_NEEDS_SOURCE_DATA]
        lab_only_rows = [row for row in adapter_rows if _is_lab_only(row)]
        watch_only_rows = [row for row in adapter_rows if _is_watch_only(row)]
        readiness_status = _readiness_status(
            ready_rows=ready_rows,
            needs_rows=needs_rows,
            lab_only_rows=lab_only_rows,
            watch_only_rows=watch_only_rows,
        )
        usefulness_score = _usefulness_score(adapter_id, ready_rows, needs_rows, candidate_lanes, lab_only_rows, watch_only_rows)
        source_data_gap_score = _source_data_gap_score(adapter_id, needs_rows, lab_only_rows)
        summaries.append(
            {
                "adapter_id": adapter_id,
                "total_rows": len(adapter_rows),
                "ready_rows": len(ready_rows),
                "needs_source_data_rows": len(needs_rows),
                "lab_only_rows": len(lab_only_rows),
                "watch_only_rows": len(watch_only_rows),
                "candidate_lanes": candidate_lanes,
                "dominant_variant_families": [family for family, _ in variant_families.most_common()],
                "readiness_status": readiness_status,
                "usefulness_score": usefulness_score,
                "source_data_gap_score": source_data_gap_score,
                "recommended_next_action": _recommended_next_action(adapter_id, readiness_status),
                "live_permission": False,
                "promotion_event_written": False,
                "risk_contract_write_required": False,
                "scheduler_required": False,
            }
        )
    return summaries


def _readiness_status(
    *,
    ready_rows: Sequence[Mapping[str, Any]],
    needs_rows: Sequence[Mapping[str, Any]],
    lab_only_rows: Sequence[Mapping[str, Any]],
    watch_only_rows: Sequence[Mapping[str, Any]],
) -> str:
    if lab_only_rows:
        return READINESS_LAB_ONLY_REVIEW_BLOCKED
    if watch_only_rows and not ready_rows:
        return READINESS_WATCH_ONLY_REVIEW
    if ready_rows:
        return READINESS_READY_FOR_COMPARISON
    if needs_rows:
        return READINESS_NEEDS_SOURCE_DATA_CAPTURE
    return READINESS_NEEDS_SOURCE_DATA_CAPTURE


def _usefulness_score(
    adapter_id: str,
    ready_rows: Sequence[Mapping[str, Any]],
    needs_rows: Sequence[Mapping[str, Any]],
    candidate_lanes: Sequence[str],
    lab_only_rows: Sequence[Mapping[str, Any]],
    watch_only_rows: Sequence[Mapping[str, Any]],
) -> int:
    score = len(ready_rows) * 5 + len(candidate_lanes) * 2
    if adapter_id == "capture_8m_short":
        score += 22
    if adapter_id == "review_ready_enrichment":
        score += 18
    if adapter_id == "near_miss_13m":
        score += 14
    if any("13m" in lane for lane in candidate_lanes):
        score += 8
    if any("8m|short" in lane for lane in candidate_lanes):
        score += 12
    if any(lane in OBSERVED_EXPANSION_REVIEW_INPUTS for lane in candidate_lanes):
        score += 10
    score += min(len(needs_rows), 10)
    if lab_only_rows:
        score -= 15
    if watch_only_rows:
        score -= 8
    return max(score, 0)


def _source_data_gap_score(
    adapter_id: str,
    needs_rows: Sequence[Mapping[str, Any]],
    lab_only_rows: Sequence[Mapping[str, Any]],
) -> int:
    score = len(needs_rows) * 3
    blockers = {str(blocker) for row in needs_rows for blocker in row.get("blockers") or []}
    if "missing_exit_outcome_comparison" in blockers:
        score += 22
    if "missing_raw_anchor_timeseries" in blockers:
        score += 18
    if "missing_mae_mfe" in blockers:
        score += 16
    if adapter_id == "review_ready_enrichment":
        score += 18
    if adapter_id == "capture_8m_short":
        score += 12
    if adapter_id == "near_miss_13m":
        score += 10
    if adapter_id == "betrayal_inverse_lab" or lab_only_rows:
        score += 95
    return score


def _recommended_next_action(adapter_id: str, readiness_status: str) -> str:
    if adapter_id == "betrayal_inverse_lab":
        return "CAPTURE_LAB_ONLY_SOURCE_CHAIN_DATA"
    if adapter_id == "watch_88m":
        return "KEEP_WATCH_ONLY_AND_CAPTURE_DURABILITY"
    if adapter_id == "exits":
        return "CAPTURE_EXIT_VARIANT_COMPARISON_DATA"
    if adapter_id == "ma_wma_anchor":
        return "CAPTURE_ANCHOR_CONFLUENCE_SOURCE_DATA"
    if adapter_id == "capture_8m_short":
        return "COMPARE_READY_ROWS_AND_CAPTURE_MISSING_EXIT_ROW"
    if adapter_id == "review_ready_enrichment":
        return "ENRICH_REVIEW_READY_ROWS_BEFORE_OBSERVED_EXPANSION_REVIEW"
    if adapter_id == "near_miss_13m":
        return "COMPARE_NEAR_MISS_REPAIR_ROWS_AND_CAPTURE_EXIT_GAPS"
    return "CAPTURE_SOURCE_DATA" if readiness_status == READINESS_NEEDS_SOURCE_DATA_CAPTURE else "COMPARE_READY_ROWS"


def _ready_row_rankings(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rankings: list[dict[str, Any]] = []
    for row in rows:
        if row.get("evidence_status") != ADAPTER_READY:
            continue
        adapter_id = str(row.get("adapter_id"))
        lane_key = str(row.get("lane_key"))
        score = 10
        if adapter_id == "capture_8m_short":
            score += 30
        if adapter_id == "review_ready_enrichment":
            score += 25
        if adapter_id == "near_miss_13m":
            score += 20
        if "8m|short" in lane_key:
            score += 15
        if lane_key in OBSERVED_EXPANSION_REVIEW_INPUTS:
            score += 12
        if "13m" in lane_key:
            score += 8
        rankings.append(
            {
                "adapter_id": adapter_id,
                "row_id": row.get("row_id"),
                "lane_key": lane_key,
                "variant_family": row.get("variant_family"),
                "variant_name": row.get("variant_name"),
                "ready_row_score": score,
                "live_permission": False,
                "promotion_event_written": False,
                "risk_contract_write_required": False,
            }
        )
    rankings.sort(key=lambda item: (-int(item["ready_row_score"]), str(item["adapter_id"]), str(item["row_id"])))
    return [{**item, "rank": rank} for rank, item in enumerate(rankings, start=1)]


def _source_data_gap_rankings(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        if row.get("evidence_status") == ADAPTER_NEEDS_SOURCE_DATA:
            for blocker in row.get("blockers") or []:
                if str(blocker).startswith("missing_"):
                    grouped.setdefault((str(row.get("adapter_id")), str(blocker)), []).append(row)
        elif _is_lab_only(row) and row.get("adapter_id") == "betrayal_inverse_lab":
            grouped.setdefault(("betrayal_inverse_lab", "missing_betrayal_source_chain_data"), []).append(row)
    rankings: list[dict[str, Any]] = []
    for (adapter_id, gap_id), gap_rows in grouped.items():
        lanes = list(dict.fromkeys(str(row.get("lane_key")) for row in gap_rows if row.get("lane_key")))
        score = len(gap_rows) * 3
        if gap_id == "missing_exit_outcome_comparison":
            score += 30
        if gap_id == "missing_raw_anchor_timeseries":
            score += 24
        if gap_id == "missing_mae_mfe":
            score += 20
        if gap_id == "missing_betrayal_source_chain_data":
            score += 85
        if adapter_id == "review_ready_enrichment":
            score += 18
        if adapter_id == "capture_8m_short":
            score += 14
        rankings.append(
            {
                "adapter_id": adapter_id,
                "gap_id": gap_id,
                "row_count": len(gap_rows),
                "candidate_lanes": lanes,
                "source_data_gap_score": score,
                "blocks_high_value_candidates": _blocks_high_value_candidates(adapter_id, lanes, gap_id),
                "recommended_next_action": _gap_recommended_action(adapter_id, gap_id),
                "live_permission": False,
                "promotion_event_written": False,
                "risk_contract_write_required": False,
            }
        )
    rankings.sort(key=lambda item: (-int(item["source_data_gap_score"]), str(item["adapter_id"]), str(item["gap_id"])))
    return [{**item, "rank": rank} for rank, item in enumerate(rankings, start=1)]


def _adapter_usefulness_ranking(family_summaries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    standard = [summary for summary in family_summaries if summary.get("adapter_id") != "betrayal_inverse_lab"]
    ranked = sorted(standard, key=lambda item: (-int(item.get("usefulness_score") or 0), str(item.get("adapter_id"))))
    return [
        {
            "rank": rank,
            "adapter_id": item.get("adapter_id"),
            "usefulness_score": item.get("usefulness_score"),
            "ready_rows": item.get("ready_rows"),
            "candidate_lane_count": len(item.get("candidate_lanes") or []),
            "readiness_status": item.get("readiness_status"),
            "recommended_next_action": item.get("recommended_next_action"),
            "excluded_from_standard_ranking": False,
            "live_permission": False,
        }
        for rank, item in enumerate(ranked, start=1)
    ]


def _recommended_capture_priorities(family_summaries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_adapter = {str(summary.get("adapter_id")): summary for summary in family_summaries}
    mapping = {
        "short_capture_improvement_adapter": "capture_8m_short",
        "exit_variant_comparison_adapter": "exits",
        "ma_wma_anchor_enrichment_adapter": "ma_wma_anchor",
        "review_ready_enrichment_adapter": "review_ready_enrichment",
        "near_miss_variant_capture_adapter": "near_miss_13m",
        "betrayal_inverse_source_chain_adapter": "betrayal_inverse_lab",
        "watch_88m_durability_adapter": "watch_88m",
    }
    rows: list[dict[str, Any]] = []
    for priority, capture_adapter in enumerate(CAPTURE_PRIORITY_IDS, start=1):
        adapter_id = mapping[capture_adapter]
        summary = by_adapter.get(adapter_id, {})
        rows.append(
            {
                "priority": priority,
                "adapter": capture_adapter,
                "source_adapter_id": adapter_id,
                "lab_only": adapter_id == "betrayal_inverse_lab",
                "watch_only": adapter_id == "watch_88m",
                "recommended_next_action": summary.get("recommended_next_action") or _recommended_next_action(adapter_id, ""),
                "live_permission": False,
                "promotion_event_written": False,
                "risk_contract_write_required": False,
                "scheduler_required": False,
            }
        )
    return rows


def _observed_expansion_review_inputs() -> list[dict[str, Any]]:
    return [
        {
            "lane_key": lane,
            "review_scope": "observed expansion review only",
            "human_review_required": True,
            "tiny_live_change_allowed": False,
            "final_command_available": False,
            "live_permission": False,
            "promotion_event_written": False,
            "risk_contract_write_required": False,
        }
        for lane in OBSERVED_EXPANSION_REVIEW_INPUTS
    ]


def _lab_only_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    lab_rows = [row for row in rows if _is_lab_only(row)]
    return {
        "lab_only_rows": len(lab_rows),
        "candidate_lanes": list(dict.fromkeys(str(row.get("lane_key")) for row in lab_rows if row.get("lane_key"))),
        "standard_promotion_excluded": True,
        "live_permission": False,
    }


def _watch_only_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    watch_rows = [row for row in rows if _is_watch_only(row)]
    return {
        "watch_only_rows": len(watch_rows),
        "candidate_lanes": list(dict.fromkeys(str(row.get("lane_key")) for row in watch_rows if row.get("lane_key"))),
        "watch_only": True,
        "recommended_next_action": "KEEP_WATCH_ONLY_AND_CAPTURE_DURABILITY",
        "live_permission": False,
    }


def _betrayal_lab_only_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    betrayal_rows = [row for row in rows if row.get("adapter_id") == "betrayal_inverse_lab"]
    return {
        "adapter_id": "betrayal_inverse_lab",
        "row_count": len(betrayal_rows),
        "lab_only": True,
        "standard_55_policy_applies": False,
        "live_permission": False,
        "tiny_live_eligible_now": False,
        "source_chain_required": True,
        "exact_risk_mapping_required": True,
        "stale_shadow_outcomes_forbidden": True,
        "excluded_from_standard_ranking": True,
        "recommended_next_action": "CAPTURE_LAB_ONLY_SOURCE_CHAIN_DATA",
        "promotion_event_written": False,
        "risk_contract_write_required": False,
        "scheduler_required": False,
    }


def _blocks_high_value_candidates(adapter_id: str, lanes: Sequence[str], gap_id: str) -> bool:
    return (
        adapter_id in {"exits", "ma_wma_anchor", "review_ready_enrichment", "capture_8m_short", "betrayal_inverse_lab"}
        or gap_id in {"missing_exit_outcome_comparison", "missing_raw_anchor_timeseries", "missing_mae_mfe", "missing_betrayal_source_chain_data"}
        or any(lane in OBSERVED_EXPANSION_REVIEW_INPUTS or "8m|short" in lane for lane in lanes)
    )


def _gap_recommended_action(adapter_id: str, gap_id: str) -> str:
    if gap_id == "missing_exit_outcome_comparison":
        return "CAPTURE_EXIT_VARIANT_COMPARISON_DATA"
    if gap_id == "missing_raw_anchor_timeseries":
        return "CAPTURE_ANCHOR_CONFLUENCE_SOURCE_DATA"
    if gap_id == "missing_mae_mfe":
        return "CAPTURE_MAE_MFE_REVIEW_READY_ENRICHMENT_DATA"
    if gap_id == "missing_betrayal_source_chain_data" or adapter_id == "betrayal_inverse_lab":
        return "CAPTURE_LAB_ONLY_SOURCE_CHAIN_DATA"
    return "CAPTURE_MISSING_SOURCE_DATA"


def _recommended_r330_path() -> dict[str, Any]:
    return {
        "phase": "R330 Human-Reviewed Observed Expansion Promotion Gate",
        "purpose": "Human-reviewed observed expansion review after R329 adapter comparison.",
        "can_alter_observed_expansion_only_after_human_review": True,
        "tiny_live_separately_gated": True,
        "live_permission": False,
        "final_command_available": False,
    }


def _recommended_r331_path() -> dict[str, Any]:
    return {
        "phase": "R331 Strategy Lab Source Data Capture Adapter Implementation",
        "purpose": "Implement source-data capture for exits, anchors, MAE/MFE, and betrayal source chain.",
        "write_promotion_events": False,
        "write_risk_contracts": False,
        "live_permission": False,
    }


def _recommended_tiny_live_path(first_tiny_live_lane: str) -> list[str]:
    return [
        f"First Tiny Live remains {first_tiny_live_lane}.",
        "R329 compares Strategy Lab adapter rows only and does not alter Tiny Live.",
        "No final command is available from R329.",
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


def _packet_blockers(
    *,
    selected_adapter_ids: set[str],
    rows: Sequence[Mapping[str, Any]],
    ready_rows: int,
    min_ready_rows: int,
    source: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not selected_adapter_ids:
        blockers.append("no_adapter_selected")
    if not rows:
        blockers.append("no_adapter_rows_available")
    if source.get("evidence_adapter_pack_status") != R328_READY:
        blockers.append("source_r328_evidence_adapter_pack_not_ready")
    if ready_rows < min_ready_rows:
        blockers.append("min_ready_rows_not_met")
    return blockers


def _is_lab_only(row: Mapping[str, Any]) -> bool:
    derived = row.get("derived_fields") if isinstance(row.get("derived_fields"), Mapping) else {}
    return row.get("evidence_status") == LAB_ONLY or derived.get("lab_only") is True


def _is_watch_only(row: Mapping[str, Any]) -> bool:
    derived = row.get("derived_fields") if isinstance(row.get("derived_fields"), Mapping) else {}
    return row.get("evidence_status") == WATCH_ONLY or derived.get("watch_only") is True


def _source_surfaces(log_dir: Path) -> list[str]:
    return [
        "docs/hammer_radar/live_readiness/R328_STRATEGY_LAB_EVIDENCE_ADAPTER_IMPLEMENTATION_PACK.md",
        "docs/hammer_radar/live_readiness/R326_CANDIDATE_FEED_EXPANSION_FOR_STRATEGY_LAB_VARIANTS.md",
        "docs/hammer_radar/live_readiness/R325_STRATEGY_LAB_PROMOTION_REVIEW_PACKET.md",
        "docs/hammer_radar/live_readiness/R324_STRATEGY_LAB_VARIANT_BATCH_RUNNER.md",
        "src/app/hammer_radar/operator/strategy_lab_evidence_adapter_pack.py",
        "src/app/hammer_radar/operator/strategy_lab_candidate_feed_expansion.py",
        "src/app/hammer_radar/operator/strategy_lab_promotion_review_packet.py",
        "src/app/hammer_radar/operator/strategy_lab_variant_batch_runner.py",
        "src/app/hammer_radar/operator/inspect.py",
        str(log_dir / "strategy_lab_evidence_adapter_pack.ndjson"),
        str(log_dir / "strategy_lab_candidate_feed_expansion.ndjson"),
        str(log_dir / "strategy_lab_promotion_review_packet.ndjson"),
        str(log_dir / "strategy_lab_variant_batch_runner.ndjson"),
    ]


def _sanitize(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.app.hammer_radar.operator.strategy_lab_adapter_output_batch_execution_packet"
    )
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--adapter", choices=("all", *ADAPTER_IDS), default="all")
    parser.add_argument("--min-ready-rows", type=int, default=1)
    parser.add_argument("--include-source-data-gaps", action="store_true", default=True)
    parser.add_argument("--include-lab-only", action="store_true", default=True)
    parser.add_argument("--include-watch-only", action="store_true", default=True)
    args = parser.parse_args(argv)

    payload = build_strategy_lab_adapter_output_batch_execution_packet(
        log_dir=args.log_dir,
        write=not args.no_write,
        adapter=args.adapter,
        min_ready_rows=args.min_ready_rows,
        include_source_data_gaps=args.include_source_data_gaps,
        include_lab_only=args.include_lab_only,
        include_watch_only=args.include_watch_only,
    )
    if args.text:
        print(format_adapter_output_batch_execution_packet_text(payload))
    else:
        print(format_adapter_output_batch_execution_packet_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
