from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_live_adapter_verification import build_first_live_adapter_status
from src.app.hammer_radar.operator.first_live_ladder_submit_adapter import build_first_live_ladder_submit_status
from src.app.hammer_radar.operator.first_live_protective_adapter import build_first_live_protective_status
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstLiveProtectiveAdapterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_protective_status_safe(self) -> None:
        payload = self.client.get("/live/first-protective/status").json()

        self.assertEqual("R63", payload["phase"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_r58_profile_carried_through(self) -> None:
        payload = build_first_live_protective_status(log_dir=self.log_dir, env={})
        profile = payload["profile"]

        self.assertEqual("BTCUSDT", profile["symbol"])
        self.assertEqual(44.0, profile["margin_usdt"])
        self.assertEqual(10, profile["leverage"])
        self.assertEqual(440.0, profile["notional_usdt"])
        self.assertEqual(444.0, profile["max_notional_usdt"])
        self.assertEqual("ISOLATED", profile["margin_mode"])
        self.assertEqual("LADDER", profile["entry_mode"])
        self.assertTrue(profile["protective_orders_required"])

    def test_protective_required_and_no_naked_entry(self) -> None:
        payload = build_first_live_protective_status(log_dir=self.log_dir, env={})
        plan = payload["protective_plan"]
        gate = payload["protective_gate"]

        self.assertTrue(plan["stop_loss_required"])
        self.assertTrue(plan["take_profit_required"])
        self.assertFalse(gate["entry_allowed_without_protective"])
        self.assertTrue(gate["naked_entry_blocked"])

    def test_missing_exact_entry_chain_blocks(self) -> None:
        payload = build_first_live_protective_status(log_dir=self.log_dir, env={})

        self.assertFalse(payload["protective_gate"]["protective_ready_for_live_entry"])
        self.assertFalse(payload["protective_plan"]["side_reduces_entry"])
        self.assertFalse(payload["protective_plan"]["quantity_matches_entry"])

    def test_reduce_only_requirement(self) -> None:
        preview = self._preview(reduce_only=False)
        with self._patched_preview(preview):
            payload = build_first_live_protective_status(log_dir=self.log_dir, env={})

        plan = payload["protective_plan"]
        self.assertTrue(plan["reduce_only_required"])
        self.assertFalse(plan["stop_loss_reduce_only_ok"])
        self.assertFalse(plan["take_profit_reduce_only_ok"])
        self.assertFalse(plan["available"])

        safe = self._preview(reduce_only=False, close_position=True, include_quantity=False)
        with self._patched_preview(safe):
            safe_payload = build_first_live_protective_status(log_dir=self.log_dir, env={})
        self.assertTrue(safe_payload["protective_plan"]["stop_loss_reduce_only_ok"])
        self.assertTrue(safe_payload["protective_plan"]["take_profit_reduce_only_ok"])

    def test_stop_loss_payload_validation(self) -> None:
        with self._patched_preview(self._preview()):
            payload = build_first_live_protective_status(log_dir=self.log_dir, env={})
        self.assertTrue(payload["protective_plan"]["stop_loss_available"])

        missing_trigger = self._preview()
        missing_trigger["protective_orders_preview"]["stop_loss"].pop("stopPrice")
        with self._patched_preview(missing_trigger):
            blocked = build_first_live_protective_status(log_dir=self.log_dir, env={})
        self.assertFalse(blocked["protective_plan"]["stop_loss_available"])

    def test_take_profit_payload_validation(self) -> None:
        with self._patched_preview(self._preview()):
            payload = build_first_live_protective_status(log_dir=self.log_dir, env={})
        self.assertTrue(payload["protective_plan"]["take_profit_available"])

        missing_reduce = self._preview()
        missing_reduce["protective_orders_preview"]["take_profit"]["reduce_only"] = False
        with self._patched_preview(missing_reduce):
            blocked = build_first_live_protective_status(log_dir=self.log_dir, env={})
        self.assertFalse(blocked["protective_plan"]["take_profit_available"])

    def test_quantity_and_side_validation(self) -> None:
        with self._patched_preview(self._preview()):
            payload = build_first_live_protective_status(log_dir=self.log_dir, env={})
        self.assertTrue(payload["protective_plan"]["side_reduces_entry"])
        self.assertTrue(payload["protective_plan"]["quantity_matches_entry"])

        wrong_side = self._preview()
        wrong_side["protective_orders_preview"]["stop_loss"]["side"] = "BUY"
        with self._patched_preview(wrong_side):
            blocked = build_first_live_protective_status(log_dir=self.log_dir, env={})
        self.assertFalse(blocked["protective_plan"]["side_reduces_entry"])

    def test_payload_sanitized(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-binance-key",
            "BINANCE_API_SECRET": "secret-binance-secret",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
        }
        with self._patched_preview(self._preview(include_secret_fields=True)):
            payload = build_first_live_protective_status(log_dir=self.log_dir, env=env)

        rendered = str(payload)
        self.assertFalse(payload["sanitized_payloads"]["signed_payload_created"])
        self.assertFalse(payload["sanitized_payloads"]["secrets_shown"])
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("signature", rendered.lower())
        self.assertNotIn("auth", rendered.lower())

    def test_no_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = build_first_live_protective_status(log_dir=self.log_dir, env={})

        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["real_order_placed"])

    def test_api_endpoints(self) -> None:
        status = self.client.get("/live/first-protective/status").json()
        check = self.client.post("/live/first-protective/check").json()
        checks = self.client.get("/live/first-protective/checks").json()

        self.assertEqual("R63", status["phase"])
        self.assertEqual("R63", check["phase"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertGreaterEqual(checks["count"], 1)
        self.assertFalse(check["real_order_placed"])

    def test_telegram_commands(self) -> None:
        check = handle_telegram_operator_command(text="FIRST LIVE PROTECTIVE CHECK", log_dir=self.log_dir)
        stop = handle_telegram_operator_command(text="FIRST LIVE STOP CHECK", log_dir=self.log_dir)
        take = handle_telegram_operator_command(text="FIRST LIVE TAKE PROFIT CHECK", log_dir=self.log_dir)
        payload = handle_telegram_operator_command(text="FIRST LIVE PROTECTIVE PAYLOAD", log_dir=self.log_dir)
        checks = handle_telegram_operator_command(text="FIRST LIVE PROTECTIVE CHECKS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", check["result_status"])
        self.assertEqual("ACCEPTED", stop["result_status"])
        self.assertEqual("ACCEPTED", take["result_status"])
        self.assertEqual("ACCEPTED", payload["result_status"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(trade_now["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_r61_integration_remains_conservative(self) -> None:
        payload = build_first_live_adapter_status(log_dir=self.log_dir, env={})

        self.assertTrue(payload["no_naked_entry_status"]["naked_entry_blocked"])
        self.assertFalse(payload["live_submit_status"]["live_protective_submit_available"])
        self.assertFalse(payload["protective_adapter_status"]["available"])

    def test_r62_integration_still_blocks_live_submit(self) -> None:
        payload = build_first_live_ladder_submit_status(log_dir=self.log_dir, env={})

        self.assertFalse(payload["submit_gate"]["protective_ready"])
        self.assertFalse(payload["submit_gate"]["live_submit_allowed"])

    def _patched_preview(self, preview: dict):
        return patch.multiple(
            "src.app.hammer_radar.operator.first_live_protective_adapter",
            build_live_execution_preview=lambda **_: preview,
            build_first_live_ladder_submit_status=lambda **_: self._ladder(preview),
        )

    @staticmethod
    def _ladder(preview: dict) -> dict:
        direction = str(preview.get("direction") or "long").lower()
        return {
            "ladder_submit_plan": {
                "side": "BUY" if direction != "short" else "SELL",
                "quantity": 0.005,
                "quantity_valid": True,
                "aggregate_preview_only": True,
            }
        }

    @staticmethod
    def _preview(
        *,
        reduce_only: bool = True,
        close_position: bool = False,
        include_quantity: bool = True,
        include_secret_fields: bool = False,
    ) -> dict:
        common = {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "quantity": 0.005,
            "reduce_only": reduce_only,
            "preview_only": True,
        }
        if close_position:
            common["closePosition"] = True
            common.pop("quantity", None)
        if not include_quantity:
            common.pop("quantity", None)
        if include_secret_fields:
            common["signature"] = "secret-signature"
            common["auth_header"] = "secret-auth"
            common["api_key"] = "secret-key"
        return {
            "status": "PREVIEW_READY",
            "direction": "long",
            "protective_orders_preview": {
                "stop_loss": {
                    **common,
                    "protective_role": "stop_loss",
                    "order_type": "STOP_MARKET",
                    "stopPrice": 80500.0,
                },
                "take_profit": {
                    **common,
                    "protective_role": "take_profit",
                    "order_type": "TAKE_PROFIT_MARKET",
                    "stopPrice": 83000.0,
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
