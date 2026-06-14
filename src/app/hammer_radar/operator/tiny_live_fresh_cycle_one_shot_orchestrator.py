"""R260 tiny-live fresh-cycle one-shot orchestrator.

This module compresses the R253 -> R253B -> R254 -> R255 dry preview -> R258
fresh-cycle sequence into one confirmed operator command. It delegates each
step to the existing phase module and never submits or calls Binance order,
account, private, or signed endpoints.
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
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import (
    DEFAULT_OFFICIAL_TINY_LIVE_LANE,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_actual_submit_gate import (
    DRY_PREVIEW_CONFIRMATION_PHRASE,
    build_tiny_live_actual_submit_gate,
)
from src.app.hammer_radar.operator.tiny_live_final_readonly_mark_price_refresh_gate import (
    CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE,
    build_tiny_live_final_readonly_mark_price_refresh_gate,
)
from src.app.hammer_radar.operator.tiny_live_fresh_context_signed_request_regeneration_gate import (
    CONFIRM_TINY_LIVE_FRESH_CONTEXT_REGENERATION_PHRASE,
    build_tiny_live_fresh_context_signed_request_regeneration_gate,
)
from src.app.hammer_radar.operator.tiny_live_fresh_cycle_checkpoint import (
    load_tiny_live_fresh_cycle_checkpoint_records,
)
from src.app.hammer_radar.operator.tiny_live_manual_submit_checkpoint import (
    CONFIRM_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_PHRASE,
    build_tiny_live_manual_submit_checkpoint,
)
from src.app.hammer_radar.operator.tiny_live_submit_gate_preview import (
    CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE,
    build_tiny_live_submit_gate_preview,
)

TINY_LIVE_FRESH_CYCLE_ONE_SHOT_READY = "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_READY"
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED = "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED"
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_REJECTED = "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_REJECTED"
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED = "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED"
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ERROR = "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ERROR"

TINY_LIVE_FRESH_CYCLE_ONE_SHOT_READY_FOR_CONFIRMATION = (
    "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_READY_FOR_CONFIRMATION"
)
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED_READY_FOR_LIVE_CONTROL_REVIEW = (
    "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED_READY_FOR_LIVE_CONTROL_REVIEW"
)
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED_STILL_BLOCKED = (
    "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED_STILL_BLOCKED"
)
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R253 = (
    "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R253"
)
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R253B = (
    "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R253B"
)
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R254 = (
    "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R254"
)
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R255 = (
    "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R255"
)
TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R258 = (
    "TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R258"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_FRESH_CYCLE_ONE_SHOT"
LEDGER_FILENAME = "tiny_live_fresh_cycle_one_shot.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R260_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ORCHESTRATOR"
CONFIRM_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_PHRASE = (
    "I CONFIRM TINY LIVE FRESH CYCLE ONE-SHOT ORCHESTRATION ONLY; "
    "REFRESH READONLY MARKET, REGENERATE LOCAL SIGNED REQUEST, RECORD PREVIEWS; "
    "NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL."
)

STEP_NAMES = [
    "R253_READONLY_REFRESH",
    "R253B_REGENERATION",
    "R254_SUBMIT_GATE_PREVIEW",
    "R255_DRY_PREVIEW",
    "R258_MANUAL_CHECKPOINT_RECHECK",
]

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_fresh_cycle_checkpoint.ndjson",
    "logs/hammer_radar_forward/tiny_live_final_readonly_mark_price_refresh_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson",
    "logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_manual_submit_checkpoint.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_fresh_cycle_one_shot_orchestrator(
    *,
    log_dir: str | Path | None = None,
    run_fresh_cycle_one_shot: bool = False,
    record_fresh_cycle_one_shot: bool = False,
    confirm_tiny_live_fresh_cycle_one_shot: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_fresh_cycle_one_shot
        == CONFIRM_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_PHRASE
    )
    symbol, timeframe, direction, _entry_mode = _lane_parts(official_lane_key)
    safety = build_one_shot_safety_summary(
        r253_ran=False,
        r253b_ran=False,
        r253b_written=False,
    )

    try:
        latest_r259 = load_latest_tiny_live_fresh_cycle_checkpoint(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        input_summary = {
            "r259_fresh_cycle_checkpoint_found": bool(latest_r259),
            "r259_fresh_cycle_checkpoint_valid": _r259_valid(latest_r259),
            "fresh_cycle_required": _fresh_cycle_required(latest_r259),
        }
        step_plan = build_one_shot_step_plan(
            run_requested=run_fresh_cycle_one_shot,
            confirmation_valid=confirmation_valid,
        )

        step_results = build_one_shot_step_results()
        if run_fresh_cycle_one_shot and confirmation_valid:
            step_results["r253_readonly_refresh"] = run_or_preview_r253_readonly_refresh_step(
                log_dir=resolved_log_dir,
                run_step=True,
                official_lane_key=official_lane_key,
            )
            if step_results["r253_readonly_refresh"]["succeeded"]:
                step_results["r253b_regeneration"] = run_or_preview_r253b_regeneration_step(
                    log_dir=resolved_log_dir,
                    run_step=True,
                    official_lane_key=official_lane_key,
                )
            if step_results["r253b_regeneration"]["succeeded"]:
                step_results["r254_submit_gate_preview"] = run_or_preview_r254_submit_gate_preview_step(
                    log_dir=resolved_log_dir,
                    run_step=True,
                    official_lane_key=official_lane_key,
                )
            if step_results["r254_submit_gate_preview"]["succeeded"]:
                step_results["r255_dry_preview"] = run_or_preview_r255_dry_preview_step(
                    log_dir=resolved_log_dir,
                    run_step=True,
                    official_lane_key=official_lane_key,
                )
            if step_results["r255_dry_preview"]["succeeded"]:
                step_results["r258_manual_checkpoint_recheck"] = run_or_preview_r258_manual_checkpoint_recheck_step(
                    log_dir=resolved_log_dir,
                    run_step=True,
                    official_lane_key=official_lane_key,
                )
            safety = build_one_shot_safety_summary(
                r253_ran=step_results["r253_readonly_refresh"]["attempted"],
                r253b_ran=step_results["r253b_regeneration"]["attempted"],
                r253b_written=step_results["r253b_regeneration"]["succeeded"],
            )

        validation = validate_one_shot_outputs(step_results=step_results)
        checkpoint_matrix = build_one_shot_checkpoint_matrix(
            input_summary=input_summary,
            step_results=step_results,
            validation=validation,
        )
        go_no_go = build_one_shot_go_no_go_packet(
            validation=validation,
            checkpoint_matrix=checkpoint_matrix,
        )
        operator_packet = build_one_shot_operator_packet(go_no_go_packet=go_no_go)
        overall = classify_tiny_live_fresh_cycle_one_shot_status(
            run_requested=run_fresh_cycle_one_shot,
            record_requested=record_fresh_cycle_one_shot,
            confirmation_valid=confirmation_valid,
            validation=validation,
            step_results=step_results,
            recorded=False,
        )
        status = _top_level_status(
            run_requested=run_fresh_cycle_one_shot,
            record_requested=record_fresh_cycle_one_shot,
            confirmation_valid=confirmation_valid,
            validation=validation,
            recorded=False,
        )

        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "run_fresh_cycle_one_shot_requested": bool(run_fresh_cycle_one_shot),
                "record_fresh_cycle_one_shot_requested": bool(record_fresh_cycle_one_shot),
                "confirmation_valid": bool(confirmation_valid),
                "fresh_cycle_one_shot_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "fresh_cycle_one_shot_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "one_shot_step_plan": step_plan,
                "one_shot_step_results": step_results,
                "one_shot_output_validation": validation,
                "one_shot_go_no_go_packet": go_no_go,
                "one_shot_operator_packet": operator_packet,
                "one_shot_checkpoint_matrix": checkpoint_matrix,
                "fresh_cycle_one_shot_overall_status": overall,
                "recommended_next_operator_move": _recommended_next_operator_move(go_no_go),
                "recommended_next_engineering_move": _recommended_next_engineering_move(go_no_go),
                "do_not_run_yet": [
                    "real submit from R260",
                    "real submit before live-control review",
                    "real submit before R255 dry preview",
                    "duplicate live submit",
                ],
                "safety": safety,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if record_fresh_cycle_one_shot and confirmation_valid:
            payload["status"] = _top_level_status(
                run_requested=run_fresh_cycle_one_shot,
                record_requested=record_fresh_cycle_one_shot,
                confirmation_valid=confirmation_valid,
                validation=validation,
                recorded=True,
            )
            payload["fresh_cycle_one_shot_recorded"] = True
            payload["fresh_cycle_one_shot_overall_status"] = classify_tiny_live_fresh_cycle_one_shot_status(
                run_requested=run_fresh_cycle_one_shot,
                record_requested=record_fresh_cycle_one_shot,
                confirmation_valid=confirmation_valid,
                validation=validation,
                step_results=step_results,
                recorded=True,
            )
            payload = append_tiny_live_fresh_cycle_one_shot_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_fresh_cycle_one_shot=confirm_tiny_live_fresh_cycle_one_shot,
            )
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": TINY_LIVE_FRESH_CYCLE_ONE_SHOT_ERROR,
                "generated_at": generated_at.isoformat(),
                "run_fresh_cycle_one_shot_requested": bool(run_fresh_cycle_one_shot),
                "record_fresh_cycle_one_shot_requested": bool(record_fresh_cycle_one_shot),
                "confirmation_valid": bool(confirmation_valid),
                "fresh_cycle_one_shot_recorded": False,
                "error": exc.__class__.__name__,
                "fresh_cycle_one_shot_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "safety": safety,
            }
        )


def load_latest_tiny_live_fresh_cycle_checkpoint(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_fresh_cycle_checkpoint_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def run_or_preview_r253_readonly_refresh_step(
    *, log_dir: str | Path | None = None, run_step: bool = False, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    if not run_step:
        return _step_result(attempted=False)
    payload = build_tiny_live_final_readonly_mark_price_refresh_gate(
        log_dir=log_dir,
        fetch_final_readonly_market=True,
        confirm_tiny_live_final_readonly_refresh=CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE,
        official_lane_key=official_lane_key,
    )
    succeeded = payload.get("final_readonly_market_fetched") is True
    fresh = payload.get("fresh_market_context_summary")
    fresh = fresh if isinstance(fresh, Mapping) else {}
    return _step_result(
        attempted=True,
        succeeded=succeeded,
        fresh_mark_price=fresh.get("mark_price"),
        blocked_by=_blocked_by_from_payload(payload, "final_readonly_refresh_gate_matrix"),
        payload=payload,
    )


def run_or_preview_r253b_regeneration_step(
    *, log_dir: str | Path | None = None, run_step: bool = False, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    if not run_step:
        return _step_result(attempted=False, signed_requests_count=None)
    payload = build_tiny_live_fresh_context_signed_request_regeneration_gate(
        log_dir=log_dir,
        regenerate_fresh_context_signed_request=True,
        confirm_tiny_live_fresh_context_regeneration=CONFIRM_TINY_LIVE_FRESH_CONTEXT_REGENERATION_PHRASE,
        official_lane_key=official_lane_key,
    )
    signed_summary = payload.get("fresh_signed_request_artifact_summary")
    signed_summary = signed_summary if isinstance(signed_summary, Mapping) else {}
    succeeded = payload.get("fresh_context_regeneration_written") is True
    return _step_result(
        attempted=True,
        succeeded=succeeded,
        signed_requests_count=signed_summary.get("signed_requests_count"),
        blocked_by=_blocked_by_from_payload(payload, "fresh_regeneration_gate_matrix"),
        payload=payload,
    )


def run_or_preview_r254_submit_gate_preview_step(
    *, log_dir: str | Path | None = None, run_step: bool = False, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    if not run_step:
        return _step_result(attempted=False)
    payload = build_tiny_live_submit_gate_preview(
        log_dir=log_dir,
        record_submit_gate_preview=True,
        confirm_tiny_live_submit_gate_preview=CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE,
        official_lane_key=official_lane_key,
    )
    return _step_result(
        attempted=True,
        succeeded=payload.get("submit_gate_preview_recorded") is True,
        blocked_by=_blocked_by_from_payload(payload, "submit_gate_preview_matrix"),
        payload=payload,
    )


def run_or_preview_r255_dry_preview_step(
    *, log_dir: str | Path | None = None, run_step: bool = False, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    if not run_step:
        return _step_result(attempted=False)
    payload = build_tiny_live_actual_submit_gate(
        log_dir=log_dir,
        dry_run_actual_submit_gate=True,
        record_actual_submit_gate_preview=True,
        confirm_tiny_live_actual_submit_gate_preview=DRY_PREVIEW_CONFIRMATION_PHRASE,
        execute_actual_submit=False,
        allow_real_binance_order_endpoint=False,
        official_lane_key=official_lane_key,
    )
    return _step_result(
        attempted=True,
        succeeded=payload.get("status") == "TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED",
        blocked_by=_blocked_by_from_payload(payload, "actual_submit_gate_matrix"),
        payload=payload,
    )


def run_or_preview_r258_manual_checkpoint_recheck_step(
    *, log_dir: str | Path | None = None, run_step: bool = False, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    if not run_step:
        return _step_result(attempted=False)
    payload = build_tiny_live_manual_submit_checkpoint(
        log_dir=log_dir,
        record_manual_submit_checkpoint=True,
        confirm_tiny_live_manual_submit_checkpoint=CONFIRM_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_PHRASE,
        official_lane_key=official_lane_key,
    )
    return _step_result(
        attempted=True,
        succeeded=payload.get("manual_submit_checkpoint_recorded") is True,
        blocked_by=_blocked_by_from_payload(payload, "manual_submit_checkpoint_matrix"),
        payload=payload,
    )


def build_one_shot_step_plan(*, run_requested: bool = False, confirmation_valid: bool = False) -> dict[str, Any]:
    active = bool(run_requested and confirmation_valid)
    return {
        "steps": list(STEP_NAMES),
        "will_call_public_readonly_binance": active,
        "will_sign_locally": active,
        "will_submit": False,
        "will_place_order": False,
        "requires_confirmation": True,
    }


def build_one_shot_step_results() -> dict[str, Any]:
    return {
        "r253_readonly_refresh": _step_result(attempted=False, fresh_mark_price=None),
        "r253b_regeneration": _step_result(attempted=False, signed_requests_count=None),
        "r254_submit_gate_preview": _step_result(attempted=False),
        "r255_dry_preview": _step_result(attempted=False),
        "r258_manual_checkpoint_recheck": _step_result(attempted=False),
    }


def validate_one_shot_outputs(*, step_results: Mapping[str, Any]) -> dict[str, Any]:
    r253 = _step(step_results, "r253_readonly_refresh")
    r253b = _step(step_results, "r253b_regeneration")
    r254 = _step(step_results, "r254_submit_gate_preview")
    r255 = _step(step_results, "r255_dry_preview")
    r258 = _step(step_results, "r258_manual_checkpoint_recheck")
    errors: list[str] = []
    for key, result in (
        ("r253_readonly_refresh", r253),
        ("r253b_regeneration", r253b),
        ("r254_submit_gate_preview", r254),
        ("r255_dry_preview", r255),
        ("r258_manual_checkpoint_recheck", r258),
    ):
        if result.get("attempted") and result.get("succeeded") is not True:
            errors.append(f"{key}_failed")
    all_attempted = all(_step(step_results, key).get("attempted") is True for key in step_results)
    all_succeeded = all(_step(step_results, key).get("succeeded") is True for key in step_results)
    if any(_step(step_results, key).get("attempted") for key in step_results) and not all_succeeded:
        errors.append("one_shot_sequence_incomplete")
    return {
        "valid": bool(all_attempted and all_succeeded and not errors),
        "fresh_signed_request_available": r253b.get("succeeded") is True,
        "signed_request_fresh_enough_for_dry_preview": r255.get("succeeded") is True,
        "submit_gate_preview_recorded": r254.get("succeeded") is True,
        "dry_preview_recorded": r255.get("succeeded") is True,
        "manual_checkpoint_rechecked": r258.get("succeeded") is True,
        "errors": _dedupe(errors),
        "warnings": [],
    }


def build_one_shot_go_no_go_packet(
    *, validation: Mapping[str, Any], checkpoint_matrix: Mapping[str, Any]
) -> dict[str, Any]:
    valid = validation.get("valid") is True
    blocked = checkpoint_matrix.get("blocked_by") if isinstance(checkpoint_matrix.get("blocked_by"), list) else []
    return {
        "go_for_manual_submit_now": False,
        "go_for_live_control_review": bool(valid),
        "go_for_r260_to_r261_ui": bool(valid),
        "next_required_step": _next_required_step(valid=valid, blocked_by=blocked),
        "operator_should_submit_now": False,
        "operator_should_arm_live_controls_manually": bool(valid),
    }


def build_one_shot_operator_packet(*, go_no_go_packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "operator_should_review_fresh_cycle_result": True,
        "operator_should_not_submit_from_r260": True,
        "operator_should_run_live_control_review_next": go_no_go_packet.get("go_for_live_control_review") is True,
        "operator_should_open_ui_when_available": go_no_go_packet.get("go_for_r260_to_r261_ui") is True,
        "manual_decision_required": True,
    }


def build_one_shot_safety_summary(
    *, r253_ran: bool = False, r253b_ran: bool = False, r253b_written: bool = False
) -> dict[str, Any]:
    return {
        **SAFETY_FALSE,
        "env_written": False,
        "env_mutated": False,
        "external_env_file_written": False,
        "config_written": False,
        "risk_contract_config_written": False,
        "lane_controls_written": False,
        "live_config_written": False,
        "fresh_cycle_one_shot_only": True,
        "hmac_signature_created": bool(r253b_written),
        "signed_request_written": bool(r253b_written),
        "signed_order_request_created": bool(r253b_written),
        "signed_trading_request_created": bool(r253b_written),
        "submit_allowed": False,
        "submit_attempted": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
        "binance_account_endpoint_called": False,
        "binance_exchange_info_endpoint_called": bool(r253_ran),
        "binance_mark_price_endpoint_called": bool(r253_ran),
        "private_binance_endpoint_called": False,
        "signed_binance_endpoint_called": False,
        "network_allowed": bool(r253_ran),
        "transfer_endpoint_called": False,
        "withdraw_endpoint_called": False,
        "kill_switch_disabled": False,
        "live_controls_armed_by_phase": False,
        "secrets_shown": False,
        "secrets_persisted": False,
        "secret_values_in_output": False,
        "global_live_flags_changed": False,
        "paper_live_separation_intact": True,
        "official_tiny_live_lane_changed": False,
        "r253b_regeneration_attempted": bool(r253b_ran),
    }


def classify_tiny_live_fresh_cycle_one_shot_status(
    *,
    run_requested: bool,
    record_requested: bool,
    confirmation_valid: bool,
    validation: Mapping[str, Any],
    step_results: Mapping[str, Any],
    recorded: bool,
) -> str:
    if (run_requested or record_requested) and not confirmation_valid:
        return TINY_LIVE_FRESH_CYCLE_ONE_SHOT_REJECTED_BAD_CONFIRMATION
    if not run_requested:
        return TINY_LIVE_FRESH_CYCLE_ONE_SHOT_READY_FOR_CONFIRMATION
    blocker = _first_blocked_step(step_results)
    if blocker:
        return blocker
    if recorded and validation.get("valid") is True:
        return TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED_READY_FOR_LIVE_CONTROL_REVIEW
    if recorded:
        return TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED_STILL_BLOCKED
    if validation.get("valid") is True:
        return TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED_READY_FOR_LIVE_CONTROL_REVIEW
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_fresh_cycle_one_shot_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_fresh_cycle_one_shot: str | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_fresh_cycle_one_shot != CONFIRM_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_PHRASE:
        raise ValueError("bad_tiny_live_fresh_cycle_one_shot_confirmation")
    path = tiny_live_fresh_cycle_one_shot_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "fresh_cycle_one_shot_record_id": record.get("fresh_cycle_one_shot_record_id")
            or f"r260_fresh_cycle_one_shot_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "fresh_cycle_one_shot_recorded": True,
            "created_by_phase": CREATED_BY_PHASE,
            "safety": dict(record.get("safety") or build_one_shot_safety_summary()),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_fresh_cycle_one_shot_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_fresh_cycle_one_shot_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_fresh_cycle_one_shot_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    packet = latest.get("one_shot_go_no_go_packet") if isinstance(latest.get("one_shot_go_no_go_packet"), Mapping) else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_recorded": latest.get("fresh_cycle_one_shot_recorded") is True,
        "latest_overall_status": latest.get("fresh_cycle_one_shot_overall_status"),
        "latest_next_required_step": packet.get("next_required_step"),
    }


def tiny_live_fresh_cycle_one_shot_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_fresh_cycle_one_shot_orchestrator_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def build_one_shot_checkpoint_matrix(
    *,
    input_summary: Mapping[str, Any],
    step_results: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    blocked_by = _blocked_by_from_step_results(step_results)
    return {
        "r259_available": input_summary.get("r259_fresh_cycle_checkpoint_found") is True,
        "fresh_cycle_required": input_summary.get("fresh_cycle_required") is True,
        "r253_succeeded": _step(step_results, "r253_readonly_refresh").get("succeeded") is True,
        "r253b_succeeded": _step(step_results, "r253b_regeneration").get("succeeded") is True,
        "r254_succeeded": _step(step_results, "r254_submit_gate_preview").get("succeeded") is True,
        "r255_dry_preview_succeeded": _step(step_results, "r255_dry_preview").get("succeeded") is True,
        "r258_recheck_succeeded": _step(step_results, "r258_manual_checkpoint_recheck").get("succeeded") is True,
        "submit_allowed": False,
        "order_placed": False,
        "blocked_by": _dedupe([*blocked_by, *list(validation.get("errors") or [])]),
    }


def _top_level_status(
    *,
    run_requested: bool,
    record_requested: bool,
    confirmation_valid: bool,
    validation: Mapping[str, Any],
    recorded: bool,
) -> str:
    if (run_requested or record_requested) and not confirmation_valid:
        return TINY_LIVE_FRESH_CYCLE_ONE_SHOT_REJECTED
    if recorded:
        return TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED
    if run_requested and validation.get("valid") is not True:
        return TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED
    return TINY_LIVE_FRESH_CYCLE_ONE_SHOT_READY


def _first_blocked_step(step_results: Mapping[str, Any]) -> str | None:
    mapping = (
        ("r253_readonly_refresh", TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R253),
        ("r253b_regeneration", TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R253B),
        ("r254_submit_gate_preview", TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R254),
        ("r255_dry_preview", TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R255),
        ("r258_manual_checkpoint_recheck", TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R258),
    )
    for key, status in mapping:
        result = _step(step_results, key)
        if result.get("attempted") is True and result.get("succeeded") is not True:
            return status
    return None


def _next_required_step(*, valid: bool, blocked_by: Sequence[str]) -> str:
    if valid:
        return "LIVE_CONTROL_REVIEW"
    joined = " ".join(blocked_by)
    if "r253" in joined or not blocked_by:
        return "R253_REFRESH_AGAIN"
    if "r253b" in joined or "credential" in joined or "signed" in joined:
        return "FIX_BLOCKER"
    return "FIX_BLOCKER"


def _recommended_next_operator_move(packet: Mapping[str, Any]) -> str:
    step = str(packet.get("next_required_step") or "WAIT")
    if step == "LIVE_CONTROL_REVIEW":
        return "Review R260 fresh-cycle result, then perform live-control review outside R260."
    if step == "R253_REFRESH_AGAIN":
        return "Fix the R253 public read-only refresh blocker and rerun R260 with exact confirmation."
    return "Fix the reported one-shot blocker before any manual submit."


def _recommended_next_engineering_move(packet: Mapping[str, Any]) -> str:
    step = str(packet.get("next_required_step") or "WAIT")
    if step == "LIVE_CONTROL_REVIEW":
        return "Build R261 live-control arming UI/API review surface; do not submit from R260."
    return "Inspect the blocked child gate output and rerun the one-shot after correction."


def _r259_valid(record: Mapping[str, Any]) -> bool:
    return bool(
        record
        and record.get("fresh_cycle_checkpoint_recorded") is True
        and record.get("target_scope", {}).get("official_lane_key") == OFFICIAL_LANE_KEY
    )


def _fresh_cycle_required(record: Mapping[str, Any]) -> bool:
    packet = record.get("fresh_cycle_go_no_go_packet") if isinstance(record.get("fresh_cycle_go_no_go_packet"), Mapping) else {}
    return packet.get("next_required_step") in {
        "RUN_R253_READONLY_REFRESH",
        "RUN_R253B_REGENERATION",
        "RUN_R254_PREVIEW",
        "RUN_R255_DRY_PREVIEW",
    } or bool(record)


def _blocked_by_from_payload(payload: Mapping[str, Any], matrix_key: str) -> list[str]:
    matrix = payload.get(matrix_key) if isinstance(payload.get(matrix_key), Mapping) else {}
    blocked = matrix.get("blocked_by")
    if isinstance(blocked, list):
        return _dedupe(str(item) for item in blocked)
    for key in ("errors", "blocking_reasons"):
        values = payload.get(key)
        if isinstance(values, list):
            return _dedupe(str(item) for item in values)
    status = str(payload.get("status") or "")
    if "BLOCKED" in status or "ERROR" in status or "REJECTED" in status:
        return [status.lower()]
    return []


def _blocked_by_from_step_results(step_results: Mapping[str, Any]) -> list[str]:
    blocked: list[str] = []
    for key, result in step_results.items():
        step = result if isinstance(result, Mapping) else {}
        if step.get("attempted") is True and step.get("succeeded") is not True:
            blocked.append(f"{key}_failed")
        blocked.extend(str(item) for item in step.get("blocked_by") or [])
    return _dedupe(blocked)


def _step_result(
    *,
    attempted: bool,
    succeeded: bool = False,
    fresh_mark_price: Any | None = None,
    signed_requests_count: int | None = None,
    blocked_by: Sequence[str] | None = None,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(attempted),
        "succeeded": bool(succeeded),
        "blocked_by": _dedupe(blocked_by or []),
    }
    if fresh_mark_price is not ...:
        result["fresh_mark_price"] = fresh_mark_price
    if signed_requests_count is not ...:
        result["signed_requests_count"] = signed_requests_count
    if payload is not None:
        result["status"] = payload.get("status")
        result["overall_status"] = (
            payload.get("final_readonly_refresh_overall_status")
            or payload.get("fresh_context_regeneration_overall_status")
            or payload.get("submit_gate_preview_overall_status")
            or payload.get("actual_submit_gate_overall_status")
            or payload.get("manual_submit_checkpoint_overall_status")
        )
    return _sanitize(result)


def _step(step_results: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = step_results.get(key)
    return value if isinstance(value, Mapping) else {}


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    scope = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    return scope.get("official_lane_key") == official_lane_key


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key).split("|")
    while len(parts) < 4:
        parts.append("")
    return parts[0], parts[1], parts[2], parts[3]


def _dedupe(values: Sequence[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in out:
            out.append(text)
    return out


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _sanitize(v) for k, v in value.items() if _safe_key(str(k))}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value


def _safe_key(key: str) -> bool:
    if key in {"secret_values_in_output", "secrets_shown", "secrets_persisted"}:
        return True
    lowered = key.lower()
    return not any(fragment in lowered for fragment in ("api_key", "api_secret", "secret_value"))
