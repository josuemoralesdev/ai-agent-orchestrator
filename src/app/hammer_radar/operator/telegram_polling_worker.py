"""Safe one-shot Telegram polling bridge for operator commands.

This module does not run forever during tests and never exposes the bot token.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.notification_watcher import load_notification_config
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command

POLLING_STATE_FILENAME = "telegram_polling_state.json"


class TelegramTransport(Protocol):
    def get_updates(self, *, token: str, offset: int | None) -> dict[str, Any]:
        ...

    def send_message(self, *, token: str, chat_id: str, text: str) -> dict[str, Any]:
        ...


class TelegramHttpTransport:
    def get_updates(self, *, token: str, offset: int | None) -> dict[str, Any]:
        params = {"timeout": 0}
        if offset is not None:
            params["offset"] = offset
        url = f"https://api.telegram.org/bot{token}/getUpdates?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - explicit Telegram polling endpoint
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
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    config = load_notification_config(env)
    if not config.telegram_configured:
        return _status("BLOCKED", "telegram bot token/chat id missing", processed=[])
    state = _load_state(resolved_log_dir)
    selected_transport = transport or TelegramHttpTransport()
    updates = selected_transport.get_updates(token=config.telegram_bot_token or "", offset=state.get("next_offset"))
    processed = []
    max_update_id = state.get("next_offset", 0) - 1 if state.get("next_offset") else None
    for update in updates.get("result", []):
        update_id = update.get("update_id")
        message = update.get("message") or {}
        text = message.get("text")
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id")) if chat.get("id") is not None else None
        if text:
            result = handle_telegram_operator_command(
                text=text,
                source="telegram_poll",
                chat_id=chat_id,
                update_id=update_id,
                log_dir=resolved_log_dir,
            )
            processed.append({"update_id": update_id, "result_status": result.get("result_status")})
            if send_responses and chat_id:
                selected_transport.send_message(
                    token=config.telegram_bot_token or "",
                    chat_id=chat_id,
                    text=result.get("message", "No response"),
                )
        if update_id is not None:
            max_update_id = max(update_id, max_update_id if max_update_id is not None else update_id)
    if max_update_id is not None:
        _save_state(resolved_log_dir, {"next_offset": max_update_id + 1})
    return _status("OK", "poll completed", processed=processed)


def telegram_polling_state_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / POLLING_STATE_FILENAME


def _load_state(log_dir: Path) -> dict[str, Any]:
    path = telegram_polling_state_path(log_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(log_dir: Path, state: dict[str, Any]) -> None:
    path = telegram_polling_state_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")


def _status(status: str, reason: str, *, processed: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "processed": processed,
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }
