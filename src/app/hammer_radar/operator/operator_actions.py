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

SAFE_ACTIONS = {
    "watch",
    "paper_approve",
    "ignore",
    "show_latest",
    "show_alerts",
    "show_candidate",
}

_LEVERAGE_RE = re.compile(r"\b(?:[2-9]\d*x|[1-9]\d+\s*x|leverage|leveraged|increase\s+leverage)\b")


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

    if _is_live_execution_command(normalized_text):
        return _parse_result(
            raw_text=raw_text,
            normalized_action="blocked_live_command",
            result_status="BLOCKED",
            reason=LIVE_BLOCK_REASON,
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
