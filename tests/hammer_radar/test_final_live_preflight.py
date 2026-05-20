from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.final_live_preflight import (
    BLOCKED,
    build_final_live_preflight,
    format_final_live_preflight_text,
)


class FinalLivePreflightTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_final_preflight_blocks_when_live_flags_are_false(self) -> None:
        payload = build_final_live_preflight(log_dir=self.log_dir, env={})

        self.assertEqual(BLOCKED, payload["status"])
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["live_orders_allowed"])
        self.assertIn("live execution disabled", payload["blockers"])
        self.assertIn("live orders disabled", payload["blockers"])

    def test_final_preflight_blocks_when_kill_switch_is_active(self) -> None:
        payload = build_final_live_preflight(
            log_dir=self.log_dir,
            env={
                "HAMMER_BINANCE_LIVE_ENABLED": "true",
                "HAMMER_LIVE_EXECUTION_ENABLED": "true",
                "HAMMER_ALLOW_LIVE_ORDERS": "true",
                "HAMMER_GLOBAL_KILL_SWITCH": "true",
                "HAMMER_BINANCE_CONNECTOR_MODE": "LIVE_ORDER_ENABLED",
                "BINANCE_API_KEY": "present-key",
                "BINANCE_API_SECRET": "present-secret",
            },
        )

        self.assertEqual(BLOCKED, payload["status"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertIn("global kill switch active", payload["blockers"])

    def test_missing_binance_credentials_are_reported_safely(self) -> None:
        payload = build_final_live_preflight(log_dir=self.log_dir, env={})

        self.assertEqual(
            {"api_key_present": False, "api_secret_present": False},
            payload["binance_credentials_present"],
        )
        self.assertIn("missing Binance credentials", payload["blockers"])

    def test_secrets_are_never_exposed(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "TELEGRAM_CHAT_ID": "secret-chat-id",
        }

        payload = build_final_live_preflight(log_dir=self.log_dir, env=env)
        rendered = json.dumps(payload, sort_keys=True)

        self.assertTrue(payload["binance_credentials_present"]["api_key_present"])
        self.assertTrue(payload["binance_credentials_present"]["api_secret_present"])
        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-chat-id", rendered)
        self.assertFalse(payload["safety"]["secrets_shown"])

    def test_source_surfaces_used_is_populated(self) -> None:
        payload = build_final_live_preflight(log_dir=self.log_dir, env={})

        self.assertGreater(len(payload["source_surfaces_used"]), 5)
        self.assertIn("operator.live_arming_preflight.build_live_arming_preflight", payload["source_surfaces_used"])
        self.assertIn("execution.binance_futures_connector.build_connector_status", payload["source_surfaces_used"])

    def test_no_order_placement_path_is_called(self) -> None:
        with patch("src.app.hammer_radar.execution.binance_futures_connector.execute_live_order") as execute_live_order:
            payload = build_final_live_preflight(log_dir=self.log_dir, env={})

        execute_live_order.assert_not_called()
        self.assertFalse(payload["safety"]["order_placed"])
        self.assertFalse(payload["safety"]["real_order_placed"])
        self.assertFalse(payload["safety"]["execution_attempted"])

    def test_output_includes_exact_blocker_list(self) -> None:
        payload = build_final_live_preflight(log_dir=self.log_dir, env={})

        self.assertIsInstance(payload["blockers"], list)
        self.assertIn("missing final review packet", payload["blockers"])
        self.assertIn("missing human approval record", payload["blockers"])
        self.assertIn("protective readiness false", payload["blockers"])
        self.assertIn("environment boundary blocked", payload["blockers"])

    def test_paper_live_separation_remains_intact(self) -> None:
        payload = build_final_live_preflight(log_dir=self.log_dir, env={})

        self.assertTrue(payload["paper_live_separation_intact"])
        self.assertFalse(payload["safety"]["order_payload_created"])
        self.assertFalse(payload["safety"]["signed_payload_created"])
        self.assertFalse(payload["safety"]["network_used"])

    def test_cli_formatter_returns_json(self) -> None:
        payload = build_final_live_preflight(log_dir=self.log_dir, env={})
        rendered = format_final_live_preflight_text(payload)

        parsed = json.loads(rendered)
        self.assertEqual(BLOCKED, parsed["status"])
        self.assertIn("source_surfaces_used", parsed)


if __name__ == "__main__":
    unittest.main()
