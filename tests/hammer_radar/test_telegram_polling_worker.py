from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.archive import append_signal
from src.app.hammer_radar.operator.live_approval import load_live_approval_requests
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_polling_worker import (
    build_arg_parser,
    poll_telegram_once,
    polling_status,
    telegram_polling_events_path,
    telegram_polling_state_path,
)


class TelegramPollingWorkerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)
        self.env = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "123"}

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_poll_once_returns_json_summary(self) -> None:
        payload = poll_telegram_once(
            env=self.env,
            log_dir=self.log_dir,
            transport=_UpdatesTransport([]),
            send_responses=False,
        )

        self.assertEqual("OK", payload["status"])
        self.assertEqual(0, payload["processed_count"])
        self.assertEqual(0, payload["replied"])
        self.assertEqual(0, payload["updates_seen"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])
        self.assertTrue(telegram_polling_events_path(self.log_dir).exists())

    def test_worker_processes_first_live_next(self) -> None:
        transport = _UpdatesTransport([_message(1, "FIRST LIVE NEXT")])

        payload = poll_telegram_once(env=self.env, log_dir=self.log_dir, transport=transport, send_responses=True)

        self.assertEqual("OK", payload["status"])
        self.assertEqual("PROCESSED", payload["processed"][0]["status"])
        self.assertEqual("first_live_next", payload["processed"][0]["normalized_action"])
        self.assertEqual(1, payload["replied"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_worker_processes_live_approve_for_fresh_signal(self) -> None:
        signal_id = self._append_signal(age_minutes=5.0)
        transport = _UpdatesTransport([_message(2, f"LIVE APPROVE {signal_id}")])

        payload = poll_telegram_once(env=self.env, log_dir=self.log_dir, transport=transport, send_responses=True)
        approvals = load_live_approval_requests(limit=10, signal_id=signal_id, log_dir=self.log_dir)

        self.assertEqual("OK", payload["status"])
        self.assertEqual("ACCEPTED", payload["processed"][0]["result_status"])
        self.assertEqual("live_approve", payload["processed"][0]["normalized_action"])
        self.assertEqual(1, len(approvals))
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_worker_rejects_stale_live_approve_without_persisting(self) -> None:
        signal_id = self._append_signal(age_minutes=20.17)
        transport = _UpdatesTransport([_message(3, f"LIVE APPROVE {signal_id}")])

        payload = poll_telegram_once(env=self.env, log_dir=self.log_dir, transport=transport, send_responses=True)
        approvals = load_live_approval_requests(limit=10, signal_id=signal_id, log_dir=self.log_dir)

        self.assertEqual("REJECTED", payload["processed"][0]["result_status"])
        self.assertEqual([], approvals)
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_worker_rejects_raw_yes_and_blocks_trade_now_live(self) -> None:
        transport = _UpdatesTransport([_message(4, "YES"), _message(5, "trade now live")])

        payload = poll_telegram_once(env=self.env, log_dir=self.log_dir, transport=transport, send_responses=True)

        self.assertEqual(["REJECTED", "BLOCKED"], [item["result_status"] for item in payload["processed"]])
        self.assertFalse((self.log_dir / "live_approval_requests.ndjson").exists())
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_dedup_offset_processes_update_once(self) -> None:
        update = _message(6, "HELP")
        first = poll_telegram_once(env=self.env, log_dir=self.log_dir, transport=_UpdatesTransport([update]), send_responses=False)
        second = poll_telegram_once(env=self.env, log_dir=self.log_dir, transport=_UpdatesTransport([update]), send_responses=False)

        self.assertEqual("PROCESSED", first["processed"][0]["status"])
        self.assertEqual("DEDUPED_OLD_UPDATE", second["processed"][0]["status"])
        self.assertEqual(6, second["last_update_id"])

    def test_state_persistence_hides_secrets(self) -> None:
        poll_telegram_once(env=self.env, log_dir=self.log_dir, transport=_UpdatesTransport([_message(7, "HELP")]))
        state = telegram_polling_state_path(self.log_dir).read_text(encoding="utf-8")

        self.assertIn("last_update_id", state)
        self.assertNotIn("secret-token", state)

    def test_polling_status_endpoint_shape(self) -> None:
        with patch.dict("os.environ", self.env, clear=False):
            response = self.client.get("/telegram/polling/status")

        payload = response.json()
        self.assertEqual(200, response.status_code)
        self.assertEqual("OK", payload["status"])
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["worker_expected"])
        self.assertIn("state_path", payload)
        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-token", str(payload))

    def test_polling_once_endpoint_returns_json_when_unconfigured(self) -> None:
        response = self.client.post("/telegram/polling/once", json={"dry_run": True})

        payload = response.json()
        self.assertEqual(200, response.status_code)
        self.assertIn(payload["status"], {"BLOCKED", "OK"})
        self.assertIn("processed_count", payload)
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])

    def test_service_file_exists_and_uses_watch(self) -> None:
        service = Path("deploy/systemd/hammer-telegram-polling.service")
        text = service.read_text(encoding="utf-8")

        self.assertIn(".venv/bin/python -m src.app.hammer_radar.operator.telegram_polling_worker --watch", text)
        self.assertIn("EnvironmentFile=/home/josue/.config/hammer-radar/notifications.env", text)
        self.assertNotIn("secret-token", text)

    def test_cli_parser_accepts_watch_alias(self) -> None:
        args = build_arg_parser().parse_args(["--watch", "--interval-seconds", "2", "--max-updates", "5"])

        self.assertTrue(args.watch)
        self.assertEqual(2, args.interval_seconds)
        self.assertEqual(5, args.max_updates)

    def _append_signal(self, *, age_minutes: float) -> str:
        timestamp = (datetime.now(UTC) - timedelta(minutes=age_minutes)).isoformat()
        signal_id = f"BTCUSDT|13m|long|{timestamp}"
        append_signal(
            SignalRecord(
                signal_id=signal_id,
                symbol="BTCUSDT",
                timeframe="13m",
                direction="long",
                timestamp=timestamp,
                hammer_strength=1.0,
                hammer_high=101.0,
                hammer_low=99.0,
                fib_50=100.0,
                fib_618=101.0,
                fib_650=101.5,
                fib_786=102.0,
                invalidation=98.0,
                bias_timeframe="4h",
                bias_direction="long",
                bias_aligned=True,
                same_direction_streak=1,
                opposite_direction_streak=0,
                tradable=True,
            ),
            log_dir=self.log_dir,
        )
        return signal_id


def _message(update_id: int, text: str) -> dict:
    return {"update_id": update_id, "message": {"text": text, "chat": {"id": 123}}}


class _UpdatesTransport:
    def __init__(self, updates: list[dict]) -> None:
        self.updates = updates
        self.send_count = 0

    def get_updates(self, *, token: str, offset: int | None, limit: int = 10) -> dict:
        return {"ok": True, "result": self.updates}

    def send_message(self, *, token: str, chat_id: str, text: str) -> dict:
        self.send_count += 1
        return {"ok": True, "result": {"chat_id": chat_id, "text_length": len(text)}}


if __name__ == "__main__":
    unittest.main()
