from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_microscopic_live_attempt import (
    append_first_microscopic_live_attempt,
    check_first_microscopic_live_attempt,
    execute_first_microscopic_live_attempt,
)
from src.app.hammer_radar.operator.live_execution_intent import append_live_execution_intent, compute_preview_hash
from src.app.hammer_radar.operator.live_executor_rehearsal import append_live_executor_rehearsal
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class FirstMicroscopicLiveAttemptTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_profile_endpoint_returns_selected_profile(self) -> None:
        payload = self.client.get("/live/first-attempt/profile").json()

        self.assertEqual("R58", payload["phase"])
        self.assertEqual("BTCUSDT", payload["profile"]["symbol"])
        self.assertEqual(44.0, payload["profile"]["margin_usdt"])
        self.assertEqual(10, payload["profile"]["leverage"])
        self.assertEqual(444.0, payload["profile"]["max_notional_usdt"])
        self.assertEqual("ISOLATED", payload["profile"]["margin_mode"])
        self.assertEqual("LADDER", payload["profile"]["entry_mode"])
        self.assertTrue(payload["profile"]["one_attempt_only"])
        self.assertTrue(payload["profile"]["protective_orders_required"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_profile_sizing_valid_at_btc_81300(self) -> None:
        with patch("src.app.hammer_radar.operator.first_microscopic_live_attempt.build_live_execution_preview", return_value=self._preview(self._signal_id())):
            payload = self.client.get("/live/first-attempt/profile").json()

        sizing = payload["profile_status"]
        self.assertEqual(440.0, sizing["notional_usdt"])
        self.assertAlmostEqual(81.3, sizing["effective_min_notional_usdt"], places=2)
        self.assertEqual(0.005, sizing["quantity"])
        self.assertTrue(sizing["quantity_valid"])
        self.assertTrue(sizing["min_notional_ok"])
        self.assertTrue(sizing["notional_cap_ok"])
        self.assertTrue(sizing["sizing_valid"])

    def test_missing_id_or_signal_blocks_execute(self) -> None:
        payload = self.client.post("/live/first-attempt/execute", json={}).json()

        self.assertEqual("REJECTED", payload["status"])
        self.assertFalse(payload["checks"]["id_or_signal_present"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_dry_run_default_records_no_real_order(self) -> None:
        preview, intent_id, rehearsal_id = self._chain()
        with self._patched_upstream(preview=preview, intent_id=intent_id, rehearsal_id=rehearsal_id):
            payload = execute_first_microscopic_live_attempt(executor_rehearsal_id=rehearsal_id, log_dir=self.log_dir)

        self.assertEqual("DRY_RUN_RECORDED", payload["status"])
        self.assertTrue(payload["dry_run_order_recorded"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_mock_attempt_records_simulated_only(self) -> None:
        preview, intent_id, rehearsal_id = self._chain()
        with self._patched_upstream(preview=preview, intent_id=intent_id, rehearsal_id=rehearsal_id):
            payload = execute_first_microscopic_live_attempt(executor_rehearsal_id=rehearsal_id, transport_mode="MOCK", log_dir=self.log_dir)

        self.assertEqual("MOCK_RECORDED", payload["status"])
        self.assertTrue(payload["simulated_order_placed"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_live_attempt_blocked_by_default_env(self) -> None:
        preview, intent_id, rehearsal_id = self._chain()
        with self._patched_upstream(preview=preview, intent_id=intent_id, rehearsal_id=rehearsal_id):
            payload = execute_first_microscopic_live_attempt(
                executor_rehearsal_id=rehearsal_id,
                transport_mode="LIVE",
                final_confirmation=True,
                dry_run=False,
                log_dir=self.log_dir,
                env={},
            )

        self.assertEqual("LIVE_BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["live_env_allows"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["real_order_placed"])

    def test_live_attempt_requires_final_confirmation(self) -> None:
        preview, intent_id, rehearsal_id = self._chain()
        with self._patched_upstream(preview=preview, intent_id=intent_id, rehearsal_id=rehearsal_id):
            payload = execute_first_microscopic_live_attempt(
                executor_rehearsal_id=rehearsal_id,
                transport_mode="LIVE",
                final_confirmation=False,
                dry_run=True,
                log_dir=self.log_dir,
            )

        self.assertEqual("LIVE_BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["final_confirmation_present"])
        self.assertIn("final confirmation is required for live attempt", payload["blockers"])

    def test_live_attempt_requires_r50_to_r56_gates(self) -> None:
        preview, intent_id, rehearsal_id = self._chain()
        with self._patched_upstream(preview=preview, intent_id=intent_id, rehearsal_id=rehearsal_id, live_begins_status="BLOCKED"):
            payload = check_first_microscopic_live_attempt(executor_rehearsal_id=rehearsal_id, transport_mode="LIVE", log_dir=self.log_dir)

        self.assertFalse(payload["checks"]["r50_allows"])
        self.assertIn("R50 live-begins is BLOCKED", payload["blockers"])

    def test_profile_mismatch_and_cap_block(self) -> None:
        preview, intent_id, rehearsal_id = self._chain()
        with self._patched_upstream(preview=preview, intent_id=intent_id, rehearsal_id=rehearsal_id):
            mismatch = execute_first_microscopic_live_attempt(
                executor_rehearsal_id=rehearsal_id,
                profile={"margin_usdt": 45, "leverage": 10, "max_notional_usdt": 444, "margin_mode": "ISOLATED", "entry_mode": "LADDER"},
                log_dir=self.log_dir,
            )
            capped = execute_first_microscopic_live_attempt(
                executor_rehearsal_id=rehearsal_id,
                profile={"margin_usdt": 44, "leverage": 11, "max_notional_usdt": 444, "margin_mode": "ISOLATED", "entry_mode": "LADDER"},
                log_dir=self.log_dir,
            )

        self.assertEqual("BLOCKED", mismatch["status"])
        self.assertFalse(mismatch["checks"]["profile_matches_required"])
        self.assertEqual("BLOCKED", capped["status"])
        self.assertFalse(capped["checks"]["profile_notional_cap_ok"])

    def test_ladder_margin_is_total_cap(self) -> None:
        payload = self.client.get("/live/first-attempt/profile").json()

        self.assertTrue(payload["profile_status"]["ladder_mode_configured"])
        self.assertTrue(payload["profile_status"]["ladder_margin_is_total_cap"])
        self.assertEqual(44.0, payload["profile_status"]["ladder_margin_total_cap_usdt"])
        self.assertEqual(440.0, payload["profile_status"]["notional_usdt"])

    def test_protective_orders_required_for_live(self) -> None:
        preview, intent_id, rehearsal_id = self._chain()
        env = dict(self._all_pass_env(), HAMMER_PROTECTIVE_ORDERS_ENABLED="false", HAMMER_PROTECTIVE_ORDER_MODE="PREVIEW_ONLY")
        with self._patched_upstream(preview=preview, intent_id=intent_id, rehearsal_id=rehearsal_id):
            payload = execute_first_microscopic_live_attempt(
                executor_rehearsal_id=rehearsal_id,
                transport_mode="LIVE",
                final_confirmation=True,
                dry_run=False,
                log_dir=self.log_dir,
                env=env,
            )

        self.assertEqual("LIVE_BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["protective_orders_ready"])

    def test_duplicate_live_attempt_blocks(self) -> None:
        preview, intent_id, rehearsal_id = self._chain()
        append_first_microscopic_live_attempt(
            {
                "attempt_id": "prior-live",
                "phase": "R58",
                "event_type": "first_microscopic_live_attempt",
                "created_at": datetime.now(UTC).isoformat(),
                "status": "LIVE_READY",
                "signal_id": preview["latest_signal_id"],
                "executor_rehearsal_id": rehearsal_id,
                "transport_mode": "LIVE",
                "execution_attempted": True,
                "order_placed": False,
                "real_order_placed": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )
        with self._patched_upstream(preview=preview, intent_id=intent_id, rehearsal_id=rehearsal_id):
            payload = execute_first_microscopic_live_attempt(
                executor_rehearsal_id=rehearsal_id,
                transport_mode="LIVE",
                final_confirmation=True,
                dry_run=False,
                log_dir=self.log_dir,
                env=self._all_pass_env(),
            )

        self.assertEqual("LIVE_BLOCKED", payload["status"])
        self.assertFalse(payload["checks"]["one_attempt_only_clear"])

    def test_api_endpoints(self) -> None:
        profile = self.client.get("/live/first-attempt/profile").json()
        status = self.client.get("/live/first-attempt/status").json()
        check = self.client.post("/live/first-attempt/check", json={}).json()
        execute = self.client.post("/live/first-attempt/execute", json={}).json()
        attempts = self.client.get("/live/first-attempt/attempts").json()

        self.assertEqual("R58", profile["phase"])
        self.assertEqual("R58", status["phase"])
        self.assertEqual("R58", check["phase"])
        self.assertEqual("R58", execute["phase"])
        self.assertEqual("ACCEPTED", attempts["result_status"])
        self.assertFalse(execute["order_placed"])
        self.assertFalse(execute["real_order_placed"])

    def test_telegram_commands(self) -> None:
        preview, intent_id, rehearsal_id = self._chain()
        profile = handle_telegram_operator_command(text="FIRST LIVE PROFILE", log_dir=self.log_dir)
        status = handle_telegram_operator_command(text="FIRST LIVE STATUS", log_dir=self.log_dir)
        check = handle_telegram_operator_command(text="FIRST LIVE CHECK", log_dir=self.log_dir)
        missing = handle_telegram_operator_command(text="FIRST LIVE ATTEMPT", log_dir=self.log_dir)
        attempts = handle_telegram_operator_command(text="FIRST LIVE ATTEMPTS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)
        with self._patched_upstream(preview=preview, intent_id=intent_id, rehearsal_id=rehearsal_id):
            mock = handle_telegram_operator_command(text=f"FIRST LIVE MOCK {rehearsal_id}", log_dir=self.log_dir)
            dry_run = handle_telegram_operator_command(text=f"FIRST LIVE DRY RUN {rehearsal_id}", log_dir=self.log_dir)
            live = handle_telegram_operator_command(text=f"FIRST LIVE EXECUTE {rehearsal_id} FINAL", log_dir=self.log_dir)

        self.assertIn(profile["result_status"], {"PROFILE_READY", "BLOCKED"})
        self.assertIn(status["result_status"], {"BLOCKED", "LIVE_READY"})
        self.assertEqual("ACCEPTED", check["result_status"])
        self.assertEqual("REJECTED", missing["result_status"])
        self.assertEqual("ACCEPTED", attempts["result_status"])
        self.assertEqual("ACCEPTED", mock["result_status"])
        self.assertEqual("ACCEPTED", dry_run["result_status"])
        self.assertEqual("BLOCKED", live["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_secret_hygiene_and_no_binance_network(self) -> None:
        env = dict(
            self._all_pass_env(),
            BINANCE_API_KEY="secret-binance-key",
            BINANCE_API_SECRET="secret-binance-secret",
            TELEGRAM_BOT_TOKEN="secret-telegram-token",
        )
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = execute_first_microscopic_live_attempt(
                executor_rehearsal_id="missing",
                transport_mode="LIVE",
                final_confirmation=True,
                dry_run=False,
                log_dir=self.log_dir,
                env=env,
            )
        rendered = str(payload)

        self.assertIn(payload["status"], {"LIVE_BLOCKED", "REJECTED"})
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("secret-telegram-token", rendered)

    def _chain(self) -> tuple[dict, str, str]:
        preview = self._preview(self._signal_id())
        intent_id = f"intent-{preview['latest_signal_id']}"
        rehearsal_id = f"rehearsal-{preview['latest_signal_id']}"
        append_live_execution_intent(
            {
                "execution_intent_id": intent_id,
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "phase": "R52",
                "event_type": "live_execution_intent",
                "status": "INTENT_READY",
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
                "status": "REHEARSAL_READY",
                "entry_order_preview": {
                    "type": "LIMIT_PREVIEW",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "position_side": "LONG",
                    "margin_mode": "ISOLATED",
                    "quantity": 0.005,
                    "notional_usdt": 440.0,
                    "leverage": 10,
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
        return preview, intent_id, rehearsal_id

    def _patched_upstream(
        self,
        *,
        preview: dict,
        intent_id: str,
        rehearsal_id: str,
        live_begins_status: str = "ELIGIBLE_TINY_LIVE",
    ) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch("src.app.hammer_radar.operator.first_microscopic_live_attempt.build_live_execution_preview", return_value=preview))
        stack.enter_context(
            patch(
                "src.app.hammer_radar.operator.first_microscopic_live_attempt.build_live_begins_status",
                return_value={"status": live_begins_status, "latest_signal_id": preview["latest_signal_id"], "order_placed": False, "real_order_placed": False},
            )
        )
        stack.enter_context(
            patch(
                "src.app.hammer_radar.operator.first_microscopic_live_attempt.build_live_arming_status",
                return_value={"status": "ARMING_ALLOWED", "order_placed": False, "real_order_placed": False},
            )
        )
        stack.enter_context(
            patch(
                "src.app.hammer_radar.operator.first_microscopic_live_attempt.build_first_live_execution_gate",
                return_value={
                    "status": "EXECUTION_GATE_READY",
                    "signal_id": preview["latest_signal_id"],
                    "execution_intent_id": intent_id,
                    "executor_rehearsal_id": rehearsal_id,
                    "live_begins_status": live_begins_status,
                    "preview_status": "PREVIEW_READY",
                    "intent_status": "INTENT_READY",
                    "rehearsal_status": "REHEARSAL_READY",
                    "arming_status": "ARMING_ALLOWED",
                    "order_placed": False,
                    "real_order_placed": False,
                    "secrets_shown": False,
                },
            )
        )
        stack.enter_context(
            patch(
                "src.app.hammer_radar.operator.first_microscopic_live_attempt.check_live_executor_transport",
                return_value={
                    "status": "TRANSPORT_READY",
                    "signal_id": preview["latest_signal_id"],
                    "execution_intent_id": intent_id,
                    "executor_rehearsal_id": rehearsal_id,
                    "order_placed": False,
                    "real_order_placed": False,
                    "secrets_shown": False,
                },
            )
        )
        return stack

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
        return "BTCUSDT|4m|long|2026-05-06T21:15:59.999000+00:00-r58"

    @staticmethod
    def _preview(signal_id: str) -> dict:
        return {
            "status": "PREVIEW_READY",
            "phase": "R51",
            "system": "money_printing_machine_hammer_radar",
            "execution_mode": "PREVIEW_ONLY",
            "latest_signal_id": signal_id,
            "symbol": "BTCUSDT",
            "timeframe": "4m",
            "direction": "long",
            "entry": 81300.0,
            "stop": 80500.0,
            "take_profit": 83000.0,
            "order_side": "BUY",
            "position_side": "LONG",
            "margin_mode": "ISOLATED",
            "margin_usdt": 44.0,
            "leverage": 10,
            "notional_usdt": 440.0,
            "risk_usdt": 4.4,
            "quantity": 0.005,
            "min_notional_ok": True,
            "protective_orders_preview": {
                "stop_loss": {"trigger_price": 80500.0, "side": "SELL", "reduce_only": True, "preview_only": True},
                "take_profit": {"trigger_price": 83000.0, "side": "SELL", "reduce_only": True, "preview_only": True},
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
