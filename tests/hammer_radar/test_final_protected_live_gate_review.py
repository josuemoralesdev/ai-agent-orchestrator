from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.execution.binance_futures_connector import append_connector_attempt
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.final_protected_live_gate_review import (
    build_final_protected_live_gate_check,
    build_final_protected_live_gate_status,
    load_final_protected_live_gate_checks,
)
from src.app.hammer_radar.operator.first_live_protective_adapter import append_first_live_protective_check
from src.app.hammer_radar.operator.live_execution_intent import append_live_execution_intent
from src.app.hammer_radar.operator.live_executor_rehearsal import append_live_executor_rehearsal
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FinalProtectedLiveGateReviewTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)
        self.signal_id = "BTCUSDT|13m|long|2026-05-12T10:00:00+00:00"
        self.intent_id = "intent-r79"
        self.rehearsal_id = "rehearsal-r79"

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_status_awaiting_chain_safe(self) -> None:
        payload = build_final_protected_live_gate_status(log_dir=self.log_dir, env={})

        self.assertIn(payload["status"], {"AWAITING_CHAIN", "BLOCKED"})
        self.assertEqual("R79", payload["phase"])
        self.assertEqual("fast", payload["performance"]["mode"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["secrets_shown"])

    def test_blocks_unexpected_live_env(self) -> None:
        env = {"HAMMER_LIVE_EXECUTION_ENABLED": "true"}

        payload = build_final_protected_live_gate_status(log_dir=self.log_dir, env=env)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("HAMMER_LIVE_EXECUTION_ENABLED is true before final gate", payload["blockers"])
        self.assertFalse(payload["order_placed"])

        allow = build_final_protected_live_gate_status(log_dir=self.log_dir, env={"HAMMER_ALLOW_LIVE_ORDERS": "true"})
        self.assertEqual("BLOCKED", allow["status"])
        self.assertIn("HAMMER_ALLOW_LIVE_ORDERS is true before final gate", allow["blockers"])

    def test_blocks_inactive_kill_switch(self) -> None:
        payload = build_final_protected_live_gate_status(log_dir=self.log_dir, env={"HAMMER_GLOBAL_KILL_SWITCH": "false"})

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("HAMMER_GLOBAL_KILL_SWITCH is not active before final gate", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_intent_but_no_rehearsal_awaiting_rehearsal(self) -> None:
        self._append_intent()

        payload = build_final_protected_live_gate_status(log_dir=self.log_dir, env={})

        self.assertEqual("AWAITING_REHEARSAL", payload["status"])
        self.assertTrue(payload["ready_checks"]["chain_ready"])
        self.assertFalse(payload["ready_checks"]["rehearsal_ready"])
        self.assertFalse(payload["order_placed"])

    def test_rehearsal_but_no_test_order(self) -> None:
        self._append_intent()
        self._append_rehearsal()

        payload = build_final_protected_live_gate_status(log_dir=self.log_dir, env={})

        self.assertEqual("AWAITING_TEST_ORDER", payload["status"])
        self.assertTrue(payload["ready_checks"]["rehearsal_ready"])
        self.assertFalse(payload["ready_checks"]["test_order_ready"])
        self.assertFalse(payload["order_placed"])

    def test_test_order_but_protective_missing(self) -> None:
        self._append_intent()
        self._append_rehearsal()
        self._append_test_order_validated()

        payload = build_final_protected_live_gate_status(log_dir=self.log_dir, env={})

        self.assertEqual("AWAITING_PROTECTIVE_READY", payload["status"])
        self.assertTrue(payload["ready_checks"]["test_order_ready"])
        self.assertFalse(payload["ready_checks"]["protective_ready"])
        self.assertFalse(payload["order_placed"])

    def test_all_structural_readiness_env_disabled(self) -> None:
        self._append_full_structural_readiness()

        payload = build_final_protected_live_gate_check(available_usdt=88, log_dir=self.log_dir, env={})

        self.assertEqual("AWAITING_MANUAL_ENV_ARMING", payload["status"])
        self.assertTrue(payload["ready_checks"]["balance_ready"])
        self.assertTrue(payload["ready_checks"]["protective_ready"])
        self.assertTrue(payload["ready_checks"]["live_execution_still_disabled"])
        self.assertTrue(payload["ready_checks"]["kill_switch_still_active"])
        self.assertFalse(payload["order_placed"])

    def test_real_order_flag_blocks(self) -> None:
        self._append_intent()
        self._append_rehearsal()
        self._append_test_order_validated(order_placed=True, real_order_placed=True)

        payload = build_final_protected_live_gate_status(log_dir=self.log_dir, env={})

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("real/order placement record found", " ".join(payload["blockers"]))
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_api_endpoints(self) -> None:
        status = self.client.get("/live/final-gate/status").json()
        runbook = self.client.get("/live/final-gate/runbook").json()
        check = self.client.post("/live/final-gate/check", json={"available_usdt": 88}).json()

        self.assertEqual("R79", status["phase"])
        self.assertEqual("R79", runbook["phase"])
        self.assertEqual("R79", check["phase"])
        self.assertFalse(check["order_placed"])
        self.assertFalse(check["real_order_placed"])
        self.assertFalse(check["execution_attempted"])
        self.assertFalse(check["secrets_shown"])

    def test_persistence_sanitized(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-binance-key",
            "BINANCE_API_SECRET": "secret-binance-secret",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
        }

        payload = build_final_protected_live_gate_check(available_usdt=88, log_dir=self.log_dir, env=env)
        records = load_final_protected_live_gate_checks(log_dir=self.log_dir)
        rendered = str(records)

        self.assertTrue(payload["audit_event_recorded"])
        self.assertEqual(1, len(records))
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("signature", rendered.lower())
        self.assertNotIn("auth", rendered.lower())
        self.assertFalse(records[0]["real_order_placed"])

    def test_telegram_commands_safe(self) -> None:
        gate = handle_telegram_operator_command(text="LIVE FINAL GATE", log_dir=self.log_dir)
        status = handle_telegram_operator_command(text="LIVE FINAL STATUS", log_dir=self.log_dir)
        runbook = handle_telegram_operator_command(text="LIVE FINAL RUNBOOK", log_dir=self.log_dir)
        check = handle_telegram_operator_command(text="LIVE FINAL CHECK", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        for payload in (gate, status, runbook, check):
            self.assertEqual("ACCEPTED", payload["result_status"])
            self.assertIn("R79_FINAL_GATE_REVIEW_ONLY", payload["message"])
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

    def _append_full_structural_readiness(self) -> None:
        self._append_intent()
        self._append_rehearsal()
        self._append_test_order_validated()
        self._append_protective_ready_check()

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
                "preview_hash": "preview-r79",
                "execution_mode": "INTENT_ONLY",
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
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
                "preview_hash": "preview-r79",
                "execution_mode": "REHEARSAL_ONLY",
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "network_allowed": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _append_test_order_validated(self, *, order_placed: bool = False, real_order_placed: bool = False) -> None:
        append_connector_attempt(
            {
                "attempt_id": "test-order-r79",
                "created_at": datetime.now(UTC).isoformat(),
                "endpoint": "test_order",
                "action": "test_order",
                "signal_id": self.signal_id,
                "status": "TEST_ORDER_MOCK_VALIDATED",
                "order_placed": order_placed,
                "real_order_placed": real_order_placed,
                "execution_attempted": True,
                "network_used": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _append_protective_ready_check(self) -> None:
        append_first_live_protective_check(
            {
                "check_id": "protective-r79",
                "phase": "R63",
                "created_at": datetime.now(UTC).isoformat(),
                "status": "PROTECTIVE_PLAN_READY",
                "protective_plan": {
                    "available": True,
                    "stop_loss_available": True,
                    "take_profit_available": True,
                },
                "protective_gate": {
                    "entry_allowed_without_protective": False,
                    "naked_entry_blocked": True,
                },
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "network_allowed": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )


if __name__ == "__main__":
    unittest.main()
