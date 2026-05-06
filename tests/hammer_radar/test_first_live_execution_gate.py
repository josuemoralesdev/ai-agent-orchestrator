from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_live_execution_gate import (
    append_first_live_execution_gate,
    build_first_live_execution_gate,
    evaluate_and_record_first_live_execution_gate,
    list_first_live_execution_gates,
)
from src.app.hammer_radar.operator.live_execution_intent import append_live_execution_intent, compute_preview_hash
from src.app.hammer_radar.operator.live_executor_rehearsal import append_live_executor_rehearsal
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstLiveExecutionGateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_gate_blocked(self) -> None:
        payload = build_first_live_execution_gate(log_dir=self.log_dir, env={})

        self.assertIn(payload["status"], {"BLOCKED", "REJECTED"})
        self.assertEqual("FIRST_LIVE_GATE", payload["execution_mode"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])
        self.assertTrue(payload["blockers"])

    def test_missing_id_or_signal_rejects(self) -> None:
        payload = self.client.post("/live/first-execution/gate", json={}).json()

        self.assertEqual("REJECTED", payload["status"])
        self.assertFalse(payload["checks"]["signal_or_intent_or_rehearsal_present"])
        self.assertFalse(payload["order_placed"])

    def test_final_confirmation_missing_blocks(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_all_pass(preview):
            payload = build_first_live_execution_gate(
                executor_rehearsal_id=rehearsal_id,
                final_confirmation=False,
                log_dir=self.log_dir,
                env=self._all_pass_env(),
            )

        self.assertEqual("FINAL_CONFIRMATION_REQUIRED", payload["status"])
        self.assertFalse(payload["checks"]["final_confirmation_present"])
        self.assertFalse(payload["order_placed"])

    def test_live_flags_disabled_block(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_all_pass(preview):
            payload = build_first_live_execution_gate(
                executor_rehearsal_id=rehearsal_id,
                final_confirmation=True,
                log_dir=self.log_dir,
                env={},
            )

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("live_execution_enabled is false", payload["blockers"])
        self.assertFalse(payload["real_order_placed"])

    def test_kill_switch_active_blocks(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)
        env = dict(self._all_pass_env(), HAMMER_GLOBAL_KILL_SWITCH="true")

        with self._patched_all_pass(preview):
            payload = build_first_live_execution_gate(
                executor_rehearsal_id=rehearsal_id,
                final_confirmation=True,
                log_dir=self.log_dir,
                env=env,
            )

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("global kill switch is active", payload["blockers"])

    def test_dry_run_only_blocks_live_network(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)
        env = dict(self._all_pass_env(), HAMMER_BINANCE_CONNECTOR_MODE="DRY_RUN_ONLY")

        with self._patched_all_pass(preview):
            payload = build_first_live_execution_gate(
                executor_rehearsal_id=rehearsal_id,
                final_confirmation=True,
                log_dir=self.log_dir,
                env=env,
            )

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["network_allowed"])
        self.assertIn("connector_mode is DRY_RUN_ONLY", payload["blockers"])

    def test_r54_arming_blocked_blocks_r55(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_live_begins(), self._patched_preview(preview), self._patched_arming(status="BLOCKED"):
            payload = build_first_live_execution_gate(
                executor_rehearsal_id=rehearsal_id,
                final_confirmation=True,
                log_dir=self.log_dir,
                env=self._all_pass_env(),
            )

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("BLOCKED", payload["arming_status"])

    def test_rehearsal_missing_or_blocked_blocks(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)

        with self._patched_all_pass(preview):
            missing = build_first_live_execution_gate(execution_intent_id=intent_id, final_confirmation=True, log_dir=self.log_dir, env=self._all_pass_env())
        self._append_rehearsal(preview, intent_id, status="BLOCKED")
        with self._patched_all_pass(preview):
            blocked = build_first_live_execution_gate(execution_intent_id=intent_id, final_confirmation=True, log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("MISSING", missing["rehearsal_status"])
        self.assertEqual("BLOCKED", blocked["rehearsal_status"])
        self.assertFalse(missing["order_placed"])

    def test_intent_missing_or_expired_blocks(self) -> None:
        preview = self._preview(self._signal_id())
        expired_intent = self._append_intent(preview, expires_at=datetime.now(UTC) - timedelta(minutes=1))
        rehearsal_id = self._append_rehearsal(preview, expired_intent)

        with self._patched_all_pass(preview):
            missing = build_first_live_execution_gate(execution_intent_id="missing", final_confirmation=True, log_dir=self.log_dir, env=self._all_pass_env())
            expired = build_first_live_execution_gate(executor_rehearsal_id=rehearsal_id, final_confirmation=True, log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("MISSING", missing["intent_status"])
        self.assertEqual("EXPIRED", expired["intent_status"])
        self.assertFalse(expired["real_order_placed"])

    def test_r51_and_r50_blocked_block(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)
        blocked_preview = dict(preview, status="BLOCKED")

        with self._patched_live_begins(status="BLOCKED"), self._patched_preview(preview), self._patched_arming():
            r50 = build_first_live_execution_gate(executor_rehearsal_id=rehearsal_id, final_confirmation=True, log_dir=self.log_dir, env=self._all_pass_env())
        with self._patched_live_begins(), self._patched_preview(blocked_preview), self._patched_arming():
            r51 = build_first_live_execution_gate(executor_rehearsal_id=rehearsal_id, final_confirmation=True, log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("BLOCKED", r50["status"])
        self.assertFalse(r50["checks"]["live_begins_allows_execution"])
        self.assertEqual("BLOCKED", r51["preview_status"])
        self.assertFalse(r51["checks"]["preview_ready"])

    def test_all_pass_returns_execution_gate_ready_without_order(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_all_pass(preview):
            payload = build_first_live_execution_gate(
                executor_rehearsal_id=rehearsal_id,
                final_confirmation=True,
                dry_run=True,
                log_dir=self.log_dir,
                env=self._all_pass_env(),
            )

        self.assertEqual("EXECUTION_GATE_READY", payload["status"])
        self.assertEqual("R55", payload["phase"])
        self.assertEqual("FIRST_LIVE_GATE", payload["execution_mode"])
        self.assertEqual(intent_id, payload["execution_intent_id"])
        self.assertEqual(rehearsal_id, payload["executor_rehearsal_id"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_idempotency_blocks_repeated_live_attempt(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)
        append_first_live_execution_gate(
            {
                "gate_evaluation_id": "prior",
                "phase": "R55",
                "event_type": "first_live_execution_gate",
                "status": "EXECUTION_GATE_READY",
                "created_at": datetime.now(UTC).isoformat(),
                "signal_id": preview["latest_signal_id"],
                "execution_intent_id": intent_id,
                "executor_rehearsal_id": rehearsal_id,
                "arming_status": "ARMING_ALLOWED",
                "final_confirmation": True,
                "dry_run": False,
                "network_allowed": True,
                "order_placed": True,
                "real_order_placed": False,
                "execution_attempted": True,
                "blockers": [],
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

        with self._patched_all_pass(preview):
            payload = build_first_live_execution_gate(executor_rehearsal_id=rehearsal_id, final_confirmation=True, log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["idempotency_clear"])
        self.assertFalse(payload["order_placed"])

    def test_payload_previews_present_and_sanitized(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_all_pass(preview):
            payload = build_first_live_execution_gate(executor_rehearsal_id=rehearsal_id, final_confirmation=True, log_dir=self.log_dir, env=self._all_pass_env())

        self.assertTrue(payload["entry_order_payload_preview"]["preview_only"])
        self.assertTrue(payload["protective_order_payloads_preview"]["stop_loss"]["preview_only"])
        self.assertTrue(payload["protective_order_payloads_preview"]["take_profit"]["reduce_only"])
        self.assertNotIn("secret-binance-key", str(payload))
        self.assertNotIn("secret-binance-secret", str(payload))

    def test_api_endpoints(self) -> None:
        status_payload = self.client.get("/live/first-execution/gate").json()
        check_payload = self.client.post("/live/first-execution/gate", json={}).json()
        gates_payload = self.client.get("/live/first-execution/gates").json()

        self.assertEqual("R55", status_payload["phase"])
        self.assertEqual("R55", check_payload["phase"])
        self.assertEqual("ACCEPTED", gates_payload["result_status"])
        self.assertFalse(status_payload["network_allowed"])
        self.assertFalse(check_payload["order_placed"])

    def test_list_endpoint_sanitized(self) -> None:
        evaluate_and_record_first_live_execution_gate(signal_id="missing", log_dir=self.log_dir)

        payload = list_first_live_execution_gates(log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", payload["result_status"])
        self.assertEqual("R55", payload["phase"])
        self.assertEqual(1, payload["count"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])

    def test_telegram_commands_are_safe(self) -> None:
        gate = handle_telegram_operator_command(text="FIRST LIVE GATE", log_dir=self.log_dir)
        execute_missing = handle_telegram_operator_command(text="FIRST LIVE EXECUTE", log_dir=self.log_dir)
        executions = handle_telegram_operator_command(text="FIRST LIVE EXECUTIONS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertIn(gate["result_status"], {"BLOCKED", "REJECTED", "FINAL_CONFIRMATION_REQUIRED"})
        self.assertEqual("REJECTED", execute_missing["result_status"])
        self.assertEqual("ACCEPTED", executions["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(gate["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_first_live_execute_final_remains_blocked_without_gates(self) -> None:
        payload = handle_telegram_operator_command(text="FIRST LIVE EXECUTE rehearsal-missing FINAL", log_dir=self.log_dir)

        self.assertEqual("BLOCKED", payload["result_status"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_secret_hygiene(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)
        env = dict(self._all_pass_env(), BINANCE_API_KEY="secret-binance-key", BINANCE_API_SECRET="secret-binance-secret", TELEGRAM_BOT_TOKEN="secret-telegram-token")

        with self._patched_all_pass(preview):
            payload = build_first_live_execution_gate(executor_rehearsal_id=rehearsal_id, final_confirmation=True, log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("raw env", rendered.lower())

    def test_no_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = build_first_live_execution_gate(log_dir=self.log_dir, env={})

        self.assertIn(payload["status"], {"BLOCKED", "REJECTED"})
        self.assertFalse(payload["order_placed"])

    def _append_intent(self, preview: dict, *, status: str = "INTENT_READY", expires_at: datetime | None = None) -> str:
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

    def _patched_all_pass(self, preview: dict):
        return _MultiContext(self._patched_live_begins(), self._patched_preview(preview), self._patched_arming())

    def _patched_live_begins(self, *, status: str = "ELIGIBLE_TINY_LIVE"):
        return patch(
            "src.app.hammer_radar.operator.first_live_execution_gate.build_live_begins_status",
            return_value={"status": status, "latest_signal_id": self._signal_id(), "freshness_status": "fresh"},
        )

    def _patched_preview(self, preview: dict):
        return patch("src.app.hammer_radar.operator.first_live_execution_gate.build_live_execution_preview", return_value=preview)

    def _patched_arming(self, *, status: str = "ARMING_ALLOWED"):
        return patch(
            "src.app.hammer_radar.operator.first_live_execution_gate.build_live_arming_status",
            return_value={
                "status": status,
                "latest_signal_id": self._signal_id(),
                "latest_execution_intent_id": f"intent-{self._signal_id()}-INTENT_READY",
                "latest_executor_rehearsal_id": f"rehearsal-{self._signal_id()}-REHEARSAL_READY",
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
        return "BTCUSDT|13m|long|2026-05-06T10:00:00+00:00-r55"

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


class _MultiContext:
    def __init__(self, *contexts):
        self.contexts = contexts

    def __enter__(self):
        for context in self.contexts:
            context.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        for context in reversed(self.contexts):
            context.__exit__(exc_type, exc, tb)
        return False


if __name__ == "__main__":
    unittest.main()
