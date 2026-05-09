from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.live_approval import append_live_approval_request, find_valid_live_approval_for_signal
from src.app.hammer_radar.operator.live_execution_intent import (
    append_live_execution_intent,
    compute_preview_hash,
    create_live_execution_intent,
    list_live_execution_intents,
    load_live_execution_intents,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class LiveExecutionIntentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_missing_signal_id_rejects(self) -> None:
        response = self.client.post("/live/execution/intent", json={})
        payload = response.json()

        self.assertEqual(200, response.status_code)
        self.assertEqual("REJECTED", payload["status"])
        self.assertFalse(payload["checks"]["signal_id_present"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])

    def test_no_exact_approval_blocks(self) -> None:
        signal_id = self._signal_id()
        with self._patched_live_begins(), self._patched_preview(self._preview(signal_id)):
            payload = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("MISSING", payload["approval_status"])
        self.assertFalse(payload["checks"]["exact_approval_present"])
        self.assertFalse(payload["order_placed"])

    def test_r68_blocked_approval_source_lookup_is_valid_for_exact_signal(self) -> None:
        signal_id = self._signal_id()
        self._append_approval(signal_id, approval_gate_status="BLOCKED")

        lookup = find_valid_live_approval_for_signal(signal_id, log_dir=self.log_dir)

        self.assertTrue(lookup["approval_found"])
        self.assertEqual("APPROVED", lookup["approval_status"])
        self.assertEqual(f"approval-{signal_id}", lookup["request_id"])
        self.assertFalse(lookup["order_placed"])
        self.assertFalse(lookup["real_order_placed"])
        self.assertFalse(lookup["secrets_shown"])

    def test_raw_yes_and_trade_now_live_remain_safe(self) -> None:
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(raw_yes["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_approval_for_different_signal_blocks(self) -> None:
        signal_a = self._signal_id(suffix="A")
        signal_b = self._signal_id(suffix="B")
        self._append_approval(signal_a)

        with self._patched_live_begins(), self._patched_preview(self._preview(signal_b)):
            payload = create_live_execution_intent(signal_id=signal_b, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["approval_matches_signal"])
        self.assertEqual("MISSING", payload["approval_status"])

    def test_exact_approval_but_r50_blocked_blocks(self) -> None:
        signal_id = self._signal_id()
        self._append_approval(signal_id)

        with self._patched_live_begins(status="BLOCKED"), self._patched_preview(self._preview(signal_id)):
            payload = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("BLOCKED", payload["live_begins_status"])
        self.assertFalse(payload["checks"]["live_begins_allows_intent"])
        self.assertIsNone(payload["execution_intent_id"])

    def test_exact_approval_but_r51_preview_blocked_blocks(self) -> None:
        signal_id = self._signal_id()
        self._append_approval(signal_id)

        with self._patched_live_begins(), self._patched_preview(self._preview(signal_id, status="BLOCKED")):
            payload = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("BLOCKED", payload["preview_status"])
        self.assertFalse(payload["checks"]["preview_allows_intent"])
        self.assertIsNone(payload["execution_intent_id"])

    def test_all_pass_creates_intent_ready(self) -> None:
        signal_id = self._signal_id()
        self._append_approval(signal_id)

        with self._patched_live_begins(), self._patched_preview(self._preview(signal_id)):
            payload = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir)

        self.assertEqual("INTENT_READY", payload["status"])
        self.assertEqual("R52", payload["phase"])
        self.assertEqual("INTENT_ONLY", payload["execution_mode"])
        self.assertIsNotNone(payload["execution_intent_id"])
        self.assertEqual(signal_id, payload["signal_id"])
        self.assertIsNotNone(payload["preview_hash"])
        self.assertEqual("APPROVED", payload["approval_status"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_r52_accepts_r68_blocked_approval_record(self) -> None:
        signal_id = self._signal_id()
        self._append_approval(signal_id, approval_gate_status="BLOCKED")

        with self._patched_live_begins(), self._patched_preview(self._preview(signal_id)):
            payload = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir)

        self.assertEqual("INTENT_READY", payload["status"])
        self.assertEqual("APPROVED", payload["approval_status"])
        self.assertEqual(f"approval-{signal_id}", payload["approval_request_id"])
        self.assertNotIn("exact approval is missing", payload["blockers"])
        self.assertNotIn("exact approval for signal_id is missing", payload["blockers"])
        self.assertIsNotNone(payload["execution_intent_id"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_expired_approval_record_blocks_intent(self) -> None:
        signal_id = self._signal_id()
        self._append_approval(
            signal_id,
            approval_gate_status="BLOCKED",
            expires_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        )

        with self._patched_live_begins(), self._patched_preview(self._preview(signal_id)):
            payload = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("EXPIRED", payload["approval_status"])
        self.assertIn("approval is missing or expired", payload["blockers"])
        self.assertIsNone(payload["execution_intent_id"])

    def test_idempotency_returns_same_unexpired_intent(self) -> None:
        signal_id = self._signal_id()
        self._append_approval(signal_id)

        with self._patched_live_begins(), self._patched_preview(self._preview(signal_id)):
            first = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir)
            second = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir)
        records = load_live_execution_intents(limit=10, signal_id=signal_id, log_dir=self.log_dir)

        self.assertEqual("INTENT_READY", first["status"])
        self.assertEqual("INTENT_READY", second["status"])
        self.assertEqual(first["execution_intent_id"], second["execution_intent_id"])
        self.assertEqual(1, len(records))

    def test_preview_changed_blocks_reapproval_required(self) -> None:
        signal_id = self._signal_id()
        self._append_approval(signal_id)
        old_preview = self._preview(signal_id, entry=101.0)
        append_live_execution_intent(
            {
                "execution_intent_id": "old-intent",
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "phase": "R52",
                "event_type": "live_execution_intent",
                "status": "INTENT_READY",
                "signal_id": signal_id,
                "preview_hash": compute_preview_hash(old_preview),
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

        with self._patched_live_begins(), self._patched_preview(self._preview(signal_id, entry=100.0)):
            payload = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("preview changed for signal_id; re-approval required", payload["blockers"])

    def test_expired_intent_does_not_count_active_and_new_intent_is_created(self) -> None:
        signal_id = self._signal_id()
        preview = self._preview(signal_id)
        self._append_approval(signal_id)
        append_live_execution_intent(
            {
                "execution_intent_id": "expired-intent",
                "created_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
                "expires_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
                "phase": "R52",
                "event_type": "live_execution_intent",
                "status": "INTENT_READY",
                "signal_id": signal_id,
                "preview_hash": compute_preview_hash(preview),
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

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir)

        self.assertEqual("INTENT_READY", payload["status"])
        self.assertNotEqual("expired-intent", payload["execution_intent_id"])

    def test_list_endpoint_returns_sanitized_list(self) -> None:
        signal_id = self._signal_id()
        self._append_approval(signal_id)
        with self._patched_live_begins(), self._patched_preview(self._preview(signal_id)):
            create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir)

        api_payload = self.client.get("/live/execution/intents").json()
        direct_payload = list_live_execution_intents(log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", api_payload["result_status"])
        self.assertEqual("R52", api_payload["phase"])
        self.assertFalse(api_payload["secrets_shown"])
        self.assertEqual(1, direct_payload["count"])

    def test_telegram_live_intent_commands(self) -> None:
        signal_id = self._signal_id()
        missing = handle_telegram_operator_command(text="LIVE INTENT", log_dir=self.log_dir)
        blocked = handle_telegram_operator_command(text=f"LIVE INTENT {signal_id}", log_dir=self.log_dir)
        intents = handle_telegram_operator_command(text="LIVE INTENTS", log_dir=self.log_dir)

        self.assertEqual("REJECTED", missing["result_status"])
        self.assertEqual("BLOCKED", blocked["result_status"])
        self.assertEqual("ACCEPTED", intents["result_status"])
        self.assertFalse(missing["order_placed"])
        self.assertFalse(blocked["real_order_placed"])

    def test_secret_hygiene(self) -> None:
        signal_id = self._signal_id()
        self._append_approval(signal_id)
        env = {
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "BINANCE_API_KEY": "secret-binance-key",
            "BINANCE_API_SECRET": "secret-binance-secret",
        }

        with self._patched_live_begins(), self._patched_preview(self._preview(signal_id)):
            payload = create_live_execution_intent(signal_id=signal_id, log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("raw env", rendered.lower())

    def test_intent_does_not_call_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = create_live_execution_intent(signal_id=self._signal_id(), log_dir=self.log_dir)

        self.assertIn(payload["status"], {"BLOCKED", "REJECTED"})
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def _append_approval(self, signal_id: str, *, approval_gate_status: str = "READY_BUT_EXECUTION_DISABLED", expires_at: str | None = None) -> None:
        append_live_approval_request(
            {
                "request_id": f"approval-{signal_id}",
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": expires_at,
                "source": "test",
                "raw_text": f"LIVE APPROVE {signal_id}",
                "normalized_action": "live_approve_exact",
                "parse_status": "ACCEPTED",
                "signal_id": signal_id,
                "approval_gate_status": approval_gate_status,
                "order_placed": False,
                "execution_attempted": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _patched_live_begins(self, *, status: str = "READY_FOR_OPERATOR_APPROVAL"):
        return patch(
            "src.app.hammer_radar.operator.live_execution_intent.build_live_begins_status",
            return_value={"status": status},
        )

    def _patched_preview(self, preview: dict):
        return patch(
            "src.app.hammer_radar.operator.live_execution_intent.build_live_execution_preview",
            return_value=preview,
        )

    @staticmethod
    def _signal_id(*, suffix: str = "ok") -> str:
        return f"BTCUSDT|13m|long|2026-05-05T10:00:00+00:00-{suffix}"

    @staticmethod
    def _preview(signal_id: str, *, status: str = "PREVIEW_READY", entry: float = 100.0) -> dict:
        return {
            "status": status,
            "phase": "R51",
            "system": "money_printing_machine_hammer_radar",
            "execution_mode": "PREVIEW_ONLY",
            "latest_signal_id": signal_id,
            "symbol": "BTCUSDT",
            "timeframe": "13m",
            "direction": "long",
            "entry": entry,
            "stop": 95.0,
            "take_profit": 110.0,
            "order_side": "BUY",
            "position_side": "LONG",
            "margin_usdt": 6.0,
            "leverage": 1.0,
            "notional_usdt": 6.0,
            "risk_usdt": 0.3,
            "quantity": 0.06,
            "protective_orders_preview": {
                "stop_loss": {"trigger_price": 95.0, "side": "SELL", "reduce_only": True},
                "take_profit": {"trigger_price": 110.0, "side": "SELL", "reduce_only": True},
                "reduce_only": True,
                "close_position": False,
                "status": "READY",
            },
            "order_placed": False,
            "real_order_placed": False,
            "secrets_shown": False,
        }


if __name__ == "__main__":
    unittest.main()
