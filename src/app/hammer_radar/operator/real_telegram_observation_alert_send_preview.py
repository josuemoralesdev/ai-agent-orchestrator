"""R318 real Telegram observation alert send gate preview.

This preview checks whether Telegram credentials and sender plumbing are ready
for a future operator-confirmed send. It never calls Telegram, writes config,
mutates arming state, starts services, submits orders, or creates final commands.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.multi_lane_observation_alert_send_gate import (
    build_multi_lane_observation_alert_send_gate,
)
from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import (
    DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    SAFETY as R315_SAFETY,
)
from src.app.hammer_radar.operator.notification_watcher import (
    NotificationConfig,
    load_notification_config,
    send_telegram_message,
)

EVENT_TYPE = "R318_REAL_TELEGRAM_ALERT_SEND_GATE_PREVIEW"
CREATED_BY_PHASE = "R318_REAL_TELEGRAM_ALERT_SEND_GATE_PREVIEW"
LEDGER_FILENAME = "real_telegram_observation_alert_send_preview.ndjson"

FUTURE_CONFIRMATION_PHRASE = "ENABLE REAL TELEGRAM OBSERVATION ALERT SEND"
RECOMMENDED_R319_SYNTHETIC_SEND_DRILL = "R319 Real Telegram Observation Alert Synthetic Send Drill Preview"
RECOMMENDED_R319_CREDENTIAL_REPAIR = "R319 Telegram Credential Readiness Repair"
RECOMMENDED_R319_PREVIEW_REPAIR = "R319 Real Telegram Preview Repair"

SAFETY = {
    **R315_SAFETY,
    "telegram_send_called": False,
    "telegram_message_sent": False,
    "real_telegram_send_called": False,
    "real_telegram_message_sent": False,
}


def build_real_telegram_observation_alert_send_preview(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    config: NotificationConfig | None = None,
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
    notification_config = config or load_notification_config(dict(env) if env is not None else None)
    telegram_readiness = build_telegram_config_readiness(
        notification_config,
        env=env,
        real_sender_available=callable(send_telegram_message),
    )
    send_gate = build_multi_lane_observation_alert_send_gate(
        log_dir=resolved_log_dir,
        apply=False,
        confirmation=None,
        telegram_sender_mode="real",
        max_age_seconds=max_age_seconds,
        rate_limit_window_seconds=rate_limit_window_seconds,
        no_write=True,
        write=False,
        now=generated_at,
        alert_preview=alert_preview,
    )
    alert_required = bool(send_gate.get("alert_required"))
    real_send_available_for_future = bool(telegram_readiness["telegram_config_valid_for_future_send"])
    real_send_blockers = list(telegram_readiness["telegram_config_blockers"])
    if not telegram_readiness["real_sender_available"]:
        real_send_blockers.append("real_sender_unavailable")
    send_blockers = _send_blockers(
        alert_required=alert_required,
        real_send_blockers=real_send_blockers,
    )
    recommended_next_operator_move = (
        "continue_observation_no_send" if not alert_required else "review_alert_before_future_real_send_drill"
    )
    recommended_r319_path = _recommended_r319_path(
        credential_ready=real_send_available_for_future,
        real_send_blockers=real_send_blockers,
    )
    safety = dict(SAFETY)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "preview_id": f"r318_real_telegram_observation_alert_send_preview_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        **telegram_readiness,
        "alert_required": alert_required,
        "alert_severity": str(send_gate.get("alert_severity") or ""),
        "alert_reasons": list(send_gate.get("alert_reasons") or []),
        "send_gate_status": send_gate.get("send_gate_status"),
        "send_gate_preview_only": True,
        "future_confirmation_phrase_required": FUTURE_CONFIRMATION_PHRASE,
        "future_confirmation_phrase_active": False,
        "future_confirmation_phrase_executable": False,
        "real_send_available_for_future": real_send_available_for_future,
        "real_send_blockers": _dedupe(real_send_blockers),
        "real_send_preview_only": True,
        "would_send_real_telegram_now": False,
        "telegram_send_called": False,
        "telegram_message_sent": False,
        "real_telegram_send_called": False,
        "real_telegram_message_sent": False,
        "telegram_preview_message": str(send_gate.get("telegram_preview_message") or ""),
        "operator_console_preview_message": str(send_gate.get("operator_console_preview_message") or ""),
        "no_heartbeat_policy_enforced": True,
        "healthy_state_send_blocked": not alert_required,
        "dedup_key": send_gate.get("dedup_key"),
        "rate_limit_window_seconds": rate_limit_window_seconds,
        "previous_matching_send_generated_at": send_gate.get("previous_matching_send_generated_at"),
        "would_suppress_duplicate": send_gate.get("would_suppress_duplicate"),
        "would_repeat_critical": send_gate.get("would_repeat_critical"),
        "send_blockers": send_blockers,
        "recommended_next_operator_move": recommended_next_operator_move,
        "recommended_r319_path": recommended_r319_path,
        "source_send_gate_preview": send_gate,
        "source_alert_preview": send_gate.get("source_alert_preview"),
        "safety": safety,
        **safety,
    }
    safe_payload = _sanitize(payload)
    if should_write:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def build_telegram_config_readiness(
    config: NotificationConfig,
    *,
    env: Mapping[str, str] | None = None,
    real_sender_available: bool = True,
) -> dict[str, Any]:
    token = config.telegram_bot_token or ""
    chat_id = config.telegram_chat_id or ""
    token_present = bool(token)
    chat_id_present = bool(chat_id)
    blockers: list[str] = []
    if not token_present:
        blockers.append("telegram_token_missing")
    if not chat_id_present:
        blockers.append("telegram_chat_id_missing")
    return {
        "telegram_token_present": token_present,
        "telegram_chat_id_present": chat_id_present,
        "telegram_config_source_kind": _telegram_config_source_kind(env),
        "telegram_token_preview": _mask_secret(token),
        "telegram_chat_id_preview": _mask_secret(chat_id),
        "telegram_config_valid_for_future_send": token_present and chat_id_present and real_sender_available,
        "telegram_config_blockers": blockers,
        "real_sender_available": real_sender_available,
        "secrets_shown": False,
    }


def load_real_telegram_observation_alert_send_preview_records(
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


def format_real_telegram_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def format_real_telegram_preview_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R318 REAL TELEGRAM OBSERVATION ALERT SEND GATE PREVIEW",
        "",
        "TELEGRAM CONFIG READINESS",
        f"telegram_token_present: {payload.get('telegram_token_present')}",
        f"telegram_chat_id_present: {payload.get('telegram_chat_id_present')}",
        f"telegram_config_source_kind: {payload.get('telegram_config_source_kind')}",
        f"telegram_token_preview: {payload.get('telegram_token_preview')}",
        f"telegram_chat_id_preview: {payload.get('telegram_chat_id_preview')}",
        f"telegram_config_valid_for_future_send: {payload.get('telegram_config_valid_for_future_send')}",
        f"telegram_config_blockers: {_join(payload.get('telegram_config_blockers'))}",
        "",
        "REAL SEND PREVIEW",
        f"real_sender_available: {payload.get('real_sender_available')}",
        f"real_send_available_for_future: {payload.get('real_send_available_for_future')}",
        f"real_send_preview_only: {payload.get('real_send_preview_only')}",
        f"would_send_real_telegram_now: {payload.get('would_send_real_telegram_now')}",
        f"telegram_send_called: {payload.get('telegram_send_called')}",
        f"telegram_message_sent: {payload.get('telegram_message_sent')}",
        f"real_telegram_send_called: {payload.get('real_telegram_send_called')}",
        f"real_telegram_message_sent: {payload.get('real_telegram_message_sent')}",
        "",
        "ALERT SUMMARY",
        f"alert_required: {payload.get('alert_required')}",
        f"alert_severity: {payload.get('alert_severity')}",
        f"alert_reasons: {_join(payload.get('alert_reasons'))}",
        f"send_gate_status: {payload.get('send_gate_status')}",
        f"would_suppress_duplicate: {payload.get('would_suppress_duplicate')}",
        f"would_repeat_critical: {payload.get('would_repeat_critical')}",
        "",
        "CONFIRMATION PHRASE PREVIEW",
        f"future_confirmation_phrase_required: {payload.get('future_confirmation_phrase_required')}",
        f"future_confirmation_phrase_active: {payload.get('future_confirmation_phrase_active')}",
        f"future_confirmation_phrase_executable: {payload.get('future_confirmation_phrase_executable')}",
        "",
        "SEND BLOCKERS",
        f"send_blockers: {_join(payload.get('send_blockers'))}",
        f"real_send_blockers: {_join(payload.get('real_send_blockers'))}",
        "",
        "NO-HEARTBEAT POLICY",
        f"no_heartbeat_policy_enforced: {payload.get('no_heartbeat_policy_enforced')}",
        f"healthy_state_send_blocked: {payload.get('healthy_state_send_blocked')}",
        "",
        "TELEGRAM PREVIEW MESSAGE",
        str(payload.get("telegram_preview_message") or ""),
        "",
        "OPERATOR CONSOLE PREVIEW MESSAGE",
        str(payload.get("operator_console_preview_message") or ""),
        "",
        "SAFETY FLAGS",
    ]
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(
        [
            "",
            "RECOMMENDED NEXT PHASE",
            str(payload.get("recommended_r319_path")),
        ]
    )
    return "\n".join(lines)


def _send_blockers(*, alert_required: bool, real_send_blockers: Sequence[str]) -> list[str]:
    blockers = ["preview_only", "future_confirmation_phrase_inactive", "future_confirmation_phrase_non_executable"]
    if not alert_required:
        blockers.extend(["alert_required_false", "no_heartbeat_policy_blocks_healthy_send"])
    blockers.extend(real_send_blockers)
    return _dedupe(blockers)


def _recommended_r319_path(*, credential_ready: bool, real_send_blockers: Sequence[str]) -> str:
    if not credential_ready and {"telegram_token_missing", "telegram_chat_id_missing"} & set(real_send_blockers):
        return RECOMMENDED_R319_CREDENTIAL_REPAIR
    if real_send_blockers:
        return RECOMMENDED_R319_PREVIEW_REPAIR
    return RECOMMENDED_R319_SYNTHETIC_SEND_DRILL


def _telegram_config_source_kind(env: Mapping[str, str] | None) -> str:
    source = os.environ if env is None else env
    has_env_keys = any(key in source for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"))
    return "env" if has_env_keys else "unknown"


def _mask_secret(value: str | None) -> str:
    raw = str(value or "")
    if not raw:
        return "missing"
    if len(raw) <= 8:
        return "present_masked"
    return f"{raw[:4]}...{raw[-4:]}"


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
        prog="python -m src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--max-age-seconds", type=int, default=180)
    parser.add_argument("--rate-limit-window-seconds", type=int, default=DEFAULT_RATE_LIMIT_WINDOW_SECONDS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload = build_real_telegram_observation_alert_send_preview(
        log_dir=args.log_dir,
        max_age_seconds=args.max_age_seconds,
        rate_limit_window_seconds=args.rate_limit_window_seconds,
        no_write=args.no_write,
    )
    if args.json and not args.text:
        print(format_real_telegram_preview_json(payload))
    else:
        print(format_real_telegram_preview_text(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint.
    raise SystemExit(main())
