"""R332 read-only merge of Strategy Lab captured source-data into adapter rows."""

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
from src.app.hammer_radar.operator.strategy_lab_adapter_output_batch_execution_packet import (
    READY as R329_READY,
    build_strategy_lab_adapter_output_batch_execution_packet,
    load_strategy_lab_adapter_output_batch_execution_packet_records,
)
from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import BASELINE_LANE, SAFETY as BASE_SAFETY
from src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack import (
    ADAPTER_READY,
    LAB_ONLY,
    READY as R328_READY,
    WATCH_ONLY,
    build_strategy_lab_evidence_adapter_pack,
    load_strategy_lab_evidence_adapter_pack_records,
)
from src.app.hammer_radar.operator.strategy_lab_source_data_capture_adapter import (
    ADAPTER_IDS as CAPTURE_ADAPTER_IDS,
    PARTIAL as R331_PARTIAL,
    READY as R331_READY,
    SOURCE_LAB_ONLY,
    SOURCE_PENDING,
    SOURCE_READY,
    SOURCE_WATCH_ONLY,
    build_strategy_lab_source_data_capture_adapter,
    load_strategy_lab_source_data_capture_adapter_records,
)

EVENT_TYPE = "R332_STRATEGY_LAB_CAPTURED_SOURCE_DATA_MERGE_INTO_ADAPTER_ROWS"
CREATED_BY_PHASE = "R332_STRATEGY_LAB_CAPTURED_SOURCE_DATA_MERGE_INTO_ADAPTER_ROWS"
LEDGER_FILENAME = "strategy_lab_captured_source_data_merge.ndjson"

READY = "STRATEGY_LAB_CAPTURED_SOURCE_DATA_MERGE_READY"
PARTIAL = "STRATEGY_LAB_CAPTURED_SOURCE_DATA_MERGE_PARTIAL"
BLOCKED = "STRATEGY_LAB_CAPTURED_SOURCE_DATA_MERGE_BLOCKED"

MERGED_READY = "MERGED_READY"
MERGED_PENDING_SOURCE_DATA = "MERGED_PENDING_SOURCE_DATA"
MERGED_LAB_ONLY = "MERGED_LAB_ONLY"
MERGED_WATCH_ONLY = "MERGED_WATCH_ONLY"
MERGED_UNMATCHED_ADAPTER_ROW = "MERGED_UNMATCHED_ADAPTER_ROW"
MERGED_UNMATCHED_SOURCE_ROW = "MERGED_UNMATCHED_SOURCE_ROW"

ADAPTER_BY_CAPTURE_ADAPTER = {
    "exit_variant_comparison": "exits",
    "ma_wma_anchor_enrichment": "ma_wma_anchor",
    "review_ready_enrichment": "review_ready_enrichment",
    "short_capture_improvement": "capture_8m_short",
    "near_miss_variant_capture": "near_miss_13m",
    "betrayal_inverse_source_chain": "betrayal_inverse_lab",
    "watch_88m_durability": "watch_88m",
}
CAPTURE_ADAPTER_BY_ADAPTER = {adapter: capture for capture, adapter in ADAPTER_BY_CAPTURE_ADAPTER.items()}

SAFETY: dict[str, bool] = {
    **BASE_SAFETY,
    "observed_expansion_written": False,
    "synthetic_performance_created": False,
}


