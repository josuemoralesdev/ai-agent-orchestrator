from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_live_adapter_verification import build_first_live_adapter_status
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstLiveAdapterVerificationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_adapter_status_safe(self) -> None:
        payload = self.client.get("/live/first-adapter/status").json()

        self.assertEqual("R61", payload["phase"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r58_profile_carried_through(self) -> None:
        payload = build_first_live_adapter_status(log_dir=self.log_dir, env={})
        profile = payload["profile"]

        self.assertEqual("BTCUSDT", profile["symbol"])
        self.assertEqual(44.0, profile["margin_usdt"])
        self.assertEqual(10, profile["leverage"])
        self.assertEqual(440.0, profile["notional_usdt"])
        self.assertEqual(444.0, profile["max_notional_usdt"])
        self.assertEqual("ISOLATED", profile["margin_mode"])
        self.assertEqual("LADDER", profile["entry_mode"])
        self.assertTrue(profile["one_attempt_only"])

    def test_ladder_total_cap(self) -> None:
        payload = build_first_live_adapter_status(log_dir=self.log_dir, env={})
        ladder = payload["ladder_adapter_status"]

        self.assertEqual(44.0, ladder["margin_total_cap_usdt"])
        self.assertEqual(444.0, ladder["notional_total_cap_usdt"])
        self.assertTrue(ladder["uses_total_margin_cap"])
        self.assertFalse(ladder["per_step_margin_violation"])
        self.assertEqual(440.0, ladder["aggregate_entry_payload_preview"]["notional_usdt_total"])

    def test_missing_ladder_live_adapter_blocks(self) -> None:
        payload = build_first_live_adapter_status(log_dir=self.log_dir, env={})
        ladder = payload["ladder_adapter_status"]

        self.assertFalse(ladder["available"])
        self.assertIn("live ladder submit adapter not implemented", ladder["blockers"])

    def test_protective_required_and_missing_adapter_blocks(self) -> None:
        payload = build_first_live_adapter_status(log_dir=self.log_dir, env={})
        protective = payload["protective_adapter_status"]

        self.assertTrue(protective["protective_orders_required"])
        self.assertFalse(protective["available"])
        self.assertFalse(protective["stop_loss_available"])
        self.assertFalse(protective["take_profit_available"])
        self.assertIn("protective live adapter unavailable", protective["blockers"])

    def test_reduce_only_requirement_when_preview_exists(self) -> None:
        with patch(
            "src.app.hammer_radar.operator.first_live_adapter_verification.build_live_execution_preview",
            return_value=self._preview(),
        ):
            payload = build_first_live_adapter_status(log_dir=self.log_dir, env={})

        protective = payload["protective_adapter_status"]
        self.assertTrue(protective["stop_loss_available"])
        self.assertTrue(protective["take_profit_available"])
        self.assertTrue(protective["reduce_only_ok"])
        self.assertTrue(protective["close_position_or_quantity_ok"])

    def test_no_naked_entry(self) -> None:
        payload = build_first_live_adapter_status(log_dir=self.log_dir, env={})
        naked = payload["no_naked_entry_status"]

        self.assertTrue(naked["naked_entry_blocked"])
        self.assertTrue(naked["entry_requires_protective_ready"])
        self.assertFalse(naked["entry_allowed_without_protective"])

    def test_test_order_path_no_network_by_default(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = build_first_live_adapter_status(log_dir=self.log_dir, env={})

        test_order = payload["test_order_status"]
        self.assertTrue(test_order["test_order_required_before_live"])
        self.assertTrue(test_order["test_order_path_available"])
        self.assertFalse(test_order["test_order_network_enabled"])
        self.assertFalse(test_order["test_order_validated_for_signal"])

    def test_live_submit_conservative(self) -> None:
        payload = build_first_live_adapter_status(log_dir=self.log_dir, env={})
        live = payload["live_submit_status"]

        self.assertFalse(live["live_submit_available"])
        self.assertFalse(live["live_ladder_submit_available"])
        self.assertFalse(live["live_protective_submit_available"])
        self.assertTrue(live["live_submit_not_implemented"])
        self.assertFalse(payload["order_placed"])

    def test_api_endpoints(self) -> None:
        status = self.client.get("/live/first-adapter/status").json()
        check = self.client.post("/live/first-adapter/check").json()
        checks = self.client.get("/live/first-adapter/checks").json()

        self.assertEqual("R61", status["phase"])
        self.assertEqual("R61", check["phase"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertGreaterEqual(checks["count"], 1)
        self.assertFalse(check["real_order_placed"])

    def test_telegram_commands(self) -> None:
        full = handle_telegram_operator_command(text="FIRST LIVE ADAPTER CHECK", log_dir=self.log_dir)
        ladder = handle_telegram_operator_command(text="FIRST LIVE LADDER ADAPTER", log_dir=self.log_dir)
        protective = handle_telegram_operator_command(text="FIRST LIVE PROTECTIVE ADAPTER", log_dir=self.log_dir)
        naked = handle_telegram_operator_command(text="FIRST LIVE NO NAKED ENTRY", log_dir=self.log_dir)
        checks = handle_telegram_operator_command(text="FIRST LIVE ADAPTER CHECKS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", full["result_status"])
        self.assertEqual("ACCEPTED", ladder["result_status"])
        self.assertEqual("ACCEPTED", protective["result_status"])
        self.assertEqual("ACCEPTED", naked["result_status"])
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
        payload = build_first_live_adapter_status(log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)

    @staticmethod
    def _preview() -> dict:
        return {
            "status": "PREVIEW_READY",
            "direction": "long",
            "protective_orders_preview": {
                "stop_loss": {"trigger_price": 80500.0, "side": "SELL", "reduce_only": True, "preview_only": True},
                "take_profit": {"trigger_price": 83000.0, "side": "SELL", "reduce_only": True, "preview_only": True},
                "reduce_only": True,
                "status": "READY",
            },
            "order_placed": False,
            "real_order_placed": False,
            "secrets_shown": False,
        }


if __name__ == "__main__":
    unittest.main()
