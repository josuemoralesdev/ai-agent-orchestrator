from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.final_approval_intent import (
    FINAL_APPROVAL_EVENT_TYPE,
    final_approval_intents_path,
    load_final_approval_intents,
)
from src.app.hammer_radar.operator.final_live_preflight import build_final_live_preflight
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class TelegramFinalApprovalFlowTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_final_preflight_command_returns_blocked_safe_summary(self) -> None:
        payload = handle_telegram_operator_command(text="/final_preflight", log_dir=self.log_dir)
        preflight = payload["payload"]["final_live_preflight"]

        self.assertEqual("final_live_preflight", payload["normalized_action"])
        self.assertEqual("BLOCKED", payload["result_status"])
        self.assertIn("Final preflight: BLOCKED", payload["message"])
        self.assertIn("live_execution_enabled=false", payload["message"])
        self.assertIn("live_orders_allowed=false", payload["message"])
        self.assertIn("global_kill_switch=true", payload["message"])
        self.assertIn("No live order was placed", payload["message"])
        self.assertIn("operator.final_live_preflight.build_final_live_preflight", preflight["source_surfaces_used"])
        self.assertGreater(len(preflight["blockers"]), 0)
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["secrets_shown"])

    def test_approve_final_rejects_malformed_message_without_recording(self) -> None:
        payload = handle_telegram_operator_command(text="/approve_final only-one-arg", log_dir=self.log_dir)

        self.assertEqual("final_approval_intent", payload["normalized_action"])
        self.assertEqual("REJECTED", payload["result_status"])
        self.assertIn("requires candidate_id risk_contract_hash packet_hash", payload["message"])
        self.assertFalse(final_approval_intents_path(self.log_dir).exists())
        self.assertFalse(payload["order_placed"])

    def test_approve_final_rejects_hash_mismatch_and_records_rejected_intent(self) -> None:
        preflight = build_final_live_preflight(log_dir=self.log_dir, env={})
        candidate_id = str(preflight["candidate_id"])

        payload = handle_telegram_operator_command(
            text=f"/approve_final {candidate_id} bad-risk-hash bad-packet-hash",
            log_dir=self.log_dir,
        )
        records = load_final_approval_intents(limit=10, log_dir=self.log_dir)

        self.assertEqual("REJECTED", payload["result_status"])
        self.assertIn("REJECTED_HASH_MISMATCH", payload["message"])
        self.assertEqual(1, len(records))
        self.assertEqual(FINAL_APPROVAL_EVENT_TYPE, records[0]["event_type"])
        self.assertIsNot(records[0]["matched_risk_contract_hash"], True)
        self.assertIsNot(records[0]["matched_packet_hash"], True)
        self.assertFalse(records[0]["approval_intent_effective"])
        self.assertFalse(records[0]["order_placed"])
        self.assertFalse(records[0]["execution_attempted"])

    def test_approve_final_records_matching_intent_as_blocked_not_execution(self) -> None:
        preflight = build_final_live_preflight(log_dir=self.log_dir, env={})
        candidate_id = str(preflight["candidate_id"])
        risk_hash = str(preflight["risk_contract_hash"])
        packet_hash = str(preflight["final_review_packet_hash"])

        payload = handle_telegram_operator_command(
            text=f"/approve_final {candidate_id} {risk_hash} {packet_hash}",
            chat_id="123456",
            log_dir=self.log_dir,
        )
        records = load_final_approval_intents(limit=10, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["result_status"])
        self.assertIn("BLOCKED_BY_FINAL_PREFLIGHT", payload["message"])
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(FINAL_APPROVAL_EVENT_TYPE, record["event_type"])
        self.assertTrue(record["matched_risk_contract_hash"])
        self.assertTrue(record["matched_packet_hash"])
        self.assertEqual("BLOCKED", record["final_preflight_status"])
        self.assertEqual("BLOCKED_BY_FINAL_PREFLIGHT", record["result_status"])
        self.assertFalse(record["approval_intent_effective"])
        self.assertFalse(record["live_execution_enabled"])
        self.assertFalse(record["live_orders_allowed"])
        self.assertTrue(record["global_kill_switch"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["real_order_placed"])
        self.assertFalse(record["execution_attempted"])
        self.assertFalse(record["secrets_shown"])
        self.assertEqual("123456", record["telegram_user_id"])

    def test_approval_intent_does_not_call_order_path_or_enable_live_flags(self) -> None:
        preflight = build_final_live_preflight(log_dir=self.log_dir, env={})
        candidate_id = str(preflight["candidate_id"])
        risk_hash = str(preflight["risk_contract_hash"])
        packet_hash = str(preflight["final_review_packet_hash"])

        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = handle_telegram_operator_command(
                text=f"/approve_final {candidate_id} {risk_hash} {packet_hash}",
                log_dir=self.log_dir,
            )

        execute_live_order.assert_not_called()
        self.assertFalse(payload["live_execution_enabled"])
        self.assertFalse(payload["allow_live_orders"])
        self.assertTrue(payload["global_kill_switch"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_secrets_are_not_exposed_in_telegram_responses_or_records(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "TELEGRAM_CHAT_ID": "secret-chat-id",
        }
        with patch.dict(os.environ, env, clear=False):
            payload = handle_telegram_operator_command(text="/final_preflight", log_dir=self.log_dir)

        rendered = json.dumps(payload, sort_keys=True)
        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-chat-id", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_paper_live_separation_remains_intact(self) -> None:
        payload = handle_telegram_operator_command(text="/final_preflight", log_dir=self.log_dir)
        preflight = payload["payload"]["final_live_preflight"]

        self.assertTrue(preflight["paper_live_separation_intact"])
        self.assertFalse(preflight["safety"]["order_placed"])
        self.assertFalse(preflight["safety"]["real_order_placed"])
        self.assertFalse(preflight["safety"]["execution_attempted"])


if __name__ == "__main__":
    unittest.main()
