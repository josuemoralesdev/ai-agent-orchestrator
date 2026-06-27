"""R316 human-reviewed multi-lane observation alert send gate.

The gate reuses the R315 preview decision, defaults to preview/mock mode, and
never calls real Telegram in Codex validation.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import (
    CRITICAL_PREVIEW_NO_SEND,
    DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    INFO_PREVIEW_NO_SEND,
    SAFETY as R315_SAFETY,
    WARNING_PREVIEW_NO_SEND,
    build_multi_lane_observation_alerting_preview,
)

EVENT_TYPE = "R316_HUMAN_REVIEWED_OBSERVATION_ALERT_SEND_GATE"
CREATED_BY_PHASE = "R316_HUMAN_REVIEWED_OBSERVATION_ALERT_SEND_GATE"
LEDGER_FILENAME = "multi_lane_observation_alert_send_gate.ndjson"

CONFIRMATION_PHRASE = "SEND MULTI LANE OBSERVATION ALERTS WHEN REQUIRED"

SEND_GATE_PREVIEW_READY = "SEND_GATE_PREVIEW_READY"
SEND_GATE_BLOCKED_NO_ALERT_REQUIRED = "SEND_GATE_BLOCKED_NO_ALERT_REQUIRED"
SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED = "SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED"
SEND_GATE_BLOCKED_RATE_LIMIT = "SEND_GATE_BLOCKED_RATE_LIMIT"
SEND_GATE_MOCK_SENT = "SEND_GATE_MOCK_SENT"
SEND_GATE_REAL_SEND_AVAILABLE_NOT_USED_IN_CODEX = "SEND_GATE_REAL_SEND_AVAILABLE_NOT_USED_IN_CODEX"

RECOMMENDED_R317_DRILL = "R317 Observation Alert Send Gate Operator Drill"
RECOMMENDED_R317_REPAIR = "R317 Alert Send Gate Repair"

SAFETY = {
    **R315_SAFETY,
    "send_gate_preview_only": True,
    "apply_requested": False,
    "confirmation_phrase_matched": False,
    "telegram_sender_mode": "mock",
    "real_telegram_send_called": False,
    "real_telegram_message_sent": False,
}


def build_multi_lane_observation_alert_send_gate(
    *,
    log_dir: str | Path | None = None,
    apply: bool = False,
    confirmation: str | None = None,
    telegram_sender_mode: str = "mock",
    max_age_seconds: int = 180,
    rate_limit_window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    no_write: bool = False,
    write: bool | None = None,
    now: datetime | None = None,
    alert_preview: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    should_write = (not no_write) if write is None else bool(write)
    mode = "real" if telegram_sender_mode == "real" else "mock"
    preview = (
        _sanitize(alert_preview)
        if alert_preview is not None
        else build_multi_lane_observation_alerting_preview(
            log_dir=resolved_log_dir,
            max_age_seconds=max_age_seconds,
            write=False,
            now=generated_at,
            rate_limit_window_seconds=rate_limit_window_seconds,
        )
    )
    alert_required = bool(preview.get("alert_required"))
    severity = str(preview.get("alert_severity") or INFO_PREVIEW_NO_SEND)
    reasons = [str(reason) for reason in preview.get("alert_reasons") or []]
    dedup_key = str(preview.get("dedup_key") or "")
    confirmation_matched = str(confirmation or "") == CONFIRMATION_PHRASE
    rate_limit = evaluate_send_rate_limit(
        log_dir=resolved_log_dir,
        dedup_key=dedup_key,
        now=generated_at,
        rate_limit_window_seconds=rate_limit_window_seconds,
        severity=severity,
    )
    blockers = _send_blockers(
        apply_requested=apply,
        confirmation_phrase_matched=confirmation_matched,
        alert_required=alert_required,
        severity=severity,
        would_suppress_duplicate=bool(rate_limit["would_suppress_duplicate"]),
    )
    status = _send_gate_status(
        apply_requested=apply,
        alert_required=alert_required,
        confirmation_phrase_matched=confirmation_matched,
        severity=severity,
        telegram_sender_mode=mode,
        blockers=blockers,
    )
    mock_sent = status == SEND_GATE_MOCK_SENT
    safety = dict(SAFETY)
    safety.update(
        {
            "send_gate_preview_only": not (apply and mock_sent),
            "apply_requested": bool(apply),
            "confirmation_phrase_matched": confirmation_matched,
            "telegram_sender_mode": mode,
            "telegram_send_called": mock_sent,
            "telegram_message_sent": mock_sent,
            "real_telegram_send_called": False,
            "real_telegram_message_sent": False,
        }
    )
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "send_gate_id": f"r316_multi_lane_observation_alert_send_gate_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        "send_gate_status": status,
        "send_gate_preview_only": safety["send_gate_preview_only"],
        "alert_required": alert_required,
        "alert_severity": severity,
        "alert_reasons": reasons,
        "confirmation_phrase_required": CONFIRMATION_PHRASE,
        "confirmation_phrase_matched": confirmation_matched,
        "apply_requested": bool(apply),
        "telegram_sender_mode": mode,
        "telegram_preview_message": str(preview.get("telegram_preview_message") or ""),
        "operator_console_preview_message": str(preview.get("operator_console_preview_message") or ""),
        "telegram_send_called": mock_sent,
        "telegram_message_sent": mock_sent,
        "real_telegram_send_called": False,
        "real_telegram_message_sent": False,
        "dedup_key": dedup_key,
        "rate_limit_window_seconds": rate_limit_window_seconds,
        "previous_matching_send_generated_at": rate_limit["previous_matching_send_generated_at"],
        "would_suppress_duplicate": rate_limit["would_suppress_duplicate"],
        "would_repeat_critical": rate_limit["would_repeat_critical"],
        "send_blockers": blockers,
        "recommended_next_operator_move": _recommended_next_operator_move(status=status, alert_required=alert_required),
        "recommended_r317_path": _recommended_r317_path(status=status),
        "source_alert_preview": preview,
        "safety": safety,
        **safety,
    }
    safe_payload = _sanitize(payload)
    if should_write:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def evaluate_send_rate_limit(
    *,
    log_dir: str | Path,
    dedup_key: str,
    now: datetime,
    rate_limit_window_seconds: int,
    severity: str,
) -> dict[str, Any]:
    window = max(0, int(rate_limit_window_seconds))
    previous_generated_at: str | None = None
    for record in load_multi_lane_observation_alert_send_gate_records(log_dir=log_dir, limit=200):
        if record.get("dedup_key") != dedup_key:
            continue
        if record.get("telegram_message_sent") is not True:
            continue
        parsed = _parse_datetime(record.get("generated_at"))
        if parsed is None:
            continue
        age = (now - parsed).total_seconds()
        if 0 <= age <= window:
            previous_generated_at = parsed.isoformat()
            break
    duplicate = previous_generated_at is not None
    critical = severity == CRITICAL_PREVIEW_NO_SEND
    actionable = severity in {WARNING_PREVIEW_NO_SEND, CRITICAL_PREVIEW_NO_SEND}
    return {
        "would_suppress_duplicate": bool(duplicate and actionable and not critical),
        "would_repeat_critical": bool(duplicate and critical),
        "previous_matching_send_generated_at": previous_generated_at,
    }


def load_multi_lane_observation_alert_send_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def append_record(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = records_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_alert_send_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def format_alert_send_gate_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R316 HUMAN-REVIEWED OBSERVATION ALERT SEND GATE",
        "",
        "SEND GATE STATUS",
        f"send_gate_status: {payload.get('send_gate_status')}",
        f"send_gate_preview_only: {payload.get('send_gate_preview_only')}",
        f"apply_requested: {payload.get('apply_requested')}",
        "",
        "ALERT SUMMARY",
        f"alert_required: {payload.get('alert_required')}",
        f"alert_severity: {payload.get('alert_severity')}",
        f"alert_reasons: {_join(payload.get('alert_reasons'))}",
        f"dedup_key: {payload.get('dedup_key')}",
        f"would_suppress_duplicate: {payload.get('would_suppress_duplicate')}",
        f"would_repeat_critical: {payload.get('would_repeat_critical')}",
        "",
        "CONFIRMATION STATUS",
        f"confirmation_phrase_required: {payload.get('confirmation_phrase_required')}",
        f"confirmation_phrase_matched: {payload.get('confirmation_phrase_matched')}",
        "",
        "SEND BLOCKERS",
        f"send_blockers: {_join(payload.get('send_blockers'))}",
        "",
        "TELEGRAM PREVIEW MESSAGE",
        str(payload.get("telegram_preview_message") or ""),
        "",
        "MOCK/REAL SEND FLAGS",
        f"telegram_sender_mode: {payload.get('telegram_sender_mode')}",
        f"telegram_send_called: {payload.get('telegram_send_called')}",
        f"telegram_message_sent: {payload.get('telegram_message_sent')}",
        f"real_telegram_send_called: {payload.get('real_telegram_send_called')}",
        f"real_telegram_message_sent: {payload.get('real_telegram_message_sent')}",
        "",
        "SAFETY FLAGS",
    ]
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(
        [
            "",
            "RECOMMENDED NEXT PHASE",
            str(payload.get("recommended_r317_path")),
        ]
    )
    return "\n".join(lines)


def _send_blockers(
    *,
    apply_requested: bool,
    confirmation_phrase_matched: bool,
    alert_required: bool,
    severity: str,
    would_suppress_duplicate: bool,
) -> list[str]:
    blockers: list[str] = []
    if not apply_requested:
        return blockers
    if not confirmation_phrase_matched:
        blockers.append("confirmation_phrase_required")
    if not alert_required:
        blockers.append("alert_required_false")
    if severity == INFO_PREVIEW_NO_SEND:
        blockers.append("info_preview_no_action_never_sends")
    if severity not in {WARNING_PREVIEW_NO_SEND, CRITICAL_PREVIEW_NO_SEND}:
        blockers.append("alert_severity_not_sendable")
    if would_suppress_duplicate:
        blockers.append("rate_limit_duplicate_non_critical")
    return _dedupe(blockers)


def _send_gate_status(
    *,
    apply_requested: bool,
    alert_required: bool,
    confirmation_phrase_matched: bool,
    severity: str,
    telegram_sender_mode: str,
    blockers: Sequence[str],
) -> str:
    if not apply_requested:
        return SEND_GATE_PREVIEW_READY
    if not alert_required or severity == INFO_PREVIEW_NO_SEND:
        return SEND_GATE_BLOCKED_NO_ALERT_REQUIRED
    if not confirmation_phrase_matched:
        return SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED
    if "rate_limit_duplicate_non_critical" in blockers:
        return SEND_GATE_BLOCKED_RATE_LIMIT
    if blockers:
        return SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED
    if telegram_sender_mode == "real":
        return SEND_GATE_REAL_SEND_AVAILABLE_NOT_USED_IN_CODEX
    return SEND_GATE_MOCK_SENT


def _recommended_next_operator_move(*, status: str, alert_required: bool) -> str:
    if status == SEND_GATE_MOCK_SENT:
        return "review_mock_send_record_and_prepare_operator_drill"
    if status == SEND_GATE_REAL_SEND_AVAILABLE_NOT_USED_IN_CODEX:
        return "do_not_run_real_send_in_codex_prepare_explicit_operator_drill"
    if status == SEND_GATE_BLOCKED_RATE_LIMIT:
        return "wait_for_rate_limit_window_or_repair_repeated_non_critical_alert"
    if not alert_required:
        return "continue_observation_no_send"
    return "repair_send_gate_blockers_before_any_real_alert"


def _recommended_r317_path(*, status: str) -> str:
    if status in {SEND_GATE_PREVIEW_READY, SEND_GATE_MOCK_SENT, SEND_GATE_REAL_SEND_AVAILABLE_NOT_USED_IN_CODEX}:
        return RECOMMENDED_R317_DRILL
    return RECOMMENDED_R317_REPAIR


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _join(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) if value else "none"
    return str(value) if value not in (None, "") else "none"


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value)
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.app.hammer_radar.operator.multi_lane_observation_alert_send_gate"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation", default=None)
    parser.add_argument("--telegram-sender-mode", choices=("mock", "real"), default="mock")
    parser.add_argument("--max-age-seconds", type=int, default=180)
    parser.add_argument("--rate-limit-window-seconds", type=int, default=DEFAULT_RATE_LIMIT_WINDOW_SECONDS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload = build_multi_lane_observation_alert_send_gate(
        log_dir=args.log_dir,
        apply=args.apply,
        confirmation=args.confirmation,
        telegram_sender_mode=args.telegram_sender_mode,
        max_age_seconds=args.max_age_seconds,
        rate_limit_window_seconds=args.rate_limit_window_seconds,
        no_write=args.no_write,
    )
    if args.json and not args.text:
        print(format_alert_send_gate_json(payload))
    else:
        print(format_alert_send_gate_text(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint.
    raise SystemExit(main())
