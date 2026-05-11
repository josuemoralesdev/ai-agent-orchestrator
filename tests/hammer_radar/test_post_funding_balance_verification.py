from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.post_funding_balance_verification import (
    build_post_funding_balance_runbook,
    build_post_funding_balance_status,
    evaluate_and_record_post_funding_balance_check,
    evaluate_manual_balance,
    load_post_funding_balance_checks,
)
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class PostFundingBalanceVerificationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_status_default_awaiting_manual_balance(self) -> None:
        payload = build_post_funding_balance_status(env={}, log_dir=self.log_dir)

        self.assertEqual("AWAITING_BALANCE_INPUT", payload["status"])
        self.assertEqual("R77", payload["phase"])
        self.assertEqual("manual_required", payload["balance_source"])
        self.assertEqual(44.0, payload["balance_status"]["minimum_required_available_usdt"])
        self.assertEqual(88.0, payload["balance_status"]["preferred_available_usdt"])
        self.assertEqual(100.0, payload["balance_status"]["do_not_exceed_initial_funding_usdt"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["secrets_shown"])

    def test_balance_below_44_not_enough(self) -> None:
        payload = evaluate_manual_balance(25, env={}, log_dir=self.log_dir)

        self.assertEqual("NOT_ENOUGH_BALANCE", payload["status"])
        self.assertFalse(payload["balance_status"]["enough_for_first_margin"])
        self.assertFalse(payload["order_placed"])

    def test_balance_44_marginal(self) -> None:
        payload = evaluate_manual_balance(44, env={}, log_dir=self.log_dir)

        self.assertEqual("MARGINAL_BALANCE", payload["status"])
        self.assertTrue(payload["balance_status"]["enough_for_first_margin"])
        self.assertFalse(payload["balance_status"]["preferred_buffer_ok"])
        self.assertTrue(any("preferred 88" in item for item in payload["warnings"]))

    def test_balance_88_ready_after_funding(self) -> None:
        payload = evaluate_manual_balance(88, env={}, log_dir=self.log_dir)

        self.assertEqual("READY_AFTER_FUNDING", payload["status"])
        self.assertTrue(payload["balance_status"]["enough_for_first_margin"])
        self.assertTrue(payload["balance_status"]["preferred_buffer_ok"])
        self.assertFalse(payload["real_order_placed"])

    def test_balance_above_100_warns(self) -> None:
        payload = evaluate_manual_balance(101, env={}, log_dir=self.log_dir)

        self.assertEqual("READY_AFTER_FUNDING", payload["status"])
        self.assertTrue(any("exceeds 100" in item for item in payload["warnings"]))
        self.assertFalse(payload["order_placed"])

    def test_execution_enabled_blocks(self) -> None:
        payload = evaluate_manual_balance(
            88,
            env={"HAMMER_LIVE_EXECUTION_ENABLED": "true", "HAMMER_ALLOW_LIVE_ORDERS": "true"},
            log_dir=self.log_dir,
        )

        self.assertEqual("BLOCKED", payload["status"])
        self.assertTrue(any("HAMMER_LIVE_EXECUTION_ENABLED" in item for item in payload["blockers"]))
        self.assertFalse(payload["order_placed"])

    def test_api_endpoints(self) -> None:
        status = self.client.get("/live/funding-balance/status").json()
        runbook = self.client.get("/live/funding-balance/runbook").json()
        check = self.client.post("/live/funding-balance/check", json={"available_usdt": 88}).json()

        self.assertEqual("R77", status["phase"])
        self.assertEqual("R77", runbook["phase"])
        self.assertEqual("READY_AFTER_FUNDING", check["status"])
        for payload in (status, runbook, check):
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["execution_attempted"])
            self.assertFalse(payload["secrets_shown"])

    def test_persistence_sanitized(self) -> None:
        env = {
            LOG_DIR_ENV_VAR: str(self.log_dir),
            "TELEGRAM_BOT_TOKEN": "secret-token",
            "BINANCE_API_KEY": "secret-key",
            "BINANCE_API_SECRET": "secret-secret",
        }

        payload = evaluate_and_record_post_funding_balance_check(available_usdt=88, env=env, log_dir=self.log_dir)
        records = load_post_funding_balance_checks(log_dir=self.log_dir)
        rendered = str(records)

        self.assertTrue(payload["audit_event_recorded"])
        self.assertEqual(1, len(records))
        self.assertFalse(records[0]["order_placed"])
        self.assertFalse(records[0]["real_order_placed"])
        self.assertFalse(records[0]["execution_attempted"])
        self.assertFalse(records[0]["secrets_shown"])
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("secret-key", rendered)
        self.assertNotIn("secret-secret", rendered)

    def test_telegram_commands(self) -> None:
        readiness = handle_telegram_operator_command(text="LIVE BALANCE READINESS", log_dir=self.log_dir)
        runbook = handle_telegram_operator_command(text="LIVE BALANCE RUNBOOK", log_dir=self.log_dir)
        check = handle_telegram_operator_command(text="LIVE BALANCE CHECK 88", log_dir=self.log_dir)
        invalid = handle_telegram_operator_command(text="LIVE BALANCE CHECK nope", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", readiness["result_status"])
        self.assertEqual("ACCEPTED", runbook["result_status"])
        self.assertEqual("ACCEPTED", check["result_status"])
        self.assertEqual("REJECTED", invalid["result_status"])
        for payload in (readiness, runbook, check):
            self.assertIn("No order placed", payload["message"])
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["secrets_shown"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])

    def test_runbook_no_secrets(self) -> None:
        payload = build_post_funding_balance_runbook(
            env={
                "TELEGRAM_BOT_TOKEN": "secret-token",
                "BINANCE_API_KEY": "secret-key",
                "BINANCE_API_SECRET": "secret-secret",
            }
        )
        rendered = str(payload)

        self.assertIn("LIVE BALANCE CHECK 88", rendered)
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("secret-key", rendered)
        self.assertNotIn("secret-secret", rendered)


if __name__ == "__main__":
    unittest.main()
