"""R232 tiny-live live authorization write gate.

This module can append a bounded local authorization ledger record only when
the exact R232 confirmation phrase is supplied. It never enables live
execution, arms lanes, creates order payloads, calls Binance/network, or
mutates env/config/lane state.
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
from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import RISK_CONTRACT_CONFIG_PATH
from src.app.hammer_radar.operator.tiny_live_live_authorization_preview import (
    LEDGER_FILENAME as R231_LEDGER_FILENAME,
    LANE_CONTROLS_PATH,
    TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY,
    TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY_FOR_FUTURE_GATE,
    TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDED,
    build_lane_control_state,
    load_tiny_live_live_authorization_preview_records,
    validate_live_authorization_prerequisites,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_config_write_gate import (
    LEDGER_FILENAME as R230_LEDGER_FILENAME,
    load_tiny_live_risk_contract_config_write_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_preview import LEDGER_FILENAME as R229_LEDGER_FILENAME
from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import (
    LEDGER_FILENAME as R228_LEDGER_FILENAME,
    load_tiny_live_10_of_10_ready_packet_records,
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_preview import (
    load_tiny_live_risk_contract_config as _load_r231_risk_contract_config,
)

TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_READY = "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_READY"
TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_REJECTED = "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_REJECTED"
TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_WRITTEN = "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_WRITTEN"
TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_BLOCKED = "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_BLOCKED"
TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_ERROR = "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_ERROR"

TINY_LIVE_AUTHORIZATION_WRITE_READY_FOR_CONFIRMATION = "TINY_LIVE_AUTHORIZATION_WRITE_READY_FOR_CONFIRMATION"
TINY_LIVE_AUTHORIZATION_WRITTEN_LIVE_EXECUTION_REQUIRED_LATER = (
    "TINY_LIVE_AUTHORIZATION_WRITTEN_LIVE_EXECUTION_REQUIRED_LATER"
)
TINY_LIVE_AUTHORIZATION_WRITE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_AUTHORIZATION_WRITE_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_AUTHORIZATION_WRITE_BLOCKED_BY_R231_PREVIEW = "TINY_LIVE_AUTHORIZATION_WRITE_BLOCKED_BY_R231_PREVIEW"
TINY_LIVE_AUTHORIZATION_WRITE_BLOCKED_BY_RISK_CONTRACT = "TINY_LIVE_AUTHORIZATION_WRITE_BLOCKED_BY_RISK_CONTRACT"
TINY_LIVE_AUTHORIZATION_WRITE_BLOCKED_BY_VALIDATION = "TINY_LIVE_AUTHORIZATION_WRITE_BLOCKED_BY_VALIDATION"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE"
LEDGER_FILENAME = "tiny_live_live_authorization_write_gate.ndjson"
CONFIRM_TINY_LIVE_LIVE_AUTHORIZATION_WRITE_PHRASE = (
    "I CONFIRM TINY LIVE AUTHORIZATION WRITE ONLY; NO LIVE ENABLE; NO ORDER; NO BINANCE CALL."
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
AUTHORIZATION_VERSION = "tiny_live_authorization_v1"
CREATED_BY_PHASE = "R232_TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE"

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
    "lane_armed": False,
    "signal_origin_promoted": False,
    "lane_promoted": False,
    "official_tiny_live_lane_changed": False,
    "alternate_lane_promoted": False,
    "betrayal_live_authorized": False,
    "betrayal_promoted": False,
    "authorization_write_gate_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{R231_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R230_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R229_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_live_authorization_write_gate(
    *,
    log_dir: str | Path | None = None,
    write_live_authorization: bool = False,
    confirm_tiny_live_live_authorization_write: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    confirmation_valid = confirm_tiny_live_live_authorization_write == CONFIRM_TINY_LIVE_LIVE_AUTHORIZATION_WRITE_PHRASE
    try:
        latest_r231 = load_latest_tiny_live_live_authorization_preview(
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
        lane_state = build_lane_control_state(lane_path, official_lane_key=official_lane_key)
        prerequisites = validate_live_authorization_prerequisites(
            latest_r228=latest_r228,
            latest_r229={},
            latest_r230=latest_r230,
            risk_contract_config=risk_config,
            lane_control_state=lane_state,
            official_lane_key=official_lane_key,
        )
        input_summary = _build_input_summary(
            latest_r231=latest_r231,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            prerequisites=prerequisites,
        )
        proposed = build_live_authorization_object(
            latest_r231=latest_r231,
            latest_r230=latest_r230,
            latest_r228=latest_r228,
            risk_contract_config=risk_config,
            input_summary=input_summary,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        validation = validate_live_authorization_object(proposed)
        r231_ready = _r231_preview_ready(latest_r231, official_lane_key=official_lane_key)
        risk_ready = input_summary["risk_contract_valid"] and input_summary["risk_contract_config_ready"]
        blocked_by = _blocked_by(
            r231_ready=r231_ready,
            risk_ready=risk_ready,
            validation=validation,
            prerequisites=prerequisites,
        )
        preview_prerequisites = (
            prerequisites
            if write_live_authorization
            else {**prerequisites, "blocked_by": [*(prerequisites.get("blocked_by") or []), "write_confirmation_required"]}
        )
        preview = build_live_authorization_write_preview(
            proposed_authorization=proposed,
            authorization_valid=validation["valid"],
            prerequisites=preview_prerequisites,
            latest_r231=latest_r231,
            official_lane_key=official_lane_key,
        )
        can_write = write_live_authorization and confirmation_valid and not blocked_by

        if write_live_authorization and not confirmation_valid:
            written = False
            status = TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_REJECTED
            overall = TINY_LIVE_AUTHORIZATION_WRITE_REJECTED_BAD_CONFIRMATION
        elif can_write:
            write_live_authorization_if_confirmed(
                authorization=proposed,
                confirm_tiny_live_live_authorization_write=confirm_tiny_live_live_authorization_write,
                log_dir=resolved_log_dir,
            )
            written = True
            status = TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_WRITTEN
            overall = TINY_LIVE_AUTHORIZATION_WRITTEN_LIVE_EXECUTION_REQUIRED_LATER
        elif not r231_ready:
            written = False
            status = TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_BLOCKED
            overall = TINY_LIVE_AUTHORIZATION_WRITE_BLOCKED_BY_R231_PREVIEW
        elif not risk_ready:
            written = False
            status = TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_BLOCKED
            overall = TINY_LIVE_AUTHORIZATION_WRITE_BLOCKED_BY_RISK_CONTRACT
        elif not validation["valid"]:
            written = False
            status = TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_BLOCKED
            overall = TINY_LIVE_AUTHORIZATION_WRITE_BLOCKED_BY_VALIDATION
        else:
            written = False
            status = TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_READY
            overall = TINY_LIVE_AUTHORIZATION_WRITE_READY_FOR_CONFIRMATION

        post_write = build_post_write_authorization_verification(
            authorization=proposed,
            authorization_written=written,
            log_dir=resolved_log_dir,
        )
        matrix = build_live_authorization_write_gate_matrix(
            r231_preview_ready=r231_ready,
            risk_contract_config_ready=risk_ready,
            authorization_valid=validation["valid"],
            authorization_write_confirmed=write_live_authorization and confirmation_valid,
            live_authorization_written=written,
            live_authorized=proposed.get("live_authorized") is True and written,
            blocked_by=blocked_by,
        )
        operator_packet = build_operator_authorization_write_review_packet(matrix, write_requested=write_live_authorization)
        safety = dict(SAFETY)
        if written:
            safety["live_authorization_written"] = True
            safety["live_authorization_created"] = True
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "authorization_written": written,
            "record_gate_requested": bool(write_live_authorization),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(official_lane_key),
            "input_summary": input_summary,
            "authorization_write_preview": preview,
            "authorization_validation": validation,
            "post_write_verification": post_write,
            "live_authorization_write_gate_matrix": matrix,
            "operator_authorization_write_review_packet": operator_packet,
            "recommended_next_operator_move": _recommended_next_operator_move(matrix, write_requested=write_live_authorization),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
            "authorization_write_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_live_authorization_write_gate_matrix(
            r231_preview_ready=False,
            risk_contract_config_ready=False,
            authorization_valid=False,
            authorization_write_confirmed=False,
            live_authorization_written=False,
            live_authorized=False,
            blocked_by=["authorization_write_gate_error"],
        )
        return _sanitize(
            {
                "status": TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "authorization_written": False,
                "record_gate_requested": bool(write_live_authorization),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(official_lane_key),
                "input_summary": _empty_input_summary(),
                "authorization_write_preview": _empty_authorization_write_preview(official_lane_key),
                "authorization_validation": {"valid": False, "errors": ["authorization_write_gate_error"], "warnings": []},
                "post_write_verification": _empty_post_write_verification(),
                "live_authorization_write_gate_matrix": matrix,
                "operator_authorization_write_review_packet": build_operator_authorization_write_review_packet(
                    matrix,
                    write_requested=write_live_authorization,
                ),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R232 authorization write-gate error before any later live execution preview.",
                "authorization_write_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_live_authorization_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_live_authorization_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        matrix = record.get("live_authorization_gate_matrix") if isinstance(record.get("live_authorization_gate_matrix"), Mapping) else {}
        if str(target.get("official_lane_key") or "") == official_lane_key and matrix.get("live_authorization_preview_ready") is True:
            return _sanitize({**record, "r231_preview_found": True})
    return {}


def load_latest_tiny_live_risk_contract_config_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_risk_contract_config_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        post_write = record.get("post_write_verification") if isinstance(record.get("post_write_verification"), Mapping) else {}
        if str(target.get("official_lane_key") or "") == official_lane_key or post_write.get("matching_contract_found") is True:
            return _sanitize({**record, "r230_config_gate_found": True})
    return {}


def load_latest_tiny_live_10_of_10_ready_packet(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_10_of_10_ready_packet_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if str(target.get("official_lane_key") or "") == official_lane_key:
            return _sanitize({**record, "r228_packet_found": True})
    return {}


def load_tiny_live_risk_contract_config(
    config_path: str | Path | None = None,
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return _load_r231_risk_contract_config(config_path, official_lane_key=official_lane_key)


def build_live_authorization_object(
    *,
    latest_r231: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    risk_contract_config: Mapping[str, Any],
    input_summary: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    contract = risk_contract_config.get("matching_risk_contract") if isinstance(risk_contract_config.get("matching_risk_contract"), Mapping) else {}
    requirement_preview = (
        latest_r231.get("live_authorization_requirement_preview")
        if isinstance(latest_r231.get("live_authorization_requirement_preview"), Mapping)
        else {}
    )
    return {
        "authorization_id": "r232_authorization_BTCUSDT_8m_short_ladder_close_50_618",
        "authorization_version": AUTHORIZATION_VERSION,
        "created_by_phase": CREATED_BY_PHASE,
        "created_at": generated_at.isoformat(),
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "source_live_authorization_preview_id": latest_r231.get("authorization_preview_record_id")
        or requirement_preview.get("authorization_preview_id"),
        "source_risk_contract_id": contract.get("contract_id") or latest_r230.get("gate_record_id"),
        "risk_contract_config_ready": input_summary.get("risk_contract_config_ready") is True,
        "evidence_ready": input_summary.get("r228_evidence_ready") is True,
        "fisherman_ready": input_summary.get("fisherman_ready") is True,
        "authorization_scope": "tiny_live_single_lane",
        "authorization_status": "AUTHORIZED_NOT_ARMED_NOT_EXECUTABLE",
        "live_authorized": True,
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_payload_allowed": False,
        "binance_call_allowed": False,
        "kill_switch_required": True,
        "operator_final_approval_required": True,
        "live_execution_enable_required_later": True,
        "lane_arm_required_later": True,
        "order_preflight_required_later": True,
        "notes": [
            "R232 writes authorization only; it does not enable live execution.",
            "Lane arming, live execution enablement, order payload creation, and Binance/network calls remain forbidden.",
            "A later phase must separately gate live execution enablement and lane arming.",
        ],
    }


def validate_live_authorization_object(authorization: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    expected = {
        "official_lane_key": OFFICIAL_LANE_KEY,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "risk_contract_config_ready": True,
        "evidence_ready": True,
        "fisherman_ready": True,
        "live_authorized": True,
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_payload_allowed": False,
        "binance_call_allowed": False,
        "kill_switch_required": True,
        "operator_final_approval_required": True,
        "live_execution_enable_required_later": True,
        "lane_arm_required_later": True,
        "order_preflight_required_later": True,
    }
    for key, value in expected.items():
        if authorization.get(key) is not value and authorization.get(key) != value:
            errors.append(f"{key}_invalid")
    if authorization.get("authorization_status") != "AUTHORIZED_NOT_ARMED_NOT_EXECUTABLE":
        errors.append("authorization_status_invalid")
    if not authorization.get("source_live_authorization_preview_id"):
        errors.append("source_live_authorization_preview_id_missing")
    if authorization.get("source_risk_contract_id") != "r230_contract_BTCUSDT_8m_short_ladder_close_50_618":
        errors.append("source_risk_contract_id_invalid")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def build_live_authorization_write_preview(
    *,
    proposed_authorization: Mapping[str, Any],
    authorization_valid: bool,
    prerequisites: Mapping[str, Any],
    latest_r231: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    r232_blockers = [blocker for blocker in prerequisites.get("blocked_by") or [] if blocker != "r229_preview_missing"]
    return {
        "would_write": bool(
            authorization_valid
            and _r231_preview_ready(latest_r231, official_lane_key=official_lane_key)
            and not r232_blockers
        ),
        "write_requires_confirmation": True,
        "target_authorization_key": official_lane_key,
        "bounded_mutation_only": True,
        "authorization_artifact": "ledger_only",
        "proposed_authorization": _sanitize(dict(proposed_authorization)),
    }


def write_live_authorization_if_confirmed(
    *,
    authorization: Mapping[str, Any],
    confirm_tiny_live_live_authorization_write: str | None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_live_authorization_write != CONFIRM_TINY_LIVE_LIVE_AUTHORIZATION_WRITE_PHRASE:
        return {"written": False, "reason": "bad_confirmation"}
    validation = validate_live_authorization_object(authorization)
    if not validation["valid"]:
        return {"written": False, "reason": "validation_failed", "validation": validation}
    record = append_tiny_live_live_authorization_write_gate_record(
        {
            "status": TINY_LIVE_LIVE_AUTHORIZATION_WRITE_GATE_WRITTEN,
            "generated_at": authorization.get("created_at"),
            "authorization_written": True,
            "record_gate_requested": True,
            "confirmation_valid": True,
            "target_scope": _target_scope(str(authorization.get("official_lane_key") or OFFICIAL_LANE_KEY)),
            "authorization": dict(authorization),
            "authorization_validation": validation,
            "safety": {**SAFETY, "live_authorization_written": True, "live_authorization_created": True},
        },
        log_dir=log_dir,
    )
    return {"written": True, "record": record}


def build_post_write_authorization_verification(
    *,
    authorization: Mapping[str, Any],
    authorization_written: bool,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_tiny_live_live_authorization_write_gate_records(log_dir=log_dir, limit=50) if authorization_written else []
    matching = _matching_authorization_record(records, authorization)
    auth = matching.get("authorization") if isinstance(matching.get("authorization"), Mapping) else {}
    validation = validate_live_authorization_object(auth)
    return {
        "authorization_written": bool(authorization_written),
        "matching_authorization_found": bool(matching),
        "matching_authorization_valid": bool(matching and validation["valid"]),
        "live_authorized": bool(matching and auth.get("live_authorized") is True),
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_payload_created": False,
        "binance_call_allowed": False,
    }


def build_live_authorization_write_gate_matrix(
    *,
    r231_preview_ready: bool,
    risk_contract_config_ready: bool,
    authorization_valid: bool,
    authorization_write_confirmed: bool,
    live_authorization_written: bool,
    live_authorized: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if not r231_preview_ready and "r231_preview_not_ready" not in blockers:
        blockers.append("r231_preview_not_ready")
    if not risk_contract_config_ready and "risk_contract_config_not_ready" not in blockers:
        blockers.append("risk_contract_config_not_ready")
    if not authorization_valid and "authorization_invalid" not in blockers:
        blockers.append("authorization_invalid")
    if not authorization_write_confirmed:
        blockers.append("exact_authorization_write_confirmation_required")
    if live_authorization_written:
        blockers = ["live_execution_disabled", "lane_not_armed", "order_payload_forbidden"]
    return {
        "r231_preview_ready": bool(r231_preview_ready),
        "risk_contract_config_ready": bool(risk_contract_config_ready),
        "authorization_valid": bool(authorization_valid),
        "authorization_write_confirmed": bool(authorization_write_confirmed),
        "live_authorization_written": bool(live_authorization_written),
        "live_authorized": bool(live_authorized),
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_authorization_write_review_packet(
    live_authorization_write_gate_matrix: Mapping[str, Any],
    *,
    write_requested: bool = False,
) -> dict[str, Any]:
    written = live_authorization_write_gate_matrix.get("live_authorization_written") is True
    ready = (
        live_authorization_write_gate_matrix.get("r231_preview_ready") is True
        and live_authorization_write_gate_matrix.get("risk_contract_config_ready") is True
        and live_authorization_write_gate_matrix.get("authorization_valid") is True
        and not written
    )
    if written:
        action = "REVIEW_R232_RESULT"
    elif ready:
        action = "CONFIRM_R232_AUTHORIZATION_WRITE"
    else:
        action = "WAIT"
    return {
        "operator_should_review_authorization_write": bool(ready or written or write_requested),
        "operator_confirmation_required": True,
        "operator_should_enable_live": False,
        "operator_should_arm_lane": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not enable live execution",
            "do not disable kill switch",
            "do not arm lane from this phase",
        ],
    }


def classify_tiny_live_live_authorization_write_status(payload: Mapping[str, Any]) -> str:
    return str(payload.get("authorization_write_overall_status") or UNKNOWN_NEEDS_MANUAL_REVIEW)


def append_tiny_live_live_authorization_write_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_live_authorization_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "gate_record_id": record.get("gate_record_id") or f"r232_authorization_write_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "authorization_written": record.get("authorization_written") is True,
            "record_gate_requested": record.get("record_gate_requested") is True,
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "authorization": dict(record.get("authorization") or {}),
            "authorization_validation": dict(record.get("authorization_validation") or {}),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_live_authorization_write_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_live_authorization_write_gate_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_tiny_live_live_authorization_write_gate_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_authorization_written": latest.get("authorization_written") is True,
        "latest_authorization_id": (latest.get("authorization") or {}).get("authorization_id")
        if isinstance(latest.get("authorization"), Mapping)
        else None,
    }


def tiny_live_live_authorization_write_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_live_authorization_write_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r231: Mapping[str, Any],
    latest_r230: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
    prerequisites: Mapping[str, Any],
) -> dict[str, Any]:
    base = prerequisites.get("input_summary") if isinstance(prerequisites.get("input_summary"), Mapping) else {}
    return {
        "r231_preview_found": bool(latest_r231),
        "r231_preview_ready": _r231_preview_ready(latest_r231),
        "r230_risk_contract_config_found": bool(latest_r230),
        "risk_contract_valid": base.get("matching_risk_contract_valid") is True,
        "r228_evidence_ready": base.get("r228_evidence_ready") is True,
        "fisherman_ready": base.get("r228_fisherman_ready") is True,
        "risk_contract_config_ready": bool(latest_r230)
        and base.get("risk_contract_config_found") is True
        and base.get("matching_risk_contract_valid") is True,
        "r228_packet_found": bool(latest_r228),
    }


def _r231_preview_ready(
    latest_r231: Mapping[str, Any],
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> bool:
    target = latest_r231.get("target_scope") if isinstance(latest_r231.get("target_scope"), Mapping) else {}
    matrix = latest_r231.get("live_authorization_gate_matrix") if isinstance(latest_r231.get("live_authorization_gate_matrix"), Mapping) else {}
    return (
        bool(latest_r231)
        and str(target.get("official_lane_key") or "") == official_lane_key
        and latest_r231.get("status") in {
            TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY,
            TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_RECORDED,
        }
        and latest_r231.get("live_authorization_preview_overall_status")
        == TINY_LIVE_LIVE_AUTHORIZATION_PREVIEW_READY_FOR_FUTURE_GATE
        and matrix.get("live_authorization_preview_ready") is True
        and matrix.get("live_authorization_written") is False
        and matrix.get("live_execution_ready") is False
        and matrix.get("lane_armed") is False
    )


def _blocked_by(
    *,
    r231_ready: bool,
    risk_ready: bool,
    validation: Mapping[str, Any],
    prerequisites: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not r231_ready:
        blockers.append("r231_preview_not_ready")
    if not risk_ready:
        blockers.append("risk_contract_config_not_ready")
    if validation.get("valid") is not True:
        blockers.extend(str(error) for error in validation.get("errors") or ["authorization_invalid"])
    for blocker in prerequisites.get("blocked_by") or []:
        if blocker != "r229_preview_missing":
            blockers.append(str(blocker))
    return _dedupe(blockers)


def _matching_authorization_record(
    records: Sequence[Mapping[str, Any]],
    authorization: Mapping[str, Any],
) -> dict[str, Any]:
    expected_id = authorization.get("authorization_id")
    for record in records:
        auth = record.get("authorization") if isinstance(record.get("authorization"), Mapping) else {}
        if auth.get("authorization_id") == expected_id and record.get("authorization_written") is True:
            return _sanitize(dict(record))
    return {}


def _target_scope(lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "authorization_write_gate_only": True,
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_payload_allowed": False,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r231_preview_found": False,
        "r231_preview_ready": False,
        "r230_risk_contract_config_found": False,
        "risk_contract_valid": False,
        "r228_evidence_ready": False,
        "fisherman_ready": False,
        "risk_contract_config_ready": False,
        "r228_packet_found": False,
    }


def _empty_authorization_write_preview(official_lane_key: str) -> dict[str, Any]:
    return {
        "would_write": False,
        "write_requires_confirmation": True,
        "target_authorization_key": official_lane_key,
        "bounded_mutation_only": True,
        "authorization_artifact": "ledger_only",
        "proposed_authorization": {},
    }


def _empty_post_write_verification() -> dict[str, Any]:
    return {
        "authorization_written": False,
        "matching_authorization_found": False,
        "matching_authorization_valid": False,
        "live_authorized": False,
        "live_execution_enabled": False,
        "lane_armed": False,
        "order_payload_created": False,
        "binance_call_allowed": False,
    }


def _recommended_next_operator_move(matrix: Mapping[str, Any], *, write_requested: bool) -> str:
    if matrix.get("live_authorization_written"):
        return "REVIEW_R232_AUTHORIZATION_WRITE_RESULT"
    if matrix.get("r231_preview_ready") and matrix.get("risk_contract_config_ready") and matrix.get("authorization_valid") and not write_requested:
        return "CONFIRM_R232_AUTHORIZATION_WRITE"
    return "WAIT"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("live_authorization_written"):
        return "Create R233 tiny-live live execution enable preview; still no live execution, Binance/network calls, orders, or lane arming."
    if matrix.get("r231_preview_ready") and matrix.get("risk_contract_config_ready") and matrix.get("authorization_valid"):
        return "Await exact R232 confirmation phrase before writing only the authorization ledger artifact."
    return "Fix R232 blockers before any authorization write."


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


def _dedupe(items: Sequence[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
