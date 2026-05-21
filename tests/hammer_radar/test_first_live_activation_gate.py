from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.first_live_activation_gate import (
    EVENT_TYPE,
    FIRST_LIVE_BLOCKED,
    build_first_live_activation_gate,
    first_live_activation_gate_checks_path,
    format_first_live_activation_gate_text,
    load_first_live_activation_gate_checks,
)
from src.app.hammer_radar.operator.one_tiny_live_order_protocol import CONFIRMATION_PHRASE_TEMPLATE
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLiveActivationGateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_activation_gate_blocks_when_final_preflight_is_blocked(self) -> None:
        payload = build_first_live_activation_gate(log_dir=self.log_dir, env={})

        self.assertEqual(FIRST_LIVE_BLOCKED, payload["status"])
        self.assertEqual("BLOCKED", payload["final_preflight_status"])
        self.assertIn("final preflight is not READY", payload["blockers"])

    def test_activation_gate_blocks_when_r104_dry_run_is_blocked(self) -> None:
        payload = build_first_live_activation_gate(log_dir=self.log_dir, env={})

        self.assertEqual("BLOCKED_FOR_DRY_RUN", payload["tiny_live_armed_dry_run_status"])
        self.assertIn("tiny-live armed dry run is not READY_FOR_DRY_RUN", payload["blockers"])

    def test_activation_gate_blocks_when_r105_protocol_is_blocked(self) -> None:
        payload = build_first_live_activation_gate(log_dir=self.log_dir, env={})

        self.assertEqual("PROTOCOL_BLOCKED", payload["one_tiny_live_order_protocol_status"])
        self.assertIn("one tiny live order protocol is not PROTOCOL_PREREQS_READY", payload["blockers"])

    def test_activation_gate_blocks_missing_approval_intent_and_confirmation(self) -> None:
        payload = build_first_live_activation_gate(log_dir=self.log_dir, env={})

        self.assertFalse(payload["approval_intent_present"])
        self.assertEqual("MISSING", payload["approval_intent_status"])
        self.assertIn("approval intent missing", payload["blockers"])
        self.assertFalse(payload["operator_confirmation_present"])
        self.assertIn("operator confirmation phrase missing", payload["blockers"])

    def test_activation_gate_never_returns_live_ready_or_enables_execution(self) -> None:
        payload = build_first_live_activation_gate(log_dir=self.log_dir, env={})

        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_gate"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])

    def test_activation_gate_never_calls_binance_order_endpoint(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = build_first_live_activation_gate(log_dir=self.log_dir, env={})

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_activation_gate_includes_confirmation_phrase_template(self) -> None:
        payload = build_first_live_activation_gate(log_dir=self.log_dir, env={})

        self.assertTrue(payload["confirmation_phrase_required"])
        self.assertEqual(CONFIRMATION_PHRASE_TEMPLATE, payload["confirmation_phrase_template"])

    def test_activation_gate_reports_candidate_stale_protective_and_funding_blockers(self) -> None:
        payload = build_first_live_activation_gate(log_dir=self.log_dir, env={})

        self.assertIn("candidate stale", payload["blockers"])
        self.assertIn("protective orders not ready", payload["blockers"])
        self.assertIn("account balance/funding unknown", payload["blockers"])
        self.assertIn("position size cap unknown", payload["blockers"])
        self.assertIn("max loss cap unknown", payload["blockers"])

    def test_activation_gate_does_not_expose_secrets(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "TELEGRAM_CHAT_ID": "secret-chat-id",
        }

        payload = build_first_live_activation_gate(log_dir=self.log_dir, env=env)
        rendered = json.dumps(payload, sort_keys=True)

        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-chat-id", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_activation_ledger_contains_safety_fields(self) -> None:
        first = build_first_live_activation_gate(log_dir=self.log_dir, env={})
        second = build_first_live_activation_gate(log_dir=self.log_dir, env={})
        records = load_first_live_activation_gate_checks(limit=0, log_dir=self.log_dir)

        self.assertTrue(first_live_activation_gate_checks_path(self.log_dir).exists())
        self.assertEqual(2, len(records))
        self.assertEqual({first["activation_gate_check_id"], second["activation_gate_check_id"]}, {record["activation_gate_check_id"] for record in records})
        for record in records:
            self.assertEqual(EVENT_TYPE, record["event_type"])
            self.assertFalse(record["live_ready"])
            self.assertFalse(record["execution_enabled_by_gate"])
            self.assertFalse(record["order_placed"])
            self.assertFalse(record["execution_attempted"])
            self.assertFalse(record["real_order_possible"])
            self.assertFalse(record["secrets_shown"])

    def test_source_surfaces_include_r102_r103_r104_and_r105(self) -> None:
        payload = build_first_live_activation_gate(log_dir=self.log_dir, env={})

        self.assertIn("operator.final_live_preflight.build_final_live_preflight", payload["source_surfaces_used"])
        self.assertIn("operator.final_approval_intent.load_final_approval_intents", payload["source_surfaces_used"])
        self.assertIn("operator.tiny_live_armed_dry_run.build_tiny_live_armed_dry_run", payload["source_surfaces_used"])
        self.assertIn("operator.one_tiny_live_order_protocol.build_one_tiny_live_order_protocol_check", payload["source_surfaces_used"])
        self.assertIn("operator.first_live_activation_gate.build_first_live_activation_gate", payload["source_surfaces_used"])

    def test_paper_live_separation_remains_intact(self) -> None:
        payload = build_first_live_activation_gate(log_dir=self.log_dir, env={})

        self.assertTrue(payload["paper_live_separation_intact"])
        self.assertFalse(payload["live_ready"])

    def test_formatter_returns_json(self) -> None:
        payload = build_first_live_activation_gate(log_dir=self.log_dir, env={})
        rendered = format_first_live_activation_gate_text(payload)

        parsed = json.loads(rendered)
        self.assertEqual(FIRST_LIVE_BLOCKED, parsed["status"])
        self.assertFalse(parsed["live_ready"])


if __name__ == "__main__":
    unittest.main()
