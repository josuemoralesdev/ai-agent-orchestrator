from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.live_policy_arming import (
    build_live_policy_arming_runbook,
    build_live_policy_arming_status,
    evaluate_and_record_live_policy_arming_check,
    load_live_policy_arming_checks,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class LivePolicyArmingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_status_safe(self) -> None:
        payload = build_live_policy_arming_status(env={})

        self.assertEqual("OK", payload["status"])
        self.assertEqual("R74", payload["phase"])
        self.assertFalse(payload["policy_env"]["micro_live_allowed"])
        self.assertFalse(payload["policy_env"]["higher_timeframe_live_allowed"])
        self.assertFalse(payload["execution_env"]["binance_live_enabled"])
        self.assertFalse(payload["execution_env"]["live_execution_enabled"])
        self.assertFalse(payload["execution_env"]["allow_live_orders"])
        self.assertTrue(payload["execution_env"]["global_kill_switch"])
        self.assertFalse(payload["execution_env"]["protective_orders_enabled"])
        self.assertEqual("PREVIEW_ONLY", payload["execution_env"]["protective_order_mode"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])

    def test_env_enabled_status_is_policy_only(self) -> None:
        payload = build_live_policy_arming_status(
            env={
                "HAMMER_MICRO_LIVE_ALLOWED": "true",
                "HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED": "true",
                "HAMMER_LIVE_EXECUTION_ENABLED": "false",
                "HAMMER_ALLOW_LIVE_ORDERS": "false",
            }
        )

        self.assertTrue(payload["policy_env"]["micro_live_allowed"])
        self.assertTrue(payload["policy_env"]["higher_timeframe_live_allowed"])
        self.assertFalse(payload["execution_env"]["live_execution_enabled"])
        self.assertFalse(payload["execution_env"]["allow_live_orders"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_runbook_contains_manual_changes_and_no_secrets(self) -> None:
        payload = build_live_policy_arming_runbook(
            env={
                "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
                "BINANCE_API_KEY": "secret-binance-key",
                "BINANCE_API_SECRET": "secret-binance-secret",
            }
        )
        rendered = str(payload)

        self.assertIn("HAMMER_MICRO_LIVE_ALLOWED=true", payload["manual_changes"])
        self.assertIn("HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED=true", payload["manual_changes"])
        self.assertIn("sudo systemctl restart hammer-approval-api.service", payload["manual_restart_commands"])
        self.assertIn("HAMMER_MICRO_LIVE_ALLOWED=false", payload["rollback_changes"])
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_api_endpoints_are_no_order(self) -> None:
        status = self.client.get("/live/policy-arming/status").json()
        runbook = self.client.get("/live/policy-arming/runbook").json()
        check = self.client.post("/live/policy-arming/check").json()

        self.assertEqual("OK", status["status"])
        self.assertEqual("OK", runbook["status"])
        self.assertEqual("OK", check["status"])
        for payload in (status, runbook, check):
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["secrets_shown"])

    def test_check_persistence_is_sanitized(self) -> None:
        env = {
            LOG_DIR_ENV_VAR: str(self.log_dir),
            "HAMMER_MICRO_LIVE_ALLOWED": "true",
            "TELEGRAM_BOT_TOKEN": "secret-token",
            "BINANCE_API_KEY": "secret-key",
            "BINANCE_API_SECRET": "secret-secret",
        }

        payload = evaluate_and_record_live_policy_arming_check(log_dir=self.log_dir, env=env)
        records = load_live_policy_arming_checks(log_dir=self.log_dir)
        rendered = str(records)

        self.assertTrue(payload["audit_event_recorded"])
        self.assertEqual(1, len(records))
        self.assertTrue(records[0]["policy_env"]["micro_live_allowed"])
        self.assertFalse(records[0]["order_placed"])
        self.assertFalse(records[0]["real_order_placed"])
        self.assertFalse(records[0]["secrets_shown"])
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("secret-key", rendered)
        self.assertNotIn("secret-secret", rendered)

    def test_telegram_policy_arming_commands(self) -> None:
        policy = handle_telegram_operator_command(text="LIVE POLICY ARMING", log_dir=self.log_dir)
        runbook = handle_telegram_operator_command(text="LIVE POLICY RUNBOOK", log_dir=self.log_dir)
        micro = handle_telegram_operator_command(text="LIVE MICRO ARMING", log_dir=self.log_dir)
        higher = handle_telegram_operator_command(text="LIVE HIGHER ARMING", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        for payload in (policy, runbook, micro, higher):
            self.assertEqual("ACCEPTED", payload["result_status"])
            self.assertIn("No order placed", payload["message"])
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["secrets_shown"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])


if __name__ == "__main__":
    unittest.main()
