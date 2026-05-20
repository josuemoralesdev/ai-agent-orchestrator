from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.final_approval_intent import evaluate_final_approval_intent
from src.app.hammer_radar.operator.final_live_preflight import build_final_live_preflight
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.tiny_live_armed_dry_run import (
    BLOCKED_FOR_DRY_RUN,
    EVENT_TYPE,
    build_tiny_live_armed_dry_run,
    format_tiny_live_armed_dry_run_text,
    load_tiny_live_armed_dry_runs,
    tiny_live_armed_dry_runs_path,
)


class TinyLiveArmedDryRunTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_dry_run_blocks_when_final_preflight_is_blocked(self) -> None:
        payload = build_tiny_live_armed_dry_run(log_dir=self.log_dir, env={})

        self.assertEqual(BLOCKED_FOR_DRY_RUN, payload["status"])
        self.assertEqual("BLOCKED", payload["final_preflight_status"])
        self.assertIn("final preflight is BLOCKED", payload["blockers"])
        self.assertFalse(payload["live_ready"])
        self.assertTrue(payload["dry_run_only"])
        self.assertFalse(payload["real_order_possible"])

    def test_missing_approval_intent_blocks_dry_run(self) -> None:
        payload = build_tiny_live_armed_dry_run(log_dir=self.log_dir, env={})

        self.assertFalse(payload["approval_intent_present"])
        self.assertEqual("MISSING", payload["approval_intent_status"])
        self.assertIn("missing final approval intent", payload["blockers"])

    def test_matching_but_blocked_approval_intent_is_considered_not_execution(self) -> None:
        preflight = build_final_live_preflight(log_dir=self.log_dir, env={})
        evaluate_final_approval_intent(
            candidate_id=str(preflight["candidate_id"]),
            supplied_risk_contract_hash=str(preflight["risk_contract_hash"]),
            supplied_packet_hash=str(preflight["final_review_packet_hash"]),
            log_dir=self.log_dir,
            env={},
        )

        payload = build_tiny_live_armed_dry_run(log_dir=self.log_dir, env={})

        self.assertTrue(payload["approval_intent_present"])
        self.assertEqual("BLOCKED_BY_FINAL_PREFLIGHT", payload["approval_intent_status"])
        self.assertIn("final approval intent is not accepted for dry-run: BLOCKED_BY_FINAL_PREFLIGHT", payload["blockers"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_stale_candidate_risk_blocks_dry_run(self) -> None:
        payload = build_tiny_live_armed_dry_run(log_dir=self.log_dir, env={})

        self.assertIn("stale candidate risk", payload["blockers"])

    def test_dry_run_never_calls_order_adapter(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = build_tiny_live_armed_dry_run(log_dir=self.log_dir, env={})

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])

    def test_secrets_are_not_exposed(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "TELEGRAM_CHAT_ID": "secret-chat-id",
        }

        payload = build_tiny_live_armed_dry_run(log_dir=self.log_dir, env=env)
        rendered = json.dumps(payload, sort_keys=True)

        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-chat-id", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_ledger_record_is_append_only_and_contains_safety_fields(self) -> None:
        first = build_tiny_live_armed_dry_run(log_dir=self.log_dir, env={})
        second = build_tiny_live_armed_dry_run(log_dir=self.log_dir, env={})
        records = load_tiny_live_armed_dry_runs(limit=0, log_dir=self.log_dir)

        self.assertTrue(tiny_live_armed_dry_runs_path(self.log_dir).exists())
        self.assertEqual(2, len(records))
        self.assertEqual({second["dry_run_id"], first["dry_run_id"]}, {record["dry_run_id"] for record in records})
        for record in records:
            self.assertEqual(EVENT_TYPE, record["event_type"])
            self.assertFalse(record["live_ready"])
            self.assertTrue(record["dry_run_only"])
            self.assertFalse(record["order_placed"])
            self.assertFalse(record["execution_attempted"])
            self.assertFalse(record["real_order_possible"])
            self.assertFalse(record["secrets_shown"])

    def test_source_surfaces_include_final_preflight_and_approval_intent(self) -> None:
        payload = build_tiny_live_armed_dry_run(log_dir=self.log_dir, env={})

        self.assertIn("operator.tiny_live_armed_dry_run.build_tiny_live_armed_dry_run", payload["source_surfaces_used"])
        self.assertIn("operator.final_live_preflight.build_final_live_preflight", payload["source_surfaces_used"])
        self.assertIn("operator.final_approval_intent.load_final_approval_intents", payload["source_surfaces_used"])

    def test_paper_live_separation_remains_intact(self) -> None:
        payload = build_tiny_live_armed_dry_run(log_dir=self.log_dir, env={})

        self.assertTrue(payload["paper_live_separation_intact"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["real_order_possible"])

    def test_formatter_returns_json(self) -> None:
        payload = build_tiny_live_armed_dry_run(log_dir=self.log_dir, env={})
        rendered = format_tiny_live_armed_dry_run_text(payload)

        parsed = json.loads(rendered)
        self.assertEqual(BLOCKED_FOR_DRY_RUN, parsed["status"])
        self.assertFalse(parsed["live_ready"])


if __name__ == "__main__":
    unittest.main()
