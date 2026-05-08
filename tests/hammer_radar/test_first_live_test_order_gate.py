from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_live_test_order_gate import (
    build_first_live_test_order_status,
    evaluate_and_record_first_live_test_order_check,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstLiveTestOrderGateTestCase(unittest.TestCase):
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
        payload = self.client.get("/live/first-test-order/status").json()

        self.assertEqual("R64", payload["phase"])
        self.assertIn(payload["status"], {"BLOCKED", "NOT_READY", "EXACT_CHAIN_MISSING"})
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_missing_ids_blocks(self) -> None:
        payload = self.client.post("/live/first-test-order/check", json={}).json()

        self.assertFalse(payload["exact_chain_status"]["exact_chain_resolved"])
        self.assertTrue(payload["blockers"])
        self.assertIn("required", " ".join(payload["exact_chain_status"]["blockers"]))

    def test_r58_profile_carried_through(self) -> None:
        payload = build_first_live_test_order_status(log_dir=self.log_dir, env={})
        profile = payload["profile"]

        self.assertEqual("BTCUSDT", profile["symbol"])
        self.assertEqual(44.0, profile["margin_usdt"])
        self.assertEqual(10, profile["leverage"])
        self.assertEqual(440.0, profile["notional_usdt"])
        self.assertEqual(444.0, profile["max_notional_usdt"])
        self.assertEqual("ISOLATED", profile["margin_mode"])
        self.assertEqual("LADDER", profile["entry_mode"])
        self.assertTrue(profile["protective_orders_required"])
        self.assertTrue(profile["one_attempt_only"])

    def test_exact_chain_missing_blocks(self) -> None:
        by_signal = build_first_live_test_order_status(signal_id="BTCUSDT|13m|long|2026-05-05T10:00:00+00:00", log_dir=self.log_dir, env={})
        by_rehearsal = build_first_live_test_order_status(executor_rehearsal_id="missing", log_dir=self.log_dir, env={})

        self.assertFalse(by_signal["exact_chain_status"]["exact_chain_resolved"])
        self.assertFalse(by_signal["exact_chain_status"]["intent_found"])
        self.assertFalse(by_rehearsal["exact_chain_status"]["exact_chain_resolved"])
        self.assertFalse(by_rehearsal["exact_chain_status"]["rehearsal_found"])

    def test_payload_readiness_false_by_default(self) -> None:
        payload = build_first_live_test_order_status(log_dir=self.log_dir, env={})
        readiness = payload["payload_readiness"]

        self.assertFalse(readiness["entry_payload_ready"])
        self.assertFalse(readiness["protective_payloads_ready"])
        self.assertFalse(readiness["stop_loss_ready"])
        self.assertFalse(readiness["take_profit_ready"])
        self.assertTrue(readiness["no_naked_entry_ok"])

    def test_test_order_required_by_default(self) -> None:
        payload = build_first_live_test_order_status(log_dir=self.log_dir, env={})
        test_order = payload["test_order_status"]

        self.assertTrue(test_order["test_order_required"])
        self.assertTrue(test_order["test_order_path_available"])
        self.assertFalse(test_order["test_order_network_enabled"])
        self.assertFalse(test_order["test_order_validated_for_signal"])
        self.assertTrue(test_order["blockers"])

    def test_no_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = build_first_live_test_order_status(log_dir=self.log_dir, env={})

        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["real_order_placed"])

    def test_api_endpoints_persist_sanitized_event(self) -> None:
        status = self.client.get("/live/first-test-order/status").json()
        check = self.client.post("/live/first-test-order/check", json={}).json()
        checks = self.client.get("/live/first-test-order/checks").json()

        self.assertEqual("R64", status["phase"])
        self.assertEqual("R64", check["phase"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertGreaterEqual(checks["count"], 1)
        self.assertFalse(check["order_placed"])
        self.assertFalse(checks["checks"][0]["real_order_placed"])

    def test_telegram_commands(self) -> None:
        first = handle_telegram_operator_command(text="FIRST LIVE TEST ORDER", log_dir=self.log_dir)
        check = handle_telegram_operator_command(text="FIRST LIVE TEST ORDER CHECK", log_dir=self.log_dir)
        exact = handle_telegram_operator_command(text="FIRST LIVE EXACT CHAIN", log_dir=self.log_dir)
        readiness = handle_telegram_operator_command(text="FIRST LIVE PAYLOAD READINESS", log_dir=self.log_dir)
        checks = handle_telegram_operator_command(text="FIRST LIVE TEST ORDER CHECKS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("EXACT_CHAIN_MISSING", first["result_status"])
        self.assertEqual("EXACT_CHAIN_MISSING", check["result_status"])
        self.assertEqual("EXACT_CHAIN_MISSING", exact["result_status"])
        self.assertEqual("EXACT_CHAIN_MISSING", readiness["result_status"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(trade_now["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_secret_hygiene(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-binance-key",
            "BINANCE_API_SECRET": "secret-binance-secret",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
        }

        payload = evaluate_and_record_first_live_test_order_check(log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("signature", rendered.lower())
        self.assertNotIn("auth", rendered.lower())


if __name__ == "__main__":
    unittest.main()
