"""R246 tiny-live refreshed order payload write gate.

This gate writes only a local, refreshed, non-executable payload artifact after
the exact R246 confirmation phrase. It never creates executable payloads,
signs requests, calls Binance/network endpoints, places orders, mutates
configs/env/lane controls, or disables the kill switch.
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
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_order_payload_refresh_preview import (
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_CLEARS_PRECISION_AND_MIN_NOTIONAL,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_READY,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDED,
    load_latest_tiny_live_binance_readonly_precision_mark_price_gate as _load_latest_r242,
    load_latest_tiny_live_leverage_notional_risk_contract_write_gate as _load_latest_r244,
    load_latest_tiny_live_order_payload_write_gate as _load_latest_r240,
    load_tiny_live_order_payload_refresh_preview_records,
    validate_refreshed_payload_preview,
)

TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_READY = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_READY"
TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_REJECTED = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_REJECTED"
TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_WRITTEN = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_WRITTEN"
TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_BLOCKED = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_BLOCKED"
TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_ERROR = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_ERROR"

TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_READY_FOR_CONFIRMATION = (
    "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_READY_FOR_CONFIRMATION"
)
TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITTEN_EXECUTABLE_PREVIEW_REQUIRED = (
    "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITTEN_EXECUTABLE_PREVIEW_REQUIRED"
)
TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_BLOCKED_BY_R245 = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_BLOCKED_BY_R245"
TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_BLOCKED_BY_VALIDATION = (
    "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_BLOCKED_BY_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE"
LEDGER_FILENAME = "tiny_live_order_payload_refresh_write_gate.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R246_TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE"
ORDER_PAYLOAD_VERSION = "tiny_live_refreshed_non_executable_payload_v1"
CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_PHRASE = (
    "I CONFIRM TINY LIVE ORDER PAYLOAD REFRESH WRITE GATE ONLY; "
    "WRITE NON-EXECUTABLE PAYLOAD ARTIFACT ONLY; NO ORDER; NO BINANCE CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "order_payload_written": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "submit_allowed": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "binance_account_endpoint_called": False,
    "binance_exchange_info_endpoint_called": False,
    "binance_mark_price_endpoint_called": False,
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "kill_switch_disabled": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
    "payload_refresh_write_gate_only": True,
    "non_executable_artifact_only": True,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_order_payload_refresh_preview.ndjson",
    "logs/hammer_radar_forward/tiny_live_leverage_notional_risk_contract_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_order_payload_write_gate.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_order_payload_refresh_write_gate(
    *,
    log_dir: str | Path | None = None,
    write_payload_refresh: bool = False,
    confirm_tiny_live_order_payload_refresh_write: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_order_payload_refresh_write
        == CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_PHRASE
    )
    symbol, _, direction, _ = _lane_parts(official_lane_key)
    try:
        latest_r245 = load_latest_tiny_live_order_payload_refresh_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r244 = load_latest_tiny_live_leverage_notional_risk_contract_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r242 = load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r240 = load_latest_tiny_live_order_payload_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        input_summary = _build_input_summary(latest_r245=latest_r245, latest_r244=latest_r244, latest_r242=latest_r242)
        artifact = build_refreshed_non_executable_payload_artifact(
            latest_r245=latest_r245,
            latest_r244=latest_r244,
            latest_r242=latest_r242,
            latest_r240=latest_r240,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        validation = validate_refreshed_non_executable_payload_artifact(artifact)
        blocked_by = _blocked_by(input_summary=input_summary, validation=validation)
        preview = build_payload_refresh_write_preview(
            proposed_refreshed_payload=artifact,
            payload_refresh_valid=validation["valid"],
            blocked_by=blocked_by,
            official_lane_key=official_lane_key,
        )

        written = False
        if write_payload_refresh and not confirmation_valid:
            status = TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_REJECTED
            overall = TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_REJECTED_BAD_CONFIRMATION
        elif blocked_by:
            status = TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_BLOCKED
            overall = classify_tiny_live_order_payload_refresh_write_status(
                input_summary=input_summary,
                payload_refresh_validation=validation,
                payload_refresh_written=False,
                rejected_bad_confirmation=False,
            )
        elif write_payload_refresh and confirmation_valid:
            write_payload_refresh_if_confirmed(
                payload_refresh=artifact,
                confirm_tiny_live_order_payload_refresh_write=confirm_tiny_live_order_payload_refresh_write,
                log_dir=resolved_log_dir,
            )
            written = True
            status = TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_WRITTEN
            overall = TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITTEN_EXECUTABLE_PREVIEW_REQUIRED
        else:
            status = TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_READY
            overall = TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_READY_FOR_CONFIRMATION

        post_write = build_post_write_payload_refresh_verification(
            payload_refresh=artifact,
            payload_refresh_written=written,
            log_dir=resolved_log_dir,
        )
        matrix = build_payload_refresh_write_gate_matrix(
            r245_refresh_preview_ready=input_summary["r245_refresh_preview_valid"],
            payload_refresh_valid=validation["valid"],
            payload_refresh_write_confirmed=bool(write_payload_refresh and confirmation_valid),
            payload_refresh_written=written,
            blocked_by=blocked_by,
        )
        operator_packet = build_operator_payload_refresh_write_packet(matrix, write_requested=write_payload_refresh)
        safety = dict(SAFETY)
        if written:
            safety["order_payload_written"] = True
            safety["order_payload_created"] = True
        return _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "payload_refresh_written": written,
                "write_payload_refresh_requested": bool(write_payload_refresh),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "direction": direction,
                    "payload_refresh_write_gate_only": True,
                    "non_executable_artifact_only": True,
                    "executable_payload_created": False,
                    "signed_order_request_created": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "payload_refresh_write_preview": preview,
                "payload_refresh_validation": validation,
                "post_write_verification": post_write,
                "payload_refresh_write_gate_matrix": matrix,
                "operator_payload_refresh_write_packet": operator_packet,
                "recommended_next_operator_move": _recommended_next_operator_move(matrix, write_requested=write_payload_refresh),
                "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
                "payload_refresh_write_overall_status": overall,
                "do_not_run_yet": _do_not_run_yet(),
                "safety": safety,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_payload_refresh_write_gate_matrix(
            r245_refresh_preview_ready=False,
            payload_refresh_valid=False,
            payload_refresh_write_confirmed=False,
            payload_refresh_written=False,
            blocked_by=["payload_refresh_write_gate_error"],
        )
        return _sanitize(
            {
                "status": TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "payload_refresh_written": False,
                "write_payload_refresh_requested": bool(write_payload_refresh),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "direction": direction,
                    "payload_refresh_write_gate_only": True,
                    "non_executable_artifact_only": True,
                    "executable_payload_created": False,
                    "signed_order_request_created": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": _empty_input_summary(),
                "payload_refresh_write_preview": _empty_payload_refresh_write_preview(official_lane_key),
                "payload_refresh_validation": {"valid": False, "errors": ["payload_refresh_write_gate_error"], "warnings": []},
                "post_write_verification": _empty_post_write_verification(),
                "payload_refresh_write_gate_matrix": matrix,
                "operator_payload_refresh_write_packet": build_operator_payload_refresh_write_packet(
                    matrix,
                    write_requested=write_payload_refresh,
                ),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R246 payload refresh write gate error before executable payload preview.",
                "payload_refresh_write_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_order_payload_refresh_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_order_payload_refresh_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        preview = (
            record.get("refreshed_non_executable_payload_preview")
            if isinstance(record.get("refreshed_non_executable_payload_preview"), Mapping)
            else {}
        )
        matrix = (
            record.get("payload_refresh_preview_gate_matrix")
            if isinstance(record.get("payload_refresh_preview_gate_matrix"), Mapping)
            else {}
        )
        quantity = (
            record.get("refreshed_quantity_preview")
            if isinstance(record.get("refreshed_quantity_preview"), Mapping)
            else {}
        )
        if (
            str(target.get("official_lane_key") or preview.get("official_lane_key") or "") == official_lane_key
            and record.get("status") in {TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_READY, TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_RECORDED}
            and record.get("payload_refresh_preview_recorded") is True
            and record.get("payload_refresh_preview_overall_status")
            == TINY_LIVE_ORDER_PAYLOAD_REFRESH_PREVIEW_CLEARS_PRECISION_AND_MIN_NOTIONAL
            and matrix.get("payload_refresh_preview_ready") is True
            and validate_refreshed_payload_preview(preview, refreshed_quantity_preview=quantity).get("valid") is True
        ):
            return _sanitize({**record, "r245_refresh_preview_found": True})
    return {}


def load_latest_tiny_live_leverage_notional_risk_contract_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r244(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r242(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_order_payload_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r240(log_dir=log_dir, official_lane_key=official_lane_key)


def build_refreshed_non_executable_payload_artifact(
    *,
    latest_r245: Mapping[str, Any],
    latest_r244: Mapping[str, Any],
    latest_r242: Mapping[str, Any],
    latest_r240: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    preview = (
        latest_r245.get("refreshed_non_executable_payload_preview")
        if isinstance(latest_r245.get("refreshed_non_executable_payload_preview"), Mapping)
        else {}
    )
    old_payload = latest_r240.get("order_payload") if isinstance(latest_r240.get("order_payload"), Mapping) else {}
    return {
        "order_payload_id": "r246_refreshed_order_payload_BTCUSDT_8m_short_ladder_close_50_618",
        "order_payload_version": ORDER_PAYLOAD_VERSION,
        "created_by_phase": CREATED_BY_PHASE,
        "created_at": generated_at.isoformat(),
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "exchange": "binance_futures",
        "side": "SELL",
        "position_side": preview.get("position_side") or old_payload.get("position_side") or "BOTH|SHORT|null",
        "order_type": "MARKET_PREVIEW_ONLY",
        "quantity": preview.get("quantity_preview"),
        "quantity_source": "r242_readonly_precision_mark_price_and_r244_adjusted_contract",
        "notional_cap_usdt": preview.get("notional_cap_usdt"),
        "notional_after_rounding": preview.get("notional_after_rounding"),
        "margin_budget_usdt": preview.get("margin_budget_usdt"),
        "leverage": preview.get("leverage"),
        "max_loss_usdt": preview.get("max_loss_usdt"),
        "max_loss_requires_review": preview.get("max_loss_requires_review") is True,
        "reduce_only": False,
        "stop_required": True,
        "take_profit_required": True,
        "stop_payload": {
            "preview_only": True,
            "executable": False,
            "signed": False,
            "order_type": "STOP_MARKET_PREVIEW_ONLY",
            "side": "BUY",
            "reduce_only": True,
            "stop_price": None,
            "requires_future_price_precision": True,
            "requires_stop_level_source_later": True,
        },
        "take_profit_payload": {
            "preview_only": True,
            "executable": False,
            "signed": False,
            "order_type": "TAKE_PROFIT_MARKET_PREVIEW_ONLY",
            "side": "BUY",
            "reduce_only": True,
            "take_profit_price": None,
            "requires_future_price_precision": True,
            "requires_take_profit_level_source_later": True,
        },
        "source_payload_refresh_preview_id": latest_r245.get("order_payload_refresh_preview_record_id")
        or preview.get("order_payload_refresh_preview_id"),
        "source_r244_risk_contract_record_id": latest_r244.get("risk_contract_write_gate_record_id")
        or preview.get("source_r244_risk_contract_record_id"),
        "source_r242_readonly_record_id": latest_r242.get("binance_readonly_record_id"),
        "artifact_only": True,
        "preview_only": False,
        "executable": False,
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "order_payload_created": True,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "order_placed": False,
        "missing_before_executable_payload": [
            "final_stop_price",
            "final_take_profit_price",
            "operator_executable_payload_confirmation",
            "signature_gate",
            "submit_gate",
        ],
    }


def validate_refreshed_non_executable_payload_artifact(payload_refresh: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    expected = {
        "official_lane_key": OFFICIAL_LANE_KEY,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "exchange": "binance_futures",
        "side": "SELL",
        "order_type": "MARKET_PREVIEW_ONLY",
        "quantity_source": "r242_readonly_precision_mark_price_and_r244_adjusted_contract",
        "notional_cap_usdt": 440,
        "margin_budget_usdt": 44,
        "leverage": 10,
        "max_loss_usdt": 4.44,
        "max_loss_requires_review": True,
        "reduce_only": False,
        "stop_required": True,
        "take_profit_required": True,
        "artifact_only": True,
        "preview_only": False,
        "executable": False,
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "order_payload_created": True,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "order_placed": False,
    }
    for key, value in expected.items():
        if payload_refresh.get(key) != value:
            errors.append(f"{key}_invalid")
    quantity = payload_refresh.get("quantity")
    if quantity != 0.007:
        errors.append("quantity_invalid")
    notional = payload_refresh.get("notional_after_rounding")
    if notional is None or abs(float(notional) - 435.4721) > 0.0001:
        errors.append("notional_after_rounding_invalid")
    for key in ("source_payload_refresh_preview_id", "source_r244_risk_contract_record_id", "source_r242_readonly_record_id"):
        if not payload_refresh.get(key):
            warnings.append(f"{key}_missing")
    stop = payload_refresh.get("stop_payload") if isinstance(payload_refresh.get("stop_payload"), Mapping) else {}
    take_profit = (
        payload_refresh.get("take_profit_payload")
        if isinstance(payload_refresh.get("take_profit_payload"), Mapping)
        else {}
    )
    for name, child in (("stop_payload", stop), ("take_profit_payload", take_profit)):
        for key, value in {
            "preview_only": True,
            "executable": False,
            "signed": False,
            "side": "BUY",
            "reduce_only": True,
            "requires_future_price_precision": True,
        }.items():
            if child.get(key) != value:
                errors.append(f"{name}_{key}_invalid")
    if stop.get("order_type") != "STOP_MARKET_PREVIEW_ONLY" or stop.get("stop_price") is not None:
        errors.append("stop_payload_invalid")
    if take_profit.get("order_type") != "TAKE_PROFIT_MARKET_PREVIEW_ONLY" or take_profit.get("take_profit_price") is not None:
        errors.append("take_profit_payload_invalid")
    required_missing = {
        "final_stop_price",
        "final_take_profit_price",
        "operator_executable_payload_confirmation",
        "signature_gate",
        "submit_gate",
    }
    if not required_missing.issubset(set(payload_refresh.get("missing_before_executable_payload") or [])):
        errors.append("missing_before_executable_payload_invalid")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def build_payload_refresh_write_preview(
    *,
    proposed_refreshed_payload: Mapping[str, Any],
    payload_refresh_valid: bool,
    blocked_by: Sequence[str] | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return {
        "would_write": bool(payload_refresh_valid and not blocked_by),
        "write_requires_confirmation": True,
        "target_payload_key": official_lane_key,
        "bounded_mutation_only": True,
        "payload_artifact": "ledger_only_non_executable_refreshed_payload",
        "proposed_refreshed_payload": _sanitize(dict(proposed_refreshed_payload)),
    }


def write_payload_refresh_if_confirmed(
    *,
    payload_refresh: Mapping[str, Any],
    confirm_tiny_live_order_payload_refresh_write: str | None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_order_payload_refresh_write != CONFIRM_TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_PHRASE:
        return {"written": False, "reason": "bad_confirmation"}
    validation = validate_refreshed_non_executable_payload_artifact(payload_refresh)
    if validation["valid"] is not True:
        return {"written": False, "reason": "validation_failed", "validation": validation}
    record = append_tiny_live_order_payload_refresh_write_gate_record(
        {
            "status": TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_WRITTEN,
            "generated_at": payload_refresh.get("created_at"),
            "payload_refresh_written": True,
            "write_payload_refresh_requested": True,
            "confirmation_valid": True,
            "target_scope": _target_scope(str(payload_refresh.get("official_lane_key") or OFFICIAL_LANE_KEY)),
            "refreshed_payload_artifact": dict(payload_refresh),
            "payload_refresh_validation": validation,
            "safety": {**SAFETY, "order_payload_written": True, "order_payload_created": True},
        },
        log_dir=log_dir,
    )
    return {"written": True, "record": record}


def build_post_write_payload_refresh_verification(
    *,
    payload_refresh: Mapping[str, Any],
    payload_refresh_written: bool,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_tiny_live_order_payload_refresh_write_gate_records(log_dir=log_dir, limit=50) if payload_refresh_written else []
    matching = _matching_payload_refresh_record(records, payload_refresh)
    artifact = (
        matching.get("refreshed_payload_artifact")
        if isinstance(matching.get("refreshed_payload_artifact"), Mapping)
        else {}
    )
    validation = validate_refreshed_non_executable_payload_artifact(artifact)
    return {
        "payload_refresh_written": bool(payload_refresh_written),
        "matching_payload_refresh_found": bool(matching),
        "matching_payload_refresh_valid": bool(matching and validation["valid"]),
        "quantity": artifact.get("quantity") if matching else None,
        "notional_after_rounding": artifact.get("notional_after_rounding") if matching else None,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "submit_allowed": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def build_payload_refresh_write_gate_matrix(
    *,
    r245_refresh_preview_ready: bool,
    payload_refresh_valid: bool,
    payload_refresh_write_confirmed: bool,
    payload_refresh_written: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if not r245_refresh_preview_ready:
        blockers.append("r245_refresh_preview_not_ready")
    if not payload_refresh_valid:
        blockers.append("payload_refresh_invalid")
    if not payload_refresh_write_confirmed:
        blockers.append("exact_payload_refresh_write_confirmation_required")
    if payload_refresh_written:
        blockers = [
            "executable_payload_preview_required_next",
            "stop_take_profit_levels_required_later",
            "signature_gate_required_later",
            "submit_gate_required_later",
            "kill_switch_still_active",
        ]
    return {
        "r245_refresh_preview_ready": bool(r245_refresh_preview_ready),
        "payload_refresh_valid": bool(payload_refresh_valid),
        "payload_refresh_write_confirmed": bool(payload_refresh_write_confirmed),
        "payload_refresh_written": bool(payload_refresh_written),
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_payload_refresh_write_packet(
    payload_refresh_write_gate_matrix: Mapping[str, Any],
    *,
    write_requested: bool = False,
) -> dict[str, Any]:
    written = payload_refresh_write_gate_matrix.get("payload_refresh_written") is True
    ready = (
        payload_refresh_write_gate_matrix.get("r245_refresh_preview_ready") is True
        and payload_refresh_write_gate_matrix.get("payload_refresh_valid") is True
        and not written
    )
    if written:
        action = "REVIEW_R246_RESULT"
    elif ready:
        action = "CONFIRM_R246_PAYLOAD_REFRESH_WRITE"
    else:
        action = "WAIT"
    return {
        "operator_should_review_payload_refresh_write": bool(ready or written or write_requested),
        "operator_confirmation_required": True,
        "operator_should_create_executable_payload_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not create executable payload",
            "do not sign request",
            "do not call Binance from this phase",
        ],
    }


def classify_tiny_live_order_payload_refresh_write_status(
    *,
    input_summary: Mapping[str, Any],
    payload_refresh_validation: Mapping[str, Any],
    payload_refresh_written: bool = False,
    rejected_bad_confirmation: bool = False,
) -> str:
    if rejected_bad_confirmation:
        return TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_REJECTED_BAD_CONFIRMATION
    if payload_refresh_written:
        return TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITTEN_EXECUTABLE_PREVIEW_REQUIRED
    if not input_summary.get("r245_refresh_preview_valid"):
        return TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_BLOCKED_BY_R245
    if payload_refresh_validation.get("valid") is not True:
        return TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_BLOCKED_BY_VALIDATION
    return TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_READY_FOR_CONFIRMATION


def append_tiny_live_order_payload_refresh_write_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_order_payload_refresh_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = dict(record.get("refreshed_payload_artifact") or {})
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "gate_record_id": record.get("gate_record_id") or f"r246_payload_refresh_write_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "payload_refresh_written": record.get("payload_refresh_written") is True,
            "write_payload_refresh_requested": record.get("write_payload_refresh_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "refreshed_payload_artifact": artifact,
            "order_payload": artifact,
            "payload_refresh_validation": dict(record.get("payload_refresh_validation") or {}),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_order_payload_refresh_write_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_order_payload_refresh_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_order_payload_refresh_write_gate_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    artifact = latest.get("refreshed_payload_artifact") if isinstance(latest.get("refreshed_payload_artifact"), Mapping) else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_payload_refresh_written": latest.get("payload_refresh_written") is True,
        "latest_order_payload_id": artifact.get("order_payload_id"),
        "latest_quantity": artifact.get("quantity"),
    }


def tiny_live_order_payload_refresh_write_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_order_payload_refresh_write_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r245: Mapping[str, Any],
    latest_r244: Mapping[str, Any],
    latest_r242: Mapping[str, Any],
) -> dict[str, Any]:
    r245_validation = _r245_validation(latest_r245)
    return {
        "r245_refresh_preview_found": bool(latest_r245),
        "r245_refresh_preview_valid": r245_validation.get("valid") is True,
        "r244_adjusted_contract_found": bool(latest_r244),
        "r244_adjusted_contract_valid": bool(latest_r244),
        "r242_readonly_found": bool(latest_r242),
        "r242_readonly_valid": bool(latest_r242),
    }


def _blocked_by(*, input_summary: Mapping[str, Any], validation: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not input_summary.get("r245_refresh_preview_valid"):
        blockers.append("r245_refresh_preview_not_ready")
    if not input_summary.get("r244_adjusted_contract_valid"):
        blockers.append("r244_adjusted_contract_not_ready")
    if not input_summary.get("r242_readonly_valid"):
        blockers.append("r242_readonly_not_ready")
    if validation.get("valid") is not True:
        blockers.extend(str(error) for error in validation.get("errors") or ["payload_refresh_invalid"])
    return _dedupe(blockers)


def _r245_validation(latest_r245: Mapping[str, Any]) -> dict[str, Any]:
    preview = (
        latest_r245.get("refreshed_non_executable_payload_preview")
        if isinstance(latest_r245.get("refreshed_non_executable_payload_preview"), Mapping)
        else {}
    )
    quantity = (
        latest_r245.get("refreshed_quantity_preview")
        if isinstance(latest_r245.get("refreshed_quantity_preview"), Mapping)
        else {}
    )
    return validate_refreshed_payload_preview(preview, refreshed_quantity_preview=quantity) if preview else {"valid": False}


def _matching_payload_refresh_record(records: Sequence[Mapping[str, Any]], payload_refresh: Mapping[str, Any]) -> dict[str, Any]:
    expected_id = payload_refresh.get("order_payload_id")
    for record in records:
        artifact = record.get("refreshed_payload_artifact") if isinstance(record.get("refreshed_payload_artifact"), Mapping) else {}
        if artifact.get("order_payload_id") == expected_id and record.get("payload_refresh_written") is True:
            return _sanitize(record)
    return {}


def _target_scope(lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "payload_refresh_write_gate_only": True,
        "non_executable_artifact_only": True,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r245_refresh_preview_found": False,
        "r245_refresh_preview_valid": False,
        "r244_adjusted_contract_found": False,
        "r244_adjusted_contract_valid": False,
        "r242_readonly_found": False,
        "r242_readonly_valid": False,
    }


def _empty_payload_refresh_write_preview(official_lane_key: str) -> dict[str, Any]:
    return {
        "would_write": False,
        "write_requires_confirmation": True,
        "target_payload_key": official_lane_key,
        "bounded_mutation_only": True,
        "payload_artifact": "ledger_only_non_executable_refreshed_payload",
        "proposed_refreshed_payload": {},
    }


def _empty_post_write_verification() -> dict[str, Any]:
    return {
        "payload_refresh_written": False,
        "matching_payload_refresh_found": False,
        "matching_payload_refresh_valid": False,
        "quantity": None,
        "notional_after_rounding": None,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "submit_allowed": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def _recommended_next_operator_move(matrix: Mapping[str, Any], *, write_requested: bool) -> str:
    if matrix.get("payload_refresh_written"):
        return "REVIEW_R246_RESULT"
    if matrix.get("r245_refresh_preview_ready") and matrix.get("payload_refresh_valid"):
        return "CONFIRM_R246_PAYLOAD_REFRESH_WRITE"
    return "WAIT" if not write_requested else "REVIEW_BLOCKED_R246_PAYLOAD_REFRESH_WRITE"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("payload_refresh_written"):
        return "Create R247 Tiny-Live Executable Payload Preview; require final stop/take-profit levels, no signed request, no Binance call, no order."
    if matrix.get("payload_refresh_valid"):
        return "Await exact R246 confirmation before appending the refreshed non-executable payload artifact."
    return "Fix R246 prerequisites before any refreshed payload artifact write."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "executable order payload creation",
        "signed order request",
        "signed trading request",
        "kill switch disable",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key).split("|")
    if len(parts) != 4:
        return ("BTCUSDT", "8m", "short", "ladder_close_50_618")
    return parts[0], parts[1], parts[2], parts[3]


def _dedupe(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text not in seen:
            result.append(text)
            seen.add(text)
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
