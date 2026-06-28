"""R325 read-only Strategy Lab promotion review packet."""

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
    DEFAULT_RISK_CONTRACT_PATH,
    TELEGRAM_SCOPE_COMPLETE_R322,
    build_strategy_lab_expansion_surface_map,
    surface_map_path,
)
from src.app.hammer_radar.operator.strategy_lab_variant_batch_runner import (
    READY as R324_READY,
    batch_runner_path,
    build_strategy_lab_variant_batch_runner,
)

EVENT_TYPE = "R325_STRATEGY_LAB_PROMOTION_REVIEW_PACKET"
CREATED_BY_PHASE = "R325_STRATEGY_LAB_PROMOTION_REVIEW_PACKET"
LEDGER_FILENAME = "strategy_lab_promotion_review_packet.ndjson"

READY = "STRATEGY_LAB_PROMOTION_REVIEW_READY"
BLOCKED = "STRATEGY_LAB_PROMOTION_REVIEW_BLOCKED"

REVIEW_READY_LANES = (
    "BTCUSDT|44m|short|ladder_382_50_618",
    "BTCUSDT|44m|short|ladder_close_50_618",
    "BTCUSDT|44m|short|ladder_22_44_22",
    "BTCUSDT|55m|long|ladder_close_50_618",
    "BTCUSDT|55m|long|market_close",
)
NEEDS_MORE_SAMPLES_LANES = (
    "BTCUSDT|13m|long|ladder_close_50_618",
    "BTCUSDT|13m|short|ladder_close_50_618",
    "BTCUSDT|8m|short|ladder_close_50_618",
)
WATCH_ONLY_LANES = ("BTCUSDT|88m|long|ladder_382_50_618",)
LAB_ONLY_LANES = ("BETRAYAL_INVERSE_LANES",)

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


