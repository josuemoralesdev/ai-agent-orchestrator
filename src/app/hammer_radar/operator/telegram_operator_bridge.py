"""Inbound Telegram-style operator command bridge.

The bridge is record-only. It returns Telegram-compatible status text and never
places orders, flips env switches, restarts services, or calls Binance.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution.binance_futures_connector import build_connector_status, build_protective_status
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_runbook import build_first_live_runbook, evaluate_first_live_runbook
from src.app.hammer_radar.operator.live_begins import evaluate_and_record_live_begins, format_live_begins_operator_message
from src.app.hammer_radar.operator.live_approval import evaluate_live_approval_request
from src.app.hammer_radar.operator.live_execution_preview import (
    evaluate_and_record_live_execution_preview,
    format_live_execution_preview_operator_message,
)
from src.app.hammer_radar.operator.live_execution_intent import (
    create_live_execution_intent,
    format_live_execution_intent_operator_message,
    format_live_execution_intents_operator_message,
    list_live_execution_intents,
)
from src.app.hammer_radar.operator.live_executor_rehearsal import (
    create_live_executor_rehearsal,
    format_live_executor_rehearsal_operator_message,
    format_live_executor_rehearsals_operator_message,
    list_live_executor_rehearsals,
)
from src.app.hammer_radar.operator.live_arming_checklist import (
    evaluate_and_record_live_arming_check,
    format_live_arming_checks_operator_message,
    format_live_arming_operator_message,
    list_live_arming_checks,
)
from src.app.hammer_radar.operator.first_live_execution_gate import (
    evaluate_and_record_first_live_execution_gate,
    format_first_live_execution_gate_operator_message,
    format_first_live_execution_gates_operator_message,
    list_first_live_execution_gates,
)
from src.app.hammer_radar.operator.first_live_adapter_verification import (
    build_first_live_adapter_status,
    evaluate_and_record_first_live_adapter_check,
    format_first_live_adapter_checks_operator_message,
    format_first_live_adapter_operator_message,
    list_first_live_adapter_checks,
)
from src.app.hammer_radar.operator.first_live_readiness import (
    build_first_live_readiness_status,
    evaluate_and_record_first_live_readiness,
    format_first_live_readiness_checks_operator_message,
    format_first_live_readiness_operator_message,
    list_first_live_readiness_checks,
)
from src.app.hammer_radar.operator.first_live_ladder_submit_adapter import (
    build_first_live_ladder_submit_status,
    evaluate_and_record_first_live_ladder_submit_check,
    format_first_live_ladder_submit_checks_operator_message,
    format_first_live_ladder_submit_operator_message,
    list_first_live_ladder_submit_checks,
)
from src.app.hammer_radar.operator.first_live_protective_adapter import (
    build_first_live_protective_status,
    evaluate_and_record_first_live_protective_check,
    format_first_live_protective_checks_operator_message,
    format_first_live_protective_operator_message,
    list_first_live_protective_checks,
)
from src.app.hammer_radar.operator.first_live_test_order_gate import (
    build_first_live_test_order_status,
    evaluate_and_record_first_live_test_order_check,
    format_first_live_test_order_checks_operator_message,
    format_first_live_test_order_gate_operator_message,
    list_first_live_test_order_checks,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import (
    build_first_live_chain_status,
    evaluate_and_record_first_live_chain_check,
    format_first_live_chain_checks_operator_message,
    format_first_live_chain_operator_message,
    list_first_live_chain_checks,
)
from src.app.hammer_radar.operator.first_live_candidate_queue import (
    build_first_live_candidate_queue,
    clear_selected_signal,
    format_first_live_candidates_operator_message,
    format_first_live_selected_operator_message,
    select_first_live_candidate,
)
from src.app.hammer_radar.operator.first_microscopic_live_attempt import (
    build_first_microscopic_live_profile,
    build_first_microscopic_live_status,
    check_first_microscopic_live_attempt,
    execute_first_microscopic_live_attempt,
    format_first_microscopic_live_attempt_operator_message,
    format_first_microscopic_live_attempts_operator_message,
    list_first_microscopic_live_attempts,
)
from src.app.hammer_radar.operator.live_executor_transport import (
    attempt_live_executor_transport,
    check_live_executor_transport,
    format_live_executor_transport_attempts_operator_message,
    format_live_executor_transport_operator_message,
    list_live_executor_transport_attempts,
)
from src.app.hammer_radar.operator.live_arming_runbook import (
    build_live_arming_runbook,
    evaluate_and_record_live_arming_runbook,
    format_live_arming_runbook_operator_message,
    format_live_arming_runbooks_operator_message,
    format_live_blockers_operator_message,
    list_live_arming_runbooks,
)
from src.app.hammer_radar.operator.live_preflight import build_promoted_strategy_preflight
from src.app.hammer_radar.operator.notification_watcher import load_alert_records
from src.app.hammer_radar.operator.operator_actions import (
    LIVE_APPROVE_REJECT_REASON,
    append_operator_action,
    build_operator_action_record,
    parse_operator_action,
)
from src.app.hammer_radar.operator.readiness import build_readiness_payload
from src.app.hammer_radar.operator.strategy_promotion_watcher import build_strategy_promotion_status
from src.app.hammer_radar.operator.telegram_approval_challenge import (
    create_first_live_approval_challenge,
    process_first_live_challenge_reply,
)
from src.app.hammer_radar.operator.trade_ticket import build_trade_ticket

COMMANDS_FILENAME = "telegram_operator_commands.ndjson"

HELP_COMMANDS = [
    "HELP",
    "FIRST LIVE PROFILE",
    "FIRST LIVE STATUS",
    "FIRST LIVE CHECK",
    "FIRST LIVE ATTEMPT <executor_rehearsal_id>",
    "FIRST LIVE DRY RUN <executor_rehearsal_id>",
    "FIRST LIVE MOCK <executor_rehearsal_id>",
    "FIRST LIVE EXECUTE <executor_rehearsal_id> FINAL",
    "FIRST LIVE ATTEMPTS",
    "FIRST LIVE READINESS",
    "FIRST LIVE CAPS",
    "FIRST LIVE FUNDS",
    "FIRST LIVE ADAPTER",
    "FIRST LIVE READINESS CHECKS",
    "FIRST LIVE ADAPTER CHECK",
    "FIRST LIVE LADDER ADAPTER",
    "FIRST LIVE PROTECTIVE ADAPTER",
    "FIRST LIVE NO NAKED ENTRY",
    "FIRST LIVE ADAPTER CHECKS",
    "FIRST LIVE LADDER CHECK",
    "FIRST LIVE LADDER PLAN",
    "FIRST LIVE LADDER PAYLOAD",
    "FIRST LIVE LADDER CHECKS",
    "FIRST LIVE PROTECTIVE CHECK",
    "FIRST LIVE STOP CHECK",
    "FIRST LIVE TAKE PROFIT CHECK",
    "FIRST LIVE PROTECTIVE PAYLOAD",
    "FIRST LIVE PROTECTIVE CHECKS",
    "FIRST LIVE TEST ORDER <executor_rehearsal_id>",
    "FIRST LIVE TEST ORDER CHECK <executor_rehearsal_id>",
    "FIRST LIVE EXACT CHAIN",
    "FIRST LIVE PAYLOAD READINESS",
    "FIRST LIVE TEST ORDER CHECKS",
    "FIRST LIVE CHAIN",
    "FIRST LIVE NEXT",
    "FIRST LIVE CANDIDATES",
    "FIRST LIVE SELECT <signal_id>",
    "FIRST LIVE SELECTED",
    "FIRST LIVE CLEAR",
    "FIRST LIVE RUNBOOK",
    "FIRST LIVE SEQUENCE",
    "FIRST LIVE CHAIN CHECKS",
    "FIRST LIVE EVALUATE",
    "FIRST LIVE CHALLENGE",
    "APPROVAL CHALLENGE",
    "LIVE BEGINS",
    "FIRST LIVE BEGINS",
    "LIVE PREVIEW",
    "FIRST LIVE PREVIEW",
    "LIVE INTENT <signal_id>",
    "FIRST LIVE INTENT <signal_id>",
    "LIVE INTENTS",
    "LIVE REHEARSAL <execution_intent_id>",
    "LIVE REHEARSAL SIGNAL <signal_id>",
    "FIRST LIVE REHEARSAL <execution_intent_id>",
    "LIVE REHEARSALS",
    "LIVE ARMING",
    "FIRST LIVE ARMING",
    "LIVE ARMING CHECKS",
    "FIRST LIVE GATE",
    "FIRST LIVE GATE <signal_id>",
    "FIRST LIVE GATE INTENT <execution_intent_id>",
    "FIRST LIVE GATE REHEARSAL <executor_rehearsal_id>",
    "FIRST LIVE EXECUTE <executor_rehearsal_id> FINAL",
    "FIRST LIVE EXECUTIONS",
    "LIVE TRANSPORT",
    "LIVE TRANSPORT CHECK",
    "LIVE TRANSPORT ATTEMPT <executor_rehearsal_id>",
    "LIVE TRANSPORT DRY RUN <executor_rehearsal_id>",
    "LIVE TRANSPORT MOCK <executor_rehearsal_id>",
    "LIVE TRANSPORT LIVE <executor_rehearsal_id> FINAL",
    "LIVE TRANSPORT ATTEMPTS",
    "LIVE RUNBOOK",
    "LIVE BLOCKERS",
    "LIVE ARMING RUNBOOK",
    "LIVE ARMING RUNBOOKS",
    "LIVE PREFLIGHT",
    "PROMOTION STATUS",
    "CONNECTOR STATUS",
    "PROTECTIVE STATUS",
    "READINESS STATUS",
    "APPROVE PAPER",
    "PAPER ONLY",
    "WATCH",
    "REJECT",
    "YES <challenge_code>",
]


def handle_telegram_operator_command(
    *,
    text: str | None,
    source: str = "telegram",
    chat_id: str | None = None,
    update_id: int | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    raw_text = (text or "").strip()
    normalized = " ".join(raw_text.upper().split())
    result = _dispatch_command(raw_text=raw_text, normalized=normalized, source=source, log_dir=resolved_log_dir)
    record = _command_record(
        raw_text=raw_text,
        source=source,
        chat_id=chat_id,
        update_id=update_id,
        result=result,
    )
    append_telegram_operator_command(record, log_dir=resolved_log_dir)
    result["command"] = record
    result["telegram_operator_commands_path"] = str(telegram_operator_commands_path(resolved_log_dir))
    return result


def append_telegram_operator_command(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = telegram_operator_commands_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_telegram_operator_commands(
    *,
    limit: int = 50,
    command_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = telegram_operator_commands_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if command_id is not None and record.get("command_id") != command_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def telegram_operator_commands_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / COMMANDS_FILENAME


def _dispatch_command(*, raw_text: str, normalized: str, source: str, log_dir: Path) -> dict[str, Any]:
    if normalized == "HELP":
        return _result("help", "ACCEPTED", "Available commands: " + ", ".join(HELP_COMMANDS))
    if normalized == "FIRST LIVE PROFILE":
        payload = build_first_microscopic_live_profile(log_dir=log_dir)
        return _result(
            "first_microscopic_live_profile",
            str(payload.get("status") or "BLOCKED"),
            format_first_microscopic_live_attempt_operator_message(payload),
            payload={"first_microscopic_live_attempt": payload},
            signal_id=payload.get("signal_id"),
        )
    if normalized == "FIRST LIVE STATUS":
        payload = build_first_microscopic_live_status(log_dir=log_dir)
        return _result(
            "first_microscopic_live_status",
            str(payload.get("status") or "BLOCKED"),
            format_first_microscopic_live_attempt_operator_message(payload),
            payload={"first_microscopic_live_attempt": payload},
            signal_id=payload.get("signal_id"),
        )
    if normalized == "FIRST LIVE CHECK":
        payload = check_first_microscopic_live_attempt(log_dir=log_dir)
        return _result(
            "first_microscopic_live_check",
            "ACCEPTED",
            format_first_microscopic_live_attempt_operator_message(payload),
            payload={"first_microscopic_live_attempt": payload},
            signal_id=payload.get("signal_id"),
        )
    if normalized == "FIRST LIVE READINESS":
        payload = evaluate_and_record_first_live_readiness(log_dir=log_dir)
        return _result(
            "first_live_readiness",
            "ACCEPTED",
            format_first_live_readiness_operator_message(payload),
            payload={"first_live_readiness": payload},
        )
    if normalized == "FIRST LIVE CAPS":
        payload = build_first_live_readiness_status(log_dir=log_dir)
        return _result(
            "first_live_caps",
            "ACCEPTED",
            format_first_live_readiness_operator_message(payload, section="caps"),
            payload={"first_live_readiness": payload},
        )
    if normalized == "FIRST LIVE FUNDS":
        payload = build_first_live_readiness_status(log_dir=log_dir)
        return _result(
            "first_live_funds",
            "ACCEPTED",
            format_first_live_readiness_operator_message(payload, section="funds"),
            payload={"first_live_readiness": payload},
        )
    if normalized == "FIRST LIVE ADAPTER":
        payload = build_first_live_readiness_status(log_dir=log_dir)
        return _result(
            "first_live_adapter",
            "ACCEPTED",
            format_first_live_readiness_operator_message(payload, section="adapter"),
            payload={"first_live_readiness": payload},
        )
    if normalized == "FIRST LIVE READINESS CHECKS":
        payload = list_first_live_readiness_checks(log_dir=log_dir)
        return _result(
            "first_live_readiness_checks",
            "ACCEPTED",
            format_first_live_readiness_checks_operator_message(payload),
            payload={"first_live_readiness_checks": payload},
        )
    if normalized == "FIRST LIVE ADAPTER CHECK":
        payload = evaluate_and_record_first_live_adapter_check(log_dir=log_dir)
        return _result(
            "first_live_adapter_check",
            "ACCEPTED",
            format_first_live_adapter_operator_message(payload),
            payload={"first_live_adapter_verification": payload},
        )
    if normalized == "FIRST LIVE LADDER ADAPTER":
        payload = build_first_live_adapter_status(log_dir=log_dir)
        return _result(
            "first_live_ladder_adapter",
            "ACCEPTED",
            format_first_live_adapter_operator_message(payload, section="ladder"),
            payload={"first_live_adapter_verification": payload},
        )
    if normalized == "FIRST LIVE PROTECTIVE ADAPTER":
        payload = build_first_live_adapter_status(log_dir=log_dir)
        return _result(
            "first_live_protective_adapter",
            "ACCEPTED",
            format_first_live_adapter_operator_message(payload, section="protective"),
            payload={"first_live_adapter_verification": payload},
        )
    if normalized == "FIRST LIVE NO NAKED ENTRY":
        payload = build_first_live_adapter_status(log_dir=log_dir)
        return _result(
            "first_live_no_naked_entry",
            "ACCEPTED",
            format_first_live_adapter_operator_message(payload, section="no_naked_entry"),
            payload={"first_live_adapter_verification": payload},
        )
    if normalized == "FIRST LIVE ADAPTER CHECKS":
        payload = list_first_live_adapter_checks(log_dir=log_dir)
        return _result(
            "first_live_adapter_checks",
            "ACCEPTED",
            format_first_live_adapter_checks_operator_message(payload),
            payload={"first_live_adapter_checks": payload},
        )
    if normalized == "FIRST LIVE LADDER CHECK":
        payload = evaluate_and_record_first_live_ladder_submit_check(log_dir=log_dir)
        return _result(
            "first_live_ladder_check",
            "ACCEPTED",
            format_first_live_ladder_submit_operator_message(payload),
            payload={"first_live_ladder_submit": payload},
        )
    if normalized == "FIRST LIVE LADDER PLAN":
        payload = build_first_live_ladder_submit_status(log_dir=log_dir)
        return _result(
            "first_live_ladder_plan",
            "ACCEPTED",
            format_first_live_ladder_submit_operator_message(payload, section="plan"),
            payload={"first_live_ladder_submit": payload},
        )
    if normalized == "FIRST LIVE LADDER PAYLOAD":
        payload = build_first_live_ladder_submit_status(log_dir=log_dir)
        return _result(
            "first_live_ladder_payload",
            "ACCEPTED",
            format_first_live_ladder_submit_operator_message(payload, section="payload"),
            payload={"first_live_ladder_submit": payload},
        )
    if normalized == "FIRST LIVE LADDER CHECKS":
        payload = list_first_live_ladder_submit_checks(log_dir=log_dir)
        return _result(
            "first_live_ladder_checks",
            "ACCEPTED",
            format_first_live_ladder_submit_checks_operator_message(payload),
            payload={"first_live_ladder_submit_checks": payload},
        )
    if normalized == "FIRST LIVE PROTECTIVE CHECK":
        payload = evaluate_and_record_first_live_protective_check(log_dir=log_dir)
        return _result(
            "first_live_protective_check",
            "ACCEPTED",
            format_first_live_protective_operator_message(payload),
            payload={"first_live_protective": payload},
        )
    if normalized == "FIRST LIVE STOP CHECK":
        payload = build_first_live_protective_status(log_dir=log_dir)
        return _result(
            "first_live_stop_check",
            "ACCEPTED",
            format_first_live_protective_operator_message(payload, section="stop"),
            payload={"first_live_protective": payload},
        )
    if normalized == "FIRST LIVE TAKE PROFIT CHECK":
        payload = build_first_live_protective_status(log_dir=log_dir)
        return _result(
            "first_live_take_profit_check",
            "ACCEPTED",
            format_first_live_protective_operator_message(payload, section="take_profit"),
            payload={"first_live_protective": payload},
        )
    if normalized == "FIRST LIVE PROTECTIVE PAYLOAD":
        payload = build_first_live_protective_status(log_dir=log_dir)
        return _result(
            "first_live_protective_payload",
            "ACCEPTED",
            format_first_live_protective_operator_message(payload, section="payload"),
            payload={"first_live_protective": payload},
        )
    if normalized == "FIRST LIVE PROTECTIVE CHECKS":
        payload = list_first_live_protective_checks(log_dir=log_dir)
        return _result(
            "first_live_protective_checks",
            "ACCEPTED",
            format_first_live_protective_checks_operator_message(payload),
            payload={"first_live_protective_checks": payload},
        )
    if normalized == "LIVE APPROVE" or normalized.startswith("LIVE APPROVE "):
        return _handle_live_approve(raw_text=raw_text, source=source, log_dir=log_dir)
    if normalized == "FIRST LIVE CHAIN CHECKS":
        payload = list_first_live_chain_checks(log_dir=log_dir)
        return _result(
            "first_live_chain_checks",
            "ACCEPTED",
            format_first_live_chain_checks_operator_message(payload),
            payload={"first_live_chain_checks": payload},
        )
    if normalized == "FIRST LIVE CANDIDATES":
        payload = build_first_live_candidate_queue(log_dir=log_dir)
        return _result(
            "first_live_candidates",
            "ACCEPTED",
            format_first_live_candidates_operator_message(payload),
            payload={"first_live_candidates": payload},
            signal_id=payload.get("selected_signal_id"),
            performance=payload.get("performance") if isinstance(payload.get("performance"), dict) else None,
            next_action=payload.get("recommended_next") if isinstance(payload.get("recommended_next"), dict) else None,
        )
    if normalized == "FIRST LIVE SELECTED":
        payload = build_first_live_candidate_queue(log_dir=log_dir)
        return _result(
            "first_live_selected",
            "ACCEPTED",
            format_first_live_selected_operator_message(payload),
            payload={"first_live_candidates": payload},
            signal_id=payload.get("selected_signal_id"),
            performance=payload.get("performance") if isinstance(payload.get("performance"), dict) else None,
            next_action=payload.get("recommended_next") if isinstance(payload.get("recommended_next"), dict) else None,
        )
    if normalized == "FIRST LIVE CLEAR":
        payload = clear_selected_signal(log_dir=log_dir, source=source, reason="telegram clear")
        return _result(
            "first_live_clear",
            "ACCEPTED",
            "R71 first-live selection cleared. No order placed. real_order_placed=false.",
            payload={"first_live_candidate_clear": payload},
        )
    if normalized == "FIRST LIVE SELECT" or normalized.startswith("FIRST LIVE SELECT "):
        parts = raw_text.split(maxsplit=3)
        signal_id = parts[3].strip() if len(parts) == 4 else None
        payload = select_first_live_candidate(signal_id=signal_id, log_dir=log_dir, source=source, reason="telegram select")
        result_status = "ACCEPTED" if payload.get("status") == "ACCEPTED" else "REJECTED"
        message = (
            f"R71 first-live select: {payload.get('status')} {payload.get('signal_id') or ''}. "
            f"reason: {payload.get('reason')}. No order placed. real_order_placed=false."
        )
        return _result(
            "first_live_select",
            result_status,
            message,
            payload={"first_live_candidate_select": payload},
            signal_id=payload.get("signal_id"),
            reason=payload.get("reason"),
        )
    if normalized == "FIRST LIVE CHAIN":
        payload = evaluate_and_record_first_live_chain_check(log_dir=log_dir)
        return _result(
            "first_live_chain",
            "ACCEPTED",
            format_first_live_chain_operator_message(payload),
            payload={"first_live_chain": payload},
            signal_id=(payload.get("current_signal") or {}).get("signal_id"),
            performance=payload.get("performance") if isinstance(payload.get("performance"), dict) else None,
            next_action=payload.get("next_action") if isinstance(payload.get("next_action"), dict) else None,
        )
    if normalized == "FIRST LIVE NEXT":
        payload = build_first_live_chain_status(log_dir=log_dir)
        return _result(
            "first_live_next",
            "ACCEPTED",
            format_first_live_chain_operator_message(payload, section="next"),
            payload={"first_live_chain": payload},
            signal_id=(payload.get("current_signal") or {}).get("signal_id"),
            performance=payload.get("performance") if isinstance(payload.get("performance"), dict) else None,
            next_action=payload.get("next_action") if isinstance(payload.get("next_action"), dict) else None,
        )
    if normalized in {"FIRST LIVE RUNBOOK", "FIRST LIVE SEQUENCE"}:
        payload = build_first_live_chain_status(log_dir=log_dir)
        return _result(
            "first_live_runbook" if normalized == "FIRST LIVE RUNBOOK" else "first_live_sequence",
            "ACCEPTED",
            format_first_live_chain_operator_message(payload, section="runbook" if normalized == "FIRST LIVE RUNBOOK" else "sequence"),
            payload={"first_live_chain": payload},
            signal_id=(payload.get("current_signal") or {}).get("signal_id"),
            performance=payload.get("performance") if isinstance(payload.get("performance"), dict) else None,
            next_action=payload.get("next_action") if isinstance(payload.get("next_action"), dict) else None,
        )
    if normalized == "FIRST LIVE TEST ORDER CHECKS":
        payload = list_first_live_test_order_checks(log_dir=log_dir)
        return _result(
            "first_live_test_order_checks",
            "ACCEPTED",
            format_first_live_test_order_checks_operator_message(payload),
            payload={"first_live_test_order_checks": payload},
        )
    if normalized == "FIRST LIVE TEST ORDER" or normalized.startswith("FIRST LIVE TEST ORDER "):
        payload = _first_live_test_order_from_command(raw_text=raw_text, normalized=normalized, log_dir=log_dir)
        return _result(
            "first_live_test_order",
            str(payload.get("status") or "BLOCKED"),
            format_first_live_test_order_gate_operator_message(payload),
            payload={"first_live_test_order": payload},
            signal_id=payload.get("signal_id"),
        )
    if normalized == "FIRST LIVE EXACT CHAIN":
        payload = build_first_live_test_order_status(log_dir=log_dir)
        return _result(
            "first_live_exact_chain",
            str(payload.get("status") or "BLOCKED"),
            format_first_live_test_order_gate_operator_message(payload, section="exact_chain"),
            payload={"first_live_test_order": payload},
            signal_id=payload.get("signal_id"),
        )
    if normalized == "FIRST LIVE PAYLOAD READINESS":
        payload = build_first_live_test_order_status(log_dir=log_dir)
        return _result(
            "first_live_payload_readiness",
            str(payload.get("status") or "BLOCKED"),
            format_first_live_test_order_gate_operator_message(payload, section="payload"),
            payload={"first_live_test_order": payload},
            signal_id=payload.get("signal_id"),
        )
    if normalized in {"LIVE RUNBOOK", "LIVE ARMING RUNBOOK"}:
        runbook = evaluate_and_record_live_arming_runbook(log_dir=log_dir)
        return _result(
            "live_arming_runbook",
            "ACCEPTED",
            format_live_arming_runbook_operator_message(runbook),
            payload={"live_arming_runbook": runbook},
            signal_id=runbook.get("latest_signal_id"),
        )
    if normalized == "LIVE BLOCKERS":
        runbook = build_live_arming_runbook(log_dir=log_dir)
        return _result(
            "live_blockers",
            "ACCEPTED",
            format_live_blockers_operator_message(runbook),
            payload={"live_arming_runbook": runbook},
            signal_id=runbook.get("latest_signal_id"),
        )
    if normalized == "LIVE ARMING RUNBOOKS":
        runbooks = list_live_arming_runbooks(log_dir=log_dir)
        return _result(
            "live_arming_runbooks",
            "ACCEPTED",
            format_live_arming_runbooks_operator_message(runbooks),
            payload={"live_arming_runbooks": runbooks},
        )
    if normalized == "FIRST LIVE EVALUATE":
        runbook = evaluate_first_live_runbook(log_dir=log_dir)
        return _result(
            "first_live_evaluate",
            "ACCEPTED",
            f"First live evaluation recorded={runbook.get('recorded')}. {runbook['runbook_status']} / {runbook['gate_decision']}. No order placed.",
            payload={"runbook": runbook},
            signal_id=runbook.get("signal_id"),
        )
    if normalized in {"FIRST LIVE CHALLENGE", "APPROVAL CHALLENGE"}:
        challenge = create_first_live_approval_challenge(log_dir=log_dir)
        return _result(
            "first_live_challenge",
            challenge["result_status"],
            challenge["message"],
            payload={"challenge_response": challenge},
            signal_id=((challenge.get("challenge") or {}).get("signal_id")),
            challenge_id=((challenge.get("challenge") or {}).get("challenge_id")),
        )
    if normalized in {"LIVE BEGINS", "FIRST LIVE BEGINS"}:
        live_begins = evaluate_and_record_live_begins(log_dir=log_dir)
        return _result(
            "live_begins",
            "ACCEPTED",
            format_live_begins_operator_message(live_begins),
            payload={"live_begins": live_begins},
            signal_id=live_begins.get("latest_signal_id"),
        )
    if normalized in {"LIVE PREVIEW", "FIRST LIVE PREVIEW"}:
        preview = evaluate_and_record_live_execution_preview(log_dir=log_dir)
        return _result(
            "live_execution_preview",
            "ACCEPTED",
            format_live_execution_preview_operator_message(preview),
            payload={"live_execution_preview": preview},
            signal_id=preview.get("latest_signal_id"),
        )
    if normalized == "LIVE INTENTS":
        intents = list_live_execution_intents(log_dir=log_dir)
        return _result(
            "live_execution_intents",
            "ACCEPTED",
            format_live_execution_intents_operator_message(intents),
            payload={"live_execution_intents": intents},
        )
    if normalized == "LIVE INTENT" or normalized.startswith("LIVE INTENT "):
        signal_id = raw_text.split(maxsplit=2)[2].strip() if len(raw_text.split(maxsplit=2)) == 3 else None
        intent = create_live_execution_intent(signal_id=signal_id, log_dir=log_dir)
        result_status = "ACCEPTED" if intent.get("status") == "INTENT_READY" else str(intent.get("status") or "BLOCKED")
        return _result(
            "live_execution_intent",
            result_status,
            format_live_execution_intent_operator_message(intent),
            payload={"live_execution_intent": intent},
            signal_id=intent.get("signal_id"),
        )
    if normalized == "FIRST LIVE INTENT" or normalized.startswith("FIRST LIVE INTENT "):
        signal_id = raw_text.split(maxsplit=3)[3].strip() if len(raw_text.split(maxsplit=3)) == 4 else None
        intent = create_live_execution_intent(signal_id=signal_id, log_dir=log_dir)
        result_status = "ACCEPTED" if intent.get("status") == "INTENT_READY" else str(intent.get("status") or "BLOCKED")
        return _result(
            "live_execution_intent",
            result_status,
            format_live_execution_intent_operator_message(intent),
            payload={"live_execution_intent": intent},
            signal_id=intent.get("signal_id"),
        )
    if normalized == "LIVE REHEARSALS":
        rehearsals = list_live_executor_rehearsals(log_dir=log_dir)
        return _result(
            "live_executor_rehearsals",
            "ACCEPTED",
            format_live_executor_rehearsals_operator_message(rehearsals),
            payload={"live_executor_rehearsals": rehearsals},
        )
    if normalized == "LIVE REHEARSAL" or normalized.startswith("LIVE REHEARSAL "):
        parts = raw_text.split(maxsplit=3)
        if len(parts) >= 4 and parts[2].upper() == "SIGNAL":
            rehearsal = create_live_executor_rehearsal(signal_id=parts[3].strip(), log_dir=log_dir)
        else:
            intent_id = raw_text.split(maxsplit=2)[2].strip() if len(raw_text.split(maxsplit=2)) == 3 else None
            rehearsal = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=log_dir)
        result_status = "ACCEPTED" if rehearsal.get("status") == "REHEARSAL_READY" else str(rehearsal.get("status") or "BLOCKED")
        return _result(
            "live_executor_rehearsal",
            result_status,
            format_live_executor_rehearsal_operator_message(rehearsal),
            payload={"live_executor_rehearsal": rehearsal},
            signal_id=rehearsal.get("signal_id"),
        )
    if normalized == "FIRST LIVE REHEARSAL" or normalized.startswith("FIRST LIVE REHEARSAL "):
        intent_id = raw_text.split(maxsplit=3)[3].strip() if len(raw_text.split(maxsplit=3)) == 4 else None
        rehearsal = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=log_dir)
        result_status = "ACCEPTED" if rehearsal.get("status") == "REHEARSAL_READY" else str(rehearsal.get("status") or "BLOCKED")
        return _result(
            "live_executor_rehearsal",
            result_status,
            format_live_executor_rehearsal_operator_message(rehearsal),
            payload={"live_executor_rehearsal": rehearsal},
            signal_id=rehearsal.get("signal_id"),
        )
    if normalized in {"LIVE ARMING", "FIRST LIVE ARMING"}:
        arming = evaluate_and_record_live_arming_check(log_dir=log_dir)
        result_status = "ACCEPTED" if arming.get("status") == "ARMING_ALLOWED" else str(arming.get("status") or "BLOCKED")
        return _result(
            "live_arming_check",
            result_status,
            format_live_arming_operator_message(arming),
            payload={"live_arming_check": arming},
            signal_id=arming.get("latest_signal_id"),
        )
    if normalized == "LIVE ARMING CHECKS":
        checks = list_live_arming_checks(log_dir=log_dir)
        return _result(
            "live_arming_checks",
            "ACCEPTED",
            format_live_arming_checks_operator_message(checks),
            payload={"live_arming_checks": checks},
        )
    if normalized == "FIRST LIVE EXECUTIONS":
        gates = list_first_live_execution_gates(log_dir=log_dir)
        return _result(
            "first_live_execution_gates",
            "ACCEPTED",
            format_first_live_execution_gates_operator_message(gates),
            payload={"first_live_execution_gates": gates},
        )
    if normalized == "FIRST LIVE ATTEMPTS":
        attempts = list_first_microscopic_live_attempts(log_dir=log_dir)
        return _result(
            "first_microscopic_live_attempts",
            "ACCEPTED",
            format_first_microscopic_live_attempts_operator_message(attempts),
            payload={"first_microscopic_live_attempts": attempts},
        )
    if normalized == "FIRST LIVE ATTEMPT" or normalized.startswith("FIRST LIVE ATTEMPT "):
        attempt = _first_microscopic_attempt_from_command(raw_text=raw_text, normalized=normalized, log_dir=log_dir, mode="DRY_RUN")
        result_status = "ACCEPTED" if attempt.get("status") in {"DRY_RUN_RECORDED", "MOCK_RECORDED"} else str(attempt.get("status") or "BLOCKED")
        return _result(
            "first_microscopic_live_attempt",
            result_status,
            format_first_microscopic_live_attempt_operator_message(attempt),
            payload={"first_microscopic_live_attempt": attempt},
            signal_id=attempt.get("signal_id"),
        )
    if normalized == "FIRST LIVE DRY RUN" or normalized.startswith("FIRST LIVE DRY RUN "):
        attempt = _first_microscopic_attempt_from_command(raw_text=raw_text, normalized=normalized, log_dir=log_dir, mode="DRY_RUN")
        result_status = "ACCEPTED" if attempt.get("status") == "DRY_RUN_RECORDED" else str(attempt.get("status") or "BLOCKED")
        return _result(
            "first_microscopic_live_attempt",
            result_status,
            format_first_microscopic_live_attempt_operator_message(attempt),
            payload={"first_microscopic_live_attempt": attempt},
            signal_id=attempt.get("signal_id"),
        )
    if normalized == "FIRST LIVE MOCK" or normalized.startswith("FIRST LIVE MOCK "):
        attempt = _first_microscopic_attempt_from_command(raw_text=raw_text, normalized=normalized, log_dir=log_dir, mode="MOCK")
        result_status = "ACCEPTED" if attempt.get("status") == "MOCK_RECORDED" else str(attempt.get("status") or "BLOCKED")
        return _result(
            "first_microscopic_live_attempt",
            result_status,
            format_first_microscopic_live_attempt_operator_message(attempt),
            payload={"first_microscopic_live_attempt": attempt},
            signal_id=attempt.get("signal_id"),
        )
    if normalized == "FIRST LIVE EXECUTE" or normalized.startswith("FIRST LIVE EXECUTE "):
        attempt = _first_microscopic_live_execute_from_command(raw_text=raw_text, normalized=normalized, log_dir=log_dir)
        if attempt.get("status") == "LIVE_ORDER_PLACED":
            result_status = "ACCEPTED"
        elif attempt.get("status") == "REJECTED":
            result_status = "REJECTED"
        else:
            result_status = "BLOCKED"
        return _result(
            "first_microscopic_live_attempt",
            result_status,
            format_first_microscopic_live_attempt_operator_message(attempt),
            payload={"first_microscopic_live_attempt": attempt},
            signal_id=attempt.get("signal_id"),
        )
    if normalized == "FIRST LIVE GATE" or normalized.startswith("FIRST LIVE GATE "):
        gate = _first_live_gate_from_command(raw_text=raw_text, normalized=normalized, log_dir=log_dir)
        result_status = "ACCEPTED" if gate.get("status") == "EXECUTION_GATE_READY" else str(gate.get("status") or "BLOCKED")
        return _result(
            "first_live_execution_gate",
            result_status,
            format_first_live_execution_gate_operator_message(gate),
            payload={"first_live_execution_gate": gate},
            signal_id=gate.get("signal_id"),
        )
    if normalized == "LIVE TRANSPORT ATTEMPTS":
        attempts = list_live_executor_transport_attempts(log_dir=log_dir)
        return _result(
            "live_executor_transport_attempts",
            "ACCEPTED",
            format_live_executor_transport_attempts_operator_message(attempts),
            payload={"live_executor_transport_attempts": attempts},
        )
    if normalized in {"LIVE TRANSPORT", "LIVE TRANSPORT CHECK"}:
        transport = check_live_executor_transport(log_dir=log_dir)
        return _result(
            "live_executor_transport",
            str(transport.get("status") or "BLOCKED"),
            format_live_executor_transport_operator_message(transport),
            payload={"live_executor_transport": transport},
            signal_id=transport.get("signal_id"),
        )
    if normalized == "LIVE TRANSPORT ATTEMPT" or normalized.startswith("LIVE TRANSPORT ATTEMPT "):
        rehearsal_id = raw_text.split(maxsplit=3)[3].strip() if len(raw_text.split(maxsplit=3)) == 4 else None
        transport = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="DRY_RUN", log_dir=log_dir)
        result_status = "ACCEPTED" if transport.get("status") in {"DRY_RUN_ATTEMPT_RECORDED", "MOCK_ATTEMPT_RECORDED"} else str(transport.get("status") or "BLOCKED")
        return _result(
            "live_executor_transport",
            result_status,
            format_live_executor_transport_operator_message(transport),
            payload={"live_executor_transport": transport},
            signal_id=transport.get("signal_id"),
        )
    if normalized == "LIVE TRANSPORT DRY RUN" or normalized.startswith("LIVE TRANSPORT DRY RUN "):
        rehearsal_id = raw_text.split(maxsplit=4)[4].strip() if len(raw_text.split(maxsplit=4)) == 5 else None
        transport = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="DRY_RUN", log_dir=log_dir)
        result_status = "ACCEPTED" if transport.get("status") == "DRY_RUN_ATTEMPT_RECORDED" else str(transport.get("status") or "BLOCKED")
        return _result(
            "live_executor_transport",
            result_status,
            format_live_executor_transport_operator_message(transport),
            payload={"live_executor_transport": transport},
            signal_id=transport.get("signal_id"),
        )
    if normalized == "LIVE TRANSPORT MOCK" or normalized.startswith("LIVE TRANSPORT MOCK "):
        rehearsal_id = raw_text.split(maxsplit=3)[3].strip() if len(raw_text.split(maxsplit=3)) == 4 else None
        transport = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="MOCK", log_dir=log_dir)
        result_status = "ACCEPTED" if transport.get("status") == "MOCK_ATTEMPT_RECORDED" else str(transport.get("status") or "BLOCKED")
        return _result(
            "live_executor_transport",
            result_status,
            format_live_executor_transport_operator_message(transport),
            payload={"live_executor_transport": transport},
            signal_id=transport.get("signal_id"),
        )
    if normalized == "LIVE TRANSPORT LIVE" or normalized.startswith("LIVE TRANSPORT LIVE "):
        parts = raw_text.split(maxsplit=4)
        rehearsal_id = parts[3].strip() if len(parts) >= 4 else None
        final_confirmation = normalized.endswith(" FINAL")
        if rehearsal_id and rehearsal_id.upper() == "FINAL":
            rehearsal_id = None
        transport = attempt_live_executor_transport(
            executor_rehearsal_id=rehearsal_id,
            transport_mode="LIVE",
            final_confirmation=final_confirmation,
            dry_run=False if final_confirmation else True,
            log_dir=log_dir,
        )
        result_status = "ACCEPTED" if transport.get("status") == "LIVE_READY" else str(transport.get("status") or "BLOCKED")
        return _result(
            "live_executor_transport",
            result_status,
            format_live_executor_transport_operator_message(transport),
            payload={"live_executor_transport": transport},
            signal_id=transport.get("signal_id"),
        )
    if normalized == "LIVE PREFLIGHT":
        preflight = build_promoted_strategy_preflight(log_dir=log_dir)
        message = (
            f"Live preflight: signal_found={preflight.get('matching_fresh_signal_found')}; "
            f"signal_id={preflight.get('candidate_signal_id') or 'none'}; "
            f"required={preflight.get('required_exact_command') or 'n/a'}. No order placed."
        )
        return _result("live_preflight", "ACCEPTED", message, payload={"preflight": preflight}, signal_id=preflight.get("candidate_signal_id"))
    if normalized == "PROMOTION STATUS":
        status = build_strategy_promotion_status(log_dir=log_dir)
        return _result(
            "promotion_status",
            "ACCEPTED",
            f"Promotion: ready={len(status.get('promotion_ready', []))}; near={len(status.get('near_promotion', []))}. No order placed.",
            payload={"promotion_status": status},
        )
    if normalized == "CONNECTOR STATUS":
        status = build_connector_status(log_dir=log_dir)
        return _result(
            "connector_status",
            "ACCEPTED",
            f"Connector: mode={status.get('connector_mode')} readiness={status.get('readiness')} live={status.get('live_execution_enabled')} allow={status.get('allow_live_orders')} kill={status.get('global_kill_switch')} order_placed=false.",
            payload={"connector_status": status},
        )
    if normalized == "PROTECTIVE STATUS":
        status = build_protective_status(log_dir=log_dir)
        return _result(
            "protective_status",
            "ACCEPTED",
            f"Protective: required={status.get('protective_orders_required')} ready={status.get('protective_orders_ready')} mode={status.get('protective_order_mode')}. No order placed.",
            payload={"protective_status": status},
        )
    if normalized == "READINESS STATUS":
        readiness = build_readiness_payload(log_dir=log_dir)
        ticket = build_trade_ticket(log_dir=log_dir)
        return _result(
            "readiness_status",
            "ACCEPTED",
            f"Readiness: {readiness.get('readiness_status')} allowed_now={readiness.get('allowed_now')} fresh_eligible_count={readiness.get('fresh_eligible_count', 0)} ticket={ticket.get('ticket_status', 'UNKNOWN')}. No order placed.",
            payload={"readiness": readiness, "ticket": ticket},
            signal_id=ticket.get("signal_id"),
        )
    if normalized in {"APPROVE PAPER", "PAPER ONLY", "WATCH", "REJECT"}:
        return _handle_paper_intent(normalized=normalized, raw_text=raw_text, source=source, log_dir=log_dir)
    if normalized == "YES" or normalized.startswith("YES "):
        reply = process_first_live_challenge_reply(text=raw_text, source=source, log_dir=log_dir)
        return _result(
            "challenge_reply",
            reply["result_status"],
            reply["message"],
            payload={"challenge_reply": reply},
            signal_id=((reply.get("challenge") or {}).get("signal_id")),
            challenge_id=((reply.get("challenge") or {}).get("challenge_id")),
            reason=reply.get("reason"),
        )
    parsed = parse_operator_action(raw_text)
    if parsed["normalized_action"] == "blocked_live_command":
        return _result("blocked_live_command", parsed["result_status"], parsed["reason"], reason=parsed["reason"])
    return _result("unknown", "REJECTED", "Unknown command. Send HELP for available commands.", reason="unknown command")


def _handle_paper_intent(*, normalized: str, raw_text: str, source: str, log_dir: Path) -> dict[str, Any]:
    candidate = _latest_alert_candidate(log_dir)
    if candidate is None:
        return _result(
            "paper_intent",
            "REJECTED",
            "No unambiguous paper candidate found. Use signal_id or wait for next alert.",
            reason="no unambiguous paper candidate",
        )
    if normalized in {"APPROVE PAPER", "PAPER ONLY"}:
        action_text = "approve paper"
        normalized_action = "paper_approve"
    elif normalized == "WATCH":
        action_text = "watch"
        normalized_action = "watch"
    else:
        action_text = "ignore"
        normalized_action = "ignore"
    record = build_operator_action_record(
        text=action_text,
        source=source,
        signal_id=candidate.get("signal_id"),
        candidate_snapshot=candidate,
    )
    append_operator_action(record, log_dir=log_dir)
    live_note = "Candidate is not live approval eligible. " if candidate.get("decision") != "ELIGIBLE_TINY_LIVE" or candidate.get("direction") == "short" else ""
    return _result(
        normalized_action,
        "ACCEPTED",
        f"Paper/manual intent recorded only. {live_note}No order placed.",
        payload={"operator_action": record, "candidate": candidate},
        signal_id=candidate.get("signal_id"),
    )


def _handle_live_approve(*, raw_text: str, source: str, log_dir: Path) -> dict[str, Any]:
    parts = raw_text.split(maxsplit=2)
    signal_id = parts[2].strip() if len(parts) == 3 else None
    if not signal_id:
        return _result("live_approve", "REJECTED", LIVE_APPROVE_REJECT_REASON, reason=LIVE_APPROVE_REJECT_REASON)
    chain = build_first_live_chain_status(log_dir=log_dir)
    current_signal = chain.get("current_signal") if isinstance(chain.get("current_signal"), dict) else {}
    current_signal_id = current_signal.get("signal_id")
    if not current_signal_id or signal_id != current_signal_id:
        reason = "signal_id does not match current first-live signal"
        return _result(
            "live_approve",
            "REJECTED",
            reason,
            payload={"first_live_chain": chain},
            signal_id=signal_id,
            reason=reason,
            performance=chain.get("performance") if isinstance(chain.get("performance"), dict) else None,
            next_action=chain.get("next_action") if isinstance(chain.get("next_action"), dict) else None,
        )
    if current_signal.get("first_live_fresh") is not True or current_signal.get("fresh") is not True:
        reason = "signal is not fresh enough for first-live approval"
        return _result(
            "live_approve",
            "REJECTED",
            reason,
            payload={"first_live_chain": chain},
            signal_id=signal_id,
            reason=reason,
            performance=chain.get("performance") if isinstance(chain.get("performance"), dict) else None,
            next_action=chain.get("next_action") if isinstance(chain.get("next_action"), dict) else None,
        )
    if current_signal.get("live_candidate_allowed", True) is not True:
        reason = "selected signal is not live-approvable under current policy"
        return _result(
            "live_approve",
            "REJECTED",
            reason,
            payload={"first_live_chain": chain},
            signal_id=signal_id,
            reason=reason,
            performance=chain.get("performance") if isinstance(chain.get("performance"), dict) else None,
            next_action=chain.get("next_action") if isinstance(chain.get("next_action"), dict) else None,
        )
    approval = evaluate_live_approval_request(text=raw_text, source=source, log_dir=log_dir)
    result_status = "ACCEPTED" if approval.get("parse_status") == "ACCEPTED" else str(approval.get("parse_status") or "REJECTED")
    message = (
        f"LIVE APPROVE recorded for {signal_id}. "
        f"approval_gate_status={approval.get('approval_gate_status', 'UNKNOWN')}. "
        "Approval is not execution. No order placed."
    )
    result = _result(
        "live_approve",
        result_status,
        message,
        payload={"live_approval": approval, "first_live_chain": chain},
        signal_id=signal_id,
        reason=approval.get("parse_reason"),
        performance=chain.get("performance") if isinstance(chain.get("performance"), dict) else None,
        next_action=chain.get("next_action") if isinstance(chain.get("next_action"), dict) else None,
    )
    result["signal_id"] = signal_id
    result["request_id"] = approval.get("request_id")
    result["approval_status"] = approval.get("approval_gate_status")
    return result


def _latest_alert_candidate(log_dir: Path) -> dict[str, Any] | None:
    alerts = load_alert_records(limit=1, log_dir=log_dir)
    if not alerts:
        return None
    candidate = alerts[0].get("candidate")
    return dict(candidate) if isinstance(candidate, dict) and candidate.get("signal_id") else None


def _first_microscopic_attempt_from_command(*, raw_text: str, normalized: str, log_dir: Path, mode: str) -> dict[str, Any]:
    if normalized in {"FIRST LIVE ATTEMPT", "FIRST LIVE DRY RUN", "FIRST LIVE MOCK"}:
        rehearsal_id = None
    elif mode == "DRY_RUN" and normalized.startswith("FIRST LIVE DRY RUN "):
        rehearsal_id = raw_text.split(maxsplit=4)[4].strip() if len(raw_text.split(maxsplit=4)) == 5 else None
    elif mode == "MOCK" and normalized.startswith("FIRST LIVE MOCK "):
        rehearsal_id = raw_text.split(maxsplit=3)[3].strip() if len(raw_text.split(maxsplit=3)) == 4 else None
    else:
        rehearsal_id = raw_text.split(maxsplit=3)[3].strip() if len(raw_text.split(maxsplit=3)) == 4 else None
    return execute_first_microscopic_live_attempt(
        executor_rehearsal_id=rehearsal_id,
        transport_mode=mode,
        dry_run=True,
        final_confirmation=False,
        log_dir=log_dir,
    )


def _first_microscopic_live_execute_from_command(*, raw_text: str, normalized: str, log_dir: Path) -> dict[str, Any]:
    parts = raw_text.split(maxsplit=4)
    final_confirmation = normalized.endswith(" FINAL")
    rehearsal_id = parts[3].strip() if len(parts) >= 4 else None
    if rehearsal_id and rehearsal_id.upper() == "FINAL":
        rehearsal_id = None
    return execute_first_microscopic_live_attempt(
        executor_rehearsal_id=rehearsal_id,
        transport_mode="LIVE",
        final_confirmation=final_confirmation,
        dry_run=False if final_confirmation else True,
        log_dir=log_dir,
    )


def _first_live_gate_from_command(*, raw_text: str, normalized: str, log_dir: Path) -> dict[str, Any]:
    parts = raw_text.split(maxsplit=4)
    if normalized == "FIRST LIVE GATE":
        return evaluate_and_record_first_live_execution_gate(log_dir=log_dir)
    if len(parts) >= 5 and parts[3].upper() == "INTENT":
        return evaluate_and_record_first_live_execution_gate(execution_intent_id=parts[4].strip(), log_dir=log_dir)
    if len(parts) >= 5 and parts[3].upper() == "REHEARSAL":
        return evaluate_and_record_first_live_execution_gate(executor_rehearsal_id=parts[4].strip(), log_dir=log_dir)
    signal_id = raw_text.split(maxsplit=3)[3].strip() if len(raw_text.split(maxsplit=3)) == 4 else None
    return evaluate_and_record_first_live_execution_gate(signal_id=signal_id, log_dir=log_dir)


def _first_live_test_order_from_command(*, raw_text: str, normalized: str, log_dir: Path) -> dict[str, Any]:
    if normalized in {"FIRST LIVE TEST ORDER", "FIRST LIVE TEST ORDER CHECK"}:
        rehearsal_id = None
    elif normalized.startswith("FIRST LIVE TEST ORDER CHECK "):
        rehearsal_id = raw_text.split(maxsplit=5)[5].strip() if len(raw_text.split(maxsplit=5)) == 6 else None
    else:
        rehearsal_id = raw_text.split(maxsplit=4)[4].strip() if len(raw_text.split(maxsplit=4)) == 5 else None
    return evaluate_and_record_first_live_test_order_check(
        executor_rehearsal_id=rehearsal_id,
        transport_mode="DRY_RUN",
        dry_run=True,
        final_confirmation=False,
        log_dir=log_dir,
    )


def _first_live_execute_from_command(*, raw_text: str, normalized: str, log_dir: Path) -> dict[str, Any]:
    parts = raw_text.split(maxsplit=4)
    final_confirmation = normalized.endswith(" FINAL")
    rehearsal_id = None
    if len(parts) >= 4:
        rehearsal_id = parts[3].strip()
        if rehearsal_id.upper() == "FINAL":
            rehearsal_id = None
    return evaluate_and_record_first_live_execution_gate(
        executor_rehearsal_id=rehearsal_id,
        final_confirmation=final_confirmation,
        dry_run=True,
        log_dir=log_dir,
    )


def _result(
    normalized_action: str,
    result_status: str,
    message: str,
    *,
    payload: dict[str, Any] | None = None,
    signal_id: str | None = None,
    challenge_id: str | None = None,
    reason: str | None = None,
    performance: dict[str, Any] | None = None,
    next_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "normalized_action": normalized_action,
        "result_status": result_status,
        "reason": reason,
        "message": message,
        "telegram_compatible": {"send_enabled": False, "text": message},
        "payload": payload or {},
        "related_signal_id": signal_id,
        "related_challenge_id": challenge_id,
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "performance": performance or {},
        "next_action": next_action or {},
        "secrets_shown": False,
    }


def _command_record(
    *,
    raw_text: str,
    source: str,
    chat_id: str | None,
    update_id: int | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "command_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "source": source,
        "chat_id_hash": _hash_chat_id(chat_id) if chat_id else None,
        "update_id": update_id,
        "raw_text": raw_text[:500],
        "normalized_action": result["normalized_action"],
        "result_status": result["result_status"],
        "message": result["message"],
        "related_signal_id": result.get("related_signal_id"),
        "related_challenge_id": result.get("related_challenge_id"),
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def _hash_chat_id(chat_id: str | None) -> str | None:
    if not chat_id:
        return None
    return hashlib.sha256(str(chat_id).encode("utf-8")).hexdigest()
