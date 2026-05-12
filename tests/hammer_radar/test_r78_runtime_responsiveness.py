from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.execution.binance_futures_connector import append_connector_attempt
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.first_live_protective_adapter import append_first_live_protective_check
from src.app.hammer_radar.operator.live_execution_intent import append_live_execution_intent, live_execution_intents_path
from src.app.hammer_radar.operator.live_executor_rehearsal import append_live_executor_rehearsal
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.rehearsal_test_order_protective_readiness import (
    build_rehearsal_test_order_protective_check,
    build_rehearsal_test_order_protective_status,
    read_recent_ndjson,
)
from src.app.hammer_radar.operator.telegram_operator_bridge import handle_telegram_operator_command


class R78RuntimeResponsivenessTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)
        self.env_patch = patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(self.log_dir)}, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)
        self.signal_id = "BTCUSDT|13m|long|2026-05-12T10:00:00+00:00"
        self.intent_id = "intent-r781"
        self.rehearsal_id = "rehearsal-r781"

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_r78_status_fast_payload(self) -> None:
        payload = build_rehearsal_test_order_protective_status(log_dir=self.log_dir, env={})

        self.assertEqual("fast", payload["performance"]["mode"])
        self.assertIn("duration_ms", payload["performance"])
        self.assertTrue(payload["performance"]["bounded_scans"])
        self.assertEqual(500, payload["performance"]["max_lines_per_file"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["execution_attempted"])

    def test_r78_status_compact_by_default(self) -> None:
        payload = self.client.get("/live/rehearsal-readiness/status").json()
        encoded = json.dumps(payload, sort_keys=True)

        self.assertEqual("fast", payload["performance"]["mode"])
        self.assertLess(len(encoded), 12000)
        self.assertNotIn("first_live_profile", payload.get("funding_balance_status", {}))
        self.assertNotIn("execution_env", payload.get("funding_balance_status", {}))

    def test_r78_check_fast(self) -> None:
        started = time.perf_counter()
        payload = self.client.post("/live/rehearsal-readiness/check", json={}).json()
        elapsed_ms = (time.perf_counter() - started) * 1000

        self.assertLess(elapsed_ms, 1000)
        self.assertEqual("fast", payload["performance"]["mode"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_missing_logs_fast(self) -> None:
        started = time.perf_counter()
        payload = build_rehearsal_test_order_protective_status(log_dir=self.log_dir, env={})

        self.assertLess((time.perf_counter() - started) * 1000, 1000)
        self.assertEqual("AWAITING_CHAIN", payload["status"])
        self.assertFalse(payload["order_placed"])

    def test_large_ndjson_is_bounded(self) -> None:
        path = live_execution_intents_path(self.log_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for index in range(2000):
                handle.write(json.dumps({"index": index, "status": "OLD"}) + "\n")

        records = read_recent_ndjson(path, max_lines=7)
        payload = build_rehearsal_test_order_protective_status(log_dir=self.log_dir, env={})

        self.assertEqual(7, len(records))
        self.assertEqual(1999, records[0]["index"])
        self.assertTrue(payload["performance"]["bounded_scans"])
        self.assertEqual(500, payload["performance"]["max_lines_per_file"])

    def test_slow_heavy_builder_is_skipped_in_fast_mode(self) -> None:
        self._append_intent()
        self._append_rehearsal()
        self._append_test_order_validated()

        def slow_builder(**_: object) -> dict:
            raise AssertionError("fast R78 must not call heavy protective builder")

        with patch(
            "src.app.hammer_radar.operator.rehearsal_test_order_protective_readiness.build_first_live_protective_status",
            side_effect=slow_builder,
        ):
            payload = build_rehearsal_test_order_protective_status(log_dir=self.log_dir, env={})

        self.assertEqual("fast", payload["performance"]["mode"])
        self.assertTrue(payload["performance"]["heavy_builders_skipped"])
        self.assertIn(payload["status"], {"READY_FOR_PROTECTIVE_REVIEW", "READY_FOR_FINAL_MANUAL_GATE"})
        self.assertFalse(payload["order_placed"])

    def test_first_live_next_preserves_fast_performance(self) -> None:
        payload = handle_telegram_operator_command(text="FIRST LIVE NEXT", log_dir=self.log_dir)

        self.assertEqual("first_live_next", payload["normalized_action"])
        self.assertEqual("ACCEPTED", payload["result_status"])
        self.assertEqual("fast", payload["performance"]["mode"])
        self.assertIn("duration_ms", payload["performance"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])

    def test_operator_performance_endpoint(self) -> None:
        payload = self.client.get("/live/operator-performance/status").json()

        self.assertEqual("OK", payload["status"])
        self.assertEqual("R78.1", payload["phase"])
        self.assertFalse(payload["order_placed"])
        self.assertFalse(payload["real_order_placed"])
        self.assertFalse(payload["secrets_shown"])

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
                "preview_hash": "preview-r781",
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
                "preview_hash": "preview-r781",
                "execution_mode": "REHEARSAL_ONLY",
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": False,
                "network_allowed": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _append_test_order_validated(self) -> None:
        append_connector_attempt(
            {
                "attempt_id": "test-order-r781",
                "created_at": datetime.now(UTC).isoformat(),
                "endpoint": "test_order",
                "action": "test_order",
                "signal_id": self.signal_id,
                "status": "TEST_ORDER_MOCK_VALIDATED",
                "order_placed": False,
                "real_order_placed": False,
                "execution_attempted": True,
                "network_used": False,
                "secrets_shown": False,
            },
            log_dir=self.log_dir,
        )

    def _append_protective_ready_check(self) -> None:
        append_first_live_protective_check(
            {
                "check_id": "protective-r781",
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
