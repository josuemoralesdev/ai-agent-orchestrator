"""R229 tiny-live risk contract preview.

This module turns the latest R228 10-of-10 ready packet into a deterministic
risk-contract preview for operator review. It is preview-only: it never writes
risk-contract config, changes lane mode, creates order payloads, calls Binance,
or authorizes live execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import (
    CAPTURE_THRESHOLD_MET,
    LEDGER_FILENAME as R228_LEDGER_FILENAME,
    RISK_CONTRACT_CONFIG_PATH,
    TINY_LIVE_10_OF_10_BLOCKED_BY_RISK_CONTRACT,
    TINY_LIVE_10_OF_10_READY_PACKET_READY,
    TINY_LIVE_10_OF_10_READY_PACKET_RECORDED,
    load_tiny_live_10_of_10_ready_packet_records,
)

TINY_LIVE_RISK_CONTRACT_PREVIEW_READY = "TINY_LIVE_RISK_CONTRACT_PREVIEW_READY"
TINY_LIVE_RISK_CONTRACT_PREVIEW_REJECTED = "TINY_LIVE_RISK_CONTRACT_PREVIEW_REJECTED"
TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED = "TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED"
TINY_LIVE_RISK_CONTRACT_PREVIEW_BLOCKED = "TINY_LIVE_RISK_CONTRACT_PREVIEW_BLOCKED"
TINY_LIVE_RISK_CONTRACT_PREVIEW_ERROR = "TINY_LIVE_RISK_CONTRACT_PREVIEW_ERROR"

TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER = (
    "TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER"
)
TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_R228_PACKET = "TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_R228_PACKET"
TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_EVIDENCE_GAP = "TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_EVIDENCE_GAP"
TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_FISHERMAN_STALE = "TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_FISHERMAN_STALE"
TINY_LIVE_RISK_PREVIEW_NOT_APPROVED = "TINY_LIVE_RISK_PREVIEW_NOT_APPROVED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_RISK_CONTRACT_PREVIEW"
LEDGER_FILENAME = "tiny_live_risk_contract_preview.ndjson"
CONFIRM_TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE RISK CONTRACT PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CONTRACT_VERSION = "tiny_live_risk_contract_preview_v1"
DEFAULT_TINY_LIVE_MARGIN_USDT = 44
DEFAULT_LEVERAGE = 1
DEFAULT_MAX_LOSS_USDT = 4.44

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "registry_config_written": False,
    "scoring_config_written": False,
    "matrix_config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "fisherman_config_written": False,
    "scheduler_config_written": False,
    "ledger_rewritten": False,
    "destructive_write": False,
    "historical_ledger_rewritten": False,
    "normalized_rows_appended": False,
    "paper_outcome_ledger_rewritten": False,
    "paper_outcomes_appended": False,
    "strategy_performance_appended": False,
    "strategy_promotion_status_appended": False,
    "ranking_scores_fabricated": False,
    "win_rates_fabricated": False,
    "promotion_eligibility_fabricated": False,
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
    "risk_contract_preview_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/tiny_live_10_of_10_ready_packet.py",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_risk_contract_preview(
    *,
    log_dir: str | Path | None = None,
    record_risk_preview: bool = False,
    confirm_tiny_live_risk_contract_preview: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_risk_contract_preview == CONFIRM_TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDING_PHRASE
    )
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    try:
        latest_r228 = load_latest_r228_packet(log_dir=resolved_log_dir, official_lane_key=official_lane_key)
        existing_context = build_existing_contract_context(
            official_lane_key=official_lane_key,
            risk_contract_config_path=risk_path,
        )
        r228_summary = build_r228_packet_summary(latest_r228, official_lane_key=official_lane_key)
        input_summary = build_input_summary(latest_r228, existing_context)
        risk_preview = build_risk_contract_preview_record(
            official_lane_key=official_lane_key,
            latest_r228=latest_r228,
        )
        risk_gate_matrix = build_risk_gate_matrix(latest_r228, r228_summary)
        operator_packet = build_operator_review_packet(risk_gate_matrix)
        overall = classify_risk_preview_overall_status(latest_r228, r228_summary, risk_gate_matrix)
        status = (
            TINY_LIVE_RISK_CONTRACT_PREVIEW_READY
            if overall == TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER
            else TINY_LIVE_RISK_CONTRACT_PREVIEW_BLOCKED
        )
        if record_risk_preview and not confirmation_valid:
            status = TINY_LIVE_RISK_CONTRACT_PREVIEW_REJECTED
        elif record_risk_preview and confirmation_valid and status == TINY_LIVE_RISK_CONTRACT_PREVIEW_READY:
            status = TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "risk_preview_recorded": False,
            "risk_preview_record_id": None,
            "record_risk_preview_requested": bool(record_risk_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(official_lane_key),
            "input_summary": input_summary,
            "r228_packet_summary": r228_summary,
            "existing_contract_context": existing_context,
            "risk_contract_preview": risk_preview,
            "risk_gate_matrix": risk_gate_matrix,
            "operator_review_packet": operator_packet,
            "recommended_next_operator_move": _recommended_next_operator_move(risk_gate_matrix),
            "recommended_next_engineering_move": _recommended_next_engineering_move(risk_gate_matrix),
            "risk_preview_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if status == TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED:
            record = append_tiny_live_risk_contract_preview_record(payload, log_dir=resolved_log_dir)
            payload["risk_preview_recorded"] = True
            payload["risk_preview_record_id"] = record["risk_preview_record_id"]
            payload["ledger_path"] = str(tiny_live_risk_contract_preview_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": TINY_LIVE_RISK_CONTRACT_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "risk_preview_recorded": False,
                "risk_preview_record_id": None,
                "record_risk_preview_requested": bool(record_risk_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(official_lane_key),
                "input_summary": _empty_input_summary(),
                "r228_packet_summary": _empty_r228_summary(),
                "existing_contract_context": build_existing_contract_context(
                    official_lane_key=official_lane_key,
                    risk_contract_config_path=risk_path,
                ),
                "risk_contract_preview": build_risk_contract_preview_record(
                    official_lane_key=official_lane_key,
                    latest_r228={},
                ),
                "risk_gate_matrix": _empty_gate_matrix(["r228_packet_error"]),
                "operator_review_packet": build_operator_review_packet(_empty_gate_matrix(["r228_packet_error"])),
                "recommended_next_operator_move": "RECHECK_R228_PACKET",
                "recommended_next_engineering_move": "Fix R229 preview error before any config-write phase.",
                "risk_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_r228_packet(
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


def build_input_summary(
    latest_r228: Mapping[str, Any],
    existing_context: Mapping[str, Any],
) -> dict[str, Any]:
    capture = latest_r228.get("capture_threshold_recheck") if isinstance(latest_r228.get("capture_threshold_recheck"), Mapping) else {}
    fisherman = (
        latest_r228.get("fisherman_health_recheck")
        if isinstance(latest_r228.get("fisherman_health_recheck"), Mapping)
        else {}
    )
    gates = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    return {
        "r228_packet_found": bool(latest_r228),
        "r228_evidence_ready": capture.get("evidence_threshold_ready") is True or gates.get("evidence_ready") is True,
        "r228_fisherman_ready": fisherman.get("fisherman_ready") is True or gates.get("fisherman_ready") is True,
        "r228_operator_review_ready": gates.get("operator_review_ready") is True,
        "existing_risk_contract_context_found": existing_context.get("context_found") is True,
        "tiny_live_capture_sync_found": bool(capture),
    }


def build_r228_packet_summary(
    latest_r228: Mapping[str, Any],
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    capture = latest_r228.get("capture_threshold_recheck") if isinstance(latest_r228.get("capture_threshold_recheck"), Mapping) else {}
    gates = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    blocked_by = list(gates.get("blocked_by") or [])
    return {
        "fresh_capture_count": int(capture.get("fresh_capture_count") or 0),
        "required_fresh_capture_count": int(capture.get("required_fresh_capture_count") or 10),
        "threshold_met": capture.get("threshold_met") is True,
        "threshold_status": capture.get("threshold_status"),
        "official_lane_unchanged": str(capture.get("official_lane_key") or "") == official_lane_key
        and capture.get("official_lane_unchanged") is True,
        "ready_packet_overall_status": latest_r228.get("ready_packet_overall_status"),
        "blocked_by": blocked_by,
    }


def build_existing_contract_context(
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    risk_contract_config_path: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    context = {
        "context_found": False,
        "config_path_checked": str(path),
        "matching_contract_found": False,
        "matching_contract_summary": None,
        "config_mutated": False,
    }
    if not path.exists():
        return context
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**context, "context_found": True, "config_read_error": True}
    contracts = payload.get("risk_contracts") if isinstance(payload, Mapping) else []
    context["context_found"] = True
    for contract in contracts if isinstance(contracts, list) else []:
        if not isinstance(contract, Mapping):
            continue
        if (
            str(contract.get("symbol") or "") == symbol
            and str(contract.get("timeframe") or "") == timeframe
            and str(contract.get("direction") or "") == direction
            and str(contract.get("entry_mode") or "") == entry_mode
        ):
            context["matching_contract_found"] = True
            context["matching_contract_summary"] = {
                "candidate_id": contract.get("candidate_id"),
                "symbol": contract.get("symbol"),
                "timeframe": contract.get("timeframe"),
                "direction": contract.get("direction"),
                "entry_mode": contract.get("entry_mode"),
                "enabled_for_preflight": contract.get("enabled_for_preflight") is True,
                "approval_status": contract.get("approval_status"),
                "approved": contract.get("approved") is True,
                "max_margin_usdt": _number_or_none(contract.get("max_margin_usdt")),
                "max_position_notional_usdt": _number_or_none(contract.get("max_position_notional_usdt")),
                "leverage": _number_or_none(contract.get("leverage")),
                "max_loss_usdt": _number_or_none(contract.get("max_loss_usdt")),
                "protective_stop_required": contract.get("protective_stop_required") is True,
                "take_profit_required": contract.get("take_profit_required") is True,
            }
            break
    return context


def build_risk_contract_preview_record(
    *,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    latest_r228: Mapping[str, Any],
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    evidence_ref = (
        latest_r228.get("packet_record_id")
        or latest_r228.get("generated_at")
        or f"logs/hammer_radar_forward/{R228_LEDGER_FILENAME}"
    )
    margin = DEFAULT_TINY_LIVE_MARGIN_USDT
    leverage = DEFAULT_LEVERAGE
    max_notional = margin * leverage
    max_loss = min(DEFAULT_MAX_LOSS_USDT, margin)
    return {
        "contract_id": f"r229_preview_{symbol}_{timeframe}_{direction}_{entry_mode}",
        "contract_version": CONTRACT_VERSION,
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "evidence_packet_reference": evidence_ref,
        "capital_mode": "tiny_live_preview",
        "max_account_risk_usdt_preview": margin,
        "max_notional_usdt_preview": max_notional,
        "leverage_preview": leverage,
        "max_loss_usdt_preview": max_loss,
        "proposed_tiny_live_margin_usdt": margin,
        "proposed_leverage": leverage,
        "proposed_max_notional_usdt": max_notional,
        "proposed_max_loss_usdt": max_loss,
        "stop_required": True,
        "take_profit_required": True,
        "stop_take_profit_relationship": "stop and take profit both required before any later live authorization; preview uses risk_reward_ratio_preview=2.0",
        "risk_reward_ratio_preview": 2.0,
        "kill_switch_required": True,
        "operator_final_approval_required": True,
        "config_write_required_later": True,
        "live_authorization_required_later": True,
        "order_payload_forbidden_now": True,
        "binance_call_forbidden_now": True,
        "preview_only": True,
        "approval_status": "NOT_APPROVED_PREVIEW_ONLY",
        "notes": [
            "Preview-only conservative defaults; not approved and not written to config.",
            "Max loss is preview-only and must be reviewed before any future config-write phase.",
            "Stop, take-profit, kill switch, final operator approval, and later config write are required.",
        ],
    }


def build_risk_gate_matrix(
    latest_r228: Mapping[str, Any],
    r228_summary: Mapping[str, Any],
) -> dict[str, Any]:
    gates = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    evidence_ready = gates.get("evidence_ready") is True
    fisherman_ready = gates.get("fisherman_ready") is True
    operator_review_ready = gates.get("operator_review_ready") is True
    r228_status_ok = str(latest_r228.get("status") or "") in {
        TINY_LIVE_10_OF_10_READY_PACKET_READY,
        TINY_LIVE_10_OF_10_READY_PACKET_RECORDED,
    }
    blocked_by: list[str] = []
    if not latest_r228:
        blocked_by.append("r228_packet_missing")
    if latest_r228 and not r228_status_ok:
        blocked_by.append("r228_packet_not_ready")
    if not r228_summary.get("official_lane_unchanged"):
        blocked_by.append("official_lane_mismatch")
    if not evidence_ready:
        blocked_by.append("evidence_threshold_not_ready")
    if not fisherman_ready:
        blocked_by.append("fisherman_not_ready")
    if not operator_review_ready:
        blocked_by.append("operator_review_not_ready")
    if gates.get("risk_contract_ready") is not False:
        blocked_by.append("r228_risk_contract_state_not_false")
    if gates.get("live_authorization_ready") is not False:
        blocked_by.append("live_authorization_state_not_false")
    if gates.get("order_ready") is not False:
        blocked_by.append("order_state_not_false")
    risk_preview_ready = not blocked_by
    if risk_preview_ready:
        blocked_by.extend(["risk_contract_config_write_required_later", "live_authorization_absent", "order_payload_forbidden"])
    return {
        "evidence_ready": evidence_ready,
        "fisherman_ready": fisherman_ready,
        "operator_review_ready": operator_review_ready,
        "risk_contract_preview_ready": risk_preview_ready,
        "risk_contract_config_written": False,
        "risk_contract_approved": False,
        "live_authorization_ready": False,
        "live_execution_ready": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": blocked_by,
    }


def build_operator_review_packet(risk_gate_matrix: Mapping[str, Any]) -> dict[str, Any]:
    preview_ready = risk_gate_matrix.get("risk_contract_preview_ready") is True
    if preview_ready:
        action = "REVIEW_R229_RISK_PREVIEW"
    elif not risk_gate_matrix.get("evidence_ready") or not risk_gate_matrix.get("fisherman_ready"):
        action = "RECHECK_R228_PACKET"
    else:
        action = "WAIT"
    return {
        "operator_should_review_risk_preview": preview_ready,
        "operator_should_write_config": False,
        "operator_should_enable_live": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not enable live",
            "do not disable kill switch",
            "do not write risk config from this preview",
        ],
    }


def classify_risk_preview_overall_status(
    latest_r228: Mapping[str, Any],
    r228_summary: Mapping[str, Any],
    risk_gate_matrix: Mapping[str, Any],
) -> str:
    if not latest_r228:
        return TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_R228_PACKET
    if not r228_summary.get("official_lane_unchanged"):
        return TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_R228_PACKET
    if not risk_gate_matrix.get("evidence_ready"):
        return TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_EVIDENCE_GAP
    if not risk_gate_matrix.get("fisherman_ready"):
        return TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_FISHERMAN_STALE
    if "r228_packet_not_ready" in risk_gate_matrix.get("blocked_by", []):
        return TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_R228_PACKET
    if risk_gate_matrix.get("risk_contract_preview_ready"):
        return TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER
    return TINY_LIVE_RISK_PREVIEW_NOT_APPROVED


def append_tiny_live_risk_contract_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_risk_contract_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "risk_preview_record_id": record.get("risk_preview_record_id") or f"r229_risk_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "r228_packet_summary": dict(record.get("r228_packet_summary") or {}),
            "existing_contract_context": dict(record.get("existing_contract_context") or {}),
            "risk_contract_preview": dict(record.get("risk_contract_preview") or {}),
            "risk_gate_matrix": dict(record.get("risk_gate_matrix") or {}),
            "operator_review_packet": dict(record.get("operator_review_packet") or {}),
            "risk_preview_overall_status": record.get("risk_preview_overall_status"),
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


def load_tiny_live_risk_contract_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_risk_contract_preview_records_path(get_log_dir(log_dir, use_env=True))
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


def tiny_live_risk_contract_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_risk_contract_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _recommended_next_operator_move(risk_gate_matrix: Mapping[str, Any]) -> str:
    if risk_gate_matrix.get("risk_contract_preview_ready"):
        return "REVIEW_R229_RISK_PREVIEW"
    if not risk_gate_matrix.get("evidence_ready") or not risk_gate_matrix.get("fisherman_ready"):
        return "RECHECK_R228_PACKET"
    return "WAIT"


def _recommended_next_engineering_move(risk_gate_matrix: Mapping[str, Any]) -> str:
    if risk_gate_matrix.get("risk_contract_preview_ready"):
        return "Create R230 guarded tiny-live risk contract config-write gate; still no live execution or Binance/network calls."
    if not risk_gate_matrix.get("evidence_ready"):
        return "Rerun R228 after restoring official 10-of-10 capture evidence."
    if not risk_gate_matrix.get("fisherman_ready"):
        return "Restore fisherman freshness and rerun R228 before R229 preview."
    return "Review R228/R229 blockers before any config-write phase."


def _target_scope(lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "paper_only": True,
        "risk_contract_preview_only": True,
        "live_authorized": False,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r228_packet_found": False,
        "r228_evidence_ready": False,
        "r228_fisherman_ready": False,
        "r228_operator_review_ready": False,
        "existing_risk_contract_context_found": False,
        "tiny_live_capture_sync_found": False,
    }


def _empty_r228_summary() -> dict[str, Any]:
    return {
        "fresh_capture_count": 0,
        "required_fresh_capture_count": 10,
        "threshold_met": False,
        "threshold_status": None,
        "official_lane_unchanged": True,
        "ready_packet_overall_status": None,
        "blocked_by": [],
    }


def _empty_gate_matrix(blockers: list[str] | None = None) -> dict[str, Any]:
    return {
        "evidence_ready": False,
        "fisherman_ready": False,
        "operator_review_ready": False,
        "risk_contract_preview_ready": False,
        "risk_contract_config_written": False,
        "risk_contract_approved": False,
        "live_authorization_ready": False,
        "live_execution_ready": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": list(blockers or []),
    }


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set any lane tiny_live",
        "write risk contract config",
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


def _number_or_none(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