def build_strategy_lab_promotion_review_packet(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    include_watch_only: bool = True,
    include_near_miss: bool = True,
    include_betrayal_lab: bool = True,
    min_sample_count: int = 30,
    preferred_sample_count: int = 50,
    standard_min_win_rate_pct: float = 55.0,
    betrayal_min_win_rate_pct: float = 60.0,
    batch_runner_packet: Mapping[str, Any] | None = None,
    surface_map_packet: Mapping[str, Any] | None = None,
    risk_contract_path: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    surface = dict(surface_map_packet) if isinstance(surface_map_packet, Mapping) else _latest_surface_or_build(resolved_log_dir, generated_at)
    batch = (
        dict(batch_runner_packet)
        if isinstance(batch_runner_packet, Mapping)
        else _latest_batch_or_build(
            log_dir=resolved_log_dir,
            now=generated_at,
            min_sample_count=min_sample_count,
            preferred_sample_count=preferred_sample_count,
            standard_min_win_rate_pct=standard_min_win_rate_pct,
            betrayal_min_win_rate_pct=betrayal_min_win_rate_pct,
            surface_map_packet=surface,
        )
    )
    risk_summary = build_r325_risk_contract_review_summary(
        review_ready_lanes=REVIEW_READY_LANES,
        risk_contract_path=risk_contract_path or DEFAULT_RISK_CONTRACT_PATH,
    )
    evidence = _evidence_by_lane(batch)
    observed = _observed_status_by_lane(surface)
    review_ready = [
        _candidate_packet(
            lane,
            source_bucket="ready_for_R325_review",
            evidence=evidence.get(lane, {}),
            risk_summary=risk_summary,
            observed_status=observed.get(lane, "NOT_CURRENTLY_OBSERVED"),
            min_sample_count=min_sample_count,
            standard_min_win_rate_pct=standard_min_win_rate_pct,
        )
        for lane in REVIEW_READY_LANES
    ]
    needs_more_samples = [
        _candidate_packet(
            lane,
            source_bucket="needs_more_samples",
            evidence=evidence.get(lane, {}),
            risk_summary=risk_summary,
            observed_status=observed.get(lane, "PAPER_LAB_REPAIR"),
            min_sample_count=min_sample_count,
            standard_min_win_rate_pct=standard_min_win_rate_pct,
        )
        for lane in NEEDS_MORE_SAMPLES_LANES
    ]
    watch_only = [
        _candidate_packet(
            lane,
            source_bucket="watch_only",
            evidence=evidence.get(lane, {}),
            risk_summary=risk_summary,
            observed_status=observed.get(lane, "WATCH_ONLY"),
            min_sample_count=min_sample_count,
            standard_min_win_rate_pct=standard_min_win_rate_pct,
        )
        for lane in WATCH_ONLY_LANES
    ]
    lab_only = list(LAB_ONLY_LANES) if include_betrayal_lab else []
    blockers = _packet_blockers(batch=batch, surface=surface, risk_summary=risk_summary)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "promotion_review_packet_id": f"r325_strategy_lab_promotion_review_packet_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_lab_promotion_review_packet_path": str(packet_path(resolved_log_dir)),
        "promotion_review_status": BLOCKED if blockers else READY,
        "blockers": blockers,
        "source_batch_runner_status": batch.get("batch_runner_status"),
        "source_surface_map_status": surface.get("surface_map_status"),
        "telegram_scope_status": surface.get("telegram_scope_status") or TELEGRAM_SCOPE_COMPLETE_R322,
        "current_tiny_live_status": surface.get("current_tiny_live_status"),
        "first_tiny_live_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
        "review_ready_candidates": review_ready,
        "observed_expansion_review_candidates": _observed_expansion_candidates(review_ready),
        "future_tiny_live_review_candidates": _future_tiny_live_candidates(review_ready),
        "needs_more_samples_candidates": needs_more_samples if include_near_miss else [],
        "watch_only_candidates": watch_only if include_watch_only else [],
        "lab_only_candidates": lab_only,
        "blocked_candidates": [],
        "betrayal_inverse_review_packet": _betrayal_inverse_packet(
            min_sample_count=min_sample_count,
            preferred_sample_count=preferred_sample_count,
            betrayal_min_win_rate_pct=betrayal_min_win_rate_pct,
        ),
        "risk_contract_review_summary": risk_summary,
        "evidence_quality_summary": _evidence_quality_summary(
            review_ready=review_ready,
            needs_more_samples=needs_more_samples,
            watch_only=watch_only,
        ),
        "promotion_policy_summary": _promotion_policy_summary(
            min_sample_count=min_sample_count,
            preferred_sample_count=preferred_sample_count,
            standard_min_win_rate_pct=standard_min_win_rate_pct,
            betrayal_min_win_rate_pct=betrayal_min_win_rate_pct,
        ),
        "human_review_required": True,
        "promotion_event_written": False,
        "risk_contract_config_mutated": False,
        "recommended_operator_decisions": _recommended_operator_decisions(),
        "recommended_r326_path": _recommended_r326_path(),
        "recommended_r327_path": _recommended_r327_path(),
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


def build_r325_risk_contract_review_summary(
    *,
    review_ready_lanes: Sequence[str],
    risk_contract_path: str | Path,
) -> dict[str, Any]:
    path = Path(risk_contract_path)
    contracts = _read_contracts(path)
    by_lane = {_contract_lane_key(row): row for row in contracts if _contract_lane_key(row)}
    present = [lane for lane in review_ready_lanes if lane in by_lane]
    missing = [lane for lane in review_ready_lanes if lane not in by_lane]
    validity = {lane: _contract_valid(by_lane.get(lane)) for lane in review_ready_lanes}
    return {
        "risk_contract_source_path": str(path),
        "source_exists": path.exists(),
        "source_read_only": True,
        "total_contracts": len(contracts),
        "contracts_present_for_review_ready": present,
        "contracts_missing_for_review_ready": missing,
        "contract_validity_by_review_ready_lane": validity,
        "all_review_ready_contracts_valid": bool(review_ready_lanes) and all(validity.values()),
        "risk_contract_config_mutated": False,
        "config_written": False,
    }


def append_packet(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = packet_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_strategy_lab_promotion_review_packet_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(packet_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def packet_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_promotion_review_packet_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_promotion_review_packet_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R325 STRATEGY LAB PROMOTION REVIEW PACKET",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        f"promotion_review_status: {payload.get('promotion_review_status')}",
        "",
        "FIRST TINY LIVE LANE",
        f"first_tiny_live_lane: {payload.get('first_tiny_live_lane')}",
        f"first_live_lane_change_allowed: {payload.get('first_live_lane_change_allowed')}",
        "",
        "REVIEW-READY CANDIDATES",
        *_format_candidate_rows(payload.get("review_ready_candidates")),
        "",
        "OBSERVED EXPANSION REVIEW CANDIDATES",
        *[str(item) for item in payload.get("observed_expansion_review_candidates") or ["none"]],
        "",
        "FUTURE TINY-LIVE REVIEW CANDIDATES",
        *[str(item) for item in payload.get("future_tiny_live_review_candidates") or ["none"]],
        "",
        "NEEDS-MORE-SAMPLES CANDIDATES",
        *_format_candidate_rows(payload.get("needs_more_samples_candidates")),
        "",
        "WATCH-ONLY CANDIDATES",
        *_format_candidate_rows(payload.get("watch_only_candidates")),
        "",
        "BETRAYAL/INVERSE LAB-ONLY PACKET",
    ]
    betrayal = payload.get("betrayal_inverse_review_packet") if isinstance(payload.get("betrayal_inverse_review_packet"), Mapping) else {}
    for key in (
        "lab_only",
        "tiny_live_eligible_now",
        "standard_55_policy_applies",
        "preferred_win_rate_pct",
        "min_sample_count",
        "preferred_sample_count",
        "avg_pnl_requirement",
        "original_vs_inverse_required",
        "source_chain_required",
        "exact_risk_mapping_required",
        "stale_shadow_outcomes_forbidden",
        "promotion_review_allowed",
        "live_permission",
    ):
        lines.append(f"{key}: {betrayal.get(key)}")
    lines.extend(["", "RISK CONTRACT SUMMARY"])
    risk = payload.get("risk_contract_review_summary") if isinstance(payload.get("risk_contract_review_summary"), Mapping) else {}
    lines.extend(
        [
            f"total_contracts: {risk.get('total_contracts')}",
            "contracts_present_for_review_ready: "
            + (",".join(risk.get("contracts_present_for_review_ready") or []) or "none"),
            "contracts_missing_for_review_ready: "
            + (",".join(risk.get("contracts_missing_for_review_ready") or []) or "none"),
            f"all_review_ready_contracts_valid: {risk.get('all_review_ready_contracts_valid')}",
            f"risk_contract_config_mutated: {risk.get('risk_contract_config_mutated')}",
            "",
            "RECOMMENDED OPERATOR DECISIONS",
        ]
    )
    for item in payload.get("recommended_operator_decisions") or []:
        lines.append(str(item))
    lines.extend(["", "RECOMMENDED R326/R327 PATH"])
    lines.append(str(payload.get("recommended_r326_path")))
    lines.append(str(payload.get("recommended_r327_path")))
    lines.extend(["", "RECOMMENDED TINY LIVE PATH"])
    for item in payload.get("recommended_tiny_live_path") or []:
        lines.append(str(item))
    lines.extend(["", "SAFETY FLAGS"])
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    for key in SAFETY:
        lines.append(f"{key}: {safety.get(key)}")
    return "\n".join(lines)


def _candidate_packet(
    lane_key: str,
    *,
    source_bucket: str,
    evidence: Mapping[str, Any],
    risk_summary: Mapping[str, Any],
    observed_status: str,
    min_sample_count: int,
    standard_min_win_rate_pct: float,
) -> dict[str, Any]:
    sample_count = _int_or_none(evidence.get("sample_count"))
    win_rate_pct = _float_or_none(evidence.get("win_rate_pct"))
    avg_pnl_pct = _float_or_none(evidence.get("avg_pnl_pct"))
    risk_validity = risk_summary.get("contract_validity_by_review_ready_lane")
    risk_valid_by_lane = risk_validity if isinstance(risk_validity, Mapping) else {}
    risk_contract_present = lane_key in set(risk_summary.get("contracts_present_for_review_ready") or [])
    risk_contract_valid = bool(risk_valid_by_lane.get(lane_key))
    evidence_ready = (
        (sample_count or 0) >= min_sample_count
        and (win_rate_pct or 0.0) >= standard_min_win_rate_pct
        and (avg_pnl_pct or 0.0) > 0.0
    )
    blockers = _candidate_blockers(
        evidence_ready=evidence_ready,
        risk_contract_present=risk_contract_present,
        risk_contract_valid=risk_contract_valid,
        source_bucket=source_bucket,
    )
    return {
        "lane_key": lane_key,
        "source_bucket": source_bucket,
        "sample_count": sample_count,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "evidence_status": evidence.get("evidence_status") or "SOURCE_MISSING",
        "risk_contract_present": risk_contract_present,
        "risk_contract_valid": risk_contract_valid,
        "observed_status": observed_status,
        "recommended_decision": _recommended_decision(
            source_bucket=source_bucket,
            evidence_ready=evidence_ready,
            risk_contract_valid=risk_contract_valid,
        ),
        "live_permission": False,
        "tiny_live_eligible_now": False,
        "human_review_required": True,
        "blockers": blockers,
    }


def _candidate_blockers(
    *,
    evidence_ready: bool,
    risk_contract_present: bool,
    risk_contract_valid: bool,
    source_bucket: str,
) -> list[str]:
    blockers = ["human_review_required", "tiny_live_separate_final_gate_required"]
    if source_bucket == "needs_more_samples":
        blockers.append("needs_more_samples_or_variant_repair")
    if source_bucket == "watch_only":
        blockers.append("watch_only_not_promotion")
    if not evidence_ready:
        blockers.append("standard_evidence_threshold_not_met")
    if not risk_contract_present:
        blockers.append("risk_contract_missing")
    elif not risk_contract_valid:
        blockers.append("risk_contract_invalid")
    return blockers


def _recommended_decision(*, source_bucket: str, evidence_ready: bool, risk_contract_valid: bool) -> str:
    if source_bucket == "needs_more_samples" or not evidence_ready:
        return "NEEDS_MORE_EVIDENCE"
    if source_bucket == "watch_only":
        return "KEEP_OBSERVED_DRY_RUN"
    if evidence_ready and risk_contract_valid:
        return "CONSIDER_FUTURE_TINY_LIVE_REVIEW"
    return "CONSIDER_OBSERVED_EXPANSION_REVIEW"


def _evidence_by_lane(batch: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for row in batch.get("batch_results") or []:
        if not isinstance(row, Mapping):
            continue
        snapshots = row.get("current_evidence_snapshot") if isinstance(row.get("current_evidence_snapshot"), Mapping) else {}
        for lane, snapshot in snapshots.items():
            if isinstance(snapshot, Mapping):
                evidence[str(lane)] = dict(snapshot)
    return evidence


def _observed_status_by_lane(surface: Mapping[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for row in surface.get("observed_primary_lanes") or []:
        if isinstance(row, Mapping) and row.get("lane_key"):
            statuses[str(row["lane_key"])] = "PRIMARY_OBSERVED_DRY_RUN"
    for row in surface.get("observed_secondary_watch_lanes") or []:
        if isinstance(row, Mapping) and row.get("lane_key"):
            statuses[str(row["lane_key"])] = "SECONDARY_WATCH_ONLY"
    statuses[BASELINE_LANE] = "FIRST_TINY_LIVE_BASELINE"
    return statuses


def _observed_expansion_candidates(review_ready: Sequence[Mapping[str, Any]]) -> list[str]:
    return [
        str(row["lane_key"])
        for row in review_ready
        if row.get("source_bucket") == "ready_for_R325_review"
        and row.get("evidence_status") == "DIRECT_PAPER_EVIDENCE"
    ]


def _future_tiny_live_candidates(review_ready: Sequence[Mapping[str, Any]]) -> list[str]:
    return [
        str(row["lane_key"])
        for row in review_ready
        if row.get("recommended_decision") == "CONSIDER_FUTURE_TINY_LIVE_REVIEW"
    ]


def _packet_blockers(*, batch: Mapping[str, Any], surface: Mapping[str, Any], risk_summary: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if batch.get("batch_runner_status") != R324_READY:
        blockers.append("source_r324_batch_runner_not_ready")
    if not surface.get("surface_map_status"):
        blockers.append("source_r323_surface_map_status_missing")
    if risk_summary.get("source_exists") is not True:
        blockers.append("risk_contract_source_missing")
    return blockers


def _betrayal_inverse_packet(
    *,
    min_sample_count: int,
    preferred_sample_count: int,
    betrayal_min_win_rate_pct: float,
) -> dict[str, Any]:
    return {
        "lane_key": "BETRAYAL_INVERSE_LANES",
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
        "promotion_review_allowed": False,
        "stricter_future_gate_required": True,
        "live_permission": False,
        "human_review_required": True,
    }


def _evidence_quality_summary(
    *,
    review_ready: Sequence[Mapping[str, Any]],
    needs_more_samples: Sequence[Mapping[str, Any]],
    watch_only: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "review_ready_direct_evidence_count": sum(1 for row in review_ready if row.get("evidence_status") == "DIRECT_PAPER_EVIDENCE"),
        "review_ready_count": len(review_ready),
        "needs_more_samples_count": len(needs_more_samples),
        "watch_only_count": len(watch_only),
        "direct_evidence_required_before_promotion": True,
        "real_candidate_detection_required_before_tiny_live": True,
    }


def _promotion_policy_summary(
    *,
    min_sample_count: int,
    preferred_sample_count: int,
    standard_min_win_rate_pct: float,
    betrayal_min_win_rate_pct: float,
) -> dict[str, Any]:
    return {
        "standard_min_sample_count": min_sample_count,
        "standard_preferred_sample_count": preferred_sample_count,
        "standard_min_win_rate_pct": standard_min_win_rate_pct,
        "standard_avg_pnl_requirement": "positive",
        "risk_contract_present_valid_preferred_not_live_sufficient": True,
        "human_review_required": True,
        "writes_promotion_events": False,
        "writes_risk_contracts": False,
        "betrayal_standard_55_policy_applies": False,
        "betrayal_min_win_rate_pct": betrayal_min_win_rate_pct,
    }


def _recommended_operator_decisions() -> list[str]:
    return [
        "Keep baseline Tiny Live lane unchanged.",
        "Keep current primary observed lanes observing.",
        "Consider moving strong 44m/55m watch-only lanes into human observed-expansion review only.",
        "Collect more samples for 13m and 8m variants.",
        "Keep Betrayal/inverse lab-only.",
        "Prepare candidate feed expansion for anchor, exit, and near-miss variants.",
        "Wait for real candidate detection before Tiny Live.",
    ]


def _recommended_r326_path() -> dict[str, str]:
    return {
        "phase": "R326 Candidate Feed Expansion for Strategy Lab Variants",
        "purpose": "Expand data capture and evidence feeds for anchor, exit, near-miss, and variant candidates.",
        "live_permission": "false",
    }


def _recommended_r327_path() -> dict[str, str]:
    return {
        "phase": "R327 Human-Reviewed Observed Expansion Promotion Gate",
        "purpose": "Later human-reviewed gate to alter observed expansion only, not live execution.",
        "tiny_live_separately_gated": "true",
    }


def _recommended_tiny_live_path() -> list[str]:
    return [
        "First Tiny Live remains BTCUSDT|44m|long|ladder_close_50_618.",
        "Future Tiny Live requires separate human approval, exact risk contract, real candidate detection, and final gate clearance.",
        "Current Tiny Live path must wait for real candidate detection before any final review.",
        "R325 does not change Tiny Live, does not submit, and does not create a final command.",
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
        "no_config_or_env_mutation": True,
        "no_systemd_mutation": True,
        "no_scheduler_start": True,
        "no_telegram_send": True,
    }


def _source_surfaces(log_dir: Path) -> list[str]:
    return [
        "docs/hammer_radar/live_readiness/R324_STRATEGY_LAB_VARIANT_BATCH_RUNNER.md",
        "docs/hammer_radar/live_readiness/R323_STRATEGY_LAB_EXPANSION_REENTRY_AND_CANDIDATE_SURFACE_MAP.md",
        "docs/hammer_radar/live_readiness/R306_ELIGIBLE_LANE_EXPANSION_DRY_RUN_PREVIEW.md",
        "docs/hammer_radar/live_readiness/R307_EXPANSION_RISK_CONTRACT_PREVIEW_REPAIR.md",
        "docs/hammer_radar/live_readiness/R308_EXPANSION_RISK_CONTRACT_WRITE_GATE_PREVIEW.md",
        "docs/hammer_radar/live_readiness/R309_HUMAN_REVIEWED_RISK_CONTRACT_WRITE_GATE.md",
        "src/app/hammer_radar/operator/strategy_lab_variant_batch_runner.py",
        "src/app/hammer_radar/operator/strategy_lab_expansion_surface_map.py",
        "src/app/hammer_radar/operator/eligible_lane_expansion_dry_run_preview.py",
        "src/app/hammer_radar/operator/expansion_risk_contract_preview_repair.py",
        "configs/hammer_radar/tiny_live_risk_contracts.json",
        str(log_dir / "strategy_lab_variant_batch_runner.ndjson"),
        str(log_dir / "strategy_lab_expansion_surface_map.ndjson"),
        str(log_dir / "strategy_promotion_events.ndjson"),
        str(log_dir / "strategy_evidence_registry.ndjson"),
    ]


def _latest_surface_or_build(log_dir: Path, now: datetime) -> dict[str, Any]:
    latest = _read_latest_ndjson_record(surface_map_path(log_dir))
    if latest:
        return latest
    return build_strategy_lab_expansion_surface_map(log_dir=log_dir, write=False, now=now)


def _latest_batch_or_build(
    *,
    log_dir: Path,
    now: datetime,
    min_sample_count: int,
    preferred_sample_count: int,
    standard_min_win_rate_pct: float,
    betrayal_min_win_rate_pct: float,
    surface_map_packet: Mapping[str, Any],
) -> dict[str, Any]:
    latest = _read_latest_ndjson_record(batch_runner_path(log_dir))
    if latest:
        return latest
    return build_strategy_lab_variant_batch_runner(
        log_dir=log_dir,
        write=False,
        now=now,
        min_sample_count=min_sample_count,
        preferred_sample_count=preferred_sample_count,
        standard_min_win_rate_pct=standard_min_win_rate_pct,
        betrayal_min_win_rate_pct=betrayal_min_win_rate_pct,
        surface_map_packet=surface_map_packet,
    )


def _read_latest_ndjson_record(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    latest = _read_latest_ndjson_line(path)
    if not latest:
        return {}
    try:
        record = json.loads(latest)
    except json.JSONDecodeError:
        return {}
    return dict(record) if isinstance(record, Mapping) else {}


def _read_latest_ndjson_line(path: Path, *, chunk_size: int = 262_144, max_bytes: int = 16_777_216) -> str:
    size = path.stat().st_size
    if size <= 0:
        return ""
    data = b""
    with path.open("rb") as handle:
        offset = size
        while offset > 0 and len(data) < max_bytes:
            read_size = min(chunk_size, offset)
            offset -= read_size
            handle.seek(offset)
            data = handle.read(read_size) + data
            lines = [line.strip() for line in data.splitlines() if line.strip()]
            if lines and (len(lines) > 1 or offset == 0):
                return lines[-1].decode("utf-8")
    lines = [line.strip() for line in data.splitlines() if line.strip()]
    return lines[-1].decode("utf-8") if lines else ""


def _read_contracts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    rows = raw.get("risk_contracts") if isinstance(raw, Mapping) else raw
    return [dict(row) for row in rows or [] if isinstance(row, Mapping)]


def _contract_lane_key(row: Mapping[str, Any]) -> str | None:
    explicit = row.get("official_lane_key") or row.get("lane_key")
    if explicit:
        return str(explicit)
    symbol = row.get("symbol")
    timeframe = row.get("timeframe")
    direction = row.get("direction")
    entry_mode = row.get("entry_mode")
    if all((symbol, timeframe, direction, entry_mode)):
        return f"{symbol}|{timeframe}|{direction}|{entry_mode}"
    return None


def _contract_valid(row: Mapping[str, Any] | None) -> bool:
    if not row:
        return False
    return (
        row.get("live_execution_enabled") is False
        and row.get("allow_live_orders") is False
        and row.get("leverage") is not None
        and row.get("max_loss_usdt") is not None
    )


def _format_candidate_rows(value: object) -> list[str]:
    rows = value if isinstance(value, list) else []
    lines: list[str] = []
    for row in rows:
        if isinstance(row, Mapping):
            lines.append(
                f"{row.get('lane_key')} | bucket={row.get('source_bucket')} "
                f"samples={row.get('sample_count')} win={row.get('win_rate_pct')} "
                f"avg={row.get('avg_pnl_pct')} decision={row.get('recommended_decision')} "
                f"live_permission={row.get('live_permission')} tiny_live_eligible_now={row.get('tiny_live_eligible_now')}"
            )
    return lines or ["none"]


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
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.strategy_lab_promotion_review_packet")
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--include-watch-only", action="store_true", default=True)
    parser.add_argument("--include-near-miss", action="store_true", default=True)
    parser.add_argument("--include-betrayal-lab", action="store_true", default=True)
    parser.add_argument("--min-sample-count", type=int, default=30)
    parser.add_argument("--preferred-sample-count", type=int, default=50)
    parser.add_argument("--standard-min-win-rate-pct", type=float, default=55.0)
    parser.add_argument("--betrayal-min-win-rate-pct", type=float, default=60.0)
    args = parser.parse_args(argv)

    payload = build_strategy_lab_promotion_review_packet(
        log_dir=args.log_dir,
        write=not args.no_write,
        include_watch_only=args.include_watch_only,
        include_near_miss=args.include_near_miss,
        include_betrayal_lab=args.include_betrayal_lab,
        min_sample_count=args.min_sample_count,
        preferred_sample_count=args.preferred_sample_count,
        standard_min_win_rate_pct=args.standard_min_win_rate_pct,
        betrayal_min_win_rate_pct=args.betrayal_min_win_rate_pct,
    )
    if args.text:
        print(format_promotion_review_packet_text(payload))
    else:
        print(format_promotion_review_packet_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
