from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from subprocess import run
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.notification_watcher import (
    NotificationConfig,
    check_notifications,
    evaluate_alert,
    load_alert_records,
    load_notification_config,
    notification_status,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class NotificationWatcherTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=True)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_notification_status_with_no_env_is_not_configured(self) -> None:
        config = load_notification_config()
        status = notification_status(log_dir=self.log_dir, config=config)

        self.assertFalse(status["telegram_enabled"])
        self.assertFalse(status["telegram_configured"])
        self.assertFalse(status["token_present"])
        self.assertFalse(status["chat_id_present"])
        self.assertFalse(status["secrets_shown"])

    def test_notification_status_never_exposes_token(self) -> None:
        config = NotificationConfig(
            telegram_enabled=True,
            telegram_bot_token="123456:SECRET_TOKEN",
            telegram_chat_id="12345",
            min_interval_seconds=300,
            poll_seconds=60,
            require_dry_run_valid=True,
            require_proposed_ticket=True,
            blocked_alert_enabled=False,
        )

        status = notification_status(log_dir=self.log_dir, config=config)
        safe = config.safe_status()

        self.assertTrue(status["token_present"])
        self.assertNotIn("SECRET_TOKEN", str(status))
        self.assertIsNone(safe["token_preview"])
        self.assertNotIn("SECRET_TOKEN", str(safe))

    def test_ready_snapshot_creates_would_alert_true(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="notify|ready"), log_dir=self.log_dir)

        result = check_notifications(send=False, channel="none", log_dir=self.log_dir)

        self.assertTrue(result["would_alert"])
        self.assertEqual("READY_TRADE_CANDIDATE", result["alert_type"])
        self.assertEqual("PROPOSED", result["ticket_status"])
        self.assertEqual("VALID", result["dry_run_status"])
        self.assertFalse(result["live_execution_enabled"])
        self.assertFalse(result["order_placed"])

    def test_not_ready_snapshot_creates_would_alert_false(self) -> None:
        result = check_notifications(send=False, channel="none", log_dir=self.log_dir)

        self.assertFalse(result["would_alert"])
        self.assertIsNone(result["alert_type"])
        self.assertEqual("NOT_READY", result["readiness_status"])

    def test_dedupe_prevents_duplicate_same_signal_alert(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="notify|dedupe"), log_dir=self.log_dir)
        config = NotificationConfig(
            telegram_enabled=True,
            telegram_bot_token="fake-token",
            telegram_chat_id="fake-chat",
            min_interval_seconds=0,
            poll_seconds=60,
            require_dry_run_valid=True,
            require_proposed_ticket=True,
            blocked_alert_enabled=False,
        )
        calls: list[tuple[str, str]] = []

        def fake_sender(chat_id: str, message: str) -> dict:
            calls.append((chat_id, message))
            return {"sent": True, "status": "sent"}

        first = check_notifications(
            send=True,
            channel="telegram",
            log_dir=self.log_dir,
            config=config,
            telegram_sender=fake_sender,
        )
        second = check_notifications(
            send=True,
            channel="telegram",
            log_dir=self.log_dir,
            config=config,
            telegram_sender=fake_sender,
        )

        self.assertTrue(first["recorded"])
        self.assertFalse(second["recorded"])
        self.assertEqual("duplicate_signal_alert", second["dedupe_reason"])
        self.assertEqual(1, len(calls))

    def test_alert_record_writes_readiness_alerts_ndjson(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="notify|record"), log_dir=self.log_dir)
        config = NotificationConfig(
            telegram_enabled=True,
            telegram_bot_token="fake-token",
            telegram_chat_id="fake-chat",
            min_interval_seconds=0,
            poll_seconds=60,
            require_dry_run_valid=True,
            require_proposed_ticket=True,
            blocked_alert_enabled=False,
        )

        result = check_notifications(
            send=True,
            channel="telegram",
            log_dir=self.log_dir,
            config=config,
            telegram_sender=lambda _chat_id, _message: {"sent": True, "status": "sent"},
        )
        records = load_alert_records(limit=10, log_dir=self.log_dir)

        self.assertTrue(result["recorded"])
        self.assertTrue((self.log_dir / "readiness_alerts.ndjson").exists())
        self.assertEqual(1, len(records))
        self.assertEqual("READY_TRADE_CANDIDATE", records[0]["alert_type"])
        self.assertFalse(records[0]["live_execution_enabled"])
        self.assertFalse(records[0]["order_placed"])

    def test_api_notifications_status_safety_fields(self) -> None:
        response = self.client.get("/notifications/status")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["secrets_shown"])
        self.assertFalse(payload["telegram_configured"])

    def test_api_notifications_check_send_false_works(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="notify|api-check"), log_dir=self.log_dir)

        with patch("src.app.hammer_radar.operator.notification_watcher.send_telegram_message") as sender:
            response = self.client.post("/notifications/check", json={"send": False, "channel": "none"})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["would_alert"])
        self.assertFalse(payload["recorded"])
        sender.assert_not_called()

    def test_api_notifications_alerts_lists_records(self) -> None:
        archive.append_signal(self._eligible_signal(signal_id="notify|api-alerts"), log_dir=self.log_dir)
        config = NotificationConfig(
            telegram_enabled=True,
            telegram_bot_token="fake-token",
            telegram_chat_id="fake-chat",
            min_interval_seconds=0,
            poll_seconds=60,
            require_dry_run_valid=True,
            require_proposed_ticket=True,
            blocked_alert_enabled=False,
        )
        check_notifications(
            send=True,
            channel="telegram",
            log_dir=self.log_dir,
            config=config,
            telegram_sender=lambda _chat_id, _message: {"sent": True, "status": "sent"},
        )

        response = self.client.get("/notifications/alerts?limit=5")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(1, len(payload["readiness_alerts"]))
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["order_placed"])

    def test_cli_notification_status_works(self) -> None:
        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "notification-status",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            env={LOG_DIR_ENV_VAR: str(self.log_dir), "PATH": os.environ.get("PATH", "")},
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR NOTIFICATION STATUS", result.stdout)
        self.assertIn("telegram_configured: false", result.stdout)
        self.assertIn("secrets_shown: false", result.stdout)

    def test_cli_notification_check_channel_none_works(self) -> None:
        result = run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(self.log_dir),
                "notification-check",
                "--channel",
                "none",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            env={LOG_DIR_ENV_VAR: str(self.log_dir), "PATH": os.environ.get("PATH", "")},
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("HAMMER RADAR NOTIFICATION CHECK", result.stdout)
        self.assertIn("channel: none", result.stdout)
        self.assertIn("secrets_shown: false", result.stdout)

    def test_ui_contains_notification_watcher_panel(self) -> None:
        response = self.client.get("/ui")

        self.assertEqual(200, response.status_code)
        self.assertIn("Notification Watcher", response.text)
        self.assertIn("Alerts only. No order placement.", response.text)
        self.assertIn("Secrets are never shown", response.text)
        self.assertIn("Use this so you do not need to watch the UI constantly.", response.text)

    def test_evaluate_alert_does_not_call_telegram(self) -> None:
        snapshot = {
            "readiness": {"readiness_status": "NOT_READY", "allowed_now": False},
            "ticket": {"ticket_status": "BLOCKED", "signal_id": None},
            "exchange_dry_run": {"validation_status": "BLOCKED"},
            "live_safety": {"live_safety_status": "BLOCKED"},
            "live_execution_enabled": False,
            "order_placed": False,
        }

        with patch("src.app.hammer_radar.operator.notification_watcher.urllib.request.urlopen") as urlopen:
            result = evaluate_alert(snapshot)

        self.assertFalse(result["would_alert"])
        urlopen.assert_not_called()

    @staticmethod
    def _eligible_signal(
        *,
        signal_id: str,
        symbol: str = "BTCUSDT",
        direction: str = "long",
        timestamp: str | None = None,
    ) -> SignalRecord:
        return SignalRecord(
            signal_id=signal_id,
            symbol=symbol,
            timeframe="13m",
            direction=direction,
            timestamp=timestamp or (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            hammer_strength=100.0,
            hammer_high=101.0,
            hammer_low=94.0,
            fib_50=100.5,
            fib_618=100.0,
            fib_650=99.5,
            fib_786=98.5,
            invalidation=95.0,
            bias_timeframe="4H",
            bias_direction="bullish",
            bias_aligned=True,
            same_direction_streak=0,
            opposite_direction_streak=0,
            tradable=True,
            reject_reason=None,
            trend_direction="bullish",
            trend_strength_score=0.4,
            trend_lookback_candles=3,
            ema_4h_20=100.0,
            price_vs_ema_4h_pct=0.1,
            signal_close=100.0,
            rsi_value=50.0,
            rsi_state="neutral",
            divergence_type="bullish",
            divergence_confirmed=True,
        )


if __name__ == "__main__":
    unittest.main()
