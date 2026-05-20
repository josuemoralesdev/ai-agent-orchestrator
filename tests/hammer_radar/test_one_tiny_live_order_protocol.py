from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.one_tiny_live_order_protocol import (
    CONFIRMATION_PHRASE_TEMPLATE,
    EVENT_TYPE,
    PROTOCOL_BLOCKED,
    build_one_tiny_live_order_protocol_check,
    format_one_tiny_live_order_protocol_check_text,
    load_one_tiny_live_order_protocol_checks,
    one_tiny_live_order_protocol_checks_path,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class OneTinyLiveOrderProtocolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_protocol_blocks_when_final_preflight_is_blocked(self) -> None:
        payload = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env={})

        self.assertEqual(PROTOCOL_BLOCKED, payload["status"])
        self.assertEqual("BLOCKED", payload["final_preflight_status"])
        self.assertIn("final preflight is not READY", payload["blockers"])

    def test_protocol_blocks_when_tiny_live_dry_run_is_blocked(self) -> None:
        payload = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env={})

        self.assertEqual(PROTOCOL_BLOCKED, payload["status"])
        self.assertEqual("BLOCKED_FOR_DRY_RUN", payload["tiny_live_armed_dry_run_status"])
        self.assertIn("tiny-live armed dry run is not READY_FOR_DRY_RUN", payload["blockers"])

    def test_protocol_never_returns_live_ready_or_enables_execution(self) -> None:
        payload = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env={})

        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_protocol"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_protocol_never_calls_order_placement(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env={})

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_protocol_includes_inactive_confirmation_phrase_template(self) -> None:
        payload = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env={})

        self.assertEqual(CONFIRMATION_PHRASE_TEMPLATE, payload["confirmation_phrase_template"])
        self.assertIn("<candidate_id>", payload["confirmation_phrase_template"])
        self.assertIn("I UNDERSTAND THIS CAN LOSE REAL MONEY", payload["confirmation_phrase_template"])

    def test_protocol_reports_missing_approval_intent_and_stale_candidate(self) -> None:
        payload = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env={})

        self.assertFalse(payload["approval_intent_present"])
        self.assertIn("missing final approval intent", payload["blockers"])
        self.assertIn("stale candidate risk", payload["blockers"])

    def test_protocol_does_not_expose_secrets(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "TELEGRAM_CHAT_ID": "secret-chat-id",
        }

        payload = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env=env)
        rendered = json.dumps(payload, sort_keys=True)

        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-chat-id", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_protocol_ledger_contains_safety_fields(self) -> None:
        first = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env={})
        second = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env={})
        records = load_one_tiny_live_order_protocol_checks(limit=0, log_dir=self.log_dir)

        self.assertTrue(one_tiny_live_order_protocol_checks_path(self.log_dir).exists())
        self.assertEqual(2, len(records))
        self.assertEqual({first["protocol_check_id"], second["protocol_check_id"]}, {record["protocol_check_id"] for record in records})
        for record in records:
            self.assertEqual(EVENT_TYPE, record["event_type"])
            self.assertFalse(record["live_ready"])
            self.assertFalse(record["execution_enabled_by_protocol"])
            self.assertFalse(record["order_placed"])
            self.assertFalse(record["execution_attempted"])
            self.assertFalse(record["secrets_shown"])

    def test_source_surfaces_include_r102_and_r104(self) -> None:
        payload = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env={})

        self.assertIn("operator.final_live_preflight.build_final_live_preflight", payload["source_surfaces_used"])
        self.assertIn("operator.tiny_live_armed_dry_run.build_tiny_live_armed_dry_run", payload["source_surfaces_used"])
        self.assertIn("operator.one_tiny_live_order_protocol.build_one_tiny_live_order_protocol_check", payload["source_surfaces_used"])

    def test_paper_live_separation_remains_intact(self) -> None:
        payload = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env={})

        self.assertTrue(payload["paper_live_separation_intact"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_protocol"])

    def test_formatter_returns_json(self) -> None:
        payload = build_one_tiny_live_order_protocol_check(log_dir=self.log_dir, env={})
        rendered = format_one_tiny_live_order_protocol_check_text(payload)

        parsed = json.loads(rendered)
        self.assertEqual(PROTOCOL_BLOCKED, parsed["status"])
        self.assertFalse(parsed["live_ready"])


if __name__ == "__main__":
    unittest.main()
