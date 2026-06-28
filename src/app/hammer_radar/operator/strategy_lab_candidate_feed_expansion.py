"""R326 read-only candidate feed expansion packet for Strategy Lab variants."""

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
from src.app.hammer_radar.operator.strategy_lab_expansion_surface_map import BASELINE_LANE
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

EVENT_TYPE = "R326_CANDIDATE_FEED_EXPANSION_FOR_STRATEGY_LAB_VARIANTS"
CREATED_BY_PHASE = "R326_CANDIDATE_FEED_EXPANSION_FOR_STRATEGY_LAB_VARIANTS"
LEDGER_FILENAME = "strategy_lab_candidate_feed_expansion.ndjson"

READY = "STRATEGY_LAB_CANDIDATE_FEED_EXPANSION_READY"
BLOCKED = "STRATEGY_LAB_CANDIDATE_FEED_EXPANSION_BLOCKED"

FEED_IDS = (
    "near_miss_13m",
    "capture_8m_short",
    "ma_wma_anchor",
    "exits",
    "betrayal_inverse_lab",
    "watch_88m",
    "review_ready_enrichment",
)

REVIEW_READY_LANES = (
    "BTCUSDT|44m|short|ladder_382_50_618",
    "BTCUSDT|44m|short|ladder_close_50_618",
    "BTCUSDT|44m|short|ladder_22_44_22",
    "BTCUSDT|55m|long|ladder_close_50_618",
    "BTCUSDT|55m|long|market_close",
)
NEAR_MISS_13M_LANES = (
    "BTCUSDT|13m|long|ladder_close_50_618",
    "BTCUSDT|13m|short|ladder_close_50_618",
)
CAPTURE_8M_SHORT_LANES = ("BTCUSDT|8m|short|ladder_close_50_618",)
WATCH_88M_LANES = ("BTCUSDT|88m|long|ladder_382_50_618",)
BETRAYAL_INVERSE_LANES = ("BETRAYAL_INVERSE_LANES",)
ANCHOR_AND_EXIT_LANES = tuple(
    dict.fromkeys([*REVIEW_READY_LANES, *NEAR_MISS_13M_LANES, *CAPTURE_8M_SHORT_LANES, *WATCH_88M_LANES])
)

