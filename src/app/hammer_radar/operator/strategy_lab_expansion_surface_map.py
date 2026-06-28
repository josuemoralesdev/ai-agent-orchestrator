"""R323 read-only Strategy Lab expansion surface map."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.eligible_lane_expansion_dry_run_preview import (
    PRIMARY_DRY_RUN_EXPANSION_LANES,
    SECONDARY_WATCH_ONLY_LANES,
    build_eligible_lane_expansion_dry_run_preview,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.strategy_lab_preview import CURRENT_TINY_LIVE_LANE

EVENT_TYPE = "R323_STRATEGY_LAB_EXPANSION_REENTRY_AND_CANDIDATE_SURFACE_MAP"
CREATED_BY_PHASE = "R323_STRATEGY_LAB_EXPANSION_REENTRY_AND_CANDIDATE_SURFACE_MAP"
LEDGER_FILENAME = "strategy_lab_expansion_surface_map.ndjson"

SURFACE_MAP_READY = "STRATEGY_LAB_SURFACE_MAP_READY"
SURFACE_MAP_BLOCKED = "STRATEGY_LAB_SURFACE_MAP_BLOCKED"
TELEGRAM_SCOPE_COMPLETE_R322 = "TELEGRAM_SCOPE_COMPLETE_R322"

BASELINE_LANE = CURRENT_TINY_LIVE_LANE
PRIMARY_LANES = tuple(PRIMARY_DRY_RUN_EXPANSION_LANES)
SECONDARY_WATCH_LANES = tuple(SECONDARY_WATCH_ONLY_LANES)
NEAR_MISS_LANES = (
    "BTCUSDT|13m|long|ladder_close_50_618",
    "BTCUSDT|13m|short|ladder_close_50_618",
    "BTCUSDT|8m|short|ladder_close_50_618",
)

DEFAULT_RISK_CONTRACT_PATH = Path("configs/hammer_radar/tiny_live_risk_contracts.json")

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


def build_strategy_lab_expansion_surface_map(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    max_observation_age_seconds: int = 300,
    include_betrayal_lab: bool = True,
    include_secondary_watch: bool = True,
    risk_contract_path: str | Path | None = None,
    expansion_preview_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    expansion = (
        dict(expansion_preview_packet)
        if isinstance(expansion_preview_packet, Mapping)
        else build_eligible_lane_expansion_dry_run_preview(log_dir=resolved_log_dir, write=False, now=generated_at)
    )
    lane_packets = [dict(row) for row in expansion.get("lane_packets") or [] if isinstance(row, Mapping)]
    blockers = _surface_blockers(expansion)
    risk_summary = build_risk_contract_summary(
        risk_contract_path=risk_contract_path or DEFAULT_RISK_CONTRACT_PATH,
        baseline_lane=BASELINE_LANE,
        primary_lanes=PRIMARY_LANES,
        secondary_lanes=SECONDARY_WATCH_LANES if include_secondary_watch else (),
    )
    promotion_summary = _promotion_candidate_summary(lane_packets)
    near_miss_summary = _near_miss_summary(resolved_log_dir)
    lab_only_summary = _lab_only_summary(include_betrayal_lab=include_betrayal_lab)
    betrayal_summary = _betrayal_inverse_summary(include_betrayal_lab=include_betrayal_lab)
    missing_contracts = risk_summary["missing_contracts_for_observed_lanes"]

    payload: dict[str, Any] = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "surface_map_id": f"r323_strategy_lab_expansion_surface_map_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_lab_expansion_surface_map_path": str(surface_map_path(resolved_log_dir)),
        "surface_map_status": SURFACE_MAP_BLOCKED if blockers else SURFACE_MAP_READY,
        "blockers": blockers,
        "telegram_scope_status": TELEGRAM_SCOPE_COMPLETE_R322,
        "current_tiny_live_status": _current_tiny_live_status(expansion),
        "armed_tiny_live_lane": _armed_lane(expansion),
        "baseline_lane": BASELINE_LANE,
        "observed_primary_lanes": _lane_summaries(lane_packets, PRIMARY_LANES),
        "observed_secondary_watch_lanes": _lane_summaries(lane_packets, SECONDARY_WATCH_LANES if include_secondary_watch else ()),
        "risk_contract_summary": risk_summary,
        "promotion_candidate_summary": promotion_summary,
        "near_miss_summary": near_miss_summary,
        "paper_only_summary": _paper_only_summary(),
        "watch_only_summary": _watch_only_summary(include_secondary_watch=include_secondary_watch),
        "blocked_candidate_summary": _blocked_candidate_summary(lane_packets, missing_contracts),
        "lab_only_summary": lab_only_summary,
        "betrayal_inverse_summary": betrayal_summary,
        "missing_risk_contract_candidates": missing_contracts,
        "candidate_surface_counts": _candidate_surface_counts(
            primary_lanes=PRIMARY_LANES,
            secondary_lanes=SECONDARY_WATCH_LANES if include_secondary_watch else (),
            near_miss_lanes=NEAR_MISS_LANES,
            lab_only_summary=lab_only_summary,
            missing_contracts=missing_contracts,
        ),
        "recommended_strategy_dimensions": _recommended_strategy_dimensions(),
        "recommended_r324_batch_plan": _recommended_r324_batch_plan(),
        "recommended_r325_promotion_review": _recommended_r325_promotion_review(),
        "recommended_tiny_live_path": _recommended_tiny_live_path(),
        "no_live_mutation_summary": _no_live_mutation_summary(),
        "max_observation_age_seconds": max_observation_age_seconds,
        "source_surfaces_used": _source_surfaces(resolved_log_dir),
        "safety": dict(SAFETY),
        **dict(SAFETY),
    }
    safe_payload = _sanitize(payload)
    if write:
        append_surface_map(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def build_risk_contract_summary(
    *,
    risk_contract_path: str | Path,
    baseline_lane: str,
    primary_lanes: Sequence[str],
    secondary_lanes: Sequence[str],
) -> dict[str, Any]:
    path = Path(risk_contract_path)
    contracts = _read_contracts(path)
    by_lane = {_contract_lane_key(contract): contract for contract in contracts if _contract_lane_key(contract)}
    relevant = [baseline_lane, *primary_lanes, *secondary_lanes]
    relevant_values = {lane: _contract_values(by_lane.get(lane)) for lane in relevant}
    primary_present = {lane: lane in by_lane for lane in primary_lanes}
    secondary_present = {lane: lane in by_lane for lane in secondary_lanes}
    missing = [lane for lane in relevant if lane not in by_lane]
    return {
        "risk_contract_source_path": str(path),
        "source_exists": path.exists(),
        "source_read_only": True,
        "config_written": False,
        "risk_contract_config_mutated": False,
        "total_contracts": len(contracts),
        "baseline_contract_present": baseline_lane in by_lane,
        "observed_primary_contracts_present": primary_present,
        "observed_secondary_contracts_present": secondary_present,
        "missing_contracts_for_observed_lanes": missing,
        "max_loss_usdt_by_lane": {lane: values.get("max_loss_usdt") for lane, values in relevant_values.items()},
        "leverage_by_lane": {lane: values.get("leverage") for lane, values in relevant_values.items()},
        "notional_caps_by_lane": {lane: values.get("max_position_notional_usdt") for lane, values in relevant_values.items()},
        "margin_budget_usdt_by_lane": {lane: values.get("margin_budget_usdt") for lane, values in relevant_values.items()},
        "relevant_contract_values": relevant_values,
    }


def append_surface_map(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = surface_map_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_strategy_lab_expansion_surface_map_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(surface_map_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def surface_map_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_surface_map_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_surface_map_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R323 STRATEGY LAB EXPANSION RE-ENTRY AND CANDIDATE SURFACE MAP",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        f"surface_map_status: {payload.get('surface_map_status')}",
        "",
        "TELEGRAM SCOPE",
        f"telegram_scope_status: {payload.get('telegram_scope_status')}",
        "",
        "TINY LIVE STATUS",
    ]
    status = payload.get("current_tiny_live_status") if isinstance(payload.get("current_tiny_live_status"), Mapping) else {}
    lines.extend(
        [
            f"status: {status.get('status')}",
            f"armed_tiny_live_lane: {payload.get('armed_tiny_live_lane')}",
            f"baseline_lane: {payload.get('baseline_lane')}",
            "",
            "OBSERVED PRIMARY LANES",
        ]
    )
    lines.extend(_format_lane_rows(payload.get("observed_primary_lanes")))
    lines.extend(["", "OBSERVED SECONDARY WATCH LANES"])
    lines.extend(_format_lane_rows(payload.get("observed_secondary_watch_lanes")))
    lines.extend(["", "RISK CONTRACT SUMMARY"])
    risk = payload.get("risk_contract_summary") if isinstance(payload.get("risk_contract_summary"), Mapping) else {}
    lines.extend(
        [
            f"total_contracts: {risk.get('total_contracts')}",
            f"baseline_contract_present: {risk.get('baseline_contract_present')}",
            f"missing_contracts_for_observed_lanes: {','.join(risk.get('missing_contracts_for_observed_lanes') or []) or 'none'}",
            "",
            "PROMOTION CANDIDATE SUMMARY",
        ]
    )
    promo = payload.get("promotion_candidate_summary") if isinstance(payload.get("promotion_candidate_summary"), Mapping) else {}
    lines.append(f"promotion_ready_candidates: {','.join(promo.get('promotion_ready_candidates') or []) or 'none'}")
    lines.append(f"paper_only_candidates: {','.join(promo.get('paper_only_candidates') or []) or 'none'}")
    lines.extend(["", "NEAR-MISS SUMMARY"])
    near = payload.get("near_miss_summary") if isinstance(payload.get("near_miss_summary"), Mapping) else {}
    lines.append(f"near_miss_candidates: {','.join(near.get('near_miss_candidates') or []) or 'none'}")
    lines.extend(["", "BETRAYAL / INVERSE LAB-ONLY SUMMARY"])
    betrayal = payload.get("betrayal_inverse_summary") if isinstance(payload.get("betrayal_inverse_summary"), Mapping) else {}
    lines.extend(
        [
            f"betrayal_live_permission: {betrayal.get('betrayal_live_permission')}",
            f"standard_55_policy_applies: {betrayal.get('standard_55_policy_applies')}",
            f"minimum_sample_count: {betrayal.get('minimum_sample_count')}",
            f"preferred_sample_count: {betrayal.get('preferred_sample_count')}",
            "",
            "RECOMMENDED R324 BATCH PLAN",
        ]
    )
    for row in payload.get("recommended_r324_batch_plan") or []:
        if isinstance(row, Mapping):
            lines.append(f"{row.get('batch')}. {row.get('name')} | {row.get('objective')}")
    lines.extend(["", "RECOMMENDED TINY LIVE PATH"])
    for item in payload.get("recommended_tiny_live_path") or []:
        lines.append(str(item))
    lines.extend(["", "SAFETY FLAGS"])
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    for key in SAFETY:
        lines.append(f"{key}: {safety.get(key)}")
    return "\n".join(lines)


def _format_lane_rows(value: object) -> list[str]:
    rows = value if isinstance(value, list) else []
    lines: list[str] = []
    for row in rows:
        if isinstance(row, Mapping):
            lines.append(
                f"{row.get('lane_key')} | status={row.get('surface_status')} "
                f"samples={row.get('sample_count')} win={row.get('win_rate_pct')} avg={row.get('avg_pnl_pct')}"
            )
    return lines or ["none"]


def _current_tiny_live_status(expansion: Mapping[str, Any]) -> dict[str, Any]:
    final_gate = expansion.get("final_gate_summary") if isinstance(expansion.get("final_gate_summary"), Mapping) else {}
    return {
        "status": final_gate.get("status") or "FINAL_TINY_LIVE_AUTHORIZATION_WAITING_FOR_REAL_CANDIDATE",
        "blockers": list(final_gate.get("blockers") or []),
        "real_order_forbidden": True,
        "submit_allowed": False,
        "final_command_available": False,
        "current_real_candidate_lane_key": final_gate.get("current_real_candidate_lane_key"),
        "tiny_live_waiting_for_real_candidate": final_gate.get("current_real_candidate_lane_key") in (None, ""),
    }


def _armed_lane(expansion: Mapping[str, Any]) -> str:
    final_gate = expansion.get("final_gate_summary") if isinstance(expansion.get("final_gate_summary"), Mapping) else {}
    return str(final_gate.get("armed_lane_key") or final_gate.get("requested_lane_key") or BASELINE_LANE)


def _lane_summaries(lane_packets: Sequence[Mapping[str, Any]], lanes: Sequence[str]) -> list[dict[str, Any]]:
    by_lane = {str(row.get("lane_key")): row for row in lane_packets if row.get("lane_key")}
    summaries: list[dict[str, Any]] = []
    for lane in lanes:
        row = by_lane.get(lane, {})
        risk = row.get("exact_risk_contract_preview") if isinstance(row.get("exact_risk_contract_preview"), Mapping) else {}
        summaries.append(
            {
                "lane_key": lane,
                "surface_status": row.get("expansion_preview_status") or "SOURCE_MISSING",
                "lane_role": row.get("lane_role"),
                "sample_count": row.get("sample_count"),
                "win_rate_pct": row.get("win_rate_pct"),
                "avg_pnl_pct": row.get("avg_pnl_pct"),
                "risk_contract_present": risk.get("exact_contract_found"),
                "risk_contract_valid": risk.get("risk_contract_valid"),
                "evidence_status": row.get("direct_evidence_status") or "SOURCE_MISSING",
                "submit_allowed": False,
                "final_command_available": False,
                "real_order_forbidden": True,
            }
        )
    return summaries


def _promotion_candidate_summary(lane_packets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_lane = {str(row.get("lane_key")): row for row in lane_packets if row.get("lane_key")}
    promotion_ready = [
        lane
        for lane in (BASELINE_LANE, *PRIMARY_LANES)
        if lane in by_lane and by_lane[lane].get("direct_evidence_status") == "DIRECT_PAPER_EVIDENCE"
    ]
    return {
        "promotion_ready_candidates": promotion_ready,
        "near_miss_candidates": list(NEAR_MISS_LANES),
        "paper_only_candidates": [
            "BTCUSDT|13m|long|ladder_close_50_618",
            "BTCUSDT|13m|short|ladder_close_50_618",
            "BTCUSDT|8m|short|ladder_close_50_618",
        ],
        "watch_only_candidates": list(SECONDARY_WATCH_LANES),
        "blocked_candidates": [],
        "lab_only_candidates": ["BETRAYAL_INVERSE_LANES"],
        "source": "R306 lane_packets plus R305/R304 known categories",
        "promotion_review_required": True,
        "live_permission_granted": False,
    }


def _near_miss_summary(log_dir: Path) -> dict[str, Any]:
    source_paths = [
        log_dir / "strategy_lab_preview.ndjson",
        log_dir / "strategy_lab_variant_test_pack.ndjson",
        log_dir / "strategy_promotion_status.ndjson",
    ]
    return {
        "near_miss_candidates": list(NEAR_MISS_LANES),
        "focus": [
            "13m long/short near-miss repair variants",
            "8m short capture-improvement target",
        ],
        "source_missing": not any(path.exists() for path in source_paths),
        "missing_source_recommendation": "R324 data adapter repair" if not any(path.exists() for path in source_paths) else None,
        "needs_more_samples": True,
    }


def _paper_only_summary() -> dict[str, Any]:
    return {
        "paper_only_candidates": list(NEAR_MISS_LANES),
        "paper_only_policy": "collect direct evidence before promotion review",
    }


def _watch_only_summary(*, include_secondary_watch: bool) -> dict[str, Any]:
    return {
        "watch_only_candidates": list(SECONDARY_WATCH_LANES) if include_secondary_watch else [],
        "watch_only_policy": "watch-only lanes do not become live without evidence, risk contract, human review, and final gate",
    }


def _blocked_candidate_summary(lane_packets: Sequence[Mapping[str, Any]], missing_contracts: Sequence[str]) -> dict[str, Any]:
    blocked = [
        str(row.get("lane_key"))
        for row in lane_packets
        if isinstance(row.get("expansion_blockers"), list)
        and "final_submit_forbidden_in_r306" in row.get("expansion_blockers", [])
    ]
    return {
        "blocked_candidates": list(dict.fromkeys([*blocked, *missing_contracts])),
        "common_blockers": [
            "live_execution_disabled_by_policy",
            "global_kill_switch_required",
            "final_submit_forbidden",
            "human_review_required_before_live",
        ],
    }


def _lab_only_summary(*, include_betrayal_lab: bool) -> dict[str, Any]:
    candidates = ["BETRAYAL_INVERSE_LANES"] if include_betrayal_lab else []
    return {
        "lab_only_candidates": candidates,
        "betrayal_inverse_lab_only": include_betrayal_lab,
        "standard_tiny_live_policy_applies": False,
    }


def _betrayal_inverse_summary(*, include_betrayal_lab: bool) -> dict[str, Any]:
    return {
        "included": include_betrayal_lab,
        "classification": "LAB_ONLY",
        "must_not_promote_to_tiny_live": True,
        "standard_55_policy_applies": False,
        "betrayal_live_permission": False,
        "preferred_win_rate_pct": 60,
        "minimum_sample_count": 30,
        "preferred_sample_count": 50,
        "avg_pnl_requirement": "positive",
        "required_checks": [
            "original-vs-inverse comparison",
            "complete signal origin/source chain",
            "exact lane/entry/risk mapping",
            "no stale shadow outcomes",
            "beats normal candidates cleanly",
        ],
        "gate_reminder": (
            "Betrayal/inverse remains lab-only unless a stricter future Betrayal Lab Gate is explicitly implemented."
        ),
    }


def _candidate_surface_counts(
    *,
    primary_lanes: Sequence[str],
    secondary_lanes: Sequence[str],
    near_miss_lanes: Sequence[str],
    lab_only_summary: Mapping[str, Any],
    missing_contracts: Sequence[str],
) -> dict[str, int]:
    return {
        "baseline_count": 1,
        "observed_primary_count": len(primary_lanes),
        "observed_secondary_watch_count": len(secondary_lanes),
        "near_miss_count": len(near_miss_lanes),
        "lab_only_count": len(lab_only_summary.get("lab_only_candidates") or []),
        "missing_risk_contract_count": len(missing_contracts),
    }


def _recommended_strategy_dimensions() -> dict[str, Any]:
    return {
        "timeframe_expansion": ["8m", "13m", "44m", "55m", "88m"],
        "long_short_symmetry": True,
        "entry_modes": ["ladder_close_50_618", "ladder_382_50_618", "ladder_22_44_22", "market_close"],
        "exits": ["fixed TP/SL", "early exit", "late exit", "trailing"],
        "filters": [
            "RSI",
            "divergence",
            "regime",
            "WMA200 or MA200 anchor",
            "HTF bias",
            "golden pocket resistance/support context",
        ],
        "betrayal_inverse": "lab only",
        "sample_thresholds": {"standard_minimum": 30, "standard_preferred": 50, "betrayal_minimum": 30, "betrayal_preferred": 50},
        "avg_pnl_requirement": "positive",
    }


def _recommended_r324_batch_plan() -> list[dict[str, str]]:
    return [
        {"batch": "1", "name": "44m short variants", "objective": "expand entry and exit variants for observed 44m short candidates"},
        {"batch": "2", "name": "55m long variants", "objective": "deepen evidence for 55m long ladder and market-close candidates"},
        {"batch": "3", "name": "13m near-miss repair variants", "objective": "repair sample/evidence gaps for 13m long and short"},
        {"batch": "4", "name": "8m short capture-improvement variants", "objective": "improve capture around the existing 8m short target"},
        {"batch": "5", "name": "88m watch-only evidence variants", "objective": "test whether 88m watch-only evidence is durable"},
        {"batch": "6", "name": "Betrayal/inverse lab-only variants", "objective": "collect stricter lab evidence without tiny-live promotion"},
        {"batch": "7", "name": "MA/WMA200 anchor variants", "objective": "measure anchor filters for trend and support/resistance context"},
        {"batch": "8", "name": "exit/TP/SL/trailing variants", "objective": "compare fixed, early, late, and trailing exits"},
    ]


def _recommended_r325_promotion_review() -> dict[str, Any]:
    return {
        "phase": "R325 Promotion Review",
        "requires": ["R324 batch evidence", "risk contract present", "human review", "final gate clearance"],
        "first_live_lane_change_allowed": False,
    }


def _recommended_tiny_live_path() -> list[str]:
    return [
        "First Tiny Live remains baseline 44m long unless explicitly changed later.",
        "More lanes increase signal surface but do not automatically become live.",
        "Tiny Live is waiting for real candidate detection and final gate clearance.",
        "Expanded lanes can become future tiny-live candidates only after evidence + risk contract + human review + final gate.",
    ]


def _no_live_mutation_summary() -> dict[str, Any]:
    return {
        "no_orders": True,
        "no_binance_order_or_test_order_endpoints": True,
        "no_leverage_or_margin_change": True,
        "no_live_flag_mutation": True,
        "no_kill_switch_mutation": True,
        "no_arming_mutation": True,
        "no_config_or_env_mutation": True,
        "no_systemd_mutation": True,
        "no_telegram_send": True,
    }


def _surface_blockers(expansion: Mapping[str, Any]) -> list[str]:
    lane_packets = expansion.get("lane_packets")
    if not isinstance(lane_packets, list) or not lane_packets:
        return ["r306_expansion_preview_source_missing"]
    return []


def _source_surfaces(log_dir: Path) -> list[str]:
    return [
        "src/app/hammer_radar/operator/strategy_lab_preview.py",
        "src/app/hammer_radar/operator/strategy_lab_variant_test_pack.py",
        "src/app/hammer_radar/operator/eligible_lane_expansion_dry_run_preview.py",
        "src/app/hammer_radar/operator/multi_lane_observation_health_panel.py",
        "configs/hammer_radar/tiny_live_risk_contracts.json",
        "configs/hammer_radar/autonomous_arming_state.json",
        str(log_dir / "multi_lane_dry_run_observation.ndjson"),
        str(log_dir / "strategy_lab_preview.ndjson"),
        str(log_dir / "strategy_lab_variant_test_pack.ndjson"),
        str(log_dir / "eligible_lane_expansion_dry_run_preview.ndjson"),
    ]


def _read_contracts(path: Path) -> list[Mapping[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    contracts = data.get("risk_contracts") if isinstance(data, Mapping) else None
    return [contract for contract in contracts or [] if isinstance(contract, Mapping)]


def _contract_lane_key(contract: Mapping[str, Any]) -> str:
    explicit = contract.get("official_lane_key") or contract.get("lane_key")
    if explicit:
        return str(explicit)
    candidate = str(contract.get("candidate_id") or "")
    if "|" in candidate:
        parts = candidate.split("|")
        if len(parts) >= 5:
            return "|".join(parts[-4:])
    symbol = contract.get("symbol")
    timeframe = contract.get("timeframe")
    direction = contract.get("direction")
    entry_mode = contract.get("entry_mode")
    if symbol and timeframe and direction and entry_mode:
        return f"{symbol}|{timeframe}|{direction}|{entry_mode}"
    return ""


def _contract_values(contract: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(contract, Mapping):
        return {
            "present": False,
            "max_loss_usdt": None,
            "leverage": None,
            "max_position_notional_usdt": None,
            "margin_budget_usdt": None,
        }
    return {
        "present": True,
        "max_loss_usdt": contract.get("max_loss_usdt"),
        "leverage": contract.get("leverage"),
        "max_position_notional_usdt": contract.get("max_position_notional_usdt") or contract.get("max_notional_usdt"),
        "margin_budget_usdt": contract.get("margin_budget_usdt") or contract.get("tiny_live_margin_usdt"),
    }


def _sanitize(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.strategy_lab_expansion_surface_map")
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--max-observation-age-seconds", type=int, default=300)
    parser.add_argument("--include-betrayal-lab", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-secondary-watch", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)

    payload = build_strategy_lab_expansion_surface_map(
        log_dir=args.log_dir,
        write=not args.no_write,
        max_observation_age_seconds=args.max_observation_age_seconds,
        include_betrayal_lab=args.include_betrayal_lab,
        include_secondary_watch=args.include_secondary_watch,
    )
    if args.text:
        print(format_surface_map_text(payload))
    else:
        print(format_surface_map_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
