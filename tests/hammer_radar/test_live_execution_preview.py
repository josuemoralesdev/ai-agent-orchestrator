from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.live_execution_preview import (
    build_live_execution_preview,
    evaluate_and_record_live_execution_preview,
    load_live_execution_previews,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class LiveExecutionPreviewTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_blocked_preview(self) -> None:
        payload = build_live_execution_preview(log_dir=self.log_dir, env={})

        self.assertIn(payload["status"], {"BLOCKED", "NOT_READY"})
        self.assertEqual("R51", payload["phase"])
        self.assertEqual("PREVIEW_ONLY", payload["execution_mode"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["would_place_order"])
        self.assertFalse(payload["secrets_shown"])
        self.assertTrue(payload["blockers"])

    def test_r50_blocked_means_r51_blocked_without_execution(self) -> None:
        with self._patched_candidate(self._candidate()), self._patched_live_begins(status="BLOCKED"):
            payload = build_live_execution_preview(log_dir=self.log_dir, env=self._preview_env())

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("BLOCKED", payload["live_begins_status"])
        self.assertIn("live begins is BLOCKED", payload["blockers"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_fresh_complete_long_candidate_maps_and_calculates_risk(self) -> None:
        with self._patched_candidate(self._candidate(direction="long")), self._patched_live_begins():
            payload = build_live_execution_preview(log_dir=self.log_dir, env=self._preview_env())

        self.assertEqual("PREVIEW_READY", payload["status"])
        self.assertEqual("long", payload["direction"])
        self.assertEqual("BUY", payload["order_side"])
        self.assertEqual("LONG", payload["position_side"])
        self.assertEqual(100.0, payload["entry"])
        self.assertEqual(95.0, payload["stop"])
        self.assertEqual(110.0, payload["take_profit"])
        self.assertGreater(payload["risk_usdt"], 0)
        self.assertFalse(payload["order_placed"])

    def test_fresh_complete_short_candidate_maps_and_calculates_risk(self) -> None:
        candidate = self._candidate(direction="short", entry=100.0, stop=105.0, take_profit=90.0)
        with self._patched_candidate(candidate), self._patched_live_begins():
            payload = build_live_execution_preview(log_dir=self.log_dir, env=self._preview_env())

        self.assertEqual("PREVIEW_READY", payload["status"])
        self.assertEqual("short", payload["direction"])
        self.assertEqual("SELL", payload["order_side"])
        self.assertEqual("SHORT", payload["position_side"])
        self.assertGreater(payload["risk_usdt"], 0)
        self.assertFalse(payload["real_order_placed"])

    def test_missing_entry_stop_take_profit_blocks(self) -> None:
        candidate = self._candidate(entry=None, stop=None, take_profit=None)
        with self._patched_candidate(candidate), self._patched_live_begins():
            payload = build_live_execution_preview(log_dir=self.log_dir, env=self._preview_env())

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["signal_complete"])
        self.assertIn("entry is missing", payload["blockers"])
        self.assertIn("stop is missing", payload["blockers"])
        self.assertIn("take_profit is missing", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_invalid_risk_blocks_for_long_and_short(self) -> None:
        cases = [
            self._candidate(direction="long", entry=100.0, stop=100.0, take_profit=110.0),
            self._candidate(direction="short", entry=100.0, stop=99.0, take_profit=90.0),
        ]
        for candidate in cases:
            with self.subTest(direction=candidate["direction"]):
                with self._patched_candidate(candidate), self._patched_live_begins():
                    payload = build_live_execution_preview(log_dir=self.log_dir, env=self._preview_env())

                self.assertEqual("BLOCKED", payload["status"])
                self.assertFalse(payload["checks"]["risk_valid"])
                self.assertIn("risk is invalid", payload["blockers"])
                self.assertFalse(payload["real_order_placed"])

    def test_protective_orders_required_but_not_ready_blocks(self) -> None:
        with self._patched_candidate(self._candidate()), self._patched_live_begins():
            payload = build_live_execution_preview(log_dir=self.log_dir, env=self._preview_env(protective_enabled=False))

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["protective_orders_ready"])
        self.assertEqual("BLOCKED", payload["protective_orders_preview"]["status"])
        self.assertIn("protective orders are required but not ready/enabled", payload["blockers"])

    def test_protective_preview_ready_when_preview_only_settings_allow(self) -> None:
        with self._patched_candidate(self._candidate()), self._patched_live_begins():
            payload = build_live_execution_preview(log_dir=self.log_dir, env=self._preview_env(protective_enabled=True))

        protective = payload["protective_orders_preview"]
        self.assertEqual("PREVIEW_READY", payload["status"])
        self.assertEqual("READY", protective["status"])
        self.assertIsNotNone(protective["stop_loss"])
        self.assertIsNotNone(protective["take_profit"])
        self.assertTrue(protective["reduce_only"])
        self.assertFalse(payload["order_placed"])

    def test_api_endpoints_return_json_and_post_records_event(self) -> None:
        status_response = self.client.get("/live/execution/preview")
        check_response = self.client.post("/live/execution/preview", json={})
        events = load_live_execution_previews(limit=10, log_dir=self.log_dir)

        self.assertEqual(200, status_response.status_code)
        self.assertEqual(200, check_response.status_code)
        self.assertEqual("R51", status_response.json()["phase"])
        self.assertEqual("PREVIEW_ONLY", check_response.json()["execution_mode"])
        self.assertFalse(status_response.json()["order_placed"])
        self.assertFalse(check_response.json()["real_order_placed"])
        self.assertEqual(1, len(events))
        self.assertEqual("live_execution_preview", events[0]["event_type"])

    def test_telegram_preview_commands_and_blocked_live_commands_are_safe(self) -> None:
        live_preview = handle_telegram_operator_command(text="LIVE PREVIEW", log_dir=self.log_dir)
        first_live_preview = handle_telegram_operator_command(text="FIRST LIVE PREVIEW", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", live_preview["result_status"])
        self.assertEqual("live_execution_preview", live_preview["normalized_action"])
        self.assertIn("R51 protected tiny-live preview", live_preview["message"])
        self.assertEqual("ACCEPTED", first_live_preview["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(live_preview["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_secret_hygiene(self) -> None:
        env = self._preview_env()
        env["TELEGRAM_BOT_TOKEN"] = "secret-telegram-token"
        env["BINANCE_API_KEY"] = "secret-binance-key"
        env["BINANCE_API_SECRET"] = "secret-binance-secret"

        with self._patched_candidate(self._candidate()), self._patched_live_begins():
            payload = build_live_execution_preview(log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("raw env", rendered.lower())

    def test_preview_does_not_call_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = evaluate_and_record_live_execution_preview(log_dir=self.log_dir, env=self._preview_env())

        self.assertIn(payload["status"], {"BLOCKED", "NOT_READY"})
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def _patched_candidate(self, candidate: dict | None):
        return patch("src.app.hammer_radar.operator.live_execution_preview._latest_candidate", return_value=candidate)

    def _patched_live_begins(self, *, status: str = "READY_FOR_OPERATOR_APPROVAL"):
        return patch(
            "src.app.hammer_radar.operator.live_execution_preview.build_live_begins_status",
            return_value={
                "status": status,
                "live_execution_enabled": True,
                "binance_live_enabled": True,
                "allow_live_orders": True,
                "global_kill_switch": False,
            },
        )

    @staticmethod
    def _preview_env(*, protective_enabled: bool = True) -> dict[str, str]:
        return {
            "HAMMER_PROTECTIVE_ORDERS_REQUIRED": "true",
            "HAMMER_PROTECTIVE_ORDERS_ENABLED": "true" if protective_enabled else "false",
            "HAMMER_PROTECTIVE_ORDER_MODE": "PREVIEW_ONLY",
            "HAMMER_TINY_LIVE_PREVIEW_MARGIN_USDT": "6.0",
            "HAMMER_TINY_LIVE_PREVIEW_LEVERAGE": "1",
        }

    @staticmethod
    def _candidate(
        *,
        direction: str = "long",
        entry: float | None = 100.0,
        stop: float | None = 95.0,
        take_profit: float | None = 110.0,
    ) -> dict:
        return {
            "signal_id": f"BTCUSDT|13m|{direction}|2026-05-05T10:00:00+00:00",
            "symbol": "BTCUSDT",
            "timeframe": "13m",
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "take_profit": take_profit,
            "freshness_status": "fresh",
        }


if __name__ == "__main__":
    unittest.main()
