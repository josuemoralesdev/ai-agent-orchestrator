from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_live_adapter_verification import build_first_live_adapter_status
from src.app.hammer_radar.operator.first_live_ladder_submit_adapter import build_first_live_ladder_submit_status
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstLiveLadderSubmitAdapterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_ladder_status_safe(self) -> None:
        payload = self.client.get("/live/first-ladder/status").json()

        self.assertEqual("R62", payload["phase"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r58_profile_carried_through(self) -> None:
        payload = build_first_live_ladder_submit_status(log_dir=self.log_dir, env={})
        profile = payload["profile"]

        self.assertEqual("BTCUSDT", profile["symbol"])
        self.assertEqual(44.0, profile["margin_usdt"])
        self.assertEqual(10, profile["leverage"])
        self.assertEqual(440.0, profile["notional_usdt"])
        self.assertEqual(444.0, profile["max_notional_usdt"])
        self.assertEqual("ISOLATED", profile["margin_mode"])
        self.assertEqual("LADDER", profile["entry_mode"])
        self.assertTrue(profile["one_attempt_only"])

    def test_total_margin_cap(self) -> None:
        payload = build_first_live_ladder_submit_status(log_dir=self.log_dir, env={})
        plan = payload["ladder_submit_plan"]

        self.assertTrue(plan["uses_total_margin_cap"])
        self.assertEqual(44.0, plan["margin_total_cap_usdt"])
        self.assertEqual(44.0, plan["planned_margin_usdt"])
        self.assertFalse(plan["per_step_margin_violation"])

    def test_notional_cap(self) -> None:
        payload = build_first_live_ladder_submit_status(log_dir=self.log_dir, env={})
        plan = payload["ladder_submit_plan"]

        self.assertEqual(440.0, plan["planned_notional_usdt"])
        self.assertEqual(444.0, plan["notional_total_cap_usdt"])
        self.assertTrue(plan["notional_cap_ok"])

        capped = build_first_live_ladder_submit_status(
            log_dir=self.log_dir,
            env={},
            profile={"margin_usdt": 45, "leverage": 10, "max_notional_usdt": 444, "margin_mode": "ISOLATED", "entry_mode": "LADDER"},
        )
        self.assertEqual("BLOCKED", capped["status"])
        self.assertFalse(capped["ladder_submit_plan"]["notional_cap_ok"])

    def test_quantity_validity(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.first_live_ladder_submit_adapter.build_live_execution_preview",
            return_value={"status": "PREVIEW_READY", "entry": 81300.0, "direction": "long"},
        ):
            payload = build_first_live_ladder_submit_status(log_dir=self.log_dir, env={})

        plan = payload["ladder_submit_plan"]
        self.assertEqual(0.005, plan["quantity"])
        self.assertTrue(plan["quantity_valid"])

    def test_missing_exact_chain_blocks_live(self) -> None:
        payload = build_first_live_ladder_submit_status(log_dir=self.log_dir, env={})
        gate = payload["submit_gate"]

        self.assertFalse(gate["r50_allows"])
        self.assertFalse(gate["r52_allows"])
        self.assertFalse(gate["r53_allows"])
        self.assertFalse(gate["live_submit_allowed"])

    def test_protective_dependency_blocks_live(self) -> None:
        payload = build_first_live_ladder_submit_status(log_dir=self.log_dir, env={})

        self.assertFalse(payload["submit_gate"]["protective_ready"])
        self.assertFalse(payload["submit_gate"]["live_submit_allowed"])
        self.assertIn("protective adapter not ready; no naked entry allowed", payload["blockers"])

    def test_env_and_funds_dependency_blocks_live(self) -> None:
        payload = build_first_live_ladder_submit_status(log_dir=self.log_dir, env={})
        gate = payload["submit_gate"]

        self.assertFalse(gate["live_env_allows"])
        self.assertFalse(gate["funds_ready"])
        self.assertFalse(gate["live_submit_allowed"])

    def test_payload_preview_sanitized(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-binance-key",
            "BINANCE_API_SECRET": "secret-binance-secret",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
        }
        payload = build_first_live_ladder_submit_status(log_dir=self.log_dir, env=env)
        rendered = str(payload)
        aggregate = payload["sanitized_payloads"]["aggregate_entry_payload"]

        self.assertIsNotNone(aggregate)
        self.assertFalse(payload["sanitized_payloads"]["signed_payload_created"])
        self.assertFalse(payload["sanitized_payloads"]["secrets_shown"])
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("signature", rendered.lower())

    def test_no_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = build_first_live_ladder_submit_status(log_dir=self.log_dir, env={})

        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["real_order_placed"])

    def test_api_endpoints(self) -> None:
        status = self.client.get("/live/first-ladder/status").json()
        check = self.client.post("/live/first-ladder/check").json()
        checks = self.client.get("/live/first-ladder/checks").json()

        self.assertEqual("R62", status["phase"])
        self.assertEqual("R62", check["phase"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertGreaterEqual(checks["count"], 1)
        self.assertFalse(check["real_order_placed"])

    def test_telegram_commands(self) -> None:
        check = handle_telegram_operator_command(text="FIRST LIVE LADDER CHECK", log_dir=self.log_dir)
        plan = handle_telegram_operator_command(text="FIRST LIVE LADDER PLAN", log_dir=self.log_dir)
        payload = handle_telegram_operator_command(text="FIRST LIVE LADDER PAYLOAD", log_dir=self.log_dir)
        checks = handle_telegram_operator_command(text="FIRST LIVE LADDER CHECKS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", check["result_status"])
        self.assertEqual("ACCEPTED", plan["result_status"])
        self.assertEqual("ACCEPTED", payload["result_status"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(trade_now["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_r61_integration_remains_conservative(self) -> None:
        payload = build_first_live_adapter_status(log_dir=self.log_dir, env={})
        ladder = payload["ladder_adapter_status"]

        self.assertTrue(ladder["ladder_submit_plan_available"])
        self.assertTrue(ladder["aggregate_preview_only"])
        self.assertFalse(ladder["ladder_child_orders_available"])
        self.assertFalse(payload["live_submit_status"]["live_ladder_submit_available"])
        self.assertTrue(payload["no_naked_entry_status"]["naked_entry_blocked"])


if __name__ == "__main__":
    unittest.main()
