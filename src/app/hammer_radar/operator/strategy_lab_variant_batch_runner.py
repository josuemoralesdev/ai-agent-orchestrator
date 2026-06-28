"""R324 read-only Strategy Lab variant batch runner."""

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
from src.app.hammer_radar.operator.strategy_lab_expansion_surface_map import (
    BASELINE_LANE,
    TELEGRAM_SCOPE_COMPLETE_R322,
    build_strategy_lab_expansion_surface_map,
)
from src.app.hammer_radar.operator.strategy_lab_variant_test_pack import (
    build_strategy_lab_variant_test_pack,
)

EVENT_TYPE = "R324_STRATEGY_LAB_VARIANT_BATCH_RUNNER"
CREATED_BY_PHASE = "R324_STRATEGY_LAB_VARIANT_BATCH_RUNNER"
LEDGER_FILENAME = "strategy_lab_variant_batch_runner.ndjson"

READY = "STRATEGY_LAB_VARIANT_BATCH_RUNNER_READY"
BLOCKED = "STRATEGY_LAB_VARIANT_BATCH_RUNNER_BLOCKED"

BATCH_IDS = (
    "44m_short",
    "55m_long",
    "13m_near_miss",
    "8m_short_capture",
    "88m_watch",
    "betrayal_inverse_lab",
    "ma_wma_anchor",
    "exits",
)

SAFETY: dict[str, bool] = {
    "live_execution_enabled": False,
    "allow_live_orders": False,
    "global_kill_switch": True,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "submit_allowed": False,
    "final_command_available": False,
    "real_order_forbidden": True,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
    "autonomous_arming_state_changed": False,
    "global_live_flags_changed": False,
    "risk_contract_config_mutated": False,
    "config_written": False,
    "env_written": False,
    "env_mutated": False,
    "systemd_unit_mutated": False,
    "scheduler_started": False,
    "telegram_send_called": False,
    "telegram_message_sent": False,
    "real_telegram_send_called": False,
    "real_telegram_message_sent": False,
}


def build_strategy_lab_variant_batch_runner(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    batch: str = "all",
    min_sample_count: int = 30,
    preferred_sample_count: int = 50,
    standard_min_win_rate_pct: float = 55.0,
    betrayal_min_win_rate_pct: float = 60.0,
    surface_map_packet: Mapping[str, Any] | None = None,
    variant_pack_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    surface = (
        dict(surface_map_packet)
        if isinstance(surface_map_packet, Mapping)
        else build_strategy_lab_expansion_surface_map(log_dir=resolved_log_dir, write=False, now=generated_at)
    )
    variant_pack = (
        dict(variant_pack_packet)
        if isinstance(variant_pack_packet, Mapping)
        else build_strategy_lab_variant_test_pack(log_dir=resolved_log_dir, write=False, now=generated_at)
    )
    selected_batch_ids = _selected_batch_ids(batch)
    evidence = _evidence_by_lane(surface=surface, variant_pack=variant_pack)
    batch_results = [
        _batch_result(
            spec=spec,
            evidence_by_lane=evidence,
            min_sample_count=min_sample_count,
            preferred_sample_count=preferred_sample_count,
            standard_min_win_rate_pct=standard_min_win_rate_pct,
            betrayal_min_win_rate_pct=betrayal_min_win_rate_pct,
        )
        for spec in _batch_specs()
        if spec["batch_id"] in selected_batch_ids
    ]
    blockers = [] if batch_results else ["no_batch_results_selected"]
    promotion_candidates = _promotion_review_candidates(batch_results)
    betrayal_packet = _find_batch(batch_results, "betrayal_inverse_lab") or _batch_result(
        spec=_spec_by_id("betrayal_inverse_lab"),
        evidence_by_lane=evidence,
        min_sample_count=min_sample_count,
        preferred_sample_count=preferred_sample_count,
        standard_min_win_rate_pct=standard_min_win_rate_pct,
        betrayal_min_win_rate_pct=betrayal_min_win_rate_pct,
    )
    ma_wma_packet = _find_batch(batch_results, "ma_wma_anchor") or _batch_result(
        spec=_spec_by_id("ma_wma_anchor"),
        evidence_by_lane=evidence,
        min_sample_count=min_sample_count,
        preferred_sample_count=preferred_sample_count,
        standard_min_win_rate_pct=standard_min_win_rate_pct,
        betrayal_min_win_rate_pct=betrayal_min_win_rate_pct,
    )
    exit_packet = _find_batch(batch_results, "exits") or _batch_result(
        spec=_spec_by_id("exits"),
        evidence_by_lane=evidence,
        min_sample_count=min_sample_count,
        preferred_sample_count=preferred_sample_count,
        standard_min_win_rate_pct=standard_min_win_rate_pct,
        betrayal_min_win_rate_pct=betrayal_min_win_rate_pct,
    )
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "batch_runner_id": f"r324_strategy_lab_variant_batch_runner_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_lab_variant_batch_runner_path": str(batch_runner_path(resolved_log_dir)),
        "batch_runner_status": BLOCKED if blockers else READY,
        "blockers": blockers,
        "source_surface_map_status": surface.get("surface_map_status"),
        "telegram_scope_status": surface.get("telegram_scope_status") or TELEGRAM_SCOPE_COMPLETE_R322,
        "tiny_live_baseline_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
        "batch_results": batch_results,
        "batch_counts": _batch_counts(batch_results),
        "top_candidate_observations": _top_candidate_observations(batch_results),
        "promotion_review_candidates": promotion_candidates,
        "near_miss_repair_candidates": _lanes_from_batches(batch_results, {"13m_near_miss", "8m_short_capture"}),
        "watch_only_candidates": promotion_candidates["watch_only"],
        "lab_only_candidates": promotion_candidates["lab_only"],
        "betrayal_inverse_lab_packet": betrayal_packet,
        "ma_wma_anchor_packet": ma_wma_packet,
        "exit_variant_packet": exit_packet,
        "missing_data_adapters": _missing_data_adapters(batch_results),
        "recommended_r325_promotion_review": _recommended_r325(promotion_candidates),
        "recommended_r326_candidate_feed_expansion": _recommended_r326(),
        "recommended_tiny_live_path": _recommended_tiny_live_path(),
        "no_live_mutation_summary": _no_live_mutation_summary(),
        "source_surfaces_used": _source_surfaces(resolved_log_dir),
        "safety": dict(SAFETY),
        **dict(SAFETY),
    }
    safe_payload = _sanitize(payload)
    if write:
        append_batch_runner(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def append_batch_runner(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = batch_runner_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_strategy_lab_variant_batch_runner_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(batch_runner_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def batch_runner_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_batch_runner_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_batch_runner_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R324 STRATEGY LAB VARIANT BATCH RUNNER",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        f"batch_runner_status: {payload.get('batch_runner_status')}",
        "",
        "TELEGRAM SCOPE STATUS",
        f"telegram_scope_status: {payload.get('telegram_scope_status')}",
        "",
        "TINY LIVE BASELINE LANE",
        f"tiny_live_baseline_lane: {payload.get('tiny_live_baseline_lane')}",
        f"first_live_lane_change_allowed: {payload.get('first_live_lane_change_allowed')}",
        "",
        "BATCH RESULTS SUMMARY",
    ]
    for row in payload.get("batch_results") or []:
        if isinstance(row, Mapping):
            lines.append(
                f"{row.get('batch_id')}: lanes={len(row.get('candidate_lanes') or [])} "
                f"variants={len(row.get('variants_to_test') or [])} action={row.get('recommended_next_action')}"
            )
    lines.extend(["", "PROMOTION REVIEW CANDIDATES"])
    promo = payload.get("promotion_review_candidates") if isinstance(payload.get("promotion_review_candidates"), Mapping) else {}
    for key in ("ready_for_R325_review", "needs_more_samples", "watch_only", "lab_only", "blocked"):
        lines.append(f"{key}: {','.join(promo.get(key) or []) or 'none'}")
    lines.extend(["", "NEAR-MISS REPAIR CANDIDATES"])
    lines.append(",".join(payload.get("near_miss_repair_candidates") or []) or "none")
    lines.extend(["", "BETRAYAL/INVERSE LAB-ONLY PACKET"])
    betrayal = payload.get("betrayal_inverse_lab_packet") if isinstance(payload.get("betrayal_inverse_lab_packet"), Mapping) else {}
    for key in (
        "lab_only",
        "tiny_live_eligible_now",
        "standard_55_policy_applies",
        "preferred_win_rate_pct",
        "avg_pnl_requirement",
        "original_vs_inverse_required",
        "source_chain_required",
        "exact_risk_mapping_required",
        "stale_shadow_outcomes_forbidden",
    ):
        lines.append(f"{key}: {betrayal.get(key)}")
    lines.extend(["", "MA/WMA ANCHOR PACKET"])
    ma = payload.get("ma_wma_anchor_packet") if isinstance(payload.get("ma_wma_anchor_packet"), Mapping) else {}
    lines.append(f"variants_to_test: {','.join(ma.get('variants_to_test') or []) or 'none'}")
    lines.extend(["", "EXIT VARIANT PACKET"])
    exits = payload.get("exit_variant_packet") if isinstance(payload.get("exit_variant_packet"), Mapping) else {}
    lines.append(f"variants_to_test: {','.join(exits.get('variants_to_test') or []) or 'none'}")
    lines.extend(["", "RECOMMENDED R325 AND R326"])
    lines.append(f"recommended_r325_promotion_review: {payload.get('recommended_r325_promotion_review')}")
    lines.append(f"recommended_r326_candidate_feed_expansion: {payload.get('recommended_r326_candidate_feed_expansion')}")
    lines.extend(["", "RECOMMENDED TINY LIVE PATH"])
    for item in payload.get("recommended_tiny_live_path") or []:
        lines.append(str(item))
    lines.extend(["", "SAFETY FLAGS"])
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    for key in SAFETY:
        lines.append(f"{key}: {safety.get(key)}")
    return "\n".join(lines)


def _batch_specs() -> list[dict[str, Any]]:
    return [
        {
            "batch_id": "44m_short",
            "batch_name": "44m short variants",
            "objective": "Compare primary 44m short entries and filters for R325 review without live promotion.",
            "candidate_lanes": [
                "BTCUSDT|44m|short|ladder_382_50_618",
                "BTCUSDT|44m|short|ladder_close_50_618",
                "BTCUSDT|44m|short|ladder_22_44_22",
            ],
            "variants_to_test": ["entry modes", "exit modes", "trailing", "RSI/regime filters", "WMA/MA anchor"],
            "candidate_bucket": "ready_or_watch",
        },
        {
            "batch_id": "55m_long",
            "batch_name": "55m long variants",
            "objective": "Compare 55m ladder and market-close long evidence for promotion review.",
            "candidate_lanes": ["BTCUSDT|55m|long|ladder_close_50_618", "BTCUSDT|55m|long|market_close"],
            "variants_to_test": ["ladder vs market close", "exit modes", "WMA/MA anchor", "HTF bias"],
            "candidate_bucket": "ready_or_watch",
        },
        {
            "batch_id": "13m_near_miss",
            "batch_name": "13m near-miss repair variants",
            "objective": "Repair 13m near-miss long/short timing and filter dimensions.",
            "candidate_lanes": ["BTCUSDT|13m|long|ladder_close_50_618", "BTCUSDT|13m|short|ladder_close_50_618"],
            "variants_to_test": ["partial entry", "timing repair", "early/late exit", "RSI/regime filter", "WMA/MA anchor"],
            "candidate_bucket": "near_miss",
        },
        {
            "batch_id": "8m_short_capture",
            "batch_name": "8m short capture improvement variants",
            "objective": "Improve 8m short capture quality before promotion review.",
            "candidate_lanes": ["BTCUSDT|8m|short|ladder_close_50_618"],
            "variants_to_test": ["faster capture", "tighter invalidation", "partial exits", "trailing", "regime filter"],
            "candidate_bucket": "near_miss",
        },
        {
            "batch_id": "88m_watch",
            "batch_name": "88m watch-only evidence variants",
            "objective": "Deepen slow-lane watch-only evidence and durability.",
            "candidate_lanes": ["BTCUSDT|88m|long|ladder_382_50_618"],
            "variants_to_test": ["durability", "slow signal confirmation", "HTF bias", "exit variants"],
            "candidate_bucket": "watch_only",
        },
        {
            "batch_id": "betrayal_inverse_lab",
            "batch_name": "Betrayal/inverse lab-only variants",
            "objective": "Capture betrayal/inverse evidence under stricter lab-only gates.",
            "candidate_lanes": ["BETRAYAL_INVERSE_LANES"],
            "variants_to_test": ["original vs inverse", "source chain", "risk mapping", "stale shadow audit"],
            "candidate_bucket": "lab_only",
            "lab_only": True,
        },
        {
            "batch_id": "ma_wma_anchor",
            "batch_name": "MA/WMA200 anchor variants",
            "objective": "Test moving-average anchor confluence across candidate lanes.",
            "candidate_lanes": [
                "BTCUSDT|44m|short|ladder_382_50_618",
                "BTCUSDT|44m|short|ladder_close_50_618",
                "BTCUSDT|55m|long|ladder_close_50_618",
                "BTCUSDT|13m|long|ladder_close_50_618",
                "BTCUSDT|13m|short|ladder_close_50_618",
                "BTCUSDT|8m|short|ladder_close_50_618",
                "BTCUSDT|88m|long|ladder_382_50_618",
            ],
            "variants_to_test": [
                "WMA200 support/resistance anchor",
                "MA200 support/resistance anchor",
                "close above/below anchor",
                "anchor slope / trend filter",
                "golden-pocket + anchor confluence",
            ],
            "candidate_bucket": "cross_cutting",
        },
        {
            "batch_id": "exits",
            "batch_name": "Exit / TP / SL / trailing variants",
            "objective": "Compare exit, stop, take-profit, partial, and trailing dimensions across candidate lanes.",
            "candidate_lanes": [
                "BTCUSDT|44m|short|ladder_382_50_618",
                "BTCUSDT|44m|short|ladder_close_50_618",
                "BTCUSDT|55m|long|ladder_close_50_618",
                "BTCUSDT|13m|long|ladder_close_50_618",
                "BTCUSDT|13m|short|ladder_close_50_618",
                "BTCUSDT|8m|short|ladder_close_50_618",
                "BTCUSDT|88m|long|ladder_382_50_618",
            ],
            "variants_to_test": ["fixed TP/SL", "early exit", "late exit", "trailing", "partial exit", "invalidation tightening"],
            "candidate_bucket": "cross_cutting",
        },
    ]


def _batch_result(
    *,
    spec: Mapping[str, Any],
    evidence_by_lane: Mapping[str, Mapping[str, Any]],
    min_sample_count: int,
    preferred_sample_count: int,
    standard_min_win_rate_pct: float,
    betrayal_min_win_rate_pct: float,
) -> dict[str, Any]:
    lanes = [str(lane) for lane in spec.get("candidate_lanes") or []]
    lab_only = bool(spec.get("lab_only"))
    snapshot = {lane: _evidence_snapshot(evidence_by_lane.get(lane, {})) for lane in lanes if lane in evidence_by_lane}
    result = {
        "batch_id": spec.get("batch_id"),
        "batch_name": spec.get("batch_name"),
        "objective": spec.get("objective"),
        "candidate_lanes": lanes,
        "variants_to_test": list(spec.get("variants_to_test") or []),
        "evidence_source": _evidence_source(snapshot),
        "current_evidence_snapshot": snapshot,
        "min_sample_count": min_sample_count,
        "preferred_sample_count": preferred_sample_count,
        "promotion_policy": _promotion_policy(lab_only=lab_only, standard_min_win_rate_pct=standard_min_win_rate_pct),
        "live_permission": False,
        "tiny_live_eligible_now": False,
        "recommended_next_action": _recommended_action(spec, snapshot, min_sample_count, standard_min_win_rate_pct),
        "blockers": _batch_blockers(spec, snapshot, min_sample_count),
        "lab_only": lab_only,
        "candidate_bucket": spec.get("candidate_bucket"),
        "first_live_lane_change_allowed": False,
        **dict(SAFETY),
    }
    if spec.get("batch_id") == "betrayal_inverse_lab":
        result.update(
            {
                "lab_only": True,
                "tiny_live_eligible_now": False,
                "standard_55_policy_applies": False,
                "preferred_win_rate_pct": betrayal_min_win_rate_pct,
                "min_sample_count": min_sample_count,
                "preferred_sample_count": preferred_sample_count,
                "avg_pnl_requirement": "positive",
                "original_vs_inverse_required": True,
                "source_chain_required": True,
                "exact_risk_mapping_required": True,
                "stale_shadow_outcomes_forbidden": True,
            }
        )
    return result


def _evidence_by_lane(*, surface: Mapping[str, Any], variant_pack: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for key in ("observed_primary_lanes", "observed_secondary_watch_lanes"):
        for row in surface.get(key) or []:
            if isinstance(row, Mapping) and row.get("lane_key"):
                evidence[str(row["lane_key"])] = dict(row)
    for key in ("variant_candidates", "top_variant_candidates", "top_near_miss_variant_opportunities"):
        for row in variant_pack.get(key) or []:
            if isinstance(row, Mapping) and row.get("lane_key"):
                lane = str(row["lane_key"])
                current = evidence.get(lane, {})
                current_sample = _int_or_none(current.get("sample_count") or current.get("direct_sample_count")) or -1
                row_sample = _int_or_none(row.get("sample_count") or row.get("direct_sample_count")) or -1
                if row_sample >= current_sample:
                    evidence[lane] = {**current, **dict(row)}
    evidence.setdefault(BASELINE_LANE, {"lane_key": BASELINE_LANE, "source": "current_tiny_live_baseline"})
    return evidence


def _evidence_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sample_count": _int_or_none(row.get("sample_count") or row.get("direct_sample_count")),
        "win_rate_pct": _float_or_none(row.get("win_rate_pct")),
        "avg_pnl_pct": _float_or_none(row.get("avg_pnl_pct")),
        "evidence_status": row.get("evidence_status") or row.get("expansion_preview_status"),
        "recommended_lab_action": row.get("recommended_lab_action") or row.get("recommended_operator_action"),
        "source_chain": list(row.get("source_chain") or row.get("evidence_files_used") or []),
    }


def _promotion_review_candidates(batch_results: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {
        "ready_for_R325_review": [],
        "needs_more_samples": [],
        "watch_only": [],
        "lab_only": [],
        "blocked": [],
    }
    for batch in batch_results:
        if batch.get("candidate_bucket") == "cross_cutting":
            continue
        target = _promotion_bucket(batch)
        buckets[target].extend(str(lane) for lane in batch.get("candidate_lanes") or [])
    return {key: list(dict.fromkeys(value)) for key, value in buckets.items()}


def _promotion_bucket(batch: Mapping[str, Any]) -> str:
    if batch.get("lab_only"):
        return "lab_only"
    bucket = batch.get("candidate_bucket")
    if bucket == "watch_only":
        return "watch_only"
    if bucket == "near_miss":
        return "needs_more_samples"
    if batch.get("blockers"):
        return "blocked"
    return "ready_for_R325_review"


def _selected_batch_ids(batch: str) -> set[str]:
    if batch == "all":
        return set(BATCH_IDS)
    if batch not in BATCH_IDS:
        return set()
    return {batch}


def _spec_by_id(batch_id: str) -> Mapping[str, Any]:
    for spec in _batch_specs():
        if spec["batch_id"] == batch_id:
            return spec
    raise KeyError(batch_id)


def _find_batch(batch_results: Sequence[Mapping[str, Any]], batch_id: str) -> Mapping[str, Any] | None:
    return next((row for row in batch_results if row.get("batch_id") == batch_id), None)


def _batch_counts(batch_results: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "batch_count": len(batch_results),
        "candidate_lane_count": len({lane for row in batch_results for lane in row.get("candidate_lanes") or []}),
        "lab_only_batch_count": sum(1 for row in batch_results if row.get("lab_only")),
        "live_permission_count": sum(1 for row in batch_results if row.get("live_permission") is True),
    }


def _top_candidate_observations(batch_results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for batch in batch_results:
        snapshot = batch.get("current_evidence_snapshot") if isinstance(batch.get("current_evidence_snapshot"), Mapping) else {}
        for lane, evidence in snapshot.items():
            if isinstance(evidence, Mapping):
                rows.append({"lane_key": lane, "batch_id": batch.get("batch_id"), **dict(evidence)})
    rows.sort(key=lambda row: (_int_or_none(row.get("sample_count")) or 0, _float_or_none(row.get("win_rate_pct")) or 0.0), reverse=True)
    return rows[:10]


def _lanes_from_batches(batch_results: Sequence[Mapping[str, Any]], batch_ids: set[str]) -> list[str]:
    return list(
        dict.fromkeys(
            str(lane)
            for row in batch_results
            if row.get("batch_id") in batch_ids
            for lane in row.get("candidate_lanes") or []
        )
    )


def _missing_data_adapters(batch_results: Sequence[Mapping[str, Any]]) -> list[str]:
    adapters: list[str] = []
    for row in batch_results:
        if row.get("blockers"):
            adapters.append(f"{row.get('batch_id')}: direct paper evidence adapter or capture scheduler")
    return adapters


def _recommended_r325(candidates: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    return {
        "phase": "R325 Strategy Lab Promotion Review Packet",
        "review_ready_lanes": list(candidates.get("ready_for_R325_review") or []),
        "must_exclude_lab_only_from_standard_promotion": True,
        "write_promotion_events": False,
        "write_risk_contracts": False,
    }


def _recommended_r326() -> dict[str, Any]:
    return {
        "phase": "R326 Candidate Feed Expansion",
        "objective": "Add missing candidate feed adapters for near-miss, anchor, exit, and betrayal lab evidence.",
        "live_permission": False,
    }


def _recommended_tiny_live_path() -> list[str]:
    return [
        "First Tiny Live remains BTCUSDT|44m|long|ladder_close_50_618.",
        "Expanded lanes increase candidate surface but do not become live automatically.",
        "Future live candidates require evidence + risk contract + human review + final gate.",
        "Current final gate still waits for real candidate detection.",
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
        "no_risk_contract_write": True,
        "no_config_or_env_mutation": True,
        "no_systemd_mutation": True,
        "no_scheduler_start": True,
        "no_telegram_send": True,
    }


def _source_surfaces(log_dir: Path) -> list[str]:
    return [
        "docs/hammer_radar/live_readiness/R323_STRATEGY_LAB_EXPANSION_REENTRY_AND_CANDIDATE_SURFACE_MAP.md",
        "docs/hammer_radar/live_readiness/R305_STRATEGY_LAB_VARIANT_TEST_PACK.md",
        "docs/hammer_radar/live_readiness/R304_PAPER_REFRESH_DURABILITY_AND_STRATEGY_LAB_PREVIEW.md",
        "docs/hammer_radar/live_readiness/R306_ELIGIBLE_LANE_EXPANSION_DRY_RUN_PREVIEW.md",
        "src/app/hammer_radar/operator/strategy_lab_expansion_surface_map.py",
        "src/app/hammer_radar/operator/strategy_lab_variant_test_pack.py",
        "src/app/hammer_radar/operator/strategy_lab_preview.py",
        "src/app/hammer_radar/operator/eligible_lane_expansion_dry_run_preview.py",
        "configs/hammer_radar/tiny_live_risk_contracts.json",
        str(log_dir / "strategy_lab_preview.ndjson"),
        str(log_dir / "strategy_lab_variant_test_pack.ndjson"),
        str(log_dir / "strategy_evidence_registry.ndjson"),
        str(log_dir / "strategy_promotion_events.ndjson"),
    ]


def _evidence_source(snapshot: Mapping[str, Any]) -> str:
    return "R323_SURFACE_MAP_AND_R305_VARIANT_PACK" if snapshot else "MISSING_DIRECT_BATCH_EVIDENCE"


def _promotion_policy(*, lab_only: bool, standard_min_win_rate_pct: float) -> dict[str, Any]:
    return {
        "standard_min_win_rate_pct": standard_min_win_rate_pct,
        "standard_policy_applies": not lab_only,
        "requires_human_review": True,
        "requires_risk_contract_before_live": True,
        "writes_promotion_events": False,
        "writes_risk_contracts": False,
    }


def _recommended_action(spec: Mapping[str, Any], snapshot: Mapping[str, Any], min_sample_count: int, win_rate: float) -> str:
    if spec.get("lab_only"):
        return "CAPTURE_LAB_ONLY_EVIDENCE_FOR_FUTURE_REVIEW"
    if not snapshot:
        return "CAPTURE_BATCH_EVIDENCE"
    ready = [
        lane
        for lane, row in snapshot.items()
        if isinstance(row, Mapping)
        and (_int_or_none(row.get("sample_count")) or 0) >= min_sample_count
        and (_float_or_none(row.get("win_rate_pct")) or 0.0) >= win_rate
    ]
    return "PREPARE_R325_PROMOTION_REVIEW" if ready else "COLLECT_MORE_PAPER_SAMPLES"


def _batch_blockers(spec: Mapping[str, Any], snapshot: Mapping[str, Any], min_sample_count: int) -> list[str]:
    if spec.get("lab_only"):
        return ["lab_only_not_standard_promotion", "tiny_live_eligible_now_false"]
    missing = [lane for lane in spec.get("candidate_lanes") or [] if lane not in snapshot]
    low_sample = [
        lane
        for lane, row in snapshot.items()
        if isinstance(row, Mapping) and (_int_or_none(row.get("sample_count")) or 0) < min_sample_count
    ]
    blockers = []
    if missing:
        blockers.append("missing_direct_evidence:" + ",".join(str(lane) for lane in missing))
    if low_sample:
        blockers.append("needs_minimum_samples:" + ",".join(str(lane) for lane in low_sample))
    return blockers


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sanitize(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.strategy_lab_variant_batch_runner")
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--batch", choices=("all", *BATCH_IDS), default="all")
    parser.add_argument("--min-sample-count", type=int, default=30)
    parser.add_argument("--preferred-sample-count", type=int, default=50)
    parser.add_argument("--standard-min-win-rate-pct", type=float, default=55.0)
    parser.add_argument("--betrayal-min-win-rate-pct", type=float, default=60.0)
    args = parser.parse_args(argv)

    payload = build_strategy_lab_variant_batch_runner(
        log_dir=args.log_dir,
        write=not args.no_write,
        batch=args.batch,
        min_sample_count=args.min_sample_count,
        preferred_sample_count=args.preferred_sample_count,
        standard_min_win_rate_pct=args.standard_min_win_rate_pct,
        betrayal_min_win_rate_pct=args.betrayal_min_win_rate_pct,
    )
    if args.text:
        print(format_batch_runner_text(payload))
    else:
        print(format_batch_runner_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
