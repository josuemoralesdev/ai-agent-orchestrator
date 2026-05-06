from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.live_arming_runbook import (
    build_live_arming_runbook,
    evaluate_and_record_live_arming_runbook,
    list_live_arming_runbooks,
)
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class LiveArmingRunbookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_default_runbook_safe(self) -> None:
        payload = build_live_arming_runbook(log_dir=self.log_dir, env={})

        self.assertIn(payload["status"], {"BLOCKED", "NOT_READY", "RUNBOOK_READY"})
        self.assertEqual("RUNBOOK_ONLY", payload["execution_mode"])
        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])

    def test_env_blockers_classified(self) -> None:
        payload = build_live_arming_runbook(log_dir=self.log_dir, env={})
        env_blockers = payload["blocker_summary"]["categories"]["env"]

        self.assertTrue(any("live_execution_enabled is false" in item for item in env_blockers))
        self.assertTrue(any("HAMMER_BINANCE_LIVE_ENABLED is false" in item for item in env_blockers))
        self.assertTrue(any("kill switch" in item for item in env_blockers))

    def test_protective_blocker_classified(self) -> None:
        payload = build_live_arming_runbook(log_dir=self.log_dir, env={})
        blockers = payload["blocker_summary"]["categories"]["protective_orders"]

        self.assertTrue(any("protective orders" in item for item in blockers))

    def test_sizing_blocker_classified(self) -> None:
        preview = self._preview(margin_usdt=4.44, leverage=1.0, entry=100000.0)
        with self._patched_chain(preview=preview):
            payload = build_live_arming_runbook(log_dir=self.log_dir, env=self._safe_env())

        blockers = payload["blocker_summary"]["categories"]["sizing"]
        self.assertTrue(any("notional is below min_notional" in item for item in blockers))
        self.assertTrue(any("quantity is invalid" in item for item in blockers))

    def test_approval_intent_rehearsal_blockers_classified(self) -> None:
        payload = build_live_arming_runbook(log_dir=self.log_dir, env={})
        categories = payload["blocker_summary"]["categories"]

        self.assertTrue(categories["approval"])
        self.assertTrue(categories["intent"])
        self.assertTrue(categories["rehearsal"])

    def test_sizing_suggestions(self) -> None:
        preview = self._preview(margin_usdt=4.44, leverage=1.0, entry=100000.0)
        with self._patched_chain(preview=preview):
            payload = build_live_arming_runbook(log_dir=self.log_dir, env=self._safe_env())

        sizing = payload["sizing_status"]
        self.assertEqual(5.0, sizing["suggested_min_margin_usdt"])
        self.assertEqual(2, sizing["suggested_min_leverage"])
        self.assertEqual("increase_margin_or_leverage", sizing["sizing_action"])

    def test_manual_runbook_present(self) -> None:
        payload = build_live_arming_runbook(log_dir=self.log_dir, env={})
        rendered = str(payload["manual_runbook"])

        self.assertIn("HAMMER_BINANCE_CONNECTOR_MODE", rendered)
        self.assertIn("HAMMER_GLOBAL_KILL_SWITCH=false", rendered)
        self.assertIn("hammer-approval-api.service", rendered)
        self.assertIn("/live/arming/status", rendered)
        self.assertIn("R58", rendered)

    def test_api_endpoints(self) -> None:
        status_payload = self.client.get("/live/arming/runbook").json()
        check_payload = self.client.post("/live/arming/runbook/check", json={}).json()
        list_payload = self.client.get("/live/arming/runbooks").json()

        self.assertEqual("R57", status_payload["phase"])
        self.assertEqual("R57", check_payload["phase"])
        self.assertEqual("ACCEPTED", list_payload["result_status"])
        self.assertGreaterEqual(list_payload["count"], 1)
        self.assertFalse(check_payload["order_placed"])
        self.assertFalse(list_payload["secrets_shown"])

    def test_telegram_commands(self) -> None:
        live_runbook = handle_telegram_operator_command(text="LIVE RUNBOOK", log_dir=self.log_dir)
        first_live_runbook = handle_telegram_operator_command(text="FIRST LIVE RUNBOOK", log_dir=self.log_dir)
        blockers = handle_telegram_operator_command(text="LIVE BLOCKERS", log_dir=self.log_dir)
        arming_runbook = handle_telegram_operator_command(text="LIVE ARMING RUNBOOK", log_dir=self.log_dir)
        runbooks = handle_telegram_operator_command(text="LIVE ARMING RUNBOOKS", log_dir=self.log_dir)
        raw_yes = handle_telegram_operator_command(text="YES", log_dir=self.log_dir)
        trade_now = handle_telegram_operator_command(text="trade now live", log_dir=self.log_dir)

        self.assertEqual("ACCEPTED", live_runbook["result_status"])
        self.assertEqual("ACCEPTED", first_live_runbook["result_status"])
        self.assertEqual("ACCEPTED", blockers["result_status"])
        self.assertEqual("ACCEPTED", arming_runbook["result_status"])
        self.assertEqual("ACCEPTED", runbooks["result_status"])
        self.assertEqual("REJECTED", raw_yes["result_status"])
        self.assertEqual("BLOCKED", trade_now["result_status"])
        self.assertFalse(trade_now["real_order_placed"])

    def test_secret_hygiene(self) -> None:
        env = {
            "TELEGRAM_BOT_TOKEN": "secret-telegram-token",
            "BINANCE_API_KEY": "secret-binance-key",
            "BINANCE_API_SECRET": "secret-binance-secret",
        }

        payload = build_live_arming_runbook(log_dir=self.log_dir, env=env)
        rendered = str(payload)

        self.assertFalse(payload["secrets_shown"])
        self.assertNotIn("secret-telegram-token", rendered)
        self.assertNotIn("secret-binance-key", rendered)
        self.assertNotIn("secret-binance-secret", rendered)
        self.assertNotIn("raw env", rendered.lower())

    def test_no_binance_network(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be called")):
            payload = build_live_arming_runbook(log_dir=self.log_dir, env={})

        self.assertFalse(payload["network_allowed"])
        self.assertFalse(payload["order_placed"])

    def _patched_chain(self, *, preview: dict):
        return _MultiContext(
            patch("src.app.hammer_radar.operator.live_arming_runbook.build_live_begins_status", return_value=self._live_begins()),
            patch("src.app.hammer_radar.operator.live_arming_runbook.build_live_execution_preview", return_value=preview),
            patch("src.app.hammer_radar.operator.live_arming_runbook.build_live_arming_status", return_value=self._arming()),
            patch("src.app.hammer_radar.operator.live_arming_runbook.build_first_live_execution_gate", return_value=self._gate()),
            patch("src.app.hammer_radar.operator.live_arming_runbook.check_live_executor_transport", return_value=self._transport()),
        )

    @staticmethod
    def _safe_env() -> dict[str, str]:
        return {
            "HAMMER_BINANCE_CONNECTOR_MODE": "DRY_RUN_ONLY",
            "HAMMER_PROTECTIVE_ORDERS_REQUIRED": "true",
            "HAMMER_PROTECTIVE_ORDERS_ENABLED": "false",
            "HAMMER_PROTECTIVE_ORDER_MODE": "PREVIEW_ONLY",
        }

    @staticmethod
    def _live_begins() -> dict:
        return {"status": "ELIGIBLE_TINY_LIVE", "latest_signal_id": "sig-r57", "approval_status": "MISSING", "blockers": []}

    @staticmethod
    def _arming() -> dict:
        return {"status": "BLOCKED", "intent_status": "MISSING", "rehearsal_status": "MISSING", "blockers": ["execution intent is MISSING", "executor rehearsal is MISSING"]}

    @staticmethod
    def _gate() -> dict:
        return {"status": "BLOCKED", "intent_status": "MISSING", "rehearsal_status": "MISSING", "blockers": ["first live gate rejected"]}

    @staticmethod
    def _transport() -> dict:
        return {"status": "REJECTED", "blockers": ["transport rejected"]}

    @staticmethod
    def _preview(*, margin_usdt: float = 4.44, leverage: float = 1.0, entry: float = 100000.0) -> dict:
        return {
            "status": "BLOCKED",
            "latest_signal_id": "sig-r57",
            "symbol": "BTCUSDT",
            "entry": entry,
            "margin_usdt": margin_usdt,
            "leverage": leverage,
            "notional_usdt": margin_usdt * leverage,
            "quantity": 0.0,
            "quantity_step": 0.001,
            "min_notional_ok": False,
            "blockers": ["notional is below min_notional", "quantity is invalid"],
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
