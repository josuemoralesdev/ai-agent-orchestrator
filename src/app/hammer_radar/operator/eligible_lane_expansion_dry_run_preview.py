"""R306 eligible lane expansion dry-run preview.

This surface previews which lanes could be observed in a future dry-run
expansion. It is read-only: no arming changes, risk contract writes, order
payloads, final commands, Binance order/test-order calls, leverage changes, or
margin changes.
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
from src.app.hammer_radar.operator.strategy_lab_preview import CURRENT_TINY_LIVE_LANE
from src.app.hammer_radar.operator.strategy_lab_variant_test_pack import (
    DIRECT_PAPER_EVIDENCE,
    HIGH_PAPER_CONFIDENCE,
    MEDIUM_PAPER_CONFIDENCE,
    build_strategy_lab_variant_test_pack,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler_timer_health import (
    TIMER_HEALTH_ACTIVE,
    build_autonomous_trigger_scheduler_timer_health,
)
from src.app.hammer_radar.operator.tiny_live_final_authorization_gate import (
    build_status_tiny_live_final_authorization_gate,
)
from src.app.hammer_radar.operator.tiny_live_fresh_trigger_watch import (
    build_latest_or_not_checked_fresh_trigger_watch,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    build_exact_lane_risk_contract_status,
)

EVENT_TYPE = "R306_ELIGIBLE_LANE_EXPANSION_DRY_RUN_PREVIEW"
CREATED_BY_PHASE = "R306_ELIGIBLE_LANE_EXPANSION_DRY_RUN_PREVIEW"
LEDGER_FILENAME = "eligible_lane_expansion_dry_run_preview.ndjson"

CURRENT_FIRST_TINY_LIVE_BASELINE = "CURRENT_FIRST_TINY_LIVE_BASELINE"
PRIMARY_DRY_RUN_EXPANSION_CANDIDATE = "PRIMARY_DRY_RUN_EXPANSION_CANDIDATE"
SECONDARY_WATCH_ONLY_CANDIDATE = "SECONDARY_WATCH_ONLY_CANDIDATE"
REJECTED = "REJECTED"

BASELINE_UNCHANGED = "BASELINE_UNCHANGED"
DRY_RUN_PREVIEW_ELIGIBLE = "DRY_RUN_PREVIEW_ELIGIBLE"
WATCH_ONLY = "WATCH_ONLY"
BLOCKED = "BLOCKED"

KEEP_FIRST_TINY_LIVE_RUNNING_AND_PREVIEW_EXPANSION_DRY_RUN = (
    "KEEP_FIRST_TINY_LIVE_RUNNING_AND_PREVIEW_EXPANSION_DRY_RUN"
)
DO_NOT_EXPAND_YET_NEED_MORE_EVIDENCE = "DO_NOT_EXPAND_YET_NEED_MORE_EVIDENCE"

PRIMARY_DRY_RUN_EXPANSION_LANES = (
    "BTCUSDT|44m|short|ladder_382_50_618",
    "BTCUSDT|44m|short|ladder_close_50_618",
    "BTCUSDT|55m|long|ladder_close_50_618",
)
SECONDARY_WATCH_ONLY_LANES = (
    "BTCUSDT|44m|short|ladder_22_44_22",
    "BTCUSDT|44m|long|ladder_382_50_618",
    "BTCUSDT|55m|long|market_close",
    "BTCUSDT|88m|long|ladder_382_50_618",
)
REJECTED_LANES = (
    "BETRAYAL_INVERSE_LANES",
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
    "real_order_forbidden": True,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
    "autonomous_arming_state_changed": False,
    "risk_contract_config_mutated": False,
    "global_live_flags_changed": False,
}


def build_eligible_lane_expansion_dry_run_preview(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    timer_health_packet: Mapping[str, Any] | None = None,
    final_gate_packet: Mapping[str, Any] | None = None,
    fresh_trigger_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    lab_pack = build_strategy_lab_variant_test_pack(log_dir=resolved_log_dir, write=False, now=generated_at)
    final_gate = dict(final_gate_packet) if isinstance(final_gate_packet, Mapping) else build_status_tiny_live_final_authorization_gate(log_dir=resolved_log_dir)
    timer = dict(timer_health_packet) if isinstance(timer_health_packet, Mapping) else build_autonomous_trigger_scheduler_timer_health(log_dir=resolved_log_dir)
    fresh = dict(fresh_trigger_packet) if isinstance(fresh_trigger_packet, Mapping) else build_latest_or_not_checked_fresh_trigger_watch(log_dir=resolved_log_dir)

    evidence_by_lane = _best_variant_evidence_by_lane(lab_pack)
    lane_packets = [
        _lane_packet(
            lane_key=CURRENT_TINY_LIVE_LANE,
            lane_role=CURRENT_FIRST_TINY_LIVE_BASELINE,
            evidence=evidence_by_lane.get(CURRENT_TINY_LIVE_LANE, {}),
            fresh=fresh,
        )
    ]
    lane_packets.extend(
        _lane_packet(
            lane_key=lane_key,
            lane_role=PRIMARY_DRY_RUN_EXPANSION_CANDIDATE,
            evidence=evidence_by_lane.get(lane_key, {}),
            fresh=fresh,
        )
        for lane_key in PRIMARY_DRY_RUN_EXPANSION_LANES
    )
    lane_packets.extend(
        _lane_packet(
            lane_key=lane_key,
            lane_role=SECONDARY_WATCH_ONLY_CANDIDATE,
            evidence=evidence_by_lane.get(lane_key, {}),
            fresh=fresh,
        )
        for lane_key in SECONDARY_WATCH_ONLY_LANES
    )

    primary_lanes = [row["lane_key"] for row in lane_packets if row["lane_role"] == PRIMARY_DRY_RUN_EXPANSION_CANDIDATE]
    secondary_lanes = [row["lane_key"] for row in lane_packets if row["lane_role"] == SECONDARY_WATCH_ONLY_CANDIDATE]
    eligible_primary = [
        row["lane_key"]
        for row in lane_packets
        if row["lane_role"] == PRIMARY_DRY_RUN_EXPANSION_CANDIDATE
        and row["expansion_preview_status"] == DRY_RUN_PREVIEW_ELIGIBLE
    ]
    recommended_move = (
        KEEP_FIRST_TINY_LIVE_RUNNING_AND_PREVIEW_EXPANSION_DRY_RUN
        if len(eligible_primary) == len(PRIMARY_DRY_RUN_EXPANSION_LANES)
        else DO_NOT_EXPAND_YET_NEED_MORE_EVIDENCE
    )
    matrix = {
        "current_first_lane_preserved": True,
        "current_first_lane_key": CURRENT_TINY_LIVE_LANE,
        "live_execution_remains_disabled": True,
        "kill_switch_remains_enabled": True,
        "global_auto_live_not_enabled": True,
        "autonomous_arming_state_unchanged": True,
        "dry_run_expansion_candidates_count": len(primary_lanes),
        "primary_candidates": primary_lanes,
        "primary_dry_run_preview_eligible": eligible_primary,
        "secondary_watch_only_candidates": secondary_lanes,
        "rejected_candidates": list(REJECTED_LANES),
        "recommended_next_operator_move": recommended_move,
        "submit_allowed": False,
        "final_command_available": False,
    }
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "preview_id": f"r306_eligible_lane_expansion_dry_run_preview_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "eligible_lane_expansion_dry_run_preview_path": str(preview_path(resolved_log_dir)),
        "current_first_tiny_live_lane": CURRENT_TINY_LIVE_LANE,
        "current_first_tiny_live_lane_unchanged": True,
        "dry_run_expansion_lanes": primary_lanes,
        "secondary_watch_only_lanes": secondary_lanes,
        "lane_packets": lane_packets,
        "expansion_gate_matrix": matrix,
        "final_gate_summary": {
            "status": final_gate.get("status"),
            "blockers": list(final_gate.get("blockers") or []),
            "real_order_forbidden": True,
            "submit_allowed": False,
            "final_command_available": False,
            "current_real_candidate_lane_key": final_gate.get("current_real_candidate_lane_key"),
            "armed_lane_key": final_gate.get("armed_lane_key") or final_gate.get("requested_lane_key"),
        },
        "timer_status": {
            "timer_active": timer.get("timer_active") is True,
            "timer_health_status": timer.get("status") or timer.get("timer_health_status"),
            "timer_active_required": True,
            "timer_health_required": TIMER_HEALTH_ACTIVE,
            "blockers": list(timer.get("blockers") or []),
        },
        "paper_refresh_health": _paper_refresh_health(resolved_log_dir),
        "betrayal_policy": {
            "betrayal_inverse_included_as_dry_run_expansion": False,
            "betrayal_remains_lab_only_capture_only": True,
        },
        "recommended_r307_path": _recommended_r307_path(lane_packets),
        "source_surfaces_used": [
            "src/app/hammer_radar/operator/strategy_lab_variant_test_pack.py",
            "src/app/hammer_radar/operator/strategy_lab_preview.py",
            "src/app/hammer_radar/operator/tiny_live_final_authorization_gate.py",
            "src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py",
            "src/app/hammer_radar/operator/tiny_live_strategy_lane_selection.py",
            "src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py",
            "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py",
            "configs/hammer_radar/autonomous_arming_state.json",
            "configs/hammer_radar/tiny_live_risk_contracts.json",
            "logs/hammer_radar_forward/strategy_lab_variant_test_pack.ndjson",
            "logs/hammer_radar_forward/strategy_lab_preview.ndjson",
        ],
        "safety": dict(SAFETY),
        **dict(SAFETY),
    }
    safe_payload = _sanitize(payload)
    if write:
        append_preview(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def append_preview(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = preview_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_eligible_lane_expansion_dry_run_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(preview_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def preview_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_preview_text(payload: Mapping[str, Any]) -> str:
    matrix = payload.get("expansion_gate_matrix") if isinstance(payload.get("expansion_gate_matrix"), Mapping) else {}
    timer = payload.get("timer_status") if isinstance(payload.get("timer_status"), Mapping) else {}
    refresh = payload.get("paper_refresh_health") if isinstance(payload.get("paper_refresh_health"), Mapping) else {}
    lines = [
        "R306 ELIGIBLE LANE EXPANSION DRY-RUN PREVIEW",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        "",
        "CURRENT FIRST TINY LIVE LANE",
        f"lane_key: {payload.get('current_first_tiny_live_lane')}",
        f"baseline_preserved: {matrix.get('current_first_lane_preserved')}",
        "",
        "FINAL LIVE SAFETY STATUS",
    ]
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(
        [
            "",
            "TIMER STATUS",
            f"timer_active: {timer.get('timer_active')}",
            f"timer_health_status: {timer.get('timer_health_status')}",
            f"timer_health_required: {timer.get('timer_health_required')}",
            "",
            "PAPER REFRESH HEALTH",
            f"paper_refresh_health_status: {refresh.get('paper_refresh_health_status')}",
            f"runs_recorded: {refresh.get('runs_recorded')}",
            "",
            "PRIMARY DRY-RUN EXPANSION CANDIDATES",
        ]
    )
    for row in payload.get("lane_packets") or []:
        if isinstance(row, Mapping) and row.get("lane_role") == PRIMARY_DRY_RUN_EXPANSION_CANDIDATE:
            lines.append(_format_lane_line(row))
    lines.append("")
    lines.append("SECONDARY WATCH-ONLY CANDIDATES")
    for row in payload.get("lane_packets") or []:
        if isinstance(row, Mapping) and row.get("lane_role") == SECONDARY_WATCH_ONLY_CANDIDATE:
            lines.append(_format_lane_line(row))
    lines.extend(["", "RISK-CONTRACT PREVIEW STATUS"])
    for row in payload.get("lane_packets") or []:
        if not isinstance(row, Mapping):
            continue
        risk = row.get("exact_risk_contract_preview") if isinstance(row.get("exact_risk_contract_preview"), Mapping) else {}
        lines.append(
            f"{row.get('lane_key')} | exact_contract_found={risk.get('exact_contract_found')} "
            f"risk_contract_valid={risk.get('risk_contract_valid')} blocked_by={','.join(risk.get('blocked_by') or []) or 'none'}"
        )
    lines.extend(
        [
            "",
            "NO LIVE ENABLED / NO ARMING MUTATION",
            f"live_execution_enabled: {payload.get('live_execution_enabled')}",
            f"autonomous_arming_state_changed: {payload.get('autonomous_arming_state_changed')}",
            f"risk_contract_config_mutated: {payload.get('risk_contract_config_mutated')}",
            "",
            "RECOMMENDED R307 PATH",
            str(payload.get("recommended_r307_path")),
        ]
    )
    return "\n".join(lines)


def _lane_packet(
    *,
    lane_key: str,
    lane_role: str,
    evidence: Mapping[str, Any],
    fresh: Mapping[str, Any],
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    risk = build_exact_lane_risk_contract_status(lane_key=lane_key)
    risk_preview = {
        "exact_contract_found": risk.get("exact_contract_found") is True,
        "risk_contract_valid": risk.get("risk_contract_valid") is True,
        "blocked_by": list(risk.get("blocked_by") or []),
    }
    status = _expansion_status(lane_role=lane_role, evidence=evidence)
    blockers = _expansion_blockers(lane_role=lane_role, evidence=evidence, risk_preview=risk_preview)
    current_lane = fresh.get("current_candidate_lane_key")
    packet = {
        "lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "lane_role": lane_role,
        "source": _source(evidence),
        "lab_score": _float_or_none(evidence.get("strategy_lab_score")),
        "confidence_class": evidence.get("confidence_class"),
        "sample_count": _int_or_none(evidence.get("direct_sample_count") or evidence.get("sample_count")),
        "win_rate_pct": _float_or_none(evidence.get("win_rate_pct")),
        "avg_pnl_pct": _float_or_none(evidence.get("avg_pnl_pct")),
        "total_pnl_pct": _float_or_none(evidence.get("total_pnl_pct")),
        "fill_rate_pct": _float_or_none(evidence.get("fill_rate_pct")),
        "stop_rate_pct": _float_or_none(evidence.get("stop_rate_pct")),
        "direct_evidence_status": evidence.get("evidence_status") or "DIRECT_EVIDENCE_NOT_FOUND",
        "strategy_lab_action": evidence.get("recommended_lab_action"),
        "expansion_preview_status": status,
        "expansion_blockers": blockers,
        "required_future_human_decision": _required_future_decision(lane_role, status),
        "exact_risk_contract_preview": risk_preview,
        "timer_requirement": {
            "timer_active_required": True,
            "timer_health_required": TIMER_HEALTH_ACTIVE,
        },
        "current_candidate_status": {
            "current_real_candidate_exists": fresh.get("current_fresh_candidate_exists") is True,
            "current_real_candidate_lane_key": current_lane,
            "current_real_candidate_matches_this_lane": bool(current_lane and current_lane == lane_key),
            "freshness_status": fresh.get("status") or "FRESH_TRIGGER_NOT_CHECKED",
        },
        **dict(SAFETY),
    }
    return _sanitize(packet)


def _best_variant_evidence_by_lane(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = [row for row in payload.get("variant_candidates") or [] if isinstance(row, Mapping)]
    ranked = sorted(rows, key=lambda row: _float_or_none(row.get("strategy_lab_score")) or 0.0, reverse=True)
    evidence: dict[str, Mapping[str, Any]] = {}
    for row in ranked:
        lane_key = str(row.get("lane_key") or "")
        if lane_key and lane_key not in evidence and row.get("evidence_status") == DIRECT_PAPER_EVIDENCE:
            evidence[lane_key] = row
    return evidence


def _expansion_status(*, lane_role: str, evidence: Mapping[str, Any]) -> str:
    if lane_role == CURRENT_FIRST_TINY_LIVE_BASELINE:
        return BASELINE_UNCHANGED
    if lane_role == SECONDARY_WATCH_ONLY_CANDIDATE:
        return WATCH_ONLY
    confidence = str(evidence.get("confidence_class") or "")
    if lane_role == PRIMARY_DRY_RUN_EXPANSION_CANDIDATE and confidence in {
        HIGH_PAPER_CONFIDENCE,
        MEDIUM_PAPER_CONFIDENCE,
    }:
        return DRY_RUN_PREVIEW_ELIGIBLE
    return BLOCKED


def _expansion_blockers(
    *,
    lane_role: str,
    evidence: Mapping[str, Any],
    risk_preview: Mapping[str, Any],
) -> list[str]:
    blockers = [
        "live_execution_disabled_by_policy",
        "global_kill_switch_required",
        "future_human_decision_required_before_any_dry_run_scheduler_expansion",
        "final_submit_forbidden_in_r306",
    ]
    if lane_role == CURRENT_FIRST_TINY_LIVE_BASELINE:
        blockers.append("current_first_tiny_live_lane_must_remain_unchanged")
    if lane_role == SECONDARY_WATCH_ONLY_CANDIDATE:
        blockers.append("secondary_watch_only_not_primary_dry_run_expansion")
    if not evidence:
        blockers.append("direct_r305_variant_evidence_missing")
    elif evidence.get("evidence_status") != DIRECT_PAPER_EVIDENCE:
        blockers.append("direct_r305_variant_evidence_not_confirmed")
    if risk_preview.get("risk_contract_valid") is not True:
        blockers.extend(str(item) for item in risk_preview.get("blocked_by") or [])
    return _dedupe(blockers)


def _required_future_decision(lane_role: str, status: str) -> str:
    if lane_role == CURRENT_FIRST_TINY_LIVE_BASELINE:
        return "KEEP_CURRENT_FIRST_TINY_LIVE_LANE_UNCHANGED"
    if status == DRY_RUN_PREVIEW_ELIGIBLE:
        return "R307_OPERATOR_APPROVES_OBSERVATION_ONLY_SCHEDULER_PREVIEW_NO_LIVE"
    if status == WATCH_ONLY:
        return "KEEP_WATCH_ONLY_UNTIL_PRIMARY_DRY_RUN_OBSERVATION_HAS_EVIDENCE"
    return "DO_NOT_EXPAND_UNTIL_DIRECT_EVIDENCE_AND_GATES_ARE_COMPLETE"


def _source(evidence: Mapping[str, Any]) -> str:
    chain = evidence.get("source_chain")
    if isinstance(chain, list) and "computed_live_eligibility_matrix" in chain:
        return "computed_live_eligibility_matrix"
    if evidence:
        return "R305_STRATEGY_LAB_VARIANT_TEST_PACK"
    return "R304_STRATEGY_LAB_PREVIEW"


def _paper_refresh_health(log_dir: Path) -> dict[str, Any]:
    refresh = scheduler_status(log_dir=log_dir)
    return {
        "paper_refresh_health_status": refresh.get("paper_refresh_health_status"),
        "runs_recorded": refresh.get("runs_recorded"),
        "last_run": refresh.get("last_run"),
    }


def _recommended_r307_path(lane_packets: list[Mapping[str, Any]]) -> str:
    missing_or_invalid_contract = any(
        isinstance(row.get("exact_risk_contract_preview"), Mapping)
        and row["lane_role"] == PRIMARY_DRY_RUN_EXPANSION_CANDIDATE
        and row["exact_risk_contract_preview"].get("risk_contract_valid") is not True
        for row in lane_packets
    )
    if missing_or_invalid_contract:
        return "R307 Expansion Risk Contract Preview Repair"
    return "R307 Multi-Lane Dry-Run Observation Scheduler"


def _format_lane_line(row: Mapping[str, Any]) -> str:
    return (
        f"{row.get('lane_key')} | status={row.get('expansion_preview_status')} "
        f"score={row.get('lab_score')} confidence={row.get('confidence_class')} "
        f"samples={row.get('sample_count')} win={row.get('win_rate_pct')} avg={row.get('avg_pnl_pct')}"
    )


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


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key, value in SAFETY.items():
            if key in sanitized:
                sanitized[key] = value
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload


def _main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.app.hammer_radar.operator.eligible_lane_expansion_dry_run_preview"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args()
    payload = build_eligible_lane_expansion_dry_run_preview(log_dir=args.log_dir, write=not args.no_write)
    if args.text:
        print(format_preview_text(payload))
    else:
        print(format_preview_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
