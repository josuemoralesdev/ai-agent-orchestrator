"""R258 tiny-live manual submit checkpoint.

This module builds the final manual checkpoint packet before a later fresh-cycle
review. It never signs, submits, calls Binance/network, regenerates signed
requests, arms live controls, or mutates configs. The only allowed mutation is
its own audit ledger append after the exact R258 confirmation phrase.
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
from src.app.hammer_radar.operator.tiny_live_final_pre_submit_arming_drill import (
    load_latest_tiny_live_actual_submit_gate as _load_latest_r255_from_r257,
    load_latest_tiny_live_fresh_context_signed_request_regeneration_gate as _load_latest_r253b_from_r257,
    load_latest_tiny_live_operator_real_submit_runbook as _load_latest_r256_from_r257,
    load_latest_tiny_live_submit_gate_preview as _load_latest_r254_from_r257,
    load_tiny_live_final_pre_submit_arming_drill_records,
    summarize_exact_submit_command_readiness,
    summarize_live_control_intent_state,
    summarize_pre_submit_blockers,
    summarize_reconciliation_readiness,
)
from src.app.hammer_radar.operator.tiny_live_operator_real_submit_runbook import (
    build_real_submit_command_template,
)

TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_READY = "TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_READY"
TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_RECORDED = (
    "TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_RECORDED"
)
TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_REJECTED = (
    "TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_REJECTED"
)
TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_BLOCKED = "TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_BLOCKED"
TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_ERROR = "TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_ERROR"

TINY_LIVE_MANUAL_CHECKPOINT_READY_FOR_RECORDING = (
    "TINY_LIVE_MANUAL_CHECKPOINT_READY_FOR_RECORDING"
)
TINY_LIVE_MANUAL_CHECKPOINT_RECORDED_FRESH_CYCLE_REQUIRED = (
    "TINY_LIVE_MANUAL_CHECKPOINT_RECORDED_FRESH_CYCLE_REQUIRED"
)
TINY_LIVE_MANUAL_CHECKPOINT_RECORDED_MANUAL_DECISION_REQUIRED = (
    "TINY_LIVE_MANUAL_CHECKPOINT_RECORDED_MANUAL_DECISION_REQUIRED"
)
TINY_LIVE_MANUAL_CHECKPOINT_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_MANUAL_CHECKPOINT_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_MANUAL_CHECKPOINT_BLOCKED_BY_MISSING_R257 = (
    "TINY_LIVE_MANUAL_CHECKPOINT_BLOCKED_BY_MISSING_R257"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT"
LEDGER_FILENAME = "tiny_live_manual_submit_checkpoint.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R258_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT"
CONFIRM_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_PHRASE = (
    "I CONFIRM TINY LIVE MANUAL SUBMIT CHECKPOINT RECORDING ONLY; "
    "NO SUBMIT; NO ORDER; NO BINANCE CALL."
)

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_final_pre_submit_arming_drill.ndjson",
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
    "manual_submit_checkpoint_only": True,
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


def build_tiny_live_manual_submit_checkpoint(
    *,
    log_dir: str | Path | None = None,
    record_manual_submit_checkpoint: bool = False,
    confirm_tiny_live_manual_submit_checkpoint: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_manual_submit_checkpoint
        == CONFIRM_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_PHRASE
    )
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)

    try:
        latest_r257 = load_latest_tiny_live_final_pre_submit_arming_drill(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
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
        input_summary = summarize_checkpoint_inputs(
            latest_r257=latest_r257,
            latest_r256=latest_r256,
            latest_r255=latest_r255,
            latest_r254=latest_r254,
            latest_r253b=latest_r253b,
        )
        blocker_summary = summarize_current_manual_submit_blockers(
            latest_r257=latest_r257,
            latest_r256=latest_r256,
            latest_r255=latest_r255,
        )
        fresh_cycle = summarize_fresh_cycle_requirement(
            manual_submit_blocker_summary=blocker_summary,
        )
        live_controls = summarize_live_controls_checkpoint(
            latest_r257=latest_r257,
            latest_r255=latest_r255,
            official_lane_key=official_lane_key,
        )
        command = summarize_real_submit_command_checkpoint(latest_r256=latest_r256)
        reconciliation = summarize_reconciliation_checkpoint(latest_r256=latest_r256)
        packet = build_manual_submit_go_no_go_packet(
            input_summary=input_summary,
            manual_submit_blocker_summary=blocker_summary,
            fresh_cycle_requirement=fresh_cycle,
            live_controls_checkpoint=live_controls,
        )
        matrix = build_manual_submit_checkpoint_matrix(
            input_summary=input_summary,
            fresh_cycle_requirement=fresh_cycle,
            live_controls_checkpoint=live_controls,
            real_submit_command_checkpoint=command,
            reconciliation_checkpoint=reconciliation,
            record_confirmed=confirmation_valid,
            recorded=False,
            blocked_by=blocker_summary["blocked_by"],
        )
        status = classify_tiny_live_manual_submit_checkpoint_status(
            input_summary=input_summary,
            record_requested=record_manual_submit_checkpoint,
            confirmation_valid=confirmation_valid,
            recorded=False,
        )
        overall = _overall_status(
            input_summary=input_summary,
            fresh_cycle_requirement=fresh_cycle,
            record_requested=record_manual_submit_checkpoint,
            confirmation_valid=confirmation_valid,
            recorded=False,
        )
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "record_manual_submit_checkpoint_requested": bool(record_manual_submit_checkpoint),
                "confirmation_valid": bool(confirmation_valid),
                "manual_submit_checkpoint_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "manual_submit_checkpoint_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "manual_submit_blocker_summary": blocker_summary,
                "fresh_cycle_requirement": fresh_cycle,
                "live_controls_checkpoint": live_controls,
                "real_submit_command_checkpoint": command,
                "reconciliation_checkpoint": reconciliation,
                "manual_submit_go_no_go_packet": packet,
                "manual_submit_checkpoint_matrix": matrix,
                "manual_submit_checkpoint_overall_status": overall,
                "recommended_next_operator_move": _recommended_next_operator_move(packet),
                "recommended_next_engineering_move": _recommended_next_engineering_move(input_summary),
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if record_manual_submit_checkpoint and confirmation_valid:
            payload["status"] = TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_RECORDED
            payload["manual_submit_checkpoint_recorded"] = True
            payload["manual_submit_checkpoint_matrix"]["record_confirmed"] = True
            payload["manual_submit_checkpoint_matrix"]["recorded"] = True
            payload["manual_submit_checkpoint_overall_status"] = _overall_status(
                input_summary=input_summary,
                fresh_cycle_requirement=fresh_cycle,
                record_requested=record_manual_submit_checkpoint,
                confirmation_valid=confirmation_valid,
                recorded=True,
            )
            payload = append_tiny_live_manual_submit_checkpoint_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_manual_submit_checkpoint=(
                    confirm_tiny_live_manual_submit_checkpoint
                ),
            )
        return payload
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        return _sanitize(
            {
                "status": TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_ERROR,
                "generated_at": generated_at.isoformat(),
                "record_manual_submit_checkpoint_requested": bool(record_manual_submit_checkpoint),
                "confirmation_valid": bool(confirmation_valid),
                "manual_submit_checkpoint_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "manual_submit_checkpoint_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "error": type(exc).__name__,
                "manual_submit_checkpoint_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "safety": dict(SAFETY),
            }
        )


def load_latest_tiny_live_final_pre_submit_arming_drill(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_final_pre_submit_arming_drill_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_operator_real_submit_runbook(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r256_from_r257(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_actual_submit_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r255_from_r257(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_submit_gate_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r254_from_r257(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_fresh_context_signed_request_regeneration_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r253b_from_r257(log_dir=log_dir, official_lane_key=official_lane_key)


def summarize_checkpoint_inputs(
    *,
    latest_r257: Mapping[str, Any] | None = None,
    latest_r256: Mapping[str, Any] | None = None,
    latest_r255: Mapping[str, Any] | None = None,
    latest_r254: Mapping[str, Any] | None = None,
    latest_r253b: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "r257_final_arming_drill_found": bool(latest_r257),
        "r257_final_arming_drill_valid": _r257_valid(latest_r257 or {}),
        "r256_operator_runbook_found": bool(latest_r256),
        "r255_actual_submit_gate_found": bool(latest_r255),
        "r254_submit_gate_preview_found": bool(latest_r254),
        "r253b_fresh_regeneration_found": bool(latest_r253b),
    }


def summarize_current_manual_submit_blockers(
    *,
    latest_r257: Mapping[str, Any] | None = None,
    latest_r256: Mapping[str, Any] | None = None,
    latest_r255: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    r257_blockers = (
        latest_r257.get("pre_submit_blocker_summary")
        if isinstance((latest_r257 or {}).get("pre_submit_blocker_summary"), Mapping)
        else {}
    )
    source = (
        dict(r257_blockers)
        if r257_blockers
        else summarize_pre_submit_blockers(latest_r256=latest_r256 or {}, latest_r255=latest_r255 or {})
    )
    blocked_by = list(source.get("blocked_by") or [])
    if not latest_r257:
        blocked_by.append("r257_final_arming_drill_missing")
    fresh_cycle_required = bool(
        source.get("requires_regeneration") is True
        or source.get("fresh_cycle_required") is True
        or "signed_request_timestamp_stale" in blocked_by
    )
    live_review_required = bool(
        source.get("requires_live_controls_arming_review") is True
        or source.get("requires_live_controls_arming") is True
        or any(
            item in blocked_by
            for item in (
                "official_lane_not_tiny_live",
                "live_execution_not_enabled",
                "kill_switch_blocks_tiny_live",
            )
        )
    )
    return {
        "blocked_by": _dedupe(blocked_by),
        "submit_allowed_now": False,
        "operator_should_not_submit_now": True,
        "fresh_cycle_required": fresh_cycle_required,
        "live_controls_manual_review_required": live_review_required,
        "manual_decision_required": True,
    }


def summarize_fresh_cycle_requirement(
    *, manual_submit_blocker_summary: Mapping[str, Any]
) -> dict[str, Any]:
    blocked_by = list(manual_submit_blocker_summary.get("blocked_by") or [])
    required = bool(manual_submit_blocker_summary.get("fresh_cycle_required") is True)
    if "signed_request_timestamp_stale" in blocked_by:
        reason = "timestamp_stale"
    elif manual_submit_blocker_summary.get("live_controls_manual_review_required") is True:
        reason = "controls_blocked"
    elif required:
        reason = "manual_checkpoint"
    else:
        reason = "manual_checkpoint"
    return {
        "required_now": required,
        "reason": reason,
        "sequence": [
            "R253 final readonly refresh",
            "R253B fresh signed request regeneration",
            "R254 submit gate preview",
            "R255 dry preview",
            "R258 manual checkpoint re-check",
        ],
        "r259_future_phase": "R259_TINY_LIVE_FRESH_CYCLE_CHECKPOINT",
    }


def summarize_live_controls_checkpoint(
    *,
    latest_r257: Mapping[str, Any] | None = None,
    latest_r255: Mapping[str, Any] | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    r257_summary = (
        latest_r257.get("live_control_intent_state")
        if isinstance((latest_r257 or {}).get("live_control_intent_state"), Mapping)
        else {}
    )
    summary = r257_summary or summarize_live_control_intent_state(
        latest_r255=latest_r255 or {},
        official_lane_key=official_lane_key,
    )
    live_execution_enabled = summary.get("live_execution_enabled") is True
    official_lane_allowed = summary.get("official_lane_allowed") is True
    kill_switch_allows = summary.get("kill_switch_allows_tiny_live") is True
    return {
        "live_execution_enabled": live_execution_enabled,
        "official_lane_allowed": official_lane_allowed,
        "kill_switch_allows_tiny_live": kill_switch_allows,
        "manual_arming_required": not (
            live_execution_enabled and official_lane_allowed and kill_switch_allows
        ),
        "auto_armed_by_this_phase": False,
    }


def summarize_real_submit_command_checkpoint(
    *, latest_r256: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    summary = summarize_exact_submit_command_readiness(latest_r256 or {})
    template = (
        (latest_r256 or {}).get("real_submit_command_template")
        if isinstance((latest_r256 or {}).get("real_submit_command_template"), Mapping)
        else build_real_submit_command_template()
    )
    return {
        "template_available": summary.get("template_available") is True,
        "must_not_auto_run": True,
        "requires_manual_operator_paste": template.get("requires_manual_operator_paste") is True,
        "contains_execute_flag": summary.get("contains_execute_flag") is True,
        "contains_allow_real_endpoint_flag": summary.get("contains_allow_real_endpoint_flag") is True,
        "contains_exact_confirmation_phrase": summary.get("contains_exact_confirmation_phrase") is True,
    }


def summarize_reconciliation_checkpoint(
    *, latest_r256: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    summary = summarize_reconciliation_readiness(latest_r256 or {})
    return {
        "post_submit_reconciliation_ready": (
            summary.get("post_submit_reconciliation_checklist_present") is True
        ),
        "partial_success_plan_ready": summary.get("partial_success_plan_present") is True,
        "abort_cleanup_ready": summary.get("abort_cleanup_tree_present") is True,
        "duplicate_submit_protection_ready": (
            summary.get("duplicate_submit_protection_present") is True
        ),
    }


def build_manual_submit_go_no_go_packet(
    *,
    input_summary: Mapping[str, Any],
    manual_submit_blocker_summary: Mapping[str, Any],
    fresh_cycle_requirement: Mapping[str, Any],
    live_controls_checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    if input_summary.get("r257_final_arming_drill_found") is not True:
        action = "FIX_BLOCKER"
    elif fresh_cycle_requirement.get("required_now") is True:
        action = "RUN_FRESH_CYCLE"
    elif live_controls_checkpoint.get("manual_arming_required") is True:
        action = "ARM_LIVE_CONTROLS_MANUALLY"
    elif input_summary.get("r255_actual_submit_gate_found") is not True:
        action = "RUN_R255_DRY_PREVIEW"
    elif manual_submit_blocker_summary.get("blocked_by"):
        action = "WAIT"
    else:
        action = "MANUAL_DECISION_REQUIRED"
    return {
        "go_for_manual_submit_now": False,
        "no_go_reasons": _dedupe(manual_submit_blocker_summary.get("blocked_by") or []),
        "operator_should_regenerate_first": fresh_cycle_requirement.get("required_now") is True,
        "operator_should_arm_live_controls_manually": (
            live_controls_checkpoint.get("manual_arming_required") is True
        ),
        "operator_should_run_r255_dry_preview": True,
        "operator_should_review_reconciliation": True,
        "operator_should_submit_now": False,
        "next_required_human_action": action,
    }


def build_manual_submit_checkpoint_matrix(
    *,
    input_summary: Mapping[str, Any],
    fresh_cycle_requirement: Mapping[str, Any],
    live_controls_checkpoint: Mapping[str, Any],
    real_submit_command_checkpoint: Mapping[str, Any],
    reconciliation_checkpoint: Mapping[str, Any],
    record_confirmed: bool,
    recorded: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "r257_available": input_summary.get("r257_final_arming_drill_found") is True,
        "fresh_cycle_requirement_known": (
            fresh_cycle_requirement.get("reason") in {"timestamp_stale", "controls_blocked", "manual_checkpoint"}
        ),
        "live_controls_state_known": all(
            key in live_controls_checkpoint
            for key in ("live_execution_enabled", "official_lane_allowed", "kill_switch_allows_tiny_live")
        ),
        "submit_command_known": real_submit_command_checkpoint.get("template_available") is True,
        "reconciliation_ready": all(bool(value) for value in reconciliation_checkpoint.values()),
        "record_confirmed": bool(record_confirmed),
        "recorded": bool(recorded),
        "submit_allowed": False,
        "order_placed": False,
        "blocked_by": _dedupe(blocked_by or []),
    }


def classify_tiny_live_manual_submit_checkpoint_status(
    *,
    input_summary: Mapping[str, Any],
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_REJECTED
    if recorded:
        return TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_RECORDED
    if input_summary.get("r257_final_arming_drill_found") is not True:
        return TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_BLOCKED
    return TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_READY


def append_tiny_live_manual_submit_checkpoint_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_manual_submit_checkpoint: str | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_manual_submit_checkpoint != CONFIRM_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_PHRASE:
        raise ValueError("bad_tiny_live_manual_submit_checkpoint_confirmation")
    path = tiny_live_manual_submit_checkpoint_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "manual_submit_checkpoint_record_id": record.get("manual_submit_checkpoint_record_id")
            or f"r258_manual_submit_checkpoint_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "manual_submit_checkpoint_recorded": True,
            "created_by_phase": CREATED_BY_PHASE,
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_manual_submit_checkpoint_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_manual_submit_checkpoint_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_manual_submit_checkpoint_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    packet = (
        latest.get("manual_submit_go_no_go_packet")
        if isinstance(latest.get("manual_submit_go_no_go_packet"), Mapping)
        else {}
    )
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_recorded": latest.get("manual_submit_checkpoint_recorded") is True,
        "latest_overall_status": latest.get("manual_submit_checkpoint_overall_status"),
        "latest_next_required_human_action": packet.get("next_required_human_action"),
    }


def tiny_live_manual_submit_checkpoint_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_manual_submit_checkpoint_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _overall_status(
    *,
    input_summary: Mapping[str, Any],
    fresh_cycle_requirement: Mapping[str, Any],
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_MANUAL_CHECKPOINT_REJECTED_BAD_CONFIRMATION
    if recorded and fresh_cycle_requirement.get("required_now") is True:
        return TINY_LIVE_MANUAL_CHECKPOINT_RECORDED_FRESH_CYCLE_REQUIRED
    if recorded:
        return TINY_LIVE_MANUAL_CHECKPOINT_RECORDED_MANUAL_DECISION_REQUIRED
    if input_summary.get("r257_final_arming_drill_found") is not True:
        return TINY_LIVE_MANUAL_CHECKPOINT_BLOCKED_BY_MISSING_R257
    return TINY_LIVE_MANUAL_CHECKPOINT_READY_FOR_RECORDING


def _r257_valid(record: Mapping[str, Any]) -> bool:
    if not record:
        return False
    safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
    return bool(
        record.get("final_pre_submit_arming_drill_recorded") is True
        and record.get("final_manual_decision_packet", {}).get("operator_should_submit_now") is False
        and safety.get("submit_allowed") is False
        and safety.get("order_placed") is False
        and safety.get("real_order_placed") is False
        and safety.get("execution_attempted") is False
        and safety.get("secrets_shown") is False
    )


def _recommended_next_operator_move(packet: Mapping[str, Any]) -> str:
    return str(packet.get("next_required_human_action") or "FIX_BLOCKER")


def _recommended_next_engineering_move(input_summary: Mapping[str, Any]) -> str:
    if input_summary.get("r257_final_arming_drill_found") is not True:
        return "Record R257 final pre-submit arming drill before R258."
    return "Create R259 fresh-cycle checkpoint; still no submit or Binance call."


def _do_not_run_yet() -> list[str]:
    return [
        "real submit without fresh cycle",
        "real submit without manual live-control arming review",
        "real submit without R255 dry preview",
        "duplicate live submit",
        "manual submit while blockers remain",
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