def build_strategy_lab_captured_source_data_merge(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    adapter: str = "all",
    include_lab_only: bool = True,
    include_watch_only: bool = True,
    include_pending: bool = True,
    max_rows: int = 1000,
    evidence_adapter_pack: Mapping[str, Any] | None = None,
    adapter_output_batch_execution_packet: Mapping[str, Any] | None = None,
    source_data_capture_adapter: Mapping[str, Any] | None = None,
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
    capture = (
        dict(source_data_capture_adapter)
        if isinstance(source_data_capture_adapter, Mapping)
        else _latest_capture_or_build(resolved_log_dir, generated_at, adapter, evidence, batch)
    )
    selected_capture_ids = _selected_capture_ids(adapter)
    adapter_rows = _filter_adapter_rows(
        evidence.get("normalized_evidence_rows") or [],
        selected_capture_ids=selected_capture_ids,
        include_lab_only=include_lab_only,
        include_watch_only=include_watch_only,
    )
    source_rows = _filter_source_rows(
        capture.get("normalized_source_data_rows") or [],
        selected_capture_ids=selected_capture_ids,
        include_lab_only=include_lab_only,
        include_watch_only=include_watch_only,
        include_pending=include_pending,
    )
    merged_rows = _merge_rows(adapter_rows=adapter_rows, source_rows=source_rows)[: max(max_rows, 0)]
    summaries = _adapter_merge_summaries(merged_rows)
    blockers = _packet_blockers(selected_capture_ids, merged_rows, evidence, batch, capture)
    status = _status(blockers, merged_rows)
    first_tiny_live_lane = (
        capture.get("first_tiny_live_lane")
        or evidence.get("first_tiny_live_lane")
        or batch.get("first_tiny_live_lane")
        or BASELINE_LANE
    )
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "captured_source_data_merge_id": f"r332_strategy_lab_captured_source_data_merge_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_lab_captured_source_data_merge_path": str(packet_path(resolved_log_dir)),
        "captured_source_data_merge_status": status,
        "blockers": blockers,
        "source_data_capture_status": capture.get("source_data_capture_status"),
        "source_adapter_batch_execution_status": batch.get("adapter_batch_execution_status"),
        "source_evidence_adapter_pack_status": evidence.get("evidence_adapter_pack_status"),
        "first_tiny_live_lane": first_tiny_live_lane,
        "first_live_lane_change_allowed": False,
        "selected_adapter": adapter,
        "include_lab_only": include_lab_only,
        "include_watch_only": include_watch_only,
        "include_pending": include_pending,
        "max_rows": max_rows,
        "merge_counts": _merge_counts(adapter_rows, source_rows, merged_rows),
        "merged_adapter_rows": merged_rows,
        "adapter_merge_summaries": summaries,
        "ready_merge_summary": _ready_merge_summary(merged_rows),
        "pending_merge_summary": _pending_merge_summary(merged_rows),
        "lab_only_merge_summary": _lab_only_merge_summary(merged_rows),
        "watch_only_merge_summary": _watch_only_merge_summary(merged_rows),
        "remaining_merge_gaps": _remaining_merge_gaps(merged_rows),
        "recommended_r333_path": _recommended_r333_path(),
        "recommended_r330_path": _recommended_r330_path(),
        "recommended_tiny_live_path": _recommended_tiny_live_path(first_tiny_live_lane),
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


def load_strategy_lab_captured_source_data_merge_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(packet_path(get_log_dir(log_dir, use_env=True)), limit=limit, max_bytes=8_000_000)


def packet_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_captured_source_data_merge_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_captured_source_data_merge_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R332 STRATEGY LAB CAPTURED SOURCE DATA MERGE INTO ADAPTER ROWS",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        f"captured_source_data_merge_status: {payload.get('captured_source_data_merge_status')}",
        "",
        "FIRST TINY LIVE LANE",
        f"first_tiny_live_lane: {payload.get('first_tiny_live_lane')}",
        f"first_live_lane_change_allowed: {payload.get('first_live_lane_change_allowed')}",
        "",
        "MERGE COUNTS",
    ]
    counts = payload.get("merge_counts") if isinstance(payload.get("merge_counts"), Mapping) else {}
    for key in (
        "adapter_rows_seen",
        "source_rows_seen",
        "merged_row_count",
        "merged_ready_rows",
        "merged_pending_rows",
        "merged_lab_only_rows",
        "merged_watch_only_rows",
        "unmatched_adapter_rows",
        "unmatched_source_rows",
        "synthetic_performance_created_count",
        "live_permission_count",
        "promotion_event_written_count",
        "risk_contract_write_required_count",
        "observed_expansion_written_count",
        "scheduler_required_count",
    ):
        lines.append(f"{key}: {counts.get(key)}")
    lines.extend(["", "ADAPTER MERGE SUMMARIES"])
    for row in payload.get("adapter_merge_summaries") or []:
        if isinstance(row, Mapping):
            lines.append(
                f"{row.get('adapter_id')}->{row.get('capture_adapter_id')}: rows={row.get('merged_row_count')} "
                f"ready={row.get('merged_ready_rows')} pending={row.get('merged_pending_rows')} "
                f"lab_only={row.get('merged_lab_only_rows')} watch_only={row.get('merged_watch_only_rows')} "
                f"unmatched_adapter={row.get('unmatched_adapter_rows')} unmatched_source={row.get('unmatched_source_rows')} "
                f"action={row.get('recommended_next_action')}"
            )
    ready = payload.get("ready_merge_summary") if isinstance(payload.get("ready_merge_summary"), Mapping) else {}
    lines.extend(["", "READY MERGE SUMMARY", f"ready_row_count: {ready.get('ready_row_count')}"])
    for row in ready.get("ready_rows") or []:
        if isinstance(row, Mapping):
            lines.append(f"{row.get('adapter_id')} {row.get('lane_key')} {row.get('variant_name')} live_permission={row.get('live_permission')}")
    pending = payload.get("pending_merge_summary") if isinstance(payload.get("pending_merge_summary"), Mapping) else {}
    lines.extend(["", "PENDING MERGE SUMMARY", f"pending_row_count: {pending.get('pending_row_count')}"])
    for row in pending.get("gaps") or []:
        if isinstance(row, Mapping):
            lines.append(f"{row.get('source_gap_id')}: rows={row.get('row_count')} lanes={','.join(row.get('affected_lanes') or [])}")
    lab = payload.get("lab_only_merge_summary") if isinstance(payload.get("lab_only_merge_summary"), Mapping) else {}
    lines.extend(["", "BETRAYAL LAB-ONLY SUMMARY"])
    for key in (
        "row_count",
        "betrayal_inverse_remains_lab_only",
        "standard_55_policy_applies",
        "source_chain_required",
        "exact_risk_mapping_required",
        "stale_shadow_outcomes_forbidden",
        "live_permission",
        "tiny_live_eligible_now",
    ):
        lines.append(f"{key}: {lab.get(key)}")
    watch = payload.get("watch_only_merge_summary") if isinstance(payload.get("watch_only_merge_summary"), Mapping) else {}
    lines.extend(["", "WATCH-ONLY SUMMARY"])
    for key in ("row_count", "watch_88m_remains_watch_only", "live_permission", "tiny_live_eligible_now"):
        lines.append(f"{key}: {watch.get(key)}")
    lines.extend(["", "RECOMMENDED R333/R330"])
    lines.append(str(payload.get("recommended_r333_path")))
    lines.append(str(payload.get("recommended_r330_path")))
    lines.extend(["", "TINY LIVE PATH"])
    for item in payload.get("recommended_tiny_live_path") or []:
        lines.append(str(item))
    lines.extend(["", "SAFETY FLAGS"])
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    for key in SAFETY:
        lines.append(f"{key}: {safety.get(key)}")
    return "\n".join(lines)


