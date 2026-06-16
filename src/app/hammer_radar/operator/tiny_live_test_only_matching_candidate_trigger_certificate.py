"""R296 test-only matching-candidate trigger certificate.

This is a certificate layer over R294/R295 only. It injects explicit test-only
candidate packets to prove exact-lane matching semantics without creating order
payloads, submit commands, Binance calls, or live execution.
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
from src.app.hammer_radar.operator.tiny_live_dry_run_lane_arming_rehearsal import (
    ALLOWED_LANE_KEYS,
    build_tiny_live_dry_run_lane_arming_rehearsal,
    validate_r294_dry_run_lane,
)
from src.app.hammer_radar.operator.tiny_live_timer_observed_armed_lane_wait_certificate import (
    TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED,
    build_latest_or_status_tiny_live_timer_observed_armed_lane_wait_certificate,
    build_tiny_live_timer_observed_armed_lane_wait_certificate,
)

EVENT_TYPE = "TINY_LIVE_TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFICATE"
CREATED_BY_PHASE = "R296_TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFICATE"
LEDGER_FILENAME = "tiny_live_test_only_matching_candidate_trigger_certificate.ndjson"

TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFIED = (
    "TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFIED"
)
TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED = (
    "TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED"
)
TEST_ONLY_NON_MATCHING_CANDIDATE_NO_TRIGGER = (
    "TEST_ONLY_NON_MATCHING_CANDIDATE_NO_TRIGGER"
)

DEFAULT_REQUESTED_LANE_KEY = "BTCUSDT|44m|long|ladder_close_50_618"
SIMULATED_CANDIDATE_SOURCE = "R296_TEST_ONLY"

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


def build_tiny_live_test_only_matching_candidate_trigger_certificate(
    *,
    lane_key: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    log_dir: str | Path | None = None,
    simulate_matching_fresh_candidate_for_tests_only: bool = False,
    simulate_nonmatching_fresh_candidate_for_tests_only: bool = False,
    record_test_only_matching_candidate_trigger_certificate: bool = False,
    timer_observed_wait_certificate_packet: Mapping[str, Any] | None = None,
    timer_health_packet: Mapping[str, Any] | None = None,
    scheduler_records: Sequence[Mapping[str, Any]] | None = None,
    current_candidate_packet: Mapping[str, Any] | None = None,
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

    lane_validation = validate_r294_dry_run_lane(requested_lane)
    simulated_candidate_lane_key = _simulated_candidate_lane(
        requested_lane=requested_lane,
        matching_requested=matching_requested,
        nonmatching_requested=nonmatching_requested,
    )
    simulated_candidate = (
        _simulated_candidate_packet(lane_key=simulated_candidate_lane_key, generated_at=generated_at)
        if matching_requested or nonmatching_requested
        else _no_candidate_packet()
    )
    candidate_matches_requested_lane = bool(
        simulated_candidate.get("exists") is True
        and requested_lane
        and simulated_candidate.get("lane_key") == requested_lane
    )

    wait_certificate = (
        dict(timer_observed_wait_certificate_packet)
        if isinstance(timer_observed_wait_certificate_packet, Mapping)
        else _build_timer_observed_wait_certificate(
            requested_lane=requested_lane,
            log_dir=resolved_log_dir,
            timer_health_packet=timer_health_packet,
            scheduler_records=scheduler_records,
            current_candidate_packet=current_candidate_packet,
            generated_at=generated_at,
        )
    )
    dry_run_rehearsal = _build_r294_lifecycle_probe(
        requested_lane=requested_lane,
        log_dir=resolved_log_dir,
        timer_health_packet=timer_health_packet,
        simulated_candidate=simulated_candidate,
        generated_at=generated_at,
        enabled=matching_requested and candidate_matches_requested_lane,
    )

    blockers = list(lane_validation.get("blockers") or [])
    if not requested_operator_id:
        blockers.append("operator_id_required")
    if not requested_reason:
        blockers.append("reason_required")
    if not matching_requested and not nonmatching_requested:
        blockers.append("missing_test_only_simulation_flag")
    if matching_requested and nonmatching_requested:
        blockers.append("conflicting_test_only_simulation_flags")
    if matching_requested and not candidate_matches_requested_lane:
        blockers.append("test_only_candidate_does_not_match_requested_lane")
    if wait_certificate.get("status") != TIMER_OBSERVED_ARMED_LANE_WAIT_CERTIFIED:
        blockers.append("timer_observed_wait_certificate_not_certified")
    if matching_requested and candidate_matches_requested_lane and not dry_run_rehearsal.get("simulated_trigger_recorded"):
        blockers.append("simulated_dry_run_trigger_lifecycle_not_recorded")

    lifecycle = _r296_lifecycle(
        requested_lane=requested_lane,
        r294_packet=dry_run_rehearsal,
        enabled=matching_requested and candidate_matches_requested_lane and not blockers,
    )
    simulated_trigger_recorded = bool(lifecycle["simulated_lifecycle_status"] == "SIMULATED_DRY_RUN_LIFECYCLE_RECORDED")
    blockers = _dedupe(blockers)
    status = _status(
        blockers=blockers,
        matching_requested=matching_requested,
        nonmatching_requested=nonmatching_requested,
        candidate_matches_requested_lane=candidate_matches_requested_lane,
        simulated_trigger_recorded=simulated_trigger_recorded,
    )
    panel = _panel(
        status=status,
        requested_lane=requested_lane,
        simulated_candidate_lane_key=str(simulated_candidate.get("lane_key") or ""),
        wait_certificate=wait_certificate,
        matching_requested=matching_requested,
        nonmatching_requested=nonmatching_requested,
        candidate_matches_requested_lane=candidate_matches_requested_lane,
        lifecycle=lifecycle,
        blockers=blockers,
    )
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "generated_at": generated_at.isoformat(),
            "status": status,
            "requested_lane_key": requested_lane or None,
            "simulated_candidate_lane_key": simulated_candidate.get("lane_key"),
            "requested_operator_id": requested_operator_id or None,
            "requested_reason": requested_reason,
            "allowed_lane_keys": list(ALLOWED_LANE_KEYS),
            "lane_is_live_qualified": lane_validation.get("lane_is_live_qualified") is True,
            "lane_is_near_miss": lane_validation.get("lane_is_near_miss") is True,
            "lane_is_paper_only": lane_validation.get("lane_is_paper_only") is True,
            "exact_lane_risk_contract": lane_validation.get("exact_lane_risk_contract"),
            "candidate_matches_requested_lane": candidate_matches_requested_lane,
            "exact_lane_only": True,
            "no_cross_lane_borrowing": True,
            "dry_run_only": True,
            "test_only": True,
            "live_execution_enabled": False,
            "allow_live_orders": False,
            "global_kill_switch": True,
            "timer_health_status": wait_certificate.get("timer_health_status"),
            "timer_active": wait_certificate.get("timer_active") is True,
            "recent_tick_seen": wait_certificate.get("recent_tick_seen") is True,
            "recent_tick_count": int(wait_certificate.get("recent_tick_count") or 0),
            "timer_observed_wait_certificate_status": wait_certificate.get("status"),
            "current_real_fresh_candidate_exists": wait_certificate.get("current_real_fresh_candidate_exists") is True
            or wait_certificate.get("current_fresh_candidate_exists") is True,
            "simulation_flag_required": not (matching_requested or nonmatching_requested),
            "simulated_fresh_candidate_injected": matching_requested or nonmatching_requested,
            "simulated_candidate_source": simulated_candidate.get("simulated_candidate_source"),
            "simulated_candidate_not_real_market_data": simulated_candidate.get("simulated_candidate_not_real_market_data") is True,
            "test_only_matching_requested": matching_requested,
            "test_only_nonmatching_requested": nonmatching_requested,
            "simulate_matching_fresh_candidate_for_tests_only": matching_requested,
            "simulate_nonmatching_fresh_candidate_for_tests_only": nonmatching_requested,
            "simulated_trigger_recorded": simulated_trigger_recorded,
            **lifecycle,
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
            "test_only_matching_candidate_trigger_certificate_panel": panel,
            "record_test_only_matching_candidate_trigger_certificate_requested": bool(
                record_test_only_matching_candidate_trigger_certificate
            ),
            "test_only_matching_candidate_trigger_certificate_recorded": False,
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_timer_observed_armed_lane_wait_certificate.py",
                "src/app/hammer_radar/operator/tiny_live_dry_run_lane_arming_rehearsal.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_loop.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py",
                "src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py",
                "src/app/hammer_radar/operator/tiny_live_one_shot_pre_activation_gate.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py",
                "configs/hammer_radar/autonomous_arming_state.json",
                "configs/hammer_radar/tiny_live_risk_contracts.json",
                f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
            ],
        }
    )
    if record_test_only_matching_candidate_trigger_certificate:
        payload = append_tiny_live_test_only_matching_candidate_trigger_certificate(
            payload,
            log_dir=resolved_log_dir,
        )
    return payload


def build_status_tiny_live_test_only_matching_candidate_trigger_certificate(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    return build_tiny_live_test_only_matching_candidate_trigger_certificate(
        log_dir=log_dir,
        operator_id="api_status_read_model",
        reason="R296 safe read-only status; explicit test-only simulation flag required; no record; no submit; no order.",
        record_test_only_matching_candidate_trigger_certificate=False,
    )


def build_latest_or_status_tiny_live_test_only_matching_candidate_trigger_certificate(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    latest = load_latest_tiny_live_test_only_matching_candidate_trigger_certificate(log_dir=log_dir)
    if latest:
        return _safe_public_payload(latest)
    return build_tiny_live_test_only_matching_candidate_trigger_certificate(log_dir=log_dir)


def load_latest_tiny_live_test_only_matching_candidate_trigger_certificate(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    records = load_tiny_live_test_only_matching_candidate_trigger_certificate_records(
        log_dir=log_dir,
        limit=1,
    )
    return records[0] if records else {}


def load_tiny_live_test_only_matching_candidate_trigger_certificate_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)]


def append_tiny_live_test_only_matching_candidate_trigger_certificate(
    record: Mapping[str, Any], *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    payload = _safe_public_payload(
        {
            **dict(record),
            "test_only_matching_candidate_trigger_certificate_record_id": record.get(
                "test_only_matching_candidate_trigger_certificate_record_id"
            )
            or f"r296_test_only_matching_candidate_trigger_certificate_{uuid4().hex}",
            "test_only_matching_candidate_trigger_certificate_recorded": True,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
        }
    )
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def format_tiny_live_test_only_matching_candidate_trigger_certificate_json(
    payload: Mapping[str, Any],
) -> str:
    return json.dumps(_safe_public_payload(payload), sort_keys=True, separators=(",", ":"))


def _build_timer_observed_wait_certificate(
    *,
    requested_lane: str,
    log_dir: str | Path,
    timer_health_packet: Mapping[str, Any] | None,
    scheduler_records: Sequence[Mapping[str, Any]] | None,
    current_candidate_packet: Mapping[str, Any] | None,
    generated_at: datetime,
) -> dict[str, Any]:
    if timer_health_packet is not None or scheduler_records is not None or current_candidate_packet is not None:
        return build_tiny_live_timer_observed_armed_lane_wait_certificate(
            log_dir=log_dir,
            lane_key=requested_lane,
            operator_id="r296_certificate",
            reason="R296 test-only matching candidate certificate dependency; no submit; no order.",
            timer_health_packet=timer_health_packet,
            scheduler_records=scheduler_records,
            current_candidate_packet=current_candidate_packet or _no_candidate_packet(),
            now=generated_at,
        )
    packet = build_latest_or_status_tiny_live_timer_observed_armed_lane_wait_certificate(log_dir=log_dir)
    packet["current_real_fresh_candidate_exists"] = packet.get("current_fresh_candidate_exists") is True
    return _sanitize(packet)


def _build_r294_lifecycle_probe(
    *,
    requested_lane: str,
    log_dir: str | Path,
    timer_health_packet: Mapping[str, Any] | None,
    simulated_candidate: Mapping[str, Any],
    generated_at: datetime,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {
            "status": None,
            "simulated_trigger_recorded": False,
            "simulated_open_record": None,
            "simulated_protective_orders": None,
            "simulated_close_plan": None,
        }
    return build_tiny_live_dry_run_lane_arming_rehearsal(
        log_dir=log_dir,
        lane_key=requested_lane,
        operator_id="r296_certificate",
        reason="R296 in-memory test-only matching candidate lifecycle probe; no submit; no order.",
        timer_health_packet=timer_health_packet,
        current_candidate_packet=dict(simulated_candidate),
        record_dry_run_lane_arming_rehearsal=False,
        now=generated_at,
    )


def _r296_lifecycle(
    *, requested_lane: str, r294_packet: Mapping[str, Any], enabled: bool
) -> dict[str, Any]:
    if not enabled:
        return {
            "simulated_open_record": None,
            "simulated_protective_orders": None,
            "simulated_close_plan": None,
            "simulated_lifecycle_status": "SIMULATED_DRY_RUN_LIFECYCLE_NOT_RECORDED",
        }
    parts = requested_lane.split("|")
    r294_open = r294_packet.get("simulated_open_record")
    r294_protective = r294_packet.get("simulated_protective_orders")
    r294_close = r294_packet.get("simulated_close_plan")
    open_record = r294_open if isinstance(r294_open, Mapping) else {}
    protective = r294_protective if isinstance(r294_protective, Mapping) else {}
    close = r294_close if isinstance(r294_close, Mapping) else {}
    entry = _number(open_record.get("entry")) or 70000.0
    notional = _number(open_record.get("notional_usdt")) or 80.0
    margin = _number(open_record.get("margin_budget_usdt")) or 8.0
    quantity = _number(open_record.get("quantity"))
    return _sanitize(
        {
            "simulated_open_record": {
                "mode": "SIMULATED_DRY_RUN_ONLY",
                "lane_key": requested_lane,
                "symbol": parts[0] if len(parts) == 4 else "BTCUSDT",
                "timeframe": parts[1] if len(parts) == 4 else None,
                "direction": parts[2] if len(parts) == 4 else None,
                "entry_mode": parts[3] if len(parts) == 4 else None,
                "simulated_entry": entry,
                "simulated_quantity": quantity,
                "simulated_notional_usdt": notional,
                "simulated_margin_usdt": margin,
                "leverage": int(_number(open_record.get("leverage")) or 10),
                "order_placed": False,
                "executable_payload_created": False,
                "submit_allowed": False,
                "final_command_available": False,
            },
            "simulated_protective_orders": {
                "mode": "SIMULATED_DRY_RUN_ONLY",
                "stop_loss_preview": protective.get("stop"),
                "take_profit_preview": protective.get("take_profit"),
                "reduce_only": True,
                "order_placed": False,
                "executable_payload_created": False,
            },
            "simulated_close_plan": {
                "mode": "SIMULATED_DRY_RUN_ONLY",
                "close_trigger_policy": close.get("close_via") or [
                    "protective_stop",
                    "take_profit",
                    "future_trailing_or_exit_logic",
                ],
                "max_loss_usdt": open_record.get("max_loss_usdt"),
                "no_live_close_order": True,
            },
            "simulated_lifecycle_status": "SIMULATED_DRY_RUN_LIFECYCLE_RECORDED",
        }
    )


def _simulated_candidate_lane(
    *, requested_lane: str, matching_requested: bool, nonmatching_requested: bool
) -> str:
    if matching_requested:
        return requested_lane
    if nonmatching_requested:
        for lane in ALLOWED_LANE_KEYS:
            if lane != requested_lane:
                return lane
        return "BTCUSDT|55m|long|ladder_close_50_618"
    return ""


def _simulated_candidate_packet(*, lane_key: str, generated_at: datetime) -> dict[str, Any]:
    parts = lane_key.split("|")
    direction = parts[2] if len(parts) == 4 else "long"
    return _sanitize(
        {
            "exists": True,
            "lane_key": lane_key,
            "signal_id": f"r296_simulated_{uuid4().hex}",
            "symbol": parts[0] if len(parts) == 4 else "BTCUSDT",
            "timeframe": parts[1] if len(parts) == 4 else None,
            "direction": direction,
            "entry_mode": parts[3] if len(parts) == 4 else None,
            "age_minutes": 1.0,
            "freshness_status": "fresh_tests_only",
            "entry": 70000.0,
            "stop": 69300.0 if direction == "long" else 70700.0,
            "take_profit": 71400.0 if direction == "long" else 68600.0,
            "simulated_candidate_source": SIMULATED_CANDIDATE_SOURCE,
            "simulated_candidate_not_real_market_data": True,
            "simulated_for_tests_only": True,
            "test_only": True,
            "generated_at": generated_at.isoformat(),
        }
    )


def _no_candidate_packet() -> dict[str, Any]:
    return {
        "exists": False,
        "lane_key": None,
        "source_status": "FRESH_TRIGGER_WAIT",
    }


def _status(
    *,
    blockers: Sequence[str],
    matching_requested: bool,
    nonmatching_requested: bool,
    candidate_matches_requested_lane: bool,
    simulated_trigger_recorded: bool,
) -> str:
    if blockers:
        return TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED
    if nonmatching_requested and not candidate_matches_requested_lane:
        return TEST_ONLY_NON_MATCHING_CANDIDATE_NO_TRIGGER
    if matching_requested and candidate_matches_requested_lane and simulated_trigger_recorded:
        return TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFIED
    return TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_BLOCKED


def _panel(
    *,
    status: str,
    requested_lane: str,
    simulated_candidate_lane_key: str,
    wait_certificate: Mapping[str, Any],
    matching_requested: bool,
    nonmatching_requested: bool,
    candidate_matches_requested_lane: bool,
    lifecycle: Mapping[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    if status == TEST_ONLY_MATCHING_CANDIDATE_TRIGGER_CERTIFIED:
        recommended = "REVIEW_R296_SIMULATED_DRY_RUN_LIFECYCLE_AND_KEEP_REAL_SUBMIT_DISABLED"
    elif status == TEST_ONLY_NON_MATCHING_CANDIDATE_NO_TRIGGER:
        recommended = "NONMATCHING_TEST_ONLY_CANDIDATE_CONFIRMED_NO_TRIGGER_KEEP_WAITING"
    else:
        recommended = "PROVIDE_EXPLICIT_R296_TEST_ONLY_SIMULATION_FLAG_OR_CLEAR_BLOCKERS: " + "; ".join(blockers)
    return _sanitize(
        {
            "status": status,
            "requested_lane_key": requested_lane or None,
            "simulation_flag_required": not (matching_requested or nonmatching_requested),
            "test_only_matching_requested": matching_requested,
            "test_only_nonmatching_requested": nonmatching_requested,
            "timer_observed_wait_certificate_summary": {
                "status": wait_certificate.get("status"),
                "timer_health_status": wait_certificate.get("timer_health_status"),
                "timer_active": wait_certificate.get("timer_active") is True,
                "recent_tick_seen": wait_certificate.get("recent_tick_seen") is True,
                "recent_tick_count": int(wait_certificate.get("recent_tick_count") or 0),
            },
            "matching_nonmatching_test_only_path_summary": {
                "simulated_candidate_lane_key": simulated_candidate_lane_key or None,
                "candidate_matches_requested_lane": candidate_matches_requested_lane,
                "exact_lane_only": True,
                "no_cross_lane_borrowing": True,
                "simulated_candidate_source": SIMULATED_CANDIDATE_SOURCE
                if (matching_requested or nonmatching_requested)
                else None,
                "simulated_candidate_not_real_market_data": matching_requested or nonmatching_requested,
            },
            "simulated_lifecycle_summary": {
                "simulated_trigger_recorded": lifecycle.get("simulated_lifecycle_status")
                == "SIMULATED_DRY_RUN_LIFECYCLE_RECORDED",
                "simulated_lifecycle_status": lifecycle.get("simulated_lifecycle_status"),
                "simulated_open_record": lifecycle.get("simulated_open_record"),
                "simulated_protective_orders": lifecycle.get("simulated_protective_orders"),
                "simulated_close_plan": lifecycle.get("simulated_close_plan"),
            },
            "blockers": blockers,
            "recommended_next_operator_move": recommended,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )


def _safe_public_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = _sanitize(dict(payload))
    result["final_command_available"] = False
    result["submit_allowed"] = False
    result["real_order_forbidden"] = True
    result["executable_payload_created"] = False
    result["order_payload_created"] = False
    result["order_placed"] = False
    result["binance_order_endpoint_called"] = False
    result["binance_test_order_endpoint_called"] = False
    result["per_signal_operator_approval_required"] = False
    result["live_execution_enabled"] = False
    result["allow_live_orders"] = False
    result["global_kill_switch"] = True
    result["safety"] = dict(SAFETY)
    return result


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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
