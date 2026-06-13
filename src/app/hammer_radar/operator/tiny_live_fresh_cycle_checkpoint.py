"""R259 tiny-live fresh-cycle checkpoint.

This module coordinates the required fresh cycle after R258. It only reads
local ledgers/configs and can append its own checkpoint ledger after the exact
R259 confirmation phrase. It never runs the fresh-cycle commands, calls
Binance/network, signs requests, regenerates artifacts, arms live controls,
submits, or places orders.
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
    load_tiny_live_actual_submit_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_final_pre_submit_arming_drill import (
    load_tiny_live_final_pre_submit_arming_drill_records,
)
from src.app.hammer_radar.operator.tiny_live_final_readonly_mark_price_refresh_gate import (
    load_tiny_live_final_readonly_mark_price_refresh_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_fresh_context_signed_request_regeneration_gate import (
    load_tiny_live_fresh_context_signed_request_regeneration_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_manual_submit_checkpoint import (
    load_tiny_live_manual_submit_checkpoint_records,
)
from src.app.hammer_radar.operator.tiny_live_operator_real_submit_runbook import (
    load_tiny_live_operator_real_submit_runbook_records,
)
from src.app.hammer_radar.operator.tiny_live_submit_gate_preview import (
    load_tiny_live_submit_gate_preview_records,
)

TINY_LIVE_FRESH_CYCLE_CHECKPOINT_READY = "TINY_LIVE_FRESH_CYCLE_CHECKPOINT_READY"
TINY_LIVE_FRESH_CYCLE_CHECKPOINT_RECORDED = (
    "TINY_LIVE_FRESH_CYCLE_CHECKPOINT_RECORDED"
)
TINY_LIVE_FRESH_CYCLE_CHECKPOINT_REJECTED = (
    "TINY_LIVE_FRESH_CYCLE_CHECKPOINT_REJECTED"
)
TINY_LIVE_FRESH_CYCLE_CHECKPOINT_BLOCKED = "TINY_LIVE_FRESH_CYCLE_CHECKPOINT_BLOCKED"
TINY_LIVE_FRESH_CYCLE_CHECKPOINT_ERROR = "TINY_LIVE_FRESH_CYCLE_CHECKPOINT_ERROR"

TINY_LIVE_FRESH_CYCLE_READY_FOR_RECORDING = (
    "TINY_LIVE_FRESH_CYCLE_READY_FOR_RECORDING"
)
TINY_LIVE_FRESH_CYCLE_RECORDED_REFRESH_REQUIRED = (
    "TINY_LIVE_FRESH_CYCLE_RECORDED_REFRESH_REQUIRED"
)
TINY_LIVE_FRESH_CYCLE_RECORDED_REGENERATION_REQUIRED = (
    "TINY_LIVE_FRESH_CYCLE_RECORDED_REGENERATION_REQUIRED"
)
TINY_LIVE_FRESH_CYCLE_RECORDED_DRY_PREVIEW_REQUIRED = (
    "TINY_LIVE_FRESH_CYCLE_RECORDED_DRY_PREVIEW_REQUIRED"
)
TINY_LIVE_FRESH_CYCLE_RECORDED_MANUAL_DECISION_REQUIRED = (
    "TINY_LIVE_FRESH_CYCLE_RECORDED_MANUAL_DECISION_REQUIRED"
)
TINY_LIVE_FRESH_CYCLE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_FRESH_CYCLE_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_FRESH_CYCLE_BLOCKED_BY_MISSING_R258 = (
    "TINY_LIVE_FRESH_CYCLE_BLOCKED_BY_MISSING_R258"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_FRESH_CYCLE_CHECKPOINT"
LEDGER_FILENAME = "tiny_live_fresh_cycle_checkpoint.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R259_TINY_LIVE_FRESH_CYCLE_CHECKPOINT"
CONFIRM_TINY_LIVE_FRESH_CYCLE_CHECKPOINT_PHRASE = (
    "I CONFIRM TINY LIVE FRESH CYCLE CHECKPOINT RECORDING ONLY; "
    "NO SUBMIT; NO ORDER; NO BINANCE CALL."
)
RISK_CONTRACT_CONFIG_PATH = Path("configs/hammer_radar/tiny_live_risk_contracts.json")
LANE_CONTROLS_PATH = Path("configs/hammer_radar/lane_controls.json")

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_manual_submit_checkpoint.ndjson",
    "logs/hammer_radar_forward/tiny_live_final_pre_submit_arming_drill.ndjson",
    "logs/hammer_radar_forward/tiny_live_operator_real_submit_runbook.ndjson",
    "logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson",
    "logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_final_readonly_mark_price_refresh_gate.ndjson",
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
    "fresh_cycle_checkpoint_only": True,
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


def build_tiny_live_fresh_cycle_checkpoint(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    record_fresh_cycle_checkpoint: bool = False,
    confirm_tiny_live_fresh_cycle_checkpoint: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_fresh_cycle_checkpoint
        == CONFIRM_TINY_LIVE_FRESH_CYCLE_CHECKPOINT_PHRASE
    )
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    risk_path = Path(risk_contract_config_path or RISK_CONTRACT_CONFIG_PATH)
    lane_path = Path(lane_controls_path or LANE_CONTROLS_PATH)

    try:
        latest_r258 = load_latest_tiny_live_manual_submit_checkpoint(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
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
        latest_r253 = load_latest_tiny_live_final_readonly_mark_price_refresh_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        input_summary = summarize_fresh_cycle_inputs(
            latest_r258=latest_r258,
            latest_r257=latest_r257,
            latest_r256=latest_r256,
            latest_r255=latest_r255,
            latest_r254=latest_r254,
            latest_r253b=latest_r253b,
            latest_r253=latest_r253,
        )
        control_summary = _read_control_summary(
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            official_lane_key=official_lane_key,
        )
        blockers = summarize_fresh_cycle_blockers(
            latest_r258=latest_r258,
            latest_r257=latest_r257,
            latest_r255=latest_r255,
            control_summary=control_summary,
        )
        step_statuses = summarize_fresh_cycle_step_statuses(
            latest_r258=latest_r258,
            latest_r253=latest_r253,
            latest_r253b=latest_r253b,
            latest_r254=latest_r254,
            latest_r255=latest_r255,
            blockers=blockers,
        )
        commands = build_fresh_cycle_command_templates()
        packet = build_fresh_cycle_go_no_go_packet(
            input_summary=input_summary,
            fresh_cycle_step_statuses=step_statuses,
            fresh_cycle_blockers=blockers,
        )
        matrix = build_fresh_cycle_checkpoint_matrix(
            input_summary=input_summary,
            fresh_cycle_step_statuses=step_statuses,
            fresh_cycle_blockers=blockers,
            record_confirmed=confirmation_valid,
            recorded=False,
        )
        status = classify_tiny_live_fresh_cycle_checkpoint_status(
            input_summary=input_summary,
            record_requested=record_fresh_cycle_checkpoint,
            confirmation_valid=confirmation_valid,
            recorded=False,
        )
        overall = _overall_status(
            input_summary=input_summary,
            packet=packet,
            record_requested=record_fresh_cycle_checkpoint,
            confirmation_valid=confirmation_valid,
            recorded=False,
        )
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "record_fresh_cycle_checkpoint_requested": bool(
                    record_fresh_cycle_checkpoint
                ),
                "confirmation_valid": bool(confirmation_valid),
                "fresh_cycle_checkpoint_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "fresh_cycle_checkpoint_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "fresh_cycle_step_statuses": step_statuses,
                "fresh_cycle_blockers": blockers,
                "fresh_cycle_command_templates": commands,
                "fresh_cycle_go_no_go_packet": packet,
                "fresh_cycle_checkpoint_matrix": matrix,
                "fresh_cycle_checkpoint_overall_status": overall,
                "recommended_next_operator_move": _recommended_next_operator_move(packet),
                "recommended_next_engineering_move": _recommended_next_engineering_move(
                    input_summary,
                    packet,
                ),
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if record_fresh_cycle_checkpoint and confirmation_valid:
            payload["status"] = TINY_LIVE_FRESH_CYCLE_CHECKPOINT_RECORDED
            payload["fresh_cycle_checkpoint_recorded"] = True
            payload["fresh_cycle_checkpoint_matrix"]["record_confirmed"] = True
            payload["fresh_cycle_checkpoint_matrix"]["recorded"] = True
            payload["fresh_cycle_checkpoint_overall_status"] = _overall_status(
                input_summary=input_summary,
                packet=packet,
                record_requested=record_fresh_cycle_checkpoint,
                confirmation_valid=confirmation_valid,
                recorded=True,
            )
            payload = append_tiny_live_fresh_cycle_checkpoint_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_fresh_cycle_checkpoint=(
                    confirm_tiny_live_fresh_cycle_checkpoint
                ),
            )
        return payload
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        return _sanitize(
            {
                "status": TINY_LIVE_FRESH_CYCLE_CHECKPOINT_ERROR,
                "generated_at": generated_at.isoformat(),
                "record_fresh_cycle_checkpoint_requested": bool(
                    record_fresh_cycle_checkpoint
                ),
                "confirmation_valid": bool(confirmation_valid),
                "fresh_cycle_checkpoint_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "fresh_cycle_checkpoint_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "error": type(exc).__name__,
                "fresh_cycle_checkpoint_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "safety": dict(SAFETY),
            }
        )


def load_latest_tiny_live_manual_submit_checkpoint(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_manual_submit_checkpoint_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


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
    for record in load_tiny_live_operator_real_submit_runbook_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_actual_submit_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_actual_submit_gate_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_submit_gate_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_submit_gate_preview_records(log_dir=log_dir, limit=50):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_fresh_context_signed_request_regeneration_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_fresh_context_signed_request_regeneration_gate_records(
        log_dir=log_dir,
        limit=50,
    ):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_final_readonly_mark_price_refresh_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_final_readonly_mark_price_refresh_gate_records(
        log_dir=log_dir,
        limit=50,
    ):
        if _record_matches_lane(record, official_lane_key):
            return _sanitize(record)
    return {}


def summarize_fresh_cycle_inputs(
    *,
    latest_r258: Mapping[str, Any] | None = None,
    latest_r257: Mapping[str, Any] | None = None,
    latest_r256: Mapping[str, Any] | None = None,
    latest_r255: Mapping[str, Any] | None = None,
    latest_r254: Mapping[str, Any] | None = None,
    latest_r253b: Mapping[str, Any] | None = None,
    latest_r253: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "r258_manual_checkpoint_found": bool(latest_r258),
        "r258_manual_checkpoint_valid": _r258_valid(latest_r258 or {}),
        "r257_final_arming_found": bool(latest_r257),
        "r256_runbook_found": bool(latest_r256),
        "r255_actual_submit_gate_found": bool(latest_r255),
        "r254_submit_gate_preview_found": bool(latest_r254),
        "r253b_fresh_regeneration_found": bool(latest_r253b),
        "r253_final_readonly_found": bool(latest_r253),
    }


def summarize_fresh_cycle_step_statuses(
    *,
    latest_r258: Mapping[str, Any] | None = None,
    latest_r253: Mapping[str, Any] | None = None,
    latest_r253b: Mapping[str, Any] | None = None,
    latest_r254: Mapping[str, Any] | None = None,
    latest_r255: Mapping[str, Any] | None = None,
    blockers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    r258_time = _record_time(latest_r258 or {})
    timestamp_stale = bool((blockers or {}).get("timestamp_stale") is True)

    r253_fresh = bool(latest_r253) and _record_is_after(latest_r253 or {}, r258_time)
    r253b_fresh = bool(latest_r253b) and _record_is_after(latest_r253b or {}, r258_time)
    r254_fresh = bool(latest_r254) and _record_is_after(latest_r254 or {}, r258_time)
    r255_fresh = bool(latest_r255) and _record_is_after(latest_r255 or {}, r258_time)

    r253_required = not r253_fresh or timestamp_stale
    r253b_required = not r253_required and not r253b_fresh
    r254_required = not r253_required and not r253b_required and not r254_fresh
    r255_required = (
        not r253_required
        and not r253b_required
        and not r254_required
        and not r255_fresh
    )
    return {
        "r253_final_readonly_refresh": {
            "available": bool(latest_r253),
            "fresh_enough": bool(r253_fresh and not timestamp_stale),
            "required_next": bool(r253_required),
        },
        "r253b_fresh_signed_regeneration": {
            "available": bool(latest_r253b),
            "fresh_enough": bool(r253b_fresh and not timestamp_stale),
            "required_next": bool(r253b_required),
        },
        "r254_submit_gate_preview": {
            "available": bool(latest_r254),
            "fresh_enough": bool(r254_fresh and not timestamp_stale),
            "required_next": bool(r254_required),
        },
        "r255_actual_submit_gate_dry_preview": {
            "available": bool(latest_r255),
            "fresh_enough": bool(r255_fresh and not timestamp_stale),
            "required_next": bool(r255_required),
        },
        "r258_manual_checkpoint_recheck": {
            "available": bool(latest_r258),
            "required_after_fresh_cycle": True,
        },
    }


def summarize_fresh_cycle_blockers(
    *,
    latest_r258: Mapping[str, Any] | None = None,
    latest_r257: Mapping[str, Any] | None = None,
    latest_r255: Mapping[str, Any] | None = None,
    control_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manual = (
        latest_r258.get("manual_submit_blocker_summary")
        if isinstance((latest_r258 or {}).get("manual_submit_blocker_summary"), Mapping)
        else {}
    )
    r257 = (
        latest_r257.get("pre_submit_blocker_summary")
        if isinstance((latest_r257 or {}).get("pre_submit_blocker_summary"), Mapping)
        else {}
    )
    r255_matrix = (
        latest_r255.get("actual_submit_gate_matrix")
        if isinstance((latest_r255 or {}).get("actual_submit_gate_matrix"), Mapping)
        else {}
    )
    blocked_by = _dedupe(
        [
            *(manual.get("blocked_by") or []),
            *(r257.get("blocked_by") or []),
            *(r255_matrix.get("blocked_by") or []),
            *((control_summary or {}).get("blocked_by") or []),
        ]
    )
    timestamp_stale = bool(
        "signed_request_timestamp_stale" in blocked_by
        or manual.get("fresh_cycle_required") is True
        or manual.get("operator_should_not_submit_now") is True
        and manual.get("fresh_cycle_required") is True
    )
    live_controls_not_armed = bool(
        manual.get("live_controls_manual_review_required") is True
        or (control_summary or {}).get("official_lane_allowed") is not True
        or (control_summary or {}).get("live_execution_enabled") is not True
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
        "blocked_by": blocked_by,
        "timestamp_stale": timestamp_stale,
        "live_controls_not_armed": live_controls_not_armed,
        "live_execution_not_enabled": bool(
            "live_execution_not_enabled" in blocked_by
            or (control_summary or {}).get("live_execution_enabled") is not True
        ),
        "manual_decision_required": True,
        "submit_allowed_now": False,
    }


def build_fresh_cycle_command_templates() -> dict[str, Any]:
    return {
        "r253_readonly_refresh_command": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward "
            "tiny-live-final-readonly-mark-price-refresh-gate "
            "--fetch-final-readonly-market "
            "--confirm-tiny-live-final-readonly-refresh "
            "\"I CONFIRM TINY LIVE FINAL READONLY MARK PRICE REFRESH ONLY; "
            "NO SUBMIT; NO ORDER; NO PRIVATE BINANCE CALL.\""
        ),
        "r253b_regeneration_command": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward "
            "tiny-live-fresh-context-signed-request-regeneration-gate "
            "--regenerate-fresh-context-signed-request "
            "--confirm-tiny-live-fresh-context-regeneration "
            "\"I CONFIRM TINY LIVE FRESH CONTEXT SIGNED REQUEST REGENERATION ONLY; "
            "NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL.\""
        ),
        "r254_submit_gate_preview_command": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward tiny-live-submit-gate-preview "
            "--record-submit-gate-preview "
            "--confirm-tiny-live-submit-gate-preview "
            "\"I CONFIRM TINY LIVE SUBMIT GATE PREVIEW RECORDING ONLY; "
            "NO SUBMIT; NO ORDER; NO BINANCE CALL.\""
        ),
        "r255_dry_preview_command": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward tiny-live-actual-submit-gate "
            "--dry-run-actual-submit-gate --record-actual-submit-gate-preview "
            "--confirm-tiny-live-actual-submit-gate-preview "
            "\"I CONFIRM TINY LIVE ACTUAL SUBMIT GATE DRY PREVIEW ONLY; "
            "NO SUBMIT; NO ORDER; NO BINANCE CALL.\""
        ),
        "r258_recheck_command": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward tiny-live-manual-submit-checkpoint "
            "--record-manual-submit-checkpoint "
            "--confirm-tiny-live-manual-submit-checkpoint "
            "\"I CONFIRM TINY LIVE MANUAL SUBMIT CHECKPOINT RECORDING ONLY; "
            "NO SUBMIT; NO ORDER; NO BINANCE CALL.\""
        ),
        "commands_are_templates_only": True,
        "must_not_auto_run": True,
    }


def build_fresh_cycle_go_no_go_packet(
    *,
    input_summary: Mapping[str, Any],
    fresh_cycle_step_statuses: Mapping[str, Any],
    fresh_cycle_blockers: Mapping[str, Any],
) -> dict[str, Any]:
    next_step = _next_required_step(input_summary, fresh_cycle_step_statuses)
    return {
        "go_for_manual_submit_now": False,
        "go_for_fresh_cycle_now": bool(next_step.startswith("RUN_R")),
        "next_required_step": next_step,
        "operator_should_submit_now": False,
        "operator_should_arm_live_controls_manually": (
            fresh_cycle_blockers.get("live_controls_not_armed") is True
        ),
        "operator_should_run_fresh_cycle": next_step.startswith("RUN_R"),
    }


def build_fresh_cycle_checkpoint_matrix(
    *,
    input_summary: Mapping[str, Any],
    fresh_cycle_step_statuses: Mapping[str, Any],
    fresh_cycle_blockers: Mapping[str, Any],
    record_confirmed: bool,
    recorded: bool,
) -> dict[str, Any]:
    packet_next = _next_required_step(input_summary, fresh_cycle_step_statuses)
    return {
        "r258_available": input_summary.get("r258_manual_checkpoint_found") is True,
        "fresh_cycle_required": bool(
            packet_next in {
                "RUN_R253_READONLY_REFRESH",
                "RUN_R253B_REGENERATION",
                "RUN_R254_PREVIEW",
                "RUN_R255_DRY_PREVIEW",
                "RUN_R258_RECHECK",
            }
        ),
        "fresh_cycle_next_step_known": packet_next != "WAIT",
        "command_templates_ready": True,
        "record_confirmed": bool(record_confirmed),
        "recorded": bool(recorded),
        "submit_allowed": False,
        "order_placed": False,
        "blocked_by": _dedupe(fresh_cycle_blockers.get("blocked_by") or []),
    }


def classify_tiny_live_fresh_cycle_checkpoint_status(
    *,
    input_summary: Mapping[str, Any],
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_FRESH_CYCLE_CHECKPOINT_REJECTED
    if recorded:
        return TINY_LIVE_FRESH_CYCLE_CHECKPOINT_RECORDED
    if input_summary.get("r258_manual_checkpoint_found") is not True:
        return TINY_LIVE_FRESH_CYCLE_CHECKPOINT_BLOCKED
    return TINY_LIVE_FRESH_CYCLE_CHECKPOINT_READY


def append_tiny_live_fresh_cycle_checkpoint_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_fresh_cycle_checkpoint: str | None = None,
) -> dict[str, Any]:
    if (
        confirm_tiny_live_fresh_cycle_checkpoint
        != CONFIRM_TINY_LIVE_FRESH_CYCLE_CHECKPOINT_PHRASE
    ):
        raise ValueError("bad_tiny_live_fresh_cycle_checkpoint_confirmation")
    path = tiny_live_fresh_cycle_checkpoint_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "fresh_cycle_checkpoint_record_id": (
                record.get("fresh_cycle_checkpoint_record_id")
                or f"r259_fresh_cycle_checkpoint_{uuid4().hex}"
            ),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "fresh_cycle_checkpoint_recorded": True,
            "created_by_phase": CREATED_BY_PHASE,
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_fresh_cycle_checkpoint_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_fresh_cycle_checkpoint_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_fresh_cycle_checkpoint_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    packet = (
        latest.get("fresh_cycle_go_no_go_packet")
        if isinstance(latest.get("fresh_cycle_go_no_go_packet"), Mapping)
        else {}
    )
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_recorded": latest.get("fresh_cycle_checkpoint_recorded") is True,
        "latest_overall_status": latest.get("fresh_cycle_checkpoint_overall_status"),
        "latest_next_required_step": packet.get("next_required_step"),
    }


def tiny_live_fresh_cycle_checkpoint_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_fresh_cycle_checkpoint_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _overall_status(
    *,
    input_summary: Mapping[str, Any],
    packet: Mapping[str, Any],
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_FRESH_CYCLE_REJECTED_BAD_CONFIRMATION
    if input_summary.get("r258_manual_checkpoint_found") is not True:
        return TINY_LIVE_FRESH_CYCLE_BLOCKED_BY_MISSING_R258
    if not recorded:
        return TINY_LIVE_FRESH_CYCLE_READY_FOR_RECORDING
    next_step = packet.get("next_required_step")
    if next_step == "RUN_R253_READONLY_REFRESH":
        return TINY_LIVE_FRESH_CYCLE_RECORDED_REFRESH_REQUIRED
    if next_step == "RUN_R253B_REGENERATION":
        return TINY_LIVE_FRESH_CYCLE_RECORDED_REGENERATION_REQUIRED
    if next_step in {"RUN_R254_PREVIEW", "RUN_R255_DRY_PREVIEW"}:
        return TINY_LIVE_FRESH_CYCLE_RECORDED_DRY_PREVIEW_REQUIRED
    return TINY_LIVE_FRESH_CYCLE_RECORDED_MANUAL_DECISION_REQUIRED


def _next_required_step(
    input_summary: Mapping[str, Any],
    statuses: Mapping[str, Any],
) -> str:
    if input_summary.get("r258_manual_checkpoint_found") is not True:
        return "FIX_BLOCKER"
    ordered = (
        ("r253_final_readonly_refresh", "RUN_R253_READONLY_REFRESH"),
        ("r253b_fresh_signed_regeneration", "RUN_R253B_REGENERATION"),
        ("r254_submit_gate_preview", "RUN_R254_PREVIEW"),
        ("r255_actual_submit_gate_dry_preview", "RUN_R255_DRY_PREVIEW"),
    )
    for key, action in ordered:
        step = statuses.get(key) if isinstance(statuses.get(key), Mapping) else {}
        if step.get("required_next") is True:
            return action
    return "RUN_R258_RECHECK"


def _recommended_next_operator_move(packet: Mapping[str, Any]) -> str:
    step = str(packet.get("next_required_step") or "FIX_BLOCKER")
    mapping = {
        "RUN_R253_READONLY_REFRESH": "Run R253 final readonly refresh first.",
        "RUN_R253B_REGENERATION": "Run R253B fresh signed request regeneration next.",
        "RUN_R254_PREVIEW": "Run R254 submit gate preview next.",
        "RUN_R255_DRY_PREVIEW": "Run R255 actual submit gate dry preview next.",
        "RUN_R258_RECHECK": "Re-run R258 manual submit checkpoint after the fresh cycle.",
        "FIX_BLOCKER": "Fix missing prerequisite checkpoint before continuing.",
        "WAIT": "Wait for operator review.",
    }
    return mapping.get(step, "Fix blocker before continuing.")


def _recommended_next_engineering_move(
    input_summary: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> str:
    if input_summary.get("r258_manual_checkpoint_found") is not True:
        return "Record R258 manual submit checkpoint before R259."
    if packet.get("next_required_step") == "RUN_R258_RECHECK":
        return "Create R260 manual live-submit execution checkpoint placeholder after fresh-cycle evidence is complete."
    return "Operator should run the next fresh-cycle command manually; do not submit or call Binance from R259."


def _do_not_run_yet() -> list[str]:
    return [
        "real submit before fresh cycle",
        "real submit before R255 dry preview",
        "real submit while live controls are not intentionally armed",
        "duplicate live submit",
        "manual submit while blockers remain",
    ]


def _r258_valid(record: Mapping[str, Any]) -> bool:
    if not record:
        return False
    safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
    packet = (
        record.get("manual_submit_go_no_go_packet")
        if isinstance(record.get("manual_submit_go_no_go_packet"), Mapping)
        else {}
    )
    return bool(
        record.get("manual_submit_checkpoint_recorded") is True
        and packet.get("go_for_manual_submit_now") is False
        and safety.get("submit_allowed") is False
        and safety.get("order_placed") is False
        and safety.get("real_order_placed") is False
        and safety.get("execution_attempted") is False
        and safety.get("secrets_shown") is False
    )


def _read_control_summary(
    *,
    risk_contract_config_path: Path,
    lane_controls_path: Path,
    official_lane_key: str,
) -> dict[str, Any]:
    lane = _matching_lane(_read_json(lane_controls_path), official_lane_key)
    contract = _matching_contract(_read_json(risk_contract_config_path), official_lane_key)
    official_lane_allowed = lane.get("mode") == "tiny_live"
    live_execution_enabled = contract.get("live_execution_enabled") is True
    blocked_by: list[str] = []
    if not official_lane_allowed:
        blocked_by.append("official_lane_not_tiny_live")
    if not live_execution_enabled:
        blocked_by.append("live_execution_not_enabled")
    return {
        "official_lane_allowed": official_lane_allowed,
        "live_execution_enabled": live_execution_enabled,
        "blocked_by": blocked_by,
    }


def _matching_lane(config: Mapping[str, Any], official_lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    lanes = config.get("lanes") if isinstance(config.get("lanes"), list) else []
    for lane in lanes:
        if not isinstance(lane, Mapping):
            continue
        if (
            lane.get("symbol") == symbol
            and lane.get("timeframe") == timeframe
            and lane.get("direction") == direction
            and lane.get("entry_mode") == entry_mode
        ):
            return dict(lane)
    return {}


def _matching_contract(config: Mapping[str, Any], official_lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    contracts = (
        config.get("risk_contracts")
        if isinstance(config.get("risk_contracts"), list)
        else []
    )
    for contract in contracts:
        if not isinstance(contract, Mapping):
            continue
        if contract.get("official_lane_key") == official_lane_key:
            return dict(contract)
        if (
            contract.get("symbol") == symbol
            and contract.get("timeframe") == timeframe
            and contract.get("direction") == direction
            and contract.get("entry_mode") == entry_mode
        ):
            return dict(contract)
    return {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _record_is_after(record: Mapping[str, Any], baseline: datetime | None) -> bool:
    record_time = _record_time(record)
    if record_time is None:
        return False
    if baseline is None:
        return True
    return record_time > baseline


def _record_time(record: Mapping[str, Any]) -> datetime | None:
    for key in ("recorded_at_utc", "generated_at"):
        value = record.get(key)
        if isinstance(value, str):
            parsed = _parse_datetime(value)
            if parsed is not None:
                return parsed
    return None


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    scope = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    if scope.get("official_lane_key") == official_lane_key:
        return True
    return record.get("official_lane_key") == official_lane_key


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
