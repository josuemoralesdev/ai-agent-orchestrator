from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.live_execution_intent import append_live_execution_intent, compute_preview_hash
from src.app.hammer_radar.operator.live_executor_rehearsal import append_live_executor_rehearsal
from src.app.hammer_radar.operator.live_executor_transport import (
    append_live_executor_transport_attempt,
    attempt_live_executor_transport,
    check_live_executor_transport,
    list_live_executor_transport_attempts,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class LiveExecutorTransportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_transport_status_safe(self) -> None:
        payload = self.client.get("/live/executor/transport/status").json()

        self.assertEqual("R56", payload["phase"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])

    def test_missing_id_or_signal_blocks_attempt(self) -> None:
        payload = self.client.post("/live/executor/transport/attempt", json={}).json()

        self.assertEqual("REJECTED", payload["status"])
        self.assertFalse(payload["checks"]["id_or_signal_present"])
        self.assertFalse(payload["order_placed"])

    def test_mock_attempt_records_simulated_result(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_gate(rehearsal_id=rehearsal_id, intent_id=intent_id, signal_id=preview["latest_signal_id"]):
            payload = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="MOCK", log_dir=self.log_dir)

        self.assertEqual("MOCK_ATTEMPT_RECORDED", payload["status"])
        self.assertTrue(payload["simulated_order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertEqual(2, len(payload["protective_order_results"]))

    def test_dry_run_attempt_records_result(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_gate(rehearsal_id=rehearsal_id, intent_id=intent_id, signal_id=preview["latest_signal_id"]):
            payload = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="DRY_RUN", log_dir=self.log_dir)

        self.assertEqual("DRY_RUN_ATTEMPT_RECORDED", payload["status"])
        self.assertTrue(payload["dry_run_order_recorded"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_live_attempt_blocked_by_default(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_gate(rehearsal_id=rehearsal_id, intent_id=intent_id, signal_id=preview["latest_signal_id"]):
            payload = attempt_live_executor_transport(
                executor_rehearsal_id=rehearsal_id,
                transport_mode="LIVE",
                final_confirmation=True,
                dry_run=False,
                log_dir=self.log_dir,
                env={},
            )

        self.assertEqual("LIVE_BLOCKED", payload["status"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["real_order_placed"])

    def test_live_attempt_requires_final_confirmation(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_gate(rehearsal_id=rehearsal_id, intent_id=intent_id, signal_id=preview["latest_signal_id"], status="FINAL_CONFIRMATION_REQUIRED"):
            payload = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="LIVE", final_confirmation=False, log_dir=self.log_dir)

        self.assertEqual("LIVE_BLOCKED", payload["status"])
        self.assertIn("final confirmation is required for live transport", payload["blockers"])

    def test_live_attempt_requires_r55_gate_ready(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_gate(rehearsal_id=rehearsal_id, intent_id=intent_id, signal_id=preview["latest_signal_id"], status="BLOCKED"):
            payload = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="LIVE", final_confirmation=True, dry_run=False, log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("LIVE_BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["first_live_gate_ready"])

    def test_live_attempt_requires_kill_switch_off_and_live_connector(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_gate(rehearsal_id=rehearsal_id, intent_id=intent_id, signal_id=preview["latest_signal_id"]):
            kill = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="LIVE", final_confirmation=True, dry_run=False, log_dir=self.log_dir, env=dict(self._all_pass_env(), HAMMER_GLOBAL_KILL_SWITCH="true"))
            dry_run_only = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="LIVE", final_confirmation=True, dry_run=False, log_dir=self.log_dir, env=dict(self._all_pass_env(), HAMMER_BINANCE_CONNECTOR_MODE="DRY_RUN_ONLY"))

        self.assertEqual("LIVE_BLOCKED", kill["status"])
        self.assertFalse(kill["checks"]["global_kill_switch_off"])
        self.assertEqual("LIVE_BLOCKED", dry_run_only["status"])
        self.assertFalse(dry_run_only["checks"]["connector_mode_allows_live"])

    def test_live_attempt_requires_protective_orders_ready(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_gate(rehearsal_id=rehearsal_id, intent_id=intent_id, signal_id=preview["latest_signal_id"]):
            payload = attempt_live_executor_transport(
                executor_rehearsal_id=rehearsal_id,
                transport_mode="LIVE",
                final_confirmation=True,
                dry_run=False,
                log_dir=self.log_dir,
                env=dict(self._all_pass_env(), HAMMER_PROTECTIVE_ORDERS_ENABLED="false", HAMMER_PROTECTIVE_ORDER_MODE="PREVIEW_ONLY"),
            )

        self.assertEqual("LIVE_BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["protective_orders_ready"])

    def test_payload_results_are_sanitized(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)
        env = dict(self._all_pass_env(), BINANCE_API_KEY="secret-binance-key", BINANCE_API_SECRET="secret-binance-secret", TELEGRAM_BOT_TOKEN="secret-telegram-token")

        with self._patched_gate(rehearsal_id=rehearsal_id, intent_id=intent_id, signal_id=preview["latest_signal_id"]):
            payload = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="MOCK", log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertTrue(payload["protective_order_results"][0]["reduce_only"])
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)

    def test_idempotency_for_duplicate_attempts(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_gate(rehearsal_id=rehearsal_id, intent_id=intent_id, signal_id=preview["latest_signal_id"]):
            first = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="MOCK", log_dir=self.log_dir)
            second = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="MOCK", log_dir=self.log_dir)
        append_live_executor_transport_attempt(
            dict(
                first,
                transport_attempt_id="live-prior",
                status="LIVE_READY",
                transport_mode="LIVE",
                network_allowed=True,
                execution_attempted=True,
            ),
            log_dir=self.log_dir,
        )
        with self._patched_gate(rehearsal_id=rehearsal_id, intent_id=intent_id, signal_id=preview["latest_signal_id"]):
            live = attempt_live_executor_transport(executor_rehearsal_id=rehearsal_id, transport_mode="LIVE", final_confirmation=True, dry_run=False, log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual(first["transport_attempt_id"], second["transport_attempt_id"])
        self.assertEqual("LIVE_BLOCKED", live["status"])
        self.assertFalse(live["checks"]["idempotency_clear"])

    def test_api_endpoints(self) -> None:
        status_payload = self.client.get("/live/executor/transport/status").json()
        check_payload = self.client.post("/live/executor/transport/check", json={}).json()
        attempt_payload = self.client.post("/live/executor/transport/attempt", json={}).json()
        attempts_payload = self.client.get("/live/executor/transport/attempts").json()

        self.assertEqual("R56", status_payload["phase"])
        self.assertEqual("R56", check_payload["phase"])
        self.assertEqual("R56", attempt_payload["phase"])
        self.assertEqual("ACCEPTED", attempts_payload["result_status"])
        self.assertFalse(status_payload["order_placed"])
        self.assertFalse(attempt_payload["real_order_placed"])

    def test_telegram_commands_are_safe(self) -> None:
        transport = handle_telegram_operator_command(text="LIVE TRANSPORT", log_dir=self.log_dir)
        check = handle_telegram_operator_command(text="LIVE TRANSPORT CHECK", log_dir=self.log_dir)
        attempts = handle_telegram_operator_command(text="LIVE TRANSPORT ATTEMPTS", log_dir=self.log_dir)
        missing = handle_telegram_operator_command(text="LIVE TRANSPORT ATTEMPT", log_dir=self.log_dir)
        live_missing = handle_telegram_operator_command(text="LIVE TRANSPORT LIVE missing FINAL", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertIn(transport["result_status"], {"REJECTED", "BLOCKED"})
        self.assertIn(check["result_status"], {"REJECTED", "BLOCKED"})
        self.assertEqual("ACCEPTED", attempts["result_status"])
        self.assertEqual("REJECTED", missing["result_status"])
        self.assertEqual("LIVE_BLOCKED", live_missing["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_no_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = attempt_live_executor_transport(executor_rehearsal_id="missing", transport_mode="LIVE", final_confirmation=True, dry_run=False, log_dir=self.log_dir)

        self.assertEqual("LIVE_BLOCKED", payload["status"])
        self.assertFalse(payload["order_placed"])

    def _append_intent(self, preview: dict, *, status: str = "INTENT_READY") -> str:
        intent_id = f"intent-{preview['latest_signal_id']}-{status}"
        append_live_execution_intent(
            {
                "execution_intent_id": intent_id,
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "phase": "R52",
                "event_type": "live_execution_intent",
                "status": status,
                "signal_id": preview["latest_signal_id"],
                "preview_hash": compute_preview_hash(preview),
                "approval_status": "APPROVED",
                "live_begins_status": "ELIGIBLE_TINY_LIVE",
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

    def _append_rehearsal(self, preview: dict, intent_id: str, *, status: str = "REHEARSAL_READY") -> str:
        rehearsal_id = f"rehearsal-{preview['latest_signal_id']}-{status}"
        append_live_executor_rehearsal(
            {
                "executor_rehearsal_id": rehearsal_id,
                "created_at": datetime.now(UTC).isoformat(),
                "phase": "R53",
                "event_type": "live_executor_rehearsal",
                "execution_mode": "REHEARSAL_ONLY",
                "execution_intent_id": intent_id,
                "signal_id": preview["latest_signal_id"],
                "preview_hash": compute_preview_hash(preview),
                "status": status,
                "sequence": [{"step": 10, "name": "stop_before_network", "status": "READY", "network": False}],
                "entry_order_preview": {
                    "type": "LIMIT_PREVIEW",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "position_side": "LONG",
                    "margin_mode": "ISOLATED",
                    "quantity": 0.06,
                    "notional_usdt": 6.0,
                    "leverage": 1.0,
                    "reduce_only": False,
                    "preview_only": True,
                },
                "protective_orders_preview": preview["protective_orders_preview"],
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "network_allowed": False,
                "blockers": [],
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )
        return rehearsal_id

    def _patched_gate(self, *, rehearsal_id: str, intent_id: str, signal_id: str, status: str = "EXECUTION_GATE_READY"):
        return patch(
            "src.app.hammer_radar.operator.live_executor_transport.build_first_live_execution_gate",
            return_value={
                "status": status,
                "phase": "R55",
                "signal_id": signal_id,
                "execution_intent_id": intent_id,
                "executor_rehearsal_id": rehearsal_id,
                "gate_evaluation_id": "gate-r56",
                "live_begins_status": "ELIGIBLE_TINY_LIVE",
                "preview_status": "PREVIEW_READY",
                "intent_status": "INTENT_READY",
                "rehearsal_status": "REHEARSAL_READY",
                "arming_status": "ARMING_ALLOWED",
                "network_allowed": False,
                "order_placed": False,
                "real_order_placed": False,
                "secrets_shown": False,
            },
        )

    @staticmethod
    def _all_pass_env() -> dict[str, str]:
        return {
            "HAMMER_BINANCE_CONNECTOR_MODE": "LIVE_ORDER_ENABLED",
            "HAMMER_BINANCE_LIVE_ENABLED": "true",
            "HAMMER_LIVE_EXECUTION_ENABLED": "true",
            "HAMMER_ALLOW_LIVE_ORDERS": "true",
            "HAMMER_GLOBAL_KILL_SWITCH": "false",
            "HAMMER_PROTECTIVE_ORDERS_REQUIRED": "true",
            "HAMMER_PROTECTIVE_ORDERS_ENABLED": "true",
            "HAMMER_PROTECTIVE_ORDER_MODE": "LIVE_PROTECTIVE_ENABLED",
            "BINANCE_API_KEY": "present-key",
            "BINANCE_API_SECRET": "present-secret",
        }

    @staticmethod
    def _signal_id() -> str:
        return "BTCUSDT|13m|long|2026-05-06T10:00:00+00:00-r56"

    @staticmethod
    def _preview(signal_id: str) -> dict:
        return {
            "status": "PREVIEW_READY",
            "phase": "R51",
            "system": "money_printing_machine_hammer_radar",
            "execution_mode": "PREVIEW_ONLY",
            "latest_signal_id": signal_id,
            "symbol": "BTCUSDT",
            "timeframe": "13m",
            "direction": "long",
            "entry": 100.0,
            "stop": 95.0,
            "take_profit": 110.0,
            "order_side": "BUY",
            "position_side": "LONG",
            "margin_mode": "ISOLATED",
            "margin_usdt": 6.0,
            "leverage": 1.0,
            "notional_usdt": 6.0,
            "risk_usdt": 0.3,
            "quantity": 0.06,
            "min_notional_ok": True,
            "protective_orders_preview": {
                "stop_loss": {"trigger_price": 95.0, "side": "SELL", "reduce_only": True, "preview_only": True},
                "take_profit": {"trigger_price": 110.0, "side": "SELL", "reduce_only": True, "preview_only": True},
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
