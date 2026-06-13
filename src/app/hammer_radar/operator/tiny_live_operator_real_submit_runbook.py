"""R256 tiny-live operator real-submit runbook and reconciliation packet.

This module is runbook-only. It never signs, submits, calls Binance/network, or
mutates live controls. The only allowed mutation is its own audit ledger append
after the exact R256 confirmation phrase.
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
    load_tiny_live_actual_submit_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_fresh_context_signed_request_regeneration_gate import (
    load_tiny_live_fresh_context_signed_request_regeneration_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_submit_gate_preview import (
    load_tiny_live_submit_gate_preview_records,
)

TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_READY = "TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_READY"
TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_RECORDED = "TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_RECORDED"
TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_REJECTED = "TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_REJECTED"
TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_BLOCKED = "TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_BLOCKED"
TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_ERROR = "TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_ERROR"

TINY_LIVE_OPERATOR_RUNBOOK_READY_FOR_RECORDING = "TINY_LIVE_OPERATOR_RUNBOOK_READY_FOR_RECORDING"
TINY_LIVE_OPERATOR_RUNBOOK_RECORDED_MANUAL_DECISION_REQUIRED = (
    "TINY_LIVE_OPERATOR_RUNBOOK_RECORDED_MANUAL_DECISION_REQUIRED"
)
TINY_LIVE_OPERATOR_RUNBOOK_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_OPERATOR_RUNBOOK_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_OPERATOR_RUNBOOK_BLOCKED_BY_MISSING_R255 = (
    "TINY_LIVE_OPERATOR_RUNBOOK_BLOCKED_BY_MISSING_R255"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK"
LEDGER_FILENAME = "tiny_live_operator_real_submit_runbook.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R256_TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_AND_RECONCILIATION"
CONFIRM_TINY_LIVE_OPERATOR_RUNBOOK_PHRASE = (
    "I CONFIRM TINY LIVE OPERATOR RUNBOOK RECORDING ONLY; "
    "NO SUBMIT; NO ORDER; NO BINANCE CALL."
)

SOURCE_SURFACES_USED = [
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
    "operator_runbook_only": True,
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
    "secrets_read": False,
    "secrets_shown": False,
    "secrets_persisted": False,
    "secret_values_in_output": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
}


def build_tiny_live_operator_real_submit_runbook(
    *,
    log_dir: str | Path | None = None,
    record_operator_real_submit_runbook: bool = False,
    confirm_tiny_live_operator_runbook: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_tiny_live_operator_runbook == CONFIRM_TINY_LIVE_OPERATOR_RUNBOOK_PHRASE
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)

    try:
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
            "r255_actual_submit_gate_found": bool(latest_r255),
            "r255_actual_submit_gate_valid": _r255_valid(latest_r255),
            "r254_submit_gate_preview_found": bool(latest_r254),
            "r253b_fresh_regeneration_found": bool(latest_r253b),
        }
        current_blockers = summarize_current_submit_blockers_for_operator(latest_r255)
        checklist = build_operator_pre_submit_checklist(current_blockers=current_blockers)
        regeneration_sequence = build_required_regeneration_sequence(current_blockers=current_blockers)
        command_template = build_real_submit_command_template()
        reconciliation = build_post_submit_reconciliation_checklist()
        partial_plan = build_partial_success_handling_plan()
        abort_tree = build_abort_cleanup_decision_tree()
        duplicate_review = build_duplicate_submit_protection_review(latest_r255)
        decision_packet = build_operator_manual_decision_packet(
            input_summary=input_summary,
            current_blockers=current_blockers,
        )
        gate_matrix = build_runbook_gate_matrix(
            input_summary=input_summary,
            record_confirmed=confirmation_valid,
            recorded=False,
            blocked_by=current_blockers["blocked_by"],
        )
        status = classify_tiny_live_operator_real_submit_runbook_status(
            input_summary=input_summary,
            record_requested=record_operator_real_submit_runbook,
            confirmation_valid=confirmation_valid,
            recorded=False,
        )
        overall = _overall_status(
            input_summary=input_summary,
            record_requested=record_operator_real_submit_runbook,
            confirmation_valid=confirmation_valid,
            recorded=False,
        )
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "record_operator_real_submit_runbook_requested": bool(record_operator_real_submit_runbook),
                "confirmation_valid": bool(confirmation_valid),
                "operator_runbook_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "operator_runbook_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "current_submit_blockers": current_blockers,
                "operator_pre_submit_checklist": checklist,
                "required_regeneration_sequence": regeneration_sequence,
                "real_submit_command_template": command_template,
                "post_submit_reconciliation_checklist": reconciliation,
                "partial_success_handling_plan": partial_plan,
                "abort_cleanup_decision_tree": abort_tree,
                "duplicate_submit_protection_review": duplicate_review,
                "operator_manual_decision_packet": decision_packet,
                "runbook_gate_matrix": gate_matrix,
                "operator_runbook_overall_status": overall,
                "recommended_next_operator_move": _recommended_next_operator_move(decision_packet),
                "recommended_next_engineering_move": _recommended_next_engineering_move(input_summary),
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if record_operator_real_submit_runbook and confirmation_valid:
            payload["status"] = TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_RECORDED
            payload["operator_runbook_overall_status"] = (
                TINY_LIVE_OPERATOR_RUNBOOK_RECORDED_MANUAL_DECISION_REQUIRED
            )
            payload["runbook_gate_matrix"]["record_confirmed"] = True
            payload["runbook_gate_matrix"]["recorded"] = True
            payload = append_tiny_live_operator_real_submit_runbook_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_operator_runbook=confirm_tiny_live_operator_runbook,
            )
        return payload
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        return _sanitize(
            {
                "status": TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_ERROR,
                "generated_at": generated_at.isoformat(),
                "record_operator_real_submit_runbook_requested": bool(record_operator_real_submit_runbook),
                "confirmation_valid": bool(confirmation_valid),
                "operator_runbook_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "operator_runbook_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "error": type(exc).__name__,
                "operator_runbook_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "safety": dict(SAFETY),
            }
        )


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


def summarize_current_submit_blockers_for_operator(latest_r255: Mapping[str, Any]) -> dict[str, Any]:
    matrix = latest_r255.get("actual_submit_gate_matrix") if isinstance(latest_r255.get("actual_submit_gate_matrix"), Mapping) else {}
    freshness = latest_r255.get("signed_request_freshness") if isinstance(latest_r255.get("signed_request_freshness"), Mapping) else {}
    blocked_by = list(matrix.get("blocked_by") or [])
    requires_regeneration = bool(
        freshness.get("requires_regeneration") is True
        or "signed_request_timestamp_stale" in blocked_by
        or not latest_r255
    )
    requires_live_controls_arming = any(
        item in blocked_by
        for item in (
            "official_lane_not_tiny_live",
            "live_execution_not_enabled",
            "kill_switch_blocks_tiny_live",
        )
    )
    if not latest_r255:
        blocked_by.append("r255_actual_submit_gate_missing")
    return {
        "blocked_by": _dedupe(str(item) for item in blocked_by),
        "requires_regeneration": requires_regeneration,
        "requires_live_controls_arming": requires_live_controls_arming,
        "requires_operator_manual_decision": True,
        "submit_allowed_now": False,
    }


def build_operator_pre_submit_checklist(
    *, current_blockers: Mapping[str, Any] | None = None
) -> list[str]:
    return [
        "run a fresh final readonly mark refresh before any manual submit decision",
        "regenerate the signed request if timestamp would be stale",
        "confirm lane/tiny-live controls are intentionally armed",
        "confirm kill-switch does not block tiny-live submit",
        "confirm no duplicate live submit exists for the idempotency key",
        "confirm exact triplet: main SELL MARKET 0.007; stop BUY STOP_MARKET reduceOnly true; TP BUY TAKE_PROFIT_MARKET reduceOnly true",
        "run R255 actual submit gate dry preview immediately before real submit",
        "review post-submit reconciliation checklist and partial-success abort paths",
        "only then consider manually pasting the exact R255 real-submit command",
    ]


def build_required_regeneration_sequence(
    *, current_blockers: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    blockers = current_blockers or {}
    return {
        "required_if_timestamp_stale": True,
        "currently_required": blockers.get("requires_regeneration") is True,
        "steps": [
            "run R253 final readonly refresh",
            "run R253B fresh context signed request regeneration",
            "run R254 submit gate preview",
            "run R255 actual submit gate dry preview",
        ],
    }


def build_real_submit_command_template() -> dict[str, Any]:
    command = (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward tiny-live-actual-submit-gate "
        "--execute-actual-submit --allow-real-binance-order-endpoint "
        f"--confirm-tiny-live-actual-submit \"{REAL_SUBMIT_CONFIRMATION_PHRASE}\""
    )
    return {
        "command_is_template_only": True,
        "must_not_auto_run": True,
        "requires_manual_operator_paste": True,
        "command": command,
        "confirmation_phrase": REAL_SUBMIT_CONFIRMATION_PHRASE,
    }


def build_post_submit_reconciliation_checklist() -> list[str]:
    return [
        "record exchange order ids",
        "verify main order status",
        "verify stop reduceOnly order status",
        "verify take-profit reduceOnly order status",
        "verify no extra orders",
        "verify live execution ledger append",
        "verify idempotency key recorded",
    ]


def build_partial_success_handling_plan() -> dict[str, list[str]]:
    return {
        "if_main_fails": [
            "do not retry automatically",
            "verify whether any stop or take-profit order was accepted",
            "cancel any accepted reduceOnly exit order if there is no matching position",
            "record exchange response and stop for operator reconciliation",
        ],
        "if_main_succeeds_stop_fails": [
            "treat position as unprotected",
            "do not submit take-profit-only recovery without operator decision",
            "operator must place or verify protective stop manually before any further action",
            "record main order id and failed stop response",
        ],
        "if_main_succeeds_tp_fails": [
            "verify stop reduceOnly protection is live",
            "do not retry take-profit until stop status and current position are reconciled",
            "record main and stop order ids plus failed take-profit response",
        ],
        "if_exit_order_duplicate": [
            "do not assume protection is missing",
            "query or inspect exchange open orders manually before retrying",
            "record duplicate client/order id details in reconciliation notes",
        ],
        "if_unknown_exchange_response": [
            "do not retry submit",
            "reconcile exchange order history and open positions first",
            "verify whether main, stop, or take-profit was accepted",
            "escalate to manual cleanup if state cannot be proven from exchange records",
        ],
    }


def build_abort_cleanup_decision_tree() -> dict[str, list[str]]:
    return {
        "before_submit": [
            "abort if signed request is stale",
            "abort if lane/tiny-live controls are not intentionally armed",
            "abort if kill-switch blocks",
            "abort if any prior live submit exists for the idempotency key",
        ],
        "after_partial_submit": [
            "stop all retries",
            "reconcile accepted order ids and current position",
            "ensure a successful main order has reduceOnly stop protection",
            "cancel orphan reduceOnly exits when no position exists",
        ],
        "after_full_submit": [
            "record all three exchange order ids",
            "verify main, stop, and take-profit statuses",
            "verify only one main order and two reduceOnly exits exist",
        ],
        "if_reconciliation_fails": [
            "do not submit again",
            "preserve logs and exchange screenshots/exports",
            "escalate to manual exchange cleanup and engineering review",
        ],
    }


def build_duplicate_submit_protection_review(latest_r255: Mapping[str, Any] | None = None) -> dict[str, Any]:
    summary = latest_r255.get("idempotency_summary") if isinstance((latest_r255 or {}).get("idempotency_summary"), Mapping) else {}
    return {
        "idempotency_key_required": True,
        "prior_live_submit_must_be_false": True,
        "do_not_retry_without_reconciliation": True,
        "latest_idempotency_key": summary.get("idempotency_key"),
        "prior_live_submit_found": summary.get("prior_live_submit_found") is True,
        "dedupe_allows_submit": summary.get("dedupe_allows_submit") is True,
    }


def build_operator_manual_decision_packet(
    *,
    input_summary: Mapping[str, Any],
    current_blockers: Mapping[str, Any],
) -> dict[str, Any]:
    if input_summary.get("r255_actual_submit_gate_found") is not True:
        action = "REVIEW_RUNBOOK"
    elif current_blockers.get("requires_regeneration") is True:
        action = "REGENERATE_SIGNED_REQUEST"
    elif current_blockers.get("requires_live_controls_arming") is True:
        action = "ARM_LIVE_CONTROLS_MANUALLY"
    elif current_blockers.get("blocked_by"):
        action = "WAIT"
    else:
        action = "MANUAL_SUBMIT_DECISION"
    return {
        "operator_should_submit_now": False,
        "operator_should_regenerate_first": current_blockers.get("requires_regeneration") is True,
        "operator_should_arm_live_controls_manually": current_blockers.get("requires_live_controls_arming") is True,
        "operator_should_review_reconciliation_plan": True,
        "next_required_human_action": action,
    }


def build_runbook_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    record_confirmed: bool,
    recorded: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "r255_available": input_summary.get("r255_actual_submit_gate_found") is True,
        "runbook_complete": True,
        "record_confirmed": bool(record_confirmed),
        "recorded": bool(recorded),
        "submit_allowed": False,
        "order_placed": False,
        "blocked_by": _dedupe(blocked_by or []),
    }


def classify_tiny_live_operator_real_submit_runbook_status(
    *,
    input_summary: Mapping[str, Any],
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_REJECTED
    if recorded:
        return TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_RECORDED
    if input_summary.get("r255_actual_submit_gate_found") is not True:
        return TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_BLOCKED
    return TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_READY


def append_tiny_live_operator_real_submit_runbook_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_operator_runbook: str | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_operator_runbook != CONFIRM_TINY_LIVE_OPERATOR_RUNBOOK_PHRASE:
        raise ValueError("bad_tiny_live_operator_runbook_confirmation")
    path = tiny_live_operator_real_submit_runbook_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "operator_runbook_record_id": record.get("operator_runbook_record_id")
            or f"r256_operator_runbook_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "operator_runbook_recorded": True,
            "created_by_phase": CREATED_BY_PHASE,
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_operator_real_submit_runbook_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_operator_real_submit_runbook_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_operator_real_submit_runbook_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_recorded": latest.get("operator_runbook_recorded") is True,
        "latest_overall_status": latest.get("operator_runbook_overall_status"),
        "latest_next_required_human_action": (
            latest.get("operator_manual_decision_packet", {}).get("next_required_human_action")
            if isinstance(latest.get("operator_manual_decision_packet"), Mapping)
            else None
        ),
    }


def tiny_live_operator_real_submit_runbook_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_operator_real_submit_runbook_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _overall_status(
    *,
    input_summary: Mapping[str, Any],
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_OPERATOR_RUNBOOK_REJECTED_BAD_CONFIRMATION
    if recorded:
        return TINY_LIVE_OPERATOR_RUNBOOK_RECORDED_MANUAL_DECISION_REQUIRED
    if input_summary.get("r255_actual_submit_gate_found") is not True:
        return TINY_LIVE_OPERATOR_RUNBOOK_BLOCKED_BY_MISSING_R255
    return TINY_LIVE_OPERATOR_RUNBOOK_READY_FOR_RECORDING


def _r255_valid(record: Mapping[str, Any]) -> bool:
    if not record:
        return False
    safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
    matrix = record.get("actual_submit_gate_matrix") if isinstance(record.get("actual_submit_gate_matrix"), Mapping) else {}
    return bool(
        record.get("actual_submit_executed") is False
        and safety.get("order_placed") is False
        and safety.get("real_order_placed") is False
        and safety.get("execution_attempted") is False
        and safety.get("secrets_shown") is False
        and matrix.get("order_triplet_valid") is True
        and matrix.get("endpoint_allowlist_valid") is True
        and matrix.get("idempotency_allows") is True
    )


def _recommended_next_operator_move(packet: Mapping[str, Any]) -> str:
    return str(packet.get("next_required_human_action") or "REVIEW_RUNBOOK")


def _recommended_next_engineering_move(input_summary: Mapping[str, Any]) -> str:
    if input_summary.get("r255_actual_submit_gate_found") is not True:
        return "Record an R255 dry preview before using the R256 operator runbook."
    return "Create R257 final pre-submit arming drill; still no real submit from Codex."


def _do_not_run_yet() -> list[str]:
    return [
        "unreviewed live submit",
        "duplicate live submit",
        "manual submit without regeneration if timestamp stale",
        "manual submit without live controls arming review",
        "manual submit without reconciliation plan",
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
