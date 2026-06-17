"""R303 final tiny-live authorization gate.

This module composes the existing R298-R302/R285 readiness surfaces into a
manual-only final authorization packet. It never places orders, signs requests,
calls Binance order/test-order/mutation endpoints, arms/disarms, or mutates
configuration.
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
from src.app.hammer_radar.operator.tiny_live_armed_dry_run_timer_observation_certificate import (
    ARMED_DRY_RUN_TIMER_OBSERVATION_TRIGGER_READY_CERTIFIED,
    ARMED_DRY_RUN_TIMER_OBSERVATION_WAIT_CERTIFIED,
    DEFAULT_REQUESTED_LANE_KEY,
    build_status_tiny_live_armed_dry_run_timer_observation_certificate,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_armed_dry_run import (
    DRY_RUN_DISARM_CONFIRMATION_PHRASE,
)
from src.app.hammer_radar.operator.tiny_live_dry_run_lane_arming_rehearsal import (
    ALLOWED_LANE_KEYS,
    validate_r294_dry_run_lane,
)
from src.app.hammer_radar.operator.tiny_live_fresh_trigger_watch import (
    FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW,
    build_latest_or_not_checked_fresh_trigger_watch,
)
from src.app.hammer_radar.operator.tiny_live_manual_operator_dry_run_arming_post_arm_certificate import (
    MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_CERTIFIED,
    build_status_tiny_live_manual_operator_dry_run_arming_post_arm_certificate,
)
from src.app.hammer_radar.operator.tiny_live_one_shot_pre_activation_gate import (
    ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER,
    ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER,
    build_not_checked_pre_activation_gate_packet,
)
from src.app.hammer_radar.operator.tiny_live_operator_exact_lane_dry_run_arming_bridge import (
    OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_ARMED_CERTIFIED,
    build_status_tiny_live_operator_exact_lane_dry_run_arming_bridge,
)
from src.app.hammer_radar.operator.tiny_live_real_candidate_dry_run_trigger_bridge import (
    REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED,
    build_status_tiny_live_real_candidate_dry_run_trigger_bridge,
)
from src.app.hammer_radar.operator.tiny_live_real_candidate_timer_observation_certificate import (
    REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED,
    REAL_CANDIDATE_TIMER_OBSERVATION_TRIGGER_CERTIFIED,
    build_status_tiny_live_real_candidate_timer_observation_certificate,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import LIVE_QUALIFIED

EVENT_TYPE = "TINY_LIVE_FINAL_AUTHORIZATION_GATE"
CREATED_BY_PHASE = "R303_FINAL_TINY_LIVE_AUTHORIZATION_GATE"
LEDGER_FILENAME = "tiny_live_final_authorization_gate.ndjson"

FINAL_TINY_LIVE_AUTHORIZATION_WAITING_FOR_REAL_CANDIDATE = (
    "FINAL_TINY_LIVE_AUTHORIZATION_WAITING_FOR_REAL_CANDIDATE"
)
FINAL_TINY_LIVE_AUTHORIZATION_READY_FOR_OPERATOR_FINAL_SUBMIT = (
    "FINAL_TINY_LIVE_AUTHORIZATION_READY_FOR_OPERATOR_FINAL_SUBMIT"
)
FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED = "FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED"

FINAL_CONFIRMATION_PHRASE = (
    "I CONFIRM MANUAL OPERATOR ONE SHOT TINY LIVE FINAL SUBMIT FOR EXACT LANE "
    "BTCUSDT 44M LONG LADDER CLOSE 50 618; MAX NOTIONAL 80 USDT; LEVERAGE 10; "
    "MARGIN BUDGET 8 USDT; MAX LOSS 4.44 USDT; REDUCE ONLY PROTECTIVE ORDERS REQUIRED."
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "risk_contract_mutated": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "codex_arming_performed": False,
    "codex_config_mutation_performed": False,
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
}


def build_tiny_live_final_authorization_gate(
    *,
    lane_key: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    log_dir: str | Path | None = None,
    record_final_authorization_gate: bool = False,
    r302_packet: Mapping[str, Any] | None = None,
    r301_packet: Mapping[str, Any] | None = None,
    r300_packet: Mapping[str, Any] | None = None,
    r299_packet: Mapping[str, Any] | None = None,
    r298_packet: Mapping[str, Any] | None = None,
    pre_activation_packet: Mapping[str, Any] | None = None,
    candidate_watch_packet: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    requested_lane = DEFAULT_REQUESTED_LANE_KEY if lane_key is None else str(lane_key).strip()
    requested_operator_id = str(operator_id or "").strip() or "local_operator"
    requested_reason = str(reason or "").strip()
    lane_validation = validate_r294_dry_run_lane(requested_lane)

    r302 = dict(r302_packet) if isinstance(r302_packet, Mapping) else build_status_tiny_live_armed_dry_run_timer_observation_certificate(log_dir=resolved_log_dir, lane_key=requested_lane)
    r301 = dict(r301_packet) if isinstance(r301_packet, Mapping) else build_status_tiny_live_manual_operator_dry_run_arming_post_arm_certificate(log_dir=resolved_log_dir, lane_key=requested_lane)
    r300 = dict(r300_packet) if isinstance(r300_packet, Mapping) else build_status_tiny_live_operator_exact_lane_dry_run_arming_bridge(log_dir=resolved_log_dir, lane_key=requested_lane)
    r299 = dict(r299_packet) if isinstance(r299_packet, Mapping) else build_status_tiny_live_real_candidate_timer_observation_certificate(log_dir=resolved_log_dir, lane_key=requested_lane)
    r298 = dict(r298_packet) if isinstance(r298_packet, Mapping) else build_status_tiny_live_real_candidate_dry_run_trigger_bridge(log_dir=resolved_log_dir, lane_key=requested_lane)
    pre_activation = dict(pre_activation_packet) if isinstance(pre_activation_packet, Mapping) else build_not_checked_pre_activation_gate_packet(log_dir=resolved_log_dir)
    candidate_watch = dict(candidate_watch_packet) if isinstance(candidate_watch_packet, Mapping) else build_latest_or_not_checked_fresh_trigger_watch(log_dir=resolved_log_dir)

    current_exists = r298.get("current_real_candidate_exists") is True
    current_lane = r298.get("current_real_candidate_lane_key")
    signal_id = r298.get("current_real_candidate_signal_id")
    candidate_matches = bool(current_exists and current_lane == requested_lane and r298.get("candidate_matches_requested_lane") is True)
    freshness = r298.get("current_real_candidate_freshness_status")
    live_class = r298.get("current_real_candidate_live_qualification_class")
    candidate_entry = _first_present(r298.get("candidate_entry"), candidate_watch.get("current_candidate_entry"))
    candidate_stop = _first_present(r298.get("candidate_stop"), candidate_watch.get("current_candidate_stop"))
    candidate_take_profit = _first_present(r298.get("candidate_take_profit"), candidate_watch.get("current_candidate_take_profit"))
    candidate_age = _first_present(r298.get("candidate_age_minutes"), candidate_watch.get("current_candidate_age_minutes"))

    matrix = _readiness_matrix(
        lane_validation=lane_validation,
        r302=r302,
        r301=r301,
        r300=r300,
        r299=r299,
        r298=r298,
        pre_activation=pre_activation,
        candidate_watch=candidate_watch,
        current_exists=current_exists,
        candidate_matches=candidate_matches,
        freshness=freshness,
        live_class=live_class,
        candidate_entry=candidate_entry,
        candidate_stop=candidate_stop,
        candidate_take_profit=candidate_take_profit,
    )
    blockers = _blockers(matrix=matrix, current_exists=current_exists)
    status = _status(matrix=matrix, current_exists=current_exists, blockers=blockers)
    ready = status == FINAL_TINY_LIVE_AUTHORIZATION_READY_FOR_OPERATOR_FINAL_SUBMIT

    final_packet = (
        _final_manual_submit_packet(
            lane_key=requested_lane,
            signal_id=str(signal_id or ""),
            candidate_entry=candidate_entry,
            candidate_stop=candidate_stop,
            candidate_take_profit=candidate_take_profit,
        )
        if ready
        else None
    )
    final_command = final_packet.get("manual_operator_only_command") if final_packet else None
    manual_disarm = _manual_disarm_command(requested_lane, requested_operator_id)
    panel = _panel(
        status=status,
        requested_lane=requested_lane,
        matrix=matrix,
        blockers=blockers,
        final_packet=final_packet,
        manual_disarm=manual_disarm,
    )
    payload = _safe_public_payload(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "generated_at": generated_at.isoformat(),
            "requested_lane_key": requested_lane or None,
            "requested_operator_id": requested_operator_id,
            "requested_reason": requested_reason,
            "allowed_lane_keys": list(ALLOWED_LANE_KEYS),
            "live_qualified_lane_keys": list(ALLOWED_LANE_KEYS),
            "status": status,
            **matrix,
            "final_command_available": ready,
            "submit_allowed": ready,
            "real_order_forbidden": not ready,
            "executable_payload_created": ready,
            "order_payload_created": ready,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "final_manual_submit_command": final_command,
            "final_manual_submit_packet": final_packet,
            "manual_disarm_command": manual_disarm,
            "blockers": blockers,
            "safety": {
                **SAFETY,
                "final_command_available": ready,
                "submit_allowed": ready,
                "real_order_forbidden": not ready,
                "executable_payload_created": ready,
                "order_payload_created": ready,
            },
            "final_tiny_live_authorization_gate_panel": panel,
            "record_final_authorization_gate_requested": bool(record_final_authorization_gate),
            "final_authorization_gate_recorded": False,
            "r302_packet": r302,
            "r301_packet": r301,
            "r300_packet": r300,
            "r299_packet": r299,
            "r298_packet": r298,
            "pre_activation_packet": pre_activation,
            "candidate_watch_packet": candidate_watch,
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_armed_dry_run_timer_observation_certificate.py",
                "src/app/hammer_radar/operator/tiny_live_manual_operator_dry_run_arming_post_arm_certificate.py",
                "src/app/hammer_radar/operator/tiny_live_operator_exact_lane_dry_run_arming_bridge.py",
                "src/app/hammer_radar/operator/tiny_live_real_candidate_timer_observation_certificate.py",
                "src/app/hammer_radar/operator/tiny_live_real_candidate_dry_run_trigger_bridge.py",
                "src/app/hammer_radar/operator/tiny_live_one_shot_pre_activation_gate.py",
                "src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py",
                "src/app/hammer_radar/operator/tiny_live_final_console.py",
                "configs/hammer_radar/autonomous_arming_state.json",
                "configs/hammer_radar/tiny_live_risk_contracts.json",
                f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
            ],
        }
    )
    if record_final_authorization_gate:
        payload = append_tiny_live_final_authorization_gate(payload, log_dir=resolved_log_dir)
    return payload


def build_status_tiny_live_final_authorization_gate(
    *, lane_key: str | None = None, log_dir: str | Path | None = None
) -> dict[str, Any]:
    return build_tiny_live_final_authorization_gate(
        lane_key=lane_key,
        log_dir=log_dir,
        operator_id="api_status_read_model",
        reason="R303 safe read-only status; no record; no submit; no order.",
        record_final_authorization_gate=False,
    )


def append_tiny_live_final_authorization_gate(
    record: Mapping[str, Any], *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    payload = _safe_public_payload(
        {
            **dict(record),
            "final_authorization_gate_record_id": record.get("final_authorization_gate_record_id")
            or f"r303_final_authorization_gate_{uuid4().hex}",
            "final_authorization_gate_recorded": True,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
        }
    )
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_final_authorization_gate_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_safe_public_payload(json.loads(line)) for line in handle if line.strip()]
    return [
        _safe_public_payload(record)
        for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)
    ]


def format_tiny_live_final_authorization_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_safe_public_payload(payload), sort_keys=True, separators=(",", ":"))


def _readiness_matrix(
    *,
    lane_validation: Mapping[str, Any],
    r302: Mapping[str, Any],
    r301: Mapping[str, Any],
    r300: Mapping[str, Any],
    r299: Mapping[str, Any],
    r298: Mapping[str, Any],
    pre_activation: Mapping[str, Any],
    candidate_watch: Mapping[str, Any],
    current_exists: bool,
    candidate_matches: bool,
    freshness: Any,
    live_class: Any,
    candidate_entry: Any,
    candidate_stop: Any,
    candidate_take_profit: Any,
) -> dict[str, Any]:
    return {
        "lane_is_live_qualified": lane_validation.get("lane_is_live_qualified") is True,
        "lane_is_near_miss": lane_validation.get("lane_is_near_miss") is True,
        "lane_is_paper_only": lane_validation.get("lane_is_paper_only") is True,
        "exact_lane_only": True,
        "no_cross_lane_borrowing": True,
        "first_live_one_shot": True,
        "operator_final_submit_required": True,
        "dry_run_lane_armed": r302.get("exact_lane_auto_armed") is True,
        "exact_lane_auto_armed": r302.get("exact_lane_auto_armed") is True,
        "any_lane_auto_armed": r302.get("any_lane_auto_armed") is True,
        "armed_lane_key": r302.get("armed_lane_key"),
        "global_auto_live_enabled": r302.get("global_auto_live_enabled") is True,
        "dry_run_only": True,
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "r302_status": r302.get("status"),
        "r301_status": r301.get("status"),
        "r300_status": r300.get("status"),
        "r299_status": r299.get("status"),
        "r298_status": r298.get("status"),
        "pre_activation_status": pre_activation.get("status"),
        "candidate_watch_status": candidate_watch.get("status"),
        "current_real_candidate_exists": current_exists,
        "current_real_candidate_lane_key": r298.get("current_real_candidate_lane_key"),
        "current_real_candidate_signal_id": r298.get("current_real_candidate_signal_id"),
        "candidate_matches_requested_lane": candidate_matches,
        "current_real_candidate_freshness_status": freshness,
        "current_real_candidate_live_qualification_class": live_class,
        "candidate_entry": _number(candidate_entry),
        "candidate_stop": _number(candidate_stop),
        "candidate_take_profit": _number(candidate_take_profit),
        "candidate_age_minutes": _number(_first_present(r298.get("candidate_age_minutes"), candidate_watch.get("current_candidate_age_minutes"))),
        "timer_health_status": r302.get("timer_health_status"),
        "timer_active": r302.get("timer_active") is True,
        "recent_tick_seen": r302.get("recent_tick_seen") is True,
        "recent_tick_count": int(r302.get("recent_tick_count") or 0),
        "binance_readiness_ready": pre_activation.get("binance_readiness_ready") is True,
        "leverage_margin_ready": pre_activation.get("leverage_margin_ready") is True,
        "post_manual_leverage_margin_verified": pre_activation.get("post_manual_leverage_margin_verified") is True,
        "wallet_ready": pre_activation.get("wallet_ready") is True,
        "wallet_supports_configured_margin_budget": pre_activation.get("wallet_supports_configured_margin_budget") is True,
        "no_conflicting_position": pre_activation.get("no_conflicting_position") is True,
        "idempotency_clean": pre_activation.get("idempotency_clean") is True,
        "prior_live_submit_found": pre_activation.get("no_prior_live_submit") is False,
        "exact_lane_risk_contract_found": pre_activation.get("exact_lane_risk_contract_found") is True,
        "exact_lane_risk_contract_valid": pre_activation.get("exact_lane_risk_contract_valid") is True,
        "risk_contract_notional_cap_usdt": _number(pre_activation.get("risk_contract_notional_cap_usdt")),
        "risk_contract_margin_budget_usdt": _number(pre_activation.get("risk_contract_margin_budget_usdt")),
        "risk_contract_leverage": _number(pre_activation.get("risk_contract_leverage")),
        "protective_triplet_preview_available": pre_activation.get("protective_triplet_preview_available") is True,
        "protective_triplet_preview_valid": pre_activation.get("protective_triplet_preview_valid") is True,
        "fake_candidate_used": r298.get("fake_candidate_used") is True or candidate_watch.get("fake_candidate_used") is True,
        "test_only": r298.get("test_only") is True or candidate_watch.get("test_only") is True,
    }


def _blockers(*, matrix: Mapping[str, Any], current_exists: bool) -> list[str]:
    blockers: list[str] = []
    if matrix.get("lane_is_near_miss") is True:
        blockers.append("requested_lane_is_near_miss")
    if matrix.get("lane_is_paper_only") is True:
        blockers.append("requested_lane_is_paper_only")
    if matrix.get("lane_is_live_qualified") is not True:
        blockers.append("requested_lane_not_live_qualified")
    if matrix.get("exact_lane_auto_armed") is not True:
        blockers.append("exact_lane_not_armed")
    if matrix.get("timer_active") is not True:
        blockers.append("timer_not_active")
    if matrix.get("recent_tick_seen") is not True or int(matrix.get("recent_tick_count") or 0) <= 0:
        blockers.append("timer_recent_tick_missing")
    if matrix.get("r301_status") != MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_CERTIFIED:
        blockers.append("r301_post_arm_not_certified")
    if matrix.get("r300_status") != OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_ARMED_CERTIFIED:
        blockers.append("r300_exact_lane_not_certified")
    if matrix.get("r299_status") not in {
        REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED,
        REAL_CANDIDATE_TIMER_OBSERVATION_TRIGGER_CERTIFIED,
    }:
        blockers.append("r299_timer_observation_not_certified")
    if matrix.get("r302_status") not in {
        ARMED_DRY_RUN_TIMER_OBSERVATION_WAIT_CERTIFIED,
        ARMED_DRY_RUN_TIMER_OBSERVATION_TRIGGER_READY_CERTIFIED,
    }:
        blockers.append("r302_armed_timer_not_certified")
    if matrix.get("live_execution_enabled") is True:
        blockers.append("global_live_execution_enabled")
    if matrix.get("allow_live_orders") is True:
        blockers.append("global_live_orders_allowed")
    if matrix.get("fake_candidate_used") is True:
        blockers.append("fake_candidate_rejected")
    if matrix.get("test_only") is True:
        blockers.append("test_candidate_rejected")
    if not current_exists:
        return _dedupe(blockers)
    if matrix.get("candidate_matches_requested_lane") is not True:
        blockers.append("real_candidate_lane_mismatch")
    if not _fresh(matrix.get("current_real_candidate_freshness_status")):
        blockers.append("candidate_not_fresh")
    if matrix.get("current_real_candidate_live_qualification_class") != LIVE_QUALIFIED:
        blockers.append("candidate_not_live_qualified")
    if matrix.get("candidate_entry") is None:
        blockers.append("candidate_entry_missing")
    if matrix.get("candidate_stop") is None:
        blockers.append("candidate_stop_missing")
    if matrix.get("candidate_take_profit") is None:
        blockers.append("candidate_take_profit_missing")
    if matrix.get("r298_status") != REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED:
        blockers.append("r298_real_candidate_bridge_not_certified")
    if matrix.get("pre_activation_status") != ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER:
        blockers.append("pre_activation_not_ready_for_dry_run_trigger")
    if matrix.get("candidate_watch_status") != FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW:
        blockers.append("candidate_watch_not_ready_for_operator_review")
    for key, blocker in (
        ("binance_readiness_ready", "binance_readiness_not_ready"),
        ("leverage_margin_ready", "leverage_margin_not_ready"),
        ("post_manual_leverage_margin_verified", "post_manual_leverage_margin_not_verified"),
        ("wallet_ready", "wallet_not_ready"),
        ("wallet_supports_configured_margin_budget", "wallet_configured_margin_budget_not_ready"),
        ("no_conflicting_position", "open_position_conflict"),
        ("idempotency_clean", "idempotency_not_clean"),
        ("exact_lane_risk_contract_found", "exact_lane_risk_contract_missing"),
        ("exact_lane_risk_contract_valid", "exact_lane_risk_contract_invalid"),
        ("protective_triplet_preview_available", "protective_triplet_preview_missing"),
        ("protective_triplet_preview_valid", "protective_triplet_preview_invalid"),
    ):
        if matrix.get(key) is not True:
            blockers.append(blocker)
    if matrix.get("prior_live_submit_found") is True:
        blockers.append("prior_live_submit_found")
    if matrix.get("risk_contract_notional_cap_usdt") != 80.0:
        blockers.append("risk_contract_notional_cap_not_80")
    if matrix.get("risk_contract_leverage") != 10.0:
        blockers.append("risk_contract_leverage_not_10")
    if matrix.get("risk_contract_margin_budget_usdt") != 8.0:
        blockers.append("risk_contract_margin_budget_not_8")
    return _dedupe(blockers)


def _status(*, matrix: Mapping[str, Any], current_exists: bool, blockers: Sequence[str]) -> str:
    if blockers:
        return FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED
    if not current_exists:
        return FINAL_TINY_LIVE_AUTHORIZATION_WAITING_FOR_REAL_CANDIDATE
    return FINAL_TINY_LIVE_AUTHORIZATION_READY_FOR_OPERATOR_FINAL_SUBMIT


def _final_manual_submit_packet(
    *, lane_key: str, signal_id: str, candidate_entry: Any, candidate_stop: Any, candidate_take_profit: Any
) -> dict[str, Any]:
    idempotency_key = f"ONE_SHOT_TINY_LIVE:{lane_key}:{signal_id}"
    command = (
        "MANUAL_OPERATOR_ONLY ONE_SHOT_TINY_LIVE EXACT_LANE_ONLY NO_CROSS_LANE_BORROWING "
        "DO_NOT_RUN_FROM_CODEX "
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward tiny-live-actual-submit-reconcile "
        "--execute-actual-live-submit --allow-binance-order-endpoint "
        f'--operator-id local_operator --reason "R303 MANUAL_OPERATOR_ONLY final one-shot tiny live submit; lane={lane_key}; signal_id={signal_id}; idempotency_key={idempotency_key}" '
        f'--confirm-actual-live-submit "{FINAL_CONFIRMATION_PHRASE}"'
    )
    return {
        "available": True,
        "manual_operator_only": True,
        "operator_final_submit_required": True,
        "do_not_run_from_codex": True,
        "one_shot_tiny_live": True,
        "exact_lane_only": True,
        "no_cross_lane_borrowing": True,
        "lane_key": lane_key,
        "signal_id": signal_id,
        "idempotency_key": idempotency_key,
        "notional_cap_usdt": 80.0,
        "leverage": 10,
        "margin_budget_usdt": 8.0,
        "max_loss_usdt": 4.44,
        "entry": _number(candidate_entry),
        "stop": _number(candidate_stop),
        "take_profit": _number(candidate_take_profit),
        "reduce_only_protective_order_requirement": "STOP_MARKET_AND_TAKE_PROFIT_MARKET_REDUCE_ONLY_REQUIRED",
        "explicit_confirmation_phrase": FINAL_CONFIRMATION_PHRASE,
        "submit_allowed": True,
        "real_order_forbidden": False,
        "order_payload_created": True,
        "executable_payload_created": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
        "manual_operator_only_command": command,
        "secrets_shown": False,
        "signed_url_shown": False,
        "signature_shown": False,
    }


def _manual_disarm_command(lane_key: str, operator_id: str) -> str:
    return (
        "MANUAL_OPERATOR_ONLY DRY_RUN_DISARM NO_ORDER: "
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward tiny-live-autonomous-dry-run-disarm-lane "
        f'--lane-key "{lane_key}" --operator-id "{operator_id}" '
        '--reason "R303 manual operator rollback/disarm dry-run arming; no submit; no order." '
        f'--confirm-dry-run-autonomous-disarm "{DRY_RUN_DISARM_CONFIRMATION_PHRASE}"'
    )


def _panel(
    *, status: str, requested_lane: str, matrix: Mapping[str, Any], blockers: Sequence[str], final_packet: Mapping[str, Any] | None, manual_disarm: str
) -> dict[str, Any]:
    if status == FINAL_TINY_LIVE_AUTHORIZATION_READY_FOR_OPERATOR_FINAL_SUBMIT:
        recommended = "OPERATOR_REVIEW_MANUAL_ONLY_FINAL_SUBMIT_PACKET"
    elif status == FINAL_TINY_LIVE_AUTHORIZATION_WAITING_FOR_REAL_CANDIDATE:
        recommended = "KEEP_TIMER_RUNNING_WAIT_FOR_REAL_MATCHING_FRESH_LIVE_QUALIFIED_CANDIDATE"
    else:
        recommended = "CLEAR_R303_BLOCKERS_OR_MANUALLY_DISARM"
    return _sanitize(
        {
            "status": status,
            "requested_lane_key": requested_lane,
            "exact_lane_armed_state": {
                "dry_run_lane_armed": matrix.get("dry_run_lane_armed"),
                "exact_lane_auto_armed": matrix.get("exact_lane_auto_armed"),
                "any_lane_auto_armed": matrix.get("any_lane_auto_armed"),
                "armed_lane_key": matrix.get("armed_lane_key"),
            },
            "real_candidate_summary": {
                "exists": matrix.get("current_real_candidate_exists"),
                "lane_key": matrix.get("current_real_candidate_lane_key"),
                "signal_id": matrix.get("current_real_candidate_signal_id"),
                "matches_requested_lane": matrix.get("candidate_matches_requested_lane"),
                "freshness_status": matrix.get("current_real_candidate_freshness_status"),
                "live_qualification_class": matrix.get("current_real_candidate_live_qualification_class"),
                "entry": matrix.get("candidate_entry"),
                "stop": matrix.get("candidate_stop"),
                "take_profit": matrix.get("candidate_take_profit"),
            },
            "readiness_matrix": dict(matrix),
            "blockers": list(blockers),
            "final_command_available": final_packet is not None,
            "final_manual_submit_packet": dict(final_packet) if final_packet else None,
            "manual_disarm_command": manual_disarm,
            "recommended_next_operator_move": recommended,
            "submit_allowed": final_packet is not None,
            "real_order_forbidden": final_packet is None,
        }
    )


def _safe_public_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = _sanitize(dict(payload))
    result["order_placed"] = False
    result["real_order_placed"] = False
    result["execution_attempted"] = False
    result["binance_order_endpoint_called"] = False
    result["binance_test_order_endpoint_called"] = False
    result["secrets_shown"] = False
    result["signed_url_shown"] = False
    result["signature_shown"] = False
    return result


def _fresh(value: Any) -> bool:
    text = str(value or "").lower()
    return bool(text and "fresh" in text and text not in {"not_fresh", "stale", "expired"})


def _first_present(*items: Any) -> Any:
    for item in items:
        if item not in {None, ""}:
            return item
    return None


def _number(value: Any) -> float | None:
    try:
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
        clean: dict[str, Any] = {}
        for key, item in value.items():
            text = str(key).lower()
            if "secret" in text and key not in {"secrets_shown", "secret_values_in_output"}:
                clean[str(key)] = "***REDACTED***" if item else item
                continue
            if "signature" in text and key not in {
                "signature_shown",
                "signed_order_request_created",
                "signed_trading_request_created",
                "signed_request_created",
            }:
                clean[str(key)] = "***REDACTED***" if item else item
                continue
            if "signed_url" in text and key != "signed_url_shown":
                clean[str(key)] = "***REDACTED***" if item else item
                continue
            clean[str(key)] = _sanitize(item)
        return clean
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
