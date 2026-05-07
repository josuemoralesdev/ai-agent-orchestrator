"""Record-only operator action loop for Hammer Radar.

This module normalizes operator text, records the result, and never places
orders or enables live execution.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
OPERATOR_ACTIONS_FILENAME = "operator_actions.ndjson"
LIVE_BLOCK_REASON = (
    "Live execution is disabled. Exact future live approval requires a signal_id "
    "and all live safety gates."
)
LIVE_APPROVE_EXACT_REASON = "exact live approval request accepted for gate evaluation only"
LIVE_APPROVE_REJECT_REASON = "LIVE APPROVE requires an exact signal_id"
FIRST_LIVE_RUNBOOK_REASON = "first protected tiny-live runbook check accepted; no execution or enablement"

SAFE_ACTIONS = {
    "watch",
    "paper_approve",
    "ignore",
    "show_latest",
    "show_alerts",
    "show_candidate",
    "first_live_check",
    "telegram_operator_command",
}

_LEVERAGE_RE = re.compile(r"\b(?:[2-9]\d*x|[1-9]\d+\s*x|leverage|leveraged|increase\s+leverage)\b")
_LIVE_APPROVE_RE = re.compile(r"^live approve(?:\s+(?P<signal_id>\S+))?$", re.IGNORECASE)


def parse_operator_action(text: str | None, *, signal_id: str | None = None) -> dict[str, Any]:
    raw_text = (text or "").strip()
    normalized_text = " ".join(raw_text.lower().replace("_", " ").split())

    if not normalized_text:
        return _parse_result(
            raw_text=raw_text,
            normalized_action="unknown",
            result_status="REJECTED",
            reason="operator action text is required",
            signal_id=signal_id,
        )

    live_approve_match = _LIVE_APPROVE_RE.match(raw_text)
    if live_approve_match:
        supplied_signal_id = live_approve_match.group("signal_id")
        if _is_exact_live_approval_signal_id(supplied_signal_id):
            return _parse_result(
                raw_text=raw_text,
                normalized_action="live_approve_exact",
                result_status="ACCEPTED",
                reason=LIVE_APPROVE_EXACT_REASON,
                signal_id=supplied_signal_id,
            )
        return _parse_result(
            raw_text=raw_text,
            normalized_action="blocked_live_command",
            result_status="REJECTED",
            reason=LIVE_APPROVE_REJECT_REASON,
            signal_id=signal_id,
        )

    if _is_live_execution_command(normalized_text):
        return _parse_result(
            raw_text=raw_text,
            normalized_action="blocked_live_command",
            result_status="BLOCKED",
            reason=LIVE_BLOCK_REASON,
            signal_id=signal_id,
        )

    telegram_commands = {
        "help",
        "first live profile",
        "first live status",
        "first live attempts",
        "first live attempt",
        "first live dry run",
        "first live mock",
        "first live execute",
        "first live readiness",
        "first live caps",
        "first live funds",
        "first live adapter",
        "first live readiness checks",
        "first live adapter check",
        "first live ladder adapter",
        "first live protective adapter",
        "first live no naked entry",
        "first live adapter checks",
        "first live ladder check",
        "first live ladder plan",
        "first live ladder payload",
        "first live ladder checks",
        "first live challenge",
        "first live begins",
        "first live preview",
        "first live intent",
        "first live rehearsal",
        "first live arming",
        "first live gate",
        "first live executions",
        "live transport",
        "live transport check",
        "live transport attempts",
        "live runbook",
        "live blockers",
        "live arming runbook",
        "live arming runbooks",
        "live begins",
        "live preview",
        "live intent",
        "live intents",
        "live rehearsal",
        "live rehearsals",
        "live arming",
        "live arming checks",
        "approval challenge",
        "live preflight",
        "promotion status",
        "connector status",
        "protective status",
        "readiness status",
        "paper only",
        "reject",
    }
    if normalized_text in {"first live check", "first live runbook", "first live evaluate"}:
        return _parse_result(
            raw_text=raw_text,
            normalized_action="first_live_check",
            result_status="ACCEPTED",
            reason=FIRST_LIVE_RUNBOOK_REASON,
            signal_id=signal_id,
        )
    if normalized_text == "yes" or normalized_text.startswith("yes "):
        return _parse_result(
            raw_text=raw_text,
            normalized_action="telegram_operator_command",
            result_status="ACCEPTED" if normalized_text.startswith("yes ") else "REJECTED",
            reason="Telegram challenge reply is handled by the inbound command bridge",
            signal_id=signal_id,
        )
    if normalized_text in telegram_commands:
        return _parse_result(
            raw_text=raw_text,
            normalized_action="telegram_operator_command",
            result_status="ACCEPTED",
            reason="Telegram operator command accepted for bridge handling only",
            signal_id=signal_id,
        )

    if normalized_text == "watch":
        action = "watch"
    elif normalized_text in {"paper approve", "approve paper", "paper_approve"}:
        action = "paper_approve"
    elif normalized_text == "ignore":
        action = "ignore"
    elif normalized_text in {"show latest", "latest"}:
        action = "show_latest"
    elif normalized_text in {"show alerts", "alerts"}:
        action = "show_alerts"
    elif normalized_text.startswith("show candidate"):
        action = "show_candidate"
        supplied_signal_id = normalized_text.removeprefix("show candidate").strip()
        if supplied_signal_id and signal_id is None:
            signal_id = supplied_signal_id
    else:
        return _parse_result(
            raw_text=raw_text,
            normalized_action="unknown",
            result_status="REJECTED",
            reason="unknown operator action",
            signal_id=signal_id,
        )

    return _parse_result(
        raw_text=raw_text,
        normalized_action=action,
        result_status="ACCEPTED",
        reason="record-only operator action accepted",
        signal_id=signal_id,
    )


def build_operator_action_record(
    *,
    text: str | None,
    source: str = "approval_api",
    signal_id: str | None = None,
    alert_id: str | None = None,
    candidate_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parsed = parse_operator_action(text, signal_id=signal_id)
    return {
        "action_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "source": source,
        "raw_text": parsed["raw_text"],
        "normalized_action": parsed["normalized_action"],
        "signal_id": parsed.get("signal_id"),
        "alert_id": alert_id,
        "candidate_snapshot": candidate_snapshot,
        "result_status": parsed["result_status"],
        "reason": parsed["reason"],
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def append_operator_action(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = operator_actions_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_operator_actions(
    *,
    limit: int = 50,
    action_id: str | None = None,
    signal_id: str | None = None,
    log_dir: str | Path,
) -> list[dict[str, Any]]:
    path = operator_actions_path(log_dir)
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if action_id is not None and record.get("action_id") != action_id:
                continue
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            records.append(record)

    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def operator_actions_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / OPERATOR_ACTIONS_FILENAME


def _is_live_execution_command(normalized_text: str) -> bool:
    blocked_phrases = {
        "trade now live",
        "open live",
        "buy now",
        "sell now",
        "market buy",
        "market sell",
        "live buy",
        "live sell",
        "execute live",
        "approve live",
    }
    return any(phrase in normalized_text for phrase in blocked_phrases) or bool(_LEVERAGE_RE.search(normalized_text))


def _is_exact_live_approval_signal_id(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    if lowered in {"latest", "all"}:
        return False
    parts = value.split("|")
    if len(parts) != 4:
        return False
    symbol, timeframe, direction, timestamp = parts
    if not symbol or not timeframe or direction not in {"long", "short"}:
        return False
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _parse_result(
    *,
    raw_text: str,
    normalized_action: str,
    result_status: str,
    reason: str,
    signal_id: str | None,
) -> dict[str, Any]:
    return {
        "raw_text": raw_text,
        "normalized_action": normalized_action,
        "signal_id": signal_id,
        "result_status": result_status,
        "reason": reason,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }
