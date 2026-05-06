from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.live_execution_intent import append_live_execution_intent, compute_preview_hash
from src.app.hammer_radar.operator.live_executor_rehearsal import (
    create_live_executor_rehearsal,
    list_live_executor_rehearsals,
    load_live_executor_rehearsals,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class LiveExecutorRehearsalTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_missing_intent_or_signal_rejects(self) -> None:
        payload = self.client.post("/live/executor/rehearsal", json={}).json()

        self.assertEqual("REJECTED", payload["status"])
        self.assertFalse(payload["checks"]["intent_id_or_signal_present"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])

    def test_missing_intent_blocks(self) -> None:
        payload = create_live_executor_rehearsal(execution_intent_id="missing", log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("MISSING", payload["intent_status"])
        self.assertIn("execution intent not found", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_expired_intent_blocks(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview, expires_at=datetime.now(UTC) - timedelta(minutes=1))

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("EXPIRED", payload["intent_status"])
        self.assertIn("execution intent is expired", payload["blockers"])
        self.assertFalse(payload["real_order_placed"])

    def test_blocked_intent_blocks(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview, status="BLOCKED")

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("BLOCKED", payload["intent_status"])
        self.assertFalse(payload["checks"]["intent_ready"])

    def test_valid_intent_but_r50_blocked_blocks_with_sequence(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)

        with self._patched_live_begins(status="BLOCKED"), self._patched_preview(preview):
            payload = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["live_begins_allows_rehearsal"])
        self.assertIn("live begins is BLOCKED", payload["blockers"])
        self.assertTrue(any(step["name"] == "validate_live_begins_state" and step["status"] == "BLOCKED" for step in payload["sequence"]))
        self.assertFalse(payload["order_placed"])

    def test_valid_intent_but_r51_preview_blocked_blocks(self) -> None:
        ready_preview = self._preview(self._signal_id())
        blocked_preview = dict(ready_preview, status="BLOCKED")
        intent_id = self._append_intent(ready_preview)

        with self._patched_live_begins(), self._patched_preview(blocked_preview):
            payload = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("BLOCKED", payload["preview_status"])
        self.assertFalse(payload["checks"]["preview_allows_rehearsal"])

    def test_preview_hash_mismatch_blocks(self) -> None:
        intent_preview = self._preview(self._signal_id(), entry=101.0)
        current_preview = self._preview(self._signal_id(), entry=100.0)
        intent_id = self._append_intent(intent_preview)

        with self._patched_live_begins(), self._patched_preview(current_preview):
            payload = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["preview_hash_matches"])
        self.assertIn("current preview hash differs from approved intent preview hash; re-approval required", payload["blockers"])

    def test_all_pass_creates_rehearsal_ready(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir)

        self.assertEqual("REHEARSAL_READY", payload["status"])
        self.assertEqual("R53", payload["phase"])
        self.assertEqual("REHEARSAL_ONLY", payload["execution_mode"])
        self.assertIsNotNone(payload["executor_rehearsal_id"])
        self.assertEqual(intent_id, payload["execution_intent_id"])
        self.assertEqual(preview["latest_signal_id"], payload["signal_id"])
        self.assertEqual(compute_preview_hash(preview), payload["preview_hash"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertTrue(any(step["name"] == "stop_before_network" for step in payload["sequence"]))

    def test_entry_order_preview_long_and_short(self) -> None:
        cases = [
            ("long", "BUY", "LONG"),
            ("short", "SELL", "SHORT"),
        ]
        for direction, side, position_side in cases:
            with self.subTest(direction=direction):
                preview = self._preview(self._signal_id(suffix=direction), direction=direction, side=side, position_side=position_side)
                intent_id = self._append_intent(preview)
                with self._patched_live_begins(), self._patched_preview(preview):
                    payload = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir)

                entry = payload["entry_order_preview"]
                self.assertEqual(side, entry["side"])
                self.assertEqual(position_side, entry["position_side"])
                self.assertTrue(entry["preview_only"])
                self.assertFalse(entry["reduce_only"])

    def test_protective_order_previews_are_present(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir)

        protective = payload["protective_orders_preview"]
        self.assertEqual("READY", protective["status"])
        self.assertTrue(protective["stop_loss"]["reduce_only"])
        self.assertTrue(protective["take_profit"]["preview_only"])
        self.assertFalse(payload["order_placed"])

    def test_idempotency_returns_same_ready_rehearsal(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)

        with self._patched_live_begins(), self._patched_preview(preview):
            first = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir)
            second = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir)
        records = load_live_executor_rehearsals(limit=10, execution_intent_id=intent_id, log_dir=self.log_dir)

        self.assertEqual("REHEARSAL_READY", first["status"])
        self.assertEqual(first["executor_rehearsal_id"], second["executor_rehearsal_id"])
        self.assertEqual(1, len(records))

    def test_list_endpoint_returns_sanitized_list(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        with self._patched_live_begins(), self._patched_preview(preview):
            create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir)

        api_payload = self.client.get("/live/executor/rehearsals").json()
        direct_payload = list_live_executor_rehearsals(log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", api_payload["result_status"])
        self.assertEqual("R53", api_payload["phase"])
        self.assertFalse(api_payload["secrets_shown"])
        self.assertEqual(1, direct_payload["count"])

    def test_telegram_commands_are_safe(self) -> None:
        missing = handle_telegram_operator_command(text="LIVE REHEARSAL", log_dir=self.log_dir)
        unknown = handle_telegram_operator_command(text="LIVE REHEARSAL unknown", log_dir=self.log_dir)
        rehearsals = handle_telegram_operator_command(text="LIVE REHEARSALS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("REJECTED", missing["result_status"])
        self.assertEqual("BLOCKED", unknown["result_status"])
        self.assertEqual("ACCEPTED", rehearsals["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(missing["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_secret_hygiene(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        env = {
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "BINANCE_API_KEY": "secret-binance-key",
            "BINANCE_API_SECRET": "secret-binance-secret",
        }

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = create_live_executor_rehearsal(execution_intent_id=intent_id, log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("raw env", rendered.lower())

    def test_rehearsal_does_not_call_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = create_live_executor_rehearsal(execution_intent_id="missing", log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def _append_intent(
        self,
        preview: dict,
        *,
        status: str = "INTENT_READY",
        expires_at: datetime | None = None,
    ) -> str:
        intent_id = f"intent-{preview['latest_signal_id']}-{status}"
        append_live_execution_intent(
            {
                "execution_intent_id": intent_id,
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": (expires_at or (datetime.now(UTC) + timedelta(minutes=5))).isoformat(),
                "phase": "R52",
                "event_type": "live_execution_intent",
                "status": status,
                "signal_id": preview["latest_signal_id"],
                "preview_hash": compute_preview_hash(preview),
                "approval_status": "APPROVED",
                "live_begins_status": "READY_FOR_OPERATOR_APPROVAL",
                "preview_status": preview["status"],
                "execution_mode": "INTENT_ONLY",
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "blockers": [],
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )
        return intent_id

    def _patched_live_begins(self, *, status: str = "READY_FOR_OPERATOR_APPROVAL"):
        return patch(
            "src.app.hammer_radar.operator.live_executor_rehearsal.build_live_begins_status",
            return_value={"status": status},
        )

    def _patched_preview(self, preview: dict):
        return patch(
            "src.app.hammer_radar.operator.live_executor_rehearsal.build_live_execution_preview",
            return_value=preview,
        )

    @staticmethod
    def _signal_id(*, suffix: str = "ok") -> str:
        return f"BTCUSDT|13m|long|2026-05-05T10:00:00+00:00-{suffix}"

    @staticmethod
    def _preview(
        signal_id: str,
        *,
        entry: float = 100.0,
        direction: str = "long",
        side: str = "BUY",
        position_side: str = "LONG",
    ) -> dict:
        close_side = "SELL" if direction == "long" else "BUY"
        return {
            "status": "PREVIEW_READY",
            "phase": "R51",
            "system": "money_printing_machine_hammer_radar",
            "execution_mode": "PREVIEW_ONLY",
            "latest_signal_id": signal_id,
            "symbol": "BTCUSDT",
            "timeframe": "13m",
            "direction": direction,
            "entry": entry,
            "stop": 95.0 if direction == "long" else 105.0,
            "take_profit": 110.0 if direction == "long" else 90.0,
            "order_side": side,
            "position_side": position_side,
            "margin_mode": "ISOLATED",
            "margin_usdt": 6.0,
            "leverage": 1.0,
            "notional_usdt": 6.0,
            "risk_usdt": 0.3,
            "quantity": 0.06,
            "protective_orders_preview": {
                "stop_loss": {"trigger_price": 95.0, "side": close_side, "reduce_only": True, "preview_only": True},
                "take_profit": {"trigger_price": 110.0, "side": close_side, "reduce_only": True, "preview_only": True},
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
