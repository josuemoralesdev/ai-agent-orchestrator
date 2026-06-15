"""R264 tiny-live actual submit and immediate reconciliation gate.

Default usage is preview-only. The real Binance Futures order endpoint can only
be called when the caller supplies the exact R264 live phrase, the explicit
execute flag, the explicit endpoint allow flag, and all local pre-submit gates
are clean.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_actual_submit_gate import (
    LANE_CONTROLS_PATH,
    RISK_CONTRACT_CONFIG_PATH,
    _executable_payload_artifact,
    load_latest_tiny_live_executable_payload_write_gate,
    load_latest_tiny_live_signed_request_write_gate,
    validate_signed_request_timestamp_freshness,
)
from src.app.hammer_radar.operator.tiny_live_controls_arming import (
    load_tiny_live_lane_controls,
    load_tiny_live_risk_contract,
)
from src.app.hammer_radar.operator.tiny_live_final_console import (
    load_tiny_live_final_console_records,
)
from src.app.hammer_radar.operator.tiny_live_percentage_risk_contract_fit_regeneration import (
    load_tiny_live_percentage_contract_fit_records,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_validation import (
    build_tiny_live_risk_contract_validation_summary,
)
from src.app.hammer_radar.operator.tiny_live_submit_gate_preview import (
    build_submit_gate_order_triplet_preview,
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R264_TINY_LIVE_ACTUAL_SUBMIT_AND_IMMEDIATE_RECONCILIATION"
EVENT_TYPE = "TINY_LIVE_ACTUAL_SUBMIT_RECONCILIATION"
LEDGER_FILENAME = "tiny_live_actual_submit_reconciliation.ndjson"
ALLOWED_ORDER_ENDPOINT = "/fapi/v1/order"
MAX_SIGNED_REQUEST_AGE_SECONDS = 60

LIVE_SUBMIT_CONFIRMATION_PHRASE = (
    "I CONFIRM TINY LIVE BTCUSDT 8M SHORT ACTUAL SUBMIT; USE LATEST R262B CONTRACT-FIT "
    "SIGNED TRIPLET ONLY; MAIN SELL MARKET 0.006 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; "
    "TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS."
)
DRY_PREVIEW_CONFIRMATION_PHRASE = (
    "I CONFIRM TINY LIVE R264 ACTUAL SUBMIT DRY PREVIEW ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
)

TINY_LIVE_ACTUAL_SUBMIT_RECONCILE_READY = "TINY_LIVE_ACTUAL_SUBMIT_RECONCILE_READY"
TINY_LIVE_ACTUAL_SUBMIT_DRY_PREVIEW_RECORDED = "TINY_LIVE_ACTUAL_SUBMIT_DRY_PREVIEW_RECORDED"
TINY_LIVE_ACTUAL_SUBMIT_REJECTED = "TINY_LIVE_ACTUAL_SUBMIT_REJECTED"
TINY_LIVE_ACTUAL_SUBMIT_BLOCKED = "TINY_LIVE_ACTUAL_SUBMIT_BLOCKED"
TINY_LIVE_ACTUAL_SUBMIT_EXECUTED_RECONCILED = "TINY_LIVE_ACTUAL_SUBMIT_EXECUTED_RECONCILED"
TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_CRITICAL = "TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_CRITICAL"
TINY_LIVE_ACTUAL_SUBMIT_ERROR = "TINY_LIVE_ACTUAL_SUBMIT_ERROR"

TINY_LIVE_ACTUAL_SUBMIT_READY_FOR_DRY_PREVIEW = "TINY_LIVE_ACTUAL_SUBMIT_READY_FOR_DRY_PREVIEW"
TINY_LIVE_ACTUAL_SUBMIT_DRY_PREVIEW_RECORDED_READY_FOR_OPERATOR_DECISION = (
    "TINY_LIVE_ACTUAL_SUBMIT_DRY_PREVIEW_RECORDED_READY_FOR_OPERATOR_DECISION"
)
TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_STALE_SIGNED_TRIPLET = (
    "TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_STALE_SIGNED_TRIPLET"
)
TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_MISSING_R263_ARMING = (
    "TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_MISSING_R263_ARMING"
)
TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_DUPLICATE_SUBMIT = (
    "TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_DUPLICATE_SUBMIT"
)
TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_RISK_CONTRACT = "TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_RISK_CONTRACT"
TINY_LIVE_ACTUAL_SUBMIT_REJECTED_BAD_CONFIRMATION = "TINY_LIVE_ACTUAL_SUBMIT_REJECTED_BAD_CONFIRMATION"
TINY_LIVE_ACTUAL_SUBMIT_EXECUTED_RECONCILED_ALL_THREE = (
    "TINY_LIVE_ACTUAL_SUBMIT_EXECUTED_RECONCILED_ALL_THREE"
)
TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_NEEDS_RECOVERY = (
    "TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_NEEDS_RECOVERY"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson",
    "logs/hammer_radar_forward/tiny_live_final_console.ndjson",
    "logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]

BASE_SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "external_env_file_written": False,
    "risk_contract_config_written": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "actual_submit_reconcile_gate": True,
    "hmac_signature_created": False,
    "signed_request_written": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "submit_allowed": False,
    "submit_attempted": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "binance_account_endpoint_called": False,
    "binance_exchange_info_endpoint_called": False,
    "binance_mark_price_endpoint_called": False,
    "private_binance_endpoint_called": False,
    "signed_binance_endpoint_called": False,
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "kill_switch_disabled": False,
    "live_controls_armed_by_phase": False,
    "secrets_read": False,
    "secrets_shown": False,
    "secrets_persisted": False,
    "secret_values_in_output": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
}


def build_tiny_live_actual_submit_reconciliation(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    dry_run_actual_submit_reconcile: bool = False,
    record_actual_submit_preview: bool = False,
    confirm_actual_submit_dry_preview: str | None = None,
    execute_actual_live_submit: bool = False,
    allow_binance_order_endpoint: bool = False,
    confirm_actual_live_submit: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    submit_client: Any | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    confirmation_valid = (
        confirm_actual_live_submit == LIVE_SUBMIT_CONFIRMATION_PHRASE
        if execute_actual_live_submit
        else confirm_actual_submit_dry_preview == DRY_PREVIEW_CONFIRMATION_PHRASE
        if record_actual_submit_preview
        else False
    )
    symbol, timeframe, direction, _entry_mode = _lane_parts(official_lane_key)
    try:
        r262b = load_latest_r262b_contract_fit_record(log_dir=resolved_log_dir, official_lane_key=official_lane_key)
        r263 = load_latest_r263_final_console_record(log_dir=resolved_log_dir, official_lane_key=official_lane_key)
        signed_triplet = load_latest_contract_fit_signed_triplet(log_dir=resolved_log_dir, official_lane_key=official_lane_key)
        controls = validate_r263_controls_armed(
            latest_r263_final_console=r263,
            lane_controls_path=lane_path,
            official_lane_key=official_lane_key,
        )
        triplet_shape = validate_contract_fit_triplet_shape(signed_triplet)
        risk = validate_contract_fit_risk(
            latest_r262b_contract_fit=r262b,
            risk_contract_config_path=risk_path,
            signed_triplet=signed_triplet,
            official_lane_key=official_lane_key,
        )
        freshness = validate_signed_triplet_freshness(signed_triplet=signed_triplet, now=generated_at)
        idempotency_key = build_actual_submit_idempotency_key(
            signed_triplet=signed_triplet,
            official_lane_key=official_lane_key,
        )
        prior_records = load_prior_actual_submit_records(
            log_dir=resolved_log_dir,
            idempotency_key=idempotency_key,
        )
        idempotency = validate_no_duplicate_actual_submit(
            idempotency_key=idempotency_key,
            prior_records=prior_records,
        )
        blocked_by = _build_blockers(
            r262b=r262b,
            r263=r263,
            signed_triplet=signed_triplet,
            controls=controls,
            triplet_shape=triplet_shape,
            risk=risk,
            freshness=freshness,
            idempotency=idempotency,
        )
        if execute_actual_live_submit and not allow_binance_order_endpoint:
            blocked_by = _dedupe([*blocked_by, "allow_binance_order_endpoint_flag_required"])
        if execute_actual_live_submit and not confirmation_valid:
            blocked_by = _dedupe([*blocked_by, "bad_actual_live_submit_confirmation"])
        if record_actual_submit_preview and not confirmation_valid:
            blocked_by = _dedupe([*blocked_by, "bad_actual_submit_dry_preview_confirmation"])

        submit_result = _empty_submit_result()
        reconciliation = _empty_reconciliation()
        actual_submit_executed = False
        actual_submit_reconciled = False
        actual_submit_preview_recorded = False
        partial_packet = build_partial_success_recovery_packet(partial_success_state={})

        if execute_actual_live_submit and confirmation_valid and allow_binance_order_endpoint and not blocked_by:
            client = submit_client or build_binance_futures_order_submit_client(
                execute_actual_live_submit=True,
                allow_binance_order_endpoint=allow_binance_order_endpoint,
                confirmation_valid=confirmation_valid,
            )
            submit_result = submit_exact_three_orders(client=client, signed_triplet=signed_triplet)
            reconciliation = reconcile_exact_three_order_responses(submit_result=submit_result)
            partial_state = classify_partial_success_state(submit_result=submit_result, reconciliation=reconciliation)
            partial_packet = build_partial_success_recovery_packet(partial_success_state=partial_state)
            actual_submit_executed = submit_result["attempted"]
            actual_submit_reconciled = reconciliation["attempted"] and reconciliation["all_three_reconciled"]
            if partial_state["partial_success"]:
                status = TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_CRITICAL
                overall = TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_NEEDS_RECOVERY
            elif actual_submit_reconciled:
                status = TINY_LIVE_ACTUAL_SUBMIT_EXECUTED_RECONCILED
                overall = TINY_LIVE_ACTUAL_SUBMIT_EXECUTED_RECONCILED_ALL_THREE
            else:
                status = TINY_LIVE_ACTUAL_SUBMIT_ERROR
                overall = UNKNOWN_NEEDS_MANUAL_REVIEW
        else:
            partial_state = classify_partial_success_state(submit_result=submit_result, reconciliation=reconciliation)
            if execute_actual_live_submit and not confirmation_valid:
                status = TINY_LIVE_ACTUAL_SUBMIT_REJECTED
                overall = TINY_LIVE_ACTUAL_SUBMIT_REJECTED_BAD_CONFIRMATION
            elif record_actual_submit_preview and not confirmation_valid:
                status = TINY_LIVE_ACTUAL_SUBMIT_REJECTED
                overall = TINY_LIVE_ACTUAL_SUBMIT_REJECTED_BAD_CONFIRMATION
            elif blocked_by:
                status = TINY_LIVE_ACTUAL_SUBMIT_BLOCKED
                overall = classify_tiny_live_actual_submit_status(
                    blocked_by=blocked_by,
                    recorded=False,
                    executed=False,
                    reconciled=False,
                    partial_success=False,
                )
            elif record_actual_submit_preview:
                status = TINY_LIVE_ACTUAL_SUBMIT_DRY_PREVIEW_RECORDED
                overall = TINY_LIVE_ACTUAL_SUBMIT_DRY_PREVIEW_RECORDED_READY_FOR_OPERATOR_DECISION
                actual_submit_preview_recorded = True
            else:
                status = TINY_LIVE_ACTUAL_SUBMIT_RECONCILE_READY
                overall = TINY_LIVE_ACTUAL_SUBMIT_READY_FOR_DRY_PREVIEW

        safety = _safety(
            actual_submit_executed=actual_submit_executed,
            order_placed=submit_result["all_three_submitted"] or any(
                submit_result[key] for key in ("main_submitted", "stop_submitted", "take_profit_submitted")
            ),
        )
        if not execute_actual_live_submit:
            safety["submit_allowed"] = False
        packet = build_actual_submit_preview_packet(
            status=status,
            generated_at=generated_at,
            dry_run_actual_submit_reconcile=dry_run_actual_submit_reconcile,
            record_actual_submit_preview=record_actual_submit_preview,
            execute_actual_live_submit=execute_actual_live_submit,
            allow_binance_order_endpoint=allow_binance_order_endpoint,
            confirmation_valid=confirmation_valid,
            actual_submit_preview_recorded=actual_submit_preview_recorded,
            actual_submit_executed=actual_submit_executed,
            actual_submit_reconciled=actual_submit_reconciled,
            official_lane_key=official_lane_key,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            r262b=r262b,
            r263=r263,
            signed_triplet=signed_triplet,
            controls=controls,
            triplet_shape=triplet_shape,
            risk=risk,
            freshness=freshness,
            idempotency=idempotency,
            blocked_by=blocked_by,
            submit_result=submit_result,
            reconciliation=reconciliation,
            partial_success_recovery_packet=partial_packet,
            overall=overall,
            safety=safety,
            operator_id=operator_id,
            reason=reason,
        )
        if actual_submit_preview_recorded or actual_submit_executed or status in {
            TINY_LIVE_ACTUAL_SUBMIT_REJECTED,
            TINY_LIVE_ACTUAL_SUBMIT_BLOCKED,
            TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_CRITICAL,
            TINY_LIVE_ACTUAL_SUBMIT_ERROR,
        } and (execute_actual_live_submit or record_actual_submit_preview):
            packet = append_tiny_live_actual_submit_record(
                packet,
                log_dir=resolved_log_dir,
                record_actual_submit_preview=actual_submit_preview_recorded,
                confirm_actual_submit_dry_preview=confirm_actual_submit_dry_preview,
                actual_execution_record=actual_submit_executed or execute_actual_live_submit,
            )
        return packet
    except Exception as exc:  # pragma: no cover - CLI/API hard boundary
        return _sanitize(
            {
                "status": TINY_LIVE_ACTUAL_SUBMIT_ERROR,
                "generated_at": generated_at.isoformat(),
                "dry_run_actual_submit_reconcile_requested": bool(dry_run_actual_submit_reconcile),
                "record_actual_submit_preview_requested": bool(record_actual_submit_preview),
                "execute_actual_live_submit_requested": bool(execute_actual_live_submit),
                "allow_binance_order_endpoint": bool(allow_binance_order_endpoint),
                "confirmation_valid": False,
                "actual_submit_preview_recorded": False,
                "actual_submit_executed": False,
                "actual_submit_reconciled": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "actual_submit_reconcile_gate": True,
                    "order_placed": False,
                },
                "error": exc.__class__.__name__,
                "actual_submit_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "safety": dict(BASE_SAFETY),
            }
        )


def load_latest_r262b_contract_fit_record(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_percentage_contract_fit_records(log_dir=log_dir, limit=50):
        if _record_lane(record) == official_lane_key:
            return _sanitize(record)
    return {}


def load_latest_r263_final_console_record(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_final_console_records(log_dir=log_dir, limit=50):
        if _record_lane(record) == official_lane_key:
            return _sanitize(record)
    return {}


def load_latest_contract_fit_signed_triplet(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    signed_record = load_latest_tiny_live_signed_request_write_gate(
        log_dir=log_dir,
        official_lane_key=official_lane_key,
    )
    payload_record = load_latest_tiny_live_executable_payload_write_gate(
        log_dir=log_dir,
        official_lane_key=official_lane_key,
    )
    artifact = signed_record.get("signed_request_artifact") if isinstance(signed_record.get("signed_request_artifact"), Mapping) else {}
    executable = _executable_payload_artifact(payload_record)
    triplet = build_submit_gate_order_triplet_preview(
        signed_request_artifact=artifact,
        executable_payload_artifact=executable,
    )
    return {
        "signed_record_found": bool(signed_record),
        "signed_request_artifact": artifact,
        "order_triplet": triplet,
        "signed_requests": artifact.get("signed_requests") if isinstance(artifact.get("signed_requests"), Mapping) else {},
        "signed_triplet_count": len(artifact.get("signed_requests") or {}),
        "official_lane_key": artifact.get("official_lane_key") or _record_lane(signed_record) or official_lane_key,
    }


def validate_r263_controls_armed(
    *,
    latest_r263_final_console: Mapping[str, Any],
    lane_controls_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    lane_controls = load_tiny_live_lane_controls(
        lane_controls_path=lane_controls_path,
        official_lane_key=official_lane_key,
    )
    lane = lane_controls.get("official_lane") if isinstance(lane_controls.get("official_lane"), Mapping) else {}
    choice = latest_r263_final_console.get("operator_choice_panel") if isinstance(latest_r263_final_console.get("operator_choice_panel"), Mapping) else {}
    controls_panel = latest_r263_final_console.get("controls_panel") if isinstance(latest_r263_final_console.get("controls_panel"), Mapping) else {}
    accepted = (
        lane.get("experimental_lane_acceptance_recorded") is True
        or choice.get("experimental_lane_acceptance_recorded") is True
    )
    armed = lane.get("mode") == "tiny_live" and accepted
    r263_armed = (
        latest_r263_final_console.get("final_console_controls_armed") is True
        or controls_panel.get("controls_armed") is True
        or lane.get("tiny_live_armed_by_phase") == "R263"
    )
    blocked_by: list[str] = []
    if not latest_r263_final_console:
        blocked_by.append("r263_final_console_record_missing")
    if not accepted:
        blocked_by.append("r263_experimental_lane_acceptance_missing")
    if lane.get("mode") != "tiny_live":
        blocked_by.append("lane_controls_not_armed_tiny_live")
    if not r263_armed:
        blocked_by.append("r263_controls_arming_missing")
    return {
        "valid": bool(armed and r263_armed),
        "controls_armed": bool(armed and r263_armed),
        "experimental_lane_acceptance_recorded": bool(accepted),
        "lane_control_mode": lane.get("mode"),
        "blocked_by": _dedupe(blocked_by),
    }


def validate_contract_fit_triplet_shape(signed_triplet: Mapping[str, Any]) -> dict[str, Any]:
    triplet = signed_triplet.get("order_triplet") if isinstance(signed_triplet.get("order_triplet"), Mapping) else {}
    main = triplet.get("main_order") if isinstance(triplet.get("main_order"), Mapping) else {}
    stop = triplet.get("stop_order") if isinstance(triplet.get("stop_order"), Mapping) else {}
    take = triplet.get("take_profit_order") if isinstance(triplet.get("take_profit_order"), Mapping) else {}
    signed_requests = signed_triplet.get("signed_requests") if isinstance(signed_triplet.get("signed_requests"), Mapping) else {}
    exact_three = len(signed_requests) == 3 and all(key in signed_requests for key in _ORDER_KEYS)
    main_valid = _upper(main.get("side")) == "SELL" and _upper(main.get("type")) == "MARKET" and _qty(main.get("quantity")) == 0.006
    stop_valid = _exit_valid(stop, "STOP_MARKET")
    take_valid = _exit_valid(take, "TAKE_PROFIT_MARKET")
    reduce_only = stop.get("reduceOnly") is True and take.get("reduceOnly") is True
    same_symbol = all(_order_symbol(order) == "BTCUSDT" for order in (main, stop, take))
    endpoint_ok = all(
        (signed_requests.get(key) or {}).get("endpoint") == ALLOWED_ORDER_ENDPOINT
        for key in _ORDER_KEYS
    )
    return {
        "valid": bool(exact_three and main_valid and stop_valid and take_valid and reduce_only and same_symbol and endpoint_ok),
        "signed_triplet_count": len(signed_requests),
        "exact_three_orders": bool(exact_three),
        "main_order_valid": bool(main_valid),
        "stop_order_valid": bool(stop_valid),
        "take_profit_order_valid": bool(take_valid),
        "reduce_only_exits": bool(reduce_only),
        "same_symbol_lane": bool(same_symbol),
        "endpoint_allowlist_valid": bool(endpoint_ok),
        "blocked_by": _triplet_blockers(exact_three, main_valid, stop_valid, take_valid, reduce_only, same_symbol, endpoint_ok),
    }


def validate_contract_fit_risk(
    *,
    latest_r262b_contract_fit: Mapping[str, Any],
    risk_contract_config_path: str | Path | None = None,
    signed_triplet: Mapping[str, Any] | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    validation = latest_r262b_contract_fit.get("output_validation") if isinstance(latest_r262b_contract_fit.get("output_validation"), Mapping) else {}
    sizing = latest_r262b_contract_fit.get("contract_fit_sizing_plan") if isinstance(latest_r262b_contract_fit.get("contract_fit_sizing_plan"), Mapping) else {}
    contract = load_tiny_live_risk_contract(
        risk_contract_config_path=risk_contract_config_path,
        official_lane_key=official_lane_key,
    )
    triplet = signed_triplet.get("order_triplet") if isinstance((signed_triplet or {}).get("order_triplet"), Mapping) else {}
    main = triplet.get("main_order") if isinstance(triplet.get("main_order"), Mapping) else {}
    candidate_qty = _qty(main.get("quantity"))
    reference_price = _num(triplet.get("entry_reference_price"))
    candidate_notional = round(candidate_qty * reference_price, 8) if candidate_qty is not None and reference_price is not None else sizing.get("candidate_notional_usdt")
    risk_summary = build_tiny_live_risk_contract_validation_summary(
        risk_contract=contract,
        candidate_qty=candidate_qty or sizing.get("candidate_qty"),
        candidate_reference_price=reference_price,
        candidate_notional_usdt=candidate_notional,
        candidate_estimated_loss_usdt=sizing.get("candidate_estimated_loss_usdt"),
        require_live_execution_enabled=True,
    )
    config_valid = risk_summary.get("valid") is True
    r262b_valid = (
        bool(latest_r262b_contract_fit)
        and validation.get("valid") is True
        and validation.get("risk_contract_valid_after") is True
        and sizing.get("fits_max_notional") is True
        and sizing.get("fits_max_loss") is True
        and _qty(sizing.get("candidate_qty")) == 0.006
    )
    blocked_by: list[str] = []
    if not latest_r262b_contract_fit:
        blocked_by.append("r262b_contract_fit_missing")
    if not r262b_valid:
        blocked_by.append("r262b_contract_fit_invalid")
    if not config_valid:
        blocked_by.append("risk_contract_config_invalid")
    return {
        "valid": bool(r262b_valid and config_valid),
        "risk_contract_valid": bool(r262b_valid and config_valid),
        "r262b_contract_fit_valid": bool(r262b_valid),
        "risk_contract_config_valid": bool(config_valid),
        "risk_contract_interpretation": risk_summary,
        "blocked_by": _dedupe(blocked_by),
    }


def validate_signed_triplet_freshness(
    *, signed_triplet: Mapping[str, Any], now: datetime | None = None
) -> dict[str, Any]:
    artifact = signed_triplet.get("signed_request_artifact") if isinstance(signed_triplet.get("signed_request_artifact"), Mapping) else {}
    base = validate_signed_request_timestamp_freshness(
        signed_request_artifact=artifact,
        now=now,
        max_allowed_age_seconds=MAX_SIGNED_REQUEST_AGE_SECONDS,
    )
    return {
        "signed_triplet_fresh": base.get("fresh_enough_for_real_submit") is True,
        "signed_triplet_age_seconds": base.get("signed_request_age_seconds"),
        "max_allowed_age_seconds": base.get("max_allowed_age_seconds"),
        "requires_regeneration": base.get("requires_regeneration") is True,
        "timestamp_present": base.get("timestamp_present") is True,
    }


def build_actual_submit_idempotency_key(
    *, signed_triplet: Mapping[str, Any], official_lane_key: str = OFFICIAL_LANE_KEY
) -> str:
    artifact = signed_triplet.get("signed_request_artifact") if isinstance(signed_triplet.get("signed_request_artifact"), Mapping) else {}
    material = {
        "artifact_id": artifact.get("signed_request_artifact_id") or artifact.get("record_id"),
        "lane": artifact.get("official_lane_key") or official_lane_key,
        "signatures": [
            (artifact.get("signed_requests") or {}).get(key, {}).get("signature")
            for key in _ORDER_KEYS
        ],
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return f"{official_lane_key}|R264|{digest}"


def load_prior_actual_submit_records(
    *, log_dir: str | Path | None = None, idempotency_key: str | None = None
) -> list[dict[str, Any]]:
    records = load_tiny_live_actual_submit_records(log_dir=log_dir, limit=0)
    if not idempotency_key:
        return records
    return [
        record
        for record in records
        if (record.get("idempotency") if isinstance(record.get("idempotency"), Mapping) else {}).get(
            "actual_submit_idempotency_key"
        )
        == idempotency_key
    ]


def validate_no_duplicate_actual_submit(
    *, idempotency_key: str, prior_records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    prior_live = any(record.get("actual_submit_executed") is True for record in prior_records)
    return {
        "actual_submit_idempotency_key": idempotency_key,
        "prior_live_submit_found": bool(prior_live),
        "prior_records_count": len(prior_records),
        "idempotency_clean": not prior_live,
    }


def build_actual_submit_preview_packet(**kwargs: Any) -> dict[str, Any]:
    signed_triplet = kwargs["signed_triplet"]
    triplet_shape = kwargs["triplet_shape"]
    submit_result = kwargs["submit_result"]
    reconciliation = kwargs["reconciliation"]
    blocked_by = list(kwargs["blocked_by"])
    matrix = {
        "r262b_valid": kwargs["risk"].get("risk_contract_valid") is True,
        "r263_armed": kwargs["controls"].get("controls_armed") is True,
        "signed_triplet_fresh": kwargs["freshness"].get("signed_triplet_fresh") is True,
        "idempotency_clean": kwargs["idempotency"].get("idempotency_clean") is True,
        "exact_confirmation": kwargs["confirmation_valid"],
        "allow_order_endpoint": kwargs["allow_binance_order_endpoint"],
        "executed": kwargs["actual_submit_executed"],
        "reconciled": kwargs["actual_submit_reconciled"],
        "partial_success": reconciliation.get("partial_success") is True,
        "blocked_by": blocked_by,
    }
    go_packet = _go_no_go_packet(
        matrix=matrix,
        blocked_by=blocked_by,
        record_actual_submit_preview=kwargs["record_actual_submit_preview"],
        execute_actual_live_submit=kwargs["execute_actual_live_submit"],
    )
    return _sanitize(
        {
            "status": kwargs["status"],
            "generated_at": kwargs["generated_at"].isoformat(),
            "dry_run_actual_submit_reconcile_requested": bool(kwargs["dry_run_actual_submit_reconcile"]),
            "record_actual_submit_preview_requested": bool(kwargs["record_actual_submit_preview"]),
            "execute_actual_live_submit_requested": bool(kwargs["execute_actual_live_submit"]),
            "allow_binance_order_endpoint": bool(kwargs["allow_binance_order_endpoint"]),
            "confirmation_valid": bool(kwargs["confirmation_valid"]),
            "actual_submit_preview_recorded": bool(kwargs["actual_submit_preview_recorded"]),
            "actual_submit_executed": bool(kwargs["actual_submit_executed"]),
            "actual_submit_reconciled": bool(kwargs["actual_submit_reconciled"]),
            "operator_intent": {
                "operator_id": str(kwargs["operator_id"] or "local_operator"),
                "reason": str(kwargs["reason"] or ""),
                "source_phase": "R264",
            },
            "target_scope": {
                "official_lane_key": kwargs["official_lane_key"],
                "symbol": kwargs["symbol"],
                "timeframe": kwargs["timeframe"],
                "direction": kwargs["direction"],
                "actual_submit_reconcile_gate": True,
                "order_placed": submit_result["all_three_submitted"]
                or any(submit_result[key] for key in ("main_submitted", "stop_submitted", "take_profit_submitted")),
            },
            "input_summary": {
                "r262b_contract_fit_found": bool(kwargs["r262b"]),
                "r262b_contract_fit_valid": kwargs["risk"].get("r262b_contract_fit_valid") is True,
                "r263_final_console_found": bool(kwargs["r263"]),
                "r263_controls_armed": kwargs["controls"].get("controls_armed") is True,
                "signed_triplet_found": bool(signed_triplet.get("signed_record_found")),
                "signed_triplet_count": signed_triplet.get("signed_triplet_count"),
            },
            "pre_submit_validation": {
                "valid": not blocked_by,
                "blocked_by": blocked_by,
                "signed_triplet_fresh": kwargs["freshness"].get("signed_triplet_fresh") is True,
                "signed_triplet_age_seconds": kwargs["freshness"].get("signed_triplet_age_seconds"),
                "risk_contract_valid": kwargs["risk"].get("risk_contract_valid") is True,
                "risk_contract_interpretation": kwargs["risk"].get("risk_contract_interpretation") or {},
                "controls_armed": kwargs["controls"].get("controls_armed") is True,
                "experimental_lane_acceptance_recorded": kwargs["controls"].get("experimental_lane_acceptance_recorded") is True,
                "duplicate_submit_found": kwargs["idempotency"].get("prior_live_submit_found") is True,
                "exact_three_orders": triplet_shape.get("exact_three_orders") is True,
                "main_order_valid": triplet_shape.get("main_order_valid") is True,
                "stop_order_valid": triplet_shape.get("stop_order_valid") is True,
                "take_profit_order_valid": triplet_shape.get("take_profit_order_valid") is True,
                "reduce_only_exits": triplet_shape.get("reduce_only_exits") is True,
            },
            "order_triplet_summary": _order_triplet_summary(signed_triplet),
            "idempotency": {
                "actual_submit_idempotency_key": kwargs["idempotency"].get("actual_submit_idempotency_key"),
                "prior_live_submit_found": kwargs["idempotency"].get("prior_live_submit_found") is True,
                "prior_records_count": kwargs["idempotency"].get("prior_records_count", 0),
            },
            "submit_plan": {
                "will_call_binance_order_endpoint": bool(kwargs["execute_actual_live_submit"] and kwargs["allow_binance_order_endpoint"] and kwargs["confirmation_valid"] and not blocked_by),
                "will_place_exactly_three_orders": bool(not blocked_by and triplet_shape.get("exact_three_orders") is True and kwargs["execute_actual_live_submit"]),
                "will_place_main_market_order": bool(not blocked_by and kwargs["execute_actual_live_submit"]),
                "will_place_reduce_only_stop": bool(not blocked_by and kwargs["execute_actual_live_submit"]),
                "will_place_reduce_only_take_profit": bool(not blocked_by and kwargs["execute_actual_live_submit"]),
                "will_place_any_extra_orders": False,
            },
            "submit_result": submit_result,
            "reconciliation": reconciliation,
            "partial_success_recovery_packet": kwargs["partial_success_recovery_packet"],
            "actual_submit_go_no_go_packet": go_packet,
            "actual_submit_matrix": matrix,
            "actual_submit_overall_status": kwargs["overall"],
            "recommended_next_operator_move": _recommended_next_operator_move(go_packet, kwargs["overall"]),
            "recommended_next_engineering_move": _recommended_next_engineering_move(go_packet, kwargs["overall"]),
            "do_not_run_yet": [
                "duplicate actual submit",
                "actual submit with stale signed triplet",
                "actual submit without R263 arming",
                "actual submit without exact phrase",
                "actual submit if prior live submit exists",
            ],
            "safety": kwargs["safety"],
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )


def build_binance_futures_order_submit_client(
    *, execute_actual_live_submit: bool, allow_binance_order_endpoint: bool, confirmation_valid: bool
) -> Any:
    if not (execute_actual_live_submit and allow_binance_order_endpoint and confirmation_valid):
        return FakeBinanceFuturesOrderSubmitClient()
    return BinanceFuturesOrderSubmitClient()


def submit_exact_three_orders(*, client: Any, signed_triplet: Mapping[str, Any]) -> dict[str, Any]:
    signed_requests = signed_triplet.get("signed_requests") if isinstance(signed_triplet.get("signed_requests"), Mapping) else {}
    responses: list[dict[str, Any]] = []
    errors: list[str] = []
    submitted = {"main_submitted": False, "stop_submitted": False, "take_profit_submitted": False}
    for key, output_key in zip(_ORDER_KEYS, submitted, strict=True):
        request = signed_requests.get(key) if isinstance(signed_requests.get(key), Mapping) else {}
        if request.get("endpoint") != ALLOWED_ORDER_ENDPOINT:
            errors.append(f"{key}_endpoint_not_allowed")
            break
        try:
            response = _sanitize(client.submit_order(request, role=key))
            responses.append({"role": key, "response": response})
            success = _response_success(response)
            submitted[output_key] = success
            if not success:
                errors.append(f"{key}_submit_not_accepted")
                break
        except Exception as exc:  # pragma: no cover - defensive real client boundary
            errors.append(f"{key}_submit_error_{exc.__class__.__name__}")
            break
    order_ids = [_response_order_id(item.get("response") or {}) for item in responses]
    client_ids = [_response_client_order_id(item.get("response") or {}) for item in responses]
    return {
        "attempted": True,
        **submitted,
        "all_three_submitted": all(submitted.values()),
        "order_ids": [item for item in order_ids if item is not None],
        "client_order_ids": [item for item in client_ids if item is not None],
        "errors": errors,
        "responses": responses,
    }


def reconcile_exact_three_order_responses(*, submit_result: Mapping[str, Any]) -> dict[str, Any]:
    roles = {item.get("role"): item.get("response") for item in submit_result.get("responses") or [] if isinstance(item, Mapping)}
    statuses = {role: _response_status(response if isinstance(response, Mapping) else {}) for role, response in roles.items()}
    all_three = (
        submit_result.get("all_three_submitted") is True
        and all(statuses.get(role) in {"NEW", "FILLED", "PARTIALLY_FILLED", "ACCEPTED", "MOCK_ACCEPTED"} for role in _ORDER_KEYS)
    )
    partial = submit_result.get("attempted") is True and not all_three and any(
        submit_result.get(key) is True for key in ("main_submitted", "stop_submitted", "take_profit_submitted")
    )
    return {
        "attempted": submit_result.get("attempted") is True,
        "all_three_reconciled": bool(all_three),
        "main_order_status": statuses.get("main_order"),
        "stop_order_status": statuses.get("stop_order"),
        "take_profit_order_status": statuses.get("take_profit_order"),
        "partial_success": bool(partial),
        "critical": bool(partial),
        "recovery_required": bool(partial),
    }


def classify_partial_success_state(
    *, submit_result: Mapping[str, Any], reconciliation: Mapping[str, Any]
) -> dict[str, Any]:
    partial = reconciliation.get("partial_success") is True
    return {
        "partial_success": bool(partial),
        "critical": bool(partial),
        "recovery_required": bool(partial),
        "reason": "one_or_two_orders_submitted_without_full_triplet_reconciliation" if partial else None,
    }


def build_partial_success_recovery_packet(*, partial_success_state: Mapping[str, Any]) -> dict[str, Any]:
    required = partial_success_state.get("partial_success") is True
    return {
        "required": bool(required),
        "reason": partial_success_state.get("reason") if required else None,
        "operator_action": "STOP; inspect Binance position/orders manually; do not resubmit main; run R265 recovery." if required else None,
        "do_not_resubmit_main": bool(required),
        "suggested_next_phase": "R265_TINY_LIVE_POST_LIVE_HARDENING_AND_RECOVERY",
    }


def append_tiny_live_actual_submit_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    record_actual_submit_preview: bool = False,
    confirm_actual_submit_dry_preview: str | None = None,
    actual_execution_record: bool = False,
) -> dict[str, Any]:
    if record_actual_submit_preview and confirm_actual_submit_dry_preview != DRY_PREVIEW_CONFIRMATION_PHRASE:
        raise ValueError("bad_r264_actual_submit_dry_preview_confirmation")
    path = tiny_live_actual_submit_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "actual_submit_reconciliation_record_id": record.get("actual_submit_reconciliation_record_id")
            or f"r264_actual_submit_reconciliation_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "actual_execution_record": bool(actual_execution_record),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_actual_submit_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_actual_submit_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def classify_tiny_live_actual_submit_status(
    *,
    blocked_by: Sequence[str],
    recorded: bool,
    executed: bool,
    reconciled: bool,
    partial_success: bool,
) -> str:
    if partial_success:
        return TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_NEEDS_RECOVERY
    if executed and reconciled:
        return TINY_LIVE_ACTUAL_SUBMIT_EXECUTED_RECONCILED_ALL_THREE
    if recorded:
        return TINY_LIVE_ACTUAL_SUBMIT_DRY_PREVIEW_RECORDED_READY_FOR_OPERATOR_DECISION
    blockers = set(blocked_by)
    if "signed_triplet_stale" in blockers:
        return TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_STALE_SIGNED_TRIPLET
    if blockers.intersection({"r263_final_console_record_missing", "r263_experimental_lane_acceptance_missing", "lane_controls_not_armed_tiny_live", "r263_controls_arming_missing"}):
        return TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_MISSING_R263_ARMING
    if "prior_live_submit_exists" in blockers:
        return TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_DUPLICATE_SUBMIT
    if blockers.intersection({"r262b_contract_fit_invalid", "risk_contract_config_invalid", "r262b_contract_fit_missing"}):
        return TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_RISK_CONTRACT
    return TINY_LIVE_ACTUAL_SUBMIT_READY_FOR_DRY_PREVIEW if not blockers else UNKNOWN_NEEDS_MANUAL_REVIEW


class FakeBinanceFuturesOrderSubmitClient:
    def __init__(self, responses: Sequence[Mapping[str, Any]] | None = None) -> None:
        self.responses = list(responses or [])
        self.requests: list[dict[str, Any]] = []

    def submit_order(self, request: Mapping[str, Any], *, role: str | None = None) -> dict[str, Any]:
        self.requests.append(_sanitize(dict(request)))
        if self.responses:
            return dict(self.responses.pop(0))
        return {"status": "MOCK_ACCEPTED", "orderId": len(self.requests), "clientOrderId": role or len(self.requests)}


class BinanceFuturesOrderSubmitClient:
    def submit_order(self, request: Mapping[str, Any], *, role: str | None = None) -> dict[str, Any]:
        if request.get("endpoint") != ALLOWED_ORDER_ENDPOINT:
            raise ValueError("only_binance_futures_order_endpoint_allowed")
        url = f"{str(request.get('base_url') or 'https://fapi.binance.com').rstrip()}{ALLOWED_ORDER_ENDPOINT}"
        query = str(request.get("query_string") or "")
        headers = dict(request.get("headers") or {})
        http_request = urllib.request.Request(url, data=query.encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(http_request, timeout=10) as response:  # noqa: S310 - explicit R264 live gate
            body = response.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            return {
                "status_code": response.status,
                "body": payload,
                "endpoint": ALLOWED_ORDER_ENDPOINT,
                "network_used": True,
                "order_placed": True,
                "real_order_placed": True,
                "exchange_order_id": payload.get("orderId"),
                "client_order_id": payload.get("clientOrderId"),
                "status": payload.get("status") or "ACCEPTED",
            }


def tiny_live_actual_submit_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_actual_submit_reconciliation_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


_ORDER_KEYS = ("main_order", "stop_order", "take_profit_order")


def _build_blockers(**kwargs: Any) -> list[str]:
    blockers: list[str] = []
    if not kwargs["r262b"]:
        blockers.append("r262b_contract_fit_missing")
    if not kwargs["r263"]:
        blockers.append("r263_final_console_record_missing")
    if not kwargs["signed_triplet"].get("signed_record_found"):
        blockers.append("signed_triplet_missing")
    for key in ("controls", "triplet_shape", "risk"):
        if kwargs[key].get("valid") is not True:
            blockers.extend(str(item) for item in kwargs[key].get("blocked_by") or [f"{key}_invalid"])
    if kwargs["freshness"].get("signed_triplet_fresh") is not True:
        blockers.append("signed_triplet_stale")
    if kwargs["idempotency"].get("idempotency_clean") is not True:
        blockers.append("prior_live_submit_exists")
    return _dedupe(blockers)


def _empty_submit_result() -> dict[str, Any]:
    return {
        "attempted": False,
        "main_submitted": False,
        "stop_submitted": False,
        "take_profit_submitted": False,
        "all_three_submitted": False,
        "order_ids": [],
        "client_order_ids": [],
        "errors": [],
    }


def _empty_reconciliation() -> dict[str, Any]:
    return {
        "attempted": False,
        "all_three_reconciled": False,
        "main_order_status": None,
        "stop_order_status": None,
        "take_profit_order_status": None,
        "partial_success": False,
        "critical": False,
        "recovery_required": False,
    }


def _order_triplet_summary(signed_triplet: Mapping[str, Any]) -> dict[str, Any]:
    triplet = signed_triplet.get("order_triplet") if isinstance(signed_triplet.get("order_triplet"), Mapping) else {}
    main = triplet.get("main_order") if isinstance(triplet.get("main_order"), Mapping) else {}
    stop = triplet.get("stop_order") if isinstance(triplet.get("stop_order"), Mapping) else {}
    take = triplet.get("take_profit_order") if isinstance(triplet.get("take_profit_order"), Mapping) else {}
    return {
        "main": {"symbol": _order_symbol(main), "side": main.get("side"), "type": main.get("type"), "quantity": _qty_string(main.get("quantity"))},
        "stop": {
            "symbol": _order_symbol(stop),
            "side": stop.get("side"),
            "type": stop.get("type"),
            "reduce_only": stop.get("reduceOnly") is True,
            "stop_price": stop.get("stopPrice"),
        },
        "take_profit": {
            "symbol": _order_symbol(take),
            "side": take.get("side"),
            "type": take.get("type"),
            "reduce_only": take.get("reduceOnly") is True,
            "stop_price": take.get("stopPrice"),
        },
    }


def _go_no_go_packet(
    *, matrix: Mapping[str, Any], blocked_by: Sequence[str], record_actual_submit_preview: bool, execute_actual_live_submit: bool
) -> dict[str, Any]:
    if "signed_triplet_stale" in blocked_by:
        step = "REFRESH_R262B"
    elif any(item.startswith("r263") or item == "lane_controls_not_armed_tiny_live" for item in blocked_by):
        step = "REARM_R263_RUNTIME"
    elif "prior_live_submit_exists" in blocked_by:
        step = "WAIT"
    elif blocked_by:
        step = "FIX_BLOCKER"
    elif not record_actual_submit_preview and not execute_actual_live_submit:
        step = "RUN_DRY_PREVIEW"
    else:
        step = "OPERATOR_DECISION"
    return {
        "go_for_actual_live_submit_now": not blocked_by and matrix.get("signed_triplet_fresh") is True and matrix.get("r263_armed") is True,
        "operator_should_submit_now": bool(execute_actual_live_submit and not blocked_by),
        "next_required_step": step,
    }


def _recommended_next_operator_move(go_packet: Mapping[str, Any], overall: str) -> str:
    if overall == TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_NEEDS_RECOVERY:
        return "Stop and run R265 recovery; do not resubmit the main order."
    if go_packet.get("next_required_step") == "RUN_DRY_PREVIEW":
        return "Run the R264 dry preview record command with the exact dry phrase."
    if go_packet.get("next_required_step") == "OPERATOR_DECISION":
        return "Review the R264 packet and decide outside Codex whether to run the exact live command."
    return str(go_packet.get("next_required_step") or "FIX_BLOCKER")


def _recommended_next_engineering_move(go_packet: Mapping[str, Any], overall: str) -> str:
    if overall == TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_NEEDS_RECOVERY:
        return "R265_TINY_LIVE_POST_LIVE_HARDENING_AND_RECOVERY"
    return "Keep R264 gate under test; no additional live automation."


def _safety(*, actual_submit_executed: bool, order_placed: bool) -> dict[str, Any]:
    return {
        **BASE_SAFETY,
        "hmac_signature_created": False,
        "submit_allowed": bool(actual_submit_executed),
        "submit_attempted": bool(actual_submit_executed),
        "order_placed": bool(order_placed),
        "real_order_placed": bool(order_placed),
        "execution_attempted": bool(actual_submit_executed),
        "binance_order_endpoint_called": bool(actual_submit_executed),
        "private_binance_endpoint_called": bool(actual_submit_executed),
        "signed_binance_endpoint_called": bool(actual_submit_executed),
        "network_allowed": bool(actual_submit_executed),
        "secrets_read": bool(actual_submit_executed),
    }


def _triplet_blockers(*flags: bool) -> list[str]:
    names = [
        "order_count_not_three",
        "main_order_shape_invalid",
        "stop_order_shape_invalid",
        "take_profit_order_shape_invalid",
        "reduce_only_exit_missing",
        "symbol_lane_mismatch",
        "endpoint_allowlist_invalid",
    ]
    return [name for flag, name in zip(flags, names, strict=True) if not flag]


def _exit_valid(order: Mapping[str, Any], expected_type: str) -> bool:
    return _upper(order.get("side")) == "BUY" and _upper(order.get("type")) == expected_type and _qty(order.get("quantity")) == 0.006


def _order_symbol(order: Mapping[str, Any]) -> str | None:
    return order.get("symbol") or "BTCUSDT"


def _response_success(response: Mapping[str, Any]) -> bool:
    body = response.get("body") if isinstance(response.get("body"), Mapping) else {}
    status = str(response.get("status") or body.get("status") or "").upper()
    return bool(response.get("order_placed") is True or response.get("orderId") or response.get("exchange_order_id") or status in {"NEW", "FILLED", "ACCEPTED", "MOCK_ACCEPTED"})


def _response_order_id(response: Mapping[str, Any]) -> Any:
    body = response.get("body") if isinstance(response.get("body"), Mapping) else {}
    return response.get("orderId") or response.get("exchange_order_id") or body.get("orderId")


def _response_client_order_id(response: Mapping[str, Any]) -> Any:
    body = response.get("body") if isinstance(response.get("body"), Mapping) else {}
    return response.get("clientOrderId") or response.get("client_order_id") or body.get("clientOrderId")


def _response_status(response: Mapping[str, Any]) -> str | None:
    body = response.get("body") if isinstance(response.get("body"), Mapping) else {}
    value = response.get("status") or body.get("status")
    return str(value).upper() if value is not None else None


def _qty(value: Any) -> float | None:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _qty_string(value: Any) -> str | None:
    qty = _qty(value)
    if qty is None:
        return None
    return f"{qty:.3f}".rstrip("0").rstrip(".") if qty != 0.006 else "0.006"


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _upper(value: Any) -> str:
    return str(value or "").upper()


def _record_lane(record: Mapping[str, Any]) -> str | None:
    scope = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    return record.get("official_lane_key") or scope.get("official_lane_key")


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key).split("|")
    padded = [*parts, "", "", "", ""]
    return padded[0], padded[1], padded[2], padded[3]


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
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            lowered = key_str.lower()
            if lowered in {"signature", "x-mbx-apikey", "api_key", "api_secret", "secret"}:
                sanitized[key_str] = "<hidden>" if item else None
            elif lowered in {"headers"} and isinstance(item, Mapping):
                sanitized[key_str] = {
                    str(header_key): "<present>" if str(header_key).lower() == "x-mbx-apikey" else _sanitize(header_value)
                    for header_key, header_value in item.items()
                }
            elif lowered in {"query_string", "query_string_without_signature"}:
                sanitized[key_str] = _redact_query_string(str(item or ""))
            else:
                sanitized[key_str] = _sanitize(item)
        return sanitized
    if isinstance(value, list | tuple):
        return [_sanitize(item) for item in value]
    return value


def _redact_query_string(value: str) -> str:
    if not value:
        return value
    parts: list[str] = []
    for item in value.split("&"):
        if "=" not in item:
            parts.append(item)
            continue
        key, raw = item.split("=", 1)
        if key.lower() in {"signature", "apikey", "api_key", "secret", "api_secret"}:
            parts.append(f"{key}=<hidden>")
        else:
            parts.append(f"{key}={raw}")
    return "&".join(parts)
