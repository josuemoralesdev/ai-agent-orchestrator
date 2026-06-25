"""R305 paper-only Strategy Lab variant test pack.

This module extends the R304 Strategy Lab preview with conservative variant
rows. It reads existing paper evidence only; missing variant evidence is marked
for capture instead of being simulated.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.paper_refresh_scheduler import scheduler_status
from src.app.hammer_radar.operator.strategy_lab_preview import (
    BETRAYAL_BLOCKED_PREVIEW_ONLY,
    BETRAYAL_INVERSE_PREVIEW,
    CURRENT_TINY_LIVE_LANE,
    EXPANSION_PREVIEW_ONLY,
    KEEP_TINY_LIVE_WAIT,
    build_strategy_lab_preview,
)
from src.app.hammer_radar.operator.tiny_live_final_authorization_gate import (
    build_status_tiny_live_final_authorization_gate,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    LIVE_QUALIFIED,
    NEAR_MISS_INCUBATOR,
    PAPER_ONLY,
    build_lane_key,
)

EVENT_TYPE = "R305_STRATEGY_LAB_VARIANT_TEST_PACK"
CREATED_BY_PHASE = "R305_STRATEGY_LAB_VARIANT_TEST_PACK"
LEDGER_FILENAME = "strategy_lab_variant_test_pack.ndjson"

INSUFFICIENT_DIRECT_VARIANT_EVIDENCE = "INSUFFICIENT_DIRECT_VARIANT_EVIDENCE"
NEEDS_PAPER_CAPTURE = "NEEDS_PAPER_CAPTURE"
DIRECT_PAPER_EVIDENCE = "DIRECT_PAPER_EVIDENCE"
CAPTURE_VARIANT_EVIDENCE = "CAPTURE_VARIANT_EVIDENCE"
KEEP_CURRENT_FIRST_TINY_LIVE_LANE_UNCHANGED = "KEEP_CURRENT_FIRST_TINY_LIVE_LANE_UNCHANGED"
PAPER_ONLY_RANKING_REVIEW = "PAPER_ONLY_RANKING_REVIEW"
BETRAYAL_CAPTURE_PRIORITY = "BETRAYAL_CAPTURE_PRIORITY"
BETRAYAL_BLOCKED_FROM_TINY_LIVE = "BETRAYAL_BLOCKED_FROM_TINY_LIVE"

HIGH_PAPER_CONFIDENCE = "HIGH_PAPER_CONFIDENCE"
MEDIUM_PAPER_CONFIDENCE = "MEDIUM_PAPER_CONFIDENCE"
LOW_PAPER_CONFIDENCE = "LOW_PAPER_CONFIDENCE"
BLOCKED = "BLOCKED"

ENTRY_MODES = (
    "ladder_close_50_618",
    "ladder_382_50_618",
    "ladder_22_44_22",
    "market_close",
    "fib_618",
    "fib_650",
)
TIMING_VARIANTS = (
    "close_entry",
    "delayed_one_candle",
    "freshness_strict",
    "freshness_relaxed_preview_only",
)
TPSL_VARIANTS = (
    "current_baseline",
    "tighter_stop_preview",
    "wider_stop_preview",
    "earlier_take_profit_preview",
    "later_take_profit_preview",
)
TRAILING_VARIANTS = (
    "no_trailing",
    "breakeven_after_partial_mfe_preview",
    "trailing_after_tp1_preview",
)
FILTER_VARIANTS = (
    "no_extra_filter",
    "RSI_extreme_filter_preview",
    "RSI_divergence_filter_preview",
    "HTF_bias_filter_preview",
    "trend_strength_filter_preview",
    "volatility_filter_preview",
)

TOP_R304_LANES = (
    CURRENT_TINY_LIVE_LANE,
    "BTCUSDT|44m|short|ladder_close_50_618",
    "BTCUSDT|55m|long|ladder_close_50_618",
    "BTCUSDT|44m|short|ladder_382_50_618",
    "BTCUSDT|44m|short|ladder_22_44_22",
    "BTCUSDT|44m|long|ladder_382_50_618",
    "BTCUSDT|88m|long|ladder_382_50_618",
    "BTCUSDT|55m|long|market_close",
    "BTCUSDT|44m|long|ladder_22_44_22",
)
NEAR_MISS_LANES = (
    "BTCUSDT|22m|long|ladder_close_50_618",
    "BTCUSDT|22m|short|ladder_close_50_618",
    "BTCUSDT|8m|short|ladder_close_50_618",
    "BTCUSDT|88m|long|ladder_22_44_22",
    "BTCUSDT|55m|long|ladder_382_50_618",
)
BROADER_PAPER_LANES = tuple(
    build_lane_key(symbol="BTCUSDT", timeframe=timeframe, direction=direction)
    for timeframe in ("4m", "8m", "13m", "88m")
    for direction in ("long", "short")
) + tuple(
    build_lane_key(symbol="BTCUSDT", timeframe=timeframe, direction=direction)
    for timeframe in ("222m", "444m", "888m")
    for direction in ("long", "short")
)

SAFETY = {
    "live_execution_enabled": False,
    "allow_live_orders": False,
    "global_kill_switch": True,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "submit_allowed": False,
    "final_command_available": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "secrets_shown": False,
    "secret_values_in_output": False,
    "kill_switch_disabled": False,
    "global_live_flags_changed": False,
    "autonomous_arming_state_changed": False,
    "risk_contract_config_mutated": False,
    "paper_live_separation_intact": True,
    "real_order_forbidden": True,
    "betrayal_live_permission": False,
}


def build_strategy_lab_variant_test_pack(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    r304 = build_strategy_lab_preview(log_dir=resolved_log_dir, write=False, now=generated_at)
    evidence_by_lane = {
        str(row.get("lane_key")): dict(row)
        for row in r304.get("preview_candidates", [])
        if isinstance(row, Mapping) and row.get("lane_key")
    }
    candidate_families = _candidate_families(evidence_by_lane)
    variant_candidates = _build_variant_rows(evidence_by_lane=evidence_by_lane, candidate_families=candidate_families)
    top_variants = _top_variants(variant_candidates)
    betrayal = _build_betrayal_rows(r304, evidence_by_lane=evidence_by_lane)
    final_gate = build_status_tiny_live_final_authorization_gate(log_dir=resolved_log_dir)
    refresh = scheduler_status(log_dir=resolved_log_dir)

    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "variant_pack_id": f"r305_strategy_lab_variant_test_pack_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_lab_variant_test_pack_path": str(strategy_lab_variant_test_pack_path(resolved_log_dir)),
        "current_tiny_live_lane": CURRENT_TINY_LIVE_LANE,
        "current_tiny_live_lane_status": _current_lane_status(evidence_by_lane, variant_candidates),
        "candidate_family_count": len(candidate_families),
        "variant_candidate_count": len(variant_candidates),
        "direct_evidence_variant_count": sum(1 for row in variant_candidates if row["evidence_status"] == DIRECT_PAPER_EVIDENCE),
        "needs_capture_variant_count": sum(1 for row in variant_candidates if row["variant_score_status"] == NEEDS_PAPER_CAPTURE),
        "candidate_families": candidate_families,
        "variant_candidates": variant_candidates,
        "top_variant_candidates": top_variants,
        "top_near_miss_variant_opportunities": _top_near_miss(variant_candidates),
        "betrayal_inverse_lab_preview": betrayal,
        "recommended_next_phase": _recommended_next_phase(top_variants),
        "final_gate_summary": {
            "status": final_gate.get("status"),
            "submit_allowed": False,
            "final_command_available": False,
            "current_real_candidate_lane_key": final_gate.get("current_real_candidate_lane_key"),
            "armed_lane_key": final_gate.get("armed_lane_key") or final_gate.get("requested_lane_key"),
        },
        "paper_refresh_health": {
            "paper_refresh_health_status": refresh.get("paper_refresh_health_status"),
            "runs_recorded": refresh.get("runs_recorded"),
            "last_run": refresh.get("last_run"),
        },
        "source_surfaces_used": [
            "src/app/hammer_radar/operator/strategy_lab_preview.py",
            "src/app/hammer_radar/operator/strategy_promotion_watcher.py",
            "src/app/hammer_radar/operator/strategy_performance.py",
            "logs/hammer_radar_forward/strategy_lab_preview.ndjson",
            "logs/hammer_radar_forward/strategy_promotion_status.ndjson",
            "logs/hammer_radar_forward/strategy_promotion_events.ndjson",
            "logs/hammer_radar_forward/strategy_performance.ndjson",
            "logs/hammer_radar_forward/outcomes.ndjson",
            "logs/hammer_radar_forward/signals.ndjson",
            "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
            "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
        ],
        "safety": dict(SAFETY),
        **_top_level_safety_fields(),
    }
    safe_payload = _sanitize(payload)
    if write:
        append_strategy_lab_variant_test_pack(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def append_strategy_lab_variant_test_pack(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = strategy_lab_variant_test_pack_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_strategy_lab_variant_test_pack_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(
        strategy_lab_variant_test_pack_path(get_log_dir(log_dir, use_env=True)),
        limit=limit,
        max_bytes=8_388_608,
    )


def strategy_lab_variant_test_pack_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_strategy_lab_variant_test_pack_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_strategy_lab_variant_test_pack_text(payload: Mapping[str, Any], *, top_limit: int = 10) -> str:
    lines = [
        "R305 STRATEGY LAB VARIANT TEST PACK",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        "",
        "FINAL GATE SUMMARY",
    ]
    gate = payload.get("final_gate_summary") if isinstance(payload.get("final_gate_summary"), Mapping) else {}
    lines.extend(
        [
            f"status: {gate.get('status')}",
            f"submit_allowed: {gate.get('submit_allowed')}",
            f"final_command_available: {gate.get('final_command_available')}",
            f"current_real_candidate_lane_key: {gate.get('current_real_candidate_lane_key')}",
            f"armed_lane_key: {gate.get('armed_lane_key')}",
            "",
            "PAPER REFRESH HEALTH",
        ]
    )
    refresh = payload.get("paper_refresh_health") if isinstance(payload.get("paper_refresh_health"), Mapping) else {}
    last_run = refresh.get("last_run") if isinstance(refresh.get("last_run"), Mapping) else {}
    lines.extend(
        [
            f"paper_refresh_health_status: {refresh.get('paper_refresh_health_status')}",
            f"runs_recorded: {refresh.get('runs_recorded')}",
            f"last_failed_tasks: {','.join(last_run.get('failed_tasks') or []) or 'none'}",
            "",
            f"TOP {top_limit} VARIANT CANDIDATES",
        ]
    )
    for row in list(payload.get("top_variant_candidates") or [])[:top_limit]:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"{row.get('lab_rank')}. {row.get('variant_key')} | score={row.get('strategy_lab_score')} "
            f"confidence={row.get('confidence_class')} samples={row.get('direct_sample_count')} "
            f"win={row.get('win_rate_pct')} avg={row.get('avg_pnl_pct')} action={row.get('recommended_lab_action')}"
        )
    if not payload.get("top_variant_candidates"):
        lines.append("none")
    lines.extend(["", "CURRENT FIRST TINY-LIVE LANE VARIANT STATUS"])
    current = payload.get("current_tiny_live_lane_status") if isinstance(payload.get("current_tiny_live_lane_status"), Mapping) else {}
    lines.extend(
        [
            f"lane_key: {current.get('lane_key')}",
            f"best_variant_key: {current.get('best_variant_key')}",
            f"best_strategy_lab_score: {current.get('best_strategy_lab_score')}",
            f"recommended_lab_action: {current.get('recommended_lab_action')}",
            f"tiny_live_lane_unchanged: {current.get('tiny_live_lane_unchanged')}",
            "",
            "TOP NEAR-MISS VARIANT OPPORTUNITIES",
        ]
    )
    for row in payload.get("top_near_miss_variant_opportunities") or []:
        if isinstance(row, Mapping):
            lines.append(
                f"{row.get('variant_key')} | score={row.get('strategy_lab_score')} samples={row.get('direct_sample_count')} "
                f"win={row.get('win_rate_pct')} avg={row.get('avg_pnl_pct')}"
            )
    if not payload.get("top_near_miss_variant_opportunities"):
        lines.append("none")
    lines.extend(["", "BETRAYAL/INVERSE CAPTURE PRIORITIES"])
    betrayal = payload.get("betrayal_inverse_lab_preview") if isinstance(payload.get("betrayal_inverse_lab_preview"), Mapping) else {}
    for row in betrayal.get("capture_priorities") or []:
        if isinstance(row, Mapping):
            lines.append(
                f"{row.get('lane_key')} | samples={row.get('true_paper_outcomes_count')}/{row.get('true_paper_min_samples_required')} "
                f"progress={row.get('sample_progress_pct')} decision={row.get('betrayal_gate_decision')}"
            )
    if not betrayal.get("capture_priorities"):
        lines.append("none")
    lines.extend(["", "SAFETY FLAGS"])
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    for key in (
        "live_execution_enabled",
        "allow_live_orders",
        "global_kill_switch",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "submit_allowed",
        "final_command_available",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "secrets_shown",
    ):
        lines.append(f"{key}: {safety.get(key)}")
    lines.extend(["", "RECOMMENDED NEXT PHASE", str(payload.get("recommended_next_phase"))])
    return "\n".join(lines)


def _candidate_families(evidence_by_lane: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    keys = [*TOP_R304_LANES, *NEAR_MISS_LANES, *BROADER_PAPER_LANES, *evidence_by_lane.keys()]
    rows: list[dict[str, Any]] = []
    for lane_key in dict.fromkeys(keys):
        symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
        family_key = build_lane_key(symbol=symbol, timeframe=timeframe, direction=direction, entry_mode=entry_mode)
        evidence = evidence_by_lane.get(family_key, {})
        rows.append(
            {
                "lane_key": family_key,
                "symbol": symbol,
                "timeframe": timeframe,
                "direction": direction,
                "entry_mode": entry_mode,
                "family": _family_label(family_key),
                "watch_category": evidence.get("watch_category") or _default_watch_category(family_key),
                "included_by_r305": family_key in {*TOP_R304_LANES, *NEAR_MISS_LANES, *BROADER_PAPER_LANES},
                "has_direct_existing_evidence": _has_direct_evidence(evidence),
            }
        )
    return rows


def _build_variant_rows(
    *,
    evidence_by_lane: Mapping[str, Mapping[str, Any]],
    candidate_families: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_triplets = list(
        dict.fromkeys(
            (row.get("symbol"), row.get("timeframe"), row.get("direction"))
            for row in candidate_families
            if row.get("symbol") and row.get("timeframe") and row.get("direction") in {"long", "short"}
        )
    )
    for symbol, timeframe, direction in base_triplets:
        for entry_mode in ENTRY_MODES:
            lane_key = build_lane_key(symbol=symbol, timeframe=timeframe, direction=direction, entry_mode=entry_mode)
            rows.append(
                _variant_row(
                    lane_key=lane_key,
                    variant_axis="entry_mode",
                    variant_value=entry_mode,
                    timing="close_entry",
                    tpsl="current_baseline",
                    trailing="no_trailing",
                    filter_name="no_extra_filter",
                    evidence=evidence_by_lane.get(lane_key, {}),
                )
            )
        base_entry = str(_best_known_entry(symbol, timeframe, direction, evidence_by_lane) or "ladder_close_50_618")
        for timing in TIMING_VARIANTS:
            if timing != "close_entry":
                rows.append(_synthetic_capture_row(symbol, timeframe, direction, base_entry, "timing", timing))
        for tpsl in TPSL_VARIANTS:
            if tpsl != "current_baseline":
                rows.append(_synthetic_capture_row(symbol, timeframe, direction, base_entry, "tp_sl", tpsl))
        for trailing in TRAILING_VARIANTS:
            if trailing != "no_trailing":
                rows.append(_synthetic_capture_row(symbol, timeframe, direction, base_entry, "trailing", trailing))
        for filter_name in FILTER_VARIANTS:
            if filter_name != "no_extra_filter":
                rows.append(_synthetic_capture_row(symbol, timeframe, direction, base_entry, "filter", filter_name))
    ranked = sorted(rows, key=_variant_sort_key, reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["lab_rank"] = index
    return ranked


def _variant_row(
    *,
    lane_key: str,
    variant_axis: str,
    variant_value: str,
    timing: str,
    tpsl: str,
    trailing: str,
    filter_name: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    has_direct = _has_direct_evidence(evidence)
    direct_sample_count = _int_or_none(evidence.get("sample_count")) if has_direct else 0
    win_rate_pct = _float_or_none(evidence.get("win_rate_pct")) if has_direct else None
    avg_pnl_pct = _float_or_none(evidence.get("avg_pnl_pct")) if has_direct else None
    fill_rate_pct = _float_or_none(evidence.get("fill_rate_pct")) if has_direct else None
    stop_rate_pct = _float_or_none(evidence.get("stop_rate_pct")) if has_direct else None
    score_parts = _score_parts(
        sample_count=direct_sample_count,
        win_rate_pct=win_rate_pct,
        avg_pnl_pct=avg_pnl_pct,
        fill_rate_pct=fill_rate_pct,
        stop_rate_pct=stop_rate_pct,
        evidence_quality=1.0 if has_direct else 0.0,
        freshness_status=str(evidence.get("freshness_status") or ""),
        betrayal=False,
    )
    score = round(sum(score_parts.values()), 4) if has_direct else 0.0
    confidence = _confidence_class(
        has_direct=has_direct,
        sample_count=direct_sample_count,
        win_rate_pct=win_rate_pct,
        avg_pnl_pct=avg_pnl_pct,
        score=score,
    )
    recommended = _recommended_action(lane_key=lane_key, confidence=confidence, evidence=evidence, has_direct=has_direct)
    return {
        "variant_key": _variant_key(lane_key, variant_axis, variant_value, timing, tpsl, trailing, filter_name),
        "lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "variant_axis": variant_axis,
        "entry_mode_variant": entry_mode,
        "timing": timing,
        "tp_sl": tpsl,
        "trailing": trailing,
        "filter": filter_name,
        "watch_category": evidence.get("watch_category") or _default_watch_category(lane_key),
        "family": _family_label(lane_key),
        "evidence_status": DIRECT_PAPER_EVIDENCE if has_direct else INSUFFICIENT_DIRECT_VARIANT_EVIDENCE,
        "variant_score_status": "SCORED_FROM_DIRECT_PAPER_EVIDENCE" if has_direct else NEEDS_PAPER_CAPTURE,
        "direct_sample_count": direct_sample_count,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "total_pnl_pct": _float_or_none(evidence.get("total_pnl_pct")) if has_direct else None,
        "fill_rate_pct": fill_rate_pct,
        "stop_rate_pct": stop_rate_pct,
        "win_rate_score": score_parts["win_rate_score"],
        "avg_pnl_score": score_parts["avg_pnl_score"],
        "sample_count_score": score_parts["sample_count_score"],
        "fill_rate_score": score_parts["fill_rate_score"],
        "stop_rate_penalty": score_parts["stop_rate_penalty"],
        "evidence_quality_score": score_parts["evidence_quality_score"],
        "live_safety_compatibility_score": score_parts["live_safety_compatibility_score"],
        "freshness_score": score_parts["freshness_score"],
        "betrayal_penalty_or_bonus": score_parts["betrayal_penalty_or_bonus"],
        "strategy_lab_score": score,
        "confidence_class": confidence,
        "source_chain": list(evidence.get("source_chain") or evidence.get("evidence_files_used") or []),
        "recommended_lab_action": recommended,
        "ranking_is_lab_only": True,
        "live_rank": None,
        "live_allowed": False,
        **_top_level_safety_fields(),
    }


def _synthetic_capture_row(
    symbol: object,
    timeframe: object,
    direction: object,
    entry_mode: str,
    axis: str,
    value: str,
) -> dict[str, Any]:
    lane_key = build_lane_key(symbol=symbol, timeframe=timeframe, direction=direction, entry_mode=entry_mode)
    return _variant_row(
        lane_key=lane_key,
        variant_axis=axis,
        variant_value=value,
        timing=value if axis == "timing" else "close_entry",
        tpsl=value if axis == "tp_sl" else "current_baseline",
        trailing=value if axis == "trailing" else "no_trailing",
        filter_name=value if axis == "filter" else "no_extra_filter",
        evidence={},
    )


def _build_betrayal_rows(
    r304: Mapping[str, Any],
    *,
    evidence_by_lane: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for raw in r304.get("betrayal_preview_candidates") or []:
        if not isinstance(raw, Mapping):
            continue
        lane_key = str(raw.get("lane_key") or "")
        sample_count = _int_or_none(raw.get("sample_count") or raw.get("true_paper_outcomes_count")) or 0
        min_required = _int_or_none(raw.get("true_paper_min_samples_required")) or 30
        inverse_avg = _float_or_none(raw.get("avg_pnl_pct"))
        original = evidence_by_lane.get(lane_key) or {}
        original_avg = _float_or_none(original.get("avg_pnl_pct"))
        delta = round(inverse_avg - original_avg, 4) if inverse_avg is not None and original_avg is not None else None
        progress = round(min((sample_count / max(min_required, 1)) * 100.0, 100.0), 2)
        rows.append(
            {
                "lane_key": lane_key,
                "watch_category": BETRAYAL_INVERSE_PREVIEW,
                "true_paper_outcomes_count": sample_count,
                "true_paper_min_samples_required": min_required,
                "true_paper_preferred_samples_required": 50,
                "sample_progress_pct": progress,
                "win_rate_pct": _float_or_none(raw.get("win_rate_pct")),
                "avg_pnl_pct": inverse_avg,
                "stale_shadow_outcome_check": raw.get("stale_shadow_outcome_check") or "NO_STALE_SHADOW_OUTCOME_SEEN",
                "original_vs_inverse_delta": delta,
                "betrayal_gate_decision": raw.get("betrayal_gate_decision") or BETRAYAL_BLOCKED_PREVIEW_ONLY,
                "recommended_next_capture_action": BETRAYAL_CAPTURE_PRIORITY,
                "recommended_lab_action": BETRAYAL_CAPTURE_PRIORITY,
                "betrayal_live_permission": False,
                "live_allowed": False,
                **_top_level_safety_fields(),
            }
        )
    rows.sort(key=lambda row: (_int_or_none(row.get("true_paper_outcomes_count")) or 0, row.get("sample_progress_pct") or 0.0), reverse=True)
    return {
        "preview_only": True,
        "betrayal_live_permission": False,
        "betrayal_gate_policy": BETRAYAL_BLOCKED_FROM_TINY_LIVE,
        "preferred_win_rate_pct": 60.0,
        "minimum_sample_count": 30,
        "preferred_sample_count": 50,
        "capture_priorities": rows[:10],
        "all_betrayal_candidates": rows,
    }


def _score_parts(
    *,
    sample_count: int | None,
    win_rate_pct: float | None,
    avg_pnl_pct: float | None,
    fill_rate_pct: float | None,
    stop_rate_pct: float | None,
    evidence_quality: float,
    freshness_status: str,
    betrayal: bool,
) -> dict[str, float]:
    return {
        "win_rate_score": round(max((win_rate_pct or 0.0) - 50.0, 0.0) * 1.25, 4),
        "avg_pnl_score": round(max(avg_pnl_pct or 0.0, 0.0) * 100.0, 4),
        "sample_count_score": round(min(float(sample_count or 0), 100.0) / 4.0, 4),
        "fill_rate_score": round(min(float(fill_rate_pct or 0.0), 100.0) / 20.0, 4),
        "stop_rate_penalty": round(-(float(stop_rate_pct or 0.0) / 20.0), 4),
        "evidence_quality_score": round(evidence_quality * 20.0, 4),
        "live_safety_compatibility_score": 10.0,
        "freshness_score": 3.0 if freshness_status == "CURRENT_FRESH_CANDIDATE" else 0.0,
        "betrayal_penalty_or_bonus": -20.0 if betrayal else 0.0,
    }


def _confidence_class(
    *,
    has_direct: bool,
    sample_count: int | None,
    win_rate_pct: float | None,
    avg_pnl_pct: float | None,
    score: float,
) -> str:
    if not has_direct:
        return INSUFFICIENT_DIRECT_VARIANT_EVIDENCE
    if avg_pnl_pct is None or avg_pnl_pct <= 0.0 or win_rate_pct is None:
        return BLOCKED
    if (sample_count or 0) >= 50 and win_rate_pct >= 60.0 and score >= 55.0:
        return HIGH_PAPER_CONFIDENCE
    if (sample_count or 0) >= 30 and win_rate_pct >= 55.0:
        return MEDIUM_PAPER_CONFIDENCE
    return LOW_PAPER_CONFIDENCE


def _recommended_action(*, lane_key: str, confidence: str, evidence: Mapping[str, Any], has_direct: bool) -> str:
    if not has_direct:
        return CAPTURE_VARIANT_EVIDENCE
    if lane_key == CURRENT_TINY_LIVE_LANE:
        return KEEP_CURRENT_FIRST_TINY_LIVE_LANE_UNCHANGED
    if confidence in {HIGH_PAPER_CONFIDENCE, MEDIUM_PAPER_CONFIDENCE}:
        return EXPANSION_PREVIEW_ONLY
    if evidence.get("watch_category") == NEAR_MISS_INCUBATOR:
        return PAPER_ONLY_RANKING_REVIEW
    return CAPTURE_VARIANT_EVIDENCE


def _current_lane_status(evidence_by_lane: Mapping[str, Mapping[str, Any]], top_variants: list[Mapping[str, Any]]) -> dict[str, Any]:
    current_rows = [row for row in top_variants if row.get("lane_key") == CURRENT_TINY_LIVE_LANE]
    best = current_rows[0] if current_rows else {}
    evidence = evidence_by_lane.get(CURRENT_TINY_LIVE_LANE, {})
    return {
        "lane_key": CURRENT_TINY_LIVE_LANE,
        "watch_category": evidence.get("watch_category"),
        "sample_count": evidence.get("sample_count"),
        "win_rate_pct": evidence.get("win_rate_pct"),
        "avg_pnl_pct": evidence.get("avg_pnl_pct"),
        "best_variant_key": best.get("variant_key"),
        "best_strategy_lab_score": best.get("strategy_lab_score"),
        "confidence_class": best.get("confidence_class"),
        "recommended_lab_action": KEEP_CURRENT_FIRST_TINY_LIVE_LANE_UNCHANGED,
        "tiny_live_lane_unchanged": True,
        "autonomous_arming_state_changed": False,
        "live_promotion_created": False,
    }


def _recommended_next_phase(top_variants: list[Mapping[str, Any]]) -> str:
    expansion_ready = [
        row
        for row in top_variants
        if row.get("lane_key") != CURRENT_TINY_LIVE_LANE
        and row.get("confidence_class") in {HIGH_PAPER_CONFIDENCE, MEDIUM_PAPER_CONFIDENCE}
        and row.get("family") == "R304_LIVE_QUALIFIED_EXPANSION_PREVIEW"
    ]
    if expansion_ready:
        return "R306 Eligible Lane Expansion Dry-Run Preview; include 44m short and 55m long as dry-run-only candidates; do not enable live."
    return "R306 Variant Evidence Capture Scheduler; collect direct paper evidence for missing timing, TP/SL, trailing, freshness, and filter dimensions."


def _top_variants(rows: list[Mapping[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    direct = sorted(
        [dict(row) for row in rows if row.get("evidence_status") == DIRECT_PAPER_EVIDENCE],
        key=_variant_sort_key,
        reverse=True,
    )
    return direct[:limit]


def _top_near_miss(rows: list[Mapping[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    near = sorted(
        [
            dict(row)
            for row in rows
            if row.get("family") == "R305_NEAR_MISS_INCUBATOR" and row.get("evidence_status") == DIRECT_PAPER_EVIDENCE
        ],
        key=_variant_sort_key,
        reverse=True,
    )
    return near[:limit]


def _variant_sort_key(row: Mapping[str, Any]) -> tuple[int, float, int, float, float]:
    return (
        _confidence_rank(str(row.get("confidence_class") or "")),
        float(row.get("strategy_lab_score") or 0.0),
        int(row.get("direct_sample_count") or 0),
        float(row.get("win_rate_pct") or 0.0),
        float(row.get("avg_pnl_pct") or 0.0),
    )


def _confidence_rank(value: str) -> int:
    return {
        HIGH_PAPER_CONFIDENCE: 4,
        MEDIUM_PAPER_CONFIDENCE: 3,
        LOW_PAPER_CONFIDENCE: 2,
        BLOCKED: 1,
        INSUFFICIENT_DIRECT_VARIANT_EVIDENCE: 0,
    }.get(value, 0)


def _variant_key(lane_key: str, axis: str, value: str, timing: str, tpsl: str, trailing: str, filter_name: str) -> str:
    return "|".join([lane_key, f"axis={axis}", f"value={value}", f"timing={timing}", f"tp_sl={tpsl}", f"trailing={trailing}", f"filter={filter_name}"])


def _best_known_entry(
    symbol: object,
    timeframe: object,
    direction: object,
    evidence_by_lane: Mapping[str, Mapping[str, Any]],
) -> str | None:
    rows = [
        evidence
        for lane_key, evidence in evidence_by_lane.items()
        if lane_key.startswith(f"{symbol}|{timeframe}|{direction}|") and _has_direct_evidence(evidence)
    ]
    rows.sort(key=lambda row: (_float_or_none(row.get("avg_pnl_pct")) or -999.0, _int_or_none(row.get("sample_count")) or 0), reverse=True)
    return str(rows[0].get("entry_mode")) if rows else None


def _family_label(lane_key: str) -> str:
    if lane_key == CURRENT_TINY_LIVE_LANE:
        return "CURRENT_FIRST_TINY_LIVE_LANE"
    if lane_key in TOP_R304_LANES:
        return "R304_LIVE_QUALIFIED_EXPANSION_PREVIEW"
    if lane_key in NEAR_MISS_LANES:
        return "R305_NEAR_MISS_INCUBATOR"
    if lane_key in BROADER_PAPER_LANES:
        return "R305_BROADER_PAPER_ONLY"
    return "R304_EXISTING_EVIDENCE"


def _default_watch_category(lane_key: str) -> str:
    if lane_key in TOP_R304_LANES:
        return LIVE_QUALIFIED
    if lane_key in NEAR_MISS_LANES:
        return NEAR_MISS_INCUBATOR
    return PAPER_ONLY


def _has_direct_evidence(evidence: Mapping[str, Any]) -> bool:
    return (_int_or_none(evidence.get("sample_count")) or 0) > 0 and _float_or_none(evidence.get("win_rate_pct")) is not None


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = [*str(lane_key or "").split("|"), "", "", "", ""]
    return parts[0], parts[1], parts[2], parts[3] or "ladder_close_50_618"


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _top_level_safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "submit_allowed": False,
        "final_command_available": False,
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
        "secrets_shown": False,
        "real_order_forbidden": True,
    }


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key, value in SAFETY.items():
            if key in sanitized:
                sanitized[key] = value
        for key, value in _top_level_safety_fields().items():
            if key in sanitized:
                sanitized[key] = value
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload


def _main() -> int:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.strategy_lab_variant_test_pack")
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args()
    payload = build_strategy_lab_variant_test_pack(log_dir=args.log_dir, write=not args.no_write)
    if args.text:
        print(format_strategy_lab_variant_test_pack_text(payload))
    else:
        print(format_strategy_lab_variant_test_pack_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
