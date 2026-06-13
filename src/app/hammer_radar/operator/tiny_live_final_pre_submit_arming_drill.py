"""R257 tiny-live final pre-submit arming drill.

This module is a final manual-decision drill only. It never signs, submits,
calls Binance/network, regenerates signed requests, or mutates live controls.
The only allowed mutation is its own audit ledger append after the exact R257
confirmation phrase.
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
from src.app.hammer_radar.operator.tiny_live_actual_submit_gate import (
    REAL_SUBMIT_CONFIRMATION_PHRASE,
    validate_kill_switch_and_lane_controls_for_tiny_live_submit,
)
from src.app.hammer_radar.operator.tiny_live_operator_real_submit_runbook import (
    build_real_submit_command_template,
    load_latest_tiny_live_actual_submit_gate as _load_latest_r255_from_r256,
    load_latest_tiny_live_fresh_context_signed_request_regeneration_gate as _load_latest_r253b_from_r256,
    load_latest_tiny_live_submit_gate_preview as _load_latest_r254_from_r256,
    load_tiny_live_operator_real_submit_runbook_records,
    summarize_current_submit_blockers_for_operator,
)

TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_READY = (
    "TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_READY"
)
TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_RECORDED = (
    "TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_RECORDED"
)
TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_REJECTED = (
    "TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_REJECTED"
)
TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_BLOCKED = (
    "TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_BLOCKED"
)
TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_ERROR = (
    "TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_ERROR"
)

TINY_LIVE_FINAL_ARMING_DRILL_READY_FOR_RECORDING = (
    "TINY_LIVE_FINAL_ARMING_DRILL_READY_FOR_RECORDING"
)
TINY_LIVE_FINAL_ARMING_DRILL_RECORDED_MANUAL_DECISION_REQUIRED = (
    "TINY_LIVE_FINAL_ARMING_DRILL_RECORDED_MANUAL_DECISION_REQUIRED"
)
TINY_LIVE_FINAL_ARMING_DRILL_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_FINAL_ARMING_DRILL_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_FINAL_ARMING_DRILL_BLOCKED_BY_MISSING_R256 = (
    "TINY_LIVE_FINAL_ARMING_DRILL_BLOCKED_BY_MISSING_R256"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL"
LEDGER_FILENAME = "tiny_live_final_pre_submit_arming_drill.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R257_TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL"
CONFIRM_TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_PHRASE = (
    "I CONFIRM TINY LIVE FINAL PRE-SUBMIT ARMING DRILL RECORDING ONLY; "
    "NO SUBMIT; NO ORDER; NO BINANCE CALL."
)

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_operator_real_submit_runbook.ndjson",
    "logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson",
    "logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "external_env_file_written": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "final_pre_submit_arming_drill_only": True,
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


def build_tiny_live_final_pre_submit_arming_drill(
    *,
    log_dir: str | Path | None = None,
    record_final_pre_submit_arming_drill: bool = False,
    confirm_tiny_live_final_pre_submit_arming_drill: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_final_pre_submit_arming_drill
        == CONFIRM_TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_PHRASE
    )
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)

    try:
        latest_r256 = load_latest_tiny_live_operator_real_submit_runbook(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r255 = load_latest_tiny_live_actual_submit_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r254 = load_latest_tiny_live_submit_gate_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r253b = load_latest_tiny_live_fresh_context_signed_request_regeneration_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )

        input_summary = {
            "r256_operator_runbook_found": bool(latest_r256),
            "r256_operator_runbook_valid": _r256_valid(latest_r256),
            "r255_actual_submit_gate_found": bool(latest_r255),
            "r254_submit_gate_preview_found": bool(latest_r254),
            "r253b_fresh_regeneration_found": bool(latest_r253b),
        }
        blocker_summary = summarize_pre_submit_blockers(
            latest_r256=latest_r256,
            latest_r255=latest_r255,
        )
        regeneration = summarize_signed_request_regeneration_requirement(
            latest_r255=latest_r255,
            pre_submit_blocker_summary=blocker_summary,
        )
        live_controls = summarize_live_control_intent_state(
            latest_r255=latest_r255,
            official_lane_key=official_lane_key,
        )
        command_readiness = summarize_exact_submit_command_readiness(latest_r256)
        reconciliation = summarize_reconciliation_readiness(latest_r256)
        decision_packet = build_final_manual_decision_packet(
            input_summary=input_summary,
            pre_submit_blocker_summary=blocker_summary,
            live_control_intent_state=live_controls,
        )
        matrix = build_final_pre_submit_arming_drill_matrix(
            input_summary=input_summary,
            pre_submit_blocker_summary=blocker_summary,
            signed_request_regeneration_requirement=regeneration,
            live_control_intent_state=live_controls,
            exact_submit_command_readiness=command_readiness,
            reconciliation_readiness=reconciliation,
            record_confirmed=confirmation_valid,
            recorded=False,
        )
        status = classify_tiny_live_final_pre_submit_arming_drill_status(
            input_summary=input_summary,
            record_requested=record_final_pre_submit_arming_drill,
            confirmation_valid=confirmation_valid,
            recorded=False,
        )
        overall = _overall_status(
            input_summary=input_summary,
            record_requested=record_final_pre_submit_arming_drill,
            confirmation_valid=confirmation_valid,
            recorded=False,
        )
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "record_final_pre_submit_arming_drill_requested": bool(
                    record_final_pre_submit_arming_drill
                ),
                "confirmation_valid": bool(confirmation_valid),
                "final_pre_submit_arming_drill_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "final_pre_submit_arming_drill_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "pre_submit_blocker_summary": blocker_summary,
                "signed_request_regeneration_requirement": regeneration,
                "live_control_intent_state": live_controls,
                "exact_submit_command_readiness": command_readiness,
                "reconciliation_readiness": reconciliation,
                "final_manual_decision_packet": decision_packet,
                "final_pre_submit_arming_drill_matrix": matrix,
                "final_pre_submit_arming_drill_overall_status": overall,
                "recommended_next_operator_move": _recommended_next_operator_move(decision_packet),
                "recommended_next_engineering_move": _recommended_next_engineering_move(input_summary),
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if record_final_pre_submit_arming_drill and confirmation_valid:
            payload["status"] = TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_RECORDED
            payload["final_pre_submit_arming_drill_overall_status"] = (
                TINY_LIVE_FINAL_ARMING_DRILL_RECORDED_MANUAL_DECISION_REQUIRED
            )
            payload["final_pre_submit_arming_drill_matrix"]["record_confirmed"] = True
            payload["final_pre_submit_arming_drill_matrix"]["recorded"] = True
            payload = append_tiny_live_final_pre_submit_arming_drill_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_final_pre_submit_arming_drill=(
                    confirm_tiny_live_final_pre_submit_arming_drill
                ),
            )
        return payload
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        return _sanitize(
            {
                "status": TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_ERROR,
                "generated_at": generated_at.isoformat(),
                "record_final_pre_submit_arming_drill_requested": bool(
                    record_final_pre_submit_arming_drill
                ),
                "confirmation_valid": bool(confirmation_valid),
                "final_pre_submit_arming_drill_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "final_pre_submit_arming_drill_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "error": type(exc).__name__,
                "final_pre_submit_arming_drill_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "safety": dict(SAFETY),
            }
        )


def load_latest_tiny_live_operator_real_submit_runbook(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_operator_real_submit_runbook_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_actual_submit_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r255_from_r256(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_submit_gate_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r254_from_r256(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_fresh_context_signed_request_regeneration_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r253b_from_r256(log_dir=log_dir, official_lane_key=official_lane_key)


def summarize_pre_submit_blockers(
    *,
    latest_r256: Mapping[str, Any] | None = None,
    latest_r255: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    r256_blockers = (
        latest_r256.get("current_submit_blockers")
        if isinstance((latest_r256 or {}).get("current_submit_blockers"), Mapping)
        else {}
    )
    source = dict(r256_blockers) if r256_blockers else summarize_current_submit_blockers_for_operator(latest_r255 or {})
    blocked_by = list(source.get("blocked_by") or [])
    if not latest_r256:
        blocked_by.append("r256_operator_runbook_missing")
    return {
        "blocked_by": _dedupe(blocked_by),
        "submit_allowed_now": False,
        "requires_regeneration": bool(source.get("requires_regeneration") is True),
        "requires_live_controls_arming_review": bool(
            source.get("requires_live_controls_arming") is True
            or any(
                item in blocked_by
                for item in (
                    "official_lane_not_tiny_live",
                    "live_execution_not_enabled",
                    "kill_switch_blocks_tiny_live",
                )
            )
        ),
        "requires_manual_operator_decision": True,
    }


def summarize_signed_request_regeneration_requirement(
    *,
    latest_r255: Mapping[str, Any] | None = None,
    pre_submit_blocker_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blockers = pre_submit_blocker_summary or {}
    freshness = (
        latest_r255.get("signed_request_freshness")
        if isinstance((latest_r255 or {}).get("signed_request_freshness"), Mapping)
        else {}
    )
    blocked_by = list(blockers.get("blocked_by") or [])
    regeneration_required = bool(
        blockers.get("requires_regeneration") is True
        or freshness.get("requires_regeneration") is True
        or "signed_request_timestamp_stale" in blocked_by
    )
    if "signed_request_timestamp_stale" in blocked_by or freshness.get("requires_regeneration") is True:
        reason = "timestamp_stale"
    elif regeneration_required:
        reason = "unknown"
    elif latest_r255:
        reason = "fresh_enough"
    else:
        reason = "unknown"
    return {
        "regeneration_required_now": regeneration_required,
        "reason": reason,
        "required_sequence": [
            "R253 final readonly refresh",
            "R253B fresh signed request regeneration",
            "R254 submit gate preview",
            "R255 dry preview",
        ],
    }


def summarize_live_control_intent_state(
    *,
    latest_r255: Mapping[str, Any] | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    latest_summary = (
        latest_r255.get("kill_switch_lane_control_summary")
        if isinstance((latest_r255 or {}).get("kill_switch_lane_control_summary"), Mapping)
        else {}
    )
    try:
        current_summary = validate_kill_switch_and_lane_controls_for_tiny_live_submit(
            official_lane_key=official_lane_key,
        )
    except Exception:
        current_summary = {}
    summary = current_summary or latest_summary
    live_execution_enabled = summary.get("live_execution_enabled") is True
    official_lane_allowed = summary.get("official_lane_allowed") is True
    kill_switch_allows = summary.get("kill_switch_allows_tiny_live") is True
    return {
        "live_execution_enabled": live_execution_enabled,
        "official_lane_allowed": official_lane_allowed,
        "kill_switch_allows_tiny_live": kill_switch_allows,
        "operator_must_arm_manually": not (live_execution_enabled and official_lane_allowed and kill_switch_allows),
        "auto_armed_by_this_phase": False,
    }


def summarize_exact_submit_command_readiness(latest_r256: Mapping[str, Any]) -> dict[str, Any]:
    template = (
        latest_r256.get("real_submit_command_template")
        if isinstance(latest_r256.get("real_submit_command_template"), Mapping)
        else build_real_submit_command_template()
    )
    command = str(template.get("command") or "")
    phrase = str(template.get("confirmation_phrase") or REAL_SUBMIT_CONFIRMATION_PHRASE)
    return {
        "template_available": bool(command),
        "contains_execute_flag": "--execute-actual-submit" in command,
        "contains_allow_real_endpoint_flag": "--allow-real-binance-order-endpoint" in command,
        "contains_exact_confirmation_phrase": bool(phrase and phrase in command),
        "must_not_auto_run": True,
    }


def summarize_reconciliation_readiness(latest_r256: Mapping[str, Any]) -> dict[str, Any]:
    reconciliation = latest_r256.get("post_submit_reconciliation_checklist")
    partial = latest_r256.get("partial_success_handling_plan")
    abort_tree = latest_r256.get("abort_cleanup_decision_tree")
    duplicate = latest_r256.get("duplicate_submit_protection_review")
    return {
        "post_submit_reconciliation_checklist_present": bool(reconciliation),
        "partial_success_plan_present": bool(partial),
        "abort_cleanup_tree_present": bool(abort_tree),
        "duplicate_submit_protection_present": bool(duplicate),
    }


def build_final_manual_decision_packet(
    *,
    input_summary: Mapping[str, Any],
    pre_submit_blocker_summary: Mapping[str, Any],
    live_control_intent_state: Mapping[str, Any],
) -> dict[str, Any]:
    if input_summary.get("r256_operator_runbook_found") is not True:
        action = "FIX_BLOCKER"
    elif pre_submit_blocker_summary.get("requires_regeneration") is True:
        action = "REGENERATE_SIGNED_REQUEST"
    elif live_control_intent_state.get("operator_must_arm_manually") is True:
        action = "ARM_LIVE_CONTROLS_MANUALLY"
    elif input_summary.get("r255_actual_submit_gate_found") is not True:
        action = "RUN_R255_DRY_PREVIEW"
    elif pre_submit_blocker_summary.get("blocked_by"):
        action = "WAIT"
    else:
        action = "MANUAL_SUBMIT_DECISION"
    return {
        "operator_should_submit_now": False,
        "operator_should_regenerate_first": pre_submit_blocker_summary.get("requires_regeneration") is True,
        "operator_should_arm_live_controls_manually": live_control_intent_state.get("operator_must_arm_manually") is True,
        "operator_should_run_r255_dry_preview_after_regeneration": True,
        "operator_should_review_runbook_again_before_manual_submit": True,
        "manual_submit_decision_required": True,
        "next_required_human_action": action,
    }


def build_final_pre_submit_arming_drill_matrix(
    *,
    input_summary: Mapping[str, Any],
    pre_submit_blocker_summary: Mapping[str, Any],
    signed_request_regeneration_requirement: Mapping[str, Any],
    live_control_intent_state: Mapping[str, Any],
    exact_submit_command_readiness: Mapping[str, Any],
    reconciliation_readiness: Mapping[str, Any],
    record_confirmed: bool,
    recorded: bool,
) -> dict[str, Any]:
    return {
        "r256_available": input_summary.get("r256_operator_runbook_found") is True,
        "runbook_reviewed": input_summary.get("r256_operator_runbook_valid") is True,
        "regeneration_status_known": signed_request_regeneration_requirement.get("reason") != "unknown",
        "live_control_intent_known": any(
            key in live_control_intent_state
            for key in ("live_execution_enabled", "official_lane_allowed", "kill_switch_allows_tiny_live")
        ),
        "exact_submit_command_known": bool(exact_submit_command_readiness.get("template_available")),
        "reconciliation_ready": all(bool(value) for value in reconciliation_readiness.values()),
        "record_confirmed": bool(record_confirmed),
        "recorded": bool(recorded),
        "submit_allowed": False,
        "order_placed": False,
        "blocked_by": _dedupe(pre_submit_blocker_summary.get("blocked_by") or []),
    }


def classify_tiny_live_final_pre_submit_arming_drill_status(
    *,
    input_summary: Mapping[str, Any],
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_REJECTED
    if recorded:
        return TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_RECORDED
    if input_summary.get("r256_operator_runbook_found") is not True:
        return TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_BLOCKED
    return TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_READY


def append_tiny_live_final_pre_submit_arming_drill_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_final_pre_submit_arming_drill: str | None = None,
) -> dict[str, Any]:
    if (
        confirm_tiny_live_final_pre_submit_arming_drill
        != CONFIRM_TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_PHRASE
    ):
        raise ValueError("bad_tiny_live_final_pre_submit_arming_drill_confirmation")
    path = tiny_live_final_pre_submit_arming_drill_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "final_pre_submit_arming_drill_record_id": (
                record.get("final_pre_submit_arming_drill_record_id")
                or f"r257_final_pre_submit_arming_drill_{uuid4().hex}"
            ),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "final_pre_submit_arming_drill_recorded": True,
            "created_by_phase": CREATED_BY_PHASE,
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_final_pre_submit_arming_drill_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_final_pre_submit_arming_drill_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_final_pre_submit_arming_drill_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    packet = (
        latest.get("final_manual_decision_packet")
        if isinstance(latest.get("final_manual_decision_packet"), Mapping)
        else {}
    )
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_recorded": latest.get("final_pre_submit_arming_drill_recorded") is True,
        "latest_overall_status": latest.get("final_pre_submit_arming_drill_overall_status"),
        "latest_next_required_human_action": packet.get("next_required_human_action"),
    }


def tiny_live_final_pre_submit_arming_drill_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_final_pre_submit_arming_drill_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _overall_status(
    *,
    input_summary: Mapping[str, Any],
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_FINAL_ARMING_DRILL_REJECTED_BAD_CONFIRMATION
    if recorded:
        return TINY_LIVE_FINAL_ARMING_DRILL_RECORDED_MANUAL_DECISION_REQUIRED
    if input_summary.get("r256_operator_runbook_found") is not True:
        return TINY_LIVE_FINAL_ARMING_DRILL_BLOCKED_BY_MISSING_R256
    return TINY_LIVE_FINAL_ARMING_DRILL_READY_FOR_RECORDING


def _r256_valid(record: Mapping[str, Any]) -> bool:
    if not record:
        return False
    safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
    return bool(
        record.get("operator_runbook_recorded") is True
        and record.get("operator_manual_decision_packet", {}).get("operator_should_submit_now") is False
        and safety.get("submit_allowed") is False
        and safety.get("order_placed") is False
        and safety.get("real_order_placed") is False
        and safety.get("execution_attempted") is False
        and safety.get("secrets_shown") is False
    )


def _recommended_next_operator_move(packet: Mapping[str, Any]) -> str:
    return str(packet.get("next_required_human_action") or "FIX_BLOCKER")


def _recommended_next_engineering_move(input_summary: Mapping[str, Any]) -> str:
    if input_summary.get("r256_operator_runbook_found") is not True:
        return "Record the R256 operator runbook before the final R257 arming drill."
    return "Create R258 manual-submit checkpoint placeholder; keep real submit manual and unexecuted."


def _do_not_run_yet() -> list[str]:
    return [
        "real submit without fresh signed request",
        "real submit without explicit live controls arming",
        "real submit without R255 dry preview",
        "real submit without reconciliation plan",
        "duplicate live submit",
    ]


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    scope = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    return scope.get("official_lane_key") == official_lane_key


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = lane_key.split("|")
    if len(parts) != 4:
        return lane_key, "", "", ""
    return parts[0], parts[1], parts[2], parts[3]


def _dedupe(items: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
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
    return value
