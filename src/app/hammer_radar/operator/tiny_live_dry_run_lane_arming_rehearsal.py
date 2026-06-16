"""R294 dry-run lane arming rehearsal under the installed timer.

This module is an operator-visible rehearsal layer only. It composes the
existing autonomous arming, fresh trigger, one-shot pre-activation, autonomous
trigger loop, scheduler, and timer-health semantics without submitting orders,
creating executable payloads, mutating env/live/risk config, or calling Binance
order/test-order/leverage/margin endpoints.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_autonomous_armed_dry_run import (
    CONFIG_PATH as AUTONOMOUS_ARMING_CONFIG_PATH,
    load_autonomous_arming_state,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_loop import (
    AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED,
    build_tiny_live_autonomous_trigger_loop,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler_timer_health import (
    TIMER_HEALTH_ACTIVE,
    build_autonomous_trigger_scheduler_timer_health,
)
from src.app.hammer_radar.operator.tiny_live_one_shot_pre_activation_gate import (
    APPROVED_LIVE_QUALIFIED_LANES,
    ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    LIVE_QUALIFIED,
    NEAR_MISS_INCUBATOR,
    PAPER_ONLY,
    build_explicit_lane_risk_contract,
)

EVENT_TYPE = "TINY_LIVE_DRY_RUN_LANE_ARMING_REHEARSAL"
CREATED_BY_PHASE = "R294_DRY_RUN_LANE_ARMING_UNDER_TIMER_REHEARSAL"
LEDGER_FILENAME = "tiny_live_dry_run_lane_arming_rehearsal.ndjson"

DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT = "DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT"
DRY_RUN_LANE_ARMING_REHEARSAL_BLOCKED = "DRY_RUN_LANE_ARMING_REHEARSAL_BLOCKED"
DRY_RUN_LANE_ARMING_REHEARSAL_SIMULATED_TRIGGER_RECORDED = (
    "DRY_RUN_LANE_ARMING_REHEARSAL_SIMULATED_TRIGGER_RECORDED"
)

ALLOWED_LANE_KEYS = tuple(sorted(APPROVED_LIVE_QUALIFIED_LANES))
NEAR_MISS_LANE_KEYS = {
    "BTCUSDT|13m|long|ladder_close_50_618",
}

OPERATOR_ROLE = "arms_disarms_tunes_risk_not_per_signal_approval"
MACHINE_ROLE = "auto_triggers_when_armed_and_all_gates_open"

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "risk_contract_mutated": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "final_command_available": False,
    "submit_allowed": False,
    "submit_attempted": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "mutation_performed": False,
    "signed_trading_request_created": False,
    "signed_order_request_created": False,
    "signed_request_created": False,
    "signed_url_shown": False,
    "signature_shown": False,
    "secrets_shown": False,
    "secret_values_in_output": False,
    "kill_switch_disabled": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "real_order_forbidden": True,
    "per_signal_operator_approval_required": False,
}


def build_tiny_live_dry_run_lane_arming_rehearsal(
    *,
    lane_key: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    log_dir: str | Path | None = None,
    record_dry_run_lane_arming_rehearsal: bool = False,
    simulate_fresh_candidate_for_tests_only: bool = False,
    simulate_candidate_lane_key: str | None = None,
    timer_health_packet: Mapping[str, Any] | None = None,
    current_candidate_packet: Mapping[str, Any] | None = None,
    autonomous_arming_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    requested_lane = str(lane_key or "").strip()
    requested_operator_id = str(operator_id or "").strip()
    requested_reason = str(reason or "").strip()
    timer_health = (
        dict(timer_health_packet)
        if isinstance(timer_health_packet, Mapping)
        else build_autonomous_trigger_scheduler_timer_health(log_dir=resolved_log_dir)
    )
    candidate_packet = (
        dict(current_candidate_packet)
        if isinstance(current_candidate_packet, Mapping)
        else _current_candidate_from_latest_surfaces(log_dir=resolved_log_dir)
    )
    if simulate_fresh_candidate_for_tests_only:
        candidate_packet = _simulated_candidate_packet(
            lane_key=str(simulate_candidate_lane_key or requested_lane),
            generated_at=generated_at,
        )

    lane_validation = validate_r294_dry_run_lane(requested_lane)
    current_lane = str(candidate_packet.get("lane_key") or "")
    current_exists = bool(candidate_packet.get("exists"))
    current_matches = bool(current_exists and requested_lane and current_lane == requested_lane)
    timer_status = str(timer_health.get("status") or "")
    timer_active = timer_health.get("timer_active") is True
    recent_tick_seen = timer_health.get("recent_tick_seen") is True

    blockers = list(lane_validation["blockers"])
    if not requested_operator_id:
        blockers.append("operator_id_required")
    if not requested_reason:
        blockers.append("reason_required")
    if timer_status != TIMER_HEALTH_ACTIVE:
        blockers.append("timer_health_not_active")
    if not timer_active:
        blockers.append("timer_not_active")
    if not recent_tick_seen:
        blockers.append("recent_scheduler_tick_not_seen")
    if current_exists and not current_matches:
        blockers.append("current_candidate_does_not_match_armed_lane")

    trigger_loop = _empty_trigger_loop()
    simulated_trigger_recorded = False
    if not blockers and current_exists and current_matches:
        trigger_loop = _build_simulated_trigger_loop(
            requested_lane=requested_lane,
            candidate_packet=candidate_packet,
            generated_at=generated_at,
            autonomous_arming_config_path=autonomous_arming_config_path,
        )
        simulated_trigger_recorded = trigger_loop.get("status") == AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED
        if not simulated_trigger_recorded:
            blockers.extend(str(item) for item in trigger_loop.get("blockers") or ["simulated_trigger_not_recorded"])

    status = _status(blockers=blockers, current_exists=current_exists, simulated_trigger_recorded=simulated_trigger_recorded)
    lifecycle = _lifecycle(trigger_loop)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "generated_at": generated_at.isoformat(),
            "operator_role": OPERATOR_ROLE,
            "machine_role": MACHINE_ROLE,
            "status": status,
            "requested_lane_key": requested_lane or None,
            "requested_operator_id": requested_operator_id or None,
            "requested_reason": requested_reason,
            "allowed_lane_keys": list(ALLOWED_LANE_KEYS),
            "lane_is_live_qualified": lane_validation["lane_is_live_qualified"],
            "lane_is_near_miss": lane_validation["lane_is_near_miss"],
            "lane_is_paper_only": lane_validation["lane_is_paper_only"],
            "exact_lane_risk_contract": lane_validation["exact_lane_risk_contract"],
            "exact_lane_only": True,
            "no_cross_lane_borrowing": True,
            "dry_run_only": True,
            "live_execution_enabled": False,
            "allow_live_orders": False,
            "global_kill_switch": True,
            "timer_health_status": timer_status,
            "timer_active": timer_active,
            "recent_tick_seen": recent_tick_seen,
            "timer_health_packet": timer_health,
            "current_fresh_candidate_exists": current_exists,
            "current_candidate_lane_key": current_lane or None,
            "current_candidate_matches_armed_lane": current_matches,
            "current_candidate_packet": candidate_packet,
            "simulate_fresh_candidate_for_tests_only": bool(simulate_fresh_candidate_for_tests_only),
            "simulated_trigger_recorded": simulated_trigger_recorded,
            "simulated_open_record": lifecycle["simulated_open_record"],
            "simulated_protective_orders": lifecycle["simulated_protective_orders"],
            "simulated_close_plan": lifecycle["simulated_close_plan"],
            "telegram_compatible_payload": _telegram_payload(
                status=status,
                requested_lane=requested_lane,
                current_lane=current_lane,
                blockers=_dedupe(blockers),
                simulated_trigger_recorded=simulated_trigger_recorded,
            ),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "executable_payload_created": False,
            "order_payload_created": False,
            "order_placed": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "per_signal_operator_approval_required": False,
            "blockers": _dedupe(blockers),
            "recommended_next_operator_move": _recommended_next_operator_move(status, blockers=_dedupe(blockers)),
            "dry_run_lane_arming_rehearsal_panel": _panel(
                status=status,
                requested_lane=requested_lane,
                timer_health=timer_health,
                candidate_packet=candidate_packet,
                current_matches=current_matches,
                simulated_trigger_recorded=simulated_trigger_recorded,
                lifecycle=lifecycle,
                blockers=_dedupe(blockers),
            ),
            "record_dry_run_lane_arming_rehearsal_requested": bool(record_dry_run_lane_arming_rehearsal),
            "dry_run_lane_arming_rehearsal_recorded": False,
            "safety": dict(SAFETY),
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_autonomous_armed_dry_run.py",
                "src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py",
                "src/app/hammer_radar/operator/tiny_live_one_shot_pre_activation_gate.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_loop.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py",
                "configs/hammer_radar/autonomous_arming_state.json",
                "configs/hammer_radar/tiny_live_risk_contracts.json",
                f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
            ],
        }
    )
    if record_dry_run_lane_arming_rehearsal:
        payload = append_tiny_live_dry_run_lane_arming_rehearsal(payload, log_dir=resolved_log_dir)
    return payload


def validate_r294_dry_run_lane(lane_key: str) -> dict[str, Any]:
    lane = str(lane_key or "").strip()
    lane_is_live_qualified = lane in ALLOWED_LANE_KEYS
    lane_is_near_miss = lane in NEAR_MISS_LANE_KEYS
    lane_is_paper_only = bool(lane and not lane_is_live_qualified and not lane_is_near_miss and lane.startswith("BTCUSDT|"))
    blockers: list[str] = []
    if not lane:
        blockers.append("lane_key_required")
    parts = lane.split("|") if lane else []
    if lane and len(parts) != 4:
        blockers.append("lane_key_must_be_exact_symbol_timeframe_direction_entry_mode")
    if parts and parts[0] != "BTCUSDT":
        blockers.append("only_BTCUSDT_lanes_supported_for_r294")
    if lane_is_near_miss:
        blockers.append("near_miss_lane_rejected")
    if lane_is_paper_only:
        blockers.append("paper_only_lane_rejected")
    if lane and not lane_is_live_qualified:
        blockers.append("lane_not_live_qualified_by_strategy_evidence")

    risk_contract = _exact_lane_risk_contract(lane) if lane_is_live_qualified else None
    if lane_is_live_qualified and not risk_contract:
        blockers.append("exact_lane_risk_contract_missing")

    return _sanitize(
        {
            "lane_key": lane or None,
            "lane_is_live_qualified": lane_is_live_qualified,
            "lane_is_near_miss": lane_is_near_miss,
            "lane_is_paper_only": lane_is_paper_only,
            "exact_lane_risk_contract": risk_contract,
            "blockers": _dedupe(blockers),
            "dry_run_only": True,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )


def load_latest_tiny_live_dry_run_lane_arming_rehearsal(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    records = load_tiny_live_dry_run_lane_arming_rehearsal_records(log_dir=log_dir, limit=1)
    return records[0] if records else {}


def load_tiny_live_dry_run_lane_arming_rehearsal_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)]


def build_latest_or_status_tiny_live_dry_run_lane_arming_rehearsal(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    latest = load_latest_tiny_live_dry_run_lane_arming_rehearsal(log_dir=log_dir)
    if latest:
        latest["final_command_available"] = False
        latest["submit_allowed"] = False
        latest["real_order_forbidden"] = True
        latest["safety"] = dict(SAFETY)
        return _sanitize(latest)
    return build_tiny_live_dry_run_lane_arming_rehearsal(log_dir=log_dir)


def append_tiny_live_dry_run_lane_arming_rehearsal(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    payload = _sanitize(
        {
            **dict(record),
            "dry_run_lane_arming_rehearsal_record_id": record.get("dry_run_lane_arming_rehearsal_record_id")
            or f"r294_dry_run_lane_arming_rehearsal_{uuid4().hex}",
            "dry_run_lane_arming_rehearsal_recorded": True,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safety": dict(SAFETY),
        }
    )
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def format_tiny_live_dry_run_lane_arming_rehearsal_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _status(*, blockers: list[str], current_exists: bool, simulated_trigger_recorded: bool) -> str:
    if blockers:
        return DRY_RUN_LANE_ARMING_REHEARSAL_BLOCKED
    if current_exists and simulated_trigger_recorded:
        return DRY_RUN_LANE_ARMING_REHEARSAL_SIMULATED_TRIGGER_RECORDED
    return DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT


def _current_candidate_from_latest_surfaces(*, log_dir: str | Path) -> dict[str, Any]:
    from src.app.hammer_radar.operator.tiny_live_fresh_trigger_watch import (
        build_latest_or_not_checked_fresh_trigger_watch,
    )

    packet = build_latest_or_not_checked_fresh_trigger_watch(log_dir=log_dir)
    return _sanitize(
        {
            "exists": packet.get("current_fresh_candidate_exists") is True,
            "lane_key": packet.get("current_candidate_lane_key"),
            "signal_id": packet.get("current_candidate_signal_id"),
            "timeframe": packet.get("current_candidate_timeframe"),
            "direction": packet.get("current_candidate_direction"),
            "entry_mode": packet.get("current_candidate_entry_mode"),
            "entry": packet.get("current_candidate_entry"),
            "stop": packet.get("current_candidate_stop"),
            "take_profit": packet.get("current_candidate_take_profit"),
            "live_qualification_class": LIVE_QUALIFIED
            if packet.get("current_candidate_is_live_qualified") is True
            else None,
            "source_status": packet.get("status"),
            "packet_event_type": packet.get("event_type"),
        }
    )


def _simulated_candidate_packet(*, lane_key: str, generated_at: datetime) -> dict[str, Any]:
    parts = lane_key.split("|")
    direction = parts[2] if len(parts) == 4 else "long"
    return _sanitize(
        {
            "exists": True,
            "lane_key": lane_key,
            "signal_id": f"r294_simulated_{uuid4().hex}",
            "symbol": "BTCUSDT",
            "timeframe": parts[1] if len(parts) == 4 else None,
            "direction": direction,
            "entry_mode": parts[3] if len(parts) == 4 else "ladder_close_50_618",
            "age_minutes": 1.0,
            "freshness_status": "fresh_tests_only",
            "entry": 70000.0,
            "stop": 69300.0 if direction == "long" else 70700.0,
            "take_profit": 71400.0 if direction == "long" else 68600.0,
            "live_qualification_class": LIVE_QUALIFIED if lane_key in ALLOWED_LANE_KEYS else PAPER_ONLY,
            "simulated_for_tests_only": True,
            "generated_at": generated_at.isoformat(),
        }
    )


def _build_simulated_trigger_loop(
    *,
    requested_lane: str,
    candidate_packet: Mapping[str, Any],
    generated_at: datetime,
    autonomous_arming_config_path: str | Path | None,
) -> dict[str, Any]:
    candidate = {
        "signal_id": candidate_packet.get("signal_id") or f"r294_candidate_{uuid4().hex}",
        "symbol": "BTCUSDT",
        "timeframe": candidate_packet.get("timeframe"),
        "direction": candidate_packet.get("direction"),
        "entry_mode": candidate_packet.get("entry_mode") or "ladder_close_50_618",
        "lane_key": requested_lane,
        "age_minutes": candidate_packet.get("age_minutes") or 1.0,
        "entry": candidate_packet.get("entry") or 70000.0,
        "stop": candidate_packet.get("stop") or 69300.0,
        "take_profit": candidate_packet.get("take_profit") or 71400.0,
    }
    pre_activation = {
        "status": ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER,
        "candidate_watch": {
            "candidate_alert_packet": {
                "status": "LIVE_QUALIFIED_FRESH_CANDIDATE_FOUND",
                "current_candidate": candidate,
                "strategy_evidence": {
                    "live_qualification_class": LIVE_QUALIFIED,
                    "watch_category": LIVE_QUALIFIED,
                },
                "blocked_by": [],
            }
        },
        "current_candidate_lane_key": requested_lane,
        "current_candidate_signal_id": candidate["signal_id"],
        "approved_lane_match": True,
        "exact_lane_risk_contract_found": True,
        "exact_lane_risk_contract_valid": True,
        "exact_lane_risk_contract": {"contract": _exact_lane_risk_contract(requested_lane)},
        "binance_readiness_ready": True,
        "wallet_ready": True,
        "leverage_margin_ready": True,
        "no_conflicting_position": True,
        "exchange_minimum_ready": True,
        "idempotency_clean": True,
        "protective_triplet_preview_available": True,
        "protective_triplet_preview_valid": True,
        "global_auto_live_enabled": True,
        "exact_lane_auto_armed": True,
        "autonomous_dry_run_arming_status": {
            "status": "R294_SIMULATED_DRY_RUN_ARMED",
            "arming_state": _r294_armed_state(requested_lane, autonomous_arming_config_path),
        },
        "safety": dict(SAFETY),
    }
    return build_tiny_live_autonomous_trigger_loop(
        pre_activation_packet=pre_activation,
        candidate_watch=pre_activation["candidate_watch"],
        record_autonomous_trigger_loop=False,
        operator_id="r294_rehearsal",
        reason="R294 in-memory dry-run lane arming rehearsal only",
        now=generated_at,
    )


def _r294_armed_state(lane_key: str, autonomous_arming_config_path: str | Path | None) -> dict[str, Any]:
    state = load_autonomous_arming_state(autonomous_arming_config_path or AUTONOMOUS_ARMING_CONFIG_PATH)
    state.update(
        {
            "global_auto_live_enabled": True,
            "auto_execute_mode": "dry_run_only",
            "armed_lane_key": lane_key,
            "allowed_lane_keys": [lane_key],
            "lane_auto_live_enabled_keys": [lane_key],
            "max_position_notional_usdt": 80.0,
            "leverage": 10.0,
            "dry_run_only": True,
            "live_execution_enabled": False,
            "allow_live_orders": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )
    return _sanitize(state)


def _exact_lane_risk_contract(lane_key: str) -> dict[str, Any] | None:
    if lane_key not in ALLOWED_LANE_KEYS:
        return None
    return build_explicit_lane_risk_contract(
        lane_key=lane_key,
        strategy_qualification={
            "lane_key": lane_key,
            "qualification_status": "QUALIFIED",
            "strategy_qualified": True,
            "live_qualification_class": LIVE_QUALIFIED,
            "win_rate_pct": 60.0,
            "sample_count": 40,
            "avg_pnl_pct": 0.12,
            "min_sample": 30,
            "min_win_rate_pct": 55.0,
        },
        now=datetime.now(UTC),
    )


def _lifecycle(trigger_loop: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "simulated_open_record": trigger_loop.get("simulated_open_record"),
        "simulated_protective_orders": trigger_loop.get("simulated_protective_orders"),
        "simulated_close_plan": trigger_loop.get("simulated_close_plan"),
    }


def _empty_trigger_loop() -> dict[str, Any]:
    return {
        "status": None,
        "blockers": [],
        "simulated_open_record": None,
        "simulated_protective_orders": None,
        "simulated_close_plan": None,
    }


def _telegram_payload(
    *,
    status: str,
    requested_lane: str,
    current_lane: str,
    blockers: list[str],
    simulated_trigger_recorded: bool,
) -> dict[str, Any]:
    return {
        "channel": "telegram_compatible",
        "send_enabled": False,
        "sent": False,
        "status": "prepared_not_sent",
        "visibility_only": True,
        "message": "\n".join(
            [
                "R294 dry-run lane arming rehearsal",
                f"status: {status}",
                f"requested lane: {requested_lane or 'n/a'}",
                f"current candidate lane: {current_lane or 'n/a'}",
                f"simulated trigger recorded: {str(simulated_trigger_recorded).lower()}",
                f"blockers: {'; '.join(blockers) if blockers else 'none'}",
                "No submit. No order. No executable payload.",
            ]
        ),
        "secrets_shown": False,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _panel(
    *,
    status: str,
    requested_lane: str,
    timer_health: Mapping[str, Any],
    candidate_packet: Mapping[str, Any],
    current_matches: bool,
    simulated_trigger_recorded: bool,
    lifecycle: Mapping[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "allowed_lane_keys": list(ALLOWED_LANE_KEYS),
        "requested_armed_lane": requested_lane or None,
        "timer_health_summary": {
            "timer_health_status": timer_health.get("status"),
            "timer_active": timer_health.get("timer_active") is True,
            "recent_tick_seen": timer_health.get("recent_tick_seen") is True,
            "documentation_warning_seen": timer_health.get("documentation_warning_seen") is True,
            "installed_unit_refresh_required": timer_health.get("installed_unit_refresh_required") is True,
        },
        "fresh_candidate_match_summary": {
            "current_fresh_candidate_exists": candidate_packet.get("exists") is True,
            "current_candidate_lane_key": candidate_packet.get("lane_key"),
            "current_candidate_matches_armed_lane": current_matches,
            "exact_lane_only": True,
            "no_cross_lane_borrowing": True,
        },
        "simulated_trigger_summary": {
            "simulated_trigger_recorded": simulated_trigger_recorded,
            "simulated_open_record": lifecycle.get("simulated_open_record"),
            "simulated_protective_orders": lifecycle.get("simulated_protective_orders"),
            "simulated_close_plan": lifecycle.get("simulated_close_plan"),
        },
        "blockers": blockers,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "recommended_next_operator_move": _recommended_next_operator_move(status, blockers=blockers),
    }


def _recommended_next_operator_move(status: str, *, blockers: list[str]) -> str:
    if status == DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT:
        return "KEEP_DRY_RUN_LANE_ARMED_AND_WAIT_FOR_TIMER_MATCHING_FRESH_CANDIDATE"
    if status == DRY_RUN_LANE_ARMING_REHEARSAL_SIMULATED_TRIGGER_RECORDED:
        return "REVIEW_R294_SIMULATED_LIFECYCLE_AND_KEEP_REAL_SUBMIT_DISABLED"
    return "CLEAR_R294_REHEARSAL_BLOCKERS_OR_DISARM_DRY_RUN_LANE: " + "; ".join(blockers)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
