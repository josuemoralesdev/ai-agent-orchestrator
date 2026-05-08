"""Safe Telegram polling bridge for operator commands.

Loop mode only runs when explicitly invoked. Tests use injectable transports,
and no response ever exposes the bot token.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.notification_watcher import load_notification_config
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command

POLLING_STATE_FILENAME = "telegram_polling_state.json"
POLLING_EVENTS_FILENAME = "telegram_polling_events.ndjson"
DEFAULT_LOOP_INTERVAL_SECONDS = 3
DEFAULT_MAX_UPDATES = 10


class TelegramTransport(Protocol):
    def get_updates(self, *, token: str, offset: int | None, limit: int = DEFAULT_MAX_UPDATES) -> dict[str, Any]:
        ...

    def send_message(self, *, token: str, chat_id: str, text: str) -> dict[str, Any]:
        ...


class TelegramHttpTransport:
    def get_updates(self, *, token: str, offset: int | None, limit: int = DEFAULT_MAX_UPDATES, timeout: int = 5) -> dict[str, Any]:
        params = {"timeout": max(0, timeout), "limit": max(1, limit)}
        if offset is not None:
            params["offset"] = offset
        url = f"https://api.telegram.org/bot{token}/getUpdates?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=max(5, timeout + 5)) as response:  # noqa: S310 - explicit Telegram polling endpoint
            return json.loads(response.read().decode("utf-8"))

    def send_message(self, *, token: str, chat_id: str, text: str) -> dict[str, Any]:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        with urllib.request.urlopen(url, data=data, timeout=10) as response:  # noqa: S310 - explicit Telegram send endpoint
            return json.loads(response.read().decode("utf-8"))


def poll_telegram_once(
    *,
    env: dict[str, str] | None = None,
    log_dir: str | Path | None = None,
    transport: TelegramTransport | None = None,
    send_responses: bool = False,
    dry_run: bool = False,
    max_updates: int = DEFAULT_MAX_UPDATES,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    config = load_notification_config(env)
    started_at = datetime.now(UTC)
    if not config.telegram_configured:
        payload = _status("BLOCKED", "telegram bot token/chat id missing", processed=[], state=_load_state(resolved_log_dir), dry_run=dry_run, updates_seen=0)
        _append_polling_event(_event(payload, started_at=started_at), log_dir=resolved_log_dir)
        return payload
    state = _load_state(resolved_log_dir)
    last_update_id = _last_update_id(state)
    selected_transport = transport or TelegramHttpTransport()
    try:
        updates = selected_transport.get_updates(
            token=config.telegram_bot_token or "",
            offset=(last_update_id + 1 if last_update_id is not None else None),
            limit=max_updates,
        )
    except TypeError:
        updates = selected_transport.get_updates(token=config.telegram_bot_token or "", offset=(last_update_id + 1 if last_update_id is not None else None))
    except Exception as exc:  # pragma: no cover - defensive network boundary
        state = {
            **state,
            "last_poll_at": started_at.isoformat(),
            "last_error": exc.__class__.__name__,
            "error_count": int(state.get("error_count") or 0) + 1,
            "secrets_shown": False,
        }
        _save_state(resolved_log_dir, state)
        payload = _status("ERROR", exc.__class__.__name__, processed=[], state=state, dry_run=dry_run, updates_seen=0)
        _append_polling_event(_event(payload, started_at=started_at), log_dir=resolved_log_dir)
        return payload
    processed = []
    max_update_id = last_update_id
    sent_count = 0
    error_count = 0
    updates_seen = len(updates.get("result", []))
    for update in updates.get("result", []):
        update_id = update.get("update_id")
        if isinstance(update_id, int) and last_update_id is not None and update_id <= last_update_id:
            processed.append({"update_id": update_id, "status": "DEDUPED_OLD_UPDATE", "message_sent": False})
            continue
        message = update.get("message") or {}
        text = message.get("text")
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id")) if chat.get("id") is not None else None
        if chat_id and config.telegram_chat_id and chat_id != str(config.telegram_chat_id):
            processed.append({"update_id": update_id, "status": "IGNORED_UNAUTHORIZED_CHAT", "message_sent": False})
            if update_id is not None:
                max_update_id = max(update_id, max_update_id if max_update_id is not None else update_id)
            continue
        if text:
            result = handle_telegram_operator_command(
                text=text,
                source="telegram_poll",
                chat_id=chat_id,
                update_id=update_id,
                log_dir=resolved_log_dir,
            )
            send_result = None
            if send_responses and not dry_run and chat_id:
                try:
                    response = selected_transport.send_message(
                        token=config.telegram_bot_token or "",
                        chat_id=chat_id,
                        text=(result.get("telegram_compatible") or {}).get("text") or result.get("message", "No response"),
                    )
                    send_result = _sanitize_send_result(response)
                    sent_count += 1 if send_result.get("message_sent") else 0
                except Exception as exc:  # pragma: no cover - defensive network boundary
                    error_count += 1
                    send_result = {"network_used": True, "message_sent": False, "telegram_ok": False, "error": exc.__class__.__name__, "secrets_shown": False}
            processed.append(
                {
                    "update_id": update_id,
                    "status": "PROCESSED",
                    "result_status": result.get("result_status"),
                    "normalized_action": result.get("normalized_action"),
                    "message_sent": bool(send_result and send_result.get("message_sent")),
                    "dry_run": dry_run,
                    "send_result": send_result,
                }
            )
        else:
            processed.append({"update_id": update_id, "status": "IGNORED_NON_TEXT", "message_sent": False})
        if update_id is not None:
            max_update_id = max(update_id, max_update_id if max_update_id is not None else update_id)
    if max_update_id is not None:
        state = {
            "last_update_id": max_update_id,
            "next_offset": max_update_id + 1,
            "updated_at": datetime.now(UTC).isoformat(),
            "last_poll_at": started_at.isoformat(),
            "last_processed_at": datetime.now(UTC).isoformat() if processed else state.get("last_processed_at"),
            "last_error": None,
            "processed_count": int(state.get("processed_count") or 0) + len([item for item in processed if item["status"] in {"PROCESSED", "IGNORED_NON_TEXT"}]),
            "sent_count": int(state.get("sent_count") or 0) + sent_count,
            "error_count": int(state.get("error_count") or 0) + error_count,
            "secrets_shown": False,
        }
        _save_state(resolved_log_dir, state)
    else:
        state = {
            **_load_state(resolved_log_dir),
            "last_poll_at": started_at.isoformat(),
            "last_error": None,
            "secrets_shown": False,
        }
        _save_state(resolved_log_dir, state)
    payload = _status("OK", "poll completed", processed=processed, state=state, dry_run=dry_run, updates_seen=updates_seen)
    _append_polling_event(_event(payload, started_at=started_at), log_dir=resolved_log_dir)
    return payload


def polling_status(*, env: dict[str, str] | None = None, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    config = load_notification_config(env)
    state = _load_state(resolved_log_dir)
    return {
        "result_status": "ACCEPTED",
        "status": "OK",
        "configured": config.telegram_configured,
        "worker_expected": True,
        "token_present": config.token_present,
        "chat_id_configured": config.chat_id_present,
        "telegram_configured": config.telegram_configured,
        "polling_enabled": config.telegram_enabled,
        "state_path": str(telegram_polling_state_path(resolved_log_dir)),
        "last_update_id": state.get("last_update_id"),
        "last_poll_at": state.get("last_poll_at"),
        "last_processed_at": state.get("last_processed_at"),
        "last_error": state.get("last_error"),
        "processed_count": state.get("processed_count", 0),
        "sent_count": state.get("sent_count", 0),
        "error_count": state.get("error_count", 0),
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def polling_state(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    state = _load_state(resolved_log_dir)
    return {
        "result_status": "ACCEPTED",
        "state_path": str(telegram_polling_state_path(resolved_log_dir)),
        "state": _sanitize_state(state),
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def run_polling_loop(
    *,
    env: dict[str, str] | None = None,
    log_dir: str | Path | None = None,
    interval_seconds: int = DEFAULT_LOOP_INTERVAL_SECONDS,
    dry_run: bool = False,
    max_updates: int = DEFAULT_MAX_UPDATES,
    transport: TelegramTransport | None = None,
) -> None:
    while True:
        poll_telegram_once(
            env=env,
            log_dir=log_dir,
            transport=transport,
            send_responses=True,
            dry_run=dry_run,
            max_updates=max_updates,
        )
        time.sleep(max(1, interval_seconds))


def telegram_polling_state_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / POLLING_STATE_FILENAME


def telegram_polling_events_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / POLLING_EVENTS_FILENAME


def _load_state(log_dir: Path) -> dict[str, Any]:
    path = telegram_polling_state_path(log_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_state(log_dir: Path, state: dict[str, Any]) -> None:
    path = telegram_polling_state_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")


def _append_polling_event(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = telegram_polling_events_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _status(status: str, reason: str, *, processed: list[dict[str, Any]], state: dict[str, Any], dry_run: bool, updates_seen: int) -> dict[str, Any]:
    replied = len([item for item in processed if item.get("message_sent") is True])
    return {
        "status": status,
        "result_status": "ACCEPTED" if status == "OK" else status,
        "reason": reason,
        "processed": processed,
        "processed_count": len(processed),
        "replied": replied,
        "updates_seen": updates_seen,
        "last_update_id": state.get("last_update_id"),
        "dry_run": dry_run,
        "state": _sanitize_state(state),
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def _event(payload: dict[str, Any], *, started_at: datetime) -> dict[str, Any]:
    return {
        "event_type": "telegram_polling_once",
        "created_at": datetime.now(UTC).isoformat(),
        "started_at": started_at.isoformat(),
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "processed_count": payload.get("processed_count", 0),
        "replied": payload.get("replied", 0),
        "updates_seen": payload.get("updates_seen", 0),
        "last_update_id": payload.get("last_update_id"),
        "dry_run": payload.get("dry_run"),
        "order_placed": False,
        "real_order_placed": False,
        "secrets_shown": False,
    }


def _last_update_id(state: dict[str, Any]) -> int | None:
    if "last_update_id" in state:
        try:
            return int(state["last_update_id"])
        except (TypeError, ValueError):
            return None
    if "next_offset" in state:
        try:
            return int(state["next_offset"]) - 1
        except (TypeError, ValueError):
            return None
    return None


def _sanitize_state(state: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(state)
    sanitized["secrets_shown"] = False
    return sanitized


def _sanitize_send_result(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "network_used": True,
        "message_sent": bool(response.get("ok", True)),
        "telegram_ok": bool(response.get("ok", True)),
        "secrets_shown": False,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hammer Radar Telegram operator polling worker")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="poll Telegram once and exit")
    mode.add_argument("--loop", action="store_true", help="poll Telegram repeatedly until stopped")
    mode.add_argument("--watch", action="store_true", help="poll Telegram repeatedly until stopped")
    parser.add_argument("--dry-run", action="store_true", help="process updates without sending Telegram responses")
    parser.add_argument("--interval", type=int, default=DEFAULT_LOOP_INTERVAL_SECONDS, help="loop sleep interval in seconds")
    parser.add_argument("--interval-seconds", type=int, default=None, help="loop sleep interval in seconds")
    parser.add_argument("--max-updates", type=int, default=DEFAULT_MAX_UPDATES, help="maximum updates to fetch per poll")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.once:
        print(json.dumps(poll_telegram_once(send_responses=True, dry_run=args.dry_run, max_updates=args.max_updates), sort_keys=True))
        return 0
    interval = args.interval_seconds if args.interval_seconds is not None else args.interval
    run_polling_loop(interval_seconds=interval, dry_run=args.dry_run, max_updates=args.max_updates)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through parser tests
    raise SystemExit(main())
