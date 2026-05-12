from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.execution.binance_futures_connector import append_connector_attempt
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_live_protective_adapter import append_first_live_protective_check
from src.app.hammer_radar.operator.live_execution_intent import append_live_execution_intent
from src.app.hammer_radar.operator.live_executor_rehearsal import append_live_executor_rehearsal
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.rehearsal_test_order_protective_readiness import (
    build_rehearsal_test_order_protective_check,
    build_rehearsal_test_order_protective_status,
    load_rehearsal_test_order_protective_checks,
)
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class RehearsalTestOrderProtectiveReadinessTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)
        self.signal_id = "BTCUSDT|13m|long|2026-05-12T10:00:00+00:00"
        self.intent_id = "intent-r78"
        self.rehearsal_id = "rehearsal-r78"

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_status_awaiting_chain_safe(self) -> None:
        payload = build_rehearsal_test_order_protective_status(log_dir=self.log_dir, env={})

        self.assertEqual("AWAITING_CHAIN", payload["status"])
        self.assertEqual("R78", payload["phase"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])
        self.assertEqual("fast", payload["performance"]["mode"])

    def test_intent_exists_but_no_rehearsal_ready_for_rehearsal(self) -> None:
        self._append_intent()

        payload = build_rehearsal_test_order_protective_check(execution_intent_id=self.intent_id, log_dir=self.log_dir, env={})

        self.assertEqual("READY_FOR_REHEARSAL", payload["status"])
        self.assertTrue(payload["chain_state"]["execution_intent_found"])
        self.assertFalse(payload["chain_state"]["executor_rehearsal_found"])
        self.assertIn("LIVE REHEARSAL", " ".join(payload["required_next_steps"]))
        self.assertFalse(payload["order_placed"])

    def test_rehearsal_exists_but_no_test_order_ready_for_test_order(self) -> None:
        self._append_intent()
        self._append_rehearsal()

        payload = build_rehearsal_test_order_protective_check(execution_intent_id=self.intent_id, log_dir=self.log_dir, env={})

        self.assertEqual("READY_FOR_TEST_ORDER", payload["status"])
        self.assertTrue(payload["rehearsal_status"]["rehearsal_ready"])
        self.assertFalse(payload["test_order_status"]["test_order_validated_for_signal"])
        self.assertFalse(payload["order_placed"])

    def test_test_order_valid_but_protective_missing_ready_for_review(self) -> None:
        self._append_intent()
        self._append_rehearsal()
        self._append_test_order_validated()

        payload = build_rehearsal_test_order_protective_check(execution_intent_id=self.intent_id, log_dir=self.log_dir, env={})

        self.assertEqual("READY_FOR_PROTECTIVE_REVIEW", payload["status"])
        self.assertTrue(payload["test_order_status"]["test_order_validated_for_signal"])
        self.assertFalse(payload["protective_status"]["protective_payloads_ready"])
        self.assertFalse(payload["order_placed"])

    def test_protective_ready_reaches_final_manual_gate(self) -> None:
        self._append_intent()
        self._append_rehearsal()
        self._append_test_order_validated()
        self._append_protective_ready_check()

        payload = build_rehearsal_test_order_protective_check(execution_intent_id=self.intent_id, log_dir=self.log_dir, env={})

        self.assertEqual("READY_FOR_FINAL_MANUAL_GATE", payload["status"])
        self.assertTrue(payload["protective_status"]["stop_loss_ready"])
        self.assertTrue(payload["protective_status"]["take_profit_ready"])
        self.assertIn("final protected live gate", " ".join(payload["required_next_steps"]))
        self.assertFalse(payload["order_placed"])

    def test_real_order_record_blocks(self) -> None:
        self._append_intent()
        self._append_rehearsal()
        self._append_test_order_validated(order_placed=True, real_order_placed=True)

        payload = build_rehearsal_test_order_protective_check(execution_intent_id=self.intent_id, log_dir=self.log_dir, env={})

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("real/order placement record found", " ".join(payload["blockers"]))
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_naked_entry_allowed_blocks(self) -> None:
        self._append_intent()
        self._append_rehearsal()
        self._append_test_order_validated()
        self._append_protective_ready_check(entry_allowed_without_protective=True)

        payload = build_rehearsal_test_order_protective_check(execution_intent_id=self.intent_id, log_dir=self.log_dir, env={})

        self.assertEqual("BLOCKED", payload["status"])
        self.assertTrue(payload["no_naked_entry_status"]["entry_allowed_without_protective"])
        self.assertIn("naked entry would be allowed", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_api_endpoints_are_safe(self) -> None:
        status = self.client.get("/live/rehearsal-readiness/status").json()
        runbook = self.client.get("/live/rehearsal-readiness/runbook").json()
        check = self.client.post("/live/rehearsal-readiness/check", json={}).json()

        self.assertEqual("R78", status["phase"])
        self.assertEqual("R78", runbook["phase"])
        self.assertEqual("R78", check["phase"])
        self.assertFalse(check["order_placed"])
        self.assertFalse(check["real_order_placed"])
        self.assertFalse(check["execution_attempted"])
        self.assertFalse(check["secrets_shown"])

    def test_persistence_writes_sanitized_ndjson(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-binance-key",
            "BINANCE_API_SECRET": "secret-binance-secret",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
        }

        payload = build_rehearsal_test_order_protective_check(log_dir=self.log_dir, env=env)
        records = load_rehearsal_test_order_protective_checks(log_dir=self.log_dir)
        rendered = str(records)

        self.assertTrue(payload["audit_event_recorded"])
        self.assertEqual(1, len(records))
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("signature", rendered.lower())
        self.assertNotIn("auth", rendered.lower())
        self.assertFalse(records[0]["real_order_placed"])

    def test_telegram_commands_and_blocked_live_commands(self) -> None:
        readiness = handle_telegram_operator_command(text="LIVE REHEARSAL READINESS", log_dir=self.log_dir)
        runbook = handle_telegram_operator_command(text="LIVE REHEARSAL RUNBOOK", log_dir=self.log_dir)
        check = handle_telegram_operator_command(text="LIVE REHEARSAL CHECK", log_dir=self.log_dir)
        protective = handle_telegram_operator_command(text="LIVE PROTECTIVE READINESS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        for payload in (readiness, runbook, check, protective):
            self.assertEqual("ACCEPTED", payload["result_status"])
            self.assertIn("R78_READINESS_ONLY", payload["message"])
            self.assertIn("No order placed", payload["message"])
            self.assertIn("real_order_placed=false", payload["message"])
            self.assertIn("execution_attempted=false", payload["message"])
            self.assertFalse(payload["order_placed"])
            self.assertFalse(payload["real_order_placed"])
            self.assertFalse(payload["execution_attempted"])

        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(trade_now["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def _append_intent(self) -> None:
        append_live_execution_intent(
            {
                "execution_intent_id": self.intent_id,
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "phase": "R52",
                "event_type": "live_execution_intent",
                "status": "INTENT_READY",
                "signal_id": self.signal_id,
                "preview_hash": "preview-r78",
                "approval_status": "APPROVED",
                "live_begins_status": "READY_FOR_OPERATOR_APPROVAL",
                "preview_status": "PREVIEW_READY",
                "execution_mode": "INTENT_ONLY",
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "blockers": [],
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _append_rehearsal(self) -> None:
        append_live_executor_rehearsal(
            {
                "executor_rehearsal_id": self.rehearsal_id,
                "execution_intent_id": self.intent_id,
                "created_at": datetime.now(UTC).isoformat(),
                "phase": "R53",
                "event_type": "live_executor_rehearsal",
                "status": "REHEARSAL_READY",
                "signal_id": self.signal_id,
                "preview_hash": "preview-r78",
                "execution_mode": "REHEARSAL_ONLY",
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "network_allowed": False,
                "blockers": [],
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _append_test_order_validated(self, *, order_placed: bool = False, real_order_placed: bool = False) -> None:
        append_connector_attempt(
            {
                "attempt_id": "test-order-r78",
                "created_at": datetime.now(UTC).isoformat(),
                "endpoint": "test_order",
                "action": "test_order",
                "connector_mode": "TEST_ORDER_ONLY",
                "signal_id": self.signal_id,
                "preflight_id": "preflight-r78",
                "status": "TEST_ORDER_MOCK_VALIDATED",
                "blockers": [],
                "network_used": False,
                "order_payload_created": True,
                "signed_payload_created": True,
                "execution_attempted": True,
                "order_placed": order_placed,
                "real_order_placed": real_order_placed,
                "mock_order_placed": False,
                "live_execution_enabled": False,
                "allow_live_orders": False,
                "global_kill_switch": True,
                "secrets_shown": False,
                "payload_preview": None,
                "sanitized_signed_request": None,
            },
            log_dir=self.log_dir,
        )

    def _append_protective_ready_check(self, *, entry_allowed_without_protective: bool = False) -> None:
        append_first_live_protective_check(
            {
                "check_id": "protective-r78",
                "phase": "R63",
                "event_type": "first_live_protective_adapter_check",
                "created_at": datetime.now(UTC).isoformat(),
                "status": "PROTECTIVE_PLAN_READY",
                "protective_plan": {
                    "available": True,
                    "stop_loss_available": True,
                    "take_profit_available": True,
                    "blockers": [],
                },
                "protective_gate": {
                    "entry_allowed_without_protective": entry_allowed_without_protective,
                    "naked_entry_blocked": not entry_allowed_without_protective,
                },
                "blockers": [],
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "network_allowed": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _patched_protective_ready(self, *, entry_allowed_without_protective: bool = False):
        payload = {
            "status": "PROTECTIVE_PLAN_READY",
            "protective_plan": {
                "available": True,
                "stop_loss_available": True,
                "take_profit_available": True,
                "blockers": [],
            },
            "protective_gate": {
                "entry_allowed_without_protective": entry_allowed_without_protective,
                "naked_entry_blocked": not entry_allowed_without_protective,
            },
            "blockers": [],
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "network_allowed": False,
            "secrets_shown": False,
        }
        return patch(
            "src.app.hammer_radar.operator.rehearsal_test_order_protective_readiness.build_first_live_protective_status",
            return_value=payload,
        )


if __name__ == "__main__":
    unittest.main()
