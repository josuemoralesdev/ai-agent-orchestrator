"""R230 guarded tiny-live risk-contract config write gate.

This module consumes the latest R229 preview and can write exactly one bounded
local config mutation when the exact R230 confirmation phrase is supplied.
It never enables live execution, arms a lane, creates order payloads, calls
Binance/network, or mutates env/lane/fisherman/scheduler config.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import RISK_CONTRACT_CONFIG_PATH
from src.app.hammer_radar.operator.tiny_live_risk_contract_preview import (
    LEDGER_FILENAME as R229_LEDGER_FILENAME,
    TINY_LIVE_RISK_CONTRACT_PREVIEW_READY,
    TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED,
    TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER,
    load_tiny_live_risk_contract_preview_records,
)

TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_READY = "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_READY"
TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_REJECTED = "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_REJECTED"
TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_WRITTEN = "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_WRITTEN"
TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_BLOCKED = "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_BLOCKED"
TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_ERROR = "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_ERROR"

TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_READY_FOR_CONFIRMATION = (
    "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_READY_FOR_CONFIRMATION"
)
TINY_LIVE_RISK_CONTRACT_CONFIG_WRITTEN_LIVE_AUTH_REQUIRED_LATER = (
    "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITTEN_LIVE_AUTH_REQUIRED_LATER"
)
TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_BLOCKED_BY_R229_PREVIEW = (
    "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_BLOCKED_BY_R229_PREVIEW"
)
TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_BLOCKED_BY_VALIDATION = (
    "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_BLOCKED_BY_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE"
LEDGER_FILENAME = "tiny_live_risk_contract_config_write_gate.ndjson"
CONFIRM_TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_PHRASE = (
    "I CONFIRM TINY LIVE RISK CONTRACT CONFIG WRITE ONLY; NO LIVE ENABLE; NO ORDER; NO BINANCE CALL."
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CONTRACT_VERSION = "tiny_live_risk_contract_v1"
CREATED_BY_PHASE = "R230_TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE"

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
    "registry_config_written": False,
    "scoring_config_written": False,
    "matrix_config_written": False,
    "ledger_rewritten": False,
    "destructive_write": False,
    "historical_ledger_rewritten": False,
    "normalized_rows_appended": False,
    "paper_outcome_ledger_rewritten": False,
    "paper_outcomes_appended": False,
    "strategy_performance_appended": False,
    "strategy_promotion_status_appended": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
    "live_authorization_created": False,
    "live_execution_enabled": False,
    "signal_origin_promoted": False,
    "lane_promoted": False,
    "official_tiny_live_lane_changed": False,
    "alternate_lane_promoted": False,
    "betrayal_live_authorized": False,
    "betrayal_promoted": False,
    "risk_contract_config_write_gate_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/tiny_live_risk_contract_preview.py",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{R229_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_risk_contract_config_write_gate(
    *,
    log_dir: str | Path | None = None,
    write_risk_config: bool = False,
    confirm_tiny_live_risk_contract_config_write: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    config_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    confirmation_valid = confirm_tiny_live_risk_contract_config_write == CONFIRM_TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_PHRASE
    try:
        latest_preview = load_latest_tiny_live_risk_contract_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        existing_config = load_existing_tiny_live_risk_contract_config(config_path)
        proposed_contract = build_tiny_live_risk_contract_config_entry(
            latest_preview=latest_preview,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        validation = validate_tiny_live_risk_contract_config_entry(proposed_contract)
        preview = build_config_write_preview(
            existing_config=existing_config,
            proposed_contract=proposed_contract,
            config_path=config_path,
            official_lane_key=official_lane_key,
        )
        r229_ready = _r229_preview_ready(latest_preview, official_lane_key=official_lane_key)
        if write_risk_config and not confirmation_valid:
            written = False
            overall = TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_REJECTED_BAD_CONFIRMATION
            status = TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_REJECTED
        elif write_risk_config and confirmation_valid and r229_ready and validation["valid"]:
            write_tiny_live_risk_contract_config_if_confirmed(
                existing_config=existing_config,
                proposed_contract=proposed_contract,
                config_path=config_path,
                confirm_tiny_live_risk_contract_config_write=confirm_tiny_live_risk_contract_config_write,
                official_lane_key=official_lane_key,
            )
            written = True
            overall = TINY_LIVE_RISK_CONTRACT_CONFIG_WRITTEN_LIVE_AUTH_REQUIRED_LATER
            status = TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_WRITTEN
        elif not r229_ready:
            written = False
            overall = TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_BLOCKED_BY_R229_PREVIEW
            status = TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_BLOCKED
        elif not validation["valid"]:
            written = False
            overall = TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_BLOCKED_BY_VALIDATION
            status = TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_BLOCKED
        else:
            written = False
            overall = TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_READY_FOR_CONFIRMATION
            status = TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_READY

        post_write = build_post_write_verification(
            config_path=config_path,
            official_lane_key=official_lane_key,
        )
        matrix = build_risk_contract_config_gate_matrix(
            r229_preview_ready=r229_ready,
            config_entry_valid=validation["valid"],
            config_write_confirmed=confirmation_valid and write_risk_config,
            risk_contract_config_written=written,
        )
        operator_packet = build_operator_config_write_review_packet(matrix, write_requested=write_risk_config)
        safety = dict(SAFETY)
        if written:
            safety["config_written"] = True
            safety["risk_contract_config_written"] = True
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "config_written": written,
            "record_gate_requested": bool(write_risk_config),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(official_lane_key),
            "input_summary": {
                "r229_preview_found": bool(latest_preview),
                "r229_preview_ready": r229_ready,
                "existing_config_found": existing_config["config_found"],
                "matching_existing_contract_found": preview["matching_existing_contract_found"],
            },
            "config_write_preview": preview,
            "config_entry_validation": validation,
            "post_write_verification": post_write,
            "risk_contract_config_gate_matrix": matrix,
            "operator_config_write_review_packet": operator_packet,
            "recommended_next_operator_move": _recommended_next_operator_move(matrix, write_requested=write_risk_config),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
            "config_write_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if write_risk_config:
            record = append_tiny_live_risk_contract_config_write_gate_record(payload, log_dir=resolved_log_dir)
            payload["gate_record_id"] = record["gate_record_id"]
            payload["ledger_path"] = str(tiny_live_risk_contract_config_write_gate_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "config_written": False,
                "record_gate_requested": bool(write_risk_config),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(official_lane_key),
                "input_summary": {
                    "r229_preview_found": False,
                    "r229_preview_ready": False,
                    "existing_config_found": config_path.exists(),
                    "matching_existing_contract_found": False,
                },
                "config_write_preview": _empty_config_write_preview(config_path, official_lane_key),
                "config_entry_validation": {"valid": False, "errors": ["config_write_gate_error"], "warnings": []},
                "post_write_verification": build_post_write_verification(
                    config_path=config_path,
                    official_lane_key=official_lane_key,
                ),
                "risk_contract_config_gate_matrix": build_risk_contract_config_gate_matrix(
                    r229_preview_ready=False,
                    config_entry_valid=False,
                    config_write_confirmed=False,
                    risk_contract_config_written=False,
                    blocked_by=["config_write_gate_error"],
                ),
                "operator_config_write_review_packet": build_operator_config_write_review_packet(
                    build_risk_contract_config_gate_matrix(
                        r229_preview_ready=False,
                        config_entry_valid=False,
                        config_write_confirmed=False,
                        risk_contract_config_written=False,
                        blocked_by=["config_write_gate_error"],
                    ),
                    write_requested=write_risk_config,
                ),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R230 config-write gate error before any later live authorization preview.",
                "config_write_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_risk_contract_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_risk_contract_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        preview = record.get("risk_contract_preview") if isinstance(record.get("risk_contract_preview"), Mapping) else {}
        if str(target.get("official_lane_key") or preview.get("official_lane_key") or "") == official_lane_key:
            return _sanitize({**record, "r229_preview_found": True})
    return {}


def load_existing_tiny_live_risk_contract_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path is not None else RISK_CONTRACT_CONFIG_PATH
    if not path.exists():
        return {"config_found": False, "config_path": str(path), "payload": {}, "shape": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"config_found": True, "config_path": str(path), "payload": {}, "shape": "invalid", "read_error": True}
    shape = "dict"
    if isinstance(payload, Mapping) and isinstance(payload.get("risk_contracts"), list):
        shape = "risk_contracts_list"
    elif isinstance(payload, Mapping) and isinstance(payload.get("contracts"), Mapping):
        shape = "contracts_dict"
    return {"config_found": True, "config_path": str(path), "payload": _sanitize(payload), "shape": shape}


def build_tiny_live_risk_contract_config_entry(
    *,
    latest_preview: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    preview = latest_preview.get("risk_contract_preview") if isinstance(latest_preview.get("risk_contract_preview"), Mapping) else {}
    margin = _number_or(preview.get("proposed_tiny_live_margin_usdt"), 44)
    leverage = int(_number_or(preview.get("proposed_leverage"), 1))
    max_notional = _number_or(preview.get("proposed_max_notional_usdt"), margin * leverage)
    max_loss = _number_or(preview.get("proposed_max_loss_usdt"), 4.44)
    return {
        "contract_id": f"r230_contract_{symbol}_{timeframe}_{direction}_{entry_mode}",
        "contract_version": CONTRACT_VERSION,
        "source_preview_id": latest_preview.get("risk_preview_record_id")
        or preview.get("contract_id")
        or f"r229_preview_{symbol}_{timeframe}_{direction}_{entry_mode}",
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "capital_mode": "tiny_live",
        "max_account_risk_usdt": margin,
        "tiny_live_margin_usdt": margin,
        "max_margin_usdt": margin,
        "leverage": leverage,
        "max_notional_usdt": max_notional,
        "max_position_notional_usdt": max_notional,
        "max_loss_usdt": max_loss,
        "risk_reward_ratio": _number_or(preview.get("risk_reward_ratio_preview"), 2.0),
        "stop_required": True,
        "protective_stop_required": True,
        "take_profit_required": True,
        "kill_switch_required": True,
        "operator_final_approval_required": True,
        "live_authorization_required_later": True,
        "order_payload_forbidden_until_live_gate": True,
        "binance_call_forbidden_until_live_gate": True,
        "approval_status": "CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED",
        "live_authorized": False,
        "live_execution_enabled": False,
        "enabled_for_preflight": False,
        "approved": False,
        "created_by_phase": CREATED_BY_PHASE,
        "created_at": generated_at.isoformat(),
        "notes": [
            "R230 writes only this local risk-contract config entry.",
            "Live authorization, lane arming, order payload creation, and Binance/network calls remain forbidden.",
            "A later phase must separately preview live authorization requirements before any live action.",
        ],
    }


def build_config_write_preview(
    *,
    existing_config: Mapping[str, Any],
    proposed_contract: Mapping[str, Any],
    config_path: str | Path,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    existing = _find_contract(existing_config.get("payload"), official_lane_key)
    new_or_updated = "new"
    if existing is not None:
        new_or_updated = "unchanged" if _contract_equivalent(existing, proposed_contract) else "update"
    return {
        "config_path": str(config_path),
        "would_write": new_or_updated != "unchanged",
        "write_requires_confirmation": True,
        "target_contract_key": official_lane_key,
        "new_or_updated": new_or_updated,
        "bounded_mutation_only": True,
        "matching_existing_contract_found": existing is not None,
        "proposed_contract": _sanitize(dict(proposed_contract)),
    }


def validate_tiny_live_risk_contract_config_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    expected = {
        "official_lane_key": OFFICIAL_LANE_KEY,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "approval_status": "CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED",
    }
    for key, value in expected.items():
        if entry.get(key) != value:
            errors.append(f"{key}_invalid")
    margin = _number_or_none(entry.get("tiny_live_margin_usdt"))
    leverage = _number_or_none(entry.get("leverage"))
    max_notional = _number_or_none(entry.get("max_notional_usdt"))
    max_loss = _number_or_none(entry.get("max_loss_usdt"))
    if margin is None or margin <= 0:
        errors.append("tiny_live_margin_usdt_invalid")
    if leverage is None or leverage < 1:
        errors.append("leverage_invalid")
    if margin is not None and leverage is not None and max_notional != margin * leverage:
        errors.append("max_notional_usdt_invalid")
    if max_loss is None or max_loss <= 0:
        errors.append("max_loss_usdt_invalid")
    if margin is not None and max_loss is not None and max_loss > margin:
        errors.append("max_loss_usdt_exceeds_margin")
    for key in (
        "stop_required",
        "take_profit_required",
        "kill_switch_required",
        "operator_final_approval_required",
        "live_authorization_required_later",
        "order_payload_forbidden_until_live_gate",
        "binance_call_forbidden_until_live_gate",
    ):
        if entry.get(key) is not True:
            errors.append(f"{key}_not_true")
    if entry.get("live_authorized") not in (None, False):
        errors.append("live_authorized_not_false")
    if entry.get("live_execution_enabled") not in (None, False):
        errors.append("live_execution_enabled_not_false")
    if entry.get("enabled_for_preflight") is True:
        warnings.append("enabled_for_preflight_true_would_not_authorize_live_but_is_unexpected")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def write_tiny_live_risk_contract_config_if_confirmed(
    *,
    existing_config: Mapping[str, Any],
    proposed_contract: Mapping[str, Any],
    config_path: str | Path,
    confirm_tiny_live_risk_contract_config_write: str | None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    if confirm_tiny_live_risk_contract_config_write != CONFIRM_TINY_LIVE_RISK_CONTRACT_CONFIG_WRITE_PHRASE:
        return {"written": False, "reason": "bad_confirmation"}
    validation = validate_tiny_live_risk_contract_config_entry(proposed_contract)
    if not validation["valid"]:
        return {"written": False, "reason": "validation_failed", "validation": validation}
    payload = _merge_contract(existing_config.get("payload"), proposed_contract, official_lane_key)
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_sanitize(payload), sort_keys=True, indent=2) + "\n"
    with NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        handle.write(text)
        tmp_path = Path(handle.name)
    tmp_path.replace(path)
    return {"written": True, "config_path": str(path)}


def build_post_write_verification(
    *,
    config_path: str | Path,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    path = Path(config_path)
    existing = load_existing_tiny_live_risk_contract_config(path)
    contract = _find_contract(existing.get("payload"), official_lane_key)
    validation = validate_tiny_live_risk_contract_config_entry(contract or {})
    return {
        "config_path": str(path),
        "config_exists": path.exists(),
        "matching_contract_found": contract is not None,
        "matching_contract_valid": bool(contract is not None and validation["valid"]),
        "live_authorized": bool(contract.get("live_authorized")) if isinstance(contract, Mapping) else False,
        "live_execution_enabled": bool(contract.get("live_execution_enabled")) if isinstance(contract, Mapping) else False,
        "order_payload_created": False,
    }


def build_risk_contract_config_gate_matrix(
    *,
    r229_preview_ready: bool,
    config_entry_valid: bool,
    config_write_confirmed: bool,
    risk_contract_config_written: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if not r229_preview_ready:
        blockers.append("r229_preview_not_ready")
    if not config_entry_valid:
        blockers.append("config_entry_invalid")
    if not config_write_confirmed:
        blockers.append("exact_config_write_confirmation_required")
    if risk_contract_config_written:
        blockers = ["live_authorization_absent", "live_execution_disabled", "order_payload_forbidden"]
    return {
        "r229_preview_ready": bool(r229_preview_ready),
        "config_entry_valid": bool(config_entry_valid),
        "config_write_confirmed": bool(config_write_confirmed),
        "risk_contract_config_written": bool(risk_contract_config_written),
        "risk_contract_approved": False,
        "live_authorization_ready": False,
        "live_execution_ready": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": blockers,
    }


def build_operator_config_write_review_packet(
    risk_contract_config_gate_matrix: Mapping[str, Any],
    *,
    write_requested: bool = False,
) -> dict[str, Any]:
    written = risk_contract_config_gate_matrix.get("risk_contract_config_written") is True
    ready = (
        risk_contract_config_gate_matrix.get("r229_preview_ready") is True
        and risk_contract_config_gate_matrix.get("config_entry_valid") is True
        and not written
    )
    if written:
        action = "REVIEW_R230_RESULT"
    elif ready:
        action = "CONFIRM_R230_CONFIG_WRITE"
    else:
        action = "WAIT"
    return {
        "operator_should_review_config_write": bool(ready or written or write_requested),
        "operator_confirmation_required": True,
        "operator_should_enable_live": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not enable live",
            "do not disable kill switch",
            "do not arm lane from this phase",
        ],
    }


def classify_tiny_live_risk_contract_config_write_status(payload: Mapping[str, Any]) -> str:
    return str(payload.get("config_write_overall_status") or UNKNOWN_NEEDS_MANUAL_REVIEW)


def append_tiny_live_risk_contract_config_write_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_risk_contract_config_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "gate_record_id": record.get("gate_record_id") or f"r230_config_write_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "config_written": record.get("config_written") is True,
            "record_gate_requested": record.get("record_gate_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "config_write_preview": dict(record.get("config_write_preview") or {}),
            "config_entry_validation": dict(record.get("config_entry_validation") or {}),
            "post_write_verification": dict(record.get("post_write_verification") or {}),
            "risk_contract_config_gate_matrix": dict(record.get("risk_contract_config_gate_matrix") or {}),
            "operator_config_write_review_packet": dict(record.get("operator_config_write_review_packet") or {}),
            "config_write_overall_status": record.get("config_write_overall_status"),
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


def load_tiny_live_risk_contract_config_write_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_risk_contract_config_write_gate_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_tiny_live_risk_contract_config_write_gate_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_config_written": latest.get("config_written") is True,
        "latest_overall_status": latest.get("config_write_overall_status"),
    }


def tiny_live_risk_contract_config_write_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_risk_contract_config_write_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _r229_preview_ready(latest_preview: Mapping[str, Any], *, official_lane_key: str) -> bool:
    target = latest_preview.get("target_scope") if isinstance(latest_preview.get("target_scope"), Mapping) else {}
    preview = latest_preview.get("risk_contract_preview") if isinstance(latest_preview.get("risk_contract_preview"), Mapping) else {}
    matrix = latest_preview.get("risk_gate_matrix") if isinstance(latest_preview.get("risk_gate_matrix"), Mapping) else {}
    return (
        bool(latest_preview)
        and str(target.get("official_lane_key") or preview.get("official_lane_key") or "") == official_lane_key
        and latest_preview.get("status") in {TINY_LIVE_RISK_CONTRACT_PREVIEW_READY, TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED}
        and latest_preview.get("risk_preview_overall_status") == TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER
        and matrix.get("risk_contract_preview_ready") is True
        and preview.get("approval_status") == "NOT_APPROVED_PREVIEW_ONLY"
        and preview.get("order_payload_forbidden_now") is True
        and preview.get("binance_call_forbidden_now") is True
    )


def _merge_contract(payload: Any, proposed_contract: Mapping[str, Any], official_lane_key: str) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        merged = _sanitize(dict(payload))
    else:
        merged = {}
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
        "tiny_live_margin_usdt",
        "leverage",
        "max_notional_usdt",
        "max_loss_usdt",
        "risk_reward_ratio",
        "approval_status",
        "live_authorized",
        "live_execution_enabled",
    ]
    return all(existing.get(key) == proposed.get(key) for key in comparable_keys)


def _target_scope(lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "config_write_gate_only": True,
        "live_authorized": False,
    }


def _empty_config_write_preview(config_path: str | Path, official_lane_key: str) -> dict[str, Any]:
    return {
        "config_path": str(config_path),
        "would_write": False,
        "write_requires_confirmation": True,
        "target_contract_key": official_lane_key,
        "new_or_updated": "new",
        "bounded_mutation_only": True,
        "proposed_contract": {},
    }


def _recommended_next_operator_move(matrix: Mapping[str, Any], *, write_requested: bool) -> str:
    if matrix.get("risk_contract_config_written"):
        return "REVIEW_R230_CONFIG_WRITE_RESULT"
    if matrix.get("r229_preview_ready") and matrix.get("config_entry_valid") and not write_requested:
        return "CONFIRM_R230_CONFIG_WRITE"
    return "WAIT"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("risk_contract_config_written"):
        return "Create R231 tiny-live live authorization preview; still no live execution, Binance/network calls, orders, lane arming, or kill switch disable."
    if matrix.get("r229_preview_ready") and matrix.get("config_entry_valid"):
        return "Await exact R230 confirmation phrase before writing only the risk-contract config."
    return "Fix R230 blockers before any config write."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set any lane tiny_live",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key or "").split("|")
    return (
        parts[0] if len(parts) > 0 else "",
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
        parts[3] if len(parts) > 3 else "",
    )


def _number_or(value: Any, default: float) -> float:
    parsed = _number_or_none(value)
    return default if parsed is None else parsed


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
