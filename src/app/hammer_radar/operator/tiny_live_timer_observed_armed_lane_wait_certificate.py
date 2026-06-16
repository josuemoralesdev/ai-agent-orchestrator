"""R295 timer-observed armed-lane wait certificate.

This module is a dry-run audit layer over the existing R294 rehearsal, R292
timer health, R288 scheduler, and fresh trigger watch surfaces. It never
creates submit/order/executable payloads or calls Binance mutation endpoints.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_loop import (
    AUTONOMOUS_TRIGGER_WAIT,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler import (
    AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED,
    LEDGER_FILENAME as SCHEDULER_LEDGER_FILENAME,
    build_latest_or_idle_autonomous_trigger_scheduler,
    load_tiny_live_autonomous_trigger_scheduler_records,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler_timer_health import (
    TIMER_HEALTH_ACTIVE,
    build_autonomous_trigger_scheduler_timer_health,
)
from src.app.hammer_radar.operator.tiny_live_dry_run_lane_arming_rehearsal import (
    ALLOWED_LANE_KEYS,
    DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT,
    build_latest_or_status_tiny_live_dry_run_lane_arming_rehearsal,
    validate_r294_dry_run_lane,
)
from src.app.hammer_radar.operator.tiny_live_fresh_trigger_watch import (
    build_latest_or_not_checked_fresh_trigger_watch,
)

EVENT_TYPE = "TINY_LIVE_TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFICATE"
CREATED_BY_PHASE = "R295_TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFICATE"
LEDGER_FILENAME = "tiny_live_timer_observed_armed_lane_wait_certificate.ndjson"

TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED = (
    "TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED"
)
TIMER_OBSERVED_ARMED_LANE_WAIT_BLOCKED = "TIMER_OBSERVED_ARMED_LANE_WAIT_BLOCKED"

DEFAULT_REQUESTED_LANE_KEY = "BTCUSDT|44m|long|ladder_close_50_618"

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


def build_tiny_live_timer_observed_armed_lane_wait_certificate(
    *,
    lane_key: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    log_dir: str | Path | None = None,
    record_timer_observed_armed_lane_wait_certificate: bool = False,
    simulate_matching_fresh_candidate_for_tests_only: bool = False,
    simulate_candidate_lane_key: str | None = None,
    timer_health_packet: Mapping[str, Any] | None = None,
    scheduler_records: Sequence[Mapping[str, Any]] | None = None,
    dry_run_lane_rehearsal_packet: Mapping[str, Any] | None = None,
    current_candidate_packet: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    rehearsal_packet = (
        dict(dry_run_lane_rehearsal_packet)
        if isinstance(dry_run_lane_rehearsal_packet, Mapping)
        else build_latest_or_status_tiny_live_dry_run_lane_arming_rehearsal(log_dir=resolved_log_dir)
    )
    requested_lane = _requested_lane(lane_key, rehearsal_packet)
    requested_operator_id = str(operator_id or "").strip()
    requested_reason = str(reason or "").strip()

    timer_health = (
        dict(timer_health_packet)
        if isinstance(timer_health_packet, Mapping)
        else build_autonomous_trigger_scheduler_timer_health(log_dir=resolved_log_dir)
    )
    records = (
        [dict(record) for record in scheduler_records]
        if scheduler_records is not None
        else load_tiny_live_autonomous_trigger_scheduler_records(log_dir=resolved_log_dir, limit=20)
    )
    scheduler_latest = records[-1] if records else build_latest_or_idle_autonomous_trigger_scheduler(log_dir=resolved_log_dir)
    candidate_packet = (
        dict(current_candidate_packet)
        if isinstance(current_candidate_packet, Mapping)
        else _current_candidate_from_fresh_watch(log_dir=resolved_log_dir)
    )
    if simulate_matching_fresh_candidate_for_tests_only:
        candidate_packet = _simulated_candidate_packet(
            lane_key=str(simulate_candidate_lane_key or requested_lane),
            generated_at=generated_at,
        )

    lane_validation = validate_r294_dry_run_lane(requested_lane)
    current_lane = str(candidate_packet.get("lane_key") or "")
    current_exists = candidate_packet.get("exists") is True
    current_matches = bool(current_exists and requested_lane and current_lane == requested_lane)
    timer_status = str(timer_health.get("status") or "")
    timer_active = timer_health.get("timer_active") is True
    recent_tick_count = len(records)
    recent_tick_seen = recent_tick_count > 0
    latest_trigger_loop_status = str(scheduler_latest.get("trigger_loop_status") or "")
    latest_scheduler_status = str(scheduler_latest.get("status") or "")
    latest_candidate_lane = scheduler_latest.get("current_candidate_lane_key")
    rehearsal_status = str(rehearsal_packet.get("status") or "")
    rehearsal_record_seen = rehearsal_status not in {"", "DRY_RUN_LANE_ARMING_REHEARSAL_BLOCKED"} and bool(
        rehearsal_packet.get("dry_run_lane_arming_rehearsal_recorded")
        or rehearsal_packet.get("dry_run_lane_arming_rehearsal_record_id")
        or rehearsal_packet.get("requested_lane_key")
    )

    blockers = list(lane_validation.get("blockers") or [])
    if not requested_operator_id:
        blockers.append("operator_id_required")
    if not requested_reason:
        blockers.append("reason_required")
    if timer_status != TIMER_HEALTH_ACTIVE:
        blockers.append("timer_health_not_active")
    if not timer_active:
        blockers.append("timer_not_active")
    if not recent_tick_seen:
        blockers.append("timer_recent_tick_missing")
    if latest_scheduler_status and latest_scheduler_status != AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED:
        blockers.append("scheduler_latest_status_not_iteration_recorded")
    if latest_trigger_loop_status and latest_trigger_loop_status != AUTONOMOUS_TRIGGER_WAIT:
        blockers.append("scheduler_latest_trigger_loop_not_wait")
    if current_exists and not current_matches:
        blockers.append("current_candidate_does_not_match_requested_lane")
    if rehearsal_status and rehearsal_status != DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT:
        blockers.append("dry_run_lane_rehearsal_not_ready_to_wait")

    simulated_trigger_recorded = bool(
        simulate_matching_fresh_candidate_for_tests_only
        and current_exists
        and current_matches
        and not blockers
    )
    status = (
        TIMER_OBSERVED_ARMED_LANE_WAIT_BLOCKED
        if blockers
        else TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED
    )
    blockers = _dedupe(blockers)
    panel = _panel(
        status=status,
        requested_lane=requested_lane,
        timer_health=timer_health,
        recent_tick_count=recent_tick_count,
        scheduler_latest=scheduler_latest,
        candidate_packet=candidate_packet,
        current_matches=current_matches,
        blockers=blockers,
    )
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "generated_at": generated_at.isoformat(),
            "status": status,
            "requested_lane_key": requested_lane or None,
            "requested_operator_id": requested_operator_id or None,
            "requested_reason": requested_reason,
            "allowed_lane_keys": list(ALLOWED_LANE_KEYS),
            "lane_is_live_qualified": lane_validation.get("lane_is_live_qualified") is True,
            "exact_lane_only": True,
            "no_cross_lane_borrowing": True,
            "dry_run_only": True,
            "live_execution_enabled": False,
            "allow_live_orders": False,
            "global_kill_switch": True,
            "timer_health_status": timer_status,
            "timer_active": timer_active,
            "recent_tick_seen": recent_tick_seen,
            "recent_tick_count": recent_tick_count,
            "scheduler_recent_ticks_observed": _scheduler_tick_summary(records),
            "scheduler_latest_status": latest_scheduler_status or None,
            "scheduler_latest_trigger_loop_status": latest_trigger_loop_status or None,
            "scheduler_latest_candidate_lane_key": latest_candidate_lane,
            "dry_run_lane_rehearsal_status": rehearsal_status or None,
            "dry_run_lane_rehearsal_record_seen": rehearsal_record_seen,
            "current_fresh_candidate_exists": current_exists,
            "current_candidate_lane_key": current_lane or None,
            "current_candidate_matches_requested_lane": current_matches,
            "exact_lane_match_required": True,
            "no_matching_candidate_action": "WAIT",
            "simulate_matching_fresh_candidate_for_tests_only": bool(
                simulate_matching_fresh_candidate_for_tests_only
            ),
            "simulated_trigger_recorded": simulated_trigger_recorded,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "executable_payload_created": False,
            "order_payload_created": False,
            "order_placed": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "per_signal_operator_approval_required": False,
            "blockers": blockers,
            "recommended_next_operator_move": panel["recommended_next_operator_move"],
            "safety": dict(SAFETY),
            "timer_observed_armed_lane_wait_certificate_panel": panel,
            "record_timer_observed_armed_lane_wait_certificate_requested": bool(
                record_timer_observed_armed_lane_wait_certificate
            ),
            "timer_observed_armed_lane_wait_certificate_recorded": False,
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_dry_run_lane_arming_rehearsal.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_armed_dry_run.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_loop.py",
                "src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py",
                "configs/hammer_radar/autonomous_arming_state.json",
                "configs/hammer_radar/tiny_live_risk_contracts.json",
                f"logs/hammer_radar_forward/{SCHEDULER_LEDGER_FILENAME}",
                "logs/hammer_radar_forward/tiny_live_dry_run_lane_arming_rehearsal.ndjson",
            ],
        }
    )
    if record_timer_observed_armed_lane_wait_certificate:
        payload = append_tiny_live_timer_observed_armed_lane_wait_certificate(
            payload,
            log_dir=resolved_log_dir,
        )
    return payload


def build_latest_or_status_tiny_live_timer_observed_armed_lane_wait_certificate(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    latest = load_latest_tiny_live_timer_observed_armed_lane_wait_certificate(log_dir=log_dir)
    if latest:
        latest["final_command_available"] = False
        latest["submit_allowed"] = False
        latest["real_order_forbidden"] = True
        latest["safety"] = dict(SAFETY)
        return _sanitize(latest)
    return build_tiny_live_timer_observed_armed_lane_wait_certificate(log_dir=log_dir)


def load_latest_tiny_live_timer_observed_armed_lane_wait_certificate(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    records = load_tiny_live_timer_observed_armed_lane_wait_certificate_records(
        log_dir=log_dir,
        limit=1,
    )
    return records[0] if records else {}


def load_tiny_live_timer_observed_armed_lane_wait_certificate_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)]


def append_tiny_live_timer_observed_armed_lane_wait_certificate(
    record: Mapping[str, Any], *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    payload = _sanitize(
        {
            **dict(record),
            "timer_observed_armed_lane_wait_certificate_record_id": record.get(
                "timer_observed_armed_lane_wait_certificate_record_id"
            )
            or f"r295_timer_observed_armed_lane_wait_certificate_{uuid4().hex}",
            "timer_observed_armed_lane_wait_certificate_recorded": True,
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


def format_tiny_live_timer_observed_armed_lane_wait_certificate_json(
    payload: Mapping[str, Any],
) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _requested_lane(lane_key: str | None, rehearsal_packet: Mapping[str, Any]) -> str:
    if lane_key is not None:
        return str(lane_key).strip()
    discovered = str(rehearsal_packet.get("requested_lane_key") or "").strip()
    if discovered:
        return discovered
    return DEFAULT_REQUESTED_LANE_KEY


def _current_candidate_from_fresh_watch(*, log_dir: str | Path) -> dict[str, Any]:
    packet = build_latest_or_not_checked_fresh_trigger_watch(log_dir=log_dir)
    return _sanitize(
        {
            "exists": packet.get("current_fresh_candidate_exists") is True,
            "lane_key": packet.get("current_candidate_lane_key"),
            "signal_id": packet.get("current_candidate_signal_id"),
            "timeframe": packet.get("current_candidate_timeframe"),
            "direction": packet.get("current_candidate_direction"),
            "entry_mode": packet.get("current_candidate_entry_mode"),
            "source_status": packet.get("status"),
            "packet_event_type": packet.get("event_type"),
        }
    )


def _simulated_candidate_packet(*, lane_key: str, generated_at: datetime) -> dict[str, Any]:
    parts = lane_key.split("|")
    return _sanitize(
        {
            "exists": True,
            "lane_key": lane_key,
            "signal_id": f"r295_simulated_{uuid4().hex}",
            "symbol": parts[0] if len(parts) == 4 else "BTCUSDT",
            "timeframe": parts[1] if len(parts) == 4 else None,
            "direction": parts[2] if len(parts) == 4 else None,
            "entry_mode": parts[3] if len(parts) == 4 else None,
            "freshness_status": "fresh_tests_only",
            "simulated_for_tests_only": True,
            "generated_at": generated_at.isoformat(),
        }
    )


def _scheduler_tick_summary(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for record in records:
        summary.append(
            {
                "status": record.get("status"),
                "trigger_loop_status": record.get("trigger_loop_status"),
                "candidate_lane_key": record.get("current_candidate_lane_key"),
                "generated_at": record.get("generated_at"),
                "recorded_at_utc": record.get("recorded_at_utc"),
                "final_command_available": False,
                "submit_allowed": False,
                "real_order_forbidden": True,
            }
        )
    return _sanitize(summary)


def _panel(
    *,
    status: str,
    requested_lane: str,
    timer_health: Mapping[str, Any],
    recent_tick_count: int,
    scheduler_latest: Mapping[str, Any],
    candidate_packet: Mapping[str, Any],
    current_matches: bool,
    blockers: list[str],
) -> dict[str, Any]:
    recommended = (
        "KEEP_DRY_RUN_LANE_ARMED_AND_WAIT_FOR_EXACT_LANE_TIMER_OBSERVED_CANDIDATE"
        if status == TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED
        else "CLEAR_R295_TIMER_OBSERVED_WAIT_CERTIFICATE_BLOCKERS: " + "; ".join(blockers)
    )
    return _sanitize(
        {
            "status": status,
            "requested_lane_key": requested_lane or None,
            "observed_lane_key": requested_lane or None,
            "timer_health": {
                "timer_health_status": timer_health.get("status"),
                "timer_active": timer_health.get("timer_active") is True,
                "recent_tick_seen": recent_tick_count > 0,
                "recent_tick_count": recent_tick_count,
            },
            "recent_scheduler_tick_summary": {
                "recent_tick_seen": recent_tick_count > 0,
                "recent_tick_count": recent_tick_count,
                "latest_scheduler_status": scheduler_latest.get("status"),
                "latest_trigger_loop_status": scheduler_latest.get("trigger_loop_status"),
                "latest_candidate_lane_key": scheduler_latest.get("current_candidate_lane_key"),
            },
            "current_candidate_summary": {
                "current_fresh_candidate_exists": candidate_packet.get("exists") is True,
                "current_candidate_lane_key": candidate_packet.get("lane_key"),
                "current_candidate_matches_requested_lane": current_matches,
            },
            "exact_lane_match_status": {
                "exact_lane_only": True,
                "exact_lane_match_required": True,
                "no_cross_lane_borrowing": True,
                "current_candidate_matches_requested_lane": current_matches,
            },
            "blockers": blockers,
            "recommended_next_operator_move": recommended,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


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
