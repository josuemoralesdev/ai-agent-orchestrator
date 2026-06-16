"""R297 timer-integrated test-only matching trigger rehearsal.

This is a bounded manual rehearsal wrapper over R296/R295/R294 and the
scheduler/timer visibility chain. It never mutates installed systemd units,
injects fake candidates into the normal scheduler, creates executable payloads,
or calls Binance order/test-order/mutation endpoints.
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
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler_timer_health import (
    build_autonomous_trigger_scheduler_timer_health,
)
from src.app.hammer_radar.operator.tiny_live_dry_run_lane_arming_rehearsal import (
    ALLOWED_LANE_KEYS,
    validate_r294_dry_run_lane,
)
from src.app.hammer_radar.operator.tiny_live_test_only_matching_candidate_trigger_certificate import (
    TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFIED,
    TEST_ONLY_NON_MATCHING_CANDIDATE_NO_TRIGGER,
    build_tiny_live_test_only_matching_candidate_trigger_certificate,
)

EVENT_TYPE = "TINY_LIVE_TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL"
CREATED_BY_PHASE = "R297_TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL"
LEDGER_FILENAME = "tiny_live_timer_integrated_test_only_matching_trigger_rehearsal.ndjson"

TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL_CERTIFIED = (
    "TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL_CERTIFIED"
)
TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL_BLOCKED = (
    "TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL_BLOCKED"
)
TIMER_INTEGRATED_TEST_ONLY_NONMATCHING_TRIGGER_REHEARSAL_NO_TRIGGER = (
    "TIMER_INTEGRATED_TEST_ONLY_NONMATCHING_TRIGGER_REHEARSAL_NO_TRIGGER"
)

DEFAULT_REQUESTED_LANE_KEY = "BTCUSDT|44m|long|ladder_close_50_618"
MAX_REHEARSAL_ITERATIONS = 2

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


def build_tiny_live_timer_integrated_test_only_matching_trigger_rehearsal(
    *,
    lane_key: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    log_dir: str | Path | None = None,
    simulate_matching_fresh_candidate_for_tests_only: bool = False,
    simulate_nonmatching_fresh_candidate_for_tests_only: bool = False,
    iterations: int = 1,
    record_timer_integrated_test_only_matching_trigger_rehearsal: bool = False,
    timer_health_packet: Mapping[str, Any] | None = None,
    timer_observed_wait_certificate_packet: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    requested_lane = (
        DEFAULT_REQUESTED_LANE_KEY if lane_key is None else str(lane_key).strip()
    )
    requested_operator_id = str(operator_id or "").strip()
    requested_reason = str(reason or "").strip()
    matching_requested = bool(simulate_matching_fresh_candidate_for_tests_only)
    nonmatching_requested = bool(simulate_nonmatching_fresh_candidate_for_tests_only)
    requested_iterations = _int(iterations, default=1)

    lane_validation = validate_r294_dry_run_lane(requested_lane)
    timer_health = (
        dict(timer_health_packet)
        if isinstance(timer_health_packet, Mapping)
        else build_autonomous_trigger_scheduler_timer_health(log_dir=resolved_log_dir)
    )
    preflight_blockers = list(lane_validation.get("blockers") or [])
    if not requested_operator_id:
        preflight_blockers.append("operator_id_required")
    if not requested_reason:
        preflight_blockers.append("reason_required")
    if not matching_requested and not nonmatching_requested:
        preflight_blockers.append("missing_test_only_simulation_flag")
    if matching_requested and nonmatching_requested:
        preflight_blockers.append("conflicting_test_only_simulation_flags")
    if requested_iterations < 1:
        preflight_blockers.append("iterations_must_be_at_least_1")
    if requested_iterations > MAX_REHEARSAL_ITERATIONS:
        preflight_blockers.append("iterations_max_2")

    iteration_packets: list[dict[str, Any]] = []
    if not preflight_blockers:
        for index in range(requested_iterations):
            certificate = build_tiny_live_test_only_matching_candidate_trigger_certificate(
                log_dir=resolved_log_dir,
                lane_key=requested_lane,
                operator_id=requested_operator_id,
                reason=requested_reason,
                simulate_matching_fresh_candidate_for_tests_only=matching_requested,
                simulate_nonmatching_fresh_candidate_for_tests_only=nonmatching_requested,
                record_test_only_matching_candidate_trigger_certificate=False,
                timer_health_packet=timer_health,
                timer_observed_wait_certificate_packet=timer_observed_wait_certificate_packet,
                now=generated_at,
            )
            iteration_packets.append(_iteration_packet(index=index, certificate=certificate))

    latest_certificate = (
        iteration_packets[-1]["test_only_matching_candidate_trigger_certificate_packet"]
        if iteration_packets
        else {}
    )
    blockers = _dedupe(
        preflight_blockers
        + [
            str(item)
            for item in latest_certificate.get("blockers", [])
            if str(item)
            and str(item)
            not in {
                "missing_test_only_simulation_flag",
                "conflicting_test_only_simulation_flags",
            }
        ]
    )
    if preflight_blockers:
        blockers = _dedupe(preflight_blockers)

    status = _status(
        blockers=blockers,
        matching_requested=matching_requested,
        nonmatching_requested=nonmatching_requested,
        latest_certificate=latest_certificate,
    )
    completed = len(iteration_packets)
    simulated_trigger_recorded = bool(
        latest_certificate.get("simulated_trigger_recorded") is True
        and status == TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL_CERTIFIED
    )
    panel = _panel(
        status=status,
        requested_lane=requested_lane,
        latest_certificate=latest_certificate,
        timer_health=timer_health,
        requested_iterations=requested_iterations,
        completed=completed,
        blockers=blockers,
    )
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "generated_at": generated_at.isoformat(),
            "status": status,
            "requested_lane_key": requested_lane or None,
            "simulated_candidate_lane_key": latest_certificate.get("simulated_candidate_lane_key"),
            "requested_operator_id": requested_operator_id or None,
            "requested_reason": requested_reason,
            "allowed_lane_keys": list(ALLOWED_LANE_KEYS),
            "lane_is_live_qualified": lane_validation.get("lane_is_live_qualified") is True,
            "candidate_matches_requested_lane": latest_certificate.get("candidate_matches_requested_lane") is True,
            "exact_lane_only": True,
            "no_cross_lane_borrowing": True,
            "dry_run_only": True,
            "test_only": True,
            "bounded_manual_rehearsal_only": True,
            "installed_systemd_timer_mutated": False,
            "installed_systemd_timer_fake_candidate_injection_enabled": False,
            "normal_scheduler_default_simulation_enabled": False,
            "live_execution_enabled": False,
            "allow_live_orders": False,
            "global_kill_switch": True,
            "timer_health_status": timer_health.get("status"),
            "timer_active": timer_health.get("timer_active") is True,
            "recent_tick_seen": timer_health.get("recent_tick_seen") is True,
            "recent_tick_count": int(timer_health.get("recent_tick_count") or 0),
            "scheduler_integration_rehearsal_supported": True,
            "scheduler_rehearsal_iterations_requested": requested_iterations,
            "scheduler_rehearsal_iterations_completed": completed,
            "scheduler_rehearsal_latest_status": iteration_packets[-1]["status"] if iteration_packets else None,
            "scheduler_rehearsal_latest_trigger_status": (
                iteration_packets[-1]["trigger_status"] if iteration_packets else None
            ),
            "scheduler_rehearsal_iterations": iteration_packets,
            "test_only_matching_certificate_status": latest_certificate.get("status"),
            "timer_observed_wait_certificate_status": latest_certificate.get("timer_observed_wait_certificate_status"),
            "simulation_flag_required": not (matching_requested or nonmatching_requested),
            "simulated_fresh_candidate_injected": latest_certificate.get("simulated_fresh_candidate_injected") is True,
            "simulated_trigger_recorded": simulated_trigger_recorded,
            "simulated_lifecycle_status": latest_certificate.get("simulated_lifecycle_status")
            or "SIMULATED_DRY_RUN_LIFECYCLE_NOT_RECORDED",
            "simulated_open_record": latest_certificate.get("simulated_open_record"),
            "simulated_protective_orders": latest_certificate.get("simulated_protective_orders"),
            "simulated_close_plan": latest_certificate.get("simulated_close_plan"),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "executable_payload_created": False,
            "order_payload_created": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "per_signal_operator_approval_required": False,
            "blockers": blockers,
            "recommended_next_operator_move": panel["recommended_next_operator_move"],
            "safety": dict(SAFETY),
            "timer_integrated_test_only_matching_trigger_rehearsal_panel": panel,
            "record_timer_integrated_test_only_matching_trigger_rehearsal_requested": bool(
                record_timer_integrated_test_only_matching_trigger_rehearsal
            ),
            "timer_integrated_test_only_matching_trigger_rehearsal_recorded": False,
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_test_only_matching_candidate_trigger_certificate.py",
                "src/app/hammer_radar/operator/tiny_live_timer_observed_armed_lane_wait_certificate.py",
                "src/app/hammer_radar/operator/tiny_live_dry_run_lane_arming_rehearsal.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_loop.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py",
                "src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py",
                "src/app/hammer_radar/operator/tiny_live_one_shot_pre_activation_gate.py",
                "ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template",
                "ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template",
                f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
            ],
        }
    )
    if record_timer_integrated_test_only_matching_trigger_rehearsal:
        payload = append_tiny_live_timer_integrated_test_only_matching_trigger_rehearsal(
            payload,
            log_dir=resolved_log_dir,
        )
    return payload


def build_status_tiny_live_timer_integrated_test_only_matching_trigger_rehearsal(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    return build_tiny_live_timer_integrated_test_only_matching_trigger_rehearsal(
        log_dir=log_dir,
        operator_id="api_status_read_model",
        reason="R297 safe read-only status; explicit test-only simulation flag required; no record; no submit; no order.",
        record_timer_integrated_test_only_matching_trigger_rehearsal=False,
    )


def load_latest_tiny_live_timer_integrated_test_only_matching_trigger_rehearsal(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    records = load_tiny_live_timer_integrated_test_only_matching_trigger_rehearsal_records(
        log_dir=log_dir,
        limit=1,
    )
    return records[0] if records else {}


def load_tiny_live_timer_integrated_test_only_matching_trigger_rehearsal_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [
        _sanitize(record)
        for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)
    ]


def append_tiny_live_timer_integrated_test_only_matching_trigger_rehearsal(
    record: Mapping[str, Any], *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    payload = _sanitize(
        {
            **dict(record),
            "timer_integrated_test_only_matching_trigger_rehearsal_record_id": record.get(
                "timer_integrated_test_only_matching_trigger_rehearsal_record_id"
            )
            or f"r297_timer_integrated_test_only_matching_trigger_rehearsal_{uuid4().hex}",
            "timer_integrated_test_only_matching_trigger_rehearsal_recorded": True,
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


def format_tiny_live_timer_integrated_test_only_matching_trigger_rehearsal_json(
    payload: Mapping[str, Any],
) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _iteration_packet(*, index: int, certificate: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize(
        {
            "iteration": index + 1,
            "status": "SCHEDULER_STYLE_TEST_ONLY_REHEARSAL_ITERATION_RECORDED",
            "trigger_status": certificate.get("status"),
            "current_candidate_lane_key": certificate.get("simulated_candidate_lane_key"),
            "candidate_matches_requested_lane": certificate.get("candidate_matches_requested_lane") is True,
            "simulated_trigger_recorded": certificate.get("simulated_trigger_recorded") is True,
            "autonomous_dry_run_execution_recorded": certificate.get("simulated_trigger_recorded") is True,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "test_only_matching_candidate_trigger_certificate_packet": dict(certificate),
        }
    )


def _status(
    *,
    blockers: Sequence[str],
    matching_requested: bool,
    nonmatching_requested: bool,
    latest_certificate: Mapping[str, Any],
) -> str:
    if blockers:
        return TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL_BLOCKED
    if (
        nonmatching_requested
        and latest_certificate.get("status") == TEST_ONLY_NON_MATCHING_CANDIDATE_NO_TRIGGER
    ):
        return TIMER_INTEGRATED_TEST_ONLY_NONMATCHING_TRIGGER_REHEARSAL_NO_TRIGGER
    if (
        matching_requested
        and latest_certificate.get("status") == TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFIED
        and latest_certificate.get("simulated_trigger_recorded") is True
    ):
        return TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL_CERTIFIED
    return TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL_BLOCKED


def _panel(
    *,
    status: str,
    requested_lane: str,
    latest_certificate: Mapping[str, Any],
    timer_health: Mapping[str, Any],
    requested_iterations: int,
    completed: int,
    blockers: Sequence[str],
) -> dict[str, Any]:
    recommended = (
        "R297_TEST_ONLY_TIMER_INTEGRATED_REHEARSAL_CERTIFIED_NO_SUBMIT_NO_ORDER"
        if status == TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL_CERTIFIED
        else "R297_NONMATCHING_TEST_ONLY_CANDIDATE_CONFIRMED_NO_TRIGGER"
        if status == TIMER_INTEGRATED_TEST_ONLY_NONMATCHING_TRIGGER_REHEARSAL_NO_TRIGGER
        else "PROVIDE_EXPLICIT_R297_TEST_ONLY_SIMULATION_FLAG_OR_CLEAR_BLOCKERS: "
        + "; ".join(blockers)
    )
    return _sanitize(
        {
            "status": status,
            "requested_lane_key": requested_lane or None,
            "allowed_lane_keys": list(ALLOWED_LANE_KEYS),
            "timer_health_summary": {
                "timer_health_status": timer_health.get("status"),
                "timer_active": timer_health.get("timer_active") is True,
                "recent_tick_seen": timer_health.get("recent_tick_seen") is True,
                "recent_tick_count": int(timer_health.get("recent_tick_count") or 0),
            },
            "scheduler_rehearsal_summary": {
                "scheduler_integration_rehearsal_supported": True,
                "scheduler_rehearsal_iterations_requested": requested_iterations,
                "scheduler_rehearsal_iterations_completed": completed,
                "bounded_manual_rehearsal_only": True,
                "normal_scheduler_default_simulation_enabled": False,
            },
            "matching_nonmatching_test_only_path_summary": {
                "simulated_candidate_lane_key": latest_certificate.get("simulated_candidate_lane_key"),
                "candidate_matches_requested_lane": latest_certificate.get("candidate_matches_requested_lane") is True,
                "exact_lane_only": True,
                "no_cross_lane_borrowing": True,
            },
            "simulated_lifecycle_summary": {
                "test_only_matching_certificate_status": latest_certificate.get("status"),
                "simulated_trigger_recorded": latest_certificate.get("simulated_trigger_recorded") is True,
                "simulated_lifecycle_status": latest_certificate.get("simulated_lifecycle_status")
                or "SIMULATED_DRY_RUN_LIFECYCLE_NOT_RECORDED",
            },
            "installed_systemd_timer_mutated": False,
            "installed_systemd_timer_fake_candidate_injection_enabled": False,
            "blockers": list(blockers),
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


def _int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
