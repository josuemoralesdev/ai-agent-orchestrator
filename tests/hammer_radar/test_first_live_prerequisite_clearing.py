from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.first_live_prerequisite_clearing import (
    EVENT_TYPE,
    GROUP_ORDER,
    MORNING_LIVE_READINESS_SEQUENCE,
    PREREQS_BLOCKED,
    build_first_live_prerequisite_clearing,
    first_live_prerequisite_clearing_path,
    format_first_live_prerequisite_clearing_text,
    load_first_live_prerequisite_clearings,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLivePrerequisiteClearingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_prerequisite_clearing_returns_required_safety_state(self) -> None:
        payload = build_first_live_prerequisite_clearing(log_dir=self.log_dir, env={})

        self.assertEqual(PREREQS_BLOCKED, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_prereq_clearing"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["secrets_shown"])

    def test_prerequisite_clearing_never_places_order(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = build_first_live_prerequisite_clearing(log_dir=self.log_dir, env={})

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])

    def test_prerequisite_clearing_does_not_expose_secret_values(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "TELEGRAM_CHAT_ID": "secret-chat-id",
        }

        payload = build_first_live_prerequisite_clearing(log_dir=self.log_dir, env=env)
        rendered = json.dumps(payload, sort_keys=True)

        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-chat-id", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_prerequisite_groups_contains_all_required_groups(self) -> None:
        payload = build_first_live_prerequisite_clearing(log_dir=self.log_dir, env={})
        groups = payload["prerequisite_groups"]

        self.assertEqual(GROUP_ORDER, list(groups))
        for group in groups.values():
            self.assertIn(group["status"], {"CLEAR", "BLOCKED", "NEEDS_OPERATOR_EVIDENCE", "UNKNOWN"})
            self.assertIn("evidence_required", group)
            self.assertIn("evidence_present", group)
            self.assertIn("next_action", group)
            self.assertIn("verification_command", group)
            self.assertIn("owner", group)
            self.assertIn("related_phase", group)
            self.assertIn("safety_notes", group)

    def test_blocked_evidence_unknown_counters_are_correct(self) -> None:
        payload = build_first_live_prerequisite_clearing(log_dir=self.log_dir, env={})
        statuses = [group["status"] for group in payload["prerequisite_groups"].values()]

        self.assertEqual(statuses.count("CLEAR"), payload["cleared_count"])
        self.assertEqual(statuses.count("BLOCKED"), payload["blocked_count"])
        self.assertEqual(statuses.count("NEEDS_OPERATOR_EVIDENCE"), payload["operator_evidence_needed_count"])
        self.assertEqual(statuses.count("UNKNOWN"), payload["unknown_count"])
        self.assertEqual(len(GROUP_ORDER), payload["cleared_count"] + payload["blocked_count"] + payload["operator_evidence_needed_count"] + payload["unknown_count"])

    def test_sacred_button_safety_reports_cannot_place_order(self) -> None:
        payload = build_first_live_prerequisite_clearing(log_dir=self.log_dir, env={})
        sacred = payload["prerequisite_groups"]["sacred_button_safety"]

        self.assertEqual("CLEAR", sacred["status"])
        self.assertFalse(sacred["evidence_present"]["can_place_order"])
        self.assertTrue(sacred["evidence_present"]["records_intent_only"])

    def test_source_statuses_include_r102_r104_r105_r106_r109_and_r110(self) -> None:
        payload = build_first_live_prerequisite_clearing(log_dir=self.log_dir, env={})

        self.assertEqual("BLOCKED", payload["source_statuses"]["R102 final preflight"])
        self.assertEqual("BLOCKED_FOR_DRY_RUN", payload["source_statuses"]["R104 tiny-live armed dry run"])
        self.assertEqual("PROTOCOL_BLOCKED", payload["source_statuses"]["R105 protocol"])
        self.assertEqual("FIRST_LIVE_BLOCKED", payload["source_statuses"]["R106 activation gate"])
        self.assertIn("R109 cockpit", payload["source_statuses"])
        self.assertEqual("BURN_DOWN_READY", payload["source_statuses"]["R110 burn-down"])

    def test_morning_live_readiness_sequence_includes_all_required_steps(self) -> None:
        payload = build_first_live_prerequisite_clearing(log_dir=self.log_dir, env={})

        self.assertEqual(MORNING_LIVE_READINESS_SEQUENCE, payload["morning_live_readiness_sequence"])
        self.assertEqual("Run first-live-burn-down", payload["morning_live_readiness_sequence"][0])
        self.assertEqual("Stop if anything remains blocked", payload["morning_live_readiness_sequence"][-1])

    def test_ledger_write_contains_safety_fields(self) -> None:
        payload = build_first_live_prerequisite_clearing(log_dir=self.log_dir, env={})
        records = load_first_live_prerequisite_clearings(limit=0, log_dir=self.log_dir)

        self.assertTrue(first_live_prerequisite_clearing_path(self.log_dir).exists())
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(EVENT_TYPE, record["event_type"])
        self.assertEqual(payload["clearing_id"], record["clearing_id"])
        self.assertFalse(record["live_ready"])
        self.assertFalse(record["execution_enabled_by_prereq_clearing"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["real_order_placed"])
        self.assertFalse(record["execution_attempted"])
        self.assertFalse(record["real_order_possible"])
        self.assertFalse(record["secrets_shown"])
        self.assertIn("source_surfaces_used", record)
        self.assertIn("prerequisite_groups", record)

    def test_paper_live_separation_remains_intact_and_formatter_returns_json(self) -> None:
        payload = build_first_live_prerequisite_clearing(log_dir=self.log_dir, env={})
        rendered = format_first_live_prerequisite_clearing_text(payload)
        parsed = json.loads(rendered)

        self.assertTrue(parsed["paper_live_separation_intact"])
        self.assertFalse(parsed["live_ready"])
        self.assertFalse(parsed["execution_enabled_by_prereq_clearing"])
        self.assertTrue(parsed["safety_summary"]["R106 remains authority"])
        self.assertTrue(parsed["safety_summary"]["cockpit is intent-only"])


if __name__ == "__main__":
    unittest.main()
