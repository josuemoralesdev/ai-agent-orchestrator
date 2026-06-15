"""R264B tiny-live just-in-time launch packet.

This module orchestrates the existing R262B/R263/R264 safe gates into one
operator packet. It never executes the final live submit command and never
calls Binance order, test-order, account, private, or signed endpoints.
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
    LANE_CONTROLS_PATH,
    RISK_CONTRACT_CONFIG_PATH,
)
from src.app.hammer_radar.operator.tiny_live_actual_submit_reconciliation import (
    DRY_PREVIEW_CONFIRMATION_PHRASE as R264_DRY_PREVIEW_CONFIRMATION_PHRASE,
    LIVE_SUBMIT_CONFIRMATION_PHRASE,
    build_tiny_live_actual_submit_reconciliation,
)
from src.app.hammer_radar.operator.tiny_live_final_console import (
    FINAL_CONSOLE_CONTROLS_ARMING_CONFIRMATION_PHRASE,
    build_tiny_live_final_console,
)
from src.app.hammer_radar.operator.tiny_live_percentage_risk_contract_fit_regeneration import (
    CONTRACT_FIT_CONFIRMATION_PHRASE,
    build_tiny_live_percentage_risk_contract_fit_regeneration,
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R264B_TINY_LIVE_JIT_LAUNCH_PACKET"
EVENT_TYPE = "TINY_LIVE_JIT_LAUNCH_PACKET"
LEDGER_FILENAME = "tiny_live_jit_launch_packet.ndjson"

JIT_LAUNCH_PREP_CONFIRMATION_PHRASE = (
    "I CONFIRM TINY LIVE JIT LAUNCH PREP ONLY; REFRESH CONTRACT-FIT TRIPLET, "
    "ARM R263 EXPERIMENTAL LANE, RUN R264 DRY PREVIEW; NO SUBMIT; NO ORDER; "
    "NO BINANCE ORDER CALL."
)

TINY_LIVE_JIT_LAUNCH_PACKET_READY = "TINY_LIVE_JIT_LAUNCH_PACKET_READY"
TINY_LIVE_JIT_LAUNCH_PACKET_RECORDED = "TINY_LIVE_JIT_LAUNCH_PACKET_RECORDED"
TINY_LIVE_JIT_LAUNCH_PACKET_REJECTED = "TINY_LIVE_JIT_LAUNCH_PACKET_REJECTED"
TINY_LIVE_JIT_LAUNCH_PACKET_BLOCKED = "TINY_LIVE_JIT_LAUNCH_PACKET_BLOCKED"
TINY_LIVE_JIT_LAUNCH_PACKET_ERROR = "TINY_LIVE_JIT_LAUNCH_PACKET_ERROR"

TINY_LIVE_JIT_READY_FOR_CONFIRMATION = "TINY_LIVE_JIT_READY_FOR_CONFIRMATION"
TINY_LIVE_JIT_RECORDED_READY_FOR_MANUAL_LIVE_COMMAND = (
    "TINY_LIVE_JIT_RECORDED_READY_FOR_MANUAL_LIVE_COMMAND"
)
TINY_LIVE_JIT_REJECTED_BAD_CONFIRMATION = "TINY_LIVE_JIT_REJECTED_BAD_CONFIRMATION"
TINY_LIVE_JIT_BLOCKED_BY_R262B = "TINY_LIVE_JIT_BLOCKED_BY_R262B"
TINY_LIVE_JIT_BLOCKED_BY_R263_ARMING = "TINY_LIVE_JIT_BLOCKED_BY_R263_ARMING"
TINY_LIVE_JIT_BLOCKED_BY_R264_DRY_PREVIEW = "TINY_LIVE_JIT_BLOCKED_BY_R264_DRY_PREVIEW"
TINY_LIVE_JIT_BLOCKED_BY_IDEMPOTENCY = "TINY_LIVE_JIT_BLOCKED_BY_IDEMPOTENCY"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/tiny_live_percentage_risk_contract_fit_regeneration.py",
    "src/app/hammer_radar/operator/tiny_live_final_console.py",
    "src/app/hammer_radar/operator/tiny_live_actual_submit_reconciliation.py",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson",
    "logs/hammer_radar_forward/tiny_live_final_console.ndjson",
    "logs/hammer_radar_forward/tiny_live_actual_submit_reconciliation.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_jit_launch_packet(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    run_jit_launch_prep: bool = False,
    record_jit_launch_packet: bool = False,
    confirm_jit_launch_prep: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    confirmation_valid = confirm_jit_launch_prep == JIT_LAUNCH_PREP_CONFIRMATION_PHRASE
    symbol, timeframe, direction, _entry_mode = _lane_parts(official_lane_key)
    try:
        steps = _empty_jit_step_results()
        if run_jit_launch_prep and not confirmation_valid:
            status = TINY_LIVE_JIT_LAUNCH_PACKET_REJECTED
            overall = TINY_LIVE_JIT_REJECTED_BAD_CONFIRMATION
        elif run_jit_launch_prep and confirmation_valid:
            steps["r262b_contract_fit_refresh"] = run_r262b_contract_fit_refresh_step(
                log_dir=resolved_log_dir,
                risk_contract_config_path=risk_path,
                official_lane_key=official_lane_key,
                now=generated_at,
            )
            if steps["r262b_contract_fit_refresh"]["succeeded"]:
                steps["r263_runtime_arming"] = run_r263_runtime_arming_step(
                    log_dir=resolved_log_dir,
                    risk_contract_config_path=risk_path,
                    lane_controls_path=lane_path,
                    operator_id=operator_id,
                    reason=reason,
                    official_lane_key=official_lane_key,
                    now=generated_at,
                )
            if steps["r263_runtime_arming"]["succeeded"]:
                steps["r264_dry_preview"] = run_r264_dry_preview_step(
                    log_dir=resolved_log_dir,
                    risk_contract_config_path=risk_path,
                    lane_controls_path=lane_path,
                    operator_id=operator_id,
                    reason=reason,
                    official_lane_key=official_lane_key,
                    now=generated_at,
                )
            validation = validate_jit_launch_packet(jit_step_results=steps)
            overall = classify_tiny_live_jit_launch_packet_status(
                run_requested=run_jit_launch_prep,
                record_requested=record_jit_launch_packet,
                confirmation_valid=confirmation_valid,
                recorded=record_jit_launch_packet and validation["valid"],
                jit_validation=validation,
            )
            status = _top_status(
                run_requested=run_jit_launch_prep,
                confirmation_valid=confirmation_valid,
                record_requested=record_jit_launch_packet,
                validation=validation,
            )
        else:
            validation = validate_jit_launch_packet(jit_step_results=steps)
            status = TINY_LIVE_JIT_LAUNCH_PACKET_READY
            overall = TINY_LIVE_JIT_READY_FOR_CONFIRMATION

        validation = locals().get("validation") or validate_jit_launch_packet(jit_step_results=steps)
        final_command = build_final_live_submit_command_packet(jit_validation=validation)
        go_no_go = _go_no_go_packet(jit_validation=validation, final_command=final_command)
        matrix = _launch_matrix(jit_validation=validation, final_command=final_command)
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "run_jit_launch_prep_requested": bool(run_jit_launch_prep),
                "record_jit_launch_packet_requested": bool(record_jit_launch_packet),
                "confirmation_valid": bool(confirmation_valid),
                "jit_launch_packet_recorded": False,
                "operator_intent": {
                    "operator_id": str(operator_id or "local_operator"),
                    "reason": str(reason or ""),
                    "source_phase": "R264B",
                },
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "jit_launch_packet_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                },
                "experimental_lane_warning": {
                    "accepted_only_by_exact_r263_phrase": steps["r263_runtime_arming"][
                        "experimental_lane_acceptance_recorded"
                    ],
                    "message": "8m short is paper-only/promotion-mismatched and is allowed only as a manual experimental tiny-live lane.",
                    "promoted_lanes_remain": [
                        "BTCUSDT|13m|long|ladder_close_50_618",
                        "BTCUSDT|44m|long|ladder_close_50_618",
                    ],
                },
                "jit_step_results": steps,
                "jit_validation": validation,
                "final_live_submit_command_packet": final_command,
                "jit_go_no_go_packet": go_no_go,
                "jit_launch_matrix": matrix,
                "jit_launch_overall_status": overall,
                "recommended_next_operator_move": _recommended_next_operator_move(go_no_go, validation),
                "recommended_next_engineering_move": _recommended_next_engineering_move(go_no_go, validation),
                "do_not_run_yet": [
                    "manual live command if JIT packet is not GO",
                    "manual live command twice",
                    "manual live command with stale signed triplet",
                    "manual live command without R263 runtime arming",
                ],
                "safety": _safety_from_steps(steps),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if record_jit_launch_packet and confirmation_valid:
            payload = append_tiny_live_jit_launch_packet_record(payload, log_dir=resolved_log_dir)
        return payload
    except Exception as exc:  # pragma: no cover - defensive operator JSON boundary
        return _sanitize(
            {
                "status": TINY_LIVE_JIT_LAUNCH_PACKET_ERROR,
                "generated_at": generated_at.isoformat(),
                "run_jit_launch_prep_requested": bool(run_jit_launch_prep),
                "record_jit_launch_packet_requested": bool(record_jit_launch_packet),
                "confirmation_valid": False,
                "jit_launch_packet_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "jit_launch_packet_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                },
                "jit_step_results": _empty_jit_step_results(),
                "jit_validation": validate_jit_launch_packet(jit_step_results=_empty_jit_step_results()),
                "jit_launch_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "error": exc.__class__.__name__,
                "safety": _safety_from_steps(_empty_jit_step_results()),
            }
        )


def run_r262b_contract_fit_refresh_step(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = build_tiny_live_percentage_risk_contract_fit_regeneration(
        log_dir=log_dir,
        risk_contract_config_path=risk_contract_config_path,
        run_contract_fit_regeneration=True,
        record_contract_fit_regeneration=True,
        confirm_contract_fit_regeneration=CONTRACT_FIT_CONFIRMATION_PHRASE,
        official_lane_key=official_lane_key,
        now=now,
    )
    validation = payload.get("output_validation") if isinstance(payload.get("output_validation"), Mapping) else {}
    sizing = payload.get("contract_fit_sizing_plan") if isinstance(payload.get("contract_fit_sizing_plan"), Mapping) else {}
    matrix = payload.get("contract_fit_matrix") if isinstance(payload.get("contract_fit_matrix"), Mapping) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    blocked = list(validation.get("errors") or [])
    blocked.extend(str(item) for item in matrix.get("blocked_by") or [])
    return _sanitize(
        {
            "attempted": True,
            "succeeded": bool(
                payload.get("contract_fit_regeneration_recorded") is True
                and validation.get("valid") is True
                and validation.get("risk_contract_valid_after") is True
                and validation.get("fresh_signed_request_available") is True
            ),
            "risk_contract_valid": validation.get("risk_contract_valid_after") is True
            or matrix.get("risk_contract_valid") is True,
            "signed_triplet_fresh": validation.get("fresh_signed_request_available") is True,
            "candidate_qty": sizing.get("candidate_qty"),
            "candidate_notional_usdt": sizing.get("candidate_notional_usdt"),
            "blocked_by": _dedupe(blocked),
            "child_status": payload.get("status"),
            "child_overall_status": payload.get("contract_fit_overall_status"),
            "safety": safety,
        }
    )


def run_r263_runtime_arming_step(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = build_tiny_live_final_console(
        log_dir=log_dir,
        risk_contract_config_path=risk_contract_config_path,
        lane_controls_path=lane_controls_path,
        arm_controls_from_final_console=True,
        confirm_final_console_controls_arming=FINAL_CONSOLE_CONTROLS_ARMING_CONFIRMATION_PHRASE,
        operator_id=operator_id,
        reason=reason,
        official_lane_key=official_lane_key,
        now=now,
    )
    controls = payload.get("controls_panel") if isinstance(payload.get("controls_panel"), Mapping) else {}
    choice = payload.get("operator_choice_panel") if isinstance(payload.get("operator_choice_panel"), Mapping) else {}
    result = payload.get("controls_arming_result") if isinstance(payload.get("controls_arming_result"), Mapping) else {}
    return _sanitize(
        {
            "attempted": True,
            "succeeded": bool(
                payload.get("final_console_controls_armed") is True
                and controls.get("controls_armed") is True
                and choice.get("experimental_lane_acceptance_recorded") is True
            ),
            "controls_armed": controls.get("controls_armed") is True,
            "experimental_lane_acceptance_recorded": choice.get("experimental_lane_acceptance_recorded") is True,
            "lane_controls_written": result.get("lane_controls_written") is True,
            "blocked_by": list(result.get("blocked_by") or []),
            "child_status": payload.get("status"),
            "child_overall_status": payload.get("final_console_overall_status"),
            "safety": payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {},
        }
    )


def run_r264_dry_preview_step(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        risk_contract_config_path=risk_contract_config_path,
        lane_controls_path=lane_controls_path,
        dry_run_actual_submit_reconcile=True,
        record_actual_submit_preview=True,
        confirm_actual_submit_dry_preview=R264_DRY_PREVIEW_CONFIRMATION_PHRASE,
        execute_actual_live_submit=False,
        allow_binance_order_endpoint=False,
        confirm_actual_live_submit=None,
        operator_id=operator_id,
        reason=reason,
        official_lane_key=official_lane_key,
        now=now,
    )
    pre = payload.get("pre_submit_validation") if isinstance(payload.get("pre_submit_validation"), Mapping) else {}
    idem = payload.get("idempotency") if isinstance(payload.get("idempotency"), Mapping) else {}
    return _sanitize(
        {
            "attempted": True,
            "succeeded": bool(payload.get("actual_submit_preview_recorded") is True and pre.get("valid") is True),
            "actual_submit_preview_recorded": payload.get("actual_submit_preview_recorded") is True,
            "pre_submit_valid": pre.get("valid") is True,
            "idempotency_clean": idem.get("prior_live_submit_found") is not True,
            "blocked_by": list(pre.get("blocked_by") or []),
            "exact_three_orders": pre.get("exact_three_orders") is True,
            "main_order_valid": pre.get("main_order_valid") is True,
            "stop_order_valid": pre.get("stop_order_valid") is True,
            "take_profit_order_valid": pre.get("take_profit_order_valid") is True,
            "reduce_only_exits": pre.get("reduce_only_exits") is True,
            "signed_triplet_fresh": pre.get("signed_triplet_fresh") is True,
            "risk_contract_valid": pre.get("risk_contract_valid") is True,
            "controls_armed": pre.get("controls_armed") is True,
            "experimental_lane_acceptance_recorded": pre.get("experimental_lane_acceptance_recorded") is True,
            "prior_live_submit_found": idem.get("prior_live_submit_found") is True,
            "child_status": payload.get("status"),
            "child_overall_status": payload.get("actual_submit_overall_status"),
            "safety": payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {},
        }
    )


def validate_jit_launch_packet(*, jit_step_results: Mapping[str, Any]) -> dict[str, Any]:
    r262b = jit_step_results.get("r262b_contract_fit_refresh") if isinstance(jit_step_results.get("r262b_contract_fit_refresh"), Mapping) else {}
    r263 = jit_step_results.get("r263_runtime_arming") if isinstance(jit_step_results.get("r263_runtime_arming"), Mapping) else {}
    r264 = jit_step_results.get("r264_dry_preview") if isinstance(jit_step_results.get("r264_dry_preview"), Mapping) else {}
    blocked: list[str] = []
    if r262b.get("attempted") and r262b.get("succeeded") is not True:
        blocked.extend(str(item) for item in r262b.get("blocked_by") or ["r262b_contract_fit_refresh_failed"])
    if r263.get("attempted") and r263.get("succeeded") is not True:
        blocked.extend(str(item) for item in r263.get("blocked_by") or ["r263_runtime_arming_failed"])
    if r264.get("attempted") and r264.get("succeeded") is not True:
        blocked.extend(str(item) for item in r264.get("blocked_by") or ["r264_dry_preview_failed"])
    if r264.get("prior_live_submit_found") is True:
        blocked.append("prior_live_submit_exists")
    valid = bool(
        r262b.get("succeeded") is True
        and r263.get("succeeded") is True
        and r264.get("succeeded") is True
        and r264.get("idempotency_clean") is True
        and r264.get("exact_three_orders") is True
        and r264.get("main_order_valid") is True
        and r264.get("stop_order_valid") is True
        and r264.get("take_profit_order_valid") is True
        and r264.get("reduce_only_exits") is True
        and r264.get("signed_triplet_fresh") is True
        and r264.get("risk_contract_valid") is True
        and r264.get("controls_armed") is True
    )
    return {
        "valid": valid,
        "blocked_by": _dedupe(blocked),
        "r262b_valid": r262b.get("succeeded") is True and r262b.get("risk_contract_valid") is True,
        "r263_armed": r263.get("succeeded") is True and r263.get("controls_armed") is True,
        "r264_dry_preview_valid": r264.get("succeeded") is True and r264.get("pre_submit_valid") is True,
        "signed_triplet_fresh": r264.get("signed_triplet_fresh") is True,
        "risk_contract_valid": r264.get("risk_contract_valid") is True or r262b.get("risk_contract_valid") is True,
        "idempotency_clean": r264.get("idempotency_clean") is True,
        "exact_three_orders": r264.get("exact_three_orders") is True,
        "no_live_submit_performed": True,
    }


def build_final_live_submit_command_packet(*, jit_validation: Mapping[str, Any]) -> dict[str, Any]:
    command = (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward tiny-live-actual-submit-reconcile "
        "--execute-actual-live-submit --allow-binance-order-endpoint "
        f'--confirm-actual-live-submit "{LIVE_SUBMIT_CONFIRMATION_PHRASE}" '
        '--operator-id local_operator --reason "R264 actual tiny-live submit after R264B JIT launch packet GO."'
    )
    return {
        "available": jit_validation.get("valid") is True,
        "must_be_run_manually_by_operator": True,
        "do_not_run_from_codex": True,
        "command": command if jit_validation.get("valid") is True else "",
        "confirmation_phrase": LIVE_SUBMIT_CONFIRMATION_PHRASE,
        "expected_orders": {
            "main": "SELL MARKET 0.006 BTC",
            "stop": "BUY STOP_MARKET REDUCE_ONLY",
            "take_profit": "BUY TAKE_PROFIT_MARKET REDUCE_ONLY",
        },
    }


def append_tiny_live_jit_launch_packet_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_jit_launch_packet_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "jit_launch_packet_record_id": record.get("jit_launch_packet_record_id")
            or f"r264b_jit_launch_packet_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "jit_launch_packet_recorded": True,
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_jit_launch_packet_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_jit_launch_packet_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def classify_tiny_live_jit_launch_packet_status(
    *,
    run_requested: bool,
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
    jit_validation: Mapping[str, Any],
) -> str:
    if run_requested and not confirmation_valid:
        return TINY_LIVE_JIT_REJECTED_BAD_CONFIRMATION
    if recorded and jit_validation.get("valid") is True:
        return TINY_LIVE_JIT_RECORDED_READY_FOR_MANUAL_LIVE_COMMAND
    blockers = set(jit_validation.get("blocked_by") or [])
    if "prior_live_submit_exists" in blockers:
        return TINY_LIVE_JIT_BLOCKED_BY_IDEMPOTENCY
    if not run_requested or not record_requested:
        return TINY_LIVE_JIT_READY_FOR_CONFIRMATION
    if jit_validation.get("r262b_valid") is not True:
        return TINY_LIVE_JIT_BLOCKED_BY_R262B
    if jit_validation.get("r263_armed") is not True:
        return TINY_LIVE_JIT_BLOCKED_BY_R263_ARMING
    if jit_validation.get("r264_dry_preview_valid") is not True:
        return TINY_LIVE_JIT_BLOCKED_BY_R264_DRY_PREVIEW
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def tiny_live_jit_launch_packet_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_jit_launch_packet_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _empty_jit_step_results() -> dict[str, dict[str, Any]]:
    return {
        "r262b_contract_fit_refresh": {
            "attempted": False,
            "succeeded": False,
            "risk_contract_valid": False,
            "signed_triplet_fresh": False,
            "candidate_qty": None,
            "candidate_notional_usdt": None,
            "blocked_by": [],
        },
        "r263_runtime_arming": {
            "attempted": False,
            "succeeded": False,
            "controls_armed": False,
            "experimental_lane_acceptance_recorded": False,
            "lane_controls_written": False,
            "blocked_by": [],
        },
        "r264_dry_preview": {
            "attempted": False,
            "succeeded": False,
            "actual_submit_preview_recorded": False,
            "pre_submit_valid": False,
            "idempotency_clean": False,
            "blocked_by": [],
        },
    }


def _top_status(
    *,
    run_requested: bool,
    confirmation_valid: bool,
    record_requested: bool,
    validation: Mapping[str, Any],
) -> str:
    if run_requested and not confirmation_valid:
        return TINY_LIVE_JIT_LAUNCH_PACKET_REJECTED
    if validation.get("valid") is not True and run_requested:
        return TINY_LIVE_JIT_LAUNCH_PACKET_BLOCKED
    if record_requested and validation.get("valid") is True:
        return TINY_LIVE_JIT_LAUNCH_PACKET_RECORDED
    return TINY_LIVE_JIT_LAUNCH_PACKET_READY


def _go_no_go_packet(*, jit_validation: Mapping[str, Any], final_command: Mapping[str, Any]) -> dict[str, Any]:
    if jit_validation.get("valid") is True and final_command.get("available") is True:
        next_step = "MANUAL_LIVE_COMMAND"
    elif not jit_validation.get("idempotency_clean"):
        next_step = "WAIT"
    elif not jit_validation.get("r262b_valid"):
        next_step = "RERUN_JIT"
    elif not jit_validation.get("r263_armed") or not jit_validation.get("r264_dry_preview_valid"):
        next_step = "RERUN_JIT"
    else:
        next_step = "FIX_BLOCKER"
    return {
        "go_for_manual_live_submit_command": jit_validation.get("valid") is True,
        "operator_should_submit_now": False,
        "next_required_step": next_step,
    }


def _launch_matrix(*, jit_validation: Mapping[str, Any], final_command: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fresh_contract_fit_ready": jit_validation.get("r262b_valid") is True
        and jit_validation.get("signed_triplet_fresh") is True,
        "controls_armed": jit_validation.get("r263_armed") is True,
        "dry_preview_clean": jit_validation.get("r264_dry_preview_valid") is True
        and jit_validation.get("idempotency_clean") is True,
        "manual_command_available": final_command.get("available") is True,
        "submit_allowed": False,
        "order_placed": False,
        "blocked_by": list(jit_validation.get("blocked_by") or []),
    }


def _recommended_next_operator_move(go_no_go: Mapping[str, Any], validation: Mapping[str, Any]) -> str:
    if not validation.get("blocked_by") and validation.get("valid") is not True:
        return "Wait for exact R264B JIT prep confirmation; do not submit from preview."
    if go_no_go.get("next_required_step") == "MANUAL_LIVE_COMMAND":
        return "Review the R264B GO packet, then manually run the printed command only once outside Codex if you still accept real order placement."
    if go_no_go.get("next_required_step") == "RERUN_JIT":
        return "Rerun the R264B JIT prep command after fixing the listed blocker or waiting for fresh state."
    if go_no_go.get("next_required_step") == "WAIT":
        return "Do not submit; idempotency or prior live-submit state requires manual review."
    if validation.get("blocked_by"):
        return "Fix the listed blocker before any manual live command."
    return "Wait for exact JIT prep confirmation."


def _recommended_next_engineering_move(go_no_go: Mapping[str, Any], validation: Mapping[str, Any]) -> str:
    if go_no_go.get("next_required_step") == "MANUAL_LIVE_COMMAND":
        return "No engineering move; keep Codex out of the real submit path."
    if validation.get("blocked_by"):
        return "Inspect the child R262B/R263/R264 blocker without loosening risk or bypassing gates."
    return "Keep R264B in preview until the operator supplies the exact prep phrase."


def _safety_from_steps(steps: Mapping[str, Any]) -> dict[str, Any]:
    r262b = steps.get("r262b_contract_fit_refresh") if isinstance(steps.get("r262b_contract_fit_refresh"), Mapping) else {}
    r263 = steps.get("r263_runtime_arming") if isinstance(steps.get("r263_runtime_arming"), Mapping) else {}
    r262b_safety = r262b.get("safety") if isinstance(r262b.get("safety"), Mapping) else {}
    return {
        **SAFETY_FALSE,
        "env_written": False,
        "env_mutated": False,
        "external_env_file_written": False,
        "risk_contract_config_written": r262b_safety.get("risk_contract_config_written") is True,
        "lane_controls_written": r263.get("lane_controls_written") is True,
        "live_config_written": False,
        "jit_launch_packet_only": True,
        "hmac_signature_created": r262b_safety.get("hmac_signature_created") is True,
        "signed_request_written": r262b_safety.get("signed_request_written") is True,
        "signed_order_request_created": r262b_safety.get("signed_order_request_created") is True,
        "signed_trading_request_created": r262b_safety.get("signed_trading_request_created") is True,
        "submit_allowed": False,
        "submit_attempted": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
        "binance_account_endpoint_called": False,
        "binance_exchange_info_endpoint_called": r262b_safety.get("binance_exchange_info_endpoint_called") is True,
        "binance_mark_price_endpoint_called": r262b_safety.get("binance_mark_price_endpoint_called") is True,
        "private_binance_endpoint_called": False,
        "signed_binance_endpoint_called": False,
        "network_allowed": r262b_safety.get("network_allowed") is True,
        "transfer_endpoint_called": False,
        "withdraw_endpoint_called": False,
        "kill_switch_disabled": False,
        "live_controls_armed_by_phase": r263.get("succeeded") is True,
        "secrets_read": False,
        "secrets_shown": False,
        "secrets_persisted": False,
        "secret_values_in_output": False,
        "global_live_flags_changed": False,
        "paper_live_separation_intact": True,
        "official_tiny_live_lane_changed": False,
    }


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key).split("|")
    padded = [*parts, "", "", "", ""]
    return padded[0], padded[1], padded[2], padded[3]


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(str(item))
            result.append(str(item))
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            lowered = key_str.lower()
            if lowered in {"signature", "x-mbx-apikey", "api_key", "api_secret", "secret"}:
                sanitized[key_str] = "<hidden>" if item else None
            elif lowered == "headers" and isinstance(item, Mapping):
                sanitized[key_str] = {
                    str(header_key): "<present>"
                    if str(header_key).lower() == "x-mbx-apikey"
                    else _sanitize(header_value)
                    for header_key, header_value in item.items()
                }
            elif lowered in {"query_string", "query_string_without_signature"}:
                sanitized[key_str] = _redact_query_string(str(item or ""))
            else:
                sanitized[key_str] = _sanitize(item)
        return sanitized
    if isinstance(value, list | tuple):
        return [_sanitize(item) for item in value]
    return value


def _redact_query_string(value: str) -> str:
    if not value:
        return value
    parts: list[str] = []
    for item in value.split("&"):
        if "=" not in item:
            parts.append(item)
            continue
        key, raw = item.split("=", 1)
        if key.lower() in {"signature", "apikey", "api_key", "secret", "api_secret"}:
            parts.append(f"{key}=<hidden>")
        else:
            parts.append(f"{key}={raw}")
    return "&".join(parts)
