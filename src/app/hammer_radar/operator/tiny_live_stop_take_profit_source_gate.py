"""R248 tiny-live stop / take-profit source gate.

This gate validates local stop/take-profit source levels for the official
tiny-live short lane. It never creates executable payloads, signs requests,
calls Binance/network endpoints, places orders, mutates configs/env/lane
controls, or disables the kill switch.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_binance_readonly_precision_mark_price_gate import (
    load_tiny_live_binance_readonly_precision_mark_price_records,
)
from src.app.hammer_radar.operator.tiny_live_executable_payload_preview import (
    load_tiny_live_executable_payload_preview_records,
    validate_executable_payload_preview,
)
from src.app.hammer_radar.operator.tiny_live_leverage_notional_risk_contract_write_gate import (
    load_tiny_live_leverage_notional_risk_contract_write_gate_records,
    validate_adjusted_risk_contract,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_refresh_preview import (
    load_tiny_live_order_payload_refresh_preview_records,
    validate_refreshed_payload_preview,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_refresh_write_gate import (
    load_tiny_live_order_payload_refresh_write_gate_records,
    validate_refreshed_non_executable_payload_artifact,
)
from src.app.hammer_radar.operator.tiny_live_order_preflight_write_gate import (
    load_tiny_live_order_preflight_write_gate_records,
    validate_order_preflight_object,
)

TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_READY = "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_READY"
TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_RECORDED = "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_RECORDED"
TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_REJECTED = "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_REJECTED"
TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_BLOCKED = "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_BLOCKED"
TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_ERROR = "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_ERROR"

TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_READY_FOR_REVIEW = (
    "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_READY_FOR_REVIEW"
)
TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_RECORDED_EXECUTABLE_WRITE_STILL_BLOCKED = (
    "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_RECORDED_EXECUTABLE_WRITE_STILL_BLOCKED"
)
TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_MISSING_SOURCE = (
    "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_MISSING_SOURCE"
)
TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_DIRECTIONAL_VALIDATION = (
    "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_DIRECTIONAL_VALIDATION"
)
TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_RISK_VALIDATION = (
    "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_RISK_VALIDATION"
)
TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_REJECTED_BAD_CONFIRMATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

CONFIRM_TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE STOP TAKE PROFIT SOURCE PREVIEW RECORDING ONLY; "
    "NO EXECUTABLE PAYLOAD; NO ORDER; NO BINANCE CALL."
)
CONFIRM_TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_PHRASE = (
    CONFIRM_TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_PREVIEW_RECORDING_PHRASE
)

EVENT_TYPE = "TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE"
LEDGER_FILENAME = "tiny_live_stop_take_profit_source_gate.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R248_TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE"
DEFAULT_RISK_CONTRACT_CONFIG_PATH = Path("configs/hammer_radar/tiny_live_risk_contracts.json")

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_executable_payload_preview.ndjson",
    "logs/hammer_radar_forward/tiny_live_order_payload_refresh_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_order_payload_refresh_preview.ndjson",
    "logs/hammer_radar_forward/tiny_live_leverage_notional_risk_contract_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_order_preflight_write_gate.ndjson",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]

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
    "stop_take_profit_source_gate_only": True,
}


def build_tiny_live_stop_take_profit_source_gate(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    record_stop_take_profit_source_preview: bool = False,
    confirm_tiny_live_stop_take_profit_source_preview: str | None = None,
    write_stop_take_profit_source: bool | None = None,
    confirm_tiny_live_stop_take_profit_source: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the R248 source gate packet and optionally append its preview ledger."""
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    record_requested = bool(record_stop_take_profit_source_preview or write_stop_take_profit_source)
    confirmation = (
        confirm_tiny_live_stop_take_profit_source_preview
        if confirm_tiny_live_stop_take_profit_source_preview is not None
        else confirm_tiny_live_stop_take_profit_source
    )
    confirmation_valid = confirmation == CONFIRM_TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_PREVIEW_RECORDING_PHRASE

    try:
        latest_r247 = load_latest_tiny_live_executable_payload_preview(
            log_dir=resolved_log_dir, official_lane_key=official_lane_key
        )
        latest_r246 = load_latest_tiny_live_order_payload_refresh_write_gate(
            log_dir=resolved_log_dir, official_lane_key=official_lane_key
        )
        latest_r245 = load_latest_tiny_live_order_payload_refresh_preview(
            log_dir=resolved_log_dir, official_lane_key=official_lane_key
        )
        latest_r244 = load_latest_tiny_live_leverage_notional_risk_contract_write_gate(
            log_dir=resolved_log_dir, official_lane_key=official_lane_key
        )
        latest_r242 = load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
            log_dir=resolved_log_dir, official_lane_key=official_lane_key
        )
        latest_r238 = load_latest_tiny_live_order_preflight_write_gate(
            log_dir=resolved_log_dir, official_lane_key=official_lane_key
        )
        risk_contract = load_adjusted_tiny_live_risk_contract(
            risk_contract_config_path=risk_contract_config_path,
            official_lane_key=official_lane_key,
        )
        precision = _precision_summary(latest_r242)
        payload_context = _payload_context_summary(latest_r246, latest_r247)
        candidates = extract_stop_take_profit_source_candidates(
            latest_r247=latest_r247,
            latest_r246=latest_r246,
            latest_r245=latest_r245,
            latest_r238=latest_r238,
            tick_size=precision.get("tick_size"),
            official_lane_key=official_lane_key,
        )
        selected = select_stop_take_profit_source(candidates)
        direction_validation = validate_short_stop_take_profit_levels(selected)
        risk_validation = compute_stop_take_profit_risk_preview(
            selected_source=selected,
            quantity_preview=payload_context.get("quantity_preview"),
            max_loss_usdt=risk_contract.get("max_loss_usdt"),
            expected_risk_reward_ratio=_number(risk_contract.get("risk_reward_ratio")) or 2.0,
        )
        preview = build_stop_take_profit_source_preview(
            selected_source=selected,
            official_lane_key=official_lane_key,
            symbol=str(payload_context.get("symbol") or "BTCUSDT"),
        )
        preview_validation = validate_stop_take_profit_source_preview(
            preview,
            selected_source=selected,
            direction_validation=direction_validation,
            risk_reward_validation=risk_validation,
        )
        input_summary = _build_input_summary(
            latest_r247=latest_r247,
            latest_r246=latest_r246,
            latest_r245=latest_r245,
            latest_r244=latest_r244,
            latest_r242=latest_r242,
            risk_contract=risk_contract,
            selected_source=selected,
        )
        matrix = build_stop_take_profit_source_gate_matrix(
            input_summary=input_summary,
            selected_source=selected,
            short_direction_validation=direction_validation,
            risk_reward_validation=risk_validation,
            preview_validation=preview_validation,
            record_confirmed=record_requested and confirmation_valid,
            recorded=False,
        )

        recorded = False
        if record_requested and not confirmation_valid:
            status = TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_REJECTED
            overall = TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_REJECTED_BAD_CONFIRMATION
        elif matrix["stop_take_profit_preview_ready"] is not True:
            status = TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_BLOCKED
            overall = classify_tiny_live_stop_take_profit_source_gate_status(
                matrix,
                record_requested=record_requested,
                confirmation_valid=confirmation_valid,
            )
        elif record_requested and confirmation_valid:
            status = TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_RECORDED
            recorded = True
            matrix = build_stop_take_profit_source_gate_matrix(
                input_summary=input_summary,
                selected_source=selected,
                short_direction_validation=direction_validation,
                risk_reward_validation=risk_validation,
                preview_validation=preview_validation,
                record_confirmed=True,
                recorded=True,
            )
            overall = TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_RECORDED_EXECUTABLE_WRITE_STILL_BLOCKED
        else:
            status = TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_READY
            overall = TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_READY_FOR_REVIEW

        operator_packet = build_operator_stop_take_profit_source_packet(matrix)
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "stop_take_profit_source_preview_recorded": recorded,
                "record_stop_take_profit_source_preview_requested": record_requested,
                "confirmation_valid": confirmation_valid,
                "target_scope": _target_scope(official_lane_key),
                "input_summary": input_summary,
                "risk_contract_summary": _risk_contract_summary(risk_contract),
                "payload_context_summary": payload_context,
                "precision_summary": precision,
                "stop_take_profit_source_candidates": candidates,
                "selected_stop_take_profit_source": selected,
                "short_direction_validation": direction_validation,
                "risk_reward_validation": risk_validation,
                "stop_take_profit_source_preview": preview,
                "stop_take_profit_source_gate_matrix": matrix,
                "operator_stop_take_profit_source_packet": operator_packet,
                "recommended_next_operator_move": _recommended_next_operator_move(matrix),
                "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
                "stop_take_profit_source_overall_status": overall,
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if recorded:
            record = append_tiny_live_stop_take_profit_source_gate_record(payload, log_dir=resolved_log_dir)
            payload["stop_take_profit_source_gate_record_id"] = record["stop_take_profit_source_gate_record_id"]
            payload["ledger_path"] = str(tiny_live_stop_take_profit_source_gate_records_path(resolved_log_dir))
        return payload
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_stop_take_profit_source_gate_matrix(
            input_summary=_empty_input_summary(),
            selected_source=_empty_selected_source(),
            short_direction_validation={"valid": False, "errors": ["stop_take_profit_source_gate_error"], "warnings": []},
            risk_reward_validation=_empty_risk_reward_validation(),
            preview_validation={"valid": False, "errors": ["stop_take_profit_source_gate_error"], "warnings": []},
            record_confirmed=False,
            recorded=False,
        )
        return _sanitize(
            {
                "status": TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "stop_take_profit_source_preview_recorded": False,
                "record_stop_take_profit_source_preview_requested": record_requested,
                "confirmation_valid": confirmation_valid,
                "target_scope": _target_scope(official_lane_key),
                "input_summary": _empty_input_summary(),
                "risk_contract_summary": _risk_contract_summary({}),
                "payload_context_summary": _empty_payload_context_summary(),
                "precision_summary": _empty_precision_summary(),
                "stop_take_profit_source_candidates": [],
                "selected_stop_take_profit_source": _empty_selected_source(),
                "short_direction_validation": {"valid": False, "errors": ["stop_take_profit_source_gate_error"], "warnings": []},
                "risk_reward_validation": _empty_risk_reward_validation(),
                "stop_take_profit_source_preview": build_stop_take_profit_source_preview(
                    selected_source=_empty_selected_source(),
                    official_lane_key=official_lane_key,
                    symbol="BTCUSDT",
                ),
                "stop_take_profit_source_gate_matrix": matrix,
                "operator_stop_take_profit_source_packet": build_operator_stop_take_profit_source_packet(matrix),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R248 source gate error before any executable payload write.",
                "stop_take_profit_source_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_executable_payload_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_executable_payload_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        preview = record.get("executable_payload_readiness_preview")
        preview = preview if isinstance(preview, Mapping) else {}
        validation = validate_executable_payload_preview(preview, input_summary=record.get("input_summary") or {})
        if (
            str(target.get("official_lane_key") or preview.get("official_lane_key") or "") == official_lane_key
            and record.get("executable_payload_preview_recorded") is True
            and validation.get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_order_payload_refresh_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_order_payload_refresh_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        payload = _r246_payload(record)
        validation = validate_refreshed_non_executable_payload_artifact(payload) if payload else {"valid": False}
        if (
            str(target.get("official_lane_key") or payload.get("official_lane_key") or "") == official_lane_key
            and record.get("payload_refresh_written") is True
            and validation.get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_order_payload_refresh_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_order_payload_refresh_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        preview = record.get("refreshed_non_executable_payload_preview")
        preview = preview if isinstance(preview, Mapping) else {}
        validation = validate_refreshed_payload_preview(preview) if preview else {"valid": False}
        if (
            str(target.get("official_lane_key") or preview.get("official_lane_key") or "") == official_lane_key
            and record.get("payload_refresh_preview_recorded") is True
            and validation.get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_leverage_notional_risk_contract_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_leverage_notional_risk_contract_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        preview = record.get("adjusted_contract_write_preview")
        preview = preview if isinstance(preview, Mapping) else {}
        contract = preview.get("proposed_adjusted_contract")
        contract = contract if isinstance(contract, Mapping) else {}
        if (
            str(target.get("official_lane_key") or contract.get("official_lane_key") or "") == official_lane_key
            and record.get("risk_contract_written") is True
            and validate_adjusted_risk_contract(contract).get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_binance_readonly_precision_mark_price_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        result = record.get("binance_readonly_result")
        result = result if isinstance(result, Mapping) else {}
        precision = result.get("precision_snapshot") if isinstance(result.get("precision_snapshot"), Mapping) else {}
        mark = result.get("mark_price_snapshot") if isinstance(result.get("mark_price_snapshot"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or "") == official_lane_key
            and record.get("readonly_fetch_performed") is True
            and precision.get("found") is True
            and mark.get("found") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_order_preflight_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_order_preflight_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        preflight = record.get("order_preflight") if isinstance(record.get("order_preflight"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or preflight.get("official_lane_key") or "") == official_lane_key
            and record.get("order_preflight_written") is True
            and validate_order_preflight_object(preflight).get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_adjusted_tiny_live_risk_contract(
    *,
    risk_contract_config_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    path = Path(risk_contract_config_path) if risk_contract_config_path else DEFAULT_RISK_CONTRACT_CONFIG_PATH
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    contracts = data.get("risk_contracts") if isinstance(data, Mapping) else []
    for contract in contracts if isinstance(contracts, list) else []:
        if isinstance(contract, Mapping) and contract.get("official_lane_key") == official_lane_key:
            return _sanitize(dict(contract))
    return {}


def extract_stop_take_profit_source_candidates(
    *,
    latest_r247: Mapping[str, Any],
    latest_r246: Mapping[str, Any],
    latest_r245: Mapping[str, Any],
    latest_r238: Mapping[str, Any],
    tick_size: Any,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> list[dict[str, Any]]:
    surfaces = [
        ("r247_executable_payload_preview", latest_r247),
        ("r246_order_payload_refresh_write_gate", latest_r246),
        ("r245_order_payload_refresh_preview", latest_r245),
        ("r238_order_preflight_write_gate", latest_r238),
    ]
    candidates: list[dict[str, Any]] = []
    for source_name, record in surfaces:
        if not record:
            continue
        record_id = _record_id(record)
        for item in _walk_mappings(record):
            if not _record_matches_lane(item, official_lane_key):
                continue
            raw_stop = _first_number(item, ("final_stop_price", "stop_price", "stop_loss_price"))
            raw_tp = _first_number(
                item,
                ("final_take_profit_price", "take_profit_price", "tp_price", "target_price"),
            )
            if raw_stop is None and raw_tp is None:
                continue
            entry = _first_number(
                item,
                ("entry_reference_price", "reference_price", "entry_price", "mark_price", "candidate_price"),
            )
            rounded_stop = round_price_to_tick(raw_stop, tick_size) if raw_stop is not None else None
            rounded_tp = round_price_to_tick(raw_tp, tick_size) if raw_tp is not None else None
            blocked_by: list[str] = []
            if entry is None:
                blocked_by.append("entry_reference_price_missing")
            if raw_stop is None:
                blocked_by.append("stop_price_missing")
            if raw_tp is None:
                blocked_by.append("take_profit_price_missing")
            if rounded_stop is None and raw_stop is not None:
                blocked_by.append("stop_price_rounding_failed")
            if rounded_tp is None and raw_tp is not None:
                blocked_by.append("take_profit_price_rounding_failed")
            candidates.append(
                {
                    "source_name": source_name,
                    "source_record_id": record_id,
                    "entry_reference_price": entry,
                    "raw_stop_price": raw_stop,
                    "raw_take_profit_price": raw_tp,
                    "rounded_stop_price": rounded_stop,
                    "rounded_take_profit_price": rounded_tp,
                    "source_valid": not blocked_by,
                    "blocked_by": blocked_by,
                }
            )
    return _sanitize(candidates)


def select_stop_take_profit_source(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    for candidate in candidates:
        if candidate.get("source_valid") is True:
            return _sanitize(dict(candidate))
    if candidates:
        return _sanitize(dict(candidates[0]))
    return _empty_selected_source()


def round_price_to_tick(price: Any, tick_size: Any) -> float | None:
    price_dec = _decimal(price)
    tick_dec = _decimal(tick_size)
    if price_dec is None or tick_dec is None or tick_dec <= 0:
        return None
    rounded = (price_dec / tick_dec).to_integral_value(rounding=ROUND_HALF_UP) * tick_dec
    return _float(rounded)


def validate_short_stop_take_profit_levels(selected_source: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    entry = _number(selected_source.get("entry_reference_price"))
    stop = _number(selected_source.get("rounded_stop_price"))
    tp = _number(selected_source.get("rounded_take_profit_price"))
    if entry is None or entry <= 0:
        errors.append("entry_reference_price_invalid")
    if stop is None:
        errors.append("stop_price_missing")
    if tp is None:
        errors.append("take_profit_price_missing")
    if entry is not None and stop is not None and stop <= entry:
        errors.append("short_stop_price_must_be_above_entry_reference_price")
    if entry is not None and tp is not None and tp >= entry:
        errors.append("short_take_profit_price_must_be_below_entry_reference_price")
    if selected_source.get("source_valid") is not True:
        errors.extend(str(item) for item in selected_source.get("blocked_by") or ["source_invalid"])
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": warnings}


def compute_stop_take_profit_risk_preview(
    *,
    selected_source: Mapping[str, Any],
    quantity_preview: Any,
    max_loss_usdt: Any,
    expected_risk_reward_ratio: float = 2.0,
    tolerance: float = 0.05,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    entry = _number(selected_source.get("entry_reference_price"))
    stop = _number(selected_source.get("rounded_stop_price"))
    tp = _number(selected_source.get("rounded_take_profit_price"))
    quantity = _number(quantity_preview)
    max_loss = _number(max_loss_usdt)
    loss = None
    reward = None
    ratio = None
    max_loss_ok = None
    if entry is None or stop is None or tp is None:
        errors.append("risk_preview_requires_entry_stop_and_take_profit")
    if quantity is None or quantity <= 0:
        errors.append("quantity_preview_invalid")
    if max_loss is None or max_loss <= 0:
        errors.append("max_loss_usdt_invalid")
    if entry is not None and stop is not None and tp is not None and quantity is not None and quantity > 0:
        loss = max((stop - entry) * quantity, 0)
        reward = max((entry - tp) * quantity, 0)
        ratio = reward / loss if loss > 0 else None
        if max_loss is not None:
            max_loss_ok = loss <= max_loss + 0.01
            if not max_loss_ok:
                errors.append("loss_usdt_preview_exceeds_max_loss")
        if ratio is None:
            errors.append("risk_reward_ratio_unavailable")
        elif abs(ratio - expected_risk_reward_ratio) > tolerance:
            errors.append("risk_reward_ratio_not_close_to_2")
    return _sanitize(
        {
            "valid": not errors,
            "entry_reference_price": entry,
            "stop_price": stop,
            "take_profit_price": tp,
            "quantity_preview": quantity,
            "loss_usdt_preview": loss,
            "reward_usdt_preview": reward,
            "risk_reward_ratio_preview": ratio,
            "max_loss_usdt": max_loss,
            "max_loss_ok": max_loss_ok,
            "errors": _dedupe(errors),
            "warnings": warnings,
        }
    )


def build_stop_take_profit_source_preview(
    *,
    selected_source: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    return _sanitize(
        {
            "preview_only": True,
            "artifact_written": False,
            "executable": False,
            "signed": False,
            "submit_allowed": False,
            "binance_call_allowed": False,
            "network_allowed": False,
            "official_lane_key": official_lane_key,
            "symbol": symbol,
            "side": "SELL",
            "stop_payload_preview": {
                "preview_only": True,
                "executable": False,
                "signed": False,
                "order_type": "STOP_MARKET_PREVIEW_ONLY",
                "side": "BUY",
                "reduce_only": True,
                "stop_price": selected_source.get("rounded_stop_price"),
            },
            "take_profit_payload_preview": {
                "preview_only": True,
                "executable": False,
                "signed": False,
                "order_type": "TAKE_PROFIT_MARKET_PREVIEW_ONLY",
                "side": "BUY",
                "reduce_only": True,
                "take_profit_price": selected_source.get("rounded_take_profit_price"),
            },
        }
    )


def validate_stop_take_profit_source_preview(
    preview: Mapping[str, Any],
    *,
    selected_source: Mapping[str, Any],
    direction_validation: Mapping[str, Any],
    risk_reward_validation: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    for key in ("preview_only",):
        if preview.get(key) is not True:
            errors.append(f"{key}_invalid")
    for key in ("artifact_written", "executable", "signed", "submit_allowed", "binance_call_allowed", "network_allowed"):
        if preview.get(key) is not False:
            errors.append(f"{key}_invalid")
    stop_preview = preview.get("stop_payload_preview") if isinstance(preview.get("stop_payload_preview"), Mapping) else {}
    tp_preview = (
        preview.get("take_profit_payload_preview")
        if isinstance(preview.get("take_profit_payload_preview"), Mapping)
        else {}
    )
    if stop_preview.get("side") != "BUY" or stop_preview.get("reduce_only") is not True:
        errors.append("stop_payload_preview_side_reduce_only_invalid")
    if tp_preview.get("side") != "BUY" or tp_preview.get("reduce_only") is not True:
        errors.append("take_profit_payload_preview_side_reduce_only_invalid")
    if selected_source.get("source_valid") is not True:
        errors.append("selected_source_invalid")
    if direction_validation.get("valid") is not True:
        errors.append("short_direction_validation_invalid")
    if risk_reward_validation.get("valid") is not True:
        errors.append("risk_reward_validation_invalid")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": []}


def build_stop_take_profit_source_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    selected_source: Mapping[str, Any],
    short_direction_validation: Mapping[str, Any],
    risk_reward_validation: Mapping[str, Any],
    preview_validation: Mapping[str, Any],
    record_confirmed: bool,
    recorded: bool,
) -> dict[str, Any]:
    blocked_by: list[str] = []
    if input_summary.get("local_stop_take_profit_source_found") is not True:
        blocked_by.append("local_stop_take_profit_source_missing")
    if selected_source.get("source_valid") is not True:
        blocked_by.extend(str(item) for item in selected_source.get("blocked_by") or ["source_invalid"])
    if short_direction_validation.get("valid") is not True:
        blocked_by.extend(str(item) for item in short_direction_validation.get("errors") or ["direction_invalid"])
    if risk_reward_validation.get("valid") is not True:
        blocked_by.extend(str(item) for item in risk_reward_validation.get("errors") or ["risk_reward_invalid"])
    if preview_validation.get("valid") is not True:
        blocked_by.extend(str(item) for item in preview_validation.get("errors") or ["preview_invalid"])
    ready = not blocked_by
    return {
        "source_found": input_summary.get("local_stop_take_profit_source_found") is True,
        "source_valid": selected_source.get("source_valid") is True,
        "directionally_valid": short_direction_validation.get("valid") is True,
        "risk_reward_valid": risk_reward_validation.get("valid") is True,
        "stop_take_profit_preview_ready": ready,
        "record_confirmed": bool(record_confirmed),
        "recorded": bool(recorded),
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blocked_by),
    }


def build_operator_stop_take_profit_source_packet(
    stop_take_profit_source_gate_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    ready = stop_take_profit_source_gate_matrix.get("stop_take_profit_preview_ready") is True
    recorded = stop_take_profit_source_gate_matrix.get("recorded") is True
    if recorded:
        action = "REVIEW_R248_STOP_TP_SOURCE"
    elif ready:
        action = "REVIEW_R248_STOP_TP_SOURCE"
    elif stop_take_profit_source_gate_matrix.get("source_found") is not True:
        action = "FIX_STOP_TP_SOURCE"
    else:
        action = "WAIT"
    return {
        "operator_should_review_stop_take_profit_source": bool(ready or recorded),
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


def classify_tiny_live_stop_take_profit_source_gate_status(
    matrix: Mapping[str, Any],
    *,
    record_requested: bool = False,
    confirmation_valid: bool = False,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_REJECTED_BAD_CONFIRMATION
    if matrix.get("recorded") is True:
        return TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_RECORDED_EXECUTABLE_WRITE_STILL_BLOCKED
    if matrix.get("source_found") is not True:
        return TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_MISSING_SOURCE
    if matrix.get("directionally_valid") is not True:
        return TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_DIRECTIONAL_VALIDATION
    if matrix.get("risk_reward_valid") is not True:
        return TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_RISK_VALIDATION
    if matrix.get("stop_take_profit_preview_ready") is True:
        return TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_READY_FOR_REVIEW
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_stop_take_profit_source_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_stop_take_profit_source_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "stop_take_profit_source_gate_record_id": record.get("stop_take_profit_source_gate_record_id")
            or f"r248_stop_take_profit_source_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "stop_take_profit_source_preview_recorded": record.get("stop_take_profit_source_preview_recorded") is True,
            "record_stop_take_profit_source_preview_requested": (
                record.get("record_stop_take_profit_source_preview_requested") is True
            ),
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "risk_contract_summary": dict(record.get("risk_contract_summary") or {}),
            "payload_context_summary": dict(record.get("payload_context_summary") or {}),
            "precision_summary": dict(record.get("precision_summary") or {}),
            "selected_stop_take_profit_source": dict(record.get("selected_stop_take_profit_source") or {}),
            "short_direction_validation": dict(record.get("short_direction_validation") or {}),
            "risk_reward_validation": dict(record.get("risk_reward_validation") or {}),
            "stop_take_profit_source_preview": dict(record.get("stop_take_profit_source_preview") or {}),
            "stop_take_profit_source_gate_matrix": dict(record.get("stop_take_profit_source_gate_matrix") or {}),
            "operator_stop_take_profit_source_packet": dict(record.get("operator_stop_take_profit_source_packet") or {}),
            "stop_take_profit_source_overall_status": record.get("stop_take_profit_source_overall_status"),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_stop_take_profit_source_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_stop_take_profit_source_gate_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_stop_take_profit_source_gate_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    selected = latest.get("selected_stop_take_profit_source")
    selected = selected if isinstance(selected, Mapping) else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_recorded": latest.get("stop_take_profit_source_preview_recorded") is True,
        "latest_source_name": selected.get("source_name"),
        "latest_stop_price": selected.get("rounded_stop_price"),
        "latest_take_profit_price": selected.get("rounded_take_profit_price"),
    }


def tiny_live_stop_take_profit_source_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_stop_take_profit_source_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r247: Mapping[str, Any],
    latest_r246: Mapping[str, Any],
    latest_r245: Mapping[str, Any],
    latest_r244: Mapping[str, Any],
    latest_r242: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    selected_source: Mapping[str, Any],
) -> dict[str, Any]:
    precision = _precision_summary(latest_r242)
    return {
        "r247_executable_payload_preview_found": bool(latest_r247),
        "r246_payload_refresh_write_found": bool(latest_r246),
        "r245_payload_refresh_preview_found": bool(latest_r245),
        "r244_adjusted_contract_found": bool(latest_r244) or bool(risk_contract),
        "r244_adjusted_contract_valid": _risk_contract_valid(risk_contract),
        "r242_precision_found": precision.get("tick_size") is not None,
        "r242_precision_valid": precision.get("tick_size") is not None and _number(precision.get("tick_size")) > 0,
        "local_stop_take_profit_source_found": selected_source.get("source_name") is not None,
    }


def _risk_contract_summary(contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "margin_budget_usdt": _int_if_whole(contract.get("margin_budget_usdt")),
        "leverage": _int_if_whole(contract.get("leverage")),
        "max_notional_usdt": _int_if_whole(contract.get("max_notional_usdt")),
        "max_loss_usdt": _number(contract.get("max_loss_usdt")) if contract else 4.44,
        "max_loss_requires_review": contract.get("max_loss_requires_review") is True,
    }


def _payload_context_summary(latest_r246: Mapping[str, Any], latest_r247: Mapping[str, Any]) -> dict[str, Any]:
    payload = _r246_payload(latest_r246)
    if not payload:
        preview = latest_r247.get("executable_payload_readiness_preview")
        preview = preview if isinstance(preview, Mapping) else {}
        payload = preview.get("base_payload") if isinstance(preview.get("base_payload"), Mapping) else {}
    return {
        "quantity_preview": _number(payload.get("quantity") or payload.get("quantity_preview")),
        "notional_after_rounding": _number(payload.get("notional_after_rounding")),
        "entry_reference_price": _number(payload.get("entry_reference_price") or payload.get("reference_price")),
        "side": payload.get("side") or "SELL",
        "position_side": payload.get("position_side"),
        "symbol": payload.get("symbol") or "BTCUSDT",
    }


def _precision_summary(latest_r242: Mapping[str, Any]) -> dict[str, Any]:
    result = latest_r242.get("binance_readonly_result") if isinstance(latest_r242.get("binance_readonly_result"), Mapping) else {}
    precision = result.get("precision_snapshot") if isinstance(result.get("precision_snapshot"), Mapping) else {}
    return {
        "tick_size": _number(precision.get("tick_size")),
        "price_precision": precision.get("price_precision"),
        "source": "r242_readonly",
    }


def _target_scope(lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, _ = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "stop_take_profit_source_gate_only": True,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def _recommended_next_operator_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("recorded") is True:
        return "REVIEW_R248_STOP_TP_SOURCE"
    if matrix.get("stop_take_profit_preview_ready") is True:
        return "REVIEW_R248_STOP_TP_SOURCE"
    if matrix.get("source_found") is not True:
        return "FIX_STOP_TP_SOURCE"
    return "WAIT"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("recorded") is True:
        return "Implement R249 to consume R248 and R247, write an executable payload artifact only under exact confirmation, and still block signing/Binance/order submission."
    if matrix.get("source_found") is not True:
        return "Provide or wire a local explicit stop/take-profit source before R249 executable payload writing."
    if matrix.get("stop_take_profit_preview_ready") is True:
        return "Record the R248 preview with the exact confirmation phrase before starting R249."
    return "Repair R248 directional or risk validation before any executable payload write gate."


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


def _r246_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("refreshed_payload_artifact", "order_payload"):
        value = record.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    lane = record.get("official_lane_key")
    if lane is not None:
        return str(lane) == official_lane_key
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    values = {
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
    }
    present = {key: record.get(key) for key in values if record.get(key) is not None}
    return not present or all(str(present[key]) == values[key] for key in present)


def _walk_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mappings(child)


def _record_id(record: Mapping[str, Any]) -> Any:
    for key in (
        "executable_payload_preview_record_id",
        "gate_record_id",
        "order_payload_refresh_preview_record_id",
        "order_preflight_id",
        "record_id",
        "event_id",
    ):
        if record.get(key):
            return record.get(key)
    return None


def _first_number(record: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        number = _number(record.get(key))
        if number is not None:
            return number
    return None


def _risk_contract_valid(contract: Mapping[str, Any]) -> bool:
    return (
        _number(contract.get("margin_budget_usdt")) == 44
        and _number(contract.get("leverage")) == 10
        and _number(contract.get("max_notional_usdt")) == 440
        and _number(contract.get("max_position_notional_usdt")) == 440
        and _number(contract.get("max_loss_usdt")) == 4.44
        and contract.get("max_loss_requires_review") is True
    )


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r247_executable_payload_preview_found": False,
        "r246_payload_refresh_write_found": False,
        "r245_payload_refresh_preview_found": False,
        "r244_adjusted_contract_found": False,
        "r244_adjusted_contract_valid": False,
        "r242_precision_found": False,
        "r242_precision_valid": False,
        "local_stop_take_profit_source_found": False,
    }


def _empty_selected_source() -> dict[str, Any]:
    return {
        "source_name": None,
        "source_record_id": None,
        "entry_reference_price": None,
        "raw_stop_price": None,
        "raw_take_profit_price": None,
        "rounded_stop_price": None,
        "rounded_take_profit_price": None,
        "source_valid": False,
        "blocked_by": ["local_stop_take_profit_source_missing"],
    }


def _empty_risk_reward_validation() -> dict[str, Any]:
    return {
        "valid": False,
        "entry_reference_price": None,
        "stop_price": None,
        "take_profit_price": None,
        "quantity_preview": None,
        "loss_usdt_preview": None,
        "reward_usdt_preview": None,
        "risk_reward_ratio_preview": None,
        "max_loss_usdt": 4.44,
        "max_loss_ok": None,
        "errors": ["risk_preview_requires_entry_stop_and_take_profit"],
        "warnings": [],
    }


def _empty_payload_context_summary() -> dict[str, Any]:
    return {
        "quantity_preview": None,
        "notional_after_rounding": None,
        "entry_reference_price": None,
        "side": "SELL",
        "position_side": None,
    }


def _empty_precision_summary() -> dict[str, Any]:
    return {"tick_size": None, "price_precision": None, "source": "r242_readonly"}


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key).split("|")
    if len(parts) != 4:
        return ("BTCUSDT", "8m", "short", "ladder_close_50_618")
    return parts[0], parts[1], parts[2], parts[3]


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    try:
        if value is None or value == "":
            return None
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _float(value: Decimal) -> float:
    return float(value.normalize())


def _int_if_whole(value: Any) -> int | float | None:
    number = _number(value)
    if number is None:
        return None
    return int(number) if number.is_integer() else number


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
