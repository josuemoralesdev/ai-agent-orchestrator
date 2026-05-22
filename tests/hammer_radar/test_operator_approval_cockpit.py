from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.execution import binance_futures_connector
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_live_activation_gate import FIRST_LIVE_ACTIVATION_READY
from src.app.hammer_radar.operator.first_live_operator_approval_cockpit import (
    EVENT_TYPE,
    build_operator_approval_cockpit_state,
    load_operator_approval_cockpit_intents,
    operator_approval_cockpit_intents_path,
    record_operator_approval_cockpit_intent,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR


class OperatorApprovalCockpitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_state_endpoint_is_non_executing_and_has_required_sections(self) -> None:
        response = self.client.get("/operator/approval-cockpit/state")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_ui"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["real_order_possible"])
        self.assertFalse(payload["secrets_shown"])
        self.assertIn("sequence_steps", payload)
        self.assertIn("simultaneous_signals", payload)
        self.assertIn("sacred_button_state", payload)
        self.assertIn("blocker_summary", payload)
        self.assertIn("operator_path_to_press", payload)
        self.assertFalse(payload["sacred_button_state"]["can_place_order"])
        self.assertTrue(payload["sacred_button_state"]["records_intent_only"])
        self.assertIn(payload["approval_window_status"], {"OPEN", "EXPIRED", "MISSING"})
        self.assertIn("approval_window_seconds_remaining", payload)
        self.assertIsInstance(payload["blockers"], list)
        self.assertIsInstance(payload["warnings"], list)
        self.assertIn("R106 first-live activation gate", payload["source_surfaces_used"])
        self.assertTrue(payload["backend_authority"]["confirmation_phrase_required"])

    def test_state_endpoint_includes_sequence_and_signal_shapes(self) -> None:
        payload = self.client.get("/operator/approval-cockpit/state").json()

        labels = [step["label"] for step in payload["sequence_steps"]]
        self.assertEqual(
            [
                "final preflight",
                "armed dry run",
                "one tiny live order protocol",
                "first live activation gate",
                "operator approval intent",
                "confirmation phrase requirement",
            ],
            labels,
        )
        for step in payload["sequence_steps"]:
            self.assertIn("status", step)
            self.assertIn("required", step)
            self.assertIn("blocker_count", step)
            self.assertIn("can_approve", step)
            self.assertIn("blocks_sacred_button", step)
            self.assertIn("expires_at_utc", step)
        signal = payload["simultaneous_signals"][0]
        self.assertIn("candidate_id", signal)
        self.assertIn("counsel_decision", signal)
        self.assertIn("tags", signal)
        self.assertIn("approval_window_status", signal)
        self.assertIn("seconds_remaining", signal)
        self.assertIn("can_record_intent", signal)
        self.assertIn("R106_GATE_AUTHORITY", signal["tags"])
        self.assertIn("INTENT_ONLY", signal["tags"])

    def test_state_includes_sacred_button_and_blocker_summary(self) -> None:
        payload = self.client.get("/operator/approval-cockpit/state").json()

        sacred = payload["sacred_button_state"]
        self.assertIn(sacred["label"], {"SACRED BUTTON LOCKED", "RECORD INTENT ONLY", "EXPIRED", "BLOCKED BY R106"})
        self.assertFalse(sacred["can_place_order"])
        self.assertTrue(sacred["records_intent_only"])
        self.assertIn(sacred["visual_state"], {"LOCKED", "REVIEWABLE", "EXPIRED", "INTENT_RECORDED"})
        if payload["first_live_activation_gate_status"] != FIRST_LIVE_ACTIVATION_READY:
            self.assertFalse(sacred["enabled"])

        summary = payload["blocker_summary"]
        self.assertIn("primary_blockers", summary)
        self.assertLessEqual(len(summary["primary_blockers"]), 5)
        self.assertIn("detailed_blocker_count", summary)
        self.assertIn("final_preflight_blocker_count", summary)
        self.assertIn("dry_run_blocker_count", summary)
        self.assertIn("protocol_blocker_count", summary)
        self.assertIn("activation_gate_blocker_count", summary)

    def test_operator_path_to_press_includes_required_r102_r106_steps(self) -> None:
        payload = self.client.get("/operator/approval-cockpit/state").json()

        labels = [step["label"] for step in payload["operator_path_to_press"]]
        self.assertIn("R102 final preflight", labels)
        self.assertIn("R104 tiny-live armed dry run", labels)
        self.assertIn("R105 one tiny live order protocol", labels)
        self.assertIn("R106 first-live activation gate", labels)
        self.assertIn("Confirmation phrase", labels)
        for step in payload["operator_path_to_press"]:
            self.assertIn("current_status", step)
            self.assertIn("required_status", step)
            self.assertIn("satisfied", step)
            self.assertIn("next_action_hint", step)

    def test_state_does_not_expose_secret_values(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
        }

        payload = build_operator_approval_cockpit_state(log_dir=self.log_dir, env=env)
        rendered = json.dumps(payload, sort_keys=True)

        self.assertNotIn("secret-api-key-value", rendered)
        self.assertNotIn("secret-api-secret-value", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertFalse(payload["secrets_shown"])

    def test_html_cockpit_has_intent_only_safety_copy_and_buttons(self) -> None:
        response = self.client.get("/operator/approval-cockpit")

        self.assertEqual(200, response.status_code)
        self.assertIn("text/html", response.headers["content-type"])
        html = response.text
        self.assertIn("INTENT ONLY", html)
        self.assertIn("NO ORDER CAN BE PLACED", html)
        self.assertIn("R106 GATE AUTHORITY", html)
        self.assertIn("FIRST LIVE COCKPIT", html)
        self.assertIn("SACRED BUTTON LOCKED", html)
        self.assertIn("This does not place an order.", html)
        self.assertIn("hourglass", html)
        self.assertIn("APPROVE INTENT ONLY", html)
        self.assertIn("REJECT INTENT ONLY", html)
        self.assertIn("WAIT INTENT ONLY", html)
        self.assertNotIn("execute_live_order", html)

    def test_intent_rejects_expired_window_and_records_rejection(self) -> None:
        expired_state = self._ready_state("EXPIRED", seconds=0)

        with patch(
            "src.app.hammer_radar.operator.first_live_operator_approval_cockpit.build_operator_approval_cockpit_state",
            return_value=expired_state,
        ):
            result = record_operator_approval_cockpit_intent(
                candidate_id="normal|BTCUSDT|13m|long|ladder_close_50_618",
                intent="APPROVE",
                counsel_decision="APPROVE",
                counsel_tags=["R108", "INTENT_ONLY"],
                risk_contract_hash="risk-hash",
                packet_hash="packet-hash",
                log_dir=self.log_dir,
            )

        self.assertFalse(result["accepted_as_intent"])
        self.assertEqual("approval window is EXPIRED", result["rejection_reason"])
        self.assertIn("sacred_button_state", result)
        self.assertFalse(result["sacred_button_state"]["enabled"])
        self.assertFalse(result["sacred_button_state"]["can_place_order"])
        records = load_operator_approval_cockpit_intents(limit=0, log_dir=self.log_dir)
        self.assertEqual(1, len(records))
        self.assertFalse(records[0]["accepted_as_intent"])

    def test_intent_records_intent_only_with_counsel_metadata(self) -> None:
        ready_state = self._ready_state("OPEN", seconds=300)

        with patch(
            "src.app.hammer_radar.operator.first_live_operator_approval_cockpit.build_operator_approval_cockpit_state",
            return_value=ready_state,
        ):
            result = record_operator_approval_cockpit_intent(
                candidate_id="normal|BTCUSDT|13m|long|ladder_close_50_618",
                intent="WAIT",
                counsel_decision="ESCALATE",
                counsel_tags=["R108", "counsel_review"],
                risk_contract_hash="risk-hash",
                packet_hash="packet-hash",
                operator_note="review only",
                log_dir=self.log_dir,
            )

        self.assertEqual("INTENT_RECORDED", result["status"])
        self.assertTrue(result["accepted_as_intent"])
        self.assertEqual("Intent recorded only. No order was placed.", result["message"])
        self.assertIn("sacred_button_state", result)
        self.assertFalse(result["sacred_button_state"]["can_place_order"])
        self.assertTrue(result["sacred_button_state"]["records_intent_only"])
        self.assertEqual(FIRST_LIVE_ACTIVATION_READY, result["current_r106_gate_status"])
        record = result["record"]
        self.assertEqual(EVENT_TYPE, record["event_type"])
        self.assertEqual("ESCALATE", record["counsel_decision"])
        self.assertEqual(["R108", "COUNSEL_REVIEW"], record["counsel_tags"])
        self.assertFalse(record["live_ready"])
        self.assertFalse(record["execution_enabled_by_ui"])
        self.assertFalse(record["order_placed"])
        self.assertFalse(record["real_order_placed"])
        self.assertFalse(record["execution_attempted"])
        self.assertFalse(record["real_order_possible"])
        self.assertFalse(record["secrets_shown"])
        self.assertEqual("Intent recorded only. No order was placed.", record["message"])
        self.assertTrue(operator_approval_cockpit_intents_path(self.log_dir).exists())

    def test_api_intent_response_includes_sacred_button_state_and_no_order_message(self) -> None:
        ready_state = self._ready_state("OPEN", seconds=300)

        with patch(
            "src.app.hammer_radar.operator.first_live_operator_approval_cockpit.build_operator_approval_cockpit_state",
            return_value=ready_state,
        ):
            response = self.client.post(
                "/operator/approval-cockpit/intent",
                json={
                    "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                    "intent": "WAIT",
                    "counsel_decision": "WAIT",
                    "counsel_tags": ["R109", "INTENT_ONLY"],
                    "risk_contract_hash": "risk-hash",
                    "packet_hash": "packet-hash",
                },
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["accepted_as_intent"])
        self.assertEqual("Intent recorded only. No order was placed.", payload["message"])
        self.assertEqual(FIRST_LIVE_ACTIVATION_READY, payload["current_r106_gate_status"])
        self.assertIn("sacred_button_state", payload)
        self.assertFalse(payload["sacred_button_state"]["can_place_order"])
        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_intent_rejects_missing_candidate_or_hash_data(self) -> None:
        missing_hash_state = self._ready_state("MISSING", seconds=0)
        missing_hash_state["risk_contract_hash"] = None

        with patch(
            "src.app.hammer_radar.operator.first_live_operator_approval_cockpit.build_operator_approval_cockpit_state",
            return_value=missing_hash_state,
        ):
            result = record_operator_approval_cockpit_intent(
                candidate_id="normal|BTCUSDT|13m|long|ladder_close_50_618",
                intent="APPROVE",
                counsel_decision="APPROVE",
                counsel_tags=["R108"],
                risk_contract_hash="risk-hash",
                packet_hash="packet-hash",
                log_dir=self.log_dir,
            )

        self.assertFalse(result["accepted_as_intent"])
        self.assertEqual("missing candidate or hash data", result["rejection_reason"])

    def test_api_malformed_intent_is_rejected(self) -> None:
        response = self.client.post(
            "/operator/approval-cockpit/intent",
            json={
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "intent": "EXECUTE",
                "counsel_decision": "APPROVE",
                "counsel_tags": ["R108"],
                "risk_contract_hash": "risk-hash",
                "packet_hash": "packet-hash",
            },
        )

        self.assertEqual(422, response.status_code)

    def test_cockpit_never_calls_binance_order_endpoint(self) -> None:
        with patch.object(binance_futures_connector, "execute_live_order") as execute_live_order:
            payload = build_operator_approval_cockpit_state(log_dir=self.log_dir, env={})

        execute_live_order.assert_not_called()
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_paper_live_separation_remains_intact(self) -> None:
        payload = build_operator_approval_cockpit_state(log_dir=self.log_dir, env={})

        self.assertFalse(payload["live_ready"])
        self.assertFalse(payload["execution_enabled_by_ui"])
        self.assertFalse(payload["real_order_possible"])
        self.assertEqual(False, payload["backend_authority"]["ui_approval_is_execution_authority"])

    def _ready_state(self, window_status: str, *, seconds: int) -> dict:
        now = datetime.now(UTC)
        return {
            "status": "READY_FOR_REVIEW" if window_status == "OPEN" else window_status,
            "checked_at_utc": now.isoformat(),
            "first_live_activation_gate_status": FIRST_LIVE_ACTIVATION_READY,
            "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
            "risk_contract_hash": "risk-hash",
            "packet_hash": "packet-hash",
            "approval_window_status": window_status,
            "approval_window_opened_at_utc": (now - timedelta(minutes=1)).isoformat(),
            "approval_window_expires_at_utc": (now + timedelta(seconds=seconds)).isoformat(),
            "approval_window_seconds_remaining": seconds,
            "blockers": [],
            "warnings": [],
            "source_surfaces_used": ["R106 first-live activation gate"],
            "sequence_steps": [],
            "simultaneous_signals": [],
            "live_ready": False,
            "execution_enabled_by_ui": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "real_order_possible": False,
            "secrets_shown": False,
        }


if __name__ == "__main__":
    unittest.main()
