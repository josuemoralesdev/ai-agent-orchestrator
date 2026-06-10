"""R241 tiny-live precision and mark-price preview.

This module is read-only except for its own append-only preview ledger after
the exact R241 confirmation phrase. It never calls Binance/network endpoints,
creates executable payloads, signs requests, places orders, mutates configs/env,
or disables the kill switch.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
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
    load_latest_tiny_live_10_of_10_ready_packet as _load_latest_tiny_live_10_of_10_ready_packet,
    load_latest_tiny_live_risk_contract_config_write_gate as _load_latest_tiny_live_risk_contract_config_write_gate,
    load_tiny_live_risk_contract_config,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_write_gate import (
    LEDGER_FILENAME as R240_LEDGER_FILENAME,
    load_latest_tiny_live_order_payload_preview,
    load_latest_tiny_live_order_preflight_write_gate as _load_latest_tiny_live_order_preflight_write_gate,
    load_tiny_live_order_payload_write_gate_records,
    validate_non_executable_order_payload_artifact,
)
from src.app.hammer_radar.operator.tiny_live_order_preflight_preview import (
    load_lane_controls_readonly,
    load_latest_tiny_live_lane_arm_write_gate as _load_latest_tiny_live_lane_arm_write_gate,
)
from src.app.hammer_radar.operator.tiny_live_order_preflight_write_gate import (
    LEDGER_FILENAME as R238_LEDGER_FILENAME,
    validate_order_preflight_object,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_preview import (
    LEDGER_FILENAME as R239_LEDGER_FILENAME,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    LEDGER_FILENAME as R230_LEDGER_FILENAME,
    validate_tiny_live_risk_contract_config_entry,
)

TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY = "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY"
TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_REJECTED = "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_REJECTED"
TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_RECORDED = "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_RECORDED"
TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED = "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED"
TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_ERROR = "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_ERROR"

TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY_FOR_FUTURE_GATE = (
    "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY_FOR_FUTURE_GATE"
)
TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_NEEDS_BINANCE_READONLY_CHECK = (
    "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_NEEDS_BINANCE_READONLY_CHECK"
)
TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_PAYLOAD = (
    "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_PAYLOAD"
)
TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_PREFLIGHT = (
    "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_PREFLIGHT"
)
TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_RISK_CONTRACT = (
    "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_RISK_CONTRACT"
)
TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_VALIDATION = (
    "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW"
LEDGER_FILENAME = "tiny_live_precision_and_mark_price_preview.ndjson"
CONFIRM_TINY_LIVE_PRECISION_MARK_PRICE_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE PRECISION AND MARK PRICE PREVIEW RECORDING ONLY; "
    "NO BINANCE CALL; NO ORDER PAYLOAD; NO ORDER."
)
FUTURE_CONFIRMATION_PHRASE_SUGGESTION = (
    "I CONFIRM TINY LIVE BINANCE READONLY PRECISION MARK PRICE CHECK ONLY; "
    "NO ORDER ENDPOINT; NO ORDER PAYLOAD; NO ORDER."
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE

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
    "precision_mark_price_preview_only": True,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R240_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R239_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R238_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R236_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R230_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/market_intelligence_snapshots.ndjson",
    "logs/hammer_radar_forward/candles_BTCUSDT_8m.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_precision_and_mark_price_preview(
    *,
    log_dir: str | Path | None = None,
    record_precision_mark_price_preview: bool = False,
    confirm_tiny_live_precision_mark_price_preview: str | None = None,
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
        confirm_tiny_live_precision_mark_price_preview
        == CONFIRM_TINY_LIVE_PRECISION_MARK_PRICE_PREVIEW_RECORDING_PHRASE
    )
    try:
        latest_r240 = load_latest_tiny_live_order_payload_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r239 = load_latest_tiny_live_order_payload_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r238 = load_latest_tiny_live_order_preflight_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r236 = load_latest_tiny_live_lane_arm_write_gate(
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
            latest_r240=latest_r240,
            latest_r239=latest_r239,
            latest_r238=latest_r238,
            latest_r236=latest_r236,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_config=risk_config,
        )
        risk_summary = _risk_contract_summary(risk_config)
        order_payload_summary = _order_payload_artifact_summary(latest_r240)
        symbol, _, direction, _ = _lane_parts(official_lane_key)
        precision_snapshot = discover_local_symbol_precision_snapshot(
            log_dir=resolved_log_dir,
            config_dir=risk_path.parent,
            symbol=symbol,
        )
        price_snapshot = discover_local_mark_or_candidate_price_snapshot(
            log_dir=resolved_log_dir,
            symbol=symbol,
            now=generated_at,
        )
        quantity_preview = build_quantity_preview_if_safe(
            notional_cap_usdt=risk_summary.get("max_notional_usdt"),
            precision_snapshot=precision_snapshot,
            price_snapshot=price_snapshot,
        )
        validation = validate_precision_and_mark_price_preview(
            input_summary=input_summary,
            order_payload_artifact_summary=order_payload_summary,
            local_precision_snapshot=precision_snapshot,
            local_mark_or_candidate_price_snapshot=price_snapshot,
            quantity_preview=quantity_preview,
        )
        matrix = build_precision_and_mark_price_gate_matrix(
            input_summary=input_summary,
            validation=validation,
            local_precision_snapshot=precision_snapshot,
            local_mark_or_candidate_price_snapshot=price_snapshot,
            quantity_preview=quantity_preview,
        )
        operator_packet = build_operator_precision_and_mark_price_review_packet(matrix)
        overall = classify_tiny_live_precision_and_mark_price_preview_status(
            input_summary=input_summary,
            validation=validation,
            gate_matrix=matrix,
        )
        if record_precision_mark_price_preview and not confirmation_valid:
            status = TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_REJECTED
        elif record_precision_mark_price_preview and confirmation_valid and validation.get("valid") is True:
            status = TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_RECORDED
        elif overall in {
            TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY_FOR_FUTURE_GATE,
            TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_NEEDS_BINANCE_READONLY_CHECK,
        }:
            status = TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY
        else:
            status = TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "precision_mark_price_preview_recorded": False,
            "precision_mark_price_preview_record_id": None,
            "record_precision_mark_price_preview_requested": bool(record_precision_mark_price_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "official_lane_key": official_lane_key,
                "symbol": symbol,
                "direction": direction,
                "precision_mark_price_preview_only": True,
                "order_payload_artifact_exists": input_summary["r240_payload_found"],
                "executable_payload_created": False,
                "signed_order_request_created": False,
                "order_placed": False,
                "binance_call_allowed": False,
                "network_allowed": False,
            },
            "input_summary": input_summary,
            "risk_contract_summary": risk_summary,
            "order_payload_artifact_summary": order_payload_summary,
            "lane_controls_readonly_summary": lane_controls,
            "local_precision_snapshot": precision_snapshot,
            "local_mark_or_candidate_price_snapshot": price_snapshot,
            "quantity_preview": quantity_preview,
            "precision_mark_price_preview_validation": validation,
            "precision_mark_price_gate_matrix": matrix,
            "operator_precision_mark_price_review_packet": operator_packet,
            "future_confirmation_phrase_suggestion": FUTURE_CONFIRMATION_PHRASE_SUGGESTION,
            "recommended_next_operator_move": _recommended_next_operator_move(operator_packet),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
            "precision_mark_price_preview_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if status == TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_RECORDED:
            record = append_tiny_live_precision_and_mark_price_preview_record(payload, log_dir=resolved_log_dir)
            payload["precision_mark_price_preview_recorded"] = True
            payload["precision_mark_price_preview_record_id"] = record["preview_record_id"]
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        matrix = build_precision_and_mark_price_gate_matrix(
            input_summary=_empty_input_summary(),
            validation={"valid": False, "errors": ["precision_mark_price_preview_error"], "warnings": []},
            local_precision_snapshot=_empty_precision_snapshot("BTCUSDT"),
            local_mark_or_candidate_price_snapshot=_empty_price_snapshot("BTCUSDT"),
            quantity_preview=_blocked_quantity_preview(["precision_mark_price_preview_error"]),
        )
        return _sanitize(
            {
                "status": TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "precision_mark_price_preview_recorded": False,
                "record_precision_mark_price_preview_requested": bool(record_precision_mark_price_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {"official_lane_key": official_lane_key},
                "input_summary": _empty_input_summary(),
                "risk_contract_summary": _empty_risk_contract_summary(official_lane_key),
                "order_payload_artifact_summary": _empty_order_payload_artifact_summary(),
                "local_precision_snapshot": _empty_precision_snapshot("BTCUSDT"),
                "local_mark_or_candidate_price_snapshot": _empty_price_snapshot("BTCUSDT"),
                "quantity_preview": _blocked_quantity_preview(["precision_mark_price_preview_error"]),
                "precision_mark_price_preview_validation": {
                    "valid": False,
                    "errors": ["precision_mark_price_preview_error"],
                    "warnings": [],
                },
                "precision_mark_price_gate_matrix": matrix,
                "operator_precision_mark_price_review_packet": build_operator_precision_and_mark_price_review_packet(matrix),
                "recommended_next_operator_move": "FIX_BLOCKER",
                "recommended_next_engineering_move": "Fix R241 precision and mark-price preview error before any later gate.",
                "precision_mark_price_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_order_payload_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_order_payload_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        artifact = record.get("order_payload") if isinstance(record.get("order_payload"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or artifact.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == "TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_WRITTEN"
            and record.get("order_payload_written") is True
            and validate_non_executable_order_payload_artifact(artifact).get("valid") is True
        ):
            return _sanitize({**record, "r240_payload_found": True})
    return {}


def load_latest_tiny_live_order_preflight_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return _load_latest_tiny_live_order_preflight_write_gate(
        log_dir=log_dir,
        official_lane_key=official_lane_key,
    )


def load_latest_tiny_live_lane_arm_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return _load_latest_tiny_live_lane_arm_write_gate(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_risk_contract_config_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return _load_latest_tiny_live_risk_contract_config_write_gate(
        log_dir=log_dir,
        official_lane_key=official_lane_key,
    )


def load_latest_tiny_live_10_of_10_ready_packet(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return _load_latest_tiny_live_10_of_10_ready_packet(
        log_dir=log_dir,
        official_lane_key=official_lane_key,
    )


def discover_local_symbol_precision_snapshot(
    *,
    log_dir: str | Path | None = None,
    config_dir: str | Path | None = None,
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    candidates: list[Path] = []
    resolved_log_dir = Path(log_dir) if log_dir is not None else get_log_dir(None, use_env=True)
    if resolved_log_dir.exists():
        candidates.extend(sorted(resolved_log_dir.glob("*.ndjson")))
    if config_dir is not None and Path(config_dir).exists():
        candidates.extend(sorted(Path(config_dir).glob("*.json")))
    for path in candidates:
        for record in _iter_json_records(path, limit=50):
            found = _find_precision_record(record, symbol=symbol)
            if found:
                step_size = _number(found.get("step_size") or found.get("quantity_step_size"))
                tick_size = _number(found.get("tick_size") or found.get("price_tick_size"))
                min_notional = _number(
                    found.get("min_notional")
                    or found.get("min_notional_usd")
                    or found.get("min_notional_usdt")
                    or found.get("min_notional_value")
                )
                if step_size is not None and tick_size is not None and min_notional is not None:
                    return {
                        "found": True,
                        "source": str(path),
                        "symbol": symbol,
                        "quantity_precision": _precision_from_step(step_size),
                        "step_size": step_size,
                        "price_precision": _precision_from_step(tick_size),
                        "tick_size": tick_size,
                        "min_notional": min_notional,
                        "read_only": True,
                        "network_used": False,
                    }
    return _empty_precision_snapshot(symbol)


def discover_local_mark_or_candidate_price_snapshot(
    *,
    log_dir: str | Path | None = None,
    symbol: str = "BTCUSDT",
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = Path(log_dir) if log_dir is not None else get_log_dir(None, use_env=True)
    preferred_names = [
        "candles_BTCUSDT_8m.ndjson",
        "market_intelligence_snapshots.ndjson",
        "multi_symbol_paper_scans.ndjson",
    ]
    paths = [resolved_log_dir / name for name in preferred_names]
    if resolved_log_dir.exists():
        paths.extend(sorted(path for path in resolved_log_dir.glob("*.ndjson") if "price" in path.name.lower()))
        paths.extend(sorted(path for path in resolved_log_dir.glob("*.ndjson") if "mark" in path.name.lower()))
    seen: set[Path] = set()
    for path in paths:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        for record in _iter_json_records(path, limit=50):
            found = _find_price_record(record, symbol=symbol)
            if not found:
                continue
            price = _number(
                found.get("mark_price")
                or found.get("candidate_price")
                or found.get("last_price")
                or found.get("close")
                or found.get("price")
            )
            timestamp = _timestamp_value(found)
            if price is None or price <= 0 or timestamp is None:
                continue
            parsed = _parse_timestamp(timestamp)
            age_seconds = None
            if parsed is not None:
                age_seconds = max(0.0, (generated_at - parsed).total_seconds())
            return {
                "found": True,
                "source": str(path),
                "symbol": symbol,
                "price": price,
                "timestamp": timestamp,
                "age_seconds": age_seconds,
                "read_only": True,
                "network_used": False,
            }
    return _empty_price_snapshot(symbol)


def build_quantity_preview_if_safe(
    *,
    notional_cap_usdt: Any,
    precision_snapshot: Mapping[str, Any],
    price_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    blocked_by: list[str] = []
    if precision_snapshot.get("found") is not True:
        blocked_by.append("local_symbol_precision_missing")
    if price_snapshot.get("found") is not True:
        blocked_by.append("local_mark_or_candidate_price_missing")
    notional = _decimal(notional_cap_usdt)
    price = _decimal(price_snapshot.get("price"))
    step = _decimal(precision_snapshot.get("step_size"))
    min_notional = _decimal(precision_snapshot.get("min_notional"))
    if notional is None or notional <= 0:
        blocked_by.append("notional_cap_invalid")
    if price is None or price <= 0:
        blocked_by.append("candidate_price_invalid")
    if step is None or step <= 0:
        blocked_by.append("step_size_invalid")
    if min_notional is None or min_notional < 0:
        blocked_by.append("min_notional_unknown")
    if blocked_by:
        return _blocked_quantity_preview(_dedupe(blocked_by))
    quantity_raw = notional / price
    quantity_rounded = (quantity_raw / step).to_integral_value(rounding=ROUND_FLOOR) * step
    notional_after_rounding = quantity_rounded * price
    if quantity_rounded <= 0:
        blocked_by.append("quantity_rounds_to_zero")
    min_notional_ok = bool(notional_after_rounding >= min_notional)
    if not min_notional_ok:
        blocked_by.append("min_notional_not_met_after_rounding")
    if blocked_by:
        return {
            "can_compute": False,
            "quantity_raw": _float(quantity_raw),
            "quantity_rounded": _float(quantity_rounded),
            "notional_after_rounding": _float(notional_after_rounding),
            "min_notional_ok": min_notional_ok,
            "blocked_by": _dedupe(blocked_by),
        }
    return {
        "can_compute": True,
        "quantity_raw": _float(quantity_raw),
        "quantity_rounded": _float(quantity_rounded),
        "notional_after_rounding": _float(notional_after_rounding),
        "min_notional_ok": True,
        "blocked_by": [],
    }


def validate_precision_and_mark_price_preview(
    *,
    input_summary: Mapping[str, Any],
    order_payload_artifact_summary: Mapping[str, Any],
    local_precision_snapshot: Mapping[str, Any],
    local_mark_or_candidate_price_snapshot: Mapping[str, Any],
    quantity_preview: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not input_summary.get("r240_payload_valid"):
        errors.append("r240_payload_artifact_invalid_or_missing")
    if not input_summary.get("r238_order_preflight_valid"):
        errors.append("r238_order_preflight_invalid_or_missing")
    if not input_summary.get("risk_contract_valid"):
        errors.append("risk_contract_invalid_or_missing")
    expected_false = (
        "executable",
        "signed",
        "submit_allowed",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "order_placed",
    )
    for key in expected_false:
        if order_payload_artifact_summary.get(key) is not False:
            errors.append(f"order_payload_artifact_{key}_not_false")
    if order_payload_artifact_summary.get("artifact_only") is not True:
        errors.append("order_payload_artifact_only_not_true")
    if local_precision_snapshot.get("network_used") is not False:
        errors.append("precision_snapshot_network_used")
    if local_mark_or_candidate_price_snapshot.get("network_used") is not False:
        errors.append("mark_or_candidate_price_network_used")
    if local_precision_snapshot.get("found") is not True:
        warnings.append("local_symbol_precision_missing")
    if local_mark_or_candidate_price_snapshot.get("found") is not True:
        warnings.append("local_mark_or_candidate_price_missing")
    if quantity_preview.get("can_compute") is not True:
        warnings.append("quantity_preview_blocked")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def build_precision_and_mark_price_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    validation: Mapping[str, Any],
    local_precision_snapshot: Mapping[str, Any],
    local_mark_or_candidate_price_snapshot: Mapping[str, Any],
    quantity_preview: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if not input_summary.get("r240_payload_valid"):
        blockers.append("r240_payload_artifact_not_ready")
    if not input_summary.get("r238_order_preflight_valid"):
        blockers.append("r238_order_preflight_not_ready")
    if not input_summary.get("r236_lane_arm_valid"):
        blockers.append("r236_lane_arm_not_ready")
    if not input_summary.get("risk_contract_valid"):
        blockers.append("risk_contract_not_ready")
    if local_precision_snapshot.get("found") is not True:
        blockers.append("local_symbol_precision_missing")
    if local_mark_or_candidate_price_snapshot.get("found") is not True:
        blockers.append("local_mark_or_candidate_price_missing")
    if quantity_preview.get("can_compute") is not True:
        blockers.extend(str(item) for item in quantity_preview.get("blocked_by") or ["quantity_preview_blocked"])
    if validation.get("valid") is not True:
        blockers.extend(str(item) for item in validation.get("errors") or ["validation_failed"])
    return {
        "payload_artifact_ready": bool(input_summary.get("r240_payload_valid")),
        "precision_snapshot_found": local_precision_snapshot.get("found") is True,
        "mark_or_candidate_price_found": local_mark_or_candidate_price_snapshot.get("found") is True,
        "quantity_preview_ready": quantity_preview.get("can_compute") is True,
        "min_notional_check_ready": quantity_preview.get("min_notional_ok") is True,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_precision_and_mark_price_review_packet(
    precision_mark_price_gate_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    ready_or_reviewable = (
        precision_mark_price_gate_matrix.get("payload_artifact_ready") is True
        and precision_mark_price_gate_matrix.get("precision_snapshot_found") is True
        and precision_mark_price_gate_matrix.get("mark_or_candidate_price_found") is True
    )
    if precision_mark_price_gate_matrix.get("payload_artifact_ready") is not True:
        action = "FIX_BLOCKER"
    elif ready_or_reviewable:
        action = "REVIEW_R241_PRECISION_MARK_PRICE_PREVIEW"
    else:
        action = "WAIT"
    return {
        "operator_should_review_precision_mark_price_preview": bool(precision_mark_price_gate_matrix.get("payload_artifact_ready")),
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


def classify_tiny_live_precision_and_mark_price_preview_status(
    *,
    input_summary: Mapping[str, Any],
    validation: Mapping[str, Any],
    gate_matrix: Mapping[str, Any],
) -> str:
    if not input_summary.get("r240_payload_valid"):
        return TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_PAYLOAD
    if not input_summary.get("r238_order_preflight_valid"):
        return TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_PREFLIGHT
    if not input_summary.get("risk_contract_valid"):
        return TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_RISK_CONTRACT
    if validation.get("valid") is not True:
        return TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_BLOCKED_BY_VALIDATION
    if (
        gate_matrix.get("precision_snapshot_found") is True
        and gate_matrix.get("mark_or_candidate_price_found") is True
        and gate_matrix.get("quantity_preview_ready") is True
    ):
        return TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_READY_FOR_FUTURE_GATE
    return TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_NEEDS_BINANCE_READONLY_CHECK


def append_tiny_live_precision_and_mark_price_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_precision_and_mark_price_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "preview_record_id": record.get("precision_mark_price_preview_record_id")
            or f"r241_precision_mark_price_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": TINY_LIVE_PRECISION_AND_MARK_PRICE_PREVIEW_RECORDED,
            "generated_at": record.get("generated_at"),
            "precision_mark_price_preview_recorded": True,
            "record_precision_mark_price_preview_requested": True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "risk_contract_summary": dict(record.get("risk_contract_summary") or {}),
            "order_payload_artifact_summary": dict(record.get("order_payload_artifact_summary") or {}),
            "local_precision_snapshot": dict(record.get("local_precision_snapshot") or {}),
            "local_mark_or_candidate_price_snapshot": dict(record.get("local_mark_or_candidate_price_snapshot") or {}),
            "quantity_preview": dict(record.get("quantity_preview") or {}),
            "precision_mark_price_preview_validation": dict(record.get("precision_mark_price_preview_validation") or {}),
            "precision_mark_price_gate_matrix": dict(record.get("precision_mark_price_gate_matrix") or {}),
            "operator_precision_mark_price_review_packet": dict(
                record.get("operator_precision_mark_price_review_packet") or {}
            ),
            "precision_mark_price_preview_overall_status": record.get(
                "precision_mark_price_preview_overall_status"
            ),
            "future_confirmation_phrase_suggestion": record.get("future_confirmation_phrase_suggestion"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_precision_and_mark_price_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_precision_and_mark_price_preview_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_tiny_live_precision_and_mark_price_preview_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_preview_recorded": latest.get("precision_mark_price_preview_recorded") is True,
        "latest_overall_status": latest.get("precision_mark_price_preview_overall_status"),
    }


def tiny_live_precision_and_mark_price_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_precision_and_mark_price_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r240: Mapping[str, Any],
    latest_r239: Mapping[str, Any],
    latest_r238: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_config: Mapping[str, Any],
) -> dict[str, Any]:
    artifact = latest_r240.get("order_payload") if isinstance(latest_r240.get("order_payload"), Mapping) else {}
    order_preflight = latest_r238.get("order_preflight") if isinstance(latest_r238.get("order_preflight"), Mapping) else {}
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    risk_contract = (
        risk_config.get("matching_risk_contract") if isinstance(risk_config.get("matching_risk_contract"), Mapping) else {}
    )
    r228_matrix = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    payload_validation = validate_non_executable_order_payload_artifact(artifact) if artifact else {"valid": False}
    preflight_validation = validate_order_preflight_object(order_preflight) if order_preflight else {"valid": False}
    lane_arm_validation = validate_lane_arm_object(lane_arm) if lane_arm else {"valid": False}
    risk_validation = validate_tiny_live_risk_contract_config_entry(risk_contract) if risk_contract else {"valid": False}
    return {
        "r240_payload_found": bool(latest_r240),
        "r240_payload_valid": payload_validation.get("valid") is True,
        "r239_payload_found": bool(latest_r239),
        "r239_payload_valid": bool(latest_r239),
        "r238_order_preflight_found": bool(latest_r238),
        "r238_order_preflight_valid": preflight_validation.get("valid") is True,
        "r236_lane_arm_found": bool(latest_r236),
        "r236_lane_arm_valid": lane_arm_validation.get("valid") is True,
        "r230_risk_contract_config_found": bool(latest_r230) and bool(risk_contract),
        "risk_contract_valid": risk_validation.get("valid") is True,
        "r228_evidence_ready": r228_matrix.get("evidence_ready") is True,
        "fisherman_ready": r228_matrix.get("fisherman_ready") is True,
    }


def _risk_contract_summary(risk_config: Mapping[str, Any]) -> dict[str, Any]:
    contract = risk_config.get("matching_risk_contract") if isinstance(risk_config.get("matching_risk_contract"), Mapping) else {}
    return {
        "official_lane_key": contract.get("official_lane_key") or OFFICIAL_LANE_KEY,
        "max_notional_usdt": contract.get("max_notional_usdt"),
        "max_loss_usdt": contract.get("max_loss_usdt"),
        "leverage": contract.get("leverage"),
    }


def _empty_risk_contract_summary(official_lane_key: str) -> dict[str, Any]:
    return {"official_lane_key": official_lane_key, "max_notional_usdt": None, "max_loss_usdt": None, "leverage": None}


def _order_payload_artifact_summary(latest_r240: Mapping[str, Any]) -> dict[str, Any]:
    artifact = latest_r240.get("order_payload") if isinstance(latest_r240.get("order_payload"), Mapping) else {}
    if not artifact:
        return _empty_order_payload_artifact_summary()
    return {
        "order_payload_id": artifact.get("order_payload_id"),
        "artifact_only": artifact.get("artifact_only") is True,
        "executable": artifact.get("executable") is True,
        "signed": artifact.get("signed") is True,
        "submit_allowed": artifact.get("submit_allowed") is True,
        "quantity": artifact.get("quantity"),
        "quantity_source": artifact.get("quantity_source"),
        "notional_cap_usdt": artifact.get("notional_cap_usdt"),
        "executable_payload_created": artifact.get("executable_payload_created") is True,
        "signed_order_request_created": artifact.get("signed_order_request_created") is True,
        "signed_trading_request_created": artifact.get("signed_trading_request_created") is True,
        "order_placed": artifact.get("order_placed") is True,
        "missing_before_executable_payload": list(artifact.get("missing_before_executable_payload") or []),
    }


def _empty_order_payload_artifact_summary() -> dict[str, Any]:
    return {
        "order_payload_id": None,
        "artifact_only": False,
        "executable": False,
        "signed": False,
        "submit_allowed": False,
        "quantity": None,
        "quantity_source": None,
        "notional_cap_usdt": None,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "order_placed": False,
        "missing_before_executable_payload": [],
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r240_payload_found": False,
        "r240_payload_valid": False,
        "r239_payload_found": False,
        "r239_payload_valid": False,
        "r238_order_preflight_found": False,
        "r238_order_preflight_valid": False,
        "r236_lane_arm_found": False,
        "r236_lane_arm_valid": False,
        "r230_risk_contract_config_found": False,
        "risk_contract_valid": False,
        "r228_evidence_ready": False,
        "fisherman_ready": False,
    }


def _empty_precision_snapshot(symbol: str) -> dict[str, Any]:
    return {
        "found": False,
        "source": None,
        "symbol": symbol,
        "quantity_precision": None,
        "step_size": None,
        "price_precision": None,
        "tick_size": None,
        "min_notional": None,
        "read_only": True,
        "network_used": False,
    }


def _empty_price_snapshot(symbol: str) -> dict[str, Any]:
    return {
        "found": False,
        "source": None,
        "symbol": symbol,
        "price": None,
        "timestamp": None,
        "age_seconds": None,
        "read_only": True,
        "network_used": False,
    }


def _blocked_quantity_preview(blocked_by: Sequence[str]) -> dict[str, Any]:
    return {
        "can_compute": False,
        "quantity_raw": None,
        "quantity_rounded": None,
        "notional_after_rounding": None,
        "min_notional_ok": None,
        "blocked_by": _dedupe(list(blocked_by)),
    }


def _recommended_next_operator_move(operator_packet: Mapping[str, Any]) -> str:
    return str(operator_packet.get("next_required_human_action") or "WAIT")


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("payload_artifact_ready") is not True:
        return "Fix R241 upstream payload/preflight/risk blockers before precision or price work."
    if matrix.get("precision_snapshot_found") is not True or matrix.get("mark_or_candidate_price_found") is not True:
        return "Create R242 Tiny-Live Binance read-only precision/mark-price gate with explicit confirmation; no order endpoints, payloads, signatures, or orders."
    if matrix.get("quantity_preview_ready") is not True:
        return "Review local precision/price quantity blockers before any executable payload design."
    return "Review R241 preview, then design a separate future executable-payload gate only after read-only precision/price evidence is accepted."


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


def _iter_json_records(path: Path, *, limit: int = 50) -> list[Any]:
    if not path.exists():
        return []
    try:
        if path.suffix == ".ndjson":
            return list(read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216))
        data = json.loads(path.read_text(encoding="utf-8"))
        return [data]
    except (OSError, json.JSONDecodeError):
        return []


def _find_precision_record(value: Any, *, symbol: str) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        if str(value.get("symbol") or "") == symbol:
            has_quantity = value.get("step_size") is not None or value.get("quantity_step_size") is not None
            has_price = value.get("tick_size") is not None or value.get("price_tick_size") is not None
            has_min = (
                value.get("min_notional") is not None
                or value.get("min_notional_usd") is not None
                or value.get("min_notional_usdt") is not None
                or value.get("min_notional_value") is not None
            )
            if has_quantity and has_price and has_min:
                return value
        for item in value.values():
            found = _find_precision_record(item, symbol=symbol)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_precision_record(item, symbol=symbol)
            if found:
                return found
    return None


def _find_price_record(value: Any, *, symbol: str) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        if str(value.get("symbol") or "") == symbol:
            has_price = any(value.get(key) is not None for key in ("mark_price", "candidate_price", "last_price", "close", "price"))
            if has_price and _timestamp_value(value) is not None:
                return value
        for item in value.values():
            found = _find_price_record(item, symbol=symbol)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_price_record(item, symbol=symbol)
            if found:
                return found
    return None


def _timestamp_value(record: Mapping[str, Any]) -> str | None:
    for key in ("timestamp", "created_at", "generated_at", "recorded_at_utc", "open_time", "close_time"):
        value = record.get(key)
        if value is not None:
            return str(value)
    return None


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: Decimal) -> float:
    return float(value.normalize())


def _precision_from_step(step: float) -> int | None:
    decimal = _decimal(step)
    if decimal is None:
        return None
    return max(0, -decimal.normalize().as_tuple().exponent)


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = lane_key.split("|")
    if len(parts) != 4:
        return lane_key, "", "", ""
    return parts[0], parts[1], parts[2], parts[3]


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
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
