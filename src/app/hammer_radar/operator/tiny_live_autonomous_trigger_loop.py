"""R287 autonomous tiny-live trigger loop packet.

This loop is autonomous dry-run only. It records what the machine would do
after a fresh live-qualified candidate appears and the exact lane is armed,
without creating executable payloads or requiring per-signal operator approval.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.strategy_promotion_watcher import (
    WATCH_BLOCKED_NEAR_MISS,
    WATCH_BLOCKED_PAPER_ONLY,
    WATCH_FOUND,
    WATCH_WAIT,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_armed_dry_run import (
    CONFIG_PATH as AUTONOMOUS_ARMING_CONFIG_PATH,
    build_simulated_order_triplet,
)
from src.app.hammer_radar.operator.tiny_live_one_shot_pre_activation_gate import (
    ONE_SHOT_PRE_ACTIVATION_BLOCKED,
    ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED,
    ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER,
    ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER,
    build_not_checked_pre_activation_gate_packet,
    build_tiny_live_one_shot_pre_activation_gate,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    LIVE_QUALIFIED,
    NEAR_MISS_INCUBATOR,
    PAPER_ONLY,
)

EVENT_TYPE = "TINY_LIVE_AUTONOMOUS_TRIGGER_LOOP"
CREATED_BY_PHASE = "R287_AUTONOMOUS_TRIGGER_LOOP_SEMANTICS_AND_DRY_RUN_EXECUTION_PATH"
LEDGER_FILENAME = "tiny_live_autonomous_trigger_loop.ndjson"

AUTONOMOUS_TRIGGER_WAIT = "AUTONOMOUS_TRIGGER_WAIT"
AUTONOMOUS_TRIGGER_BLOCKED = "AUTONOMOUS_TRIGGER_BLOCKED"
AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED = "AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED"
AUTONOMOUS_TRIGGER_NOT_CHECKED = "AUTONOMOUS_TRIGGER_NOT_CHECKED"

WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE = "WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE"
ARM_APPROVED_LANE_DRY_RUN_ONLY_IF_OPERATOR_WANTS_MACHINE_ACTIVE = (
    "ARM_APPROVED_LANE_DRY_RUN_ONLY_IF_OPERATOR_WANTS_MACHINE_ACTIVE"
)
CLEAR_AUTONOMOUS_TRIGGER_BLOCKERS = "CLEAR_AUTONOMOUS_TRIGGER_BLOCKERS"
RUN_READONLY_PRE_ACTIVATION_CHECKS = "RUN_READONLY_PRE_ACTIVATION_CHECKS"
AUTONOMOUS_DRY_RUN_LIFECYCLE_RECORDED = "AUTONOMOUS_DRY_RUN_LIFECYCLE_RECORDED"

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


def build_tiny_live_autonomous_trigger_loop(
    *,
    log_dir: str | Path | None = None,
    fetch_binance_readonly_precision_mark_price: bool = False,
    confirm_tiny_live_binance_readonly_fetch: str | None = None,
    fetch_binance_readonly_account_position: bool = False,
    confirm_binance_readonly_account_position: str | None = None,
    load_discovered_binance_readonly_env: bool = False,
    binance_readonly_env_file: str | Path | None = None,
    record_autonomous_trigger_loop: bool = False,
    operator_id: str = "local_operator",
    reason: str | None = None,
    risk_contract_config_path: str | Path | None = None,
    autonomous_arming_config_path: str | Path | None = None,
    pre_activation_packet: Mapping[str, Any] | None = None,
    candidate_watch: Mapping[str, Any] | None = None,
    binance_readiness: Mapping[str, Any] | None = None,
    post_manual_verification: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
    urlopen_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    arming_path = (
        Path(autonomous_arming_config_path)
        if autonomous_arming_config_path is not None
        else AUTONOMOUS_ARMING_CONFIG_PATH
    )
    fetch_requested = bool(
        fetch_binance_readonly_precision_mark_price
        or fetch_binance_readonly_account_position
        or load_discovered_binance_readonly_env
        or binance_readonly_env_file is not None
    )

    if pre_activation_packet is not None:
        pre_activation = dict(pre_activation_packet)
    elif fetch_requested or candidate_watch is not None or binance_readiness is not None or post_manual_verification is not None:
        pre_activation = build_tiny_live_one_shot_pre_activation_gate(
            log_dir=resolved_log_dir,
            fetch_binance_readonly_precision_mark_price=fetch_binance_readonly_precision_mark_price,
            confirm_tiny_live_binance_readonly_fetch=confirm_tiny_live_binance_readonly_fetch,
            fetch_binance_readonly_account_position=fetch_binance_readonly_account_position,
            confirm_binance_readonly_account_position=confirm_binance_readonly_account_position,
            load_discovered_binance_readonly_env=load_discovered_binance_readonly_env,
            binance_readonly_env_file=binance_readonly_env_file,
            risk_contract_config_path=risk_contract_config_path,
            autonomous_arming_config_path=arming_path,
            candidate_watch=candidate_watch,
            binance_readiness=binance_readiness,
            post_manual_verification=post_manual_verification,
            now=generated_at,
            env=env,
            urlopen_func=urlopen_func,
        )
    else:
        pre_activation = build_not_checked_pre_activation_gate_packet(log_dir=resolved_log_dir)

    watch = dict(candidate_watch or pre_activation.get("candidate_watch") or {})
    candidate = _current_candidate(pre_activation, watch)
    evidence = _strategy_evidence(pre_activation, watch)
    candidate_alert = _candidate_alert(pre_activation, watch)
    watch_status = str(candidate_alert.get("status") or pre_activation.get("candidate_watch_status") or WATCH_WAIT)
    live_class = str(
        evidence.get("live_qualification_class")
        or evidence.get("watch_category")
        or pre_activation.get("current_candidate_watch_category")
        or ""
    )
    lane_key = str(candidate.get("lane_key") or pre_activation.get("current_candidate_lane_key") or "")
    signal_id = str(candidate.get("signal_id") or pre_activation.get("current_candidate_signal_id") or "")
    blockers = _blockers(
        pre_activation=pre_activation,
        candidate=candidate,
        watch_status=watch_status,
        live_class=live_class,
    )
    status = _status(
        pre_activation=pre_activation,
        candidate=candidate,
        watch_status=watch_status,
        live_class=live_class,
        blockers=blockers,
    )
    lifecycle = (
        _build_dry_run_lifecycle(candidate=candidate, pre_activation=pre_activation)
        if status == AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED
        else _empty_lifecycle()
    )
    next_required_step = _next_required_step(status=status, blockers=blockers)

    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "generated_at": generated_at.isoformat(),
            "operator_role": OPERATOR_ROLE,
            "machine_role": MACHINE_ROLE,
            "per_signal_operator_approval_required": False,
            "alert_is_visibility_only": True,
            "autonomous_mode": "dry_run_only",
            "live_execution_enabled": False,
            "allow_live_orders": False,
            "global_kill_switch": True,
            "status": status,
            "pre_activation_status": pre_activation.get("status"),
            "fresh_trigger_watch_status": _fresh_trigger_watch_status(pre_activation, candidate, watch_status, live_class),
            "current_fresh_candidate_exists": bool(candidate),
            "current_candidate_lane_key": lane_key or None,
            "current_candidate_signal_id": signal_id or None,
            "approved_lane_match": pre_activation.get("approved_lane_match") is True,
            "candidate_live_qualified": _candidate_is_live_qualified(watch_status, live_class),
            "exact_lane_auto_armed": pre_activation.get("exact_lane_auto_armed") is True,
            "global_auto_live_enabled": pre_activation.get("global_auto_live_enabled") is True,
            "dry_run_only": True,
            "exact_lane_risk_contract_found": pre_activation.get("exact_lane_risk_contract_found") is True,
            "exact_lane_risk_contract_valid": pre_activation.get("exact_lane_risk_contract_valid") is True,
            "binance_readiness_ready": pre_activation.get("binance_readiness_ready") is True,
            "wallet_ready": pre_activation.get("wallet_ready") is True,
            "leverage_margin_ready": pre_activation.get("leverage_margin_ready") is True,
            "no_conflicting_position": pre_activation.get("no_conflicting_position") is True,
            "exchange_minimum_ready": pre_activation.get("exchange_minimum_ready") is True,
            "idempotency_clean": pre_activation.get("idempotency_clean") is True,
            "protective_triplet_preview_available": pre_activation.get("protective_triplet_preview_available") is True,
            "protective_triplet_preview_valid": pre_activation.get("protective_triplet_preview_valid") is True,
            "autonomous_dry_run_execution_recorded": False,
            "simulated_open_record": lifecycle["simulated_open_record"],
            "simulated_close_plan": lifecycle["simulated_close_plan"],
            "simulated_protective_orders": lifecycle["simulated_protective_orders"],
            "next_required_step": next_required_step,
            "blockers": blockers,
            "record_autonomous_trigger_loop_requested": bool(record_autonomous_trigger_loop),
            "operator_intent": {
                "operator_id": str(operator_id or "local_operator"),
                "reason": str(reason or ""),
                "record_only": True,
                "operator_controls_arming_risk_kill_switch": True,
                "per_signal_approval": False,
            },
            "alert_payload": _alert_payload(status=status, candidate=candidate, blockers=blockers),
            "autonomous_trigger_loop_panel": _panel(
                status=status,
                candidate=candidate,
                pre_activation=pre_activation,
                lifecycle=lifecycle,
                next_required_step=next_required_step,
                blockers=blockers,
            ),
            "pre_activation_packet": pre_activation,
            "candidate_watch": watch,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safety": _merged_safety(pre_activation),
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_one_shot_pre_activation_gate.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_armed_dry_run.py",
                "src/app/hammer_radar/operator/strategy_promotion_watcher.py",
                "configs/hammer_radar/autonomous_arming_state.json",
                "configs/hammer_radar/tiny_live_risk_contracts.json",
                f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
            ],
        }
    )
    if record_autonomous_trigger_loop and status == AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED:
        payload = append_tiny_live_autonomous_trigger_loop(payload, log_dir=resolved_log_dir)
    return payload


def load_latest_tiny_live_autonomous_trigger_loop(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_tiny_live_autonomous_trigger_loop_records(log_dir=log_dir, limit=1)
    return records[0] if records else {}


def load_tiny_live_autonomous_trigger_loop_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_autonomous_trigger_loop_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)]


def append_tiny_live_autonomous_trigger_loop(
    record: Mapping[str, Any], *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    payload = _sanitize(
        {
            **dict(record),
            "autonomous_trigger_loop_record_id": record.get("autonomous_trigger_loop_record_id")
            or f"r287_autonomous_trigger_loop_{uuid4().hex}",
            "autonomous_dry_run_execution_recorded": True,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safety": _merged_safety(record),
        }
    )
    path = tiny_live_autonomous_trigger_loop_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def tiny_live_autonomous_trigger_loop_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def build_latest_or_not_checked_autonomous_trigger_loop(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    latest = load_latest_tiny_live_autonomous_trigger_loop(log_dir=log_dir)
    if latest:
        latest["final_command_available"] = False
        latest["submit_allowed"] = False
        latest["real_order_forbidden"] = True
        latest["safety"] = _merged_safety(latest)
        return _sanitize(latest)
    return build_tiny_live_autonomous_trigger_loop(log_dir=log_dir)


def format_tiny_live_autonomous_trigger_loop_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _status(
    *,
    pre_activation: Mapping[str, Any],
    candidate: Mapping[str, Any],
    watch_status: str,
    live_class: str,
    blockers: list[str],
) -> str:
    pre_status = str(pre_activation.get("status") or "")
    if pre_status == ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED:
        return AUTONOMOUS_TRIGGER_NOT_CHECKED
    if not candidate and pre_status == ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER:
        return AUTONOMOUS_TRIGGER_WAIT
    if not candidate:
        return AUTONOMOUS_TRIGGER_BLOCKED if blockers else AUTONOMOUS_TRIGGER_WAIT
    if watch_status in {WATCH_BLOCKED_PAPER_ONLY, WATCH_BLOCKED_NEAR_MISS} or live_class in {
        PAPER_ONLY,
        NEAR_MISS_INCUBATOR,
    }:
        return AUTONOMOUS_TRIGGER_BLOCKED
    if blockers:
        return AUTONOMOUS_TRIGGER_BLOCKED
    if pre_status == ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER:
        return AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED
    return AUTONOMOUS_TRIGGER_BLOCKED


def _blockers(
    *,
    pre_activation: Mapping[str, Any],
    candidate: Mapping[str, Any],
    watch_status: str,
    live_class: str,
) -> list[str]:
    blockers: list[str] = []
    pre_status = str(pre_activation.get("status") or "")
    if pre_status == ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED:
        blockers.append("pre_activation_gate_not_checked")
    elif pre_status == ONE_SHOT_PRE_ACTIVATION_BLOCKED:
        blockers.extend(str(item) for item in pre_activation.get("blockers") or ["pre_activation_not_ready"])
    if not candidate:
        return _dedupe(blockers)
    if watch_status == WATCH_BLOCKED_PAPER_ONLY or live_class == PAPER_ONLY:
        blockers.extend(["strategy_not_live_qualified", "paper_only"])
    if watch_status == WATCH_BLOCKED_NEAR_MISS or live_class == NEAR_MISS_INCUBATOR:
        blockers.extend(["strategy_not_live_qualified", "near_miss"])
    required = {
        "approved_lane_match": "candidate_lane_not_approved_for_r287",
        "candidate_live_qualified": "current_candidate_not_live_qualified",
        "exact_lane_risk_contract_found": "exact_lane_risk_contract_missing",
        "exact_lane_risk_contract_valid": "exact_lane_risk_contract_invalid",
        "binance_readiness_ready": "binance_readiness_not_ready",
        "wallet_ready": "wallet_not_ready",
        "leverage_margin_ready": "leverage_margin_not_ready",
        "no_conflicting_position": "position_conflict_not_clear",
        "exchange_minimum_ready": "exchange_minimum_not_ready",
        "idempotency_clean": "idempotency_not_clean",
        "protective_triplet_preview_available": "protective_triplet_preview_missing",
        "protective_triplet_preview_valid": "protective_triplet_preview_invalid",
    }
    checks = {
        "approved_lane_match": pre_activation.get("approved_lane_match") is True,
        "candidate_live_qualified": _candidate_is_live_qualified(watch_status, live_class),
        "exact_lane_risk_contract_found": pre_activation.get("exact_lane_risk_contract_found") is True,
        "exact_lane_risk_contract_valid": pre_activation.get("exact_lane_risk_contract_valid") is True,
        "binance_readiness_ready": pre_activation.get("binance_readiness_ready") is True,
        "wallet_ready": pre_activation.get("wallet_ready") is True,
        "leverage_margin_ready": pre_activation.get("leverage_margin_ready") is True,
        "no_conflicting_position": pre_activation.get("no_conflicting_position") is True,
        "exchange_minimum_ready": pre_activation.get("exchange_minimum_ready") is True,
        "idempotency_clean": pre_activation.get("idempotency_clean") is True,
        "protective_triplet_preview_available": pre_activation.get("protective_triplet_preview_available") is True,
        "protective_triplet_preview_valid": pre_activation.get("protective_triplet_preview_valid") is True,
    }
    for key, blocker in required.items():
        if checks[key] is not True:
            blockers.append(blocker)
    if pre_activation.get("global_auto_live_enabled") is not True:
        blockers.append("global_auto_live_not_enabled")
    if pre_activation.get("exact_lane_auto_armed") is not True:
        blockers.append("exact_lane_not_armed")
    return _dedupe(blockers)


def _next_required_step(*, status: str, blockers: list[str]) -> str:
    if status == AUTONOMOUS_TRIGGER_WAIT:
        return WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE
    if status == AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED:
        return AUTONOMOUS_DRY_RUN_LIFECYCLE_RECORDED
    if status == AUTONOMOUS_TRIGGER_NOT_CHECKED:
        return RUN_READONLY_PRE_ACTIVATION_CHECKS
    if "exact_lane_not_armed" in blockers or "global_auto_live_not_enabled" in blockers:
        return ARM_APPROVED_LANE_DRY_RUN_ONLY_IF_OPERATOR_WANTS_MACHINE_ACTIVE
    return CLEAR_AUTONOMOUS_TRIGGER_BLOCKERS


def _build_dry_run_lifecycle(
    *, candidate: Mapping[str, Any], pre_activation: Mapping[str, Any]
) -> dict[str, Any]:
    arming_status = pre_activation.get("autonomous_dry_run_arming_status")
    arming_state = {}
    if isinstance(arming_status, Mapping) and isinstance(arming_status.get("arming_state"), Mapping):
        arming_state = dict(arming_status["arming_state"])
    arming_state.update(
        {
            "max_position_notional_usdt": 80.0,
            "leverage": 10.0,
            "margin_budget_usdt": 8.0,
            "require_protective_orders": True,
        }
    )
    triplet = build_simulated_order_triplet(selected_candidate=candidate, arming_state=arming_state)
    contract = pre_activation.get("exact_lane_risk_contract")
    contract_body = contract.get("contract") if isinstance(contract, Mapping) and isinstance(contract.get("contract"), Mapping) else {}
    entry = triplet.get("entry_order") if isinstance(triplet.get("entry_order"), Mapping) else {}
    stop = triplet.get("protective_stop_order") if isinstance(triplet.get("protective_stop_order"), Mapping) else {}
    take_profit = triplet.get("take_profit_order") if isinstance(triplet.get("take_profit_order"), Mapping) else {}
    return _sanitize(
        {
            "simulated_open_record": {
                "status": "SIMULATED_OPEN_READY",
                "signal_id": candidate.get("signal_id"),
                "lane_key": candidate.get("lane_key"),
                "symbol": candidate.get("symbol"),
                "intended_side": entry.get("side"),
                "direction": candidate.get("direction"),
                "entry": candidate.get("entry"),
                "quantity": entry.get("quantity"),
                "qty_rounded": entry.get("quantity"),
                "notional_usdt": entry.get("notional_usdt"),
                "notional_lte_80_usdt": _number(entry.get("notional_usdt")) is not None
                and _number(entry.get("notional_usdt")) <= 80.0,
                "leverage": 10,
                "margin_budget_usdt": 8.0,
                "max_loss_usdt": _number(contract_body.get("max_loss_usdt")),
                "dry_run_only": True,
                "executable_payload_created": False,
                "submit_allowed": False,
                "real_order_forbidden": True,
            },
            "simulated_protective_orders": {
                "status": "PROTECTIVE_ORDERS_SIMULATED",
                "protective_stop_required": True,
                "take_profit_required": True,
                "stop": candidate.get("stop"),
                "take_profit": candidate.get("take_profit"),
                "stop_order": stop,
                "take_profit_order": take_profit,
                "executable_payload_created": False,
                "submit_allowed": False,
                "real_order_forbidden": True,
            },
            "simulated_close_plan": {
                "status": "PROTECTIVE_ORDERS_SIMULATED",
                "close_via": ["protective_stop", "take_profit", "future_trailing_or_exit_logic"],
                "exit_side": stop.get("side"),
                "quantity": entry.get("quantity"),
                "dry_run_only": True,
                "executable_payload_created": False,
                "submit_allowed": False,
                "real_order_forbidden": True,
            },
        }
    )


def _empty_lifecycle() -> dict[str, Any]:
    return {
        "simulated_open_record": None,
        "simulated_protective_orders": None,
        "simulated_close_plan": None,
    }


def _fresh_trigger_watch_status(
    pre_activation: Mapping[str, Any],
    candidate: Mapping[str, Any],
    watch_status: str,
    live_class: str,
) -> str:
    pre_status = str(pre_activation.get("status") or "")
    if pre_status == ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED:
        return "FRESH_TRIGGER_NOT_CHECKED"
    if not candidate and pre_status == ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER:
        return "FRESH_TRIGGER_WAIT"
    if watch_status in {WATCH_BLOCKED_PAPER_ONLY, WATCH_BLOCKED_NEAR_MISS} or live_class in {
        PAPER_ONLY,
        NEAR_MISS_INCUBATOR,
    }:
        return "FRESH_TRIGGER_BLOCKED"
    if candidate and _candidate_is_live_qualified(watch_status, live_class):
        return "FRESH_TRIGGER_READY_FOR_MACHINE_AUTO_TRIGGER_WHEN_ARMED"
    return "FRESH_TRIGGER_BLOCKED"


def _alert_payload(*, status: str, candidate: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    return {
        "channel": "telegram_compatible",
        "send_enabled": False,
        "sent": False,
        "status": "prepared_not_sent",
        "visibility_only": True,
        "permission_gate": False,
        "message": "\n".join(
            [
                "Hammer Radar autonomous dry-run trigger loop",
                f"status: {status}",
                f"lane: {candidate.get('lane_key') or 'n/a'}",
                f"signal_id: {candidate.get('signal_id') or 'n/a'}",
                f"blockers: {'; '.join(blockers) if blockers else 'none'}",
                "Operator visibility only. Machine auto-triggers when dry-run armed and gates are open.",
                "No submit. No order. No executable payload.",
            ]
        ),
        "secrets_shown": False,
    }


def _panel(
    *,
    status: str,
    candidate: Mapping[str, Any],
    pre_activation: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    next_required_step: str,
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "operator_role": OPERATOR_ROLE,
        "machine_role": MACHINE_ROLE,
        "per_signal_operator_approval_required": False,
        "alert_is_visibility_only": True,
        "status": status,
        "candidate_summary": {
            "lane_key": candidate.get("lane_key") or pre_activation.get("current_candidate_lane_key"),
            "signal_id": candidate.get("signal_id") or pre_activation.get("current_candidate_signal_id"),
            "timeframe": candidate.get("timeframe"),
            "direction": candidate.get("direction"),
            "entry_mode": candidate.get("entry_mode"),
            "entry": candidate.get("entry"),
            "stop": candidate.get("stop"),
            "take_profit": candidate.get("take_profit"),
        },
        "arming_status": {
            "global_auto_live_enabled": pre_activation.get("global_auto_live_enabled") is True,
            "exact_lane_auto_armed": pre_activation.get("exact_lane_auto_armed") is True,
            "dry_run_only": True,
        },
        "autonomous_dry_run_lifecycle_status": (
            "recorded" if status == AUTONOMOUS_TRIGGER_DRY_RUN_EXECUTED else "not_recorded"
        ),
        "simulated_open_record": lifecycle.get("simulated_open_record"),
        "simulated_protective_orders": lifecycle.get("simulated_protective_orders"),
        "simulated_close_plan": lifecycle.get("simulated_close_plan"),
        "next_required_step": next_required_step,
        "blockers": blockers,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _candidate_is_live_qualified(watch_status: str, live_class: str) -> bool:
    return watch_status == WATCH_FOUND and live_class == LIVE_QUALIFIED


def _current_candidate(pre_activation: Mapping[str, Any], watch: Mapping[str, Any]) -> dict[str, Any]:
    alert = _candidate_alert(pre_activation, watch)
    candidate = alert.get("current_candidate")
    if isinstance(candidate, Mapping):
        return dict(candidate)
    panel = pre_activation.get("one_shot_pre_activation_gate_panel")
    if isinstance(panel, Mapping) and isinstance(panel.get("candidate"), Mapping):
        return dict(panel["candidate"])
    return {}


def _strategy_evidence(pre_activation: Mapping[str, Any], watch: Mapping[str, Any]) -> dict[str, Any]:
    alert = _candidate_alert(pre_activation, watch)
    evidence = alert.get("strategy_evidence")
    return dict(evidence) if isinstance(evidence, Mapping) else {}


def _candidate_alert(pre_activation: Mapping[str, Any], watch: Mapping[str, Any]) -> dict[str, Any]:
    alert = watch.get("candidate_alert_packet")
    if isinstance(alert, Mapping):
        return dict(alert)
    candidate_watch = pre_activation.get("candidate_watch")
    if isinstance(candidate_watch, Mapping) and isinstance(candidate_watch.get("candidate_alert_packet"), Mapping):
        return dict(candidate_watch["candidate_alert_packet"])
    return {}


def _merged_safety(*surfaces: Mapping[str, Any]) -> dict[str, Any]:
    safety = dict(SAFETY)
    for surface in surfaces:
        source = surface.get("safety") if isinstance(surface.get("safety"), Mapping) else surface
        for key in list(safety):
            if key in source:
                if safety[key] is False:
                    safety[key] = source.get(key) is True
                elif safety[key] is True:
                    safety[key] = source.get(key) is not False
    safety.update(
        {
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
            "real_order_forbidden": True,
            "paper_live_separation_intact": True,
            "per_signal_operator_approval_required": False,
        }
    )
    return safety


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            text = str(key).lower()
            if "secret" in text and key not in {"secrets_shown", "secret_values_in_output", "loaded_secret_names_redacted"}:
                clean[key] = "***REDACTED***" if item else item
                continue
            if "signature" in text and key not in {
                "signature_shown",
                "signed_order_request_created",
                "signed_trading_request_created",
                "signed_request_created",
            }:
                clean[key] = "***REDACTED***" if item else item
                continue
            if "signed_url" in text and key != "signed_url_shown":
                clean[key] = "***REDACTED***" if item else item
                continue
            clean[str(key)] = _sanitize(item)
        return clean
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        text = str(item)
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output
