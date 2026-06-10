"""R244 guarded tiny-live leverage / notional risk-contract write gate.

This gate consumes the recorded R243 leverage/notional adjustment preview and
can write exactly one bounded local risk-contract config mutation when the
exact R244 confirmation phrase is supplied. It never calls Binance/network,
creates payloads, signs requests, places orders, mutates env/lane controls, or
disables the kill switch.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import RISK_CONTRACT_CONFIG_PATH
from src.app.hammer_radar.operator.tiny_live_leverage_notional_adjustment_preview import (
    LEDGER_FILENAME as R243_LEDGER_FILENAME,
    TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_CLEARS_BINANCE_MINIMUMS,
    TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDED,
    load_latest_tiny_live_10_of_10_ready_packet as _load_latest_tiny_live_10_of_10_ready_packet,
    load_latest_tiny_live_binance_readonly_precision_mark_price_gate as _load_latest_tiny_live_binance_readonly_precision_mark_price_gate,
    load_latest_tiny_live_risk_contract_config_write_gate as _load_latest_tiny_live_risk_contract_config_write_gate,
    load_tiny_live_leverage_notional_adjustment_preview_records,
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    load_tiny_live_risk_contract_config as _load_tiny_live_risk_contract_config,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    load_existing_tiny_live_risk_contract_config,
)

TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_READY = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_READY"
)
TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_REJECTED = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_REJECTED"
)
TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_WRITTEN = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_WRITTEN"
)
TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_BLOCKED = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_BLOCKED"
)
TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_ERROR = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_ERROR"
)

TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_READY_FOR_CONFIRMATION = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_READY_FOR_CONFIRMATION"
)
TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITTEN_PAYLOAD_REFRESH_REQUIRED = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITTEN_PAYLOAD_REFRESH_REQUIRED"
)
TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_BLOCKED_BY_R243 = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_BLOCKED_BY_R243"
)
TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_BLOCKED_BY_VALIDATION = (
    "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_BLOCKED_BY_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE"
LEDGER_FILENAME = "tiny_live_leverage_notional_risk_contract_write_gate.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
UPDATED_BY_PHASE = "R244_TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE"
ADJUSTMENT_SOURCE_PHASE = "R243_TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW"
CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_PHRASE = (
    "I CONFIRM TINY LIVE LEVERAGE NOTIONAL RISK CONTRACT WRITE GATE ONLY; "
    "WRITE RISK CONFIG ONLY; NO ORDER; NO BINANCE CALL."
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
    "risk_contract_write_gate_only": True,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R243_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_risk_contract_config_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_10_of_10_ready_packet.ndjson",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_leverage_notional_risk_contract_write_gate(
    *,
    log_dir: str | Path | None = None,
    write_risk_contract: bool = False,
    confirm_tiny_live_leverage_notional_risk_contract_write: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    config_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    confirmation_valid = (
        confirm_tiny_live_leverage_notional_risk_contract_write
        == CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_PHRASE
    )
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)

    try:
        latest_r243 = load_latest_tiny_live_leverage_notional_adjustment_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r242 = load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
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
        risk_config = load_tiny_live_risk_contract_config(config_path, official_lane_key=official_lane_key)
        existing_config = load_existing_tiny_live_risk_contract_config(config_path)
        input_summary = _build_input_summary(
            latest_r243=latest_r243,
            latest_r242=latest_r242,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_config=risk_config,
        )
        current_summary = _current_contract_summary(risk_config)
        adjusted_contract = build_adjusted_risk_contract(
            existing_risk_contract=risk_config.get("matching_risk_contract") or {},
            latest_r243=latest_r243,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        validation = validate_adjusted_risk_contract(adjusted_contract)
        preview = build_adjusted_risk_contract_write_preview(
            existing_config=existing_config,
            proposed_adjusted_contract=adjusted_contract,
            config_path=config_path,
            official_lane_key=official_lane_key,
            prerequisites_ready=input_summary["r243_adjustment_preview_ready"]
            and input_summary["adjusted_model_clears_binance_minimums"],
        )

        if write_risk_contract and not confirmation_valid:
            written = False
            overall = TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_REJECTED_BAD_CONFIRMATION
            status = TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_REJECTED
        elif not input_summary["r243_adjustment_preview_ready"] or not input_summary["adjusted_model_clears_binance_minimums"]:
            written = False
            overall = TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_BLOCKED_BY_R243
            status = TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_BLOCKED
        elif validation["valid"] is not True:
            written = False
            overall = TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_BLOCKED_BY_VALIDATION
            status = TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_BLOCKED
        elif write_risk_contract and confirmation_valid:
            write_adjusted_risk_contract_if_confirmed(
                existing_config=existing_config,
                proposed_adjusted_contract=adjusted_contract,
                config_path=config_path,
                confirm_tiny_live_leverage_notional_risk_contract_write=(
                    confirm_tiny_live_leverage_notional_risk_contract_write
                ),
                official_lane_key=official_lane_key,
            )
            written = True
            overall = TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITTEN_PAYLOAD_REFRESH_REQUIRED
            status = TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_WRITTEN
        else:
            written = False
            overall = TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_READY_FOR_CONFIRMATION
            status = TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_READY

        post_write = build_post_write_adjusted_risk_contract_verification(
            config_path=config_path,
            official_lane_key=official_lane_key,
            risk_contract_written=written,
        )
        matrix = build_adjusted_risk_contract_write_gate_matrix(
            input_summary=input_summary,
            adjusted_contract_validation=validation,
            risk_contract_write_confirmed=bool(write_risk_contract and confirmation_valid),
            risk_contract_written=written,
        )
        operator_packet = build_operator_adjusted_risk_contract_write_review_packet(
            matrix,
            write_requested=write_risk_contract,
        )
        safety = dict(SAFETY)
        if written:
            safety["config_written"] = True
            safety["risk_contract_config_written"] = True
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "risk_contract_written": written,
            "write_risk_contract_requested": bool(write_risk_contract),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "official_lane_key": official_lane_key,
                "symbol": symbol,
                "direction": direction,
                "risk_contract_write_gate_only": True,
                "config_written": written,
                "live_authorized": False,
                "live_execution_enabled": False,
                "order_placed": False,
                "binance_call_allowed": False,
                "network_allowed": False,
            },
            "input_summary": input_summary,
            "current_contract_summary": current_summary,
            "adjusted_contract_write_preview": preview,
            "adjusted_contract_validation": validation,
            "post_write_verification": post_write,
            "risk_contract_write_gate_matrix": matrix,
            "operator_risk_contract_write_review_packet": operator_packet,
            "recommended_next_operator_move": _recommended_next_operator_move(matrix),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
            "risk_contract_write_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if write_risk_contract:
            record = append_tiny_live_leverage_notional_risk_contract_write_gate_record(
                payload,
                log_dir=resolved_log_dir,
            )
            payload["risk_contract_write_gate_record_id"] = record["risk_contract_write_gate_record_id"]
            payload["ledger_path"] = str(
                tiny_live_leverage_notional_risk_contract_write_gate_records_path(resolved_log_dir)
            )
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "risk_contract_written": False,
                "write_risk_contract_requested": bool(write_risk_contract),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "direction": direction,
                    "risk_contract_write_gate_only": True,
                    "config_written": False,
                    "live_authorized": False,
                    "live_execution_enabled": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": _empty_input_summary(config_path.exists()),
                "current_contract_summary": _empty_current_contract_summary(),
                "adjusted_contract_write_preview": _empty_write_preview(config_path, official_lane_key),
                "adjusted_contract_validation": {"valid": False, "errors": ["r244_write_gate_error"], "warnings": []},
                "post_write_verification": build_post_write_adjusted_risk_contract_verification(
                    config_path=config_path,
                    official_lane_key=official_lane_key,
                    risk_contract_written=False,
                ),
                "risk_contract_write_gate_matrix": build_adjusted_risk_contract_write_gate_matrix(
                    input_summary=_empty_input_summary(config_path.exists()),
                    adjusted_contract_validation={"valid": False, "errors": ["r244_write_gate_error"], "warnings": []},
                    risk_contract_write_confirmed=False,
                    risk_contract_written=False,
                    blocked_by=["r244_write_gate_error"],
                ),
                "operator_risk_contract_write_review_packet": build_operator_adjusted_risk_contract_write_review_packet(
                    {"blocked_by": ["r244_write_gate_error"]},
                    write_requested=write_risk_contract,
                ),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R244 write-gate error before any payload refresh.",
                "risk_contract_write_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_leverage_notional_adjustment_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_leverage_notional_adjustment_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        matrix = record.get("adjustment_gate_matrix") if isinstance(record.get("adjustment_gate_matrix"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDED
            and record.get("adjustment_preview_recorded") is True
            and record.get("adjustment_preview_overall_status")
            == TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_CLEARS_BINANCE_MINIMUMS
            and matrix.get("clears_binance_minimums") is True
            and not matrix.get("blocked_by")
        ):
            return _sanitize({**record, "r243_adjustment_preview_found": True})
    return {}


def load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
        log_dir=log_dir,
        official_lane_key=official_lane_key,
    )


def load_latest_tiny_live_risk_contract_config_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_tiny_live_risk_contract_config_write_gate(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_10_of_10_ready_packet(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_tiny_live_10_of_10_ready_packet(log_dir=log_dir, official_lane_key=official_lane_key)


def load_tiny_live_risk_contract_config(
    config_path: str | Path | None = None,
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return _load_tiny_live_risk_contract_config(config_path, official_lane_key=official_lane_key)


def build_adjusted_risk_contract(
    *,
    existing_risk_contract: Mapping[str, Any],
    latest_r243: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    base = _sanitize(dict(existing_risk_contract)) if isinstance(existing_risk_contract, Mapping) else {}
    contract = {
        **base,
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "capital_mode": "tiny_live_margin_10x",
        "tiny_live_margin_usdt": 44,
        "margin_budget_usdt": 44,
        "max_margin_usdt": 44,
        "leverage": 10,
        "max_notional_usdt": 440,
        "max_position_notional_usdt": 440,
        "max_account_risk_usdt": 44,
        "max_loss_usdt": 4.44,
        "max_loss_requires_review": True,
        "risk_reward_ratio": 2.0,
        "stop_required": True,
        "protective_stop_required": True,
        "take_profit_required": True,
        "kill_switch_required": True,
        "operator_final_approval_required": True,
        "live_authorization_required_later": True,
        "live_authorized": False,
        "live_execution_enabled": False,
        "enabled_for_preflight": False,
        "approved": False,
        "order_payload_forbidden_until_live_gate": True,
        "binance_call_forbidden_until_live_gate": True,
        "approval_status": "CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED",
        "adjustment_source_phase": ADJUSTMENT_SOURCE_PHASE,
        "updated_by_phase": UPDATED_BY_PHASE,
        "updated_at": generated_at.isoformat(),
        "source_adjustment_preview_record_id": latest_r243.get("adjustment_preview_record_id"),
        "notes": [
            "R244 updates the risk contract to model 44 USDT margin at 10x leverage.",
            "Max notional becomes 440 USDT so BTCUSDT quantity clears Binance step size/min notional.",
            "This config write does not enable live execution, create payloads, sign requests, or place orders.",
        ],
    }
    if "contract_id" not in contract:
        contract["contract_id"] = f"r244_contract_{symbol}_{timeframe}_{direction}_{entry_mode}"
    if "contract_version" not in contract:
        contract["contract_version"] = "tiny_live_risk_contract_v1"
    return _sanitize(contract)


def validate_adjusted_risk_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    expected = {
        "official_lane_key": OFFICIAL_LANE_KEY,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "margin_budget_usdt": 44,
        "tiny_live_margin_usdt": 44,
        "leverage": 10,
        "max_notional_usdt": 440,
        "max_position_notional_usdt": 440,
        "max_account_risk_usdt": 44,
        "max_loss_usdt": 4.44,
        "approval_status": "CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED",
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            errors.append(f"{key}_invalid")
    required_true = (
        "max_loss_requires_review",
        "stop_required",
        "protective_stop_required",
        "take_profit_required",
        "kill_switch_required",
        "operator_final_approval_required",
        "order_payload_forbidden_until_live_gate",
        "binance_call_forbidden_until_live_gate",
    )
    for key in required_true:
        if contract.get(key) is not True:
            errors.append(f"{key}_not_true")
    required_false = ("live_authorized", "live_execution_enabled", "enabled_for_preflight")
    for key in required_false:
        if contract.get(key) is not False:
            errors.append(f"{key}_not_false")
    notes = contract.get("notes")
    if not isinstance(notes, list) or not notes:
        warnings.append("notes_missing")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def build_adjusted_risk_contract_write_preview(
    *,
    existing_config: Mapping[str, Any],
    proposed_adjusted_contract: Mapping[str, Any],
    config_path: str | Path,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    prerequisites_ready: bool = True,
) -> dict[str, Any]:
    existing = _find_contract(existing_config.get("payload"), official_lane_key)
    new_or_updated = "new"
    if existing is not None:
        new_or_updated = "unchanged" if _contract_equivalent(existing, proposed_adjusted_contract) else "update"
    return {
        "would_write": bool(prerequisites_ready and new_or_updated != "unchanged"),
        "write_requires_confirmation": True,
        "config_path": str(config_path),
        "target_contract_key": official_lane_key,
        "new_or_updated": new_or_updated,
        "bounded_mutation_only": True,
        "matching_existing_contract_found": existing is not None,
        "proposed_adjusted_contract": _sanitize(dict(proposed_adjusted_contract)),
    }


def write_adjusted_risk_contract_if_confirmed(
    *,
    existing_config: Mapping[str, Any],
    proposed_adjusted_contract: Mapping[str, Any],
    config_path: str | Path,
    confirm_tiny_live_leverage_notional_risk_contract_write: str | None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    if confirm_tiny_live_leverage_notional_risk_contract_write != CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_PHRASE:
        return {"written": False, "reason": "bad_confirmation"}
    validation = validate_adjusted_risk_contract(proposed_adjusted_contract)
    if validation["valid"] is not True:
        return {"written": False, "reason": "validation_failed", "validation": validation}
    payload = _merge_contract(existing_config.get("payload"), proposed_adjusted_contract, official_lane_key)
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_sanitize(payload), sort_keys=True, indent=2) + "\n"
    with NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        handle.write(text)
        tmp_path = Path(handle.name)
    tmp_path.replace(path)
    return {"written": True, "config_path": str(path)}


def build_post_write_adjusted_risk_contract_verification(
    *,
    config_path: str | Path,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_written: bool = False,
) -> dict[str, Any]:
    existing = load_existing_tiny_live_risk_contract_config(config_path)
    contract = _find_contract(existing.get("payload"), official_lane_key)
    validation = validate_adjusted_risk_contract(contract or {})
    return {
        "risk_contract_written": bool(risk_contract_written),
        "matching_adjusted_contract_found": contract is not None,
        "matching_adjusted_contract_valid": bool(contract is not None and validation["valid"]),
        "leverage": contract.get("leverage") if isinstance(contract, Mapping) else None,
        "margin_budget_usdt": contract.get("margin_budget_usdt") if isinstance(contract, Mapping) else None,
        "max_notional_usdt": contract.get("max_notional_usdt") if isinstance(contract, Mapping) else None,
        "live_authorized": bool(contract.get("live_authorized")) if isinstance(contract, Mapping) else False,
        "live_execution_enabled": bool(contract.get("live_execution_enabled")) if isinstance(contract, Mapping) else False,
        "order_payload_created": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def build_adjusted_risk_contract_write_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    adjusted_contract_validation: Mapping[str, Any],
    risk_contract_write_confirmed: bool,
    risk_contract_written: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if not input_summary.get("r243_adjustment_preview_ready"):
        blockers.append("r243_adjustment_preview_not_ready")
    if not input_summary.get("adjusted_model_clears_binance_minimums"):
        blockers.append("adjusted_model_does_not_clear_binance_minimums")
    if adjusted_contract_validation.get("valid") is not True:
        blockers.extend(str(item) for item in adjusted_contract_validation.get("errors") or ["adjusted_contract_invalid"])
    if not risk_contract_write_confirmed:
        blockers.append("exact_r244_risk_contract_write_confirmation_required")
    if risk_contract_written:
        blockers = ["payload_refresh_required", "live_authorization_absent", "live_execution_disabled"]
    return {
        "r243_adjustment_preview_ready": bool(input_summary.get("r243_adjustment_preview_ready")),
        "adjusted_model_clears_binance_minimums": bool(input_summary.get("adjusted_model_clears_binance_minimums")),
        "adjusted_contract_valid": adjusted_contract_validation.get("valid") is True,
        "risk_contract_write_confirmed": bool(risk_contract_write_confirmed),
        "risk_contract_written": bool(risk_contract_written),
        "config_written": bool(risk_contract_written),
        "live_authorized": False,
        "live_execution_enabled": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_adjusted_risk_contract_write_review_packet(
    risk_contract_write_gate_matrix: Mapping[str, Any],
    *,
    write_requested: bool = False,
) -> dict[str, Any]:
    written = risk_contract_write_gate_matrix.get("risk_contract_written") is True
    ready = (
        risk_contract_write_gate_matrix.get("r243_adjustment_preview_ready") is True
        and risk_contract_write_gate_matrix.get("adjusted_model_clears_binance_minimums") is True
        and risk_contract_write_gate_matrix.get("adjusted_contract_valid") is True
        and not written
    )
    if written:
        action = "REVIEW_R244_RESULT"
    elif ready:
        action = "CONFIRM_R244_RISK_CONTRACT_WRITE"
    else:
        action = "WAIT"
    return {
        "operator_should_review_risk_contract_write": bool(ready or written or write_requested),
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


def classify_tiny_live_leverage_notional_risk_contract_write_status(payload: Mapping[str, Any]) -> str:
    return str(payload.get("risk_contract_write_overall_status") or UNKNOWN_NEEDS_MANUAL_REVIEW)


def append_tiny_live_leverage_notional_risk_contract_write_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_leverage_notional_risk_contract_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "risk_contract_write_gate_record_id": record.get("risk_contract_write_gate_record_id")
            or f"r244_leverage_notional_risk_contract_write_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "risk_contract_written": record.get("risk_contract_written") is True,
            "write_risk_contract_requested": record.get("write_risk_contract_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "current_contract_summary": dict(record.get("current_contract_summary") or {}),
            "adjusted_contract_write_preview": dict(record.get("adjusted_contract_write_preview") or {}),
            "adjusted_contract_validation": dict(record.get("adjusted_contract_validation") or {}),
            "post_write_verification": dict(record.get("post_write_verification") or {}),
            "risk_contract_write_gate_matrix": dict(record.get("risk_contract_write_gate_matrix") or {}),
            "operator_risk_contract_write_review_packet": dict(
                record.get("operator_risk_contract_write_review_packet") or {}
            ),
            "risk_contract_write_overall_status": record.get("risk_contract_write_overall_status"),
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


def load_tiny_live_leverage_notional_risk_contract_write_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_leverage_notional_risk_contract_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_leverage_notional_risk_contract_write_gate_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_risk_contract_written": latest.get("risk_contract_written") is True,
        "latest_overall_status": latest.get("risk_contract_write_overall_status"),
    }


def tiny_live_leverage_notional_risk_contract_write_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_leverage_notional_risk_contract_write_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r243: Mapping[str, Any],
    latest_r242: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_config: Mapping[str, Any],
) -> dict[str, Any]:
    r243_matrix = latest_r243.get("adjustment_gate_matrix") if isinstance(latest_r243.get("adjustment_gate_matrix"), Mapping) else {}
    r242_result = latest_r242.get("binance_readonly_result") if isinstance(latest_r242.get("binance_readonly_result"), Mapping) else {}
    r230_matrix = latest_r230.get("risk_contract_config_gate_matrix") if isinstance(latest_r230.get("risk_contract_config_gate_matrix"), Mapping) else {}
    r228_matrix = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    return {
        "r243_adjustment_preview_found": bool(latest_r243),
        "r243_adjustment_preview_ready": (
            bool(latest_r243)
            and latest_r243.get("adjustment_preview_recorded") is True
            and r243_matrix.get("clears_binance_minimums") is True
            and not r243_matrix.get("blocked_by")
        ),
        "adjusted_model_clears_binance_minimums": r243_matrix.get("clears_binance_minimums") is True,
        "r242_readonly_found": bool(latest_r242),
        "r242_readonly_valid": (
            bool(latest_r242)
            and latest_r242.get("readonly_fetch_performed") is True
            and r242_result.get("exchange_info_endpoint_called") is True
            and r242_result.get("mark_price_endpoint_called") is True
        ),
        "existing_risk_contract_found": bool(risk_config.get("matching_risk_contract")),
        "existing_risk_contract_valid": bool(risk_config.get("matching_risk_contract")),
        "r230_risk_contract_config_found": bool(latest_r230),
        "r230_risk_contract_config_written": r230_matrix.get("risk_contract_config_written") is True,
        "r228_evidence_ready": r228_matrix.get("evidence_ready") is True,
    }


def _current_contract_summary(risk_config: Mapping[str, Any]) -> dict[str, Any]:
    contract = risk_config.get("matching_risk_contract") if isinstance(risk_config.get("matching_risk_contract"), Mapping) else {}
    return {
        "leverage": contract.get("leverage"),
        "max_notional_usdt": contract.get("max_notional_usdt"),
        "margin_budget_usdt": contract.get("margin_budget_usdt"),
        "quantity_rounds_to_zero": True if contract.get("max_notional_usdt") == 44 else None,
    }


def _empty_input_summary(config_found: bool = False) -> dict[str, Any]:
    return {
        "r243_adjustment_preview_found": False,
        "r243_adjustment_preview_ready": False,
        "adjusted_model_clears_binance_minimums": False,
        "r242_readonly_found": False,
        "r242_readonly_valid": False,
        "existing_risk_contract_found": config_found,
        "existing_risk_contract_valid": False,
        "r228_evidence_ready": False,
    }


def _empty_current_contract_summary() -> dict[str, Any]:
    return {"leverage": None, "max_notional_usdt": None, "margin_budget_usdt": None, "quantity_rounds_to_zero": None}


def _empty_write_preview(config_path: str | Path, official_lane_key: str) -> dict[str, Any]:
    return {
        "would_write": False,
        "write_requires_confirmation": True,
        "config_path": str(config_path),
        "target_contract_key": official_lane_key,
        "bounded_mutation_only": True,
        "proposed_adjusted_contract": {},
    }


def _recommended_next_operator_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("risk_contract_written") is True:
        return "REVIEW_R244_RESULT"
    if (
        matrix.get("r243_adjustment_preview_ready") is True
        and matrix.get("adjusted_model_clears_binance_minimums") is True
        and matrix.get("adjusted_contract_valid") is True
    ):
        return "CONFIRM_R244_RISK_CONTRACT_WRITE"
    return "WAIT"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("risk_contract_written") is True:
        return "Create R245 non-executable order payload refresh preview using the R244 10x / 440 USDT risk contract; no signed request, no order, no Binance order endpoint."
    if (
        matrix.get("r243_adjustment_preview_ready") is True
        and matrix.get("adjusted_model_clears_binance_minimums") is True
        and matrix.get("adjusted_contract_valid") is True
    ):
        return "Await exact R244 confirmation before writing only the adjusted risk-contract config."
    return "Fix R244 input or validation blockers before any config write."


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


def _merge_contract(payload: Any, proposed_contract: Mapping[str, Any], official_lane_key: str) -> dict[str, Any]:
    merged = _sanitize(dict(payload)) if isinstance(payload, Mapping) else {}
    if isinstance(merged.get("risk_contracts"), list):
        contracts = [_sanitize(contract) for contract in merged["risk_contracts"] if isinstance(contract, Mapping)]
        replaced = False
        for index, contract in enumerate(contracts):
            if _contract_matches_lane(contract, official_lane_key):
                contracts[index] = _sanitize(dict(proposed_contract))
                replaced = True
                break
        if not replaced:
            contracts.append(_sanitize(dict(proposed_contract)))
        merged["risk_contracts"] = contracts
        return merged
    if isinstance(merged.get("contracts"), Mapping):
        contracts_dict = dict(merged["contracts"])
        contracts_dict[official_lane_key] = _sanitize(dict(proposed_contract))
        merged["contracts"] = contracts_dict
        return merged
    merged["contracts"] = {official_lane_key: _sanitize(dict(proposed_contract))}
    return merged


def _find_contract(payload: Any, official_lane_key: str) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    contracts_dict = payload.get("contracts")
    if isinstance(contracts_dict, Mapping) and isinstance(contracts_dict.get(official_lane_key), Mapping):
        return _sanitize(dict(contracts_dict[official_lane_key]))
    contracts = payload.get("risk_contracts")
    if isinstance(contracts, list):
        for contract in contracts:
            if isinstance(contract, Mapping) and _contract_matches_lane(contract, official_lane_key):
                return _sanitize(dict(contract))
    return None


def _contract_matches_lane(contract: Mapping[str, Any], official_lane_key: str) -> bool:
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    return (
        contract.get("official_lane_key") == official_lane_key
        or (
            str(contract.get("symbol") or "") == symbol
            and str(contract.get("timeframe") or "") == timeframe
            and str(contract.get("direction") or "") == direction
            and str(contract.get("entry_mode") or "") == entry_mode
        )
    )


def _contract_equivalent(existing: Mapping[str, Any], proposed: Mapping[str, Any]) -> bool:
    comparable_keys = [
        "official_lane_key",
        "symbol",
        "timeframe",
        "direction",
        "entry_mode",
        "capital_mode",
        "tiny_live_margin_usdt",
        "margin_budget_usdt",
        "leverage",
        "max_notional_usdt",
        "max_position_notional_usdt",
        "max_loss_usdt",
        "max_loss_requires_review",
        "approval_status",
        "live_authorized",
        "live_execution_enabled",
        "enabled_for_preflight",
    ]
    return all(existing.get(key) == proposed.get(key) for key in comparable_keys)


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
            seen.add(text)
            result.append(text)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
