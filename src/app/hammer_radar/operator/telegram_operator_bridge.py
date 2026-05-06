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
from src.app.hammer_radar.operator.live_preflight import build_promoted_strategy_preflight
from src.app.hammer_radar.operator.notification_watcher import load_alert_records
from src.app.hammer_radar.operator.operator_actions import (
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
    "FIRST LIVE CHECK",
    "FIRST LIVE RUNBOOK",
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
    if normalized in {"FIRST LIVE CHECK", "FIRST LIVE RUNBOOK"}:
        runbook = build_first_live_runbook(log_dir=log_dir)
        return _result(
            "first_live_check",
            "ACCEPTED",
            f"First live runbook: {runbook['runbook_status']} / {runbook['gate_decision']}. No order placed.",
            payload={"runbook": runbook},
            signal_id=runbook.get("signal_id"),
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


def _latest_alert_candidate(log_dir: Path) -> dict[str, Any] | None:
    alerts = load_alert_records(limit=1, log_dir=log_dir)
    if not alerts:
        return None
    candidate = alerts[0].get("candidate")
    return dict(candidate) if isinstance(candidate, dict) and candidate.get("signal_id") else None


def _result(
    normalized_action: str,
    result_status: str,
    message: str,
    *,
    payload: dict[str, Any] | None = None,
    signal_id: str | None = None,
    challenge_id: str | None = None,
    reason: str | None = None,
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
