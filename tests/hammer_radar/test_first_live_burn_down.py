from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.first_live_burn_down import (
    EVENT_TYPE,
    STATUS,
    build_first_live_burn_down,
    first_live_burn_down_reports_path,
    format_first_live_burn_down_text,
    load_first_live_burn_down_reports,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class FirstLiveBurnDownTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_burn_down_returns_required_safety_state(self) -> None:
        payload = build_first_live_burn_down(log_dir=self.log_dir, env={})

        self.assertEqual(STATUS, payload["status"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_burn_down"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["secrets_shown"])

    def test_burn_down_never_places_order(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = build_first_live_burn_down(log_dir=self.log_dir, env={})

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_burn_down_does_not_expose_secret_values(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "TELEGRAM_CHAT_ID": "secret-chat-id",
        }

        payload = build_first_live_burn_down(log_dir=self.log_dir, env=env)
        rendered = json.dumps(payload, sort_keys=True)

        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-chat-id", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_burn_down_includes_gate_chain_and_operator_pack_sections(self) -> None:
        payload = build_first_live_burn_down(log_dir=self.log_dir, env={})

        chain = payload["current_gate_chain"]
        self.assertEqual("BLOCKED", chain["final_preflight_status"])
        self.assertEqual("BLOCKED_FOR_DRY_RUN", chain["tiny_live_armed_dry_run_status"])
        self.assertEqual("PROTOCOL_BLOCKED", chain["protocol_status"])
        self.assertEqual("FIRST_LIVE_BLOCKED", chain["first_live_activation_gate_status"])
        self.assertIn("cockpit_status", chain)
        self.assertIn("sacred_button_state", chain)
        self.assertIn("blocker_groups", payload)
        self.assertIn("priority_burn_down", payload)
        self.assertIn("morning_command_pack", payload)
        self.assertIn("human_checklist", payload)

    def test_burn_down_groups_known_blockers_correctly(self) -> None:
        payload = build_first_live_burn_down(log_dir=self.log_dir, env={})
        groups = payload["blocker_groups"]

        self.assertIn("candidate stale", groups["candidate_blockers"]["blockers"])
        self.assertIn("approval intent missing", groups["approval_record_blockers"]["blockers"])
        self.assertIn("Binance credentials missing", groups["binance_credential_blockers"]["blockers"])
        self.assertIn("account balance/funding unknown", groups["account_funding_blockers"]["blockers"])
        self.assertIn("protective orders not ready", groups["protective_order_blockers"]["blockers"])
        self.assertIn("live order adapter not configured", groups["adapter_blockers"]["blockers"])
        self.assertIn("operator confirmation phrase missing", groups["confirmation_phrase_blockers"]["blockers"])
        for group in groups.values():
            self.assertIn(group["owner"], {"OPERATOR", "CODE", "CONFIG", "MARKET", "EXCHANGE", "UNKNOWN"})
            self.assertIsInstance(group["can_clear_tomorrow"], bool)
            self.assertIsInstance(group["next_action"], str)
            self.assertIsInstance(group["related_phase"], str)

    def test_burn_down_priority_and_morning_commands_include_required_actions(self) -> None:
        payload = build_first_live_burn_down(log_dir=self.log_dir, env={})

        actions = [item["action"] for item in payload["priority_burn_down"]]
        self.assertEqual("Wait for or identify fresh promoted candidate.", actions[0])
        self.assertIn("Verify R102 final-live-preflight status.", actions)
        self.assertIn("Record/verify final approval intent.", actions)
        self.assertIn("Complete human approval/review records.", actions)
        self.assertIn("Configure Binance credentials safely, without exposing values.", actions)
        self.assertIn("Verify account/funding without placing orders.", actions)
        self.assertIn("Configure protective order readiness.", actions)
        self.assertIn("Verify live adapter boundary.", actions)
        self.assertIn("Define tiny position size and max loss cap.", actions)
        self.assertIn("Re-run R102/R104/R105/R106/R109 state.", actions)
        self.assertIn("Confirm sacred button remains intent-only.", actions)
        self.assertIn("Only then prepare future explicit authorization phase.", actions)

        commands = payload["morning_command_pack"]
        self.assertIn("final-live-preflight", commands["final_live_preflight"])
        self.assertIn("tiny-live-armed-dry-run", commands["tiny_live_armed_dry_run"])
        self.assertIn("one-tiny-live-order-protocol", commands["one_tiny_live_order_protocol"])
        self.assertIn("first-live-activation-gate", commands["first_live_activation_gate"])
        self.assertIn("/operator/approval-cockpit/state", commands["approval_cockpit_state_curl"])
        self.assertIn("first-live-burn-down", commands["first_live_burn_down"])

    def test_burn_down_human_checklist_and_readiness_path(self) -> None:
        payload = build_first_live_burn_down(log_dir=self.log_dir, env={})

        checklist_items = [item["item"] for item in payload["human_checklist"]]
        self.assertEqual(
            [
                "candidate fresh?",
                "hashes match?",
                "R106 ready?",
                "protective orders ready?",
                "max loss known?",
                "exchange funding checked?",
                "kill switch understood?",
                "emergency cancel path known?",
                "no conflicting position?",
                "no second order before postmortem?",
            ],
            checklist_items,
        )
        self.assertEqual(
            [
                "BLOCKED",
                "READY",
                "READY_FOR_DRY_RUN",
                "PROTOCOL_PREREQS_READY",
                "FIRST_LIVE_ACTIVATION_READY",
                "future explicit execution authorization",
            ],
            payload["readiness_path"],
        )

    def test_burn_down_writes_append_only_ledger(self) -> None:
        first = build_first_live_burn_down(log_dir=self.log_dir, env={})
        second = build_first_live_burn_down(log_dir=self.log_dir, env={})
        records = load_first_live_burn_down_reports(limit=0, log_dir=self.log_dir)

        self.assertTrue(first_live_burn_down_reports_path(self.log_dir).exists())
        self.assertEqual(2, len(records))
        self.assertEqual({first["report_id"], second["report_id"]}, {record["report_id"] for record in records})
        for record in records:
            self.assertEqual(EVENT_TYPE, record["event_type"])
            self.assertEqual(STATUS, record["status"])
            self.assertFalse(record["live_ready"])
            self.assertFalse(record["execution_enabled_by_burn_down"])
            self.assertFalse(record["order_placed"])
            self.assertFalse(record["execution_attempted"])
            self.assertFalse(record["real_order_possible"])
            self.assertFalse(record["secrets_shown"])
            self.assertIn("current_gate_chain", record)
            self.assertIn("blocker_groups", record)
            self.assertIn("priority_burn_down", record)
            self.assertIn("source_surfaces_used", record)

    def test_source_surfaces_include_r102_r104_r105_r106_and_r109(self) -> None:
        payload = build_first_live_burn_down(log_dir=self.log_dir, env={})

        self.assertIn("R102 final-live-preflight", payload["source_surfaces_used"])
        self.assertIn("R104 tiny-live-armed-dry-run", payload["source_surfaces_used"])
        self.assertIn("R105 one-tiny-live-order-protocol", payload["source_surfaces_used"])
        self.assertIn("R106 first-live-activation-gate", payload["source_surfaces_used"])
        self.assertIn("R109 first-live cockpit sacred button state", payload["source_surfaces_used"])

    def test_paper_live_separation_remains_intact_and_formatter_returns_json(self) -> None:
        payload = build_first_live_burn_down(log_dir=self.log_dir, env={})
        rendered = format_first_live_burn_down_text(payload)
        parsed = json.loads(rendered)

        self.assertTrue(parsed["paper_live_separation_intact"])
        self.assertFalse(parsed["live_ready"])
        self.assertFalse(parsed["execution_enabled_by_burn_down"])


if __name__ == "__main__":
    unittest.main()
