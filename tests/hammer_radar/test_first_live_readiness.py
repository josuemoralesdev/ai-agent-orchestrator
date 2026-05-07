from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_live_readiness import (
    build_first_live_readiness_status,
    evaluate_and_record_first_live_readiness,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstLiveReadinessTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_readiness_blocked_safe(self) -> None:
        payload = self.client.get("/live/first-readiness/status").json()

        self.assertEqual("R59", payload["phase"])
        self.assertIn(payload["status"], {"BLOCKED", "NOT_READY", "READY_FOR_MANUAL_ENV_ARMING"})
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_cap_alignment_detects_legacy_conflict(self) -> None:
        payload = build_first_live_readiness_status(log_dir=self.log_dir, env={})
        caps = payload["cap_status"]

        self.assertTrue(caps["legacy_cap_conflict"])
        self.assertEqual(44.0, caps["legacy_max_position_usd"])
        self.assertEqual(3.0, caps["legacy_max_leverage"])
        self.assertIn("legacy HAMMER_LIVE_MAX_POSITION_USD", "; ".join(caps["blockers"]))

    def test_first_live_cap_values(self) -> None:
        payload = build_first_live_readiness_status(log_dir=self.log_dir, env={})
        caps = payload["cap_status"]

        self.assertEqual(44.0, payload["profile"]["margin_usdt"])
        self.assertEqual(10, payload["profile"]["leverage"])
        self.assertEqual(440.0, caps["profile_notional_usdt"])
        self.assertEqual(444.0, caps["required_max_notional_usdt"])
        self.assertEqual(10, caps["required_max_leverage"])
        self.assertTrue(caps["margin_cap_ok"])
        self.assertTrue(caps["notional_cap_ok"])
        self.assertTrue(caps["leverage_cap_ok"])

    def test_env_files_surfaced_without_secrets(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-binance-key",
            "BINANCE_API_SECRET": "secret-binance-secret",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
        }
        payload = build_first_live_readiness_status(log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertIn("/home/josue/.config/hammer-radar/binance-readonly.env", payload["env_status"]["env_files"])
        self.assertIn("/home/josue/.config/hammer-radar/notifications.env", payload["env_status"]["env_files"])
        self.assertTrue(payload["env_status"]["binance_key_present"])
        self.assertTrue(payload["env_status"]["binance_secret_present"])
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)

    def test_manual_env_plan_present_and_does_not_modify_env(self) -> None:
        before = dict()
        payload = evaluate_and_record_first_live_readiness(log_dir=self.log_dir, env=before)
        plan = payload["manual_env_plan"]
        profile_values = [item for item in plan if item["group"] == "profile_caps"][0]["values"]
        arming_values = [item for item in plan if item["group"] == "live_arming"][0]["values"]
        rollback_values = [item for item in plan if item["group"] == "rollback"][0]["values"]

        self.assertEqual("44", profile_values["HAMMER_FIRST_LIVE_MARGIN_USDT"])
        self.assertEqual("10", profile_values["HAMMER_FIRST_LIVE_LEVERAGE"])
        self.assertEqual("444", profile_values["HAMMER_FIRST_LIVE_MAX_NOTIONAL_USDT"])
        self.assertEqual("LIVE_ORDER_ENABLED", arming_values["HAMMER_BINANCE_CONNECTOR_MODE"])
        self.assertEqual("DRY_RUN_ONLY", rollback_values["HAMMER_BINANCE_CONNECTOR_MODE"])
        self.assertEqual({}, before)

    def test_funds_status_safe_no_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = build_first_live_readiness_status(log_dir=self.log_dir, env={})

        funds = payload["funds_status"]
        self.assertFalse(funds["checked"])
        self.assertFalse(funds["network_used"])
        self.assertEqual(44.0, funds["required_margin_usdt"])
        self.assertFalse(funds["has_required_margin"])

    def test_adapter_status_conservative(self) -> None:
        payload = build_first_live_readiness_status(log_dir=self.log_dir, env={})
        adapter = payload["adapter_status"]

        self.assertFalse(adapter["live_submit_adapter_available"])
        self.assertFalse(adapter["live_ladder_submit_available"])
        self.assertFalse(adapter["protective_live_adapter_available"])
        self.assertTrue(adapter["test_order_available"])

    def test_api_endpoints(self) -> None:
        status = self.client.get("/live/first-readiness/status").json()
        check = self.client.post("/live/first-readiness/check").json()
        checks = self.client.get("/live/first-readiness/checks").json()

        self.assertEqual("R59", status["phase"])
        self.assertEqual("R59", check["phase"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertGreaterEqual(checks["count"], 1)
        self.assertFalse(status["order_placed"])
        self.assertFalse(check["real_order_placed"])

    def test_telegram_commands(self) -> None:
        readiness = handle_telegram_operator_command(text="FIRST LIVE READINESS", log_dir=self.log_dir)
        caps = handle_telegram_operator_command(text="FIRST LIVE CAPS", log_dir=self.log_dir)
        funds = handle_telegram_operator_command(text="FIRST LIVE FUNDS", log_dir=self.log_dir)
        adapter = handle_telegram_operator_command(text="FIRST LIVE ADAPTER", log_dir=self.log_dir)
        checks = handle_telegram_operator_command(text="FIRST LIVE READINESS CHECKS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", readiness["result_status"])
        self.assertEqual("ACCEPTED", caps["result_status"])
        self.assertEqual("ACCEPTED", funds["result_status"])
        self.assertEqual("ACCEPTED", adapter["result_status"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(trade_now["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])


if __name__ == "__main__":
    unittest.main()
