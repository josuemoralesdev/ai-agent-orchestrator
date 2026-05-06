from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.live_arming_checklist import (
    build_live_arming_status,
    evaluate_and_record_live_arming_check,
    list_live_arming_checks,
)
from src.app.hammer_radar.operator.live_execution_intent import append_live_execution_intent, compute_preview_hash
from src.app.hammer_radar.operator.live_executor_rehearsal import append_live_executor_rehearsal
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class LiveArmingChecklistTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_arming_blocked(self) -> None:
        payload = build_live_arming_status(log_dir=self.log_dir, env={})

        self.assertIn(payload["status"], {"BLOCKED", "NOT_READY"})
        self.assertEqual("ARMING_CHECK_ONLY", payload["execution_mode"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["secrets_shown"])
        self.assertTrue(payload["blockers"])

    def test_live_flags_disabled_block(self) -> None:
        preview = self._preview(self._signal_id())
        with self._patched_live_begins(), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env={})

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("live_execution_enabled is false", payload["blockers"])
        self.assertIn("HAMMER_BINANCE_LIVE_ENABLED is false", payload["blockers"])
        self.assertFalse(payload["order_placed"])

    def test_kill_switch_active_blocks(self) -> None:
        env = dict(self._all_pass_env(), HAMMER_GLOBAL_KILL_SWITCH="true")
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        self._append_rehearsal(preview, intent_id)

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env=env)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertIn("global kill switch is active", payload["blockers"])
        self.assertFalse(payload["real_order_placed"])

    def test_missing_binance_credentials_block(self) -> None:
        env = dict(self._all_pass_env())
        env.pop("BINANCE_API_KEY")
        env.pop("BINANCE_API_SECRET")
        preview = self._preview(self._signal_id())

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env=env)

        self.assertFalse(payload["binance_key_present"])
        self.assertFalse(payload["binance_secret_present"])
        self.assertIn("Binance API key and secret presence is required", payload["blockers"])
        self.assertNotIn("secret-binance-key", str(payload))

    def test_protective_orders_not_ready_block(self) -> None:
        env = dict(self._all_pass_env(), HAMMER_PROTECTIVE_ORDERS_ENABLED="false", HAMMER_PROTECTIVE_ORDER_MODE="PREVIEW_ONLY")
        preview = self._preview(self._signal_id())

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env=env)

        self.assertEqual("BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["protective_orders_ready"])
        self.assertTrue(any("protective orders are required but not ready" in blocker for blocker in payload["blockers"]))

    def test_r50_blocked_blocks_arming(self) -> None:
        preview = self._preview(self._signal_id())
        with self._patched_live_begins(status="BLOCKED"), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("BLOCKED", payload["live_begins_status"])
        self.assertFalse(payload["checks"]["live_begins_allows_arming"])

    def test_r51_preview_blocked_blocks_arming(self) -> None:
        preview = dict(self._preview(self._signal_id()), status="BLOCKED")
        with self._patched_live_begins(), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("BLOCKED", payload["preview_status"])
        self.assertFalse(payload["checks"]["preview_ready"])

    def test_missing_r52_intent_blocks(self) -> None:
        preview = self._preview(self._signal_id())
        with self._patched_live_begins(), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("MISSING", payload["intent_status"])
        self.assertIn("execution intent is MISSING", payload["blockers"])

    def test_expired_r52_intent_blocks(self) -> None:
        preview = self._preview(self._signal_id())
        self._append_intent(preview, expires_at=datetime.now(UTC) - timedelta(minutes=1))

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("EXPIRED", payload["intent_status"])

    def test_missing_r53_rehearsal_blocks(self) -> None:
        preview = self._preview(self._signal_id())
        self._append_intent(preview)

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("MISSING", payload["rehearsal_status"])
        self.assertIn("executor rehearsal is MISSING", payload["blockers"])

    def test_rehearsal_not_ready_blocks(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        self._append_rehearsal(preview, intent_id, status="BLOCKED")

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("BLOCKED", payload["status"])
        self.assertNotEqual("REHEARSAL_READY", payload["rehearsal_status"])
        self.assertFalse(payload["order_placed"])

    def test_all_pass_returns_arming_allowed(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        rehearsal_id = self._append_rehearsal(preview, intent_id)

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env=self._all_pass_env())

        self.assertEqual("ARMING_ALLOWED", payload["status"])
        self.assertEqual(intent_id, payload["latest_execution_intent_id"])
        self.assertEqual(rehearsal_id, payload["latest_executor_rehearsal_id"])
        self.assertTrue(payload["checks"]["operator_final_arm_required"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["blockers"])

    def test_api_endpoints_return_json_and_record_check(self) -> None:
        status_payload = self.client.get("/live/arming/status").json()
        check_payload = self.client.post("/live/arming/check", json={}).json()
        checks_payload = self.client.get("/live/arming/checks").json()

        self.assertEqual("R54", status_payload["phase"])
        self.assertEqual("R54", check_payload["phase"])
        self.assertEqual("ACCEPTED", checks_payload["result_status"])
        self.assertFalse(status_payload["order_placed"])
        self.assertFalse(check_payload["real_order_placed"])
        self.assertGreaterEqual(checks_payload["count"], 1)

    def test_list_endpoint_filters_sanitized_checks(self) -> None:
        evaluate_and_record_live_arming_check(log_dir=self.log_dir, env={})

        payload = list_live_arming_checks(log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", payload["result_status"])
        self.assertEqual("R54", payload["phase"])
        self.assertEqual(1, payload["count"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])

    def test_telegram_commands_are_safe(self) -> None:
        live_arming = handle_telegram_operator_command(text="LIVE ARMING", log_dir=self.log_dir)
        first_live_arming = handle_telegram_operator_command(text="FIRST LIVE ARMING", log_dir=self.log_dir)
        checks = handle_telegram_operator_command(text="LIVE ARMING CHECKS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertIn(live_arming["result_status"], {"BLOCKED", "NOT_READY", "ACCEPTED"})
        self.assertIn(first_live_arming["result_status"], {"BLOCKED", "NOT_READY", "ACCEPTED"})
        self.assertEqual("ACCEPTED", checks["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(live_arming["order_placed"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_secret_hygiene(self) -> None:
        preview = self._preview(self._signal_id())
        intent_id = self._append_intent(preview)
        self._append_rehearsal(preview, intent_id)
        env = dict(
            self._all_pass_env(),
            TELEGRAM_BOT_TOKEN="secret-telegram-token",
            BINANCE_API_KEY="secret-binance-key",
            BINANCE_API_SECRET="secret-binance-secret",
        )

        with self._patched_live_begins(), self._patched_preview(preview):
            payload = build_live_arming_status(log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertFalse(payload["secrets_shown"])
        self.assertTrue(payload["telegram_token_present"])
        self.assertTrue(payload["binance_key_present"])
        self.assertTrue(payload["binance_secret_present"])
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("raw env", rendered.lower())

    def test_arming_does_not_call_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = build_live_arming_status(log_dir=self.log_dir, env={})

        self.assertIn(payload["status"], {"BLOCKED", "NOT_READY"})
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
                "entry_order_preview": {"symbol": "BTCUSDT", "preview_only": True, "reduce_only": False},
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

    def _patched_live_begins(self, *, status: str = "ELIGIBLE_TINY_LIVE"):
        return patch(
            "src.app.hammer_radar.operator.live_arming_checklist.build_live_begins_status",
            return_value={
                "status": status,
                "latest_signal_id": self._signal_id(),
                "freshness_status": "fresh",
                "order_placed": False,
                "real_order_placed": False,
                "secrets_shown": False,
            },
        )

    def _patched_preview(self, preview: dict):
        return patch(
            "src.app.hammer_radar.operator.live_arming_checklist.build_live_execution_preview",
            return_value=preview,
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
        return "BTCUSDT|13m|long|2026-05-06T10:00:00+00:00-r54"

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