MISSING_ADAPTERS = (
    "near_miss_variant_capture_adapter",
    "short_capture_improvement_adapter",
    "ma_wma_anchor_enrichment_adapter",
    "exit_variant_comparison_adapter",
    "betrayal_inverse_source_chain_adapter",
    "watch_88m_durability_adapter",
    "review_ready_enrichment_adapter",
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
    "promotion_event_written": False,
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


def build_strategy_lab_candidate_feed_expansion(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    feed: str = "all",
    min_sample_count: int = 30,
    preferred_sample_count: int = 50,
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
    selected_feed_ids = _selected_feed_ids(feed)
    all_packets = _feed_packets(
        min_sample_count=min_sample_count,
        preferred_sample_count=preferred_sample_count,
    )
    selected_packets = [packet for packet in all_packets if packet["feed_id"] in selected_feed_ids]
    blockers = _packet_blockers(
        selected_packets=selected_packets,
        promotion=promotion,
        batch=batch,
        selected_feed_ids=selected_feed_ids,
    )
    packet_by_id = {packet["feed_id"]: packet for packet in all_packets}
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "candidate_feed_expansion_id": f"r326_strategy_lab_candidate_feed_expansion_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_lab_candidate_feed_expansion_path": str(packet_path(resolved_log_dir)),
        "candidate_feed_expansion_status": BLOCKED if blockers else READY,
        "blockers": blockers,
        "source_promotion_review_status": promotion.get("promotion_review_status"),
        "source_batch_runner_status": batch.get("batch_runner_status"),
        "first_tiny_live_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
        "selected_feed": feed,
        "feed_expansion_packets": selected_packets,
        "feed_counts": _feed_counts(selected_packets),
        "missing_adapter_summary": _missing_adapter_summary(),
        "near_miss_feed_packet": packet_by_id["near_miss_13m"],
        "capture_8m_short_feed_packet": packet_by_id["capture_8m_short"],
        "ma_wma_anchor_feed_packet": packet_by_id["ma_wma_anchor"],
        "exit_variant_feed_packet": packet_by_id["exits"],
        "betrayal_inverse_lab_feed_packet": packet_by_id["betrayal_inverse_lab"],
        "watch_88m_feed_packet": packet_by_id["watch_88m"],
        "review_ready_enrichment_packet": packet_by_id["review_ready_enrichment"],
        "recommended_r327_path": _recommended_r327_path(),
        "recommended_r328_path": _recommended_r328_path(),
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


def load_strategy_lab_candidate_feed_expansion_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(packet_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def packet_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_candidate_feed_expansion_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_candidate_feed_expansion_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R326 CANDIDATE FEED EXPANSION FOR STRATEGY LAB VARIANTS",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        f"candidate_feed_expansion_status: {payload.get('candidate_feed_expansion_status')}",
        "",
        "FIRST TINY LIVE LANE",
        f"first_tiny_live_lane: {payload.get('first_tiny_live_lane')}",
        f"first_live_lane_change_allowed: {payload.get('first_live_lane_change_allowed')}",
        "",
        "FEED PACKET SUMMARY",
    ]
    for packet in payload.get("feed_expansion_packets") or []:
        if isinstance(packet, Mapping):
            lines.append(
                f"{packet.get('feed_id')}: lanes={len(packet.get('candidate_lanes') or [])} "
                f"adapter_inputs={len(packet.get('required_adapter_inputs') or [])} "
                f"action={packet.get('recommended_next_action')}"
            )
    lines.extend(["", "MISSING ADAPTER SUMMARY"])
    missing = payload.get("missing_adapter_summary") if isinstance(payload.get("missing_adapter_summary"), Mapping) else {}
    for adapter in missing.get("missing_adapters") or []:
        lines.append(str(adapter))
    lines.extend(["", "BETRAYAL/INVERSE LAB FEED"])
    betrayal = payload.get("betrayal_inverse_lab_feed_packet") if isinstance(payload.get("betrayal_inverse_lab_feed_packet"), Mapping) else {}
    for key in (
        "lab_only",
        "standard_55_policy_applies",
        "live_permission",
        "tiny_live_eligible_now",
        "original_vs_inverse_required",
        "source_chain_required",
        "exact_risk_mapping_required",
        "stale_shadow_outcomes_forbidden",
        "preferred_win_rate_pct",
        "min_sample_count",
        "preferred_sample_count",
        "avg_pnl_requirement",
    ):
        lines.append(f"{key}: {betrayal.get(key)}")
    lines.extend(["", "RECOMMENDED R327/R328"])
    lines.append(str(payload.get("recommended_r327_path")))
    lines.append(str(payload.get("recommended_r328_path")))
    lines.extend(["", "TINY LIVE PATH"])
    for item in payload.get("recommended_tiny_live_path") or []:
        lines.append(str(item))
    lines.extend(["", "SAFETY FLAGS"])
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    for key in SAFETY:
        lines.append(f"{key}: {safety.get(key)}")
    return "\n".join(lines)


def _feed_packets(*, min_sample_count: int, preferred_sample_count: int) -> list[dict[str, Any]]:
    return [
        _feed_packet(
            feed_id="near_miss_13m",
            feed_name="13m near-miss repair feed",
            candidate_lanes=NEAR_MISS_13M_LANES,
            evidence_gap="win rate below standard live threshold despite high sample count",
            feed_dimensions=[
                "timing repair",
                "partial entry",
                "early/late exit",
                "RSI/regime filter",
                "MA/WMA anchor",
                "golden-pocket support/resistance context",
            ],
            required_adapter_inputs=[
                "paper/lab timing repair observations",
                "partial entry fill/outcome rows",
                "early and late exit comparisons",
                "RSI/regime filter snapshots",
                "MA/WMA anchor context",
                "golden-pocket support/resistance context",
            ],
            output_artifact_plan=["near-miss 13m variant evidence rows", "timing repair comparison artifact"],
            recommended_next_action="add paper/lab capture adapters for variants",
            blockers=["standard_evidence_threshold_not_met", "variant_adapter_not_implemented"],
        ),
        _feed_packet(
            feed_id="capture_8m_short",
            feed_name="8m short capture improvement feed",
            candidate_lanes=CAPTURE_8M_SHORT_LANES,
            evidence_gap="near 55% threshold but not ready",
            feed_dimensions=[
                "faster capture",
                "tighter invalidation",
                "partial exit",
                "trailing",
                "regime filter",
                "entry timing",
            ],
            required_adapter_inputs=[
                "fast-capture signal timestamp",
                "tight invalidation price and outcome",
                "partial exit outcome",
                "trailing outcome",
                "regime filter snapshot",
                "entry timing delta",
            ],
            output_artifact_plan=["8m short capture-improvement evidence rows", "threshold repair comparison artifact"],
            recommended_next_action="add capture-improvement evidence adapter",
            blockers=["below_review_ready_threshold", "capture_improvement_adapter_not_implemented"],
        ),
        _feed_packet(
            feed_id="ma_wma_anchor",
            feed_name="MA/WMA200 anchor enrichment feed",
            candidate_lanes=ANCHOR_AND_EXIT_LANES,
            evidence_gap="anchor confluence fields are not consistently attached to Strategy Lab variant evidence",
            feed_dimensions=[
                "WMA200 support/resistance anchor",
                "MA200 support/resistance anchor",
                "close above/below anchor",
                "anchor slope",
                "golden-pocket + anchor confluence",
            ],
            required_adapter_inputs=[
                "WMA200 price and side",
                "MA200 price and side",
                "close-vs-anchor state",
                "anchor slope state",
                "golden-pocket confluence state",
            ],
            output_artifact_plan=["anchor-enriched Strategy Lab variant rows", "anchor confluence matrix"],
            recommended_next_action="add anchor enrichment fields to strategy lab variants",
            blockers=["anchor_enrichment_adapter_not_implemented"],
        ),
        _feed_packet(
            feed_id="exits",
            feed_name="Exit / TP / SL / trailing comparison feed",
            candidate_lanes=ANCHOR_AND_EXIT_LANES,
            evidence_gap="exit sensitivity is not split into comparable fixed TP/SL, early/late, trailing, partial, and invalidation variants",
            feed_dimensions=[
                "fixed TP/SL",
                "early exit",
                "late exit",
                "trailing",
                "partial exit",
                "invalidation tightening",
            ],
            required_adapter_inputs=[
                "fixed take-profit and stop outcome",
                "early exit outcome",
                "late exit outcome",
                "trailing stop outcome",
                "partial exit outcome",
                "tight invalidation outcome",
            ],
            output_artifact_plan=["exit-comparison evidence artifacts", "TP/SL/trailing variant matrix"],
            recommended_next_action="add exit-comparison evidence artifacts",
            blockers=["exit_variant_comparison_adapter_not_implemented"],
        ),
        _feed_packet(
            feed_id="betrayal_inverse_lab",
            feed_name="Betrayal/inverse lab-only source-chain feed",
            candidate_lanes=BETRAYAL_INVERSE_LANES,
            evidence_gap="Betrayal/inverse needs lab-only source-chain evidence with original-vs-inverse mapping before future review",
            feed_dimensions=[
                "original signal source chain",
                "inverse signal source chain",
                "original-vs-inverse comparison",
                "exact risk mapping",
                "stale shadow outcome rejection",
            ],
            required_adapter_inputs=[
                "original signal identity",
                "inverse signal identity",
                "source-chain lineage",
                "exact lane/entry/risk mapping",
                "true paper outcome freshness",
                "shadow outcome staleness audit",
            ],
            output_artifact_plan=["betrayal source-chain comparison artifact", "original-vs-inverse lab evidence rows"],
            recommended_next_action="source-chain and original-vs-inverse capture adapter only",
            blockers=["lab_only_not_standard_promotion", "source_chain_adapter_not_implemented"],
            extra={
                "lab_only": True,
                "standard_55_policy_applies": False,
                "original_vs_inverse_required": True,
                "source_chain_required": True,
                "exact_risk_mapping_required": True,
                "stale_shadow_outcomes_forbidden": True,
                "preferred_win_rate_pct": 60,
                "min_sample_count": min_sample_count,
                "preferred_sample_count": preferred_sample_count,
                "avg_pnl_requirement": "positive",
            },
        ),
        _feed_packet(
            feed_id="watch_88m",
            feed_name="88m watch-only durability feed",
            candidate_lanes=WATCH_88M_LANES,
            evidence_gap="88m has watch-only evidence but needs deeper durability before any later review",
            feed_dimensions=["durability", "slow confirmation", "HTF bias", "exit variants", "anchor filters"],
            required_adapter_inputs=[
                "slow-lane durability observations",
                "confirmation delay state",
                "HTF bias state",
                "exit variant outcome",
                "anchor filter state",
            ],
            output_artifact_plan=["88m durability evidence rows", "watch-only durability artifact"],
            recommended_next_action="keep watch-only and deepen evidence",
            blockers=["watch_only_not_promotion", "durability_adapter_not_implemented"],
        ),
        _feed_packet(
            feed_id="review_ready_enrichment",
            feed_name="44m/55m review-ready enrichment feed",
            candidate_lanes=REVIEW_READY_LANES,
            evidence_gap="review-ready lanes need stability, regime, adverse excursion, exit sensitivity, and anchor context before observed expansion review",
            feed_dimensions=[
                "stability over recent samples",
                "regime split",
                "adverse excursion",
                "exit sensitivity",
                "anchor confluence",
            ],
            required_adapter_inputs=[
                "recent sample stability window",
                "regime split outcome",
                "MAE/MFE adverse excursion",
                "exit sensitivity outcome",
                "anchor confluence state",
            ],
            output_artifact_plan=["review-ready enrichment artifact", "observed expansion review input rows"],
            recommended_next_action="enrich evidence before observed expansion gate",
            blockers=["review_ready_enrichment_adapter_not_implemented"],
        ),
    ]


def _feed_packet(
    *,
    feed_id: str,
    feed_name: str,
    candidate_lanes: Sequence[str],
    evidence_gap: str,
    feed_dimensions: Sequence[str],
    required_adapter_inputs: Sequence[str],
    output_artifact_plan: Sequence[str],
    recommended_next_action: str,
    blockers: Sequence[str],
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    packet = {
        "feed_id": feed_id,
        "feed_name": feed_name,
        "candidate_lanes": list(candidate_lanes),
        "evidence_gap": evidence_gap,
        "feed_dimensions": list(feed_dimensions),
        "required_adapter_inputs": list(required_adapter_inputs),
        "output_artifact_plan": list(output_artifact_plan),
        "scheduler_required": False,
        "live_permission": False,
        "promotion_event_written": False,
        "risk_contract_write_required": False,
        "tiny_live_eligible_now": False,
        "recommended_next_action": recommended_next_action,
        "blockers": list(blockers),
    }
    if extra:
        packet.update(dict(extra))
    return packet


def _selected_feed_ids(feed: str) -> set[str]:
    if feed == "all":
        return set(FEED_IDS)
    if feed not in FEED_IDS:
        return set()
    return {feed}


def _packet_blockers(
    *,
    selected_packets: Sequence[Mapping[str, Any]],
    promotion: Mapping[str, Any],
    batch: Mapping[str, Any],
    selected_feed_ids: set[str],
) -> list[str]:
    blockers: list[str] = []
    if not selected_feed_ids:
        blockers.append("no_feed_selected")
    if not selected_packets:
        blockers.append("no_feed_packets_built")
    if promotion.get("promotion_review_status") != R325_READY:
        blockers.append("source_r325_promotion_review_not_ready")
    if batch.get("batch_runner_status") != R324_READY:
        blockers.append("source_r324_batch_runner_not_ready")
    return blockers


def _feed_counts(packets: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    lanes = {str(lane) for packet in packets for lane in packet.get("candidate_lanes") or []}
    return {
        "feed_packet_count": len(packets),
        "candidate_lane_count": len(lanes),
        "lab_only_feed_count": sum(1 for packet in packets if packet.get("lab_only") is True),
        "live_permission_count": sum(1 for packet in packets if packet.get("live_permission") is True),
        "scheduler_required_count": sum(1 for packet in packets if packet.get("scheduler_required") is True),
        "promotion_event_written_count": sum(1 for packet in packets if packet.get("promotion_event_written") is True),
        "risk_contract_write_required_count": sum(1 for packet in packets if packet.get("risk_contract_write_required") is True),
    }


def _missing_adapter_summary() -> dict[str, Any]:
    return {
        "planning_only": True,
        "schedulers_implemented": False,
        "adapters_implemented": False,
        "missing_adapters": list(MISSING_ADAPTERS),
        "do_not_start_schedulers_in_r326": True,
        "do_not_write_observed_expansion_in_r326": True,
    }


def _recommended_r327_path() -> dict[str, Any]:
    return {
        "phase": "R327 Human-Reviewed Observed Expansion Promotion Gate",
        "purpose": "Human-reviewed observed expansion only after R326 feed map review.",
        "can_alter_observed_expansion_after_human_review": True,
        "live_permission": False,
        "tiny_live_separately_gated": True,
    }


def _recommended_r328_path() -> dict[str, Any]:
    return {
        "phase": "R328 Strategy Lab Evidence Adapter Implementation Pack",
        "purpose": "Implement actual evidence adapters from the R326 feed map for deeper R328/R329 batch execution.",
        "implements_r326_adapters": True,
        "write_promotion_events": False,
        "write_risk_contracts": False,
        "live_permission": False,
    }


def _recommended_tiny_live_path() -> list[str]:
    return [
        "First Tiny Live remains BTCUSDT|44m|long|ladder_close_50_618.",
        "R326 does not change Tiny Live, does not arm, does not submit, and does not create a final command.",
        "Tiny Live remains separately gated and still waits for a real candidate.",
        "Future Tiny Live requires human approval, exact risk contract, real candidate detection, and final gate clearance.",
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
        "docs/hammer_radar/live_readiness/R325_STRATEGY_LAB_PROMOTION_REVIEW_PACKET.md",
        "docs/hammer_radar/live_readiness/R324_STRATEGY_LAB_VARIANT_BATCH_RUNNER.md",
        "docs/hammer_radar/live_readiness/R323_STRATEGY_LAB_EXPANSION_REENTRY_AND_CANDIDATE_SURFACE_MAP.md",
        "docs/hammer_radar/live_readiness/R305_STRATEGY_LAB_VARIANT_TEST_PACK.md",
        "docs/hammer_radar/live_readiness/R304_PAPER_REFRESH_DURABILITY_AND_STRATEGY_LAB_PREVIEW.md",
        "src/app/hammer_radar/operator/strategy_lab_promotion_review_packet.py",
        "src/app/hammer_radar/operator/strategy_lab_variant_batch_runner.py",
        "src/app/hammer_radar/operator/strategy_lab_expansion_surface_map.py",
        "src/app/hammer_radar/operator/strategy_lab_variant_test_pack.py",
        "src/app/hammer_radar/operator/strategy_lab_preview.py",
        "src/app/hammer_radar/operator/paper_refresh_scheduler.py",
        "src/app/hammer_radar/operator/inspect.py",
        str(log_dir / "strategy_lab_promotion_review_packet.ndjson"),
        str(log_dir / "strategy_lab_variant_batch_runner.ndjson"),
        str(log_dir / "strategy_lab_variant_test_pack.ndjson"),
        str(log_dir / "strategy_evidence_registry.ndjson"),
        str(log_dir / "strategy_promotion_events.ndjson"),
    ]


def _latest_promotion_or_build(
    log_dir: Path,
    now: datetime,
    min_sample_count: int,
    preferred_sample_count: int,
) -> dict[str, Any]:
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


def _latest_batch_or_build(
    log_dir: Path,
    now: datetime,
    min_sample_count: int,
    preferred_sample_count: int,
) -> dict[str, Any]:
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


def _sanitize(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion")
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--feed", choices=("all", *FEED_IDS), default="all")
    parser.add_argument("--min-sample-count", type=int, default=30)
    parser.add_argument("--preferred-sample-count", type=int, default=50)
    args = parser.parse_args(argv)

    payload = build_strategy_lab_candidate_feed_expansion(
        log_dir=args.log_dir,
        write=not args.no_write,
        feed=args.feed,
        min_sample_count=args.min_sample_count,
        preferred_sample_count=args.preferred_sample_count,
    )
    if args.text:
        print(format_candidate_feed_expansion_text(payload))
    else:
        print(format_candidate_feed_expansion_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