def _merge_rows(
    *,
    adapter_rows: Sequence[Mapping[str, Any]],
    source_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    adapter_by_row_id = {str(row.get("row_id")): row for row in adapter_rows if row.get("row_id")}
    adapter_by_key: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for row in adapter_rows:
        key = (str(row.get("adapter_id")), str(row.get("lane_key")), str(row.get("variant_name")))
        adapter_by_key[key] = row

    merged: list[dict[str, Any]] = []
    matched_adapter_ids: set[str] = set()
    for source in source_rows:
        adapter = adapter_by_row_id.get(str(source.get("source_row_id")))
        if not adapter:
            source_inputs = source.get("source_inputs") if isinstance(source.get("source_inputs"), Mapping) else {}
            adapter_id = str(source_inputs.get("source_adapter_id") or ADAPTER_BY_CAPTURE_ADAPTER.get(str(source.get("capture_adapter_id")), ""))
            variant_name = str(source_inputs.get("source_variant_name") or "")
            adapter = adapter_by_key.get((adapter_id, str(source.get("lane_key")), variant_name))
        if adapter and adapter.get("row_id"):
            matched_adapter_ids.add(str(adapter.get("row_id")))
        merged.append(_merged_row(adapter=adapter, source=source, unmatched_source=not bool(adapter)))

    for adapter in adapter_rows:
        if str(adapter.get("row_id")) in matched_adapter_ids:
            continue
        merged.append(_merged_row(adapter=adapter, source=None, unmatched_adapter=True))
    return merged


def _merged_row(
    *,
    adapter: Mapping[str, Any] | None,
    source: Mapping[str, Any] | None,
    unmatched_adapter: bool = False,
    unmatched_source: bool = False,
) -> dict[str, Any]:
    adapter = adapter or {}
    source = source or {}
    capture_adapter_id = str(source.get("capture_adapter_id") or CAPTURE_ADAPTER_BY_ADAPTER.get(str(adapter.get("adapter_id")), ""))
    adapter_id = str(adapter.get("adapter_id") or ADAPTER_BY_CAPTURE_ADAPTER.get(capture_adapter_id, ""))
    lane_key = str(source.get("lane_key") or adapter.get("lane_key") or "")
    timeframe = source.get("timeframe") or adapter.get("timeframe")
    side = source.get("side") or adapter.get("side")
    entry_mode = source.get("entry_mode") or adapter.get("entry_mode")
    variant_name = adapter.get("variant_name") or _source_variant_name(source)
    blockers = list(dict.fromkeys([*(adapter.get("blockers") or []), *(source.get("blockers") or [])]))
    merged_status = _merged_status(adapter, source, unmatched_adapter=unmatched_adapter, unmatched_source=unmatched_source)
    if merged_status == MERGED_UNMATCHED_ADAPTER_ROW:
        blockers.append("source_data_capture_row_missing")
    if merged_status == MERGED_UNMATCHED_SOURCE_ROW:
        blockers.append("adapter_row_missing")
    blockers = list(dict.fromkeys(str(blocker) for blocker in blockers if blocker))
    return {
        "merge_row_id": f"r332|{adapter_id or 'unmatched_adapter'}|{capture_adapter_id or 'unmatched_source'}|{lane_key}|{variant_name or source.get('capture_name')}",
        "adapter_row_id": adapter.get("row_id"),
        "source_row_id": source.get("source_row_id"),
        "adapter_id": adapter_id,
        "capture_adapter_id": capture_adapter_id,
        "lane_key": lane_key,
        "timeframe": timeframe,
        "side": side,
        "entry_mode": entry_mode,
        "variant_family": adapter.get("variant_family") or source.get("capture_family"),
        "variant_name": variant_name,
        "evidence_status_from_adapter": adapter.get("evidence_status"),
        "capture_status_from_source": source.get("capture_status"),
        "merged_status": merged_status,
        "source_gap_id": source.get("source_gap_id") or _adapter_source_gap(adapter),
        "adapter_input_fields": adapter.get("input_fields") or {},
        "source_capture_fields": {
            "capture_name": source.get("capture_name"),
            "capture_family": source.get("capture_family"),
            "source_inputs": source.get("source_inputs") or {},
            "derived_capture_fields": source.get("derived_capture_fields") or {},
        },
        "source_chain": _source_chain(adapter, source),
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


def _merged_status(
    adapter: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    unmatched_adapter: bool,
    unmatched_source: bool,
) -> str:
    if unmatched_adapter:
        return MERGED_UNMATCHED_ADAPTER_ROW
    if unmatched_source:
        return MERGED_UNMATCHED_SOURCE_ROW
    if source.get("capture_status") == SOURCE_LAB_ONLY or adapter.get("evidence_status") == LAB_ONLY:
        return MERGED_LAB_ONLY
    if source.get("capture_status") == SOURCE_WATCH_ONLY or adapter.get("evidence_status") == WATCH_ONLY:
        return MERGED_WATCH_ONLY
    if source.get("capture_status") == SOURCE_PENDING:
        return MERGED_PENDING_SOURCE_DATA
    if adapter.get("evidence_status") == ADAPTER_READY and source.get("capture_status") == SOURCE_READY:
        return MERGED_READY
    return MERGED_PENDING_SOURCE_DATA


def _merge_counts(
    adapter_rows: Sequence[Mapping[str, Any]],
    source_rows: Sequence[Mapping[str, Any]],
    merged_rows: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    return {
        "adapter_rows_seen": len(adapter_rows),
        "source_rows_seen": len(source_rows),
        "merged_row_count": len(merged_rows),
        "merged_ready_rows": _count_status(merged_rows, MERGED_READY),
        "merged_pending_rows": _count_status(merged_rows, MERGED_PENDING_SOURCE_DATA),
        "merged_lab_only_rows": _count_status(merged_rows, MERGED_LAB_ONLY),
        "merged_watch_only_rows": _count_status(merged_rows, MERGED_WATCH_ONLY),
        "unmatched_adapter_rows": _count_status(merged_rows, MERGED_UNMATCHED_ADAPTER_ROW),
        "unmatched_source_rows": _count_status(merged_rows, MERGED_UNMATCHED_SOURCE_ROW),
        "synthetic_performance_created_count": sum(1 for row in merged_rows if row.get("synthetic_performance_created") is True),
        "live_permission_count": sum(1 for row in merged_rows if row.get("live_permission") is True),
        "promotion_event_written_count": sum(1 for row in merged_rows if row.get("promotion_event_written") is True),
        "risk_contract_write_required_count": sum(1 for row in merged_rows if row.get("risk_contract_write_required") is True),
        "observed_expansion_written_count": sum(1 for row in merged_rows if row.get("observed_expansion_written") is True),
        "scheduler_required_count": sum(1 for row in merged_rows if row.get("scheduler_required") is True),
    }


def _adapter_merge_summaries(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for capture_adapter_id in CAPTURE_ADAPTER_IDS:
        adapter_id = ADAPTER_BY_CAPTURE_ADAPTER[capture_adapter_id]
        family_rows = [row for row in rows if row.get("capture_adapter_id") == capture_adapter_id or row.get("adapter_id") == adapter_id]
        gaps = Counter(str(row.get("source_gap_id")) for row in family_rows if row.get("source_gap_id"))
        summaries.append(
            {
                "adapter_id": adapter_id,
                "capture_adapter_id": capture_adapter_id,
                "candidate_lanes": list(dict.fromkeys(str(row.get("lane_key")) for row in family_rows if row.get("lane_key"))),
                "merged_row_count": len(family_rows),
                "merged_ready_rows": _count_status(family_rows, MERGED_READY),
                "merged_pending_rows": _count_status(family_rows, MERGED_PENDING_SOURCE_DATA),
                "merged_lab_only_rows": _count_status(family_rows, MERGED_LAB_ONLY),
                "merged_watch_only_rows": _count_status(family_rows, MERGED_WATCH_ONLY),
                "unmatched_adapter_rows": _count_status(family_rows, MERGED_UNMATCHED_ADAPTER_ROW),
                "unmatched_source_rows": _count_status(family_rows, MERGED_UNMATCHED_SOURCE_ROW),
                "dominant_gaps": [gap for gap, _ in gaps.most_common()],
                "recommended_next_action": _recommended_next_action(capture_adapter_id, family_rows),
                "live_permission": False,
                "promotion_event_written": False,
                "risk_contract_write_required": False,
                "observed_expansion_written": False,
                "scheduler_required": False,
            }
        )
    return summaries


def _ready_merge_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ready_rows = [row for row in rows if row.get("merged_status") == MERGED_READY]
    return {
        "ready_row_count": len(ready_rows),
        "ready_rows": [
            {
                "merge_row_id": row.get("merge_row_id"),
                "adapter_id": row.get("adapter_id"),
                "capture_adapter_id": row.get("capture_adapter_id"),
                "lane_key": row.get("lane_key"),
                "timeframe": row.get("timeframe"),
                "side": row.get("side"),
                "variant_name": row.get("variant_name"),
                "live_permission": False,
                "tiny_live_eligible_now": False,
            }
            for row in ready_rows
        ],
        "includes_8m_short_ready_rows": any(row.get("capture_adapter_id") == "short_capture_improvement" for row in ready_rows),
        "includes_13m_near_miss_ready_rows": any(row.get("capture_adapter_id") == "near_miss_variant_capture" for row in ready_rows),
        "includes_review_ready_enrichment_ready_rows": any(row.get("capture_adapter_id") == "review_ready_enrichment" for row in ready_rows),
        "live_permission": False,
    }


def _pending_merge_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pending_rows = [row for row in rows if row.get("merged_status") in {MERGED_PENDING_SOURCE_DATA, MERGED_UNMATCHED_ADAPTER_ROW, MERGED_UNMATCHED_SOURCE_ROW}]
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in pending_rows:
        grouped.setdefault(str(row.get("source_gap_id") or row.get("merged_status")), []).append(row)
    return {
        "pending_row_count": len(pending_rows),
        "gaps": [
            {
                "source_gap_id": gap_id,
                "row_count": len(gap_rows),
                "affected_lanes": list(dict.fromkeys(str(row.get("lane_key")) for row in gap_rows if row.get("lane_key"))),
                "do_not_fake_data": True,
            }
            for gap_id, gap_rows in sorted(grouped.items())
        ],
        "do_not_fake_data": True,
    }


def _lab_only_merge_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    lab_rows = [row for row in rows if row.get("merged_status") == MERGED_LAB_ONLY or row.get("capture_adapter_id") == "betrayal_inverse_source_chain"]
    return {
        "row_count": len(lab_rows),
        "candidate_lanes": list(dict.fromkeys(str(row.get("lane_key")) for row in lab_rows if row.get("lane_key"))),
        "betrayal_inverse_remains_lab_only": True,
        "standard_55_policy_applies": False,
        "source_chain_required": True,
        "exact_risk_mapping_required": True,
        "stale_shadow_outcomes_forbidden": True,
        "live_permission": False,
        "tiny_live_eligible_now": False,
    }


def _watch_only_merge_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    watch_rows = [row for row in rows if row.get("merged_status") == MERGED_WATCH_ONLY or row.get("capture_adapter_id") == "watch_88m_durability"]
    return {
        "row_count": len(watch_rows),
        "candidate_lanes": list(dict.fromkeys(str(row.get("lane_key")) for row in watch_rows if row.get("lane_key"))),
        "watch_88m_remains_watch_only": True,
        "live_permission": False,
        "tiny_live_eligible_now": False,
    }


def _remaining_merge_gaps(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    gap_rows = [row for row in rows if row.get("merged_status") != MERGED_READY]
    grouped = Counter(str(row.get("source_gap_id") or row.get("merged_status")) for row in gap_rows)
    return {
        "gap_count": len(grouped),
        "gaps": [
            {"gap_id": gap_id, "row_count": row_count, "do_not_fake_data": True}
            for gap_id, row_count in grouped.most_common()
        ],
        "do_not_fake_data": True,
        "pending_rows_not_converted_to_ready": True,
    }


def _filter_adapter_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    selected_capture_ids: set[str],
    include_lab_only: bool,
    include_watch_only: bool,
) -> list[Mapping[str, Any]]:
    selected_adapter_ids = {ADAPTER_BY_CAPTURE_ADAPTER[capture_id] for capture_id in selected_capture_ids}
    selected: list[Mapping[str, Any]] = []
    for row in rows:
        if row.get("adapter_id") not in selected_adapter_ids:
            continue
        if not include_lab_only and row.get("evidence_status") == LAB_ONLY:
            continue
        if not include_watch_only and row.get("evidence_status") == WATCH_ONLY:
            continue
        selected.append(row)
    return selected


def _filter_source_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    selected_capture_ids: set[str],
    include_lab_only: bool,
    include_watch_only: bool,
    include_pending: bool,
) -> list[Mapping[str, Any]]:
    selected: list[Mapping[str, Any]] = []
    for row in rows:
        if row.get("capture_adapter_id") not in selected_capture_ids:
            continue
        if not include_lab_only and row.get("capture_status") == SOURCE_LAB_ONLY:
            continue
        if not include_watch_only and row.get("capture_status") == SOURCE_WATCH_ONLY:
            continue
        if not include_pending and row.get("capture_status") == SOURCE_PENDING:
            continue
        selected.append(row)
    return selected


def _selected_capture_ids(adapter: str) -> set[str]:
    if adapter == "all":
        return set(CAPTURE_ADAPTER_IDS)
    if adapter not in CAPTURE_ADAPTER_IDS:
        return set()
    return {adapter}


def _latest_evidence_or_build(log_dir: Path, now: datetime, adapter: str) -> dict[str, Any]:
    records = load_strategy_lab_evidence_adapter_pack_records(log_dir=log_dir, limit=1)
    if records:
        return records[-1]
    source_adapter = ADAPTER_BY_CAPTURE_ADAPTER.get(adapter, "all") if adapter != "all" else "all"
    return build_strategy_lab_evidence_adapter_pack(log_dir=log_dir, write=False, now=now, adapter=source_adapter)


def _latest_batch_or_build(log_dir: Path, now: datetime, adapter: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    records = load_strategy_lab_adapter_output_batch_execution_packet_records(log_dir=log_dir, limit=1)
    if records:
        return records[-1]
    source_adapter = ADAPTER_BY_CAPTURE_ADAPTER.get(adapter, "all") if adapter != "all" else "all"
    return build_strategy_lab_adapter_output_batch_execution_packet(
        log_dir=log_dir,
        write=False,
        now=now,
        adapter=source_adapter,
        evidence_adapter_pack=evidence,
    )


def _latest_capture_or_build(
    log_dir: Path,
    now: datetime,
    adapter: str,
    evidence: Mapping[str, Any],
    batch: Mapping[str, Any],
) -> dict[str, Any]:
    records = load_strategy_lab_source_data_capture_adapter_records(log_dir=log_dir, limit=1)
    if records:
        return records[-1]
    return build_strategy_lab_source_data_capture_adapter(
        log_dir=log_dir,
        write=False,
        now=now,
        adapter=adapter,
        include_lab_only=True,
        include_watch_only=True,
        max_source_rows=1000,
        evidence_adapter_pack=evidence,
        adapter_output_batch_execution_packet=batch,
    )


def _packet_blockers(
    selected_capture_ids: set[str],
    rows: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    batch: Mapping[str, Any],
    capture: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not selected_capture_ids:
        blockers.append("no_capture_adapter_selected")
    if not rows:
        blockers.append("no_merged_adapter_rows_built")
    if evidence.get("evidence_adapter_pack_status") != R328_READY:
        blockers.append("source_r328_evidence_adapter_pack_not_ready")
    if batch.get("adapter_batch_execution_status") != R329_READY:
        blockers.append("source_r329_adapter_batch_execution_not_ready")
    if capture.get("source_data_capture_status") not in {R331_READY, R331_PARTIAL}:
        blockers.append("source_r331_capture_adapter_not_ready_or_partial")
    return blockers


def _status(blockers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    if blockers:
        return BLOCKED
    if any(row.get("merged_status") != MERGED_READY for row in rows):
        return PARTIAL
    return READY


def _source_variant_name(source: Mapping[str, Any]) -> Any:
    source_inputs = source.get("source_inputs") if isinstance(source.get("source_inputs"), Mapping) else {}
    return source_inputs.get("source_variant_name") or source.get("capture_name")


def _adapter_source_gap(adapter: Mapping[str, Any]) -> Any:
    derived = adapter.get("derived_fields") if isinstance(adapter.get("derived_fields"), Mapping) else {}
    return derived.get("raw_source_gap")


def _source_chain(adapter: Mapping[str, Any], source: Mapping[str, Any]) -> list[str]:
    chain = [*(adapter.get("source_chain") or []), *(source.get("source_chain") or []), "strategy_lab_captured_source_data_merge"]
    return list(dict.fromkeys(str(item) for item in chain if item))


def _count_status(rows: Sequence[Mapping[str, Any]], status: str) -> int:
    return sum(1 for row in rows if row.get("merged_status") == status)


def _recommended_next_action(capture_adapter_id: str, rows: Sequence[Mapping[str, Any]]) -> str:
    if capture_adapter_id == "betrayal_inverse_source_chain":
        return "KEEP_LAB_ONLY_AND_CAPTURE_SOURCE_CHAIN_DATA"
    if capture_adapter_id == "watch_88m_durability":
        return "KEEP_WATCH_ONLY_AND_CAPTURE_DURABILITY"
    if any(row.get("merged_status") == MERGED_PENDING_SOURCE_DATA for row in rows):
        return "R333_RANK_MERGED_EVIDENCE_WITH_PENDING_SOURCE_DATA_VISIBLE"
    if any(row.get("merged_status") == MERGED_READY for row in rows):
        return "R333_RANK_MERGED_READY_EVIDENCE"
    return "REVIEW_UNMATCHED_ROWS_WITHOUT_CREATING_SYNTHETIC_DATA"


def _recommended_r333_path() -> dict[str, Any]:
    return {
        "phase": "R333 Strategy Lab Merged Evidence Ranking Packet",
        "purpose": "Rank merged evidence after R331 source-data status is attached to R328/R329 adapter rows.",
        "input_ledger": LEDGER_FILENAME,
        "live_permission": False,
        "write_promotion_events": False,
        "write_risk_contracts": False,
        "write_observed_expansion": False,
    }


def _recommended_r330_path() -> dict[str, Any]:
    return {
        "phase": "R330 Human-Reviewed Observed Expansion Promotion Gate",
        "purpose": "Observed expansion can later change only after human review of merged evidence.",
        "can_later_alter_observed_expansion_after_human_review": True,
        "tiny_live_separately_gated": True,
        "live_permission": False,
    }


def _recommended_tiny_live_path(first_tiny_live_lane: str) -> list[str]:
    return [
        f"First Tiny Live remains {first_tiny_live_lane}.",
        "R332 merges Strategy Lab evidence only and does not alter Tiny Live.",
        "Tiny Live remains separately gated from R332/R333/R330.",
        "No final command, submit path, arming change, or live order is available from R332.",
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
        "no_synthetic_performance_creation": True,
    }


def _source_surfaces(log_dir: Path) -> list[str]:
    return [
        "docs/hammer_radar/live_readiness/R331_STRATEGY_LAB_SOURCE_DATA_CAPTURE_ADAPTER_IMPLEMENTATION.md",
        "docs/hammer_radar/live_readiness/R329_STRATEGY_LAB_ADAPTER_OUTPUT_BATCH_EXECUTION_PACKET.md",
        "docs/hammer_radar/live_readiness/R328_STRATEGY_LAB_EVIDENCE_ADAPTER_IMPLEMENTATION_PACK.md",
        "docs/hammer_radar/live_readiness/R326_CANDIDATE_FEED_EXPANSION_FOR_STRATEGY_LAB_VARIANTS.md",
        "src/app/hammer_radar/operator/strategy_lab_source_data_capture_adapter.py",
        "src/app/hammer_radar/operator/strategy_lab_adapter_output_batch_execution_packet.py",
        "src/app/hammer_radar/operator/strategy_lab_evidence_adapter_pack.py",
        "src/app/hammer_radar/operator/strategy_lab_candidate_feed_expansion.py",
        "src/app/hammer_radar/operator/inspect.py",
        str(log_dir / "strategy_lab_source_data_capture_adapter.ndjson"),
        str(log_dir / "strategy_lab_adapter_output_batch_execution_packet.ndjson"),
        str(log_dir / "strategy_lab_evidence_adapter_pack.ndjson"),
        str(log_dir / "strategy_lab_candidate_feed_expansion.ndjson"),
    ]


def _sanitize(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.strategy_lab_captured_source_data_merge")
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--adapter", choices=("all", *CAPTURE_ADAPTER_IDS), default="all")
    parser.add_argument("--include-lab-only", action="store_true", default=True)
    parser.add_argument("--include-watch-only", action="store_true", default=True)
    parser.add_argument("--include-pending", action="store_true", default=True)
    parser.add_argument("--max-rows", type=int, default=1000)
    args = parser.parse_args(argv)

    payload = build_strategy_lab_captured_source_data_merge(
        log_dir=args.log_dir,
        write=not args.no_write,
        adapter=args.adapter,
        include_lab_only=args.include_lab_only,
        include_watch_only=args.include_watch_only,
        include_pending=args.include_pending,
        max_rows=args.max_rows,
    )
    if args.text:
        print(format_captured_source_data_merge_text(payload))
    else:
        print(format_captured_source_data_merge_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
