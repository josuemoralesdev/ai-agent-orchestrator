"""R310 multi-lane dry-run observation scheduler preview.

This surface observes the current baseline lane plus R306/R307 primary and
secondary expansion lanes without arming, submitting, signing, changing config,
or calling Binance order/test-order/mutation endpoints.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.expansion_risk_contract_preview_repair import (
    PRIMARY_DRY_RUN_EXPANSION_CANDIDATE,
    PRIMARY_DRY_RUN_EXPANSION_LANES,
    SECONDARY_WATCH_ONLY_CANDIDATE,
    SECONDARY_WATCH_ONLY_LANES,
    build_expansion_risk_contract_lane_preview,
    build_lane_key,
    lane_parts,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.strategy_lab_preview import CURRENT_TINY_LIVE_LANE
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler_timer_health import (
    TIMER_HEALTH_ACTIVE,
    build_autonomous_trigger_scheduler_timer_health,
)
from src.app.hammer_radar.operator.tiny_live_fresh_trigger_watch import (
    build_latest_or_not_checked_fresh_trigger_watch,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_validation import (
    DEFAULT_RISK_CONTRACT_CONFIG_PATH,
)

EVENT_TYPE = "R310_MULTI_LANE_DRY_RUN_OBSERVATION"
CREATED_BY_PHASE = "R310_MULTI_LANE_DRY_RUN_OBSERVATION_SCHEDULER"
LEDGER_FILENAME = "multi_lane_dry_run_observation.ndjson"

BASELINE_CURRENT_FIRST_TINY_LIVE = "BASELINE_CURRENT_FIRST_TINY_LIVE"
PRIMARY_DRY_RUN_OBSERVATION = "PRIMARY_DRY_RUN_OBSERVATION"
SECONDARY_WATCH_ONLY_VISIBLE = "SECONDARY_WATCH_ONLY_VISIBLE"

OBSERVING_DRY_RUN = "OBSERVING_DRY_RUN"
WATCH_ONLY_VISIBLE = "WATCH_ONLY_VISIBLE"
BLOCKED_RISK_CONTRACT = "BLOCKED_RISK_CONTRACT"
BLOCKED_TIMER_HEALTH = "BLOCKED_TIMER_HEALTH"
BLOCKED_POLICY = "BLOCKED_POLICY"

RECORD_ONLY_NO_SUBMIT = "RECORD_ONLY_NO_SUBMIT"
WATCH_ONLY_NO_SUBMIT = "WATCH_ONLY_NO_SUBMIT"
BLOCKED_NO_ACTION = "BLOCKED_NO_ACTION"

KEEP_OBSERVING_MULTI_LANE_DRY_RUN = "KEEP_OBSERVING_MULTI_LANE_DRY_RUN"
REPAIR_OBSERVATION_BLOCKERS = "REPAIR_OBSERVATION_BLOCKERS"
R311_TIMER_UNIT_PREVIEW = "R311 Multi-Lane Dry-Run Timer Unit Preview"
R311_BLOCKER_REPAIR = "R311 Observation Blocker Repair"

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
    "global_live_flags_changed": False,
    "risk_contract_config_mutated": False,
    "config_written": False,
    "env_written": False,
    "env_mutated": False,
    "systemd_unit_mutated": False,
    "scheduler_started": False,
}


def build_multi_lane_dry_run_observation(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    write: bool = False,
    now: datetime | None = None,
    timer_health_packet: Mapping[str, Any] | None = None,
    fresh_trigger_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    risk_path = (
        Path(risk_contract_config_path)
        if risk_contract_config_path is not None
        else DEFAULT_RISK_CONTRACT_CONFIG_PATH
    )
    timer = (
        dict(timer_health_packet)
        if isinstance(timer_health_packet, Mapping)
        else build_autonomous_trigger_scheduler_timer_health(log_dir=resolved_log_dir)
    )
    fresh = (
        dict(fresh_trigger_packet)
        if isinstance(fresh_trigger_packet, Mapping)
        else build_latest_or_not_checked_fresh_trigger_watch(log_dir=resolved_log_dir)
    )
    contracts_by_lane = _contracts_by_lane(risk_path)
    lane_packets = [
        _lane_packet(
            lane_key=CURRENT_TINY_LIVE_LANE,
            lane_role=BASELINE_CURRENT_FIRST_TINY_LIVE,
            risk_contract_config_path=risk_path,
            contracts_by_lane=contracts_by_lane,
            timer=timer,
            fresh=fresh,
        )
    ]
    lane_packets.extend(
        _lane_packet(
            lane_key=lane_key,
            lane_role=PRIMARY_DRY_RUN_OBSERVATION,
            risk_contract_config_path=risk_path,
            contracts_by_lane=contracts_by_lane,
            timer=timer,
            fresh=fresh,
        )
        for lane_key in PRIMARY_DRY_RUN_EXPANSION_LANES
    )
    lane_packets.extend(
        _lane_packet(
            lane_key=lane_key,
            lane_role=SECONDARY_WATCH_ONLY_VISIBLE,
            risk_contract_config_path=risk_path,
            contracts_by_lane=contracts_by_lane,
            timer=timer,
            fresh=fresh,
        )
        for lane_key in SECONDARY_WATCH_ONLY_LANES
    )

    primary_packets = [row for row in lane_packets if row["lane_role"] == PRIMARY_DRY_RUN_OBSERVATION]
    secondary_packets = [row for row in lane_packets if row["lane_role"] == SECONDARY_WATCH_ONLY_VISIBLE]
    all_primary_valid = all(row["risk_contract_valid"] is True for row in primary_packets)
    timer_active = timer.get("timer_active") is True
    timer_health_status = str(timer.get("status") or timer.get("timer_health_status") or "")
    timer_health_active = timer_active and timer_health_status == TIMER_HEALTH_ACTIVE
    observation_blockers = _dedupe(
        blocker
        for row in lane_packets
        for blocker in row.get("observation_blockers", [])
        if row["lane_role"] != SECONDARY_WATCH_ONLY_VISIBLE
    )
    recommended_move = (
        KEEP_OBSERVING_MULTI_LANE_DRY_RUN
        if all_primary_valid and timer_health_active and not observation_blockers
        else REPAIR_OBSERVATION_BLOCKERS
    )
    gate_matrix = {
        "baseline_lane_preserved": True,
        "baseline_lane_key": CURRENT_TINY_LIVE_LANE,
        "observed_primary_lane_count": len(primary_packets),
        "secondary_watch_only_count": len(secondary_packets),
        "primary_observed_lanes": [row["lane_key"] for row in primary_packets],
        "secondary_watch_only_lanes": [row["lane_key"] for row in secondary_packets],
        "all_primary_risk_contracts_valid": all_primary_valid,
        "timer_health_active": timer_health_active,
        "timer_active": timer_active,
        "timer_health_status": timer_health_status or "TIMER_HEALTH_UNKNOWN",
        "live_execution_remains_disabled": True,
        "arming_state_unchanged": True,
        "scheduler_started": False,
        "recommended_next_operator_move": recommended_move,
        "recommended_r311_path": (
            R311_TIMER_UNIT_PREVIEW if recommended_move == KEEP_OBSERVING_MULTI_LANE_DRY_RUN else R311_BLOCKER_REPAIR
        ),
    }
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "observation_id": f"r310_multi_lane_dry_run_observation_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        "preview_only": not bool(write),
        "current_first_tiny_live_lane": CURRENT_TINY_LIVE_LANE,
        "current_first_tiny_live_lane_unchanged": True,
        "baseline_lane": CURRENT_TINY_LIVE_LANE,
        "primary_observed_lanes": list(PRIMARY_DRY_RUN_EXPANSION_LANES),
        "secondary_watch_only_lanes": list(SECONDARY_WATCH_ONLY_LANES),
        "betrayal_policy": {
            "betrayal_inverse_included_as_observed_lane": False,
            "betrayal_inverse_remains_lab_only_blocked": True,
        },
        "lane_packets": lane_packets,
        "multi_lane_observation_gate_matrix": gate_matrix,
        "timer_health_summary": {
            "timer_active": timer_active,
            "timer_health_status": timer_health_status or "TIMER_HEALTH_UNKNOWN",
            "timer_health_required": TIMER_HEALTH_ACTIVE,
            "blockers": list(timer.get("blockers") or []),
        },
        "candidate_visibility_summary": _candidate_visibility_summary(fresh=fresh, lane_packets=lane_packets),
        "source_surfaces_used": [
            "src/app/hammer_radar/operator/eligible_lane_expansion_dry_run_preview.py",
            "src/app/hammer_radar/operator/expansion_risk_contract_preview_repair.py",
            "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py",
            "src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py",
            "src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py",
            "configs/hammer_radar/tiny_live_risk_contracts.json",
            "configs/hammer_radar/autonomous_arming_state.json",
        ],
        "safety": dict(SAFETY),
        **dict(SAFETY),
    }
    safe_payload = _sanitize(payload)
    if write:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def load_multi_lane_dry_run_observation_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def append_record(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = records_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_observation_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def format_observation_text(payload: Mapping[str, Any]) -> str:
    matrix = payload.get("multi_lane_observation_gate_matrix")
    matrix = matrix if isinstance(matrix, Mapping) else {}
    timer = payload.get("timer_health_summary")
    timer = timer if isinstance(timer, Mapping) else {}
    candidate = payload.get("candidate_visibility_summary")
    candidate = candidate if isinstance(candidate, Mapping) else {}
    lines = [
        "R310 MULTI-LANE DRY-RUN OBSERVATION",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        "",
        "BASELINE LANE",
        str(payload.get("baseline_lane")),
        "",
        "PRIMARY OBSERVED LANES",
        *[str(item) for item in payload.get("primary_observed_lanes") or []],
        "",
        "SECONDARY WATCH-ONLY LANES",
        *[str(item) for item in payload.get("secondary_watch_only_lanes") or []],
        "",
        "RISK-CONTRACT READINESS",
    ]
    for row in payload.get("lane_packets") or []:
        if isinstance(row, Mapping):
            lines.append(
                f"{row.get('lane_key')} | role={row.get('lane_role')} "
                f"exact_contract_found={row.get('exact_contract_found')} "
                f"risk_contract_valid={row.get('risk_contract_valid')} "
                f"blocked_by={','.join(row.get('risk_contract_blocked_by') or []) or 'none'}"
            )
    lines.extend(
        [
            "",
            "TIMER HEALTH",
            f"timer_active: {timer.get('timer_active')}",
            f"timer_health_status: {timer.get('timer_health_status')}",
            "",
            "CANDIDATE VISIBILITY SUMMARY",
            f"current_candidate_seen: {candidate.get('current_candidate_seen')}",
            f"current_candidate_lane_key: {candidate.get('current_candidate_lane_key')}",
            f"candidate_freshness_status: {candidate.get('candidate_freshness_status')}",
            "",
            "SAFETY FLAGS",
        ]
    )
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(
        [
            "",
            "GATE MATRIX",
            f"baseline_lane_preserved: {matrix.get('baseline_lane_preserved')}",
            f"observed_primary_lane_count: {matrix.get('observed_primary_lane_count')}",
            f"secondary_watch_only_count: {matrix.get('secondary_watch_only_count')}",
            f"all_primary_risk_contracts_valid: {matrix.get('all_primary_risk_contracts_valid')}",
            f"timer_health_active: {matrix.get('timer_health_active')}",
            f"recommended_next_operator_move: {matrix.get('recommended_next_operator_move')}",
            f"recommended_r311_path: {matrix.get('recommended_r311_path')}",
        ]
    )
    return "\n".join(lines)


def _lane_packet(
    *,
    lane_key: str,
    lane_role: str,
    risk_contract_config_path: Path,
    contracts_by_lane: Mapping[str, Mapping[str, Any]],
    timer: Mapping[str, Any],
    fresh: Mapping[str, Any],
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = lane_parts(lane_key)
    risk_role = _risk_preview_role(lane_role)
    risk = build_expansion_risk_contract_lane_preview(
        lane_key=lane_key,
        lane_role=risk_role,
        risk_contract_config_path=risk_contract_config_path,
    )
    contract = contracts_by_lane.get(lane_key, {})
    timer_active = timer.get("timer_active") is True
    timer_status = str(timer.get("status") or timer.get("timer_health_status") or "TIMER_HEALTH_UNKNOWN")
    current_lane = str(fresh.get("current_candidate_lane_key") or "")
    current_seen = fresh.get("current_fresh_candidate_exists") is True or bool(current_lane)
    risk_blockers = list(risk.get("blocked_by") or [])
    blockers = _observation_blockers(
        lane_role=lane_role,
        risk_valid=risk.get("risk_contract_valid") is True,
        risk_blockers=risk_blockers,
        timer_active=timer_active,
        timer_status=timer_status,
    )
    status = _observation_status(
        lane_role=lane_role,
        risk_valid=risk.get("risk_contract_valid") is True,
        timer_active=timer_active,
        timer_status=timer_status,
        blockers=blockers,
    )
    action = _observation_action(lane_role=lane_role, status=status)
    return _sanitize(
        {
            "lane_key": lane_key,
            "lane_role": lane_role,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": entry_mode,
            "exact_contract_found": risk.get("exact_contract_found") is True,
            "risk_contract_valid": risk.get("risk_contract_valid") is True,
            "risk_contract_blocked_by": risk_blockers,
            "live_execution_enabled_from_contract": contract.get("live_execution_enabled") is True,
            "allow_live_orders_from_contract": contract.get("allow_live_orders") is True,
            "current_candidate_seen": current_seen,
            "current_candidate_matches_lane": bool(current_lane and current_lane == lane_key),
            "candidate_freshness_status": fresh.get("status") or "FRESH_TRIGGER_NOT_CHECKED",
            "timer_health_status": timer_status,
            "timer_active": timer_active,
            "observation_status": status,
            "observation_blockers": blockers,
            "observation_action": action,
            "dry_run_order_payload_created": False,
            "executable_payload_created": False,
            "signed_request_created": False,
            "submit_allowed": False,
            "final_command_available": False,
            "exact_risk_contract_preview": risk,
            **dict(SAFETY),
        }
    )


def _risk_preview_role(lane_role: str) -> str:
    if lane_role == PRIMARY_DRY_RUN_OBSERVATION:
        return PRIMARY_DRY_RUN_EXPANSION_CANDIDATE
    if lane_role == SECONDARY_WATCH_ONLY_VISIBLE:
        return SECONDARY_WATCH_ONLY_CANDIDATE
    return "CURRENT_FIRST_TINY_LIVE_BASELINE"


def _observation_status(
    *,
    lane_role: str,
    risk_valid: bool,
    timer_active: bool,
    timer_status: str,
    blockers: Sequence[str],
) -> str:
    if lane_role == SECONDARY_WATCH_ONLY_VISIBLE:
        return WATCH_ONLY_VISIBLE
    if not risk_valid:
        return BLOCKED_RISK_CONTRACT
    if not timer_active or timer_status != TIMER_HEALTH_ACTIVE:
        return BLOCKED_TIMER_HEALTH
    if blockers:
        return BLOCKED_POLICY
    return OBSERVING_DRY_RUN


def _observation_blockers(
    *,
    lane_role: str,
    risk_valid: bool,
    risk_blockers: Sequence[str],
    timer_active: bool,
    timer_status: str,
) -> list[str]:
    blockers: list[str] = []
    if lane_role == SECONDARY_WATCH_ONLY_VISIBLE:
        blockers.append("secondary_watch_only_not_primary_observation")
    if not risk_valid:
        blockers.extend(risk_blockers or ["risk_contract_invalid_or_missing"])
    if not timer_active:
        blockers.append("timer_not_active")
    if timer_status != TIMER_HEALTH_ACTIVE:
        blockers.append("timer_health_not_active")
    return _dedupe(blockers)


def _observation_action(*, lane_role: str, status: str) -> str:
    if lane_role == SECONDARY_WATCH_ONLY_VISIBLE:
        return WATCH_ONLY_NO_SUBMIT
    if status == OBSERVING_DRY_RUN:
        return RECORD_ONLY_NO_SUBMIT
    return BLOCKED_NO_ACTION


def _candidate_visibility_summary(
    *, fresh: Mapping[str, Any], lane_packets: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    current_lane = str(fresh.get("current_candidate_lane_key") or "")
    return {
        "current_candidate_seen": fresh.get("current_fresh_candidate_exists") is True or bool(current_lane),
        "current_candidate_lane_key": current_lane or None,
        "candidate_freshness_status": fresh.get("status") or "FRESH_TRIGGER_NOT_CHECKED",
        "matching_observed_lane_keys": [
            str(row.get("lane_key"))
            for row in lane_packets
            if current_lane and row.get("lane_key") == current_lane
        ],
    }


def _contracts_by_lane(path: Path) -> dict[str, Mapping[str, Any]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("risk_contracts") if isinstance(raw, Mapping) else []
    lookup: dict[str, Mapping[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        keys = [
            str(row.get("official_lane_key") or ""),
            str(row.get("lane_key") or ""),
            build_lane_key(
                symbol=row.get("symbol"),
                timeframe=row.get("timeframe"),
                direction=row.get("direction"),
                entry_mode=row.get("entry_mode"),
            ),
        ]
        for key in keys:
            if key.strip("|") and key not in lookup:
                lookup[key] = row
    return lookup


def _dedupe(items: Sequence[str] | Any) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


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
        prog="python -m src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--risk-contract-config-path", default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="Build preview packet without writing ledger.")
    mode.add_argument("--once", action="store_true", help="Write one observation tick to the observation ledger.")
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args()
    payload = build_multi_lane_dry_run_observation(
        log_dir=args.log_dir,
        risk_contract_config_path=args.risk_contract_config_path,
        write=bool(args.once),
    )
    print(format_observation_text(payload) if args.text else format_observation_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
