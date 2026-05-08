from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_live_chain_runbook import build_first_live_chain_status
from src.app.hammer_radar.operator.live_approval import append_live_approval_request
from src.app.hammer_radar.operator.live_execution_intent import append_live_execution_intent
from src.app.hammer_radar.operator.live_executor_rehearsal import append_live_executor_rehearsal
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstLiveChainRunbookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)
        timestamp = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        self.signal_id = f"BTCUSDT|13m|long|{timestamp}"
        self.intent_id = "intent-r65"
        self.rehearsal_id = "rehearsal-r65"

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_status_safe(self) -> None:
        payload = self.client.get("/live/first-chain/status").json()

        self.assertEqual("R65", payload["phase"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])

    def test_default_waits_or_blocks_safely(self) -> None:
        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertFalse(payload["chain_state"]["exact_chain_resolved"])
        self.assertIn(payload["next_action"]["kind"], {"wait_for_signal", "blocked"})
        self.assertNotEqual(True, payload.get("live_eligibility"))

    def test_phase_statuses_surface_r58_to_r64(self) -> None:
        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})
        statuses = payload["phase_statuses"]

        for key in (
            "r58_profile",
            "r59_readiness",
            "r60_caps",
            "r61_adapter",
            "r62_ladder",
            "r63_protective",
            "r64_test_order_gate",
        ):
            self.assertIn(key, statuses)

    def test_operator_sequence_present(self) -> None:
        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})
        sequence = payload["operator_sequence"]

        self.assertGreaterEqual(len(sequence), 8)
        self.assertEqual([1, 2, 3], [item["step"] for item in sequence[:3]])
        self.assertTrue(all(item["required"] for item in sequence))
        self.assertFalse(payload["execution_attempted"])

    def test_no_fresh_signal_waits(self) -> None:
        payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertIn(payload["status"], {"WAITING_FOR_FRESH_SIGNAL", "BLOCKED"})
        self.assertIn(payload["next_action"]["kind"], {"wait_for_signal", "blocked"})

    def test_fresh_signal_without_approval_waits_for_approval(self) -> None:
        with self._patched_preview(), self._patched_r64():
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("WAITING_FOR_APPROVAL", payload["status"])
        self.assertEqual("approve_signal", payload["next_action"]["kind"])
        self.assertEqual(f"LIVE APPROVE {self.signal_id}", payload["next_action"]["telegram_command"])

    def test_approval_without_intent_waits_for_intent(self) -> None:
        self._append_approval()
        with self._patched_preview(), self._patched_r64():
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("WAITING_FOR_INTENT", payload["status"])
        self.assertEqual("create_intent", payload["next_action"]["kind"])
        self.assertEqual(f"LIVE INTENT {self.signal_id}", payload["next_action"]["telegram_command"])

    def test_intent_without_rehearsal_waits_for_rehearsal(self) -> None:
        self._append_approval()
        self._append_intent()
        with self._patched_preview(), self._patched_r64():
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("WAITING_FOR_REHEARSAL", payload["status"])
        self.assertEqual("run_rehearsal", payload["next_action"]["kind"])
        self.assertEqual(f"LIVE REHEARSAL {self.intent_id}", payload["next_action"]["telegram_command"])

    def test_rehearsal_without_payloads_or_test_order_waits_conservatively(self) -> None:
        self._append_approval()
        self._append_intent()
        self._append_rehearsal()
        r64 = self._r64_payload(payloads_ready=True, test_order_validated=False)
        with self._patched_preview(), self._patched_r64(r64):
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertEqual("WAITING_FOR_TEST_ORDER", payload["status"])
        self.assertEqual("validate_test_order", payload["next_action"]["kind"])
        self.assertEqual(f"FIRST LIVE TEST ORDER {self.rehearsal_id}", payload["next_action"]["telegram_command"])

    def test_api_endpoints_persist_sanitized_event(self) -> None:
        status = self.client.get("/live/first-chain/status").json()
        check = self.client.post("/live/first-chain/check").json()
        checks = self.client.get("/live/first-chain/checks").json()

        self.assertEqual("R65", status["phase"])
        self.assertEqual("R65", check["phase"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertGreaterEqual(checks["count"], 1)
        self.assertFalse(checks["checks"][0]["real_order_placed"])

    def test_telegram_commands(self) -> None:
        chain = handle_telegram_operator_command(text="FIRST LIVE CHAIN", log_dir=self.log_dir)
        next_action = handle_telegram_operator_command(text="FIRST LIVE NEXT", log_dir=self.log_dir)
        runbook = handle_telegram_operator_command(text="FIRST LIVE RUNBOOK", log_dir=self.log_dir)
        sequence = handle_telegram_operator_command(text="FIRST LIVE SEQUENCE", log_dir=self.log_dir)
        checks = handle_telegram_operator_command(text="FIRST LIVE CHAIN CHECKS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", chain["result_status"])
        self.assertEqual("ACCEPTED", next_action["result_status"])
        self.assertEqual("ACCEPTED", runbook["result_status"])
        self.assertEqual("ACCEPTED", sequence["result_status"])
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(trade_now["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_secret_hygiene(self) -> None:
        env = {
            "BINANCE_API_KEY": "secret-binance-key",
            "BINANCE_API_SECRET": "secret-binance-secret",
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
        }

        payload = build_first_live_chain_status(log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("signature", rendered.lower())
        self.assertNotIn("auth", rendered.lower())

    def test_no_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = build_first_live_chain_status(log_dir=self.log_dir, env={})

        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["real_order_placed"])

    def _append_approval(self) -> None:
        append_live_approval_request(
            {
                "request_id": "approval-r65",
                "created_at": datetime.now(UTC).isoformat(),
                "raw_text": f"LIVE APPROVE {self.signal_id}",
                "normalized_action": "live_approve_exact",
                "parse_status": "ACCEPTED",
                "signal_id": self.signal_id,
                "approval_gate_status": "BLOCKED",
                "order_placed": False,
                "execution_attempted": False,
            },
            log_dir=self.log_dir,
        )

    def _append_intent(self) -> None:
        append_live_execution_intent(
            {
                "execution_intent_id": self.intent_id,
                "status": "INTENT_READY",
                "execution_mode": "INTENT_ONLY",
                "signal_id": self.signal_id,
                "preview_hash": "preview-r65",
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
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
                "status": "REHEARSAL_READY",
                "execution_mode": "REHEARSAL_ONLY",
                "signal_id": self.signal_id,
                "preview_hash": "preview-r65",
                "created_at": datetime.now(UTC).isoformat(),
                "network_allowed": False,
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _patched_preview(self):
        return patch(
            "src.app.hammer_radar.operator.first_live_chain_runbook.build_live_execution_preview",
            return_value={
                "status": "PREVIEW_READY",
                "latest_signal_id": self.signal_id,
                "symbol": "BTCUSDT",
                "timeframe": "13m",
                "direction": "long",
                "freshness_status": "fresh",
            },
        )

    def _patched_r64(self, payload: dict | None = None):
        return patch(
            "src.app.hammer_radar.operator.first_live_chain_runbook.build_first_live_test_order_status",
            return_value=payload or self._r64_payload(),
        )

    def _r64_payload(self, *, payloads_ready: bool = False, test_order_validated: bool = False) -> dict:
        return {
            "status": "PAYLOADS_READY_TEST_ORDER_MISSING" if payloads_ready and not test_order_validated else "EXACT_CHAIN_MISSING",
            "payload_readiness": {
                "entry_payload_ready": payloads_ready,
                "protective_payloads_ready": payloads_ready,
            },
            "test_order_status": {"test_order_validated_for_signal": test_order_validated},
            "live_eligibility": {"eligible_for_manual_env_arming": False},
            "blockers": [] if payloads_ready else ["payloads missing"],
        }


if __name__ == "__main__":
    unittest.main()
