"""R239 tiny-live order payload preview.

This module previews the future order payload shape for the official tiny-live
lane. It never creates an executable payload, signs a request, calls Binance or
network endpoints, places orders, mutates configs/env, or disables the kill
switch.
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
from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import (
    LEDGER_FILENAME as R228_LEDGER_FILENAME,
    RISK_CONTRACT_CONFIG_PATH,
)
from src.app.hammer_radar.operator.tiny_live_lane_arm_write_gate import (
    LEDGER_FILENAME as R236_LEDGER_FILENAME,
    validate_lane_arm_object,
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_preview import LANE_CONTROLS_PATH
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    LEDGER_FILENAME as R232_LEDGER_FILENAME,
    load_latest_tiny_live_10_of_10_ready_packet,
    load_latest_tiny_live_risk_contract_config_write_gate as _load_latest_tiny_live_risk_contract_config_write_gate,
    load_tiny_live_risk_contract_config,
    validate_live_authorization_object,
)
from src.app.hammer_radar.operator.tiny_live_live_execution_enable_write_gate import (
    LEDGER_FILENAME as R234_LEDGER_FILENAME,
    validate_live_execution_enable_object,
)
from src.app.hammer_radar.operator.tiny_live_order_preflight_preview import (
    LEDGER_FILENAME as R237_LEDGER_FILENAME,
    load_lane_controls_readonly,
    load_latest_tiny_live_lane_arm_write_gate,
    load_latest_tiny_live_live_authorization_write_gate,
    load_latest_tiny_live_live_execution_enable_write_gate,
)
from src.app.hammer_radar.operator.tiny_live_order_preflight_write_gate import (
    LEDGER_FILENAME as R238_LEDGER_FILENAME,
    load_latest_tiny_live_order_preflight_preview,
    load_tiny_live_order_preflight_write_gate_records,
    validate_order_preflight_object,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    LEDGER_FILENAME as R230_LEDGER_FILENAME,
    validate_tiny_live_risk_contract_config_entry,
)

TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY = "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY"
TINY_LIVE_ORDER_PAYLOAD_PREVIEW_REJECTED = "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_REJECTED"
TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDED = "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDED"
TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED = "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED"
TINY_LIVE_ORDER_PAYLOAD_PREVIEW_ERROR = "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_ERROR"

TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY_FOR_FUTURE_GATE = (
    "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY_FOR_FUTURE_GATE"
)
TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_PREFLIGHT = (
    "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_PREFLIGHT"
)
TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_LANE_ARM = (
    "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_LANE_ARM"
)
TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE = (
    "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE"
)
TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_AUTHORIZATION = (
    "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_AUTHORIZATION"
)
TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_RISK_CONTRACT = (
    "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_RISK_CONTRACT"
)
TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_EVIDENCE = (
    "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_EVIDENCE"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_ORDER_PAYLOAD_PREVIEW"
LEDGER_FILENAME = "tiny_live_order_payload_preview.ndjson"
CONFIRM_TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE ORDER PAYLOAD PREVIEW RECORDING ONLY; "
    "NO ORDER PAYLOAD; NO ORDER; NO BINANCE CALL."
)
FUTURE_ORDER_PAYLOAD_WRITE_CONFIRMATION_PHRASE = (
    "I CONFIRM TINY LIVE ORDER PAYLOAD WRITE GATE ONLY; "
    "NON-EXECUTABLE PAYLOAD ARTIFACT ONLY; NO ORDER; NO BINANCE CALL."
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "lane_controls_written": False,
    "fisherman_config_written": False,
    "scheduler_config_written": False,
    "live_config_written": False,
    "live_authorization_written": False,
    "live_execution_enable_written": False,
    "lane_arm_written": False,
    "order_preflight_written": False,
    "order_payload_preview_recorded": False,
    "order_payload_allowed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "binance_account_endpoint_called": False,
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "kill_switch_disabled": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
    "order_payload_preview_only": True,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R238_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R237_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R236_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R234_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R232_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R230_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_order_payload_preview(
    *,
    log_dir: str | Path | None = None,
    record_order_payload_preview: bool = False,
    confirm_tiny_live_order_payload_preview: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    confirmation_valid = (
        confirm_tiny_live_order_payload_preview
        == CONFIRM_TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDING_PHRASE
    )
    try:
        latest_r238 = load_latest_tiny_live_order_preflight_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r237 = load_latest_tiny_live_order_preflight_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r236 = load_latest_tiny_live_lane_arm_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r234 = load_latest_tiny_live_live_execution_enable_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r232 = load_latest_tiny_live_live_authorization_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r230 = load_latest_tiny_live_risk_contract_config_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r228 = load_latest_tiny_live_10_of_10_ready_packet(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        risk_config = load_tiny_live_risk_contract_config(risk_path, official_lane_key=official_lane_key)
        lane_controls = load_lane_controls_readonly(lane_path, official_lane_key=official_lane_key)
        input_summary = _build_input_summary(
            latest_r238=latest_r238,
            latest_r237=latest_r237,
            latest_r236=latest_r236,
            latest_r234=latest_r234,
            latest_r232=latest_r232,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_config=risk_config,
        )
        risk_summary = _risk_contract_summary(risk_config)
        preview = build_non_executable_order_payload_preview(
            risk_contract_summary=risk_summary,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        validation = validate_order_payload_preview(preview)
        blocked_by = _blocked_by(input_summary=input_summary, validation=validation, official_lane_key=official_lane_key)
        matrix = build_order_payload_preview_gate_matrix(input_summary=input_summary, blocked_by=blocked_by)
        operator_packet = build_operator_order_payload_preview_review_packet(matrix)
        recommendations = build_order_payload_preview_recommendations(matrix)
        overall = classify_tiny_live_order_payload_preview_status(
            input_summary=input_summary,
            gate_matrix=matrix,
        )
        status = (
            TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY
            if overall == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY_FOR_FUTURE_GATE
            else TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED
        )
        if record_order_payload_preview and not confirmation_valid:
            status = TINY_LIVE_ORDER_PAYLOAD_PREVIEW_REJECTED
        elif record_order_payload_preview and confirmation_valid and status == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY:
            status = TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDED

        safety = dict(SAFETY)
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "order_payload_preview_recorded": False,
            "order_payload_preview_record_id": None,
            "record_order_payload_preview_requested": bool(record_order_payload_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(
                official_lane_key,
                live_authorized=input_summary["live_authorized"],
                live_execution_enabled=input_summary["live_execution_enabled"],
                lane_armed=input_summary["lane_armed"],
                order_preflight_written=input_summary["order_preflight_written"],
            ),
            "input_summary": input_summary,
            "risk_contract_summary": risk_summary,
            "order_preflight_summary": _order_preflight_summary(latest_r238),
            "lane_controls_readonly_summary": lane_controls,
            "non_executable_order_payload_preview": preview,
            "order_payload_preview_validation": validation,
            "order_payload_preview_gate_matrix": matrix,
            "operator_order_payload_preview_review_packet": operator_packet,
            "recommended_next_operator_move": recommendations["recommended_next_operator_move"],
            "recommended_next_engineering_move": recommendations["recommended_next_engineering_move"],
            "future_confirmation_phrase_suggestion": FUTURE_ORDER_PAYLOAD_WRITE_CONFIRMATION_PHRASE,
            "order_payload_preview_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if status == TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDED:
            record = append_tiny_live_order_payload_preview_record(payload, log_dir=resolved_log_dir)
            payload["order_payload_preview_recorded"] = True
            payload["order_payload_preview_record_id"] = record["order_payload_preview_record_id"]
            payload["ledger_path"] = str(tiny_live_order_payload_preview_records_path(resolved_log_dir))
            payload["safety"] = {**safety, "order_payload_preview_recorded": True}
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = _empty_gate_matrix(["order_payload_preview_error"])
        return _sanitize(
            {
                "status": TINY_LIVE_ORDER_PAYLOAD_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "order_payload_preview_recorded": False,
                "order_payload_preview_record_id": None,
                "record_order_payload_preview_requested": bool(record_order_payload_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(
                    official_lane_key,
                    live_authorized=False,
                    live_execution_enabled=False,
                    lane_armed=False,
                    order_preflight_written=False,
                ),
                "input_summary": _empty_input_summary(),
                "risk_contract_summary": _risk_contract_summary({}),
                "order_preflight_summary": _order_preflight_summary({}),
                "non_executable_order_payload_preview": build_non_executable_order_payload_preview(
                    risk_contract_summary=_risk_contract_summary({}),
                    official_lane_key=official_lane_key,
                    now=generated_at,
                ),
                "order_payload_preview_validation": {
                    "valid": False,
                    "errors": ["order_payload_preview_error"],
                    "warnings": [],
                },
                "order_payload_preview_gate_matrix": matrix,
                "operator_order_payload_preview_review_packet": build_operator_order_payload_preview_review_packet(matrix),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R239 order-payload preview error before any future write gate.",
                "future_confirmation_phrase_suggestion": FUTURE_ORDER_PAYLOAD_WRITE_CONFIRMATION_PHRASE,
                "order_payload_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_order_preflight_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_order_preflight_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        artifact = record.get("order_preflight") if isinstance(record.get("order_preflight"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or artifact.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == "TINY_LIVE_ORDER_PREFLIGHT_WRITE_GATE_WRITTEN"
            and record.get("order_preflight_written") is True
            and validate_order_preflight_object(artifact).get("valid") is True
        ):
            return _sanitize({**record, "r238_order_preflight_found": True})
    return {}


def load_tiny_live_order_payload_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_order_payload_preview_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def load_latest_tiny_live_risk_contract_config_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return _load_latest_tiny_live_risk_contract_config_write_gate(
        log_dir=log_dir,
        official_lane_key=official_lane_key,
    )


def build_non_executable_order_payload_preview(
    *,
    risk_contract_summary: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    del now
    symbol, _, direction, _ = _lane_parts(official_lane_key)
    max_notional = min(_float_or_default(risk_contract_summary.get("max_notional_usdt"), 44.0), 44.0)
    max_loss = min(_float_or_default(risk_contract_summary.get("max_loss_usdt"), 4.44), 4.44)
    leverage = int(risk_contract_summary.get("leverage") or 1)
    return {
        "order_payload_preview_id": f"r239_order_payload_preview_{symbol}_8m_{direction}_ladder_close_50_618_{uuid4().hex}",
        "preview_only": True,
        "executable": False,
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "official_lane_key": official_lane_key,
        "exchange": "binance_futures",
        "symbol": symbol,
        "side": "SELL",
        "position_side": "BOTH|SHORT|null",
        "order_type": "MARKET|LIMIT_PREVIEW_ONLY",
        "time_in_force": None,
        "quantity_preview": None,
        "quantity_source": "requires_precision_and_mark_price_later",
        "notional_cap_usdt": int(max_notional) if max_notional.is_integer() else max_notional,
        "max_loss_usdt": max_loss,
        "leverage": leverage,
        "reduce_only": False,
        "stop_required": True,
        "take_profit_required": True,
        "stop_payload_preview": {
            "preview_only": True,
            "order_type": "STOP_MARKET|STOP_PREVIEW_ONLY",
            "side": "BUY",
            "reduce_only": True,
            "stop_price": None,
            "requires_future_price_precision": True,
        },
        "take_profit_payload_preview": {
            "preview_only": True,
            "order_type": "TAKE_PROFIT_MARKET|TP_PREVIEW_ONLY",
            "side": "BUY",
            "reduce_only": True,
            "take_profit_price": None,
            "requires_future_price_precision": True,
        },
        "missing_before_payload_write": [
            "symbol_precision_check",
            "mark_price_or_candidate_price_snapshot",
            "quantity_rounding",
            "min_notional_check",
            "final_operator_payload_confirmation",
        ],
        "required_precision_checks_later": [
            "price_precision",
            "quantity_precision",
            "step_size",
            "tick_size",
            "min_notional",
        ],
        "required_binance_connectivity_later": True,
        "required_signature_later": True,
        "required_payload_write_gate_later": True,
        "future_suggested_confirmation_phrase": FUTURE_ORDER_PAYLOAD_WRITE_CONFIRMATION_PHRASE,
    }


def validate_order_payload_preview(order_payload_preview: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    expected = {
        "preview_only": True,
        "executable": False,
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "official_lane_key": OFFICIAL_LANE_KEY,
        "exchange": "binance_futures",
        "symbol": "BTCUSDT",
        "side": "SELL",
        "quantity_preview": None,
        "quantity_source": "requires_precision_and_mark_price_later",
        "notional_cap_usdt": 44,
        "max_loss_usdt": 4.44,
        "leverage": 1,
        "reduce_only": False,
        "stop_required": True,
        "take_profit_required": True,
    }
    for key, value in expected.items():
        if order_payload_preview.get(key) is not value and order_payload_preview.get(key) != value:
            errors.append(f"{key}_invalid")
    if not str(order_payload_preview.get("order_payload_preview_id") or "").startswith(
        "r239_order_payload_preview_BTCUSDT_8m_short_ladder_close_50_618_"
    ):
        errors.append("order_payload_preview_id_invalid")
    if order_payload_preview.get("order_type") not in {"MARKET|LIMIT_PREVIEW_ONLY"}:
        errors.append("order_type_invalid")
    if order_payload_preview.get("position_side") != "BOTH|SHORT|null":
        errors.append("position_side_invalid")
    stop = order_payload_preview.get("stop_payload_preview") if isinstance(order_payload_preview.get("stop_payload_preview"), Mapping) else {}
    tp = (
        order_payload_preview.get("take_profit_payload_preview")
        if isinstance(order_payload_preview.get("take_profit_payload_preview"), Mapping)
        else {}
    )
    if stop.get("preview_only") is not True or stop.get("reduce_only") is not True or stop.get("stop_price") is not None:
        errors.append("stop_payload_preview_invalid")
    if tp.get("preview_only") is not True or tp.get("reduce_only") is not True or tp.get("take_profit_price") is not None:
        errors.append("take_profit_payload_preview_invalid")
    if "final_operator_payload_confirmation" not in (order_payload_preview.get("missing_before_payload_write") or []):
        errors.append("missing_before_payload_write_invalid")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def build_order_payload_preview_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    ready = not blockers
    if ready:
        blockers = [
            "future_order_payload_write_gate_required",
            "symbol_precision_check_required",
            "mark_price_or_candidate_price_snapshot_required",
            "quantity_rounding_required",
            "min_notional_check_required",
            "final_operator_payload_confirmation_required",
            "signed_request_forbidden",
            "binance_call_forbidden",
            "kill_switch_still_active",
        ]
    return {
        "evidence_ready": input_summary.get("r228_evidence_ready") is True,
        "fisherman_ready": input_summary.get("fisherman_ready") is True,
        "risk_contract_config_ready": input_summary.get("risk_contract_valid") is True,
        "live_authorization_written": input_summary.get("r232_authorization_found") is True,
        "live_authorized": input_summary.get("live_authorized") is True,
        "live_execution_enable_written": input_summary.get("r234_execution_enable_found") is True,
        "live_execution_enabled": input_summary.get("live_execution_enabled") is True,
        "lane_arm_written": input_summary.get("r236_lane_arm_found") is True,
        "lane_armed": input_summary.get("lane_armed") is True,
        "order_preflight_written": input_summary.get("order_preflight_written") is True,
        "order_payload_preview_ready": ready,
        "order_payload_created": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_order_payload_preview_review_packet(
    order_payload_preview_gate_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    ready = order_payload_preview_gate_matrix.get("order_payload_preview_ready") is True
    if ready:
        action = "REVIEW_R239_ORDER_PAYLOAD_PREVIEW"
    elif any("not_ready" in str(item) or "missing" in str(item) for item in order_payload_preview_gate_matrix.get("blocked_by") or []):
        action = "WAIT"
    else:
        action = "FIX_BLOCKER"
    return {
        "operator_should_review_order_payload_preview": ready,
        "operator_should_create_order_payload_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not create executable order payload from this phase",
            "do not sign request",
            "do not call Binance from this phase",
        ],
    }


def build_order_payload_preview_recommendations(order_payload_preview_gate_matrix: Mapping[str, Any]) -> dict[str, str]:
    if order_payload_preview_gate_matrix.get("order_payload_preview_ready"):
        return {
            "recommended_next_operator_move": "REVIEW_R239_ORDER_PAYLOAD_PREVIEW",
            "recommended_next_engineering_move": "Create R240 Tiny-Live Order Payload Write Gate; guarded non-executable artifact only, no Binance/network calls, no orders, no executable payloads, and no signed requests.",
        }
    if not order_payload_preview_gate_matrix.get("order_preflight_written"):
        return {
            "recommended_next_operator_move": "WAIT",
            "recommended_next_engineering_move": "Restore or write the R238 order-preflight artifact before any order-payload preview can proceed.",
        }
    return {
        "recommended_next_operator_move": "FIX_BLOCKER",
        "recommended_next_engineering_move": "Fix R239 evidence, risk-contract, authorization, execution-enable, lane-arm, or order-preflight blockers before R240.",
    }


def classify_tiny_live_order_payload_preview_status(
    *,
    input_summary: Mapping[str, Any],
    gate_matrix: Mapping[str, Any],
) -> str:
    blocked_by = set(gate_matrix.get("blocked_by") or [])
    if gate_matrix.get("order_payload_preview_ready"):
        return TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY_FOR_FUTURE_GATE
    if not input_summary.get("r238_order_preflight_found") or "order_preflight_not_ready" in blocked_by:
        return TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_PREFLIGHT
    if not input_summary.get("r236_lane_arm_found") or "lane_arm_not_ready" in blocked_by:
        return TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_LANE_ARM
    if not input_summary.get("r234_execution_enable_found") or "execution_enable_not_ready" in blocked_by:
        return TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_EXECUTION_ENABLE
    if not input_summary.get("r232_authorization_found") or "authorization_not_ready" in blocked_by:
        return TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_AUTHORIZATION
    if not input_summary.get("risk_contract_valid") or "risk_contract_config_not_ready" in blocked_by:
        return TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_RISK_CONTRACT
    if not input_summary.get("r228_evidence_ready") or not input_summary.get("fisherman_ready"):
        return TINY_LIVE_ORDER_PAYLOAD_PREVIEW_BLOCKED_BY_EVIDENCE
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_order_payload_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_order_payload_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    safety = {**dict(record.get("safety") or SAFETY), "order_payload_preview_recorded": True}
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "order_payload_preview_record_id": record.get("order_payload_preview_record_id")
            or f"r239_order_payload_preview_record_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "order_payload_preview_recorded": True,
            "record_order_payload_preview_requested": record.get("record_order_payload_preview_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "risk_contract_summary": dict(record.get("risk_contract_summary") or {}),
            "order_preflight_summary": dict(record.get("order_preflight_summary") or {}),
            "non_executable_order_payload_preview": dict(record.get("non_executable_order_payload_preview") or {}),
            "order_payload_preview_validation": dict(record.get("order_payload_preview_validation") or {}),
            "order_payload_preview_gate_matrix": dict(record.get("order_payload_preview_gate_matrix") or {}),
            "operator_order_payload_preview_review_packet": dict(
                record.get("operator_order_payload_preview_review_packet") or {}
            ),
            "order_payload_preview_overall_status": record.get("order_payload_preview_overall_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "future_confirmation_phrase_suggestion": record.get("future_confirmation_phrase_suggestion"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": safety,
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def summarize_tiny_live_order_payload_preview_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_preview_recorded": latest.get("order_payload_preview_recorded") is True,
        "latest_overall_status": latest.get("order_payload_preview_overall_status"),
    }


def tiny_live_order_payload_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_order_payload_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r238: Mapping[str, Any],
    latest_r237: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    latest_r234: Mapping[str, Any],
    latest_r232: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_config: Mapping[str, Any],
) -> dict[str, Any]:
    order_preflight = latest_r238.get("order_preflight") if isinstance(latest_r238.get("order_preflight"), Mapping) else {}
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    execution_enable = latest_r234.get("execution_enable") if isinstance(latest_r234.get("execution_enable"), Mapping) else {}
    auth = latest_r232.get("authorization") if isinstance(latest_r232.get("authorization"), Mapping) else {}
    risk_contract = (
        risk_config.get("matching_risk_contract") if isinstance(risk_config.get("matching_risk_contract"), Mapping) else {}
    )
    r228_matrix = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    order_preflight_validation = (
        validate_order_preflight_object(order_preflight) if order_preflight else {"valid": False}
    )
    lane_arm_validation = validate_lane_arm_object(lane_arm) if lane_arm else {"valid": False}
    execution_validation = validate_live_execution_enable_object(execution_enable) if execution_enable else {"valid": False}
    auth_validation = validate_live_authorization_object(auth) if auth else {"valid": False}
    risk_validation = (
        validate_tiny_live_risk_contract_config_entry(risk_contract)
        if risk_contract
        else {"valid": False}
    )
    return {
        "r238_order_preflight_found": bool(latest_r238),
        "r238_order_preflight_valid": order_preflight_validation.get("valid") is True,
        "r237_order_preflight_preview_found": bool(latest_r237),
        "r236_lane_arm_found": bool(latest_r236),
        "r236_lane_arm_valid": lane_arm_validation.get("valid") is True,
        "r234_execution_enable_found": bool(latest_r234),
        "r234_execution_enable_valid": execution_validation.get("valid") is True,
        "r232_authorization_found": bool(latest_r232),
        "r232_authorization_valid": auth_validation.get("valid") is True,
        "r230_risk_contract_config_found": bool(latest_r230) and bool(risk_contract),
        "risk_contract_valid": risk_validation.get("valid") is True,
        "r228_evidence_ready": r228_matrix.get("evidence_ready") is True,
        "fisherman_ready": r228_matrix.get("fisherman_ready") is True,
        "live_authorized": auth.get("live_authorized") is True
        and execution_enable.get("live_authorized") is True
        and lane_arm.get("live_authorized") is True
        and order_preflight.get("live_authorized") is True,
        "live_execution_enabled": execution_enable.get("live_execution_enabled") is True
        and lane_arm.get("live_execution_enabled") is True
        and order_preflight.get("live_execution_enabled") is True,
        "lane_armed": lane_arm.get("lane_armed") is True and order_preflight.get("lane_armed") is True,
        "order_preflight_written": order_preflight.get("order_preflight_written") is True
        and latest_r238.get("order_preflight_written") is True,
        "order_payload_allowed": False,
        "order_payload_created": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "kill_switch_disabled": False,
    }


def _blocked_by(
    *,
    input_summary: Mapping[str, Any],
    validation: Mapping[str, Any],
    official_lane_key: str,
) -> list[str]:
    blockers: list[str] = []
    if official_lane_key != OFFICIAL_LANE_KEY:
        blockers.append("official_lane_mismatch")
    if not input_summary.get("r228_evidence_ready"):
        blockers.append("r228_evidence_not_ready")
    if not input_summary.get("fisherman_ready"):
        blockers.append("fisherman_not_ready")
    if not input_summary.get("risk_contract_valid"):
        blockers.append("risk_contract_config_not_ready")
    if not input_summary.get("r232_authorization_valid") or not input_summary.get("live_authorized"):
        blockers.append("authorization_not_ready")
    if not input_summary.get("r234_execution_enable_valid") or not input_summary.get("live_execution_enabled"):
        blockers.append("execution_enable_not_ready")
    if not input_summary.get("r236_lane_arm_valid") or not input_summary.get("lane_armed"):
        blockers.append("lane_arm_not_ready")
    if not input_summary.get("r238_order_preflight_valid") or not input_summary.get("order_preflight_written"):
        blockers.append("order_preflight_not_ready")
    for key in (
        "order_payload_allowed",
        "order_payload_created",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "binance_call_allowed",
        "network_allowed",
        "kill_switch_disabled",
    ):
        expected = False
        if input_summary.get(key) is not expected:
            blockers.append(f"{key}_not_false")
    if not validation.get("valid"):
        blockers.extend(str(error) for error in validation.get("errors") or ["order_payload_preview_invalid"])
    return _dedupe(blockers)


def _risk_contract_summary(risk_contract_config: Mapping[str, Any]) -> dict[str, Any]:
    contract = risk_contract_config.get("matching_risk_contract") if isinstance(risk_contract_config.get("matching_risk_contract"), Mapping) else {}
    return {
        "official_lane_key": contract.get("official_lane_key") or OFFICIAL_LANE_KEY,
        "max_account_risk_usdt": contract.get("max_account_risk_usdt"),
        "max_loss_usdt": contract.get("max_loss_usdt"),
        "max_notional_usdt": contract.get("max_notional_usdt"),
        "leverage": contract.get("leverage"),
    }


def _order_preflight_summary(latest_r238: Mapping[str, Any]) -> dict[str, Any]:
    order_preflight = latest_r238.get("order_preflight") if isinstance(latest_r238.get("order_preflight"), Mapping) else {}
    return {
        "order_preflight_id": order_preflight.get("order_preflight_id"),
        "order_preflight_status": order_preflight.get("order_preflight_status"),
        "order_preflight_written": order_preflight.get("order_preflight_written") is True,
        "order_payload_allowed": order_preflight.get("order_payload_allowed") is True,
        "order_payload_created": order_preflight.get("order_payload_created") is True,
        "executable_payload_created": order_preflight.get("executable_payload_created") is True,
        "signed_order_request_created": order_preflight.get("signed_order_request_created") is True,
        "signed_trading_request_created": order_preflight.get("signed_trading_request_created") is True,
        "order_placed": order_preflight.get("order_placed") is True,
        "binance_call_allowed": order_preflight.get("binance_call_allowed") is True,
        "network_allowed": order_preflight.get("network_allowed") is True,
        "kill_switch_disabled": order_preflight.get("kill_switch_disabled") is True,
    }


def _target_scope(
    lane_key: str,
    *,
    live_authorized: bool,
    live_execution_enabled: bool,
    lane_armed: bool,
    order_preflight_written: bool,
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "order_payload_preview_only": True,
        "live_authorized": bool(live_authorized),
        "live_execution_enabled": bool(live_execution_enabled),
        "lane_armed": bool(lane_armed),
        "order_preflight_written": bool(order_preflight_written),
        "order_payload_created": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_placed": False,
        "kill_switch_disabled": False,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r238_order_preflight_found": False,
        "r238_order_preflight_valid": False,
        "r237_order_preflight_preview_found": False,
        "r236_lane_arm_found": False,
        "r236_lane_arm_valid": False,
        "r234_execution_enable_found": False,
        "r234_execution_enable_valid": False,
        "r232_authorization_found": False,
        "r232_authorization_valid": False,
        "r230_risk_contract_config_found": False,
        "risk_contract_valid": False,
        "r228_evidence_ready": False,
        "fisherman_ready": False,
        "live_authorized": False,
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_preflight_written": False,
        "order_payload_allowed": False,
        "order_payload_created": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "kill_switch_disabled": False,
    }


def _empty_gate_matrix(blocked_by: list[str] | None = None) -> dict[str, Any]:
    return {
        "evidence_ready": False,
        "fisherman_ready": False,
        "risk_contract_config_ready": False,
        "live_authorization_written": False,
        "live_authorized": False,
        "live_execution_enable_written": False,
        "live_execution_enabled": False,
        "lane_arm_written": False,
        "lane_armed": False,
        "order_preflight_written": False,
        "order_payload_preview_ready": False,
        "order_payload_created": False,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": list(blocked_by or []),
    }


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
    parts = lane_key.split("|")
    if len(parts) != 4:
        return lane_key, "", "", ""
    return parts[0], parts[1], parts[2], parts[3]


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
