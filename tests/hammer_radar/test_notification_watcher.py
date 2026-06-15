from __future__ import annotations

import os
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from subprocess import run
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord
from src.app.hammer_radar.operator.notification_watcher import (
    NotificationConfig,
    check_notifications,
    evaluate_alert,
    load_alert_records,
    load_notification_config,
    notification_status,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.strategy_config import DEFAULT_MINIMUM_HAMMER_STRENGTH


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
            actionable_paper_enabled=True,
            actionable_paper_min_score=80,
            expiring_soon_minutes=5,
            expired_missed_record_enabled=True,
        )

        status = notification_status(log_dir=self.log_dir, config=config)
        safe = config.safe_status()

        self.assertTrue(status["token_present"])
        self.assertNotIn("SECRET_TOKEN", str(status))
        self.assertIsNone(safe["token_preview"])
        self.assertNotIn("SECRET_TOKEN", str(safe))

    def test_ready_snapshot_creates_would_alert_true(self) -> None:
        self._seed_strategy_evidence(timeframe="13m", direction="long")
        archive.append_signal(self._eligible_signal(signal_id="notify|ready"), log_dir=self.log_dir)

        result = check_notifications(send=False, channel="none", log_dir=self.log_dir)

        self.assertTrue(result["would_alert"])
        self.assertEqual("LIVE_READY", result["alert_type"])
        self.assertEqual("PROPOSED", result["ticket_status"])
        self.assertEqual("VALID", result["dry_run_status"])
        self.assertFalse(result["live_execution_enabled"])
        self.assertFalse(result["order_placed"])

    def test_not_ready_snapshot_creates_would_alert_false(self) -> None:
        result = check_notifications(send=False, channel="none", log_dir=self.log_dir)

        self.assertFalse(result["would_alert"])
        self.assertIsNone(result["alert_type"])
        self.assertEqual("NOT_READY", result["readiness_status"])

    def test_actionable_paper_alerts_without_live_ticket(self) -> None:
        archive.append_signal(
            self._eligible_signal(
                signal_id="notify|paper",
                hammer_strength=DEFAULT_MINIMUM_HAMMER_STRENGTH,
                rsi_state=None,
            ),
            log_dir=self.log_dir,
        )

        result = check_notifications(send=False, channel="none", log_dir=self.log_dir)

        self.assertTrue(result["would_alert"])
        self.assertEqual("ACTIONABLE_PAPER", result["alert_type"])
        self.assertEqual("BLOCKED", result["ticket_status"])
        self.assertEqual("BLOCKED", result["dry_run_status"])
        self.assertEqual("BLOCKED", result["live_safety_status"])
        self.assertEqual("notify|paper", result["signal_id"])
        self.assertEqual("ACTIONABLE_PAPER_CANDIDATE", result["candidate"]["tier"])
        self.assertEqual(DEFAULT_MINIMUM_HAMMER_STRENGTH, result["candidate"]["minimum_hammer_strength"])
        self.assertEqual(DEFAULT_MINIMUM_HAMMER_STRENGTH, result["candidate"]["hammer_strength"])
        self.assertIn("alert_type: ACTIONABLE_PAPER", result["message"])
        self.assertIn("symbol: BTCUSDT", result["message"])
        self.assertIn("paper candidate for operator visibility only", result["message"])
        self.assertIn("live readiness is not implied", result["message"])
        self.assertIn("operator action: watch / approve paper / wait for next fresh candidate", result["message"])
        self.assertNotIn("passes conservative manual tiny-live checklist", result["message"])
        self.assertFalse(result["live_execution_enabled"])
        self.assertFalse(result["order_placed"])

    def test_actionable_paper_requires_configured_hammer_strength_minimum(self) -> None:
        archive.append_signal(
            self._eligible_signal(
                signal_id="notify|below-hammer-min",
                hammer_strength=DEFAULT_MINIMUM_HAMMER_STRENGTH - 1.0,
            ),
            log_dir=self.log_dir,
        )

        result = check_notifications(send=False, channel="none", log_dir=self.log_dir)

        self.assertFalse(result["would_alert"])
        self.assertIsNone(result["alert_type"])
        self.assertIsNone(result["candidate"])
        self.assertFalse(result["live_execution_enabled"])
        self.assertFalse(result["order_placed"])

    def test_actionable_paper_short_is_paper_visibility_not_live_approval(self) -> None:
        archive.append_signal(
            self._eligible_signal(
                signal_id="notify|short-paper",
                direction="short",
                hammer_strength=DEFAULT_MINIMUM_HAMMER_STRENGTH,
                divergence_type="bearish",
                bias_direction="bearish",
            ),
            log_dir=self.log_dir,
        )

        result = check_notifications(send=False, channel="none", log_dir=self.log_dir)

        self.assertTrue(result["would_alert"])
        self.assertEqual("ACTIONABLE_PAPER", result["alert_type"])
        self.assertEqual("short", result["candidate"]["direction"])
        self.assertEqual("BLOCKED", result["ticket_status"])
        self.assertIn("short is paper/operator visibility only, not live approval", result["message"])
        self.assertIn("live readiness is not implied", result["message"])
        self.assertFalse(result["live_execution_enabled"])
        self.assertFalse(result["order_placed"])

    def test_expired_candidate_records_missed_without_telegram_spam(self) -> None:
        archive.append_signal(
            self._eligible_signal(
                signal_id="notify|expired",
                hammer_strength=DEFAULT_MINIMUM_HAMMER_STRENGTH,
                rsi_state=None,
                timestamp=(datetime.now(UTC) - timedelta(minutes=35)).isoformat(),
            ),
            log_dir=self.log_dir,
        )
        config = NotificationConfig(
            telegram_enabled=True,
            telegram_bot_token="fake-token",
            telegram_chat_id="fake-chat",
            min_interval_seconds=0,
            poll_seconds=60,
            require_dry_run_valid=True,
            require_proposed_ticket=True,
            blocked_alert_enabled=False,
            actionable_paper_enabled=True,
            actionable_paper_min_score=80,
            expiring_soon_minutes=5,
            expired_missed_record_enabled=True,
        )
        calls: list[tuple[str, str]] = []

        result = check_notifications(
            send=True,
            channel="telegram",
            log_dir=self.log_dir,
            config=config,
            telegram_sender=lambda chat_id, message: calls.append((chat_id, message)) or {"sent": True, "status": "sent"},
        )
        records = load_alert_records(limit=10, log_dir=self.log_dir)

        self.assertFalse(result["would_alert"])
        self.assertEqual("EXPIRED_MISSED", result["alert_type"])
        self.assertTrue(result["recorded"])
        self.assertEqual({"sent": False, "status": "not_requested"}, result["telegram"])
        self.assertEqual([], calls)
        self.assertEqual(1, len(records))
        self.assertEqual("EXPIRED_MISSED", records[0]["alert_type"])
        self.assertFalse(records[0]["telegram_sent"])

    def test_duplicate_actionable_paper_candidate_does_not_alert_twice(self) -> None:
        archive.append_signal(
            self._eligible_signal(
                signal_id="notify|paper-dedupe",
                hammer_strength=DEFAULT_MINIMUM_HAMMER_STRENGTH,
                rsi_state=None,
            ),
            log_dir=self.log_dir,
        )
        config = NotificationConfig(
            telegram_enabled=True,
            telegram_bot_token="fake-token",
            telegram_chat_id="fake-chat",
            min_interval_seconds=0,
            poll_seconds=60,
            require_dry_run_valid=True,
            require_proposed_ticket=True,
            blocked_alert_enabled=False,
            actionable_paper_enabled=True,
            actionable_paper_min_score=80,
            expiring_soon_minutes=5,
            expired_missed_record_enabled=True,
        )
        calls: list[tuple[str, str]] = []

        first = check_notifications(
            send=True,
            channel="telegram",
            log_dir=self.log_dir,
            config=config,
            telegram_sender=lambda chat_id, message: calls.append((chat_id, message)) or {"sent": True, "status": "sent"},
        )
        second = check_notifications(
            send=True,
            channel="telegram",
            log_dir=self.log_dir,
            config=config,
            telegram_sender=lambda chat_id, message: calls.append((chat_id, message)) or {"sent": True, "status": "sent"},
        )

        self.assertTrue(first["recorded"])
        self.assertFalse(second["recorded"])
        self.assertEqual("duplicate_signal_alert", second["dedupe_reason"])
        self.assertEqual(1, len(calls))

    def test_expiring_soon_candidate_alerts_before_freshness_expiry(self) -> None:
        archive.append_signal(
            self._eligible_signal(
                signal_id="notify|expiring",
                hammer_strength=DEFAULT_MINIMUM_HAMMER_STRENGTH,
                rsi_state=None,
                timestamp=(datetime.now(UTC) - timedelta(minutes=27)).isoformat(),
            ),
            log_dir=self.log_dir,
        )

        result = check_notifications(send=False, channel="none", log_dir=self.log_dir)

        self.assertTrue(result["would_alert"])
        self.assertEqual("EXPIRING_SOON", result["alert_type"])
        self.assertEqual("fresh", result["candidate"]["freshness_status"])

    def test_eth_actionable_paper_does_not_produce_operator_alert(self) -> None:
        archive.append_signal(
            self._eligible_signal(
                signal_id="notify|eth",
                symbol="ETHUSDT",
                hammer_strength=DEFAULT_MINIMUM_HAMMER_STRENGTH,
                rsi_state=None,
            ),
            log_dir=self.log_dir,
        )

        result = check_notifications(send=False, channel="none", log_dir=self.log_dir)

        self.assertFalse(result["would_alert"])
        self.assertIsNone(result["alert_type"])
        self.assertFalse(result["live_execution_enabled"])
        self.assertFalse(result["order_placed"])

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
            actionable_paper_enabled=True,
            actionable_paper_min_score=80,
            expiring_soon_minutes=5,
            expired_missed_record_enabled=True,
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
        risk_path = self._write_r267_risk_contract(timeframe="13m", direction="long")
        self._seed_strategy_evidence(timeframe="13m", direction="long")
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
            actionable_paper_enabled=True,
            actionable_paper_min_score=80,
            expiring_soon_minutes=5,
            expired_missed_record_enabled=True,
        )

        with patch("src.app.hammer_radar.operator.trade_ticket.DEFAULT_RISK_CONTRACT_CONFIG_PATH", risk_path), patch(
            "src.app.hammer_radar.operator.tiny_live_strategy_lane_selection.DEFAULT_RISK_CONTRACT_CONFIG_PATH",
            risk_path,
        ):
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
        self.assertEqual("LIVE_READY", records[0]["alert_type"])
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
            actionable_paper_enabled=True,
            actionable_paper_min_score=80,
            expiring_soon_minutes=5,
            expired_missed_record_enabled=True,
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
        hammer_strength: float = 100.0,
        rsi_state: str | None = "neutral",
        divergence_type: str = "bullish",
        bias_direction: str = "bullish",
    ) -> SignalRecord:
        return SignalRecord(
            signal_id=signal_id,
            symbol=symbol,
            timeframe="13m",
            direction=direction,
            timestamp=timestamp or (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            hammer_strength=hammer_strength,
            hammer_high=101.0,
            hammer_low=94.0,
            fib_50=100.5,
            fib_618=100.0,
            fib_650=99.5,
            fib_786=98.5,
            invalidation=95.0,
            bias_timeframe="4H",
            bias_direction=bias_direction,
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
            rsi_state=rsi_state,
            divergence_type=divergence_type,
            divergence_confirmed=True,
        )

    def _seed_strategy_evidence(
        self,
        *,
        timeframe: str = "13m",
        direction: str = "long",
        wins: int = 20,
        losses: int = 10,
    ) -> None:
        base_time = datetime.now(UTC) - timedelta(hours=3)
        for index in range(wins + losses):
            pnl_pct = 1.0 if index < wins else -0.5
            signal_id = f"strategy|{timeframe}|{direction}|{index}"
            timestamp = (base_time + timedelta(minutes=index)).isoformat()
            archive.append_signal(
                self._eligible_signal(
                    signal_id=signal_id,
                    direction=direction,
                    timestamp=timestamp,
                ),
                log_dir=self.log_dir,
            )
            archive.append_outcome(
                OutcomeRecord(
                    signal_id=signal_id,
                    symbol="BTCUSDT",
                    timeframe=timeframe,
                    direction=direction,
                    timestamp=timestamp,
                    entry_price=100.0,
                    exit_price=100.0 + pnl_pct,
                    fill_status="filled",
                    outcome="win" if pnl_pct > 0 else "loss",
                    mae_pct=abs(pnl_pct) / 2.0,
                    mfe_pct=abs(pnl_pct),
                    pnl_pct=pnl_pct,
                    stop_hit=pnl_pct <= 0,
                    evaluated_at=(base_time + timedelta(minutes=index + 1)).isoformat(),
                    entry_mode="ladder_close_50_618",
                ),
                log_dir=self.log_dir,
            )

    def _write_r267_risk_contract(self, *, timeframe: str = "13m", direction: str = "long") -> Path:
        path = self.log_dir / "tiny_live_risk_contracts.json"
        path.write_text(
            json.dumps(
                {
                    "risk_contracts": [
                        {
                            "official_lane_key": f"BTCUSDT|{timeframe}|{direction}|ladder_close_50_618",
                            "symbol": "BTCUSDT",
                            "timeframe": timeframe,
                            "direction": direction,
                            "entry_mode": "ladder_close_50_618",
                            "tiny_live_contract_mode": "explicit_notional_cap_with_leverage",
                            "max_position_notional_usdt": 80.0,
                            "max_notional_usdt": 80.0,
                            "margin_budget_usdt": 8.0,
                            "tiny_live_margin_usdt": 8.0,
                            "leverage": 10.0,
                            "max_loss_usdt": 4.44,
                            "live_execution_enabled": False,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return path


if __name__ == "__main__":
    unittest.main()
