"""R249 tiny-live executable payload artifact write gate.

This gate writes a local executable-shaped payload artifact only after the
exact R249 confirmation phrase. It never signs requests, calls Binance/network
endpoints, submits orders, places orders, mutates configs/env/lane controls, or
disables the kill switch.
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
from src.app.hammer_radar.operator.tiny_live_order_payload_refresh_write_gate import (
    load_tiny_live_order_payload_refresh_write_gate_records,
    validate_refreshed_non_executable_payload_artifact,
)
from src.app.hammer_radar.operator.tiny_live_stop_take_profit_source_gate import (
    load_tiny_live_stop_take_profit_source_gate_records,
    validate_short_stop_take_profit_levels,
)

TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_READY = "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_READY"
TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_REJECTED = "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_REJECTED"
TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_WRITTEN = "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_WRITTEN"
TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_BLOCKED = "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_BLOCKED"
TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_ERROR = "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_ERROR"

TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_READY_FOR_CONFIRMATION = (
    "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_READY_FOR_CONFIRMATION"
)
TINY_LIVE_EXECUTABLE_PAYLOAD_WRITTEN_SIGNATURE_GATE_REQUIRED = (
    "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITTEN_SIGNATURE_GATE_REQUIRED"
)
TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_R248 = "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_R248"
TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_R247 = "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_R247"
TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_VALIDATION = (
    "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE"
LEDGER_FILENAME = "tiny_live_executable_payload_write_gate.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R249_TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE"
DEFAULT_RISK_CONTRACT_CONFIG_PATH = Path("configs/hammer_radar/tiny_live_risk_contracts.json")
CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_PHRASE = (
    "I CONFIRM TINY LIVE EXECUTABLE PAYLOAD WRITE GATE ONLY; "
    "WRITE LOCAL PAYLOAD ARTIFACT ONLY; NO SIGNATURE; NO ORDER; NO BINANCE CALL."
)

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_executable_payload_preview.ndjson",
    "logs/hammer_radar_forward/tiny_live_order_payload_refresh_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_leverage_notional_risk_contract_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
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
    "executable_payload_write_gate_only": True,
    "executable_payload_written": False,
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
}


def build_tiny_live_executable_payload_write_gate(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    write_executable_payload: bool = False,
    confirm_tiny_live_executable_payload_write: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_tiny_live_executable_payload_write == CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_PHRASE
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    try:
        latest_r248 = load_latest_tiny_live_stop_take_profit_source_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r247 = load_latest_tiny_live_executable_payload_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r246 = load_latest_tiny_live_order_payload_refresh_write_gate(
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
        risk_contract = load_adjusted_tiny_live_risk_contract(
            risk_contract_config_path=risk_contract_config_path,
            official_lane_key=official_lane_key,
        )
        input_summary = _build_input_summary(
            latest_r248=latest_r248,
            latest_r247=latest_r247,
            latest_r246=latest_r246,
            latest_r244=latest_r244,
            latest_r242=latest_r242,
            risk_contract=risk_contract,
        )
        artifact = build_executable_payload_artifact(
            latest_r248=latest_r248,
            latest_r247=latest_r247,
            latest_r246=latest_r246,
            latest_r244=latest_r244,
            latest_r242=latest_r242,
            risk_contract=risk_contract,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        validation = validate_executable_payload_artifact(artifact)
        blocked_by = _blocked_by(input_summary=input_summary, validation=validation)
        preview = build_executable_payload_artifact_preview(
            proposed_executable_payload_artifact=artifact,
            validation=validation,
            blocked_by=blocked_by,
        )

        written = False
        if write_executable_payload and not confirmation_valid:
            status = TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_REJECTED
            overall = TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_REJECTED_BAD_CONFIRMATION
        elif blocked_by:
            status = TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_BLOCKED
            overall = classify_tiny_live_executable_payload_write_gate_status(
                input_summary=input_summary,
                payload_artifact_validation=validation,
                executable_payload_written=False,
                rejected_bad_confirmation=False,
            )
        elif write_executable_payload and confirmation_valid:
            write_result = write_executable_payload_artifact_if_confirmed(
                executable_payload_artifact=artifact,
                confirm_tiny_live_executable_payload_write=confirm_tiny_live_executable_payload_write,
                log_dir=resolved_log_dir,
            )
            written = write_result.get("written") is True
            status = TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_WRITTEN if written else TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_BLOCKED
            overall = (
                TINY_LIVE_EXECUTABLE_PAYLOAD_WRITTEN_SIGNATURE_GATE_REQUIRED
                if written
                else TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_VALIDATION
            )
        else:
            status = TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_READY
            overall = TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_READY_FOR_CONFIRMATION

        post_write = build_post_write_executable_payload_verification(
            executable_payload_artifact=artifact,
            executable_payload_written=written,
            log_dir=resolved_log_dir,
        )
        matrix = build_executable_payload_write_gate_matrix(
            input_summary=input_summary,
            payload_artifact_valid=validation["valid"],
            write_confirmed=bool(write_executable_payload and confirmation_valid),
            executable_payload_written=written,
            blocked_by=blocked_by,
        )
        operator_packet = build_operator_executable_payload_write_packet(matrix)
        safety = _safety(written)
        return _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "write_executable_payload_requested": bool(write_executable_payload),
                "confirmation_valid": bool(confirmation_valid),
                "executable_payload_written": bool(written),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "executable_payload_write_gate_only": True,
                    "signed_order_request_created": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "payload_artifact_preview": preview,
                "payload_artifact_validation": validation,
                "post_write_verification": post_write,
                "executable_payload_write_gate_matrix": matrix,
                "operator_executable_payload_write_packet": operator_packet,
                "recommended_next_operator_move": _recommended_next_operator_move(matrix),
                "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
                "executable_payload_write_overall_status": overall,
                "do_not_run_yet": _do_not_run_yet(),
                "safety": safety,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_executable_payload_write_gate_matrix(
            input_summary=_empty_input_summary(),
            payload_artifact_valid=False,
            write_confirmed=False,
            executable_payload_written=False,
            blocked_by=["executable_payload_write_gate_error"],
        )
        return _sanitize(
            {
                "status": TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "write_executable_payload_requested": bool(write_executable_payload),
                "confirmation_valid": bool(confirmation_valid),
                "executable_payload_written": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "executable_payload_write_gate_only": True,
                    "signed_order_request_created": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": _empty_input_summary(),
                "payload_artifact_preview": build_executable_payload_artifact_preview(
                    proposed_executable_payload_artifact={},
                    validation={"valid": False, "errors": ["executable_payload_write_gate_error"], "warnings": []},
                    blocked_by=["executable_payload_write_gate_error"],
                ),
                "payload_artifact_validation": {
                    "valid": False,
                    "errors": ["executable_payload_write_gate_error"],
                    "warnings": [],
                },
                "post_write_verification": _empty_post_write_verification(),
                "executable_payload_write_gate_matrix": matrix,
                "operator_executable_payload_write_packet": build_operator_executable_payload_write_packet(matrix),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R249 executable payload write gate error before any signature gate.",
                "executable_payload_write_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": _safety(False),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_stop_take_profit_source_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_stop_take_profit_source_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        source = _extract_r248_source(record)
        validation = _validate_r248_source(source)
        if (
            _record_matches_lane(record, official_lane_key)
            and validation["valid"] is True
            and (
                record.get("stop_take_profit_source_written") is True
                or record.get("stop_take_profit_source_preview_recorded") is True
            )
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_executable_payload_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_executable_payload_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        preview = record.get("executable_payload_readiness_preview")
        preview = preview if isinstance(preview, Mapping) else {}
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("executable_payload_preview_recorded") is True
            and validate_executable_payload_preview(preview, input_summary=record.get("input_summary") or {}).get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_order_payload_refresh_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_order_payload_refresh_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        artifact = _r246_payload(record)
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("payload_refresh_written") is True
            and validate_refreshed_non_executable_payload_artifact(artifact).get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_leverage_notional_risk_contract_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_leverage_notional_risk_contract_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        contract = _r244_contract(record)
        if (
            _record_matches_lane(record, official_lane_key)
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
        result = record.get("binance_readonly_result")
        result = result if isinstance(result, Mapping) else {}
        precision = result.get("precision_snapshot") if isinstance(result.get("precision_snapshot"), Mapping) else {}
        mark = result.get("mark_price_snapshot") if isinstance(result.get("mark_price_snapshot"), Mapping) else {}
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("readonly_fetch_performed") is True
            and precision.get("found") is True
            and mark.get("found") is True
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


def build_executable_payload_artifact_preview(
    *,
    proposed_executable_payload_artifact: Mapping[str, Any],
    validation: Mapping[str, Any],
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "would_write": bool(validation.get("valid") is True and not blocked_by),
        "write_requires_confirmation": True,
        "artifact_only": True,
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "proposed_executable_payload_artifact": _sanitize(dict(proposed_executable_payload_artifact)),
    }


def build_executable_payload_artifact(
    *,
    latest_r248: Mapping[str, Any],
    latest_r247: Mapping[str, Any],
    latest_r246: Mapping[str, Any],
    latest_r244: Mapping[str, Any],
    latest_r242: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    source = _extract_r248_source(latest_r248)
    base = _r246_payload(latest_r246)
    contract = risk_contract or _r244_contract(latest_r244)
    precision = _precision(latest_r242)
    quantity = _number(source.get("quantity")) or _number(base.get("quantity"))
    reference = _number(source.get("reference_price")) or _number(source.get("entry_reference_price"))
    stop_price = _number(source.get("stop_price")) or _number(source.get("final_stop_price")) or _number(source.get("rounded_stop_price"))
    take_profit_price = (
        _number(source.get("take_profit_price"))
        or _number(source.get("final_take_profit_price"))
        or _number(source.get("rounded_take_profit_price"))
    )
    loss = _number(source.get("estimated_loss_at_stop_usdt"))
    reward = _number(source.get("estimated_reward_at_take_profit_usdt"))
    if loss is None and reference is not None and stop_price is not None and quantity is not None:
        loss = max((stop_price - reference) * quantity, 0)
    if reward is None and reference is not None and take_profit_price is not None and quantity is not None:
        reward = max((reference - take_profit_price) * quantity, 0)
    ratio = _number(source.get("risk_reward_ratio"))
    if ratio is None and loss and reward is not None:
        ratio = reward / loss
    return _sanitize(
        {
            "executable_payload_id": f"r249_executable_payload_{symbol}_{timeframe}_{direction}_{entry_mode}",
            "artifact_only": True,
            "created_by_phase": CREATED_BY_PHASE,
            "created_at": generated_at.isoformat(),
            "official_lane_key": official_lane_key,
            "exchange": "binance_futures",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": entry_mode,
            "reference_price": reference,
            "main_order": {
                "symbol": symbol,
                "side": "SELL",
                "type": "MARKET",
                "quantity": quantity,
                "reduceOnly": False,
                "positionSide": base.get("position_side") or "BOTH|SHORT|null",
            },
            "stop_order": {
                "symbol": symbol,
                "side": "BUY",
                "type": "STOP_MARKET",
                "stopPrice": stop_price,
                "quantity": quantity,
                "reduceOnly": True,
                "workingType": "MARK_PRICE",
            },
            "take_profit_order": {
                "symbol": symbol,
                "side": "BUY",
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": take_profit_price,
                "quantity": quantity,
                "reduceOnly": True,
                "workingType": "MARK_PRICE",
            },
            "risk": {
                "margin_budget_usdt": contract.get("margin_budget_usdt") or base.get("margin_budget_usdt"),
                "tiny_live_margin_usdt": contract.get("tiny_live_margin_usdt"),
                "leverage": contract.get("leverage") or base.get("leverage"),
                "max_notional_usdt": contract.get("max_notional_usdt") or base.get("notional_cap_usdt"),
                "max_position_notional_usdt": contract.get("max_position_notional_usdt"),
                "notional_after_rounding": base.get("notional_after_rounding"),
                "max_loss_usdt": contract.get("max_loss_usdt") or base.get("max_loss_usdt"),
                "estimated_loss_at_stop_usdt": loss,
                "estimated_reward_at_take_profit_usdt": reward,
                "risk_reward_ratio": ratio,
                "max_loss_requires_review": contract.get("max_loss_requires_review") is True,
                "tick_size": precision.get("tick_size"),
            },
            "source_refs": {
                "r248_stop_take_profit_source_gate_record_id": latest_r248.get("stop_take_profit_source_gate_record_id"),
                "r247_executable_payload_preview_record_id": latest_r247.get("executable_payload_preview_record_id"),
                "r246_payload_refresh_write_gate_record_id": latest_r246.get("gate_record_id"),
                "r244_risk_contract_record_id": latest_r244.get("risk_contract_write_gate_record_id"),
                "r242_readonly_record_id": latest_r242.get("binance_readonly_record_id"),
            },
            "controls": {
                "signed": False,
                "submit_allowed": False,
                "binance_call_allowed": False,
                "network_allowed": False,
                "requires_signature_gate": True,
                "requires_submit_gate": True,
                "requires_future_readonly_mark_price_refresh_before_submit": True,
                "requires_operator_final_submit_confirmation": True,
                "kill_switch_required": True,
            },
            "safety": {
                "executable_payload_created": True,
                "signed_order_request_created": False,
                "signed_trading_request_created": False,
                "submit_allowed": False,
                "order_placed": False,
                "binance_order_endpoint_called": False,
                "network_allowed": False,
            },
        }
    )


def validate_executable_payload_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    expected = {
        "official_lane_key": OFFICIAL_LANE_KEY,
        "exchange": "binance_futures",
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "artifact_only": True,
        "created_by_phase": CREATED_BY_PHASE,
    }
    for key, value in expected.items():
        if artifact.get(key) != value:
            errors.append(f"{key}_invalid")
    reference = _number(artifact.get("reference_price"))
    main = artifact.get("main_order") if isinstance(artifact.get("main_order"), Mapping) else {}
    stop = artifact.get("stop_order") if isinstance(artifact.get("stop_order"), Mapping) else {}
    take_profit = artifact.get("take_profit_order") if isinstance(artifact.get("take_profit_order"), Mapping) else {}
    risk = artifact.get("risk") if isinstance(artifact.get("risk"), Mapping) else {}
    controls = artifact.get("controls") if isinstance(artifact.get("controls"), Mapping) else {}
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), Mapping) else {}
    if main.get("symbol") != "BTCUSDT" or main.get("side") != "SELL" or main.get("type") != "MARKET":
        errors.append("main_order_shape_invalid")
    quantity = _number(main.get("quantity"))
    if quantity is None or quantity <= 0:
        errors.append("main_order_quantity_invalid")
    if stop.get("symbol") != "BTCUSDT" or stop.get("side") != "BUY" or stop.get("type") != "STOP_MARKET":
        errors.append("stop_order_shape_invalid")
    if stop.get("reduceOnly") is not True:
        errors.append("stop_order_reduce_only_invalid")
    stop_price = _number(stop.get("stopPrice"))
    if reference is not None and stop_price is not None and stop_price <= reference:
        errors.append("short_stop_price_must_be_above_reference_price")
    if take_profit.get("symbol") != "BTCUSDT" or take_profit.get("side") != "BUY" or take_profit.get("type") != "TAKE_PROFIT_MARKET":
        errors.append("take_profit_order_shape_invalid")
    if take_profit.get("reduceOnly") is not True:
        errors.append("take_profit_order_reduce_only_invalid")
    tp_price = _number(take_profit.get("stopPrice"))
    if reference is not None and tp_price is not None and tp_price >= reference:
        errors.append("short_take_profit_price_must_be_below_reference_price")
    if _number(stop.get("quantity")) != quantity or _number(take_profit.get("quantity")) != quantity:
        errors.append("protective_quantity_mismatch")
    for key, expected_value in {
        "leverage": 10,
        "margin_budget_usdt": 44,
        "max_notional_usdt": 440,
        "max_loss_usdt": 4.44,
    }.items():
        if _number(risk.get(key)) != expected_value:
            errors.append(f"risk_{key}_invalid")
    estimated_loss = _number(risk.get("estimated_loss_at_stop_usdt"))
    max_loss = _number(risk.get("max_loss_usdt"))
    tick = _number(risk.get("tick_size")) or 0.1
    tolerance = max(0.01, tick * (quantity or 0))
    if estimated_loss is None or max_loss is None or estimated_loss > max_loss + tolerance:
        errors.append("estimated_loss_at_stop_usdt_exceeds_tolerance")
    if abs((_number(risk.get("risk_reward_ratio")) or 0) - 2.0) > 0.05:
        errors.append("risk_reward_ratio_invalid")
    for key in ("signed", "submit_allowed", "binance_call_allowed", "network_allowed"):
        if controls.get(key) is not False:
            errors.append(f"controls_{key}_invalid")
    for key in (
        "requires_signature_gate",
        "requires_submit_gate",
        "requires_future_readonly_mark_price_refresh_before_submit",
        "requires_operator_final_submit_confirmation",
        "kill_switch_required",
    ):
        if controls.get(key) is not True:
            errors.append(f"controls_{key}_invalid")
    for key in (
        "signed_order_request_created",
        "signed_trading_request_created",
        "submit_allowed",
        "order_placed",
        "binance_order_endpoint_called",
        "network_allowed",
    ):
        if safety.get(key) is not False:
            errors.append(f"safety_{key}_invalid")
    if safety.get("executable_payload_created") is not True:
        errors.append("safety_executable_payload_created_invalid")
    for key, value in (artifact.get("source_refs") if isinstance(artifact.get("source_refs"), Mapping) else {}).items():
        if not value:
            warnings.append(f"{key}_missing")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def write_executable_payload_artifact_if_confirmed(
    *,
    executable_payload_artifact: Mapping[str, Any],
    confirm_tiny_live_executable_payload_write: str | None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_executable_payload_write != CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_PHRASE:
        return {"written": False, "reason": "bad_confirmation"}
    validation = validate_executable_payload_artifact(executable_payload_artifact)
    if validation["valid"] is not True:
        return {"written": False, "reason": "validation_failed", "validation": validation}
    record = append_tiny_live_executable_payload_write_gate_record(
        {
            "status": TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_GATE_WRITTEN,
            "generated_at": executable_payload_artifact.get("created_at"),
            "executable_payload_written": True,
            "write_executable_payload_requested": True,
            "confirmation_valid": True,
            "target_scope": _target_scope(str(executable_payload_artifact.get("official_lane_key") or OFFICIAL_LANE_KEY)),
            "executable_payload_artifact": dict(executable_payload_artifact),
            "payload_artifact_validation": validation,
            "safety": _safety(True),
        },
        log_dir=log_dir,
    )
    return {"written": True, "record": record}


def build_post_write_executable_payload_verification(
    *,
    executable_payload_artifact: Mapping[str, Any],
    executable_payload_written: bool,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_tiny_live_executable_payload_write_gate_records(log_dir=log_dir, limit=50) if executable_payload_written else []
    matching = _matching_executable_payload_record(records, executable_payload_artifact)
    artifact = matching.get("executable_payload_artifact") if isinstance(matching.get("executable_payload_artifact"), Mapping) else {}
    validation = validate_executable_payload_artifact(artifact)
    controls = artifact.get("controls") if isinstance(artifact.get("controls"), Mapping) else {}
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), Mapping) else {}
    return {
        "executable_payload_written": bool(executable_payload_written),
        "matching_executable_payload_found": bool(matching),
        "matching_executable_payload_valid": bool(matching and validation["valid"]),
        "signed": controls.get("signed", False) is True,
        "submit_allowed": controls.get("submit_allowed", False) is True,
        "signed_order_request_created": safety.get("signed_order_request_created", False) is True,
        "order_placed": safety.get("order_placed", False) is True,
        "binance_call_allowed": controls.get("binance_call_allowed", False) is True,
        "network_allowed": controls.get("network_allowed", False) is True,
    }


def build_executable_payload_write_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    payload_artifact_valid: bool,
    write_confirmed: bool,
    executable_payload_written: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if not input_summary.get("r248_stop_take_profit_source_valid"):
        blockers.append("r248_stop_take_profit_source_not_ready")
    if not input_summary.get("r247_executable_payload_preview_valid"):
        blockers.append("r247_executable_payload_preview_not_ready")
    if not input_summary.get("r246_payload_refresh_write_valid"):
        blockers.append("r246_payload_refresh_write_not_ready")
    if not payload_artifact_valid:
        blockers.append("payload_artifact_invalid")
    if not write_confirmed:
        blockers.append("exact_executable_payload_write_confirmation_required")
    if executable_payload_written:
        blockers = [
            "signature_gate_required",
            "submit_gate_required",
            "future_readonly_mark_price_refresh_required_before_submit",
            "kill_switch_still_required",
        ]
    return {
        "r248_stop_take_profit_source_ready": input_summary.get("r248_stop_take_profit_source_valid") is True,
        "r247_executable_payload_preview_ready": input_summary.get("r247_executable_payload_preview_valid") is True,
        "r246_payload_refresh_write_ready": input_summary.get("r246_payload_refresh_write_valid") is True,
        "payload_artifact_valid": bool(payload_artifact_valid),
        "write_confirmed": bool(write_confirmed),
        "executable_payload_written": bool(executable_payload_written),
        "signature_gate_required": True,
        "submit_gate_required": True,
        "signed_order_request_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_executable_payload_write_packet(
    executable_payload_write_gate_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    written = executable_payload_write_gate_matrix.get("executable_payload_written") is True
    ready = (
        executable_payload_write_gate_matrix.get("r248_stop_take_profit_source_ready") is True
        and executable_payload_write_gate_matrix.get("r247_executable_payload_preview_ready") is True
        and executable_payload_write_gate_matrix.get("r246_payload_refresh_write_ready") is True
        and executable_payload_write_gate_matrix.get("payload_artifact_valid") is True
    )
    if written:
        action = "REVIEW_R249_RESULT"
    elif ready:
        action = "CONFIRM_R249_EXECUTABLE_PAYLOAD_WRITE"
    elif executable_payload_write_gate_matrix.get("blocked_by"):
        action = "FIX_BLOCKER"
    else:
        action = "WAIT"
    return {
        "operator_should_review_executable_payload_artifact": bool(ready or written),
        "operator_should_sign_now": False,
        "operator_should_submit_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not sign request",
            "do not call Binance from this phase",
        ],
    }


def classify_tiny_live_executable_payload_write_gate_status(
    *,
    input_summary: Mapping[str, Any],
    payload_artifact_validation: Mapping[str, Any],
    executable_payload_written: bool = False,
    rejected_bad_confirmation: bool = False,
) -> str:
    if rejected_bad_confirmation:
        return TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_REJECTED_BAD_CONFIRMATION
    if executable_payload_written:
        return TINY_LIVE_EXECUTABLE_PAYLOAD_WRITTEN_SIGNATURE_GATE_REQUIRED
    if not input_summary.get("r248_stop_take_profit_source_valid"):
        return TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_R248
    if not input_summary.get("r247_executable_payload_preview_valid"):
        return TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_R247
    if payload_artifact_validation.get("valid") is not True:
        return TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_BLOCKED_BY_VALIDATION
    return TINY_LIVE_EXECUTABLE_PAYLOAD_WRITE_READY_FOR_CONFIRMATION


def append_tiny_live_executable_payload_write_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_executable_payload_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = dict(record.get("executable_payload_artifact") or {})
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "executable_payload_write_gate_record_id": record.get("executable_payload_write_gate_record_id")
            or f"r249_executable_payload_write_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "executable_payload_written": record.get("executable_payload_written") is True,
            "write_executable_payload_requested": record.get("write_executable_payload_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "executable_payload_artifact": artifact,
            "payload_artifact_validation": dict(record.get("payload_artifact_validation") or {}),
            "safety": dict(record.get("safety") or _safety(False)),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_executable_payload_write_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_executable_payload_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_executable_payload_write_gate_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    artifact = latest.get("executable_payload_artifact") if isinstance(latest.get("executable_payload_artifact"), Mapping) else {}
    main = artifact.get("main_order") if isinstance(artifact.get("main_order"), Mapping) else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_executable_payload_written": latest.get("executable_payload_written") is True,
        "latest_executable_payload_id": artifact.get("executable_payload_id"),
        "latest_quantity": main.get("quantity"),
    }


def tiny_live_executable_payload_write_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_executable_payload_write_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r248: Mapping[str, Any],
    latest_r247: Mapping[str, Any],
    latest_r246: Mapping[str, Any],
    latest_r244: Mapping[str, Any],
    latest_r242: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
) -> dict[str, Any]:
    r247_preview = latest_r247.get("executable_payload_readiness_preview") if isinstance(latest_r247.get("executable_payload_readiness_preview"), Mapping) else {}
    r248_source = _extract_r248_source(latest_r248)
    return {
        "r248_stop_take_profit_source_found": bool(latest_r248),
        "r248_stop_take_profit_source_valid": _validate_r248_source(r248_source)["valid"],
        "r247_executable_payload_preview_found": bool(latest_r247),
        "r247_executable_payload_preview_valid": (
            bool(latest_r247)
            and validate_executable_payload_preview(r247_preview, input_summary=latest_r247.get("input_summary") or {}).get("valid") is True
        ),
        "r246_payload_refresh_write_found": bool(latest_r246),
        "r246_payload_refresh_write_valid": validate_refreshed_non_executable_payload_artifact(_r246_payload(latest_r246)).get("valid") is True,
        "r244_adjusted_contract_found": bool(latest_r244) or bool(risk_contract),
        "r244_adjusted_contract_valid": validate_adjusted_risk_contract(risk_contract or _r244_contract(latest_r244)).get("valid") is True,
        "r242_readonly_found": bool(latest_r242),
        "r242_readonly_valid": bool(latest_r242),
    }


def _blocked_by(*, input_summary: Mapping[str, Any], validation: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not input_summary.get("r248_stop_take_profit_source_valid"):
        blockers.append("r248_stop_take_profit_source_not_ready")
    if not input_summary.get("r247_executable_payload_preview_valid"):
        blockers.append("r247_executable_payload_preview_not_ready")
    if not input_summary.get("r246_payload_refresh_write_valid"):
        blockers.append("r246_payload_refresh_write_not_ready")
    if not input_summary.get("r244_adjusted_contract_valid"):
        blockers.append("r244_adjusted_contract_not_ready")
    if not input_summary.get("r242_readonly_valid"):
        blockers.append("r242_readonly_not_ready")
    if validation.get("valid") is not True:
        blockers.extend(str(item) for item in validation.get("errors") or ["payload_artifact_invalid"])
    return _dedupe(blockers)


def _extract_r248_source(record: Mapping[str, Any]) -> dict[str, Any]:
    source = record.get("stop_take_profit_source") if isinstance(record.get("stop_take_profit_source"), Mapping) else {}
    selected = record.get("selected_stop_take_profit_source") if isinstance(record.get("selected_stop_take_profit_source"), Mapping) else {}
    risk = record.get("risk_reward_validation") if isinstance(record.get("risk_reward_validation"), Mapping) else {}
    source = dict(source or {})
    return _sanitize(
        {
            **source,
            "official_lane_key": source.get("official_lane_key") or _target_from_record(record).get("official_lane_key"),
            "symbol": source.get("symbol") or "BTCUSDT",
            "timeframe": source.get("timeframe") or "8m",
            "direction": source.get("direction") or "short",
            "entry_mode": source.get("entry_mode") or "ladder_close_50_618",
            "reference_price": source.get("reference_price") or selected.get("entry_reference_price"),
            "entry_reference_price": source.get("entry_reference_price") or selected.get("entry_reference_price") or source.get("reference_price"),
            "stop_price": source.get("stop_price") or source.get("final_stop_price") or selected.get("rounded_stop_price"),
            "take_profit_price": source.get("take_profit_price") or source.get("final_take_profit_price") or selected.get("rounded_take_profit_price"),
            "quantity": source.get("quantity") or risk.get("quantity_preview"),
            "estimated_loss_at_stop_usdt": source.get("estimated_loss_at_stop_usdt") or risk.get("loss_usdt_preview"),
            "estimated_reward_at_take_profit_usdt": source.get("estimated_reward_at_take_profit_usdt") or risk.get("reward_usdt_preview"),
            "risk_reward_ratio": source.get("risk_reward_ratio") or risk.get("risk_reward_ratio_preview"),
        }
    )


def _validate_r248_source(source: Mapping[str, Any]) -> dict[str, Any]:
    selected = {
        "entry_reference_price": source.get("reference_price") or source.get("entry_reference_price"),
        "rounded_stop_price": source.get("stop_price") or source.get("final_stop_price"),
        "rounded_take_profit_price": source.get("take_profit_price") or source.get("final_take_profit_price"),
        "source_valid": True,
        "blocked_by": [],
    }
    validation = validate_short_stop_take_profit_levels(selected)
    quantity = _number(source.get("quantity"))
    if quantity is not None and quantity <= 0:
        validation["errors"].append("quantity_invalid")
    if source.get("official_lane_key") not in (None, OFFICIAL_LANE_KEY):
        validation["errors"].append("official_lane_key_invalid")
    validation["valid"] = not validation["errors"]
    return validation


def _r246_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("refreshed_payload_artifact", "order_payload"):
        value = record.get(key)
        if isinstance(value, Mapping):
            return _sanitize(dict(value))
    return {}


def _r244_contract(record: Mapping[str, Any]) -> dict[str, Any]:
    preview = record.get("adjusted_contract_write_preview") if isinstance(record.get("adjusted_contract_write_preview"), Mapping) else {}
    contract = preview.get("proposed_adjusted_contract") if isinstance(preview.get("proposed_adjusted_contract"), Mapping) else {}
    return _sanitize(dict(contract))


def _precision(record: Mapping[str, Any]) -> dict[str, Any]:
    result = record.get("binance_readonly_result") if isinstance(record.get("binance_readonly_result"), Mapping) else {}
    snapshot = result.get("precision_snapshot") if isinstance(result.get("precision_snapshot"), Mapping) else {}
    return {"tick_size": _number(snapshot.get("tick_size"))}


def _matching_executable_payload_record(records: Sequence[Mapping[str, Any]], artifact: Mapping[str, Any]) -> dict[str, Any]:
    expected_id = artifact.get("executable_payload_id")
    for record in records:
        candidate = record.get("executable_payload_artifact")
        candidate = candidate if isinstance(candidate, Mapping) else {}
        if candidate.get("executable_payload_id") == expected_id:
            return _sanitize(dict(record))
    return {}


def _target_scope(official_lane_key: str = OFFICIAL_LANE_KEY) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    return {
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "executable_payload_write_gate_only": True,
        "signed_order_request_created": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def _target_from_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    target = record.get("target_scope")
    return target if isinstance(target, Mapping) else {}


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    target = _target_from_record(record)
    if target.get("official_lane_key") == official_lane_key:
        return True
    for value in record.values():
        if isinstance(value, Mapping) and value.get("official_lane_key") == official_lane_key:
            return True
    return False


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r248_stop_take_profit_source_found": False,
        "r248_stop_take_profit_source_valid": False,
        "r247_executable_payload_preview_found": False,
        "r247_executable_payload_preview_valid": False,
        "r246_payload_refresh_write_found": False,
        "r246_payload_refresh_write_valid": False,
        "r244_adjusted_contract_found": False,
        "r244_adjusted_contract_valid": False,
        "r242_readonly_found": False,
        "r242_readonly_valid": False,
    }


def _empty_post_write_verification() -> dict[str, Any]:
    return {
        "executable_payload_written": False,
        "matching_executable_payload_found": False,
        "matching_executable_payload_valid": False,
        "signed": False,
        "submit_allowed": False,
        "signed_order_request_created": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def _recommended_next_operator_move(matrix: Mapping[str, Any]) -> str:
    return str(build_operator_executable_payload_write_packet(matrix)["next_required_human_action"])


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("executable_payload_written") is True:
        return "Create R250 signature gate preview from the R249 executable payload artifact; do not write signed requests, call Binance, submit, or place orders."
    if matrix.get("payload_artifact_valid") is True:
        return "Run the exact R249 confirmation only if the operator wants a local executable payload artifact; no signature or order."
    return "Fix R249 blockers before any executable payload artifact write."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "signed order request",
        "signed trading request",
        "kill switch disable",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _safety(written: bool) -> dict[str, Any]:
    safety = dict(SAFETY)
    safety["executable_payload_written"] = bool(written)
    safety["executable_payload_created"] = bool(written)
    return safety


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = lane_key.split("|")
    if len(parts) != 4:
        return "BTCUSDT", "8m", "short", "ladder_close_50_618"
    return parts[0], parts[1], parts[2], parts[3]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
